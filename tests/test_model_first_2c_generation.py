from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_model_first_2c as generator  # noqa: E402
from evaluate_policy_baseline import load_scenarios  # noqa: E402


def test_locked_split_sizes_templates_and_exact_content_are_separate():
    groups, _ = generator.generate(seed=20261009)
    audit = generator._validate(groups)

    assert audit["counts"] == {"train": 2800, "validation": 500, "test": 400}
    assert audit["templates"] == {"train": 6, "validation": 3, "test": 9}
    assert audit["content_fingerprints_unique"] == 3700
    train_families = {row["family_id"] for row in groups["train"]}
    validation_families = {row["family_id"] for row in groups["validation"]}
    test_families = {row["family_id"] for row in groups["test"]}
    assert not train_families & validation_families
    assert not train_families & test_families
    assert not validation_families & test_families


def test_synthetic_entities_use_unknown_base_and_explicit_current_stats():
    row = generator._case(5, "train", "train_trade_sparse", 5, mode="safe")
    for side in ("self_player", "opponent"):
        for entity in row["state"][side]["board"]:
            assert entity["card"]["attack"] is None
            assert entity["card"]["health"] is None
            assert entity["card"]["mechanics"] == []
            assert entity["current_attack"] is not None
            assert entity["current_health"] is not None
            assert entity["card"]["card_id"] != "BE_036"


def test_local_gold_rules_cover_safe_trade_end_turn_and_lethal():
    safe = generator._case(10, "train", "train_trade_sparse", 10, mode="safe")
    no_gain = generator._case(11, "train", "train_no_gain", 11, mode="no_gain")
    lethal = generator._case(12, "train", "train_face_finish", 12, mode="lethal")

    assert safe["category"] == "favorable_trade"
    assert safe["correct_actions"]
    assert all(action["type"] == "ATTACK" and action["target_kind"] == "MINION"
               and action["source_attack"] >= action["target_health"]
               and action["target_attack"] < action["source_health"]
               for action in safe["correct_actions"])
    assert no_gain["correct_actions"] == [{"play_position": 0, "type": "END_TURN"}]
    assert lethal["category"] == "lethal"
    assert all(action["target_kind"] == "HERO"
               and action["source_attack"] >= action["target_health"]
               for action in lethal["correct_actions"])


def test_counterfactual_factors_hold_unrelated_state_constant():
    low, high = generator._stat_pair(7)
    assert low["correct_actions"][0]["source_card_id"] != high["correct_actions"][0]["source_card_id"]
    original, permuted = generator._permute_pair(7)
    original_gold = {action["source_card_id"] for action in original["correct_actions"]}
    permuted_gold = {action["source_card_id"] for action in permuted["correct_actions"]}
    assert original_gold == permuted_gold
    small, large = generator._board_pair(7)
    assert small["correct_actions"][0]["source_card_id"] == large["correct_actions"][0]["source_card_id"]
    known, unknown = generator._id_pair(7)
    known_entities = known["state"]["self_player"]["board"] + known["state"]["opponent"]["board"]
    unknown_entities = unknown["state"]["self_player"]["board"] + unknown["state"]["opponent"]["board"]
    for left, right in zip(known_entities, unknown_entities, strict=True):
        assert {k: v for k, v in left["card"].items() if k != "card_id"} == {
            k: v for k, v in right["card"].items() if k != "card_id"}
        assert left["current_attack"] == right["current_attack"]
        assert left["current_health"] == right["current_health"]
    assert [generator._action_semantic_signature(a) for a in known["correct_actions"]] == [
        generator._action_semantic_signature(a) for a in unknown["correct_actions"]]


def test_generated_jsonl_uses_strict_scenario_schema(tmp_path):
    groups, _ = generator.generate(seed=20261009)
    generator._validate(groups)
    path = tmp_path / "test.jsonl"
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                 for row in groups["test"]), encoding="utf-8")

    loaded = load_scenarios(path)
    assert len(loaded) == 400
    assert {row["category"] for row in loaded} == {"favorable_trade", "no_proven_gain", "lethal"}
