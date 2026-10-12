"""Background worker of the model shadow: the main LIVE loop only hands over a decision and returns.

* ``submit`` and ``invalidate`` take a tiny lock and never touch a file, a model or the disk.
* One worker thread (at most one decision waiting; an older one that never started is recorded as superseded) is the
  only writer of the journal, so rows of different decisions cannot interleave or mix.
* A decision that stops being current while its models run is not written as a score: the worker records a
  ``MODEL_SHADOW_DISCARDED`` row (reason only); a row that was already written gets a ``MODEL_SHADOW_INVALIDATION``.
* ``threaded=False`` runs everything inline (tests, replay comparison); the rows are identical.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

from manamind.live.snapshot import Snapshot

from .journal import ModelShadowJournal, utc_now
from .shadow import ModelShadow, ShadowFailed, identity_fields


@dataclass
class _Job:
    snapshot: Snapshot
    recommendation: object
    cancel_reason: str | None = None
    superseded: bool = False
    row_written: bool = False


@dataclass
class _Control:
    job: _Job
    reason: str


def _lower_thread_priority() -> None:
    """Best effort: the worker must never compete with the polling loop that serves the displayed recommendation."""
    try:
        import ctypes
        kernel = ctypes.windll.kernel32           # Windows only; any failure is ignored
        kernel.SetThreadPriority(kernel.GetCurrentThread(), -1)   # THREAD_PRIORITY_BELOW_NORMAL
    except Exception:
        pass


class ModelShadowWorker:
    def __init__(self, shadow: ModelShadow, journal: ModelShadowJournal, *, threaded: bool = True) -> None:
        self.shadow = shadow
        self.journal = journal
        self.threaded = threaded
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._queue: deque = deque()
        self._current: _Job | None = None
        self._active = 0
        self._last: _Job | None = None
        self._closing = False
        self._thread: threading.Thread | None = None
        if threaded:
            self._thread = threading.Thread(target=self._loop, name="model-shadow", daemon=True)
            self._thread.start()

    # -- called by the LIVE loop: constant time, no I/O -----------------------------------------------------------

    def submit(self, snapshot: Snapshot, recommendation) -> None:
        job = _Job(snapshot, recommendation)
        with self._lock:
            self.shadow.stats.decisions += 1
            for item in self._queue:
                if isinstance(item, _Job) and not item.superseded and item.cancel_reason is None:
                    item.superseded = True        # never started and replaced by a newer decision
            self._queue.append(job)
            self._wake.notify()
        if not self.threaded:
            self.drain()

    def invalidate(self, snapshot: Snapshot, reason: str) -> None:
        with self._lock:
            target = None
            for item in list(self._queue):
                if isinstance(item, _Job) and item.snapshot is snapshot:
                    target = item
            if target is None and self._current is not None and self._current.snapshot is snapshot:
                target = self._current
            if target is None and self._last is not None and self._last.snapshot is snapshot:
                target = self._last
            if target is None:
                return
            if target.cancel_reason is None:
                target.cancel_reason = reason
            self._queue.append(_Control(target, reason))
            self._wake.notify()
        if not self.threaded:
            self.drain()

    def flush(self, timeout: float = 30.0) -> bool:
        """Wait until nothing is queued or running (tests and offline replay only; LIVE never waits)."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if not self._queue and self._active == 0:
                    return True
            time.sleep(0.002)
        return False

    def close(self, timeout: float = 2.0) -> None:
        """Let the worker finish what it has (bounded); whatever remains is counted as abandoned, never written."""
        if self._thread is None:
            self.drain()
            return
        with self._lock:
            self._closing = True
            self._wake.notify()
        self._thread.join(timeout)
        with self._lock:
            self.shadow.stats.abandoned += sum(1 for item in self._queue if isinstance(item, _Job))

    # -- the single writer ------------------------------------------------------------------------------------

    def _loop(self) -> None:
        _lower_thread_priority()
        while True:
            with self._lock:
                while not self._queue and not self._closing:
                    self._wake.wait()
                if not self._queue and self._closing:
                    return
                item = self._queue.popleft()
                self._active += 1
                if isinstance(item, _Job):
                    self._current = item
            try:
                self._handle(item)
            except Exception:                    # the thread must outlive any single failure
                self.shadow.stats.failed += 1
                self.shadow.stats.reasons["SHADOW_RUNTIME_ERROR"] += 1
            finally:
                with self._lock:
                    self._current = None
                    self._active -= 1

    def drain(self) -> None:
        """Process everything queued, inline (only used when not threaded)."""
        while True:
            with self._lock:
                if not self._queue:
                    return
                item = self._queue.popleft()
                self._active += 1
                if isinstance(item, _Job):
                    self._current = item
            try:
                self._handle(item)
            except Exception:
                self.shadow.stats.failed += 1
                self.shadow.stats.reasons["SHADOW_RUNTIME_ERROR"] += 1
            finally:
                with self._lock:
                    self._current = None
                    self._active -= 1

    def _write(self, row: dict) -> bool:
        try:
            self.journal.append(row)
            return True
        except (OSError, ValueError):
            self.shadow.stats.journal_failures += 1
            return False

    def _event(self, event: str, job: _Job, **extra) -> dict:
        return {"event": event, **identity_fields(job.snapshot), "at_utc": utc_now(), **extra}

    def _handle(self, item) -> None:
        if isinstance(item, _Control):
            job = item.job
            with self._lock:
                already = job.row_written
            if already:
                self._write(self._event("MODEL_SHADOW_INVALIDATION", job, reason=item.reason))
                with self._lock:
                    if self._last is job:
                        self._last = None
            return
        job = item
        stats = self.shadow.stats
        if job.superseded:
            stats.superseded += 1
            self._write(self._event("MODEL_SHADOW_ERROR", job, reason="SUPERSEDED_BEFORE_START"))
            return
        if job.cancel_reason is not None:
            stats.discarded += 1
            self._write(self._event("MODEL_SHADOW_DISCARDED", job, reason="DECISION_CHANGED_BEFORE_START"))
            return
        try:
            record = self.shadow.score(job.snapshot, job.recommendation, cancelled=lambda: job.cancel_reason)
        except ShadowFailed as error:
            stats.failed += 1
            stats.reasons[error.reason] += 1
            self._write(self._event("MODEL_SHADOW_ERROR", job, reason=error.reason))
            return
        except Exception:
            stats.failed += 1
            stats.reasons["SHADOW_RUNTIME_ERROR"] += 1
            self._write(self._event("MODEL_SHADOW_ERROR", job, reason="SHADOW_RUNTIME_ERROR"))
            return
        with self._lock:                         # the decision may have changed while the models ran
            cancelled = job.cancel_reason
            if cancelled is None:
                job.row_written = True
                self._last = job
        if cancelled is not None:
            stats.discarded += 1
            self._write(self._event("MODEL_SHADOW_DISCARDED", job, reason="DECISION_CHANGED_DURING_INFERENCE"))
            return
        if self._write(self._event("MODEL_SHADOW", job, **record)):
            stats.recorded += 1
        else:
            job.row_written = False


__all__ = ["ModelShadowWorker"]
