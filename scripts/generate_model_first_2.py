"""Generate deterministic, locally provable attack-ranking examples for MODEL-FIRST-2."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from manamind.domain.game_state import GameState, PlayerObservation
from manamind.domain.serialization import game_state_from_dict
from manamind.live.snapshot import canonical_json, state_to_dict
from manamind.training.model_first_1_control import (
    scenario_content_fingerprint, validate_no_control_overlap,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("data/processed_synthetic/model_first_2")

# Families and templates are preassigned to splits. The held-out split uses new
# board sizes/stat ranges and card IDs, not renamed copies of a training family.
PLAN = {
    "train": [("single_favorable_trade", 200), ("multi_favorable_trade", 200),
              ("taunt_safe_trade", 200), ("single_face_lethal", 200),
              ("multi_face_lethal", 200), ("mixed_target_trade", 200)],
    "validation": [("validation_three_target_trade", 100),
                   ("validation_two_attacker_lethal", 100), ("validation_taunt_trade", 100)],
    "test": [("heldout_wide_board_trade", 100), ("heldout_three_attacker_lethal", 100),
             ("heldout_unknown_id_trade", 100)],
}


def _action_key(action: dict) -> str:
    return canonical_json({k: v for k, v in action.items() if k != "entity_id"})


def _entity(card_id: str, attack: int, health: int, position: int, *, can_attack: bool, taunt=False):
    return {
        "board_position": position, "can_attack": can_attack,
        "cant_be_targeted_by_hero_powers": None, "cant_be_targeted_by_spells": None,
        "card": {"attack": attack, "card_class": "UNKNOWN_CLASS", "card_id": card_id,
                 "card_type": "MINION", "cost": None, "current_attack": None,
                 "current_cost": None, "current_durability": None, "current_health": None,
                 "current_spell_damage": None, "dark_gifts": None, "durability": None,
                 "effect_turns_remaining": None, "freeze_turns_remaining": None, "health": health,
                 "held_spell_progress": None, "mechanics": ["TAUNT"] if taunt else [],
                 "prepare_locked": None, "prepare_used": None, "race": None,
                 "shatter_fragment": None, "shatter_original_card_id": None,
                 "shatter_partner_hand_position": None, "trigger_remaining": None},
        "charge": False, "current_attack": attack, "current_health": health,
        "divine_shield": False, "dormant": False, "frozen": False, "immune": False,
        "lifesteal": False, "max_health": health, "poisonous": False, "reborn": False,
        "rush": False, "silenced": False, "stealth": False, "taunt": taunt,
        "windfury": False,
    }


def _attack(source: dict, target: dict | None, hero_health: int) -> dict:
    return {"play_position": 0, "source_attack": source["current_attack"],
            "source_board_position": source["board_position"],
            "source_card_id": source["card"]["card_id"],
            "source_health": source["current_health"], "source_is_hero": False,
            "source_kind": "MINION", "target_attack": target["current_attack"] if target else 0,
            "target_board_position": target["board_position"] if target else -1,
            "target_card_id": target["card"]["card_id"] if target else None,
            "target_health": target["current_health"] if target else hero_health,
            "target_is_hero": target is None,
            "target_kind": "HERO" if target is None else "MINION",
            "target_side": "OPPONENT", "target_taunt": bool(target and target["taunt"]),
            "type": "ATTACK"}


def _base_state() -> dict:
    # Start from a fresh domain object; frozen MODEL-FIRST-1 scenarios are used
    # only by the explicit overlap guard and are never a generation template.
    state = GameState(turn_number=8, active_player="SELF",
                      self_player=PlayerObservation(hero_health=30),
                      opponent=PlayerObservation(hero_health=30))
    return state_to_dict(state)


def _build_case(seed: int, split: str, template: str, ordinal: int, base: dict) -> dict:
    rng = random.Random(seed)
    # held-out templates intentionally use novel board cardinality / IDs / stat
    # bands; the combat gold rule itself is simple and explicitly stated below.
    heldout = split == "test"
    friendly_count = (3 if template == "heldout_three_attacker_lethal" else
                      3 if template == "heldout_wide_board_trade" else
                      2 if template in {"multi_favorable_trade", "multi_face_lethal",
                                       "validation_two_attacker_lethal"} else 1)
    enemy_count = (4 if template == "heldout_wide_board_trade" else
                   3 if template in {"validation_three_target_trade", "mixed_target_trade",
                                     "heldout_unknown_id_trade"} else 2)
    if template in {"single_face_lethal", "multi_face_lethal", "validation_two_attacker_lethal",
                    "heldout_three_attacker_lethal"}:
        enemy_count = 0

    low, high = (5, 9) if heldout else (2, 6)
    if heldout:
        self_ids = [f"MF2_HELDOUT_SELF_{i}" for i in range(friendly_count)]
        enemy_ids = [f"MF2_HELDOUT_ENEMY_{i}" for i in range(enemy_count)]
    else:
        # A real pinned-catalog identity is seen during fitting; held-out IDs
        # map through the existing unknown-card path without vocab changes.
        self_ids = ["BE_036"] * friendly_count
        enemy_ids = ["BE_036"] * enemy_count
    friendly = []
    for i in range(friendly_count):
        attack = rng.randint(low, high)
        # Ensure selected favorable-trade cases exist by making source robust.
        health = attack + rng.randint(2, 6)
        friendly.append(_entity(self_ids[i], attack, health, i + 1, can_attack=True))
    enemies = []
    for i in range(enemy_count):
        attack = rng.randint(low, high)
        health = rng.randint(low, high + 2)
        enemies.append(_entity(enemy_ids[i], attack, health, i + 1, can_attack=False))

    taunt_case = "taunt" in template
    if taunt_case:
        # Each taunt is a legal target; all generated taunt trades are lethal to
        # the defender while the attacker survives.
        for target in enemies:
            target["taunt"] = True
            target["card"]["mechanics"] = ["TAUNT"]
            source = friendly[0]
            target["current_health"] = max(1, source["current_attack"] - 1)
            target["card"]["health"] = target["current_health"]
            target["current_attack"] = max(1, source["current_health"] - 1)
            target["card"]["attack"] = target["current_attack"]
    elif enemies and "lethal" not in template:
        # Every trade template contains one arithmetically provable positive
        # exchange; the remaining choices vary with the sample seed.
        source, target = friendly[0], enemies[0]
        target["current_health"] = max(1, source["current_attack"] - 1)
        target["card"]["health"] = target["current_health"]
        target["current_attack"] = max(1, source["current_health"] - 1)
        target["card"]["attack"] = target["current_attack"]

    lethal_case = "lethal" in template
    enemy_health = 1 if lethal_case else 30
    if lethal_case:
        total = sum(m["current_attack"] for m in friendly)
        enemy_health = max(1, total - rng.randint(0, max(0, total - 1)))
    state = copy.deepcopy(base)
    state["turn_number"] = 20 + ordinal
    state["self_player"]["board"] = friendly
    state["opponent"]["board"] = enemies
    state["opponent"]["hero_health"] = enemy_health
    state["opponent"]["armor"] = 0
    state = state_to_dict(game_state_from_dict(state))

    actions = []
    correct = []
    has_taunt = any(m["taunt"] for m in enemies)
    for source in friendly:
        candidates = enemies if has_taunt else [*enemies, None]
        for target in candidates:
            actions.append(_attack(source, target, enemy_health))
            if target is None:
                if lethal_case:
                    correct.append(actions[-1])
                continue
            kills = source["current_attack"] >= target["current_health"]
            survives = target["current_attack"] < source["current_health"]
            if kills and survives:
                correct.append(actions[-1])
    actions.append({"play_position": 0, "type": "END_TURN"})

    # A local exchange is supervised only when at least one unambiguous positive
    # combat result exists. Labels follow arithmetic combat consequences, never
    # the baseline's ranking or its heuristic scores.
    if not correct:
        raise ValueError(f"No provable positive tactical label for {template}")
    row = {"schema_version": 1, "scenario_id": f"mf2_{split}_{template}_{ordinal:04d}",
           "family_id": f"mf2_{split}_{template}", "template_id": f"mf2_template_{split}_{template}",
           "split": split, "category": "lethal" if lethal_case else "taunt" if taunt_case else "target_selection",
           "state": state, "legal_actions": actions, "correct_actions": correct,
           "label_status": "LABELED", "tags": ["synthetic", "local_combat_proof", template]}
    return row


def generate(seed: int = 20261009, per_template: dict[str, int] | None = None) -> tuple[list[dict], list[dict]]:
    base = _base_state()
    rows, provenance = [], []
    ordinal = 0
    for split, templates in PLAN.items():
        for template, default_count in templates:
            count = (per_template or {}).get(template, default_count)
            for local_index in range(count):
                sample_seed = seed + ordinal * 104729
                row = _build_case(sample_seed, split, template, local_index, base)
                rows.append(row)
                provenance.append({"scenario_id": row["scenario_id"], "seed": sample_seed,
                                   "family_id": row["family_id"], "template_id": row["template_id"],
                                   "split": split, "generator": "model_first_2.local_combat/1",
                                   "content_fingerprint": scenario_content_fingerprint(row)})
                ordinal += 1
    return rows, provenance


def validate_splits(rows: list[dict]) -> None:
    seen = {}
    groups = {name: [r for r in rows if r["split"] == name] for name in ("train", "validation", "test")}
    if any(not groups[name] for name in groups):
        raise ValueError("All three splits must be nonempty")
    for name, part in groups.items():
        validate_no_control_overlap(part)
        for row in part:
            fingerprint = scenario_content_fingerprint(row)
            if fingerprint in seen:
                raise ValueError(f"Exact state/menu overlap between {seen[fingerprint]} and {name}")
            seen[fingerprint] = name
    family_splits, template_splits = {}, {}
    for row in rows:
        family_splits.setdefault(row["family_id"], set()).add(row["split"])
        template_splits.setdefault(row["template_id"], set()).add(row["split"])
    if any(len(v) != 1 for v in [*family_splits.values(), *template_splits.values()]):
        raise ValueError("Family/template leakage across splits")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20261009)
    args = parser.parse_args()
    rows, provenance = generate(seed=args.seed)
    validate_splits(rows)
    args.output.mkdir(parents=True, exist_ok=False)
    for split in ("train", "validation", "test"):
        selected = [r for r in rows if r["split"] == split]
        (args.output / f"{split}.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in selected),
            encoding="utf-8", newline="\n")
    (args.output / "provenance.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in provenance),
        encoding="utf-8", newline="\n")
    manifest = {"schema_version": 1, "seed": args.seed, "generator": "model_first_2.local_combat/1",
                "scenario_count": len(rows), "split_counts": dict(Counter(r["split"] for r in rows)),
                "family_counts": dict(Counter(r["family_id"] for r in rows)),
                "template_counts": dict(Counter(r["template_id"] for r in rows)),
                "content_sha256": hashlib.sha256("".join(
                    canonical_json({"state": r["state"], "legal_actions": sorted(_action_key(a) for a in r["legal_actions"])})
                    for r in rows).encode()).hexdigest(),
                "label_rule": "ATTACK face iff attacks alone guarantee lethal; minion attack iff target dies and source survives; only visible ordinary combat and forced Taunt menus; otherwise reject.",
                "gold_source": "independent integer combat arithmetic; no model/baseline outputs"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
