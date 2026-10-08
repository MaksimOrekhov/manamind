"""Sanitized workflow tests for canonical real-policy dataset refresh."""
import copy
import json
from dataclasses import replace
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_real_policy_dataset import CATALOG, fixture  # noqa: E402
from manamind.domain.card import CardFeatures  # noqa: E402
from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.live.snapshot import state_hash, state_to_dict  # noqa: E402
from refresh_real_policy_dataset import (  # noqa: E402
    canonical_content_identity,
    compare_datasets,
    compare_state_fields,
    dataset_identity,
    frozen_experiment_usage,
    input_fingerprint,
    importer_source_fingerprint,
    quality_summary,
    IMPORTER_FILES,
    propose_unused_split,
    rebuild_once,
    verify_two_rebuilds,
)
from manamind.training.real_policy import audit_dataset, validate_example  # noqa: E402


def write_fixture(directory: Path, *, seed: int, name: str = "match.log", complete: bool = True) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    lines = fixture(seed=seed).lines
    if not complete:
        lines = lines[:-1]
    path = directory / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def rebuild(raw: Path, output: Path, *, source_sha: str = "a" * 40) -> dict:
    return rebuild_once(raw, output, ROOT / "data/cards/standard_current_enUS.json",
                        repo_root=ROOT, source_sha=source_sha)


def test_legacy_rows_reject_but_canonical_reexport_writes_current_schema(tmp_path):
    from manamind.integrations.powerlog.policy_import import extract_match

    row, = extract_match(fixture(seed=41).lines, CATALOG)[0]
    legacy = copy.deepcopy(row)
    legacy["state"]["self_player"].pop("healing_bonus")
    legacy["provenance"]["state_hash"] = state_hash(legacy["state"])
    with pytest.raises(ValueError, match="noncanonical"):
        validate_example(legacy)

    raw = tmp_path / "raw"
    write_fixture(raw, seed=41)
    output = tmp_path / "refresh"
    result = rebuild(raw, output)
    assert result["validation"] == "PASS"
    rebuilt = json.loads(next(output.glob("*.jsonl")).read_text(encoding="utf-8"))
    assert "healing_bonus" in rebuilt["state"]["self_player"]
    assert rebuilt["state"]["self_player"]["healing_bonus"] is None
    assert audit_dataset(output, CATALOG)["decisions_labeled"] == 1


def test_missing_and_known_zero_healing_bonus_remain_distinct():
    from manamind.integrations.powerlog.policy_import import extract_match

    row, = extract_match(fixture(seed=42).lines, CATALOG)[0]
    unknown = game_state_from_dict(row["state"])
    known_zero = replace(unknown, self_player=replace(unknown.self_player, healing_bonus=0))
    assert state_to_dict(unknown)["self_player"]["healing_bonus"] is None
    assert state_to_dict(known_zero)["self_player"]["healing_bonus"] == 0
    assert state_to_dict(unknown) != state_to_dict(known_zero)


def test_duplicate_raw_match_imports_once_and_is_reported(tmp_path):
    raw = tmp_path / "raw"
    write_fixture(raw, seed=43, name="a.log")
    write_fixture(raw, seed=43, name="b.log")
    output = tmp_path / "refresh"
    result = rebuild(raw, output)
    assert result["matches"] == 1
    assert result["decisions"] == 1
    assert result["raw_rejections"] == {"DUPLICATE_MATCH": 1}
    assert len(list(output.glob("*.jsonl"))) == 1


def test_manifest_mismatch_invalid_label_and_privacy_leak_fail_closed(tmp_path):
    from manamind.integrations.powerlog.policy_import import extract_match

    row, = extract_match(fixture(seed=44).lines, CATALOG)[0]
    bad_label = copy.deepcopy(row)
    bad_label["chosen_action_index"] = len(row["legal_actions"])
    with pytest.raises(ValueError, match="Chosen action"):
        validate_example(bad_label)
    leaked = copy.deepcopy(row)
    leaked_state = game_state_from_dict(leaked["state"])
    leaked_state = replace(leaked_state, opponent_known_cards=(CardFeatures(card_id="CS2_029"),))
    leaked["state"] = state_to_dict(leaked_state)
    leaked["provenance"]["state_hash"] = state_hash(leaked["state"])
    with pytest.raises(ValueError, match="privacy"):
        validate_example(leaked)

    raw = tmp_path / "raw"
    write_fixture(raw, seed=44)
    output = tmp_path / "refresh"
    rebuild(raw, output)
    manifest = next(output.glob("*.audit.json"))
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["decisions_labeled"] += 1
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest|inconsistent|Missing"):
        audit_dataset(output, CATALOG)


def test_input_and_output_fingerprints_ignore_names_order_and_timestamps(tmp_path):
    raw_a, raw_b = tmp_path / "a", tmp_path / "b"
    write_fixture(raw_a, seed=45, name="one.log")
    write_fixture(raw_a, seed=46, name="two.log")
    write_fixture(raw_b, seed=46, name="renamed-2.log")
    write_fixture(raw_b, seed=45, name="renamed-1.log")
    paths_a = list(raw_a.glob("*.log"))
    paths_b = list(raw_b.glob("*.log"))
    assert input_fingerprint(paths_a) == input_fingerprint(paths_b)
    out_a, out_b = tmp_path / "out-a", tmp_path / "out-b"
    rebuild(raw_a, out_a)
    rebuild(raw_b, out_b)
    assert canonical_content_identity(out_a) == canonical_content_identity(out_b)
    assert dataset_identity([
        json.loads(line) for path in out_a.glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines() if line
    ]) == dataset_identity([
        json.loads(line) for path in out_b.glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines() if line
    ])


def test_quality_summary_uses_game_state_turn_number():
    from manamind.integrations.powerlog.policy_import import extract_match

    example, = extract_match(fixture(seed=46).lines, CATALOG)[0]
    rows = []
    for index, turn in enumerate((1, 3, 7), 1):
        row = copy.deepcopy(example)
        row["decision_id"] = f"{row['game_id']}:{index}"
        row["state"]["turn_number"] = turn
        rows.append(row)

    summary = quality_summary(rows, {}, {})

    assert summary["turn_decisions"] == {"1": 1, "3": 1, "7": 1}


def test_quality_summary_reports_new_hero_fields_without_collapsing_unknowns():
    from manamind.integrations.powerlog.policy_import import extract_match

    example, = extract_match(fixture(seed=461).lines, CATALOG)[0]
    example["state"]["self_player"].update({
        "hero_max_health": 30, "hero_frozen": False, "hero_power_ready": True,
    })
    example["state"]["opponent"].update({
        "hero_max_health": 40, "hero_frozen": None, "hero_power_ready": False,
    })

    summary = quality_summary([example], {}, {})["hero_state_fields"]

    assert summary["hero_max_health"]["self_player"] == {
        "known": 1, "unknown": 0, "values": {"30": 1},
    }
    assert summary["hero_max_health"]["opponent"]["values"] == {"40": 1}
    assert summary["hero_frozen"]["self_player"]["values"] == {"false": 1}
    assert summary["hero_frozen"]["opponent"]["values"] == {"unknown": 1}
    assert summary["hero_power_ready"]["self_player"]["values"] == {"true": 1}
    assert summary["hero_power_ready"]["opponent"]["values"] == {"false": 1}


def test_observation_revision_preserves_labels_and_only_changes_approved_hero_fields():
    from manamind.integrations.powerlog.policy_import import extract_match

    current, = extract_match(fixture(seed=462).lines, CATALOG)[0]
    previous = copy.deepcopy(current)
    rebuilt = copy.deepcopy(current)
    for side in ("self_player", "opponent"):
        previous["state"][side].pop("hero_max_health", None)
        previous["state"][side]["hero_frozen"] = None
        previous["state"][side]["hero_power_ready"] = None
    for side, max_health, frozen, ready in (
        ("self_player", 30, True, False), ("opponent", 40, False, True),
    ):
        player = rebuilt["state"][side]
        player.pop("hero_max_health", None)
        player["hero_max_health"] = max_health
        player["hero_frozen"] = frozen
        player["hero_power_ready"] = ready

    field_diff = compare_state_fields([previous], [rebuilt])
    dataset_diff = compare_datasets([previous], [rebuilt])

    assert field_diff["expected_changes_by_path"] == {
        "opponent.hero_frozen": 1,
        "opponent.hero_max_health": 1,
        "opponent.hero_power_ready": 1,
        "self_player.hero_frozen": 1,
        "self_player.hero_max_health": 1,
        "self_player.hero_power_ready": 1,
    }
    assert field_diff["decisions_with_unexpected_state_changes"] == 0
    assert field_diff["unexpected_changes_by_path"] == {}
    assert dataset_diff["chosen_index_changed"] == 0
    assert dataset_diff["chosen_action_semantics_changed"] == 0
    assert dataset_diff["legal_menu_changed"] == 0
    assert dataset_diff["outcome_changed"] == 0

    unexpected = copy.deepcopy(rebuilt)
    unexpected["state"]["self_player"]["available_mana"] += 1
    rejected_diff = compare_state_fields([previous], [unexpected])
    assert rejected_diff["decisions_with_unexpected_state_changes"] == 1
    assert rejected_diff["unexpected_changes_by_path"] == {"self_player.available_mana": 1}


def test_observation_fields_keep_state_encoder_shape_and_checkpoint_features_compatible():
    from manamind.encoding.state_encoder import GLOBAL_FEATURE_NAMES, STATE_ENCODING_SCHEMA_VERSION, StateEncoder
    from manamind.integrations.powerlog.policy_import import extract_match

    row, = extract_match(fixture(seed=463).lines, CATALOG)[0]
    state = game_state_from_dict(row["state"])
    encoder = StateEncoder(CATALOG)
    base = encoder.encode(state)
    max_health_only = replace(
        state,
        self_player=replace(state.self_player, hero_max_health=40),
    )
    changed_max = encoder.encode(max_health_only)
    feature_state = replace(
        state,
        self_player=replace(state.self_player, hero_frozen=True, hero_power_ready=False),
    )
    changed_features = encoder.encode(feature_state)

    assert STATE_ENCODING_SCHEMA_VERSION == 16
    assert "hero_max_health" not in GLOBAL_FEATURE_NAMES
    assert base.global_features.shape == changed_max.global_features.shape == changed_features.global_features.shape
    assert (base.global_features == changed_max.global_features).all()
    for name in ("self_hero_frozen", "self_hero_power_ready"):
        index = GLOBAL_FEATURE_NAMES.index(name)
        assert base.global_features[index] != changed_features.global_features[index]


def test_verify_two_rebuilds_checks_independent_canonical_output(tmp_path):
    raw = tmp_path / "raw"
    write_fixture(raw, seed=464)
    output = tmp_path / "canonical"

    proof = verify_two_rebuilds(raw, output, ROOT / "data/cards/standard_current_enUS.json",
                                repo_root=ROOT, source_sha="b" * 40)

    assert proof["runs"] == 2
    assert proof["identical_content_identity"] is True
    assert proof["canonical_content_identity_sha256"]
    assert proof["dataset_identity_sha256"]
    assert not output.exists()


def test_importer_source_fingerprint_changes_when_relevant_source_changes(tmp_path):
    for index, relative in enumerate(IMPORTER_FILES):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"source-{index}", encoding="utf-8")

    expected_sources = {
        "src/manamind/integrations/powerlog/visible_state.py",
        "src/manamind/live/session.py",
        "src/manamind/domain/game_state.py",
        "src/manamind/integrations/powerlog/policy_actions.py",
    }
    assert expected_sources <= set(IMPORTER_FILES)
    before = importer_source_fingerprint(tmp_path)
    changed = tmp_path / "src/manamind/integrations/powerlog/visible_state.py"
    changed.write_text(changed.read_text(encoding="utf-8") + "changed", encoding="utf-8")

    assert importer_source_fingerprint(tmp_path) != before

def test_incomplete_game_is_rejected_not_admitted(tmp_path):
    raw = tmp_path / "raw"
    write_fixture(raw, seed=47, complete=False)
    output = tmp_path / "refresh"
    result = rebuild(raw, output)
    assert result["validation"] == "NO_ADMITTED_MATCHES"
    assert result["matches"] == result["decisions"] == 0
    assert result["raw_rejections"] == {"INCOMPLETE": 1}
    assert not list(output.glob("*.jsonl"))


def test_refresh_refuses_existing_output_without_touching_it(tmp_path):
    raw = tmp_path / "raw"
    write_fixture(raw, seed=48)
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        rebuild(raw, output)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_experiment_registry_marks_prior_eval_and_split_filters_contaminated_games():
    rows = []
    eval_ids = [f"{i:064x}" for i in range(100, 112)]
    train_id, val_id, test_id = (f"{i:064x}" for i in (1, 2, 3))
    for i, game_id in enumerate(eval_ids):
        for decision in range(1, 44 if i < 11 else 43):
            rows.append({"game_id": game_id, "decision_id": f"{game_id}:{decision}"})
    previous = rows
    split = {"game_ids": {"train": [train_id], "validation": [val_id], "test": [test_id]}}
    payload = {"experiment": {
        "dataset_sha256": "dataset", "split_sha256": "split", "split": split,
    }}
    eval_report = {
        "current_dataset": {"identity_sha256": dataset_identity(previous)},
        "fresh_game_id_disjoint_evaluation": {
            "v1": {"top1_accuracy": 0.5}, "v2": {"top1_accuracy": 0.6},
        },
    }
    # The current extraction has a new dataset identity, while the old rows remain
    # the authoritative corpus used to map ML-EVAL-0 game IDs.
    current_rows = copy.deepcopy(rows)
    for row in current_rows:
        row["state"] = {"self_player": {"hero_max_health": 30, "hero_frozen": None}}
    assert dataset_identity(current_rows) != dataset_identity(previous)
    current_records = [{"match_id": game_id} for game_id in eval_ids]
    registry = frozen_experiment_usage(
        current_records, current_rows, previous, payload, copy.deepcopy(payload), eval_report
    )
    assert registry["eval_mapping_reliable"] is True
    by_id = {item["match_id"]: item for item in registry["entries"]}
    assert all("ML_EVAL_0_INFERENCE" in by_id[game_id]["usage"] for game_id in eval_ids)
    assert "POLICY_V1_TRAIN" in by_id[train_id]["usage"]
    assert by_id[train_id]["status"] == "KNOWN_USED"

    contaminated = [{"match_id": train_id, "status": "KNOWN_USED", "usage": ["POLICY_V1_TRAIN"]}]
    for game_id in eval_ids[:2]:
        contaminated.append({"match_id": game_id, "status": "NOT_KNOWN_USED", "usage": []})
    proposal = propose_unused_split(rows, {"entries": contaminated}, seed=77)
    assert proposal["status"] == "NO_CLEAN_THREE_WAY_SPLIT"
    assert proposal["eligible_matches"] == 2


def test_unused_split_never_separates_decisions_from_a_match():
    from manamind.integrations.powerlog.policy_import import extract_match

    rows = []
    entries = []
    for seed in (50, 51, 52):
        match, = extract_match(fixture(seed=seed).lines, CATALOG)[0]
        # Replicate sanitized decisions with unique decision IDs to verify group isolation.
        for index in range(3):
            row = copy.deepcopy(match)
            row["decision_id"] = f'{row["game_id"]}:{index + 1}'
            rows.append(row)
        entries.append({"match_id": match["game_id"], "status": "NOT_KNOWN_USED", "usage": []})
    split = propose_unused_split(rows, {"entries": entries}, seed=123)
    assert split["status"] == "PROPOSED"
    memberships = {part: set(ids) for part, ids in split["parts"].items()}
    assert not (memberships["train"] & memberships["validation"])
    assert not (memberships["train"] & memberships["test"])
    assert not (memberships["validation"] & memberships["test"])
    assert sum(split["decision_counts"].values()) == len(rows)
