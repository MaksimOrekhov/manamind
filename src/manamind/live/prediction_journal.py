"""Append-only local record of displayed recommendations and their invalidation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .recommendation import Recommendation
from .snapshot import Snapshot


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decision_id(snapshot: Snapshot) -> str:
    return f"{snapshot.game_key}:{snapshot.seq}:{snapshot.decision['options_id']}:{snapshot.state_hash}"


class PredictionJournal:
    """Store only sanitized action descriptors, hashes and stable game identity."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _append(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            file.write("\n")
            file.flush()

    def recommendation(self, snapshot: Snapshot, recommendation: Recommendation,
                       checkpoint_sha256: str) -> None:
        self._append({
            "event": "RECOMMENDATION",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "checkpoint_sha256": checkpoint_sha256,
            "top3": [{"rank": rank, "action": dict(item.action)}
                     for rank, item in enumerate(recommendation.ranked, 1)],
            "recommended_at_utc": _utc_now(),
            "observed_action": {"status": "UNKNOWN"},
        })

    def invalidation(self, snapshot: Snapshot, reason: str) -> None:
        self._append({
            "event": "INVALIDATION",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "invalidated_at_utc": _utc_now(),
            "reason": reason,
            "observed_action": {"status": "UNKNOWN"},
        })
