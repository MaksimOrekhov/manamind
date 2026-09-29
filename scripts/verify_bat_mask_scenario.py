"""Verify Bat Mask changes a Voidwalker to 1/1 and fills the board with copies."""

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


def main() -> None:
    warlock_deck = make_simple_test_deck(player_class="WARLOCK")
    warlock_deck[0] = "DINO_402"
    errors = validate_deck(warlock_deck, player_class="WARLOCK")
    if errors:
        raise RuntimeError("Warlock deck is invalid: " + "; ".join(errors))

    opponent_deck = make_simple_test_deck(player_class="WARRIOR")
    game = SimulatorSession(
        warlock_deck,
        opponent_deck,
        player1_class="WARLOCK",
        player2_class="WARRIOR",
        shuffle=False,
        random_start=False,
        random_seed=402,
    )

    minion_played = False
    for step in range(120):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()

        if state.active_player == "SELF":
            if not minion_played:
                play_voidwalker = next(
                    (
                        action for action in actions
                        if action["type"] == "PLAY_CARD"
                        and action.get("card_id") == "CORE_CS2_065"
                    ),
                    None,
                )
                if play_voidwalker is not None:
                    game.apply_action(play_voidwalker)
                    minion_played = True
                    continue

            if state.self_player.max_mana >= 8:
                play_bat_mask = next(
                    (
                        action for action in actions
                        if action["type"] == "PLAY_CARD"
                        and action.get("card_id") == "DINO_402"
                        and action.get("target_is_self")
                        and not action.get("target_is_hero")
                    ),
                    None,
                )
                if play_bat_mask is not None:
                    game.apply_action(play_bat_mask)
                    board = game.observation("PLAYER1").self_player.board
                    if len(board) != 7:
                        raise AssertionError(
                            f"Bat Mask should fill the board to 7 minions, got {len(board)}"
                        )
                    for minion in board:
                        if (
                            minion.card.card_id != "CORE_CS2_065"
                            or minion.current_attack != 1
                            or minion.max_health != 1
                        ):
                            raise AssertionError(
                                "Every resulting minion should be a 1/1 copy of "
                                f"the original 1/3 Voidwalker; got {minion}"
                            )

                    print(
                        "PASS DINO_402 Bat Mask: changed a 1/3 Voidwalker to 1/1 "
                        "and filled the board with six 1/1 copies",
                        flush=True,
                    )
                    return

            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
            continue

        game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError("Scenario did not play Bat Mask within 120 actions")


if __name__ == "__main__":
    main()
