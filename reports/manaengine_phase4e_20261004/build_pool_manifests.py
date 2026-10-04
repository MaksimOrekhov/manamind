"""Rebuild Phase 4E candidate manifests from frozen Phase 4B audit inputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "reports/manaengine_phase4b_20261004"
OUTPUT = ROOT / "experiments/manaengine/data/pools"
SNAPSHOT_ID = "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
SNAPSHOT = ROOT / SNAPSHOT_ID
SNAPSHOT_SHA256 = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
PROFILE_ID = "standard_full_20261001_v1"
AS_OF_DATE = "2026-10-01"


def _membership_hash(ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()


def _fingerprint(raw: dict[str, Any]) -> str:
    pred, metadata = raw["predicate"], raw["metadata_snapshot"]
    lines = [
        f"schema={raw['schema_version']}", f"contract={raw['contract_version']}", f"pool={raw['pool_id']}",
        f"profile={raw['format_profile_id']}", f"as_of={raw['as_of_date']}", f"predicate={pred['kind']}",
        f"school={pred['school'] or ''}", f"base_cost={-1 if pred['base_cost'] is None else pred['base_cost']}",
        f"class_policy={pred['class_policy']}", f"metadata_id={metadata['id']}",
        f"metadata_sha256={metadata['sha256']}", f"membership={raw['sorted_membership_sha256']}",
    ]
    for entry in raw["exclusions"]:
        lines.append(f"exclusion={entry['category']}|{entry['status']}|{entry['rationale']}|{entry['evidence_ref']}")
        lines.extend(f"id={card_id}" for card_id in entry["card_ids"])
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def _manifest(pool_id: str, ids: list[str], predicate: dict[str, Any], exclusions: list[dict[str, Any]]) -> dict[str, Any]:
    ids = sorted(ids)
    raw: dict[str, Any] = {
        "pool_id": pool_id, "schema_version": 1, "contract_version": 1,
        "format_profile_id": PROFILE_ID, "as_of_date": AS_OF_DATE, "predicate": predicate,
        "card_ids": ids, "count": len(ids), "sorted_membership_sha256": _membership_hash(ids),
        "metadata_snapshot": {"id": SNAPSHOT_ID, "sha256": SNAPSHOT_SHA256},
        "membership_status": "CANDIDATE", "dependency_status": "OPEN", "training_eligible": False,
        "exclusions": exclusions,
    }
    raw["predicate_rules_fingerprint"] = _fingerprint(raw)
    return raw


def _ledger(category: str, status: str, ids: list[str], rationale: str, ref: str) -> dict[str, Any]:
    return {"category": category, "status": status, "card_ids": sorted(ids), "rationale": rationale, "evidence_ref": ref}


def main() -> None:
    fire = json.loads((AUDIT / "VULCANOS_FIRE_POOL_REVIEW.json").read_text(encoding="utf-8"))
    whelp = json.loads((AUDIT / "WHELP_ONE_COST_POOL_PROVISIONAL.json").read_text(encoding="utf-8"))
    fire_ids = fire["candidate_ids"]
    fire_exclusions = [
        _ledger("QUEST", "REVIEWED_EXCLUDED", [], "No Quest identity is present among the 33 pinned Fire metadata candidates.", "Phase4B VULCANOS_FIRE_POOL_REVIEW.json"),
        _ledger("RUNE", "REVIEWED_EXCLUDED", [], "No candidate has a three-rune requirement in the reviewed metadata slice.", "Phase4B VULCANOS_FIRE_POOL_REVIEW.json"),
        _ledger("ALIAS", "REVIEWED_EXCLUDED", [], "Canonical card IDs are one ticket each; legacy aliases do not add a second identity.", "Phase4B VULCANOS_FIRE_POOL_REVIEW.json"),
        _ledger("NON_GENERATABLE", "UNRESOLVED", [], "A complete patch-specific ordinary-random-generation exception inventory/client trace is unavailable.", "official generation exclusion inventory unresolved"),
    ]
    outputs = {
        "fire_spell_standard_20261001_candidate_v1.json": _manifest(
            "fire_spell_standard_20261001_candidate_v1", fire_ids,
            {"kind": "STANDARD_SPELL_SCHOOL", "school": "FIRE", "base_cost": None, "class_policy": "ANY_CLASS"},
            fire_exclusions,
        ),
    }
    whelp_by_name = {variant["name"]: variant["ids"] for variant in whelp["variants"]}
    quest_ids = whelp["working_exclusions"]["quest_ids"]
    neutral_ids = whelp["working_exclusions"]["neutral_ids"]
    common = [
        _ledger("QUEST", "UNRESOLVED", quest_ids, "The Quest exclusion is supported by historical developer evidence but the precise current ordinary Discover gate is not proven for every Quest-like card.", "Phase4B WHELP_ONE_COST_POOL_PROVISIONAL.json"),
        _ledger("NON_GENERATABLE", "UNRESOLVED", [], "Current ordinary Discover exceptions have not been exhaustively reviewed.", "official generation exclusion inventory unresolved"),
    ]
    outputs["whelp_one_cost_spell_standard_20261001_raw_candidate_v1.json"] = _manifest(
        "whelp_one_cost_spell_standard_20261001_raw_candidate_v1", whelp["candidate_ids"],
        {"kind": "STANDARD_SPELL_BASE_COST", "school": None, "base_cost": 1, "class_policy": "ANY_CLASS"},
        common + [_ledger("NEUTRAL_POLICY", "UNRESOLVED", neutral_ids, "‘From any class’ may or may not include Neutral-class spells; keep both identities visible in the candidate envelope.", "Phase4B WHELP_ONE_COST_POOL_PROVISIONAL.json")],
    )
    outputs["whelp_one_cost_spell_standard_20261001_nonquest_anyclass_candidate_v1.json"] = _manifest(
        "whelp_one_cost_spell_standard_20261001_nonquest_anyclass_candidate_v1", whelp_by_name["NONQUEST_INCLUDING_NEUTRAL_PENDING_CLASS_REVIEW"],
        {"kind": "STANDARD_SPELL_BASE_COST", "school": None, "base_cost": 1, "class_policy": "ANY_CLASS"},
        common + [_ledger("NEUTRAL_POLICY", "UNRESOLVED", neutral_ids, "Neutral inclusion is unresolved; this 65-member set is a provisional alternative, not admitted membership.", "Phase4B WHELP_ONE_COST_POOL_PROVISIONAL.json")],
    )
    outputs["whelp_one_cost_spell_standard_20261001_class_candidate_v1.json"] = _manifest(
        "whelp_one_cost_spell_standard_20261001_class_candidate_v1", whelp_by_name["WORKING_CLASS_SPELLS_EXCLUDING_QUEST"],
        {"kind": "STANDARD_SPELL_BASE_COST", "school": None, "base_cost": 1, "class_policy": "NON_NEUTRAL_CLASS"},
        common + [_ledger("NEUTRAL_POLICY", "UNRESOLVED", neutral_ids, "This variant excludes the two Neutral candidates provisionally; exact ‘any class’ semantics remain unresolved.", "Phase4B WHELP_ONE_COST_POOL_PROVISIONAL.json")],
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, document in outputs.items():
        (OUTPUT / name).write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(outputs)} candidate manifests; Fire={len(fire_ids)}, Whelp raw={len(whelp['candidate_ids'])}, variants=65/63")


if __name__ == "__main__":
    main()
