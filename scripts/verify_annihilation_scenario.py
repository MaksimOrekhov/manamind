"""Verify Annihilation clears both boards and summons bottom-deck Demons."""

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
    warlock_deck[0] = "JAIL_510"
    # Deck setup reverses the list for deterministic games, making its final
    # entries the bottom cards. Put two Demons and one non-Demon there.
    warlock_deck[-3:] = ["CS3_003", "CORE_UNG_205", "CS3_003"]
    errors = validate_deck(warlock_deck, player_class="WARLOCK")
    if errors:
        raise RuntimeError("Warlock deck is invalid: " + "; ".join(errors))

    opponent_deck = make_simple_test_deck(player_class="WARRIOR")
    opponent_deck[0] = "CORE_UNG_205"
    errors = validate_deck(opponent_deck, player_class="WARRIOR")
    if errors:
        raise RuntimeError("Warrior deck is invalid: " + "; ".join(errors))

    game = SimulatorSession(
        warlock_deck,
        opponent_deck,
        player1_class="WARLOCK",
        player2_class="WARRIOR",
        shuffle=False,
        random_start=False,
        random_seed=510,
    )

    enemy_minion_played = False
    friendly_minion_played = False
    for step in range(160):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()

        if state.active_player == "SELF":
            if not friendly_minion_played:
                play_friendly = next(
                    (action for action in actions
                     if action["type"] == "PLAY_CARD"
                     and action.get("card_id") == "CORE_UNG_205"),
                    None,
                )
                if play_friendly is not None:
                    game.apply_action(play_friendly)
                    friendly_minion_played = True
                    continue

            if state.self_player.max_mana >= 8:
                play = next(
                    (action for action in actions
                     if action["type"] == "PLAY_CARD"
                     and action.get("card_id") == "JAIL_510"),
                    None,
                )
                if play is not None:
                    game.apply_action(play)
                    after = game.observation("PLAYER1")
                    demon_ids = [
                        minion.card.card_id for minion in after.self_player.board
                        if minion.card.card_id == "CS3_003"
                    ]
                    if demon_ids != ["CS3_003", "CS3_003"]:
                        raise AssertionError(
                            "Expected both Demons in the bottom three to be "
                            f"summoned once; friendly board is {after.self_player.board}"
                        )
                    if after.opponent.board:
                        raise AssertionError(
                            "Annihilation should destroy all enemy minions"
                        )
                    if len(after.self_player.board) != 2:
                        raise AssertionError(
                            "Annihilation should destroy the friendly minion and "
                            "summon exactly two Demons"
                        )
                    print(
                        "PASS JAIL_510 Annihilation: cleared both boards and "
                        "summoned only the two Demons from the bottom three",
                        flush=True,
                    )
                    return

            game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
            continue

        if not enemy_minion_played:
            play_minion = next(
                (action for action in actions
                 if action["type"] == "PLAY_CARD"
                 and action.get("card_id") == "CORE_UNG_205"),
                None,
            )
            if play_minion is not None:
                game.apply_action(play_minion)
                enemy_minion_played = True
                continue
        game.apply_action(next(a for a in actions if a["type"] == "END_TURN"))

    raise RuntimeError(
        "Scenario did not play Annihilation within 160 actions"
    )


if __name__ == "__main__":
    main()
