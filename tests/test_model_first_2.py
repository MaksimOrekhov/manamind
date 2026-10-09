"""Focused correctness and leakage tests for the bounded synthetic experiment."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_model_first_2 as generator  # noqa: E402
import train_model_first_2 as trainer  # noqa: E402
from evaluate_policy_baseline import action_key, load_scenarios  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract  # noqa: E402
from manamind.training.model_first_1_control import (  # noqa: E402
    scenario_content_fingerprint, validate_no_control_overlap,
)
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint  # noqa: E402


def small_data(tmp_path):
    rows, provenance = generator.generate(seed=100, per_template={name: 2 for group in generator.PLAN.values()
                                                                  for name, _ in group})
    generator.validate_splits(rows)
    for split in ("train", "validation", "test"):
        selected = [row for row in rows if row["split"] == split]
        path = tmp_path / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in selected), encoding="utf-8")
        load_scenarios(path)
    return rows, provenance


def _baseline(tmp_path):
    catalog = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")
    encoder = StateEncoder(catalog)
    contract = feature_contract(encoder)
    policy = PolicyNetworkV2(card_count=encoder.vocabulary.card_count,
                             state_feature_count=len(contract["state_feature_names"]),
                             entity_feature_count=len(contract["entity_feature_names"]),
                             hidden_size=8, dropout=0.1)
    split = {"dataset_sha256": "a" * 64, "game_ids": {"train": ["train"],
             "validation": ["validation"], "test": ["test"]}}
    config = {"seed": 1}
    metadata = {"dataset_sha256": split["dataset_sha256"], "split": split,
                "split_sha256": identity(split), "config": config, "config_sha256": identity(config)}
    path = tmp_path / "base.pt"
    save_policy_checkpoint(path, policy, encoder, metadata)
    return path


def test_generator_has_provenance_and_split_independence(tmp_path):
    rows, provenance = small_data(tmp_path)
    assert len(rows) == 24
    assert len(provenance) == len(rows)
    assert {r["split"] for r in rows} == {"train", "validation", "test"}
    assert len({r["seed"] for r in provenance}) == len(provenance)
    assert len({scenario_content_fingerprint(row) for row in rows}) == len(rows)
    for split in ("train", "validation", "test"):
        validate_no_control_overlap([row for row in rows if row["split"] == split])


def test_local_gold_labels_use_combat_arithmetic_and_unseen_ids():
    rows, _ = generator.generate(seed=123, per_template={name: 1 for group in generator.PLAN.values()
                                                         for name, _ in group})
    trade = next(row for row in rows if row["scenario_id"].endswith("single_favorable_trade_0000"))
    correct = {action_key(action) for action in trade["correct_actions"]}
    for action in trade["legal_actions"]:
        if action["type"] == "ATTACK" and action["target_kind"] == "MINION":
            actual = (action["source_attack"] >= action["target_health"]
                      and action["target_attack"] < action["source_health"])
            assert (action_key(action) in correct) == actual
    heldout = next(row for row in rows if row["split"] == "test")
    card_id = heldout["state"]["self_player"]["board"][0]["card"]["card_id"]
    assert card_id.startswith("MF2_HELDOUT_")


def test_generator_rejects_cross_split_exact_semantic_content(tmp_path):
    rows, _ = small_data(tmp_path)
    training = next(row for row in rows if row["split"] == "train")
    heldout = next(row for row in rows if row["split"] == "test")
    duplicate = copy.deepcopy(training)
    duplicate.update(split="test", scenario_id="renamed", family_id="other", template_id="other")
    duplicate["legal_actions"] = list(reversed(duplicate["legal_actions"]))
    assert scenario_content_fingerprint(duplicate) == scenario_content_fingerprint(training)
    with pytest.raises(ValueError, match="Exact state/menu overlap"):
        generator.validate_splits([*rows, duplicate])
    assert heldout["split"] == "test"


def test_short_training_roundtrips_checkpoint_from_existing_v2_contract(tmp_path):
    small_data(tmp_path)
    base = _baseline(tmp_path)
    output = tmp_path / "run"
    report = trainer.run(tmp_path / "train.jsonl", tmp_path / "validation.jsonl", base, output,
                         max_epochs=2, patience=2, batch_size=4, device="cpu",
                         expected_baseline_sha=None)
    restored, encoder, payload = load_policy_checkpoint(output / "policy.pt")
    assert report["epochs_run"] <= 2
    assert payload["model_config"]["architecture"] == "PolicyNetworkV2"
    assert payload["experiment"]["selected_epoch"] >= 1
    assert encoder.vocabulary.card_id("MF2_HELDOUT_SELF_0") == 1
    assert hashlib.sha256((output / "policy.pt").read_bytes()).hexdigest() == report["checkpoint_sha256"]
