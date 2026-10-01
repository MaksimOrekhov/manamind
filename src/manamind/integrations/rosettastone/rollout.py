"""Small baseline rollouts that turn completed RosettaStone matches into labels."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from manamind.domain.game_state import GameState
from manamind.integrations.rosettastone.rosettastone import (
    DeckValidationError,
    SimulatorSession,
    validate_decks,
)


@dataclass(frozen=True, slots=True)
class SimulatorExample:
    state: GameState
    target: float
    game_id: str
    sample_id: str
    perspective: str = "SELF"
    source: str = "rosettastone_baseline"


@dataclass(frozen=True, slots=True)
class BaselineGame:
    game_id: str
    result: str
    examples: tuple[SimulatorExample, ...]


def choose_baseline_action(
    state: GameState, actions: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Play the cheapest minion, otherwise take an attack, otherwise end the turn."""
    choices = [action for action in actions if action.get("type") == "CHOOSE_CARD"]
    if choices:
        # M.O.T.H.E.R. applies its largest reduction to the selected card, so
        # the simple baseline anchors the effect on the most expensive option.
        return max(choices, key=lambda action: int(action.get("card_cost", 0)))

    minion_plays = []
    for action in actions:
        if action.get("type") != "PLAY_CARD":
            continue
        hand_index = int(action["hand_index"])
        if hand_index >= len(state.self_hand):
            continue
        card = state.self_hand[hand_index]
        if card.card_type == "MINION" and len(state.self_player.board) < 7:
            minion_plays.append((card.effective_cost if card.effective_cost is not None else 99, action))
    if minion_plays:
        return min(minion_plays, key=lambda item: item[0])[1]

    attack = next((action for action in actions if action.get("type") == "ATTACK"), None)
    if attack is not None:
        return attack

    end_turn = next((action for action in actions if action.get("type") == "END_TURN"), None)
    if end_turn is not None:
        return end_turn
    raise RuntimeError("No supported baseline action is available")


def play_baseline_game(
    player1_deck: Sequence[str],
    player2_deck: Sequence[str],
    *,
    player1_class: str = "WARLOCK",
    player2_class: str = "PALADIN",
    max_actions: int = 2000,
    random_seed: int = 0,
    format: str = "STANDARD",
) -> BaselineGame:
    """Run one full seeded baseline game and label both viewpoints."""
    if max_actions < 1:
        raise ValueError("max_actions must be positive")
    deck_errors = validate_decks(
        player1_deck, player2_deck,
        player1_class=player1_class, player2_class=player2_class, format=format,
    )
    if deck_errors:
        raise DeckValidationError(deck_errors)
    session = SimulatorSession(
        player1_deck, player2_deck,
        player1_class=player1_class,
        player2_class=player2_class,
        format=format,
        shuffle=True,
        random_start=True,
        random_seed=random_seed,
    )
    game_id = f"rosetta-{uuid4().hex}"
    states: list[tuple[int, GameState, GameState]] = []

    for action_index in range(max_actions):
        if session.is_complete:
            break
        current = session.observation("ACTIVE")
        actions = session.legal_actions()
        if not actions:
            raise RuntimeError(
                f"Game stopped at action {action_index}: no supported legal action is available"
            )
        # The value-state schema does not include a pending-choice marker or
        # its options, so don't serialize this intermediate decision window.
        if not session.needs_choice:
            states.append((action_index, session.observation("PLAYER1"), session.observation("PLAYER2")))
        action = choose_baseline_action(current, actions)
        next_state = session.apply_action(action)
        if next_state == current and not session.is_complete:
            raise RuntimeError(
                f"Baseline action made no visible progress at turn {current.turn_number}: {action}"
            )
    else:
        if not session.is_complete:
            raise RuntimeError(f"Game did not finish within {max_actions} actions")

    result = session.result
    if result not in {"PLAYER1_WIN", "PLAYER2_WIN", "DRAW"}:
        raise RuntimeError(f"Completed match has unsupported result: {result!r}")

    examples: list[SimulatorExample] = []
    for action_index, player1_state, player2_state in states:
        player1_target = 0.5 if result == "DRAW" else float(result == "PLAYER1_WIN")
        player2_target = 0.5 if result == "DRAW" else float(result == "PLAYER2_WIN")
        examples.extend((
            SimulatorExample(
                state=player1_state, target=player1_target, game_id=game_id,
                sample_id=f"{game_id}-{action_index:05d}-p1",
            ),
            SimulatorExample(
                state=player2_state, target=player2_target, game_id=game_id,
                sample_id=f"{game_id}-{action_index:05d}-p2",
            ),
        ))
    return BaselineGame(game_id=game_id, result=result, examples=tuple(examples))


def save_simulator_examples(path: str | Path, examples: Sequence[SimulatorExample]) -> None:
    """Write training-loader-compatible JSONL; refuse to overwrite existing data."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        for example in examples:
            row = {
                "schema_version": 1,
                "game_id": example.game_id,
                "sample_id": example.sample_id,
                "perspective": example.perspective,
                "source": example.source,
                "state": asdict(example.state),
                "target": example.target,
            }
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play a small baseline RosettaStone match and save labeled positions."
    )
    parser.add_argument("deck_config", type=Path, help="JSON with player1_deck/player2_deck and optional classes")
    parser.add_argument("output", type=Path, help="New JSONL output path; existing files are not overwritten")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1, help="Seed for reproducible shuffled decks")
    parser.add_argument("--max-actions", type=int, default=2000)
    args = parser.parse_args()
    if args.games < 1:
        parser.error("--games must be at least 1")

    config = json.loads(args.deck_config.read_text(encoding="utf-8"))
    games = [
        play_baseline_game(
            config["player1_deck"], config["player2_deck"],
            player1_class=config.get("player1_class", "WARLOCK"),
            player2_class=config.get("player2_class", "PALADIN"),
            max_actions=args.max_actions,
            random_seed=args.seed + index,
            format=config.get("format", "STANDARD"),
        )
        for index in range(args.games)
    ]
    examples = [example for game in games for example in game.examples]
    save_simulator_examples(args.output, examples)
    summary = ", ".join(f"{game.game_id}: {game.result}" for game in games)
    print(f"Saved {len(examples)} positions from {len(games)} games to {args.output}")
    print(summary)


if __name__ == "__main__":
    main()
