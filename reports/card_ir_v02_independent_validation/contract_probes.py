"""Post-baseline diagnostic followups, kept separate from the frozen 38-case metric."""
from __future__ import annotations

import copy

from author_first_pass import ROOT, write
from measure import check, read
from manamind.card_ir.audit_render import render_audit
from manamind.card_metadata import CardMetadata


def main():
    meta = CardMetadata.load()
    rows = []

    def record(id_, doc, finding, binding=None):
        result, report = check(doc, meta, binding)
        lines = render_audit(doc, meta, binding, report)
        rows.append(dict(id=id_, declaration=doc, finding=finding, **result, audit=lines))
        return lines

    cases = {r["id"]: r for r in read(ROOT / "negative_cases.json")}
    doc = copy.deepcopy(cases["torch_notes_only"]["declaration"])
    doc["abilities"][0]["effect"] = doc["abilities"][0]["effect"]["seq"][0]
    record("torch_notes_structured_followup", doc,
           "After removing the unrelated one-item-seq defect, no ADD_TO_HAND is present and the return/persistence is only in notes. Strict accepts FULL_DEP. This followup was not included retroactively in the initial negative metric.")
    doc = read(ROOT / "final/CATA_585.json")
    a = doc["abilities"][0]
    a["span"] += " " + doc.pop("unexpressed")[0]["span"]
    a["effect"] = dict(seq=[a["effect"], dict(op="ADD_TO_HAND", player="SELF", what=dict(from_zone="SELF"))])
    doc["dependencies"] = [d for d in doc["dependencies"] if d["id"] != "persistent_damage"]
    doc["decisions"] = [d for d in doc["decisions"] if d.get("dep") != "persistent_damage"]
    doc["status"] = "FULL_DEP"
    record("torch_legacy_short_source", doc,
           "Structurally accepted short source SELF still crashes a legacy lint .get call; strict turns the exception into rejection. That is fail-closed shape handling, not detection of missing excess.")
    doc = read(ROOT / "final/TIME_216.json")
    doc["abilities"][0]["target"]["choose"]["n"] = 99
    lines = record("selector_n_render", doc,
                   "n=99 on CHOSEN is structurally and strictly accepted but absent from audit rendering; selector cardinality should be constrained to contexts where it has a meaning or shown explicitly.")
    assert "99" not in "\n".join(lines)
    doc = read(ROOT / "final/TIME_216.json")
    steps = doc["abilities"][0]["effect"]["seq"]
    steps[0]["as"] = "damage_result"
    steps[1]["then"] = {"if": {"cmp": [dict(stat="HEALTH", of=dict(ref="damage_result")), ">", 0]}, "then": steps[1]["then"]}
    lines = record("damage_binding_render", doc,
                   "DEAL_DAMAGE as damage_result is legal and used by a later guard, but audit rendering omits the binding introduction; references are shown without their definition.")
    assert "as <damage_result>" not in "\n".join(lines)
    doc = read(ROOT / "final/EDR_895.json")
    for dependency in doc["dependencies"]:
        if dependency["scope"] == "CORE":
            dependency["scope"] = "CONDITIONAL"
    doc["status"] = "FULL_DEP"
    record("aviana_assumptions_still_visible", doc,
           "FULL_DEP passes on unresolved activation/new-card assumptions. The audit DOES show UNKNOWN decisions/dependencies; the defect is trusting status or author-selected scope, not a hidden executable rule.")
    doc = read(ROOT / "final/CORE_BT_921.json")
    doc["abilities"] = None
    record("malformed_document", doc, "Invalid collection shape must reject and audit must show the original malformed content.")
    write(ROOT / "contract_probes.json", dict(phase="Post-fix diagnostic followups, not part of frozen before/after count", cases=rows))
    print([(r["id"], r["strict"]["accepted"], r["strict"]["complete"]) for r in rows])


if __name__ == "__main__":
    main()
