"""Display-only names from a pinned HearthstoneJSON client localization snapshot."""
from __future__ import annotations

import json
from pathlib import Path


class CardNames:
    def __init__(self, names: dict | None = None, texts: dict[str, str] | None = None) -> None:
        self.names = names or {}
        self.texts = texts or {}

    @classmethod
    def load(cls, path: Path, fallback: Path | None = None) -> CardNames:
        names = {}
        texts = {}
        if fallback is not None:
            try:
                payload = json.loads(fallback.read_text(encoding="utf-8-sig"))
                records = payload.get("cards", []) if isinstance(payload, dict) else payload
                names = {r["id"]: {"enUS": r["name"]} for r in records if r.get("name")}
                texts = {r["id"]: r["text"] for r in records
                         if r.get("id") and isinstance(r.get("text"), str) and r["text"]}
            except (OSError, ValueError, KeyError, TypeError):
                pass
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["schema"] != "manamind.card_names/1":
                raise ValueError("Unsupported names schema")
            for card_id, localized in payload["names"].items():
                names[card_id] = {**names.get(card_id, {}), **localized}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return cls(names, texts)

    def text(self, card_id: str | None) -> str:
        return self.texts.get(card_id, "") if card_id else ""

    def get(self, card_id: str | None, language: str = "ru") -> str:
        if not card_id:
            return "Неизвестная карта" if language == "ru" else "Unknown card"
        names = self.names.get(card_id, {})
        return (names.get("ruRU") if language == "ru" else None) or names.get("enUS") or card_id
