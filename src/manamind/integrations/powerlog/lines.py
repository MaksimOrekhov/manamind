"""Newline-safe Power.log reading and per-game segmentation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

CREATE_GAME_RE = re.compile(r"^[DWE] \S+ GameState\.DebugPrintPower\(\) - CREATE_GAME\s*$")
META_RE = re.compile(r"^[DWE] \S+ GameState\.DebugPrintGame\(\) - (GameType|FormatType)=(\w+)\s*$")
COMPLETE_RE = re.compile(
    r"^[DWE] \S+ GameState\.DebugPrintPower\(\) - TAG_CHANGE Entity=GameEntity "
    r"tag=STATE value=COMPLETE\b"
)
PLAYER_HEADER_RE = re.compile(r"GameState\.DebugPrintPower\(\) -\s+Player EntityID=")
TURN_RE = re.compile(r"GameState\.DebugPrintPower\(\) -\s+tag=TURN value=(\d+)")


@dataclass
class SegmentInfo:
    """Facts proven from one CREATE_GAME section; contains no log text."""

    lines: list[str]
    start_key: str | None
    complete_index: int | None
    game_types: set[str]
    formats: set[str]
    mid_game_start: bool


def split_games(lines: list[str]) -> list[list[str]]:
    """Cut a log into per-game sections at every top-level CREATE_GAME line."""
    sections: list[list[str]] = []
    for line in lines:
        if CREATE_GAME_RE.match(line):
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
        if header_end is None and PLAYER_HEADER_RE.search(line):
            header_end = index
        if header_end is None:
            turn = TURN_RE.search(line)
            if turn and int(turn.group(1)) > 0:
                mid_game_start = True  # e.g. reconnect re-dump of a running game
        meta = META_RE.match(line)
        if meta:
            (game_types if meta.group(1) == "GameType" else formats).add(meta.group(2))
        if complete_index is None and COMPLETE_RE.match(line):
            complete_index = index

    # Identity: the CREATE_GAME header up to the first Player line. It contains the
    # per-game seed and stays identical while the file grows and across file copies.
    start_key = None
    if header_end is not None:
        start_key = game_key_from_header(lines[:header_end])
    return SegmentInfo(lines, start_key, complete_index, game_types, formats, mid_game_start)


def game_key_from_header(header_lines: list[str]) -> str:
    digest = hashlib.sha256("\n".join(header_lines).encode("utf-8", "replace"))
    return digest.hexdigest()


def read_complete_lines(path: Path) -> list[str]:
    """Read a possibly growing file; drop a trailing line that is not newline-terminated."""
    with path.open("r", encoding="utf-8", errors="replace", newline="") as file:
        text = file.read()
    lines = text.split("\n")
    lines.pop()  # '' after a final newline, otherwise a partially written last line
    return [line.rstrip("\r") for line in lines]
