"""Independent metric expectations, test isolation and fail-closed checkpoint loading."""
import copy
import json
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from test_real_policy_dataset import CATALOG, fixture  # noqa: E402
from import_policy_power_log import save_match  # noqa: E402
import train_real_policy as trainer  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.models.policy import PolicyNetwork  # noqa: E402
from manamind.training.policy_checkpoint import (  # noqa: E402
    identity, load_policy_checkpoint, save_policy_checkpoint,
)
from manamind.training.policy_metrics import summarize, uniform_metrics  # noqa: E402
from manamind.training.real_policy import encode_example, load_examples  # noqa: E402

ROOT = Path(__file__).parents[1]


def test_uniform_metrics_are_expectations_not_arbitrary_tie_order():
    rows = [{"legal_actions": [0]}, {"legal_actions": list(range(4))}]
    metrics = uniform_metrics(rows)
    assert metrics["cross_entropy"] == pytest.approx(__import__("math").log(4) / 2)
    assert metrics["top1_accuracy"] == 0.625
    assert metrics["top3_accuracy"] == 0.75
    assert metrics["top3_decisions"] == 1
    assert metrics["mean_reciprocal_rank"] == pytest.approx((1 + (1+1/2+1/3+1/4)/4) / 2)
    ranked = [{"loss": 0.0, "rank": 1, "menu_size": 1}, {"loss": 2.0, "rank": 4, "menu_size": 4}]
    assert summarize(ranked)["top3_accuracy"] == 0.0
    assert summarize(ranked)["mean_reciprocal_rank"] == 0.625


def metadata():
    config = {"seed": 42}
    split = {"dataset_sha256": "a" * 64, "game_ids": {"train": ["a" * 64],
             "validation": ["b" * 64], "test": ["c" * 64]}}
    return {"dataset_sha256": "a" * 64, "split": split, "split_sha256": identity(split),
            "config": config, "config_sha256": identity(config)}


def test_checkpoint_roundtrip_preserves_logits_and_unknown_vocabulary(tmp_path):
    encoder = StateEncoder(CATALOG)
    policy = PolicyNetwork(card_count=encoder.vocabulary.card_count)
    rows, _ = extract_match(fixture(45).lines, CATALOG)
    inputs = encode_example(rows[0], encoder)
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, policy, encoder, metadata())
    restored, restored_encoder, payload = load_policy_checkpoint(path)
    with torch.no_grad():
        assert torch.equal(policy(*inputs), restored(*encode_example(rows[0], restored_encoder)))
    assert restored_encoder.vocabulary.card_id("NEW_CARD_X") == 1
    assert payload["card_vocabulary"] == encoder.vocabulary.to_dict()
    with pytest.raises(FileExistsError):
        save_policy_checkpoint(path, policy, encoder, metadata())


@pytest.mark.parametrize("field,value", [
    ("schema", "legacy"), ("state_encoding_schema_version", 15), ("policy_action_schema_version", 3),
    ("semantic_action_schema_version", 2), ("real_policy_dataset_schema_version", 2),
    ("state_feature_names", []), ("action_feature_names", []), ("normalization", "linear"),
    ("catalog_sha256", "bad"), ("vocabulary_sha256", "bad"), ("model_config", {}),
])
def test_checkpoint_rejects_incompatible_contract(tmp_path, field, value):
    encoder = StateEncoder(CATALOG)
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, PolicyNetwork(card_count=encoder.vocabulary.card_count), encoder, metadata())
    payload = torch.load(path, weights_only=True)
    payload[field] = value
    torch.save(payload, path)
    with pytest.raises(ValueError):
        load_policy_checkpoint(path)


@pytest.mark.parametrize("mutation", ["leak", "split_hash", "dataset_hash", "config_hash", "weights", "vocab"])
def test_checkpoint_rejects_identity_leak_and_weight_tampering(tmp_path, mutation):
    encoder = StateEncoder(CATALOG)
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, PolicyNetwork(card_count=encoder.vocabulary.card_count), encoder, metadata())
    payload = torch.load(path, weights_only=True)
    experiment = payload["experiment"]
    if mutation == "leak":
        experiment["split"]["game_ids"]["test"] = experiment["split"]["game_ids"]["train"]
        experiment["split_sha256"] = identity(experiment["split"])
    elif mutation == "split_hash":
        experiment["split_sha256"] = "bad"
    elif mutation == "dataset_hash":
        experiment["dataset_sha256"] = "bad"
    elif mutation == "config_hash":
        experiment["config"]["seed"] = 0
    elif mutation == "weights":
        payload["policy_state_dict"]["scorer.0.weight"] = torch.zeros(2, 2)
    else:
        ids = payload["card_vocabulary"]["card_ids"]
        a, b = list(ids)[:2]
        ids[a], ids[b] = ids[b], ids[a]
        payload["vocabulary_sha256"] = identity(payload["card_vocabulary"])
    torch.save(payload, path)
    with pytest.raises(ValueError):
        load_policy_checkpoint(path)


def test_split_and_training_reproduce_and_test_is_only_scored_after_checkpoint(tmp_path, monkeypatch):
    dataset = tmp_path / "input"
    for seed in range(8):
        rows, summary = extract_match(fixture(45, seed=seed).lines, CATALOG)
        save_match(rows, summary, dataset)
    rows = load_examples(dataset)
    parts, published = trainer.freeze_split(rows, 42, 1)
    reordered, _ = trainer.freeze_split(list(reversed(rows)), 42, 1)
    assert parts == reordered
    assert set(published) <= {r["game_id"] for r in parts["train"]}
    sets = [{r["game_id"] for r in rs} for rs in parts.values()]
    assert not sets[0] & sets[1] and not sets[0] & sets[2] and not sets[1] & sets[2]
    test_ids = sets[2]
    config = json.loads((ROOT / "configs/real_policy_ml1c.json").read_text(encoding="utf-8-sig"))
    config.update(max_epochs=2, hidden_size=16)
    original = trainer.evaluate
    scored_test = []
    active_output = None
    def guarded(policy, rs, encoder):
        if {r["game_id"] for r in rs} & test_ids:
            assert (active_output / "policy.pt").is_file()
            assert (active_output / "history.json").is_file()
            scored_test.append(True)
        return original(policy, rs, encoder)
    monkeypatch.setattr(trainer, "evaluate", guarded)
    checkpoints = []
    for index in range(2):
        active_output = tmp_path / f"run{index}"
        trainer.run(dataset, ROOT / "data/cards/standard_current_enUS.json", active_output, copy.deepcopy(config))
        checkpoints.append(load_policy_checkpoint(active_output / "policy.pt")[0].state_dict())
    assert len(scored_test) == 2
    assert all(torch.equal(t, checkpoints[1][key]) for key, t in checkpoints[0].items())
    with pytest.raises(FileExistsError):
        trainer.run(dataset, ROOT / "data/cards/standard_current_enUS.json", active_output, config)


def test_invalidated_data_is_rejected_before_output_creation(tmp_path):
    dataset = tmp_path / "invalid"
    dataset.mkdir()
    (dataset / "INVALIDATED.json").write_text("{}")
    config = json.loads((ROOT / "configs/real_policy_ml1c.json").read_text(encoding="utf-8-sig"))
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="invalidated"):
        trainer.run(dataset, ROOT / "data/cards/standard_current_enUS.json", output, config)
    assert not output.exists()
