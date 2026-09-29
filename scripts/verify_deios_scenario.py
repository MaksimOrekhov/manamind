"""Verify Chrono-Lord Deios doubles friendly Battlecries, Deathrattles, and Hero Power."""

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


def make_game(
    player_class: str,
    deck_edits: dict[int, str],
    *,
    opponent_edits: dict[int, str] | None = None,
) -> SimulatorSession:
    player_deck = make_simple_test_deck(player_class=player_class)
    for index, card_id in deck_edits.items():
        player_deck[index] = card_id
    errors = validate_deck(player_deck, player_class=player_class)
    if errors:
        raise RuntimeError(f"{player_class} deck is invalid: " + "; ".join(errors))

    opponent_deck = make_simple_test_deck(player_class="WARRIOR")
    for index, card_id in (opponent_edits or {}).items():
        opponent_deck[index] = card_id
    errors = validate_deck(opponent_deck, player_class="WARRIOR")
    if errors:
        raise RuntimeError("Warrior deck is invalid: " + "; ".join(errors))
    return SimulatorSession(
        player_deck,
        opponent_deck,
        player1_class=player_class,
        player2_class="WARRIOR",
        shuffle=False,
        random_start=False,
        random_seed=64,
    )


def verify_battlecry() -> None:
    game = make_game("SHAMAN", {0: "TIME_064", 1: "CORE_CS2_042"})
    deios_played = False

    for step in range(180):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            if not deios_played and state.self_player.max_mana >= 7:
                action = find_action(actions, "PLAY_CARD", "TIME_064")
                if action:
                    game.apply_action(action)
                    deios_played = True
                    continue

            if deios_played and state.self_player.max_mana >= 9:
                action = next(
                    (
                        candidate for candidate in actions
                        if candidate["type"] == "PLAY_CARD"
                        and candidate.get("card_id") == "CORE_CS2_042"
                        and candidate.get("target_is_hero")
                        and not candidate.get("target_is_self")
                    ),
                    None,
                )
                if action:
                    game.apply_action(action)
                    health = game.observation("PLAYER1").opponent.hero_health
                    if health != 22:
                        raise AssertionError(
                            "Fire Elemental should deal 8 damage under Deios; "
                            f"opponent health is {health}, expected 22"
                        )
                    print("PASS TIME_064 Battlecry: Fire Elemental dealt 8 damage")
                    return

            end_turn(game, actions)
        else:
            end_turn(game, actions)

    raise RuntimeError("Battlecry scenario did not complete within 180 actions")


def verify_deathrattle() -> None:
    game = make_game(
        "WARLOCK",
        {0: "JAIL_399", 1: "TIME_064"},
        opponent_edits={0: "Core_CS2_200"},
    )
    stooge_played = False
    deios_played = False
    ogre_played = False

    for step in range(180):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            if not stooge_played and state.self_player.max_mana >= 3:
                action = find_action(actions, "PLAY_CARD", "JAIL_399")
                if action:
                    game.apply_action(action)
                    stooge_played = True
                    continue

            if stooge_played and not deios_played and state.self_player.max_mana >= 7:
                action = find_action(actions, "PLAY_CARD", "TIME_064")
                if action:
                    game.apply_action(action)
                    deios_played = True
                    continue

            end_turn(game, actions)
        else:
            if not ogre_played:
                action = find_action(actions, "PLAY_CARD", "Core_CS2_200")
                if action:
                    game.apply_action(action)
                    ogre_played = True
                    continue

            target_position = next(
                (
                    minion.board_position for minion in state.self_player.board
                    if minion.card.card_id == "JAIL_399" and minion.taunt
                ),
                None,
            )
            attack = next(
                (
                    action for action in actions
                    if action["type"] == "ATTACK"
                    and not action.get("source_is_hero")
                    and action.get("source_attack") == 6
                    and action.get("target_board_position") == target_position
                    and not action.get("target_is_self")
                ),
                None,
            )
            if attack is not None:
                deck_before = state.self_player.deck_size
                game.apply_action(attack)
                deck_after = game.observation("PLAYER1").self_player.deck_size
                if deck_after - deck_before != 4:
                    raise AssertionError(
                        "Imp Gang Stooge should add four Imps to deck when its "
                        "Deathrattle is doubled; deck size changed by "
                        f"{deck_after - deck_before}, expected 4"
                    )
                print("PASS TIME_064 Deathrattle: Imp Gang Stooge added four Imps")
                return

            end_turn(game, actions)

    raise RuntimeError("Deathrattle scenario did not complete within 180 actions")


def verify_hero_power() -> None:
    game = make_game("WARLOCK", {0: "TIME_064"})
    deios_played = False

    for step in range(180):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF":
            if not deios_played and state.self_player.max_mana >= 7:
                action = find_action(actions, "PLAY_CARD", "TIME_064")
                if action:
                    game.apply_action(action)
                    deios_played = True
                    continue

            if deios_played and state.self_player.max_mana >= 8:
                action = next(
                    (candidate for candidate in actions
                     if candidate["type"] == "HERO_POWER"),
                    None,
                )
                if action:
                    deck_before = state.self_player.deck_size
                    health_before = state.self_player.hero_health
                    game.apply_action(action)
                    after = game.observation("PLAYER1").self_player
                    if after.deck_size != deck_before - 2:
                        raise AssertionError(
                            "Life Tap under Deios should draw two cards; deck "
                            f"size {deck_before} -> {after.deck_size}"
                        )
                    if after.hero_health != health_before - 4:
                        raise AssertionError(
                            "Life Tap under Deios should deal 4 damage; health "
                            f"{health_before} -> {after.hero_health}"
                        )
                    print("PASS TIME_064 Hero Power: Life Tap drew two and dealt 4 damage")
                    return

            end_turn(game, actions)
        else:
            end_turn(game, actions)

    raise RuntimeError("Hero Power scenario did not complete within 180 actions")


def find_action(actions: list[dict], action_type: str, card_id: str) -> dict | None:
    return next(
        (
            action for action in actions
            if action["type"] == action_type and action.get("card_id") == card_id
        ),
        None,
    )


def end_turn(game: SimulatorSession, actions: list[dict]) -> None:
    action = next((candidate for candidate in actions if candidate["type"] == "END_TURN"), None)
    if action is None:
        raise RuntimeError("No end-turn action is available")
    game.apply_action(action)


def main() -> None:
    verify_battlecry()
    verify_deathrattle()
    verify_hero_power()


if __name__ == "__main__":
    main()
