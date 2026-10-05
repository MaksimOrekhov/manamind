"""Experimental ManaEngine backend; separate from the Rosetta adapter."""

from .engine import EngineDefectError, FailureKind, ManaEngineSession, NativeFailure, UnsupportedSimulationError
from .simulation import (
    AttemptDiagnostics, AttemptReason, InvalidParentSession, SimulationAttempt,
    SimulationOutcome, acting_seat, attempt_action,
)

__all__ = [
    "EngineDefectError", "FailureKind", "NativeFailure", "ManaEngineSession", "UnsupportedSimulationError", "AttemptDiagnostics", "AttemptReason",
    "InvalidParentSession", "SimulationAttempt", "SimulationOutcome", "acting_seat", "attempt_action",
]
