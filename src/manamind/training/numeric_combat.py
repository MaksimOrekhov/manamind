"""Isolated experimental ordinary-combat input; no production dispatch or simulation."""
from __future__ import annotations

import math
from pathlib import Path

import torch
from torch import nn

from manamind.domain.serialization import game_state_from_dict
from manamind.models.policy_v2 import PolicyNetworkV2
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint
from manamind.training.tactical_learning import encode_rows

FEATURES = ("ordinary_target_destroyed", "target_destroyed_known",
            "ordinary_source_survives", "source_survives_known")
SCHEMA = "manamind.numeric_combat_ablation/1"


def combat_features(row, metadata, device="cpu"):
    raw_boards = [m for side in ("self_player","opponent") for m in row["state"][side]["board"]]
    if any(type(m.get(k)) is not bool for m in raw_boards for k in
           ("divine_shield","immune","poisonous","reborn","lifesteal","windfury","dormant")):
        return torch.zeros((len(row["legal_actions"]),len(FEATURES)),device=device)
    state = game_state_from_dict(row["state"])
    # Text is visible card metadata, never goal/correct_actions/consequences.
    texts = {**metadata, **{t["id"]:t for t in row.get("certificate", {}).get("texts", [])}}
    result = torch.zeros((len(row["legal_actions"]), len(FEATURES)), device=device)
    if row.get("numeric_unknown_context"):
        return result  # Explicit metadata unavailable for this unlabelled fixture.
    boards = (*state.self_player.board, *state.opponent.board)
    def ordinary(m):
        record = texts.get(m.card.card_id)
        return (record is not None and record.get("type") == "MINION" and record.get("text", None) == ""
                and not record.get("mechanics") and not (m.reborn or m.lifesteal or m.windfury or m.dormant))
    context_known = (all(ordinary(m) for m in boards) and not state.evidence_constraints
        and not any(p.secret_count or p.active_effects or p.locations for p in (state.self_player,state.opponent)))
    if not context_known:
        return result  # No fabricated ordinary outcome for unknown text/reactive context.
    for i,a in enumerate(row["legal_actions"]):
        if a["type"] != "ATTACK" or a.get("source_kind") != "MINION" or a.get("target_kind") != "MINION":
            continue
        source = next(m for m in state.self_player.board if m.board_position == a["source_board_position"])
        target = next(m for m in state.opponent.board if m.board_position == a["target_board_position"])
        if any(type(getattr(m,k)) is not bool for m in (source,target) for k in ("divine_shield","immune","poisonous")):
            continue
        kills = (source.current_attack > 0 and not target.immune and not target.divine_shield
                 and (source.poisonous or source.current_attack >= target.current_health))
        survives = (source.immune or source.divine_shield or target.current_attack == 0
                    or (not target.poisonous and source.current_health > target.current_attack))
        result[i] = torch.tensor([float(kills),1.,float(survives),1.],device=device)
    return result


def numeric_rows(rows, encoder, metadata, device="cpu"):
    return [(tuple(inputs)+(combat_features(row,metadata,device),), gold)
            for row,(inputs,gold) in zip(rows,encode_rows(rows,encoder,device),strict=True)]


class NumericCombatPolicy(PolicyNetworkV2):
    """Four zero-initialized columns appended to the existing action projection."""
    def __init__(self, base):
        super().__init__(base.card_embedding.num_embeddings,base.state_feature_count,
                         base.entity_feature_count,base.hidden_size,base.dropout)
        self.load_state_dict(base.state_dict(),strict=True)
        old = self.action_encoder[0]
        new = nn.Linear(old.in_features+len(FEATURES),old.out_features)
        with torch.no_grad():
            new.weight.zero_()
            new.weight[:,:old.in_features].copy_(old.weight)
            new.bias.copy_(old.bias)
        self.action_encoder[0] = new
        self.to(next(base.parameters()).device)

    def forward(self,state,ids,entities,actions,card_ids,links,numeric):
        if numeric.shape != (len(actions),len(FEATURES)) or not torch.isfinite(numeric).all():
            raise ValueError("Incompatible numeric feature schema")
        # Original encoder validates all bindings/shapes before these inputs reach the model.
        tokens = self.entity_encoder(torch.cat((entities,self.card_embedding(ids)),dim=-1))
        source,target,left,right = (tokens[links.clamp_min(0)]*links.ge(0).unsqueeze(-1)).unbind(dim=1)
        query = self.action_encoder(torch.cat((actions,self.card_embedding(card_ids).flatten(1),source,target,numeric),dim=-1))
        attention = torch.softmax(query@tokens.T/math.sqrt(self.hidden_size),dim=-1)
        context = attention@tokens
        global_rows = self.global_encoder(state).expand(len(actions),-1)
        return self.scorer(torch.cat((query,global_rows,context,source*target,left,right),dim=-1)).squeeze(-1)


def save_numeric(path,policy,encoder,metadata,card_metadata):
    path = Path(path)
    base = PolicyNetworkV2(policy.card_embedding.num_embeddings,policy.state_feature_count,
                          policy.entity_feature_count,policy.hidden_size,policy.dropout)
    state = {k:v.cpu().clone() for k,v in policy.state_dict().items()}
    base_state = dict(state)
    base_state["action_encoder.0.weight"] = state["action_encoder.0.weight"][:,:-len(FEATURES)]
    base.load_state_dict(base_state,strict=True)
    save_policy_checkpoint(path.parent/"base.pt",base,encoder,metadata)
    with path.open("xb") as f:
        torch.save({"schema":SCHEMA,"features":FEATURES,"normalization":"binary values and presence masks",
                    "base_sha256":file_sha(path.parent/"base.pt"),"metadata":card_metadata,
                    "metadata_sha256":identity(card_metadata),"state":state,"experiment":metadata},f)


def file_sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_numeric(path,device="cpu"):
    path = Path(path)
    p = torch.load(path,map_location=device,weights_only=True)
    if (p.get("schema") != SCHEMA or p.get("features") != FEATURES or
        p.get("normalization") != "binary values and presence masks" or
        p.get("metadata_sha256") != identity(p.get("metadata")) or
        p.get("base_sha256") != file_sha(path.parent/"base.pt")):
        raise ValueError("Incompatible numeric checkpoint contract")
    base,encoder,payload = load_policy_checkpoint(path.parent/"base.pt",device)
    if p["experiment"] != payload["experiment"]:
        raise ValueError("Numeric checkpoint metadata mismatch")
    policy = NumericCombatPolicy(base).to(device)
    policy.load_state_dict(p["state"],strict=True)
    if not all(torch.isfinite(t).all() for t in policy.state_dict().values()):
        raise ValueError("Nonfinite numeric weights")
    policy.eval()
    return policy,encoder,p,p["metadata"]
