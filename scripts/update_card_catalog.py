"""Build a date-stamped Standard catalog from HearthstoneJSON card data."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = "https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "cards" / "standard_sets.json"
DEFAULT_OUTPUT = ROOT / "data" / "cards" / "standard_current_enUS.json"


def read_source(source_file: Path | None) -> tuple[list[dict], str]:
    if source_file is not None:
        payload = json.loads(source_file.read_text(encoding="utf-8-sig"))
        source = str(source_file.resolve())
    else:
        request = Request(SOURCE_URL, headers={"User-Agent": "ManaMind card catalog updater"})
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
            source = response.geturl()
    if not isinstance(payload, list):
        raise ValueError("Card source must be a JSON list")
    if any(not isinstance(card, dict) for card in payload):
        raise ValueError("Card source contains a non-object record")
    return payload, source


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
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
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-file", type=Path, help="Use a previously downloaded card JSON file")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    allowed_sets = set(manifest.get("standard_sets", []))
    raw_card_ids = manifest.get("standard_card_ids", [])
    if manifest.get("format") != "STANDARD" or not allowed_sets:
        raise ValueError("Manifest must define format=STANDARD and a non-empty standard_sets list")
    if (
        not isinstance(raw_card_ids, list)
        or any(not isinstance(card_id, str) or not card_id for card_id in raw_card_ids)
        or len(set(raw_card_ids)) != len(raw_card_ids)
    ):
        raise ValueError("standard_card_ids must be a list of unique non-empty strings")
    allowed_card_ids = set(raw_card_ids)

    source_cards, resolved_source = read_source(args.source_file)
    ids = [card.get("id") for card in source_cards]
    if any(not card_id for card_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Card source has missing or duplicate card IDs")

    available_sets = {str(card.get("set", "")) for card in source_cards}
    missing_sets = allowed_sets - available_sets
    if missing_sets:
        raise ValueError(f"Manifest set IDs missing from source: {sorted(missing_sets)}")

    source_by_id = {card["id"]: card for card in source_cards}
    missing_card_ids = allowed_card_ids - set(source_by_id)
    if missing_card_ids:
        raise ValueError(
            f"Manifest Standard card IDs missing from source: {sorted(missing_card_ids)}"
        )
    non_collectible_card_ids = {
        card_id
        for card_id in allowed_card_ids
        if source_by_id[card_id].get("collectible") is not True
    }
    if non_collectible_card_ids:
        raise ValueError(
            "Manifest Standard card IDs must be collectible: "
            f"{sorted(non_collectible_card_ids)}"
        )

    selected = [
        card for card in source_cards
        if card.get("collectible") is True
        and (card.get("set") in allowed_sets or card.get("id") in allowed_card_ids)
    ]
    if not selected:
        raise ValueError("No collectible cards matched the Standard set manifest")
    selected.sort(key=lambda card: card["id"])

    output = {
        "schema_version": 1,
        "game": "Hearthstone",
        "format": "STANDARD",
        "valid_as_of": manifest["valid_as_of"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "HearthstoneJSON latest collectible card data",
        "source_url": SOURCE_URL,
        "resolved_source": resolved_source,
        "manifest": str(args.manifest.resolve()),
        "standard_sets": sorted(allowed_sets),
        "standard_card_ids": sorted(allowed_card_ids),
        "source_collectible_count": len(source_cards),
        "standard_card_count": len(selected),
        "cards": selected,
    }
    atomic_write(args.output, output)

    counts = Counter(card["set"] for card in selected)
    print(f"Updated {args.output}: {len(selected)} cards (source records: {len(source_cards)})")
    print(f"Data build: {resolved_source}")
    for set_id in sorted(counts):
        print(f"  {set_id}: {counts[set_id]}")


if __name__ == "__main__":
    main()
