"""Independent visible-entity, relational-menu and v2 checkpoint expectations."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import torch

from manamind.cards.catalog import CardCatalog
from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity, LocationEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.encoding.entity_encoder import NUMERIC_FEATURES
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.policy import encode_policy_state
from manamind.models.policy_v2 import ACTION_V2_FEATURE_NAMES, PolicyNetworkV2, encode_policy_v2, feature_contract
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint
from manamind.training.real_policy import load_examples

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_real_policy_dataset import fixture  # noqa: E402
from test_real_policy_training import metadata  # noqa: E402
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from import_policy_power_log import save_match  # noqa: E402
import train_real_policy as trainer  # noqa: E402

CATALOG = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")


def model(encoder, hidden_size=16):
    contract = feature_contract(encoder)
    return PolicyNetworkV2(encoder.vocabulary.card_count, len(contract["state_feature_names"]),
                           len(contract["entity_feature_names"]), hidden_size=hidden_size).eval()


def scene():
    card = CardFeatures("NEW_VISIBLE", cost=5, current_cost=0, attack=3, health=4, card_type="MINION")
    minion = BoardEntity(card, current_attack=3, current_health=2, max_health=4,
                         board_position=1, taunt=True, divine_shield=True, can_attack=True)
    location = LocationEntity(CardFeatures("NEW_LOCATION", card_type="LOCATION"),
                              current_health=2, max_health=3, board_position=2, can_activate=None)
    state = GameState(8, "SELF", PlayerObservation(25, armor=3, hand_size=1, board=(minion,), locations=(location,)),
                      PlayerObservation(20, board=(replace(minion, board_position=1),)), self_hand=(card,))
    base = {"type": "PLAY_CARD", "card_id": card.card_id, "source_card_id": card.card_id,
            "source_kind": "MINION", "card_type": "MINION", "hand_index": 0, "card_cost": 0,
            "target_kind": "MINION", "target_card_id": card.card_id, "target_side": "OPPONENT",
            "target_board_position": 1, "target_attack": 3, "target_health": 2}
    return state, [{"type": "END_TURN", "play_position": 0},
                   *[{**base, "play_position": slot} for slot in range(1, 4)]]


def test_entity_features_use_current_values_masks_flags_and_shared_positions():
    encoder = StateEncoder(CATALOG)
    state, actions = scene()
    global_features, ids, entities, action, card_ids, links = encode_policy_v2(state, actions, encoder)
    names = feature_contract(encoder)["entity_feature_names"]
    assert entities.shape[1] == len(names) and global_features.shape[0] == len(feature_contract(encoder)["state_feature_names"])
    hand, minion, location, target = 2, 3, 4, 5
    assert ids[hand] == ids[location] == ids[target] == 1  # UNK retains all structured features.
    assert entities[hand, names.index("base_cost")] > 0
    assert entities[hand, names.index("current_cost")] == 0
    assert entities[hand, names.index("has_current_cost")] == 1
    assert entities[hand, names.index("has_current_durability")] == 0
    assert entities[minion, names.index("divine_shield")] == 1
    assert entities[location, names.index("can_activate_known")] == 0
    assert entities[location, names.index("zone_position")] > entities[minion, names.index("zone_position")]
    assert links.tolist() == [[-1, -1, -1, -1], [hand, target, -1, minion],
                             [hand, target, minion, location], [hand, target, location, -1]]
    assert card_ids[0].tolist() == [0, 0]  # END_TURN has neither identity nor a source/target.
    assert action[0, ACTION_V2_FEATURE_NAMES.index("end_turn")] == 1
    assert action[1, ACTION_V2_FEATURE_NAMES.index("has_card_cost")] == 1
    assert action[1, ACTION_V2_FEATURE_NAMES.index("has_source_attack")] == 0
    assert len({tuple(row.tolist()) for row in action}) == 4


def test_v2_retains_identity_and_flags_discarded_by_v1_and_hand_order():
    encoder = StateEncoder(CATALOG)
    state, actions = scene()
    altered = replace(state, opponent=replace(state.opponent, board=(replace(state.opponent.board[0], divine_shield=False),)))
    assert np.array_equal(encode_policy_state(state, encoder), encode_policy_state(altered, encoder))
    a, b = encode_policy_v2(state, actions, encoder), encode_policy_v2(altered, actions, encoder)
    assert not torch.equal(a[2], b[2])
    altered = replace(state, self_hand=(state.self_hand[0], next(iter(CATALOG))),
                      self_player=replace(state.self_player, hand_size=2))
    reversed_hand = replace(altered, self_hand=tuple(reversed(altered.self_hand)))
    assert not torch.equal(encode_policy_v2(altered, actions[:1], encoder)[1],
                           encode_policy_v2(reversed_hand, actions[:1], encoder)[1])


@pytest.mark.parametrize("mutation", ["hidden", "secret", "unknown_target", "source_kind", "absent", "slot"])
def test_invalid_visibility_and_semantic_bindings_fail_closed(mutation):
    state, actions = scene()
    if mutation == "hidden":
        state = replace(state, opponent=replace(state.opponent, hand_size=1),
                        opponent_known_cards=(CardFeatures("PRIVATE_CANARY"),))
    elif mutation == "secret":
        state = replace(state, self_player=replace(state.self_player, secret_count=1,
                        known_secrets=(CardFeatures("PRIVATE_CANARY"),)))
    elif mutation == "unknown_target":
        actions[1]["target_card_id"] = "OTHER_UNK"  # Two UNK IDs must not make a wrong binding valid.
    elif mutation == "source_kind":
        actions[1]["source_kind"] = "LOCATION"
    elif mutation == "absent":
        actions[1]["target_board_position"] = 7
    else:
        actions[1]["play_position"] = 4
    with pytest.raises(ValueError):
        encode_policy_v2(state, actions, StateEncoder(CATALOG))


def test_model_menu_equivariance_context_sensitivity_and_finite_gradients():
    torch.manual_seed(42)
    encoder = StateEncoder(CATALOG)
    state, actions = scene()
    policy = model(encoder)
    inputs = encode_policy_v2(state, actions, encoder)
    logits = policy(*inputs)
    order = torch.tensor([3, 1, 0, 2])
    permuted = (*inputs[:3], *(x[order] for x in inputs[3:]))
    assert torch.allclose(policy(*permuted), logits[order], atol=1e-7)
    altered = list(inputs)
    altered[2] = inputs[2].clone()
    altered[2][5, NUMERIC_FEATURES.index("current_health")] += 0.3
    assert not torch.equal(policy(*altered), logits)
    loss = torch.nn.functional.cross_entropy(logits[None], torch.tensor([2]))
    loss.backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in policy.parameters())
    assert policy.card_embedding.weight.grad[1].abs().sum() > 0
    bad = list(inputs)
    bad[-1] = inputs[-1].clone()
    bad[-1][0, 0] = 100
    with pytest.raises(ValueError):
        policy(*bad)


def test_checkpoint_v2_roundtrip_and_feature_contract_rejections(tmp_path):
    encoder = StateEncoder(CATALOG)
    policy = model(encoder)
    state, actions = scene()
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, policy, encoder, metadata())
    restored, saved_encoder, payload = load_policy_checkpoint(path)
    assert payload["schema"] == "manamind.real_policy/2"
    inputs = encode_policy_v2(state, actions, encoder)
    assert torch.equal(policy(*inputs), restored(*encode_policy_v2(state, actions, saved_encoder)))
    original = copy.deepcopy(payload)
    for field in ("entity_feature_names", "action_links", "entity_roles", "representation_version", "action_feature_names"):
        payload = copy.deepcopy(original)
        payload[field] = []
        torch.save(payload, path)
        with pytest.raises(ValueError):
            load_policy_checkpoint(path)
    for field, value in (("architecture", "PolicyNetwork"), ("entity_feature_count", 1), ("dropout", float("nan"))):
        payload = copy.deepcopy(original)
        payload["model_config"][field] = value
        torch.save(payload, path)
        with pytest.raises(ValueError):
            load_policy_checkpoint(path)

    payload = copy.deepcopy(original)
    payload["policy_state_dict"]["card_embedding.weight"][1, 0] = float("inf")
    torch.save(payload, path)
    with pytest.raises(ValueError, match="Nonfinite"):
        load_policy_checkpoint(path)


def test_v2_training_frozen_reference_and_reproduction(tmp_path, monkeypatch):
    dataset = tmp_path / "data"
    for seed in range(8):
        rows, summary = extract_match(fixture(45, seed=seed).lines, CATALOG)
        save_match(rows, summary, dataset)
    cards = ROOT / "data/cards/standard_current_enUS.json"
    v1config = json.loads((ROOT / "configs/real_policy_ml1c.json").read_text())
    v1config.update(hidden_size=16, max_epochs=1)
    trainer.run(dataset, cards, tmp_path / "v1", v1config)
    config = json.loads((ROOT / "configs/real_policy_ml2a.json").read_text())
    config.update(hidden_size=16, max_epochs=2)
    baseline = tmp_path / "v1/policy.pt"
    rows = load_examples(dataset)
    test_ids = {r["game_id"] for r in trainer.freeze_split(rows, 42, 1)[0]["test"]}
    original = trainer.evaluate
    active = None
    def guard(policy, rows, encoder):
        if {r["game_id"] for r in rows} & test_ids:
            assert (active / "policy.pt").exists() and (active / "history.json").exists()
        return original(policy, rows, encoder)
    monkeypatch.setattr(trainer, "evaluate", guard)
    policies, results = [], []
    for i in range(2):
        active = tmp_path / f"v2_{i}"
        results.append(trainer.run(dataset, cards, active, config, baseline_checkpoint=baseline))
        policies.append(load_policy_checkpoint(active / "policy.pt")[0].state_dict())
    assert results[0]["metrics"] == results[1]["metrics"]
    assert all(torch.equal(t, policies[1][key]) for key, t in policies[0].items())
    payload = torch.load(baseline, weights_only=True)
    payload["experiment"]["dataset_sha256"] = "b" * 64
    payload["experiment"]["split"]["dataset_sha256"] = "b" * 64
    payload["experiment"]["split_sha256"] = identity(payload["experiment"]["split"])
    torch.save(payload, baseline)
    with pytest.raises(ValueError, match="frozen split identity mismatch"):
        trainer.run(dataset, cards, tmp_path / "invalid", config, baseline_checkpoint=baseline)
    assert not (tmp_path / "invalid").exists()


def test_live_v2_requires_explicit_file_pin_and_uses_saved_encoder(tmp_path):
    import hashlib
    from manamind.live.recommendation import PolicyRecommender, RecommendationUnavailable
    encoder = StateEncoder(CATALOG)
    path = tmp_path / "v2.pt"
    save_policy_checkpoint(path, model(encoder), encoder, metadata())
    with pytest.raises(RecommendationUnavailable, match="CHECKPOINT_IDENTITY_MISMATCH"):
        PolicyRecommender(path)
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    scorer = PolicyRecommender(path, expected_sha256=pin)
    assert isinstance(scorer.policy, PolicyNetworkV2)
    scorer.require_catalog(CATALOG)
    for bad in ("", "0" * 64, "not-a-sha"):
        with pytest.raises(RecommendationUnavailable, match="CHECKPOINT_IDENTITY_MISMATCH"):
            PolicyRecommender(path, expected_sha256=bad)
