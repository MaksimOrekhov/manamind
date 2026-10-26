"""Current strict verdicts vs immutable execution-pilot mutation measurements (no native run)."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from data_access import REPO, read, write_new
from manamind.card_ir.strict_v02 import validate_strict_v02
from manamind.card_metadata import CardMetadata


def build():
    folder = REPO / "reports/card_ir_execution_pilot_1"
    spec = importlib.util.spec_from_file_location("parity_historical_scenarios", folder / "scenarios.py")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module by name during construction.
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    meta = CardMetadata.load()
    rows = []
    for old in read(folder / "RESULTS.json")["rows"]:
        if "mutation" not in old:
            continue
        mutation = module.MUTATIONS[old["ir"]]
        doc = copy.deepcopy(read(folder / "declarations" / f"{mutation.card}.json"))
        mutation.change(doc)
        result = validate_strict_v02(doc, meta)
        before = old["mutation"]["validator"]
        after = "ACCEPTED" if result.accepted else "REJECTED"
        rows.append(dict(id=old["id"], before=before, after=after, changed=before != after,
                         findings=result.errors + result.warnings))
    return dict(native_execution=False, historical_files_changed=False, cases=rows,
                changed=[r["id"] for r in rows if r["changed"]],
                note="Original native execution outcomes are preserved; only strict validation of copied IR is re-measured.")


if __name__ == "__main__":
    data = build()
    write_new(Path(__file__).parent / "historical_v02_verdict_deltas.json", data)
    print("changed strict verdicts:", data["changed"])
