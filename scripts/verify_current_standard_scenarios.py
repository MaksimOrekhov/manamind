"""Run small deterministic scenarios for individually supported current cards."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (
    SimulatorSession,
    make_simple_test_deck,
    validate_deck,
)


def verify_earthen_drake_end_turn_damage() -> None:
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player1_deck[0] = "CATA_999"  # Drawn in the opening hand with shuffle disabled.
    player2_deck = make_simple_test_deck(player_class="PALADIN")

    errors = validate_deck(player1_deck, player_class="WARLOCK")
    if errors:
        raise RuntimeError("Test deck is invalid: " + "; ".join(errors))

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )

    card_played = False
    for _ in range(40):
        state = game.observation("PLAYER1")
        if (
            state.active_player == "SELF"
            and state.turn_number >= 9
            and not card_played
        ):
            play_card = next(
                (
                    action
                    for action in game.legal_actions()
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "CATA_999"
                ),
                None,
            )
            if play_card is not None:
                health_before_play = state.opponent.hero_health
                game.apply_action(play_card)
                health_after_play = game.observation("PLAYER1").opponent.hero_health
                if health_after_play != health_before_play:
                    raise AssertionError("Earthen Drake must not deal damage on play")

                card_played = True
                end_turn = next(
                    action
                    for action in game.legal_actions()
                    if action["type"] == "END_TURN"
                )
                game.apply_action(end_turn)
                health_after_turn = game.observation("PLAYER1").opponent.hero_health
                expected_health = health_before_play - 4
                if health_after_turn != expected_health:
                    raise AssertionError(
                        "Earthen Drake should deal 4 damage at end of its controller's "
                        f"turn: expected {expected_health} health, got {health_after_turn}"
                    )
                print(
                    "PASS CATA_999 Earthen Drake: "
                    f"enemy hero {health_before_play} -> {health_after_turn} "
                    "after the controller's turn ended"
                )
                return

        end_turn = next(
            action
            for action in game.legal_actions()
            if action["type"] == "END_TURN"
        )
        game.apply_action(end_turn)

    raise RuntimeError("Scenario did not reach a playable Earthen Drake")


def verify_deios_end_turn_interaction(deios_owner: int) -> None:
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    if deios_owner == 1:
        player1_deck[0] = "TIME_064"
        player1_deck[1] = "CATA_999"
    elif deios_owner == 2:
        player1_deck[0] = "CATA_999"
        player2_deck[0] = "TIME_064"
    else:
        raise ValueError("deios_owner must be 1 or 2")

    errors = validate_deck(player1_deck, player_class="WARLOCK")
    if errors:
        raise RuntimeError("Test deck is invalid: " + "; ".join(errors))
    errors = validate_deck(player2_deck, player_class="PALADIN")
    if errors:
        raise RuntimeError("Test deck is invalid: " + "; ".join(errors))

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )

    deios_played = False
    drake_played = False
    for _ in range(40):
        state = game.observation("PLAYER1")
        is_deios_owner_turn = state.active_player == (
            "SELF" if deios_owner == 1 else "OPPONENT"
        )
        deios_turn_number = 13 if deios_owner == 1 else 14
        if (
            is_deios_owner_turn
            and not deios_played
            and state.turn_number >= deios_turn_number
        ):
            deios = next(
                (
                    action
                    for action in game.legal_actions()
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "TIME_064"
                ),
                None,
            )
            if deios is not None:
                game.apply_action(deios)
                deios_played = True

        state = game.observation("PLAYER1")
        if (
            state.active_player == "SELF"
            and deios_played
            and not drake_played
            and state.turn_number >= 15
        ):
            health_before_play = state.opponent.hero_health
            drake = next(
                (
                    action
                    for action in game.legal_actions()
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "CATA_999"
                ),
                None,
            )
            if drake is not None:
                game.apply_action(drake)
                health_after_play = game.observation("PLAYER1").opponent.hero_health
                if health_after_play != health_before_play:
                    raise AssertionError("Earthen Drake must not damage on play")

                end_turn = next(
                    action
                    for action in game.legal_actions()
                    if action["type"] == "END_TURN"
                )
                game.apply_action(end_turn)
                health_after_turn = game.observation("PLAYER1").opponent.hero_health
                expected_damage = 8 if deios_owner == 1 else 4
                expected_health = health_before_play - expected_damage
                if health_after_turn != expected_health:
                    raise AssertionError(
                        "Unexpected Earthen Drake damage with Deios owned by "
                        f"player {deios_owner}: expected {expected_damage} damage "
                        f"({expected_health} health), "
                        f"got {health_after_turn}"
                    )
                print(
                    f"PASS Deios owner P{deios_owner} + CATA_999: "
                    f"enemy hero {health_before_play} -> {health_after_turn} "
                    "after the controller's turn ended"
                )
                return

        end_turn = next(
            action
            for action in game.legal_actions()
            if action["type"] == "END_TURN"
        )
        game.apply_action(end_turn)

    raise RuntimeError("Scenario did not reach a playable Deios + Earthen Drake")


def verify_deios_doubles_earthen_drake() -> None:
    verify_deios_end_turn_interaction(deios_owner=1)


def verify_opponent_deios_does_not_double_earthen_drake() -> None:
    verify_deios_end_turn_interaction(deios_owner=2)


def verify_warlock_basics(card_id: str) -> None:
    """Check the base damage and Lifesteal behavior against a live minion."""
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="WARLOCK")
    if card_id in player1_deck:
        spell_index = player1_deck.index(card_id)
        player1_deck[0], player1_deck[spell_index] = (
            player1_deck[spell_index],
            player1_deck[0],
        )
    else:
        player1_deck[0] = card_id
    player2_deck = [value for value in player2_deck if value != "CORE_CS2_065"]
    player2_deck[:0] = ["CORE_CS2_065", "CORE_CS2_065"]

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="WARLOCK",
        shuffle=False,
    )
    spell_played = False
    for _ in range(80):
        # Keep the perspective fixed to PLAYER1 so SELF consistently means
        # the Warlock holding the spell, even while PLAYER2 is taking a turn.
        state = game.observation("PLAYER1")
        actions = game.legal_actions()

        if state.active_player == "SELF":
            before = game.observation("PLAYER1")
            if card_id == "CORE_ICC_055" and before.self_player.hero_health == 30:
                hero_power = next(
                    (a for a in actions if a["type"] == "HERO_POWER"),
                    None,
                )
                if hero_power is not None:
                    game.apply_action(hero_power)
                    continue
            spell_action = next(
                (
                    a
                    for a in actions
                    if a["type"] == "PLAY_CARD"
                    and a.get("card_id") == card_id
                    and (card_id != "CORE_ICC_055" or not a.get("target_is_self", False))
                ),
                None,
            )
            if spell_action is not None:
                target_position = spell_action.get("target_board_position", -1)
                target_minion = (
                    before.opponent.board[target_position]
                    if 0 <= target_position < len(before.opponent.board)
                    else None
                )
                if card_id == "CORE_ICC_055" and target_minion is None:
                    pass
                else:
                    health_before = before.self_player.hero_health
                    enemy_before = before.opponent.hero_health
                    enemy_board_health_before = sum(
                        minion.current_health for minion in before.opponent.board
                    )
                    self_board_health_before = sum(
                        minion.current_health for minion in before.self_player.board
                    )
                    game.apply_action(spell_action)
                    after = game.observation("PLAYER1")
                    if card_id == "CORE_CS2_062":
                        if after.self_player.hero_health != health_before - 3:
                            raise AssertionError(
                                "Hellfire must deal 3 damage to its controller: "
                                f"{health_before} -> {after.self_player.hero_health}; "
                                f"enemy {enemy_before} -> {after.opponent.hero_health}; "
                                f"own board {self_board_health_before} -> "
                                f"{sum(m.current_health for m in after.self_player.board)}; "
                                f"enemy board {enemy_board_health_before} -> "
                                f"{sum(m.current_health for m in after.opponent.board)}; "
                                f"action={spell_action}"
                            )
                        if after.opponent.hero_health != enemy_before - 3:
                            raise AssertionError("Hellfire must deal 3 damage to the enemy hero")
                        if not before.opponent.board or after.opponent.board:
                            raise AssertionError(
                                "Hellfire must also deal 3 damage to the enemy Voidwalkers"
                            )
                        print("PASS CORE_CS2_062 Hellfire: both heroes took 3 damage")
                    else:
                        enemy_board_health_after = sum(
                            minion.current_health for minion in after.opponent.board
                        )
                        if enemy_board_health_before - enemy_board_health_after != 3:
                            raise AssertionError(
                                "Drain Soul must deal 3 damage to one enemy minion: "
                                f"action={spell_action}, enemy board health "
                                f"{enemy_board_health_before} -> {enemy_board_health_after}"
                            )
                        if after.self_player.hero_health != min(30, health_before + 3):
                            raise AssertionError("Drain Soul must restore 3 Health through Lifesteal")
                        healed = after.self_player.hero_health - health_before
                        print(
                            "PASS CORE_ICC_055 Drain Soul: target took 3 damage; "
                            f"hero healed {healed} (capped at 30)"
                        )
                    spell_played = True
                    return

            # Put the first available minion into play; otherwise let the opponent
            # develop a target instead of consuming the spell on a hero.
            end_turn = next(a for a in actions if a["type"] == "END_TURN")
            game.apply_action(end_turn)
        else:
            face_attack = next(
                (
                    a
                    for a in actions
                    if a["type"] == "ATTACK" and a.get("target_is_hero")
                ),
                None,
            )
            if face_attack is not None:
                game.apply_action(face_attack)
                continue
            minion_action = next(
                (
                    a
                    for a in actions
                    if a["type"] == "PLAY_CARD"
                    and a.get("card_id") == "CORE_CS2_065"
                ),
                None,
            )
            if minion_action is not None:
                game.apply_action(minion_action)
            else:
                end_turn = next(a for a in actions if a["type"] == "END_TURN")
                game.apply_action(end_turn)

    if not spell_played:
        raise RuntimeError(f"Did not reach a playable {card_id} scenario")


def verify_glacial_shard_battlecry_freeze() -> None:
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="WARLOCK")
    shard_id = "CORE_UNG_205"
    if shard_id in player1_deck:
        shard_index = player1_deck.index(shard_id)
        player1_deck[0], player1_deck[shard_index] = (
            player1_deck[shard_index],
            player1_deck[0],
        )
    else:
        player1_deck[0] = shard_id
    player2_deck = [card_id for card_id in player2_deck if card_id != "CORE_CS2_065"]
    player2_deck[:0] = ["CORE_CS2_065", "CORE_CS2_065"]

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="WARLOCK",
        shuffle=False,
    )

    for _ in range(40):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            if state.opponent.board:
                freeze_action = next(
                    (
                        action
                        for action in actions
                        if action["type"] == "PLAY_CARD"
                        and action.get("card_id") == shard_id
                        and not action.get("target_is_self", False)
                        and not action.get("target_is_hero", False)
                    ),
                    None,
                )
                if freeze_action is not None:
                    position = freeze_action["target_board_position"]
                    game.apply_action(freeze_action)
                    after = game.observation("PLAYER1")
                    frozen_target = next(
                        (
                            minion
                            for minion in after.opponent.board
                            if minion.board_position == position
                        ),
                        None,
                    )
                    if frozen_target is None or not frozen_target.frozen:
                        raise AssertionError(
                            "Glacial Shard's Battlecry must freeze the selected enemy minion"
                        )
                    print("PASS CORE_UNG_205 Glacial Shard: Battlecry froze an enemy minion")
                    return
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
        else:
            voidwalker = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "CORE_CS2_065"
                ),
                None,
            )
            if voidwalker is not None:
                game.apply_action(voidwalker)
            else:
                game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError("Did not reach a playable Glacial Shard Battlecry scenario")


def verify_caged_cranium_health_scales_with_hand() -> None:
    card_id = "JAIL_513"
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    if card_id in player1_deck:
        card_index = player1_deck.index(card_id)
        player1_deck[0], player1_deck[card_index] = (
            player1_deck[card_index],
            player1_deck[0],
        )
    else:
        player1_deck[0] = card_id

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )

    for _ in range(40):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            play_action = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == card_id
                ),
                None,
            )
            if play_action is not None:
                expected_health = 1 + len(state.self_hand) - 1
                game.apply_action(play_action)
                after = game.observation("PLAYER1")
                minion = next(
                    (item for item in after.self_player.board if item.card.card_id == card_id),
                    None,
                )
                if minion is None:
                    raise AssertionError("Caged Cranium should enter its controller's board")
                if minion.current_health != expected_health:
                    raise AssertionError(
                        "Caged Cranium should gain +1 Health for each card remaining "
                        f"in hand: expected {expected_health}, got {minion.current_health}"
                    )
                if not minion.taunt:
                    raise AssertionError("Caged Cranium should retain Taunt")
                print(
                    "PASS JAIL_513 Caged Cranium: "
                    f"{len(state.self_hand) - 1} cards in hand gave it "
                    f"{minion.current_health} Health and Taunt"
                )
                return
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
        else:
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError("Did not reach a playable Caged Cranium scenario")


def verify_unseen_atlas_hand_discount_and_draw() -> None:
    card_id = "JAIL_514"
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    if card_id in player1_deck:
        card_index = player1_deck.index(card_id)
        player1_deck[0], player1_deck[card_index] = (
            player1_deck[card_index],
            player1_deck[0],
        )
    else:
        player1_deck[0] = card_id

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )

    for _ in range(40):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            play_action = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == card_id
                ),
                None,
            )
            if play_action is not None:
                cards_before = len(state.self_hand)
                expected_cost = max(0, 10 - cards_before)
                if play_action["card_cost"] != expected_cost:
                    raise AssertionError(
                        "The Unseen Atlas should cost 10 minus cards in hand: "
                        f"expected {expected_cost}, got {play_action['card_cost']}"
                    )
                game.apply_action(play_action)
                after = game.observation("PLAYER1")
                expected_hand_size = min(10, cards_before + 2)
                if len(after.self_hand) != expected_hand_size:
                    raise AssertionError(
                        "The Unseen Atlas should draw 3 cards after leaving the hand: "
                        f"expected hand size {expected_hand_size}, got {len(after.self_hand)}"
                    )
                print(
                    "PASS JAIL_514 The Unseen Atlas: "
                    f"{cards_before} cards reduced cost to {play_action['card_cost']}; "
                    "draw 3 resolved"
                )
                return
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
        else:
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError("Did not reach a playable The Unseen Atlas scenario")


def verify_rafaam_ladder_draws_distinct_costs() -> None:
    card_id = "TIME_031"
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    if card_id in player1_deck:
        card_index = player1_deck.index(card_id)
        player1_deck[0], player1_deck[card_index] = (
            player1_deck[card_index],
            player1_deck[0],
        )
    else:
        player1_deck[0] = card_id
    # Keep an otherwise rare 4-cost card in the deck so three unique costs
    # remain available when the test spell is cast at four mana.
    player1_deck[15] = "CORE_CS2_179"  # Sen'jin Shieldmasta, 4 mana.

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )

    for _ in range(40):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            play_action = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == card_id
                ),
                None,
            )
            if play_action is not None:
                cards_before = len(state.self_hand)
                game.apply_action(play_action)
                after = game.observation("PLAYER1")
                expected_hand_size = min(10, cards_before + 2)
                if len(after.self_hand) != expected_hand_size:
                    raise AssertionError(
                        "RAFAAM LADDER!! should draw 3 cards after leaving the hand: "
                        f"expected {expected_hand_size} (from {cards_before}), "
                        f"got {len(after.self_hand)}; after="
                        f"{[(card.card_id, card.effective_cost) for card in after.self_hand]}"
                    )
                drawn_cards = after.self_hand[cards_before - 1 :]
                if len(drawn_cards) != 3:
                    raise AssertionError(
                        f"RAFAAM LADDER!! should draw 3 cards, got {len(drawn_cards)}"
                    )
                drawn_costs = [card.effective_cost for card in drawn_cards]
                if len(set(drawn_costs)) != 3:
                    raise AssertionError(
                        "RAFAAM LADDER!! must draw cards with distinct Costs: "
                        f"got {drawn_costs}"
                    )
                print(
                    "PASS TIME_031 RAFAAM LADDER!!: "
                    f"drew 3 cards with distinct costs {drawn_costs}"
                )
                return
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
        else:
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError("Did not reach a playable RAFAAM LADDER!! scenario")


def verify_cursed_catacombs_discovers_temporary_card() -> None:
    catacombs_id = "TLC_451"
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    player1_deck[0] = catacombs_id
    expected_card = player1_deck[4]

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )
    for _ in range(20):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            cast = next(
                (a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == catacombs_id),
                None,
            )
            if cast is not None:
                game.apply_action(cast)
                choices = game.legal_actions()
                choice = next(
                    (a for a in choices if a["type"] == "CHOOSE_CARD" and a.get("card_id") == expected_card),
                    None,
                )
                if choice is None:
                    raise AssertionError(f"Expected deck choice for {expected_card}, got {choices}")
                game.apply_action(choice)
                hand_after_choice = game.observation("PLAYER1").self_hand
                hand_count_after_choice = sum(
                    card.card_id == expected_card for card in hand_after_choice
                )
                if hand_count_after_choice == 0:
                    raise AssertionError("Cursed Catacombs must put the selected deck card in hand")
                game.apply_action(next(a for a in game.legal_actions() if a["type"] == "END_TURN"))
                hand_after_turn = game.observation("PLAYER1").self_hand
                hand_count_after_turn = sum(
                    card.card_id == expected_card for card in hand_after_turn
                )
                if hand_count_after_turn != hand_count_after_choice - 1:
                    raise AssertionError(
                        "The selected temporary card must leave hand at end of turn; "
                        f"copies in hand: {hand_count_after_choice} -> "
                        f"{hand_count_after_turn}"
                    )
                print("PASS TLC_451 Cursed Catacombs: discovered card entered hand and expired at end of turn")
                return
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
        else:
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
    raise RuntimeError("Did not reach a playable Cursed Catacombs scenario")


def verify_cursed_chains_returns_minion_after_opponent_turn() -> None:
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    player1_deck[0] = "CATA_496"
    target_card_id = player2_deck[0]
    player2_deck = [target_card_id, target_card_id] + [
        card_id for card_id in player2_deck if card_id != target_card_id
    ][:28]

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )
    target_stolen = False
    target_returned = False
    player1_turns = 0
    for _ in range(24):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            player1_turns += 1
            chains_action = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "CATA_496"
                    and action.get("card_type") == "SPELL"
                    and any(
                        minion.card.card_id == target_card_id
                        for minion in state.opponent.board
                    )
                ),
                None,
            )
            if chains_action is not None and player1_turns >= 3:
                target_stolen = True
                game.apply_action(chains_action)
                state = game.observation("PLAYER1")
                stolen_minion = next(
                    (m for m in state.self_player.board if m.card.card_id == target_card_id),
                    None,
                )
                if stolen_minion is None:
                    raise AssertionError("Cursed Chains must transfer the target to our board")
                if stolen_minion.can_attack:
                    raise AssertionError("The stolen minion must not attack during this turn")
                game.apply_action(next(a for a in game.legal_actions() if a["type"] == "END_TURN"))
                state = game.observation("PLAYER1")
                if not any(m.card.card_id == target_card_id for m in state.self_player.board):
                    raise AssertionError("Cursed Chains must retain control through our turn end")
                continue

            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
        else:
            if target_stolen:
                game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
                state = game.observation("PLAYER1")
                target_returned = any(
                    m.card.card_id == target_card_id for m in state.opponent.board
                )
                if target_returned:
                    print("PASS CATA_496 Cursed Chains: control lasted through our turn and returned after the opponent's turn")
                    return
                continue

            minion = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == target_card_id
                ),
                None,
            )
            if minion is not None:
                game.apply_action(minion)
            else:
                game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError(
        "Cursed Chains scenario did not complete "
        f"(target_stolen={target_stolen}, target_returned={target_returned})"
    )


def verify_shadow_rounds_repeats_after_kill() -> None:
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    player1_deck[0] = "JAIL_515"
    player2_cards = {"CORE_UNG_205", "CATA_999"}
    player2_deck = ["CORE_UNG_205", "CATA_999"] + [
        card_id for card_id in player2_deck if card_id not in player2_cards
    ][:28]

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )
    doctor_played = False
    guard_played = False
    for _ in range(32):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "OPPONENT":
            if not doctor_played:
                play = next(
                    (a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == "CORE_UNG_205"),
                    None,
                )
                if play:
                    game.apply_action(play)
                    doctor_played = True
                    continue
            if doctor_played and not guard_played:
                play = next(
                    (a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == "CATA_999"),
                    None,
                )
                if play:
                    game.apply_action(play)
                    guard_played = True
                    continue
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
            continue

        state = game.observation("PLAYER1")
        doctor = next(
            (m for m in state.opponent.board if m.card.card_id == "CORE_UNG_205"),
            None,
        )
        guard = next(
            (m for m in state.opponent.board if m.card.card_id == "CATA_999"),
            None,
        )
        cast = next(
            (
                a for a in actions
                if a["type"] == "PLAY_CARD"
                and a.get("card_id") == "JAIL_515"
                and doctor is not None
                and a.get("target_board_position") == doctor.board_position
            ),
            None,
        )
        if guard_played and doctor is not None and guard is not None and cast is not None:
            game.apply_action(cast)
            after = game.observation("PLAYER1").opponent.board
            shard_remaining = any(m.card.card_id == "CORE_UNG_205" for m in after)
            drake_after = next((m for m in after if m.card.card_id == "CATA_999"), None)
            if shard_remaining or drake_after is None or drake_after.current_health != 2:
                raise AssertionError(
                    "Shadow Rounds must kill the 1-health target, then deal 2 to the remaining 4-health minion"
                )
            print("PASS JAIL_515 Shadow Rounds: killed the first minion and repeated damage on the other")
            return

        game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError(
        "Did not reach Shadow Rounds scenario "
        f"(doctor_played={doctor_played}, guard_played={guard_played})"
    )


def verify_shadowsworn_disciple_herald_and_deathrattle() -> None:
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    player1_deck[0] = "CATA_725"
    player1_deck[1] = "CATA_725"

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        shuffle=False,
    )
    disciples_played = 0
    life_taps = 0
    for _ in range(48):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "OPPONENT":
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
            continue

        if disciples_played == 1 and life_taps < 2 and state.turn_number >= 3:
            hero_power = next(
                (a for a in actions if a["type"] == "HERO_POWER"), None
            )
            if hero_power is not None:
                game.apply_action(hero_power)
                life_taps += 1
                continue

        if disciples_played < 2:
            disciple = next(
                (
                    a for a in actions
                    if a["type"] == "PLAY_CARD" and a.get("card_id") == "CATA_725"
                ),
                None,
            )
            if disciple is not None and (disciples_played == 0 or life_taps == 2):
                game.apply_action(disciple)
                disciples_played += 1
                continue

        game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
        if disciples_played == 2:
            after = game.observation("PLAYER1")
            soldiers = [
                minion for minion in after.self_player.board
                if minion.card.card_id == "CATA_725t"
            ]
            if (
                after.self_player.hero_health != 29
                or len(soldiers) != 2
                or sorted(minion.current_attack for minion in soldiers) != [5, 9]
                or sorted(minion.current_health for minion in soldiers) != [5, 9]
            ):
                raise AssertionError(
                    "Two Heralds should summon and upgrade two Soldiers; the first Soldier "
                    "should consume the Disciple to its right, triggering 3 healing; "
                    f"health={after.self_player.hero_health}, soldiers="
                    f"{[(m.current_attack, m.current_health) for m in soldiers]}, "
                    f"board={[(m.card.card_id, m.current_health) for m in after.self_player.board]}"
                )
            print(
                "PASS CATA_725 Shadowsworn Disciple: summoned and upgraded two Soldiers; "
                "a Soldier consumed the adjacent Disciple and its Deathrattle healed 3"
            )
            return

    raise RuntimeError(
        "Did not complete Shadowsworn Disciple scenario "
        f"(disciples_played={disciples_played}, life_taps={life_taps})"
    )


if __name__ == "__main__":
    verify_earthen_drake_end_turn_damage()
    verify_deios_doubles_earthen_drake()
    verify_opponent_deios_does_not_double_earthen_drake()
    verify_warlock_basics("CORE_ICC_055")
    verify_warlock_basics("CORE_CS2_062")
    verify_glacial_shard_battlecry_freeze()
    verify_caged_cranium_health_scales_with_hand()
    verify_unseen_atlas_hand_discount_and_draw()
    verify_rafaam_ladder_draws_distinct_costs()
    verify_cursed_catacombs_discovers_temporary_card()
    verify_cursed_chains_returns_minion_after_opponent_turn()
    verify_shadow_rounds_repeats_after_kill()
    verify_shadowsworn_disciple_herald_and_deathrattle()
