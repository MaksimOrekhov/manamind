"""Independent denominators for exact source/target agreement and game uncertainty."""
import math

import pytest

from manamind.training.retrain_metrics import agreement, grouped_metrics, paired_bootstrap, source_key, target_key


def examples():
    own = {"type": "PLAY_CARD", "hand_index": 0, "card_id": "A", "target_kind": "MINION",
           "target_board_position": 1, "target_side": "SELF", "target_card_id": "B"}
    enemy = dict(own, target_side="OPPONENT")
    duplicate_card = dict(own, hand_index=1)
    end = {"type": "END_TURN"}
    return [{"game_id": game, "chosen_action_index": chosen, "legal_actions": [own, enemy, duplicate_card, end],
             "state": {"self_player": {"player_class": "PRIEST"}}}
            for game, chosen in (("game-a", 0), ("game-a", 3), ("game-b", 2))]


def records(indices, ranks):
    return [{"prediction_index": index, "rank": rank, "loss": math.log(4), "menu_size": 4,
             "unknown_hand": False, "chosen_unknown": False} for index, rank in zip(indices, ranks)]


def test_source_instances_and_target_sides_are_distinct():
    menu = examples()[0]["legal_actions"]
    assert source_key(menu[0]) != source_key(menu[2])  # two copies in hand are different sources
    assert target_key(menu[0]) != target_key(menu[1])  # same ID/slot on different sides
    diagnostics = agreement(examples(), records([1, 3, 0], [2, 1, 2]))
    assert diagnostics["action_type"]["correct"] == 3
    assert diagnostics["source"] == {"matches": 2, "decisions": 2, "correct": 1, "accuracy": 0.5}
    assert diagnostics["target"]["correct"] == 1
    assert diagnostics["target_given_correct_type_source"]["decisions"] == 1
    assert diagnostics["target_given_correct_type_source"]["correct"] == 0
    assert diagnostics["target_side"]["accuracy"] == 0.5


def test_missing_target_is_an_error_with_a_separate_side_denominator():
    diagnostics = agreement(examples(), records([3, 3, 2], [4, 1, 1]))
    assert diagnostics["target"]["accuracy"] == 0.5
    assert diagnostics["target_side"]["decisions"] == 1
    assert diagnostics["missing_target_predictions"] == 1
    assert diagnostics["false_end_turn"]["decisions"] == 1
    groups = grouped_metrics(examples(), records([3, 3, 2], [4, 1, 1]))
    assert groups["kind"]["PLAY_CARD"]["matches"] == 2
    assert groups["kind"]["PLAY_CARD"]["decisions"] == 2


def test_bootstrap_samples_games_and_preserves_paired_decision_weights():
    rows = examples()
    old = records([0, 3, 2], [1, 1, 1])
    new = records([1, 0, 0], [2, 2, 2])
    result = paired_bootstrap(rows, old, new, draws=100)
    assert result["matches"] == 2 and result["decisions"] == 3
    assert result["top1_delta"] == -1
    assert result["top1_delta_ci95"] == [-1, -1]
    assert result["cross_entropy_delta_ci95"] == [0, 0]
    assert result["worsened_games"] == 2
    assert result == paired_bootstrap(rows, old, new, draws=100)
    with pytest.raises(ValueError):
        paired_bootstrap(rows, old[:1], new)
