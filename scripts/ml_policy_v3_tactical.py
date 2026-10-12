"""ML-POLICY-V3-1: rank the project's existing controlled tactical scenarios with several checkpoints.

Reuses the locked MODEL-FIRST-1 control set and the MODEL-FIRST-2 / 2C synthetic test sets (hand-written rule labels:
plumbing/regression evidence, not playing strength; v2 development already looked at these sets). Inference only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_policy_baseline import action_key  # noqa: E402
from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.models.policy_inputs import encode_policy_inputs, representation_of  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402

SETS = {
    "model_first_1_control": ROOT / "data/evaluation/model_first_1/control_test.jsonl",
    "model_first_2_test": ROOT / "model-first-2/data/processed_synthetic/model_first_2/test.jsonl",
    "model_first_2c_test": ROOT / "model-first-2/data/processed_synthetic/model_first_2c/test.jsonl",
}


def rank_scenarios(policy, encoder, rows) -> dict:
    groups = defaultdict(list)
    policy.eval()
    for row in rows:
        if row["label_status"] != "LABELED":
            continue
        state = game_state_from_dict(row["state"])
        actions = row["legal_actions"]
        correct = {action_key(a) for a in row["correct_actions"]}
        with torch.inference_mode():
            scores = policy(*encode_policy_inputs(state, actions, encoder, representation=representation_of(policy)))
        order = sorted(range(len(actions)), key=lambda i: (-float(scores[i]), action_key(actions[i])))
        rank = min(order.index(i) + 1 for i, a in enumerate(actions) if action_key(a) in correct)
        item = {"rank": rank, "size": len(actions), "scenario": row["scenario_id"]}
        groups[row["category"]].append(item)
        groups["ALL"].append(item)
    def metrics(items):
        eligible = [i for i in items if i["size"] >= 3]
        return {"scenarios": len(items), "top1": sum(i["rank"] == 1 for i in items) / len(items),
                "top3": sum(i["rank"] <= 3 for i in eligible) / len(eligible) if eligible else None,
                "mrr": sum(1 / i["rank"] for i in items) / len(items), "wrong_top1": sum(i["rank"] > 1 for i in items)}
    return {k: metrics(v) for k, v in sorted(groups.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", required=True, help="name=checkpoint")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {}
    for item in args.model:
        name, path = item.split("=", 1)
        policy, encoder, _ = load_policy_checkpoint(Path(path))
        result[name] = {}
        for set_name, set_path in SETS.items():
            rows = [json.loads(x) for x in set_path.read_text(encoding="utf-8").splitlines() if x.strip()]
            result[name][set_name] = rank_scenarios(policy, encoder, rows)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    for set_name in SETS:
        print("==", set_name)
        for name in result:
            a = result[name][set_name]["ALL"]
            print(f"  {name:<20} n={a['scenarios']} top1={a['top1']:.3f} top3={a['top3']} mrr={a['mrr']:.3f} wrong_top1={a['wrong_top1']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
