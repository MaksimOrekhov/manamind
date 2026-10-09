#!/usr/bin/env python3
"""Build a read-only ledger for the frozen Fire/Whelp candidate manifests."""

from __future__ import annotations

# HISTORICAL / DEACTIVATED (MODEL-FIRST-MIGRATION-1): this script reads archived RosettaStone evidence and the frozen
# Standard registry snapshot. Its output is NOT current verified coverage, is not ManaEngine evidence and must not
# guide new work. It refuses to run unless --historical-rerun is given, so committed results are never overwritten.
import sys as _sys


import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
POOL_FILES = {
    "fire_spell_standard_20261001_candidate_v1": "experiments/manaengine/data/pools/fire_spell_standard_20261001_candidate_v1.json",
    "whelp_one_cost_spell_standard_20261001_raw_candidate_v1": "experiments/manaengine/data/pools/whelp_one_cost_spell_standard_20261001_raw_candidate_v1.json",
    "whelp_one_cost_spell_standard_20261001_nonquest_anyclass_candidate_v1": "experiments/manaengine/data/pools/whelp_one_cost_spell_standard_20261001_nonquest_anyclass_candidate_v1.json",
    "whelp_one_cost_spell_standard_20261001_class_candidate_v1": "experiments/manaengine/data/pools/whelp_one_cost_spell_standard_20261001_class_candidate_v1.json",
}
DISPOSITIONS = {
    "CATA_528": ("MISSING_MAJOR_ARCHITECTURE", "start-of-turn scheduler contract not established"),
    "CATA_554": ("RULES_EVIDENCE_REQUIRED", "target count is clear from 'pick another', but exact set-Health and resolution semantics need review"),
    "CATA_581": ("RULES_EVIDENCE_REQUIRED", "improved amount and area-damage snapshot/order unresolved"),
    "CORE_AT_037": ("MISSING_BOUNDED_CAPABILITY", "typed Choose One continuation missing"),
    "CORE_CS2_074": ("MISSING_BOUNDED_CAPABILITY", "friendly-weapon legality and current-instance Attack mutation missing"),
    "DINO_406": ("RULES_EVIDENCE_REQUIRED", "eligible Elemental zones and damage/buff timing require review"),
    "DINO_417": ("MISSING_MAJOR_ARCHITECTURE", "instance-specific end-turn destruction is not represented"),
    "EDR_570": ("MISSING_BOUNDED_CAPABILITY", "typed Choose One continuation missing"),
    "EDR_813": ("MISSING_MAJOR_ARCHITECTURE", "Death Knight Corpse resource and conditional continuation absent"),
    "FIR_909": ("RULES_EVIDENCE_REQUIRED", "distinctness, target timing, short-target and packet order unresolved"),
    "FIR_910": ("RULES_EVIDENCE_REQUIRED", "first target and follow-up/discard timing unresolved"),
    "FIR_923": ("RULES_EVIDENCE_REQUIRED", "held-card cost snapshot and target timing unresolved"),
    "JAIL_307": ("RULES_EVIDENCE_REQUIRED", "deck-size snapshot and repeat/death boundary unresolved"),
    "TIME_212": ("RULES_EVIDENCE_REQUIRED", "second random-target timing after first damage unresolved"),
    "TLC_221": ("MISSING_MAJOR_ARCHITECTURE", "random-damage outcome drives summon count and deathrattle dependency"),
    "TLC_227": ("RULES_EVIDENCE_REQUIRED", "lowest-Health reselection, ties and packet ordering unresolved"),
}


def read_json(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def classify(card_id: str, registry_card: dict[str, Any], declared: dict[str, Any]) -> tuple[str, str]:
    evidence = registry_card["rules_verification"]
    spec = declared.get(card_id)
    if spec:
        if evidence["status"] == "VERIFIED_SCOPED" and evidence["evidence_validity"] == "CURRENT":
            return "IMPLEMENTED_SCOPED_VERIFIED", "ManaEngine declaration and current scoped evidence"
        return "IMPLEMENTED_BUT_RULES_BLOCKED", (
            f"ManaEngine declaration is {spec.get('support_state', 'unknown')}; "
            f"canonical rules state is {evidence['status']}/{evidence['evidence_validity']}"
        )
    if card_id in DISPOSITIONS:
        return DISPOSITIONS[card_id]
    if registry_card["dependencies"]["static_dependency_status"] != "NO_STATIC_SOURCE_REFERENCE_DETECTED_NOT_PROOF_OF_NONE":
        return "DEPENDENCY_BLOCKED", "source dependencies exist but are not reviewed closed"
    return "MISSING_BOUNDED_CAPABILITY", "no current declaration or reviewed route; capability scope needs triage"


def build() -> dict[str, Any]:
    abilities = read_json("experiments/manaengine/data/card_abilities.json")["cards"]
    registry = read_json("data/cards/standard_registry_20261001_enUS.json")
    pools = {pool_id: read_json(path) for pool_id, path in POOL_FILES.items()}
    rows_by_card: dict[str, dict[str, Any]] = {}
    for pool_id, manifest in pools.items():
        for card_id in manifest["card_ids"]:
            card = registry["cards"].get(card_id)
            if card is None:
                raise ValueError(f"candidate {card_id} is missing from canonical registry")
            classification, rationale = classify(card_id, card, abilities)
            row = rows_by_card.setdefault(card_id, {
                "card_id": card_id,
                "name": card["identity"]["name"],
                "manaengine_declaration": card_id in abilities,
                "manaengine_support_state": abilities.get(card_id, {}).get("support_state"),
                "classification": classification,
                "classification_rationale": rationale,
                "canonical_rules_status": card["rules_verification"]["status"],
                "canonical_evidence_validity": card["rules_verification"]["evidence_validity"],
                "static_dependency_status": card["dependencies"]["static_dependency_status"],
                "dynamic_dependency_status": card["dependencies"]["dynamic_dependency_status"],
                "known_source_candidates": card["dependency_closure"]["known_source_candidate_ids"],
                "pool_memberships": [],
            })
            row["pool_memberships"].append(pool_id)
    pool_summary = {}
    for pool_id, manifest in pools.items():
        card_ids = manifest["card_ids"]
        if len(card_ids) != manifest["count"] or len(set(card_ids)) != len(card_ids):
            raise ValueError(f"candidate pool cardinality/uniqueness mismatch: {pool_id}")
        pool_summary[pool_id] = {
            "count": manifest["count"],
            "membership_status": manifest["membership_status"],
            "dependency_status": manifest["dependency_status"],
            "training_eligible": manifest["training_eligible"],
            "count_recomputed": len(manifest["card_ids"]),
            "membership_sha256_recomputed": hashlib.sha256(
                "\n".join(sorted(card_ids)).encode("utf-8")
            ).hexdigest(),
        }
    unique_counts = Counter(row["classification"] for row in rows_by_card.values())
    pool_counts = {
        pool_id: dict(Counter(rows_by_card[card_id]["classification"] for card_id in manifest["card_ids"]))
        for pool_id, manifest in pools.items()
    }
    return {
        "schema_version": 1,
        "report_id": "manaengine_fire_whelp_frontier_20261005_v1",
        "profile_id": "standard_full_20261001_v1",
        "as_of_date": "2026-10-05",
        "classification_basis": "ManaEngine declarations are checked independently from canonical RosettaStone route registration. A declaration is not scoped verified unless canonical evidence is current. Explicit prior dispositions are used only for the listed reviewed frontier cases; unreviewed remainder is conservatively queued as bounded-capability triage, not certified as bounded.",
        "classification_axes_note": "The classification is per-card implementation/rules triage. Pool membership, pool dependency closure and training eligibility remain separately reported facts and are not inferred from it.",
        "pool_manifests": pool_summary,
        "pool_classification_counts": pool_counts,
        "unique_candidate_roots": len(rows_by_card),
        "unique_classification_counts": dict(unique_counts),
        "cards": sorted(rows_by_card.values(), key=lambda row: row["card_id"]),
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# ManaEngine Fire/Whelp frontier ledger",
        "",
        f"Generated from current checked-in artifacts on {data['as_of_date']}.",
        "",
        f"Pinned profile: `{data['profile_id']}`. Unique candidate roots: **{data['unique_candidate_roots']}**.",
        "",
        "> This ledger does not certify pool membership, dependency closure, or training eligibility. The four candidate manifests remain independent inputs.",
        "",
        "## Baseline pool facts",
        "",
        "| Manifest | Roots | Membership | Dependency closure | Training |",
        "|---|---:|---|---|---|",
    ]
    for pool_id, pool in data["pool_manifests"].items():
        lines.append(f"| `{pool_id}` | {pool['count']} | {pool['membership_status']} | {pool['dependency_status']} | {pool['training_eligible']} |")
    lines += ["", "## Per-card implementation/rules classification", "", "| Card | Classification | Declaration | Canonical rules/evidence | Static deps | Dynamic deps | Candidate pools |", "|---|---|---:|---|---|---|---|"]
    for row in data["cards"]:
        lines.append(
            f"| `{row['card_id']}` {row['name']} | {row['classification']} | {row['manaengine_declaration']} | "
            f"{row['canonical_rules_status']} / {row['canonical_evidence_validity']} | "
            f"{row['static_dependency_status']} | {row['dynamic_dependency_status']} | "
            f"{', '.join(row['pool_memberships'])} |"
        )
    lines += ["", "## Classification counts", "", "| Scope | Classification | Count |", "|---|---|---:|"]
    for scope, counts in [("Unique roots", data["unique_classification_counts"]), *data["pool_classification_counts"].items()]:
        for status in ("IMPLEMENTED_SCOPED_VERIFIED", "IMPLEMENTED_BUT_RULES_BLOCKED", "MISSING_BOUNDED_CAPABILITY", "MISSING_MAJOR_ARCHITECTURE", "RULES_EVIDENCE_REQUIRED", "DEPENDENCY_BLOCKED"):
            lines.append(f"| {scope} | {status} | {counts.get(status, 0)} |")
    lines += ["", "## Interpretation", "", "The canonical Standard registry records RosettaStone registration/evidence and is not ManaEngine gameplay certification. Pool dependency states apply to candidate universes as a whole; they do not prove an individual card's execution route is complete.", ""]
    return "\n".join(lines)


def main() -> int:
    if "--historical-rerun" not in _sys.argv:
        raise SystemExit("Deactivated historical tool: archived RosettaStone evidence / frozen registry, not current coverage. "
                         "Pass --historical-rerun only to reproduce the old output; see docs/history/rosettastone_legacy/README.md.")
    if "--historical-rerun" in _sys.argv:
        _sys.argv.remove("--historical-rerun")
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build()
    json_path = ROOT / "reports/manaengine_phase4f_20261005/FRONTIER_LEDGER.json"
    md_path = ROOT / "reports/manaengine_phase4f_20261005/FRONTIER_LEDGER.md"
    expected = {
        json_path: json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        md_path: render_markdown(data),
    }
    stale = []
    for path, content in expected.items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        raise SystemExit("stale frontier ledger outputs: " + ", ".join(stale))
    print(f"Frontier ledger: {data['unique_candidate_roots']} unique roots; pools=" + ", ".join(f"{key}:{value['count']}" for key, value in data['pool_manifests'].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
