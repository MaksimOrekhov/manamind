"""Audit current Standard card metadata against the pinned RosettaStone checkout.

This is a preflight report, not proof that a card's rules are implemented. The
simulator keeps card metadata in Resources/cards.json and card behavior in C++
CardSets sources, so both inventories need separate follow-up work.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "data" / "cards" / "standard_current_enUS.json"
DEFAULT_ENGINE_CARDS = ROOT / "vendor" / "RosettaStone" / "Resources" / "cards.json"
DEFAULT_ENGINE_OVERLAY = ROOT / "vendor" / "RosettaStone" / "Resources" / "cards.standard_current.json"
DEFAULT_CARD_SOURCES = ROOT / "vendor" / "RosettaStone" / "Sources" / "Rosetta" / "PlayMode" / "CardSets"


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def audit(catalog_path: Path, engine_cards_path: Path, engine_overlay_path: Path, source_dir: Path) -> dict:
    catalog = load_json(catalog_path)
    engine_cards = load_json(engine_cards_path)
    engine_overlay = load_json(engine_overlay_path) if engine_overlay_path.exists() else []
    if not isinstance(catalog, dict) or not isinstance(catalog.get("cards"), list):
        raise ValueError(f"Catalog has no cards list: {catalog_path}")
    if not isinstance(engine_cards, list):
        raise ValueError(f"RosettaStone card resource is not a list: {engine_cards_path}")
    if not isinstance(engine_overlay, list):
        raise ValueError(f"RosettaStone card overlay is not a list: {engine_overlay_path}")

    current_cards = catalog["cards"]
    current_ids = {card["id"] for card in current_cards if isinstance(card, dict) and card.get("id")}
    engine_by_id = {
        card["id"]: card
        for card in engine_cards
        if isinstance(card, dict) and card.get("id")
    }
    engine_ids = set(engine_by_id)
    overlay_ids = {
        card["id"]
        for card in engine_overlay
        if isinstance(card, dict) and card.get("id")
    }
    loaded_ids = engine_ids | overlay_ids

    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(source_dir.glob("*CardsGen.cpp"))
    )
    # Existing RosettaStone card implementations are registered using
    # cards.emplace("CARD_ID", cardDef). This is an inventory hint only.
    scripted_ids = set(re.findall(r'cards\.emplace\(\s*"([A-Za-z0-9_]+)"', source_text))

    by_set: dict[str, list[dict]] = {}
    for card in current_cards:
        if isinstance(card, dict) and card.get("id"):
            by_set.setdefault(str(card.get("set", "UNKNOWN")), []).append(card)

    set_rows = []
    for set_id, cards in sorted(by_set.items()):
        ids = {card["id"] for card in cards}
        set_rows.append(
            {
                "set_id": set_id,
                "catalog_cards": len(ids),
                "metadata_in_base_resource": len(ids & engine_ids),
                "metadata_in_current_overlay": len(ids & overlay_ids),
                "metadata_missing_after_merge": len(ids - loaded_ids),
                "ids_registered_in_card_set_sources_heuristic": len(ids & scripted_ids),
            }
        )

    missing_metadata = sorted(current_ids - loaded_ids)
    return {
        "format": catalog.get("format"),
        "catalog_valid_as_of": catalog.get("valid_as_of"),
        "catalog_path": str(catalog_path),
        "rosettastone_cards_path": str(engine_cards_path),
        "rosettastone_overlay_path": str(engine_overlay_path),
        "current_standard_card_count": len(current_ids),
        "rosettastone_base_resource_card_count": len(engine_ids),
        "rosettastone_current_overlay_card_count": len(overlay_ids),
        "current_cards_with_metadata_loaded": len(current_ids & loaded_ids),
        "current_cards_missing_after_merge": len(missing_metadata),
        "current_ids_registered_in_card_set_sources_heuristic": len(current_ids & scripted_ids),
        "missing_metadata_ids": missing_metadata,
        "sets": set_rows,
        "limitations": [
            "Metadata availability does not mean gameplay effects are implemented.",
            "Card-set source ID matching is only a source-code inventory heuristic.",
            "Generated tokens and related non-collectible cards are not audited here.",
            "This report does not check Standard legality bans or card-specific correctness.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--engine-cards", type=Path, default=DEFAULT_ENGINE_CARDS)
    parser.add_argument("--engine-overlay", type=Path, default=DEFAULT_ENGINE_OVERLAY)
    parser.add_argument("--card-sources", type=Path, default=DEFAULT_CARD_SOURCES)
    parser.add_argument("--output", type=Path, help="Optional path for a detailed JSON report")
    args = parser.parse_args()

    report = audit(args.catalog, args.engine_cards, args.engine_overlay, args.card_sources)
    print(
        f"Standard catalog: {report['current_standard_card_count']} cards; "
        f"RosettaStone base: {report['rosettastone_base_resource_card_count']}, "
        f"overlay: {report['rosettastone_current_overlay_card_count']}; "
        f"current metadata loaded: {report['current_cards_with_metadata_loaded']}, "
        f"missing: {report['current_cards_missing_after_merge']}; "
        f"{report['current_ids_registered_in_card_set_sources_heuristic']} IDs found in card sources (heuristic)."
    )
    for row in report["sets"]:
        print(
            f"  {row['set_id']}: {row['catalog_cards']} cards, "
            f"{row['metadata_in_base_resource']} base + "
            f"{row['metadata_in_current_overlay']} overlay metadata, "
            f"{row['metadata_missing_after_merge']} missing after merge, "
            f"{row['ids_registered_in_card_set_sources_heuristic']} source IDs"
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Detailed report written to {args.output}")


if __name__ == "__main__":
    main()
