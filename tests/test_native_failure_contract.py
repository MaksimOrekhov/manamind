"""Phase 4K.1b T12/T13/T18/T20: payload mapping without diagnostic heuristics."""
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from manamind.integrations.manaengine import (
    AttemptDiagnostics, AttemptReason, EngineDefectError, FailureKind, NativeFailure,
    SimulationAttempt, SimulationOutcome, UnsupportedSimulationError, attempt_action,
)
from test_simulation_attempt_contract import END, FakeSession


class TypedSession(FakeSession):
    record = None
    thrown_record = None
    valid_after_error = False

    def _apply_raw(self, action):
        self.failure = self.record
        self.is_valid = self.valid_after_error
        self.unsupported_outcome = self.record.detail if self.record else None
        failure = self.thrown_record or self.record
        cls = EngineDefectError if failure and failure.kind == FailureKind.ENGINE_DEFECT else UnsupportedSimulationError
        raise cls(failure.detail if failure else "untyped diagnostic", failure=failure)


@pytest.mark.parametrize("kind,code,reason,eligible", [
    (FailureKind.UNSUPPORTED, "UNSUPPORTED_GENERATED_CARD", AttemptReason.NATIVE_UNSUPPORTED, True),
    (FailureKind.RULE_UNRESOLVED, "POOL_IDENTITY_NOT_LOADED", AttemptReason.NATIVE_RULE_UNRESOLVED, True),
    (FailureKind.BUDGET_LIMIT, "DAMAGE_DEPTH_BUDGET_EXCEEDED", AttemptReason.NATIVE_BUDGET_LIMIT, False),
    (FailureKind.ENGINE_DEFECT, "MISSING_DISPATCH_HANDLER", AttemptReason.NATIVE_ENGINE_DEFECT, False),
    (FailureKind.ENGINE_DEFECT, "LEGACY_UNTYPED", AttemptReason.NATIVE_FAILURE_UNTYPED, False),
])
@pytest.mark.parametrize("detail", ["action failed after mutation: fake", "damage group: mutation failed", "damage group: reaction failed", "ordinary message"])
def test_t12_kind_owns_verdict(kind, code, reason, eligible, detail):
    parent = TypedSession()
    parent.record = NativeFailure(kind, code, detail, "context")
    result = attempt_action(parent, END)
    assert result.reason == reason and result.fallback_eligible == eligible
    assert result.diagnostics.native_failure == parent.record
    assert result.state is result.child is None
    assert parent.is_valid and parent.failure is None
    with pytest.raises(FrozenInstanceError):
        result.diagnostics.native_failure.detail = "edited"


def test_t18_record_mismatch_and_valid_child_never_fallback():
    parent = TypedSession()
    parent.record = NativeFailure(FailureKind.UNSUPPORTED, "UNSUPPORTED_GENERATED_CARD", "stored")
    parent.thrown_record = NativeFailure(FailureKind.UNSUPPORTED, "UNSUPPORTED_GENERATED_CARD", "thrown")
    result = attempt_action(parent, END)
    assert result.reason == AttemptReason.ATTEMPT_INVARIANT_VIOLATED
    parent.thrown_record = None
    parent.valid_after_error = True
    assert attempt_action(parent, END).reason == AttemptReason.ATTEMPT_INVARIANT_VIOLATED


def test_t18_missing_stored_typed_payload_is_invariant_defect():
    parent = TypedSession()
    parent.thrown_record = NativeFailure(FailureKind.UNSUPPORTED, "UNSUPPORTED_GENERATED_CARD", "missing stored payload")
    result = attempt_action(parent, END)
    assert result.reason == AttemptReason.ATTEMPT_INVARIANT_VIOLATED and not result.fallback_eligible


def test_t20_untyped_is_defect():
    result = attempt_action(TypedSession(), END)
    assert result.reason == AttemptReason.NATIVE_FAILURE_UNTYPED and not result.fallback_eligible


@pytest.mark.parametrize("kind,code,reason", [
    (FailureKind.UNSUPPORTED, "UNSUPPORTED_CARD_IN_ACTIVE_HAND", AttemptReason.ENUMERATION_UNAVAILABLE),
    (FailureKind.RULE_UNRESOLVED, "POOL_IDENTITY_NOT_LOADED", AttemptReason.ENUMERATION_UNAVAILABLE),
    (FailureKind.BUDGET_LIMIT, "DAMAGE_WORK_BUDGET_EXCEEDED", AttemptReason.NATIVE_BUDGET_LIMIT),
    (FailureKind.ENGINE_DEFECT, "QUIESCENCE_VIOLATED", AttemptReason.ENUMERATION_DEFECT),
])
def test_t08_enumeration_typed(kind, code, reason):
    record = NativeFailure(kind, code, "same message")
    result = attempt_action(FakeSession(enumeration_error=UnsupportedSimulationError(record.detail, failure=record)), END)
    assert result.reason == reason
    assert result.fallback_eligible == (kind in {FailureKind.UNSUPPORTED, FailureKind.RULE_UNRESOLVED})


def test_t12_source_has_no_text_classification():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/manamind/integrations/manaengine/simulation.py").read_text()
    for fragment in ("action failed after mutation:", "damage group: mutation failed", "damage group: reaction failed"):
        assert fragment not in source
    assert "validate_invariants(" not in source


@pytest.mark.parametrize("outcome", list(SimulationOutcome)[1:])
@pytest.mark.parametrize("reason", list(AttemptReason))
def test_t13_explicit_fallback_policy(outcome, reason):
    args = dict(outcome=outcome, perspective="PLAYER1", action=END, reason=reason, diagnostics=AttemptDiagnostics())
    try:
        result = SimulationAttempt(**args)
    except ValueError:
        return
    expected = outcome == SimulationOutcome.UNSIMULATABLE and reason in {
        AttemptReason.NATIVE_UNSUPPORTED, AttemptReason.NATIVE_RULE_UNRESOLVED, AttemptReason.ENUMERATION_UNAVAILABLE,
    }
    assert result.fallback_eligible == expected


def guard_module():
    import importlib.util
    import sys

    folder = Path(__file__).resolve().parents[1] / "reports/manaengine_unknown_state_architecture"
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("phase_4k1b_typed_failure_guard", folder / "phase_4k1b_typed_failure_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_t21_inventory_and_source_guard_reject_regressions():
    guard = guard_module()
    assert guard.check() == []
    assert guard.source_problems('void x(){throw UnsupportedSimulationError("text");}')
    assert guard.source_problems('void x(){reject_unsupported("text");}')
    assert guard.source_problems('void x(){throw std::logic_error("new runtime path");}')
    assert guard.source_problems('void x(){throw UnsupportedSimulationError(FailureCode::INVALID_DAMAGE_PACKET,"detail");}') == []
    assert guard.source_problems('// reject_unsupported("text");\nconst char* s="throw UnsupportedSimulationError";') == []


def test_t19_append_only_code_ids_and_kinds():
    import json
    import re

    from manamind.integrations.manaengine.engine import _FAILURE_CODE_KINDS

    root = Path(__file__).resolve().parents[1]
    inventory = json.loads((root / "reports/manaengine_unknown_state_architecture/PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json").read_text())
    golden = {row["code"]: row["value"] for row in inventory["reason_codes"]}
    source = (root / "experiments/manaengine/include/manaengine/failure.hpp").read_text()
    actual = {name: int(value) for name, value in re.findall(r"^\s+([A-Z_]+) = (\d+),", source, re.MULTILINE)}
    assert actual == golden and len(actual) == len(set(actual.values())) == 57
    assert set(_FAILURE_CODE_KINDS) == set(golden)
    kind_names = {"Unsupported": FailureKind.UNSUPPORTED, "RuleUnresolved": FailureKind.RULE_UNRESOLVED,
                  "BudgetLimit": FailureKind.BUDGET_LIMIT, "EngineDefect": FailureKind.ENGINE_DEFECT}
    for row in inventory["reason_codes"]:
        assert _FAILURE_CODE_KINDS[row["code"]] == kind_names[row["future_kind"]]
