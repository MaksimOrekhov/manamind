"""Build a separate preview catalog for an upcoming Hearthstone card set."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from update_card_catalog import SOURCE_URL, atomic_write, read_source

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "cards" / "preview_BE_enUS.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="set_id", default="BE")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--source-file", type=Path, help="Use a previously downloaded card JSON file"
    )
    args = parser.parse_args()

    source_cards, resolved_source = read_source(args.source_file)
    source_ids = [card.get("id") for card in source_cards]
    if any(not card_id for card_id in source_ids) or len(set(source_ids)) != len(source_ids):
        raise ValueError("Card source has missing or duplicate card IDs")

    selected = [
        card
        for card in source_cards
        if card.get("collectible") is True and card.get("set") == args.set_id
    ]
    if not selected:
        raise ValueError(f"No collectible cards found for preview set {args.set_id!r}")
    selected.sort(key=lambda card: card["id"])

    preview = {
        "schema_version": 1,
        "game": "Hearthstone",
        "format": "PREVIEW",
        "set": args.set_id,
        "valid_as_of": datetime.now(timezone.utc).date().isoformat(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "HearthstoneJSON latest collectible card data",
        "source_url": SOURCE_URL,
        "resolved_source": resolved_source,
        "source_collectible_count": len(source_cards),
        "preview_card_count": len(selected),
        "cards": selected,
    }
    atomic_write(args.output, preview)

    print(
        f"Updated {args.output}: {len(selected)} collectible preview cards "
        f"from set {args.set_id} (source records: {len(source_cards)})"
    )
    print(f"Data build: {resolved_source}")
    print("Preview metadata only; not Standard-legal or ready for simulator training.")


if __name__ == "__main__":
    main()
