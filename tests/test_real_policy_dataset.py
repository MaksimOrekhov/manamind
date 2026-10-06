"""Independent selection/visibility expectations, not simulated action labels."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from live_fixtures import CANARIES, LiveLog, desc  # noqa: E402
from import_policy_power_log import import_log, save_match  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match  # noqa: E402
from manamind.models.policy import (  # noqa: E402
    ACTION_FEATURE_NAMES, POLICY_STATE_FEATURE_NAMES, PolicyNetwork,
    encode_action_card_ids, encode_legal_actions, load_policy_weights,
)
from manamind.training.real_policy import (  # noqa: E402
    audit_dataset, encode_example, evaluate_held_out, load_examples, split_matches, validate_example,
)

ROOT = Path(__file__).parents[1]
CATALOG = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")


def fixture(source=6, target=0, *, seed=1, only_end=False, duplicate=False, position=0,
            supersede=False, canaries=False, sub=False):
    log = LiveLog(seed=seed, canaries=canaries).create_game().mulligan()
    log.p("TAG_CHANGE Entity=6 tag=CARDTYPE value=SPELL")
    log.entity(45, "LOCATION_UNKNOWN", {"CARDTYPE": "LOCATION", "ZONE": "PLAY", "CONTROLLER": 1,
                                       "ZONE_POSITION": 2, "HEALTH": 3, "EXHAUSTED": 0})
    if canaries:
        log.canary_reveals().opponent_hand_identity()
    log.begin_turn(1)
    log.raw("GameState", "DebugPrintOptions", "id=1")
    log.raw("GameState", "DebugPrintOptions", "option 0 type=END_TURN mainEntity= error=INVALID errorParam=")
    if not only_end:
        zone = "HAND" if source == 6 else "PLAY"
        card = {6: "CS2_029", 41: "CS2_231", 40: "HERO_POWER_X", 45: "LOCATION_UNKNOWN", 4: "HERO_01"}[source]
        for index in [1, 2] if duplicate else [1]:
            log.raw("GameState", "DebugPrintOptions",
                    f"option {index} type=POWER mainEntity={desc(source, zone, 1, card, 1)} error=NONE errorParam=")
            if sub:
                log.raw("GameState", "DebugPrintOptions",
                        f"subOption 2 entity={desc(6, 'HAND', 1, 'CS2_029', 1)} error=NONE errorParam=")
            if target:
                log.raw("GameState", "DebugPrintOptions",
                        f"target 0 entity={desc(target, 'PLAY', 1, 'CS2_168', 2)} error=NONE errorParam=")
    if supersede:
        log.p("TAG_CHANGE Entity=2 tag=RESOURCES_USED value=1")
    log.raw("GameState", "SendOption", f"selectedOption={0 if only_end else 1} selectedSubOption=-1 "
            f"selectedTarget={target} selectedPosition={position}")
    if not only_end:
        log.p(f"BLOCK_START BlockType={'ATTACK' if source in (4, 41) else 'PLAY'} "
              f"Entity={desc(source, zone, 1, card, 1)} EffectCardId= EffectIndex=0 Target={target} SubOption=-1")
        log.p("BLOCK_END")
    log.p("TAG_CHANGE Entity=2 tag=PLAYSTATE value=WON")
    log.p("TAG_CHANGE Entity=3 tag=PLAYSTATE value=LOST")
    log.complete()
    return log


@pytest.mark.parametrize("source,target,expected", [
    (6, 0, "PLAY_CARD"), (6, 50, "PLAY_CARD"), (41, 50, "ATTACK"), (4, 50, "ATTACK"),
    (40, 0, "HERO_POWER"), (45, 0, "ACTIVATE_LOCATION"),
])
def test_exact_source_target_labels(source, target, expected):
    rows, summary = extract_match(fixture(source, target).lines, CATALOG)
    assert summary["decisions_total"] == summary["decisions_labeled"] == 1
    row = rows[0]
    validate_example(row)
    assert row["final_result"] == 1.0
    action = row["legal_actions"][row["chosen_action_index"]]
    assert action["type"] == expected
    assert row["legal_actions"][0]["type"] == "END_TURN"
    if target:
        assert action["target_side"] == "OPPONENT"
        assert action["target_card_id"] == "CS2_168"
        assert action["target_board_position"] == 1
    if source == 41:
        assert action["source_card_id"] == "CS2_231" and action["source_board_position"] == 1
    if source == 4:
        assert action["source_is_hero"] and action["source_health"] == 30


def test_end_turn_only_with_real_invalid_error():
    rows, summary = extract_match(fixture(only_end=True).lines, CATALOG)
    assert summary["decisions_labeled"] == 1
    assert rows[0]["chosen_action_index"] == 0
    assert rows[0]["legal_actions"] == [{"type": "END_TURN", "play_position": 0}]


@pytest.mark.parametrize("kwargs,reason", [
    ({"duplicate": True}, "AMBIGUOUS_SELECTION"),
    ({"supersede": True}, "OPTIONS_SUPERSEDED"),
    ({"sub": True}, "CHOICE_UNRESOLVED"),
    ({"position": 7}, "TARGET_UNRESOLVED"),
])
def test_never_guess_ambiguous_or_stale_selection(kwargs, reason):
    rows, summary = extract_match(fixture(**kwargs).lines, CATALOG)
    assert rows == []
    assert summary["decisions_total"] == summary["decisions_skipped"] == 1
    assert summary["skip_reasons"] == {reason: 1}


def test_hidden_identity_and_raw_handle_exclusion():
    rows, _ = extract_match(fixture(canaries=True).lines, CATALOG)
    serialized = json.dumps(rows)
    for canary in CANARIES:
        assert canary not in serialized
    assert "GameAccountId" not in serialized and "entityName" not in serialized
    for action in rows[0]["legal_actions"]:
        assert not any("handle" in key or "entity_id" in key for key in action)
    assert rows[0]["state"]["opponent_known_cards"] == []
    tampered = copy.deepcopy(rows[0])
    tampered["legal_actions"][0]["entity_id"] = 777
    with pytest.raises(ValueError):
        validate_example(tampered)
    tampered = copy.deepcopy(rows[0])
    tampered["state"]["opponent"]["hidden_deck"] = ["PRIVATE_CARD"]
    with pytest.raises(ValueError):
        validate_example(tampered)


def test_targets_are_entity_handles_not_target_ordinals():
    log = fixture(6, 50)
    log.lines = [line.replace("selectedTarget=50", "selectedTarget=1") for line in log.lines]
    rows, summary = extract_match(log.lines, CATALOG)
    assert not rows and summary["skip_reasons"] == {"TARGET_UNRESOLVED": 1}


def test_hand_power_that_is_actually_deck_action_is_not_a_play_label():
    log = fixture()
    log.lines = [line.replace("BlockType=PLAY Entity=", "BlockType=DECK_ACTION Entity=") for line in log.lines]
    rows, summary = extract_match(log.lines, CATALOG)
    assert rows == [] and summary["skip_reasons"] == {"UNSUPPORTED_DECISION_KIND": 1}


def test_public_actor_is_exact_and_names_are_irrelevant():
    log = fixture()
    renamed = [line.replace("entityName=X", "entityName=Другая карта") for line in log.lines]
    assert extract_match(renamed, CATALOG)[0] == extract_match(log.lines, CATALOG)[0]
    wrong = [line.replace(" id=6 ", " id=7 ") if "BLOCK_START" in line else line for line in log.lines]
    rows, summary = extract_match(wrong, CATALOG)
    assert rows == [] and summary["skip_reasons"] == {"UNSUPPORTED_DECISION_KIND": 1}


def test_import_and_audit_clis_have_private_safe_summaries(tmp_path):
    path, out = tmp_path / "fake.log", tmp_path / "out"
    path.write_text("\n".join(fixture(canaries=True).lines) + "\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    command = [sys.executable, str(ROOT / "scripts/import_policy_power_log.py"), str(path), "--output-dir", str(out)]
    first = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    assert first.returncode == 0 and json.loads(first.stdout)["decisions_labeled"] == 1
    duplicate = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    assert duplicate.returncode == 1 and json.loads(duplicate.stdout)["game_skip_reasons"] == {"DUPLICATE_MATCH": 1}
    audit = subprocess.run([sys.executable, str(ROOT / "scripts/audit_real_policy_dataset.py"), str(out)],
                           cwd=ROOT, env=env, capture_output=True, text=True)
    assert audit.returncode == 0 and json.loads(audit.stdout)["privacy_checks"] == "PASS"
    for result in (first, duplicate, audit):
        assert not result.stderr and all(canary not in result.stdout for canary in CANARIES)
        assert "GameAccountId" not in result.stdout and "entityName" not in result.stdout
    (out / "INVALIDATED.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="invalidated"):
        load_examples(out)


def test_invalid_duplicate_hand_variant_still_blocks_menu_semantics():
    log = fixture(duplicate=True)
    log.lines = [line.replace("error=NONE", "error=REQ_ENOUGH_MANA")
                 if "option 2 type=POWER" in line else line for line in log.lines]
    rows, summary = extract_match(log.lines, CATALOG)
    assert rows == [] and summary["skip_reasons"] == {"AMBIGUOUS_SELECTION": 1}


def test_unready_minion_power_is_not_assumed_to_be_attack():
    log = fixture(41, 50)
    start = next(i for i, line in enumerate(log.lines) if "DebugPrintOptions() - id=" in line)
    log.lines.insert(start, "D 20:00:00.0000000 GameState.DebugPrintPower() - "
                     "TAG_CHANGE Entity=41 tag=EXHAUSTED value=1")
    rows, summary = extract_match(log.lines, CATALOG)
    assert rows == [] and summary["skip_reasons"] == {"UNSUPPORTED_DECISION_KIND": 1}


def test_placement_expands_every_public_board_insertion_slot():
    log = fixture(6, position=3)
    start = next(i for i, text in enumerate(log.lines) if "DebugPrintOptions() - id=" in text)
    log.lines.insert(start, "D 20:00:00.0000000 GameState.DebugPrintPower() - "
                     "TAG_CHANGE Entity=6 tag=CARDTYPE value=MINION")
    rows, _ = extract_match(log.lines, CATALOG)
    assert rows[0]["legal_actions"][rows[0]["chosen_action_index"]]["play_position"] == 3
    assert [a["play_position"] for a in rows[0]["legal_actions"] if a["type"] == "PLAY_CARD"] == [1, 2, 3]
    features = encode_legal_actions(rows[0]["legal_actions"])
    assert len(set(features[:, ACTION_FEATURE_NAMES.index("play_position")])) == 4


def test_two_send_options_for_one_menu_invalidate_the_label():
    log = fixture()
    index = next(i for i, line in enumerate(log.lines) if "SendOption()" in line)
    log.lines.insert(index + 1, log.lines[index].replace("selectedOption=1", "selectedOption=0"))
    rows, summary = extract_match(log.lines, CATALOG)
    assert rows == [] and summary["skip_reasons"] == {"AMBIGUOUS_SELECTION": 1}


def test_schema_rejects_chosen_indices_outside_menu_and_private_action_strings():
    rows, _ = extract_match(fixture().lines, CATALOG)
    for index in (-1, len(rows[0]["legal_actions"]), True):
        row = copy.deepcopy(rows[0]); row["chosen_action_index"] = index
        with pytest.raises(ValueError):
            validate_example(row)
    row = copy.deepcopy(rows[0]); row["legal_actions"][1]["card_id"] = "Private#1234"
    with pytest.raises(ValueError):
        validate_example(row)


def test_schema_v3_migration_preserves_embeddings_and_zeroes_placement():
    policy = PolicyNetwork(card_count=2)
    state = {key: value.clone() for key, value in policy.state_dict().items()}
    old_names = list(ACTION_FEATURE_NAMES[:-1])
    placement_column = len(POLICY_STATE_FEATURE_NAMES) + len(old_names)
    weight = state["scorer.0.weight"]
    state["scorer.0.weight"] = torch.cat([weight[:, :placement_column], weight[:, placement_column+1:]], dim=1)
    payload = {"policy_state_dict": state, "policy_action_schema_version": 3,
               "state_feature_names": list(POLICY_STATE_FEATURE_NAMES), "action_feature_names": old_names,
               "card_vocabulary": {}}
    assert load_policy_weights(policy, payload)
    assert torch.count_nonzero(policy.scorer[0].weight[:, placement_column]) == 0
    assert torch.equal(policy.scorer[0].weight[:, placement_column+1:], weight[:, placement_column+1:])


def test_duplicate_import_rejected_and_value_destination_forbidden(tmp_path):
    rows, summary = extract_match(fixture().lines, CATALOG)
    save_match(rows, summary, tmp_path)
    before = (tmp_path / (summary["game_id"] + ".jsonl")).read_bytes()
    with pytest.raises(PolicyImportError, match="DUPLICATE_MATCH"):
        save_match(rows, summary, tmp_path)
    assert (tmp_path / (summary["game_id"] + ".jsonl")).read_bytes() == before
    with pytest.raises(PolicyImportError, match="VALUE_DATASET_DESTINATION"):
        save_match(rows, summary, tmp_path / "processed_real")
    summary = audit_dataset(tmp_path, CATALOG)
    assert summary["unique_matches"] == 1 and summary["privacy_checks"] == "PASS"


def test_split_loader_rejects_same_match_in_different_files(tmp_path):
    rows, summary = extract_match(fixture().lines, CATALOG)
    save_match(rows, summary, tmp_path)
    row = copy.deepcopy(rows[0]); row["decision_id"] = row["game_id"] + ":2"
    (tmp_path / "second.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate match"):
        load_examples(tmp_path)


def test_future_outcome_is_not_a_policy_input():
    rows, _ = extract_match(fixture().lines, CATALOG)
    other = copy.deepcopy(rows[0]); other["final_result"] = 0.0
    encoder = StateEncoder(CATALOG)
    before, after = encode_example(rows[0], encoder), encode_example(other, encoder)
    assert all(torch.equal(a, b) for a, b in zip(before, after))


def test_segmented_intake_requires_per_game_metadata_completion(tmp_path):
    a, b = fixture(seed=1), fixture(seed=2)
    path = tmp_path / "fake.log"
    path.write_text("\n".join(a.lines + b.lines) + "\n", encoding="utf-8")
    with pytest.raises(PolicyImportError, match="EXPECTED_ONE_MATCH"):
        import_log(path, tmp_path / "out", CATALOG)
    assert import_log(path, tmp_path / "out", CATALOG, segmented=True)["games_imported"] == 2
    invalid = fixture(seed=3)
    invalid.lines = [line for line in invalid.lines if "GameType=" not in line]
    with pytest.raises(PolicyImportError, match="MODE_INELIGIBLE"):
        extract_match(invalid.lines, CATALOG)
    with pytest.raises(PolicyImportError, match="INCOMPLETE"):
        extract_match(a.lines[:-1], CATALOG)


def test_whole_match_split_encoding_unknown_and_backward():
    rows = []
    for seed in range(5):
        examples, _ = extract_match(fixture(45, seed=seed).lines, CATALOG)
        rows.extend(examples)
        second = copy.deepcopy(examples[0])
        second["decision_id"] = second["game_id"] + ":2"
        rows.append(second)
    parts = split_matches(rows)
    ids = [{r["game_id"] for r in part} for part in parts.values()]
    assert all(ids) and not ids[0] & ids[1] and not ids[0] & ids[2] and not ids[1] & ids[2]
    encoder = StateEncoder(CATALOG)
    actions = rows[0]["legal_actions"]
    assert encode_action_card_ids(actions, encoder)[1] == 1  # shared UNK
    policy = PolicyNetwork(card_count=encoder.vocabulary.card_count)
    logits = policy(*encode_example(rows[0], encoder))
    loss = torch.nn.functional.cross_entropy(logits[None], torch.tensor([rows[0]["chosen_action_index"]]))
    loss.backward()
    assert np.isfinite(loss.item()) and policy.scorer[0].weight.grad is not None
    metrics = evaluate_held_out(policy, parts["test"], encoder, ids[0])
    assert 0 <= metrics["top1_accuracy"] <= 1 and 0 < metrics["mean_reciprocal_rank"] <= 1
    with pytest.raises(ValueError, match="held-out"):
        evaluate_held_out(policy, parts["train"], encoder, ids[0])
    with pytest.raises(ValueError, match="three whole"):
        split_matches(rows[:1])
