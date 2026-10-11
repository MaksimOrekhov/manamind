"""Pure building blocks of the LIVE outcome shadow (ACTION-OUTCOME-2): forecast a whole menu, make a compact record.

Nothing here reads a log, a file or the clock beyond the injected ``clock``; the LIVE wiring lives in
``manamind.outcome.live_shadow`` and the offline analysis in ``manamind.outcome.shadow_analysis``. A record keeps
what the forecaster *claims* (exact local effects, bounds, the tags of what is open) plus a digest of the full
forecast, never the pre-action state: the state of a decision is already in the LIVE recording, and the digest lets
an analyzer prove that it recomputed the same forecast from that recording.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from typing import Any

from manamind.domain.game_state import GameState
from manamind.outcome.forecast import describe_action, forecast_action
from manamind.outcome.model import Forecast, Status, Tier
from manamind.outcome.texts import TextSource
from manamind.outcome.world import ObservedContext

SHADOW_SCHEMA = "manamind.outcome_shadow/1"
MAX_EFFECTS_PER_ACTION = 24      # a larger ledger is cut; ``effects_more`` says by how much, the digest still covers all
MAX_MENU = 160                    # a menu this large is cut in Policy rank order; the rest is NOT_COMPUTED
DEFAULT_BUDGET_MS = 250.0         # wall clock for one decision; exceeded -> the remaining actions are NOT_COMPUTED

# Statuses of a recorded action that are not a forecast status.
NOT_COMPUTED = "NOT_COMPUTED"
ERROR = "ERROR"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def action_digest(action: dict[str, Any]) -> str:
    """Identity of a legal action inside its decision; 16 hex characters are plenty for a menu of at most a few dozen."""
    return digest(action)[:16]


def context_to_dict(context: ObservedContext) -> dict[str, Any]:
    """JSON form of an ``ObservedContext``; fields still at their default are omitted.

    An observed ``False`` (for example "Ruby Sanctum is not active") is a fact and is kept: only the field's own
    default (``None`` = not observed, or a ``False`` switch) is dropped.
    """
    out: dict[str, Any] = {}
    for name, spec in context.__dataclass_fields__.items():
        value = getattr(context, name)
        if value == spec.default:
            continue
        if name == "hand_keywords":
            value = [None if item is None else sorted(item) for item in value]
        out[name] = value
    return out


def context_from_dict(data: dict[str, Any]) -> ObservedContext:
    values = dict(data)
    if "hand_keywords" in values:
        values["hand_keywords"] = tuple(None if item is None else frozenset(item) for item in values["hand_keywords"])
    return ObservedContext(**values)


def forecast_digest(forecast: Forecast) -> str:
    """Digest of the complete forecast ledger (changes, events, unknowns, assumptions, rules)."""
    return digest(forecast.to_dict())


def compact_forecast(forecast: Forecast) -> dict[str, Any]:
    """What a LIVE record keeps of one forecast. Open details are reduced to stable tags (no free text)."""
    effects = [[c.ref.label(), c.field, c.before, c.after] for c in forecast.effect_changes]
    bounds = [[c.ref.label(), c.field, c.before, c.at_least, c.at_most] for c in forecast.bounded_changes]
    row: dict[str, Any] = {
        "status": forecast.status.value,
        "tier": forecast.tier.value,
        "own": int(forecast.own_effect_known),
        "effects": effects[:MAX_EFFECTS_PER_ACTION],
        "bookkeeping": sum(1 for c in forecast.exact_changes if c.role == "BOOKKEEPING"),
        "unknowns": sorted({f"{u.kind.value}:{u.tag}" if u.tag else u.kind.value for u in forecast.unknowns}),
        "digest": forecast_digest(forecast),
    }
    if len(effects) > MAX_EFFECTS_PER_ACTION:
        row["effects_more"] = len(effects) - MAX_EFFECTS_PER_ACTION
    if bounds:
        row["bounds"] = bounds[:MAX_EFFECTS_PER_ACTION]
    if forecast.unsupported_reason:
        row["reason"] = forecast.unsupported_reason
    return row


def forecast_menu(
    state: GameState,
    menu: Sequence[tuple[int, int, dict[str, Any]]],
    texts: TextSource,
    context: ObservedContext,
    *,
    budget_ms: float = DEFAULT_BUDGET_MS,
    clock: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, Any]:
    """Forecast every action of one decision, independently, from the same pre-action state.

    ``menu`` is ``(menu index, Policy rank, action)`` in Policy rank order. A failure of one action is recorded
    for that action only; once the wall-clock budget is spent the remaining actions are recorded as NOT_COMPUTED
    (the budget is checked between actions, one forecast is never interrupted). The result is the ``actions`` /
    counters part of a journal row; ``elapsed_ms`` and each ``us`` are measurements, everything else is
    deterministic in (state, menu, texts, context).
    """
    started = clock()
    rows: list[dict[str, Any]] = []
    spent = False
    for index, rank, action in list(menu)[:MAX_MENU]:
        row: dict[str, Any] = {"index": index, "rank": rank, "label": _label(state, action),
                               "action": action_digest(action)}
        if spent or (clock() - started) / 1e6 > budget_ms:
            spent = True
            row["status"] = NOT_COMPUTED
            rows.append(row)
            continue
        begun = clock()
        try:
            forecast = forecast_action(state, action, texts, context)
            row.update(compact_forecast(forecast))
        except Exception as error:  # one action must not cost the menu; only the exception class is kept
            row["status"] = ERROR
            row["error"] = type(error).__name__
        row["us"] = (clock() - begun) // 1000
        rows.append(row)
    for index, rank, action in list(menu)[MAX_MENU:]:
        rows.append({"index": index, "rank": rank, "label": _label(state, action),
                     "action": action_digest(action), "status": NOT_COMPUTED})
    computed = [r for r in rows if r["status"] not in (NOT_COMPUTED, ERROR)]
    return {
        "menu_size": len(menu),
        "computed": len(computed),
        "not_computed": sum(r["status"] == NOT_COMPUTED for r in rows),
        "errors": sum(r["status"] == ERROR for r in rows),
        "complete": len(computed) + sum(r["status"] == ERROR for r in rows) == len(menu),
        "elapsed_ms": round((clock() - started) / 1e6, 3),
        "budget_ms": budget_ms,
        "actions": rows,
    }


def _label(state: GameState, action: dict[str, Any]) -> str:
    try:
        return describe_action(state, action)
    except Exception:
        return str(action.get("type", "?"))


STATUS_ORDER = tuple(s.value for s in Status) + (NOT_COMPUTED, ERROR)
TIER_ORDER = tuple(t.value for t in Tier)
