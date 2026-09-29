"""Build a reproducible pool/dependency audit for selected Dark Gift cards."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
DECKS = ROOT / "data/samples/standard_meta_deck_pool_20260928.json"
OUTPUT = ROOT / "reports/dark_gift_support_audit_20260929.json"
TARGETS = {"EDR_456", "FIR_939", "EDR_856"}
DECK_NAMES = {"Dragon Warrior", "Quest Priest"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    catalog_doc = json.loads(CATALOG.read_text(encoding="utf-8"))
    cards = {card["id"]: card for card in catalog_doc["cards"] if card.get("id")}
    deck_doc = json.loads(DECKS.read_text(encoding="utf-8"))
    decks = {deck["name"]: deck for deck in deck_doc["decks"]}
    missing = TARGETS - cards.keys()
    if missing:
        raise SystemExit(f"catalog is missing selected Dark Gift cards: {sorted(missing)}")
    if not DECK_NAMES <= decks.keys():
        raise SystemExit(f"deck pool is missing expected lists: {sorted(DECK_NAMES - decks.keys())}")

    standard_minions = {
        card_id: card
        for card_id, card in cards.items()
        if card.get("collectible") and card.get("type") == "MINION"
    }
    dragons = sorted(
        card_id for card_id, card in standard_minions.items() if card.get("race") == "DRAGON"
    )
    warriors = sorted(
        card_id
        for card_id, card in standard_minions.items()
        if card.get("cardClass") == "WARRIOR"
    )
    quest_priest_minions = sorted(
        card_id
        for card_id in set(decks["Quest Priest"]["cards"])
        if card_id in cards and cards[card_id].get("type") == "MINION"
    )
    xavius_deck_candidates = [card_id for card_id in quest_priest_minions if card_id != "EDR_856"]
    selected = {
        card_id: {
            "name": cards[card_id].get("name"),
            "card_type": cards[card_id].get("type"),
            "text": cards[card_id].get("text"),
        }
        for card_id in sorted(TARGETS)
    }
    overlap = sorted(set(dragons) & set(warriors))
    report = {
        "schema_version": 1,
        "generated_for": "Dark Gift rules and candidate-pool scope; not a correctness or training-eligibility claim",
        "catalog_valid_as_of": catalog_doc.get("valid_as_of"),
        "catalog_sha256": sha256(CATALOG),
        "deck_pool_sha256": sha256(DECKS),
        "selected_cards": selected,
        "gifts": [
            {"id": 1, "effect": "+3 Attack, Lifesteal"},
            {"id": 2, "effect": "+2/+2, Elusive"},
            {"id": 3, "effect": "Cost -2, Attack -2; resulting Attack must remain at least 1"},
            {"id": 4, "effect": "Charge"},
            {"id": 5, "effect": "Playing minion summons a 2/2 copy"},
            {"id": 6, "effect": "Battlecries trigger twice; Battlecry required"},
            {"id": 7, "effect": "+4 Health, Taunt"},
            {"id": 8, "effect": "Reborn; returns with full Health and enchantments"},
            {"id": 9, "effect": "+4/+5; put card on top of deck"},
            {"id": 10, "effect": "Divine Shield, Windfury"},
        ],
        "candidate_pools": {
            "EDR_456": {"predicate": "collectible Standard minion with race DRAGON", "count": len(dragons), "card_ids": dragons},
            "FIR_939": {"predicate": "collectible Standard minion with cardClass WARRIOR", "count": len(warriors), "card_ids": warriors},
            "EDR_856": {
                "predicate": "actual minion entities in saved Quest Priest deck, excluding played Xavius card ID",
                "count": len(xavius_deck_candidates),
                "card_ids": xavius_deck_candidates,
            },
        },
        "pool_relationship": {"dragon_warrior_overlap_count": len(overlap), "dragon_warrior_overlap_ids": overlap, "union_count": len(set(dragons) | set(warriors))},
        "limitations": [
            "Candidate-pool metadata does not implement the Dark Gift choice or effect.",
            "Selected minion future behavior remains a transitive dependency; unsupported candidates cannot be hidden in strict training.",
            "Gift-specific card behavior is not inferred from rules text or metadata by this script.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
        OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Dark Gift audit: Dragon pool={len(dragons)}, Warrior pool={len(warriors)}, union={report['pool_relationship']['union_count']}, Xavius deck pool={len(xavius_deck_candidates)}")
    print(f"Wrote {OUTPUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
