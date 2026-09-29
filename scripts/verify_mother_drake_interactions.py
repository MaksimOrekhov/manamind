"""Verify the Mother Drake Warlock board-filling and board-clear combo."""

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
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player1_deck[:4] = ["JAIL_399", "TIME_064", "DINO_402", "JAIL_510"]
    player1_deck[4:6] = ["JAIL_511", "JAIL_511"]
    player2_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Interaction decks are invalid: " + "; ".join(errors))

    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="WARRIOR",
        shuffle=False,
        random_start=False,
        random_seed=999,
    )
    played: set[str] = set()

    for _ in range(300):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if game.is_complete:
            break

        if state.active_player != "SELF":
            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
            continue

        desired_card = None
        if "JAIL_399" not in played and state.self_player.max_mana >= 3:
            desired_card = "JAIL_399"
        elif "JAIL_399" in played and "TIME_064" not in played and state.self_player.max_mana >= 7:
            desired_card = "TIME_064"
        elif "TIME_064" in played and "DINO_402" not in played and state.self_player.max_mana >= 8:
            desired_card = "DINO_402"
        elif "DINO_402" in played and "JAIL_510" not in played and state.self_player.max_mana >= 9:
            desired_card = "JAIL_510"

        if desired_card is not None:
            card_actions = [
                a for a in actions
                if a["type"] == "PLAY_CARD" and a.get("card_id") == desired_card
            ]
            if desired_card == "DINO_402":
                stooge_position = next(
                    m.board_position for m in state.self_player.board
                    if m.card.card_id == "JAIL_399"
                )
                card_actions = [
                    a for a in card_actions
                    if not a.get("target_is_hero")
                    and a.get("target_board_position") == stooge_position
                ]

            if card_actions:
                if desired_card == "JAIL_510":
                    deck_size_before = state.self_player.deck_size
                game.apply_action(card_actions[0])
                played.add(desired_card)

                if desired_card == "DINO_402":
                    board = game.observation("PLAYER1").self_player.board
                    stooges = [m for m in board if m.card.card_id == "JAIL_399"]
                    deios = [m for m in board if m.card.card_id == "TIME_064"]
                    if len(board) != 7 or len(stooges) != 6 or len(deios) != 1:
                        raise AssertionError(
                            "Bat Mask should leave six Stooges and Deios on a full board; "
                            f"got {[m.card.card_id for m in board]}"
                        )
                    if not any(
                        card.card_id == "JAIL_511"
                        for card in game.observation("PLAYER1").self_hand
                    ):
                        raise AssertionError(
                            "The full-board scenario must retain a Spire of Solitude "
                            "in hand to check its play action"
                        )
                    if any(
                        a["type"] == "PLAY_CARD" and a.get("card_id") == "JAIL_511"
                        for a in game.legal_actions()
                    ):
                        raise AssertionError(
                            "A Location must not be offered as playable when minions "
                            "and Locations together fill the board"
                        )

                if desired_card == "JAIL_510":
                    after = game.observation("PLAYER1")
                    expected_deck_delta = 21  # 6 Deathrattles add 24 Imps; three are summoned.
                    actual_deck_delta = after.self_player.deck_size - deck_size_before
                    if actual_deck_delta != expected_deck_delta:
                        raise AssertionError(
                            "Deios should double all six copied Imp Gang Stooge "
                            "Deathrattles before Annihilation summons three bottom "
                            f"Demons; deck changed by {actual_deck_delta}, "
                            f"expected {expected_deck_delta}"
                        )
                    if len(after.self_player.board) != 3 or any(
                        minion.card.card_id != "JAIL_399t1"
                        for minion in after.self_player.board
                    ):
                        raise AssertionError(
                            "Annihilation should leave three newly added Grandmother "
                            "Imps on the board; got "
                            f"{[m.card.card_id for m in after.self_player.board]}"
                        )
                    if after.opponent.board:
                        raise AssertionError("Annihilation should clear the opponent board")
                    print(
                        "PASS Mother Drake combo: Bat Mask copied the Stooge six times; "
                        "Deios doubled all Deathrattles; Annihilation summoned three "
                        "Grandmother Imps"
                    )
                    return
                continue

        game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError(f"Combo did not finish; cards played: {sorted(played)}")


if __name__ == "__main__":
    main()
