from __future__ import annotations

from manamind.integrations.manaengine import ManaEngineSession
from manamind.integrations.rosettastone.policy import encode_legal_actions


def test_exports_existing_game_state_and_policy_compatible_card_actions() -> None:
    deck = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=17,
    )

    state = session.observation()
    assert state.active_player == "SELF"
    assert len(state.self_hand) == 4
    assert state.opponent.hand_size == 5
    assert state.self_player.hero_power is not None
    assert state.self_player.hero_power.card_id == "HERO_08bp"
    assert state.self_player.hero_power_ready is True
    assert state.opponent_known_cards == ()
    assert not hasattr(state.self_player.board[0], "entity_id") if state.self_player.board else True

    actions = session.legal_actions()
    plays = [action for action in actions if action["type"] == "PLAY_CARD"]
    assert not any(action["type"] == "HERO_POWER" for action in actions)
    assert plays
    assert all(action["card_id"] == "CORE_EX1_145" for action in plays)
    assert all(action["field_position"] == -1 for action in plays)
    encoded = encode_legal_actions(actions)
    assert encoded.shape[0] == len(actions)

    clone = session.clone()
    assert clone.observation() == state
    result_state = session.apply_action(plays[0])
    assert result_state.self_player.available_mana == 1
    assert len(result_state.self_hand) == 3
    assert clone.observation() == state
