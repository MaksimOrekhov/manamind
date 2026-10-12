"""Model shadow: rank one displayed LIVE decision with the primary and the experimental Policies, write nothing shown.

Every model sees the same decoded public state and the same complete legal menu (in menu order). The primary model's
displayed ranking is taken from the ``Recommendation`` itself; a private copy of its network is re-run through this
very code path, so each row proves (``reproduced``) that the experimental models were fed exactly what the primary
model was fed. A failure of one model is recorded for that model only. ``manamind.live``, the overlay and ``apps`` never
import this package (a test enforces it); only the launcher script connects it, after the recommendation was displayed
and journaled.
"""
from __future__ import annotations

import copy
import hashlib
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import torch

from manamind.domain.serialization import game_state_from_dict
from manamind.live.prediction_journal import decision_id
from manamind.live.recommendation import Recommendation
from manamind.live.snapshot import Snapshot, canonical_json
from manamind.models.policy_inputs import encode_policy_inputs, representation_of

MODEL_SHADOW_SCHEMA = "manamind.model_shadow/1"
DEFAULT_BUDGET_MS = 250.0
PRIMARY_NAME = "policy_v2"


class ShadowFailed(Exception):
    """A decision whose shadow row could not be produced; ``reason`` is a stable code (no log or exception text)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def action_sha(action: dict) -> str:
    return hashlib.sha256(canonical_json(action).encode("utf-8")).hexdigest()[:16]


def _inputs_sha(inputs) -> str:
    digest = hashlib.sha256()
    for tensor in inputs:
        digest.update(str(tuple(tensor.shape)).encode("ascii"))
        digest.update(tensor.detach().cpu().numpy().tobytes())
    return digest.hexdigest()[:16]


def face_attack_lethal_candidate(state: dict, actions: list[dict]) -> bool:
    """Visible total attack of the distinct sources that may legally hit the opposing hero >= its health + armor.

    A flag for later review, not a guarantee: immunity, divine shield, spells and Secrets are not modelled. Taunt is
    already reflected by which face attacks are legal.
    """
    sources: dict[tuple, int] = {}
    for action in actions:
        if (action.get("type") == "ATTACK" and action.get("target_kind") == "HERO"
                and action.get("target_side") == "OPPONENT" and isinstance(action.get("source_attack"), int)):
            sources[(action.get("source_board_position"), bool(action.get("source_is_hero")))] = action["source_attack"]
    opponent = state["opponent"]
    return bool(sources) and sum(sources.values()) >= opponent["hero_health"] + opponent["armor"]


def _order(logits) -> list[int]:
    return torch.argsort(logits, descending=True, stable=True).tolist()


def _entry_from_order(order: list[int], actions: list[dict], scores: list[float]) -> dict:
    ranks = [0] * len(order)
    for position, index in enumerate(order, 1):
        ranks[index] = position
    return {
        "ranks": ranks, "scores": [round(float(s), 4) for s in scores],
        "top1_type": actions[order[0]]["type"],
        "top3": [{"rank": rank, "index": index, "type": actions[index]["type"], "action": dict(actions[index])}
                 for rank, index in enumerate(order[:3], 1)],
    }


@dataclass
class ModelStats:
    ok: int = 0
    error: int = 0
    skipped: int = 0
    over_budget: int = 0
    reasons: Counter = field(default_factory=Counter)
    elapsed_ms: list[float] = field(default_factory=list)


@dataclass
class ShadowStats:
    decisions: int = 0
    recorded: int = 0
    failed: int = 0
    discarded: int = 0
    superseded: int = 0
    abandoned: int = 0
    journal_failures: int = 0
    reasons: Counter = field(default_factory=Counter)
    models: dict[str, ModelStats] = field(default_factory=lambda: defaultdict(ModelStats))
    not_reproduced: int = 0

    def summary(self) -> str:
        if not self.decisions:
            return "model shadow: no decisions"
        text = (f"model shadow: {self.recorded}/{self.decisions} decisions recorded, {self.failed} failed, "
                f"{self.discarded} discarded, {self.superseded} superseded, {self.abandoned} abandoned, "
                f"{self.journal_failures} journal failures")
        for name, stats in sorted(self.models.items()):
            if stats.elapsed_ms:
                text += (f"; {name} {float(np.percentile(stats.elapsed_ms, 50)):.2f} ms median "
                         f"{float(np.percentile(stats.elapsed_ms, 95)):.2f} ms p95 {max(stats.elapsed_ms):.2f} ms max"
                         f" ({stats.error} errors)")
        if self.not_reproduced:
            text += f"; {self.not_reproduced} primary re-runs differ"
        return text


class ModelShadow:
    def __init__(self, primary_policy, primary_encoder, primary_sha256: str, models, *,
                 primary_name: str = PRIMARY_NAME, budget_ms: float = DEFAULT_BUDGET_MS,
                 clock: Callable[[], int] = time.perf_counter_ns) -> None:
        if budget_ms <= 0:
            raise ValueError("Model shadow budget must be positive")
        # Private copies: nothing the shadow does can touch the objects that serve the displayed recommendation.
        self.primary_policy = copy.deepcopy(primary_policy).eval()
        self.primary_encoder = copy.deepcopy(primary_encoder)
        self.primary_sha256 = primary_sha256
        self.primary_name = primary_name
        self.models = list(models)
        self.budget_ms = budget_ms
        self.clock = clock
        self.stats = ShadowStats()

    # -- one model ----------------------------------------------------------------------------------------------

    def _run(self, policy, encoder, representation: int, state, actions: list[dict]) -> tuple[Any, dict]:
        started = self.clock()
        inputs = encode_policy_inputs(state, actions, encoder, representation=representation)
        encoded = self.clock()
        with torch.inference_mode():
            logits = policy(*inputs)
        finished = self.clock()
        if logits.ndim != 1 or len(logits) != len(actions) or not torch.isfinite(logits).all():
            raise ShadowFailed("INVALID_MODEL_OUTPUT")
        return logits, {"inputs_sha256": _inputs_sha(inputs), "input_representation": 1 if representation == 1 else 2,
                        "inference_ms": round((finished - started) / 1e6, 3),
                        "forward_ms": round((finished - encoded) / 1e6, 3)}

    def _primary_entry(self, recommendation: Recommendation, ordered, state, actions) -> dict:
        scores = [item.score for item in ordered]
        displayed_order = [item.index for item in recommendation.menu]
        entry = {
            "name": self.primary_name, "role": "primary", "checkpoint_sha256": self.primary_sha256,
            "schema": f"representation_{representation_of(self.primary_policy)}",
            "status": "OK", "live_latency_ms": round(float(recommendation.latency_ms), 3),
            **_entry_from_order(displayed_order, actions, scores),
        }
        try:
            logits, timing = self._run(self.primary_policy, self.primary_encoder, representation_of(self.primary_policy),
                                       state, actions)
            rerun = [float(x) for x in logits]
            entry.update(timing)
            entry["max_abs_logit_diff"] = float(max(abs(a - b) for a, b in zip(rerun, scores)))
            entry["reproduced"] = _order(logits) == displayed_order and entry["max_abs_logit_diff"] <= 1e-5
        except Exception:                      # the check failing is a fact about the check, not about the primary
            entry["reproduced"] = None
            entry["check_error"] = "PRIMARY_RERUN_FAILED"
        return entry

    def _model_entry(self, model, state, actions, started_ns: int, cancelled) -> dict:
        entry = {"name": model.name, "role": "experimental", "checkpoint_sha256": model.sha256,
                 "schema": model.schema, "architecture": model.architecture, "parameters": model.parameters}
        stats = self.stats.models[model.name]
        reason = cancelled()
        if reason is not None:
            stats.skipped += 1
            return {**entry, "status": "SKIPPED", "reason": "CANCELLED"}
        if (self.clock() - started_ns) / 1e6 > self.budget_ms:
            stats.skipped += 1
            return {**entry, "status": "SKIPPED", "reason": "BUDGET_EXCEEDED"}
        try:
            logits, timing = self._run(model.policy, model.encoder, model.representation, state, actions)
        except ShadowFailed as error:
            stats.error += 1
            stats.reasons[error.reason] += 1
            return {**entry, "status": "ERROR", "reason": error.reason}
        except Exception:                      # one model failing never touches another model or the Policy path
            stats.error += 1
            stats.reasons["INFERENCE_FAILED"] += 1
            return {**entry, "status": "ERROR", "reason": "INFERENCE_FAILED"}
        stats.ok += 1
        stats.elapsed_ms.append(timing["inference_ms"])
        over = timing["inference_ms"] > self.budget_ms
        stats.over_budget += over
        return {**entry, "status": "OK", **timing, **({"over_budget": True} if over else {}),
                **_entry_from_order(_order(logits), actions, [float(x) for x in logits])}

    # -- one decision -------------------------------------------------------------------------------------------

    def score(self, snapshot: Snapshot, recommendation: Recommendation,
              cancelled: Callable[[], str | None] = lambda: None) -> dict[str, Any]:
        """The journal record of one decision. Raises ``ShadowFailed`` with a stable reason; nothing else escapes."""
        started = self.clock()
        if not recommendation.menu:
            raise ShadowFailed("NO_MENU")
        ordered = sorted(recommendation.menu, key=lambda item: item.index)   # menu order, like the recommender saw it
        if [item.index for item in ordered] != list(range(len(ordered))):
            raise ShadowFailed("MENU_INDEX_MISMATCH")
        if (recommendation.identity[:3] != (snapshot.game_key, snapshot.seq, snapshot.decision["options_id"])
                or recommendation.identity[3] != snapshot.state_hash):
            raise ShadowFailed("RECOMMENDATION_SNAPSHOT_MISMATCH")
        actions = [dict(item.action) for item in ordered]
        try:
            state = game_state_from_dict(snapshot.state)
        except Exception:
            raise ShadowFailed("STATE_UNREADABLE") from None
        entries = [self._primary_entry(recommendation, ordered, state, actions)]
        if entries[0].get("reproduced") is False:
            self.stats.not_reproduced += 1
        entries += [self._model_entry(model, state, actions, started, cancelled) for model in self.models]
        me, opponent = snapshot.state["self_player"], snapshot.state["opponent"]
        return {
            "schema": MODEL_SHADOW_SCHEMA, "turn": snapshot.turn, "self_class": me["player_class"],
            "opponent_class": opponent["player_class"], "mana": me["available_mana"],
            "menu_size": len(actions),
            "menu_sha256": hashlib.sha256(canonical_json(actions).encode("utf-8")).hexdigest(),
            "actions": [{"index": i, "type": a["type"], "sha": action_sha(a)} for i, a in enumerate(actions)],
            "face_attack_lethal_candidate": face_attack_lethal_candidate(snapshot.state, actions),
            "budget_ms": self.budget_ms, "total_ms": round((self.clock() - started) / 1e6, 3),
            "models": entries,
        }


def identity_fields(snapshot: Snapshot) -> dict[str, Any]:
    return {"match_id": snapshot.game_key, "decision_id": decision_id(snapshot), "seq": snapshot.seq,
            "options_id": snapshot.decision["options_id"], "state_hash": snapshot.state_hash}


__all__ = ["MODEL_SHADOW_SCHEMA", "ModelShadow", "ShadowFailed", "ShadowStats", "action_sha",
           "face_attack_lethal_candidate", "identity_fields"]
