"""Single sealed-control opening after two selected saves; no training."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from manamind.training.numeric_combat import load_numeric,numeric_rows,combat_features
from manamind.training.policy_checkpoint import load_policy_checkpoint
from manamind.training.tactical_learning import evaluate,encode_rows,read_rows,real_parts,compact
from evaluate_tactical_learning_2 import pairs,changes
from prepare_tactical_learning import ROOT,INITIAL,INITIAL_SHA,sha,write
from evaluate_tactical_learning import FROZEN,FROZEN_SHA
from prepare_numeric_combat_ablation import TL2


def pair_summary(rows,records):
    result = {}
    for kind in ("base","position","id"):
        chosen = [r for r in rows if "pair" in r and
                  (r["scenario_id"].endswith("_"+kind) if kind!="base" else
                   not r["scenario_id"].endswith(("_position","_id")))]
        result[kind] = pairs(chosen,records)["stats"]
    return result


def run(dataset,runs,output):
    manifest = json.loads((dataset/"manifest.json").read_text())
    complete = json.loads((runs/"TRAINING_COMPLETE.json").read_text())
    if sha(INITIAL)!=INITIAL_SHA or sha(FROZEN)!=FROZEN_SHA or complete["dataset_manifest_sha256"] != sha(dataset/"manifest.json"):
        raise ValueError("Immutable input mismatch")
    paths = {"frozen":FROZEN,"initial":INITIAL,
             "TL2_A":ROOT/"data/processed_tactical_learning_2/runs/A/policy.pt",
             "TL2_B":ROOT/"data/processed_tactical_learning_2/runs/B/policy.pt",
             "A":runs/"A/policy.pt","B":runs/"B/policy.pt"}
    for n in ("A","B"):
        if sha(paths[n]) != complete["candidates"][n]["checkpoint_sha256"]:raise ValueError("Candidate changed")
    if sha(dataset/"control.jsonl") != manifest["files"]["control"]:raise ValueError("Control changed")
    write(runs/"CONTROL_OPENED.json",{"models":{n:sha(p) for n,p in paths.items()},
        "training_complete_sha256":sha(runs/"TRAINING_COMPLETE.json"),"control_sha256":sha(dataset/"control.jsonl")})
    output.mkdir(parents=True,exist_ok=False)
    control = read_rows(dataset/"control.jsonl")
    old = read_rows(TL2/"control.jsonl")
    torch.set_num_threads(1)
    real = real_parts(ROOT/"data/processed_policy_real/real_policy_retrain_1",
        load_policy_checkpoint(INITIAL)[2]["experiment"]["split"])
    models,summary = {},{}
    features = {}
    for n,path in paths.items():
        if n=="B":
            policy,encoder,_,metadata = load_numeric(path)
            encode = lambda rows:numeric_rows(rows,encoder,metadata)
        else:
            policy,encoder,_ = load_policy_checkpoint(path)
            encode = lambda rows:encode_rows(rows,encoder,"cpu")
        result = {p:evaluate(policy,rows,encode(rows)) for p,rows in real.items()}
        result["control"] = evaluate(policy,control,encode(control))
        result["pairs"] = pair_summary(control,result["control"]["records"])
        if n in ("A","B"):
            result["TL2_disclosed_control"] = evaluate(policy,old,encode(old))
        if n=="B":
            encoded = encode(control)
            # Diagnostic ablation only: zero selected B's four inputs, no weights/selection changes.
            zeroed = [(tuple(inputs[:-1])+(torch.zeros_like(inputs[-1]),),gold) for inputs,gold in encoded]
            result["numeric_zero_control"] = evaluate(policy,control,zeroed)
            result["numeric_zero_pairs"] = pair_summary(control,result["numeric_zero_control"]["records"])
            features = {r["scenario_id"]:combat_features(r,metadata).tolist() for r in control}
            if any(any(any(x for x in vector) for vector in features[r["scenario_id"]])
                   for r in control if r.get("numeric_unknown_context")):
                raise ValueError("Unknown conditions fabricated")
        write(output/f"{n}.json",result)
        models[n] = result
        summary[n] = {k:compact(v) for k,v in result.items() if k not in ("pairs","numeric_zero_pairs")}
        summary[n]["pairs"] = result["pairs"]
        if n=="B":summary[n]["numeric_zero_pairs"] = result["numeric_zero_pairs"]
        print(json.dumps({"model":n,"control_correct":result["control"]["overall"]["correct"],
                          "base_stats_pairs":result["pairs"]["base"]["both_correct_and_changed_source"]}),flush=True)
    ids = [r["scenario_id"] for r in control if r["correct_actions"]]
    lethal = [i for i in ids if i.startswith("nca_lethal_")]
    comparison = {f"B_vs_{n}":changes(m["control"]["records"],models["B"]["control"]["records"],ids)
                  for n,m in models.items() if n!="B"}
    lethal_changes = {n:changes(models[n]["control"]["records"],models["B"]["control"]["records"],lethal)
                     for n in ("A","frozen","TL2_B")}
    gates = manifest["config"]["gates"]
    bp,ap = models["B"]["pairs"],models["A"]["pairs"]
    rv = {n:models[n]["validation"]["overall"] for n in ("A","B","initial")}
    checks = {"primary_pairs":bp["base"]["both_correct_and_changed_source"]>=gates["minimum_base_stats_pairs"],
        "pair_gain":bp["base"]["both_correct_and_changed_source"]-ap["base"]["both_correct_and_changed_source"]>=gates["minimum_stats_pair_gain_over_A"],
        "unknown_ID_pairs":bp["id"]["both_correct_and_changed_source"]>=gates["minimum_variant_stats_pairs"],
        "position_pairs":bp["position"]["both_correct_and_changed_source"]>=gates["minimum_variant_stats_pairs"],
        "real_CE":rv["B"]["cross_entropy"]<=min(rv[n]["cross_entropy"] for n in ("A","initial"))+gates["maximum_real_CE_increase"],
        "real_top1":rv["B"]["top1_accuracy"]>=max(rv[n]["top1_accuracy"] for n in ("A","initial"))-gates["maximum_real_top1_drop"],
        "no_new_lethal":all(len(c["new_errors"])<=gates["maximum_new_lethal_errors"] for c in lethal_changes.values()),
        "selection_guards":all(c["selection_guard_passed"] for c in complete["candidates"].values())}
    safety = all(checks[k] for k in ("real_CE","real_top1","no_new_lethal","selection_guards"))
    verdict = "GO" if all(checks.values()) else "NO-GO" if not safety or not checks["pair_gain"] else "INCONCLUSIVE"
    public = {"verdict":verdict,"checks":checks,"models":summary,"comparison":comparison,
              "lethal_changes":lethal_changes,"training":complete,"features":features}
    write(output/"comparison.json",public)
    return public


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset","runs","output"):parser.add_argument("--"+name,type=Path,required=True)
    args = parser.parse_args()
    result = run(args.dataset,args.runs,args.output)
    print(json.dumps({"verdict":result["verdict"],"checks":result["checks"]},indent=2))
