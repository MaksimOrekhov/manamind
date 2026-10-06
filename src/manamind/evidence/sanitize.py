"""Output sanitizers: only identifiers that cannot carry a player name leave the extractor."""

from __future__ import annotations

import re

from hearthstone.enums import GameTag

_CARD_ID = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_CODE = re.compile(r"^[A-Z0-9_]{1,64}$")

_KNOWN_TAGS = frozenset(int(tag) for tag in GameTag)


def safe_card_id(value) -> str | None:
    """A card id as the game spells it, or None for anything else (never raw text)."""
    if isinstance(value, str) and _CARD_ID.match(value):
        return value
    return None


def safe_code(value) -> str | int | None:
    """An enum name, an unknown numeric id (kept as a number) or None."""
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str) and _CODE.match(name):
        return name
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str) and _CODE.match(value):
        return value
    return "UNKNOWN"


def to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def tag_is_known(tag: int) -> bool:
    return int(tag) in _KNOWN_TAGS


def tag_label(tag: int) -> str:
    """Tag name when this hearthstone package knows it, otherwise the numeric id as text."""
    tag = int(tag)
    return GameTag(tag).name if tag in _KNOWN_TAGS else str(tag)
