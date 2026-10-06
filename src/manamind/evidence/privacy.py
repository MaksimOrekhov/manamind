"""Privacy scan of generated output against identifiers read from the *input*.

The sentinels (player names, BattleTags, account-id fragments) live only in memory and are never
printed; the result carries counts. Any leak fails the run and the output is removed.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME_LINE = re.compile(r"(?:PlayerName|Player)=([^\r\n,]*?)(?:\s+(?:TaskList|ChoiceType)=|[\r\n,]|$)")
BATTLETAG = re.compile(r"[^\s\"'\\\[\],=]{2,}#\d{3,6}")
ACCOUNT = re.compile(r"\b(?:hi|lo)=(\d{8,})")
FORBIDDEN_FRAGMENTS = ("PlayerName", "GameAccountId", "BattleTag", "BNetId", "[hi=", " lo=")
MIN_SENTINEL = 4


class PrivacyError(Exception):
    pass


def collect_sentinels(lines) -> set[str]:
    found: set[str] = set()
    for line in lines:
        if "Player" not in line and "#" not in line and "hi=" not in line and "lo=" not in line:
            continue
        for match in NAME_LINE.finditer(line):
            value = match.group(1).strip()
            if len(value) >= MIN_SENTINEL:
                found.add(value)
                stem = value.split("#")[0]
                if "#" in value and len(stem) >= MIN_SENTINEL:
                    found.add(stem)
        for match in BATTLETAG.finditer(line):
            found.add(match.group(0))
        for match in ACCOUNT.finditer(line):
            found.add(match.group(1))
    return {value for value in found if len(value) >= MIN_SENTINEL}


def scan_files(paths: list[Path], sentinels: set[str]) -> dict:
    """Counts only. ``leaks`` counts distinct sentinel/pattern hits across the files."""
    leaks = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        leaks += sum(1 for sentinel in sentinels if sentinel in text)
        leaks += len(BATTLETAG.findall(text))
        leaks += sum(1 for fragment in FORBIDDEN_FRAGMENTS if fragment in text)
    return {"files_scanned": len(paths), "sentinels_checked": len(sentinels), "leaks": leaks}
