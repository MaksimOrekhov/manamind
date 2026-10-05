"""Attempt one action on an isolated full-information simulator clone.

No fallback consumer is implemented. Outcomes may depend on hidden deck/RNG
state and must not be connected to a real observed root without a reviewed
information-set boundary. Failure diagnostics are internal-only evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from manamind.domain.game_state import GameState

from .engine import (
    FailureKind, ManaEngineSession, NativeFailure, UnsupportedSimulationError,
    _EXECUTION_FIELDS, _execution_key,
)


class SimulationOutcome(str, Enum):
    COMPLETED = "COMPLETED"
    UNSIMULATABLE = "UNSIMULATABLE"
    ILLEGAL = "ILLEGAL"
    ENGINE_DEFECT = "ENGINE_DEFECT"


class AttemptReason(str, Enum):
    ILLEGAL_MALFORMED = "ILLEGAL_MALFORMED"
    ILLEGAL_NOT_LEGAL = "ILLEGAL_NOT_LEGAL"
    NATIVE_UNSUPPORTED = "NATIVE_UNSUPPORTED"
    NATIVE_RULE_UNRESOLVED = "NATIVE_RULE_UNRESOLVED"
    NATIVE_BUDGET_LIMIT = "NATIVE_BUDGET_LIMIT"
    NATIVE_ENGINE_DEFECT = "NATIVE_ENGINE_DEFECT"
    NATIVE_FAILURE_UNTYPED = "NATIVE_FAILURE_UNTYPED"
    ENUMERATION_UNAVAILABLE = "ENUMERATION_UNAVAILABLE"
    ENUMERATION_DEFECT = "ENUMERATION_DEFECT"
    # Deprecated compatibility names; never emitted by typed classification.
    NATIVE_EXCEPTION_NORMALIZED = "NATIVE_EXCEPTION_NORMALIZED"
    NATIVE_CATCH_ALL = "NATIVE_CATCH_ALL"
    ATTEMPT_INVARIANT_VIOLATED = "ATTEMPT_INVARIANT_VIOLATED"
    CLONE_FAILED = "CLONE_FAILED"
    EXPORT_FAILED = "EXPORT_FAILED"
    ADAPTER_FAILURE = "ADAPTER_FAILURE"


_UNSIMULATABLE_REASONS = {
    AttemptReason.NATIVE_UNSUPPORTED, AttemptReason.NATIVE_RULE_UNRESOLVED,
    AttemptReason.NATIVE_BUDGET_LIMIT, AttemptReason.ENUMERATION_UNAVAILABLE,
}
_FALLBACK_REASONS = frozenset({
    AttemptReason.NATIVE_UNSUPPORTED, AttemptReason.NATIVE_RULE_UNRESOLVED,
    AttemptReason.ENUMERATION_UNAVAILABLE,
})
_REASONS = {
    SimulationOutcome.ILLEGAL: {AttemptReason.ILLEGAL_MALFORMED, AttemptReason.ILLEGAL_NOT_LEGAL},
    SimulationOutcome.UNSIMULATABLE: _UNSIMULATABLE_REASONS,
    SimulationOutcome.ENGINE_DEFECT: set(AttemptReason) - _UNSIMULATABLE_REASONS - {
        AttemptReason.ILLEGAL_MALFORMED, AttemptReason.ILLEGAL_NOT_LEGAL,
    },
}


def _classification(failure: NativeFailure | None, *, enumeration: bool = False):
    if failure is None or failure.code == "LEGACY_UNTYPED":
        return SimulationOutcome.ENGINE_DEFECT, AttemptReason.NATIVE_FAILURE_UNTYPED
    if failure.kind == FailureKind.ENGINE_DEFECT:
        return (SimulationOutcome.ENGINE_DEFECT,
                AttemptReason.ENUMERATION_DEFECT if enumeration else AttemptReason.NATIVE_ENGINE_DEFECT)
    if failure.kind == FailureKind.BUDGET_LIMIT:
        return SimulationOutcome.UNSIMULATABLE, AttemptReason.NATIVE_BUDGET_LIMIT
    if enumeration:
        return SimulationOutcome.UNSIMULATABLE, AttemptReason.ENUMERATION_UNAVAILABLE
    return (SimulationOutcome.UNSIMULATABLE,
            AttemptReason.NATIVE_UNSUPPORTED if failure.kind == FailureKind.UNSUPPORTED
            else AttemptReason.NATIVE_RULE_UNRESOLVED)


def _strings(values: Any) -> tuple[str, ...]:
    if isinstance(values, str):
        raise ValueError("expected a collection of diagnostic/evidence strings")
    result = tuple(values)
    if any(not isinstance(value, str) for value in result):
        raise ValueError("diagnostic/evidence values must be strings")
    return result


@dataclass(frozen=True, slots=True)
class AttemptDiagnostics:
    """Immutable failure snapshot; never owns a session or native handle."""

    native_failure: NativeFailure | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    unsupported_outcome: str | None = None
    evidence_at_failure: tuple[str, ...] = ()
    trace_tail: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.native_failure is not None and not isinstance(self.native_failure, NativeFailure):
            raise ValueError("native_failure must be an immutable NativeFailure")
        for name in ("exception_type", "exception_message", "unsupported_outcome"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be a string or None")
        object.__setattr__(self, "evidence_at_failure", _strings(self.evidence_at_failure))
        object.__setattr__(self, "trace_tail", _strings(self.trace_tail)[-32:])


class InvalidParentSession(RuntimeError):
    """A poisoned parent cannot be used as an attempt root."""


@dataclass(frozen=True, slots=True)
class SimulationAttempt:
    """Only COMPLETED owns a visible state or optional internal child handle.

    child is mutable, full-information simulator infrastructure; it must never
    enter model features, live observations, diagnostics or live-game search.
    action retains only immutable scalar execution fields, not caller extras.
    """

    outcome: SimulationOutcome
    perspective: str
    action: Mapping[str, str | int] | None
    state: GameState | None = None
    child: ManaEngineSession | None = field(default=None, repr=False, compare=False)
    evidence_constraints: tuple[str, ...] = ()
    reason: AttemptReason | None = None
    diagnostics: AttemptDiagnostics | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, SimulationOutcome):
            raise ValueError("outcome must be a SimulationOutcome")
        if self.perspective not in ("PLAYER1", "PLAYER2"):
            raise ValueError("attempt perspective must be PLAYER1 or PLAYER2")
        if self.action is not None:
            key = _execution_key(self.action)
            object.__setattr__(self, "action", MappingProxyType(dict(zip(_EXECUTION_FIELDS, key, strict=True))))
        object.__setattr__(self, "evidence_constraints", _strings(self.evidence_constraints))
        if self.diagnostics is not None and not isinstance(self.diagnostics, AttemptDiagnostics):
            raise ValueError("diagnostics must be an immutable AttemptDiagnostics")
        if self.completed:
            if not isinstance(self.state, GameState) or self.action is None:
                raise ValueError("COMPLETED requires a GameState and execution action")
            if self.reason is not None or self.diagnostics is not None:
                raise ValueError("COMPLETED cannot carry failure reason or diagnostics")
            if self.evidence_constraints != self.state.evidence_constraints:
                raise ValueError("COMPLETED evidence must equal state evidence")
            if self.child is not None and not self.child.is_valid:
                raise ValueError("COMPLETED cannot retain an invalid child")
        else:
            if self.state is not None or self.child is not None or self.evidence_constraints:
                raise ValueError("failed attempts cannot expose a state, child or transition evidence")
            if not isinstance(self.reason, AttemptReason) or self.reason not in _REASONS[self.outcome]:
                raise ValueError("reason does not belong to the attempt outcome")
            if self.outcome != SimulationOutcome.ILLEGAL and self.diagnostics is None:
                raise ValueError("simulation failures require diagnostics")

    @property
    def completed(self) -> bool:
        return self.outcome == SimulationOutcome.COMPLETED

    @property
    def fallback_eligible(self) -> bool:
        return self.outcome == SimulationOutcome.UNSIMULATABLE and self.reason in _FALLBACK_REASONS

    @property
    def has_evidence_debt(self) -> bool:
        return bool(self.evidence_constraints)


def acting_seat(session: ManaEngineSession) -> str:
    """Resolve the acting root seat from a visible PLAYER1 observation, without mutation."""
    return "PLAYER1" if session.observation("PLAYER1").active_player == "SELF" else "PLAYER2"


def _diagnostics(session: ManaEngineSession, exc: Exception | None) -> AttemptDiagnostics:
    """Snapshot best-effort diagnostic accessors; process/resource failures propagate."""
    def read(name: str, default: Any) -> Any:
        try:
            return getattr(session, name)
        except MemoryError:
            raise
        except Exception:
            return default

    def strings(name: str) -> tuple[str, ...]:
        try:
            return _strings(read(name, ()))
        except MemoryError:
            raise
        except Exception:
            return ()

    unsupported = read("unsupported_outcome", None)
    native_failure = read("failure", None) or getattr(exc, "failure", None)
    return AttemptDiagnostics(
        native_failure=native_failure if isinstance(native_failure, NativeFailure) else None,
        exception_type=type(exc).__name__ if exc is not None else None,
        exception_message=str(exc) if exc is not None else None,
        unsupported_outcome=unsupported if isinstance(unsupported, str) else None,
        evidence_at_failure=strings("evidence_constraints"),
        trace_tail=strings("diagnostic_trace"),
    )


def attempt_action(
    parent: ManaEngineSession, action: Mapping[str, Any], *,
    perspective: str | None = None, retain_child: bool = True,
) -> SimulationAttempt:
    """Try one canonical legal action on a clone, preserving parent state and RNG.

    The root seat is resolved once. apply_action's post-action ACTIVE view is
    deliberately ignored. Typed kind/code owns classification; the explicit
    fallback allowlist excludes budgets, defects and all untyped failures.
    """
    if not parent.is_valid:
        raise InvalidParentSession("attempt root is invalid/poisoned")
    if perspective is not None and perspective not in ("PLAYER1", "PLAYER2"):
        raise ValueError("perspective must be PLAYER1 or PLAYER2")
    if type(retain_child) is not bool:
        raise ValueError("retain_child must be bool")
    seat = acting_seat(parent) if perspective is None else perspective
    normalized = None

    def failure(outcome: SimulationOutcome, reason: AttemptReason,
                session: ManaEngineSession, exc: Exception | None = None) -> SimulationAttempt:
        return SimulationAttempt(outcome, seat, normalized, reason=reason, diagnostics=_diagnostics(session, exc))

    try:
        key = _execution_key(action)
        normalized = dict(zip(_EXECUTION_FIELDS, key, strict=True))
    except MemoryError:
        raise
    except Exception as exc:
        return failure(SimulationOutcome.ILLEGAL, AttemptReason.ILLEGAL_MALFORMED, parent, exc)
    try:
        legal = parent._legal_execution_keys()
    except MemoryError:
        raise
    except UnsupportedSimulationError as exc:
        return failure(*_classification(exc.failure, enumeration=True), parent, exc)
    except Exception as exc:
        return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ADAPTER_FAILURE, parent, exc)
    if key not in legal:
        return SimulationAttempt(SimulationOutcome.ILLEGAL, seat, normalized, reason=AttemptReason.ILLEGAL_NOT_LEGAL)
    try:
        child = parent.clone()
    except MemoryError:
        raise
    except Exception as exc:
        return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.CLONE_FAILED, parent, exc)
    if child is parent:
        return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.CLONE_FAILED, parent,
                       RuntimeError("clone returned the parent session"))
    try:
        if not child.is_valid:
            return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.CLONE_FAILED, child,
                           RuntimeError("clone returned an invalid session"))
        child._apply_raw(legal[key])
    except MemoryError:
        raise
    except UnsupportedSimulationError as exc:
        try:
            if child.is_valid:
                return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ATTEMPT_INVARIANT_VIOLATED, child, exc)
            stored = child.failure
            if exc.failure is not None and stored != exc.failure and (
                stored is not None or exc.failure.code != "LEGACY_UNTYPED"
            ):
                return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ATTEMPT_INVARIANT_VIOLATED, child, exc)
            return failure(*_classification(exc.failure or stored), child, exc)
        except MemoryError:
            raise
        except Exception as classification_exc:
            return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ADAPTER_FAILURE, child, classification_exc)
    except Exception as exc:
        return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ADAPTER_FAILURE, child, exc)
    try:
        if not child.is_valid:
            return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ATTEMPT_INVARIANT_VIOLATED, child)
    except MemoryError:
        raise
    except Exception as exc:
        return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ADAPTER_FAILURE, child, exc)
    try:
        state = child.observation(seat)
        evidence = child.evidence_constraints
    except MemoryError:
        raise
    except Exception as exc:
        return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.EXPORT_FAILED, child, exc)
    try:
        if not child.is_valid or not isinstance(state, GameState) or state.evidence_constraints != evidence:
            return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ATTEMPT_INVARIANT_VIOLATED, child)
        return SimulationAttempt(SimulationOutcome.COMPLETED, seat, normalized, state,
                                 child if retain_child else None, evidence)
    except MemoryError:
        raise
    except Exception as exc:
        return failure(SimulationOutcome.ENGINE_DEFECT, AttemptReason.ATTEMPT_INVARIANT_VIOLATED, child, exc)
