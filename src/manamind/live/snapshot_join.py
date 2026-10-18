"""Conservative identity checks for repeated recorded LIVE snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .snapshot import canonical_json, state_hash


@dataclass(frozen=True)
class SnapshotJoinResult:
    """The one safely representable observation for an exact LIVE join key."""

    snapshot: dict | None
    source_rows: int
    reason: str | None = None


def collapse_identical_main_action_snapshots(rows: Iterable[dict]) -> SnapshotJoinResult:
    """Collapse repeated MAIN_ACTION snapshots only when they differ by ``seq`` alone.

    The caller groups rows by ``(game_key, options_id, state_hash)``. This function
    independently verifies that key, validates the state hash, and requires each
    repeated event to have a distinct positive sequence number. Every serialized
    field other than ``seq`` must be identical. Ambiguous or malformed groups fail
    closed and return no snapshot.
    """
    snapshots = list(rows)
    if not snapshots:
        return SnapshotJoinResult(None, 0, "NO_SNAPSHOT")

    first = snapshots[0]
    if not _valid_main_action_snapshot(first):
        return SnapshotJoinResult(None, len(snapshots), "INVALID_SNAPSHOT")
    if len(snapshots) == 1:
        return SnapshotJoinResult(first, 1)

    first_identity = _without_seq(first)
    first_key = _join_key(first)
    sequences: set[int] = set()
    for row in snapshots:
        if not _valid_main_action_snapshot(row):
            return SnapshotJoinResult(None, len(snapshots), "INVALID_SNAPSHOT")
        seq = row.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq <= 0:
            return SnapshotJoinResult(None, len(snapshots), "INVALID_SNAPSHOT_SEQ")
        if seq in sequences:
            return SnapshotJoinResult(None, len(snapshots), "AMBIGUOUS_SNAPSHOT_SEQ")
        sequences.add(seq)
        if _join_key(row) != first_key or canonical_json(_without_seq(row)) != canonical_json(first_identity):
            return SnapshotJoinResult(None, len(snapshots), "CONFLICTING_SNAPSHOTS")

    return SnapshotJoinResult(first, len(snapshots))


def _valid_main_action_snapshot(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    decision = row.get("decision")
    state = row.get("state")
    digest = row.get("state_hash")
    return (
        isinstance(decision, dict)
        and decision.get("kind") == "MAIN_ACTION"
        and isinstance(decision.get("options_id"), int)
        and not isinstance(decision.get("options_id"), bool)
        and isinstance(row.get("game_key"), str)
        and bool(row["game_key"])
        and isinstance(state, dict)
        and isinstance(digest, str)
        and len(digest) == 64
        and state_hash(state) == digest
    )


def _join_key(row: dict) -> tuple[str, int, str]:
    decision = row["decision"]
    return row["game_key"], int(decision["options_id"]), row["state_hash"]


def _without_seq(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "seq"}
