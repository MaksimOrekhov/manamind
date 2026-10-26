"""CARD-IR-EXECUTION-PILOT-1, level L4: are real Power.log observations of the pilot cards consistent with their IR?

    python reports/card_ir_execution_pilot_1/real_evidence.py     # needs the ignored local data/ directory

Reads EVIDENCE-0B observations (``data/processed_evidence/collected/<game>/observations.jsonl``). Matches of the
protected ``fresh_holdout`` part are skipped by directory name before any file inside is opened. The output keeps only
aggregate counts and public card IDs of targets: no game keys, names or hidden facts. Spell Damage, healing bonuses
and other modifiers at the time of a play are not visible in an observation, so an amount above the base is reported
as "above base", never as a match; observations with recorded confounders are counted separately.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "data"
OUT = HERE / "real_evidence.json"
CARDS = {"CORE_EX1_238": ("DAMAGE", 3), "CORE_AT_055": ("HEAL", 5), "CORE_ICC_055": ("DAMAGE_LIFESTEAL", 3),
         "FIR_906": ("BUFF", 1)}
ROLES = {"PLAYED_CARD", "CONTROL_SAMPLE"}
# Confounders that say another effect may have modified the outcome; the others only weaken fact attribution.
MODIFIER_CONFOUNDERS = {"FOREIGN_ENCHANTMENT_ACTIVE", "FOREIGN_UNIT_WITH_EFFECTS_IN_WINDOW"}
CONSISTENT = {"DAMAGE_BASE", "HEAL_BASE_CAPPED", "DAMAGE_BASE+HEAL_EQUALS_DAMAGE_CAPPED",
              "DAMAGE_BASE+HEAL_EQUALS_DAMAGE_CAPPED+OVERKILL"}


def _own_facts(observation: dict) -> list[dict]:
    units = {u["unit_id"] for u in observation["window"]["units"] if u["relation_to_subject"] in ("ROOT", "SUBJECT_OWN")}
    return [f for f in observation["facts"] if f["unit_id"] in units and f["attribution"]["basis"] != "NESTED_ONLY"]


def _restored(packet: dict) -> int | None:
    before, after = packet.get("damage_tag_before"), packet.get("damage_tag_after")
    return None if before is None or after is None else before - after


def classify(card: str, observation: dict) -> str:
    kind, base = CARDS[card]
    facts = _own_facts(observation)
    damage = [f["data"] for f in facts if f["kind"] == "DAMAGE_PACKET"]
    healing = [f["data"] for f in facts if f["kind"] == "HEALING_PACKET"]
    side = observation["subject"]["side"]
    if kind in ("DAMAGE", "DAMAGE_LIFESTEAL"):
        if len(damage) != 1:
            return "NO_SINGLE_DAMAGE_PACKET"
        amount = damage[0]["amount"]
        label = "BASE" if amount == base else "ABOVE_BASE" if amount > base else "BELOW_BASE"
        if kind == "DAMAGE":
            return f"DAMAGE_{label}"
        own_hero = [h for h in healing if h["target"]["card_type"] == "HERO" and h["target"]["side"] == side]
        if not own_hero:
            return f"DAMAGE_{label}+HEAL_NOT_OBSERVED"
        restored = _restored(own_hero[0])
        before = own_hero[0].get("damage_tag_before") or 0
        heal = "EQUALS_DAMAGE_CAPPED" if restored == min(amount, before) else "DIFFERENT"
        # Overkill: the packet exceeded the target's remaining Health; Lifesteal still counts the full amount.
        remaining = damage[0].get("target_health", 0) - (damage[0].get("damage_tag_before") or 0)
        return f"DAMAGE_{label}+HEAL_{heal}" + ("+OVERKILL" if amount > remaining else "")
    if kind == "HEAL":
        if damage and not healing:
            return "HEALING_REPLACED_BY_DAMAGE"
        if len(healing) != 1:
            return "NO_SINGLE_HEALING_PACKET"
        restored, before = _restored(healing[0]), healing[0].get("damage_tag_before") or 0
        if restored == min(base, before):
            return "HEAL_BASE_CAPPED"
        return "HEAL_ABOVE_BASE" if restored is not None and restored > min(base, before) else "HEAL_OTHER"
    return "NOT_CLASSIFIED"


def main() -> int:
    plan_path = DATA / "processed_policy_prepare_1/split_plan.json"
    evidence_dir = DATA / "processed_evidence/collected"
    if not plan_path.exists() or not evidence_dir.exists():
        print("local evidence data is not present; nothing written")
        return 1
    held = {key[:16] for key in json.loads(plan_path.read_text(encoding="utf-8"))["parts"]["fresh_holdout"]}
    games = sorted(p for p in evidence_dir.iterdir() if p.is_dir())
    skipped = [p for p in games if p.name[:16] in held]
    groups = ("no_confounder", "attribution_confounder_only", "possible_modifier")
    cards: dict[str, dict] = {card: {"observations": 0, **{g: Counter() for g in groups},
                                     "confounder_kinds": Counter(), "target_types": Counter()} for card in CARDS}
    for game in games:
        if game.name[:16] in held:
            continue  # protected: never opened
        for line in (game / "observations.jsonl").read_text(encoding="utf-8").splitlines():
            observation = json.loads(line)
            subject = observation.get("subject") or {}
            card = subject.get("card_id")
            if card not in CARDS or subject.get("role") not in ROLES:
                continue
            row = cards[card]
            row["observations"] += 1
            label = classify(card, observation)
            confounders = sorted({c.get("kind") for c in observation.get("confounders", [])})
            group = "possible_modifier" if MODIFIER_CONFOUNDERS & set(confounders) else (
                "attribution_confounder_only" if confounders else "no_confounder")
            row[group][label] += 1
            row["confounder_kinds"].update(confounders)
            for fact in _own_facts(observation):
                if fact["kind"] == "PLAY_TARGET" and fact["data"].get("target"):
                    target = fact["data"]["target"]
                    row["target_types"][f"{target['side']}_{target['card_type']}"] += 1
    summary = {}
    for card, row in cards.items():
        modifier_free = row["no_confounder"] + row["attribution_confounder_only"]
        consistent = sum(n for label, n in modifier_free.items() if label in CONSISTENT)
        total = sum(modifier_free.values())
        if row["observations"] == 0:
            verdict = "NO_OBSERVATIONS"
        elif total == 0:
            verdict = f"ONLY_POSSIBLY_MODIFIED ({row['observations']} observations)"
        else:
            verdict = f"{consistent}/{total} modifier-free observations fully consistent"
        summary[card] = {"verdict": verdict, "observations": row["observations"],
                         **{key: dict(sorted(row[key].items())) for key in
                            (*groups, "confounder_kinds", "target_types")}}
    result = {
        "schema": "card_ir_execution_pilot_1/real-evidence-1",
        "source": "data/processed_evidence/collected (EVIDENCE-0B observations; ignored local data)",
        "games_present": len(games), "holdout_games_skipped_unopened": len(skipped),
        "games_read": len(games) - len(skipped),
        "limits": ["single observed outcomes, not rules", "Spell Damage and healing modifiers at play time are not "
                   "visible here", "possible_modifier observations are listed but never counted as consistent or inconsistent",
                   "HEAL_NOT_OBSERVED: the caster's hero Health before the play is not in the observation"],
        "cards": summary,
    }
    OUT.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
