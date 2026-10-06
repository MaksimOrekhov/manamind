"""Trust statuses, stable reason codes and the mode gate.

Reasons are fixed identifiers. They never contain log text, so they are safe to
print and store.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LiveStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    WAITING_FOR_GAME = "WAITING_FOR_GAME"
    SYNCING = "SYNCING"
    READY = "READY"
    UNTRUSTED = "UNTRUSTED"
    GAME_OVER = "GAME_OVER"


class Reason:
    NO_LOGS_ROOT = "NO_LOGS_ROOT"
    NO_POWER_LOG = "NO_POWER_LOG"
    UNREADABLE = "UNREADABLE"
    UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
    MODE_AMBIGUOUS = "MODE_AMBIGUOUS"
    SPECTATOR = "SPECTATOR"
    FILE_DISCONTINUITY = "FILE_DISCONTINUITY"
    ENTITY_UNKNOWN = "ENTITY_UNKNOWN"
    PARSE_ERROR = "PARSE_ERROR"
    INVARIANT = "INVARIANT"
    SELF_AMBIGUOUS = "SELF_AMBIGUOUS"
    SETTLE_TIMEOUT = "SETTLE_TIMEOUT"
    GAME_RESET = "GAME_RESET"
    RECONNECT = "RECONNECT"
    AWAITING_DECISION = "AWAITING_DECISION"
    AWAITING_SELF = "AWAITING_SELF"


# Only this developer-selectable game type may be added to Ranked Standard.
DEVELOPER_GAME_TYPES = frozenset({"GT_VS_AI"})


@dataclass(frozen=True)
class ModePolicy:
    """Ranked Standard always; extra game types only through an explicit developer option."""

    extra_game_types: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        unknown = set(self.extra_game_types) - DEVELOPER_GAME_TYPES
        if unknown:
            raise ValueError(f"unsupported developer mode: {sorted(unknown)}")

    def allows(self, game_type: str, format_type: str) -> bool:
        if game_type == "GT_RANKED" and format_type == "FT_STANDARD":
            return True
        return game_type in self.extra_game_types


@dataclass(frozen=True)
class StatusEvent:
    status: LiveStatus
    reason: str | None
    game_key: str | None = None

    def to_dict(self) -> dict:
        from . import STATUS_SCHEMA

        return {
            "schema": STATUS_SCHEMA,
            "status": self.status.value,
            "reason": self.reason,
            "game_key": self.game_key,
        }
