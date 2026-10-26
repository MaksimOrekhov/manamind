"""Strict acceptance of Card IR v0.2 and a version dispatcher for strict acceptance.

v0.2 strict = the v0.2 structural validator + every validation-2 strict check (structure, gap receipts, CORE anchors,
reminders, both v0.1 lints, the strict lint) + the v0.2 text checks. Only the v0.1 strict-lint warnings listed in
``lint_v02.SUPERSEDED_V01`` are dropped, each replaced by a v0.2 check. Gap receipts and their migration file work
unchanged: they are external audit data, never inferred from the candidate.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from manamind.card_ir.lint import lint_declaration
from manamind.card_ir.lint_v02 import lint_v02, superseded
from manamind.card_ir.numeric_lint_v02 import lint_numeric_roles
from manamind.card_ir.semantic_lint import lint_semantics
from manamind.card_ir.strict import _NUMERIC, StrictReport, _gaps, _reminders, _structure, validate_strict
from manamind.card_ir.strict_lint import lint_strict
from manamind.card_ir.validate import IR_VERSION
from manamind.card_ir.validate_v02 import IR_VERSION_V02, validate_declaration_v02

SUPPORTED_VERSIONS = (IR_VERSION, IR_VERSION_V02)


def validate_strict_v02(doc: Mapping[str, Any], meta: Any, bindings: Mapping | None = None) -> StrictReport:
    report = StrictReport(str(doc.get("card_id")) if isinstance(doc, Mapping) else "?")
    if not isinstance(doc, Mapping):
        report.errors.append("STRUCTURE: declaration must be an object")
        return report
    try:
        base = validate_declaration_v02(doc, meta)
        report.errors.extend(base.errors)
        report.status = base.computed_status
        if base.errors:
            return report
        _structure(doc, report.errors, ("damaged", "alive"), (*_NUMERIC, "increase", "turn_starts"))
        _gaps(doc, bindings, report.errors)
        _reminders(doc, report.errors)
        report.warnings.extend(lint_declaration(doc))
        report.warnings.extend(lint_semantics(doc))
        report.warnings.extend(w for w in lint_strict(doc) if not superseded(w))
        report.warnings.extend(lint_v02(doc))
        report.warnings.extend(lint_numeric_roles(doc))
    except (TypeError, ValueError, KeyError, AttributeError, IndexError, RecursionError) as exc:
        report.errors.append(f"STRUCTURE: malformed declaration ({type(exc).__name__})")
    return report


def validate_strict_any(doc: Any, meta: Any, bindings: Mapping | None = None) -> StrictReport:
    """Strict acceptance by the declaration's own ``ir`` version; an unknown version is rejected, never guessed."""
    version = doc.get("ir") if isinstance(doc, Mapping) else None
    if version == IR_VERSION_V02:
        return validate_strict_v02(doc, meta, bindings)
    if version == IR_VERSION or not isinstance(doc, Mapping):
        return validate_strict(doc, meta, bindings)
    report = StrictReport(str(doc.get("card_id")))
    report.errors.append(f"VERSION: ir {version!r} is not one of {SUPPORTED_VERSIONS}")
    return report
