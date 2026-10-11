"""Ordinary-combat boundaries and experimental compatibility, no optimizer runs."""
import sys
from pathlib import Path

import pytest
import torch

from manamind.models.policy_v2 import PolicyNetworkV2,feature_contract
from manamind.training.numeric_combat import combat_features,NumericCombatPolicy,save_numeric,load_numeric,numeric_rows
from manamind.training.policy_checkpoint import identity,load_policy_checkpoint

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import test_tactical_learning_2 as fixtures  # noqa: E402
from prepare_numeric_combat_ablation import control_pair  # noqa: E402
from prepare_tactical_learning import menu  # noqa: E402
from manamind.domain.serialization import game_state_from_dict  # noqa: E402


@pytest.fixture
def context():
    return fixtures.context.__wrapped__()


def row_for(context):
    encoder,pool,raw = context
    return control_pair("health",0,encoder,pool,raw)[0]


def test_numeric_pair_swaps_survival_and_gold_without_identity_change(context):
    encoder,pool,raw = context
    a,b = control_pair("health",0,encoder,pool,raw)
    feats = [combat_features(r,raw) for r in (a,b)]
    for r,f in zip((a,b),feats,strict=True):
        correct = r["correct_actions"][0]
        idx = r["legal_actions"].index(correct)
        assert f[idx].tolist() == [1,1,1,1]
    assert a["correct_actions"][0]["source_card_id"] != b["correct_actions"][0]["source_card_id"]


@pytest.mark.parametrize("shield,immune,poison,attack,hp,expected", [
    (True,False,True,3,17,False),(False,True,True,3,17,False),
    (False,False,True,3,17,True),(False,False,False,16,17,False),
    (False,False,False,17,17,True)])
def test_kill_threshold_shield_immune_poison(context,shield,immune,poison,attack,hp,expected):
    _,_,raw = context
    r = row_for(context)
    source = r["state"]["self_player"]["board"][0]
    target = r["state"]["opponent"]["board"][0]
    source.update(current_attack=attack,poisonous=poison)
    target.update(current_health=hp,divine_shield=shield,immune=immune)
    # Test one primitive even for an Immune target absent from a real legal menu.
    a = {"type":"ATTACK","source_kind":"MINION","target_kind":"MINION",
         "source_board_position":source["board_position"],"target_board_position":target["board_position"]}
    r["legal_actions"] = [a]
    assert bool(combat_features(r,raw)[0,0]) is expected


@pytest.mark.parametrize("reason", ["unknown_text","secret","reborn","unavailable","flag_unknown"])
def test_unknown_context_stays_masked(context,reason):
    _,_,raw = context
    r = row_for(context)
    if reason=="unknown_text":r["certificate"]["texts"][0]["text"] = "Unknown reactive effect"
    elif reason=="secret":r["state"]["opponent"]["secret_count"] = 1
    elif reason=="reborn":r["state"]["self_player"]["board"][0]["reborn"] = True
    elif reason=="unavailable":r["numeric_unknown_context"] = True
    else:
        for m in r["state"]["self_player"]["board"]:m["poisonous"] = None
    assert not combat_features(r,raw).any()


def test_numeric_input_cannot_read_gold_or_teacher_consequences(context):
    _,_,raw = context
    r = row_for(context);original = combat_features(r,raw)
    r["correct_actions"] = [];r["certificate"]["goal"] = "CHANGED"
    r["certificate"]["consequences"] = "Never a model input"
    assert torch.equal(original,combat_features(r,raw))


def test_zero_columns_and_strict_checkpoint_roundtrip(context,tmp_path):
    encoder,_,raw = context
    contract = feature_contract(encoder)
    base = PolicyNetworkV2(encoder.vocabulary.card_count,len(contract["state_feature_names"]),
                           len(contract["entity_feature_names"]),hidden_size=8,dropout=0).eval()
    numeric = NumericCombatPolicy(base).eval()
    row = row_for(context)
    row["legal_actions"] = menu(game_state_from_dict(row["state"]))
    inputs = numeric_rows([row],encoder,raw)[0][0]
    torch.testing.assert_close(base(*inputs[:-1]),numeric(*inputs),atol=1e-6,rtol=1e-5)
    split = {"game_ids":{"train":["a"],"validation":["b"],"test":["c"]},"dataset_sha256":"test"}
    experiment = {"split":split,"split_sha256":identity(split),"dataset_sha256":"test",
                  "config":{},"config_sha256":identity({})}
    save_numeric(tmp_path/"policy.pt",numeric,encoder,experiment,raw)
    restored,enc,_,metadata = load_numeric(tmp_path/"policy.pt")
    other = numeric_rows([row],enc,metadata)[0][0]
    assert torch.equal(numeric(*inputs),restored(*other))
    with pytest.raises(ValueError,match="schema"):load_policy_checkpoint(tmp_path/"policy.pt")
    payload = torch.load(tmp_path/"policy.pt",weights_only=True)
    payload["features"] = tuple(reversed(payload["features"]))
    torch.save(payload,tmp_path/"bad.pt")
    with pytest.raises(ValueError,match="contract"):load_numeric(tmp_path/"bad.pt")
