"""Verify M.O.T.H.E.R.'s selected-card and adjacent-card cost reductions."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession,
    make_simple_test_deck,
    validate_deck,
)


def main() -> None:
    verify_single_trigger()
    verify_repeated_trigger()


def verify_single_trigger() -> None:
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player1_deck[0] = "BE_036"
    player1_deck[1] = "Core_CS2_200"  # Boulderfist Ogre, cost 6.
    player1_deck[2] = "Core_CS2_200"
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

    for _ in range(60):
        state = game.observation("PLAYER1")
        if state.active_player == "SELF" and state.turn_number >= 9:
            mother = next(
                (
                    action
                    for action in game.legal_actions()
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "BE_036"
                ),
                None,
            )
            if mother is not None:
                game.apply_action(mother)
                if not game.needs_choice:
                    raise AssertionError("M.O.T.H.E.R. must ask for a hand-card choice")

                before = game.observation("PLAYER1").self_hand
                choices = game.legal_actions()
                if len(choices) != len(before) or not choices:
                    raise AssertionError(
                        "M.O.T.H.E.R. must offer exactly the remaining cards in hand"
                    )

                # The choice actions preserve the current hand order. Select
                # an interior card when possible to check reductions both ways.
                selected_index = len(choices) // 2
                selected = choices[selected_index]
                if selected.get("type") != "CHOOSE_CARD":
                    raise AssertionError(f"Unexpected choice action: {selected}")
                game.apply_action(selected)
                if game.needs_choice:
                    raise AssertionError("M.O.T.H.E.R. should finish after one choice")

                after = game.observation("PLAYER1").self_hand
                for index, (before_card, after_card) in enumerate(zip(before, after)):
                    reduction = max(0, 5 - abs(index - selected_index))
                    old_cost = int(before_card.cost or 0)
                    expected = max(0, old_cost - reduction)
                    actual = int(after_card.cost or 0)
                    if actual != expected:
                        raise AssertionError(
                            f"Hand slot {index}: expected cost {expected} "
                            f"(was {old_cost}, reduction {reduction}), got {actual}"
                        )

                print(
                    "PASS BE_036 M.O.T.H.E.R.: selected hand slot "
                    f"{selected_index} among {len(before)}; cost reductions "
                    "5, 4, 3, 2, 1 applied outward and stop at zero"
                )
                return

        end_turn = next(
            action
            for action in game.legal_actions()
            if action["type"] == "END_TURN"
        )
        game.apply_action(end_turn)

    raise RuntimeError("Scenario did not reach a playable M.O.T.H.E.R.")


def verify_repeated_trigger() -> None:
    """Brann must produce a second M.O.T.H.E.R. choice and discount."""
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player1_deck[:3] = ["BE_036", "CORE_LOE_077", "TLC_248"]
    player2_deck = make_simple_test_deck(player_class="PALADIN")
    game = SimulatorSession(
        player1_deck,
        player2_deck,
        player1_class="WARLOCK",
        player2_class="PALADIN",
        format="WILD",
        shuffle=False,
    )

    for _ in range(80):
        player1_state = game.observation("PLAYER1")
        active_actions = game.legal_actions()
        if player1_state.active_player == "SELF":
            brann = next((action for action in active_actions
                          if action["type"] == "PLAY_CARD"
                          and action.get("card_id") == "CORE_LOE_077"), None)
            if brann is not None:
                game.apply_action(brann)
                continue
            if player1_state.turn_number >= 9:
                mother = next((action for action in active_actions
                               if action["type"] == "PLAY_CARD"
                               and action.get("card_id") == "BE_036"), None)
                if mother is not None:
                    game.apply_action(mother)
                    if not game.needs_choice:
                        raise AssertionError("M.O.T.H.E.R. did not request its first choice")
                    for repetition in range(2):
                        choices = game.legal_actions()
                        target = next((action for action in choices
                                       if action.get("card_id") == "TLC_248"), None)
                        if target is None:
                            raise AssertionError("Expected Ultragigasaur in M.O.T.H.E.R. choices")
                        game.apply_action(target)
                        if repetition == 0 and not game.needs_choice:
                            raise AssertionError("Brann's repeated Battlecry choice was lost")
                    if game.needs_choice:
                        raise AssertionError("Repeated M.O.T.H.E.R. choices did not finish")
                    card = next(card for card in game.observation("PLAYER1").self_hand
                                if card.card_id == "TLC_248")
                    if card.cost != 1:
                        raise AssertionError(
                            f"Brann + M.O.T.H.E.R. should reduce cost 11 to 1, got {card.cost}"
                        )
                    print("PASS Brann + M.O.T.H.E.R.: two sequential choices reduce 11 cost to 1")
                    return
        end_turn = next((action for action in active_actions if action["type"] == "END_TURN"), None)
        if end_turn is None:
            raise RuntimeError("Game has no supported action while waiting for combo")
        game.apply_action(end_turn)
    raise RuntimeError("Scenario did not complete Brann + M.O.T.H.E.R.")


if __name__ == "__main__":
    main()
