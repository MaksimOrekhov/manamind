"""Preference provenance and mechanical scope, without training or real corpus access."""
from copy import deepcopy

import pytest

from manamind.training.action_preferences import candidates, mechanical_scopes, validate_annotations
from manamind.training.policy_checkpoint import identity


def pack():
    actions = [{"type": "ATTACK", "source_kind": "MINION", "source_board_position": i,
                "source_card_id": f"S{i}", "target_kind": "MINION", "target_side": "OPPONENT",
                "target_board_position": 1, "target_card_id": "T"} for i in (1, 2)]
    alternatives = [{"action": a, "combat": {"properties": {
        "source_body_dies": {"value": bool(i), "knownness": "VERIFIED_LOCAL"},
        "target_body_dies": {"value": True, "knownness": "VERIFIED_LOCAL"}}}} for i, a in enumerate(actions)]
    pair = {"pair_id": "P001", "game_group": "M01", "game_group_sha256": "stable_game", "source_part": "train", "alternatives": alternatives}
    return {"schema": "manamind.action_preference_pack/1", "pairs": [pair]}


def annotation(p):
    return {"schema": "manamind.preference_annotations/1", "pack_sha256": identity(p), "reviewer": "r1",
            "annotations": [{"pair_id": "P001", "pair_sha256": identity(p["pairs"][0]), "initial": {
                "result": "A", "basis": "verified_mechanics", "aspect": "source_survival", "confidence": "high",
                "explanation": "Only survival of the original source body in this local exchange.",
                "timestamp": "2026-10-11T10:00:00Z"}, "revisions": [], "revealed": False}]}


def test_verified_scope_does_not_become_global_optimality():
    p = pack()
    assert mechanical_scopes(p["pairs"][0])["source_survival"]["relation"] == "A"
    result = validate_annotations(p, annotation(p))
    assert len(result["strict_preferences"]) == 1
    assert result["strict_preferences"][0]["game_group_sha256"] == "stable_game"
    assert result["ready_for_training"] is False


@pytest.mark.parametrize("change", ["conditional", "strategic", "wrong_direction", "stale_pair", "stale_pack", "duplicate", "missing_confidence", "late_initial"])
def test_invalid_or_unproved_label_is_rejected(change):
    p = pack()
    if change == "conditional": p["pairs"][0]["alternatives"][0]["combat"]["properties"]["source_body_dies"]["knownness"] = "CONDITIONAL"
    a = annotation(p)
    e = a["annotations"][0]
    if change == "strategic": e["initial"]["aspect"] = "strategic"
    elif change == "wrong_direction": e["initial"]["result"] = "B"
    elif change == "stale_pair": e["pair_sha256"] = "changed"
    elif change == "stale_pack": a["pack_sha256"] = "changed"
    elif change == "duplicate": a["annotations"].append(deepcopy(e))
    elif change == "missing_confidence": e["initial"].pop("confidence")
    elif change == "late_initial": e.update(revealed=True, reveal_timestamp="2026-10-11T09:00:00Z")
    with pytest.raises(ValueError): validate_annotations(p, a)


def test_abstention_and_equivalence_are_separate_from_strict_pairs():
    p = pack()
    a = annotation(p)
    e = a["annotations"][0]["initial"]
    e.update(result="INSUFFICIENT", basis="insufficient", aspect="strategic")
    result = validate_annotations(p, a)
    assert not result["strict_preferences"] and len(result["abstentions"]) == 1
    e.update(result="EQUIVALENT", basis="verified_mechanics", aspect="target_destruction")
    result = validate_annotations(p, a)
    assert not result["strict_preferences"] and len(result["aspect_equivalences"]) == 1


@pytest.mark.parametrize("result_key,bucket", [
    ("BOTH_BAD", "both_bad"),
    ("SEQUENCE_DEPENDENT", "sequence_dependent"),
])
def test_new_assessments_stay_outside_pairwise_training_categories(result_key, bucket):
    p = pack()
    a = annotation(p)
    a["schema"] = "manamind.preference_annotations/2"
    label = a["annotations"][0]["initial"]
    label.update(result=result_key, basis="expert", aspect="strategic")
    result = validate_annotations(p, a)
    assert len(result[bucket]) == 1
    assert not result["strict_preferences"]
    assert not result["aspect_equivalences"]
    assert not result["abstentions"]
    assert result[bucket][0]["label"]["result"] == result_key


def test_legacy_annotations_remain_accepted_without_relabeling():
    p = pack()
    a = annotation(p)
    assert a["schema"] == "manamind.preference_annotations/1"
    result = validate_annotations(p, a)
    assert result["strict_preferences"][0]["label"]["result"] == "A"
    assert not result["both_bad"] and not result["sequence_dependent"]


def test_new_assessments_require_annotation_schema_v2():
    p = pack()
    a = annotation(p)
    a["annotations"][0]["initial"].update(result="BOTH_BAD", basis="expert", aspect="strategic")
    with pytest.raises(ValueError, match="schema /2"):
        validate_annotations(p, a)


def test_corrections_do_not_overwrite_initial_blind_label():
    p = pack()
    a = annotation(p)
    e = a["annotations"][0]
    e.update(revealed=True, reveal_timestamp="2026-10-11T10:01:00Z")
    revision = deepcopy(e["initial"])
    revision.update(result="B", basis="expert", aspect="strategic", timestamp="2026-10-11T10:02:00Z")
    e["revisions"].append(revision)
    result = validate_annotations(p, a)
    assert result["strict_preferences"][0]["label"]["result"] == "A"
    assert result["strict_preferences"][0]["revisions"][0]["result"] == "B"


def test_player_choice_cannot_be_a_candidate_label():
    p = pack()
    row = {"legal_actions": [x["action"] for x in p["pairs"][0]["alternatives"]]}
    facts = {i: x["combat"] for i, x in enumerate(p["pairs"][0]["alternatives"])}
    first = candidates(row, facts, [0, 1])
    row["chosen_action_index"] = 999
    assert candidates(row, facts, [0, 1]) == first
    assert "identity_suspicion" in first[0]["tags"]
    assert all("label" not in c for c in first)


def test_empty_manual_export_has_zero_training_labels():
    p = pack()
    a = annotation(p)
    a["annotations"] = []
    result = validate_annotations(p, a)
    assert result["unlabelled"] == 1 and not result["strict_preferences"]
