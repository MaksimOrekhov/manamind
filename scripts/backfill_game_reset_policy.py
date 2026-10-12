"""POLICY-GAME-RESET-RECOVERY-1: re-import saved raw matches that the Policy importer used to reject for GAME_RESET.

Selects raw slices that contain a GAME_RESET block and runs the unchanged canonical importer
(``import_policy_power_log.import_log``) on each, into a NEW output directory - existing datasets are never written.
Afterwards every imported ``game_id`` is checked against the given existing Policy datasets; an overlap is reported
and makes the command fail. Raw logs are only read. Output: counts and reasons only, no log text or names.

  python scripts/backfill_game_reset_policy.py data/raw/collected --output data/processed_game_reset_recovery_1/policy \
      --existing data/processed_policy_real/collected
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from import_policy_power_log import import_log  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError  # noqa: E402

RESET_MARKER = "BLOCK_START BlockType=GAME_RESET"


def reset_slices(raw_dir: Path) -> dict[Path, int]:
    """{raw slice: number of GAME_RESET events} (GameState lines only; PowerTaskList repeats each one)."""
    found = {}
    for path in sorted(Path(raw_dir).glob("*.log")):
        with path.open(encoding="utf-8", errors="replace") as stream:
            events = sum(RESET_MARKER in line and "GameState.DebugPrintPower()" in line for line in stream)
        if events:
            found[path] = events
    return found


def game_ids(directory: Path) -> set[str]:
    ids = set()
    for path in Path(directory).glob("*.audit.json"):
        ids.add(json.loads(path.read_text(encoding="utf-8"))["game_id"])
    for path in Path(directory).glob("*.jsonl"):
        with path.open(encoding="utf-8") as stream:
            ids.update(json.loads(line)["game_id"] for line in stream if line.strip())
    return ids


def backfill(raw_dir: Path, output: Path, catalog: CardCatalog, existing: list[Path]) -> dict:
    if output.exists():
        raise SystemExit(f"refusing to write into an existing directory: {output}")
    slices = reset_slices(raw_dir)
    games, labeled, total = 0, 0, 0
    decision_reasons, game_reasons, per_slice = Counter(), Counter(), []
    for path in slices:
        try:
            result = import_log(path, output, catalog, segmented=True)
        except PolicyImportError as error:
            game_reasons[error.reason] += 1
            per_slice.append({"status": "REJECTED", "reason": error.reason})
            continue
        games += result["games_imported"]
        labeled += result["decisions_labeled"]
        total += result["decisions_total"]
        decision_reasons.update(result["decision_skip_reasons"])
        game_reasons.update(result["game_skip_reasons"])
        per_slice.append({"status": "IMPORTED" if result["games_imported"] else "REJECTED",
                          "labeled": result["decisions_labeled"], "game_skip_reasons": result["game_skip_reasons"],
                          "decision_skip_reasons": result["decision_skip_reasons"]})
    imported = game_ids(output) if output.exists() else set()
    overlaps = {str(directory): len(imported & game_ids(directory)) for directory in existing}
    return {"raw_slices_with_game_reset": len(slices), "game_reset_events": sum(slices.values()),
            "games_imported": games, "decisions_labeled": labeled,
            "decisions_total": total, "decision_skip_reasons": dict(sorted(decision_reasons.items())),
            "game_skip_reasons": dict(sorted(game_reasons.items())), "overlap_with_existing": overlaps,
            "slices": per_slice}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="NEW directory for the recovered Policy rows")
    parser.add_argument("--existing", type=Path, nargs="*", default=[], help="Policy datasets to check for duplicates")
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    args = parser.parse_args(argv)
    summary = backfill(args.raw, args.output, CardCatalog.from_json(args.cards), args.existing)
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 1 if any(summary["overlap_with_existing"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
