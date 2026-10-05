"""Audit whether collected real examples can pass through the value pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from manamind.training.readiness import audit_real_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/processed_real"))
    parser.add_argument(
        "--cards", type=Path, default=Path("data/cards/standard_current_enUS.json"),
    )
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    try:
        report = audit_real_dataset(args.input_dir, args.cards, args.batch_size)
    except (OSError, ValueError, json.JSONDecodeError):
        # Paths and data values are intentionally omitted from the user-facing summary.
        print(json.dumps({"training_readiness": "INVALID_DATA", "audit_error": True}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
