"""LIVE wiring of the Strategic Scorer shadow (``--strategy-shadow``): rank the displayed menu independently, write it down.

The shadow reads what the Policy path already trusted - the same ``Snapshot`` (state and observed SELF facts) and the
same complete legal menu - but it takes the menu in *menu order*, never in Policy rank order, and it never reads a
Policy score. Its ranking goes only to its own journal file; the displayed Top-3, the Policy journal and the overlay
are untouched. ``manamind.live`` and the apps never import this module (a test enforces it); only the launcher script
connects it, after the recommendation has been displayed and journaled.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from manamind.domain.serialization import game_state_from_dict
from manamind.live.recommendation import Recommendation
from manamind.live.snapshot import Snapshot
from manamind.outcome.observation import context_from_observed
from manamind.outcome.shadow import FORECASTER_REVISION, action_digest, context_to_dict, digest
from manamind.outcome.texts import TextSource
from manamind.outcome.world import ObservedContext
from manamind.strategy.scorer import DEFAULT_BUDGET_MS, SCORER_VERSION, score_menu
from manamind.strategy.value import PARAMS_VERSION

STRATEGY_SCHEMA = "manamind.strategy_shadow/1"


class StrategyFailed(Exception):
    """A strategy shadow that could not be produced; ``reason`` is a stable code (no log or exception text)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class StrategyStats:
    decisions: int = 0
    recorded: int = 0
    failed: int = 0
    incomplete: int = 0
    journal_failures: int = 0
    reasons: Counter = field(default_factory=Counter)
    elapsed_ms: list[float] = field(default_factory=list)

    def summary(self) -> str:
        if not self.decisions:
            return "strategy shadow: no decisions"
        text = (f"strategy shadow: {self.recorded}/{self.decisions} decisions recorded, {self.failed} failed, "
                f"{self.incomplete} incomplete, {self.journal_failures} journal failures")
        if self.elapsed_ms:
            text += (f"; scoring {float(np.percentile(self.elapsed_ms, 50)):.2f} ms median, "
                     f"{float(np.percentile(self.elapsed_ms, 95)):.2f} ms p95, {max(self.elapsed_ms):.2f} ms max")
        return text


class StrategyShadow:
    def __init__(self, texts: TextSource, *, budget_ms: float = DEFAULT_BUDGET_MS,
                 clock: Callable[[], int] = time.perf_counter_ns) -> None:
        self.texts = texts
        self.budget_ms = budget_ms
        self.clock = clock
        self.stats = StrategyStats()
        self._texts_sha256 = digest(texts.fingerprints) if texts.fingerprints else None

    def score(self, snapshot: Snapshot, recommendation: Recommendation) -> dict[str, Any]:
        """The journal record for one decision. Raises ``StrategyFailed`` with a stable reason; nothing else escapes."""
        if not recommendation.menu:
            raise StrategyFailed("NO_MENU")
        ordered = sorted(recommendation.menu, key=lambda item: item.index)   # menu order: Policy order is not an input
        if [item.index for item in ordered] != list(range(len(ordered))):
            raise StrategyFailed("MENU_INDEX_MISMATCH")
        actions = [dict(item.action) for item in ordered]
        try:
            state = game_state_from_dict(snapshot.state)
        except Exception:
            raise StrategyFailed("STATE_UNREADABLE") from None
        try:
            context = context_from_observed(snapshot.observed, state)
            context_failed = False
        except Exception:                      # unreadable facts mean unknown facts, which is always safe
            context, context_failed = ObservedContext(), True
        try:
            result = score_menu(state, actions, self.texts, context, budget_ms=self.budget_ms, clock=self.clock)
        except Exception:
            raise StrategyFailed("SCORING_FAILED") from None
        coverage = snapshot.observed.coverage if getattr(snapshot, "observed", None) is not None else "NONE"
        top = []
        for rank, group in enumerate(result.groups[:3], 1):
            head = result.actions[group[0]]
            top.append({"rank": rank, "indices": list(group), **head.to_dict()})
        return {
            "schema": STRATEGY_SCHEMA, "scorer": SCORER_VERSION, "params": PARAMS_VERSION,
            "forecaster_rev": FORECASTER_REVISION, "texts_sha256": self._texts_sha256, "coverage": coverage,
            "context": context_to_dict(context), **({"context_failed": True} if context_failed else {}),
            "menu_size": len(actions), "computed": result.computed,
            "complete": result.computed == len(actions), "elapsed_ms": result.elapsed_ms, "budget_ms": self.budget_ms,
            "top3": top,
            "actions": [{"index": a.index, "action": action_digest(a.action), "score": round(a.score, 3),
                         "status": a.status, "uncertainty": a.uncertainty.level} for a in result.actions],
        }

    def count(self, record: dict[str, Any]) -> None:
        self.stats.recorded += 1
        self.stats.elapsed_ms.append(record["elapsed_ms"])
        if not record["complete"]:
            self.stats.incomplete += 1

    def fail(self, reason: str) -> None:
        self.stats.failed += 1
        self.stats.reasons[reason] += 1


__all__ = ["STRATEGY_SCHEMA", "StrategyFailed", "StrategyShadow", "StrategyStats"]
