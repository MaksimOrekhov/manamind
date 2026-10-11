"""Census of SIDE_MISDIRECTION / SELF_HARM over finished LIVE recordings (read-only; writes one NEW report file).

  python scripts/consequence_diagnostics_report.py --shadow <outcome_shadow.jsonl ...> \
      --recordings-root <data/raw/live> --out <new file>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.outcome.diagnostics_analysis import census  # noqa: E402
from manamind.outcome.live_shadow import load_texts  # noqa: E402
from manamind.outcome.shadow_analysis import find_recordings, read_shadow_rows  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", nargs="+", required=True, type=Path)
    parser.add_argument("--recordings-root", required=True, type=Path)
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit("refusing to overwrite an existing report")
    rows, _ = read_shadow_rows(args.shadow)
    unique = {row["decision_id"]: row for row in rows if row.get("event") == "OUTCOME_SHADOW"}
    report = census(unique.values(), find_recordings(args.recordings_root), CardCatalog.from_json(args.cards),
                    load_texts(ROOT))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("games", "decisions", "SIDE_MISDIRECTION", "SELF_HARM")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
