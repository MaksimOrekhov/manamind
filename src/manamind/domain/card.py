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
    current_cost: int | None = None
    current_attack: int | None = None
    current_health: int | None = None
    current_durability: int | None = None
    shatter_fragment: str | None = None
    shatter_original_card_id: str | None = None
    shatter_partner_hand_position: int | None = None
    prepare_locked: bool | None = None

    @property
    def effective_cost(self) -> int | None:
        return self.cost if self.current_cost is None else self.current_cost

    @property
    def effective_attack(self) -> int | None:
        return self.attack if self.current_attack is None else self.current_attack

    @property
    def effective_durability(self) -> int | None:
        return self.durability if self.current_durability is None else self.current_durability
