from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_overlay_window import _REQUIRED_CHECKS, smoke_passed  # noqa: E402


def test_smoke_passes_only_when_every_required_result_is_true():
    result = {name: True for name in _REQUIRED_CHECKS}
    assert smoke_passed(result)


@pytest.mark.parametrize("failed_check", _REQUIRED_CHECKS)
def test_each_required_smoke_failure_changes_exit_decision(failed_check: str):
    result = {name: True for name in _REQUIRED_CHECKS}
    result[failed_check] = False
    assert not smoke_passed(result)


def test_smoke_fails_if_a_required_result_is_missing_or_window_check_raised():
    result = {name: True for name in _REQUIRED_CHECKS}
    del result["warning_en"]
    assert not smoke_passed(result)
    result["warning_en"] = True
    result["failure_class"] = "RuntimeError"
    assert not smoke_passed(result)
