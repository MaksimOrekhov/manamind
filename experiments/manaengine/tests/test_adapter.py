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


def test_held_spell_progress_is_per_card_instance_and_clone_safe() -> None:
    deck = [
        "TEST_HELD_TRACKER", "TEST_HELD_TRACKER", "CORE_EX1_129",
        "TEST_HELD_TRACKER", "CORE_EX1_129", "TEST_HELD_TRACKER",
        *(["TEST_HELD_TRACKER"] * 24),
    ]
    session = ManaEngineSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=41,
    )

    for _ in range(2):
        end_turn = next(action for action in session.legal_actions() if action["type"] == "END_TURN")
        session.apply_action(end_turn)
    first_fan = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_EX1_129")
    progressed = session.apply_action(first_fan)
    tracker_costs = sorted(
        card.current_cost for card in progressed.self_hand if card.card_id == "TEST_HELD_TRACKER"
    )
    assert tracker_costs == [1, 1, 1, 2]

    branch = session.clone()
    assert sorted(
        card.current_cost for card in branch.observation().self_hand if card.card_id == "TEST_HELD_TRACKER"
    ) == tracker_costs

    for _ in range(2):
        end_turn = next(action for action in session.legal_actions() if action["type"] == "END_TURN")
        session.apply_action(end_turn)
    second_fan = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_EX1_129")
    after_branch = session.apply_action(second_fan)
    assert sorted(
        card.current_cost for card in after_branch.self_hand if card.card_id == "TEST_HELD_TRACKER"
    ) == [0, 0, 0, 1, 1, 2]
    assert sorted(
        card.current_cost for card in branch.observation().self_hand if card.card_id == "TEST_HELD_TRACKER"
    ) == tracker_costs
    assert any(
        action.get("card_id") == "TEST_HELD_TRACKER" and action.get("card_cost") == 0
        for action in session.legal_actions()
    )
