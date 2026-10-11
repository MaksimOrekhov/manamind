"""Analyze outcome-shadow journals: coverage, invariants and (where the game is finished) a check against what happened.

  python scripts/outcome_shadow_report.py --shadow data/raw/live/prediction_journal.outcome_shadow.jsonl [...] \
      --recordings-root data/raw/live --out reports/<new>/shadow_report.json

Safe to run on a journal that is still being written and to re-run as games finish: rows of unfinished games are
reported as not joined, never guessed. Reads recordings (private) but writes only counts, hashes and card IDs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.outcome.live_shadow import load_texts  # noqa: E402
from manamind.outcome.shadow_analysis import (  # noqa: E402
    coverage_summary, find_recordings, group_decisions, read_shadow_rows, verify_recordings,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shadow", nargs="+", required=True, type=Path,
                        help="outcome-shadow JSONL files (rotated files included)")
    parser.add_argument("--recordings-root", type=Path, help="LIVE recordings: <root>/<session>/<game key>/slice.log")
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--out", type=Path, required=True, help="NEW file; an existing one is never overwritten")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit("refusing to overwrite an existing report")
    rows, bad_lines = read_shadow_rows(args.shadow)
    decisions = group_decisions(rows)
    report = {"inputs": {"shadow_files": [p.name for p in args.shadow], "rows": len(rows), "unreadable_lines": bad_lines},
              "coverage": coverage_summary(decisions)}
    if args.recordings_root is not None:
        report["against_recordings"] = verify_recordings(
            decisions, find_recordings(args.recordings_root), CardCatalog.from_json(args.cards), load_texts(ROOT))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    print(f"wrote {args.out.name}: {len(decisions)} decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
