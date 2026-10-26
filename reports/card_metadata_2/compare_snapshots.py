"""Compare the pinned previous snapshot (build 253216) with the current one (build 255130).

Offline and deterministic: reads only data/card_metadata and the old collectible-only source file. Writes JSON with
sorted keys to --output (a new path; an existing file is never overwritten). Run from the repository root:

    python -I reports/card_metadata_2/compare_snapshots.py --output reports/card_metadata_2/compare_snapshots.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from manamind.card_metadata import CardMetadata  # noqa: E402
from manamind.card_metadata.compare import compare_snapshots  # noqa: E402

OLD_COLLECTIBLE = ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
PREVIEW = ROOT / "data/cards/preview_BE_enUS.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--old", default="hsjson_253216_enUS")
    parser.add_argument("--new", default=None, help="default: the manifest's current snapshot")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; refusing to overwrite")

    old, new = CardMetadata.load(args.old), CardMetadata.load(args.new)
    collectible_raw = OLD_COLLECTIBLE.read_bytes()
    collectible = json.loads(collectible_raw.decode("utf-8"))
    result = compare_snapshots(old, new, [card["id"] for card in collectible])
    by_id = {record["id"]: record for record in old.records()}
    result["old_collectible_file"] = {
        "path": str(OLD_COLLECTIBLE.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(collectible_raw).hexdigest(),
        "records": len(collectible),
        "records_identical_to_old_snapshot": all(by_id.get(card["id"]) == card for card in collectible),
    }
    preview = json.loads(PREVIEW.read_text(encoding="utf-8"))["cards"]
    new_by_id = {record["id"]: record for record in new.records()}
    result["preview_be_file"] = {
        "cards": [card["id"] for card in preview],
        "present_in_new_snapshot": sum(1 for card in preview if card["id"] in new_by_id),
        "changed_in_new_snapshot": [card["id"] for card in preview
                                    if card["id"] in new_by_id and any(new_by_id[card["id"]].get(k) != v for k, v in card.items())],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ("ids", "scope_effect", "new_set_totals")}, indent=1, sort_keys=True))
    print("changed:", json.dumps(result["changed"]["cause_groups"], sort_keys=True))


if __name__ == "__main__":
    main()
