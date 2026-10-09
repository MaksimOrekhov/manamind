from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import model_first_2b_shortcut_challenge as challenge  # noqa: E402


def test_challenge_gold_is_unique_and_derived_from_combat_arithmetic():
    rows = challenge.generate_challenge()
    audit = challenge._audit_challenge_gold(rows)

    assert len(rows) == 240
    assert audit["unambiguous_scenarios"] == 240
    assert len(audit["gold_source_position_counts"]) > 1
    assert len(audit["gold_target_position_counts"]) > 1
    assert audit["gold_source_position_counts"].get(1, 0) < 240
    assert audit["kill_target_lose_attacker_actions"] > 0
    assert audit["targets_not_killable_in_one_attack"] > 0


def test_synthetic_card_base_metadata_is_unknown_and_current_stats_are_explicit():
    rows = challenge.generate_challenge()
    metadata = challenge._verify_metadata(rows)

    assert metadata["be_036_occurrences"] == 0
    for row in rows:
        for side in ("self_player", "opponent"):
            for entity in row["state"][side]["board"]:
                card = entity["card"]
                assert card["attack"] is None
                assert card["health"] is None
                assert card["mechanics"] == []
                assert entity["current_attack"] is not None
                assert entity["current_health"] is not None


def test_id_counterfactual_changes_only_identity_and_uses_real_known_metadata():
    row = challenge._challenge_case(17)
    known = challenge._remap_cards(row, known=True)
    unknown = challenge._remap_cards(row, known=False)

    for side in ("self_player", "opponent"):
        known_board = known["state"][side]["board"]
        unknown_board = unknown["state"][side]["board"]
        for known_entity, unknown_entity in zip(known_board, unknown_board, strict=True):
            assert known_entity["card"]["card_id"] == challenge.KNOWN_ID
            assert known_entity["card"]["attack"] == 6
            assert known_entity["card"]["health"] == 7
            assert known_entity["card"]["mechanics"] == []
            assert known_entity["current_attack"] == unknown_entity["current_attack"]
            assert known_entity["current_health"] == unknown_entity["current_health"]
            known_card = {k: v for k, v in known_entity["card"].items() if k != "card_id"}
            unknown_card = {k: v for k, v in unknown_entity["card"].items() if k != "card_id"}
            assert known_card == unknown_card
    def signature(action):
        return (action["source_board_position"], action["target_board_position"],
                action["source_attack"], action["source_health"],
                action["target_attack"], action["target_health"])
    assert {signature(a) for a in known["correct_actions"]} == {
        signature(a) for a in unknown["correct_actions"]}
    assert len(known["legal_actions"]) == len(unknown["legal_actions"])


def test_stat_pair_requires_the_model_to_switch_off_first_attacker():
    low, high = challenge._stat_pair(4)

    assert low["correct_actions"][0]["source_board_position"] == 1
    assert high["correct_actions"][0]["source_board_position"] == 2
    assert challenge._audit_challenge_gold([low, high])["unambiguous_scenarios"] == 2


def test_position_permutation_keeps_gold_entity_pair_but_moves_positions():
    original, permuted = challenge._permute_pair(4)

    original_gold = original["correct_actions"][0]
    permuted_gold = permuted["correct_actions"][0]
    assert original_gold["source_card_id"] == permuted_gold["source_card_id"]
    assert original_gold["target_card_id"] == permuted_gold["target_card_id"]
    source_count = len(original["state"]["self_player"]["board"])
    target_count = len(original["state"]["opponent"]["board"])
    assert permuted_gold["source_board_position"] == source_count + 1 - original_gold["source_board_position"]
    assert permuted_gold["target_board_position"] == target_count + 1 - original_gold["target_board_position"]


def test_corrective_examples_have_arithmetic_labels_and_disjoint_split_families():
    train = [challenge._corrective_case(i, "train") for i in range(300)]
    validation = [challenge._corrective_case(i, "validation") for i in range(100)]

    assert challenge._audit_challenge_gold(train + validation)["unambiguous_scenarios"] == 400
    assert not ({r["family_id"] for r in train} & {r["family_id"] for r in validation})
    assert not ({r["template_id"] for r in train} & {r["template_id"] for r in validation})
    assert challenge._verify_metadata(train + validation)["be_036_occurrences"] == 0
