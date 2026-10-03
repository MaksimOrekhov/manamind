from __future__ import annotations

from manamind.integrations.manaengine import ManaEngineSession, UnsupportedSimulationError
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


def test_optional_diagnostic_trace_is_off_by_default_and_clone_local() -> None:
    deck = ["CORE_DRG_107"] * 30
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    assert session.diagnostic_trace == ()
    session.set_diagnostic_trace(True)
    branch = session.clone()
    session.apply_action(next(row for row in session.legal_actions() if row["type"] == "END_TURN"))
    assert session.diagnostic_trace and session.diagnostic_trace[0].startswith("ACTION ")
    assert branch.diagnostic_trace == ()
    session.set_diagnostic_trace(False)
    assert session.diagnostic_trace == ()


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


def test_profile_held_threshold_transform_exports_minion_actions_and_clones() -> None:
    deck = [
        "JAIL_801", "CORE_EX1_145", "CORE_EX1_145", "CORE_EX1_145",
        *(["CORE_EX1_145"] * 26),
    ]
    opponent_deck = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(
        deck,
        opponent_deck,
        player1_class="SHAMAN",
        player2_class="MAGE",
        shuffle=False,
        random_seed=53,
    )

    for _ in range(2):
        action = next(action for action in session.legal_actions() if action["card_id"] == "CORE_EX1_145")
        session.apply_action(action)
    assert session.observation().self_hand[0].card_id == "JAIL_801"
    branch = session.clone()

    third_spell = next(action for action in session.legal_actions() if action["card_id"] == "CORE_EX1_145")
    state = session.apply_action(third_spell)
    transformed = state.self_hand[0]
    assert transformed.card_id == "JAIL_801t"
    assert transformed.card_type == "MINION"
    assert transformed.attack == transformed.health == 3
    assert branch.observation().self_hand[0].card_id == "JAIL_801"

    for _ in range(6):
        end_turn = next(action for action in session.legal_actions() if action["type"] == "END_TURN")
        session.apply_action(end_turn)
    battlecry = next(
        action for action in session.legal_actions()
        if action["card_id"] == "JAIL_801t" and action.get("target_entity_id") == 2
    )
    assert battlecry["card_type"] == "MINION"
    final_state = session.apply_action(battlecry)
    assert final_state.opponent.hero_health == 26


def test_blazing_invocation_uses_complete_pinned_pool_and_choice_continuation() -> None:
    deck = ["CORE_GIL_836"] * 30
    session = ManaEngineSession(
        deck,
        deck,
        player1_class="SHAMAN",
        player2_class="SHAMAN",
        shuffle=False,
        random_seed=0,
    )
    root = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_GIL_836")
    session.apply_action(root)
    assert session.needs_choice
    options = [action for action in session.legal_actions() if action["type"] == "CHOOSE_CARD"]
    assert len(options) == 3
    assert len({action["choice_card_id"] for action in options}) == 3
    assert all(action["choice_card_type"] == "MINION" for action in options)
    assert encode_legal_actions(options).shape[0] == 3
    repeated = ManaEngineSession(
        deck,
        deck,
        player1_class="SHAMAN",
        player2_class="SHAMAN",
        shuffle=False,
        random_seed=0,
    )
    repeated_root = next(action for action in repeated.legal_actions() if action.get("card_id") == "CORE_GIL_836")
    repeated.apply_action(repeated_root)
    repeated_ids = [action["choice_card_id"] for action in repeated.legal_actions()]
    assert [action["choice_card_id"] for action in options] == repeated_ids
    unsupported_branch = session.clone()
    unsupported_choice = unsupported_branch.legal_actions()[0]
    try:
        unsupported_branch.apply_action(unsupported_choice)
    except UnsupportedSimulationError:
        pass
    else:
        raise AssertionError("selecting an unsupported full-pool outcome must invalidate the branch")
    assert not unsupported_branch.is_valid

    # Find a reproducible draw containing the already supported neutral Viper.
    selected_session = None
    viper_option = None
    for seed in range(512):
        candidate = ManaEngineSession(
            deck,
            deck,
            player1_class="SHAMAN",
            player2_class="SHAMAN",
            shuffle=False,
            random_seed=seed,
        )
        candidate_root = next(action for action in candidate.legal_actions() if action.get("card_id") == "CORE_GIL_836")
        candidate.apply_action(candidate_root)
        choice_actions = candidate.legal_actions()
        option = next((action for action in choice_actions if action["choice_card_id"] == "CORE_SW_072"), None)
        if option is not None:
            selected_session, viper_option = candidate, option
            break
    assert selected_session is not None and viper_option is not None
    branch = selected_session.clone()
    branch_options = branch.legal_actions()
    assert [row["choice_card_id"] for row in branch_options] == [row["choice_card_id"] for row in selected_session.legal_actions()]
    result = selected_session.apply_action(viper_option)
    viper = next(card for card in result.self_hand if card.card_id == "CORE_SW_072")
    assert viper.current_cost == 2
    assert any(action["type"] == "END_TURN" for action in selected_session.legal_actions())
