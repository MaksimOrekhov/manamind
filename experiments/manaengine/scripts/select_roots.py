from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "configs/standard_profile.json"
REGISTRY = ROOT / "data/cards/standard_registry_20261001_enUS.json"
MATRIX = ROOT / "reports/meta_training_20261002_v1/card_matrix.json"
EVIDENCE_DIR = ROOT / "docs/history/rosettastone_legacy/card_rules"  # archived pre-migration evidence
OUTPUT = ROOT / "experiments/manaengine/data/root_selection.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_scoped_evidence() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(EVIDENCE_DIR.glob("*.evidence.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cards = payload.get("cards", {})
        if isinstance(cards, dict):
            rows = cards.items()
        elif isinstance(cards, list):
            rows = ((str(card.get("card_id", "")), card) for card in cards)
        else:
            continue
        for card_id, row in rows:
            if card_id and isinstance(row, dict) and row.get("status") == "VERIFIED_SCOPED":
                found.setdefault(card_id, []).append(path.relative_to(ROOT).as_posix())
    return found


def main() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    evidence = current_scoped_evidence()
    selected = []

    for row in matrix["roots"]:
        if row.get("meta_profile_verification") != "VERIFIED_SCOPED_CURRENT":
            continue
        card_id = row["card_id"]
        evidence_files = evidence.get(card_id, [])
        if not evidence_files:
            raise SystemExit(f"current Meta Profile status has no scoped evidence file: {card_id}")
        canonical = registry["cards"].get(card_id, {})
        canonical_rules = canonical.get("rules_verification", {})
        tier = "A" if (
            canonical_rules.get("status") == "VERIFIED_SCOPED"
            and canonical_rules.get("evidence_validity") == "CURRENT"
        ) else "B"
        selected.append({
            "card_id": card_id,
            "name": row["name"],
            "tier": tier,
            "meta_profile_status": row["meta_profile_verification"],
            "canonical_rules_status": canonical_rules.get("status", "UNKNOWN"),
            "canonical_evidence_validity": canonical_rules.get("evidence_validity", "UNKNOWN"),
            "evidence_files": sorted(set(evidence_files)),
        })

    selected.sort(key=lambda card: card["card_id"])
    if not 15 <= len(selected) <= 25:
        raise SystemExit(f"expected 15-25 current Tier A/B roots; found {len(selected)}")
    if not any(card["tier"] == "A" for card in selected):
        raise SystemExit("no Tier A canonical anchors found")
    source_hashes = {
        path.relative_to(ROOT).as_posix(): sha256(path)
        for path in (PROFILE, REGISTRY, MATRIX)
    }
    source_hashes.update({
        file: sha256(ROOT / file)
        for card in selected for file in card["evidence_files"]
    })
    output = {
        "schema_version": 1,
        "profile_id": matrix["profile_id"],
        "standard_profile_id": profile["profile_id"],
        "selection_policy": "all current VERIFIED_SCOPED_CURRENT Meta Profile roots; tier A iff canonical registry evidence is also current",
        "tier_a_count": sum(card["tier"] == "A" for card in selected),
        "tier_b_count": sum(card["tier"] == "B" for card in selected),
        "tier_c_included": False,
        "source_sha256": dict(sorted(source_hashes.items())),
        "cards": selected,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"selected {len(selected)} roots: Tier A={output['tier_a_count']}, Tier B={output['tier_b_count']}")
    for card in selected:
        print(f"{card['tier']} {card['card_id']} | {card['name']}")


if __name__ == "__main__":
    main()
