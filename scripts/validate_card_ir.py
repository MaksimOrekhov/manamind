"""Strict, opt-in Card IR acceptance (v0.1 or v0.2, by the declaration's ``ir``) and human audit; no execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from manamind.card_ir.audit_render import render_audit  # noqa: E402
from manamind.card_ir.strict_v02 import validate_strict_any  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("declaration", type=Path)
    parser.add_argument("--bindings", type=Path, help="Explicit single receipt or card_id -> receipt registry")
    parser.add_argument("--audit-output", type=Path, help="Write expanded plain-text review; never overwrite")
    args = parser.parse_args()
    try:
        doc = json.loads(args.declaration.read_text(encoding="utf-8"))
        binding_data = json.loads(args.bindings.read_text(encoding="utf-8")) if args.bindings else None
        if binding_data is not None and not isinstance(binding_data, dict):
            parser.error("bindings must be an object")
        binding = (binding_data if "gaps" in binding_data else binding_data.get(doc.get("card_id"))) if binding_data else None
        if args.audit_output and args.audit_output.exists():
            parser.error("audit output already exists; refusing to overwrite")
    except (OSError, ValueError, AttributeError) as exc:
        parser.error(str(exc))
    meta = CardMetadata.load()
    result = validate_strict_any(doc, meta, binding)
    print(json.dumps({"card_id": result.card_id, "accepted": result.accepted, "complete": result.complete,
                      "status": result.status, "errors": result.errors, "warnings": result.warnings,
                      "semantic_gold": "NOT_MEASURED"}, ensure_ascii=False, indent=2))
    if args.audit_output and isinstance(doc, dict):
        lines = render_audit(doc, meta, binding, result)
        with args.audit_output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines) + "\n")
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
