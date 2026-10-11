"""Scoring a forecast against the next observation, on hand-built logged pairs."""

from __future__ import annotations

from dataclasses import replace

from manamind.outcome import ObservedContext, Status, TextSource
from manamind.outcome import scenario as sc
from manamind.outcome.verify import (
    LoggedDecision, observe, score_pair, successor_pairs, summarise_results,
)

TRUSTED = ObservedContext(trust_spell_damage=True)
TEXTS = TextSource.from_records([
    {"id": "T_HOLD", "type": "SPELL", "mechanics": [], "text": "<b>Prepare</b>\nGive a minion +5/+5 and <b>Lifesteal</b>."},
    {"id": "T_NOVA", "type": "SPELL", "mechanics": [], "text": "Deal $2 damage to all minions."},
    *({"id": card, "type": "MINION", "mechanics": [], "text": ""} for card in ("A", "B", "C", "TOKEN"))])


def _decision(state, action, number=1, game="g"):
    return LoggedDecision(game, number, f"{game}:{number}", state, action, (action,))


def _hold_pair():
    state = sc.position(self_side=sc.side(mana=5), opponent=sc.side(board=(sc.minion("A", 6, 6, 1),)),
                        hand=(sc.hand_card("T_HOLD", "SPELL", 5),))
    action = sc.play("T_HOLD", 0, "SPELL", 5, sc.target_minion("OPPONENT", 1, "A"))
    return state, action


def _truth(state, **overrides):
    """A next observation written by hand from the rules, independent of the forecaster."""
    return replace(state, self_player=replace(state.self_player, available_mana=0, hand_size=0),
                   self_hand=(), self_hand_known_count=0,
                   opponent=replace(state.opponent, board=(sc.minion("A", 11, 11, 1, lifesteal=True),)),
                   **overrides)


def test_correct_forecast_is_confirmed_field_by_field():
    state, action = _hold_pair()
    result = score_pair(_decision(state, action), _decision(_truth(state), action, 2), TEXTS)
    assert result.verdict == "CONFIRMED", (result.contradicted, result.missed)
    for path in ("OPPONENT.board[0:A].current_attack", "OPPONENT.board[0:A].current_health",
                 "OPPONENT.board[0:A].max_health", "OPPONENT.board[0:A].lifesteal", "SELF.mana"):
        assert path in result.confirmed, (path, result.confirmed)
    assert result.confirmed["OPPONENT.board[0:A].current_attack"] == 11


def test_wrong_observation_is_a_contradiction_and_an_extra_change_is_missed():
    state, action = _hold_pair()
    truth = _truth(state)
    wrong = replace(truth, opponent=replace(truth.opponent, board=(sc.minion("A", 11, 9, 1, lifesteal=True),)))
    result = score_pair(_decision(state, action), _decision(wrong, action, 2), TEXTS)
    assert result.verdict == "CONTRADICTED"
    assert result.contradicted["OPPONENT.board[0:A].current_health"] == (11, 9)
    extra = replace(truth, opponent=replace(truth.opponent, hero_health=25))
    result = score_pair(_decision(state, action), _decision(extra, action, 2), TEXTS)
    assert result.missed == {"OPPONENT.hero.health": (30, 25)}


def test_unobserved_values_in_the_next_state_are_neither_right_nor_wrong():
    state, action = _hold_pair()
    state = replace(state, self_player=replace(state.self_player, hero_power_ready=True))
    truth = _truth(state)
    truth = replace(truth, self_player=replace(truth.self_player, hero_power_ready=None))
    result = score_pair(_decision(state, action), _decision(truth, action, 2), TEXTS)
    assert "SELF.hero.power_ready" not in result.missed


def test_a_death_does_not_cascade_into_every_later_index():
    state = sc.position(self_side=sc.side(mana=5), opponent=sc.side(board=(
        sc.minion("A", 1, 2, 1), sc.minion("B", 3, 3, 2), sc.minion("C", 4, 4, 3))),
                        hand=(sc.hand_card("T_NOVA", "SPELL", 2),))
    action = sc.play("T_NOVA", 0, "SPELL", 2)
    truth = replace(state, self_player=replace(state.self_player, available_mana=3, hand_size=0),
                    self_hand=(), self_hand_known_count=0,
                    opponent=replace(state.opponent, board=(sc.minion("B", 3, 1, 1, max_health=3),
                                                            sc.minion("C", 4, 2, 2, max_health=4))))
    result = score_pair(_decision(state, action), _decision(truth, action, 2), TEXTS, TRUSTED)
    assert result.verdict == "CONFIRMED", (result.contradicted, result.missed)
    assert result.confirmed["OPPONENT.board[0:A].gone"] is True
    assert result.confirmed["OPPONENT.board[1:B].current_health"] == 1


def test_an_unpredicted_new_entity_is_missed_and_a_predicted_one_that_is_absent_is_contradicted():
    state = sc.position(self_side=sc.side(mana=5), opponent=sc.side(),
                        hand=(sc.hand_card("A", "MINION", 1, attack=1, health=1),))
    action = sc.play("A", 0, "MINION", 1, play_position=1)
    absent = replace(state, self_player=replace(state.self_player, available_mana=4, hand_size=0),
                     self_hand=(), self_hand_known_count=0)
    result = score_pair(_decision(state, action), _decision(absent, action, 2), TEXTS)
    assert result.contradicted["SELF.board.new[A].present"] == (True, False)
    token = replace(absent, opponent=replace(absent.opponent, board=(sc.minion("TOKEN", 1, 1, 1),)))
    result = score_pair(_decision(state, sc.end_turn()), _decision(token, action, 2), TEXTS)
    assert result.missed["OPPONENT.board.new[TOKEN].present"] == (False, True)


def test_successor_pairs_need_adjacent_numbers_one_self_turn_and_no_end_turn():
    state, action = _hold_pair()
    later_turn = replace(state, turn_number=state.turn_number + 2)
    games = {"g": [_decision(state, action, 1), _decision(state, action, 2), _decision(state, action, 4),
                   _decision(later_turn, action, 5), _decision(later_turn, sc.end_turn(), 6),
                   _decision(state, action, 7)]}
    pairs = [(a.number, b.number) for a, b in successor_pairs(games)]
    # 2->4 skips an unlabeled decision, 4->5 changes turns, 6->7 starts from END_TURN
    assert pairs == [(1, 2), (5, 6)]


def test_summary_counts_by_status_and_verdict():
    state, action = _hold_pair()
    good = score_pair(_decision(state, action), _decision(_truth(state), action, 2), TEXTS)
    unsupported = score_pair(_decision(state, {"type": "TRADE_CARD"}), _decision(state, action, 2), TEXTS)
    summary = summarise_results([good, unsupported])
    assert summary["pairs"] == 2 and summary["status"]["UNSUPPORTED"] == 1
    assert unsupported.status is Status.UNSUPPORTED and unsupported.verdict == "UNSUPPORTED"
    assert observe(state)["SELF.hand"] == [{"card_id": "T_HOLD"}]
