"""Structured presentation events and a small, privacy-allowlisted overlay DTO."""
from __future__ import annotations

import copy
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from manamind.domain.policy_action import ACTION_FIELDS

from .instructions import instruction
from .localization import CardNames
from .recommendation import Recommendation
from .snapshot import Snapshot
from .trust import LiveStatus, Reason

_REASONS = frozenset(v for k, v in vars(Reason).items() if k.isupper()) | frozenset({
    "OPTIONS_CHANGED", "DECISION_CHANGED", "DECISION_CHANGED_DURING_INFERENCE", "APP_STOP", "GAME_OVER",
    "CHECKPOINT_UNAVAILABLE", "CHECKPOINT_IDENTITY_MISMATCH", "CHECKPOINT_INCOMPATIBLE", "LIVE_FAILED",
    "INFERENCE_FAILED", "INVALID_MODEL_OUTPUT", "PRIVACY_OR_STATE_MISMATCH", "RUNTIME_CATALOG_MISMATCH",
    "INCOMPLETE_MENU", "MENU_KIND_MISMATCH", "MENU_TARGET_MISMATCH", "INVALID_PUBLIC_CARD_ID",
    "UNSUPPORTED_ACTION", "NOT_CURRENT_READY_SELF", "UNTRUSTED_OR_UNSETTLED", "TARGET_UNRESOLVED",
    "CHOICE_UNRESOLVED", "AMBIGUOUS_SELECTION", "UNSUPPORTED_DECISION_KIND", "UNAVAILABLE",
})


def public_reason(reason: str) -> str:
    if reason in _REASONS:
        return reason
    parts = reason.split(":")
    if (len(parts) == 3 and parts[0] == "TRUST_LOST" and parts[1] in {s.value for s in LiveStatus}
            and parts[2] in _REASONS):
        return reason
    return "UNAVAILABLE"


@dataclass(frozen=True)
class PresentationEvent:
    kind: str
    status: str | None = None
    reason: str | None = None
    snapshot: Snapshot | None = None
    recommendation: Recommendation | None = None


class OverlayFeed:
    """Latest state only. Reloads read current data; no replay queue or cached advice."""
    def __init__(self, names: CardNames, *, clock=time.monotonic, policy_available: bool = True) -> None:
        self._names, self._clock = names, clock
        self._lock = threading.Lock()
        self._last_tick = clock()
        self._frame = {"schema": "manamind.overlay/1", "session": uuid.uuid4().hex,
                       "revision": 0, "status": "DISCONNECTED", "reason": None,
                       "policy_available": policy_available,
                       "turn": None, "generated_at": None, "recommendations": []}

    def heartbeat(self) -> None:
        with self._lock:
            self._last_tick = self._clock()

    def publish(self, event: PresentationEvent) -> None:
        with self._lock:
            self._frame["revision"] += 1
            self._frame.update(turn=None, generated_at=None, recommendations=[], reason=None)
            status = event.status or {"thinking": "THINKING", "invalidated": "SYNCING",
                                      "unavailable": "UNAVAILABLE"}.get(event.kind, "UNAVAILABLE")
            allowed = {"DISCONNECTED", "WAITING_FOR_GAME", "SYNCING", "READY", "UNTRUSTED",
                       "GAME_OVER", "THINKING", "UNAVAILABLE"}
            self._frame["status"] = status if status in allowed else "UNAVAILABLE"
            if event.reason:
                self._frame["reason"] = public_reason(event.reason)
            result, snap = event.recommendation, event.snapshot
            if event.kind == "recommendation" and result is not None and snap is not None:
                expected = (snap.game_key, snap.seq, snap.decision.get("options_id"), snap.state_hash)
                if result.identity != expected or snap.status != "READY" or snap.active_player != "SELF":
                    self._frame.update(status="UNAVAILABLE", reason="OPTIONS_CHANGED")
                    return
                rows = []
                for rank, item in enumerate(result.ranked, 1):
                    action = {k: v for k, v in item.action.items() if k in ACTION_FIELDS}
                    rows.append({"rank": rank, "action": action, "logit": item.score,
                                 "view": {lang: instruction(action, snap.state, self._names, lang)
                                          for lang in ("ru", "en")}})
                self._frame.update(status="READY", turn=result.turn, recommendations=rows,
                                   generated_at=datetime.now(timezone.utc).isoformat())

    def read(self) -> dict:
        with self._lock:
            if self._clock() - self._last_tick > 2 and self._frame["status"] != "DISCONNECTED":
                # Fail closed if the polling worker is blocked. It needs a fresh event to show advice again.
                self._frame.update(status="DISCONNECTED", reason="RUNTIME_TIMEOUT", recommendations=[],
                                   turn=None, generated_at=None, revision=self._frame["revision"] + 1)
            return copy.deepcopy(self._frame)
