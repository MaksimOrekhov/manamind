from copy import deepcopy
import json
from pathlib import Path

from scripts import build_standard_registry as builder
from scripts.registry_admission import derive_admission, training_blockers
from scripts.verification_evidence import scoped_status


def verified_row():
    return {
        "rules_verification": {"status": "VERIFIED_SCOPED", "evidence_validity": "CURRENT", "training_scope": "FULL_PROFILE"},
        "bridge_action_support": {"status": "VERIFIED_SCOPED"},
    }


def test_builder_stale_blocker_belongs_to_current_card(monkeypatch):
    roots = json.loads(Path("data/cards/standard_roots_20261001_enUS.json").read_text(encoding="utf-8"))
    roots["roots"] = [r for r in roots["roots"] if r["card_id"] in {"CORE_CS2_004", "CORE_SW_066"}]
    monkeypatch.setattr(builder, "evidence_status", lambda card_id, *_: {"status": "STALE" if card_id == "CORE_CS2_004" else "CURRENT"})
    profile = builder.load_profile()
    profile["verification_evidence"] = []
    registry, _ = builder.build_registry(roots, profile=profile)
    assert "evidence:stale_historical_scope" in registry["cards"]["CORE_CS2_004"]["blockers"]
    assert "evidence:stale_historical_scope" not in registry["cards"]["CORE_SW_066"]["blockers"]


def test_admission_requires_complete_closure_current_dependencies_and_match_gates():
    row = verified_row()
    closure = {"closure_completeness": "COMPLETE_REVIEWED", "known_source_candidate_ids": ["token"], "unresolved_dynamic_pool_ids": []}
    dependencies = {"token": verified_row()}
    assert training_blockers(row, closure, dependencies, session_match_current=True) == []
    incomplete = {**closure, "closure_completeness": "INCOMPLETE_UNREVIEWED_STATIC_AND_DYNAMIC_HEURISTICS"}
    assert "dependency:closure_not_reviewed_complete" in training_blockers(row, incomplete, dependencies, session_match_current=True)
    stale = deepcopy(dependencies)
    stale["token"]["rules_verification"]["evidence_validity"] = "STALE"
    assert "dependency:reachable_rules_not_verified" in training_blockers(row, closure, stale, session_match_current=True)
    scoped = deepcopy(dependencies)
    scoped["token"]["rules_verification"]["training_scope"] = "SCOPED_PACKAGE_ONLY"
    assert "dependency:reachable_rules_not_verified" in training_blockers(row, closure, scoped, session_match_current=True)
    assert "session_match:not_current" in training_blockers(row, closure, dependencies, session_match_current=False)


def test_admission_transitions_and_decks_are_derived():
    cards = {"A": {"training_eligibility": {"status": "BLOCKED", "blockers": ["rules:missing"]}}}
    assert derive_admission(cards, profile_id="test", session_match_current=True)["status"] == "BLOCKED"
    cards["A"]["training_eligibility"] = {"status": "ELIGIBLE", "blockers": []}
    result = derive_admission(cards, profile_id="test", session_match_current=True, decks=[{"card_ids": ["A"], "legality": "PASS", "session_match": "PASS"}])
    assert (result["status"], result["eligible_roots"], result["eligible_decks"]) == ("ELIGIBLE", 1, 1)
    assert derive_admission(cards, profile_id="test", session_match_current=False)["status"] == "BLOCKED"
    assert derive_admission({}, profile_id="test", session_match_current=True)["status"] == "BLOCKED"


def test_explicit_evidence_is_independent_of_ignored_local_binaries():
    identity = {"profile_id": "test", "engine_source_sha256": "a" * 64}
    evidence = {"schema_version": 2, "execution_identity": identity, "artifacts": {key: {"sha256": "b" * 64} for key in ("engine_library", "native_tests", "bridge_module")}, "execution_result": {"native_scenarios": "PASS", "bridge_smoke": "PASS"}, "cards": {"A": {"status": "VERIFIED_SCOPED", "scope": "independent reviewed scenario"}}}
    assert scoped_status(evidence, "A", identity)["status"] == "CURRENT"
    assert scoped_status(evidence, "A", {**identity, "engine_source_sha256": "c" * 64})["status"] == "STALE"
    assert scoped_status({**evidence, "schema_version": 1}, "A", identity)["status"] == "STALE_OR_INCOMPLETE"


def test_registry_rebuild_matches_committed_output():
    profile = builder.load_profile()
    roots = builder.read_json(builder.profile_path(profile, "roots"))
    registry, aux = builder.build_registry(roots, profile=profile)
    expected = builder.read_json(builder.profile_path(profile, "registry"))
    assert registry == expected
    report, markdown = builder.build_reports(registry, aux)
    assert report == builder.read_json(builder.profile_path(profile, "reports") / "summary.json")
    assert markdown == (builder.profile_path(profile, "reports") / "summary.md").read_text(encoding="utf-8")
