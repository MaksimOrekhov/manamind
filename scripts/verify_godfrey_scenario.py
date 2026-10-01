"""Verify Godfrey's deferred overdraw returns and one-mana discount."""

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
    deck = make_simple_test_deck(player_class="WARLOCK")
    deck[0] = "JAIL_509"  # Start of Game activates Godfrey from the deck.
    deck[4] = "JAIL_514"  # Draw 3 at full hand.
    deck[11] = "Core_CS2_200"
    deck[12] = "Core_CS2_200"
    errors = validate_deck(deck, player_class="WARLOCK")
    if errors:
        raise RuntimeError("Test deck is invalid: " + "; ".join(errors))

    opponent_deck = make_simple_test_deck(player_class="WARRIOR")
    game = SimulatorSession(
        deck,
        opponent_deck,
        player1_class="WARLOCK",
        player2_class="WARRIOR",
        shuffle=False,
    )

    atlas_played = False
    followup_played = False
    for _ in range(80):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()

        if (
            state.active_player == "SELF"
            and not atlas_played
            and state.self_player.hand_size == 10
        ):
            play_atlas = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "JAIL_514"
                ),
                None,
            )
            if play_atlas is not None:
                game.apply_action(play_atlas)
                atlas_played = True
                continue

        if state.active_player == "SELF" and atlas_played and not followup_played:
            play_anything = next(
                (
                    action
                    for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") != "JAIL_514"
                ),
                None,
            )
            if play_anything is not None:
                game.apply_action(play_anything)
                after = game.observation("PLAYER1")
                discounted_overdrawn = [
                    card
                    for card in after.self_hand
                    if card.card_id == "Core_CS2_200" and card.effective_cost == 5
                ]
                if after.self_player.hand_size != 10:
                    raise AssertionError(
                        "An overdrawn card should return after the follow-up play; "
                        f"hand size is {after.self_player.hand_size}, expected 10"
                    )
                if not discounted_overdrawn:
                    raise AssertionError(
                        "A returned Boulderfist Ogre should cost 5 instead of 6"
                    )
                print(
                    "PASS JAIL_509 Godfrey the Betrayer: overdrawn card returned "
                    "when hand space opened, at one less cost",
                    flush=True,
                )
                followup_played = True
                return

        end_turn = next(
            (action for action in actions if action["type"] == "END_TURN"), None
        )
        if end_turn is None:
            raise RuntimeError(
                f"No action at iteration {_}: state={state}, "
                f"needs_choice={game.needs_choice}, complete={game.is_complete}, "
                f"atlas_played={atlas_played}, followup_played={followup_played}"
            )
        game.apply_action(end_turn)

    raise RuntimeError(
        "Scenario did not fill the hand, play The Unseen Atlas, and return an "
        "overdrawn card"
    )


if __name__ == "__main__":
    main()
