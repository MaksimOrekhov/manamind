"""Reject candidates overlapping frozen test identities, provenance, or exact contents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from manamind.training.model_first_1_control import validate_no_control_overlap


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="JSONL scenario file proposed for train/validation")
    args = parser.parse_args(argv)
    rows = [json.loads(line) for line in args.candidate.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    validate_no_control_overlap(rows)
    print(f"PASS: {len(rows)} candidate scenarios have no frozen test identity/provenance/content overlap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
