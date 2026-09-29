"""Audit and import all one-match Power.log files from a local folder."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
import warnings
from pathlib import Path

from audit_power_log import audit_log
from import_power_log import import_power_log


def import_folder(input_dir: Path, output_dir: Path, catalog_path: Path) -> dict:
    log_files = sorted(input_dir.glob("*.log"))
    report = {
        "logs_found": len(log_files),
        "new_games_imported": 0,
        "duplicate_logs_skipped": 0,
        "rejected_logs": 0,
        "examples_written": 0,
        "results": [],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    for index, log_path in enumerate(log_files, start=1):
        try:
            audit = audit_log(log_path)
            if not audit.get("eligible_for_capture"):
                report["rejected_logs"] += 1
                report["results"].append({
                    "log_number": index,
                    "status": "rejected",
                    "reason": audit.get("reason", "log is not eligible"),
                })
                continue

            output_path = output_dir / f"{uuid.uuid4().hex}.jsonl"
            converted = import_power_log(log_path, output_path, catalog_path)
            if converted.get("duplicate"):
                report["duplicate_logs_skipped"] += 1
                status = "duplicate_skipped"
            else:
                report["new_games_imported"] += 1
                report["examples_written"] += converted["examples_written"]
                status = "imported"
            report["results"].append({
                "log_number": index,
                "status": status,
                "examples_written": converted["examples_written"],
                "result": converted.get("result"),
                "turns": converted.get("turns"),
            })
        except Exception as error:
            report["rejected_logs"] += 1
            report["results"].append({
                "log_number": index,
                "status": "rejected",
                "reason": f"processing failed ({type(error).__name__})",
            })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed_real"))
    parser.add_argument(
        "--cards", type=Path, default=Path("data/cards/standard_current_enUS.json")
    )
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        parser.error(f"input directory does not exist: {args.input_dir}")
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    report = import_folder(args.input_dir, args.output_dir, args.cards)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["rejected_logs"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
