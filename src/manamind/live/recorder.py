"""Local recording of a live game for deterministic replay.

Layout (git-ignored, private)::

    data/raw/live/<session>/<game_key16>/
        slice.log         raw lines from CREATE_GAME on; contains player names, never share
        tail_trace.jsonl  one row per read batch: monotonic ms, line count, byte range
        snapshots.jsonl   the emitted sanitized snapshots
        status.jsonl      status transitions
        meta.json         versions and policy flags, no player data
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from .session import GameRun
from .snapshot import Snapshot, canonical_json
from .trust import ModePolicy, StatusEvent

BRIDGE_VERSION = "live-0b"


@dataclass
class _Cursor:
    directory: Path
    lines: int = 0
    rows: int = 0


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


class Recorder:
    def __init__(self, root: Path, *, catalog_path: Path | None = None, mode_policy: ModePolicy | None = None) -> None:
        self.root = Path(root)
        self.catalog_sha256 = _sha256(catalog_path) if catalog_path else None
        self.mode_policy = mode_policy or ModePolicy()
        self._cursors: dict[str, _Cursor] = {}

    def sync(self, session_name: str | None, games: list[GameRun], events: list) -> None:
        for game in games:
            if game.game_key is None or game.mode_state != "OK":
                continue
            cursor = self._cursor(session_name, game)
            self._write_slice(cursor, game)
            self._write_trace(cursor, game)
        for event in events:
            key = event.game_key
            cursor = self._cursors.get(key) if key else None
            if cursor is None:
                continue
            if isinstance(event, Snapshot):
                _append(cursor.directory / "snapshots.jsonl", event.to_json())
            elif isinstance(event, StatusEvent):
                _append(cursor.directory / "status.jsonl", canonical_json(event.to_dict()))

    # -- internals -----------------------------------------------------------

    def _cursor(self, session_name: str | None, game: GameRun) -> _Cursor:
        key = game.game_key
        cursor = self._cursors.get(key)
        if cursor is None:
            directory = self.root / (session_name or "session") / key[:16]
            directory.mkdir(parents=True, exist_ok=True)
            cursor = self._cursors[key] = _Cursor(directory)
            self._write_meta(cursor, game)
        return cursor

    def _write_meta(self, cursor: _Cursor, game: GameRun) -> None:
        meta = {
            "bridge_version": BRIDGE_VERSION,
            "snapshot_schema": "manamind.live.snapshot/1",
            "game_key": game.game_key,
            "client_build": game.build,
            "game_type": game.game_type,
            "format": game.format_type,
            "hslog": package_version("hslog"),
            "hearthstone": package_version("hearthstone"),
            "python": platform.python_version(),
            "catalog_sha256": self.catalog_sha256,
            "extra_game_types": sorted(self.mode_policy.extra_game_types),
            "opponent_identity_policy": "none",
        }
        (cursor.directory / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8", newline="\n")

    @staticmethod
    def _write_slice(cursor: _Cursor, game: GameRun) -> None:
        path = cursor.directory / "slice.log"
        if len(game.lines) < cursor.lines:
            cursor.lines = 0
            path.write_text("", encoding="utf-8")
        new = game.lines[cursor.lines:]
        if new:
            with path.open("a", encoding="utf-8", newline="\n") as file:
                file.write("\n".join(new) + "\n")
            cursor.lines = len(game.lines)

    @staticmethod
    def _write_trace(cursor: _Cursor, game: GameRun) -> None:
        path = cursor.directory / "tail_trace.jsonl"
        if len(game.trace) < cursor.rows:
            cursor.rows = 0
            path.write_text("", encoding="utf-8")
        for row in game.trace[cursor.rows:]:
            _append(path, canonical_json(row))
        cursor.rows = len(game.trace)


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(text + "\n")


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None
