"""Poll loop: tail -> session -> recorder. One ``step`` is one poll."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from .recorder import Recorder, RecordingResumeError
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
        self.recording_failures: Counter[str] = Counter()
        self._games: dict[str, GameRun] = {}
        self._match_recording_failures: dict[str, Counter[str]] = {}
        if recorder is not None:
            self.session.sequence_resume = self._resume_sequence

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
                events += self.session.feed(
                    batch.lines, now_ms, (batch.start_offset, batch.end_offset), catchup=batch.reset is not None
                )
                touched += self.session.last_touched
        events += self.session.tick(now_ms, batch.partial)
        touched += self.session.last_touched

        if self.recorder is not None:
            unique = list({id(game): game for game in touched}.values())
            for game in unique:
                if game.game_key is not None:
                    self._games[game.game_key] = game
            try:
                self.recorder.sync(self.session.session_name, unique, events)
            except Exception as error:
                code = _recording_failure_code(error)
                failed_keys = [game.game_key for game in unique if game.game_key is not None]
                if isinstance(error, RecordingResumeError):
                    for key in failed_keys:
                        self.recorder.disable_game(key, code)
                self._note_recording_failure(code, failed_keys)
        return events

    def drain_recording_failures(self) -> dict[str, int]:
        failures = dict(self.recording_failures)
        self.recording_failures.clear()
        return failures

    def finish(self) -> None:
        if self.recorder is None:
            return
        try:
            self.recorder.finalize()
        except Exception as error:
            code = _recording_failure_code(error)
            self.recording_failures[code] += 1
            self.recorder.note_failure(code)

    def capture_summary_for(self, game_key: str) -> dict | None:
        game = self._games.get(game_key)
        if game is None:
            return None
        recorded = self.recorder.capture_summary_for(game_key) if self.recorder is not None else None
        if recorded is not None:
            return recorded
        return {
            "game_key": game_key,
            "live_observed": True,
            "counter_scope": "CURRENT_PROCESS",
            "capture_status": "COMPLETE" if game.ended else "ACTIVE",
            "options_packets_seen": game.options_packets_seen,
            "trusted_snapshots_emitted": game.trusted_snapshots,
            "trusted_snapshots_increment": max(
                0, game.trusted_snapshots - game.resumed_snapshot_duplicates
            ),
            "resumed_snapshot_duplicates": game.resumed_snapshot_duplicates,
            "snapshots_saved": (self.recorder.snapshot_count_for(game_key)
                                if self.recorder is not None else 0),
            "trust_rejections": dict(sorted(game.trust_rejections.items())),
            "superseded_menus": game.gate.superseded,
            "recording_failures": dict(sorted(
                self._match_recording_failures.get(game_key, {}).items()
            )),
        }

    def _resume_sequence(self, game_key: str, options_id: int, digest: str) -> tuple[int | None, int]:
        if self.recorder is None:
            return None, 0
        try:
            return self.recorder.sequence_for(self.session.session_name, game_key, options_id, digest)
        except Exception as error:
            code = _recording_failure_code(error)
            self.recorder.disable_game(game_key, code)
            self._note_recording_failure(code, [game_key])
            # Sequence history cannot be proven. Keep a process-local identity for LIVE
            # recommendations, but permanently fail closed on recording this match.
            return None, 0

    def _note_recording_failure(self, code: str, game_keys: list[str]) -> None:
        self.recording_failures[code] += 1
        if self.recorder is None or not game_keys:
            if self.recorder is not None:
                self.recorder.note_failure(code)
            return
        for game_key in game_keys:
            self._match_recording_failures.setdefault(game_key, Counter())[code] += 1
            self.recorder.note_match_failure(game_key, code)


def _recording_failure_code(error: Exception) -> str:
    if isinstance(error, RecordingResumeError):
        return "RECORDING_RESUME_FAILED"
    if isinstance(error, PermissionError):
        return "FILE_ACCESS_DENIED"
    if isinstance(error, FileNotFoundError):
        return "FILE_NOT_FOUND"
    if isinstance(error, OSError):
        return "FILE_IO_ERROR"
    if isinstance(error, (ValueError, TypeError, KeyError)):
        return "INVALID_RECORDING_DATA"
    return "RECORDING_ERROR"
