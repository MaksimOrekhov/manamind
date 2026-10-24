from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.live.journal_join import outcome_journal_signature  # noqa: E402


def _outcome_row() -> dict:
    return {
        "schema": "manamind.outcome_shadow/1",
        "forecaster_rev": 2,
        "texts_sha256": "a" * 64,
        "context": {"self_turn": 3},
        "complete": True,
        "menu_size": 1,
        "actions": [{
            "index": 0,
            "rank": 1,
            "action": "b" * 16,
            "status": "PARTIAL",
            "unknowns": ["MECHANIC:UNSUPPORTED"],
            "digest": "c" * 64,
            "us": 18,
        }],
        "elapsed_ms": 18.5,
    }


def test_outcome_signature_ignores_per_action_runtime_measurements_only():
    first = _outcome_row()
    repeated = copy.deepcopy(first)
    repeated["elapsed_ms"] = 41.2
    repeated["actions"][0]["us"] = 41_000

    assert outcome_journal_signature(first) == outcome_journal_signature(repeated)


def test_outcome_signature_keeps_forecast_semantics_significant():
    original = _outcome_row()
    for field, value in (
        ("status", "UNSUPPORTED"),
        ("unknowns", ["MECHANIC:OTHER"]),
        ("digest", "d" * 64),
        ("action", "e" * 16),
    ):
        changed = copy.deepcopy(original)
        changed["actions"][0][field] = value
        assert outcome_journal_signature(original) != outcome_journal_signature(changed)


def test_outcome_signature_keeps_menu_order_and_non_timing_fields_significant():
    first = _outcome_row()
    second = copy.deepcopy(first)
    second["actions"].append({"index": 1, "rank": 2, "action": "f" * 16, "us": 12})
    second["menu_size"] = 2

    assert outcome_journal_signature(first) != outcome_journal_signature(second)
