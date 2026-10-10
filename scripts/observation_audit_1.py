"""OBSERVATION-AUDIT-1: read-only replay of collected Power.log files for two hidden mechanics.

Each complete single-game log is replayed packet by packet with the same hslog exporter the LIVE reducer
uses. At every ``Options`` packet (a decision point) the Ruby Sanctum heal-to-damage state and the SELF
Quest state are read from already-applied packets only. Later packets are used solely to check those
predictions. Raw logs are never modified; the output contains counts and hashed match keys only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from hearthstone.enums import BlockType, CardType, GameTag, Zone
from hslog import LogParser
from hslog.packets import Block, Options, SubSpell

from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games
from manamind.integrations.powerlog.visible_state import infer_local_player_id
from manamind.live.reducer import PacketExporter, preorder, quiet_parser

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
EXPECTED_CATALOG = "c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34"
SANCTUM, SANCTUM_EFFECT = "CATA_301", "CATA_301e"
# Targeted pure heals: pinned text starts with "Restore #N Health", plus the Priest hero power whose
# +2 restore CONSEQUENCE-PILOT-1 verified from outcomes (hero powers are not in the pinned catalog).
OBSERVED_HEAL_HERO_POWERS = frozenset({"HERO_09bp", "HERO_09dbp"})
ACTIVE, INACTIVE, UNKNOWN = "ACTIVE", "INACTIVE", "UNKNOWN"
CHOSEN_ENTITY = re.compile(r"m_chosenEntities\[\d+\]=\[.*player=(\d+)\]\s*$")
GAME_STATE_LINE = re.compile(r"^[DWE] \S+ GameState\.\w+\(\) - ")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tag(entity, name: GameTag):
    return entity.tags.get(name) if entity is not None else None


def cards(game) -> list:
    """Card entities only (the Game and Player entities carry no card identity)."""
    return [entity for entity in game.entities if hasattr(entity, "card_id")]


def by_id(game, entity_id):
    return game.find_entity_by_id(entity_id) if entity_id else None


def sanctum_state(game, player) -> dict:
    """ACTIVE / INACTIVE only when the player flag and the attached enchantment agree; never from absence of
    the location. A never-set tag in a log replayed from CREATE_GAME is the game default 0."""
    flag = tag(player, GameTag.HEALING_DOES_DAMAGE)
    effects = [e for e in cards(game) if e.card_id == SANCTUM_EFFECT and e.zone == Zone.PLAY
               and tag(e, GameTag.ATTACHED) == player.id]
    locations = [e for e in cards(game) if e.card_id == SANCTUM and e.zone == Zone.PLAY
                 and e.controller == player]
    if flag == 1 and effects:
        state = ACTIVE
    elif not flag and not effects:
        state = INACTIVE
    else:
        state = UNKNOWN
    return {"state": state, "flag": flag, "effects": len(effects), "location_in_play": bool(locations),
            "location_on_cooldown": any(tag(e, GameTag.LOCATION_ACTION_COOLDOWN) for e in locations)}


def quests(game, player) -> dict[int, dict]:
    return {e.id: {"card_id": e.card_id or None, "progress": tag(e, GameTag.QUEST_PROGRESS),
                   "total": tag(e, GameTag.QUEST_PROGRESS_TOTAL)}
            for e in cards(game) if e.zone == Zone.SECRET and e.controller == player
            and tag(e, GameTag.QUEST) == 1}


def secrets_without_quest(game, player) -> list:
    return [e for e in cards(game) if e.zone == Zone.SECRET and e.controller == player
            and tag(e, GameTag.QUEST) != 1]


def health(entity) -> int | None:
    if entity is None or tag(entity, GameTag.HEALTH) is None:
        return None
    return tag(entity, GameTag.HEALTH) - (tag(entity, GameTag.DAMAGE) or 0) + (tag(entity, GameTag.ARMOR) or 0)


class Replay:
    def __init__(self, tree, self_id: int, records: dict, labeled: set[str], key: str):
        self.game = None
        self.exporter = PacketExporter(tree)
        self.self_id, self.records, self.labeled, self.key = self_id, records, labeled, key
        self.decision = None
        self.last_quests = self.last_sanctum = None
        self.first_progress = Counter()
        self.decisions, self.actions, self.effect_life = [], [], {}
        self.tree = tree

    @property
    def me(self):
        return next(p for p in self.exporter.game.players if p.tags.get(GameTag.PLAYER_ID) == self.self_id)

    @property
    def them(self):
        return next(p for p in self.exporter.game.players if p.tags.get(GameTag.PLAYER_ID) != self.self_id)

    def run(self) -> None:
        with quiet_parser():
            self.walk(self.tree.packets, 0)

    def walk(self, packets, depth: int) -> None:
        for packet in packets:
            if isinstance(packet, Options):
                self.on_options(packet)
            action = (depth == 0 and isinstance(packet, Block) and packet.type in (BlockType.PLAY, BlockType.ATTACK)
                      and self.decision is not None)
            before = self.capture(packet) if action else None
            self.exporter.export_packet(packet)
            if isinstance(packet, (Block, SubSpell)):
                self.walk(packet.packets, depth + 1)
            if action:
                self.on_action(packet, before, self.capture(packet))

    def quest_drift(self, game) -> bool:
        current = {k: v["progress"] for k, v in quests(game, self.me).items()}
        changed = self.last_quests is not None and any(
            k in self.last_quests and self.last_quests[k] != v for k, v in current.items())
        self.last_quests = current
        return changed

    def sanctum_drift(self, game) -> bool:
        current = sanctum_state(game, self.me)["state"]
        changed = self.last_sanctum is not None and self.last_sanctum != current
        self.last_sanctum = current
        return changed

    def turn(self) -> int | None:
        return tag(self.exporter.game, GameTag.TURN)

    def track_effects(self) -> None:
        """Sampled at decision points and after own actions; enough to see which turn an effect left play."""
        game = self.exporter.game
        for entity in cards(game):
            if entity.card_id != SANCTUM_EFFECT:
                continue
            life = self.effect_life.setdefault(entity.id, {"created_turn": self.turn(), "removed_turn": None,
                                                           "consumed_in_heal": False, "location_gone": False,
                                                           "consumed_by": None,
                                                           "self": entity.controller == self.me})
            if entity.zone == Zone.PLAY:
                if not any(e.card_id == SANCTUM and e.zone == Zone.PLAY and e.controller == entity.controller
                           for e in cards(game)):
                    life["location_gone"] = True
            elif life["removed_turn"] is None:
                life["removed_turn"] = self.turn()

    def on_options(self, packet) -> None:
        self.track_effects()
        game = self.exporter.game
        me, them = self.me, self.them
        hand = [e for e in cards(game) if e.zone == Zone.HAND and e.controller == me]
        own_secrets = secrets_without_quest(game, me)
        foe_secrets = secrets_without_quest(game, them)
        self.decision = {
            "decision_id": f"{self.key}:{packet.id}", "labeled": f"{self.key}:{packet.id}" in self.labeled,
            "turn": self.turn(), "sanctum": sanctum_state(game, me),
            "self_quests": quests(game, me), "opponent_quests": quests(game, them),
            "self_quest_ids_known": all(q["card_id"] for q in quests(game, me).values()),
            "opponent_quest_ids_known": all(q["card_id"] for q in quests(game, them).values()),
            "self_secret_ids_known": all(e.card_id for e in own_secrets), "self_secrets": len(own_secrets),
            "opponent_hidden_secret_ids_exposed": sum(bool(e.card_id) for e in foe_secrets
                                                      if tag(e, GameTag.SECRET) == 1),
            "opponent_public_secret_zone_cards": sum(bool(e.card_id) for e in foe_secrets
                                                     if tag(e, GameTag.SECRET) != 1),
            "opponent_secrets": sum(tag(e, GameTag.SECRET) == 1 for e in foe_secrets),
            "quest_changed_outside_own_actions": self.quest_drift(game),
            "sanctum_changed_outside_own_actions": self.sanctum_drift(game),
            "hand_contributors": {e.id: tag(e, GameTag.QUEST_CONTRIBUTOR) for e in hand},
            # Hidden cards that carry the hint would leak information if a projection ever read them.
            "opponent_hidden_cards_with_contributor_tag": sum(
                e.controller == them and e.zone in (Zone.HAND, Zone.DECK)
                and tag(e, GameTag.QUEST_CONTRIBUTOR) is not None for e in cards(game)),
            "self_deck_cards_with_contributor_tag": sum(
                e.controller == me and e.zone == Zone.DECK and tag(e, GameTag.QUEST_CONTRIBUTOR) is not None
                for e in cards(game)),
        }
        self.decisions.append(self.decision)

    def capture(self, packet) -> dict:
        game = self.exporter.game
        target = by_id(game, packet.target)
        return {"sanctum": sanctum_state(game, self.me), "target_health": health(target),
                "target_damage": tag(target, GameTag.DAMAGE),
                "target_zone": target.zone if target is not None else None,
                "self_quests": quests(game, self.me),
                "effects_in_play": {e.id for e in cards(game)
                                    if e.card_id == SANCTUM_EFFECT and e.zone == Zone.PLAY}}

    def on_action(self, packet, before: dict, after: dict) -> None:
        game = self.exporter.game
        source = by_id(game, packet.entity)
        self.track_effects()
        consumed = before["effects_in_play"] - after["effects_in_play"]
        for entity_id in consumed:
            self.effect_life[entity_id]["consumed_by"] = getattr(source, "card_id", None) or "UNKNOWN_SOURCE"
        if source is None or source.controller != self.me:
            return
        self.quest_drift(game)
        self.sanctum_drift(game)
        card = self.records.get(source.card_id, {})
        heal = packet.type == BlockType.PLAY and packet.target and (
            source.card_id in OBSERVED_HEAL_HERO_POWERS
            or re.match(r"Restore #\d+ Health", card.get("text") or ""))
        if heal:
            for entity_id in consumed:
                self.effect_life[entity_id]["consumed_in_heal"] = True
        progress, completed = {}, []
        for quest_id, quest in before["self_quests"].items():
            later = after["self_quests"].get(quest_id)
            if later is None:  # left the SECRET zone during this action
                completed.append(quest["card_id"])
            new = later["progress"] if later else quest["total"]
            progress[quest["card_id"]] = (new or 0) - (quest["progress"] or 0)
            if quest["progress"] is None and later and later["progress"] is not None:
                self.first_progress[later["progress"]] += 1
        self.actions.append({
            "decision_id": self.decision["decision_id"], "labeled": self.decision["labeled"],
            "source_card_id": source.card_id, "card_type": tag(source, GameTag.CARDTYPE),
            "spell_school": card.get("spellSchool"), "heal": bool(heal),
            "predicted": self.decision["sanctum"]["state"], "consumed": bool(consumed),
            "state_changed_between_decision_and_action": self.decision["sanctum"]["state"] != before["sanctum"]["state"],
            "target_delta": (None if before["target_health"] is None or after["target_health"] is None
                             else after["target_health"] - before["target_health"]),
            "target_left_play": before["target_zone"] == Zone.PLAY and after["target_zone"] != Zone.PLAY,
            "target_full_before": before["target_health"] is not None and not before["target_damage"],
            "contributor_tag": self.decision["hand_contributors"].get(source.id, "NOT_IN_HAND"),
            "quest_progress_delta": progress, "quest_completed": completed,
        })


def replay_segment(lines: list[str], records: dict, labeled: set[str]) -> tuple[str, Replay | None, str | None]:
    info = inspect_segment(lines)
    if info.start_key is None or info.mid_game_start or info.complete_index is None:
        return "", None, "INCOMPLETE_OR_MID_GAME"
    parser = LogParser()
    with quiet_parser():
        for line in lines[:info.complete_index + 1]:
            # Same routing as LiveSession: only GameState messages reach hslog (PowerTaskList repeats them).
            if GAME_STATE_LINE.match(line):
                parser.read_line(line)
        parser.flush()
    if len(parser.games) != 1:
        return info.start_key, None, "NOT_ONE_GAME"
    tree = parser.games[0]
    probe = PacketExporter(tree)
    with quiet_parser():
        for packet in preorder(tree.packets):
            probe.export_packet(packet)
    # LiveSession rule A: the side owning the entities the client sent in SendChoices (mulligan); rule B (hand
    # identities) must not disagree.
    chosen = {int(match.group(1)) for line in lines[:info.complete_index + 1]
              if "GameState.SendChoices()" in line and (match := CHOSEN_ENTITY.search(line))}
    try:
        by_hand = infer_local_player_id(probe.game)
    except ValueError:
        by_hand = None
    signals = {value for value in (*chosen, by_hand) if value is not None}
    if len(chosen) > 1 or len(signals) != 1:
        return info.start_key, None, "SELF_AMBIGUOUS"
    self_id = signals.pop()
    replay = Replay(tree, self_id, records, labeled, info.start_key)
    replay.run()
    return info.start_key, replay, None


def verdicts(replays: list[Replay]) -> dict:
    states = Counter()
    labeled_states = Counter()
    hidden_active = Counter()
    proxy = Counter()
    heal, heal_full, drift = Counter(), Counter(), Counter()
    state_shift = 0
    contradictions = []
    for replay in replays:
        for decision in replay.decisions:
            sanctum = decision["sanctum"]
            states[sanctum["state"]] += 1
            if decision["labeled"]:
                labeled_states[sanctum["state"]] += 1
                visible_guess = ACTIVE if sanctum["location_on_cooldown"] else INACTIVE
                proxy[(sanctum["state"], visible_guess)] += 1
            drift[decision["sanctum_changed_outside_own_actions"]] += 1
            if sanctum["state"] == ACTIVE and not sanctum["location_in_play"]:
                hidden_active[decision["labeled"]] += 1
        for action in replay.actions:
            if not action["heal"]:
                continue
            converted = action["consumed"] or (action["target_delta"] is not None and action["target_delta"] < 0)
            if action["predicted"] == UNKNOWN:
                verdict = "no_claim"
            elif action["target_delta"] is None and not action["consumed"]:
                verdict = "unobservable"
            else:
                verdict = "confirmed" if converted == (action["predicted"] == ACTIVE) else "contradicted"
            heal[(action["predicted"], verdict)] += 1
            heal_full[(action["predicted"], action["target_full_before"], verdict)] += 1
            state_shift += action["state_changed_between_decision_and_action"]
            if verdict == "contradicted":
                contradictions.append({"match": hashlib.sha256(replay.key.encode()).hexdigest()[:12],
                                       **{k: action[k] for k in ("source_card_id", "predicted", "consumed",
                                                                 "target_delta", "labeled")}})
    lives = [life for replay in replays for life in replay.effect_life.values()]
    return {
        "decision_states": dict(states), "labeled_decision_states": dict(labeled_states),
        "active_without_visible_location": {"all": sum(hidden_active.values()), "labeled": hidden_active[True]},
        "visible_cooldown_proxy_vs_log_state": [{"log_state": k[0], "cooldown_proxy": k[1], "count": n}
                                                 for k, n in sorted(proxy.items())],
        "heal_actions": [{"predicted": k[0], "verdict": k[1], "count": n} for k, n in sorted(heal.items())],
        "heal_actions_by_target_full": [{"predicted": k[0], "target_full_before": k[1], "verdict": k[2], "count": n}
                                        for k, n in sorted(heal_full.items(), key=str)],
        "heal_contradictions": contradictions,
        "state_changed_between_decision_and_heal_action": state_shift,
        "decisions_with_state_change_outside_own_actions": drift[True],
        "effect_lifecycles": {
            "instances": len(lives), "self": sum(life["self"] for life in lives),
            "matches_with_instances": sum(bool(replay.effect_life) for replay in replays),
            "matches_with_self_instances": sum(any(life["self"] for life in replay.effect_life.values())
                                               for replay in replays),
            "consumed_by_targeted_pure_heal": sum(life["consumed_in_heal"] for life in lives),
            "never_removed": sum(life["removed_turn"] is None for life in lives),
            "removed_during_action_by_source": dict(Counter(life["consumed_by"] for life in lives
                                                            if life["consumed_by"])),
            "removed_outside_any_action_after_turn_change": sum(
                life["removed_turn"] is not None and not life["consumed_by"]
                and life["removed_turn"] != life["created_turn"] for life in lives),
            "removed_outside_any_action_same_turn": sum(
                life["removed_turn"] is not None and not life["consumed_by"]
                and life["removed_turn"] == life["created_turn"] for life in lives),
            "outlived_its_location": sum(life["location_gone"] for life in lives)},
    }


def quest_verdicts(replays: list[Replay], records: dict) -> dict:
    parent = records["TLC_817"]["text"]
    holy_first = parent.index("Holy") < parent.index("Shadow")  # order of the two quests in the pinned text
    expected_school = {"TLC_817t": "HOLY" if holy_first else "SHADOW", "TLC_817t2": "SHADOW" if holy_first else "HOLY"}
    decisions = Counter()
    school_rule = Counter()
    contributor = Counter()
    completions = Counter()
    progress_without_own_spell = 0
    examples = []
    for replay in replays:
        for decision in replay.decisions:
            own = decision["self_quests"]
            decisions["with_self_quest"] += bool(own)
            decisions["self_quest_identity_known"] += bool(own) and decision["self_quest_ids_known"]
            decisions["self_quest_progress_tag_absent"] += sum(q["progress"] is None for q in own.values())
            decisions["self_quest_total_known"] += bool(own) and all(q["total"] for q in own.values())
            decisions["with_opponent_quest"] += bool(decision["opponent_quests"])
            decisions["opponent_quest_identity_known"] += bool(decision["opponent_quests"]) and decision[
                "opponent_quest_ids_known"]
            decisions["with_self_non_quest_secret"] += bool(decision["self_secrets"])
            decisions["self_secret_identity_known"] += bool(decision["self_secrets"]) and decision[
                "self_secret_ids_known"]
            decisions["with_opponent_secret"] += bool(decision["opponent_secrets"])
            decisions["opponent_hidden_secret_identities_exposed"] += decision["opponent_hidden_secret_ids_exposed"]
            decisions["opponent_public_secret_zone_card_observations"] += decision["opponent_public_secret_zone_cards"]
            decisions["self_quest_changed_outside_own_actions"] += decision["quest_changed_outside_own_actions"]
            decisions["opponent_hidden_cards_with_contributor_tag"] += decision[
                "opponent_hidden_cards_with_contributor_tag"]
            decisions["decisions_with_self_deck_contributor_tags"] += bool(decision[
                "self_deck_cards_with_contributor_tag"])
            decisions["labeled_with_self_quest"] += decision["labeled"] and bool(own)
        for action in replay.actions:
            deltas = action["quest_progress_delta"]
            if not deltas:
                continue
            moved = {card for card, delta in deltas.items() if delta > 0}
            for card in action["quest_completed"]:
                completions[card] += 1
            if action["card_type"] == CardType.SPELL:
                for card, school in expected_school.items():
                    if card in deltas and action["spell_school"] is None:
                        school_rule[("no_claim_school_not_in_pinned_catalog",
                                     "progress" if card in moved else "no_progress")] += 1
                    elif card in deltas:
                        predicted = action["spell_school"] == school
                        school_rule[("confirmed" if predicted == (card in moved) else "contradicted",
                                     "progress" if predicted else "no_progress")] += 1
                        if predicted != (card in moved) and len(examples) < 10:
                            examples.append({"quest": card, "source_card_id": action["source_card_id"],
                                             "spell_school": action["spell_school"], "delta": deltas[card]})
            elif moved:
                progress_without_own_spell += 1
            if action["contributor_tag"] != "NOT_IN_HAND":
                value = action["contributor_tag"]
                contributor[("tag_" + ("absent" if value is None else str(value)),
                             "progressed" if moved else "no_progress")] += 1
    decisions["matches_with_self_quest"] = sum(any(d["self_quests"] for d in r.decisions) for r in replays)
    decisions["distinct_self_quest_cards"] = len({q["card_id"] for r in replays for d in r.decisions
                                                  for q in d["self_quests"].values()})
    return {"decisions": dict(decisions), "dual_quest_school_mapping": expected_school,
            "completions_during_own_actions": dict(completions),
            "first_progress_value_after_absent_tag": dict(sum((r.first_progress for r in replays), Counter())),
            "school_rule_on_own_spells": [{"verdict": k[0], "predicted": k[1], "count": n}
                                          for k, n in sorted(school_rule.items())],
            "school_rule_contradiction_examples": examples,
            "progress_from_own_non_spell_actions": progress_without_own_spell,
            "quest_contributor_tag_vs_progress": [{"tag": k[0], "outcome": k[1], "count": n}
                                                  for k, n in sorted(contributor.items())]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw",
                        help="searched recursively; games are split and de-duplicated by their header key")
    parser.add_argument("--canonical", type=Path,
                        default=ROOT / "data/processed_data_checkpoint_1_20261010/canonical")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/observation_audit_1/results.json")
    args = parser.parse_args()
    if sha(CATALOG) != EXPECTED_CATALOG:
        raise ValueError("Pinned catalog identity mismatch")
    records = {card["id"]: card for card in json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]}
    labeled = {json.loads(line)["decision_id"] for path in sorted(args.canonical.glob("*.jsonl"))
               for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    replays, rejected, keys, segments = [], Counter(), set(), 0
    paths = sorted(args.raw.rglob("*.log"))
    for path in paths:
        for lines in split_games(read_complete_lines(path)):
            segments += 1
            key = inspect_segment(lines).start_key
            if key in keys:
                rejected["DUPLICATE_MATCH"] += 1
                continue
            key, replay, reason = replay_segment(lines, records, labeled)
            if replay is None:
                rejected[reason] += 1
                continue
            keys.add(key)
            replays.append(replay)
    canonical_games = {decision.split(":")[0] for decision in labeled}
    result = {
        "inputs": {"raw_log_files": len(paths), "game_segments": segments, "replayed_matches": len(replays),
                   "rejected": dict(rejected), "replayed_canonical_matches": len(keys & canonical_games),
                   "canonical_matches": len(canonical_games),
                   "decision_points": sum(len(r.decisions) for r in replays),
                   "labeled_decisions_matched": sum(d["labeled"] for r in replays for d in r.decisions),
                   "labeled_decisions_total": len(labeled), "self_actions": sum(len(r.actions) for r in replays),
                   "catalog_sha256": EXPECTED_CATALOG},
        "ruby_sanctum": verdicts(replays),
        "quests": quest_verdicts(replays, records),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")


if __name__ == "__main__":
    main()
