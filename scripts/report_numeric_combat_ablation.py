"""Report saved logits and numeric-column coverage, without control re-scoring."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from manamind.training.numeric_combat import load_numeric,combat_features,FEATURES
from manamind.training.policy_checkpoint import identity
from manamind.training.tactical_learning import read_rows,real_parts
from prepare_tactical_learning import ROOT,sha,write
from report_tactical_learning_2 import real_uncertainty
from evaluate_tactical_learning import changes


def run(directory,output):
    c = json.loads((directory/"evaluation/comparison.json").read_text())
    features = c.pop("features")
    write(output/"comparison.json",c)
    for source,destination in (("dataset/manifest.json","manifest.json"),
        ("runs/protocol.json","training_protocol.json"),("runs/A/history.json","history_A.json"),
        ("runs/B/history.json","history_B.json")):
        write(output/destination,json.loads((directory/source).read_text()))
    gate = json.loads((directory/"dataset/data_gate.json").read_text())
    write(output/"data_gate_summary.json",{"passed":gate["passed"],"rows":gate["rows"],
        "sha256":sha(directory/"dataset/data_gate.json"),"checks":["pinned text/base metadata",
        "synthetic declarations","legal menu","independent arithmetic vs exact Outcome",
        "new control normalized overlap TL1/TL2/MF1/MF2C = 0","encoding before optimizers"]})
    rows = read_rows(directory/"dataset/control.jsonl")
    models = {n:json.loads((directory/f"evaluation/{n}.json").read_text()) for n in ("A","B","TL2_B")}
    old_ids = [r["id"] for r in models["B"]["TL2_disclosed_control"]["records"]]
    write(output/"disclosed_TL2_regressions.json",{n:changes(json.loads(
        (ROOT/f"data/processed_tactical_learning_2/evaluation/{n}.json").read_text())["control"]["records"],
        models["B"]["TL2_disclosed_control"]["records"],old_ids) for n in ("frozen","initial","A","B")})
    lookups = {n:{r["id"]:r for r in m["control"]["records"]} for n,m in models.items()}
    groups = defaultdict(list)
    for r in rows:
        if "pair" in r:groups[r["pair"]["id"]].append(r)
    diagnostics = {}
    for pair,rs in groups.items():
        result = {"field":rs[0]["pair"]["field"],"models":{}}
        for name,lookup in lookups.items():
            def scores(row):
                rec = lookup[row["scenario_id"]]
                return {identity({k:v for k,v in a.items() if k not in
                    ("source_attack","source_health","target_attack","target_health")}):v
                    for a,v in zip(row["legal_actions"],rec["scores"],strict=True)}
            a,b = [scores(r) for r in rs]
            if a.keys()!=b.keys():raise ValueError("Numeric pair changed handles")
            delta = [b[k]-a[k] for k in a]
            recs = [lookup[r["scenario_id"]] for r in rs]
            result["models"][name] = {"max_logit_change":max(map(abs,delta)),
                "delta_range":max(delta)-min(delta),"ranks":[r["rank"] for r in recs],
                "sources":[r["prediction"].get("source_board_position") for r in recs],
                "gold_sources":[r["correct_actions"][0]["source_board_position"] for r in rs]}
        diagnostics[pair] = result
    write(output/"pair_logits.json",diagnostics)
    policy,encoder,payload,metadata = load_numeric(directory/"runs/B/policy.pt")
    weight = policy.action_encoder[0].weight[:,-len(FEATURES):].detach().cpu()
    real = real_parts(ROOT/"data/processed_policy_real/real_policy_retrain_1",payload["experiment"]["split"])
    coverage = {}
    for part,rs in real.items():
        matrices = [combat_features(r,metadata) for r in rs]
        coverage["real_"+part] = {"decisions":len(rs),"decisions_with_known_combat":sum(bool(m[:,1].any()) for m in matrices),
            "actions":sum(len(m) for m in matrices),"known_combat_actions":sum(int(m[:,1].sum()) for m in matrices)}
    for part in ("train","validation","control"):
        rs = read_rows(directory/f"dataset/{part}.jsonl")
        matrices = [combat_features(r,metadata) for r in rs]
        coverage["tactical_"+part] = {"decisions":len(rs),"decisions_with_known_combat":sum(bool(m[:,1].any()) for m in matrices)}
    examples = {}
    for row in rows:
        if row["scenario_id"] in ("nca_health_0_a","nca_health_0_b","nca_health_0_a_id","nca_health_0_b_id",
                                   "nca_attack_0_a","nca_attack_0_b"):
            examples[row["scenario_id"]] = [{"source_position":a.get("source_board_position"),
                "target_position":a.get("target_board_position"),"type":a["type"],"features":v}
                for a,v in zip(row["legal_actions"],features[row["scenario_id"]],strict=True)]
    write(output/"feature_audit.json",{"features":FEATURES,"coverage":coverage,"examples":examples,
        "new_column_l2_norms":weight.norm(dim=0).tolist(),"new_column_max_abs":weight.abs().max(dim=0).values.tolist()})
    write(output/"real_uncertainty.json",real_uncertainty(directory))
    write(output/"artifact_hashes.json",{"private_predictions":{n:sha(directory/f"evaluation/{n}.json")
        for n in c["models"]},"B_companion_base_sha256":sha(directory/"runs/B/base.pt"),
        "control_opened_sha256":sha(directory/"runs/CONTROL_OPENED.json"),
        "source_sha256":{str(p.relative_to(ROOT)):sha(p) for p in [
            *ROOT.glob("scripts/*numeric_combat_ablation.py"),ROOT/"src/manamind/training/numeric_combat.py",
            ROOT/"tests/test_numeric_combat.py"]}})
    return {"verdict":c["verdict"],"coverage":coverage,"weights":weight.abs().max().item()}


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.directory,args.output),indent=2))
