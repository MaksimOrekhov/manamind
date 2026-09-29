"""Adapter from the native RosettaStone bridge to ManaMind's GameState."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

from manamind.domain.game_state import GameState
from manamind.domain.serialization import game_state_from_dict

_BRIDGE: ModuleType | None = None


def _load_bridge() -> ModuleType:
    global _BRIDGE
    if _BRIDGE is not None:
        return _BRIDGE

    project_root = Path(__file__).resolve().parents[4]
    bridge_root = project_root / "integrations" / "rosettastone"
    bridge_dirs = (
        bridge_root / "build" / "python",
        bridge_root / "build-alt" / "python",
        bridge_root / "build-alt2" / "python",
        bridge_root / "build-alt3" / "python",
    )
    candidates = sorted(
        (candidate for directory in bridge_dirs
         for candidate in directory.glob("mana_rosetta_bridge*.pyd")),
        key=lambda candidate: candidate.stat().st_mtime,
    )
    if not candidates:
        raise RuntimeError(
            "ManaMind's RosettaStone bridge is not built. "
            "See docs/ROSETTASTONE_INTEGRATION.md for the build command."
        )

    spec = importlib.util.spec_from_file_location("mana_rosetta_bridge", candidates[-1])
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load native bridge from {candidates[-1]}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _BRIDGE = module
    return module


def make_sample_game_state() -> GameState:
    """Create a deterministic sample match and return SELF's visible position."""
    raw_observation = _load_bridge().make_sample_observation()
    return game_state_from_dict(raw_observation)


class SimulatorSession:
    """Persistent RosettaStone match with player-visible observations.

    Actions must be selected from ``legal_actions()`` for the current position.
    The session rejects stale or unsupported actions.
    """

    def __init__(
        self,
        player1_deck: Sequence[str],
        player2_deck: Sequence[str],
        *,
        player1_class: str = "WARLOCK",
        player2_class: str = "PALADIN",
        format: str = "STANDARD",
        shuffle: bool = False,
        random_start: bool = False,
        random_seed: int = 0,
    ) -> None:
        if not 0 <= random_seed <= 0xFFFFFFFF:
            raise ValueError("random_seed must be between 0 and 2**32 - 1")
        self._native = _load_bridge().SimulatorSession(
            list(player1_deck), list(player2_deck), player1_class, player2_class,
            format, shuffle, random_start, random_seed,
        )

    def observation(self, perspective: str = "ACTIVE") -> GameState:
        """Return the current state as seen by ACTIVE, PLAYER1, or PLAYER2."""
        return game_state_from_dict(self._native.observation(perspective))

    def legal_actions(self) -> tuple[dict[str, Any], ...]:
        """Return supported legal actions for the player whose turn it is."""
        return tuple(dict(action) for action in self._native.legal_actions())

    def apply_action(self, action: dict[str, Any]) -> GameState:
        """Apply a currently legal action and return the next active view."""
        return game_state_from_dict(self._native.apply_action(action))

    @property
    def is_complete(self) -> bool:
        """Whether RosettaStone has ended the match."""
        return self._native.is_complete()

    @property
    def needs_choice(self) -> bool:
        """Whether the engine is waiting for a card choice before continuing."""
        return self._native.needs_choice()

    @property
    def result(self) -> str | None:
        """Match result: PLAYER1_WIN, PLAYER2_WIN, DRAW, or None while running."""
        return self._native.result()


class DeckValidationError(ValueError):
    """A deck contains one or more violations reported by RosettaStone."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


def validate_deck(
    deck: Sequence[str], *, player_class: str, format: str = "STANDARD"
) -> tuple[str, ...]:
    """Return all deck legality issues according to this RosettaStone revision."""
    return tuple(_load_bridge().validate_deck(list(deck), player_class, format))


def make_simple_test_deck(
    *, player_class: str, format: str = "STANDARD"
) -> list[str]:
    """Build a legal 30-card deck from low-cost collectible minions in the engine pool."""
    candidates = _load_bridge().list_deck_candidates(player_class, format)
    candidates = sorted(candidates, key=lambda item: (item["cost"], item["card_id"]))
    deck: list[str] = []
    seen_dbf_ids: set[int] = set()
    for card in candidates:
        dbf_id = int(card["dbf_id"])
        if dbf_id in seen_dbf_ids:
            continue
        seen_dbf_ids.add(dbf_id)
        deck.extend([str(card["card_id"])] * int(card["max_copies"]))
        if len(deck) >= 30:
            break
    deck = deck[:30]
    errors = validate_deck(deck, player_class=player_class, format=format)
    if errors:
        raise DeckValidationError(errors)
    return deck


def validate_decks(
    player1_deck: Sequence[str],
    player2_deck: Sequence[str],
    *,
    player1_class: str = "WARLOCK",
    player2_class: str = "PALADIN",
    format: str = "STANDARD",
) -> tuple[str, ...]:
    """Validate both decks and prefix any issues with the owning player."""
    errors = [
        f"Player 1: {message}"
        for message in validate_deck(player1_deck, player_class=player1_class, format=format)
    ]
    errors.extend(
        f"Player 2: {message}"
        for message in validate_deck(player2_deck, player_class=player2_class, format=format)
    )
    return tuple(errors)


def inspect_decks(
    player1_deck: Sequence[str],
    player2_deck: Sequence[str],
    *,
    player1_class: str = "WARLOCK",
    player2_class: str = "PALADIN",
) -> tuple[GameState, tuple[dict[str, Any], ...]]:
    """Create a deterministic opening state and enumerate supported legal actions.

    Both decks must contain exactly 30 card IDs known to RosettaStone. The
    simulator does not currently validate deck-building rules such as copy limits.
    """
    result = _load_bridge().inspect_decks(
        list(player1_deck),
        list(player2_deck),
        player1_class,
        player2_class,
    )
    state = game_state_from_dict(result["state"])
    return state, tuple(dict(action) for action in result["legal_actions"])

if __name__ == "__main__":
    from dataclasses import asdict
    import json

    print(json.dumps(asdict(make_sample_game_state()), indent=2))
