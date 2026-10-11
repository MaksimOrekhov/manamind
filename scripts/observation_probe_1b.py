"""Read-only probe: which missing facts can be recovered from past Power.log events, and do they predict outcomes?

Each complete single-game raw log is replayed packet by packet with the same hslog exporter the LIVE reducer
uses. At every ``Options`` packet (a decision point) a few SELF facts are read from already-applied packets
only; later packets are used solely to check them. Nothing hidden is read: only the SELF player, SELF hero,
SELF minions and SELF hand. Raw logs are never modified.

Candidate facts (the forecaster's open blockers, see reports/action_outcome_1b):
  hero Divine Shield, SELF hand-instance keywords, Spell Damage (+ the damage-doubling flag),
  healing bonus (+ the spell-healing-doubling flag), Ruby Sanctum state.

Output: a per-decision facts file (ignored data dir, no log lines or names) and a JSON of counters.
  python scripts/observation_probe_1b.py --raw <data/raw> --facts-out data/processed_observation_probe_1b/facts.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.enums import BlockType, CardType, GameTag, Zone  # noqa: E402
from hslog import LogParser  # noqa: E402
from hslog.packets import Block, Options, SubSpell  # noqa: E402

from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games  # noqa: E402
from manamind.integrations.powerlog.visible_state import infer_local_player_id  # noqa: E402
from manamind.live.reducer import PacketExporter, preorder, quiet_parser  # noqa: E402
from manamind.outcome import TextSource  # noqa: E402
from manamind.outcome.grammar import parse_text  # noqa: E402

CHOSEN = re.compile(r"m_chosenEntities\[\d+\]=\[.*player=(\d+)\]\s*$")
GAME_STATE_LINE = re.compile(r"^[DWE] \S+ GameState\.\w+\(\) - ")
SANCTUM, SANCTUM_EFFECT = "CATA_301", "CATA_301e"
KEYWORD_TAGS = {"taunt": GameTag.TAUNT, "divine_shield": GameTag.DIVINE_SHIELD, "lifesteal": GameTag.LIFESTEAL,
                "reborn": GameTag.REBORN, "charge": GameTag.CHARGE, "rush": GameTag.RUSH,
                "windfury": GameTag.WINDFURY, "stealth": GameTag.STEALTH, "poisonous": GameTag.POISONOUS}
BASE_MECHANIC = {"taunt": "TAUNT", "divine_shield": "DIVINE_SHIELD", "lifesteal": "LIFESTEAL", "reborn": "REBORN",
                 "charge": "CHARGE", "rush": "RUSH", "windfury": "WINDFURY", "stealth": "STEALTH",
                 "poisonous": "POISONOUS"}
HERO_HEAL_POWERS = {"HERO_09bp": 2, "HERO_09dbp": 2}      # Lesser Heal variants; hero powers are not in the catalog


def tag(entity, name):
    return entity.tags.get(name) if entity is not None else None


def cards(game):
    return [entity for entity in game.entities if hasattr(entity, "card_id")]


class Replay:
    def __init__(self, tree, self_id: int, key: str, texts: TextSource):
        self.tree, self.self_id, self.key, self.texts = tree, self_id, key, texts
        self.exporter = PacketExporter(tree)
        self.facts: list[dict] = []
        self.decision: dict | None = None
        self.checks: list[dict] = []

    @property
    def me(self):
        return next(p for p in self.exporter.game.players if p.tags.get(GameTag.PLAYER_ID) == self.self_id)

    def run(self) -> None:
        with quiet_parser():
            self.walk(self.tree.packets, 0)

    def walk(self, packets, depth: int) -> None:
        for packet in packets:
            if isinstance(packet, Options):
                self.on_options(packet)
            action = (depth == 0 and isinstance(packet, Block) and packet.type == BlockType.PLAY
                      and self.decision is not None)
            before = self.capture(packet) if action else None
            self.exporter.export_packet(packet)
            if isinstance(packet, (Block, SubSpell)):
                self.walk(packet.packets, depth + 1)
            if action:
                self.on_action(packet, before, self.capture(packet))

    # ----- facts read before a decision ----------------------------------------------------------------

    def hero(self, game, mine: bool = True):
        me = self.me
        return next((e for e in cards(game) if e.zone == Zone.PLAY and tag(e, GameTag.CARDTYPE) == CardType.HERO
                     and (e.controller == me) == mine), None)

    def sanctum(self, game) -> str:
        me = self.me
        flag = tag(me, GameTag.HEALING_DOES_DAMAGE)
        effects = [e for e in cards(game) if e.card_id == SANCTUM_EFFECT and e.zone == Zone.PLAY
                   and tag(e, GameTag.ATTACHED) == me.id]
        if flag == 1 and effects:
            return "ACTIVE"
        return "INACTIVE" if not flag and not effects else "UNKNOWN"

    def spell_power(self, game) -> dict:
        me = self.me
        minions = [e for e in cards(game) if e.zone == Zone.PLAY and e.controller == me
                   and tag(e, GameTag.CARDTYPE) == CardType.MINION]
        return {"current_sum": sum(tag(e, GameTag.CURRENT_SPELLPOWER) or 0 for e in minions),
                "printed_sum": sum(tag(e, GameTag.SPELLPOWER) or 0 for e in minions),
                "player_current": tag(me, GameTag.CURRENT_SPELLPOWER) or 0,
                "doubled": bool(tag(me, GameTag.SPELLPOWER_DOUBLE))}

    def healing(self, game) -> dict:
        me = self.me
        return {"bonus": tag(me, GameTag.CURRENT_HEALING_POWER) or 0,
                "spell_double": bool(tag(me, GameTag.SPELL_HEALING_DOUBLE)),
                "all_double": bool(tag(me, GameTag.ALL_HEALING_DOUBLE))}

    def on_options(self, packet) -> None:
        game = self.exporter.game
        me = self.me
        hero = self.hero(game)
        hand = sorted((e for e in cards(game) if e.zone == Zone.HAND and e.controller == me),
                      key=lambda e: tag(e, GameTag.ZONE_POSITION) or 0)
        self.decision = {
            "decision_id": f"{self.key}:{packet.id}",
            "hero_divine_shield": bool(tag(hero, GameTag.DIVINE_SHIELD)),
            "opponent_hero_divine_shield": bool(tag(self.hero(game, mine=False), GameTag.DIVINE_SHIELD)),
            "sanctum": self.sanctum(game),
            "spell_power": self.spell_power(game),
            "healing": self.healing(game),
            "hand": [{"card_id": e.card_id, "type": getattr(tag(e, GameTag.CARDTYPE), "name", None),
                      "keywords": sorted(name for name, t in KEYWORD_TAGS.items() if tag(e, t))}
                     for e in hand],
        }
        self.facts.append(self.decision)

    # ----- outcomes -----------------------------------------------------------------------------------

    def capture(self, packet) -> dict:
        game = self.exporter.game
        source = game.find_entity_by_id(packet.entity) if packet.entity else None
        target = game.find_entity_by_id(packet.target) if packet.target else None
        return {"damage": tag(target, GameTag.DAMAGE) or 0, "armor": tag(target, GameTag.ARMOR) or 0,
                "shield": bool(tag(target, GameTag.DIVINE_SHIELD)), "immune": bool(tag(target, GameTag.IMMUNE)),
                "zone": target.zone if target is not None else None,
                "health": tag(target, GameTag.HEALTH), "target_is_hero": tag(target, GameTag.CARDTYPE) == CardType.HERO,
                "source_tags": {name: bool(tag(source, t)) for name, t in KEYWORD_TAGS.items()},
                "source_zone": source.zone if source is not None else None,
                "opponent_secrets": sum(e.zone == Zone.SECRET and e.controller != self.me
                                        and tag(e, GameTag.SECRET) == 1 for e in cards(game)),
                "minions": {e.id: {"damage": tag(e, GameTag.DAMAGE) or 0, "shield": bool(tag(e, GameTag.DIVINE_SHIELD)),
                                   "immune": bool(tag(e, GameTag.IMMUNE)), "zone": e.zone,
                                   "mine": e.controller == self.me, "dormant": bool(tag(e, GameTag.DORMANT))}
                            for e in cards(game) if tag(e, GameTag.CARDTYPE) == CardType.MINION
                            and e.zone in (Zone.PLAY, Zone.GRAVEYARD)}}

    def on_action(self, packet, before: dict, after: dict) -> None:
        game = self.exporter.game
        source = game.find_entity_by_id(packet.entity) if packet.entity else None
        if source is None or source.controller != self.me:
            return
        decision = self.decision
        card_type = tag(source, GameTag.CARDTYPE)
        if card_type == CardType.MINION:
            hand_before = [h for h in decision["hand"] if h["card_id"] == source.card_id]
            if hand_before:
                kept = sorted(name for name, t in KEYWORD_TAGS.items() if after["source_tags"].get(name))
                entry = self.texts.get(source.card_id)
                base = sorted(name for name, mech in BASE_MECHANIC.items() if entry and mech in entry.mechanics)
                hand_kw = hand_before[0]["keywords"]
                self.checks.append({"kind": "minion_keywords", "card": source.card_id,
                                    "hand_equals_board": hand_kw == kept, "hand_equals_base": hand_kw == base,
                                    "ambiguous": len(hand_before) > 1 and len({tuple(h["keywords"]) for h in hand_before}) > 1})
            return
        entry = self.texts.get(source.card_id) if card_type == CardType.SPELL else None
        if card_type == CardType.SPELL and entry is not None:
            self.check_spell(entry, before, after, decision, source)
        elif card_type == CardType.HERO_POWER and source.card_id in HERO_HEAL_POWERS:
            self.check_heal(source, HERO_HEAL_POWERS[source.card_id], before, after, decision, hero_power=True)

    def check_spell(self, entry, before, after, decision, source) -> None:
        clauses = [c for c in parse_text(entry.text).clauses if c.kind not in ("KEYWORDS", "PREPARE", "COST_ONLY")]
        damage_all = [c for c in clauses if c.kind == "DAMAGE" and c.selector.mode == "ALL"]
        if len(damage_all) == 1 and all(c.kind in ("DAMAGE", "HEAL") for c in clauses):
            self.check_area_damage(source, damage_all[0], clauses, before, after, decision)
            return
        if len(clauses) != 1 or clauses[0].kind not in ("DAMAGE", "HEAL") or clauses[0].selector.mode != "CHOSEN":
            return
        clause = clauses[0]
        if clause.kind == "HEAL":
            self.check_heal(source, clause.amount, before, after, decision, hero_power=False)
            return
        if before["shield"] or before["immune"] or before["target_is_hero"] or after["zone"] != Zone.PLAY:
            return                                         # shields, immunity, armor and lethal hits blur the delta
        observed = after["damage"] - before["damage"]
        sp = decision["spell_power"]
        n = clause.amount
        candidates = {
            "base_only": n,
            "plus_current_minions": n + sp["current_sum"],
            "plus_current_minions_doubled": (n + sp["current_sum"]) * (2 if sp["doubled"] else 1),
            "plus_player_current": n + sp["player_current"],
            "plus_player_current_doubled": (n + sp["player_current"]) * (2 if sp["doubled"] else 1),
            "doubled_base_only": n * (2 if sp["doubled"] else 1),
        }
        self.checks.append({"kind": "spell_damage", "card": source.card_id, "base": n, "observed": observed,
                            "secret_consumed": after["opponent_secrets"] < before["opponent_secrets"],
                            "doubled": sp["doubled"], "sp_current": sp["current_sum"], "sp_player": sp["player_current"],
                            "match": {k: v == observed for k, v in candidates.items()}})

    def check_area_damage(self, source, clause, clauses, before, after, decision) -> None:
        """Every minion the area effect can hit and that took a plain, surviving hit is one measurement."""
        sides = {"ANY": (True, False), "FRIENDLY": (True,), "ENEMY": (False,)}[clause.selector.allegiance]
        if any(c.kind == "HEAL" for c in clauses) and True in sides:
            return                                         # friendly minions are also healed: the delta mixes both
        sp, n = decision["spell_power"], clause.amount
        for entity_id, old in before["minions"].items():
            new = after["minions"].get(entity_id)
            if (new is None or old["zone"] != Zone.PLAY or new["zone"] != Zone.PLAY or old["mine"] not in sides
                    or old["shield"] or old["immune"] or old["dormant"]):
                continue
            observed = new["damage"] - old["damage"]
            candidates = {"base_only": n, "plus_current_minions": n + sp["current_sum"],
                          "plus_current_minions_doubled": (n + sp["current_sum"]) * (2 if sp["doubled"] else 1),
                          "plus_player_current": n + sp["player_current"],
                          "plus_player_current_doubled": (n + sp["player_current"]) * (2 if sp["doubled"] else 1),
                          "doubled_base_only": n * (2 if sp["doubled"] else 1)}
            self.checks.append({"kind": "spell_damage", "card": source.card_id, "base": n, "observed": observed,
                                "secret_consumed": after["opponent_secrets"] < before["opponent_secrets"],
                                "doubled": sp["doubled"], "sp_current": sp["current_sum"],
                                "sp_player": sp["player_current"], "area": True,
                                "match": {k: v == observed for k, v in candidates.items()}})

    def check_heal(self, source, amount: int, before, after, decision, hero_power: bool) -> None:
        if decision["sanctum"] != "INACTIVE":
            return
        healed = before["damage"] - after["damage"]
        hl = decision["healing"]
        bonus, doubled = hl["bonus"], hl["spell_double"] or hl["all_double"]
        base = amount + bonus
        candidates = {"base_only": amount, "plus_bonus": base,
                      "plus_bonus_then_doubled": base * (2 if doubled else 1),
                      "doubled_base_only": amount * (2 if doubled else 1)}
        # a heal is capped by the missing health: only uncapped cases measure the amount
        if before["damage"] < max(candidates.values()) + 1:
            return
        self.checks.append({"kind": "hero_power_heal" if hero_power else "spell_heal", "card": source.card_id,
                            "secret_consumed": after["opponent_secrets"] < before["opponent_secrets"],
                            "base": amount, "observed": healed, "bonus": bonus, "doubled": doubled,
                            "match": {k: v == healed for k, v in candidates.items()}})


def replay_segment(lines: list[str], texts: TextSource):
    info = inspect_segment(lines)
    if info.start_key is None or info.mid_game_start or info.complete_index is None:
        return None, "INCOMPLETE_OR_MID_GAME"
    parser = LogParser()
    with quiet_parser():
        for line in lines[:info.complete_index + 1]:
            if GAME_STATE_LINE.match(line):
                parser.read_line(line)
        parser.flush()
    if len(parser.games) != 1:
        return None, "NOT_ONE_GAME"
    tree = parser.games[0]
    probe = PacketExporter(tree)
    with quiet_parser():
        for packet in preorder(tree.packets):
            probe.export_packet(packet)
    chosen = {int(m.group(1)) for line in lines[:info.complete_index + 1]
              if "GameState.SendChoices()" in line and (m := CHOSEN.search(line))}
    try:
        by_hand = infer_local_player_id(probe.game)
    except ValueError:
        by_hand = None
    signals = {v for v in (*chosen, by_hand) if v is not None}
    if len(chosen) > 1 or len(signals) != 1:
        return None, "SELF_AMBIGUOUS"
    replay = Replay(tree, signals.pop(), info.start_key, texts)
    replay.run()
    return replay, None


def tally(checks: list[dict], kind: str, formulas: list[str]) -> dict:
    """A measurement made while an opponent Secret was consumed is set aside: the spell may have been countered."""
    rows = [c for c in checks if c["kind"] == kind]
    kept = [c for c in rows if not c["secret_consumed"]]
    return {"n": len(kept), "set_aside_secret_consumed": len(rows) - len(kept),
            "match_by_formula": {f: sum(c["match"][f] for c in kept) for f in formulas},
            "kept_without_any_matching_formula": sum(not any(c["match"].values()) for c in kept)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--catalog", default=str(ROOT / "data" / "cards" / "standard_current_enUS.json"))
    parser.add_argument("--reviewed", default=str(ROOT / "data" / "outcome" / "reviewed_texts.json"))
    parser.add_argument("--supplement", nargs="*", default=[])
    parser.add_argument("--facts-out", type=Path, default=ROOT / "data" / "processed_observation_probe_1b" / "facts.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "action_outcome_1b" / "observation_probe.json")
    args = parser.parse_args()
    raw = args.raw
    if not raw.exists():
        raw = next((p / args.raw for p in ROOT.parents if (p / args.raw).exists()), raw)
    texts = TextSource.from_files(args.catalog, args.reviewed, *args.supplement)

    replays, rejected, keys, segments = [], Counter(), set(), 0
    paths = sorted(raw.rglob("*.log"))
    for path in paths:
        for lines in split_games(read_complete_lines(path)):
            segments += 1
            key = inspect_segment(lines).start_key
            if key in keys:
                rejected["DUPLICATE_MATCH"] += 1
                continue
            replay, reason = replay_segment(lines, texts)
            if replay is None:
                rejected[reason] += 1
                continue
            keys.add(key)
            replays.append(replay)

    facts = [f for r in replays for f in r.facts]
    checks = [c for r in replays for c in r.checks]
    keyword = [c for c in checks if c["kind"] == "minion_keywords"]
    report = {
        "inputs": {"raw_log_files": len(paths), "game_segments": segments, "replayed_matches": len(replays),
                   "rejected": dict(rejected), "decision_points": len(facts)},
        "hero_divine_shield": {"decisions_with_shield": sum(f["hero_divine_shield"] for f in facts)},
        "sanctum_states": dict(Counter(f["sanctum"] for f in facts)),
        "spell_damage_doubling_flag": {"decisions_doubled": sum(f["spell_power"]["doubled"] for f in facts),
                                       "decisions_with_minion_spell_power": sum(bool(f["spell_power"]["current_sum"]) for f in facts),
                                       "decisions_with_player_current_spellpower": sum(bool(f["spell_power"]["player_current"]) for f in facts)},
        "healing": {"decisions_with_bonus": sum(bool(f["healing"]["bonus"]) for f in facts),
                    "bonus_values": dict(Counter(f["healing"]["bonus"] for f in facts)),
                    "decisions_spell_healing_doubled": sum(f["healing"]["spell_double"] for f in facts)},
        "minion_hand_keywords": {
            "plays": len(keyword), "hand_tags_equal_board_tags": sum(c["hand_equals_board"] for c in keyword),
            "hand_tags_equal_printed_keywords": sum(c["hand_equals_base"] for c in keyword),
            "hand_tags_differ_from_printed": sum(not c["hand_equals_base"] for c in keyword),
            "identical_copies_with_different_tags": sum(c["ambiguous"] for c in keyword)},
        "spell_damage_vs_formulas": tally(checks, "spell_damage", [
            "base_only", "plus_current_minions", "plus_current_minions_doubled", "plus_player_current",
            "plus_player_current_doubled", "doubled_base_only"]),
        "spell_heal_vs_formulas": tally(checks, "spell_heal", [
            "base_only", "plus_bonus", "plus_bonus_then_doubled", "doubled_base_only"]),
        "hero_power_heal_vs_formulas": tally(checks, "hero_power_heal", [
            "base_only", "plus_bonus", "plus_bonus_then_doubled", "doubled_base_only"]),
        "mismatches": [
            {k: v for k, v in c.items() if k != "match"} | {"matching_formulas": [f for f, ok in c["match"].items() if ok]}
            for c in checks if c["kind"] in ("spell_damage", "spell_heal", "hero_power_heal")
            and not any(c["match"].values()) and not c["secret_consumed"]][:40],
    }
    args.facts_out.parent.mkdir(parents=True, exist_ok=True)
    with args.facts_out.open("x", encoding="utf-8", newline="\n") as stream:
        for fact in facts:
            stream.write(json.dumps(fact, sort_keys=True) + "\n")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in report if k != "mismatches"}, indent=1, default=str)[:4000])
    print(f"mismatches without any matching formula: {len(report['mismatches'])} (see {args.out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
