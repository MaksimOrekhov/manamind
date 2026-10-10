"""Read-only ranking of one current, complete LIVE MAIN_ACTION decision."""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path

import torch

from manamind.domain.policy_action import ACTION_FIELDS, ACTION_TYPES
from manamind.domain.serialization import game_state_from_dict
from manamind.integrations.powerlog.policy_actions import ActionMappingError, map_actions
from manamind.models.policy_inputs import encode_policy_inputs, representation_of
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint

from .session import LiveSession
from .snapshot import Snapshot, state_hash, state_to_dict
from .trust import LiveStatus

REVIEWED_CHECKPOINT_SHA256 = "5a5e3435c0dcda5ce69bcd0a48dc8521fb3696e2a7794e268b894efbf7e3e95e"
_PUBLIC_ID = re.compile(r"[A-Za-z0-9_]+\Z")


class RecommendationUnavailable(ValueError):
    """Stable reason only; exception text from a log or checkpoint is never printed."""


@dataclass(frozen=True)
class RankedAction:
    index: int
    score: float
    action: dict


@dataclass(frozen=True)
class Recommendation:
    identity: tuple[str, int, int, str]
    turn: int
    menu_size: int
    ranked: tuple[RankedAction, ...]
    latency_ms: float


def _validate_snapshot(snapshot: Snapshot, session: LiveSession):
    if (session.status is not LiveStatus.READY or session.current_snapshot is not snapshot
            or snapshot.status != LiveStatus.READY.value or snapshot.reason is not None
            or snapshot.phase != "SELF_DECISION" or snapshot.active_player != "SELF"
            or snapshot.game_type != "GT_RANKED" or snapshot.format != "FT_STANDARD"
            or snapshot.decision.get("kind") != "MAIN_ACTION"):
        raise RecommendationUnavailable("NOT_CURRENT_READY_SELF")
    game = session.game
    if (game is None or game.blocked or game.game_key != snapshot.game_key
            or game.mode_state != "OK" or game.self_player_id is None
            or game.gate.pending is not None or not game.gate.settled):
        raise RecommendationUnavailable("UNTRUSTED_OR_UNSETTLED")
    packet = game.reducer.last_options()
    if packet is None or packet.id != snapshot.decision.get("options_id"):
        raise RecommendationUnavailable("OPTIONS_CHANGED")
    try:
        state = game_state_from_dict(snapshot.state)
        if (state_to_dict(state) != snapshot.state or state.active_player != "SELF"
                or state.turn_number != snapshot.turn or state_hash(snapshot.state) != snapshot.state_hash
                or state.opponent_known_cards or state.self_player.known_secrets
                or state.opponent.known_secrets or state.pending_choice_owner is not None):
            raise RecommendationUnavailable("PRIVACY_OR_STATE_MISMATCH")
    except (ValueError, KeyError, TypeError) as error:
        raise RecommendationUnavailable("PRIVACY_OR_STATE_MISMATCH") from error
    return game, packet, state


def _complete_menu(snapshot: Snapshot, mapped) -> None:
    roots = snapshot.decision.get("legal")
    if not isinstance(roots, list) or not roots or not mapped.actions or len(mapped.actions) != len(mapped.keys):
        raise RecommendationUnavailable("INCOMPLETE_MENU")
    by_option = {}
    for root in roots:
        if not isinstance(root, dict) or type(root.get("option_index")) is not int:
            raise RecommendationUnavailable("INCOMPLETE_MENU")
        if root["option_index"] in by_option:
            raise RecommendationUnavailable("INCOMPLETE_MENU")
        by_option[root["option_index"]] = root
    if set(by_option) != {key[0] for key in mapped.keys}:
        raise RecommendationUnavailable("INCOMPLETE_MENU")
    kinds = {"USE_LOCATION": "ACTIVATE_LOCATION"}
    for action, key in zip(mapped.actions, mapped.keys):
        root = by_option[key[0]]
        if kinds.get(root.get("kind"), root.get("kind")) != action.get("type"):
            raise RecommendationUnavailable("MENU_KIND_MISMATCH")
        if (not set(action) <= ACTION_FIELDS or action["type"] not in ACTION_TYPES
                or type(action.get("play_position")) is not int):
            raise RecommendationUnavailable("UNSUPPORTED_ACTION")
        for field, value in action.items():
            if field.endswith("card_id") and value is not None:
                if not isinstance(value, str) or _PUBLIC_ID.fullmatch(value) is None:
                    raise RecommendationUnavailable("INVALID_PUBLIC_CARD_ID")
        targets = root.get("targets", [])
        if key[2] and key[2] not in {t.get("handle") for t in targets}:
            raise RecommendationUnavailable("MENU_TARGET_MISMATCH")
        if not key[2] and targets:
            raise RecommendationUnavailable("MENU_TARGET_MISMATCH")


def _inputs(state, actions, encoder, *, representation=1) -> tuple[torch.Tensor, ...]:
    return encode_policy_inputs(state, actions, encoder, representation=representation)


class PolicyRecommender:
    def __init__(self, checkpoint: Path, *, expected_sha256: str | None = None) -> None:
        path = Path(checkpoint)
        expected = REVIEWED_CHECKPOINT_SHA256 if expected_sha256 is None else expected_sha256
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise RecommendationUnavailable("CHECKPOINT_IDENTITY_MISMATCH")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RecommendationUnavailable("CHECKPOINT_IDENTITY_MISMATCH")
        self.checkpoint_sha256 = expected
        try:
            self.policy, self.encoder, self.checkpoint = load_policy_checkpoint(path, device="cpu")
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            raise RecommendationUnavailable("CHECKPOINT_INCOMPATIBLE") from error
        self.policy.eval()
        self._bound_catalog = None

    def require_catalog(self, catalog) -> None:
        if catalog is self._bound_catalog:
            return
        if identity(catalog.to_dict()) != self.checkpoint["catalog_sha256"]:
            raise RecommendationUnavailable("RUNTIME_CATALOG_MISMATCH")
        self._bound_catalog = catalog

    def score(self, snapshot: Snapshot, session: LiveSession) -> Recommendation:
        started = time.perf_counter_ns()
        try:
            self.require_catalog(session.catalog)
            game, packet, state = _validate_snapshot(snapshot, session)
            mapped = map_actions(packet, game.reducer.game, game.self_player_id, state)
            _complete_menu(snapshot, mapped)
            with torch.inference_mode():
                logits = self.policy(*_inputs(state, mapped.actions, self.encoder,
                                             representation=representation_of(self.policy)))
            if logits.ndim != 1 or len(logits) != len(mapped.actions) or not torch.isfinite(logits).all():
                raise RecommendationUnavailable("INVALID_MODEL_OUTPUT")
            order = torch.argsort(logits, descending=True, stable=True).tolist()
            ranked = tuple(RankedAction(i, float(logits[i]), mapped.actions[i]) for i in order[:3])
            if any(not math.isfinite(item.score) for item in ranked):
                raise RecommendationUnavailable("INVALID_MODEL_OUTPUT")
            if session.current_snapshot is not snapshot or session.status is not LiveStatus.READY:
                raise RecommendationUnavailable("OPTIONS_CHANGED")
            return Recommendation(
                (snapshot.game_key, snapshot.seq, packet.id, snapshot.state_hash),
                snapshot.turn, len(mapped.actions), ranked, (time.perf_counter_ns() - started) / 1e6,
            )
        except ActionMappingError as error:
            raise RecommendationUnavailable(error.reason) from error
        except RecommendationUnavailable:
            raise
        except Exception as error:
            raise RecommendationUnavailable("INFERENCE_FAILED") from error


def describe_action(action: dict) -> str:
    kind = action["type"]
    if kind == "END_TURN":
        return "END_TURN"
    source = action.get("card_id") or "UNKNOWN_CARD"
    text = f"{kind}: {source}"
    if action.get("hand_index") is not None:
        text += f" [hand {action['hand_index'] + 1}]"
    elif action.get("source_board_position", -1) > 0:
        text += f" [board {action['source_board_position']}]"
    if "target_kind" in action:
        target = action.get("target_card_id") or "UNKNOWN_CARD"
        text += f" -> {action['target_side']} {action['target_kind']} {target}"
        if action.get("target_board_position", -1) > 0:
            text += f" [board {action['target_board_position']}]"
    if action.get("play_position", 0) > 0:
        text += f" [insert {action['play_position']}]"
    return text


def render_recommendation(recommendation: Recommendation) -> str:
    lines = [f"TURN {recommendation.turn} - READY - {recommendation.menu_size} legal variants"]
    for rank, item in enumerate(recommendation.ranked, 1):
        lines.append(f"#{rank} {describe_action(item.action)} | policy ranking score {item.score:.3f}")
    lines.append("source: EXPERIMENTAL_NEURAL_POLICY (behavior cloning; not win probability)")
    return "\n".join(lines)
