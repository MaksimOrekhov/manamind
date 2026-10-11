"""Retraining must preserve closed test matches, provenance and the v2 contract."""
import copy
import json
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from test_real_policy_dataset import fixture  # noqa: E402
from import_policy_power_log import save_match  # noqa: E402
import prepare_policy_retrain as protocol  # noqa: E402
import train_real_policy as trainer  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract  # noqa: E402
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint  # noqa: E402
from manamind.training.policy_metrics import evaluate  # noqa: E402
from manamind.training.real_policy import load_examples  # noqa: E402

ROOT = Path(__file__).parents[1]
CARDS = ROOT / "data/cards/standard_current_enUS.json"


@pytest.fixture
def prepared(tmp_path):
    catalog = CardCatalog.from_json(CARDS)
    directory = tmp_path / "input"
    for seed in range(8):
        rows, summary = extract_match(fixture(45, seed=seed).lines, catalog)
        save_match(rows, summary, directory)
    rows = load_examples(directory)
    games = sorted({row["game_id"] for row in rows})
    old_split = {"dataset_sha256": "a" * 64,
                 "game_ids": {part: [game] for part, game in zip(("train", "validation", "test"), games)}}
    config = json.loads((ROOT / "configs/real_policy_retrain_1.json").read_text())
    config.update(device="cpu", max_epochs=2, hidden_size=16)
    encoder = StateEncoder(catalog)
    contract = feature_contract(encoder)
    model = PolicyNetworkV2(encoder.vocabulary.card_count, len(contract["state_feature_names"]),
                            len(contract["entity_feature_names"]), hidden_size=16)
    metadata = {"dataset_sha256": "a" * 64, "split": old_split, "split_sha256": identity(old_split),
                "config": config, "config_sha256": identity(config)}
    checkpoint = tmp_path / "baseline.pt"
    save_policy_checkpoint(checkpoint, model, encoder, metadata)
    payload = load_policy_checkpoint(checkpoint)[2]
    entries = [{"match_id": game, "status": "KNOWN_USED", "usage": [f"POLICY_V2_{part.upper()}"]}
               for part, members in old_split["game_ids"].items() for game in members]
    registry = {"entries": entries, "registry_identity_sha256": identity(entries), "eval_mapping_reliable": True}
    manifest = protocol.freeze(rows, registry, payload, config, test_matches=2, validation_matches=2)
    manifest["baseline_sha256"] = protocol.sha256_file(checkpoint)
    path = directory / "manifest.json"
    trainer.write_json(path, manifest)
    return directory, rows, config, checkpoint, manifest, path, registry, payload


def test_fresh_split_is_deterministic_disjoint_and_covers_all_decisions(prepared):
    _, rows, config, checkpoint, manifest, _, registry, payload = prepared
    reversed_manifest = protocol.freeze(list(reversed(rows)), registry, payload, config,
                                        test_matches=2, validation_matches=2)
    reversed_manifest["baseline_sha256"] = protocol.sha256_file(checkpoint)
    assert manifest == reversed_manifest
    parts = protocol.validate_manifest(manifest, rows, config, checkpoint)
    old = {g for members in payload["experiment"]["split"]["game_ids"].values() for g in members}
    assert not old & {row["game_id"] for row in parts["test"]}
    assert sum(map(len, parts.values())) == len(rows)


@pytest.mark.parametrize("change", ["config", "overlap", "decision", "historical", "data"])
def test_frozen_protocol_rejects_tampering(prepared, change):
    _, rows, config, checkpoint, manifest, _, _, _ = prepared
    mutated = copy.deepcopy(manifest)
    if change == "config":
        config = dict(config, learning_rate=0.5)
    elif change == "overlap":
        mutated["split"]["game_ids"]["test"] = mutated["split"]["game_ids"]["train"]
        mutated["split_sha256"] = identity(mutated["split"])
    elif change == "decision":
        mutated["split"]["decision_ids"]["train"] = []
        mutated["split_sha256"] = identity(mutated["split"])
    elif change == "historical":
        game = mutated["split"]["game_ids"]["test"][0]
        next(entry for entry in mutated["historical_usage"] if entry["game_id"] == game)["previous_usage"] = ["POLICY_V2_TRAIN"]
    else:
        rows = rows[1:]
    with pytest.raises(ValueError):
        protocol.validate_manifest(mutated, rows, config, checkpoint)


def test_test_opens_after_selected_checkpoint_and_training_reproduces(prepared, tmp_path, monkeypatch):
    directory, rows, config, checkpoint, manifest, path, _, _ = prepared
    test_ids = set(manifest["split"]["game_ids"]["test"])
    original = trainer.evaluate
    active_output = None
    opened = []

    def guarded(policy, selected, encoder):
        if {row["game_id"] for row in selected} & test_ids:
            assert (active_output / "policy.pt").exists()
            assert (active_output / "history.json").exists()
            opened.append(True)
        return original(policy, selected, encoder)

    monkeypatch.setattr(trainer, "evaluate", guarded)
    weights = []
    baseline_sha = protocol.sha256_file(checkpoint)
    for index in range(2):
        active_output = tmp_path / f"run{index}"
        trainer.run(directory, CARDS, active_output, config, baseline_checkpoint=checkpoint, prepared_manifest=path)
        weights.append(load_policy_checkpoint(active_output / "policy.pt")[0].state_dict())
    assert len(opened) == 4  # selected model + frozen comparison, once per run
    assert all(torch.equal(value, weights[1][key]) for key, value in weights[0].items())
    assert protocol.sha256_file(checkpoint) == baseline_sha
    assert not (active_output / "dataset").exists()  # one frozen canonical corpus, no redundant copy
    assert identity(sorted(load_examples(directory), key=lambda row: row["decision_id"])) == manifest["split"]["dataset_sha256"]


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA unavailable")
def test_evaluator_scores_cuda_without_cpu_tensor_mismatch(prepared):
    _, rows, _, checkpoint, _, _, _, _ = prepared
    policy, encoder, _ = load_policy_checkpoint(checkpoint, device="cuda")
    cuda_metrics, _ = evaluate(policy, rows[:2], encoder)
    cpu_metrics, _ = evaluate(policy.cpu(), rows[:2], encoder)
    assert cuda_metrics["cross_entropy"] == pytest.approx(cpu_metrics["cross_entropy"], abs=1e-6)
    assert cuda_metrics["top1_accuracy"] == cpu_metrics["top1_accuracy"]


def test_reviewed_holdout_requires_explicit_flag_and_remains_baseline_disjoint(prepared):
    _, rows, config, _, _, _, registry, payload = prepared
    tagged = copy.deepcopy(registry)
    old = {entry["match_id"] for entry in tagged["entries"]}
    for game in sorted({row["game_id"] for row in rows} - old):
        tagged["entries"].append({"match_id": game, "status": "KNOWN_USED", "usage": ["LATER_AUDIT_SEEN"]})
    tagged["registry_identity_sha256"] = identity(tagged["entries"])
    with pytest.raises(ValueError, match="Insufficient"):
        protocol.freeze(rows, tagged, payload, config, test_matches=2, validation_matches=2)
    manifest = protocol.freeze(rows, tagged, payload, config, test_matches=2, validation_matches=2,
                               allow_reviewed_test=True)
    assert manifest["summary"]["test"]["previously_used_matches"] == 2
    assert not set(manifest["split"]["game_ids"]["test"]) & old
