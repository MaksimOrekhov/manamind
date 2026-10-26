"""Replay fixed numeric probes; output is exclusive and source declarations stay read-only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from manamind.card_ir.strict_v02 import validate_strict_v02  # noqa: E402
from manamind.card_ir.validate_v02 import validate_declaration_v02  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402


def probes():
    folder = REPO / "reports/card_ir_execution_pilot_1/declarations"
    docs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))}
    rows = [(f"original_{card}", "control", doc) for card, doc in docs.items()]
    for label, index, field, value in (("attack_7", 0, "attack", 7), ("attack_2", 0, "attack", 2),
                                      ("health_9", 0, "health", 9), ("second_attack_7", 1, "attack", 7),
                                      ("second_health_9", 1, "health", 9)):
        doc = copy.deepcopy(docs["FIR_906"])
        node = doc["abilities"][0]["effect"]["seq"][index]
        if index:
            node = node["then"]
        node[field] = value
        rows.append((label, "wrong", doc))
    for label, value in (("discard_2", 2), ("implicit_discard_one", None)):
        doc = copy.deepcopy(docs["FIR_906"])
        discard = doc["abilities"][0]["effect"]["seq"][1]["pay"]["discard"]
        if value is None:
            discard.pop("n")
        else:
            discard["n"] = value
        rows.append((label, "control" if value is None else "wrong", doc))
    return rows


def build():
    meta = CardMetadata.load()
    rows = []
    for name, kind, doc in probes():
        base = validate_declaration_v02(doc, meta)
        report = validate_strict_v02(doc, meta)
        rows.append(dict(id=name, kind=kind, declaration=doc, structural_valid=base.ok,
                         errors=report.errors, warnings=report.warnings, accepted=report.accepted,
                         complete=report.complete, status=report.status))
    return dict(cases=rows, summary={kind: dict(total=sum(r["kind"] == kind for r in rows),
                 accepted=sum(r["kind"] == kind and r["accepted"] for r in rows)) for kind in ("control", "wrong")},
                source_sha256={p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted((REPO / "src/manamind/card_ir").glob("*.py"))})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    value = build()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(value["summary"])
