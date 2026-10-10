"""Settle gate: a SELF options message becomes a decision only once the UI caught up.

``GameState`` packets run ahead of what the player sees. The client's own task-list
markers say how far the UI is: ``PowerTaskList.DebugDump ID=n`` queues list ``n`` and
``PowerProcessor.EndCurrentTaskList m_currentTaskList=n`` finishes it. An options
message is emitted only when it is complete, no newer GameState packet superseded
it, and every queued list has finished. Later client task lists hide the rating
and revalidate this same menu after settling, if no GameState packet replaced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

SETTLE_TIMEOUT_MS = 15_000
MESSAGE_IDLE_MS = 100  # quiet time after which an options message is taken as complete
PARTIAL_HOLD_MS = 1_000  # longer wait while the tail still buffers a half-written line

DUMP_RE = re.compile(r"^ID=(\d+) ParentID=")
END_RE = re.compile(r"^m_currentTaskList=(\d+)")


@dataclass
class PendingOptions:
    options_id: int
    packet: object  # hslog Options packet, mutated while its lines arrive
    started_ms: int
    last_ms: int
    complete: bool = False
    line_in_game: int = 0


@dataclass
class SettleGate:
    q_created: int = 0
    q_ended: int = 0
    pending: PendingOptions | None = None
    last_taken: PendingOptions | None = None
    superseded: int = 0
    emitted_ids: set[int] = field(default_factory=set)

    def reset(self) -> None:
        self.q_created = 0
        self.q_ended = 0
        self.pending = None
        self.last_taken = None
        self.superseded = 0
        self.emitted_ids = set()

    # -- task-list markers ---------------------------------------------------

    def queued(self, list_id: int) -> None:
        self.q_created = max(self.q_created, list_id)

    def ended(self, list_id: int) -> None:
        self.q_ended = max(self.q_ended, list_id)

    @property
    def settled(self) -> bool:
        return self.q_ended >= self.q_created

    # -- options message lifecycle -------------------------------------------

    def begin(self, packet, options_id: int, now_ms: int, line_in_game: int) -> None:
        if self.pending is not None:
            self.superseded += 1
        self.pending = PendingOptions(options_id, packet, now_ms, now_ms, line_in_game=line_in_game)
        self.last_taken = None

    def recheck_current(self, now_ms: int) -> None:
        """Revalidate an unchanged menu after new client task lists.

        The rating is hidden while tasks run. Only task-list markers can rearm
        this menu; a newer GameState packet clears it through supersede/begin.
        """
        if self.pending is None and self.last_taken is not None:
            self.pending = replace(self.last_taken, started_ms=now_ms)
            self.emitted_ids.discard(self.pending.options_id)

    def touch(self, now_ms: int) -> None:
        if self.pending is not None:
            self.pending.last_ms = now_ms

    def close_message(self) -> None:
        if self.pending is not None:
            self.pending.complete = True

    def idle(self, now_ms: int, partial_line: bool = False) -> None:
        pending = self.pending
        if pending is None or pending.complete:
            return
        wait = PARTIAL_HOLD_MS if partial_line else MESSAGE_IDLE_MS
        if now_ms - pending.last_ms >= wait:
            pending.complete = True

    def supersede(self) -> None:
        self.last_taken = None
        if self.pending is not None:
            self.pending = None
            self.superseded += 1

    def discard(self) -> None:
        self.pending = None
        self.last_taken = None

    def timed_out(self, now_ms: int) -> bool:
        pending = self.pending
        return pending is not None and not self.settled and now_ms - pending.started_ms >= SETTLE_TIMEOUT_MS

    def take_ready(self) -> PendingOptions | None:
        """Return the pending message once, when complete and the UI has settled."""
        pending = self.pending
        if pending is None or not pending.complete or not self.settled:
            return None
        self.pending = None
        if pending.options_id in self.emitted_ids:
            return None  # no duplicate without an explicit task-list recheck
        self.emitted_ids.add(pending.options_id)
        self.last_taken = pending
        return pending
