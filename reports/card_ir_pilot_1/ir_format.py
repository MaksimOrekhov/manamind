"""Canonical, review-friendly JSON layout for Card IR declarations: short objects and lists stay on one line."""

from __future__ import annotations

import json
from typing import Any

WIDTH = 118


def _dump(value: Any, indent: int, used: int) -> str:
    """``indent``: nesting of this value; ``used``: characters already on its first line (indent + key)."""
    flat = json.dumps(value, ensure_ascii=False)
    if used + len(flat) <= WIDTH or not isinstance(value, (dict, list)) or not value:
        return flat
    pad, inner = " " * indent, " " * (indent + 2)
    if isinstance(value, list):
        items = [inner + _dump(item, indent + 2, indent + 2) for item in value]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    items = []
    for key, item in value.items():
        head = f"{inner}{json.dumps(key, ensure_ascii=False)}: "
        items.append(head + _dump(item, indent + 2, len(head)))
    return "{\n" + ",\n".join(items) + "\n" + pad + "}"


def dumps(value: Any) -> str:
    return _dump(value, 0, 0) + "\n"
