"""Offline measurements against the installed checker; writes only a new output folder."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from manamind.card_ir.audit_render import render_audit
from manamind.card_ir.strict_v02 import validate_strict_any
from manamind.card_ir.validate_v02 import validate_declaration_v02
from manamind.card_metadata import CardMetadata

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(doc, meta, binding=None):
    try:
        base = validate_declaration_v02(doc, meta)
        structural = dict(ok=base.ok, errors=base.errors, status=base.computed_status,
                          rules=sorted(base.rules), elements=dict(sorted(base.elements.items())))
    except (TypeError, ValueError, KeyError, AttributeError, IndexError, RecursionError) as exc:
        structural = dict(ok=False, errors=[f"EXCEPTION: {type(exc).__name__}: {exc}"], status=None)
    strict = validate_strict_any(doc, meta, binding)
    return dict(structural=structural, strict=dict(accepted=strict.accepted, complete=strict.complete,
                status=strict.status, errors=strict.errors, warnings=strict.warnings)), strict


def measure(source, bindings, output):
    source = source.resolve()
    meta = CardMetadata.load()
    receipts = read(bindings)
    output.mkdir(parents=True, exist_ok=False)
    results = {}
    for card_id in read(ROOT / "protocol.json")["order"]:
        path = source / f"{card_id}.json"
        doc = read(path)
        binding = receipts.get(card_id)
        result, strict = check(doc, meta, binding)
        result.update(declaration=str(path.relative_to(ROOT)).replace("\\", "/"),
                      sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      dependencies=doc["dependencies"], decisions=doc["decisions"],
                      unexpressed=doc.get("unexpressed", []))
        results[card_id] = result
        (output / f"{card_id}.txt").write_text("\n".join(render_audit(doc, meta, binding, strict)) + "\n", encoding="utf-8")
    summary = dict(cards=len(results), structural_valid=sum(r["structural"]["ok"] for r in results.values()),
                   strict_valid=sum(r["strict"]["accepted"] for r in results.values()),
                   complete=sum(r["strict"]["complete"] for r in results.values()),
                   declared_complete=sum(r["strict"]["status"] in ("FULL", "FULL_DEP") for r in results.values()),
                   partial=sum(r["strict"]["status"] == "PARTIAL" for r in results.values()))
    (output / "measurement.json").write_text(json.dumps(dict(summary=summary, cards=results), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    for card_id, r in results.items():
        print(card_id, r["structural"]["errors"], r["strict"]["errors"], r["strict"]["warnings"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("bindings", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    measure(args.source, args.bindings, args.output)
