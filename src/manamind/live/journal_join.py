"""Semantic signatures for strict joins of repeated LIVE shadow journal rows."""

from __future__ import annotations

import hashlib
from typing import Any

from .snapshot import canonical_json

_OUTCOME_FIELDS = (
    "schema", "forecaster_rev", "texts_sha256", "context", "complete", "menu_size", "actions",
)


def outcome_journal_signature(row: dict[str, Any]) -> str:
    """Return the semantic identity of an Outcome Shadow row.

    ``forecast_menu`` records per-action ``us`` as a runtime measurement. It is
    intentionally excluded from identity: otherwise identical forecasts from
    repeated displays conflict solely because their execution times differ.
    Every other action field and the ordered action list remain significant.
    """
    value = {field: row.get(field) for field in _OUTCOME_FIELDS}
    actions = value["actions"]
    if isinstance(actions, list):
        value["actions"] = [
            {key: item_value for key, item_value in action.items() if key != "us"}
            if isinstance(action, dict) else action
            for action in actions
        ]
    encoded = canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
