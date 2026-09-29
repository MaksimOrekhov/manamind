"""Core domain types independent of any simulator or game-log source."""

from .card import CardFeatures
from .entity import BoardEntity
from .game_state import GameState, PlayerObservation
from .serialization import game_state_from_dict

__all__ = [
    "BoardEntity",
    "CardFeatures",
    "GameState",
    "PlayerObservation",
    "game_state_from_dict",
]
