"""Build the locked MODEL-FIRST-2C synthetic combat datasets."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from pathlib import Path

from manamind.domain.game_state import GameState, PlayerObservation
from manamind.domain.serialization import game_state_from_dict
from manamind.live.snapshot import state_to_dict
from manamind.training.model_first_1_control import (
    scenario_content_fingerprint,
    validate_no_control_overlap,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/processed_synthetic/model_first_2c"
KNOWN_ID = "Core_CS2_200"  # Pinned Core Boulderfist Ogre: base 6/7, vanilla.
KNOWN_META = {"attack": 6, "card_class": "NEUTRAL", "card_type": "MINION", "cost": 6,
              "health": 7, "mechanics": []}
COUNTS = {"train": 2800, "validation": 500, "test": 400}
TEMPLATES = {
    "train": ("train_trade_sparse", "train_trade_dense", "train_mixed_targets",
              "train_no_gain", "train_face_finish", "train_multi_correct"),
    "validation": ("validation_wide_trade", "validation_no_gain_face", "validation_multi_finish"),
    "test": ("test_swapped_trade", "test_wide_mixed", "test_no_gain", "test_face_finish",
             "test_multi_safe"),
}


def _card(card_id: str, known: bool = False) -> dict:
    meta = KNOWN_META if known else {}
    return {"attack": meta.get("attack"), "card_class": meta.get("card_class", "UNKNOWN_CLASS"),
            "card_id": card_id, "card_type": meta.get("card_type", "MINION"), "cost": meta.get("cost"),
            "current_attack": None, "current_cost": None, "current_durability": None,
            "current_health": None, "current_spell_damage": None, "dark_gifts": None,
            "durability": None, "effect_turns_remaining": None, "freeze_turns_remaining": None,
            "health": meta.get("health"), "held_spell_progress": None,
            "mechanics": list(meta.get("mechanics", [])), "prepare_locked": None,
            "prepare_used": None, "race": None, "shatter_fragment": None,
            "shatter_original_card_id": None, "shatter_partner_hand_position": None,
            "trigger_remaining": None}


def _entity(card_id: str, position: int, attack: int, health: int, *, side: str,
            max_health: int | None = None, known: bool = False) -> dict:
    return {"board_position": position, "can_attack": side == "SELF",
            "cant_be_targeted_by_hero_powers": None, "cant_be_targeted_by_spells": None,
            "card": _card(card_id, known), "charge": False, "current_attack": attack,
            "current_health": health, "divine_shield": False, "dormant": False, "frozen": False,
            "immune": False, "lifesteal": False, "max_health": max_health or health,
            "poisonous": False, "reborn": False, "rush": False, "silenced": False,
            "stealth": False, "taunt": False, "windfury": False}


def _base_state(turn: int, friends: list[dict], enemies: list[dict], hero_health: int) -> dict:
    state = state_to_dict(GameState(turn_number=turn, active_player="SELF",
                                    self_player=PlayerObservation(hero_health=30),
                                    opponent=PlayerObservation(hero_health=hero_health)))
    state["self_player"]["board"] = friends
    state["opponent"]["board"] = enemies
    return state_to_dict(game_state_from_dict(state))


def _attack(source: dict, target: dict | None, hero_health: int) -> dict:
    return {"play_position": 0, "source_attack": source["current_attack"],
            "source_board_position": source["board_position"], "source_card_id": source["card"]["card_id"],
            "source_health": source["current_health"], "source_is_hero": False,
            "source_kind": "MINION", "target_attack": target["current_attack"] if target else 0,
            "target_board_position": target["board_position"] if target else -1,
            "target_card_id": target["card"]["card_id"] if target else None,
            "target_health": target["current_health"] if target else hero_health,
            "target_is_hero": target is None, "target_kind": "HERO" if target is None else "MINION",
            "target_side": "OPPONENT", "target_taunt": False, "type": "ATTACK"}


def _row(scenario_id: str, family_id: str, template_id: str, split: str, state: dict,
         tags: list[str] | None = None) -> dict:
    state = state_to_dict(game_state_from_dict(state))
    friends = state["self_player"]["board"]
    enemies = state["opponent"]["board"]
    hero_health = state["opponent"]["hero_health"] + state["opponent"]["armor"]
    actions = [_attack(source, target, hero_health) for source in friends for target in enemies]
    if not any(enemy["taunt"] for enemy in enemies):
        actions.extend(_attack(source, None, hero_health) for source in friends)
    lethal = [a for a in actions if a["target_kind"] == "HERO"
              and a["source_attack"] >= hero_health]
    safe_kills = [a for a in actions if a["target_kind"] == "MINION"
                  and a["source_attack"] >= a["target_health"]
                  and a["target_attack"] < a["source_health"]]
    if lethal:
        category, correct = "lethal", lethal
    elif safe_kills:
        category, correct = "favorable_trade", safe_kills
    else:
        category, correct = "no_proven_gain", []
    end_turn = {"play_position": 0, "type": "END_TURN"}
    actions.append(end_turn)
    if not correct:
        category, correct = "no_proven_gain", [end_turn]
    return {"schema_version": 1, "scenario_id": scenario_id, "family_id": family_id,
            "template_id": template_id, "split": split, "category": category, "state": state,
            "legal_actions": actions, "correct_actions": correct, "label_status": "LABELED",
            "tags": tags or ["model_first_2c", "local_combat_rule"]}


def _case(seed: int, split: str, template: str, ordinal: int, *, mode: str | None = None,
          friendly_count: int | None = None, enemy_count: int | None = None,
          known: bool = False, family_id: str | None = None, template_id: str | None = None) -> dict:
    rng = random.Random(seed)
    if mode is None:
        mode = ("safe", "safe", "multiple", "no_gain", "lethal")[ordinal % 5]
    default_friendly = 2 + rng.randrange(4)
    default_enemy = 1 + rng.randrange(5)
    n_friends = friendly_count or default_friendly
    n_enemies = enemy_count if enemy_count is not None else default_enemy
    friends, enemies = [], []
    for pos in range(1, n_friends + 1):
        attack = rng.randint(2, 9)
        health = rng.randint(4, 14)
        card_id = KNOWN_ID if known else f"MF2C_{split.upper()}_{ordinal:05d}_S{pos}"
        friends.append(_entity(card_id, pos, attack, health, side="SELF", known=known,
                               max_health=health + rng.randint(0, 3)))
    for pos in range(1, n_enemies + 1):
        attack = rng.randint(1, 10)
        health = rng.randint(4, 18)
        card_id = KNOWN_ID if known else f"MF2C_{split.upper()}_{ordinal:05d}_E{pos}"
        enemies.append(_entity(card_id, pos, attack, health, side="OPPONENT", known=known,
                               max_health=health + rng.randint(0, 3)))
    hero_health = 30
    if n_enemies:
        target_pos = rng.randint(1, n_enemies)
        target = enemies[target_pos - 1]
        if mode in {"safe", "multiple"}:
            target_attack = rng.randint(1, 8)
            target_health = rng.randint(3, 7)
            target["current_attack"] = target_attack
            target["current_health"] = target_health
            target["max_health"] = max(target["max_health"], target_health)
            safe_count = 2 if mode == "multiple" and n_friends > 2 else 1
            safe_positions = rng.sample(range(1, n_friends + 1), safe_count)
            for source_pos in safe_positions:
                source = friends[source_pos - 1]
                source["current_attack"] = rng.randint(target_health, 9)
                source["current_health"] = max(source["current_health"], target_attack + 1)
                source["max_health"] = max(source["max_health"], source["current_health"])
            sacrifice_pos = next((p for p in range(1, n_friends + 1) if p not in safe_positions), None)
            if sacrifice_pos is not None:
                source = friends[sacrifice_pos - 1]
                source["current_attack"] = rng.randint(target_health, 9)
                source["current_health"] = max(1, min(source["current_health"], target_attack))
        elif mode == "no_gain":
            max_attack = max(m["current_attack"] for m in friends)
            target["current_health"] = max(max_attack + 1, 12)
            target["max_health"] = max(target["max_health"], target["current_health"])
            target["current_attack"] = max(m["current_health"] for m in friends)
            for other in enemies:
                other["current_health"] = max(other["current_health"], max_attack + 1)
                other["max_health"] = max(other["max_health"], other["current_health"])
        else:  # A guaranteed one-attack lethal with nonlethal alternatives in the menu.
            source_pos = rng.randint(1, n_friends)
            hero_health = rng.randint(1, friends[source_pos - 1]["current_attack"])
            enemies[target_pos - 1]["current_health"] = max(12, enemies[target_pos - 1]["current_health"])
            enemies[target_pos - 1]["max_health"] = max(enemies[target_pos - 1]["max_health"],
                                                          enemies[target_pos - 1]["current_health"])
            state = _base_state(ordinal + 1, friends, enemies, hero_health)
            return _row(f"mf2c_{split}_{ordinal:05d}", family_id or f"mf2c_{split}_{template}",
                        template_id or f"mf2c_template_{split}_{template}", split, state,
                        ["model_first_2c", "local_combat_rule", "generated_mode_lethal"])
    else:
        hero_health = 30
    state = _base_state(ordinal + 1, friends, enemies, hero_health)
    return _row(f"mf2c_{split}_{ordinal:05d}", family_id or f"mf2c_{split}_{template}",
                template_id or f"mf2c_template_{split}_{template}", split, state,
                ["model_first_2c", "local_combat_rule", f"generated_mode_{mode}"])


def _stat_pair(index: int) -> tuple[dict, dict]:
    rng = random.Random(0x2C5100 + index)
    friend_count, enemy_count = 3, 3
    source_pos = 1 + index % friend_count
    alternate_pos = 1 + (source_pos % friend_count)
    target_pos = 1 + (index * 2 % enemy_count)
    target_attack, target_health = rng.randint(3, 8), rng.randint(3, 6)
    ids_f = [f"MF2C_STAT_{index:03d}_S{p}" for p in range(1, friend_count + 1)]
    ids_e = [f"MF2C_STAT_{index:03d}_E{p}" for p in range(1, enemy_count + 1)]
    enemies = [_entity(ids_e[p - 1], p, 1, 18, side="OPPONENT") for p in range(1, enemy_count + 1)]
    target = enemies[target_pos - 1]
    target.update(current_attack=target_attack, current_health=target_health,
                  max_health=target_health)
    low_friends, high_friends = [], []
    for pos in range(1, friend_count + 1):
        if pos == source_pos:
            low_attack, low_health = target_health, target_attack + 2
            high_attack, high_health = target_health + 2, max(1, target_attack - 1)
        elif pos == alternate_pos:
            low_attack, low_health = max(1, target_health - 1), target_attack + 2
            high_attack, high_health = target_health, target_attack + 2
        else:
            low_attack, low_health = 1, target_attack + 3
            high_attack, high_health = 1, target_attack + 3
        low_friends.append(_entity(ids_f[pos - 1], pos, low_attack, low_health, side="SELF"))
        high_friends.append(_entity(ids_f[pos - 1], pos, high_attack, high_health, side="SELF"))
    family, template = f"mf2c_stat_pair_{index:03d}", "mf2c_stat_counterfactual"
    low = _row(f"mf2c_stat_{index:03d}_low", family, template, "test",
               _base_state(index + 5000, low_friends, copy.deepcopy(enemies), 30),
               ["model_first_2c", "counterfactual_stats", "low"])
    high = _row(f"mf2c_stat_{index:03d}_high", family, template, "test",
                _base_state(index + 6000, high_friends, copy.deepcopy(enemies), 30),
                ["model_first_2c", "counterfactual_stats", "high"])
    return low, high


def _permute_pair(index: int) -> tuple[dict, dict]:
    source = _case(0x2C6000 + index, "test", "test_position_counterfactual", index, mode="safe")
    original = copy.deepcopy(source)
    original["scenario_id"] = f"mf2c_position_{index:03d}_original"
    original["family_id"] = f"mf2c_position_pair_{index:03d}"
    original["template_id"] = "mf2c_position_counterfactual"
    state = copy.deepcopy(source["state"])
    for side in ("self_player", "opponent"):
        board = state[side]["board"]
        size = len(board)
        for entity in board:
            entity["board_position"] = size + 1 - entity["board_position"]
        board.sort(key=lambda entity: entity["board_position"])
    permuted = _row(f"mf2c_position_{index:03d}_permuted", f"mf2c_position_pair_{index:03d}",
                    "mf2c_position_counterfactual", "test", state,
                    ["model_first_2c", "counterfactual_position", "permuted"])
    original["tags"] = ["model_first_2c", "counterfactual_position", "original"]
    return original, permuted


def _board_pair(index: int) -> tuple[dict, dict]:
    small = _case(0x2C7000 + index, "test", "test_board_counterfactual", index, mode="safe",
                  friendly_count=2, enemy_count=2)
    small["scenario_id"] = f"mf2c_board_{index:03d}_small"
    small["family_id"] = f"mf2c_board_pair_{index:03d}"
    small["template_id"] = "mf2c_board_counterfactual"
    state = copy.deepcopy(small["state"])
    friends, enemies = state["self_player"]["board"], state["opponent"]["board"]
    for extra in range(2):
        friends.append(_entity(f"MF2C_BOARD_{index:03d}_SF{extra}", len(friends) + 1,
                               1, 20, side="SELF"))
        enemies.append(_entity(f"MF2C_BOARD_{index:03d}_SE{extra}", len(enemies) + 1,
                               1, 20, side="OPPONENT"))
    large = _row(f"mf2c_board_{index:03d}_large", f"mf2c_board_pair_{index:03d}",
                 "mf2c_board_counterfactual", "test", state,
                 ["model_first_2c", "counterfactual_board_size", "large"])
    small["tags"] = ["model_first_2c", "counterfactual_board_size", "small"]
    return small, large


def _id_pair(index: int) -> tuple[dict, dict]:
    source = _case(0x2C8000 + index, "test", "test_id_counterfactual", index, mode="safe",
                   known=True)
    known = copy.deepcopy(source)
    unknown = copy.deepcopy(source)
    known["scenario_id"] = f"mf2c_id_{index:03d}_known"
    unknown["scenario_id"] = f"mf2c_id_{index:03d}_unknown"
    known["family_id"] = unknown["family_id"] = f"mf2c_id_pair_{index:03d}"
    known["template_id"] = unknown["template_id"] = "mf2c_id_counterfactual"
    for side in ("self_player", "opponent"):
        for entity in unknown["state"][side]["board"]:
            entity["card"]["card_id"] = f"MF2C_ID_{index:03d}_{side}_{entity['board_position']}"
    def remap_actions(row: dict) -> None:
        by_side_pos = {("SELF", e["board_position"]): e["card"]["card_id"]
                       for e in row["state"]["self_player"]["board"]}
        by_side_pos.update({("OPPONENT", e["board_position"]): e["card"]["card_id"]
                            for e in row["state"]["opponent"]["board"]})
        for action in row["legal_actions"]:
            if action["type"] != "ATTACK":
                continue
            action["source_card_id"] = by_side_pos[("SELF", action["source_board_position"])]
            if action["target_kind"] == "MINION":
                action["target_card_id"] = by_side_pos[("OPPONENT", action["target_board_position"])]
        correct_signatures = {_action_semantic_signature(a) for a in row["correct_actions"]}
        row["correct_actions"] = [a for a in row["legal_actions"]
                                   if _action_semantic_signature(a) in correct_signatures]
    remap_actions(unknown)
    known["tags"] = ["model_first_2c", "counterfactual_card_id", "known_core_id"]
    unknown["tags"] = ["model_first_2c", "counterfactual_card_id", "unknown_id"]
    return known, unknown


def _action_semantic_signature(action: dict) -> tuple:
    return tuple(action.get(key) for key in (
        "type", "source_board_position", "target_kind", "target_side", "target_board_position",
        "source_attack", "source_health", "target_attack", "target_health"))


def generate(seed: int = 20261009) -> tuple[dict[str, list[dict]], dict]:
    groups: dict[str, list[dict]] = {split: [] for split in COUNTS}
    provenance = []
    ordinal_global = 0
    # Train/validation each use separate implemented templates and identities.
    for split in ("train", "validation"):
        templates = TEMPLATES[split]
        for ordinal in range(COUNTS[split]):
            template = templates[ordinal % len(templates)]
            mode = ("safe", "safe", "multiple", "no_gain", "lethal")[ordinal % 5]
            split_seed = seed + ordinal_global * 104729
            row = _case(split_seed, split, template, ordinal, mode=mode)
            groups[split].append(row)
            provenance.append({"scenario_id": row["scenario_id"], "seed": split_seed,
                               "split": split, "family_id": row["family_id"],
                               "template_id": row["template_id"],
                               "fingerprint": scenario_content_fingerprint(row)})
            ordinal_global += 1
    # A 180-case varied test plus separate, deliberately paired interventions.
    for ordinal in range(180):
        template = TEMPLATES["test"][(ordinal * 2) % len(TEMPLATES["test"])]
        mode = ("safe", "safe", "multiple", "no_gain", "lethal")[ordinal % 5]
        split_seed = seed + 0x2C0000 + ordinal * 65537
        groups["test"].append(_case(split_seed, "test", template, ordinal, mode=mode))
    for factor, builder, count in (("stats", _stat_pair, 40), ("position", _permute_pair, 30),
                                   ("board", _board_pair, 20), ("id", _id_pair, 20)):
        for index in range(count):
            pair = builder(index)
            groups["test"].extend(pair)
            for row in pair:
                provenance.append({"scenario_id": row["scenario_id"], "seed": seed + index,
                                   "split": "test", "family_id": row["family_id"],
                                   "template_id": row["template_id"], "counterfactual_factor": factor,
                                   "fingerprint": scenario_content_fingerprint(row)})
    for row in groups["test"][:180]:
        provenance.append({"scenario_id": row["scenario_id"], "seed": seed + 0x2C0000,
                           "split": "test", "family_id": row["family_id"],
                           "template_id": row["template_id"],
                           "fingerprint": scenario_content_fingerprint(row)})
    return groups, {"seed": seed, "provenance": provenance, "ordinal_count": ordinal_global}


def _validate(groups: dict[str, list[dict]]) -> dict:
    for split, rows in groups.items():
        if len(rows) != COUNTS[split]:
            raise ValueError(f"Wrong {split} size: {len(rows)} != {COUNTS[split]}")
        if split != "test":
            validate_no_control_overlap(rows)
    seen_content = {}
    family_splits, template_splits = {}, {}
    for split, rows in groups.items():
        for row in rows:
            if row["label_status"] != "LABELED" or not row["correct_actions"]:
                raise ValueError(f"Unlabeled/ambiguous supervised row: {row['scenario_id']}")
            fingerprint = scenario_content_fingerprint(row)
            if fingerprint in seen_content:
                raise ValueError(f"Exact state/menu overlap across scenarios: {row['scenario_id']}")
            seen_content[fingerprint] = row["scenario_id"]
            family_splits.setdefault(row["family_id"], set()).add(split)
            template_splits.setdefault(row["template_id"], set()).add(split)
            for side in ("self_player", "opponent"):
                for entity in row["state"][side]["board"]:
                    card = entity["card"]
                    synthetic_id = (card["card_id"].startswith("MF2C_")
                                    and not card["card_id"].startswith("MF2C_ID_"))
                    if synthetic_id and (card["attack"] is not None or card["health"] is not None
                                         or card["mechanics"]):
                        raise ValueError(f"Synthetic identity has fake base stats: {row['scenario_id']}")
                    if entity["current_attack"] is None or entity["current_health"] is None:
                        raise ValueError(f"Current instance stats missing: {row['scenario_id']}")
    if any(len(splits) > 1 for splits in [*family_splits.values(), *template_splits.values()]):
        raise ValueError("Family/template provenance crosses splits")
    return {"counts": {key: len(value) for key, value in groups.items()},
            "families": {key: len({r['family_id'] for r in rows}) for key, rows in groups.items()},
            "templates": {key: len({r['template_id'] for r in rows}) for key, rows in groups.items()},
            "content_fingerprints_unique": len(seen_content)}


def write_dataset(output: Path, seed: int = 20261009) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite MODEL-FIRST-2C dataset: {output}")
    groups, generated = generate(seed)
    validation = _validate(groups)
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for split, rows in groups.items():
        path = output / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
                        encoding="utf-8", newline="\n")
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    provenance_path = output / "provenance.jsonl"
    provenance_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                                  for row in generated["provenance"]),
                               encoding="utf-8", newline="\n")
    hashes[provenance_path.name] = hashlib.sha256(provenance_path.read_bytes()).hexdigest()
    manifest = {"schema_version": 1, "generator": "model_first_2c.robust_local_combat/1",
                "seed": seed, "split_counts": validation["counts"],
                "family_counts": validation["families"], "template_counts": validation["templates"],
                "jsonl_sha256": hashes, "exact_content_fingerprints": validation["content_fingerprints_unique"],
                "gold_rule": "single-action guaranteed hero lethal; else all trades that kill a minion while source survives; else END_TURN when neither condition is present",
                "scope": "local one-action ranking objective; not proof of global move optimality",
                "test_composition": {"varied_base": 180, "stats_pairs": 40, "position_pairs": 30,
                                     "board_size_pairs": 20, "known_unknown_id_pairs": 20},
                "test_was_not_read_by_trainer": True}
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20261009)
    args = parser.parse_args()
    write_dataset(args.output, args.seed)


if __name__ == "__main__":
    main()
