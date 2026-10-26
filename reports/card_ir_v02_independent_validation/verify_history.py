"""Reproduce historical measurements into a new scratch directory, recording byte hashes."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

from author_first_pass import ROOT, write

REPO = ROOT.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.scratch.mkdir(exist_ok=False)
    checks = [
        ("reports/card_ir_pilot_1/select_sample.py", "reports/card_ir_pilot_1/protocol.json"),
        ("reports/card_ir_pilot_1/measure.py", "reports/card_ir_pilot_1/results.json"),
        ("reports/card_ir_pilot_1/mutants.py", "reports/card_ir_pilot_1/mutants.json"),
        ("reports/card_ir_pilot_1/engine_mapping.py", "reports/card_ir_pilot_1/engine_mapping.json"),
        ("reports/card_ir_stage_b1/select_sample.py", "reports/card_ir_stage_b1/protocol.json"),
        ("reports/card_ir_stage_b1/measure.py", "reports/card_ir_stage_b1/results.json"),
        ("reports/card_ir_validation_2/measure.py", "reports/card_ir_validation_2/results.json"),
        ("reports/card_ir_v02/measure.py", "reports/card_ir_v02_independent_validation/v02_after.json"),
    ]
    rows = []
    for i, (script, expected) in enumerate(checks):
        output = args.scratch / f"{i}.json"
        command = [sys.executable, "-I", script, "--output", str(output)]
        run = subprocess.run(command, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
        actual = output.read_bytes() if output.exists() else b""
        reference = (REPO / expected).read_bytes()
        rows.append(dict(script=script, expected=expected, exit_code=run.returncode,
                         bytes_equal=actual == reference,
                         actual_sha256=hashlib.sha256(actual).hexdigest(), expected_sha256=hashlib.sha256(reference).hexdigest(),
                         stderr=run.stderr, stdout=run.stdout))
        print(script, run.returncode, actual == reference)
    result = dict(checks=rows, passed=sum(r["exit_code"] == 0 and r["bytes_equal"] for r in rows), total=len(rows),
                  scope="Static declarations/measurements only, no engine execution or training; original files untouched")
    write(args.output, result)
    if result["passed"] != result["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
