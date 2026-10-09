"""Score all MODEL-FIRST-2C checkpoints and locked diagnostics after training."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_policy_baseline import (  # noqa: E402
    action_key,
    compare_common_applicable,
    evaluate_heuristic,
    evaluate_model,
    evaluate_random,
    load_scenarios,
)
from manamind.training.model_first_1_control import verify_frozen_control  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402

DATA = ROOT / "data/processed_synthetic/model_first_2c"
BASELINE = ROOT.parent / "data/processed_policy_ml2a/seed42_v2/policy.pt"
MODEL2 = ROOT / "data/processed_policy_ml2b/model_first_2_seed42/policy.pt"
MODEL2B = ROOT / "data/processed_policy_ml2b/model_first_2b_corrective/policy.pt"
MODEL2C_6 = ROOT / "data/processed_policy_ml2c/seed42_mix_v1/policy.pt"
MODEL2C_12 = ROOT / "data/processed_policy_ml2c/seed42_mix_v2_longer/policy.pt"
FROZEN_CONTROL = ROOT / "data/evaluation/model_first_1/control_test.jsonl"
OLD_DATA = ROOT / "data/processed_synthetic/model_first_2"
OLD_CHALLENGE = ROOT / "data/processed_synthetic/model_first_2b_postcorrective/challenge.jsonl"


def _positional_action(row: dict) -> str:
    attacks = [action for action in row["legal_actions"] if action["type"] == "ATTACK"]
    first_pair = [action for action in attacks if action.get("source_board_position") == 1
                  and action.get("target_kind") == "MINION" and action.get("target_board_position") == 1]
    if first_pair:
        return action_key(first_pair[0])
    faces = [action for action in attacks if action.get("target_kind") == "HERO"]
    if faces:
        return action_key(min(faces, key=lambda action: (action.get("source_board_position", 0),
                                                         action_key(action))))
    return "NO_POSITIONAL_ACTION"


def _top_action(row: dict, detail: dict) -> dict:
    if detail.get("top_action") is None:
        return {}
    wanted = detail["top_action"]
    return next(action for action in row["legal_actions"] if action_key(action) == wanted)


def _metrics(rows: list[dict], models: dict, repeats: int) -> dict:
    model_results = {name: evaluate_model(policy, encoder, rows, repeats=repeats)
                     for name, (policy, encoder, _) in models.items()}
    heuristic = evaluate_heuristic(rows)
    random = evaluate_random(rows)
    positional_decisions = {}
    labeled = [row for row in rows if row["label_status"] == "LABELED"]
    for row in labeled:
        action = _positional_action(row)
        positional_decisions[row["scenario_id"]] = {"action": action,
            "correct": action in {action_key(a) for a in row["correct_actions"]}}
    positional = {"scenarios": len(labeled),
                  "top1_count": sum(value["correct"] for value in positional_decisions.values()),
                  "top1": (sum(value["correct"] for value in positional_decisions.values()) / len(labeled)
                           if labeled else None),
                  "not_applicable": sum(value["action"] == "NO_POSITIONAL_ACTION"
                                        for value in positional_decisions.values())}
    result = {
        "scenario_count": len(rows), "labelled": len(labeled),
        "ambiguous": sum(row["label_status"] == "AMBIGUOUS" for row in rows),
        "categories": dict(Counter(row["category"] for row in rows)),
        "models": {name: {"overall": value["overall"], "by_category": value["by_category"],
                          "decisions": {item["scenario_id"]: item for item in value["decisions"]}}
                   for name, value in model_results.items()},
        "heuristic": {"overall": heuristic["overall"], "by_category": heuristic["by_category"],
                      "not_applicable": heuristic["not_applicable"],
                      "decisions": {item["scenario_id"]: item for item in heuristic["decisions"]}},
        "random": random["overall"], "positional": {**positional, "decisions": positional_decisions},
        "common_heuristic_applicable": compare_common_applicable(rows, model_results, heuristic),
    }
    for name, model in result["models"].items():
        by_id = model["decisions"]
        turn_top = hero_top = 0
        for row in labeled:
            top = _top_action(row, by_id[row["scenario_id"]])
            turn_top += top.get("type") == "END_TURN"
            hero_top += top.get("target_kind") == "HERO"
        model["end_turn_top1_count"] = turn_top
        model["end_turn_top1_rate"] = turn_top / len(labeled) if labeled else None
        model["hero_attack_top1_count"] = hero_top
        model["hero_attack_top1_rate"] = hero_top / len(labeled) if labeled else None
    heuristic["decisions"] = result["heuristic"]["decisions"]
    return result


def _paired(rows: list[dict], dataset_results: dict) -> dict:
    families = defaultdict(list)
    for row in rows:
        if "counterfactual_" in " ".join(row["tags"]):
            families[row["family_id"]].append(row)
    factors = {"stats": {}, "position": {}, "board": {}, "id": {}}
    for family, pair in families.items():
        if len(pair) != 2:
            continue
        pair.sort(key=lambda row: row["scenario_id"])
        tag_text = " ".join(pair[0]["tags"])
        factor = next((key for key, tag in (("stats", "counterfactual_stats"),
                                            ("position", "counterfactual_position"),
                                            ("board", "counterfactual_board_size"),
                                            ("id", "counterfactual_card_id"))
                       if tag in tag_text), None)
        if factor is None:
            continue
        arms = [row["scenario_id"].rsplit("_", 1)[-1] for row in pair]
        metrics = factors[factor].setdefault("arms", defaultdict(lambda: defaultdict(list)))
        pair_record = {"scenario_ids": [row["scenario_id"] for row in pair], "models": {}}
        for model_name, model_result in dataset_results["models"].items():
            decisions = model_result["decisions"]
            correct_by_arm = []
            selected = []
            for row, arm in zip(pair, arms, strict=True):
                decision = decisions[row["scenario_id"]]
                correct = not decision["wrong_top1"]
                correct_by_arm.append(correct)
                metrics[model_name][arm].append(correct)
                selected_action = _top_action(row, decision)
                if factor == "position":
                    selected.append((selected_action.get("source_card_id"),
                                     selected_action.get("target_card_id")))
                else:
                    selected.append((selected_action.get("source_board_position"),
                                     selected_action.get("target_board_position"),
                                     selected_action.get("type")))
            pair_record["models"][model_name] = {
                "both_correct": all(correct_by_arm),
                "same_semantic_choice": selected[0] == selected[1],
            }
        factors[factor].setdefault("pairs", []).append(pair_record)
    for factor, details in factors.items():
        summaries = {}
        for model_name, arms in details.get("arms", {}).items():
            summaries[model_name] = {arm: {"scenarios": len(values),
                "top1": sum(values) / len(values) if values else None,
                "top1_count": sum(values)} for arm, values in arms.items()}
            pairs = details["pairs"]
            stable = [pair["models"][model_name]["same_semantic_choice"] for pair in pairs]
            summaries[model_name]["pairs_both_correct"] = sum(
                pair["models"][model_name]["both_correct"] for pair in pairs)
            summaries[model_name]["same_semantic_choice_rate"] = (
                sum(stable) / len(stable) if stable else None)
        details["summary"] = summaries
        details["pair_count"] = len(details.get("pairs", []))
    return factors


def run(output: Path, data: Path = DATA, repeats: int = 1) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite MODEL-FIRST-2C results: {output}")
    verify_frozen_control()
    checkpoint_paths = {
        "source_policy_v2": BASELINE,
        "model_first_2": MODEL2,
        "model_first_2b": MODEL2B,
        "model_first_2c_6_epoch": MODEL2C_6,
        "model_first_2c_12_epoch": MODEL2C_12,
    }
    models = {}
    checkpoint_hashes = {}
    for name, path in checkpoint_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required local checkpoint is missing: {path}")
        policy, encoder, payload = load_policy_checkpoint(path, device="cpu")
        models[name] = (policy, encoder, payload)
        checkpoint_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    datasets = {
        "model_first_2_train": OLD_DATA / "train.jsonl",
        "model_first_2_validation": OLD_DATA / "validation.jsonl",
        "model_first_2_synthetic_test": OLD_DATA / "test.jsonl",
        "model_first_2b_challenge_viewed": ROOT / "data/processed_synthetic/model_first_2b_postcorrective/challenge.jsonl",
        "model_first_2c_train": data / "train.jsonl",
        "model_first_2c_validation": data / "validation.jsonl",
        "model_first_2c_locked_test": data / "test.jsonl",
        "frozen_model_first_1": FROZEN_CONTROL,
    }
    all_results, loaded_rows, hashes = {}, {}, {}
    for name, path in datasets.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required evaluation dataset is missing: {path}")
        rows = load_scenarios(path)
        loaded_rows[name] = rows
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        all_results[name] = _metrics(rows, models, repeats)
        all_results[name]["source_sha256"] = hashes[name]
        if name == "model_first_2c_locked_test":
            all_results[name]["counterfactual_pairs"] = _paired(rows, all_results[name])
        for model_name, details in all_results[name]["models"].items():
            good = [row for row in rows if row["label_status"] == "LABELED"
                    and not details["decisions"][row["scenario_id"]]["wrong_top1"]]
            bad = [row for row in rows if row["label_status"] == "LABELED"
                   and details["decisions"][row["scenario_id"]]["wrong_top1"]]
            if model_name == "model_first_2c_12_epoch":
                details["examples"] = {
                    "successes": [{"scenario_id": row["scenario_id"], "category": row["category"],
                                   "top_action": details["decisions"][row["scenario_id"]]["top_action"],
                                   "correct_actions": [action_key(a) for a in row["correct_actions"]]}
                                  for row in good[:3]],
                    "errors": [{"scenario_id": row["scenario_id"], "category": row["category"],
                                "top_action": details["decisions"][row["scenario_id"]]["top_action"],
                                "correct_actions": [action_key(a) for a in row["correct_actions"]]}
                               for row in bad[:3]],
                }
    # Keep aggregate tables, paired counterfactual summaries, and compact locked-test
    # examples. Per-row action dumps duplicate large action payloads and obscure review.
    for report in all_results.values():
        for details in report["models"].values():
            details.pop("decisions", None)
        report["heuristic"].pop("decisions", None)
        report["positional"].pop("decisions", None)
    result = {"schema_version": 1, "experiment": "MODEL-FIRST-2C Robust Tactical Learning",
              "training_performed": True, "test_read_by_trainer": False,
              "dataset_manifest": json.loads((data / "manifest.json").read_text(encoding="utf-8")),
              "dataset_manifest_sha256": hashlib.sha256((data / "manifest.json").read_bytes()).hexdigest(),
              "training_runs": {},
              "new_data_sha256": {name: hashes[f"model_first_2c_{name}"]
                                  for name in ("train", "validation", "locked_test")},
              "checkpoint_sha256": checkpoint_hashes,
              "datasets": all_results,
              "limits": ["Synthetic local action ranking is not proof of game strength.",
                         "MODEL-FIRST-2B challenge and older test sets are viewed diagnostics.",
                         "The new MODEL-FIRST-2C test was held out from both training runs and epoch selection.",
                         "The rules select only immediate lethal, safe minion kills, or END_TURN if neither exists.",
                         "Heuristic NOT_APPLICABLE rows are excluded from its accuracy denominator and shown separately."]}
    for name, checkpoint_path in (("six_epoch", MODEL2C_6), ("twelve_epoch", MODEL2C_12)):
        training = json.loads((checkpoint_path.parent / "training.json").read_text(encoding="utf-8"))
        result["training_runs"][name] = {
            "checkpoint_sha256": training["checkpoint_sha256"],
            "source_checkpoint_sha256": training["source_checkpoint_sha256"],
            "config": training["config"], "selected_epoch": training["selected_epoch"],
            "epochs_run": training["epochs_run"], "training_seconds": training["training_seconds"],
            "initial_validation": training["initial_validation"],
            "selected_validation": training["selected_validation"],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/model_first_2c/results.json")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    result = run(args.output, args.data, args.repeats)
    summary = {dataset: {"scenario_count": report["scenario_count"],
        "models": {name: value["overall"] for name, value in report["models"].items()},
        "heuristic": report["heuristic"]["overall"], "random": report["random"],
        "positional": {key: value for key, value in report["positional"].items() if key != "decisions"}}
        for dataset, report in result["datasets"].items()}
    print(json.dumps({"results": str(args.output), "summary": summary}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
