"""Evaluate the selected MODEL-FIRST-2 checkpoint on all locked comparisons."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from manamind.training.policy_checkpoint import load_policy_checkpoint
from manamind.training.model_first_1_control import verify_frozen_control

from evaluate_policy_baseline import (
    compare_common_applicable, evaluate_heuristic, evaluate_model, evaluate_random, load_scenarios,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed_synthetic/model_first_2"
CONTROL = ROOT / "data/evaluation/model_first_1/control_test.jsonl"


def _metrics(path: Path, baseline: Path, trained: Path, repeats: int):
    rows = load_scenarios(path)
    models, policies, encoders = {}, {}, {}
    for name, checkpoint in (("baseline_policy_v2", baseline), ("finetuned_policy_v2", trained)):
        policy, encoder, payload = load_policy_checkpoint(checkpoint, device="cpu")
        models[name] = {"checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                        "architecture": payload["model_config"]["architecture"],
                        **evaluate_model(policy, encoder, rows, repeats=repeats)}
        policies[name], encoders[name] = policy, encoder
    heuristic, random = evaluate_heuristic(rows), evaluate_random(rows)
    unseen_id_rows = [row for row in rows if any(
        str(entity.get("card", {}).get("card_id", "")).startswith("MF2_HELDOUT_")
        for side in ("self_player", "opponent") for entity in row["state"][side]["board"])]
    unseen_id_metrics = {}
    if unseen_id_rows:
        unseen_id_metrics = {
            name: {"count": len(unseen_id_rows),
                  "overall": evaluate_model(policies[name], encoders[name], unseen_id_rows,
                                            repeats=repeats)["overall"]}
            for name in policies}
    model_summaries = {}
    for name, result in models.items():
        decisions = [item for item in result["decisions"] if item.get("status") == "APPLICABLE"]
        successes = [item for item in decisions if not item["wrong_top1"]]
        errors = [item for item in decisions if item["wrong_top1"]]
        example_fields = ("scenario_id", "category", "rank", "correct_ranks", "top_action", "menu_size")
        model_summaries[name] = {key: result[key] for key in (
            "checkpoint_sha256", "architecture", "overall", "by_category", "ambiguous",
            "not_applicable", "inference_ms_mean", "inference_ms_median", "policy_forward_ms_mean",
            "policy_forward_ms_median", "inference_timing_scope", "inference_repeats", "warmup_scenarios")}
        model_summaries[name]["examples"] = {
            "first_top1_success": ({key: successes[0][key] for key in example_fields} if successes else None),
            "first_top1_error": ({key: errors[0][key] for key in example_fields} if errors else None)}
    heuristic_summary = {key: value for key, value in heuristic.items() if key != "decisions"}
    return {"scenario_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "scenario_count": len(rows), "categories": dict(Counter(r["category"] for r in rows)),
            "labelled": sum(r["label_status"] == "LABELED" for r in rows),
            "ambiguous": sum(r["label_status"] == "AMBIGUOUS" for r in rows),
            "models": model_summaries, "heuristic": heuristic_summary, "random": random,
            "unseen_card_id_subset": unseen_id_metrics,
            "common_heuristic_applicable": compare_common_applicable(rows, models, heuristic)}


def evaluate(baseline: Path, trained: Path, data: Path = DATA, control: Path = CONTROL, repeats: int = 1):
    # The saved paired comparison is run after checkpoint selection. A prior
    # baseline-only preflight attempt failed during output creation and was not
    # used for training or checkpoint selection.
    verify_frozen_control()
    synthetic = {split: _metrics(data / f"{split}.jsonl", baseline, trained, repeats)
                 for split in ("train", "validation", "test")}
    control_rows = load_scenarios(control)
    if len(control_rows) != 13 or any(r["split"] != "test" for r in control_rows):
        raise ValueError("Frozen MODEL-FIRST-1 control must contain all 13 held-out scenarios")
    control_result = _metrics(control, baseline, trained, repeats)
    return {"schema_version": 1, "experiment": "MODEL-FIRST-2",
            "training_tuning_used": "train and validation only; synthetic test and M1 control opened after checkpoint selection",
            "synthetic": synthetic, "frozen_model_first_1_control": control_result,
            "control_label_status": Counter(row["label_status"] for row in control_rows),
            "limits": ["Synthetic tactical imitation is not game-strength evidence.",
                       "Synthetic test covers three generated held-out families only.",
                       "Heuristic applicability is reported separately from all labeled rows.",
                       "A single fixed seed does not establish statistical significance."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--trained", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--control", type=Path, default=CONTROL)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/model_first_2/results.json")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    result = evaluate(args.baseline, args.trained, args.data, args.control, args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=dict) + "\n",
                           encoding="utf-8")
    summary = {split: {name: model["overall"] for name, model in report["models"].items()}
               for split, report in result["synthetic"].items()}
    summary["synthetic_test"] = {"heuristic": result["synthetic"]["test"]["heuristic"]["overall"],
                                 "random": result["synthetic"]["test"]["random"]}
    summary["frozen_control"] = {name: model["overall"] for name, model in
                                 result["frozen_model_first_1_control"]["models"].items()}
    print(json.dumps({"output": str(args.output), "summary": summary}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
