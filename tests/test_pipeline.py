import json
from pathlib import Path

import numpy as np
import torch
import pytest

from manamind.cards import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.domain.card import CardFeatures
from manamind.encoding import StateEncoder, collate_encoded_states
from manamind.inference import predict_game_states, predict_win_probabilities
from manamind.models import ValueNetwork, ValueNetworkConfig
from manamind.training.checkpoint import load_checkpoint, save_checkpoint
from manamind.training.metrics import binary_metrics, roc_auc
from manamind.training.pipeline import _validate_game_disjoint_splits
from manamind.training.split import split_dataset
from manamind.training.synthetic import (
    create_synthetic_catalog,
    generate_synthetic_dataset,
)
from manamind.training.trainer import TrainingConfig, train_value_network

ROOT = Path(__file__).parents[1]


def _sample_state():
    with (ROOT / "data" / "samples" / "example_state.json").open(encoding="utf-8") as file:
        return game_state_from_dict(json.load(file))


def _sample_catalog():
    return CardCatalog.from_json(ROOT / "data" / "samples" / "sample_cards.json")


def test_catalog_enriches_known_card_and_preserves_unknown_properties():
    catalog = _sample_catalog()
    known = catalog.enrich(CardFeatures(card_id="EX1_116"))
    unknown = catalog.enrich(
        CardFeatures(card_id="FUTURE_CARD", cost=3, attack=4, health=5, card_type="MINION")
    )

    assert known.cost == 5
    assert known.attack == 6
    assert "CHARGE" in known.mechanics
    assert unknown.card_id == "FUTURE_CARD"
    assert (unknown.cost, unknown.attack, unknown.health) == (3, 4, 5)


def test_encoder_keeps_unknown_card_properties_and_excludes_hidden_hand():
    encoder = StateEncoder(_sample_catalog())
    encoded = encoder.encode(_sample_state())

    assert encoded.global_features.shape == (54,)
    assert encoded.self_hand.card_ids.tolist() == [4, 1]
    assert encoded.self_hand.numeric[1, 0] > 0
    assert encoded.opponent_known_cards.size == 0
    assert encoded.opponent_known_cards.mechanics.shape[0] == 0


def test_shatter_fragment_semantics_are_encoded_without_engine_handles():
    from manamind.domain.game_state import GameState, PlayerObservation

    state = GameState(
        turn_number=1,
        active_player="SELF",
        self_player=PlayerObservation(hero_health=30, hand_size=2),
        opponent=PlayerObservation(hero_health=30),
        self_hand=(
            CardFeatures(card_id="CATA_489t", cost=4, card_type="SPELL", card_class="MAGE",
                         shatter_fragment="LEFT", shatter_original_card_id="CATA_489",
                         shatter_partner_hand_position=1),
            CardFeatures(card_id="CATA_489t2", cost=4, card_type="SPELL", card_class="MAGE",
                         shatter_fragment="RIGHT", shatter_original_card_id="CATA_489",
                         shatter_partner_hand_position=0),
        ),
    )
    catalog = _sample_catalog().merged(CardCatalog([CardFeatures(card_id="CATA_489", card_type="SPELL", card_class="MAGE", cost=4)]))
    encoded = StateEncoder(catalog).encode(state).self_hand

    assert encoded.card_ids.tolist() == [StateEncoder(catalog).vocabulary.card_id("CATA_489")] * 2
    assert encoded.hand_semantic_features[0, :3].tolist() == [1.0, 0.0, 0.0]
    assert encoded.hand_semantic_features[1, :3].tolist() == [0.0, 1.0, 0.0]
    assert encoded.hand_semantic_features[0, 3] > 0 > encoded.hand_semantic_features[1, 3]
    assert not hasattr(state.self_hand[0], "entity_id")
    from manamind.integrations.rosettastone.policy import (
        ACTION_FEATURE_NAMES, POLICY_STATE_FEATURE_NAMES, encode_action_card_ids,
        encode_hand_card_ids, encode_legal_actions, encode_policy_state,
    )
    actions = [{
        "type": "PLAY_CARD", "card_id": "CATA_489t", "card_type": "SPELL",
        "hand_index": 0, "shatter_fragment": "LEFT",
        "shatter_original_card_id": "CATA_489", "shatter_partner_hand_position": 1,
    }]
    policy_state = encode_policy_state(state, StateEncoder(catalog))
    action_features = encode_legal_actions(actions)
    assert policy_state.shape[0] == len(POLICY_STATE_FEATURE_NAMES)
    assert policy_state[POLICY_STATE_FEATURE_NAMES.index("self_hand_shatter_left")] > 0
    assert action_features[0, ACTION_FEATURE_NAMES.index("shatter_left")] == 1
    assert action_features[0, ACTION_FEATURE_NAMES.index("shatter_partner_relative_position")] > 0
    assert encode_hand_card_ids(state, StateEncoder(catalog))[:2].tolist() == [
        StateEncoder(catalog).vocabulary.card_id("CATA_489")
    ] * 2
    assert encode_action_card_ids(actions, StateEncoder(catalog))[0] == StateEncoder(catalog).vocabulary.card_id("CATA_489")


def test_prepare_legal_action_has_distinct_policy_feature():
    from manamind.integrations.rosettastone.policy import ACTION_FEATURE_NAMES, encode_legal_actions

    features = encode_legal_actions([{
        "type": "PREPARE_CARD", "card_id": "JAIL_321", "card_type": "MINION",
        "card_cost": 5, "hand_index": 2,
    }])
    assert features[0, ACTION_FEATURE_NAMES.index("prepare_card")] == 1.0
    assert features[0, ACTION_FEATURE_NAMES.index("play_card")] == 0.0


def test_game_state_rejects_malformed_shatter_link():
    from manamind.domain.game_state import GameState, PlayerObservation

    with pytest.raises(ValueError, match="reciprocal"):
        GameState(
            turn_number=1,
            active_player="SELF",
            self_player=PlayerObservation(hero_health=30, hand_size=2),
            opponent=PlayerObservation(hero_health=30),
            self_hand=(
                CardFeatures(card_id="CATA_489t", shatter_fragment="LEFT",
                             shatter_original_card_id="CATA_489", shatter_partner_hand_position=1),
                CardFeatures(card_id="CATA_489t2", shatter_fragment="RIGHT",
                             shatter_original_card_id="CATA_489", shatter_partner_hand_position=1),
            ),
        )


def test_encoder_preserves_visible_self_hand_order():
    state = _sample_state()
    encoded = StateEncoder(_sample_catalog()).encode(state)
    positions = encoded.self_hand.numeric[:, 7]
    position_known = encoded.self_hand.numeric_present[:, 7]

    assert position_known.tolist() == [1.0, 1.0]
    assert positions[0] < positions[1]
    assert encoded.opponent_known_cards.numeric_present[:, 7].sum() == 0


def test_policy_encodes_card_identity_and_hand_position():
    from manamind.integrations.rosettastone.policy import (
        ACTION_FEATURE_NAMES,
        PolicyNetwork,
        encode_action_card_ids,
        encode_hand_card_ids,
        encode_legal_actions,
        encode_policy_state,
    )

    state = _sample_state()
    encoder = StateEncoder(_sample_catalog())
    actions = [
        {"type": "PLAY_CARD", "card_id": "EX1_116", "card_type": "MINION", "hand_index": 0},
        {"type": "CHOOSE_CARD", "card_id": "UNKNOWN_CARD", "card_type": "MINION", "hand_index": 1},
    ]
    state_features = torch.as_tensor(encode_policy_state(state, encoder))
    action_features = torch.as_tensor(encode_legal_actions(actions))
    hand_ids = torch.as_tensor(encode_hand_card_ids(state, encoder), dtype=torch.long)
    action_ids = torch.as_tensor(encode_action_card_ids(actions, encoder), dtype=torch.long)
    policy = PolicyNetwork(
        state_feature_count=len(state_features), card_count=encoder.vocabulary.card_count
    )

    assert len(ACTION_FEATURE_NAMES) == action_features.shape[1]
    assert hand_ids[0] != hand_ids[1]
    assert action_ids[0] != action_ids[1]
    assert action_features[0, ACTION_FEATURE_NAMES.index("hand_index")] != action_features[
        1, ACTION_FEATURE_NAMES.index("hand_index")
    ]
    gift_action = encode_legal_actions([{
        "type": "CHOOSE_CARD", "card_id": "CATA_133", "card_type": "MINION",
        "dark_gift_id": 8,
    }])
    gift_features = [
        gift_action[0, ACTION_FEATURE_NAMES.index(f"dark_gift_{gift_id}")]
        for gift_id in range(1, 11)
    ]
    assert gift_features == [0.0] * 7 + [1.0, 0.0, 0.0]
    location_action = encode_legal_actions([{
        "type": "ACTIVATE_LOCATION", "card_id": "JAIL_511",
        "card_type": "LOCATION", "source_health": 2,
    }])
    assert location_action[0, ACTION_FEATURE_NAMES.index("activate_location")] == 1.0
    logits = policy(state_features, action_features, hand_ids, action_ids)
    assert logits.shape == (2,)
    assert torch.isfinite(logits).all()


def test_policy_distinguishes_semantic_action_sources_targets_and_choice_options():
    from manamind.integrations.rosettastone.policy import (
        ACTION_FEATURE_NAMES,
        encode_action_card_ids,
        encode_legal_actions,
    )

    encoder = StateEncoder(_sample_catalog())
    card_ids = sorted(card_id for card_id in encoder.vocabulary._card_ids)
    assert len(card_ids) >= 2
    source_a, source_b = card_ids[:2]

    pairs = (
        (
            {"type": "PLAY_CARD", "card_id": "EX1_116", "card_type": "SPELL",
             "target_is_hero": True, "target_entity_id": 1},
            {"type": "PLAY_CARD", "card_id": "EX1_116", "card_type": "SPELL",
             "target_is_hero": False, "target_card_id": source_a, "target_entity_id": 101},
        ),
        (
            {"type": "ATTACK", "source_card_id": source_a, "source_board_position": 0,
             "target_card_id": source_b, "target_board_position": 1,
             "attacker_entity_id": 101, "target_entity_id": 202},
            {"type": "ATTACK", "source_card_id": source_b, "source_board_position": 1,
             "target_card_id": source_b, "target_board_position": 1,
             "attacker_entity_id": 102, "target_entity_id": 202},
        ),
        (
            {"type": "HERO_POWER", "card_id": "HERO_08bp", "target_is_hero": True,
             "target_entity_id": 2},
            {"type": "HERO_POWER", "card_id": "HERO_08bp", "target_is_hero": False,
             "target_card_id": source_a, "target_entity_id": 102},
        ),
        (
            {"type": "CHOOSE_CARD", "choice_index": 0, "choice_card_id": source_a,
             "target_entity_id": 101},
            {"type": "CHOOSE_CARD", "choice_index": 1, "choice_card_id": source_b,
             "target_entity_id": 102},
        ),
    )
    for left, right in pairs:
        features = encode_legal_actions([left, right])
        ids = encode_action_card_ids([left, right], encoder)
        representations = np.concatenate((features, ids[:, None]), axis=1)
        assert not np.array_equal(representations[0], representations[1])
        assert "target_entity_id" not in ACTION_FEATURE_NAMES
        assert "attacker_entity_id" not in ACTION_FEATURE_NAMES

    choice_rows = encode_legal_actions([pairs[3][0], pairs[3][1]])
    assert choice_rows[0, ACTION_FEATURE_NAMES.index("choice_index")] != choice_rows[
        1, ACTION_FEATURE_NAMES.index("choice_index")
    ]


def test_current_policy_weights_migrate_when_dark_gift_actions_are_added():
    from manamind.integrations.rosettastone.policy import (
        ACTION_FEATURE_NAMES,
        POLICY_STATE_FEATURE_NAMES,
        PolicyNetwork,
        load_policy_weights,
    )

    encoder = StateEncoder(_sample_catalog())
    new_state_features = {
        "self_hand_shatter_left", "self_hand_shatter_right", "self_hand_shatter_solo",
        "self_hand_shatter_intervening_cards_mean",
        "self_hand_prepare_locked_count", "self_hand_prepare_known_count",
    }
    new_action_features = {
        "shatter_left", "shatter_right", "shatter_solo",
        "shatter_partner_relative_position", "prepare_card",
    }
    old_state_names = [name for name in POLICY_STATE_FEATURE_NAMES if name not in new_state_features]
    old_names = [name for name in ACTION_FEATURE_NAMES if name not in new_action_features]
    old_policy = PolicyNetwork(card_count=encoder.vocabulary.card_count)
    new_policy = PolicyNetwork(card_count=encoder.vocabulary.card_count)
    old_checkpoint_state = {
        name: value.clone() for name, value in old_policy.state_dict().items()
    }
    current_weight = old_checkpoint_state["scorer.0.weight"]
    state_count = len(POLICY_STATE_FEATURE_NAMES)
    old_action_indices = [ACTION_FEATURE_NAMES.index(name) for name in old_names]
    old_state_indices = [POLICY_STATE_FEATURE_NAMES.index(name) for name in old_state_names]
    embedding_start = state_count + len(ACTION_FEATURE_NAMES)
    old_checkpoint_state["scorer.0.weight"] = torch.cat((
        current_weight[:, old_state_indices],
        current_weight[:, state_count + torch.as_tensor(old_action_indices)],
        current_weight[:, embedding_start:],
    ), dim=1)
    old_weight = old_checkpoint_state["scorer.0.weight"]
    payload = {
        "state_feature_names": old_state_names,
        "action_feature_names": old_names,
        "card_vocabulary": {"UNKNOWN_CARD": 0},
        "policy_state_dict": old_checkpoint_state,
    }

    assert load_policy_weights(new_policy, payload)
    new_weight = new_policy.scorer[0].weight
    old_action_index = old_names.index("hand_index")
    new_action_index = ACTION_FEATURE_NAMES.index("hand_index")
    state_count = len(POLICY_STATE_FEATURE_NAMES)
    old_action_offset = len(old_state_names)
    assert torch.equal(
        new_weight[:, state_count + new_action_index],
        old_weight[:, old_action_offset + old_action_index],
    )
    for feature_name in new_action_features:
        assert torch.count_nonzero(new_weight[:, state_count + ACTION_FEATURE_NAMES.index(feature_name)]) == 0
    for feature_name in new_state_features:
        assert torch.count_nonzero(new_weight[:, POLICY_STATE_FEATURE_NAMES.index(feature_name)]) == 0
    assert torch.equal(
        new_weight[:, state_count + len(ACTION_FEATURE_NAMES):],
        old_weight[:, old_action_offset + len(old_names):],
    )


def test_legacy_policy_weights_migrate_to_card_embeddings():
    from manamind.integrations.rosettastone.policy import (
        ACTION_FEATURE_NAMES,
        POLICY_STATE_FEATURE_NAMES,
        PolicyNetwork,
        load_policy_weights,
    )

    encoder = StateEncoder(_sample_catalog())
    policy = PolicyNetwork(card_count=encoder.vocabulary.card_count)
    old_action_names = [name for name in ACTION_FEATURE_NAMES if not name.startswith("shatter_") and not name.startswith("dark_gift_") and name != "prepare_card"]
    old_state_names = [
        name for name in POLICY_STATE_FEATURE_NAMES
        if name not in {"self_hero_power_ready", "opponent_hero_power_ready",
                        "self_hand_shatter_left", "self_hand_shatter_right",
                        "self_hand_shatter_solo", "self_hand_shatter_intervening_cards_mean"}
        | {"self_hand_prepare_locked_count", "self_hand_prepare_known_count"}
    ]
    old_state = {
        name: value.clone() for name, value in policy.state_dict().items()
    }
    weight = old_state["scorer.0.weight"]
    old_state["scorer.0.weight"] = weight[:, :len(old_state_names) + len(old_action_names)]
    payload = {
        "state_feature_names": old_state_names,
        "action_feature_names": old_action_names,
        "policy_state_dict": old_state,
    }

    assert load_policy_weights(policy, payload)
    state_count = len(POLICY_STATE_FEATURE_NAMES)
    assert torch.count_nonzero(policy.scorer[0].weight[:, state_count + len(old_action_names):]) == 0


def test_model_forward_batch_and_gradients():
    encoder = StateEncoder(_sample_catalog())
    encoded = encoder.encode(_sample_state())
    batch = collate_encoded_states([encoded, encoded])
    model = ValueNetwork(
        encoder.vocabulary,
        ValueNetworkConfig(
            card_embedding_dim=8,
            category_embedding_dim=4,
            entity_hidden_dim=16,
            global_hidden_dim=16,
            fusion_hidden_dim=24,
        ),
    )

    logits = model(batch)
    assert logits.shape == (2,)
    assert torch.isfinite(logits).all()
    logits.sum().backward()
    assert model.value_head.weight.grad is not None


def test_checkpoint_round_trip_preserves_predictions(tmp_path: Path):
    encoder = StateEncoder(_sample_catalog())
    model = ValueNetwork(encoder.vocabulary)
    model.eval()
    encoded = encoder.encode(_sample_state())
    batch = collate_encoded_states([encoded])
    before = model.predict_probability(batch).detach()

    path = tmp_path / "value.pt"
    save_checkpoint(path, model, encoder.vocabulary, 1, {"loss": 0.5}, catalog=encoder.catalog)
    restored_model, restored_vocabulary, _ = load_checkpoint(path)
    after = restored_model.predict_probability(batch).detach()
    restored_encoder = StateEncoder(_sample_catalog(), vocabulary=restored_vocabulary)
    restored_state = restored_encoder.encode(_sample_state())
    restored_batch = collate_encoded_states([restored_state])
    after_reencoding = restored_model.predict_probability(restored_batch).detach()

    assert restored_vocabulary.to_dict() == encoder.vocabulary.to_dict()
    torch.testing.assert_close(before, after)
    torch.testing.assert_close(before, after_reencoding)


def test_small_synthetic_training_reduces_train_loss(tmp_path: Path):
    catalog = create_synthetic_catalog(_sample_catalog())
    examples = generate_synthetic_dataset(192, catalog, seed=9)
    splits = split_dataset(examples, seed=9)
    encoder = StateEncoder(catalog)
    model = ValueNetwork(
        encoder.vocabulary,
        ValueNetworkConfig(
            card_embedding_dim=8,
            category_embedding_dim=4,
            entity_hidden_dim=16,
            global_hidden_dim=16,
            fusion_hidden_dim=24,
        ),
    )

    _, history = train_value_network(
        model,
        encoder.vocabulary,
        encoder,
        splits.train,
        splits.validation,
        TrainingConfig(batch_size=32, learning_rate=0.002, epochs=4, weight_decay=0, seed=9),
        tmp_path / "best.pt",
        device=torch.device("cpu"),
    )

    assert history[-1]["train_loss"] < history[0]["train_loss"]


def test_predictor_handles_multiple_states():
    encoder = StateEncoder(_sample_catalog())
    model = ValueNetwork(encoder.vocabulary)
    predictions = predict_win_probabilities([_sample_state(), _sample_state()], encoder, model)

    assert len(predictions) == 2
    assert all(np.isfinite(value) and 0.0 <= value <= 1.0 for value in predictions)
    from dataclasses import replace
    state = _sample_state()
    unknown_state = replace(
        state,
        self_hand=state.self_hand + (CardFeatures(card_id="UNSEEN_CARD"),),
        self_hand_known_count=state.self_hand_known_count + 1,
    )
    detailed = predict_game_states([unknown_state], encoder, model)[0]
    assert detailed.model_version == "value_v1"
    assert "UNSEEN_CARD" in detailed.unknown_cards


def test_active_player_changes_encoded_features():
    state = _sample_state()
    from dataclasses import replace
    opponent_turn = replace(state, active_player="OPPONENT")
    encoder = StateEncoder(_sample_catalog())
    first = encoder.encode(state).global_features
    second = encoder.encode(opponent_turn).global_features
    assert first[1:3].tolist() == [1.0, 0.0]
    assert second[1:3].tolist() == [0.0, 1.0]
    assert not np.array_equal(first, second)


def test_state_validation_and_nested_board_defaults():
    with np.testing.assert_raises(ValueError):
        from manamind.domain import PlayerObservation
        PlayerObservation(hero_health=30, deck_size=-1)
    entity = {
        "card": {"card_id": "MINION", "attack": 3, "health": 4},
        "current_health": 2,
    }
    from manamind.domain.serialization import _board_entity
    parsed = _board_entity(entity)
    assert (parsed.current_attack, parsed.current_health, parsed.max_health) == (3, 2, 4)


def test_locations_are_encoded_and_share_the_seven_slot_board_limit():
    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding.entity_encoder import STATE_FLAG_NAMES

    state = game_state_from_dict({
        "turn_number": 3,
        "active_player": "SELF",
        "self_player": {
            "hero_health": 30,
            "board": [{"card": {"card_id": "MINION", "card_type": "MINION"}}],
            "locations": [{
                "card": {"card_id": "LOCATION", "card_type": "LOCATION", "durability": 3},
                "current_health": 2,
                "max_health": 3,
                "board_position": 1,
                "on_cooldown": True,
            }],
        },
        "opponent": {"hero_health": 30},
    })
    catalog = CardCatalog([
        CardFeatures(card_id="MINION", card_type="MINION"),
        CardFeatures(card_id="LOCATION", card_type="LOCATION", durability=3),
    ])
    encoded = StateEncoder(catalog).encode(state)
    assert encoded.self_locations.size == 1
    assert encoded.self_locations.state_flags[0, STATE_FLAG_NAMES.index("on_cooldown")] == 1
    assert encoded.self_locations.numeric_present[0, 5] == 1

    state_data = {
        "turn_number": 3, "active_player": "SELF",
        "self_player": {"hero_health": 30,
                         "board": [{} for _ in range(7)],
                         "locations": [{"card": {"card_id": "LOC"}}]},
        "opponent": {"hero_health": 30},
    }
    with np.testing.assert_raises(ValueError):
        game_state_from_dict(state_data)


def test_split_keeps_match_groups_together_and_dataset_round_trips(tmp_path: Path):
    from manamind.training.synthetic import load_labeled_dataset, save_synthetic_dataset
    catalog = create_synthetic_catalog(_sample_catalog())
    examples = generate_synthetic_dataset(90, catalog, seed=31)
    splits = split_dataset(examples, seed=31)
    game_ids = [{item.game_id for item in split} for split in (splits.train, splits.validation, splits.test)]
    assert not (game_ids[0] & game_ids[1] or game_ids[0] & game_ids[2] or game_ids[1] & game_ids[2])
    path = tmp_path / "train.jsonl"
    save_synthetic_dataset(path, splits.train)
    loaded = load_labeled_dataset(path)
    assert loaded[0].game_id == splits.train[0].game_id
    assert loaded[0].sample_id == splits.train[0].sample_id


def test_loaded_splits_reject_a_match_shared_with_evaluation():
    from dataclasses import replace

    example = generate_synthetic_dataset(1, create_synthetic_catalog(_sample_catalog()))[0]
    train = [replace(example, game_id="shared-match")]
    validation = [replace(example, game_id="shared-match")]
    test = [replace(example, game_id="held-out-match")]

    with np.testing.assert_raises_regex(ValueError, "Dataset leakage"):
        _validate_game_disjoint_splits(train, validation, test)


def test_draw_metrics_exclude_draws_from_accuracy_and_auc():
    metrics = binary_metrics(np.asarray([0.0, 0.5, 1.0]), np.asarray([0.1, 0.99, 0.9]))
    assert metrics["accuracy"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert roc_auc(np.asarray([0.5, 0.5]), np.asarray([0.1, 0.9])) is None


def test_checkpoint_restores_exact_catalog_and_rejects_old_format(tmp_path: Path):
    encoder = StateEncoder(_sample_catalog())
    model = ValueNetwork(encoder.vocabulary)
    path = tmp_path / "value.pt"
    save_checkpoint(path, model, encoder.vocabulary, 1, {"loss": 0.5}, catalog=encoder.catalog)
    _, _, payload = load_checkpoint(path)
    restored = CardCatalog.from_dict(payload["catalog"])
    assert restored.to_dict() == encoder.catalog.to_dict()
    legacy_path = tmp_path / "legacy.pt"
    torch.save({"format_version": 1}, legacy_path)
    with np.testing.assert_raises_regex(ValueError, "older feature schema"):
        load_checkpoint(legacy_path)

    schema_two_payload = torch.load(path, weights_only=True)
    schema_two_payload["state_encoding_schema_version"] = 2
    schema_two_path = tmp_path / "schema-two.pt"
    torch.save(schema_two_payload, schema_two_path)
    with np.testing.assert_raises_regex(ValueError, "state_encoding_schema_version"):
        load_checkpoint(schema_two_path)
    schema_six_payload = torch.load(path, weights_only=True)
    schema_six_payload["state_encoding_schema_version"] = 6
    schema_six_path = tmp_path / "schema-six.pt"
    torch.save(schema_six_payload, schema_six_path)
    with np.testing.assert_raises_regex(ValueError, "state_encoding_schema_version"):
        load_checkpoint(schema_six_path)
