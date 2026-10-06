"""Deterministic replay of a recorded game: slice.log + tail_trace.jsonl -> snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from manamind.cards.catalog import CardCatalog

from .session import LiveSession
from .snapshot import Snapshot
from .trust import ModePolicy


def replay_game(directory: Path, catalog: CardCatalog) -> list[Snapshot]:
    directory = Path(directory)
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    policy = ModePolicy(frozenset(meta.get("extra_game_types", [])))
    text = (directory / "slice.log").read_text(encoding="utf-8")
    lines = text.split("\n")[:-1]
    rows = [
        json.loads(row)
        for row in (directory / "tail_trace.jsonl").read_text(encoding="utf-8").splitlines()
        if row.strip()
    ]

    session = LiveSession(catalog, policy)
    snapshots: list[Snapshot] = []
    index = 0
    for row in rows:
        count = int(row["n"])
        chunk = lines[index:index + count]
        index += count
        events = session.feed(chunk, int(row["t"])) if count else []
        events += session.tick(int(row["t"]))
        snapshots += [event for event in events if isinstance(event, Snapshot)]
    return snapshots


def recorded_hashes(directory: Path) -> list[str]:
    path = Path(directory) / "snapshots.jsonl"
    if not path.exists():
        return []
    return [json.loads(row)["state_hash"] for row in path.read_text(encoding="utf-8").splitlines() if row.strip()]


def verify_replay(directory: Path, catalog: CardCatalog) -> tuple[bool, list[str], list[str]]:
    """Return (identical, recorded hashes, replayed hashes)."""
    recorded = recorded_hashes(directory)
    replayed = [snapshot.state_hash for snapshot in replay_game(directory, catalog)]
    return recorded == replayed, recorded, replayed
