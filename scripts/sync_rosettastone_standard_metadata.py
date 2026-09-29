"""Write the current collectible Standard catalog as a RosettaStone overlay."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "data" / "cards" / "standard_current_enUS.json"
DEFAULT_MANIFEST = ROOT / "data" / "cards" / "standard_sets.json"
DEFAULT_OUTPUT = (
    ROOT
    / "vendor"
    / "RosettaStone"
    / "Resources"
    / "cards.standard_current.json"
)


def atomic_write(path: Path, cards: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(cards, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    allowed_sets = set(manifest.get("standard_sets", []))
    raw_card_ids = manifest.get("standard_card_ids", [])
    cards = catalog.get("cards") if isinstance(catalog, dict) else None
    if manifest.get("format") != "STANDARD" or not allowed_sets:
        raise ValueError("Manifest must define format=STANDARD and standard_sets")
    if (
        not isinstance(raw_card_ids, list)
        or any(not isinstance(card_id, str) or not card_id for card_id in raw_card_ids)
        or len(set(raw_card_ids)) != len(raw_card_ids)
    ):
        raise ValueError("standard_card_ids must be a list of unique non-empty strings")
    allowed_card_ids = set(raw_card_ids)
    if not isinstance(cards, list) or not cards:
        raise ValueError("Catalog must contain a non-empty cards list")

    selected = [
        card
        for card in cards
        if isinstance(card, dict)
        and card.get("collectible") is True
        and (card.get("set") in allowed_sets or card.get("id") in allowed_card_ids)
    ]
    ids = [card.get("id") for card in selected]
    if len(selected) != len(cards):
        raise ValueError(
            "Catalog must contain only collectible cards from the configured Standard sets"
        )
    if any(not card_id for card_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Catalog has missing or duplicate card IDs")
    missing_card_ids = allowed_card_ids - set(ids)
    if missing_card_ids:
        raise ValueError(
            "Catalog is missing configured Standard card IDs: "
            f"{sorted(missing_card_ids)}"
        )

    atomic_write(args.output, selected)
    counts: dict[str, int] = {}
    for card in selected:
        set_id = card["set"]
        counts[set_id] = counts.get(set_id, 0) + 1
    print(f"Wrote {len(selected)} Standard card records to {args.output}")
    for set_id in sorted(counts):
        print(f"  {set_id}: {counts[set_id]}")
    print("Metadata overlay only; this does not implement card effects or tokens.")


if __name__ == "__main__":
    main()
