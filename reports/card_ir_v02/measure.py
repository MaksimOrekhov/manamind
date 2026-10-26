"""Deterministic CARD-IR-V02 measurements: examples, conformance cases, history, diagnostics, mutations.

Historical declarations, receipts and tools are read only. Writes a new file and refuses to overwrite.

    python -I reports/card_ir_v02/measure.py --output <new-results>.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from conformance import build_cases, read  # noqa: E402
from manamind.card_ir.audit_render import render_audit  # noqa: E402
from manamind.card_ir.render_v02 import render_v02  # noqa: E402
from manamind.card_ir.strict import validate_strict  # noqa: E402
from manamind.card_ir.strict_v02 import validate_strict_any, validate_strict_v02  # noqa: E402
from manamind.card_ir.validate import validate_declaration  # noqa: E402
from manamind.card_ir.validate_v02 import validate_declaration_v02  # noqa: E402
from manamind.card_ir.vocabulary import ELEMENTS, RULES  # noqa: E402
from manamind.card_ir.vocabulary_v02 import ELEMENTS_V02, PROVISIONAL_RULES, RULES_V02  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402


def payload(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def examples(meta):
    receipts = read(HERE / "examples/gap_bindings.json")
    rows = []
    for path in sorted((HERE / "examples").glob("*.json")):
        if path.stem == "gap_bindings":
            continue
        doc = read(path)
        receipt = receipts.get(doc["card_id"])
        report = validate_strict_v02(doc, meta, receipt)
        base = validate_declaration_v02(doc, meta)
        legacy = validate_declaration(doc, meta)
        rows.append({"card_id": doc["card_id"], "status": report.status, "accepted": report.accepted,
                     "complete": report.complete, "errors": report.errors, "warnings": report.warnings,
                     "new_elements": sorted(e for e in base.elements if e not in ELEMENTS),
                     "rules": sorted(base.rules),
                     "provisional_acknowledged": sorted(d["rule"] for d in doc["dependencies"] if "rule" in d),
                     "dependencies": [f"{d['id']} {d['kind']}/{d['scope']}" for d in doc["dependencies"]],
                     "v01_validator_rejects": bool(legacy.errors), "v01_first_error": legacy.errors[:1],
                     "render": render_v02(doc, meta),
                     "audit": render_audit(doc, meta, receipt, report)})
    return rows


def conformance(meta):
    fixture_meta, cases = build_cases(meta)
    rows = []
    for case in cases:
        report = validate_strict_any(case["doc"], fixture_meta, case["bindings"])
        messages = report.errors + report.warnings
        if case["expect"] == "accept":
            lines = "\n".join(render_audit(case["doc"], fixture_meta, case["bindings"], report))
            missing = [text for text in case["render"] if text not in lines]
            passed = report.accepted and report.status == case["status"] and not missing
        else:
            missing = []
            passed = not report.accepted and any(case["code"] in m for m in messages)
        rows.append({"name": case["name"], "feature": case["feature"], "kind": case["kind"],
                     "origin": case["origin"], "expect": case["expect"], "code": case["code"],
                     "accepted": report.accepted, "status": report.status, "passed": passed,
                     "missing_render": missing, "messages": messages[:3]})
    by_feature = {}
    for row in rows:
        group = by_feature.setdefault(row["feature"], Counter())
        group[row["kind"]] += 1
        group["passed"] += row["passed"]
        group["total"] += 1
    return {"total": len(rows), "passed": sum(r["passed"] for r in rows),
            "by_kind": dict(sorted(Counter(r["kind"] for r in rows).items())),
            "by_origin": dict(sorted(Counter(r["origin"] for r in rows).items())),
            "by_feature": {k: dict(sorted(v.items())) for k, v in sorted(by_feature.items())}, "cases": rows}


def history(meta):
    links = read(ROOT / "reports/card_ir_validation_2/historical_gap_bindings.json")
    rows = []
    for folder in ("reports/card_ir_pilot_1/declarations", "reports/card_ir_stage_b1/final"):
        for path in sorted((ROOT / folder).glob("*.json")):
            doc = read(path)
            receipt = links.get(doc["card_id"])
            v01 = validate_strict(doc, meta, receipt)
            routed = validate_strict_any(doc, meta, receipt)
            v02 = validate_declaration_v02(doc, meta)
            rows.append({"card_id": doc["card_id"], "v01_status": v01.status, "v01_accepted": v01.accepted,
                         "dispatch_identical": (routed.errors, routed.warnings, routed.status) == (
                             v01.errors, v01.warnings, v01.status),
                         "v02_validator_rejects_version": any("ir must be card-ir/0.2" in e for e in v02.errors)})
    return {"total": len(rows), "v01_accepted": sum(r["v01_accepted"] for r in rows),
            "dispatch_identical": sum(r["dispatch_identical"] for r in rows),
            "v02_rejects_version": sum(r["v02_validator_rejects_version"] for r in rows),
            "status": dict(sorted(Counter(r["v01_status"] for r in rows).items())), "rows": rows}


def diagnostics(meta):
    """The nine Opus diagnostics, relabelled card-ir/0.2: v0.2 must not reopen any of them."""
    data = read(ROOT / "reports/card_ir_b1_independent_review/diagnostics.json")["wrong_but_accepted"]
    rows = {}
    for name, row in data.items():
        doc = dict(row["declaration"], ir="card-ir/0.2")
        report = validate_strict_v02(doc, meta)
        rows[name] = {"rejected": not report.accepted, "reasons": (report.errors + report.warnings)[:3]}
    return {"total": len(rows), "rejected": sum(r["rejected"] for r in rows.values()), "rows": rows}


def mutations(meta):
    spec = importlib.util.spec_from_file_location("v02_mutants_A", ROOT / "reports/card_ir_pilot_1/mutants.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipts = read(HERE / "examples/gap_bindings.json")
    rows = []
    for path in sorted((HERE / "examples").glob("*.json")):
        if path.stem == "gap_bindings":
            continue
        doc = read(path)
        for operator in module.ORDER:
            changed = module.mutate(doc, operator)
            if changed is None or changed[0] == doc:
                continue
            report = validate_strict_v02(changed[0], meta, receipts.get(doc["card_id"]))
            rows.append({"card_id": doc["card_id"], "operator": operator, "site": changed[1],
                         "detected": not report.accepted})
    by_operator = {}
    for row in rows:
        group = by_operator.setdefault(row["operator"], Counter())
        group["total"] += 1
        group["detected"] += row["detected"]
    return {"total": len(rows), "detected": sum(r["detected"] for r in rows),
            "by_operator": {k: dict(v) for k, v in by_operator.items()},
            "undetected": [r for r in rows if not r["detected"]]}


def vocabulary():
    return {"elements_v01": len(ELEMENTS), "elements_v02": len(ELEMENTS_V02),
            "new_elements": sorted(set(ELEMENTS_V02) - set(ELEMENTS)),
            "rules_v01": len(RULES), "rules_v02": len(RULES_V02),
            "new_rules": sorted(set(RULES_V02) - set(RULES)),
            "changed_rules": sorted(r for r in RULES if RULES[r] != RULES_V02[r]),
            "provisional_rules": sorted(PROVISIONAL_RULES),
            "rule_bases_v02": dict(sorted(Counter(r.basis for r in RULES_V02.values()).items()))}


def build():
    meta = CardMetadata.load()
    return {"vocabulary": vocabulary(), "examples": examples(meta), "conformance": conformance(meta),
            "history": history(meta), "diagnostics_relabelled": diagnostics(meta), "mutations": mutations(meta)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    with args.output.open("xb") as stream:
        stream.write(payload(build()))


if __name__ == "__main__":
    main()
