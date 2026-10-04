from dataclasses import asdict, replace

import pytest

from manamind.cards import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.encoding import StateEncoder
from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION


def test_public_minion_history_roundtrip_and_known_masks():
    state = game_state_from_dict({
        "turn_number": 3, "active_player": "SELF",
        "self_player": {"hero_health": 30, "current_turn_minion_types_played": [],
                        "previous_turn_minion_types_played": ["ELEMENTAL", "BEAST", "ELEMENTAL"]},
        "opponent": {"hero_health": 30},
    })
    assert state.self_player.previous_turn_minion_types_played == ("BEAST", "ELEMENTAL")
    assert state.opponent.previous_turn_minion_types_played is None
    assert game_state_from_dict(asdict(state)) == state
    encoder = StateEncoder(CardCatalog([]))
    encoded = encoder.encode(state)
    names = encoder.global_feature_names
    assert STATE_ENCODING_SCHEMA_VERSION == 15
    assert encoded.global_features[names.index("self_has_current_minion_type_history")] > 0
    assert encoded.global_features[names.index("self_previous_minion_type_elemental")] > 0
    assert encoded.global_features[names.index("opponent_has_previous_minion_type_history")] == 0
    known = replace(state, opponent=replace(state.opponent, previous_turn_minion_types_played=()))
    assert encoder.encode(known).global_features[names.index("opponent_has_previous_minion_type_history")] > 0


def test_minion_history_rejects_ids_and_copies_mutable_input():
    state = game_state_from_dict({"turn_number": 1, "active_player": "SELF",
                                 "self_player": {"hero_health": 30}, "opponent": {"hero_health": 30}})
    values = ["ELEMENTAL"]
    player = replace(state.self_player, current_turn_minion_types_played=values)
    values.clear()
    assert player.current_turn_minion_types_played == ("ELEMENTAL",)
    for invalid in (("TLC_226",), "ELEMENTAL", ("NEW_UNKNOWN_TYPE",)):
        with pytest.raises(ValueError, match="minion type history"):
            replace(player, current_turn_minion_types_played=invalid)
