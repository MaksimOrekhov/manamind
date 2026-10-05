"""Automatically collect finished Ranked Standard matches from a growing Power.log.

Why this does not call the single-match tools on a whole log
------------------------------------------------------------
``hslog.LogParser.game_meta`` is ONE dict for the whole parse. Every
``GameType=`` / ``FormatType=`` line overwrites it, and a game that prints no such
line silently inherits the previous game's values. With several games in one file
the audited/imported mode would therefore be wrong or guessed.

What the log itself proves (checked against real logs and hslog 1.20 source): the
``GameState.DebugPrintGame()`` metadata lines are printed *inside* the section that
starts at each ``GameState.DebugPrintPower() - CREATE_GAME`` line, after that
game's entity/player header and before the next ``CREATE_GAME``. So the section
between two ``CREATE_GAME`` lines carries its own mode evidence. The collector
cuts the stream at those lines and treats each section as an independent game with
its own fresh parser. A game is admitted only if its own section has exactly one
consistent ``GameType`` and ``FormatType`` and an authoritative top-level
``GameEntity STATE=COMPLETE``. Anything else fails closed. Filename, modification
time and neighbouring games are never used as evidence.

The cut section (up to and including the COMPLETE line) is handed unchanged to the
existing ``audit_log`` and ``import_power_log``, which keep their one-game
contracts. EOF is never treated as completion.

Known limits are listed in docs/REAL_MATCH_DATA.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    from scripts.audit_power_log import audit_log
    from scripts.import_power_log import import_power_log
except ModuleNotFoundError:
    from audit_power_log import audit_log
    from import_power_log import import_power_log

IMPORTED = "IMPORTED"
SKIPPED_ALREADY_IMPORTED = "SKIPPED_ALREADY_IMPORTED"
SKIPPED_INCOMPLETE = "SKIPPED_INCOMPLETE"
SKIPPED_NOT_RANKED = "SKIPPED_NOT_RANKED"
SKIPPED_NOT_STANDARD = "SKIPPED_NOT_STANDARD"
SKIPPED_METADATA_AMBIGUOUS = "SKIPPED_METADATA_AMBIGUOUS"
SKIPPED_MID_GAME_START = "SKIPPED_MID_GAME_START"
PARSE_FAILED = "PARSE_FAILED"

# A decided game is never re-examined. INCOMPLETE and PARSE_FAILED are retried.
TERMINAL_STATUSES = frozenset({
    IMPORTED,
    SKIPPED_ALREADY_IMPORTED,
    SKIPPED_NOT_RANKED,
    SKIPPED_NOT_STANDARD,
    SKIPPED_METADATA_AMBIGUOUS,
    SKIPPED_MID_GAME_START,
})

STATE_VERSION = 1
RESULT_LABEL = {"WON": "WIN", "LOST": "LOSS", "TIED": "DRAW"}

_CREATE_GAME_RE = re.compile(r"^[DWE] \S+ GameState\.DebugPrintPower\(\) - CREATE_GAME\s*$")
_META_RE = re.compile(r"^[DWE] \S+ GameState\.DebugPrintGame\(\) - (GameType|FormatType)=(\w+)\s*$")
_COMPLETE_RE = re.compile(
    r"^[DWE] \S+ GameState\.DebugPrintPower\(\) - TAG_CHANGE Entity=GameEntity "
    r"tag=STATE value=COMPLETE\b"
)
_PLAYER_HEADER_RE = re.compile(r"GameState\.DebugPrintPower\(\) -\s+Player EntityID=")
_TURN_RE = re.compile(r"GameState\.DebugPrintPower\(\) -\s+tag=TURN value=(\d+)")


@dataclass
class SegmentInfo:
    """Facts proven from one CREATE_GAME section; contains no log text."""

    lines: list[str]
    start_key: str | None
    complete_index: int | None
    game_types: set[str]
    formats: set[str]
    mid_game_start: bool


@dataclass
class Stats:
    files_seen: set[str] = field(default_factory=set)
    games_seen: set[str] = field(default_factory=set)
    matches_imported: int = 0
    decision_states: int = 0
    duplicates: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    parse_failures: int = 0

    def as_dict(self) -> dict:
        return {
            "files_seen": len(self.files_seen),
            "games_seen": len(self.games_seen),
            "matches_imported": self.matches_imported,
            "decision_states": self.decision_states,
            "duplicates": self.duplicates,
            "skipped": dict(sorted(self.skipped.items())),
            "parse_failures": self.parse_failures,
        }

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())


def split_games(lines: list[str]) -> list[list[str]]:
    """Cut a log into per-game sections at every top-level CREATE_GAME line."""
    sections: list[list[str]] = []
    for line in lines:
        if _CREATE_GAME_RE.match(line):
            sections.append([])
        if sections:
            sections[-1].append(line)
    return sections


def inspect_segment(lines: list[str]) -> SegmentInfo:
    game_types: set[str] = set()
    formats: set[str] = set()
    complete_index: int | None = None
    header_end: int | None = None
    mid_game_start = False

    for index, line in enumerate(lines):
        if header_end is None and _PLAYER_HEADER_RE.search(line):
            header_end = index
        if header_end is None:
            turn = _TURN_RE.search(line)
            if turn and int(turn.group(1)) > 0:
                mid_game_start = True  # e.g. reconnect re-dump of a running game
        meta = _META_RE.match(line)
        if meta:
            (game_types if meta.group(1) == "GameType" else formats).add(meta.group(2))
        if complete_index is None and _COMPLETE_RE.match(line):
            complete_index = index

    # Identity: the CREATE_GAME header up to the first Player line. It contains the
    # per-game seed and stays identical while the file grows and across file copies.
    start_key = None
    if header_end is not None:
        digest = hashlib.sha256("\n".join(lines[:header_end]).encode("utf-8", "replace"))
        start_key = digest.hexdigest()
    return SegmentInfo(lines, start_key, complete_index, game_types, formats, mid_game_start)


def classify_metadata(info: SegmentInfo) -> str | None:
    """Return a skip status when the section's own evidence is not usable, else None."""
    if info.mid_game_start:
        return SKIPPED_MID_GAME_START
    if len(info.game_types) != 1 or len(info.formats) != 1:
        return SKIPPED_METADATA_AMBIGUOUS  # missing or conflicting within the game
    if next(iter(info.game_types)) != "GT_RANKED":
        return SKIPPED_NOT_RANKED
    if next(iter(info.formats)) != "FT_STANDARD":
        return SKIPPED_NOT_STANDARD
    return None


def read_complete_lines(path: Path) -> list[str]:
    """Read a possibly growing file; drop a trailing line that is not newline-terminated."""
    with path.open("r", encoding="utf-8", errors="replace", newline="") as file:
        text = file.read()
    lines = text.split("\n")
    lines.pop()  # '' after a final newline, otherwise a partially written last line
    return [line.rstrip("\r") for line in lines]


def candidate_files(logs_root: Path, max_sessions: int) -> list[Path]:
    """Power*.log directly in the root plus the newest ``max_sessions`` session folders.

    Bounded on purpose: older sessions are not rescanned on every poll.
    """
    found: dict[Path, None] = {}
    for path in sorted(logs_root.glob("Power*.log")):
        if path.is_file():
            found[path] = None
    sessions = [entry for entry in logs_root.glob("Hearthstone_*") if entry.is_dir()]
    sessions.sort(key=lambda entry: (_mtime(entry), entry.name), reverse=True)
    for session in sessions[:max_sessions]:
        for path in sorted(session.glob("Power*.log")):
            if path.is_file():
                found[path] = None
    return list(found)


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


class Collector:
    def __init__(
        self,
        logs_root: Path,
        raw_output: Path,
        processed_output: Path,
        catalog_path: Path,
        *,
        state_path: Path | None = None,
        max_sessions: int = 3,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        self.logs_root = Path(logs_root)
        self.raw_output = Path(raw_output)
        self.processed_output = Path(processed_output)
        self.catalog_path = Path(catalog_path)
        self.state_path = Path(state_path) if state_path else self.raw_output / "collector_state.json"
        self.max_sessions = max_sessions
        self.emit = emit or (lambda message: print(message, flush=True))
        self.stats = Stats()
        self._known: dict[str, str] = self._load_state()
        self._signatures: dict[Path, tuple[int, int]] = {}
        self._announced: set[str] = set()
        self._failure_announced: set[str] = set()
        self._duplicate_seen: set[str] = set()

    # -- state ---------------------------------------------------------------

    def _load_state(self) -> dict[str, str]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            games = data.get("games", {}) if data.get("version") == STATE_VERSION else {}
            return {k: v for k, v in games.items() if v in TERMINAL_STATUSES}
        except (OSError, ValueError, AttributeError):
            return {}  # importer fingerprint dedup still protects against re-import

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": STATE_VERSION, "games": dict(sorted(self._known.items()))}
        _atomic_write(self.state_path, json.dumps(payload, indent=1))

    def write_summary(self) -> Path:
        path = self.raw_output / "collector_last_summary.json"
        self.raw_output.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(self.stats.as_dict(), indent=1))
        return path

    # -- scanning ------------------------------------------------------------

    def scan_once(self) -> None:
        for path in candidate_files(self.logs_root, self.max_sessions):
            try:
                self._scan_file(path)
            except Exception:  # never let one file stop a long-running collector
                self.stats.parse_failures += 1
                self._signatures.pop(path, None)

    def _scan_file(self, path: Path) -> None:
        stat = path.stat()
        signature = (stat.st_size, stat.st_mtime_ns)
        if self._signatures.get(path) == signature:
            return
        self.stats.files_seen.add(str(path))
        lines = read_complete_lines(path)
        failed = False
        for section in split_games(lines):
            info = inspect_segment(section)
            if info.start_key is None:
                continue  # CREATE_GAME header still being written
            self.stats.games_seen.add(info.start_key)
            if info.start_key in self._known:
                self._note_known(info.start_key)
                continue
            if self._process(info) == PARSE_FAILED:
                failed = True
        if not failed:
            self._signatures[path] = signature

    def _note_known(self, key: str) -> None:
        if self._known[key] in (IMPORTED, SKIPPED_ALREADY_IMPORTED) and key not in self._duplicate_seen:
            self._duplicate_seen.add(key)
            self.stats.duplicates += 1

    # -- one game ------------------------------------------------------------

    def _process(self, info: SegmentInfo) -> str:
        key = info.start_key
        assert key is not None
        verdict = classify_metadata(info)
        if verdict is None and info.complete_index is None:
            verdict = SKIPPED_INCOMPLETE
        if verdict is not None:
            return self._finish(key, verdict)

        self._announce(key)
        pending = self.raw_output / ".pending"
        pending.mkdir(parents=True, exist_ok=True)
        slice_path = pending / f"{key[:16]}.log"
        part_path = self.processed_output / f"{uuid.uuid4().hex}.jsonl.part"
        try:
            body = "\n".join(info.lines[: info.complete_index + 1]) + "\n"
            slice_path.write_text(body, encoding="utf-8", newline="\n")
            audit = audit_log(slice_path)
            if not audit.get("eligible_for_capture"):
                reason = str(audit.get("reason", ""))
                # Our section scan and the parser must agree on the mode.
                disagree = "Ranked" in reason or "Standard" in reason or "exactly one" in reason
                return self._finish(key, SKIPPED_METADATA_AMBIGUOUS if disagree else SKIPPED_INCOMPLETE)
            result = import_power_log(slice_path, part_path, self.catalog_path)
            if result.get("duplicate"):
                return self._finish(key, SKIPPED_ALREADY_IMPORTED)
            self.processed_output.mkdir(parents=True, exist_ok=True)
            os.replace(part_path, self.processed_output / f"{uuid.uuid4().hex}.jsonl")
            os.replace(slice_path, self.raw_output / f"{key[:16]}.log")
            return self._finish(key, IMPORTED, result)
        except Exception:  # privacy: report the status only, never the exception text
            return self._finish(key, PARSE_FAILED)
        finally:
            for leftover in (part_path, slice_path):
                try:
                    leftover.unlink()
                except OSError:
                    pass

    def _announce(self, key: str) -> None:
        if key not in self._announced:
            self._announced.add(key)
            self.emit(f"[{_now()}] match detected")

    def _finish(self, key: str, status: str, result: dict | None = None) -> str:
        if status == PARSE_FAILED:
            self.stats.parse_failures += 1
            if key not in self._failure_announced:
                self._failure_announced.add(key)
                self.emit(f"[{_now()}] could not process a match yet; will retry")
            return status
        if status == SKIPPED_INCOMPLETE:
            if key not in self._announced:
                self._announced.add(key)
                self.emit(f"[{_now()}] match in progress")
            return status

        if status == IMPORTED and result is not None:
            self.stats.matches_imported += 1
            self.stats.decision_states += int(result.get("examples_written", 0))
            label = RESULT_LABEL.get(str(result.get("result")), "?")
            self.emit(f"[{_now()}] Ranked Standard · {label} · {result.get('turns')} turns")
            self.emit(f"[{_now()}] imported {result.get('examples_written')} decision states")
        elif status == SKIPPED_ALREADY_IMPORTED:
            self.stats.duplicates += 1
            self._duplicate_seen.add(key)
            self.emit(f"[{_now()}] already imported (duplicate), skipped")
        else:
            self.stats.skipped[status] = self.stats.skipped.get(status, 0) + 1
            self.emit(f"[{_now()}] skipped: {status}")

        self._known[key] = status
        self._save_state()
        self.emit(
            f"[{_now()}] total session: {self.stats.matches_imported} imported, "
            f"{self.stats.skipped_total} skipped"
        )
        return status

    # -- loop ----------------------------------------------------------------

    def run(self, poll_seconds: float, once: bool = False) -> None:
        self.emit("ManaMind collector")
        self.emit(f"Watching: {self.logs_root}")
        try:
            self.scan_once()
            while not once:
                time.sleep(poll_seconds)
                self.scan_once()
        except KeyboardInterrupt:
            self.emit("Stopping…")
        finally:
            self.write_summary()
            summary = self.stats.as_dict()
            self.emit(
                "Summary: "
                f"{summary['matches_imported']} imported, {summary['duplicates']} duplicates, "
                f"{self.stats.skipped_total} skipped, {summary['parse_failures']} parse failures"
            )


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _atomic_write(path: Path, text: str) -> None:
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def main() -> int:
    env_root = os.environ.get("MANAMIND_HEARTHSTONE_LOGS")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--logs-root", type=Path, default=Path(env_root) if env_root else None,
        help="Hearthstone Logs folder (or set MANAMIND_HEARTHSTONE_LOGS)",
    )
    parser.add_argument("--once", action="store_true", help="scan once and exit")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--raw-output", type=Path, default=Path("data/raw/collected"))
    parser.add_argument("--processed-output", type=Path, default=Path("data/processed_real"))
    parser.add_argument("--cards", type=Path, default=Path("data/cards/standard_current_enUS.json"))
    parser.add_argument("--max-sessions", type=int, default=3,
                        help="newest Hearthstone_<timestamp> folders to scan (default 3)")
    args = parser.parse_args()

    if args.logs_root is None:
        parser.error("--logs-root is required (or set MANAMIND_HEARTHSTONE_LOGS)")
    if not args.logs_root.is_dir():
        parser.error(f"logs root does not exist: {args.logs_root}")
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")

    # Parser warnings may contain raw game text or player identifiers.
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    collector = Collector(
        args.logs_root, args.raw_output, args.processed_output, args.cards,
        max_sessions=args.max_sessions,
    )
    collector.run(args.poll_seconds, once=args.once)
    return 1 if args.once and collector.stats.parse_failures else 0


if __name__ == "__main__":
    sys.exit(main())
