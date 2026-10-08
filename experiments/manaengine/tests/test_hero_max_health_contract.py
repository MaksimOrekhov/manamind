"""OBSERVATION-EXTRACTION-1: the shared ``hero_max_health`` field and the native observation.

The native observation does not export a hero maximum Health (``ObservedPlayer`` has no such field), so the Python adapter
must leave the shared field unknown instead of guessing 30. If the native export ever gains the value, this test fails and
the adapter and the state-import analyzer must be updated together.
"""
from __future__ import annotations

from manamind.integrations.manaengine import ManaEngineSession


def test_native_observation_exports_no_hero_max_health_and_the_adapter_keeps_it_unknown() -> None:
    deck = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False, random_seed=17)
    raw = session._native.observation("PLAYER1")
    assert "hero_max_health" not in raw["self_player"] and "hero_max_health" not in raw["opponent"]
    state = session.observation()
    assert state.self_player.hero_health == 30
    assert state.self_player.hero_max_health is None and state.opponent.hero_max_health is None
    # Explicit native values keep their tri-state type: exhausted status and Frozen are real booleans here.
    assert state.self_player.hero_power_ready is True and state.self_player.hero_frozen is False
