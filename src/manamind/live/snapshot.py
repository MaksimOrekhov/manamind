"""Versioned live snapshot and the canonical state hash."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from manamind.domain.game_state import GameState

from . import SNAPSHOT_SCHEMA


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def state_to_dict(state: GameState) -> dict:
    """JSON-normalized (tuples become lists) so the dict equals what is serialized."""
    return json.loads(canonical_json(asdict(state)))


def state_hash(state_dict: dict) -> str:
    return hashlib.sha256(canonical_json(state_dict).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    seq: int
    status: str
    reason: str | None
    game_key: str
    session: str | None
    client_build: int | None
    game_type: str
    format: str
    phase: str
    turn: int
    active_player: str
    state: dict
    decision: dict
    state_hash: str
    source: dict

    def to_dict(self) -> dict:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "seq": self.seq,
            "status": self.status,
            "reason": self.reason,
            "game_key": self.game_key,
            "session": self.session,
            "source": self.source,
            "client_build": self.client_build,
            "game_type": self.game_type,
            "format": self.format,
            "phase": self.phase,
            "turn": self.turn,
            "active_player": self.active_player,
            "state": self.state,
            "decision": self.decision,
            "state_hash": self.state_hash,
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())
