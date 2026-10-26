"""Deterministic paired measurements; original declarations/tools are read-only."""
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
from cases import build_cases, read  # noqa: E402
from manamind.card_ir.audit_render import render_audit  # noqa: E402
from manamind.card_ir.lint import lint_declaration  # noqa: E402
from manamind.card_ir.semantic_lint import lint_semantics  # noqa: E402
from manamind.card_ir.strict import validate_strict  # noqa: E402
from manamind.card_ir.validate import validate_declaration  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402


def payload(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def run(doc, meta, binding=None):
    legacy = validate_declaration(doc, meta)
    before = legacy.errors + lint_declaration(doc) + lint_semantics(doc)
    after = validate_strict(doc, meta, binding)
    return {"before_detected": bool(before), "after_detected": not after.accepted,
            "before": before, "strict_errors": after.errors, "strict_warnings": after.warnings,
            "status": after.status}


def mutants(docs, meta, links):
    spec = importlib.util.spec_from_file_location("validation2_mutants_A", ROOT / "reports/card_ir_pilot_1/mutants.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = []
    for doc in docs:
        binding = links.get(doc["card_id"])
        assert validate_strict(doc, meta, binding).accepted, doc["card_id"]
        for operator in module.ORDER:
            changed = module.mutate(doc, operator)
            if changed is None or changed[0] == doc:
                continue
            candidate, site = changed
            rows.append({"card_id": doc["card_id"], "operator": operator, "site": site, **run(candidate, meta, binding)})
    summary = {"total": len(rows), "before_detected": sum(r["before_detected"] for r in rows),
               "after_detected": sum(r["after_detected"] for r in rows)}
    by_operator = {}
    for operator in module.ORDER:
        group = [r for r in rows if r["operator"] == operator]
        by_operator[operator] = {"total": len(group), "before_detected": sum(r["before_detected"] for r in group),
                                 "after_detected": sum(r["after_detected"] for r in group)}
    return {"summary": summary, "by_operator": by_operator, "details": rows}


def build():
    meta = CardMetadata.load()
    links = read(HERE / "historical_gap_bindings.json")
    diagnostic = read(ROOT / "reports/card_ir_b1_independent_review/diagnostics.json")
    nine = {name: run(row["declaration"], meta) for name, row in diagnostic["wrong_but_accepted"].items()}
    fixture_meta, pairs, controls = build_cases(meta)
    new = [{"name": c["name"], "group": c["group"], "origin": c["origin"],
            "bad": run(c["bad"], fixture_meta, c["bad_bindings"]),
            "good": run(c["good"], fixture_meta, c["good_bindings"])} for c in pairs]
    control_results = [run(doc, fixture_meta) for doc in controls]
    history, docs_by_group = {}, {}
    for name, folder in (("A", "reports/card_ir_pilot_1/declarations"), ("B1", "reports/card_ir_stage_b1/final")):
        docs = [read(p) for p in sorted((ROOT / folder).glob("*.json"))]
        docs_by_group[name] = docs
        history[name] = [{"card_id": d["card_id"], **run(d, meta, links.get(d["card_id"]))} for d in docs]
    table = {}
    for group in sorted({c["group"] for c in new}):
        items = [r for r in new if r["group"] == group]
        table[group] = {"wrong": len(items), "before": sum(i["bad"]["before_detected"] for i in items),
                        "after": sum(i["bad"]["after_detected"] for i in items),
                        "positive_controls": len(items), "false_alerts": sum(i["good"]["after_detected"] for i in items)}
    totals = Counter()
    for row in table.values():
        totals.update(row)
    # Review both the role-ambiguous counterfactual and the diagnostics: improved
    # rendering must expose exactly what the earlier render hid.
    cf = diagnostic["counterfactual"]["FIR_953"]["declaration"]
    cf_result = validate_strict(cf, meta)
    return {
        "id": "CARD-IR-VALIDATION-2", "base_commit": "0cfc3b0397494418427bb1f2a3f62701ad09c0c6",
        "baseline": "frozen validator + A lint + B1 semantic lint, not validator alone",
        "nine_summary": {"total": len(nine), "before": sum(r["before_detected"] for r in nine.values()),
                         "after": sum(r["after_detected"] for r in nine.values())},
        "nine": nine, "new_summary": dict(totals), "new_table": table, "new_pairs": new,
        "positive_summary": {"total": len(new) + len(controls),
                             "false_alerts": sum(r["good"]["after_detected"] for r in new) + sum(r["after_detected"] for r in control_results),
                             "known_conservative_reminder_rejections": sum(r["after_detected"] for r in control_results)},
        "extra_positive_controls": control_results, "historical_regressions": history,
        "mutations": {name: mutants(docs, meta, links) for name, docs in docs_by_group.items()},
        "audit_render_magma_counterfactual": render_audit(cf, meta, strict_report=cf_result),
        "audit_render_hidden_reminders": {name: render_audit(row["declaration"], meta)
                                           for name, row in diagnostic["wrong_but_accepted"].items()
                                           if "reminder" in name},
        "limitations": ["Model-authored tests are not independent gold or a measured real false-acceptance rate.",
                        "Paired mutations may commute/be equivalent; rates are detection, not semantic accuracy.",
                        "External gap receipts are explicit reviewed assertions, not proof their reasons are true.",
                        "Legacy callers remain permissive; strict acceptance requires opting into validate_strict/CLI.",
                        "Grammar is bounded; arbitrary English equivalence and unknown rules are not solved."],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    result = build()
    with args.output.open("xb") as stream:
        stream.write(payload(result))
    print("Nine:", result["nine_summary"])
    print("New paired cases:", result["new_summary"])
    for name, row in result["mutations"].items():
        print("Mutations", name, row["summary"])
