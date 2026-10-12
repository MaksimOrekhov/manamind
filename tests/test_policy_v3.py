"""PolicyNetworkV3 contract: unchanged v2 inputs, menu-aware scoring, strict checkpoint and dispatch."""
from pathlib import Path
import sys

import pytest
import torch

from manamind.cards.catalog import CardCatalog
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.policy_inputs import encode_policy_inputs, representation_of
from manamind.models.policy_v2 import PolicyNetworkV2, encode_policy_v2, feature_contract
from manamind.models.policy_v3 import PolicyNetworkV3
from manamind.training.policy_checkpoint import (
    FORMAT_V3, compatibility, identity, load_policy_checkpoint, save_policy_checkpoint)

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_policy_v2 import scene  # noqa: E402
from test_real_policy_training import metadata  # noqa: E402

CATALOG = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")


def model(encoder, **kwargs):
    contract = feature_contract(encoder)
    torch.manual_seed(0)
    return PolicyNetworkV3(encoder.vocabulary.card_count, len(contract["state_feature_names"]),
                           len(contract["entity_feature_names"]), hidden_size=16, heads=2, **kwargs).eval()


def test_v3_uses_exactly_the_v2_inputs_and_dispatch():
    encoder = StateEncoder(CATALOG)
    state, actions = scene()
    policy = model(encoder)
    assert representation_of(policy) == 3 and representation_of(PolicyNetworkV2(
        encoder.vocabulary.card_count, 1, 1)) == 2
    inputs = encode_policy_inputs(state, actions, encoder, representation=3)
    for a, b in zip(inputs, encode_policy_v2(state, actions, encoder)):
        assert torch.equal(a, b)
    logits = policy(*inputs)
    assert logits.shape == (len(actions),) and torch.isfinite(logits).all()


@pytest.mark.parametrize("entity_layers,menu_layers", [(0, 0), (1, 0), (0, 1), (1, 1), (2, 1)])
def test_v3_shapes_and_menu_permutation_equivariance(entity_layers, menu_layers):
    encoder = StateEncoder(CATALOG)
    state, actions = scene()
    policy = model(encoder, entity_layers=entity_layers, menu_layers=menu_layers)
    state_f, ids, entities, action_f, card_ids, links = encode_policy_inputs(state, actions, encoder, representation=3)
    expected = policy(state_f, ids, entities, action_f, card_ids, links)
    order = torch.tensor([2, 0, 3, 1])
    shuffled = policy(state_f, ids, entities, action_f[order], card_ids[order], links[order])
    assert torch.allclose(shuffled, expected[order], atol=1e-5)  # a set layer must not read menu order


def test_menu_layer_makes_a_score_depend_on_the_alternatives():
    encoder = StateEncoder(CATALOG)
    state, actions = scene()
    inputs = list(encode_policy_inputs(state, actions, encoder, representation=3))
    with_menu = model(encoder, menu_layers=1)
    without_menu = model(encoder, menu_layers=0)
    full = with_menu(*inputs)[0].item()
    alone = with_menu(*inputs[:3], inputs[3][:1], inputs[4][:1], inputs[5][:1])[0].item()
    assert abs(full - alone) > 1e-6  # END_TURN scored with and without its alternatives
    assert abs(without_menu(*inputs)[0].item() - without_menu(
        *inputs[:3], inputs[3][:1], inputs[4][:1], inputs[5][:1])[0].item()) < 1e-5  # v2-style: independent


def test_v3_rejects_malformed_inputs():
    encoder = StateEncoder(CATALOG)
    state, actions = scene()
    policy = model(encoder)
    state_f, ids, entities, action_f, card_ids, links = encode_policy_inputs(state, actions, encoder, representation=3)
    with pytest.raises(ValueError):
        policy(state_f, ids, entities, action_f, card_ids, links + 100)
    with pytest.raises(ValueError):
        policy(state_f, ids, entities[:, :-1], action_f, card_ids, links)


def test_v3_checkpoint_round_trip_is_strict(tmp_path):
    encoder = StateEncoder(CATALOG)
    state, actions = scene()
    policy = model(encoder, entity_layers=1, menu_layers=1)
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, policy, encoder, metadata())
    restored, restored_encoder, payload = load_policy_checkpoint(path)
    assert payload["schema"] == FORMAT_V3 and isinstance(restored, PolicyNetworkV3)
    assert payload["model_config"]["menu_layers"] == 1 and compatibility(encoder, 3)["schema"] == FORMAT_V3
    inputs = encode_policy_inputs(state, actions, restored_encoder, representation=representation_of(restored))
    with torch.no_grad():
        assert torch.equal(policy(*inputs), restored(*inputs))
    payload["model_config"]["menu_layers"] = 2  # shape no longer matches the saved weights
    broken = tmp_path / "broken.pt"
    torch.save(payload, broken)
    with pytest.raises(ValueError):
        load_policy_checkpoint(broken)
    payload["model_config"]["menu_layers"] = 1
    payload["schema"] = "manamind.real_policy/2"  # v2 loader must never accept a v3 network
    wrong = tmp_path / "wrong.pt"
    torch.save(payload, wrong)
    with pytest.raises(ValueError):
        load_policy_checkpoint(wrong)
    assert identity(payload["model_config"])
