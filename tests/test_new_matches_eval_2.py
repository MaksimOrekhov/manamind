from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import new_matches_eval_2 as evaluation


def test_id_exclusion_precedes_game_content_access():
    protected, trained = "a" * 64, "b" * 64
    assert evaluation.exclusion_reason(protected[:16], {protected}, {}, set()) == "PROTECTED_FRESH_HOLDOUT_ID_ONLY"
    assert evaluation.exclusion_reason(trained[:16], set(), {trained: []}, set()) == "MATCH_ID_IN_PRIOR_SPLIT_OR_EVALUATION"
    assert evaluation.exclusion_reason("c" * 16, set(), {}, {"c" * 16}) == "SOURCE_ALREADY_IN_EVAL_1_INVENTORY"
    assert evaluation.exclusion_reason("d" * 16, set(), {}, set()) is None
    assert evaluation.exclusion_reason("Power", set(), {}, set()) == "LEGACY_FILENAME_WITHOUT_MATCH_KEY"


def row(game="a" * 64, option=1):
    return {"example": {"game_id": game, "decision_id": f"{game}:{option}",
            "provenance": {"state_hash": "b" * 64}, "legal_actions": [{}, {}, {}]}}


@pytest.mark.parametrize("forbidden", ["heldout", "history", "prior"])
def test_no_protected_training_or_previous_eval_overlap(forbidden):
    g = "a" * 64
    groups = {"heldout": set(), "history": set(), "prior": set()}
    groups[forbidden].add(g)
    with pytest.raises(ValueError, match="overlaps"):
        evaluation.assert_independent([row()], groups["heldout"], groups["history"], groups["prior"])


def test_duplicate_decisions_fail_closed_and_identity_depends_on_sources():
    with pytest.raises(ValueError, match="duplicate"):
        evaluation.assert_independent([row(), row()], set(), {}, set())
    evaluation.assert_independent([row(), row(option=2)], set(), {}, set())
    inputs = {"matches": ["a"], "decisions": ["a:1"], "inputs": {"raw": "sha1"}}
    assert evaluation.digest(inputs) == evaluation.digest(deepcopy(inputs))
    changed = deepcopy(inputs)
    changed["inputs"]["raw"] = "sha2"
    assert evaluation.digest(changed) != evaluation.digest(inputs)


def test_safe_snapshot_join_still_requires_exact_state_and_shadow_checks(monkeypatch):
    state = {"turn": 1}
    sha = evaluation.base._sha256_bytes(evaluation.canonical_json(state).encode())
    snapshot = {"game_key": "a" * 64, "state": state, "state_hash": sha, "seq": 1,
                "decision": {"kind": "MAIN_ACTION", "options_id": 2}}
    example = {"state": state}
    calls = []
    def pair(*args, **kwargs):
        calls.append(kwargs)
        return "CONFLICTING_OUTCOME_ROWS"
    monkeypatch.setattr(evaluation, "_pair_reason", pair)
    snapshots = [snapshot, {**snapshot, "seq": 2}]
    assert evaluation.join_reason(example, (), snapshots, {}, 1) == "CONFLICTING_OUTCOME_ROWS"
    assert calls == [{"require_snapshot_sequence_membership": True}]
    assert evaluation.join_reason(example, (), snapshots, {}, 2) == "AMBIGUOUS_RAW_DECISION_KEY"
    assert evaluation.join_reason({"state": {"turn": 2}}, (), snapshots, {}, 1) == "LIVE_STATE_MISMATCH"
    bad = {**snapshot, "seq": 3, "source": "different"}
    assert evaluation.join_reason(example, (), [snapshot, bad], {}, 1) == "CONFLICTING_SNAPSHOTS"


def test_family_adjusted_intervals_use_paired_whole_matches():
    rows = [row(option=1), row(option=2), row(game="c" * 64)]
    left = [{"cross_entropy": 1., "top1": True, "top3": True, "mrr": 1.}] * 3
    right = [{"cross_entropy": 2., "top1": False, "top3": False, "mrr": .5}] * 3
    result = evaluation.simultaneous_bootstrap(rows, left, right)
    assert result == evaluation.simultaneous_bootstrap(rows, left, right)
    assert result["cross_entropy"]["ci99"] == pytest.approx([-1., -1.])
    assert result["top1"]["ci99"] == pytest.approx([1., 1.])
    # A game with many decisions is resampled as one cluster, not independent rows.
    left[0] = {**left[0], "cross_entropy": 4.}
    left[1] = {**left[1], "cross_entropy": 4.}
    result = evaluation.simultaneous_bootstrap(rows, left, right)
    assert result["cross_entropy"]["ci99"] == pytest.approx([-1., 2.])


def test_top3_denominator_and_uniform_are_preserved():
    a = evaluation.base._record([0., 0.], chosen=0, menu_size=2)
    b = evaluation.base._record([0., 0., 0., 0.], chosen=3, menu_size=4)
    a["game_id"] = "a"
    b["game_id"] = "b"
    result = evaluation.base._metric_stats([a, b], [2, 4])["metrics"]
    assert result["top3_decisions"] == 1
    assert result["top3"] == 0
    assert result["uniform_random"]["top3"] == .75
    assert result["uniform_random"]["top1"] == .375


def test_real_join_checks_shadow_sequence_and_order_and_duplicate_indices():
    state = {"turn": 1}
    sha = evaluation.digest(state)
    game = "a" * 64
    key = (game, 2, sha)
    actions = [{"type": "END_TURN"}, {"type": "HERO_POWER"}]
    snapshot = {"game_key": game, "state": state, "state_hash": sha, "seq": 8,
                "decision": {"kind": "MAIN_ACTION", "options_id": 2}}
    identity = {"match_id": game, "state_hash": sha, "decision_id": f"{game}:8:2:{sha}"}
    menu = {**identity, "menu_size": 2, "actions": [{"index": i, "action": evaluation.base.action_digest(a)}
                                                  for i, a in enumerate(actions)]}
    prediction = {**identity, "checkpoint_sha256": evaluation.base.MODELS[0]["sha256"],
                  "top3": [{"action": actions[0]}]}
    groups = {"prediction": {key: [prediction]}, "strategy": {key: [deepcopy(menu)]}, "outcome": {key: [deepcopy(menu)]}}
    example = {"state": state, "legal_actions": actions}
    assert evaluation.join_reason(example, key, [snapshot], groups, 1) is None
    groups["outcome"][key][0]["actions"].append(deepcopy(menu["actions"][0]))
    assert evaluation.join_reason(example, key, [snapshot], groups, 1) == "OUTCOME_MENU_DUPLICATE_INDEX"
    groups["outcome"][key] = [deepcopy(menu)]
    groups["outcome"][key][0]["decision_id"] = f"{game}:9:2:{sha}"
    assert evaluation.join_reason(example, key, [snapshot], groups, 1) == "OUTCOME_SEQ_NOT_IN_SNAPSHOT_GROUP"
    groups["outcome"][key] = [deepcopy(menu)]
    groups["outcome"][key][0]["actions"][0]["action"] = "wrong"
    assert evaluation.join_reason(example, key, [snapshot], groups, 1) == "OUTCOME_MENU_MISMATCH"


def test_locked_verification_rejects_membership_and_source_changes(monkeypatch):
    rows = [row()]
    inputs = {"split_plan_sha256": "same", "catalog_sha256": "same", "usage_registry_sha256": "same",
              "prior_protocol_sha256": "same", "raw_log_sha256": {"source.log": "same"},
              "live_snapshot_sha256": {}, "candidate_shadow_rows_sha256": {}}
    p = {"code_sha256": {}, "inputs": inputs, "history_ids": [], "prior_match_ids": [],
         "protected_fresh_holdout": {"ids": []}, "eligible_match_ids": ["a" * 64],
         "eligible_decision_ids": [rows[0]["example"]["decision_id"]], "private_decisions_sha256": "same"}
    p["dataset_identity_sha256"] = evaluation.digest({"matches": p["eligible_match_ids"],
                                                     "decisions": p["eligible_decision_ids"], "inputs": inputs})
    monkeypatch.setattr(evaluation.base, "sha256_file", lambda path: "same")
    monkeypatch.setattr(evaluation.base, "_load_shadow_rows", lambda *args: ({}, {}))
    monkeypatch.setattr(evaluation.base, "MODELS", [])
    evaluation.verify(p, rows)
    changed = deepcopy(rows)
    changed[0]["example"]["decision_id"] += "2"
    with pytest.raises(ValueError, match="membership"):
        evaluation.verify(p, changed)
    p["inputs"]["raw_log_sha256"]["source.log"] = "changed"
    with pytest.raises(ValueError, match="source changed"):
        evaluation.verify(p, rows)
