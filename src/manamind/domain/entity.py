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
