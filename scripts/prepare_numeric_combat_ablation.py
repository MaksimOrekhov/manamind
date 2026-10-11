"""Seal new counterfactual control; reuse only verified TL2 train/validation."""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

from manamind.domain.serialization import game_state_from_dict
from manamind.training.policy_checkpoint import identity,load_policy_checkpoint
from manamind.training.tactical_learning import read_rows,encode_rows
from manamind.training.tactical_learning_2_gate import arithmetic_gold,validate_row
from prepare_tactical_learning import ROOT,INITIAL,INITIAL_SHA,sha,write,menu,vanilla_pool,semantic_fingerprint
from prepare_tactical_learning_2 import fixture

TL2 = ROOT/"data/processed_tactical_learning_2/dataset"


def control_pair(kind,n,encoder,pool,raw):
    row = fixture("control","health" if kind=="health" else "attack",n,encoder,pool,raw)
    row["scenario_id"] = f"nca_{kind}_{n}_a"
    row["family_id"] = f"nca_{kind}_{n}"
    row["template_id"] = "nca_large_board_three_taunts"
    own = row["state"]["self_player"]["board"]
    enemy = row["state"]["opponent"]["board"]
    # Five to seven sources; three Taunts including two shielded distractors.
    for j in range(5+n%3-len(own)):
        m = copy.deepcopy(own[0]);m["card"]["card_id"] = f"TL2_NCA_{kind}_{n}_{j}"
        m["board_position"] = len(own)+1;own.append(m)
        row["certificate"]["texts"].append({"id":m["card"]["card_id"],"type":"MINION","text":"","mechanics":[]})
    target = next(m for m in enemy if not m["divine_shield"])
    target["current_attack"] = 8+n
    target["current_health"] = 17+n
    distractor = copy.deepcopy(next(m for m in enemy if m["divine_shield"]))
    distractor["card"]["card_id"] = f"TL2_NCA_TARGET_{kind}_{n}"
    distractor["board_position"] = 3;enemy.append(distractor)
    row["certificate"]["texts"].append({"id":distractor["card"]["card_id"],"type":"MINION","text":"","mechanics":[]})
    field = "current_health" if kind=="health" else "current_attack"
    for m in own:
        m["current_attack"] = 3 if kind=="health" else target["current_health"]-1
        m["current_health"] = target["current_attack"] if kind=="health" else target["current_attack"]+2
    winner = n%len(own)
    own[winner][field] += 1
    row["pair"] = {"kind":"stats","id":f"nca_{kind}_{n}","field":field}
    right = copy.deepcopy(row)
    right["scenario_id"] = f"nca_{kind}_{n}_b"
    swapped = right["state"]["self_player"]["board"]
    other = (winner+1)%len(own)
    swapped[winner][field],swapped[other][field] = swapped[other][field],swapped[winner][field]
    for r in (row,right):
        r["legal_actions"] = menu(game_state_from_dict(r["state"]))
        r["correct_actions"] = [r["legal_actions"][i] for i in arithmetic_gold(r)]
    return row,right


def prepare(output,config):
    if sha(INITIAL) != INITIAL_SHA:raise ValueError("Initial changed")
    _,encoder,_ = load_policy_checkpoint(INITIAL)
    data = json.loads((ROOT/"data/cards/standard_current_enUS.json").read_text(encoding="utf-8"))
    records = data["cards"] if isinstance(data,dict) else data
    raw = {c["id"]:c for c in records}
    metadata = {k:{"id":k,"type":v["type"],"text":v.get("text",""),"mechanics":v.get("mechanics",[])} for k,v in raw.items()}
    pool = vanilla_pool(encoder,records)
    groups = {part:read_rows(TL2/f"{part}.jsonl") for part in ("train","validation")}
    tl2_manifest = json.loads((TL2/"manifest.json").read_text())
    for part in groups:
        if sha(TL2/f"{part}.jsonl") != tl2_manifest["files"][part]:raise ValueError("TL2 data changed")
    base = [r for kind in ("health","attack") for n in range(4) for r in control_pair(kind,n,encoder,pool,raw)]
    control = list(base)
    for kind in ("position","id"):
        variants = []
        for r in base:
            v = copy.deepcopy(r);v["scenario_id"] += "_"+kind
            v["pair"]["id"] += "_"+kind
            for side in ("self_player","opponent"):
                board = v["state"][side]["board"]
                if kind=="position":
                    for m in board:m["board_position"] = len(board)+1-m["board_position"]
                    board.sort(key=lambda m:m["board_position"])
                else:
                    for m in board:
                        old = m["card"]["card_id"];new = f"TL2_NCA_UNKNOWN_{r['pair']['id']}_{side}_{m['board_position']}"
                        m["card"]["card_id"] = new
                        next(t for t in v["certificate"]["texts"] if t["id"]==old)["id"] = new
            v["legal_actions"] = menu(game_state_from_dict(v["state"]))
            v["correct_actions"] = [v["legal_actions"][i] for i in arithmetic_gold(v)]
            variants.append(v)
        control.extend(variants)
    for n in range(8):
        r = fixture("control","one_finish",n,encoder,pool,raw)
        r["scenario_id"] = f"nca_lethal_{n}"
        own = r["state"]["self_player"]["board"]
        # New four-source lethal with attacker shield; distinct from TL1/TL2 controls.
        m = copy.deepcopy(own[0]);m["card"]["card_id"] = f"TL2_NCA_LETHAL_{n}";m["board_position"] = 4
        m["current_attack"] = 1;own.append(m)
        for m in own:m["divine_shield"] = True
        r["certificate"]["texts"].append({"id":own[-1]["card"]["card_id"],"type":"MINION","text":"","mechanics":[]})
        r["legal_actions"] = menu(game_state_from_dict(r["state"]))
        r["correct_actions"] = [r["legal_actions"][i] for i in arithmetic_gold(r)]
        control.append(r)
    for n,r in enumerate(base[:8]):
        v = copy.deepcopy(r);v["scenario_id"] = f"nca_unknown_mechanics_{n}"
        v.pop("pair");v["correct_actions"] = []
        v["certificate"]["goal"] = "AMBIGUOUS";v["certificate"]["certainty"] = "AMBIGUOUS"
        # Remove text availability, not replace an ability with an empty text.
        v["numeric_unknown_context"] = True
        control.append(v)
    groups["control"] = control
    proofs = {}
    for part,rows in groups.items():
        for row in rows:
            if part=="control":random.Random(row["scenario_id"]).shuffle(row["legal_actions"])
            proofs[row["scenario_id"]] = validate_row(row,encoder,raw,menu)
        encode_rows(rows,encoder,"cpu")
    old_files = [TL2/"control.jsonl",ROOT/"data/processed_tactical_learning_1/dataset/control.jsonl",
        ROOT/"data/evaluation/model_first_1/control_test.jsonl",
        ROOT/"model-first-2/data/processed_synthetic/model_first_2c/test.jsonl"]
    old = {semantic_fingerprint(r) for p in old_files for r in read_rows(p)}
    if old & {semantic_fingerprint(r) for r in control}:raise ValueError("Disclosed control clone")
    output.mkdir(parents=True,exist_ok=False)
    for part,rows in groups.items():
        with (output/f"{part}.jsonl").open("x",encoding="utf-8",newline="\n") as f:
            for r in rows:f.write(json.dumps(r,sort_keys=True)+"\n")
    write(output/"metadata.json",metadata)
    manifest = {"schema":"numeric_combat_ablation/1","config":config,"config_sha256":identity(config),
        "initial_sha256":INITIAL_SHA,"counts":{p:len(rs) for p,rs in groups.items()},
        "files":{p:sha(output/f"{p}.jsonl") for p in groups},"tl2_manifest_sha256":sha(TL2/"manifest.json"),
        "metadata_sha256":sha(output/"metadata.json"),"old_controls_overlap":0,
        "source_sha256":{p:sha(ROOT/p) for p in ("scripts/prepare_numeric_combat_ablation.py",
            "src/manamind/training/numeric_combat.py")}}
    write(output/"manifest.json",manifest)
    write(output/"data_gate.json",{"passed":True,"rows":sum(map(len,groups.values())),"proofs":proofs})
    print(json.dumps(manifest,indent=2))


if __name__=="__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--config",type=Path,required=True)
    args = parser.parse_args()
    prepare(args.output,json.loads(args.config.read_text(encoding="utf-8")))
