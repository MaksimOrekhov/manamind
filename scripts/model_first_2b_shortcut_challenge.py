"""Run the no-training MODEL-FIRST-2B shortcut and feature-ablation checks."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from manamind.domain.game_state import GameState, PlayerObservation
from manamind.domain.serialization import game_state_from_dict
from manamind.live.snapshot import state_to_dict
from manamind.training.model_first_1_control import scenario_content_fingerprint
from manamind.training.policy_checkpoint import load_policy_checkpoint

ROOT = Path(__file__).resolve().parents[1]
OLD_DATA = ROOT / "data/processed_synthetic/model_first_2"
OLD_BASELINE = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
OLD_TUNED = ROOT / "data/processed_policy_ml2b/model_first_2_seed42/policy.pt"
DEFAULT_OUTPUT = ROOT / "data/processed_synthetic/model_first_2b"
KNOWN_ID = "Core_CS2_200"  # actual pinned metadata: vanilla Boulderfist Ogre, 6/7, no mechanics
KNOWN_META = {"cost": 6, "attack": 6, "health": 7, "card_class": "NEUTRAL",
              "card_type": "MINION", "mechanics": []}

sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_policy_baseline import (  # noqa: E402
    action_key, evaluate_model, load_scenarios, random_metrics,
)
from evaluate_policy_baseline import heuristic as policy_heuristic  # noqa: E402


def _card(card_id: str, *, base: dict | None = None) -> dict:
    base = base or {}
    return {"attack": base.get("attack"), "card_class": base.get("card_class", "UNKNOWN_CLASS"),
            "card_id": card_id, "card_type": base.get("card_type", "MINION"),
            "cost": base.get("cost"), "current_attack": None, "current_cost": None,
            "current_durability": None, "current_health": None, "current_spell_damage": None,
            "dark_gifts": None, "durability": None, "effect_turns_remaining": None,
            "freeze_turns_remaining": None, "health": base.get("health"),
            "held_spell_progress": None, "mechanics": list(base.get("mechanics", [])),
            "prepare_locked": None, "prepare_used": None, "race": None,
            "shatter_fragment": None, "shatter_original_card_id": None,
            "shatter_partner_hand_position": None, "trigger_remaining": None}


def _entity(card_id: str, position: int, attack: int, health: int, *, side: str,
            base: dict | None = None) -> dict:
    return {"board_position": position, "can_attack": side == "SELF",
            "cant_be_targeted_by_hero_powers": None, "cant_be_targeted_by_spells": None,
            "card": _card(card_id, base=base), "charge": False,
            "current_attack": attack, "current_health": health, "divine_shield": False,
            "dormant": False, "frozen": False, "immune": False, "lifesteal": False,
            "max_health": max(health, 1), "poisonous": False, "reborn": False,
            "rush": False, "silenced": False, "stealth": False, "taunt": False,
            "windfury": False}


def _attack(source: dict, target: dict) -> dict:
    return {"play_position": 0, "source_attack": source["current_attack"],
            "source_board_position": source["board_position"],
            "source_card_id": source["card"]["card_id"], "source_health": source["current_health"],
            "source_is_hero": False, "source_kind": "MINION",
            "target_attack": target["current_attack"], "target_board_position": target["board_position"],
            "target_card_id": target["card"]["card_id"], "target_health": target["current_health"],
            "target_is_hero": False, "target_kind": "MINION", "target_side": "OPPONENT",
            "target_taunt": False, "type": "ATTACK"}


def _state(friendly: list[dict], enemies: list[dict], turn: int) -> dict:
    state = state_to_dict(GameState(turn_number=turn, active_player="SELF",
                                    self_player=PlayerObservation(hero_health=30),
                                    opponent=PlayerObservation(hero_health=30)))
    state["self_player"]["board"] = friendly
    state["opponent"]["board"] = enemies
    return state


def _row(scenario_id: str, family: str, template: str, friendly: list[dict], enemies: list[dict],
         *, turn: int, split: str = "test", tags: list[str] | None = None) -> dict:
    state = state_to_dict(game_state_from_dict(_state(friendly, enemies, turn)))
    current_friendly = state["self_player"]["board"]
    current_enemies = state["opponent"]["board"]
    actions = [_attack(source, target) for source in current_friendly for target in current_enemies]
    correct = [action for action in actions
               if action["source_attack"] >= action["target_health"]
               and action["target_attack"] < action["source_health"]]
    actions.append({"play_position": 0, "type": "END_TURN"})
    if not correct:
        raise ValueError(f"No provably safe kill in {scenario_id}")
    return {"schema_version": 1, "scenario_id": scenario_id, "family_id": family,
            "template_id": template, "split": split, "category": "target_selection",
            "state": state, "legal_actions": actions, "correct_actions": correct,
            "label_status": "LABELED", "tags": tags or ["model_first_2b", "combat_arithmetic"]}


def _challenge_case(ordinal: int) -> dict:
    rng = random.Random(0x2B0000 + ordinal)
    friendly_count = 2 + ordinal % 3
    enemy_count = 2 + (ordinal // 3) % 3
    source_pos = 1 if ordinal % 4 == 0 else 2 + ((ordinal // 4) % (friendly_count - 1))
    target_pos = 1 + ((ordinal * 7 + ordinal // 5) % enemy_count)
    source_attack = 5 + ordinal % 4
    source_health = 8 + ordinal % 5
    target_health = source_attack - 1
    target_attack = source_health - 1
    ids_self = [f"MF2B_CHAL_{ordinal:03d}_SELF_{pos}" for pos in range(1, friendly_count + 1)]
    ids_enemy = [f"MF2B_CHAL_{ordinal:03d}_ENEMY_{pos}" for pos in range(1, enemy_count + 1)]
    friends, enemies = [], []
    sacrificial_pos = 1 if source_pos != 1 else 2
    for pos in range(1, friendly_count + 1):
        if pos == source_pos:
            attack, health = source_attack, source_health
        elif pos == sacrificial_pos:
            attack, health = target_health + 1, 2
        else:
            attack, health = rng.randint(1, 3), rng.randint(3, 5)
        friends.append(_entity(ids_self[pos - 1], pos, attack, health, side="SELF"))
    for pos in range(1, enemy_count + 1):
        if pos == target_pos:
            attack, health = target_attack, target_health
        else:
            attack, health = rng.randint(1, 7), 12 + rng.randint(0, 4)
        enemies.append(_entity(ids_enemy[pos - 1], pos, attack, health, side="OPPONENT"))
    return _row(f"mf2b_challenge_{ordinal:03d}", "mf2b_balanced_position_challenge",
                "mf2b_variable_board_safe_trade", friends, enemies, turn=ordinal + 1,
                tags=["model_first_2b", "heldout_diagnostic", "unknown_ids", "safe_trade",
                      f"gold_source_{source_pos}", f"gold_target_{target_pos}"])


def _remap_cards(row: dict, *, known: bool) -> dict:
    """ID-only counterfactual; clone exact real Core metadata into both arms."""
    result = copy.deepcopy(row)
    state = result["state"]
    mapping = {}
    for side, player in (("SELF", state["self_player"]), ("OPPONENT", state["opponent"])):
        for entity in player["board"]:
            old_id = entity["card"]["card_id"]
            position = entity["board_position"]
            new_id = KNOWN_ID if known else f"MF2B_IDCF_{result['scenario_id']}_{side}_{position}"
            mapping[(side, position, old_id)] = new_id
            entity["card"] = _card(new_id, base=KNOWN_META)
    correct_keys = {action_key(a) for a in result["correct_actions"]}
    actions, correct_actions = [], []
    for action in result["legal_actions"]:
        changed = copy.deepcopy(action)
        if changed["type"] == "ATTACK":
            if not changed.get("source_is_hero"):
                changed["source_card_id"] = mapping[("SELF", changed["source_board_position"],
                                                      changed["source_card_id"])]
            if not changed.get("target_is_hero"):
                changed["target_card_id"] = mapping[("OPPONENT", changed["target_board_position"],
                                                      changed["target_card_id"])]
        actions.append(changed)
        if action_key(action) in correct_keys:
            correct_actions.append(changed)
    result["legal_actions"] = actions
    result["correct_actions"] = correct_actions
    result["scenario_id"] += "_known" if known else "_unknown"
    result["family_id"] = f"mf2b_id_pair_{row['scenario_id']}"
    result["template_id"] = f"mf2b_id_template_{row['scenario_id']}"
    result["tags"] = ["model_first_2b", "counterfactual_id_only", "known_id" if known else "unknown_id"]
    result["state"] = state_to_dict(game_state_from_dict(state))
    return result


def _stat_pair(ordinal: int) -> tuple[dict, dict]:
    target_attack, target_health = 4 + ordinal % 4, 3 + ordinal % 3
    friends_low = [_entity(f"MF2B_STAT_{ordinal}_A1", 1, target_health, target_attack + 3, side="SELF"),
                   _entity(f"MF2B_STAT_{ordinal}_A2", 2, 1, 2, side="SELF")]
    friends_high = [_entity(f"MF2B_STAT_{ordinal}_A1", 1, target_health + 2, target_attack - 1, side="SELF"),
                    _entity(f"MF2B_STAT_{ordinal}_A2", 2, target_health, target_attack + 2, side="SELF")]
    enemies = [_entity(f"MF2B_STAT_{ordinal}_E1", 1, target_attack, target_health, side="OPPONENT"),
               _entity(f"MF2B_STAT_{ordinal}_E2", 2, 1, 15, side="OPPONENT")]
    family = f"mf2b_stat_pair_{ordinal:02d}"
    low = _row(f"{family}_low", family, f"{family}_template", friends_low, enemies, turn=ordinal + 1,
               tags=["model_first_2b", "counterfactual_current_combat_stats", "profile_low"])
    high = _row(f"{family}_high", family, f"{family}_template", friends_high, enemies, turn=ordinal + 100,
                tags=["model_first_2b", "counterfactual_current_combat_stats", "profile_high"])
    return low, high


def _board_pair(ordinal: int) -> tuple[dict, dict]:
    base = _challenge_case(ordinal + 400)
    small = copy.deepcopy(base)
    small["scenario_id"] = f"mf2b_board_{ordinal:02d}_small"
    small["family_id"] = f"mf2b_board_pair_{ordinal:02d}"
    small["template_id"] = f"mf2b_board_template_{ordinal:02d}"
    small["tags"] = ["model_first_2b", "counterfactual_board_size", "small"]
    state = copy.deepcopy(base["state"])
    friends = state["self_player"]["board"]
    enemies = state["opponent"]["board"]
    start_f, start_e = len(friends), len(enemies)
    for offset in (1, 2):
        friends.append(_entity(f"MF2B_BOARD_{ordinal}_EXTRA_F{offset}", start_f + offset,
                               1, 3, side="SELF"))
        enemies.append(_entity(f"MF2B_BOARD_{ordinal}_EXTRA_E{offset}", start_e + offset,
                               1, 15, side="OPPONENT"))
    large = _row(f"mf2b_board_{ordinal:02d}_large", f"mf2b_board_pair_{ordinal:02d}",
                 f"mf2b_board_template_{ordinal:02d}", friends, enemies, turn=ordinal + 200,
                 tags=["model_first_2b", "counterfactual_board_size", "large"])
    return small, large


def _permute_pair(ordinal: int) -> tuple[dict, dict]:
    base = _challenge_case(ordinal + 800)
    original = copy.deepcopy(base)
    original["scenario_id"] = f"mf2b_position_{ordinal:02d}_original"
    original["family_id"] = f"mf2b_position_pair_{ordinal:02d}"
    original["template_id"] = f"mf2b_position_template_{ordinal:02d}"
    original["tags"] = ["model_first_2b", "counterfactual_position", "original"]
    permuted_state = copy.deepcopy(base["state"])
    for side in ("self_player", "opponent"):
        board = permuted_state[side]["board"]
        n = len(board)
        for entity in board:
            entity["board_position"] = n + 1 - entity["board_position"]
        board.sort(key=lambda e: e["board_position"])
    permuted_state = state_to_dict(game_state_from_dict(permuted_state))
    friends, enemies = permuted_state["self_player"]["board"], permuted_state["opponent"]["board"]
    permuted = _row(f"mf2b_position_{ordinal:02d}_permuted", f"mf2b_position_pair_{ordinal:02d}",
                    f"mf2b_position_template_{ordinal:02d}", friends, enemies, turn=ordinal + 300,
                    tags=["model_first_2b", "counterfactual_position", "permuted"])
    return original, permuted


def _corrective_case(ordinal: int, split: str) -> dict:
    rng = random.Random((0x2B2000 if split == "train" else 0x2B8000) + ordinal)
    friendly_count = 2 + rng.randrange(3)
    enemy_count = 2 + rng.randrange(3)
    source_pos = 1 + rng.randrange(friendly_count)
    sacrificial_pos = next(pos for pos in range(1, friendly_count + 1) if pos != source_pos)
    target_pos = 1 + rng.randrange(enemy_count)
    target_health, target_attack = rng.randint(3, 8), rng.randint(3, 10)
    friends, enemies = [], []
    for position in range(1, friendly_count + 1):
        if position == source_pos:
            attack, health = target_health + rng.randint(0, 2), target_attack + rng.randint(1, 4)
        elif position == sacrificial_pos:
            attack, health = target_health + rng.randint(0, 2), max(1, target_attack - rng.randint(0, 2))
        else:
            attack, health = rng.randint(1, min(3, target_health - 1)), target_attack + rng.randint(1, 5)
        friends.append(_entity(f"MF2B_CORR_{split.upper()}_{ordinal:04d}_SELF_{position}",
                               position, attack, health, side="SELF"))
    for position in range(1, enemy_count + 1):
        if position == target_pos:
            attack, health = target_attack, target_health
        else:
            attack, health = rng.randint(1, 8), 12 + rng.randint(0, 4)
        enemies.append(_entity(f"MF2B_CORR_{split.upper()}_{ordinal:04d}_ENEMY_{position}",
                               position, attack, health, side="OPPONENT"))
    group = ordinal // 100
    family = f"mf2b_corrective_{split}_family_{group:02d}"
    template = f"mf2b_corrective_{split}_template_{group:02d}"
    return _row(f"mf2b_corrective_{split}_{ordinal:04d}", family, template, friends, enemies,
                turn=ordinal + 400, split=split,
                tags=["model_first_2b", "corrective_train_only", "combat_arithmetic"])


def generate_corrective_data(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite corrective data: {output}")
    train = [_corrective_case(i, "train") for i in range(1200)]
    validation_rows = [_corrective_case(i, "validation") for i in range(300)]
    _audit_challenge_gold(train + validation_rows)
    if ({r["family_id"] for r in train} & {r["family_id"] for r in validation_rows}
            or {r["template_id"] for r in train} & {r["template_id"] for r in validation_rows}):
        raise ValueError("Corrective train/validation family or template overlap")
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name, rows in (("train", train), ("validation", validation_rows)):
        path = output / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                        encoding="utf-8", newline="\n")
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"train_count": len(train), "validation_count": len(validation_rows),
            "train_templates": len({r["template_id"] for r in train}),
            "validation_templates": len({r["template_id"] for r in validation_rows}),
            "sha256": hashes}


def _positional_action(row: dict) -> str:
    attacks = [a for a in row["legal_actions"] if a["type"] == "ATTACK"]
    if not attacks:
        return "NO_POSITIONAL_ACTION"
    # Shortcut under test: first ready minion into first target; otherwise face.
    first_pair = [a for a in attacks if a["source_board_position"] == 1
                  and a["target_kind"] == "MINION" and a["target_board_position"] == 1]
    if first_pair:
        return action_key(first_pair[0])
    face = [a for a in attacks if a["source_board_position"] == 1 and a["target_kind"] == "HERO"]
    if face:
        return action_key(face[0])
    face = [a for a in attacks if a["target_kind"] == "HERO"]
    if face:
        return action_key(min(face, key=lambda a: (a.get("source_board_position", 0), action_key(a))))
    return "NO_POSITIONAL_ACTION"


def _predictor_results(rows, models, encoders) -> dict:
    correct_by_id = {row["scenario_id"]: {action_key(a) for a in row["correct_actions"]} for row in rows}
    output = {}
    for name, model in models.items():
        rankings = evaluate_model(model, encoders[name], rows, repeats=1)
        output[name] = {"metrics": rankings["overall"], "by_category": rankings["by_category"],
                        "inference_ms_mean": rankings["inference_ms_mean"],
                        "decisions": {d["scenario_id"]: d for d in rankings["decisions"]}}
    heuristic_rows = []
    heuristic_details = {}
    positional = {}
    random_top1, random_mrr = [], []
    for row in rows:
        state = game_state_from_dict(row["state"])
        prediction, status = policy_heuristic(state, row["legal_actions"])
        gold = correct_by_id[row["scenario_id"]]
        heuristic_rows.append((status == "APPLICABLE", prediction in gold if status == "APPLICABLE" else False))
        heuristic_details[row["scenario_id"]] = {"applicable": status == "APPLICABLE",
                                                  "correct": status == "APPLICABLE" and prediction in gold,
                                                  "action": prediction}
        pos = _positional_action(row)
        positional[row["scenario_id"]] = {"action": pos, "top_action": pos, "correct": pos in gold}
        random = random_metrics(len(row["legal_actions"]), len(gold))
        random_top1.append(random["top1"])
        random_mrr.append(random["mrr"])
    labeled_count = len(rows)
    applicable = sum(a for a, _ in heuristic_rows)
    output["heuristic"] = {"applicable": applicable,
                            "top1": (sum(ok for a, ok in heuristic_rows if a) / applicable if applicable else None),
                            "decisions": heuristic_details}
    output["positional"] = {"metrics": {"scenarios": labeled_count,
                                         "top1": sum(v["correct"] for v in positional.values()) / labeled_count,
                                         "top1_count": sum(v["correct"] for v in positional.values())},
                            "decisions": positional}
    output["random"] = {"top1": sum(random_top1) / labeled_count, "mrr": sum(random_mrr) / labeled_count}
    return output


def _summary_and_pairs(rows, predictions, factor: str) -> dict:
    pairs = defaultdict(dict)
    for row in rows:
        parts = row["scenario_id"].rsplit("_", 1)
        if factor == "id":
            pair_key = row["scenario_id"].rsplit("_", 1)[0]
            arm = parts[1]
        else:
            arm = parts[1]
            pair_key = parts[0]
        pairs[pair_key][arm] = row["scenario_id"]
    result = {name: {} for name in predictions if name not in ("random",)}
    for name in result:
        if name == "positional":
            decision = predictions[name]["decisions"]
            correct = {row["scenario_id"]: decision[row["scenario_id"]]["correct"] for row in rows}
        elif name == "heuristic":
            decision = predictions[name]["decisions"]
            correct = {row["scenario_id"]: decision[row["scenario_id"]]["correct"] for row in rows}
        else:
            decision = predictions[name]["decisions"]
            correct = {row["scenario_id"]: not decision[row["scenario_id"]]["wrong_top1"] for row in rows}
        items = list(correct.values())
        pair_values = [tuple(correct[scenario_id] for scenario_id in pair.values())
                       for pair in pairs.values() if len(pair) == 2]
        result[name] = {"scenarios": len(rows), "top1": sum(items) / len(items),
                        "correct_count": sum(items), "pairs": len(pair_values),
                        "both_correct": sum(all(p) for p in pair_values) / len(pair_values) if pair_values else None,
                        "neither_correct": sum(not any(p) for p in pair_values) / len(pair_values) if pair_values else None}
        if factor == "position_permutation":
            decisions = predictions[name]["decisions"]
            stable = []
            for pair in pairs.values():
                if len(pair) != 2:
                    continue
                semantic_actions = []
                for scenario_id in pair.values():
                    action_key_text = (decisions[scenario_id]["top_action"] if name not in ("heuristic",)
                                       else decisions[scenario_id]["action"])
                    if name == "positional":
                        action_key_text = decisions[scenario_id]["action"]
                    action = json.loads(action_key_text) if action_key_text != "NO_POSITIONAL_ACTION" else {}
                    semantic_actions.append((action.get("source_card_id"), action.get("target_card_id"),
                                              action.get("type")))
                stable.append(semantic_actions[0] == semantic_actions[1])
            result[name]["same_entity_action_after_permutation"] = (
                sum(stable) / len(stable) if stable else None)
    result["random"] = {"top1": predictions["random"]["top1"], "mrr": predictions["random"]["mrr"]}
    return result


def _original_results(baseline_path: Path, trained_path: Path) -> dict:
    models, encoders = {}, {}
    for name, path in (("baseline_policy_v2", baseline_path), ("finetuned_policy_v2", trained_path)):
        models[name], encoders[name], _ = load_policy_checkpoint(path, device="cpu")
    results = {}
    for split in ("train", "validation", "test"):
        rows = load_scenarios(OLD_DATA / f"{split}.jsonl")
        predictions = _predictor_results(rows, models, encoders)
        results[split] = {name: {"top1": predictions[name]["metrics"]["top1"],
                                 "mrr": predictions[name]["metrics"]["mrr"]}
                          for name in ("baseline_policy_v2", "finetuned_policy_v2")}
        results[split].update({"heuristic": {"top1": predictions["heuristic"]["top1"],
                                              "applicable": predictions["heuristic"]["applicable"]},
                               "positional": predictions["positional"]["metrics"],
                               "random": predictions["random"]})
        if split == "test":
            family_stats = defaultdict(Counter)
            for row in rows:
                decision = predictions["baseline_policy_v2"]["decisions"][row["scenario_id"]]
                top_key = decision["top_action"]
                top = next(a for a in row["legal_actions"] if action_key(a) == top_key)
                family_stats[row["family_id"]]["total"] += 1
                family_stats[row["family_id"]]["top1_correct"] += int(not decision["wrong_top1"])
                family_stats[row["family_id"]]["end_turn_top1"] += int(top["type"] == "END_TURN")
            results[split]["baseline_by_family"] = {family: dict(stats) for family, stats in family_stats.items()}
    return results


def generate_challenge(count: int = 240) -> list[dict]:
    rows = [_challenge_case(i) for i in range(count)]
    if count != 240:
        raise ValueError("Challenge size is fixed at 240; do not vary the diagnostic set after inspection")
    sources = Counter(int(tag.split("_")[-1]) for row in rows for tag in row["tags"] if tag.startswith("gold_source_"))
    targets = Counter(int(tag.split("_")[-1]) for row in rows for tag in row["tags"] if tag.startswith("gold_target_"))
    if len(sources) < 2 or len(targets) < 2 or sources[1] >= count or targets[1] >= count:
        raise ValueError("Diagnostic challenge does not sufficiently vary selected positions")
    return rows


def _audit_challenge_gold(rows: list[dict]) -> dict:
    source_positions, target_positions = Counter(), Counter()
    kill_but_die = unkillable_targets = ambiguous = 0
    for row in rows:
        arithmetic_gold = []
        target_can_be_killed = set()
        for action in row["legal_actions"]:
            if action["type"] != "ATTACK" or action.get("target_kind") != "MINION":
                continue
            if action["source_attack"] >= action["target_health"]:
                target_can_be_killed.add(action["target_board_position"])
                if action["target_attack"] >= action["source_health"]:
                    kill_but_die += 1
                else:
                    arithmetic_gold.append(action)
        recorded = {action_key(action) for action in row["correct_actions"]}
        derived = {action_key(action) for action in arithmetic_gold}
        if len(derived) != 1:
            ambiguous += 1
        if recorded != derived:
            raise ValueError(f"Gold label does not match direct combat arithmetic: {row['scenario_id']}")
        source_positions.update(a["source_board_position"] for a in arithmetic_gold)
        target_positions.update(a["target_board_position"] for a in arithmetic_gold)
        for target in {a["target_board_position"] for a in row["legal_actions"]
                       if a["type"] == "ATTACK" and a.get("target_kind") == "MINION"}:
            target_attacks = [a for a in row["legal_actions"]
                              if a["type"] == "ATTACK" and a.get("target_kind") == "MINION"
                              and a["target_board_position"] == target]
            if target_attacks and all(a["source_attack"] < a["target_health"] for a in target_attacks):
                unkillable_targets += 1
    if ambiguous:
        raise ValueError(f"Diagnostic challenge contains {ambiguous} ambiguous scenarios")
    return {"scenario_count": len(rows), "unambiguous_scenarios": len(rows) - ambiguous,
            "gold_source_position_counts": dict(source_positions),
            "gold_target_position_counts": dict(target_positions),
            "kill_target_lose_attacker_actions": kill_but_die,
            "targets_not_killable_in_one_attack": unkillable_targets}


def generate_counterfactuals(old_test: list[dict], challenge: list[dict]) -> dict[str, list[dict]]:
    ids = []
    for index, source_row in enumerate(old_test):
        known, unknown = _remap_cards(source_row, known=True), _remap_cards(source_row, known=False)
        known["scenario_id"] = f"mf2b_oldtest_id_{index:03d}_known"
        unknown["scenario_id"] = f"mf2b_oldtest_id_{index:03d}_unknown"
        known["family_id"] = unknown["family_id"] = f"mf2b_oldtest_id_pair_{index:03d}"
        known["template_id"] = unknown["template_id"] = f"mf2b_oldtest_id_template_{index:03d}"
        ids.extend((known, unknown))
    stats = [scenario for i in range(48) for scenario in _stat_pair(i)]
    board = [scenario for i in range(48) for scenario in _board_pair(i)]
    positions = [scenario for i in range(48) for scenario in _permute_pair(i)]
    return {"id": ids, "combat_stats": stats, "board_size": board, "position_permutation": positions}


def _verify_metadata(rows: list[dict]) -> dict:
    bad_base, wrong_ids, missing_current = 0, 0, 0
    for row in rows:
        for side in ("self_player", "opponent"):
            for entity in row["state"][side]["board"]:
                card = entity["card"]
                if card["card_id"] == "BE_036":
                    wrong_ids += 1
                if card["card_id"].startswith("MF2B_CHAL_") and (
                        card["attack"] is not None or card["health"] is not None or card["mechanics"]):
                    bad_base += 1
                if entity["current_attack"] is None or entity["current_health"] is None:
                    missing_current += 1
    if wrong_ids or bad_base or missing_current:
        raise ValueError("Synthetic base/current-stat contract failed")
    return {"scenario_count": len(rows), "entity_count": sum(
        len(r["state"]["self_player"]["board"]) + len(r["state"]["opponent"]["board"]) for r in rows),
        "challenge_synthetic_base_stats_missing": True,
        "all_current_stats_explicit": True, "be_036_occurrences": 0}


def run(output: Path = DEFAULT_OUTPUT, baseline_path: Path = OLD_BASELINE, trained_path: Path = OLD_TUNED,
        training_summary_path: Path | None = None) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite MODEL-FIRST-2B output: {output}")
    original = _original_results(baseline_path, trained_path)
    challenge = generate_challenge()
    gold_audit = _audit_challenge_gold(challenge)
    old_test = load_scenarios(OLD_DATA / "test.jsonl")
    counterfactuals = generate_counterfactuals(old_test, challenge)
    validation = load_scenarios  # keep generated JSONL on the same strict parser path
    output.mkdir(parents=True, exist_ok=False)
    (output / "challenge.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in challenge),
                                             encoding="utf-8", newline="\n")
    (output / "challenge_provenance.jsonl").write_text("".join(json.dumps({
        "scenario_id": r["scenario_id"], "family_id": r["family_id"], "template_id": r["template_id"],
        "seed": 0x2B0000 + i, "gold_rule": "kill target and survive; direct attack/health arithmetic",
        "fingerprint": scenario_content_fingerprint(r)} , sort_keys=True) + "\n"
        for i, r in enumerate(challenge)), encoding="utf-8", newline="\n")
    loaded_challenge = validation(output / "challenge.jsonl")
    counter_results, hashes, metadata = {}, {}, {}
    models, encoders = {}, {}
    for name, path in (("baseline_policy_v2", baseline_path), ("finetuned_policy_v2", trained_path)):
        models[name], encoders[name], _ = load_policy_checkpoint(path, device="cpu")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    challenge_predictions = _predictor_results(loaded_challenge, models, encoders)
    challenge_metrics = {name: challenge_predictions[name]["metrics"] for name in models}
    challenge_metrics.update({"heuristic": {"top1": challenge_predictions["heuristic"]["top1"],
                                             "applicable": challenge_predictions["heuristic"]["applicable"]},
                              "positional": challenge_predictions["positional"]["metrics"],
                              "random": challenge_predictions["random"]})
    challenge_errors = {name: [sid for sid, d in prediction["decisions"].items()
                               if d["wrong_top1"]]
                       for name, prediction in challenge_predictions.items() if name in models}
    for factor, rows in counterfactuals.items():
        path = output / f"counterfactual_{factor}.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
        checked = validation(path)
        predictions = _predictor_results(checked, models, encoders)
        counter_results[factor] = _summary_and_pairs(checked, predictions, factor)
        if factor == "id":
            counter_results[factor]["arms"] = {
                "known_core_cs2_200_6_7": {name: predictions[name]["metrics"]["top1"] for name in models},
                "unknown_synthetic_same_properties": {name: predictions[name]["metrics"]["top1"]
                                                       for name in models}}
        elif factor in {"combat_stats", "board_size", "position_permutation"}:
            arms = {}
            for arm_name in ("low", "high") if factor == "combat_stats" else (
                    ("small", "large") if factor == "board_size" else ("original", "permuted")):
                arm_rows = [r for r in checked if r["scenario_id"].endswith(f"_{arm_name}")]
                if arm_rows:
                    arm_predictions = _predictor_results(arm_rows, models, encoders)
                    arms[arm_name] = {name: arm_predictions[name]["metrics"]["top1"] for name in models}
                    arms[arm_name].update({"heuristic": arm_predictions["heuristic"]["top1"],
                                           "positional": arm_predictions["positional"]["metrics"]["top1"]})
            counter_results[factor]["arms"] = arms
    metadata = _verify_metadata(loaded_challenge)
    dataset_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(output.glob("*.jsonl"))}
    result = {"schema_version": 1, "experiment": "MODEL-FIRST-2B Shortcut Challenge",
              "training_performed": training_summary_path is not None,
              "corrective_training": (json.loads(training_summary_path.read_text(encoding="utf-8"))
                                      if training_summary_path is not None else None),
              "source_checkpoints": hashes,
              "original_model_first_2": original, "challenge": {
                  "count": len(loaded_challenge), "metadata_contract": metadata,
                  "positional_source_distribution": dict(Counter(int(t.split("_")[-1]) for r in loaded_challenge
                      for t in r["tags"] if t.startswith("gold_source_"))),
              "positional_target_distribution": dict(Counter(int(t.split("_")[-1]) for r in loaded_challenge
                      for t in r["tags"] if t.startswith("gold_target_"))),
                  "gold_audit": gold_audit,
                  "metrics": challenge_metrics, "model_top1_errors": challenge_errors},
              "counterfactuals": counter_results, "counterfactual_jsonl_sha256": dataset_hashes,
              "limits": ["Synthetic diagnostic, not evidence of match strength.",
                         "ID pairs change identity only while holding a copied known-card property bundle constant.",
                         "A repeated score after any corrective training would be a revisited, not independent, test."]}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate-corrective-output", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline", type=Path, default=OLD_BASELINE)
    parser.add_argument("--trained", type=Path, default=OLD_TUNED)
    parser.add_argument("--training-summary", type=Path)
    parser.add_argument("--results", type=Path, default=ROOT / "reports/model_first_2b/results.json")
    args = parser.parse_args()
    if args.generate_corrective_output is not None:
        print(json.dumps(generate_corrective_data(args.generate_corrective_output), indent=2))
        return
    result = run(args.output, args.baseline, args.trained, args.training_summary)
    report = args.results
    report.parent.mkdir(parents=True, exist_ok=True)
    if report.exists():
        raise FileExistsError(f"Refusing to overwrite MODEL-FIRST-2B results: {report}")
    report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "challenge": result["challenge"]["metrics"],
                      "counterfactuals": result["counterfactuals"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
