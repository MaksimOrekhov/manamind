"""Deterministic integer vocabularies used by the state encoder."""

from manamind.cards.catalog import CardCatalog


class CardVocabulary:
    """Map card IDs and categorical properties to stable indices."""

    PAD_CARD = 0
    UNKNOWN_CARD = 1

    def __init__(self, catalog: CardCatalog) -> None:
        cards = list(catalog)
        card_ids = sorted({card.card_id for card in cards if card.card_id != "UNKNOWN_CARD"})
        self._card_ids = {card_id: index + 2 for index, card_id in enumerate(card_ids)}
        self.card_count = len(self._card_ids) + 2

        self._type_ids = self._categorical_values(card.card_type for card in cards)
        self._class_ids = self._categorical_values(card.card_class for card in cards)
        self._race_ids = self._categorical_values(card.race for card in cards if card.race)
        self._mechanic_ids = self._categorical_values(
            mechanic for card in cards for mechanic in card.mechanics
        )
        self._mechanic_ids.setdefault("UNKNOWN_MECHANIC", 0)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/pickle-friendly vocabulary description for checkpoints."""
        return {
            "card_ids": self._card_ids,
            "type_ids": self._type_ids,
            "class_ids": self._class_ids,
            "race_ids": self._race_ids,
            "mechanic_ids": self._mechanic_ids,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "CardVocabulary":
        """Restore the exact index mapping stored with a model checkpoint."""
        vocabulary = cls.__new__(cls)
        vocabulary._card_ids = {str(key): int(value) for key, value in payload["card_ids"].items()}
        vocabulary._type_ids = {str(key): int(value) for key, value in payload["type_ids"].items()}
        vocabulary._class_ids = {str(key): int(value) for key, value in payload["class_ids"].items()}
        vocabulary._race_ids = {str(key): int(value) for key, value in payload["race_ids"].items()}
        vocabulary._mechanic_ids = {
            str(key): int(value) for key, value in payload["mechanic_ids"].items()
        }
        vocabulary.card_count = len(vocabulary._card_ids) + 2
        return vocabulary

    @staticmethod
    def _categorical_values(values) -> dict[str, int]:
        tokens = sorted({str(value).strip().upper() for value in values if value})
        tokens = [token for token in tokens if not token.startswith("UNKNOWN_")]
        return {"UNKNOWN": 0, **{token: index + 1 for index, token in enumerate(tokens)}}

    @property
    def mechanics_count(self) -> int:
        """Number of columns in the multi-hot mechanics vector."""
        return max(self._mechanic_ids.values(), default=0) + 1

    @property
    def card_type_count(self) -> int:
        return max(self._type_ids.values(), default=0) + 1

    @property
    def card_class_count(self) -> int:
        return max(self._class_ids.values(), default=0) + 1

    @property
    def race_count(self) -> int:
        return max(self._race_ids.values(), default=0) + 1

    def card_id(self, token: str) -> int:
        return self._card_ids.get(str(token), self.UNKNOWN_CARD)

    def card_type(self, token: str) -> int:
        return self._type_ids.get(str(token).strip().upper(), 0)

    def card_class(self, token: str) -> int:
        return self._class_ids.get(str(token).strip().upper(), 0)

    def race(self, token: str | None) -> int:
        return self._race_ids.get(str(token).strip().upper(), 0) if token else 0

    def mechanics(self, tokens: tuple[str, ...]) -> list[int]:
        """Return indices to activate, including the unknown-mechanic bit as needed."""
        if not tokens:
            return []
        indices = [self._mechanic_ids.get(token.strip().upper(), 0) for token in tokens]
        return sorted(set(indices))

    def player_class(self, token: str) -> int:
        return self.card_class(token)
