from dataclasses import dataclass

from .card import CardFeatures


@dataclass(frozen=True, slots=True)
class BoardEntity:
    """A card on the board with current, possibly modified, game values."""

    card: CardFeatures
    current_attack: int
    current_health: int
    max_health: int
    board_position: int
    taunt: bool = False
    divine_shield: bool = False
    stealth: bool = False
    frozen: bool = False
    silenced: bool = False
    immune: bool = False
    rush: bool = False
    charge: bool = False
    windfury: bool = False
    lifesteal: bool = False
    poisonous: bool = False
    reborn: bool = False
    dormant: bool = False
    can_attack: bool = False
    cant_be_targeted_by_spells: bool | None = None
    cant_be_targeted_by_hero_powers: bool | None = None


@dataclass(frozen=True, slots=True)
class LocationEntity:
    """A Location on the shared board, with visible durability and activation state."""

    card: CardFeatures
    current_health: int
    max_health: int
    board_position: int
    on_cooldown: bool = False
    can_activate: bool | None = None
