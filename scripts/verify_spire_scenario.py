"""Verify Spire of Solitude summons and forces its Demon to attack."""

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
    warlock_deck[0] = "JAIL_511"
    errors = validate_deck(warlock_deck, player_class="WARLOCK")
    if errors:
        raise RuntimeError("Warlock deck is invalid: " + "; ".join(errors))

    warrior_deck = make_simple_test_deck(player_class="WARRIOR")
    warrior_deck[0] = "CORE_UNG_205"  # Glacial Shard: controlled enemy minion.
    errors = validate_deck(warrior_deck, player_class="WARRIOR")
    if errors:
        raise RuntimeError("Warrior deck is invalid: " + "; ".join(errors))

    game = SimulatorSession(
        warlock_deck,
        warrior_deck,
        player1_class="WARLOCK",
        player2_class="WARRIOR",
        shuffle=False,
        random_start=False,
        random_seed=511,
    )

    location_played = False
    enemy_minion_played = False
    for step in range(100):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()

        if state.active_player == "SELF":
            if not location_played:
                play_spire = next(
                    (
                        action for action in actions
                        if action["type"] == "PLAY_CARD"
                        and action.get("card_id") == "JAIL_511"
                    ),
                    None,
                )
                if play_spire is not None:
                    game.apply_action(play_spire)
                    location_played = True
                    continue

            if location_played:
                activate = next(
                    (
                        action for action in actions
                        if action["type"] == "ACTIVATE_LOCATION"
                        and action.get("card_id") == "JAIL_511"
                    ),
                    None,
                )
                if activate is not None:
                    expected_stats = state.self_player.hand_size
                    game.apply_action(activate)
                    after = game.observation("PLAYER1")
                    demon = next(
                        (
                            minion for minion in after.self_player.board
                            if minion.card.card_id == "JAIL_511t"
                        ),
                        None,
                    )
                    if demon is None:
                        raise AssertionError("Spire did not summon Shivarra Infiltrator")
                    if (
                        demon.current_attack != expected_stats
                        or demon.max_health != expected_stats
                    ):
                        raise AssertionError(
                            "Summoned Demon stats should equal hand size at activation; "
                            f"expected {expected_stats}/{expected_stats}, got "
                            f"{demon.current_attack}/{demon.max_health}"
                        )
                    if any(
                        minion.card.card_id == "CORE_UNG_205"
                        for minion in after.opponent.board
                    ):
                        raise AssertionError(
                            "The summoned Demon should attack the only enemy minion"
                        )
                    print(
                        "PASS JAIL_511 Spire of Solitude: summoned a Demon matching "
                        "hand size and it attacked the only enemy minion",
                        flush=True,
                    )
                    return

            if not any(action["type"] == "END_TURN" for action in actions):
                raise RuntimeError(f"No end-turn action at step {step}: {state}")
            game.apply_action(next(action for action in actions if action["type"] == "END_TURN"))
            continue

        if not enemy_minion_played:
            play_enemy_minion = next(
                (
                    action for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "CORE_UNG_205"
                ),
                None,
            )
            if play_enemy_minion is not None:
                game.apply_action(play_enemy_minion)
                enemy_minion_played = True
                continue
        game.apply_action(next(action for action in actions if action["type"] == "END_TURN"))

    raise RuntimeError(
        "Scenario did not play and activate Spire of Solitude within 100 actions"
    )


if __name__ == "__main__":
    main()
