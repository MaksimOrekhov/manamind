"""POLICY-PREPARE-DATA-1: action schema 2 (PREPARE_CARD) is accepted only on request, and the corpus builder is isolated.

Synthetic logs only; no checkpoint is trained or written.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from build_policy_prepare_corpus import (  # noqa: E402
    build, check_encoders, compare_with_baseline, plan_split, prepare_statistics, privacy_scan, select_logs,
    tree_digest, usage_registry,
)
from import_policy_power_log import import_log, save_match  # noqa: E402
from test_prepare_roots import prepare_log  # noqa: E402
from test_real_policy_dataset import CATALOG, fixture  # noqa: E402

from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match  # noqa: E402
from manamind.models.policy_inputs import encode_policy_inputs  # noqa: E402
from manamind.training.real_policy import (  # noqa: E402
    audit_dataset, encode_example, load_examples, split_matches, validate_example,
)

PLAY_AND_PREPARE = [("NONE", True), ("NONE", False)]       # targeted root = play, target-free root = Prepare
CHEAP_ONLY = [("NONE", False), ("REQ_ENOUGH_MANA", False)]  # only the Prepare root is affordable


def prepare_rows(seed=1, roots=PLAY_AND_PREPARE, **kwargs):
    kwargs.setdefault("mana", 9 if roots is PLAY_AND_PREPARE else 3)
    send = kwargs.pop("send", 2 if roots is PLAY_AND_PREPARE else 1)
    rows, summary = extract_match(prepare_log(roots, seed=seed, send=send, target=0, block="DECK_ACTION", **kwargs).lines,
                                  CATALOG, prepare_actions=True)
    assert summary["decisions_labeled"] == 1, summary
    return rows


def v1_row(seed=3):
    rows, _ = extract_match(fixture(seed=seed).lines, CATALOG)
    return rows[0]


def chosen(row):
    return row["legal_actions"][row["chosen_action_index"]]


def write_log(directory: Path, name: str, log) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("\n".join(log.lines) + "\n", encoding="utf-8")
    return path


# -- schema: version 1 stays the default ----------------------------------------------------------------------------------

def test_version_1_rows_are_accepted_unchanged_by_default_and_with_the_new_mode():
    row = v1_row()
    assert row["action_schema_version"] == 1
    validate_example(row)
    validate_example(row, allow_prepare=True)
    assert load_example_roundtrip(row)


def load_example_roundtrip(row):
    return json.loads(json.dumps(row)) == row


def test_version_2_row_needs_the_explicit_mode_everywhere():
    row, = prepare_rows()
    assert row["action_schema_version"] == 2 and chosen(row)["type"] == "PREPARE_CARD"
    for call in (lambda: validate_example(row),
                 lambda: encode_example(row, StateEncoder(CATALOG), representation=2),
                 lambda: split_matches([row] * 3)):
        with pytest.raises(ValueError):
            call()
    validate_example(row, allow_prepare=True)
    encode_example(row, StateEncoder(CATALOG), representation=2, allow_prepare=True)


def test_directory_loader_and_audit_do_not_silently_take_version_2(tmp_path):
    row, = prepare_rows()
    summary = {"schema_version": 1, "game_id": row["game_id"], "final_result": 1.0, "decisions_total": 1,
               "decisions_labeled": 1, "decisions_skipped": 0, "skip_reasons": {}, "skipped_decisions": []}
    (tmp_path / f"{row['game_id']}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (tmp_path / f"{row['game_id']}.audit.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError):
        load_examples(tmp_path)
    with pytest.raises(ValueError):
        audit_dataset(tmp_path, CATALOG)
    assert len(load_examples(tmp_path, allow_prepare=True)) == 1
    assert audit_dataset(tmp_path, CATALOG, allow_prepare=True)["chosen_action_distribution"]["PREPARE_CARD"] == 1


# -- schema: the version must describe the menu, and bad content is refused ----------------------------------------------

def test_version_must_match_menu_in_both_directions():
    prepared, = prepare_rows()
    wrong = copy.deepcopy(prepared)
    wrong["action_schema_version"] = 1                      # PREPARE_CARD smuggled into a version 1 row
    with pytest.raises(ValueError):
        validate_example(wrong, allow_prepare=True)
    plain = v1_row()
    plain["action_schema_version"] = 2                      # version 2 label on a menu without PREPARE_CARD
    with pytest.raises(ValueError):
        validate_example(plain, allow_prepare=True)
    for bad in (0, 3, True, "2", None):
        row = copy.deepcopy(prepared)
        row["action_schema_version"] = bad
        with pytest.raises(ValueError):
            validate_example(row, allow_prepare=True)


def _set(action_index, **changes):
    def mutate(row):
        row["legal_actions"][action_index].update(changes)
    return mutate


def _prepare_index(row):
    return next(i for i, a in enumerate(row["legal_actions"]) if a["type"] == "PREPARE_CARD")


@pytest.mark.parametrize("name", [
    "unknown_type", "target_field", "board_slot", "hand_index_out_of_range", "other_hand_card", "source_mismatch",
    "not_finite", "unknown_field", "duplicate_prepare", "negative_hand_index", "string_hand_index",
    "hero_flag_without_hero", "bad_target_side",
])
def test_corrupt_prepare_rows_are_refused(name):
    row, = prepare_rows()
    index = _prepare_index(row)
    action = row["legal_actions"][index]
    if name == "unknown_type":
        action["type"] = "TRADE_CARD"
    elif name == "target_field":
        action.update(target_kind="MINION", target_side="OPPONENT", target_card_id="CS2_168")
    elif name == "board_slot":
        action["play_position"] = 2
    elif name == "hand_index_out_of_range":
        action["hand_index"] = 99
    elif name == "other_hand_card":
        action["card_id"] = action["source_card_id"] = "CS2_168"
    elif name == "source_mismatch":
        action["source_card_id"] = "CS2_168"
    elif name == "not_finite":
        action["card_cost"] = float("nan")
    elif name == "unknown_field":
        action["entity_id"] = 6
    elif name == "duplicate_prepare":
        twin = copy.deepcopy(action)
        twin["card_cost"] += 1                               # differs, so only the one-PREPARE-per-card rule can catch it
        row["legal_actions"].append(twin)
    elif name == "negative_hand_index":
        action["hand_index"] = -1
    elif name == "string_hand_index":
        action["hand_index"] = "0"
    elif name == "hero_flag_without_hero":
        action["source_is_hero"] = True
    elif name == "bad_target_side":
        action["target_side"] = "ELSEWHERE"
    with pytest.raises(ValueError):
        validate_example(row, allow_prepare=True)


def test_prepare_card_is_not_a_version_1_action_even_if_the_row_claims_version_1():
    row, = prepare_rows()
    row["action_schema_version"] = 1
    with pytest.raises(ValueError):
        validate_example(row)                                 # default mode: unsupported action type
    plain = v1_row()
    plain["legal_actions"].append({"type": "TRADE_CARD", "play_position": 0})
    with pytest.raises(ValueError):
        validate_example(plain, allow_prepare=True)


# -- PREPARE_CARD is chosen for the right card and its handle is the ordered hand ------------------------------------------

def test_choosing_prepare_names_the_hand_card_and_the_menu_keeps_both_actions():
    row, = prepare_rows()
    action = chosen(row)
    state = game_state_from_dict(row["state"])
    assert action["type"] == "PREPARE_CARD" and action["card_id"] == "CS2_029"
    assert state.self_hand[action["hand_index"]].card_id == action["card_id"]
    assert "target_kind" not in action and action["play_position"] == 0
    kinds = sorted(a["type"] for a in row["legal_actions"])
    assert kinds == ["END_TURN", "PLAY_CARD", "PREPARE_CARD"]
    play, = (a for a in row["legal_actions"] if a["type"] == "PLAY_CARD")
    assert play["hand_index"] == action["hand_index"] and "target_kind" in play
    stats = prepare_statistics([row])
    assert stats["decisions_where_player_chose_prepare"] == 1
    assert stats["menus_where_a_card_has_both_play_and_prepare"] == 1


def test_choosing_the_normal_play_of_a_prepare_card_is_not_counted_as_prepare():
    rows, summary = extract_match(prepare_log(PLAY_AND_PREPARE, mana=9, send=1, target=50, block="PLAY").lines,
                                  CATALOG, prepare_actions=True)
    assert summary["decisions_labeled"] == 1
    row, = rows
    assert chosen(row)["type"] == "PLAY_CARD" and row["action_schema_version"] == 2
    stats = prepare_statistics(rows)
    assert stats["decisions_with_prepare_in_menu"] == 1 and stats["decisions_where_player_chose_prepare"] == 0


# -- saving and duplicate protection -------------------------------------------------------------------------------------

def test_saving_a_version_2_match_needs_the_prepare_mode(tmp_path):
    log = prepare_log(PLAY_AND_PREPARE, mana=9, send=2, target=0, block="DECK_ACTION")
    rows, summary = extract_match(log.lines, CATALOG, prepare_actions=True)
    with pytest.raises(ValueError):
        save_match(rows, summary, tmp_path / "v1")
    assert not list((tmp_path / "v1").glob("*.jsonl"))
    save_match(rows, summary, tmp_path / "v2", allow_prepare=True)
    assert len(list((tmp_path / "v2").glob("*.jsonl"))) == 1


def test_default_import_never_writes_version_2_and_keeps_refusing_prepare_cards(tmp_path):
    raw = write_log(tmp_path / "raw", "m.log", prepare_log(PLAY_AND_PREPARE, mana=9, send=2, target=0, block="DECK_ACTION"))
    result = import_log(raw, tmp_path / "default", CATALOG)
    assert result["games_imported"] == 1 and result["decisions_labeled"] == 0
    assert result["decision_skip_reasons"] == {"AMBIGUOUS_SELECTION": 1}
    result = import_log(raw, tmp_path / "prepare", CATALOG, prepare_actions=True)
    assert result["decisions_labeled"] == 1
    assert {json.loads(line)["action_schema_version"]
            for p in (tmp_path / "prepare").glob("*.jsonl") for line in p.read_text(encoding="utf-8").splitlines()} == {2}


def test_the_same_match_cannot_be_imported_twice(tmp_path):
    raw = write_log(tmp_path / "raw", "m.log", prepare_log(CHEAP_ONLY, seed=5, send=1))
    first = import_log(raw, tmp_path / "out", CATALOG, prepare_actions=True)
    again = import_log(raw, tmp_path / "out", CATALOG, prepare_actions=True)
    assert first["games_imported"] == 1 and again["games_imported"] == 0
    assert again["game_skip_reasons"] == {"DUPLICATE_MATCH": 1}
    with pytest.raises(PolicyImportError):
        rows, summary = extract_match(prepare_log(CHEAP_ONLY, seed=5, send=1).lines, CATALOG, prepare_actions=True)
        save_match(rows, summary, tmp_path / "out", allow_prepare=True)


def test_a_copy_of_a_collected_match_is_not_selected_as_an_extra_source(tmp_path):
    original = write_log(tmp_path / "collected", "a.log", prepare_log(CHEAP_ONLY, seed=6, send=1))
    copy_ = write_log(tmp_path / "live", "slice.log", prepare_log(CHEAP_ONLY, seed=6, send=1))
    other = write_log(tmp_path / "live", "other.log", prepare_log(CHEAP_ONLY, seed=7, send=1))
    selected, sources = select_logs([original], [copy_, other])
    assert selected == [original, other]
    roles = {s["name"]: s["role"] for s in sources}
    assert roles == {"a.log": "primary", "slice.log": "extra_ignored_duplicate", "other.log": "extra"}


# -- previously labeled decisions are unchanged ----------------------------------------------------------------------------

def test_previously_labeled_rows_are_byte_identical_and_new_rows_are_reported():
    ordinary = fixture(seed=11)
    old, _ = extract_match(ordinary.lines, CATALOG)
    new, _ = extract_match(ordinary.lines, CATALOG, prepare_actions=True)
    report = compare_with_baseline(old, new + prepare_rows(seed=12))
    assert report["common_decisions"] == 1 and report["common_byte_identical"] == 1
    assert report["common_not_identical"] == 0 and report["baseline_decisions_missing_from_new"] == 0
    assert report["added_decisions"] == 1 and report["added_with_prepare_in_menu"] == 1
    assert report["added_prepare_chosen"] == 1 and report["added_schema_versions"] == {"2": 1}


def test_any_change_to_a_previously_labeled_row_is_visible():
    old, _ = extract_match(fixture(seed=13).lines, CATALOG)
    changed = copy.deepcopy(old)
    changed[0]["chosen_action_index"] = 0 if old[0]["chosen_action_index"] else 1
    report = compare_with_baseline(old, changed)
    assert report["common_not_identical"] == 1 and report["not_identical_by_field"] == {"chosen_action_index": 1}
    assert compare_with_baseline(old, [])["baseline_decisions_missing_from_new"] == len(old)


# -- split: whole matches, seen vs fresh --------------------------------------------------------------------------------

def _fake_rows(game_ids, prepare_chosen=()):
    rows = []
    for game in game_ids:
        action = "PREPARE_CARD" if game in prepare_chosen else "END_TURN"
        rows.append({"game_id": game, "decision_id": f"{game}:1", "final_result": 1.0,
                     "legal_actions": [{"type": "END_TURN"}, {"type": action}], "chosen_action_index": 1})
    return rows


def _registry(status):
    return {"entries": [{"match_id": g, "status": s, "usage": {}, "live_session_recorded": False}
                        for g, s in status.items()]}


def test_split_keeps_whole_matches_and_never_mixes_fresh_with_used():
    games = [f"{i:02d}" * 32 for i in range(12)]
    status = {g: ("NOT_KNOWN_USED" if i % 3 == 0 else "TRAINED_OR_SELECTED") for i, g in enumerate(games)}
    frozen = {"train": games[1:6], "validation": games[6:8], "test": games[8:11]}
    plan = plan_split(_fake_rows(games), _registry(status), frozen, seed=1)
    parts = {k: set(v) for k, v in plan["parts"].items()}
    assert set().union(*parts.values()) == set(games)
    assert sum(len(v) for v in parts.values()) == len(games)               # nothing duplicated, nothing lost
    assert parts["fresh_holdout"] == {g for g in games if status[g] == "NOT_KNOWN_USED"}
    for name in ("train", "validation", "test_seen"):
        assert not parts[name] & parts["fresh_holdout"]
    assert parts["test_seen"] == set(games[8:11]) - parts["fresh_holdout"]
    assert any(v.startswith("INSUFFICIENT_FRESH_MATCHES") for v in plan["independence_verdicts"])
    assert plan == plan_split(_fake_rows(games), _registry(status), frozen, seed=1)         # deterministic


def test_an_evaluated_only_match_is_never_called_fresh_or_trained():
    games = [f"{i:02d}" * 32 for i in range(4)]
    status = {games[0]: "EVALUATED_ONLY", games[1]: "NOT_KNOWN_USED", games[2]: "TRAINED_OR_SELECTED",
              games[3]: "TRAINED_OR_SELECTED"}
    plan = plan_split(_fake_rows(games), _registry(status), {"train": [games[2]], "validation": [games[3]]}, seed=2)
    assert plan["parts"]["test_seen"] == [games[0]]
    assert plan["parts"]["fresh_holdout"] == [games[1]]
    assert plan["parts"]["train"] == [games[2]] and plan["parts"]["validation"] == [games[3]]


def test_fresh_holdout_reports_when_prepare_choices_are_too_few():
    games = [f"{i:02d}" * 32 for i in range(14)]
    plan = plan_split(_fake_rows(games, prepare_chosen=games[:2]), _registry({g: "NOT_KNOWN_USED" for g in games}),
                      None, seed=3)
    assert plan["summary"]["fresh_holdout"]["prepare_chosen"] == 2
    assert any(v.startswith("INSUFFICIENT_FRESH_PREPARE_CHOICES") for v in plan["independence_verdicts"])
    assert not any(v.startswith("INSUFFICIENT_FRESH_MATCHES") for v in plan["independence_verdicts"])


def test_usage_registry_marks_checkpoint_and_evaluation_matches(tmp_path):
    games = {"a" * 64, "b" * 64, "c" * 64, "d" * 64}
    split_path = tmp_path / "data/processed_policy_v3/frozen_split.json"
    split_path.parent.mkdir(parents=True)
    split_path.write_text(json.dumps({"game_ids": {"train": ["a" * 64], "validation": [], "test": ["b" * 64]}}))
    report = tmp_path / "reports/model_shadow_eval_1/eval_20261013.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"inputs": {"importer_summaries": {"cccccccc": {}}}}))
    registry = usage_registry(tmp_path, games)
    status = {e["match_id"]: e["status"] for e in registry["entries"]}
    assert status == {"a" * 64: "TRAINED_OR_SELECTED", "b" * 64: "EVALUATED_ONLY", "c" * 64: "EVALUATED_ONLY",
                      "d" * 64: "NOT_KNOWN_USED"}


# -- encoders --------------------------------------------------------------------------------------------------------------

def test_prepare_rows_encode_for_policy_v2_and_v3_and_pass_the_technical_checks():
    rows = prepare_rows(seed=21) + prepare_rows(seed=22, roots=CHEAP_ONLY)
    encoder = StateEncoder(CATALOG)
    for row in rows:
        state = game_state_from_dict(row["state"])
        v2 = encode_policy_inputs(state, row["legal_actions"], encoder, representation=2)
        v3 = encode_policy_inputs(state, row["legal_actions"], encoder, representation=3)
        assert all(torch.equal(a, b) for a, b in zip(v2, v3))
        _state, ids, entities, actions, card_ids, links = v2
        assert len(actions) == len(row["legal_actions"]) and links.shape == (len(actions), 4)
        assert all(bool(torch.isfinite(t).all()) for t in (_state, entities, actions))
        index = _prepare_index(row)
        assert int(links[index, 0]) >= 0 and int(links[index, 1]) == -1
        assert int(ids[links[index, 0]]) == int(card_ids[index, 0]) != 0
    report = check_encoders(rows, CATALOG, {})
    assert report["verdict"] == "PASS", report
    assert report["checks"][0]["prepare_actions_encoded_correctly"] == 2


def test_check_encoders_counts_ids_the_vocabulary_maps_to_unknown():
    hero_attack, = extract_match(fixture(4, 50).lines, CATALOG)[0]       # the hero is not a catalog card
    report = check_encoders([hero_attack], CATALOG, {})
    assert report["verdict"] == "PASS"
    counts = report["checks"][0]["action_card_ids_mapped_to_unknown"]
    assert counts["unknown"] >= 1
    assert counts["unknown"] <= counts["total"]


def test_check_encoders_fails_loudly_on_a_broken_link_row():
    row, = prepare_rows(seed=23)
    row["legal_actions"][_prepare_index(row)]["source_card_id"] = "CS2_168"     # no longer the hand card of the link
    with pytest.raises(ValueError):
        check_encoders([row], CATALOG, {})


# -- end-to-end builder on synthetic raw logs: isolation, idempotence, determinism ----------------------------------------

def _sandbox(tmp_path):
    data = tmp_path / "data"
    raw = data / "raw/collected"
    write_log(raw, "p1.log", prepare_log(PLAY_AND_PREPARE, seed=31, mana=9, send=2, target=0, block="DECK_ACTION"))
    write_log(raw, "p2.log", prepare_log(CHEAP_ONLY, seed=32, send=1))
    write_log(raw, "o.log", fixture(seed=33))
    existing = data / "processed_policy_real/previous"
    existing.mkdir(parents=True)
    (existing / "keep.jsonl").write_text("{}\n", encoding="utf-8")
    return data, raw, existing


def _args(data, raw, out):
    import argparse
    return argparse.Namespace(data_root=data, collected_dir=raw, extra_raw=[], cards=ROOT / "data/cards/standard_current_enUS.json",
                              out_root=out, seed=7, source_sha="b" * 40, verify_determinism=True, skip_checkpoints=True)


def test_builder_writes_an_isolated_new_corpus_and_refuses_to_overwrite(tmp_path):
    data, raw, existing = _sandbox(tmp_path)
    before = tree_digest([data / "raw", existing])
    out = data / "processed_policy_prepare_1"
    result = build(_args(data, raw, out))
    assert tree_digest([data / "raw", existing]) == before                 # raw logs and old datasets untouched
    assert sorted(p.name for p in out.iterdir()) == [
        "audit.json", "baseline_v1", "comparison.json", "dataset", "encoder_check.json", "manifest.json",
        "split_plan.json", "usage_registry.json"]
    audit, comparison = result["audit"], result["comparison"]
    assert audit["matches"] == 3 and audit["decisions_labeled"] == 3
    assert audit["prepare"]["decisions_where_player_chose_prepare"] == 2
    assert audit["privacy"]["verdict"] == "PASS"
    assert comparison["common_byte_identical"] == 1 and comparison["common_not_identical"] == 0
    assert comparison["added_decisions"] == 2 and comparison["added_prepare_chosen"] == 2
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["determinism"]["identical_content_identity"] and manifest["isolation"]["unchanged"]
    assert manifest["verdict_inputs"]["baseline_byte_identical"] is True
    # the version 1 baseline directory holds no schema 2 row, and only the Prepare corpus needs the new mode
    assert {r["action_schema_version"] for r in load_examples(out / "baseline_v1")} == {1}
    assert {r["action_schema_version"] for r in load_examples(out / "dataset", allow_prepare=True)} == {1, 2}
    with pytest.raises(ValueError):
        load_examples(out / "dataset")
    # a second run into the same place must refuse and change nothing
    digest = tree_digest([out])
    with pytest.raises(FileExistsError):
        build(_args(data, raw, out))
    assert tree_digest([out]) == digest


def test_builder_refuses_the_value_dataset_directory_and_a_stale_staging_directory(tmp_path):
    data, raw, _ = _sandbox(tmp_path)
    with pytest.raises(ValueError):
        build(_args(data, raw, data / "processed_real/policy"))
    out = data / "processed_policy_prepare_1"
    (data / ".processed_policy_prepare_1.building").mkdir()
    with pytest.raises(FileExistsError):
        build(_args(data, raw, out))
    assert not out.exists()


def test_privacy_scan_flags_a_battletag_like_string_and_a_handle_key():
    row, = prepare_rows(seed=41)
    assert privacy_scan([row])["verdict"] == "PASS"
    leaked = copy.deepcopy(row)
    leaked["state"]["self_player"]["player_class"] = "Name#12345"
    assert privacy_scan([leaked])["verdict"] == "FAIL"
    handle = copy.deepcopy(row)
    handle["legal_actions"][0]["entity_id"] = 6
    assert privacy_scan([handle])["verdict"] == "FAIL"
