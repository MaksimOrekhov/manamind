"""Public healing-bonus observation contract (ENGINE-PRIMITIVE-1 review fix).

``healing_bonus`` is a nullable public integer: ``None`` is unknown (historical real-game imports), ``0`` is a known
"no bonus". It is intentionally not an encoder feature, so existing Policy/Value checkpoints stay compatible.
"""
import json
from dataclasses import asdict, replace

import pytest

from manamind.cards import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.encoding import StateEncoder
from manamind.encoding.state_encoder import (
    GLOBAL_FEATURE_NAMES, PLAYER_NUMERIC_FEATURE_NAMES, STATE_ENCODING_SCHEMA_VERSION,
)
from manamind.training.readiness import _validate_visible_state_shape


def _state(self_extra=None, opponent_extra=None):
    return game_state_from_dict({
        "turn_number": 4, "active_player": "SELF",
        "self_player": {"hero_health": 25, **(self_extra or {})},
        "opponent": {"hero_health": 30, **(opponent_extra or {})},
    })


def test_missing_value_stays_unknown_and_zero_stays_known():
    historical = _state()
    assert historical.self_player.healing_bonus is None and historical.opponent.healing_bonus is None
    known = _state({"healing_bonus": 0}, {"healing_bonus": 4})
    assert known.self_player.healing_bonus == 0 and known.opponent.healing_bonus == 4
    assert historical != known and _state({"healing_bonus": 0}) != _state({"healing_bonus": 2}) != historical
    assert game_state_from_dict(asdict(known)) == known
    assert game_state_from_dict(asdict(historical)) == historical  # None survives the round trip, never becomes 0


@pytest.mark.parametrize("invalid", [-1, True, 1.5, "2"])
def test_invalid_values_are_rejected(invalid):
    with pytest.raises(ValueError, match="healing_bonus"):
        _state({"healing_bonus": invalid})


def test_encoder_and_checkpoint_schema_are_unchanged():
    assert STATE_ENCODING_SCHEMA_VERSION == 16
    assert not any("healing" in name for name in PLAYER_NUMERIC_FEATURE_NAMES)
    assert len(GLOBAL_FEATURE_NAMES) == 3 + 2 * len(PLAYER_NUMERIC_FEATURE_NAMES) + 5
    encoder = StateEncoder(CardCatalog([]))
    base = encoder.encode(_state())
    for bonus in (0, 2, 7):
        encoded = encoder.encode(replace(_state(), self_player=replace(_state().self_player, healing_bonus=bonus)))
        assert (encoded.global_features == base.global_features).all()
    assert encoder.global_feature_names == GLOBAL_FEATURE_NAMES


def _json(state):
    return json.loads(json.dumps(asdict(state)))


def test_visible_schema_accepts_new_and_historical_player_dictionaries():
    historical = _json(_state())
    for player in ("self_player", "opponent"):
        historical[player].pop("healing_bonus")
    _validate_visible_state_shape(historical)
    _validate_visible_state_shape(_json(_state({"healing_bonus": 2})))
    smuggled = _json(_state())
    smuggled["self_player"]["healing_bonus_source_entity"] = 12
    with pytest.raises(ValueError, match="outside its visible schema"):
        _validate_visible_state_shape(smuggled)
