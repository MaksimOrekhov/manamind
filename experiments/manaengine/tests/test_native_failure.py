"""Real native funnel/resource exception round trip, including pybind MemoryError."""
import importlib.util
from pathlib import Path

import pytest

from manamind.integrations.manaengine.engine import _load_native


def probes():
    native = _load_native()
    folder = Path(native.__file__).parent
    path = next(folder.glob("manaengine_failure_probes.*"))
    spec = importlib.util.spec_from_file_location("manaengine_failure_probes", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_t16_real_bad_alloc_is_python_memoryerror():
    module = probes()
    with pytest.raises(MemoryError):
        module.exercise("bad_alloc")
    failure = module.snapshot()
    assert failure["kind"] == "ENGINE_DEFECT" and failure["code"] == "RESOURCE_EXHAUSTED"
    assert not failure["valid"] and failure["frames"] == 0
    assert "earlier soft failure" in failure["context"]


@pytest.mark.parametrize("mode,code", [("std_exception", "UNEXPECTED_EXCEPTION"), ("unknown", "UNKNOWN_EXCEPTION"), ("legacy", "LEGACY_UNTYPED")])
def test_t06_t17_t20_native_funnel_probes(mode, code):
    module = probes()
    module.exercise(mode)
    failure = module.snapshot()
    assert failure["kind"] == "ENGINE_DEFECT" and failure["code"] == code
    assert not failure["valid"] and "earlier soft failure" in failure["context"]
    if mode == "std_exception":
        assert "original std detail" in failure["detail"] and "logic_error" in failure["context"]


def test_t18_native_exception_payload_and_exact_echo():
    from manamind.integrations.manaengine import EngineDefectError, FailureKind, UnsupportedSimulationError
    from manamind.integrations.manaengine.engine import _wrap_native

    native = _load_native()
    assert issubclass(native.EngineDefectError, native.UnsupportedSimulationError)
    assert issubclass(EngineDefectError, UnsupportedSimulationError)
    with pytest.raises(native.UnsupportedSimulationError) as caught:
        native.GameSession([], [], native.CardCatalog([]), 0, False, "WARRIOR", "MAGE")
    exc = caught.value
    assert exc.kind == "UNSUPPORTED" and exc.code == "UNSUPPORTED_HERO_CLASS"
    wrapped = _wrap_native(exc)
    assert wrapped.failure.kind == FailureKind.UNSUPPORTED and wrapped.failure.detail == str(exc)
    assert wrapped.failure.context == exc.context


def test_t11_binding_perspective_is_valueerror():
    from manamind.integrations.manaengine import ManaEngineSession

    session = ManaEngineSession(["CORE_EX1_145"] * 30, ["CORE_EX1_145"] * 30,
                               player1_class="MAGE", player2_class="MAGE", shuffle=False)
    with pytest.raises(ValueError, match="perspective"):
        session._native.observation("BAD_PERSPECTIVE")
    assert session.is_valid and session.failure is None


def test_t19_native_code_table_matches_independent_inventory():
    import json

    native = _load_native()
    root = Path(__file__).resolve().parents[3]
    rows = json.loads((root / "reports/manaengine_unknown_state_architecture/PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json").read_text())["reason_codes"]
    kinds = {"Unsupported": native.FailureKind.UNSUPPORTED, "RuleUnresolved": native.FailureKind.RULE_UNRESOLVED,
             "BudgetLimit": native.FailureKind.BUDGET_LIMIT, "EngineDefect": native.FailureKind.ENGINE_DEFECT}
    for row in rows:
        code = getattr(native.FailureCode, row["code"])
        assert int(code) == row["value"]
        assert native.failure_kind_of(code) == kinds[row["future_kind"]]


def test_t16_attempt_propagates_actual_native_resource_exception():
    from manamind.integrations.manaengine import attempt_action
    from manamind.integrations.manaengine.engine import _execution_key

    module = probes()

    class ProbeSession:
        is_valid = True

        def _legal_execution_keys(self):
            return {_execution_key({"type": "END_TURN"}): {"type": "END_TURN"}}

        def clone(self):
            return ProbeSession()

        def _apply_raw(self, action):
            module.exercise("bad_alloc")

    parent = ProbeSession()
    with pytest.raises(MemoryError):
        attempt_action(parent, {"type": "END_TURN"}, perspective="PLAYER1")
    assert parent.is_valid and module.snapshot()["code"] == "RESOURCE_EXHAUSTED"
