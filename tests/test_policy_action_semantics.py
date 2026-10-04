"""Phase 4B public action distinctions and explicit policy schema migration."""

import numpy as np
import pytest
import torch

from manamind.integrations.rosettastone.policy import (
    ACTION_FEATURE_NAMES,
    POLICY_ACTION_SCHEMA_VERSION,
    POLICY_STATE_FEATURE_NAMES,
    PolicyNetwork,
    encode_legal_actions,
    load_policy_weights,
)


def test_per_card_spell_damage_and_choice_effective_cost_are_distinct():
    fireball = {"type": "PLAY_CARD", "card_id": "CORE_CS2_029", "card_type": "SPELL",
                "card_cost": 4, "hand_index": 0}
    rows = encode_legal_actions([
        {**fireball, "card_spell_damage": 0},
        {**fireball, "card_spell_damage": 1},
        {"type": "CHOOSE_CARD", "choice_index": 0, "choice_card_cost": 1},
        {"type": "CHOOSE_CARD", "choice_index": 0, "choice_card_cost": 2},
    ])
    assert not np.array_equal(rows[0], rows[1])
    assert rows[1, ACTION_FEATURE_NAMES.index("card_spell_damage")] > 0
    assert not np.array_equal(rows[2], rows[3])
    assert rows[3, ACTION_FEATURE_NAMES.index("choice_card_cost")] > rows[2, ACTION_FEATURE_NAMES.index("choice_card_cost")]


def test_known_zero_is_distinct_from_missing_and_handles_are_ignored():
    action = {"type": "PLAY_CARD", "card_type": "SPELL", "hand_index": 0}
    rows = encode_legal_actions([
        action, {**action, "card_spell_damage": 0},
        {**action, "card_spell_damage": 0, "entity_id": 999, "target_entity_id": 12},
        {**action, "choice_card_cost": -1},
    ])
    assert not np.array_equal(rows[0], rows[1])
    assert np.array_equal(rows[1], rows[2])
    assert np.array_equal(rows[0], rows[3])


def test_prepare_shatter_choice_targeting_and_current_cost_remain_distinct():
    base = {"type": "PLAY_CARD", "card_type": "SPELL", "hand_index": 0, "card_cost": 4}
    actions = [base, {**base, "type": "PREPARE_CARD"}, {**base, "type": "CHOOSE_CARD"},
               {**base, "shatter_fragment": "LEFT", "shatter_partner_hand_position": 2},
               {**base, "shatter_fragment": "RIGHT", "shatter_partner_hand_position": 2},
               {**base, "target_is_hero": True}, {**base, "target_is_self": True},
               {**base, "card_cost": 3}]
    rows = encode_legal_actions(actions)
    assert len({row.tobytes() for row in rows}) == len(actions)


def test_policy_schema_migration_zero_initializes_only_new_features():
    new_features = {"card_spell_damage", "choice_card_cost", "card_spell_damage_known", "choice_card_cost_known"}
    old_features = [name for name in ACTION_FEATURE_NAMES if name not in new_features]
    policy = PolicyNetwork(card_count=2)
    old_state = {key: value.clone() for key, value in policy.state_dict().items()}
    retained = len(POLICY_STATE_FEATURE_NAMES) + len(old_features)
    old_state["scorer.0.weight"] = torch.ones((128, retained))
    payload = {"policy_state_dict": old_state, "state_feature_names": list(POLICY_STATE_FEATURE_NAMES),
               "action_feature_names": old_features, "policy_action_schema_version": 1}
    assert load_policy_weights(policy, payload)
    weight = policy.state_dict()["scorer.0.weight"]
    for name in new_features:
        assert torch.count_nonzero(weight[:, len(POLICY_STATE_FEATURE_NAMES) + ACTION_FEATURE_NAMES.index(name)]) == 0
    for name in old_features:
        assert torch.all(weight[:, len(POLICY_STATE_FEATURE_NAMES) + ACTION_FEATURE_NAMES.index(name)] == 1)
    payload["policy_action_schema_version"] = POLICY_ACTION_SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="schema version"):
        load_policy_weights(policy, payload)
