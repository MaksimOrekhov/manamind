from dataclasses import dataclass, field
from typing import Literal

from .card import CardFeatures
from .entity import BoardEntity, LocationEntity

EVIDENCE_CONSTRAINT_IDS = frozenset({
    "DARK_GIFT_SAMPLER_UNVERIFIED",
    "DARK_GIFT_RUNTIME_MEMBERSHIP_UNRESOLVED",
    "REBORN_MULTI_DEATH_SLOT_UNVERIFIED",
    "MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED",
    "ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED",
    "FIRE_POOL_MEMBERSHIP_INFERRED",
})

MINION_HISTORY_TYPES = (
    "BEAST", "DEMON", "DRAENEI", "DRAGON", "ELEMENTAL", "MECHANICAL",
    "MURLOC", "NAGA", "PIRATE", "QUILBOAR", "TOTEM", "UNDEAD",
)


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
    secret_count: int = 0
    spell_damage: int = 0
    known_secrets: tuple[CardFeatures, ...] = field(default_factory=tuple)
    hero_power_ready: bool | None = None
    hero_frozen: bool | None = None
    player_class: str = "UNKNOWN_CLASS"
    weapon: CardFeatures | None = None
    hero_power: CardFeatures | None = None
    board: tuple[BoardEntity, ...] = field(default_factory=tuple)
    locations: tuple[LocationEntity, ...] = field(default_factory=tuple)
    hero_divine_shield: bool | None = None
    spells_cast_this_turn: int | None = None
    spell_discount: int | None = None
    demon_discount: int | None = None
    hero_freeze_turns_remaining: int | None = None
    active_effects: tuple[CardFeatures, ...] = field(default_factory=tuple)
    current_turn_minion_types_played: tuple[str, ...] | None = None
    previous_turn_minion_types_played: tuple[str, ...] | None = None
    # Persistent additive bonus to this side's healing effects (public enchantment on the player).
    # None means unknown (historical imports); 0 is a known "no bonus". Not an encoder feature, so
    # existing Policy/Value checkpoints and STATE_ENCODING_SCHEMA_VERSION are unchanged.
    healing_bonus: int | None = None

    def __post_init__(self) -> None:
        if self.healing_bonus is not None and (
                isinstance(self.healing_bonus, bool) or not isinstance(self.healing_bonus, int) or self.healing_bonus < 0):
            raise ValueError("healing_bonus must be None or a non-negative integer")
        for name in ("current_turn_minion_types_played", "previous_turn_minion_types_played"):
            history = getattr(self, name)
            if history is not None:
                if isinstance(history, str) or any(value not in MINION_HISTORY_TYPES for value in history):
                    raise ValueError(f"Invalid minion type history: {name}")
                object.__setattr__(self, name, tuple(sorted(set(history))))
        for name in (
            "hero_health", "armor", "hero_attack", "max_mana", "available_mana",
            "overloaded_mana", "pending_overload", "deck_size", "hand_size", "fatigue", "secret_count", "spell_damage",
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
    pending_choice_owner: Literal["SELF", "OPPONENT"] | None = None
    pending_choice_options: tuple[CardFeatures, ...] = field(default_factory=tuple)
    evidence_constraints: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.turn_number < 0:
            raise ValueError("turn_number cannot be negative")
        if isinstance(self.evidence_constraints, str):
            raise ValueError("evidence_constraints must be a collection of known constraint IDs")
        unknown_constraints = set(self.evidence_constraints) - EVIDENCE_CONSTRAINT_IDS
        if unknown_constraints:
            raise ValueError(f"Unknown evidence constraints: {sorted(unknown_constraints)}")
        object.__setattr__(self, "evidence_constraints", tuple(sorted(set(self.evidence_constraints))))
        if self.pending_choice_owner not in (None, "SELF", "OPPONENT"):
            raise ValueError("Invalid pending choice owner")
        if self.pending_choice_options and self.pending_choice_owner != "SELF":
            raise ValueError("Only SELF pending choice identities may be exposed")
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
        if len(self.opponent.known_secrets) > 0:
            raise ValueError("Opponent Secret identities must remain hidden")
        if len(self.self_player.known_secrets) > self.self_player.secret_count:
            raise ValueError("Known self Secrets cannot exceed the active Secret count")
        for position, card in enumerate(self.self_hand):
            role = card.shatter_fragment
            if role is None:
                if card.shatter_partner_hand_position is not None or card.shatter_original_card_id is not None:
                    raise ValueError("Unshattered hand cards cannot expose Shatter link fields")
                continue
            role = role.upper()
            if role not in ("LEFT", "RIGHT", "SOLO") or not card.shatter_original_card_id:
                raise ValueError("Shatter hand cards require a valid role and original card ID")
            partner_position = card.shatter_partner_hand_position
            if role == "SOLO":
                if partner_position is not None:
                    raise ValueError("Solo Shatter fragments cannot expose a partner position")
                continue
            if partner_position is None or not 0 <= partner_position < len(self.self_hand):
                raise ValueError("Linked Shatter fragments require a valid partner position")
            partner = self.self_hand[partner_position]
            expected_role = "RIGHT" if role == "LEFT" else "LEFT"
            if (partner.shatter_fragment != expected_role or
                    partner.shatter_original_card_id != card.shatter_original_card_id or
                    partner.shatter_partner_hand_position != position):
                raise ValueError("Shatter partner positions and roles must be reciprocal")
