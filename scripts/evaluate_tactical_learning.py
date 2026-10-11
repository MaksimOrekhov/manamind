"""Open sealed control once, after exactly two selected checkpoints exist."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch

from manamind.training.policy_checkpoint import load_policy_checkpoint
from manamind.training.tactical_certificates import certify
from manamind.training.tactical_learning import compact, encode_rows, evaluate, read_rows, real_parts

from prepare_tactical_learning import INITIAL, INITIAL_SHA, ROOT, sha, write

FROZEN = ROOT/"data/processed_policy_ml2a/seed42_v2/policy.pt"
FROZEN_SHA = "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"


def changes(left, right, ids):
    a = {r["id"]: r["rank"] == 1 for r in left}
    b = {r["id"]: r["rank"] == 1 for r in right}
    return {"fixed": [i for i in ids if not a[i] and b[i]],
            "new_errors": [i for i in ids if a[i] and not b[i]],
            "shared_errors": [i for i in ids if not a[i] and not b[i]]}


def semantic_choice(row, prediction, kind):
    """Transport selected handles, allowing multiple equivalent correct prefixes."""
    result = [prediction["type"], prediction.get("target_side"), prediction.get("target_kind")]
    for role, side in (("source", "self_player"), ("target", "opponent")):
        if prediction.get(f"{role}_kind") == "MINION":
            board = row["state"][side]["board"]
            entity = next(m for m in board if m["board_position"] == prediction[f"{role}_board_position"])
            result.append(entity["card"]["card_id"] if kind != "id" else entity["board_position"])
        else:
            result.append(prediction.get(f"{role}_kind"))
    return result


def pairs(control, records):
    groups, lookup = defaultdict(list), {r["id"]: r for r in records}
    for row in control:
        if "pair" in row:
            groups[(row["pair"]["kind"], row["pair"]["id"])].append(row)
    answer = defaultdict(lambda: {"pairs": 0, "both_correct": 0, "same_semantic_choice": 0,
                                  "changed_source": 0, "details": []})
    for (kind, pair_id), rows in groups.items():
        if len(rows) != 2:
            raise ValueError("Invalid control pair")
        a, b = (lookup[r["scenario_id"]] for r in rows)
        same = semantic_choice(rows[0], a["prediction"], kind) == semantic_choice(rows[1], b["prediction"], kind)
        both = a["rank"] == b["rank"] == 1
        changed_source = a["prediction"].get("source_card_id") != b["prediction"].get("source_card_id")
        result = answer[kind]
        result["pairs"] += 1
        result["both_correct"] += both
        result["same_semantic_choice"] += same
        result["changed_source"] += changed_source
        result["details"].append({"id": pair_id, "both_correct": both, "same_choice": same,
                                  "changed_source": changed_source, "field": rows[0]["pair"].get("field")})
    return dict(answer)


def run(dataset, runs, output):
    complete = json.loads((runs/"TRAINING_COMPLETE.json").read_text())
    manifest = json.loads((dataset/"manifest.json").read_text())
    if (complete["dataset_manifest_sha256"] != sha(dataset/"manifest.json")
            or sha(INITIAL) != INITIAL_SHA or sha(FROZEN) != FROZEN_SHA):
        raise ValueError("Immutable input mismatch")
    paths = {"frozen": FROZEN, "initial": INITIAL, "A": runs/"A/policy.pt", "B": runs/"B/policy.pt"}
    for n in ("A", "B"):
        if sha(paths[n]) != complete["candidates"][n]["checkpoint_sha256"]:
            raise ValueError("Selected candidate changed")
    if sha(dataset/"control.jsonl") != manifest["files"]["control"]:
        raise ValueError("Control seal mismatch")
    # Exclusive persistent marker prevents repeated ranking/tuning after opening.
    write(runs/"CONTROL_OPENED.json", {"training_complete_sha256": sha(runs/"TRAINING_COMPLETE.json"),
          "models": {n: sha(p) for n, p in paths.items()}, "control_sha256": manifest["files"]["control"]})
    output.mkdir(parents=True, exist_ok=False)
    control = read_rows(dataset/"control.jsonl")
    certificates = {r["scenario_id"]: certify(r) for r in control}
    for row in control:
        wanted = [row["legal_actions"][i] for i in certificates[row["scenario_id"]]["gold"]]
        if {json.dumps(a, sort_keys=True) for a in wanted} != {json.dumps(a, sort_keys=True) for a in row["correct_actions"]}:
            raise ValueError("Certificate changed")
    torch.set_num_threads(1)
    models, summaries = {}, {}
    for name, path in paths.items():
        policy, encoder, payload = load_policy_checkpoint(path)
        real = real_parts(ROOT/"data/processed_policy_real/real_policy_retrain_1",
                          load_policy_checkpoint(INITIAL)[2]["experiment"]["split"])
        results = {p: evaluate(policy, rs, encode_rows(rs, encoder, "cpu")) for p, rs in real.items()}
        results["control"] = evaluate(policy, control, encode_rows(control, encoder, "cpu"))
        results["pairs"] = pairs(control, results["control"]["records"])
        # Historical labels are retained as diagnostics, never re-certified as optimal.
        for label, filename in [("MF1", "data/evaluation/model_first_1/control_test.jsonl"),
                                ("MF2C", "model-first-2/data/processed_synthetic/model_first_2c/test.jsonl")]:
            rows = read_rows(ROOT/filename)
            results[label] = evaluate(policy, rows, encode_rows(rows, encoder, "cpu"))
        write(output/f"{name}.json", results)
        models[name] = results
        summaries[name] = {p: compact(r) for p, r in results.items() if p != "pairs"}
        summaries[name]["pairs"] = results["pairs"]
        print(json.dumps({"model": name, "real_validation_CE": results["validation"]["overall"]["cross_entropy"],
                          "control_correct": results["control"]["overall"]["correct"]}), flush=True)
    ids = [r["scenario_id"] for r in control if r["certificate"]["certainty"] == "PROVEN_PROPERTY"]
    base_ids = [i for i in ids if not i.endswith(("_alias", "_position"))]
    comparison = {"B_vs_A": changes(models["A"]["control"]["records"], models["B"]["control"]["records"], ids),
                  "B_vs_initial": changes(models["initial"]["control"]["records"], models["B"]["control"]["records"], ids),
                  "B_vs_A_base": changes(models["A"]["control"]["records"], models["B"]["control"]["records"], base_ids)}
    gate = manifest["config"]["gates"]
    a, b, initial = (models[n]["validation"]["overall"] for n in ("A", "B", "initial"))
    warrior = {n: models[n]["validation"]["by_class"].get("WARRIOR", {}) for n in ("A", "B", "initial")}
    checks = {"certified_base_gain": len(comparison["B_vs_A_base"]["fixed"])-len(comparison["B_vs_A_base"]["new_errors"]) >= gate["minimum_B_minus_A_proven_correct"],
              "real_CE": b["cross_entropy"] <= min(a["cross_entropy"], initial["cross_entropy"])+gate["maximum_real_validation_CE_increase"],
              "real_top1": b["top1_accuracy"] >= max(a["top1_accuracy"], initial["top1_accuracy"])-gate["maximum_real_validation_top1_drop"],
              "Warrior_top1": warrior["B"]["top1_accuracy"] >= max(warrior["A"]["top1_accuracy"], warrior["initial"]["top1_accuracy"])-gate["maximum_Warrior_validation_top1_drop"],
              "no_new_vs_A": len(comparison["B_vs_A"]["new_errors"]) <= gate["maximum_new_proven_errors_against_A"],
              "no_new_vs_initial": len(comparison["B_vs_initial"]["new_errors"]) <= gate["maximum_new_proven_errors_against_initial"],
              "selection_guards": all(c["selection_guard_passed"] for c in complete["candidates"].values())}
    verdict = "GO" if all(checks.values()) else "NO-GO" if (not checks["no_new_vs_A"] or not checks["real_CE"] or
                                                                  not checks["no_new_vs_initial"]) else "INCONCLUSIVE"
    public = {"models": summaries, "comparison": comparison, "checks": checks, "verdict": verdict,
              "base_proven": len(base_ids), "all_proven": len(ids), "certificates": certificates,
              "manifest_sha256": sha(dataset/"manifest.json"), "training": complete}
    write(output/"comparison.json", public)
    return public


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.dataset, args.runs, args.output)
    print(json.dumps({"verdict": result["verdict"], "checks": result["checks"]}, indent=2))
