"""Build the deterministic, registry-derived audit for a frozen meta profile."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="configs/training_profiles/meta_training_20261002_v1.json",
    )
    args = parser.parse_args()
    profile_path = (ROOT / args.profile).resolve()
    profile = read_json(profile_path)
    standard = read_json(ROOT / "configs/standard_profile.json")
    if profile["source_standard_profile_id"] != standard["profile_id"]:
        raise SystemExit("Meta profile points at a different pinned Standard profile")
    registry = read_json(ROOT / standard["registry"])
    registry_summary = read_json(ROOT / standard["reports"] / "summary.json")
    if profile["source_standard_registry_id"] != registry["registry_id"]:
        raise SystemExit("Meta profile points at a different canonical registry")

    profile_hash = hashlib.sha256(
        json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    import sys
    sys.path.insert(0, str(ROOT))
    from scripts.standard_profile import execution_identity, load_profile
    from scripts.verification_evidence import scoped_status
    identity = execution_identity(load_profile())
    profile_evidence = []
    for evidence_path in profile.get("verification_evidence", []):
        path = ROOT / evidence_path
        if path.exists():
            profile_evidence.append(read_json(path))

    roots: dict[str, dict] = {}
    deck_rows: list[dict] = []
    for deck in profile["decks"]:
        root_ids = set()
        seed_rows = []
        for slot in deck["slots"]:
            card_id = slot.get("card_id")
            if card_id:
                root_ids.add(card_id)
                record = registry["cards"].get(card_id)
                if record is None:
                    raise SystemExit(f"Pinned root {card_id} is absent from the canonical registry")
                if record["identity"]["name"].casefold() != slot["display_name"].casefold():
                    raise SystemExit(
                        f"Name/ID mismatch: {slot['display_name']} -> {card_id} -> "
                        f"{record['identity']['name']}"
                    )
                roots[card_id] = record
            else:
                seed_rows.append(slot)

        # Registry edges are source candidates until independently reviewed.
        closure = set(root_ids)
        changed = True
        while changed:
            changed = False
            for edge in registry["dependency_graph"]["edges"]:
                if edge["from"] in closure and edge["to"] not in closure:
                    closure.add(edge["to"])
                    changed = True
        closure_nodes = closure - root_ids
        pools = set()
        for card_id in closure:
            record = registry["cards"].get(card_id)
            if record:
                pools.update(record["dependencies"].get("dynamic_pool_ids", []))
                pools.update(
                    record["dependency_closure"].get("unresolved_dynamic_pool_ids", [])
                )
        registration = Counter(
            registry["cards"][card_id]["implementation"]["registration_status"]
            for card_id in root_ids
        )
        rules = Counter(
            registry["cards"][card_id]["rules_verification"]["status"]
            for card_id in root_ids
        )
        current = sum(
            1
            for card_id in root_ids
            if is_current_profile_evidence(card_id, profile_hash, identity, profile_evidence, scoped_status)
        )
        deck_rows.append(
            {
                "deck_id": deck["deck_id"],
                "class": deck["class"],
                "source_entries": len(deck["slots"]),
                "declared_slots": sum(x["quantity"] for x in deck["slots"]),
                "pinned_root_ids": len(root_ids),
                "unresolved_or_external_seed_entries": seed_rows,
                "registered_roots": len(root_ids)
                - registration.get("NO_DETECTED_RULE_REGISTRATION", 0),
                "current_scoped_verified_roots": current,
                "implemented_unverified_roots": rules.get("IMPLEMENTED_UNVERIFIED", 0),
                "unknown_rules_roots": rules.get("UNKNOWN", 0),
                "known_candidate_dependency_nodes": len(closure_nodes),
                "unreviewed_static_candidate_edges": sum(
                    1
                    for edge in registry["dependency_graph"]["edges"]
                    if edge["from"] in closure
                    and edge["evidence_status"] == "UNREVIEWED_SOURCE_CANDIDATE"
                ),
                "unresolved_dynamic_pool_definitions": sorted(pools),
                "closure_status": "LOWER_BOUND_ONLY_BLOCKED",
            }
        )

    # Keep each external/non-collectible seed visible without treating it as a
    # collectible root or silently accepting its external ID as pinned data.
    seed_records = []
    seen_seed_ids = set()
    for deck in profile["decks"]:
        for slot in deck["slots"]:
            candidate_id = slot.get("candidate_card_id")
            if candidate_id and candidate_id not in seen_seed_ids:
                seen_seed_ids.add(candidate_id)
                seed_records.append(
                    {
                        "candidate_card_id": candidate_id,
                        "display_name": slot["display_name"],
                        "resolution": slot["resolution"],
                        "resolution_source_url": slot["resolution_source_url"],
                        "registry_status": "NOT_IN_PINNED_STANDARD_REGISTRY",
                    }
                )
    roots_out = []
    for card_id in sorted(roots):
        record = roots[card_id]
        roots_out.append(
            {
                "card_id": card_id,
                "name": record["identity"]["name"],
                "card_class": record["identity"]["card_class"],
                "registration_status": record["implementation"]["registration_status"],
                "implementation_route": record["implementation"]["route_proposal"],
                "rules_status": record["rules_verification"]["status"],
                "evidence_validity": record["rules_verification"]["evidence_validity"],
                "known_dependency_candidates": record["dependencies"]["known_source_candidates"],
                "dynamic_pool_ids": record["dependencies"]["dynamic_pool_ids"],
                "training_eligibility": record["training_eligibility"]["status"],
                "meta_profile_verification": (
                    "VERIFIED_SCOPED_CURRENT"
                    if is_current_profile_evidence(card_id, profile_hash, identity, profile_evidence, scoped_status)
                    else "NO_CURRENT_META_PROFILE_EVIDENCE"
                ),
            }
        )

    report_dir = ROOT / "reports/meta_training_20261002_v1"
    report_dir.mkdir(parents=True, exist_ok=True)
    matrix = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source_standard_profile_id": standard["profile_id"],
        "source_standard_registry_id": registry["registry_id"],
        "unique_pinned_standard_roots": len(roots_out),
        "unique_external_noncollectible_seed_candidates": len(seed_records),
        "roots": roots_out,
        "external_noncollectible_seed_candidates": seed_records,
        "decks": deck_rows,
    }
    (report_dir / "card_matrix.json").write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    render_markdown(
        profile, standard, registry, registry_summary, roots_out, seed_records,
        deck_rows, report_dir, profile_hash
    )
    print(
        f"Built profile audit: {len(profile['decks'])} decks, {len(roots_out)} pinned roots, "
        f"{len(seed_records)} external non-collectible seed candidates."
    )


def is_current_profile_evidence(card_id, profile_hash, identity, evidence_docs, status_fn) -> bool:
    for document in evidence_docs:
        row = document.get("cards", {}).get(card_id)
        if not row:
            continue
        if document.get("profile_manifest_sha256") != profile_hash:
            continue
        if row.get("profile_manifest_sha256") != profile_hash:
            continue
        if status_fn(document, card_id, identity).get("status") == "CURRENT":
            return True
    return False


def render_markdown(profile, standard, registry, registry_summary, roots, seeds, decks, report_dir: Path, profile_hash: str) -> None:
    canonical_current = sum(
        1
        for root in roots
        if root["rules_status"] == "VERIFIED_SCOPED"
        and root["evidence_validity"] == "CURRENT"
    )
    root_stale = sum(1 for root in roots if root["evidence_validity"] == "STALE")
    root_unregistered = sum(
        1 for root in roots if root["registration_status"] == "NO_DETECTED_RULE_REGISTRATION"
    )
    profile_current = sum(1 for root in roots if root["meta_profile_verification"] == "VERIFIED_SCOPED_CURRENT")
    root_registered_unverified = len(roots) - canonical_current - root_unregistered
    dynamic_ids = sorted(
        {pool for deck in decks for pool in deck["unresolved_dynamic_pool_definitions"]}
    )
    total_candidates = sum(deck["known_candidate_dependency_nodes"] for deck in decks)
    classes = sorted({deck["class"] for deck in decks})
    total_slots = sum(deck["declared_slots"] for deck in decks)
    distinct_names = {
        slot["display_name"].casefold()
        for deck in profile["decks"]
        for slot in deck["slots"]
    }
    audit = [
        f"# Meta Training Profile v1 audit draft — {profile['profile_id']}",
        "",
        f"Pinned source: `{standard['profile_id']}` / `{registry['registry_id']}` "
        f"(Standard snapshot {standard['as_of_date']}).",
        "",
        "## Resolution checkpoint",
        "",
        f"- Frozen decklists and quantities: {len(profile['decks'])} lists, {total_slots} slots parsed.",
        f"- Distinct decklist names: {len(distinct_names)}; pinned collectible canonical roots: {len(roots)}.",
        f"- Noncollectible Fabled deck entries: {len(seeds)} distinct candidates; their IDs are external candidates and are absent from the pinned registry.",
        f"- Current scoped-verified roots in this profile: {profile_current}; current under canonical Standard registry evidence: {canonical_current}; stale historical evidence: {root_stale}.",
        f"- Registered but not current-verified roots: {root_registered_unverified}; roots with no detected registration: {root_unregistered}.",
        f"- Distinct classes in the frozen lists: {len(classes)} ({', '.join(classes)}).",
        "",
        "The six Fabled entries remain visible in the slot list because the frozen source lists them. They are not collectible Standard roots. The profile keeps their externally matched IDs as candidates only; they require explicit dependency metadata and runtime verification. `Scarlet Bruiser` remains a separate Beatrix dependency with unresolved ID.",
        "",
        "## Closure and admission",
        "",
        f"The Standard registry reports {registry_summary['summary']['roots_with_complete_dependency_closure']} Standard roots with complete closure and {registry_summary['summary']['roots_training_eligible']} roots training-eligible in its full-profile scope. Meta-scoped closures are therefore not inferred from these global figures.",
        f"The profile roots reach {total_candidates} known source-candidate dependency-node occurrences across decks and {len(dynamic_ids)} unique unresolved pool definitions. Candidate edges are not reviewed closure; source metadata may omit real outcomes.",
        "",
        f"No deck currently has a complete meta closure or current profile session/match evidence. `configs/standard_profile.json` has no `session_match_evidence`. Meta-profile scoped evidence is checked separately against the pinned Standard execution identity and manifest hash `{profile_hash}`; it does not make a root training-eligible in the canonical Standard registry. The current registry also marks all six candidate seed IDs absent from its pinned root/dependency inventory.",
        "",
        "## Stop/continue assessment",
        "",
        "The chosen classes and archetypes are structurally useful, and the user-approved reserve deck can cover one disproportionate blocker. The profile is not yet implementation-ready as an exact simulator manifest: six listed Fabled entries and the extra Scarlet Bruiser lack pinned dependency records, and no complete root/dependency closure exists. Do not silently treat these as Standard collectible roots or shrink their outcomes. Initial package work can proceed only on exact pinned collectible roots whose contract and dependencies are independently reviewed; Fabled/session work remains a separate explicit blocker.",
    ]
    (report_dir / "profile_audit.md").write_text("\n".join(audit) + "\n", encoding="utf-8")

    lines = [
        "# Per-deck reachable-closure audit (registry lower bound)",
        "",
        "Candidate edges and pool hypotheses are not reviewed closure. Counts below describe only known registry candidates reachable from pinned collectible roots; they do not include unresolved Fabled seeds.",
        "",
        "| Deck | Class | Listed slots | Pinned roots | Current verified | Registered, unverified | Unregistered | Known candidate nodes | Candidate edges | Unresolved pools |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for deck in decks:
        lines.append(
            f"| {deck['deck_id']} | {deck['class']} | {deck['declared_slots']} | {deck['pinned_root_ids']} | "
            f"{deck['current_scoped_verified_roots']} | {deck['implemented_unverified_roots']} | {deck['unknown_rules_roots']} | "
            f"{deck['known_candidate_dependency_nodes']} | {deck['unreviewed_static_candidate_edges']} | "
            f"{len(deck['unresolved_dynamic_pool_definitions'])} |"
        )
    lines.extend(["", "## Pool IDs", ""])
    for deck in decks:
        lines.append(f"- `{deck['deck_id']}`: " + (", ".join(f"`{x}`" for x in deck["unresolved_dynamic_pool_definitions"]) or "none detected"))
    lines.extend(["", "No row is complete or training-eligible. Full root tests, reviewed static edges, exact dynamic memberships/outcome rules, bridge/action checks, and class/session/match evidence remain required."])
    (report_dir / "deck_closure.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
