"""Poll loop: tail -> session -> recorder. One ``step`` is one poll."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from .recorder import Recorder
from .session import GameRun, LiveEvent, LiveSession
from .tail import FILE_DISCONTINUITY, NEW_SESSION, START, LogTail


class LiveRunner:
    def __init__(
        self,
        logs_root: Path,
        session: LiveSession,
        recorder: Recorder | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.tail = LogTail(logs_root)
        self.session = session
        self.recorder = recorder
        self.clock = clock

    def step(self) -> list[LiveEvent]:
        now_ms = int(self.clock() * 1000)
        batch = self.tail.poll()
        events: list[LiveEvent] = []
        touched: list[GameRun] = []

        if batch.problem:
            events += self.session.disconnected(batch.problem)
        else:
            events += self.session.connected()
            if batch.reset == NEW_SESSION:
                events += self.session.new_source(batch.session)
            elif batch.reset == FILE_DISCONTINUITY:
                events += self.session.file_discontinuity(batch.has_game)
            elif batch.reset == START:
                self.session.session_name = batch.session
            if batch.lines:
                events += self.session.feed(batch.lines, now_ms, (batch.start_offset, batch.end_offset))
                touched += self.session.last_touched
        events += self.session.tick(now_ms, batch.partial)
        touched += self.session.last_touched

        if self.recorder is not None:
            unique = list({id(game): game for game in touched}.values())
            self.recorder.sync(self.session.session_name, unique, events)
        return events
