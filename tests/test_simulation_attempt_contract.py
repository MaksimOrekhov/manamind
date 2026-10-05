"""Source-only attempt contracts; no native extension is loaded by these cases."""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, dataclass, field, fields
from types import SimpleNamespace

import pytest

from manamind.domain.card import CardFeatures
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.integrations.manaengine import (
    AttemptDiagnostics, AttemptReason, InvalidParentSession, ManaEngineSession,
    SimulationAttempt, SimulationOutcome, UnsupportedSimulationError, acting_seat, attempt_action,
)
from manamind.integrations.manaengine.engine import _EXECUTION_FIELDS, _execution_key

FIRE = ("FIRE_POOL_MEMBERSHIP_INFERRED",)
END = {"type": "END_TURN"}


@dataclass
class FakeSession:
    active: str = "PLAYER1"
    is_valid: bool = True
    evidence_constraints: tuple[str, ...] = ()
    unsupported_outcome: str | None = None
    diagnostic_trace: tuple[str, ...] = ()
    actions: list[dict] = field(default_factory=lambda: [{"type": "END_TURN", "card_cost": 0}])
    behavior: str = "success"
    enumeration_error: Exception | None = None
    clone_error: BaseException | None = None
    apply_error: BaseException | None = None
    export_error: BaseException | None = None
    count: int = 0
    rng: int = 5
    submitted: dict | None = None

    def observation(self, perspective="ACTIVE"):
        if self.count and self.export_error is not None:
            raise self.export_error
        seat = self.active if perspective == "ACTIVE" else perspective
        return GameState(
            turn_number=self.count, active_player="SELF" if self.active == seat else "OPPONENT",
            self_player=PlayerObservation(hero_health=30, armor=self.count, hand_size=1),
            opponent=PlayerObservation(hero_health=30, hand_size=2),
            self_hand=(CardFeatures(card_id=seat + "_HAND"),),
            evidence_constraints=() if self.behavior == "mismatch" and self.count else self.evidence_constraints,
        )

    def _legal_execution_keys(self):
        if self.enumeration_error:
            raise self.enumeration_error
        return {_execution_key(a): dict(a) for a in self.actions}

    def clone(self):
        if self.clone_error is not None:
            raise self.clone_error
        if self.behavior == "same_clone":
            return self
        return copy.deepcopy(self)

    def _apply_raw(self, action):
        self.submitted = dict(action)
        self.count += 1
        self.rng += 1
        self.active = "PLAYER2" if self.active == "PLAYER1" else "PLAYER1"
        if self.apply_error:
            raise self.apply_error
        if self.behavior in {"inferred", "unsupported", "mismatch"}:
            self.evidence_constraints = FIRE
        if self.behavior in {"unsupported", "invalid", "normalized", "mutation", "reaction"}:
            self.is_valid = False
        if self.behavior in {"unsupported", "normalized", "mutation", "reaction", "valid_unsupported"}:
            messages = {
                "unsupported": "selected generated outcome is unsupported: TEST_FIRE",
                "normalized": "action failed after mutation: synthetic defect",
                "mutation": "damage group: mutation failed", "reaction": "damage group: reaction failed",
                "valid_unsupported": "synthetic unsupported without poison",
            }
            self.unsupported_outcome = messages[self.behavior]
            self.diagnostic_trace = tuple(f"trace-{i}" for i in range(40))
            raise UnsupportedSimulationError(self.unsupported_outcome)
        return {"ignored": "post-action ACTIVE view"}


def test_sa01_sa02_sa03_sa04_success_parent_and_second_fixed_seat_attempt():
    parent = FakeSession()
    before = copy.deepcopy(parent)
    first = attempt_action(parent, END)
    assert first.completed and not first.fallback_eligible and not first.has_evidence_debt
    assert first.perspective == "PLAYER1" and first.state.active_player == "OPPONENT"
    assert first.state.self_hand[0].card_id == "PLAYER1_HAND"
    assert parent == before
    assert first.child is not parent
    second = attempt_action(first.child, END, perspective=first.perspective)
    assert second.completed and second.state.active_player == "SELF"
    assert second.state.self_hand[0].card_id == "PLAYER1_HAND"
    assert first.child.count == 1 and second.child.count == 2


def test_sa05_sa13_inferred_completion_and_evidence_independence():
    parent = FakeSession(behavior="inferred")
    result = attempt_action(parent, END)
    assert result.completed and result.has_evidence_debt and not result.fallback_eligible
    assert result.evidence_constraints == result.state.evidence_constraints == result.child.evidence_constraints == FIRE
    assert parent.evidence_constraints == ()
    result.child.evidence_constraints = ()
    assert result.evidence_constraints == FIRE


def test_sa06_sa07_sa08_sa12_unsupported_has_diagnostics_only():
    parent = FakeSession(behavior="unsupported")
    before = copy.deepcopy(parent)
    result = attempt_action(parent, END)
    assert result.outcome == SimulationOutcome.UNSIMULATABLE and result.fallback_eligible
    assert result.reason == AttemptReason.NATIVE_UNSUPPORTED
    assert result.state is result.child is None and result.evidence_constraints == ()
    assert not result.has_evidence_debt
    assert result.diagnostics.evidence_at_failure == FIRE
    assert "TEST_FIRE" in result.diagnostics.unsupported_outcome
    assert result.diagnostics.exception_type == "UnsupportedSimulationError"
    assert result.diagnostics.trace_tail == tuple(f"trace-{i}" for i in range(8, 40))
    assert parent == before
    assert all(not isinstance(getattr(result.diagnostics, f.name), FakeSession) for f in fields(AttemptDiagnostics))


@pytest.mark.parametrize("action", [None, [], 7, {}, {"type": None}, {"type": 1}, {"type": ""}])
def test_sa09_malformed_action(action):
    result = attempt_action(FakeSession(), action)
    assert result.outcome == SimulationOutcome.ILLEGAL and result.reason == AttemptReason.ILLEGAL_MALFORMED
    assert not result.fallback_eligible and result.state is result.child is None


@pytest.mark.parametrize("name", _EXECUTION_FIELDS[1:])
@pytest.mark.parametrize("bad", [True, False, 1.0, "1", None])
def test_sa09_execution_fields_require_strict_integer(name, bad):
    result = attempt_action(FakeSession(), {**END, name: bad})
    assert result.reason == AttemptReason.ILLEGAL_MALFORMED


@pytest.mark.parametrize("action", [
    {"type": "PLAY_CARD", "hand_index": 999}, {"type": "HERO_POWER", "target_entity_id": 999},
    {"type": "CHOOSE_CARD", "choice_index": 99}, {"type": "UNKNOWN"}, {**END, "choose_one": 1},
])
def test_sa10_stale_wrong_turn_or_unknown_execution_is_not_legal(action):
    parent = FakeSession()
    result = attempt_action(parent, action)
    assert result.reason == AttemptReason.ILLEGAL_NOT_LEGAL and not result.fallback_eligible
    assert parent.count == 0 and parent.rng == 5


@pytest.mark.parametrize("behavior, reason", [
    ("normalized", AttemptReason.NATIVE_EXCEPTION_NORMALIZED),
    ("mutation", AttemptReason.NATIVE_CATCH_ALL), ("reaction", AttemptReason.NATIVE_CATCH_ALL),
    ("valid_unsupported", AttemptReason.ATTEMPT_INVARIANT_VIOLATED),
])
def test_sa11_native_defect_heuristic(behavior, reason):
    result = attempt_action(FakeSession(behavior=behavior), END)
    assert result.outcome == SimulationOutcome.ENGINE_DEFECT and result.reason == reason
    assert not result.fallback_eligible and result.state is result.child is None


def test_sa14_deterministic_attempt_does_not_advance_parent_rng():
    parent = FakeSession(behavior="inferred")
    a, b = attempt_action(parent, END), attempt_action(parent, END)
    assert a == b and a.child.rng == b.child.rng == 6
    assert parent.rng == 5


def test_sa16_enumeration_unavailable_and_ordinary_adapter_error():
    result = attempt_action(FakeSession(enumeration_error=UnsupportedSimulationError("draw unavailable")), END)
    assert result.reason == AttemptReason.ENUMERATION_UNAVAILABLE and result.fallback_eligible
    bad = attempt_action(FakeSession(enumeration_error=RuntimeError("enumeration bug")), END)
    assert bad.reason == AttemptReason.ADAPTER_FAILURE and not bad.fallback_eligible


def test_sa17_execution_defaults_extra_fields_and_canonical_submission():
    caller = {**END, "card_cost": object(), "arbitrary": {"mutable": []}}
    result = attempt_action(FakeSession(), caller)
    assert result.child.submitted == {"type": "END_TURN", "card_cost": 0}
    assert dict(result.action) == dict(zip(_EXECUTION_FIELDS, ("END_TURN", -1, -1, -1, -1, 0), strict=True))
    caller["type"] = "ATTACK"
    assert result.action["type"] == "END_TURN"
    with pytest.raises(TypeError):
        result.action["type"] = "ATTACK"


def test_sa17_native_helper_key_mapping_and_exception_normalization():
    class NativeUnsupported(RuntimeError):
        pass

    native_actions = [{"type": "CHOOSE_CARD", "choice_index": 2, "choose_one": 1, "card_cost": 3}]
    native = SimpleNamespace(legal_actions=lambda: native_actions, apply_action=lambda action: {"received": action})
    session = object.__new__(ManaEngineSession)
    session._native = native
    session._unsupported_exception = NativeUnsupported
    legal = session._legal_execution_keys()
    assert list(legal) == [("CHOOSE_CARD", -1, -1, -1, 2, 1)]
    assert session._apply_raw(legal[next(iter(legal))]) == {"received": native_actions[0]}

    def reject():
        raise NativeUnsupported("unsupported enumeration")

    native.legal_actions = reject
    with pytest.raises(UnsupportedSimulationError, match="unsupported enumeration"):
        session._legal_execution_keys()
    native.legal_actions = lambda: native_actions * 2
    with pytest.raises(RuntimeError, match="duplicate execution key"):
        session._legal_execution_keys()


def test_sa18_complete_session_has_no_action():
    result = attempt_action(FakeSession(actions=[]), END)
    assert result.reason == AttemptReason.ILLEGAL_NOT_LEGAL


def test_sa19_retaining_child_is_optional_without_reexecution():
    result = attempt_action(FakeSession(), END, retain_child=False)
    assert result.completed and result.child is None and result.state.turn_number == 1


@pytest.mark.parametrize("parent, reason", [
    (FakeSession(behavior="invalid"), AttemptReason.ATTEMPT_INVARIANT_VIOLATED),
    (FakeSession(export_error=UnsupportedSimulationError("unsafe export")), AttemptReason.EXPORT_FAILED),
    (FakeSession(export_error=RuntimeError("export bug")), AttemptReason.EXPORT_FAILED),
    (FakeSession(behavior="mismatch"), AttemptReason.ATTEMPT_INVARIANT_VIOLATED),
    (FakeSession(clone_error=RuntimeError("clone bug")), AttemptReason.CLONE_FAILED),
    (FakeSession(behavior="same_clone"), AttemptReason.CLONE_FAILED),
    (FakeSession(apply_error=RuntimeError("adapter bug")), AttemptReason.ADAPTER_FAILURE),
])
def test_sa20_sa21_failure_postconditions(parent, reason):
    result = attempt_action(parent, END)
    assert result.outcome == SimulationOutcome.ENGINE_DEFECT and result.reason == reason
    assert result.state is result.child is None and result.evidence_constraints == ()
    assert not result.fallback_eligible


@pytest.mark.parametrize("error", [MemoryError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("phase", ["enumeration_error", "clone_error", "apply_error", "export_error"])
def test_sa22_process_and_resource_failures_propagate(error, phase):
    parent = FakeSession(**{phase: error("fatal")})
    with pytest.raises(error, match="fatal"):
        attempt_action(parent, END)
    assert parent.is_valid and parent.count == 0 and parent.rng == 5


def test_sa23_explicit_player2_invalid_perspective_and_invalid_parent():
    parent = FakeSession()
    result = attempt_action(parent, END, perspective="PLAYER2")
    assert result.perspective == "PLAYER2" and result.state.self_hand[0].card_id == "PLAYER2_HAND"
    assert result.state.active_player == "SELF" and acting_seat(parent) == "PLAYER1"
    for invalid in ("ACTIVE", "SELF", 1, []):
        with pytest.raises(ValueError, match="perspective"):
            attempt_action(parent, END, perspective=invalid)
    with pytest.raises(InvalidParentSession):
        attempt_action(FakeSession(is_valid=False), END)


def test_sa24_child_is_excluded_from_repr_and_equality_and_state_is_visible():
    result = attempt_action(FakeSession(), END)
    child_field = next(f for f in fields(SimulationAttempt) if f.name == "child")
    assert not child_field.repr and not child_field.compare and "FakeSession" not in repr(result)
    assert result.state.opponent_known_cards == () and result.state.opponent.hand_size == 2


@pytest.mark.parametrize("updates", [
    {"outcome": SimulationOutcome.COMPLETED}, {"perspective": "ACTIVE"},
    {"reason": AttemptReason.EXPORT_FAILED}, {"state": FakeSession().observation()},
    {"child": FakeSession()}, {"evidence_constraints": FIRE},
    {"outcome": SimulationOutcome.UNSIMULATABLE, "reason": AttemptReason.NATIVE_UNSUPPORTED},
    {"outcome": SimulationOutcome.ENGINE_DEFECT, "reason": AttemptReason.EXPORT_FAILED},
])
def test_sa25_failed_result_invariants(updates):
    args = dict(outcome=SimulationOutcome.ILLEGAL, perspective="PLAYER1", action=END,
                reason=AttemptReason.ILLEGAL_NOT_LEGAL)
    with pytest.raises(ValueError):
        SimulationAttempt(**(args | updates))


def test_sa25_completed_and_diagnostic_invariants():
    state = FakeSession().observation()
    args = dict(outcome=SimulationOutcome.COMPLETED, perspective="PLAYER1", action=END, state=state)
    for bad in ({"reason": AttemptReason.NATIVE_UNSUPPORTED}, {"diagnostics": AttemptDiagnostics()},
                {"evidence_constraints": FIRE}, {"child": FakeSession(is_valid=False)}, {"action": None}):
        with pytest.raises(ValueError):
            SimulationAttempt(**(args | bad))
    diagnostics = AttemptDiagnostics(evidence_at_failure=list(FIRE), trace_tail=["safe"])
    with pytest.raises(FrozenInstanceError):
        diagnostics.exception_message = "mutated"
    with pytest.raises(ValueError):
        AttemptDiagnostics(unsupported_outcome=FakeSession())
    with pytest.raises(ValueError):
        AttemptDiagnostics(trace_tail=[FakeSession()])
