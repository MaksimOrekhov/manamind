"""Load and look up structured Hearthstone card data."""

import json
from pathlib import Path
from typing import Any

from manamind.domain.card import CardFeatures


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any, fallback: str) -> str:
    if value is None or value == "":
        return fallback
    return str(value).strip().upper()


def _mechanics(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("name")
        if item:
            names.append(str(item).strip().upper())
    return tuple(sorted(set(names)))


def _first_race(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None or value == "":
        return None
    return str(value).strip().upper()


class CardCatalog:
    """Small local card catalog with a non-throwing unknown-card fallback."""

    def __init__(self, cards: list[CardFeatures] | tuple[CardFeatures, ...] = ()) -> None:
        self._cards = {card.card_id: card for card in cards if card.card_id}

    @classmethod
    def from_json(cls, path: str | Path) -> "CardCatalog":
        """Read a HearthstoneJSON-style file containing a list of card objects."""
        with Path(path).open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)

        if isinstance(payload, dict):
            payload = payload.get("cards", [])
        if not isinstance(payload, list):
            raise ValueError("Card JSON must contain a list of cards")

        cards = [cls._from_record(record) for record in payload if isinstance(record, dict)]
        return cls(cards)

    @staticmethod
    def _from_record(record: dict[str, Any]) -> CardFeatures:
        mechanics = _mechanics(record.get("mechanics"))
        return CardFeatures(
            card_id=str(record.get("card_id") or record.get("id") or record.get("dbfId") or "UNKNOWN_CARD"),
            cost=_optional_int(record.get("cost")),
            attack=_optional_int(record.get("attack")),
            health=_optional_int(record.get("health")),
            durability=_optional_int(record.get("durability")),
            card_type=_text(record.get("card_type", record.get("type")), "UNKNOWN_TYPE"),
            card_class=_text(
                record.get("card_class", record.get("cardClass") or record.get("playerClass")),
                "UNKNOWN_CLASS",
            ),
            race=_first_race(record.get("race") or record.get("races")),
            mechanics=mechanics,
            current_spell_damage=_optional_int(record.get("current_spell_damage")),
            prepare_used=record.get("prepare_used"),
            held_spell_progress=_optional_int(record.get("held_spell_progress")),
            trigger_remaining=_optional_int(record.get("trigger_remaining")),
            effect_turns_remaining=_optional_int(record.get("effect_turns_remaining")),
            freeze_turns_remaining=_optional_int(record.get("freeze_turns_remaining")),
            shatter_fragment=record.get("shatter_fragment") or None,
            shatter_original_card_id=record.get("shatter_original_card_id") or None,
            shatter_partner_hand_position=record.get("shatter_partner_hand_position"),
            prepare_locked=record.get("prepare_locked"),
        )

    def __len__(self) -> int:
        return len(self._cards)

    def to_dict(self) -> list[dict[str, Any]]:
        """Return a stable, JSON-compatible snapshot of the catalog."""
        return [
            {
                "card_id": card.card_id, "cost": card.cost, "attack": card.attack,
                "health": card.health, "durability": card.durability,
                "card_type": card.card_type, "card_class": card.card_class,
                "race": card.race, "mechanics": list(card.mechanics),
                "shatter_fragment": card.shatter_fragment,
                "shatter_original_card_id": card.shatter_original_card_id,
                "shatter_partner_hand_position": card.shatter_partner_hand_position,
                "prepare_locked": card.prepare_locked,
                "current_spell_damage": card.current_spell_damage,
                "prepare_used": card.prepare_used,
                "held_spell_progress": card.held_spell_progress,
                "trigger_remaining": card.trigger_remaining,
                "effect_turns_remaining": card.effect_turns_remaining,
                "freeze_turns_remaining": card.freeze_turns_remaining,
            }
            for card in sorted(self._cards.values(), key=lambda item: item.card_id)
        ]

    @classmethod
    def from_dict(cls, records: list[dict[str, Any]]) -> "CardCatalog":
        return cls([cls._from_record(record) for record in records])

    def merged(self, other: "CardCatalog") -> "CardCatalog":
        """Add records from another catalog only where this catalog lacks them."""
        cards = dict(self._cards)
        for card in other:
            cards.setdefault(card.card_id, card)
        return CardCatalog(list(cards.values()))

    def __iter__(self):
        return iter(self._cards.values())

    def get(self, card_id: str) -> CardFeatures:
        """Return the catalog record or a property-light record for an unknown ID."""
        key = str(card_id)
        return self._cards.get(key, CardFeatures(card_id=key or "UNKNOWN_CARD"))

    def enrich(self, observed: CardFeatures) -> CardFeatures:
        """Fill missing observed properties from the catalog without losing known data."""
        catalog_card = self.get(observed.card_id)
        return CardFeatures(
            card_id=observed.card_id,
            cost=observed.cost if observed.cost is not None else catalog_card.cost,
            attack=observed.attack if observed.attack is not None else catalog_card.attack,
            health=observed.health if observed.health is not None else catalog_card.health,
            durability=(observed.durability if observed.durability is not None else catalog_card.durability),
            card_type=(observed.card_type if observed.card_type != "UNKNOWN_TYPE" else catalog_card.card_type),
            card_class=(observed.card_class if observed.card_class != "UNKNOWN_CLASS" else catalog_card.card_class),
            race=observed.race if observed.race is not None else catalog_card.race,
            mechanics=tuple(sorted(set(observed.mechanics) | set(catalog_card.mechanics))),
            current_cost=observed.current_cost,
            current_spell_damage=observed.current_spell_damage,
            prepare_used=observed.prepare_used,
            held_spell_progress=observed.held_spell_progress,
            trigger_remaining=observed.trigger_remaining,
            effect_turns_remaining=observed.effect_turns_remaining,
            freeze_turns_remaining=observed.freeze_turns_remaining,
            current_attack=observed.current_attack,
            current_health=observed.current_health,
            current_durability=observed.current_durability,
            shatter_fragment=observed.shatter_fragment or catalog_card.shatter_fragment,
            shatter_original_card_id=(observed.shatter_original_card_id or catalog_card.shatter_original_card_id),
            shatter_partner_hand_position=(observed.shatter_partner_hand_position if observed.shatter_partner_hand_position is not None else catalog_card.shatter_partner_hand_position),
            prepare_locked=(observed.prepare_locked if observed.prepare_locked is not None else catalog_card.prepare_locked),
        )
