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
from collections import Counter
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

from .session import GameRun
from .snapshot import Snapshot, canonical_json
from .trust import ModePolicy, StatusEvent

BRIDGE_VERSION = "live-0b"


@dataclass
class _Cursor:
    directory: Path
    game_id: int | None = None
    lines: int = 0
    rows: int = 0
    saved_snapshots: dict[tuple[int, str], dict] | None = None
    snapshot_count: int = 0
    capture_totals: dict = field(default_factory=dict)
    trusted_snapshots_seen: int = 0
    failure_counts_seen: Counter[str] = field(default_factory=Counter)
    resume_trace_pending: bool = False
    resume_snapshot_pending: bool = False


class RecordingResumeError(OSError):
    """An existing recording does not match the game history being resumed."""


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
        self._resume_indexes: dict[Path, tuple[dict[tuple[int, str], dict], int]] = {}
        self._games: dict[str, GameRun] = {}
        self._recording_failures: Counter[str] = Counter()
        self._recording_failures_by_game: dict[str, Counter[str]] = {}
        self._disabled_games: dict[str, str] = {}

    def sync(self, session_name: str | None, games: list[GameRun], events: list) -> None:
        touched: dict[str, tuple[_Cursor, GameRun, bool]] = {}
        for game in games:
            if game.game_key is None or game.mode_state != "OK" or game.game_key in self._disabled_games:
                continue
            cursor = self._cursor(session_name, game)
            self._games[game.game_key] = game
            changed = self._write_slice(cursor, game)
            changed = self._write_trace(cursor, game) or changed
            touched[game.game_key] = cursor, game, changed
        for event in events:
            key = event.game_key
            if key in self._disabled_games:
                continue
            cursor = self._cursors.get(key) if key else None
            if cursor is None:
                continue
            if isinstance(event, Snapshot):
                self._append_snapshot(cursor, event)
                if key in touched:
                    c, game, _ = touched[key]
                    touched[key] = c, game, True
            elif isinstance(event, StatusEvent):
                _append(cursor.directory / "status.jsonl", canonical_json(event.to_dict()))
                if key in touched:
                    c, game, _ = touched[key]
                    touched[key] = c, game, True
        for cursor, game, changed in touched.values():
            totals_changed = self._update_capture_totals(cursor, game)
            if changed or totals_changed or game.ended:
                self._write_capture_summary(cursor, game, update=False)

    def sequence_for(self, session_name: str | None, game_key: str, options_id: int,
                     digest: str) -> tuple[int | None, int]:
        """Reuse an identical last-process decision identity; otherwise continue its sequence."""
        current = self.root / (session_name or "session") / game_key[:16]
        candidates = {current, *self.root.glob(f"*/{game_key[:16]}")}
        max_seq = 0
        matching_sequences: list[int] = []
        for directory in sorted(candidates):
            try:
                rows, last_seq = self._resume_index(directory, game_key)
            except RecordingResumeError:
                if directory == current:
                    raise
                continue
            max_seq = max(max_seq, last_seq)
            row = rows.get((options_id, digest))
            if row is not None:
                matching_sequences.append(int(row["seq"]))
        return (min(matching_sequences) if matching_sequences else None), max_seq

    def note_failure(self, code: str) -> None:
        self._recording_failures[code] += 1

    def note_match_failure(self, game_key: str, code: str) -> None:
        self._recording_failures[code] += 1
        self._recording_failures_by_game.setdefault(game_key, Counter())[code] += 1

    def disable_game(self, game_key: str, code: str) -> None:
        """Stop writes for a match whose existing recording cannot be resumed safely."""
        self._disabled_games[game_key] = code

    def capture_summary_for(self, game_key: str) -> dict | None:
        cursor = self._cursors.get(game_key)
        game = self._games.get(game_key)
        if cursor is None or game is None:
            return None
        self._update_capture_totals(cursor, game)
        return {**cursor.capture_totals, "game_key": game_key,
                "capture_status": "COMPLETE" if game.ended else "ACTIVE",
                "counter_scope": "CUMULATIVE_MATCH"}

    def snapshot_count_for(self, game_key: str) -> int:
        cursor = self._cursors.get(game_key)
        return cursor.snapshot_count if cursor is not None else 0

    def finalize(self) -> None:
        for key, cursor in self._cursors.items():
            game = self._games.get(key)
            if game is not None:
                self._write_capture_summary(cursor, game)

    # -- internals -----------------------------------------------------------

    def _cursor(self, session_name: str | None, game: GameRun) -> _Cursor:
        key = game.game_key
        cursor = self._cursors.get(key)
        if cursor is None:
            directory = self.root / (session_name or "session") / key[:16]
            directory.mkdir(parents=True, exist_ok=True)
            rows, _ = self._resume_index(directory, key, game.lines)
            slice_path = directory / "slice.log"
            existing_lines = len(slice_path.read_text(encoding="utf-8").splitlines()) if slice_path.exists() else 0
            snapshot_count = _jsonl_count(directory / "snapshots.jsonl")
            capture_totals = self._load_capture_totals(directory, key, snapshot_count)
            cursor = self._cursors[key] = _Cursor(
                directory=directory,
                game_id=id(game),
                lines=existing_lines,
                saved_snapshots=rows,
                snapshot_count=snapshot_count,
                capture_totals=capture_totals,
                resume_trace_pending=bool(existing_lines),
                resume_snapshot_pending=bool(rows),
            )
            if not (directory / "meta.json").exists():
                self._write_meta(cursor, game)
        elif cursor.game_id != id(game):
            self._validate_existing_prefix(cursor.directory, key, game.lines)
            cursor.game_id = id(game)
            cursor.rows = 0
            resumed_catchup = any(row.get("catchup") for row in game.trace)
            cursor.resume_trace_pending = resumed_catchup
            cursor.resume_snapshot_pending = resumed_catchup
        return cursor

    @staticmethod
    def _load_capture_totals(directory: Path, game_key: str, snapshot_count: int) -> dict:
        path = directory / "capture_summary.json"
        summary = {}
        if path.exists():
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise RecordingResumeError("capture summary is unreadable") from error
            if not isinstance(summary, dict) or summary.get("game_key") != game_key:
                raise RecordingResumeError("capture summary identity mismatch")
            if summary.get("schema") != "manamind.live.capture/1":
                raise RecordingResumeError("capture summary schema mismatch")
            for name in ("options_packets_seen", "trusted_snapshots_emitted", "snapshots_saved",
                         "superseded_menus"):
                if name in summary and not _is_nonnegative_count(summary[name]):
                    raise RecordingResumeError("capture summary counter is invalid")
            for name in ("trust_rejections", "recording_failures"):
                if name in summary and not _is_count_mapping(summary[name]):
                    raise RecordingResumeError("capture summary counter map is invalid")
            saved_count = _nonnegative_count(summary.get("snapshots_saved"))
            if saved_count > snapshot_count:
                raise RecordingResumeError("capture summary snapshot count mismatch")
        result = {
            "options_packets_seen": _nonnegative_count(summary.get("options_packets_seen")),
            "trusted_snapshots_emitted": max(
                snapshot_count, _nonnegative_count(summary.get("trusted_snapshots_emitted"))
            ),
            "snapshots_saved": snapshot_count,
            "trust_rejections": _count_mapping(summary.get("trust_rejections")),
            "superseded_menus": _nonnegative_count(summary.get("superseded_menus")),
            "recording_failures": _count_mapping(summary.get("recording_failures")),
        }
        return result

    @staticmethod
    def _validate_existing_prefix(directory: Path, game_key: str, current_lines: list[str]) -> None:
        meta_path = directory / "meta.json"
        slice_path = directory / "slice.log"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            previous = slice_path.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError) as error:
            raise RecordingResumeError("recording metadata or slice is unreadable") from error
        if meta.get("game_key") != game_key or len(current_lines) < len(previous) or current_lines[:len(previous)] != previous:
            raise RecordingResumeError("recording slice does not match resumed game")

    def _resume_index(self, directory: Path, game_key: str,
                      current_lines: list[str] | None = None) -> tuple[dict[tuple[int, str], dict], int]:
        cached = self._resume_indexes.get(directory)
        if cached is None:
            meta_path = directory / "meta.json"
            slice_path = directory / "slice.log"
            snapshot_path = directory / "snapshots.jsonl"
            has_content = any(path.exists() for path in (slice_path, snapshot_path,
                                                           directory / "tail_trace.jsonl"))
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as error:
                    raise RecordingResumeError("invalid recording metadata") from error
                if meta.get("game_key") != game_key:
                    raise RecordingResumeError("recording game key mismatch")
            elif has_content:
                raise RecordingResumeError("recording metadata is missing")
            snapshots: dict[tuple[int, str], dict] = {}
            max_seq = 0
            if snapshot_path.exists():
                try:
                    for text in snapshot_path.read_text(encoding="utf-8").splitlines():
                        if not text.strip():
                            continue
                        row = json.loads(text)
                        options_id = int(row["decision"]["options_id"])
                        digest = str(row["state_hash"])
                        seq = int(row["seq"])
                        if seq < 1 or row.get("game_key") != game_key:
                            raise ValueError("invalid snapshot identity")
                        max_seq = max(max_seq, seq)
                        snapshots.setdefault((options_id, digest), row)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    raise RecordingResumeError("invalid recorded snapshot index") from error
            if slice_path.exists() and (directory / "tail_trace.jsonl").exists():
                try:
                    trace_rows = [json.loads(row) for row in
                                  (directory / "tail_trace.jsonl").read_text(encoding="utf-8").splitlines()
                                  if row.strip()]
                    if sum(int(row["n"]) for row in trace_rows) != len(
                            slice_path.read_text(encoding="utf-8").splitlines()):
                        raise ValueError("trace line count mismatch")
                except (OSError, ValueError, KeyError, TypeError) as error:
                    raise RecordingResumeError("invalid recorded trace") from error
            cached = (snapshots, max_seq)
            self._resume_indexes[directory] = cached
        if current_lines is not None:
            path = directory / "slice.log"
            if path.exists():
                try:
                    previous = path.read_text(encoding="utf-8").splitlines()
                except OSError as error:
                    raise RecordingResumeError("recording slice is unreadable") from error
                if len(current_lines) < len(previous) or current_lines[:len(previous)] != previous:
                    raise RecordingResumeError("recording slice does not match resumed game")
                trace_path = directory / "tail_trace.jsonl"
                if not trace_path.exists():
                    raise RecordingResumeError("recording trace is missing")
                try:
                    traces = [json.loads(row) for row in trace_path.read_text(encoding="utf-8").splitlines()
                              if row.strip()]
                    if sum(int(row["n"]) for row in traces) != len(previous):
                        raise ValueError("trace line count mismatch")
                except (OSError, ValueError, KeyError, TypeError) as error:
                    raise RecordingResumeError("invalid recorded trace") from error
        return cached

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
    def _write_slice(cursor: _Cursor, game: GameRun) -> bool:
        path = cursor.directory / "slice.log"
        if len(game.lines) < cursor.lines:
            raise RecordingResumeError("game log became shorter than the recording cursor")
        new = game.lines[cursor.lines:]
        if new:
            with path.open("a", encoding="utf-8", newline="\n") as file:
                file.write("\n".join(new) + "\n")
            cursor.lines = len(game.lines)
            return True
        return False

    @staticmethod
    def _write_trace(cursor: _Cursor, game: GameRun) -> bool:
        path = cursor.directory / "tail_trace.jsonl"
        if len(game.trace) < cursor.rows:
            cursor.rows = 0
        changed = False
        for row in game.trace[cursor.rows:]:
            recorded = row
            if cursor.resume_trace_pending and row.get("catchup"):
                # During an app restart, historical lines already present in slice.log are
                # replayed silently. Only the newly appended suffix belongs in this trace.
                old_line_count = sum(int(item.get("n", 0)) for item in _existing_trace_rows(path))
                added = max(0, cursor.lines - old_line_count)
                recorded = {**row, "n": min(int(row.get("n", 0)), added)}
                cursor.resume_trace_pending = False
                if recorded["n"] == 0:
                    continue
            _append(path, canonical_json(recorded))
            changed = True
        cursor.rows = len(game.trace)
        return changed

    @staticmethod
    def _identity(row: dict) -> tuple[int, str]:
        return int(row["decision"]["options_id"]), str(row["state_hash"])

    def _append_snapshot(self, cursor: _Cursor, snapshot: Snapshot) -> None:
        row = snapshot.to_dict()
        identity = self._identity(row)
        saved = cursor.saved_snapshots if cursor.saved_snapshots is not None else {}
        previous = saved.get(identity)
        if cursor.resume_snapshot_pending and previous is not None:
            left, right = dict(previous), dict(row)
            left.pop("seq", None)
            right.pop("seq", None)
            if canonical_json(left) != canonical_json(right):
                raise RecordingResumeError("resumed snapshot identity conflicts with saved row")
            cursor.resume_snapshot_pending = False
            return
        _append(cursor.directory / "snapshots.jsonl", snapshot.to_json())
        saved[identity] = row
        cursor.saved_snapshots = saved
        cursor.snapshot_count += 1
        cursor.resume_snapshot_pending = False

    def _update_capture_totals(self, cursor: _Cursor, game: GameRun) -> bool:
        totals = cursor.capture_totals
        before = canonical_json(totals)
        totals["options_packets_seen"] = max(
            int(totals.get("options_packets_seen", 0)), game.options_packets_seen
        )
        effective_trusted = max(0, game.trusted_snapshots - game.resumed_snapshot_duplicates)
        trusted_delta = max(0, effective_trusted - cursor.trusted_snapshots_seen)
        totals["trusted_snapshots_emitted"] = int(totals.get("trusted_snapshots_emitted", 0)) + trusted_delta
        cursor.trusted_snapshots_seen = max(cursor.trusted_snapshots_seen, effective_trusted)
        totals["snapshots_saved"] = cursor.snapshot_count
        reasons = Counter(totals.get("trust_rejections", {}))
        for reason, count in game.trust_rejections.items():
            reasons[reason] = max(reasons[reason], count)
        totals["trust_rejections"] = dict(sorted(reasons.items()))
        totals["superseded_menus"] = max(int(totals.get("superseded_menus", 0)), game.gate.superseded)
        failures = Counter(totals.get("recording_failures", {}))
        current_failures = self._recording_failures_by_game.get(game.game_key or "", Counter())
        for code, count in current_failures.items():
            previous_count = cursor.failure_counts_seen[code]
            if count > previous_count:
                failures[code] += count - previous_count
                cursor.failure_counts_seen[code] = count
        totals["recording_failures"] = dict(sorted(failures.items()))
        return before != canonical_json(totals)

    def _write_capture_summary(self, cursor: _Cursor, game: GameRun, *, update: bool = True) -> None:
        if update:
            self._update_capture_totals(cursor, game)
        payload = {
            "schema": "manamind.live.capture/1",
            "game_key": game.game_key,
            "capture_status": "COMPLETE" if game.ended else "ACTIVE",
            **cursor.capture_totals,
        }
        target = cursor.directory / "capture_summary.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n",
                              encoding="utf-8", newline="\n")
        temporary.replace(target)


def _existing_trace_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines() if row.strip()]
    except (OSError, ValueError):
        return []


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(bool(row.strip()) for row in path.read_text(encoding="utf-8").splitlines())
    except OSError as error:
        raise RecordingResumeError("recorded snapshot file is unreadable") from error


def _nonnegative_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _is_nonnegative_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_count_mapping(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and _is_nonnegative_count(count) for key, count in value.items()
    )


def _count_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(text + "\n")


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None
