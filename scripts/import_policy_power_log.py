"""Import completed Ranked Standard log sections into a separate local policy dataset."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.integrations.powerlog.lines import read_complete_lines, split_games
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match
from manamind.live.snapshot import canonical_json
from manamind.training.real_policy import validate_example


def save_match(rows, summary, output_dir: Path) -> None:
    output_dir = Path(output_dir)
    if (output_dir / "INVALIDATED.json").exists():
        raise PolicyImportError("DATASET_INVALIDATED")
    # Value imports have their own schema and must never receive policy records.
    if "processed_real" in {part.lower() for part in output_dir.resolve().parts}:
        raise PolicyImportError("VALUE_DATASET_DESTINATION")
    output_dir.mkdir(parents=True, exist_ok=True)
    game_id = summary["game_id"]
    if not isinstance(game_id, str) or not re.fullmatch(r"[0-9a-f]{64}", game_id):
        raise PolicyImportError("INVALID_MATCH_ID")
    for path in output_dir.glob("*.audit.json"):
        if json.loads(path.read_text(encoding="utf-8"))["game_id"] == game_id:
            raise PolicyImportError("DUPLICATE_MATCH")
    for path in output_dir.glob("*.jsonl"):
        with path.open(encoding="utf-8") as stream:
            if any(json.loads(line)["game_id"] == game_id for line in stream if line.strip()):
                raise PolicyImportError("DUPLICATE_MATCH")
    target = output_dir / f"{game_id}.jsonl"
    manifest = output_dir / f"{game_id}.audit.json"
    if target.exists() or manifest.exists():
        raise PolicyImportError("DUPLICATE_MATCH")
    for row in rows:
        validate_example(row)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(canonical_json(row) + "\n")
    with manifest.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(summary) + "\n")


def import_log(log_path: Path, output_dir: Path, catalog: CardCatalog, *, segmented=False) -> dict:
    lines = read_complete_lines(log_path)
    if any(marker in line for line in lines for marker in
           ("Start Spectator Game", "Begin Spectating 1st player", "Begin Spectating 2nd player")):
        raise PolicyImportError("SPECTATOR")
    segments = split_games(lines)
    if not segments or (not segmented and len(segments) != 1):
        raise PolicyImportError("EXPECTED_ONE_MATCH")
    imported, labeled, total, decision_skips, game_skips = 0, 0, 0, Counter(), Counter()
    for segment in segments:
        try:
            rows, summary = extract_match(segment, catalog)
            save_match(rows, summary, output_dir)
            imported += 1
            labeled += len(rows)
            total += summary["decisions_total"]
            decision_skips.update(summary["skip_reasons"])
        except PolicyImportError as error:
            game_skips[error.reason] += 1
    return {"games_inspected": len(segments), "games_imported": imported,
            "decisions_total": total, "decisions_labeled": labeled,
            "decisions_skipped": sum(decision_skips.values()),
            "decision_skip_reasons": dict(sorted(decision_skips.items())),
            "game_skip_reasons": dict(sorted(game_skips.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed_policy_real"))
    parser.add_argument("--cards", type=Path, default=Path("data/cards/standard_current_enUS.json"))
    parser.add_argument("--segmented", action="store_true", help="Safely inspect each CREATE_GAME section")
    args = parser.parse_args()
    try:
        result = import_log(args.log_file, args.output_dir, CardCatalog.from_json(args.cards), segmented=args.segmented)
    except Exception as error:
        reason = error.reason if isinstance(error, PolicyImportError) else type(error).__name__
        print(json.dumps({"games_imported": 0, "reason": reason}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["games_imported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
