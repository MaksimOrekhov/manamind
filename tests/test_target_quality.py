"""Independent expectations for diagnostic identity boundaries and representation gaps."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import torch

from manamind.cards.catalog import CardCatalog
from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.policy_v2 import encode_policy_v2
from manamind.research.target_quality import disagreement, sibling_key, source_key, summarize, target_key


def play(**extra):
    return {"type": "PLAY_CARD", "source_kind": "MINION", "source_card_id": "SAME",
            "hand_index": 0, "play_position": 1, "target_kind": "MINION",
            "target_side": "OPPONENT", "target_card_id": "COPY", "target_board_position": 1, **extra}


def test_copies_and_placement_are_separate_from_target():
    a = play()
    assert disagreement(a, play(hand_index=1)) == "different_source"
    assert disagreement(a, play(play_position=2)) == "same_source_same_target_other_fields"
    assert disagreement(a, play(target_board_position=2)) == "target_only"
    assert disagreement(a, play(play_position=2, target_board_position=2)) == "target_and_other_fields"
    assert sibling_key(a) != sibling_key(play(play_position=2))
    assert source_key(a) == source_key(play(play_position=2))


@pytest.mark.parametrize("kind", ["ATTACK", "ACTIVATE_LOCATION"])
def test_board_source_copy_is_not_card_id(kind):
    a = {"type": kind, "source_kind": "MINION", "source_card_id": "COPY", "source_board_position": 1}
    assert source_key(a) != source_key(dict(a, source_board_position=2))


def test_target_copy_side_and_shared_position():
    a = play()
    assert target_key(a) != target_key(play(target_side="SELF"))
    assert target_key(a) != target_key(play(target_board_position=2))
    assert target_key(a) != target_key(play(target_kind="LOCATION"))
    assert target_key(a) != target_key({"type": "END_TURN", "play_position": 0})
    # A hero has one entity per side; its cosmetic identity is not another target.
    hero = play(target_kind="HERO", target_board_position=-1)
    assert target_key(hero) == target_key(dict(hero, target_card_id="ANOTHER_SKIN"))


def test_siblings_keep_every_nontarget_attribute():
    a = play(card_cost=3)
    assert sibling_key(a) == sibling_key(play(card_cost=3, target_health=9))
    assert sibling_key(a) != sibling_key(play(card_cost=0))
    assert sibling_key(a) != sibling_key(play(card_cost=3, source_health=4))


def test_summary_distinguishes_conditional_target_from_global_source():
    a, b = play(), play(target_board_position=2)
    end = {"type": "END_TURN", "play_position": 0}
    rows = [{"decision_id": "one", "legal_actions": [a, b, end], "chosen_action_index": 1},
            {"decision_id": "two", "legal_actions": [a, b, end], "chosen_action_index": 1},
            {"decision_id": "three", "legal_actions": [b, end], "chosen_action_index": 0}]
    before = deepcopy(rows)
    result = summarize(rows, {"one": [0, 1, 2], "two": [2, 1, 0], "three": [0, 1]})
    assert result["top1"]["same_source"] == 2
    assert result["top1"]["target_only"] == 1
    assert result["top1"]["different_source"] == 1
    assert result["top1"]["exact"] == 1
    assert result["top1"]["same_source_multi_target"] == 1
    assert result["given_player_source_and_slot"] == {
        "multi_target_source_decisions": 2, "target_match": 1, "exact_match": 1,
        "uniform_target_match_expected": 1.0}
    assert rows == before


def scene():
    card = CardFeatures("UNKNOWN_SPELL", card_type="SPELL")
    state = GameState(4, "SELF", PlayerObservation(30, hero_max_health=30, hand_size=1),
                      PlayerObservation(30, hero_max_health=30), self_hand=(card,))
    action = {"type": "PLAY_CARD", "source_card_id": card.card_id, "source_kind": "SPELL",
              "hand_index": 0, "play_position": 0, "target_kind": "HERO", "target_side": "SELF",
              "target_health": 30, "target_attack": 0, "target_is_self": True, "target_is_hero": True}
    encoder = StateEncoder(CardCatalog.from_json(Path(__file__).parents[1] / "data/cards/standard_current_enUS.json"))
    return state, [action], encoder


@pytest.mark.parametrize("field,value", [("hero_max_health", 40), ("healing_bonus", 7)])
def test_policy_cannot_distinguish_omitted_healing_facts(field, value):
    state, actions, encoder = scene()
    altered = replace(state, self_player=replace(state.self_player, **{field: value}))
    assert altered != state
    assert all(torch.equal(a, b) for a, b in zip(encode_policy_v2(state, actions, encoder),
                                               encode_policy_v2(altered, actions, encoder)))


@pytest.mark.parametrize("flag", ["divine_shield", "poisonous", "reborn", "lifesteal", "immune"])
def test_combat_counterexamples_change_encoding_despite_identical_attack_health(flag):
    state, actions, encoder = scene()
    minion = BoardEntity(CardFeatures("UNKNOWN_TARGET", card_type="MINION"), 3, 3, 3, 1)
    state = replace(state, opponent=replace(state.opponent, board=(minion,)))
    altered = replace(state, opponent=replace(state.opponent, board=(replace(minion, **{flag: True}),)))
    assert state.opponent.board[0].current_health == altered.opponent.board[0].current_health == 3
    assert state.opponent.board[0].current_attack == altered.opponent.board[0].current_attack == 3
    assert not torch.equal(encode_policy_v2(state, actions, encoder)[2], encode_policy_v2(altered, actions, encoder)[2])


def test_secret_counterexample_keeps_targets_but_changes_visible_context():
    state, actions, encoder = scene()
    altered = replace(state, opponent=replace(state.opponent, secret_count=1))
    assert not torch.equal(encode_policy_v2(state, actions, encoder)[0], encode_policy_v2(altered, actions, encoder)[0])
    assert torch.equal(encode_policy_v2(state, actions, encoder)[3], encode_policy_v2(altered, actions, encoder)[3])
