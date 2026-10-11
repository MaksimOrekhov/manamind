"""Check the production observed-fact extractor against what the logs later show (OBSERVATION-EXT-1a).

Every completed single-game raw log is replayed packet by packet with the hslog exporter LIVE uses. At each ``Options``
packet ``extract_observed_facts`` runs over the packets applied so far (exactly what LIVE does); the packets that follow
are used only to score the fact. Reads only SELF's entities and the two heroes' Divine Shield, like the extractor.

  python scripts/validate_observed_facts.py --raw data/raw --facts data/processed_observation_ext_1a/observed_facts.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import observation_probe_1b as probe  # noqa: E402  (reuses its replay driver, not its facts)
from hearthstone.enums import BlockType, CardType, GameTag, Zone  # noqa: E402
from hslog.packets import Block, Options, SubSpell  # noqa: E402

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games  # noqa: E402
from manamind.integrations.powerlog.observed_facts import (  # noqa: E402
    KEYWORD_TAGS, SANCTUM_EFFECT_CARD, ObservationHistory, extract_observed_facts,
)
from manamind.outcome import TextSource  # noqa: E402
from manamind.outcome.grammar import parse_text  # noqa: E402


def find(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.exists() else next((p / path for p in ROOT.parents if (p / path).exists()), candidate)


class Validation(probe.Replay):
    def __init__(self, tree, self_id, key, texts, catalog):
        super().__init__(tree, self_id, key, texts)
        self.catalog = catalog
        self.prod = None
        self.prod_by_decision: dict[str, dict] = {}
        self.rows: list[dict] = []
        self.channel: list[dict] = []
        self.sanctum_cross: Counter = Counter()
        self.excluded_by_text = 0
        self.extract_ms: list[float] = []

    # the probe only descends into PLAY blocks; attacks are needed for the hero Divine Shield check
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

    def hand_entities(self):
        me = self.me
        return sorted((e for e in probe.cards(self.exporter.game) if e.zone == Zone.HAND and e.controller == me
                       and e.card_id), key=lambda e: (probe.tag(e, GameTag.ZONE_POSITION) or 0, e.id))

    def on_options(self, packet) -> None:
        super().on_options(packet)
        exporter = self.exporter
        history = ObservationHistory(exporter.created_turn, exporter.resets)
        start = time.perf_counter_ns()
        self.prod = extract_observed_facts(exporter.game, self.self_id, history, self.catalog)
        self.extract_ms.append((time.perf_counter_ns() - start) / 1e6)
        self.prod_by_decision[self.decision["decision_id"]] = self.prod.to_dict()
        game, me = exporter.game, self.me
        flag = probe.tag(me, GameTag.HEALING_DOES_DAMAGE)
        effect = any(e.card_id == SANCTUM_EFFECT_CARD and e.zone == Zone.PLAY and probe.tag(e, GameTag.ATTACHED) == me.id
                     for e in probe.cards(game))
        self.sanctum_cross[(f"flag={flag}", f"effect={effect}")] += 1
        for owner, who in ((me, "SELF"), (next(p for p in game.players if p is not me), "OPPONENT")):
            minions = [e for e in probe.cards(game) if e.zone == Zone.PLAY and e.controller == owner
                       and probe.tag(e, GameTag.CARDTYPE) == CardType.MINION]
            self.channel.append({"who": who, "aggregate": probe.tag(owner, GameTag.CURRENT_SPELLPOWER) or 0,
                                 "minions": sum(probe.tag(e, GameTag.SPELLPOWER) or 0 for e in minions)})

    def capture(self, packet) -> dict:
        row = super().capture(packet)
        ids = [e.id for e in self.hand_entities()]
        row["hand_index"] = ids.index(packet.entity) if packet.entity in ids else None
        game = self.exporter.game
        target = game.find_entity_by_id(packet.target) if packet.target else None
        row["target_side"] = (None if target is None else "SELF" if target.controller == self.me else "OPPONENT")
        row["target_armor"] = probe.tag(target, GameTag.ARMOR) or 0 if target is not None else 0
        row["target_hero_shield"] = bool(probe.tag(target, GameTag.DIVINE_SHIELD)) if target is not None else False
        if packet.type == BlockType.ATTACK:
            exporter = self.exporter
            row["fresh"] = extract_observed_facts(
                game, self.self_id, ObservationHistory(exporter.created_turn, exporter.resets), self.catalog)
        return row

    def on_action(self, packet, before: dict, after: dict) -> None:
        game = self.exporter.game
        source = game.find_entity_by_id(packet.entity) if packet.entity else None
        if source is None:
            return
        if packet.type == BlockType.ATTACK:       # either side attacks: facts are re-read at the start of the block
            self.check_hero_shield(source, before, after)
            return
        if source.controller != self.me:
            return
        card_type = probe.tag(source, GameTag.CARDTYPE)
        if card_type == CardType.MINION:
            self.check_minion(source, before, after)
            return
        entry = self.texts.get(source.card_id) if card_type == CardType.SPELL else None
        if card_type == CardType.SPELL and entry is not None:
            self.check_spell(entry, before, after, source)
        elif card_type == CardType.HERO_POWER and source.card_id in probe.HERO_HEAL_POWERS:
            self.check_heal(source, probe.HERO_HEAL_POWERS[source.card_id], before, after, "hero_power_heal")

    # ----- hand keywords ------------------------------------------------------------------------------------------

    def check_minion(self, source, before: dict, after: dict) -> None:
        index = before["hand_index"]
        if index is None or index >= len(self.prod.hand):
            return
        fact = self.prod.hand[index]
        copies = [h for h in self.prod.hand if h.card_id == fact.card_id]
        kept = sorted(name for name in KEYWORD_TAGS if after["source_tags"].get(name))
        game = self.exporter.game
        grants = [{"enchantment": e.card_id, "creator": getattr(game.find_entity_by_id(probe.tag(e, GameTag.CREATOR)), "card_id", None),
                   "creator_side": ("SELF" if (c := game.find_entity_by_id(probe.tag(e, GameTag.CREATOR))) is not None
                                    and c.controller == self.me else "OPPONENT")}
                  for e in probe.cards(game)
                  if probe.tag(e, GameTag.CARDTYPE) is not None and probe.tag(e, GameTag.CARDTYPE).name == "ENCHANTMENT"
                  and e.zone == Zone.PLAY and probe.tag(e, GameTag.ATTACHED) == source.id]
        self.rows.append({
            "kind": "minion_keywords", "decision": self.decision["decision_id"], "card": fact.card_id,
            "fact_card_matches": fact.card_id == source.card_id, "fact_keywords": list(fact.keywords or []),
            "fact_known": fact.keywords is not None, "board_keywords": kept,
            "equal": list(fact.keywords or []) == kept, "copies_in_hand": len(copies),
            "copies_differ": len({c.keywords for c in copies}) > 1, "attached_enchantments": grants,
            "extra_on_board": sorted(set(kept) - set(fact.keywords or [])),
            "missing_on_board": sorted(set(fact.keywords or []) - set(kept)),
            "printed": sorted(name for name, mech in probe.BASE_MECHANIC.items()
                              if (entry := self.texts.get(source.card_id)) and mech in entry.mechanics)})

    # ----- damage and healing ---------------------------------------------------------------------------------------

    def damage_candidates(self, n: int):
        prod = self.prod
        bonus = prod.spell_damage if prod.spell_damage_status == "NONE_SEEN" else None
        if bonus is None or prod.spell_damage_doubled is None:
            return None
        f = 2 if prod.spell_damage_doubled else 1
        return bonus, f, {"(n+bonus)*f": (n + bonus) * f, "n*f+bonus": n * f + bonus}

    def damage_row(self, source, n, observed, before, after, bonus, f, candidates, area: bool) -> None:
        self.rows.append({"kind": "spell_damage", "decision": self.decision["decision_id"], "card": source.card_id,
                          "n": n, "bonus": bonus, "f": f, "observed": observed, "area": area,
                          "secret_consumed": after["opponent_secrets"] < before["opponent_secrets"],
                          "match": {k: v == observed for k, v in candidates.items()},
                          "order_discriminates": candidates["(n+bonus)*f"] != candidates["n*f+bonus"]})

    def check_spell(self, entry, before, after, source) -> None:
        clauses = [c for c in parse_text(entry.text).clauses if c.kind not in ("KEYWORDS", "PREPARE", "COST_ONLY")]
        area = [c for c in clauses if c.kind == "DAMAGE" and c.selector.mode == "ALL"]
        if len(area) == 1 and all(c.kind in ("DAMAGE", "HEAL") for c in clauses):
            self.check_area_damage(source, area[0], clauses, before, after)
            return
        if len(clauses) != 1 or clauses[0].kind not in ("DAMAGE", "HEAL") or clauses[0].selector.mode != "CHOSEN":
            return
        clause = clauses[0]
        if clause.kind == "HEAL":
            self.check_heal(source, clause.amount, before, after, "spell_heal")
            return
        if before["shield"] or before["immune"] or before["target_is_hero"] or after["zone"] != Zone.PLAY:
            return
        found = self.damage_candidates(clause.amount)
        if found is not None:
            bonus, f, candidates = found
            self.damage_row(source, clause.amount, after["damage"] - before["damage"], before, after, bonus, f,
                            candidates, False)

    def check_area_damage(self, source, clause, clauses, before, after) -> None:
        """Every minion the area effect can hit and that took a plain, surviving hit is one measurement."""
        sides = {"ANY": (True, False), "FRIENDLY": (True,), "ENEMY": (False,)}[clause.selector.allegiance]
        if any(c.kind == "HEAL" for c in clauses) and True in sides:
            return                                         # friendly minions are also healed: the delta mixes both
        found = self.damage_candidates(clause.amount)
        if found is None:
            return
        bonus, f, candidates = found
        for entity_id, old in before["minions"].items():
            new = after["minions"].get(entity_id)
            if (new is None or old["zone"] != Zone.PLAY or new["zone"] != Zone.PLAY or old["mine"] not in sides
                    or old["shield"] or old["immune"] or old["dormant"]):
                continue
            self.damage_row(source, clause.amount, new["damage"] - old["damage"], before, after, bonus, f,
                            candidates, True)

    def check_heal(self, source, amount: int, before, after, kind: str) -> None:
        prod = self.prod
        if prod.healing_bonus is None or prod.spell_healing_doubled is None:
            return
        healed = before["damage"] - after["damage"]
        bonus = prod.healing_bonus
        f = 2 if (prod.spell_healing_doubled or prod.all_healing_doubled) else 1
        candidates = {"(base+bonus)*f": (amount + bonus) * f, "base*f+bonus": amount * f + bonus,
                      "base+bonus": amount + bonus, "base*f": amount * f}
        # a heal is capped by the missing health; only an uncapped heal measures the amount
        if before["damage"] < max(candidates.values()) + 1 and prod.healing_does_damage is not True:
            return
        self.rows.append({"kind": kind, "decision": self.decision["decision_id"], "card": source.card_id, "base": amount,
                          "bonus": bonus, "f": f, "observed": healed, "sanctum": prod.healing_does_damage,
                          "secret_consumed": after["opponent_secrets"] < before["opponent_secrets"],
                          "match": {k: v == healed for k, v in candidates.items()},
                          "order_discriminates": candidates["(base+bonus)*f"] != candidates["base*f+bonus"]})

    # ----- hero Divine Shield ----------------------------------------------------------------------------------------

    def check_hero_shield(self, source, before, after) -> None:
        if not before["target_is_hero"] or before["immune"]:
            return
        attack = probe.tag(source, GameTag.ATK) or 0
        entry = self.texts.get(source.card_id)
        if attack <= 0 or (entry is not None and "Instead of damaging" in entry.text):   # text replaces hero damage
            self.excluded_by_text += attack > 0
            return
        prod = before["fresh"]
        fact = prod.self_hero_divine_shield if before["target_side"] == "SELF" else prod.opponent_hero_divine_shield
        absorbed = (after["damage"] == before["damage"]) and (after["armor"] == before["armor"])
        self.rows.append({"kind": "hero_shield_attack", "decision": self.decision["decision_id"],
                          "target_side": before["target_side"], "fact": fact, "tag_at_block_start": before["shield"],
                          "attacker": source.card_id, "attack": attack, "armor_before": before["target_armor"],
                          "damage_before": before["damage"], "damage_after": after["damage"],
                          "armor_after": after["armor"], "attacker_zone_after": str(after["source_zone"]),
                          "absorbed": absorbed, "secret_consumed": after["opponent_secrets"] < before["opponent_secrets"]})


def counted(values) -> dict[str, int]:
    return {str(k): v for k, v in Counter(values).items()}


def order_check(rows: list[dict]) -> dict:
    """Heals made while Ruby Sanctum is active become damage of the same computed amount: a second look at the order."""
    active = [r for r in rows if r["kind"] in ("spell_heal", "hero_power_heal") and r["sanctum"] is True]
    counts: Counter = Counter()
    for r in active:
        a, b = -(r["base"] + r["bonus"]) * r["f"], -(r["base"] * r["f"] + r["bonus"])
        counts["discriminating" if a != b else "same_by_both_orders"] += 1
        if a != b:
            counts["discriminating_matching_(base+bonus)*f"] += r["observed"] == a
            counts["discriminating_matching_base*f+bonus"] += r["observed"] == b
        else:
            counts["same_by_both_orders_and_matching"] += r["observed"] == a
    counts["measured"] = len(active)
    return dict(sorted(counts.items()))


def tally(rows: list[dict], kind: str, formulas: list[str]) -> dict:
    chosen = [r for r in rows if r["kind"] == kind and r.get("sanctum") is not True]
    kept = [r for r in chosen if not r["secret_consumed"]]
    discriminating = [r for r in kept if r["order_discriminates"]]
    return {"measurements": len(kept), "set_aside_secret_consumed": len(chosen) - len(kept),
            "with_doubling": sum(r["f"] == 2 for r in kept), "with_nonzero_bonus": sum(bool(r["bonus"]) for r in kept),
            "match_by_formula": {f: sum(r["match"][f] for r in kept) for f in formulas},
            "order_discriminating_measurements": len(discriminating),
            "order_discriminating_matching_by_formula": {f: sum(r["match"][f] for r in discriminating) for f in formulas},
            "without_any_matching_formula": [
                {k: v for k, v in r.items() if k != "match"} for r in kept if not any(r["match"].values())][:20]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--catalog", default="data/cards/standard_current_enUS.json")
    parser.add_argument("--reviewed", default="data/outcome/reviewed_texts.json")
    parser.add_argument("--supplement", nargs="*", default=[])
    parser.add_argument("--facts", default="data/processed_observation_ext_1a/observed_facts.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "observation_ext_1a" / "observation_validation.json")
    args = parser.parse_args()

    catalog = CardCatalog.from_json(find(args.catalog))
    texts = TextSource.from_files(str(find(args.catalog)), str(find(args.reviewed)), *args.supplement)
    replays, seen, rejected = [], set(), Counter()
    for path in sorted(find(args.raw).rglob("*.log")):
        for lines in split_games(read_complete_lines(path)):
            key = inspect_segment(lines).start_key
            if key in seen:
                rejected["DUPLICATE_MATCH"] += 1
                continue
            replay, reason = probe.replay_segment(lines, texts)
            if replay is None:
                rejected[reason] += 1
                continue
            seen.add(key)
            validation = Validation(replay.tree, replay.self_id, replay.key, texts, catalog)
            validation.run()
            replays.append(validation)

    rows = [r for v in replays for r in v.rows]
    decisions = {d: f for v in replays for d, f in v.prod_by_decision.items()}
    keyword = [r for r in rows if r["kind"] == "minion_keywords"]
    known = [r for r in keyword if r["fact_known"]]
    unequal = [r for r in known if not r["equal"]]
    shield = [r for r in rows if r["kind"] == "hero_shield_attack" and not r["secret_consumed"]]
    channel = [c for v in replays for c in v.channel]
    timings = sorted(ms for v in replays for ms in v.extract_ms)
    report = {
        "extraction_ms": {"n": len(timings), "mean": round(statistics.fmean(timings), 4),
                          "p50": round(timings[len(timings) // 2], 4), "p95": round(timings[int(0.95 * len(timings))], 4),
                          "max": round(timings[-1], 4)},
        "inputs": {"matches_replayed": len(replays), "rejected": dict(rejected), "decision_points": len(decisions),
                   "coverage": counted(f["coverage"] for f in decisions.values())},
        "hand_keywords": {
            "minion_plays": len(keyword), "plays_with_known_fact": len(known),
            "plays_with_unknown_fact": len(keyword) - len(known),
            "known_equal_to_board_after_play": sum(r["equal"] for r in known),
            "known_unequal": unequal,
            "known_plays_with_identical_copies_in_hand": sum(r["copies_in_hand"] > 1 for r in known),
            "known_identical_copies_with_different_keywords": sum(r["copies_differ"] for r in known),
            "known_fact_differs_from_printed": sum(r["fact_keywords"] != r["printed"] for r in known),
            "known_fact_differs_from_printed_and_equals_board": sum(
                r["fact_keywords"] != r["printed"] and r["equal"] for r in known)},
        "spell_damage": tally(rows, "spell_damage", ["(n+bonus)*f", "n*f+bonus"]),
        "spell_heal": tally(rows, "spell_heal", ["(base+bonus)*f", "base*f+bonus", "base+bonus", "base*f"]),
        "hero_power_heal": tally(rows, "hero_power_heal", ["(base+bonus)*f", "base*f+bonus", "base+bonus", "base*f"]),
        "hero_shield": {
            "attacks_on_a_hero": len(shield),
            "excluded_attacks_whose_text_replaces_hero_damage": sum(v.excluded_by_text for v in replays),
            "by_fact": {str(k): v for k, v in Counter((r["fact"], r["absorbed"]) for r in shield).items()},
            "fact_false_but_absorbed_rows": [r for r in shield if r["fact"] is False and r["absorbed"]],
            "fact_true_and_absorbed": sum(r["fact"] is True and r["absorbed"] for r in shield),
            "fact_true_and_not_absorbed": sum(r["fact"] is True and not r["absorbed"] for r in shield),
            "fact_false_and_absorbed": sum(r["fact"] is False and r["absorbed"] for r in shield),
            "fact_unknown": sum(r["fact"] is None for r in shield),
            "decisions_with_self_shield": sum(f["self_hero_divine_shield"] is True for f in decisions.values()),
            "decisions_with_opponent_shield": sum(f["opponent_hero_divine_shield"] is True for f in decisions.values())},
        "sanctum": {
            "flag_x_effect_over_all_decisions": {" ".join(k): v for k, v in sum(
                (v.sanctum_cross for v in replays), Counter()).items()},
            "fact_values": counted(f["healing_does_damage"] for f in decisions.values()),
            "active_heal_order_check": order_check(rows),
            "heals_measured_while_active": [{k: v for k, v in r.items() if k != "match"} | {"matching": [f for f, ok in r["match"].items() if ok]}
                                            for r in rows if r["kind"] in ("spell_heal", "hero_power_heal") and r["sanctum"] is True]},
        "spell_damage_channel": {
            "aggregate_equals_minion_sum": sum(c["aggregate"] == c["minions"] for c in channel),
            "aggregate_differs_from_minion_sum": [c for c in channel if c["aggregate"] != c["minions"]][:10],
            "points_with_nonzero_spell_damage": dict(Counter(c["who"] for c in channel if c["aggregate"] or c["minions"])),
            "points": len(channel)},
        "facts_values": {
            "healing_bonus": counted(f["healing_bonus"] for f in decisions.values()),
            "spell_damage_status": counted(f["spell_damage_status"] for f in decisions.values()),
            "spell_damage_doubled": counted(f["spell_damage_doubled"] for f in decisions.values()),
            "spell_healing_doubled": counted(f["spell_healing_doubled"] for f in decisions.values()),
            "unknown_reasons": dict(Counter(f"{k}:{v}" for f in decisions.values() for k, v in f["unknown"].items()))},
    }
    facts_path = find(args.facts)
    if facts_path.exists():
        live = {json.loads(l)["decision_id"]: json.loads(l)["facts"] for l in facts_path.read_text(encoding="utf-8").splitlines()}
        shared = [d for d in live if d in decisions]
        differing = [d for d in shared if live[d] != decisions[d]]
        report["live_session_vs_options_time"] = {
            "live_decisions": len(live), "shared_with_replay": len(shared), "identical": len(shared) - len(differing),
            "different": [{"decision": d, "fields": sorted(k for k in live[d] if live[d][k] != decisions[d][k])}
                          for d in differing][:20]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({k: (v if k != "hand_keywords" else {a: b for a, b in v.items() if a != "known_unequal"})
                      for k, v in report.items()}, indent=1, default=str)[:7000])
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
