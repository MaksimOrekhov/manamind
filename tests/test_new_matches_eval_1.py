from __future__ import annotations

import json

import pytest

from scripts import new_matches_eval_1 as evaluation


def test_journal_identity_uses_match_options_and_state_hash() -> None:
    game_id = "a" * 64
    state_hash = "b" * 64
    row = {"match_id": game_id, "state_hash": state_hash,
           "decision_id": f"{game_id}:8:12:{state_hash}"}

    assert evaluation._decision_id_parts(row) == (game_id, 12, state_hash)
    assert evaluation._decision_id_parts({**row, "state_hash": "c" * 64}) is None
    assert evaluation._decision_id_parts({**row, "decision_id": "malformed"}) is None


def test_live_menu_join_requires_same_order_and_all_actions() -> None:
    actions = [{"type": "END_TURN"}, {"type": "HERO_POWER", "card_id": "HP_01"}]
    live_row = {"menu_size": 2, "actions": [
        {"index": 0, "action": evaluation.action_digest(actions[0])},
        {"index": 1, "action": evaluation.action_digest(actions[1])},
    ]}

    assert evaluation._match_menu_actions(live_row, actions)
    assert not evaluation._match_menu_actions(live_row, list(reversed(actions)))
    assert not evaluation._match_menu_actions({**live_row, "menu_size": 1}, actions)


def test_record_checks_logits_and_uses_stable_menu_order() -> None:
    row = evaluation._record([2.0, 1.0, 1.0], chosen=2, menu_size=3)

    assert row["top_index"] == 0
    assert row["rank"] == 3
    assert row["top1"] is False
    assert row["top3"] is True
    assert row["mrr"] == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match="logit/menu/chosen-index mismatch"):
        evaluation._record([0.0], chosen=1, menu_size=1)


def test_uniform_baseline_and_match_balanced_spread_are_reported() -> None:
    records = [
        {"game_id": "a" * 64, "cross_entropy": 0.1, "top1": True, "top3": True, "mrr": 1.0},
        {"game_id": "b" * 64, "cross_entropy": 0.8, "top1": False, "top3": False, "mrr": 0.5},
    ]
    result = evaluation._metric_stats(records, [3, 3])

    assert result["decisions"] == 2
    assert result["matches"] == 2
    assert result["metrics"]["uniform_random"]["top1"] == pytest.approx(1 / 3)
    assert result["metrics"]["uniform_random"]["top3"] == pytest.approx(1.0)
    assert result["mean_across_matches"]["cross_entropy"]["std"] == pytest.approx(0.35)
    assert "per_match" not in result


def test_cluster_bootstrap_is_paired_and_deterministic() -> None:
    rows = [
        {"example": {"game_id": "a" * 64, "legal_actions": [{}, {}, {}]}},
        {"example": {"game_id": "a" * 64, "legal_actions": [{}, {}, {}]}},
        {"example": {"game_id": "b" * 64, "legal_actions": [{}, {}, {}]}},
    ]
    left = [
        {"cross_entropy": 0.1, "top1": True, "top3": True, "mrr": 1.0},
        {"cross_entropy": 0.2, "top1": False, "top3": True, "mrr": 0.5},
        {"cross_entropy": 0.3, "top1": True, "top3": True, "mrr": 1.0},
    ]
    right = [
        {"cross_entropy": 0.2, "top1": False, "top3": False, "mrr": 0.5},
        {"cross_entropy": 0.3, "top1": False, "top3": True, "mrr": 0.5},
        {"cross_entropy": 0.4, "top1": False, "top3": False, "mrr": 0.25},
    ]

    first = evaluation._paired_cluster_bootstrap(rows, left, right, seed=7, draws=100)
    second = evaluation._paired_cluster_bootstrap(rows, left, right, seed=7, draws=100)

    assert first == second
    assert first["matches"] == 2
    assert first["decisions"] == 3
    assert first["metrics"]["cross_entropy"]["difference"] == pytest.approx(-0.1)
    assert first["metrics"]["top1"]["difference"] == pytest.approx(2 / 3)


def test_public_protocol_keeps_match_ids_private_and_aggregates_exclusions() -> None:
    private_id = "c" * 64
    protocol = {
        "dataset_identity_sha256": "d" * 64,
        "source_commit": "e" * 40,
        "source_code_sha256": "f" * 64,
        "inputs": {"split_plan_sha256": "a" * 64},
        "inventory": {
            "raw_collected_log_files": 3, "keyed_collected_match_logs": 3,
            "legacy_filename_logs": 0, "protected_raw_log_prefixes_skipped": 0,
            "new_nonoverlap_raw_candidates": 1, "completed_matches_imported": 1,
            "new_eligible_matches": 1, "new_eligible_decisions": 4,
            "prepare_decisions": 0, "prepare_chosen": 0,
            "prepare_menu_decisions_imported": 0, "prepare_menu_decisions_live_matched": 0,
            "prepare_chosen_live_matched": 0, "prepare_menu_decision_exclusions": {},
            "collector_pending_logs": 0, "live_recording_directories_nonprotected": 1,
            "importer_skip_reasons": {},
            "decision_exclusions": {},
        },
        "source_inventory": [
            {"category": "NEW_ELIGIBLE", "source": f"{private_id}.log"},
            {"category": "INCOMPLETE", "reason": "COLLECTOR_PENDING_SLICE", "source": "pending"},
        ],
        "protected_fresh_holdout": {"count": 9, "opened": False, "inference_run": False},
        "models": {}, "protocol": {},
    }

    public = evaluation._public_protocol(protocol)
    serialized = json.dumps(public)

    assert public["match_categories"] == {"INCOMPLETE": 1, "NEW_ELIGIBLE": 1}
    assert private_id not in serialized
    assert public["protected_fresh_holdout"] == {"count": 9, "opened": False, "inference_run": False}
