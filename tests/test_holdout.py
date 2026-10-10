"""Safe preparation and resume checks for the isolated LIVE Policy holdout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import run_manamind  # noqa: E402
from holdout import HoldoutError, prepare_holdout, verify_holdout_disjoint  # noqa: E402
from manamind.integrations.powerlog.lines import inspect_segment, split_games  # noqa: E402
from live_fixtures import LiveLog  # noqa: E402
from collect_power_logs import IMPORTED, STATE_VERSION  # noqa: E402


def _write_checkpoint(data_root: Path, folder: str, name: str, ids: list[str]) -> None:
    path = data_root / folder / name / "policy.pt"
    path.parent.mkdir(parents=True)
    torch.save({"experiment": {"split": {"game_ids": {
        "train": [ids[0]], "validation": [ids[1]], "test": [ids[2]],
    }}}}, path)


def _setup(tmp_path: Path):
    data = tmp_path / "data"
    raw = data / "raw" / "collected"
    raw.mkdir(parents=True)
    # Model the known mismatch: collector state covers 43 games while the raw
    # corpus contains 61 completed games.
    state_path = raw / "collector_state.json"
    raw_ids = set()
    for index in range(61):
        raw_id = LiveLog(seed=800 + index).create_game().mulligan().begin_turn(1).complete()
        raw_game_id = inspect_segment(split_games(raw_id.lines)[0]).start_key
        raw_ids.add(raw_game_id)
        (raw / f"old-{index}.log").write_text("\n".join(raw_id.lines) + "\n", encoding="utf-8")
    state_ids = set(sorted(raw_ids)[:43])
    regular_state = {"version": STATE_VERSION,
                     "games": {game_id: IMPORTED for game_id in state_ids}}
    state_path.write_text(json.dumps(regular_state), encoding="utf-8")

    logs = tmp_path / "Logs"
    logs.mkdir()
    log_id = LiveLog(seed=801).create_game().mulligan().begin_turn(1)
    (logs / "Power.log").write_text("\n".join(log_id.lines) + "\n", encoding="utf-8")

    split_ids = ["b" * 64, "c" * 64, "d" * 64]
    _write_checkpoint(data, "processed_policy_ml1c", "baseline_seed42_v1", split_ids)
    _write_checkpoint(data, "processed_policy_ml2a", "seed42_v2", split_ids)
    dataset = data / "processed_policy_real" / "prior" / "train.jsonl"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(json.dumps({"game_id": "e" * 64}) + "\n", encoding="utf-8")
    log_game_id = inspect_segment(split_games(log_id.lines)[0]).start_key
    return data, logs, state_path, raw_ids | state_ids | {log_game_id, "b" * 64, "c" * 64,
                                    "d" * 64, "e" * 64}


def test_holdout_seeds_raw_state_logs_and_historical_ids_without_mutating_regular_state(tmp_path):
    data, logs, source_state, expected_excluded = _setup(tmp_path)
    source_before = source_state.read_bytes()

    prepared = prepare_holdout(data, logs)

    backup = prepared.root / "provenance" / "regular_collector_state.backup.json"
    assert backup.read_bytes() == source_before
    assert source_state.read_bytes() == source_before
    holdout_state = json.loads(prepared.state_path.read_text(encoding="utf-8"))
    assert holdout_state["games"] == {game_id: "SKIPPED_ALREADY_IMPORTED"
                                      for game_id in expected_excluded}
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_state_matches"] == 43
    assert manifest["source_raw_matches"] == 61
    assert manifest["raw_ids_missing_from_source_state"] == 18
    assert manifest["initial_holdout_matches"] == 0
    assert manifest["initial_holdout_policy_overlap"] == 0
    assert verify_holdout_disjoint(prepared) == {"policy_matches": 0, "historical_overlap": 0}
    assert prepared.raw_output != data / "raw" / "collected"
    assert prepared.policy_output != data / "processed_policy_real" / "collected"


def test_holdout_resume_is_idempotent_and_refuses_changed_regular_baseline(tmp_path):
    data, logs, source_state, _ = _setup(tmp_path)
    prepared = prepare_holdout(data, logs)
    initial_state = prepared.state_path.read_bytes()

    resumed = prepare_holdout(data, logs)

    assert resumed.state_path.read_bytes() == initial_state
    assert source_state.read_bytes() == (prepared.root / "provenance" /
                                         "regular_collector_state.backup.json").read_bytes()
    source_state.write_text(json.dumps({"version": STATE_VERSION, "games": {}}), encoding="utf-8")
    with pytest.raises(HoldoutError, match="BASELINE_CHANGED"):
        prepare_holdout(data, logs)


def test_corrupt_original_state_refuses_before_creating_holdout(tmp_path):
    data, logs, source_state, _ = _setup(tmp_path)
    source_state.write_text("{invalid", encoding="utf-8")

    with pytest.raises(HoldoutError, match="INVALID_REGULAR_COLLECTOR_STATE"):
        prepare_holdout(data, logs)
    assert not (data / "raw" / "holdout_checkpoint_2").exists()


def test_holdout_resume_refuses_new_historical_policy_data(tmp_path):
    data, logs, _, _ = _setup(tmp_path)
    prepare_holdout(data, logs)
    later_dataset = data / "processed_policy_real" / "later" / "train.jsonl"
    later_dataset.parent.mkdir(parents=True)
    later_dataset.write_text(json.dumps({"game_id": "f" * 64}) + "\n", encoding="utf-8")

    with pytest.raises(HoldoutError, match="HISTORICAL_POLICY_DATA_CHANGED"):
        prepare_holdout(data, logs)


def test_holdout_policy_overlap_with_historical_dataset_fails_closed(tmp_path):
    data, logs, _, historical = _setup(tmp_path)
    prepared = prepare_holdout(data, logs)
    prepared.policy_output.mkdir(parents=True)
    (prepared.policy_output / "overlap.jsonl").write_text(
        json.dumps({"game_id": "b" * 64}) + "\n", encoding="utf-8")

    with pytest.raises(HoldoutError, match="OVERLAPS_HISTORICAL_DATA"):
        verify_holdout_disjoint(prepared)


def test_unified_cli_has_opt_in_holdout_switch():
    args = run_manamind.build_parser().parse_args([])
    assert args.holdout is False
    assert run_manamind.build_parser().parse_args(["--ui", "--holdout"]).holdout is True
