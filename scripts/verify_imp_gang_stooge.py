"""Verify Imp Gang Stooge's Deathrattle in a live simulator session."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (
    SimulatorSession,
    make_simple_test_deck,
    validate_decks,
)


def main() -> None:
    warlock_deck = make_simple_test_deck(player_class="WARLOCK")
    warrior_deck = make_simple_test_deck(player_class="WARRIOR")
    warlock_deck[0] = "JAIL_399"
    warrior_deck[0] = "Core_CS2_200"  # Boulderfist Ogre (6/7)

    errors = validate_decks(
        warlock_deck,
        warrior_deck,
        player1_class="WARLOCK",
        player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Test decks are invalid: " + "; ".join(errors))

    game = SimulatorSession(
        warlock_deck,
        warrior_deck,
        player1_class="WARLOCK",
        player2_class="WARRIOR",
        shuffle=False,
    )
    stooge_played = False
    ogre_played = False

    for _ in range(80):
        state = game.observation("ACTIVE")
        actions = game.legal_actions()

        if (
            state.self_player.player_class == "WARLOCK"
            and not stooge_played
            and state.self_player.max_mana >= 3
        ):
            play = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "JAIL_399"
                ),
                None,
            )
            if play is not None:
                game.apply_action(play)
                stooge_played = True
                continue

        if (
            state.self_player.player_class == "WARRIOR"
            and stooge_played
            and not ogre_played
            and state.self_player.max_mana >= 6
        ):
            play = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "Core_CS2_200"
                ),
                None,
            )
            if play is not None:
                game.apply_action(play)
                ogre_played = True
                continue

        if state.self_player.player_class == "WARLOCK" and ogre_played:
            stooge_position = next(
                (
                    minion.board_position
                    for minion in state.self_player.board
                    if minion.card.card_id == "JAIL_399"
                ),
                None,
            )
            ogre_position = next(
                (
                    minion.board_position
                    for minion in state.opponent.board
                    if minion.card.card_id == "Core_CS2_200"
                ),
                None,
            )
            attack = next(
                (
                    action
                    for action in actions
                    if action["type"] == "ATTACK"
                    and action.get("source_board_position") == stooge_position
                    and action.get("target_board_position") == ogre_position
                ),
                None,
            )
            if attack is not None:
                deck_size_before = state.self_player.deck_size
                game.apply_action(attack)
                deck_size_after = game.observation("PLAYER1").self_player.deck_size
                if deck_size_after != deck_size_before + 2:
                    raise AssertionError(
                        "Imp Gang Stooge should add exactly two cards to its deck; "
                        f"deck size changed from {deck_size_before} to {deck_size_after}"
                    )
                print(
                    "PASS JAIL_399 Imp Gang Stooge: Deathrattle added two cards "
                    f"to the deck ({deck_size_before} -> {deck_size_after})"
                )
                return

        end_turn = next(
            (action for action in actions if action["type"] == "END_TURN"), None
        )
        if end_turn is None:
            raise RuntimeError(f"No supported action available: {actions}")
        game.apply_action(end_turn)

    raise RuntimeError("Scenario did not reach Imp Gang Stooge's Deathrattle")


if __name__ == "__main__":
    main()
