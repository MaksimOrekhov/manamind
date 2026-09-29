from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CardFeatures:
    """Public, structured card properties; identity may be unknown to the catalog."""

    card_id: str = "UNKNOWN_CARD"
    cost: int | None = None
    attack: int | None = None
    health: int | None = None
    durability: int | None = None
    card_type: str = "UNKNOWN_TYPE"
    card_class: str = "UNKNOWN_CLASS"
    race: str | None = None
    mechanics: tuple[str, ...] = field(default_factory=tuple)
