from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from manamind.domain.card import CardFeatures
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.training.readiness import audit_real_dataset
from scripts import train_real_value


SOURCE = "power_log_ranked_standard"


def _state(card_id: str = "KNOWN_CARD") -> GameState:
    return GameState(
        turn_number=4,
        active_player="SELF",
        self_player=PlayerObservation(hero_health=27, hand_size=1),
        opponent=PlayerObservation(hero_health=24, hand_size=3),
        self_hand=(CardFeatures(card_id=card_id, cost=2, card_type="SPELL"),),
        self_hand_known_count=1,
    )


def _row(game_id: str, sample_id: str, target: float = 1.0, *, card_id: str = "KNOWN_CARD"):
    return {
        "schema_version": 1,
        "game_id": game_id,
        "sample_id": sample_id,
        "perspective": "SELF",
        "source": SOURCE,
        "state": asdict(_state(card_id)),
        "target": target,
    }


def _write_dataset(directory: Path, rows: list[dict], name: str = "examples.jsonl") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "cards.json"
    path.write_text(json.dumps([{
        "card_id": "KNOWN_CARD", "card_type": "SPELL", "card_class": "MAGE",
        "cost": 2,
    }]), encoding="utf-8")
    return path


def _prepared_snapshot(path: Path, *, shared_game: bool = False) -> Path:
    path.mkdir(parents=True)
    (path / "report.json").write_text("{}\n", encoding="utf-8")
    ids = ["same-game" if shared_game else f"game-{index}" for index in range(3)]
    for split, game_id in zip(("train", "validation", "test"), ids, strict=True):
        _write_dataset(path, [_row(game_id, f"sample-{split}")], f"{split}.jsonl")
    return path


def test_valid_real_style_dataset_audits_with_whole_match_splits(tmp_path: Path):
    rows = [_row(f"game-{index}", f"sample-{index}") for index in range(4)]
    for index, row in enumerate(rows):
        row["state"]["self_player"]["hero_health"] -= index
    input_dir = tmp_path / "input"
    _write_dataset(input_dir, rows)

    report = audit_real_dataset(input_dir, _catalog_path(tmp_path), batch_size=2)

    assert report["sample_integrity"] == "OK"
    assert report["unique_matches"] == 4
    assert report["split_readiness"]["can_create_train_validation_test"] is True
    assert report["pipeline_ready"] is True


def test_readiness_rejects_game_leakage_across_created_splits(tmp_path: Path):
    snapshot = _prepared_snapshot(tmp_path / "snapshot", shared_game=True)

    with pytest.raises(ValueError, match="Dataset leakage"):
        train_real_value.validate_snapshot(snapshot)


def test_missing_game_id_is_invalid_data(tmp_path: Path):
    row = _row("game-1", "sample-1")
    row["game_id"] = ""
    input_dir = tmp_path / "input"
    _write_dataset(input_dir, [row])

    report = audit_real_dataset(input_dir, _catalog_path(tmp_path))

    assert report["training_readiness"] == "INVALID_DATA"
    assert report["sample_integrity"] == "INVALID"


def test_duplicate_sample_ids_are_rejected(tmp_path: Path):
    input_dir = tmp_path / "input"
    _write_dataset(input_dir, [
        _row("game-1", "same-sample"),
        _row("game-1", "same-sample"),
    ])

    report = audit_real_dataset(input_dir, _catalog_path(tmp_path))

    assert report["sample_integrity"] == "INVALID"
    assert report["duplicate_sample_ids"] == 1


def test_wrong_source_is_invalid_data(tmp_path: Path):
    row = _row("game-1", "sample-1")
    row["source"] = "synthetic"
    input_dir = tmp_path / "input"
    _write_dataset(input_dir, [row])

    report = audit_real_dataset(input_dir, _catalog_path(tmp_path))

    assert report["training_readiness"] == "INVALID_DATA"
    assert report["failure_count"] == 1


def test_unmodeled_hidden_opponent_identity_field_is_rejected(tmp_path: Path):
    row = _row("game-1", "sample-1")
    row["state"]["opponent"]["hidden_hand_card_ids"] = ["PRIVATE_ID"]
    input_dir = tmp_path / "input"
    _write_dataset(input_dir, [row])

    report = audit_real_dataset(input_dir, _catalog_path(tmp_path))

    assert report["training_readiness"] == "INVALID_DATA"
    assert report["encoding"]["attempted"] is False


def test_unknown_card_uses_unk_and_still_runs_forward(tmp_path: Path):
    input_dir = tmp_path / "input"
    _write_dataset(input_dir, [_row("game-1", "sample-1", card_id="UNSEEN_VISIBLE_CARD")])

    report = audit_real_dataset(input_dir, _catalog_path(tmp_path), batch_size=1)

    assert report["card_identity"]["unknown_catalog_ids"] == 1
    assert report["card_identity"]["unknown_ids_use_shared_unk_index"] is True
    assert report["batch_forward"]["success"] is True
    assert report["batch_forward"]["output_shape"] == [1]


def test_model_forward_and_encoder_counts_every_row(tmp_path: Path):
    input_dir = tmp_path / "input"
    _write_dataset(input_dir, [_row("game-1", f"sample-{i}") for i in range(3)])

    report = audit_real_dataset(input_dir, _catalog_path(tmp_path), batch_size=2)

    assert report["encoding"]["states_encoded"] == 3
    assert report["encoding"]["failures"] == 0
    assert report["batch_forward"]["batch_size"] == 2
    assert report["batch_forward"]["finite_output"] is True


def test_too_few_matches_reports_insufficient_without_fabrication(tmp_path: Path):
    input_dir = tmp_path / "input"
    _write_dataset(input_dir, [_row("game-1", "sample-1")])

    report = audit_real_dataset(input_dir, _catalog_path(tmp_path))

    assert report["training_readiness"] == "INSUFFICIENT_MATCHES"
    assert report["pipeline_ready"] is True
    assert report["split_readiness"]["can_create_train_validation_test"] is False
    assert report["unique_matches"] == 1


def test_real_private_dataset_directory_is_not_tracked():
    result = subprocess.run(
        ["git", "ls-files", "--", "data/processed_real"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == ""


def test_wrapper_refuses_missing_or_invalid_snapshot(tmp_path: Path):
    with pytest.raises(ValueError, match="prepared snapshot"):
        train_real_value.validate_snapshot(tmp_path / "missing")

    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "report.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing train split"):
        train_real_value.validate_snapshot(invalid)


def test_smoke_checkpoint_never_overwrites_existing_file(tmp_path: Path, monkeypatch):
    snapshot = _prepared_snapshot(tmp_path / "snapshot")
    checkpoint = tmp_path / "candidate.pt"
    checkpoint.write_bytes(b"keep-this-candidate")
    called = False

    def should_not_train(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("pipeline must not run")

    monkeypatch.setattr(train_real_value, "run_synthetic_training", should_not_train)
    with pytest.raises(FileExistsError, match="already exists"):
        train_real_value.train_real_value(snapshot, checkpoint, smoke=True)

    assert checkpoint.read_bytes() == b"keep-this-candidate"
    assert called is False


def test_wrapper_requires_explicit_overwrite_to_replace_candidate(tmp_path: Path, monkeypatch):
    snapshot = _prepared_snapshot(tmp_path / "snapshot")
    checkpoint = tmp_path / "candidate.pt"
    checkpoint.write_bytes(b"existing")
    called = False

    def fake_pipeline(*args, **kwargs):
        nonlocal called
        called = True
        return {"history": []}

    monkeypatch.setattr(
        train_real_value,
        "run_synthetic_training",
        fake_pipeline,
    )

    with pytest.raises(FileExistsError):
        train_real_value.train_real_value(snapshot, checkpoint)
    assert checkpoint.read_bytes() == b"existing"
    assert called is False

    train_real_value.train_real_value(snapshot, checkpoint, overwrite_checkpoint=True)
    assert called is True


def test_smoke_is_one_epoch_and_suppresses_quality_metrics(tmp_path: Path, monkeypatch, capsys):
    snapshot = _prepared_snapshot(tmp_path / "snapshot")
    checkpoint = tmp_path / "candidate.pt"
    observed = {}

    def fake_pipeline(*args, **kwargs):
        observed.update(kwargs)
        print("accuracy 0.99; roc_auc 1.0")
        return {"history": []}

    monkeypatch.setattr(train_real_value, "run_synthetic_training", fake_pipeline)
    train_real_value.train_real_value(snapshot, checkpoint, smoke=True)

    assert observed["epochs"] == 1
    assert "accuracy" not in capsys.readouterr().out
