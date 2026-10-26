"""Evaluate the fixed adversarial corpus without tuning it; refuse output overwrite."""
from __future__ import annotations

import argparse
from collections import Counter

from author_first_pass import ROOT, write
from measure import check, read
from manamind.card_ir.audit_render import render_audit
from manamind.card_metadata import CardMetadata


def build():
    meta = CardMetadata.load()
    rows = []
    for case in read(ROOT / "negative_cases.json"):
        result, strict = check(case["declaration"], meta, case["bindings"])
        rows.append({k: case[k] for k in ("id", "card_id", "category", "kind", "witness")} | result | dict(
            audit=render_audit(case["declaration"], meta, case["bindings"], strict)))
    summary = {}
    for kind in sorted({r["kind"] for r in rows}):
        group = [r for r in rows if r["kind"] == kind]
        summary[kind] = dict(total=len(group), structure_accepted=sum(r["structural"]["ok"] for r in group),
                             strict_accepted=sum(r["strict"]["accepted"] for r in group),
                             accepted_complete=sum(r["strict"]["complete"] for r in group))
    summary["strict_accepted_categories"] = dict(Counter(r["category"] for r in rows if r["strict"]["accepted"] and r["kind"] != "equivalent_control"))
    return dict(summary=summary, cases=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    args = parser.parse_args()
    result = build()
    write(ROOT / args.output, result)
    print(result["summary"])
    for row in result["cases"]:
        print(row["id"], "ACCEPT" if row["strict"]["accepted"] else "REJECT", row["strict"]["status"], row["strict"]["errors"], row["strict"]["warnings"])
