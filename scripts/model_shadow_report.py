"""Compare Policy v2, Retrained v2 and Policy v3 recommendations after one or more matches (local, read-only).

Reads the model-shadow journal(s) written by ``run_manamind.py --model-shadow`` (rotated files included) and,
optionally, the Policy prediction journal to prove the displayed Top-3 was not changed. Prints a short summary and
writes the full JSON to a new file. Nothing is trained, nothing in the game data is modified.

  python scripts/model_shadow_report.py                       # default journals under data/raw/live
  python scripts/model_shadow_report.py --out reports/<new dir>/shadow_report.json --examples 8
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.policy_shadow.analysis import analyse, read_journal, render  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--journal", type=Path, nargs="*",
                        help="model-shadow journal files; default: <data-root>/raw/live/prediction_journal.model_shadow*.jsonl")
    parser.add_argument("--prediction-journal", type=Path, help="Policy journal for the displayed-Top-3 cross-check")
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    parser.add_argument("--examples", type=int, default=5, help="examples listed per disagreement category")
    parser.add_argument("--out", type=Path, help="write the full report here (a NEW file)")
    args = parser.parse_args(argv)
    live = args.data_root / "raw/live"
    paths = args.journal or sorted(live.glob("prediction_journal.model_shadow*.jsonl"))
    if not paths:
        print("no model-shadow journal found; run run_manamind.py with --model-shadow first")
        return 1
    primary_path = args.prediction_journal or live / "prediction_journal.jsonl"
    primary_rows = read_journal([primary_path]) if primary_path.is_file() else None
    report = analyse(read_journal(paths), primary_rows, examples=args.examples)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    print(render(report))
    if primary_rows is None:
        print("note: Policy prediction journal not found; displayed Top-3 not cross-checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
