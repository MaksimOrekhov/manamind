"""Evaluate saved Policy checkpoints against a small, frozen scenario set.

The scenarios are controlled ranking checks, not proof of game strength.  The
heuristic deliberately supports only ordinary attacks, visible Taunt, simple
combat trades, and a narrow lethal check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch

from manamind.domain.policy_action import ACTION_FIELDS, ACTION_TYPES
from manamind.domain.serialization import game_state_from_dict
from manamind.live.snapshot import canonical_json, state_to_dict
from manamind.models.policy import ACTION_FEATURE_NAMES, POLICY_STATE_FEATURE_NAMES
from manamind.models.policy_inputs import encode_policy_inputs, representation_of
from manamind.models.policy_v2 import feature_contract
from manamind.training.policy_checkpoint import load_policy_checkpoint
from manamind.training.model_first_1_control import verify_frozen_control

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = ROOT / "data/evaluation/model_first_1/control_test.jsonl"
DEFAULT_V1 = ROOT / "data/processed_policy_ml1c/baseline_seed42_v1/policy.pt"
DEFAULT_V2 = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"


def action_key(action: dict) -> str:
    """Canonical semantic action; protocol/entity handles never enter scenarios."""
    return canonical_json({k: v for k, v in action.items() if k != "entity_id"})


def load_scenarios(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if Path(path).resolve() == DEFAULT_SCENARIOS.resolve():
        frozen_ids, frozen_families, frozen_templates, _ = verify_frozen_control()
        if ({row.get("scenario_id") for row in rows} != frozen_ids
                or {row.get("family_id") for row in rows} != frozen_families
                or {row.get("template_id") for row in rows} != frozen_templates):
            raise ValueError("Frozen MODEL-FIRST-1 control identities do not match lock")
    seen = set()
    for row in rows:
        required = {"schema_version", "scenario_id", "family_id", "template_id", "split", "category", "state",
                    "legal_actions", "correct_actions", "label_status", "tags"}
        if set(row) != required or row["schema_version"] != 1:
            raise ValueError("Invalid scenario schema")
        if row["scenario_id"] in seen:
            raise ValueError(f"Duplicate scenario_id: {row['scenario_id']}")
        seen.add(row["scenario_id"])
        if row["split"] not in {"train", "validation", "test"}:
            raise ValueError(f"Invalid split in {row['scenario_id']}")
        if row["label_status"] not in {"LABELED", "AMBIGUOUS"}:
            raise ValueError(f"Invalid label_status in {row['scenario_id']}")
        if (not isinstance(row["scenario_id"], str) or not row["scenario_id"]
                or not isinstance(row["family_id"], str) or not row["family_id"]
                or not isinstance(row["template_id"], str) or not row["template_id"]
                or not isinstance(row["category"], str) or not isinstance(row["tags"], list)):
            raise ValueError("Scenario identity/category/tags are invalid")
        if not isinstance(row["legal_actions"], list) or not row["legal_actions"]:
            raise ValueError(f"Empty legal menu in {row['scenario_id']}")
        if len({action_key(a) for a in row["legal_actions"]}) != len(row["legal_actions"]):
            raise ValueError(f"Duplicate semantic actions in {row['scenario_id']}")
        if any(not isinstance(a, dict) or a.get("type") not in ACTION_TYPES
               or set(a) - ACTION_FIELDS or type(a.get("play_position")) is not int
               for a in row["legal_actions"]):
            raise ValueError(f"Unsupported legal action fields in {row['scenario_id']}")
        actions = {action_key(a) for a in row["legal_actions"]}
        correct = row["correct_actions"]
        if not isinstance(correct, list) or any(action_key(a) not in actions for a in correct):
            raise ValueError(f"Expected actions must be present in legal menu: {row['scenario_id']}")
        if len({action_key(a) for a in correct}) != len(correct):
            raise ValueError(f"Duplicate expected actions in {row['scenario_id']}")
        if row["label_status"] == "LABELED" and not correct:
            raise ValueError(f"Labeled scenario needs at least one correct action: {row['scenario_id']}")
        if row["label_status"] == "AMBIGUOUS" and correct:
            raise ValueError(f"Ambiguous scenario cannot assert correct actions: {row['scenario_id']}")
        state = game_state_from_dict(row["state"])
        if state_to_dict(state) != row["state"]:
            raise ValueError(f"State is not canonical: {row['scenario_id']}")
        _validate_attack_menu(state, row["legal_actions"], row["scenario_id"])
    family_splits = defaultdict(set)
    template_splits = defaultdict(set)
    for row in rows:
        family_splits[row["family_id"]].add(row["split"])
        template_splits[row["template_id"]].add(row["split"])
    if (any(len(splits) > 1 for splits in family_splits.values())
            or any(len(splits) > 1 for splits in template_splits.values())):
        raise ValueError("A scenario family/template cannot cross train/validation/test splits")
    return rows


def _validate_attack_menu(state, actions, scenario_id):
    """Check visible source/target links and obvious Taunt restrictions."""
    minions = {m.board_position: m for m in state.self_player.board}
    enemies = {m.board_position: m for m in state.opponent.board}
    taunts = {p for p, m in enemies.items() if m.taunt}
    for action in actions:
        if action["type"] != "ATTACK":
            continue
        if action.get("source_kind") != "MINION":
            raise ValueError(f"Scenario attack source kind is outside this control set: {scenario_id}")
        if action.get("source_kind") == "MINION":
            source = minions.get(action.get("source_board_position"))
            if source is None or not source.can_attack or source.card.card_id != action.get("source_card_id"):
                raise ValueError(f"Invalid attack source in {scenario_id}")
            if action.get("source_attack") != source.current_attack or action.get("source_health") != source.current_health:
                raise ValueError(f"Attack source stats disagree with state in {scenario_id}")
        if action.get("target_kind") == "MINION" and action.get("target_side") == "OPPONENT":
                target = enemies.get(action.get("target_board_position"))
                if target is None or target.card.card_id != action.get("target_card_id"):
                    raise ValueError(f"Invalid attack target in {scenario_id}")
                if action.get("target_attack") != target.current_attack or action.get("target_health") != target.current_health:
                    raise ValueError(f"Attack target stats disagree with state in {scenario_id}")
                if action.get("target_taunt", False) != target.taunt:
                    raise ValueError(f"Attack Taunt flag disagrees with state in {scenario_id}")
        if taunts and action.get("target_kind") == "HERO" and action.get("target_side") == "OPPONENT":
            raise ValueError(f"Face attack bypasses visible Taunt in {scenario_id}")
        if (action.get("target_kind") == "MINION" and action.get("target_side") != "OPPONENT"):
            raise ValueError(f"Control scenario attacks a non-opponent minion: {scenario_id}")
        if action.get("target_kind") not in {"HERO", "MINION"} or action.get("target_side") != "OPPONENT":
            raise ValueError(f"Control scenario has an unsupported attack target: {scenario_id}")
        if taunts and action.get("target_kind") == "MINION" and not action.get("target_taunt"):
            raise ValueError(f"Attack bypasses visible Taunt in {scenario_id}")


def random_metrics(menu_size: int, correct_count: int) -> dict:
    if not correct_count:
        return {"top1": None, "top3": None, "mrr": None}
    # Probability the first correct choice in a random permutation is at rank r.
    mrr = sum((math.comb(menu_size - r, correct_count - 1) / math.comb(menu_size, correct_count)) / r
              for r in range(1, menu_size - correct_count + 2))
    top3 = (None if menu_size < 3 else 1.0 if menu_size - correct_count < 3 else
            1.0 - math.comb(menu_size - correct_count, 3) / math.comb(menu_size, 3))
    return {"top1": correct_count / menu_size, "top3": top3, "mrr": mrr}


def heuristic(state, actions) -> tuple[str, str]:
    """Return semantic best action key and status; no unsupported mechanics guessed."""
    attacks = [a for a in actions if a["type"] == "ATTACK"]
    if not attacks or any(a["type"] not in {"ATTACK", "END_TURN"} for a in actions):
        return "NOT_APPLICABLE", "NOT_APPLICABLE"
    if any(m.divine_shield or m.poisonous or m.immune or m.stealth or m.reborn or m.dormant
           for m in (*state.self_player.board, *state.opponent.board)):
        return "NOT_APPLICABLE", "NOT_APPLICABLE"
    ready_sources = {m.board_position for m in state.self_player.board if m.can_attack}
    menu_sources = {a.get("source_board_position") for a in attacks}
    if not ready_sources or menu_sources != ready_sources:
        return "NOT_APPLICABLE", "NOT_APPLICABLE"
    enemy = state.opponent
    if any(m.taunt for m in enemy.board):
        # Taunt is explicitly modeled; skip if the menu does not expose the whole Taunt set.
        if any(a.get("target_kind") == "HERO" and a.get("target_side") == "OPPONENT" for a in attacks):
            return "NOT_APPLICABLE", "NOT_APPLICABLE"
        attack_by_source = defaultdict(list)
        for a in attacks:
            attack_by_source[a.get("source_board_position")].append(a)
        candidates = [a for a in attacks if a.get("target_kind") == "MINION"
                      and a.get("target_side") == "OPPONENT" and a.get("target_taunt")]
        if not candidates:
            return "NOT_APPLICABLE", "NOT_APPLICABLE"
        score = lambda a: (10 if a["source_attack"] >= a["target_health"]
                           and a["target_attack"] < a["source_health"] else
                           2 if a["source_attack"] >= a["target_health"] else -1)
        best = max(score(a) for a in candidates)
        return (min(action_key(a) for a in candidates if score(a) == best), "APPLICABLE")
    total_attack = sum(m.current_attack for m in state.self_player.board if m.can_attack)
    face = [a for a in attacks if a.get("target_kind") == "HERO" and a.get("target_side") == "OPPONENT"]
    face_sources = {a.get("source_board_position") for a in face}
    if (face and face_sources == ready_sources and enemy.hero_health + enemy.armor > 0
            and total_attack >= enemy.hero_health + enemy.armor):
        return min(action_key(a) for a in face), "APPLICABLE"
    scores = []
    for action in attacks:
        if action.get("target_kind") != "MINION" or action.get("target_side") != "OPPONENT":
            continue
        kills = action["source_attack"] >= action["target_health"]
        survives = action["target_attack"] < action["source_health"]
        if kills and survives:
            scores.append((3, action))
        elif kills:
            scores.append((1, action))
        elif not survives:
            scores.append((-2, action))
        else:
            scores.append((0, action))
    if not scores:
        return "NOT_APPLICABLE", "NOT_APPLICABLE"
    top = max(score for score, _ in scores)
    if top <= 0:
        return "NOT_APPLICABLE", "NOT_APPLICABLE"
    best = [a for score, a in scores if score == top]
    return min(action_key(a) for a in best), "APPLICABLE"


def rank_one(policy, encoder, row) -> tuple[list[int], float, float, dict[str, float]]:
    total_start = time.perf_counter_ns()
    state = game_state_from_dict(row["state"])
    device = next(policy.parameters()).device
    inputs = encode_policy_inputs(state, row["legal_actions"], encoder,
                                  representation=representation_of(policy), device=device)
    forward_start = time.perf_counter_ns()
    with torch.inference_mode():
        scores = policy(*inputs)
    forward_ms = (time.perf_counter_ns() - forward_start) / 1_000_000
    elapsed = (time.perf_counter_ns() - total_start) / 1_000_000
    if scores.ndim != 1 or not torch.isfinite(scores).all():
        raise ValueError(f"Invalid policy output for {row['scenario_id']}")
    # Stable semantic tie break makes output independent of menu order.
    indexed = sorted(range(len(row["legal_actions"])),
                     key=lambda i: (-float(scores[i]), action_key(row["legal_actions"][i])))
    by_action = {action_key(action): float(scores[i]) for i, action in enumerate(row["legal_actions"])}
    return indexed, elapsed, forward_ms, by_action


def evaluate_model(policy, encoder, rows, repeats=3) -> dict:
    details, elapsed, forward_elapsed = [], [], []
    for row in rows[:min(3, len(rows))]:
        rank_one(policy, encoder, row)
    for row in rows:
        orders = []
        score_maps = []
        for _ in range(repeats):
            order, ms, forward_ms, score_map = rank_one(policy, encoder, row)
            orders.append([action_key(row["legal_actions"][i]) for i in order])
            score_maps.append(score_map)
            elapsed.append(ms)
            forward_elapsed.append(forward_ms)
        if len(set(tuple(o) for o in orders)) != 1:
            raise ValueError(f"Nondeterministic ranking: {row['scenario_id']}")
        if any(any(not math.isclose(score_maps[0][key], scores[key], rel_tol=0, abs_tol=1e-7)
                   for key in score_maps[0]) for scores in score_maps[1:]):
            raise ValueError(f"Nondeterministic raw scores: {row['scenario_id']}")
        score_map = score_maps[0]
        if row["label_status"] == "AMBIGUOUS":
            details.append({"scenario_id": row["scenario_id"], "status": "AMBIGUOUS"})
            continue
        correct = {action_key(a) for a in row["correct_actions"]}
        ranked = orders[0]
        correct_ranks = [ranked.index(key) + 1 for key in correct]
        rank = min(correct_ranks)
        margin = (score_map[ranked[0]] - score_map[ranked[1]]) if len(ranked) > 1 else None
        details.append({"scenario_id": row["scenario_id"], "category": row["category"],
                        "status": "APPLICABLE", "rank": rank, "correct_ranks": sorted(correct_ranks),
                        "top_action": ranked[0], "wrong_top1": ranked[0] not in correct,
                        "top_gap_raw": margin, "menu_size": len(ranked)})
    # Paired menu permutations must preserve each semantic action's raw score.
    by_family = defaultdict(list)
    for row in rows:
        if "menu_permutation" in row["tags"]:
            by_family[row["family_id"]].append(row)
    for family, variants in by_family.items():
        if len(variants) < 2:
            raise ValueError(f"Menu permutation family needs at least two variants: {family}")
        reference = None
        for row in variants:
            _, _, _, scores = rank_one(policy, encoder, row)
            if reference is None:
                reference = scores
            elif reference.keys() != scores.keys() or any(
                    not math.isclose(reference[key], scores[key], rel_tol=0, abs_tol=1e-7) for key in reference):
                raise ValueError(f"Menu order changed semantic action scores: {family}")
    labeled = [d for d in details if d["status"] == "APPLICABLE"]
    groups = defaultdict(list)
    for row, detail in zip(rows, details):
        if detail["status"] == "APPLICABLE":
            groups[row["category"]].append(detail)
    def metrics(items):
        if not items:
            return {"scenarios": 0, "top1": None, "top3": None, "mrr": None}
        top3_items = [d for d in items if d["menu_size"] >= 3]
        return {"scenarios": len(items), "top1_count": sum(d["rank"] == 1 for d in items),
                "top1": sum(d["rank"] == 1 for d in items) / len(items),
                "top3_count": sum(d["rank"] <= 3 for d in top3_items),
                "top3_denominator": len(top3_items),
                "top3": sum(d["rank"] <= 3 for d in top3_items) / len(top3_items) if top3_items else None,
                "mrr": sum(1 / d["rank"] for d in items) / len(items),
                "wrong_top1": sum(d["wrong_top1"] for d in items)}
    return {"overall": metrics(labeled), "by_category": {k: metrics(v) for k, v in sorted(groups.items())},
            "ambiguous": sum(d["status"] == "AMBIGUOUS" for d in details),
            "not_applicable": 0, "inference_ms_mean": statistics.mean(elapsed) if elapsed else None,
            "inference_ms_median": statistics.median(elapsed) if elapsed else None,
            "policy_forward_ms_mean": statistics.mean(forward_elapsed) if forward_elapsed else None,
            "policy_forward_ms_median": statistics.median(forward_elapsed) if forward_elapsed else None,
            "inference_timing_scope": "state decode + feature encoding + model forward; excludes checkpoint load",
            "inference_repeats": repeats, "warmup_scenarios": min(3, len(rows)), "decisions": details}


def evaluate_heuristic(rows) -> dict:
    decisions, groups = [], defaultdict(list)
    for row in rows:
        if row["label_status"] == "AMBIGUOUS":
            decisions.append({"scenario_id": row["scenario_id"], "status": "AMBIGUOUS"})
            continue
        state = game_state_from_dict(row["state"])
        prediction, status = heuristic(state, row["legal_actions"])
        correct = {action_key(a) for a in row["correct_actions"]}
        detail = {"scenario_id": row["scenario_id"], "category": row["category"], "status": status,
                  "wrong_top1": status == "APPLICABLE" and prediction not in correct,
                  "top1": status == "APPLICABLE" and prediction in correct}
        decisions.append(detail)
        if status == "APPLICABLE":
            groups[row["category"]].append(detail)
    def metrics(items):
        return {"applicable": len(items), "top1_count": sum(d["top1"] for d in items),
                "top1": sum(d["top1"] for d in items) / len(items) if items else None,
                "wrong_top1": sum(d["wrong_top1"] for d in items)}
    return {"overall": metrics([d for d in decisions if d["status"] == "APPLICABLE"]),
            "by_category": {k: metrics(v) for k, v in sorted(groups.items())},
            "ambiguous": sum(d["status"] == "AMBIGUOUS" for d in decisions),
            "not_applicable": sum(d["status"] == "NOT_APPLICABLE" for d in decisions),
            "decisions": decisions}


def evaluate_random(rows) -> dict:
    items, groups = [], defaultdict(list)
    for row in rows:
        if row["label_status"] == "AMBIGUOUS":
            continue
        item = random_metrics(len(row["legal_actions"]), len(row["correct_actions"]))
        item["scenario_id"] = row["scenario_id"]
        items.append(item)
        groups[row["category"]].append(item)
    def aggregate(values):
        top3_values = [v["top3"] for v in values if v["top3"] is not None]
        return {"top1": sum(v["top1"] for v in values) / len(values),
                "top3": sum(top3_values) / len(top3_values) if top3_values else None,
                "top3_count": len(top3_values), "mrr": sum(v["mrr"] for v in values) / len(values)}
    return {"overall": aggregate(items), "by_category": {k: aggregate(v) for k, v in sorted(groups.items())}}


def compare_common_applicable(rows, model_results, heuristic_result) -> dict:
    """Compare every ranker on the same labeled scenarios where heuristic applies."""
    applicable_ids = {d["scenario_id"] for d in heuristic_result["decisions"]
                      if d["status"] == "APPLICABLE"}
    common_rows = [row for row in rows if row["scenario_id"] in applicable_ids
                   and row["label_status"] == "LABELED"]
    def aggregate(model_details=None):
        if model_details is not None:
            by_id = {d["scenario_id"]: d for d in model_details}
            items = [by_id[row["scenario_id"]] for row in common_rows]
            ranks = [item["rank"] for item in items]
            top1 = sum(not item["wrong_top1"] for item in items)
            menu_sizes = [item["menu_size"] for item in items]
        else:
            ranks, menu_sizes = [], []
            heuristic_by_id = {d["scenario_id"]: d for d in heuristic_result["decisions"]}
            top1 = sum(heuristic_by_id[row["scenario_id"]]["top1"] for row in common_rows)
        top3_count = sum(rank <= 3 for rank, size in zip(ranks, menu_sizes) if size >= 3)
        top3_denominator = sum(size >= 3 for size in menu_sizes)
        return {"scenarios": len(common_rows), "top1_count": top1,
                "top1": top1 / len(common_rows) if common_rows else None,
                "top3_count": top3_count, "top3_denominator": top3_denominator,
                "top3": top3_count / top3_denominator if top3_denominator else None,
                "mrr": sum(1 / rank for rank in ranks) / len(ranks) if ranks else None}
    random = evaluate_random(common_rows)["overall"]
    comparison = {name: aggregate(result["decisions"]) for name, result in model_results.items()}
    comparison["heuristic"] = aggregate()
    comparison["random"] = {"scenarios": len(common_rows), "top1": random["top1"],
                             "top3": random["top3"], "mrr": random["mrr"]}
    return comparison


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--v1", type=Path, default=DEFAULT_V1)
    parser.add_argument("--v2", type=Path, default=DEFAULT_V2)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/model_first_1/results.json")
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    torch.set_num_threads(1)
    rows = [r for r in load_scenarios(args.scenarios) if r["split"] == args.split]
    if not rows:
        parser.error(f"No scenarios for split {args.split}")
    result = {"schema_version": 1, "scenario_file_sha256": hashlib.sha256(args.scenarios.read_bytes()).hexdigest(),
              "split": args.split, "scenario_count": len(rows),
              "categories": dict(sorted(Counter(r["category"] for r in rows).items())),
              "labelled": sum(r["label_status"] == "LABELED" for r in rows),
              "ambiguous": sum(r["label_status"] == "AMBIGUOUS" for r in rows), "models": {}}
    for name, path in (("policy_v1", args.v1), ("policy_v2", args.v2)):
        policy, encoder, payload = load_policy_checkpoint(path, device="cpu")
        feature_names = ({"state": list(POLICY_STATE_FEATURE_NAMES), "action": list(ACTION_FEATURE_NAMES)}
                         if representation_of(policy) == 1 else feature_contract(encoder))
        result["models"][name] = {"checkpoint": str(path),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "architecture": payload["model_config"]["architecture"],
                                  "input_feature_contract": feature_names,
                                  "catalog_sha256": payload["catalog_sha256"],
                                  "vocabulary_sha256": payload["vocabulary_sha256"],
                                  **evaluate_model(policy, encoder, rows, args.repeats)}
    result["heuristic"] = evaluate_heuristic(rows)
    result["random"] = evaluate_random(rows)
    result["common_heuristic_applicable"] = compare_common_applicable(
        rows, result["models"], result["heuristic"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "split": args.split, "scenarios": len(rows),
                      "models": {name: info["overall"] for name, info in result["models"].items()},
                      "heuristic": result["heuristic"]["overall"], "random": result["random"]["overall"]},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
