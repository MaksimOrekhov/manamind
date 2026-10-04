"""Encode cards and board entities into fixed-width NumPy arrays."""

from dataclasses import dataclass

import numpy as np

from manamind.cards.catalog import CardCatalog
from manamind.cards.vocabulary import CardVocabulary
from manamind.domain.card import CardFeatures
from manamind.domain.dark_gift import DARK_GIFT_OPTION_IDS, dark_gift_counts
from manamind.domain.entity import BoardEntity, LocationEntity

NUMERIC_FEATURES = (
    "base_cost",
    "base_attack",
    "base_health",
    "base_durability",
    "current_attack",
    "current_health",
    "max_health",
    "zone_position",
    "current_cost",
    "current_durability",
    "current_spell_damage",
    "prepare_used",
    "held_spell_progress",
    "trigger_remaining",
    "effect_turns_remaining",
    "freeze_turns_remaining",
    *(f"dark_gift_{gift_id}" for gift_id in DARK_GIFT_OPTION_IDS),
)

PRESENCE_FEATURES = tuple(f"has_{name}" for name in NUMERIC_FEATURES)

STATE_FLAG_NAMES = (
    "taunt",
    "divine_shield",
    "stealth",
    "frozen",
    "silenced",
    "immune",
    "rush",
    "charge",
    "windfury",
    "lifesteal",
    "poisonous",
    "reborn",
    "dormant",
    "can_attack",
    "on_cooldown",
    "can_activate",
    "can_activate_known",
    "cant_be_targeted_by_spells",
    "cant_be_targeted_by_spells_known",
    "cant_be_targeted_by_hero_powers",
    "cant_be_targeted_by_hero_powers_known",
)

NUMERIC_LIMIT = 10_000.0
NORMALIZATION_CONFIG = {"version": 1, "method": "signed_log1p", "clip": NUMERIC_LIMIT}


def _normalise(value: float | None) -> float:
    """Log-scale large card values while preserving sign and handling missing data."""
    if value is None:
        return 0.0
    clipped = max(-NUMERIC_LIMIT, min(NUMERIC_LIMIT, float(value)))
    return float(np.sign(clipped) * np.log1p(abs(clipped)) / np.log1p(NUMERIC_LIMIT))


@dataclass(frozen=True, slots=True)
class EncodedZone:
    """One variable-length zone, ready for padding and batching later."""

    card_ids: np.ndarray
    card_type_ids: np.ndarray
    card_class_ids: np.ndarray
    race_ids: np.ndarray
    mechanics: np.ndarray
    numeric: np.ndarray
    numeric_present: np.ndarray
    state_flags: np.ndarray
    hand_semantic_features: np.ndarray

    @property
    def size(self) -> int:
        return int(self.card_ids.shape[0])


@dataclass(frozen=True, slots=True)
class _EntityInput:
    card: CardFeatures
    board_entity: BoardEntity | None = None
    location_entity: LocationEntity | None = None
    zone_position: int | None = None


class EntityEncoder:
    """Encode card identity and properties, including safe unknown-card inputs."""

    def __init__(self, catalog: CardCatalog, vocabulary: CardVocabulary) -> None:
        self.catalog = catalog
        self.vocabulary = vocabulary

    def encode_zone(
        self, cards: tuple[CardFeatures, ...], *, ordered: bool = False
    ) -> EncodedZone:
        """Encode ordered zones with visible positions when requested."""
        return self.encode_entities(tuple(
            _EntityInput(card, zone_position=index if ordered else None)
            for index, card in enumerate(cards)
        ))

    def encode_board(self, entities: tuple[BoardEntity, ...]) -> EncodedZone:
        """Encode board entities with current stats and status flags."""
        return self.encode_entities(
            tuple(_EntityInput(entity.card, entity) for entity in entities)
        )

    def encode_locations(self, entities: tuple[LocationEntity, ...]) -> EncodedZone:
        return self.encode_entities(tuple(
            _EntityInput(entity.card, location_entity=entity) for entity in entities
        ))

    def encode_optional_card(self, card: CardFeatures | None) -> EncodedZone:
        """Encode a weapon or hero power as a one-item zone, or as an empty zone."""
        return self.encode_entities((_EntityInput(card),)) if card else self.empty_zone()

    def empty_zone(self) -> EncodedZone:
        """Return correctly shaped arrays for an empty collection."""
        return EncodedZone(
            card_ids=np.zeros((0,), dtype=np.int64),
            card_type_ids=np.zeros((0,), dtype=np.int64),
            card_class_ids=np.zeros((0,), dtype=np.int64),
            race_ids=np.zeros((0,), dtype=np.int64),
            mechanics=np.zeros((0, self.vocabulary.mechanics_count), dtype=np.float32),
            numeric=np.zeros((0, len(NUMERIC_FEATURES)), dtype=np.float32),
            numeric_present=np.zeros((0, len(PRESENCE_FEATURES)), dtype=np.float32),
            state_flags=np.zeros((0, len(STATE_FLAG_NAMES)), dtype=np.float32),
            hand_semantic_features=np.zeros((0, 6), dtype=np.float32),
        )

    def encode_entities(self, entities: tuple[_EntityInput, ...]) -> EncodedZone:
        if not entities:
            return self.empty_zone()

        count = len(entities)
        card_ids = np.zeros((count,), dtype=np.int64)
        card_type_ids = np.zeros((count,), dtype=np.int64)
        card_class_ids = np.zeros((count,), dtype=np.int64)
        race_ids = np.zeros((count,), dtype=np.int64)
        mechanics = np.zeros((count, self.vocabulary.mechanics_count), dtype=np.float32)
        numeric = np.zeros((count, len(NUMERIC_FEATURES)), dtype=np.float32)
        numeric_present = np.zeros((count, len(PRESENCE_FEATURES)), dtype=np.float32)
        state_flags = np.zeros((count, len(STATE_FLAG_NAMES)), dtype=np.float32)
        hand_semantic_features = np.zeros((count, 6), dtype=np.float32)

        for row, item in enumerate(entities):
            card = self.catalog.enrich(item.card)
            if item.zone_position is not None and card.shatter_fragment:
                role = card.shatter_fragment.upper()
                role_column = {"LEFT": 0, "RIGHT": 1, "SOLO": 2}.get(role)
                if role_column is None:
                    raise ValueError(f"Unknown Shatter fragment role: {card.shatter_fragment}")
                hand_semantic_features[row, role_column] = 1.0
                if card.shatter_partner_hand_position is not None:
                    hand_semantic_features[row, 3] = _normalise(
                        card.shatter_partner_hand_position - item.zone_position
                    )
            if item.zone_position is not None and card.prepare_locked is not None:
                hand_semantic_features[row, 4] = float(card.prepare_locked)
                hand_semantic_features[row, 5] = 1.0
            # A fragment is the source card plus an explicit Shatter role. This
            # keeps generated fragment IDs out of the collectible vocabulary.
            model_card_id = card.shatter_original_card_id or card.card_id
            card_ids[row] = self.vocabulary.card_id(model_card_id)
            card_type_ids[row] = self.vocabulary.card_type(card.card_type)
            card_class_ids[row] = self.vocabulary.card_class(card.card_class)
            race_ids[row] = self.vocabulary.race(card.race)

            base_values = (card.cost, card.attack, card.health, card.durability)
            for column, value in enumerate(base_values):
                numeric[row, column] = _normalise(value)
                numeric_present[row, column] = float(value is not None)

            for mechanic_index in self.vocabulary.mechanics(card.mechanics):
                mechanics[row, mechanic_index] = 1.0

            for name in ("current_cost", "current_attack", "current_health", "current_durability", "current_spell_damage", "prepare_used", "held_spell_progress", "trigger_remaining", "effect_turns_remaining", "freeze_turns_remaining"):
                column = NUMERIC_FEATURES.index(name)
                value = getattr(card, name)
                numeric[row, column] = _normalise(value)
                numeric_present[row, column] = float(value is not None)

            if card.dark_gifts is not None:
                for gift_id, count in zip(DARK_GIFT_OPTION_IDS, dark_gift_counts(card.dark_gifts)):
                    column = NUMERIC_FEATURES.index(f"dark_gift_{gift_id}")
                    numeric[row, column] = _normalise(count)
                    numeric_present[row, column] = 1.0

            entity = item.board_entity
            location = item.location_entity
            if location is not None:
                state_values = (
                    0,
                    location.current_health,
                    location.max_health,
                    location.board_position,
                )
                for offset, value in enumerate(state_values, start=4):
                    numeric[row, offset] = _normalise(value)
                    numeric_present[row, offset] = 1.0
                state_flags[row, STATE_FLAG_NAMES.index("on_cooldown")] = float(location.on_cooldown)
                if location.can_activate is not None:
                    state_flags[row, STATE_FLAG_NAMES.index("can_activate")] = float(location.can_activate)
                    state_flags[row, STATE_FLAG_NAMES.index("can_activate_known")] = 1.0
            elif entity is not None:
                state_values = (
                    entity.current_attack,
                    entity.current_health,
                    entity.max_health,
                    entity.board_position,
                )
                for offset, value in enumerate(state_values, start=4):
                    numeric[row, offset] = _normalise(value)
                    numeric_present[row, offset] = 1.0
                for column, flag_name in enumerate(STATE_FLAG_NAMES):
                    value = getattr(entity, flag_name, False)
                    state_flags[row, column] = float(value) if value is not None else 0.0
                for name in ("cant_be_targeted_by_spells", "cant_be_targeted_by_hero_powers"):
                    state_flags[row, STATE_FLAG_NAMES.index(name + "_known")] = float(getattr(entity, name) is not None)
            elif item.zone_position is not None:
                numeric[row, 7] = _normalise(item.zone_position)
                numeric_present[row, 7] = 1.0

        return EncodedZone(
            card_ids=card_ids,
            card_type_ids=card_type_ids,
            card_class_ids=card_class_ids,
            race_ids=race_ids,
            mechanics=mechanics,
            numeric=numeric,
            numeric_present=numeric_present,
            state_flags=state_flags,
            hand_semantic_features=hand_semantic_features,
        )

