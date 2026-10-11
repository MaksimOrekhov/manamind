"""Publish aggregates from saved predictions; never load or score a model."""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from evaluate_tactical_learning_2 import changes
from prepare_tactical_learning import ROOT, sha, write
from manamind.training.policy_checkpoint import identity
from manamind.training.tactical_learning import read_rows


def real_uncertainty(directory):
    """Paired cluster bootstrap over seven whole validation matches, not positions."""
    protocol = json.loads((directory/"runs/protocol.json").read_text())
    manifest = json.loads((ROOT/"data/processed_policy_real/real_policy_retrain_1/retrain_manifest.json").read_text())
    split = manifest["split"]
    if identity(split) != protocol["real_split_sha256"]:
        raise ValueError("Real split changed")
    groups = []
    for game in split["game_ids"]["validation"]:
        rows = read_rows(ROOT/f"data/processed_policy_real/real_policy_retrain_1/{game}.jsonl")
        groups.append([r["decision_id"] for r in rows])
    models = {n: {r["id"]: r for r in json.loads((directory/f"evaluation/{n}.json").read_text())[
        "validation"]["records"]} for n in ("initial", "A", "B")}
    answer = {}
    for baseline in ("A", "initial"):
        rng = random.Random(42)
        values = {"CE": [], "Top1": []}
        for _ in range(10000):
            sample = [i for _ in groups for i in rng.choice(groups)]
            values["CE"].append(sum(models["B"][i]["loss"]-models[baseline][i]["loss"] for i in sample)/len(sample))
            values["Top1"].append(sum((models["B"][i]["rank"] == 1)-(models[baseline][i]["rank"] == 1)
                                      for i in sample)/len(sample))
        answer[f"B_minus_{baseline}"] = {metric: [sorted(v)[249], sorted(v)[9749]] for metric,v in values.items()}
    return {"method": "paired whole-match percentile bootstrap; decision-weighted metrics",
            "seed":42, "resamples":10000, "validation_matches":len(groups), "coverage":.95,
            "intervals":answer, "limitation":"Only seven reused validation matches; not an independent real test"}


def run(directory, output):
    comparison = json.loads((directory/"evaluation/comparison.json").read_text())
    control = read_rows(directory/"dataset/control.jsonl")
    models = {n: json.loads((directory/f"evaluation/{n}.json").read_text())
              for n in ("frozen", "initial", "A", "B")}
    ids = [r["scenario_id"] for r in control if r["correct_actions"]]
    comparison.pop("certificates")  # Full dataset/proofs remain local.
    comparison["comparison"]["B_vs_frozen"] = changes(
        models["frozen"]["control"]["records"], models["B"]["control"]["records"], ids)
    base = [i for i in ids if not i.endswith(("_position", "_id"))]
    comparison["base_correct"] = {n: sum(r["rank"] == 1 for r in m["control"]["records"]
                                          if r["id"] in base) for n,m in models.items()}
    write(output/"comparison.json", comparison)
    manifest = json.loads((directory/"dataset/manifest.json").read_text())
    audit = json.loads((directory/"dataset/data_gate.json").read_text())
    write(output/"manifest.json", manifest)
    write(output/"data_gate_summary.json", {"all_passed": audit["all_passed"], "rows": audit["rows"],
          "checks": audit["checks"], "data_gate_sha256": sha(directory/"dataset/data_gate.json"),
          "goals": {k:sum(v["scope"] == k for v in audit["certificates"].values())
                    for k in sorted({v["scope"] for v in audit["certificates"].values()})}})
    write(output/"training_protocol.json", json.loads((directory/"runs/protocol.json").read_text()))
    for name in ("A", "B"):
        write(output/f"history_{name}.json", json.loads((directory/f"runs/{name}/history.json").read_text()))
    # Continuous sensitivity computed on aligned existing logits, no repeat inference.
    groups = defaultdict(list)
    for row in control:
        if row.get("pair", {}).get("kind") == "stats":
            groups[row["pair"]["id"]].append(row)
    sensitive = {}
    for name, m in models.items():
        lookup = {r["id"]:r for r in m["control"]["records"]}
        details = []
        for pair_id, rows in groups.items():
            records = [lookup[r["scenario_id"]] for r in rows]
            def keyed(row, record):
                keys = {identity({k:v for k,v in a.items() if k not in
                                  ("source_attack", "source_health", "target_attack", "target_health")}): s
                        for a,s in zip(row["legal_actions"], record["scores"], strict=True)}
                return keys
            a,b = (keyed(r,c) for r,c in zip(rows,records,strict=True))
            if a.keys() != b.keys():
                raise ValueError("Stats intervention changed handles")
            deltas = [b[k]-a[k] for k in a]
            details.append({"id":pair_id, "field":rows[0]["pair"]["field"],
                            "max_logit_change":max(abs(x) for x in deltas),
                            "logit_delta_range":max(deltas)-min(deltas)})
        sensitive[name] = details
    write(output/"stats_sensitivity.json", sensitive)
    write(output/"real_uncertainty.json", real_uncertainty(directory))
    write(output/"artifact_hashes.json", {"private_prediction_sha256":{
        n:sha(directory/f"evaluation/{n}.json") for n in models},
        "control_opened_sha256":sha(directory/"runs/CONTROL_OPENED.json"),
        "data_manifest_sha256":sha(directory/"dataset/manifest.json"),
        "public_source_sha256":{p:sha(ROOT/p) for p in ("scripts/evaluate_tactical_learning_2.py",
            "scripts/report_tactical_learning_2.py", "tests/test_tactical_learning_2.py")}})
    return {n:max(d["max_logit_change"] for d in ds) for n,ds in sensitive.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.directory,args.output), indent=2))
