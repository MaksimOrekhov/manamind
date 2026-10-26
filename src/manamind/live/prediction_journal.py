"""Append-only local record of displayed recommendations and their invalidation."""
from __future__ import annotations

import json
import hashlib
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from .recommendation import Recommendation
from .snapshot import Snapshot, canonical_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decision_id(snapshot: Snapshot) -> str:
    return f"{snapshot.game_key}:{snapshot.seq}:{snapshot.decision['options_id']}:{snapshot.state_hash}"


SHADOW_MAX_BYTES = 64 * 1024 * 1024


def _rotation_stamp() -> str:
    """Informational time in an archive name. Uniqueness never depends on it (see ``_archive_target``)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _archive_target(path: Path) -> Path:
    """Reserve a fresh archive name ``<stem>.<stamp>.<index>.jsonl`` for ``path`` and return it.

    The index is one more than the highest index among the archives already on disk (older ``<stem>.<stamp>.jsonl``
    archives count as index 0), so it grows with every rotation, survives restarts and ignores the clock. The name is
    then created with ``open(..., "x")`` (O_EXCL: atomic, fails if anything already has that name on Windows and
    Linux); on ``FileExistsError`` the next index is tried. An existing archive is therefore never replaced, even by a
    concurrent writer. The caller owns the empty placeholder this leaves behind.
    """
    pattern = re.compile(rf"^{re.escape(path.stem)}\.\d{{8}}T\d{{12}}Z(?:\.(\d+))?\.jsonl$")
    taken = [int(m.group(1) or 0) for entry in path.parent.iterdir() if (m := pattern.match(entry.name))]
    index = max(taken, default=0) + 1
    stamp = _rotation_stamp()
    while True:
        target = path.with_name(f"{path.stem}.{stamp}.{index:06d}.jsonl")
        try:
            with target.open("x"):
                return target
        except FileExistsError:
            index += 1


class PredictionJournal:
    """Store only sanitized action descriptors, hashes and stable game identity.

    The outcome shadow (ACTION-OUTCOME-2) writes to its own append-only file next to this journal so that the
    format and the growth of the RECOMMENDATION stream stay exactly what they were; rows of both files join on
    ``decision_id``. The shadow file is created only when the shadow is switched on. At ``shadow_max_bytes`` it is
    renamed (never deleted or truncated) to ``<name>.<UTC time>.<index>.jsonl`` and a fresh file is started, so one file
    never grows without bound and no row is lost; archive or analyze the rotated files at will. Guarantees: a rotation
    never overwrites an existing archive (reserved with O_EXCL, index independent of the clock); within one process
    appends and rotations are serialised; if a rotation fails the active file keeps growing and every row is still
    appended (``rotation_failures`` counts the failures). One process per journal directory is the supported model. The strategy shadow
    (STRATEGIC-SCORER-1) follows the same rules in its own ``<stem>.strategy_shadow.jsonl``.
    """

    def __init__(self, path: Path, *, shadow_path: Path | None = None,
                 shadow_max_bytes: int = SHADOW_MAX_BYTES, feedback_path: Path | None = None,
                 strategy_path: Path | None = None) -> None:
        self.path = Path(path)
        self.feedback_path = (Path(feedback_path) if feedback_path is not None
                              else self.path.with_name("decision_feedback.jsonl"))
        self.shadow_path = (Path(shadow_path) if shadow_path is not None
                            else self.path.with_name(f"{self.path.stem}.outcome_shadow.jsonl"))
        self.strategy_path = (Path(strategy_path) if strategy_path is not None
                              else self.path.with_name(f"{self.path.stem}.strategy_shadow.jsonl"))
        self.shadow_max_bytes = shadow_max_bytes
        self.rotation_failures = 0
        self._lock = threading.Lock()

    def _append(self, event: dict, path: Path | None = None) -> None:
        target = self.path if path is None else path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as file:
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

    def suspicious(self, snapshot: Snapshot, recommendation: Recommendation,
                   checkpoint_sha256: str) -> None:
        """Record an unassessed user flag and the exact legal menu; never a preference label."""
        if (recommendation.identity != (snapshot.game_key, snapshot.seq,
                                        snapshot.decision.get("options_id"), snapshot.state_hash)
                or not recommendation.menu):
            raise ValueError("Feedback must reference the displayed complete recommendation")
        menu = [{"menu_index": item.index, "policy_rank": rank, "action": dict(item.action),
                 "action_sha256": hashlib.sha256(canonical_json(item.action).encode("utf-8")).hexdigest()}
                for rank, item in enumerate(recommendation.menu, 1)]
        top3 = [{"rank": rank, "action": dict(item.action)}
                for rank, item in enumerate(recommendation.ranked, 1)]
        self._append({
            "schema": "manamind.live_feedback/1",
            "event": "SUSPECTED_RECOMMENDATION",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "checkpoint_sha256": checkpoint_sha256,
            "flagged_at_utc": _utc_now(),
            "assessment": "UNASSESSED",
            "top3": top3,
            "legal_menu": menu,
        }, self.feedback_path)

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

    def unavailable(self, snapshot: Snapshot, reason: str) -> None:
        """Record a stable scorer refusal without persisting exception or log text."""
        self._append({
            "event": "UNAVAILABLE",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "at_utc": _utc_now(),
            "reason": reason,
            "observed_action": {"status": "UNKNOWN"},
        })

    def discarded(self, snapshot: Snapshot, reason: str) -> None:
        """Record a scored result dropped after the decision changed during inference."""
        self._append({
            "event": "DISCARDED",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "at_utc": _utc_now(),
            "reason": reason,
            "observed_action": {"status": "UNKNOWN"},
        })

    # -- outcome shadow (ACTION-OUTCOME-2) ---------------------------------------------------------------------

    def _append_rotating(self, event: dict, path: Path) -> None:
        with self._lock:
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                size = 0
            if size >= self.shadow_max_bytes:
                self._rotate(path)
            self._append(event, path)

    def _rotate(self, path: Path) -> None:
        """Move the full active file to a new unique archive; on any OS error leave everything as it was."""
        target = None
        try:
            target = _archive_target(path)
            os.replace(path, target)        # replaces only the empty placeholder reserved just above
        except OSError:
            self.rotation_failures += 1
            if target is not None:
                try:
                    if target.stat().st_size == 0:
                        target.unlink()
                except OSError:
                    pass

    def _append_shadow(self, event: dict) -> None:
        self._append_rotating(event, self.shadow_path)

    def outcome_shadow(self, snapshot: Snapshot, record: dict) -> None:
        """One row per displayed decision: the compact forecast of its whole menu (see ``outcome.shadow``)."""
        self._append_shadow({
            "event": "OUTCOME_SHADOW",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "seq": snapshot.seq,
            "options_id": snapshot.decision["options_id"],
            "state_hash": snapshot.state_hash,
            "at_utc": _utc_now(),
            **record,
        })

    def outcome_shadow_error(self, snapshot: Snapshot, reason: str) -> None:
        """A shadow that failed or was discarded; ``reason`` is a stable code, never exception or log text."""
        self._append_shadow({
            "event": "OUTCOME_SHADOW_ERROR",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "at_utc": _utc_now(),
            "reason": reason,
        })

    def outcome_shadow_invalidation(self, snapshot: Snapshot, reason: str) -> None:
        """The decision a shadow row belongs to is no longer current: its forecasts are history, not advice."""
        self._append_shadow({
            "event": "OUTCOME_SHADOW_INVALIDATION",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "at_utc": _utc_now(),
            "reason": reason,
        })

    # -- strategy shadow (STRATEGIC-SCORER-1) ------------------------------------------------------------------

    def _append_strategy(self, event: dict) -> None:
        self._append_rotating(event, self.strategy_path)

    def strategy_shadow(self, snapshot: Snapshot, record: dict) -> None:
        """One row per displayed decision: the independent Strategic Scorer ranking of its whole menu."""
        self._append_strategy({
            "event": "STRATEGY_SHADOW",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "seq": snapshot.seq,
            "options_id": snapshot.decision["options_id"],
            "state_hash": snapshot.state_hash,
            "at_utc": _utc_now(),
            **record,
        })

    def strategy_shadow_error(self, snapshot: Snapshot, reason: str) -> None:
        """A strategy shadow that failed; ``reason`` is a stable code, never exception or log text."""
        self._append_strategy({
            "event": "STRATEGY_SHADOW_ERROR",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "at_utc": _utc_now(),
            "reason": reason,
        })

    def strategy_shadow_invalidation(self, snapshot: Snapshot, reason: str) -> None:
        """The decision a strategy row belongs to is no longer current."""
        self._append_strategy({
            "event": "STRATEGY_SHADOW_INVALIDATION",
            "match_id": snapshot.game_key,
            "decision_id": decision_id(snapshot),
            "state_hash": snapshot.state_hash,
            "at_utc": _utc_now(),
            "reason": reason,
        })
