"""Freeze TL2 data only after every row passes catalog, menu and two-mechanism gates."""
from __future__ import annotations

import argparse
import copy
import json
import random
from dataclasses import asdict,replace
from pathlib import Path

from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity
from manamind.domain.game_state import GameState,PlayerObservation
from manamind.domain.serialization import game_state_from_dict
from manamind.live.snapshot import state_to_dict
from manamind.training.policy_checkpoint import identity,load_policy_checkpoint
from manamind.training.tactical_learning import read_rows,encode_rows
from manamind.training.tactical_learning_2_gate import arithmetic_gold,validate_row
from prepare_tactical_learning import ROOT,INITIAL,INITIAL_SHA,menu,sha,write,vanilla_pool,semantic_fingerprint


def fixture(split,family,n,encoder,pool,raw):
    rng=random.Random(int(identity(["TL2",split,family,n])[:12],16))
    pool=list(pool)
    rng.shuffle(pool)
    texts=[]
    def body(a,h,**flags):
        base=pool[len(texts)%len(pool)]
        known=(rng.random()<0.5 or split=="control") and base.card_id not in {t['id'] for t in texts}
        card=base if known else CardFeatures(**{**asdict(base),"card_id":f"TL2_{split}_{family}_{n}_{len(texts)}"})
        record=raw.get(card.card_id)
        texts.append({"id":card.card_id,"type":"MINION","text":record.get("text","") if record else "",
                      "mechanics":record.get("mechanics",[]) if record else []})
        return BoardEntity(card,a,h,24,len(texts),**flags)
    own,enemy,hand=[],[],[]
    hp,armor,shield=30,0,False
    retaliation=rng.randint(4,8)
    health=rng.randint(9,15)
    goal="REMOVE_AND_SURVIVE"
    if family in ["one_finish","multi_finish"]:
        hp,armor=rng.randint(5,9),rng.randint(3,6)
        needed=hp+armor
        if family=="one_finish":
            goal="WIN_NOW"
            own=[body(needed,20,can_attack=True),body(needed-1,20,can_attack=True)]
            enemy=[body(0,4,divine_shield=True)]
            if split=="control":
                own.append(body(needed-2,20,can_attack=True))
                enemy.append(body(1,6,divine_shield=True))
        else:
            goal="WIN_BY_ATTACKS"
            count=2 if split!="control" else 3
            shield=split!="train"
            own=[body(2,20,can_attack=True) for _ in range(count)]+[body(needed,20,can_attack=True)]
            enemy=[body(0,2,taunt=True) for _ in range(2 if split=="control" else 1)]
    elif family in ["health","attack"]:
        count={"train":2,"validation":3,"control":4}[split]
        for k in range(count):
            own.append(body(3 if family=="health" else health if k==0 else health-1,
                            retaliation+2 if family=="attack" or k==0 else retaliation-1,
                            can_attack=True,poisonous=family=="health"))
        enemy=[body(retaliation,health,taunt=True),body(1,health+3,taunt=True,divine_shield=True)]
    elif family=="target":
        goal="DEAL_ENEMY_DAMAGE"
        hp,armor=30,0 if split=="train" else 7
        shield=split!="validation"
        own=[body(3,10),body(2,4)]
        enemy=[body(2,rng.randint(2,6),taunt=True),body(3,9,divine_shield=True)]
        if split=="control":
            own.append(body(1,7))
            enemy.append(body(4,8,divine_shield=True))
        hand=[encoder.catalog.get("CORE_CS2_029")]
        record=raw[hand[0].card_id]
        texts.append({"id":hand[0].card_id,"type":record["type"],"text":record["text"],"mechanics":record.get("mechanics",[])})
    elif family=="harm":
        goal="PURE_SELF_HARM"
        count={"train":1,"validation":2,"control":3}[split]
        own=[body(rng.randint(2,7),1) for _ in range(count)]
        enemy=[body(0,8,immune=True)]
        hand=[CardFeatures(card_id="TL2_DAMAGE_ALL",cost=1,current_cost=1,card_type="SPELL",card_class="WARRIOR")]
        texts.append({"id":"TL2_DAMAGE_ALL","text":"Deal $2 damage to all minions.","type":"SPELL","mechanics":[]})
    elif family=="ambiguous":
        goal="AMBIGUOUS"
        own=[body(2,8,can_attack=True),body(7,8,can_attack=True)]
        enemy=[body(3,5,divine_shield=True),body(1,6)]
        hp,armor,shield=9,2,None
    else:
        raise ValueError(family)
    rng.shuffle(own);rng.shuffle(enemy)
    own=[replace(m,board_position=i+1) for i,m in enumerate(own)]
    enemy=[replace(m,board_position=i+1) for i,m in enumerate(enemy)]
    state=GameState(turn_number=rng.randint(3,20),active_player="SELF",
        self_player=PlayerObservation(hero_health=20,hero_max_health=30,hero_divine_shield=False,
            hero_frozen=False,healing_bonus=0,spell_damage=0,board=tuple(own),hand_size=len(hand),
            available_mana=4 if hand else 0,max_mana=4,deck_size=20,player_class="MAGE" if family=="target" else "WARRIOR"),
        opponent=PlayerObservation(hero_health=hp,armor=armor,hero_max_health=40,hero_divine_shield=shield,
            hero_frozen=False,healing_bonus=0,spell_damage=0,board=tuple(enemy),deck_size=20),self_hand=tuple(hand))
    row={"scenario_id":f"tl2_{split}_{family}_{n}","split":split,"family_id":f"tl2_{split}_{family}",
         "template_id":f"tl2_{split}_{family}","category":family,"state":state_to_dict(state),
         "legal_actions":menu(state),"correct_actions":[],"certificate":{"goal":goal,
            "certainty":"AMBIGUOUS" if goal=="AMBIGUOUS" else "PROVEN_PROPERTY","texts":texts,
            "observed":{"spell_damage":0,"spell_damage_doubled":False,"healing_does_damage":False,
                        "spell_healing_doubled":False,"hand_keywords":[[] for _ in hand]},
            "scope":"Observed current flags are declared fixture facts; known vanilla base and text verified, not global optimality"}}
    row["correct_actions"]=[row["legal_actions"][i] for i in arithmetic_gold(row)]
    return row


def prepare(output,config):
    if sha(INITIAL)!=INITIAL_SHA:
        raise ValueError("Initial checkpoint changed")
    _,encoder,_=load_policy_checkpoint(INITIAL)
    pinned=ROOT/"data/cards/standard_current_enUS.json"
    data=json.loads(pinned.read_text(encoding="utf-8"))
    records=data["cards"] if isinstance(data,dict) else data
    raw={c["id"]:c for c in records}
    pool=vanilla_pool(encoder,records)
    recipes={"train":["one_finish","multi_finish","health","attack","target","harm"],
             "validation":["multi_finish","health","attack","target"],
             "control":["one_finish","multi_finish","health","attack","target","harm","ambiguous"]}
    groups={split:[fixture(split,family,n,encoder,pool,raw) for family in families
                   for n in range(32 if split=="train" else 4 if split=="control" and family in
                                  ["one_finish","multi_finish"] else 8)] for split,families in recipes.items()}
    # Stats pairs: same everything except the two current numeric observations and matching menu fields.
    for split,rows in groups.items():
        for j,left in enumerate(rows):
            if left["category"] not in ["health","attack"] or int(left["scenario_id"].split('_')[-1])%2:
                continue
            right=copy.deepcopy(left)
            right["scenario_id"]=rows[j+1]["scenario_id"]
            field="current_health" if left["category"]=="health" else "current_attack"
            board=right["state"]["self_player"]["board"]
            ranked=sorted(board,key=lambda m:m[field],reverse=True)
            ranked[0][field],ranked[1][field]=ranked[1][field],ranked[0][field]
            right["legal_actions"]=menu(game_state_from_dict(right["state"]))
            right["correct_actions"]=[right["legal_actions"][i] for i in arithmetic_gold(right)]
            left["pair"]=right["pair"]={"kind":"stats","id":left["scenario_id"],"field":field}
            rows[j+1]=right
    control=groups["control"]
    for kind in ["position","id"]:
        for n in range(6):
            left=control[n];right=copy.deepcopy(left)
            # One row can participate in position and ID interventions.
            p={"kind":kind,"id":f"tl2_{kind}_{n}"}
            left.setdefault("pairs",[]).append(p)
            right["pairs"]=[p]
            right["scenario_id"]+="_"+kind
            for side in ["self_player","opponent"]:
                board=right["state"][side]["board"]
                if kind=="position":
                    for m in board: m["board_position"]=len(board)+1-m["board_position"]
                    board.sort(key=lambda m:m["board_position"])
                else:
                    for m in board:
                        old=m["card"]["card_id"]; new=f"TL2_ALIAS_{n}_{side}_{m['board_position']}"
                        m["card"]["card_id"]=new
                        next(t for t in right["certificate"]["texts"] if t["id"]==old)["id"]=new
            right["legal_actions"]=menu(game_state_from_dict(right["state"]))
            right["correct_actions"]=[right["legal_actions"][i] for i in arithmetic_gold(right)]
            control.append(right)
    audit={}
    for split,rows in groups.items():
        for row in rows:
            random.Random(row["scenario_id"]).shuffle(row["legal_actions"])
            audit[row["scenario_id"]]=validate_row(row,encoder,raw,menu)
        encode_rows(rows,encoder,"cpu")  # Schema/handles check, no model ranking.
    normalized={k:{semantic_fingerprint(r) for r in v} for k,v in groups.items()}
    if any(normalized[a]&normalized[b] for a,b in [("train","validation"),("train","control"),("validation","control")]):
        raise ValueError("Cross-split mechanical content overlap")
    old=read_rows(ROOT/"data/processed_tactical_learning_1/dataset/control.jsonl")
    if normalized["control"]&{semantic_fingerprint(r) for r in old}:
        raise ValueError("Old disclosed control clone")
    output.mkdir(parents=True,exist_ok=False)
    for split,rows in groups.items():
        with (output/f"{split}.jsonl").open("x",encoding="utf-8",newline="\n") as f:
            for row in rows:f.write(json.dumps(row,sort_keys=True)+"\n")
    manifest={"schema":"manamind.tactical_learning/2","initial_sha256":INITIAL_SHA,"config":config,
              "config_sha256":identity(config),"counts":{k:len(v) for k,v in groups.items()},
              "files":{k:sha(output/f"{k}.jsonl") for k in groups},"recipes":recipes,
              "pinned_catalog_sha256":sha(pinned),"vanilla_ids":[c.card_id for c in pool],
              "old_control_overlap":0,"normalized_unique":{k:len(v) for k,v in normalized.items()},
              "source_sha256":{p:sha(ROOT/p) for p in ["scripts/prepare_tactical_learning_2.py",
                  "src/manamind/training/tactical_learning_2_gate.py"]},"data_gate_passed":True}
    write(output/"manifest.json",manifest)
    write(output/"data_gate.json",{"all_passed":True,"rows":len(audit),"certificates":audit,
        "checks":["pinned known texts/types/base stats/mechanics","declared synthetic IDs","complete legal menu",
                  "observed Spell Damage consistency","independent arithmetic vs exact Outcome",
                  "bounded integer winning prefixes vs independent Outcome attack replay","encoding contract",
                  "cross-split and old-control normalized-content overlap"]})
    return manifest


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--config",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,json.loads(args.config.read_text())),indent=2))
