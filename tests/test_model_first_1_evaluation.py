"""Controlled scenarios, semantic action ranking, and conservative heuristic tests."""
import json
from pathlib import Path

import pytest
import torch

from manamind.cards.catalog import CardCatalog
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.policy import PolicyNetwork
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract
from manamind.training.policy_checkpoint import load_policy_checkpoint
from manamind.training.model_first_1_control import (
    normalized_sha256,
    validate_no_control_overlap,
    verify_frozen_control,
)
from scripts.evaluate_policy_baseline import (
    evaluate_heuristic,
    evaluate_model,
    load_scenarios,
    random_metrics,
)

ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "data/evaluation/model_first_1/control_test.jsonl"
CATALOG = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")


def test_scenarios_round_trip_labels_menus_and_family_splits(tmp_path):
    rows = load_scenarios(SCENARIOS)
    assert len(rows) == 13
    corrected = next(row for row in rows if row["scenario_id"] == "t10_target_health_high")
    assert corrected["label_status"] == "AMBIGUOUS"
    assert corrected["correct_actions"] == []
    locked_ids, locked_families, locked_templates, _ = verify_frozen_control()
    assert locked_ids == {row["scenario_id"] for row in rows}
    assert locked_families == {row["family_id"] for row in rows}
    assert locked_templates == {row["template_id"] for row in rows}
    candidates = []
    for index, split in enumerate(("train", "validation")):
        candidate = dict(rows[index])
        candidate.update(scenario_id=f"example_{split}", family_id=f"example_family_{split}",
                         template_id=f"example_template_{split}", split=split)
        candidate["state"] = dict(candidate["state"])
        candidate["state"]["turn_number"] += 100
        candidates.append(candidate)
    validate_no_control_overlap(candidates)
    candidate_path = tmp_path / "split_schema_smoke.jsonl"
    candidate_path.write_text("".join(json.dumps(row) + "\n" for row in candidates), encoding="utf-8")
    assert [r["split"] for r in load_scenarios(candidate_path)] == ["train", "validation"]
    template_leak = dict(candidates[0], template_id=rows[0]["template_id"])
    with pytest.raises(ValueError, match="template_ids"):
        validate_no_control_overlap([template_leak])


def test_exact_control_copy_is_blocked_after_identity_and_menu_order_changes():
    original = load_scenarios(SCENARIOS)[0]
    clone = dict(original)
    clone.update(scenario_id="renamed", family_id="renamed_family", template_id="renamed_template")
    clone["legal_actions"] = list(reversed(original["legal_actions"]))
    with pytest.raises(ValueError, match="content_fingerprints"):
        validate_no_control_overlap([clone])


def test_frozen_hash_normalizes_checkout_line_endings(tmp_path):
    lf = tmp_path / "lf.jsonl"
    crlf = tmp_path / "crlf.jsonl"
    lf.write_bytes(b'{"x":1}\n{"y":2}\n')
    crlf.write_bytes(b'{"x":1}\r\n{"y":2}\r\n')
    assert normalized_sha256(lf) == normalized_sha256(crlf)


def test_random_multi_answer_metrics_are_exact():
    metrics = random_metrics(menu_size=2, correct_count=1)
    assert metrics == {"top1": 0.5, "top3": None, "mrr": 0.75}


def test_heuristic_is_conservative_and_handles_control_scenarios():
    rows = [r for r in load_scenarios(SCENARIOS) if r["split"] == "test"]
    result = evaluate_heuristic(rows)
    assert result["ambiguous"] == 2
    assert result["not_applicable"] == 0
    assert result["overall"] == {"applicable": 11, "top1_count": 11, "top1": 1.0, "wrong_top1": 0}


def test_both_saved_checkpoints_load_with_their_declared_contracts():
    for path in (
        ROOT / "data/processed_policy_ml1c/baseline_seed42_v1/policy.pt",
        ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt",
    ):
        if path.exists():
            policy, encoder, payload = load_policy_checkpoint(path, device="cpu")
            assert policy.training is False
            assert payload["catalog_sha256"]
            assert encoder.vocabulary.card_count == payload["model_config"]["card_count"]


def test_model_inference_is_deterministic_and_semantic_menu_order_invariant():
    torch.manual_seed(41)
    rows = [r for r in load_scenarios(SCENARIOS) if r["split"] == "test"]
    encoder = StateEncoder(CATALOG)
    for representation in (1, 2):
        if representation == 1:
            model = PolicyNetwork(card_count=encoder.vocabulary.card_count, hidden_size=16).eval()
        else:
            contract = feature_contract(encoder)
            model = PolicyNetworkV2(
                encoder.vocabulary.card_count,
                len(contract["state_feature_names"]),
                len(contract["entity_feature_names"]),
                hidden_size=16,
                dropout=0.1,
            ).eval()
        result = evaluate_model(model, encoder, rows, repeats=2)
        assert result["ambiguous"] == 2
        assert result["overall"]["scenarios"] == 11
        assert result["inference_ms_mean"] >= 0
