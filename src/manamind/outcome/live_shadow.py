"""LIVE wiring of the outcome shadow (ACTION-OUTCOME-2): forecast the whole menu of a displayed decision, write it down.

This module lives in ``manamind.outcome`` on purpose: the ``manamind.live`` package, the overlay and ``apps`` never
import the forecaster (a test enforces it), so no forecast can reach a displayed recommendation. Only the launcher script
connects the two, and only when ``--outcome-shadow`` is given.

The shadow is a read-only consumer of what the Policy path already trusted: the same ``Snapshot`` (state, ``observed``
SELF facts) and the same legal menu (``Recommendation.menu``, in Policy rank order). It never touches the ranking, the
displayed text, the encoder or a checkpoint, and every failure ends in a stable code in the shadow journal and in
``stats`` - never in an exception that reaches the runtime. See ``manamind.outcome.shadow`` for the record.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from manamind.domain.serialization import game_state_from_dict
from manamind.live.recommendation import Recommendation
from manamind.live.snapshot import Snapshot
from manamind.outcome.observation import context_from_observed
from manamind.outcome.shadow import (
    DEFAULT_BUDGET_MS, ERROR, FORECASTER_REVISION, NOT_COMPUTED, SHADOW_SCHEMA, context_to_dict, digest, forecast_menu,
)
from manamind.outcome.texts import TextSource
from manamind.outcome.world import ObservedContext

DEFAULT_TEXT_FILES = ("data/cards/standard_current_enUS.json", "data/outcome/reviewed_texts.json")


class ShadowFailed(Exception):
    """A shadow that could not be produced; ``reason`` is a stable code (no log or exception text)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class ShadowStats:
    """Session counters for the diagnostics line printed at the end of a run."""

    decisions: int = 0
    recorded: int = 0
    failed: int = 0
    incomplete: int = 0
    journal_failures: int = 0
    reasons: Counter = field(default_factory=Counter)
    status: Counter = field(default_factory=Counter)
    elapsed_ms: list[float] = field(default_factory=list)

    def summary(self) -> str:
        if not self.decisions:
            return "outcome shadow: no decisions"
        text = (f"outcome shadow: {self.recorded}/{self.decisions} decisions recorded, {self.failed} failed, "
                f"{self.incomplete} incomplete, {self.journal_failures} journal failures")
        if self.elapsed_ms:
            text += (f"; forecast {float(np.percentile(self.elapsed_ms, 50)):.2f} ms median, "
                     f"{float(np.percentile(self.elapsed_ms, 95)):.2f} ms p95, {max(self.elapsed_ms):.2f} ms max")
        return text


def load_texts(root: Path) -> TextSource:
    return TextSource.from_files(*(Path(root) / name for name in DEFAULT_TEXT_FILES))


class OutcomeShadow:
    def __init__(self, texts: TextSource, *, budget_ms: float = DEFAULT_BUDGET_MS,
                 clock: Callable[[], int] = time.perf_counter_ns) -> None:
        self.texts = texts
        self.budget_ms = budget_ms
        self.clock = clock
        self.stats = ShadowStats()
        self._texts_sha256 = digest(texts.fingerprints) if texts.fingerprints else None

    def forecast(self, snapshot: Snapshot, recommendation: Recommendation) -> dict[str, Any]:
        """The journal record for one decision. Raises ``ShadowFailed`` with a stable reason; nothing else escapes."""
        if not recommendation.menu:
            raise ShadowFailed("NO_MENU")
        try:
            state = game_state_from_dict(snapshot.state)
        except Exception:
            raise ShadowFailed("STATE_UNREADABLE") from None
        try:
            context = context_from_observed(snapshot.observed, state)
            context_failed = False
        except Exception:                      # unreadable facts mean unknown facts, which is always safe
            context, context_failed = ObservedContext(), True
        menu = [(item.index, rank, item.action) for rank, item in enumerate(recommendation.menu, 1)]
        try:
            record = forecast_menu(state, menu, self.texts, context, budget_ms=self.budget_ms, clock=self.clock)
        except Exception:
            raise ShadowFailed("FORECAST_FAILED") from None
        coverage = snapshot.observed.coverage if snapshot.observed is not None else "NONE"
        return {"schema": SHADOW_SCHEMA, "forecaster_rev": FORECASTER_REVISION, "texts_sha256": self._texts_sha256, "coverage": coverage,
                "context": context_to_dict(context), **({"context_failed": True} if context_failed else {}),
                **record}

    def count(self, record: dict[str, Any]) -> None:
        self.stats.recorded += 1
        self.stats.elapsed_ms.append(record["elapsed_ms"])
        for row in record["actions"]:
            self.stats.status[row["status"]] += 1
        if not record["complete"]:
            self.stats.incomplete += 1

    def fail(self, reason: str) -> None:
        self.stats.failed += 1
        self.stats.reasons[reason] += 1


__all__ = ["ERROR", "NOT_COMPUTED", "OutcomeShadow", "ShadowFailed", "ShadowStats", "load_texts"]
