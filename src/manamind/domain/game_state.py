from dataclasses import dataclass, field
from typing import Literal

from .card import CardFeatures
from .entity import BoardEntity, LocationEntity


@dataclass(frozen=True, slots=True)
class PlayerObservation:
    """Visible information about one side, expressed as SELF or OPPONENT."""

    hero_health: int
    armor: int = 0
    hero_attack: int = 0
    max_mana: int = 0
    available_mana: int = 0
    overloaded_mana: int = 0
    pending_overload: int = 0
    deck_size: int = 0
    hand_size: int = 0
    fatigue: int = 0
    hero_power_ready: bool | None = None
    player_class: str = "UNKNOWN_CLASS"
    weapon: CardFeatures | None = None
    hero_power: CardFeatures | None = None
    board: tuple[BoardEntity, ...] = field(default_factory=tuple)
    locations: tuple[LocationEntity, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in (
            "hero_health", "armor", "hero_attack", "max_mana", "available_mana",
            "overloaded_mana", "pending_overload", "deck_size", "hand_size", "fatigue",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True, slots=True)
class GameState:
    """A player-visible game position, never simulator hidden state."""

    turn_number: int
    active_player: Literal["SELF", "OPPONENT"]
    self_player: PlayerObservation
    opponent: PlayerObservation
    self_hand: tuple[CardFeatures, ...] = field(default_factory=tuple)
    self_hand_known_count: int | None = None
    opponent_known_cards: tuple[CardFeatures, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.turn_number < 0:
            raise ValueError("turn_number cannot be negative")
        if self.active_player not in ("SELF", "OPPONENT"):
            raise ValueError("active_player must be 'SELF' or 'OPPONENT'")
        if self.self_hand_known_count is not None and self.self_hand_known_count < 0:
            raise ValueError("self_hand_known_count cannot be negative")
        if (len(self.self_player.board) + len(self.self_player.locations) > 7 or
                len(self.opponent.board) + len(self.opponent.locations) > 7):
            raise ValueError("A board cannot contain more than seven entities")
        if self.self_hand_known_count is None:
            object.__setattr__(self, "self_hand_known_count", len(self.self_hand))
        if len(self.self_hand) > self.self_player.hand_size:
            raise ValueError("Known self hand cards cannot exceed self hand_size")
        if self.self_hand_known_count > self.self_player.hand_size:
            raise ValueError("self_hand_known_count cannot exceed self hand_size")
        if len(self.opponent_known_cards) > self.opponent.hand_size:
            raise ValueError("Known opponent cards cannot exceed opponent hand_size")
