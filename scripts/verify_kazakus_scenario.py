"""Exercise Godfather Kazakus' chained trial choices and generated trials."""

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


def start_game_with_kazakus(random_seed: int = 0) -> SimulatorSession:
    player1_deck = make_simple_test_deck(player_class="WARLOCK")
    player1_deck[0] = "CAP_405"
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
        random_seed=random_seed,
    )
    for _ in range(40):
        state = game.observation("PLAYER1")
        if state.active_player == "SELF" and state.turn_number >= 3:
            action = next(
                (
                    action
                    for action in game.legal_actions()
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "CAP_405"
                ),
                None,
            )
            if action is not None:
                game.apply_action(action)
                if not game.needs_choice:
                    raise AssertionError("Kazakus should start its first trial choice")
                return game
        game.apply_action(
            next(action for action in game.legal_actions() if action["type"] == "END_TURN")
        )
    raise AssertionError("Could not play Kazakus during the scenario")


def choose_trial_effects(game: SimulatorSession) -> bool:
    first_choices = game.legal_actions()
    if len(first_choices) != 3:
        raise AssertionError(f"Expected 3 first effect options, got {first_choices}")
    first = next(
        (choice for choice in first_choices if choice["card_id"] == "MANA_KAZAKUS_EFFECT_3"),
        first_choices[0],
    )
    game.apply_action(first)

    second_choices = game.legal_actions()
    if len(second_choices) != 3:
        raise AssertionError(f"Expected 3 second effect options, got {second_choices}")
    if first["card_id"] in {choice["card_id"] for choice in second_choices}:
        raise AssertionError("The second effect choice must exclude the first effect")
    second = next(
        (choice for choice in second_choices if choice["card_id"] == "MANA_KAZAKUS_EFFECT_3"),
        second_choices[0],
    )
    game.apply_action(second)
    return "MANA_KAZAKUS_EFFECT_3" in {first["card_id"], second["card_id"]}


def choose_length(game: SimulatorSession, length: int) -> None:
    choices = game.legal_actions()
    selected = next(
        (choice for choice in choices
         if choice["card_id"] == f"MANA_KAZAKUS_LENGTH_{length}"),
        None,
    )
    if selected is None or len(choices) != 3:
        raise AssertionError(f"Expected three trial lengths including {length}: {choices}")
    game.apply_action(selected)


def verify_rushed_trial() -> None:
    game = start_game_with_kazakus()
    choose_trial_effects(game)
    choose_length(game, 7)

    trial_cards = [
        card
        for card in game.observation("PLAYER1").self_hand
        if card.card_id == "MANA_KAZAKUS_TRIAL"
    ]
    if len(trial_cards) != 1 or trial_cards[0].effective_cost != 7:
        raise AssertionError(
            "Rushed Trial should create a 7-cost custom spell in hand; "
            f"found {[(card.card_id, card.effective_cost) for card in trial_cards]}"
        )

    trial_played = False
    for _ in range(60):
        state = game.observation("PLAYER1")
        if state.active_player == "SELF" and state.turn_number >= 7:
            action = next(
                (
                    action
                    for action in game.legal_actions()
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") == "MANA_KAZAKUS_TRIAL"
                ),
                None,
            )
            if action is not None:
                game.apply_action(action)
                trial_played = True
                break
        game.apply_action(
            next(action for action in game.legal_actions() if action["type"] == "END_TURN")
        )
    if not trial_played:
        raise AssertionError("The 7-cost custom Kazakus spell should be playable")
    print("PASS CAP_405 Godfather Kazakus: Rushed Trial creates and casts a 7-cost spell")


def verify_grueling_trial() -> None:
    game = start_game_with_kazakus(random_seed=1)
    includes_draw = choose_trial_effects(game)
    if not includes_draw:
        raise AssertionError("The deterministic scenario should select Crate of Contraband")
    turn_when_plotted = game.observation("PLAYER1").turn_number
    choose_length(game, 4)
    hand_size_before = len(game.observation("PLAYER1").self_hand)
    if any(card.card_id == "MANA_KAZAKUS_TRIAL"
           for card in game.observation("PLAYER1").self_hand):
        raise AssertionError("Grueling Trial should resolve from its timer, not hand")

    for _ in range(8):
        state = game.observation("PLAYER1")
        if state.active_player == "SELF" and state.turn_number > turn_when_plotted:
            if includes_draw and len(state.self_hand) != hand_size_before + 4:
                raise AssertionError(
                    "A delayed Crate of Contraband should draw 3 in addition to the turn draw; "
                    f"hand size was {hand_size_before}, now {len(state.self_hand)}"
                )
            print("PASS CAP_405 Godfather Kazakus: Grueling Trial resolves next own turn")
            return
        game.apply_action(
            next(action for action in game.legal_actions() if action["type"] == "END_TURN")
        )
    raise AssertionError("Grueling Trial did not reach its scheduled own turn")


def verify_unending_trial() -> None:
    game = start_game_with_kazakus(random_seed=1)
    includes_draw = choose_trial_effects(game)
    if not includes_draw:
        raise AssertionError("The deterministic scenario should select Crate of Contraband")
    turn_when_plotted = game.observation("PLAYER1").turn_number
    choose_length(game, 0)
    initial_hand_size = len(game.observation("PLAYER1").self_hand)
    own_turn_starts = 0

    for _ in range(24):
        state = game.observation("PLAYER1")
        if state.active_player == "SELF" and state.turn_number > turn_when_plotted:
            own_turn_starts += 1
            if includes_draw:
                expected_hand_size = min(
                    10,
                    initial_hand_size
                    + own_turn_starts
                    + (3 if own_turn_starts >= 4 else 0),
                )
                if len(state.self_hand) != expected_hand_size:
                    raise AssertionError(
                        "Unending Trial should wait through three own turns and resolve "
                        f"at the fourth; expected hand size {expected_hand_size}, "
                        f"got {len(state.self_hand)}"
                    )
            if own_turn_starts == 4:
                print("PASS CAP_405 Godfather Kazakus: Unending Trial resolves after four own turns")
                return
        game.apply_action(
            next(action for action in game.legal_actions() if action["type"] == "END_TURN")
        )
    raise AssertionError("Unending Trial did not reach its fourth scheduled own turn")


def main() -> None:
    verify_rushed_trial()
    verify_grueling_trial()
    verify_unending_trial()
    verify_spurious_shiv_steals_cards()


def verify_spurious_shiv_steals_cards() -> None:
    game = None
    for seed in range(100):
        candidate = start_game_with_kazakus(random_seed=seed)
        effects = candidate.legal_actions()
        first = next(
            (choice for choice in effects
             if choice.get("card_id") == "MANA_KAZAKUS_EFFECT_8"),
            None,
        )
        if first is None:
            continue
        game = candidate
        game.apply_action(first)
        second = game.legal_actions()[0]
        game.apply_action(second)
        choose_length(game, 7)
        break

    if game is None:
        raise AssertionError("Could not find a Kazakus choice containing Spurious Shiv")

    for _ in range(120):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        if state.active_player == "SELF" and state.self_player.max_mana >= 7:
            trial = next(
                (action for action in actions
                 if action["type"] == "PLAY_CARD"
                 and action.get("card_id") == "MANA_KAZAKUS_TRIAL"),
                None,
            )
            if trial is not None:
                own_hand_before = len(state.self_hand)
                opponent_hand_before = state.opponent.hand_size
                game.apply_action(trial)
                after = game.observation("PLAYER1")
                stolen_count = min(2, opponent_hand_before)
                expected_own_hand = min(10, own_hand_before - 1 + stolen_count)
                if after.opponent.hand_size != opponent_hand_before - stolen_count:
                    raise AssertionError(
                        "Spurious Shiv should remove up to two cards from the "
                        f"opponent's hand: {opponent_hand_before} -> "
                        f"{after.opponent.hand_size}"
                    )
                if len(after.self_hand) != expected_own_hand:
                    raise AssertionError(
                        "Spurious Shiv should transfer the stolen cards into "
                        f"the player's hand: expected {expected_own_hand}, got "
                        f"{len(after.self_hand)}"
                    )
                print(
                    "PASS CAP_405 Spurious Shiv: transferred "
                    f"{stolen_count} opponent cards into the player's hand"
                )
                return
        game.apply_action(
            next(action for action in actions if action["type"] == "END_TURN")
        )

    raise AssertionError("Spurious Shiv did not become playable")


if __name__ == "__main__":
    main()
