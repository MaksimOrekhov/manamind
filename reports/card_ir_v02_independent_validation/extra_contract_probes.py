"""Two late cost/render diagnostics, separate from before/after adversarial counts."""
from __future__ import annotations

from author_first_pass import ROOT, write
from measure import check, read
from manamind.card_ir.audit_render import render_audit
from manamind.card_metadata import CardMetadata


def main():
    meta = CardMetadata.load()
    rows = []
    for id_ in ("negative_cost_expression", "next_turn_render"):
        doc = read(ROOT / "final/CORE_SCH_713.json")
        if id_ == "negative_cost_expression":
            doc["abilities"][0]["effect"]["modifier"]["cost"]["increase"] = {"sub": [0, 1]}
        result, report = check(doc, meta)
        rows.append(dict(id=id_, declaration=doc, **result, audit=render_audit(doc, meta, strict_report=report)))
    write(ROOT / "extra_contract_probes.json", dict(phase="Post-fix diagnostics; excluded from frozen 38 cases", cases=rows))
    print([(r["id"], r["strict"]["accepted"], r["strict"]["complete"]) for r in rows])


if __name__ == "__main__":
    main()
