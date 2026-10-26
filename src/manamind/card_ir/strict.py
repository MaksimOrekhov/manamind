"""Opt-in acceptance of v0.1, without changing its frozen language or historical tools.

Gap bindings are an external audit receipt, not executable IR. They must be supplied
explicitly, never inferred afresh from the declaration being checked: otherwise a
deleted dependency could silently disappear from both sides of the comparison.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from manamind.card_ir.lint import lint_declaration
from manamind.card_ir.semantic_lint import lint_semantics
from manamind.card_ir.strict_lint import lint_strict
from manamind.card_ir.validate import validate_declaration


def walk(value: Any, path: str = ""):
    yield path, value
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from walk(child, f"{path}/{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, f"{path}/{i}")


@dataclass
class StrictReport:
    card_id: str
    status: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def accepted(self):
        """Accepts honest PARTIAL; this is not semantic gold or execution readiness."""
        return not self.errors and not self.warnings

    @property
    def complete(self):
        return self.accepted and self.status in ("FULL", "FULL_DEP")


def _gaps(doc, bindings, errors):
    deps = {d["id"]: d for d in doc["dependencies"]}
    if len(deps) != len(doc["dependencies"]):
        errors.append("DEPENDENCY_ID: duplicate dependency IDs")
    linked = {n[k] for section in ("abilities", "keywords", "decisions")
              for _, n in walk(doc.get(section, [])) if isinstance(n, Mapping)
              for k in ("dep", "unknown") if isinstance(n.get(k), str)}
    gaps = doc.get("unexpressed", [])
    if bindings is None:
        if gaps:
            errors.append("GAP_BINDINGS: explicit external bindings required for every unexpressed span")
    else:
        if not isinstance(bindings, Mapping) or set(bindings) != {"card_id", "snapshot", "text_sha256", "gaps"}:
            errors.append("GAP_BINDINGS: expected card_id/snapshot/text_sha256/gaps receipt")
            return
        if any(bindings.get(k) != doc[k] for k in ("card_id", "snapshot", "text_sha256")):
            errors.append("GAP_BINDINGS: receipt belongs to different card/text/snapshot")
        entries = bindings.get("gaps")
        if not isinstance(entries, list):
            errors.append("GAP_BINDINGS: gaps must be a list")
            return
        seen = set()
        for entry in entries:
            if not isinstance(entry, Mapping) or set(entry) != {"gap", "span", "why", "dependencies"}:
                errors.append("GAP_BINDINGS: expected gap/span/why/dependencies entry")
                continue
            path = entry["gap"]
            if not isinstance(path, str) or not re.fullmatch(r"/unexpressed/\d+", path):
                errors.append("GAP_BINDINGS: gap must point to /unexpressed/index")
                continue
            i = int(path.rsplit("/", 1)[1])
            if path in seen or i >= len(gaps):
                errors.append(f"GAP_BINDINGS: duplicate or missing gap {path}")
                continue
            seen.add(path)
            if any(entry[k] != gaps[i][k] for k in ("span", "why")):
                errors.append(f"GAP_BINDINGS: stale span/reason at {path}")
            ids = entry["dependencies"]
            if not isinstance(ids, list) or not ids or not all(isinstance(d, str) for d in ids):
                errors.append(f"GAP_BINDINGS: {path} needs explicit dependency IDs")
                continue
            for dep_id in ids:
                if dep_id not in deps:
                    errors.append(f"GAP_DEPENDENCY: {path} requires missing {dep_id!r}")
            if not any(deps.get(d, {}).get("scope") == "CORE" for d in ids):
                errors.append(f"GAP_DEPENDENCY: {path} needs a CORE gap dependency")
            linked.update(ids)
        if seen != {f"/unexpressed/{i}" for i in range(len(gaps))}:
            errors.append("GAP_BINDINGS: each unexpressed span needs exactly one binding")
    for i, gap in enumerate(gaps):
        why = gap["why"]
        if (not isinstance(why, str) or not re.search(r"[A-Za-zА-Яа-яЁё]", why)
                or re.fullmatch(r"\s*(?:unknown|unsupported|todo|tbd|n/?a|probe|flavou?r|reminder|неизвестно)\W*", why, re.I)):
            errors.append(f"GAP_REASON: /unexpressed/{i} needs an explanation, not a placeholder")
    for dep_id, dep in deps.items():
        if dep["scope"] == "CORE" and dep_id not in linked:
            errors.append(f"CORE_ORPHAN: {dep_id!r} has no gap, unknown node or decision reference")


# Deliberately narrow: only a parenthesized UI progress readout is non-operative.
# Keyword explanations/prose are NOT silently trusted; put them through explicit
# review or leave them as a linked PARTIAL gap until a reminder contract exists.
_DISPLAY = re.compile(r"\(\d+\s*(?:/\s*\d+|(?:turns? |uses? |charges? )?(?:left|remaining))!?\)", re.I)


def validate_strict(doc: Mapping[str, Any], meta: Any, bindings: Mapping | None = None) -> StrictReport:
    report = StrictReport(str(doc.get("card_id")) if isinstance(doc, Mapping) else "?")
    if not isinstance(doc, Mapping):
        report.errors.append("STRUCTURE: declaration must be an object")
        return report
    try:
        base = validate_declaration(doc, meta)
        report.errors.extend(base.errors)
        report.status = base.computed_status
        if base.errors:
            return report
        for section in ("abilities", "keywords"):
            for path, node in walk(doc.get(section, []), f"/{section}"):
                if isinstance(node, Mapping):
                    if "damaged" in node and not isinstance(node["damaged"], bool):
                        report.errors.append(f"STRUCTURE: {path}/damaged must be a boolean")
                    for key in ("amount", "n", "count", "attack", "health", "reduce", "set", "turns", "uses", "options", "goal", "spell_damage"):
                        if isinstance(node.get(key), bool):
                            report.errors.append(f"STRUCTURE: {path}/{key} must not be a boolean number")
        _gaps(doc, bindings, report.errors)
        for i, reminder in enumerate(doc.get("reminders", [])):
            if not isinstance(reminder["why"], str) or not reminder["why"].strip():
                report.errors.append(f"REMINDER: /reminders/{i} needs a display explanation")
            if not _DISPLAY.fullmatch(reminder["span"]):
                report.errors.append(f"REMINDER: /reminders/{i} is not a non-operative progress readout")
        report.warnings.extend(lint_declaration(doc))
        report.warnings.extend(lint_semantics(doc))
        report.warnings.extend(lint_strict(doc))
    except (TypeError, ValueError, KeyError, AttributeError, IndexError, RecursionError) as exc:
        # The legacy walker assumes typed JSON after a few shape checks. The strict
        # boundary must reject malformed input instead of crashing or accepting it.
        report.errors.append(f"STRUCTURE: malformed declaration ({type(exc).__name__})")
    return report
