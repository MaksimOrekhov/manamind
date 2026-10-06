"""Read-only follower of the newest Hearthstone ``Power.log``.

Opens the file only for reading, and only for the duration of one poll, so it never keeps
a handle that could block the client or HDT from renaming a closed log. Hands out
newline-terminated lines only; a partial trailing line stays buffered until its newline.
Never writes, renames or deletes anything under the Logs folder and never touches
``log.config``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .trust import Reason

POWER_LOG = "Power.log"
SESSION_GLOB = "Hearthstone_*"
# Catch-up scans only the newest part of a huge file.
MAX_SCAN_BYTES = 256 * 1024 * 1024
_CREATE_GAME_BYTES_RE = re.compile(
    rb"^[DWE] \S+ GameState\.DebugPrintPower\(\) - CREATE_GAME[ \t]*\r?$", re.MULTILINE
)

START = "START"
NEW_SESSION = "NEW_SESSION"
FILE_DISCONTINUITY = "FILE_DISCONTINUITY"


@dataclass
class TailBatch:
    lines: list[str] = field(default_factory=list)
    reset: str | None = None      # START | NEW_SESSION | FILE_DISCONTINUITY
    has_game: bool = False        # a CREATE_GAME was found when a reset re-read the file
    problem: str | None = None    # NO_LOGS_ROOT | NO_POWER_LOG | UNREADABLE
    partial: bool = False         # a half-written line is buffered: the writer is mid-write
    session: str | None = None
    start_offset: int = 0
    end_offset: int = 0


def newest_power_log(logs_root: Path) -> Path | None:
    """The Power.log of the newest ``Hearthstone_<timestamp>`` folder (names sort by time)."""
    sessions = sorted(
        (entry for entry in logs_root.glob(SESSION_GLOB) if entry.is_dir()),
        key=lambda entry: entry.name,
        reverse=True,
    )
    for session in sessions:
        candidate = session / POWER_LOG
        if candidate.is_file():
            return candidate
    legacy = logs_root / POWER_LOG
    return legacy if legacy.is_file() else None


def find_last_create_game(path: Path) -> tuple[int | None, int]:
    """Return (offset of the last complete CREATE_GAME line or None, offset after the last newline)."""
    with path.open("rb") as file:
        size = os.fstat(file.fileno()).st_size
        base = max(0, size - MAX_SCAN_BYTES)
        file.seek(base)
        data = file.read()
    matches = list(_CREATE_GAME_BYTES_RE.finditer(data))
    # A match must be a complete line: it ends in a newline inside the data.
    for match in reversed(matches):
        end = data.find(b"\n", match.end())
        if end != -1:
            return base + match.start(), base + data.rfind(b"\n") + 1
    last_newline = data.rfind(b"\n")
    return None, (base + last_newline + 1) if last_newline != -1 else base


def _identity(stat: os.stat_result) -> tuple | None:
    if stat.st_ino:
        return (stat.st_dev, stat.st_ino)
    return None


class LogTail:
    def __init__(self, logs_root: Path) -> None:
        self.logs_root = Path(logs_root)
        self.path: Path | None = None
        self.session: str | None = None
        self._offset = 0
        self._identity: tuple | None = None
        self._remainder = b""
        self._first = True

    # -- public --------------------------------------------------------------

    def poll(self) -> TailBatch:
        if not self.logs_root.is_dir():
            return self._problem_batch(Reason.NO_LOGS_ROOT)
        try:
            newest = newest_power_log(self.logs_root)
        except OSError:
            return self._problem_batch(Reason.UNREADABLE)
        if newest is None:
            return self._problem_batch(Reason.NO_POWER_LOG)

        if self.path is None or newest != self.path:
            reset = START if self._first else NEW_SESSION
            return self._attach(newest, reset)
        try:
            return self._read_more()
        except OSError:
            return self._problem_batch(Reason.UNREADABLE)

    # -- internals -----------------------------------------------------------

    def _problem_batch(self, problem: str) -> TailBatch:
        # The problem is reported on every poll. The file position is dropped: after
        # recovery the tail re-attaches and catches up from the last CREATE_GAME.
        self.path = None
        self._remainder = b""
        return TailBatch(problem=problem, session=self.session)

    def _attach(self, path: Path, reset: str) -> TailBatch:
        """(Re)start on a file: silently catch up from its last CREATE_GAME."""
        try:
            offset, complete_end = find_last_create_game(path)
            self.path = path
            self.session = path.parent.name if path.parent != self.logs_root else None
            self._first = False
            self._remainder = b""
            self._offset = offset if offset is not None else complete_end
            with path.open("rb") as file:
                self._identity = _identity(os.fstat(file.fileno()))
            batch = self._read_more()
        except OSError:
            self.path = None
            return self._problem_batch(Reason.UNREADABLE)
        batch.reset = reset
        batch.has_game = offset is not None
        return batch

    def _read_more(self) -> TailBatch:
        assert self.path is not None
        with self.path.open("rb") as file:
            stat = os.fstat(file.fileno())
            identity = _identity(stat)
            if (
                stat.st_size < self._offset + len(self._remainder)
                or (self._identity is not None and identity is not None and identity != self._identity)
            ):
                return self._attach_after_discontinuity()
            file.seek(self._offset + len(self._remainder))
            data = file.read()
        start = self._offset
        buffered = self._remainder + data
        cut = buffered.rfind(b"\n")
        if cut == -1:
            self._remainder = buffered
            return TailBatch(session=self.session, start_offset=start, end_offset=start, partial=bool(buffered))
        complete, self._remainder = buffered[: cut + 1], buffered[cut + 1:]
        self._offset = start + len(complete)
        text = complete.decode("utf-8", errors="replace")
        lines = [line.rstrip("\r") for line in text.split("\n")[:-1]]
        return TailBatch(lines=lines, session=self.session, start_offset=start, end_offset=self._offset,
                         partial=bool(self._remainder))

    def _attach_after_discontinuity(self) -> TailBatch:
        assert self.path is not None
        return self._attach(self.path, FILE_DISCONTINUITY)
