"""Fail-closed admission derived from current per-card and profile evidence."""
from __future__ import annotations


def training_blockers(row: dict, closure: dict, dependencies: dict, *, session_match_current: bool) -> list[str]:
    blockers = []
    rules = row["rules_verification"]
    if rules["status"] != "VERIFIED_SCOPED":
        blockers.append(f"rules:{rules['status']}")
    validity = rules["evidence_validity"]
    if validity != "CURRENT":
        blockers.append("evidence:stale_historical_scope" if validity == "STALE" else "evidence:missing_or_incomplete")
    if rules.get("training_scope") != "FULL_PROFILE":
        blockers.append("rules:scope_not_full_profile")
    if closure["closure_completeness"] != "COMPLETE_REVIEWED":
        blockers.append("dependency:closure_not_reviewed_complete")
    if closure["unresolved_dynamic_pool_ids"]:
        blockers.append("dependency:unresolved_dynamic_pool")
    if any(dependencies.get(card_id, {}).get("rules_verification", {}).get("status") != "VERIFIED_SCOPED" or dependencies.get(card_id, {}).get("rules_verification", {}).get("evidence_validity") != "CURRENT" or dependencies.get(card_id, {}).get("rules_verification", {}).get("training_scope") != "FULL_PROFILE" for card_id in closure["known_source_candidate_ids"]):
        blockers.append("dependency:reachable_rules_not_verified")
    if row["bridge_action_support"]["status"] != "VERIFIED_SCOPED":
        blockers.append("bridge_action:not_audited")
    if not session_match_current:
        blockers.append("session_match:not_current")
    if row.get("legality", {}).get("banned_in_standard_snapshot"):
        blockers.append("legality:banned_in_profile")
    return blockers


def derive_admission(cards: dict, *, profile_id: str, session_match_current: bool, decks: list[dict] | None = None) -> dict:
    eligible_ids = {key for key, row in cards.items() if row["training_eligibility"]["status"] == "ELIGIBLE"}
    eligible_decks = sum(bool(deck.get("card_ids")) and set(deck["card_ids"]) <= eligible_ids and deck.get("legality") == "PASS" and deck.get("session_match") == "PASS" for deck in decks or [])
    complete = bool(cards) and len(eligible_ids) == len(cards) and session_match_current
    blockers = sorted({blocker for row in cards.values() for blocker in row["training_eligibility"]["blockers"]})
    if not cards:
        blockers.append("profile:empty_root_pool")
    if not session_match_current:
        blockers = sorted(set(blockers) | {"session_match:not_current"})
    return {"profile_id": profile_id, "status": "ELIGIBLE" if complete else "BLOCKED", "eligible_roots": len(eligible_ids), "eligible_decks": eligible_decks, "session_match_gates_status": "CURRENT" if session_match_current else "NOT_MET", "blockers": blockers}
