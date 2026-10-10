"""TACTICAL-DECISION-1: temporary SELF-only overlay read from Power.log at each decision point (offline only).

The production ``GameState`` and ``StateEncoder`` are untouched. The overlay is a separate, experimental
side channel with three facts that OBSERVATION-AUDIT-1 verified as reliable and that the dataset contract hides:

* ``healing_does_damage`` - Ruby Sanctum style "next Healing effect deals damage": ACTIVE only when the player
  flag and the attached ``CATA_301e`` enchantment agree, INACTIVE only when both are absent, otherwise UNKNOWN;
* ``quests`` - identity, progress and target of the player's own Quests (SECRET zone, ``QUEST=1``);
* ``hand_contributors`` - the client's ``QUEST_CONTRIBUTOR`` hint on cards in the player's own hand only.

Only packets applied before the ``Options`` packet are read. Opponent hidden zones are never inspected.
The packet-by-packet replay mirrors the LIVE reducer (``GameState.*`` lines only, same ``PacketExporter``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from hearthstone.enums import GameTag, Zone
from hslog import LogParser
from hslog.packets import Block, Options, SubSpell

from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games
from manamind.integrations.powerlog.visible_state import infer_local_player_id
from manamind.live.reducer import PacketExporter, preorder, quiet_parser

SANCTUM_EFFECT = "CATA_301e"
ACTIVE, INACTIVE, UNKNOWN = "ACTIVE", "INACTIVE", "UNKNOWN"
CHOSEN_ENTITY = re.compile(r"m_chosenEntities\[\d+\]=\[.*player=(\d+)\]\s*$")
GAME_STATE_LINE = re.compile(r"^[DWE] \S+ GameState\.\w+\(\) - ")


@dataclass(frozen=True, slots=True)
class QuestState:
    card_id: str
    progress: int  # an unset QUEST_PROGRESS tag is progress 0 (verified: the first value ever set is 1)
    total: int


@dataclass(frozen=True, slots=True)
class DecisionOverlay:
    decision_id: str
    healing_does_damage: str
    quests: tuple[QuestState, ...]
    hand_card_ids: tuple[str, ...]  # SELF hand in ZONE_POSITION order, for aligning with the dataset hand
    hand_contributors: tuple[int | None, ...]


def _tag(entity, name: GameTag):
    return entity.tags.get(name) if entity is not None else None


def _cards(game) -> list:
    return [entity for entity in game.entities if hasattr(entity, "card_id")]


def healing_state(game, player) -> str:
    flag = _tag(player, GameTag.HEALING_DOES_DAMAGE)
    effects = [e for e in _cards(game) if e.card_id == SANCTUM_EFFECT and e.zone == Zone.PLAY
               and _tag(e, GameTag.ATTACHED) == player.id]
    if flag == 1 and effects:
        return ACTIVE
    if not flag and not effects:
        return INACTIVE
    return UNKNOWN


def own_quests(game, player) -> tuple[QuestState, ...]:
    found = [e for e in _cards(game) if e.zone == Zone.SECRET and e.controller == player
             and _tag(e, GameTag.QUEST) == 1]
    return tuple(QuestState(e.card_id or "", _tag(e, GameTag.QUEST_PROGRESS) or 0,
                            _tag(e, GameTag.QUEST_PROGRESS_TOTAL) or 0) for e in sorted(found, key=lambda e: e.id))


def own_hand(game, player) -> list:
    hand = [e for e in _cards(game) if e.zone == Zone.HAND and e.controller == player]
    return sorted(hand, key=lambda e: (_tag(e, GameTag.ZONE_POSITION) or 0, e.id))


class _Walker:
    def __init__(self, tree, self_id: int, key: str):
        self.exporter = PacketExporter(tree)
        self.tree, self.self_id, self.key = tree, self_id, key
        self.overlays: dict[str, DecisionOverlay] = {}

    def run(self) -> None:
        with quiet_parser():
            self._walk(self.tree.packets)

    def _walk(self, packets) -> None:
        for packet in packets:
            if isinstance(packet, Options):
                self._on_options(packet)
            self.exporter.export_packet(packet)
            if isinstance(packet, (Block, SubSpell)):
                self._walk(packet.packets)

    def _on_options(self, packet) -> None:
        game = self.exporter.game
        me = next(p for p in game.players if p.tags.get(GameTag.PLAYER_ID) == self.self_id)
        hand = own_hand(game, me)
        decision_id = f"{self.key}:{packet.id}"
        self.overlays[decision_id] = DecisionOverlay(
            decision_id, healing_state(game, me), own_quests(game, me),
            tuple(e.card_id or "" for e in hand),
            tuple(_tag(e, GameTag.QUEST_CONTRIBUTOR) for e in hand))


def replay_overlays(lines: list[str]) -> tuple[str | None, dict[str, DecisionOverlay], str | None]:
    """Overlay per Options packet of one complete single-game log segment; (key, overlays, rejection reason)."""
    info = inspect_segment(lines)
    if info.start_key is None or info.mid_game_start or info.complete_index is None:
        return info.start_key, {}, "INCOMPLETE_OR_MID_GAME"
    parser = LogParser()
    with quiet_parser():
        for line in lines[:info.complete_index + 1]:
            if GAME_STATE_LINE.match(line):
                parser.read_line(line)
        parser.flush()
    if len(parser.games) != 1:
        return info.start_key, {}, "NOT_ONE_GAME"
    tree = parser.games[0]
    probe = PacketExporter(tree)
    with quiet_parser():
        for packet in preorder(tree.packets):
            probe.export_packet(packet)
    chosen = {int(m.group(1)) for line in lines[:info.complete_index + 1]
              if "GameState.SendChoices()" in line and (m := CHOSEN_ENTITY.search(line))}
    try:
        by_hand = infer_local_player_id(probe.game)
    except ValueError:
        by_hand = None
    signals = {value for value in (*chosen, by_hand) if value is not None}
    if len(chosen) > 1 or len(signals) != 1:
        return info.start_key, {}, "SELF_AMBIGUOUS"
    walker = _Walker(tree, signals.pop(), info.start_key)
    walker.run()
    return info.start_key, walker.overlays, None


def collect_overlays(raw_root: Path) -> tuple[dict[str, DecisionOverlay], dict]:
    """All unique complete matches under ``raw_root`` (searched recursively, de-duplicated by header key)."""
    overlays: dict[str, DecisionOverlay] = {}
    keys: set[str] = set()
    rejected: dict[str, int] = {}
    segments = 0
    paths = sorted(raw_root.rglob("*.log"))
    for path in paths:
        for lines in split_games(read_complete_lines(path)):
            segments += 1
            key = inspect_segment(lines).start_key
            if key in keys:
                rejected["DUPLICATE_MATCH"] = rejected.get("DUPLICATE_MATCH", 0) + 1
                continue
            key, found, reason = replay_overlays(lines)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            keys.add(key)
            overlays.update(found)
    return overlays, {"raw_log_files": len(paths), "game_segments": segments, "replayed_matches": len(keys),
                      "rejected": rejected}
