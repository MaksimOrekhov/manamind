"""Rules-text lookup for the forecaster.

Text comes only from pinned card JSON files (the Standard catalog first, then an optional
supplemental snapshot for tokens, coins and hero powers). A card absent from every source has no
text: the forecaster reports that, it never guesses from the card ID.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CardText:
    card_id: str
    text: str
    card_type: str
    mechanics: tuple[str, ...]
    source: str
    attack: int | None = None          # printed (base) stats, from the card JSON; None for non-minions
    health: int | None = None
    spell_school: str | None = None


class TextSource:
    def __init__(self, records: Iterable[CardText] = ()) -> None:
        self._records = {record.card_id: record for record in records}
        self.fingerprints: dict[str, str] = {}

    @classmethod
    def from_records(cls, records: Iterable[dict[str, Any]], source: str = "inline") -> "TextSource":
        return cls(_card_text(record, source) for record in records)

    @classmethod
    def from_files(cls, *paths: str | Path) -> "TextSource":
        """Earlier files win; later files only supply card IDs the earlier ones lack."""
        merged: dict[str, CardText] = {}
        fingerprints: dict[str, str] = {}
        for path in paths:
            file_path = Path(path)
            raw = file_path.read_bytes()
            fingerprints[file_path.name] = hashlib.sha256(raw).hexdigest()
            payload = json.loads(raw.decode("utf-8-sig"))
            if isinstance(payload, dict):
                payload = payload.get("cards", [])
            for record in payload:
                if isinstance(record, dict) and record.get("id"):
                    merged.setdefault(str(record["id"]), _card_text(record, file_path.name))
        source = cls(merged.values())
        source.fingerprints = fingerprints
        return source

    def extended(self, records: Iterable[dict[str, Any]], source: str = "inline") -> "TextSource":
        """A copy that adds (or replaces) the given records; used for controlled scenarios."""
        merged = dict(self._records)
        merged.update({record.card_id: record for record in (_card_text(r, source) for r in records)})
        copy = TextSource(merged.values())
        copy.fingerprints = dict(self.fingerprints)
        return copy

    def get(self, card_id: str) -> CardText | None:
        return self._records.get(card_id)

    def __len__(self) -> int:
        return len(self._records)


def _card_text(record: dict[str, Any], source: str) -> CardText:
    mechanics = record.get("mechanics") or ()
    return CardText(
        card_id=str(record["id"]),
        text=str(record.get("text") or ""),
        card_type=str(record.get("type") or "UNKNOWN_TYPE").upper(),
        mechanics=tuple(sorted({str(item).upper() for item in mechanics})),
        source=source,
        attack=_optional_int(record.get("attack")),
        health=_optional_int(record.get("health")),
        spell_school=(str(record["spellSchool"]).upper() if record.get("spellSchool") else None),
    )


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
