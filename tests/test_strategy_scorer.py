# ruff: noqa: F811
"""STRATEGIC-SCORER-1: an independent, explainable ranking that never touches the Policy path."""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import outcome_shadow_replay as replay  # noqa: E402
import run_manamind  # noqa: E402
from live_fixtures import CANARIES, LiveLog  # noqa: E402
from test_live_recommendation import recommender  # noqa: E402,F401
from test_outcome_shadow import record_log, two_decision_log  # noqa: E402

from manamind.live.prediction_journal import PredictionJournal  # noqa: E402
from manamind.outcome import ObservedContext, TextSource  # noqa: E402
from manamind.outcome import scenario as sc  # noqa: E402
from manamind.outcome.live_shadow import load_texts  # noqa: E402
from manamind.strategy import score_menu  # noqa: E402
from manamind.strategy import scorer as scorer_module  # noqa: E402
from manamind.strategy.live_shadow import STRATEGY_SCHEMA, StrategyFailed, StrategyShadow  # noqa: E402
from manamind.strategy.value import (  # noqa: E402
    PARAMS, face_damage_through_taunts, health_value, mana_potential, minion_value, position_value,
)

TEXTS = TextSource.from_records([
    {"id": "T_KILL", "type": "SPELL", "mechanics": [], "text": "Destroy a minion. Restore #3 Health to your hero."},
    {"id": "T_BOLT", "type": "SPELL", "mechanics": [], "text": "Deal $3 damage."},
    {"id": "T_ODD", "type": "SPELL", "mechanics": [], "text": "Summon a plant that dreams of electric sheep."},
    {"id": "T_WALL", "type": "MINION", "mechanics": ["TAUNT"], "text": "<b>Taunt</b>"},
    {"id": "T_BEAR", "type": "MINION", "mechanics": [], "text": ""},
    *({"id": card, "type": "MINION", "mechanics": [], "text": ""} for card in ("A", "B", "C", "D", "E"))])
KNOWN = ObservedContext(trust_spell_damage=True, spell_healing_doubled=False, healing_does_damage=False, healing_bonus=0,
                        self_hero_divine_shield=False, opponent_hero_divine_shield=False)


def ranked(state, actions, texts=TEXTS, context=KNOWN):
    result = score_menu(state, actions, texts, context)
    return result, [result.actions[i] for i in result.ranking]


def first(state, actions, **kwargs):
    return ranked(state, actions, **kwargs)[1][0].index


# ----- 1. ordinary attacks and simple trades ----------------------------------------------------------------------


def test_attack_arithmetic_is_the_forecasters_and_values_add_up():
    state = sc.position(self_side=sc.side(board=(sc.minion("B", 4, 4, 1, can_attack=True),)),
                        opponent=sc.side(board=(sc.minion("A", 3, 3, 1),)))
    actions = [sc.end_turn(), sc.attack(1, "B", sc.target_minion("OPPONENT", 1, "A"))]
    result, _ = ranked(state, actions)
    trade = result.actions[1]
    # the enemy 3/3 dies, our 4/4 becomes 4/1: board terms change by +6 and -3 exactly
    assert trade.confirmed == pytest.approx(6.0 - 3.0)
    assert trade.score == pytest.approx(trade.confirmed + trade.risk + trade.plan + trade.unknown_estimate)
    assert any(code == "DIES" and "OPPONENT" in detail for code, _, detail in trade.factors)


def test_a_good_trade_beats_the_face_and_a_bad_trade_does_not():
    attacker = sc.minion("B", 4, 4, 1, can_attack=True)
    good = sc.position(self_side=sc.side(board=(attacker,)), opponent=sc.side(board=(sc.minion("A", 3, 3, 1),)))
    bad = sc.position(self_side=sc.side(board=(attacker,)), opponent=sc.side(board=(sc.minion("A", 6, 6, 1),)))
    actions = [sc.end_turn(), sc.attack(1, "B", sc.target_hero("OPPONENT")),
               sc.attack(1, "B", sc.target_minion("OPPONENT", 1, "A"))]
    assert first(good, actions) == 2               # kill a 3/3 and survive
    assert first(bad, actions) == 1                # do not suicide into a 6/6; hit the hero instead


# ----- 2. removing a strong threat ----------------------------------------------------------------------------------


def _threat_position(self_health=22):
    return sc.position(
        self_side=sc.side(hero_health=self_health, mana=6, board=(sc.minion("B", 1, 3, 1), sc.minion("C", 2, 3, 2))),
        opponent=sc.side(board=(sc.minion("A", 4, 5, 1), sc.minion("D", 6, 7, 2)), hand_size=4),
        hand=(sc.hand_card("T_KILL", "SPELL", 4), sc.hand_card("T_WALL", "MINION", 3, attack=3, health=6,
                                                                   mechanics=("TAUNT",))))


def test_destroying_the_biggest_threat_is_preferred_and_explained():
    state = _threat_position()
    actions = [sc.end_turn(), sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 2, "D")),
               sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 1, "A")),
               sc.play("T_WALL", 1, "MINION", 3, play_position=3)]
    result, order = ranked(state, actions)
    assert order[0].index == 1                     # the 6/7, not the 4/5
    kill = result.actions[1]
    codes = {code for code, _, _ in kill.factors}
    assert {"ENEMY_BOARD", "INCOMING_THREAT"} <= codes and kill.unknown_estimate == 0
    assert result.actions[0].score < min(a.score for a in result.actions[1:])   # passing wastes 6 Mana


def test_the_taunt_wins_when_the_threat_is_lethal_otherwise_and_removal_is_out_of_reach():
    # 5 Health left; the enemy 4/5 + 6/7 would kill next turn unless something blocks; only the Taunt is affordable
    state = _threat_position(self_health=5)
    state = replace(state, self_player=replace(state.self_player, available_mana=3))
    actions = [sc.end_turn(), sc.play("T_WALL", 1, "MINION", 3, play_position=3),
               sc.attack(1, "B", sc.target_hero("OPPONENT"))]
    state = replace(state, self_player=replace(state.self_player, board=(
        replace(state.self_player.board[0], can_attack=True), state.self_player.board[1])))
    assert first(state, actions) == 1


# ----- 3. developing can beat an immediate attack ------------------------------------------------------------------


def test_developing_a_taunt_beats_a_small_face_hit_when_threatened():
    state = sc.position(
        self_side=sc.side(hero_health=9, mana=3, board=(sc.minion("B", 1, 1, 1, can_attack=True),)),
        opponent=sc.side(hero_health=30, board=(sc.minion("A", 5, 5, 1), sc.minion("C", 4, 4, 2))),
        hand=(sc.hand_card("T_WALL", "MINION", 3, attack=2, health=6, mechanics=("TAUNT",)),))
    actions = [sc.end_turn(), sc.attack(1, "B", sc.target_hero("OPPONENT")),
               sc.play("T_WALL", 0, "MINION", 3, play_position=2)]
    assert first(state, actions) == 2


def test_but_lethal_on_board_is_taken_before_anything_else():
    state = sc.position(
        self_side=sc.side(hero_health=9, mana=3, board=(sc.minion("B", 3, 1, 1, can_attack=True),)),
        opponent=sc.side(hero_health=3, board=(sc.minion("A", 5, 5, 1),)),
        hand=(sc.hand_card("T_WALL", "MINION", 3, attack=2, health=6, mechanics=("TAUNT",)),))
    actions = [sc.end_turn(), sc.play("T_WALL", 0, "MINION", 3, play_position=2),
               sc.attack(1, "B", sc.target_hero("OPPONENT"))]
    result, order = ranked(state, actions)
    assert order[0].index == 2 and any(code == "LETHAL" for code, _, _ in order[0].factors)


# ----- 4. keeping a card can beat a small immediate gain -----------------------------------------------------------


def test_hard_removal_is_kept_rather_than_spent_on_a_one_one():
    small = sc.position(self_side=sc.side(mana=4), opponent=sc.side(board=(sc.minion("A", 1, 1, 1),)),
                        hand=(sc.hand_card("T_KILL", "SPELL", 4),))
    big = sc.position(self_side=sc.side(mana=4), opponent=sc.side(board=(sc.minion("A", 7, 7, 1),)),
                      hand=(sc.hand_card("T_KILL", "SPELL", 4),))
    actions = [sc.end_turn(), sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 1, "A"))]
    assert first(small, actions) == 0              # same action, wrong context: keep the card
    assert first(big, actions) == 1


def test_end_turn_wins_when_every_action_hurts():
    state = sc.position(self_side=sc.side(mana=0, board=(sc.minion("B", 1, 1, 1, can_attack=True),)),
                        opponent=sc.side(board=(sc.minion("A", 5, 5, 1, taunt=True),)))
    actions = [sc.end_turn(), sc.attack(1, "B", sc.target_minion("OPPONENT", 1, "A"))]
    assert first(state, actions) == 0


# ----- 5. incomplete coverage ---------------------------------------------------------------------------------------


def test_an_unreadable_effect_is_estimated_not_treated_as_nothing_and_marked():
    state = sc.position(self_side=sc.side(mana=5), opponent=sc.side(), hand=(sc.hand_card("T_ODD", "SPELL", 3),))
    actions = [sc.end_turn(), sc.play("T_ODD", 0, "SPELL", 3)]
    result, _ = ranked(state, actions)
    odd = result.actions[1]
    assert odd.status == "PARTIAL" and odd.unknown_estimate == pytest.approx(PARAMS.card_base + 3 * PARAMS.card_per_mana)
    assert odd.uncertainty.level == "HIGH" and "OWN_TEXT_UNPARSED" in odd.uncertainty.tags
    assert any(code == "UNREAD_EFFECT_ESTIMATE" for code, _, _ in odd.factors)
    assert odd.score > odd.score - odd.unknown_estimate      # without the estimate it would look like a pure loss


def test_an_action_the_forecaster_refuses_is_scored_from_bookkeeping_and_flagged():
    weapon = replace(sc.hand_card("W", "WEAPON", 2), attack=3, durability=2)
    state = sc.position(self_side=sc.side(mana=3), opponent=sc.side(), hand=(weapon,))
    actions = [sc.end_turn(), sc.play("W", 0, "WEAPON", 2)]
    result, _ = ranked(state, actions)
    row = result.actions[1]
    assert row.status == "UNSUPPORTED" and row.uncertainty.level == "HIGH"
    assert any(tag.startswith("NOT_FORECAST") for tag in row.uncertainty.tags) and row.unknown_estimate > 0


def test_a_bounded_heal_counts_only_its_guaranteed_part():
    state = _threat_position()
    actions = [sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 1, "A"))]
    known = score_menu(state, actions, TEXTS, KNOWN).actions[0]
    unknown = score_menu(state, actions, TEXTS, ObservedContext()).actions[0]   # healing doubling not observed
    assert known.confirmed == pytest.approx(unknown.confirmed)
    assert unknown.uncertainty.magnitude > known.uncertainty.magnitude


# ----- 6. hidden information ----------------------------------------------------------------------------------------


def test_the_ranking_ignores_everything_but_visible_counts_on_the_opponent_side():
    state = _threat_position()
    actions = [sc.end_turn(), sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 2, "D"))]
    revealed = replace(state, opponent=replace(state.opponent, deck_size=3, fatigue=2),
                       opponent_known_cards=(sc.hand_card("T_BOLT", "SPELL", 1),))
    a = [x.score for x in score_menu(state, actions, TEXTS, KNOWN).actions]
    b = [x.score for x in score_menu(revealed, actions, TEXTS, KNOWN).actions]
    assert a == b


def test_the_package_reads_no_hidden_fields_and_no_policy():
    for path in (ROOT / "src/manamind/strategy").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("opponent_known_cards", "deck_size", "logits", "policy_rank", "chosen_action",
                          "final_result", "torch"):
            assert forbidden not in text, (path.name, forbidden)


# ----- 7. determinism -------------------------------------------------------------------------------------------------


def test_ranking_is_deterministic_and_independent_of_menu_order():
    state = _threat_position()
    actions = [sc.end_turn(), sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 2, "D")),
               sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 1, "A")),
               sc.play("T_WALL", 1, "MINION", 3, play_position=1), sc.play("T_WALL", 1, "MINION", 3, play_position=3)]
    one = score_menu(state, actions, TEXTS, KNOWN)
    two = score_menu(state, actions, TEXTS, KNOWN)
    assert [a.to_dict() for a in one.actions] == [a.to_dict() for a in two.actions] and one.ranking == two.ranking
    flipped = score_menu(state, list(reversed(actions)), TEXTS, KNOWN)
    key = lambda a: json.dumps(a.action, sort_keys=True)   # noqa: E731
    assert {key(a): a.score for a in one.actions} == {key(a): a.score for a in flipped.actions}
    # the two Taunt placements tie and are reported as one group, represented by the lower menu index
    wall = next(g for g in one.groups if 3 in g)
    assert wall == (3, 4)


def test_budget_exhaustion_is_visible_and_still_ranks_every_action():
    state = _threat_position()
    actions = [sc.end_turn(), sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 2, "D"))]
    ticks = iter(range(0, 10**12, 400_000_000))
    result = score_menu(state, actions, TEXTS, KNOWN, budget_ms=100, clock=lambda: next(ticks))
    assert result.computed < len(actions) and len(result.ranking) == len(actions)
    assert all(a.uncertainty.level == "HIGH" for a in result.actions if a.status == "NOT_COMPUTED")


def test_one_failing_forecast_costs_only_its_action(monkeypatch):
    state = _threat_position()
    actions = [sc.end_turn(), sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 2, "D"))]
    original = scorer_module.forecast_action

    def flaky(state_, action, texts, context):
        if action["type"] == "END_TURN":
            raise RuntimeError("private text")
        return original(state_, action, texts, context)

    monkeypatch.setattr(scorer_module, "forecast_action", flaky)
    result = score_menu(state, actions, TEXTS, KNOWN)
    assert result.actions[0].status == "ERROR" and result.actions[1].status != "ERROR"
    assert "private" not in json.dumps([a.to_dict() for a in result.actions])


# ----- value pieces ---------------------------------------------------------------------------------------------------


def test_value_pieces_behave_as_documented():
    assert health_value(5) - health_value(4) > health_value(25) - health_value(24) > 0      # low Health is dearer
    shielded = sc.minion("A", 3, 3, 1, divine_shield=True)
    assert minion_value(shielded) == pytest.approx(3 + 3 + 3)
    wall = sc.minion("W", 1, 4, 1, taunt=True)
    defender = sc.side(board=(wall,))
    assert face_damage_through_taunts([5, 2], defender) == 2            # the 5 breaks the Taunt, the 2 goes face
    assert face_damage_through_taunts([2, 1, 1], defender) == 0         # all needed to clear 4 Health
    rich = sc.position(self_side=sc.side(mana=3), opponent=sc.side(),
                       hand=(sc.hand_card("T_BEAR", "MINION", 2, attack=3, health=2),
                             sc.hand_card("T_BOLT", "SPELL", 3)))
    # the best one of them fits; both together do not
    assert mana_potential(rich, TEXTS) == pytest.approx(0.5 * max(5.0, 7.0))
    closed = position_value(rich, TEXTS, turn_open=False)
    assert closed.get("mana_potential") == 0 and position_value(rich, TEXTS, turn_open=True).get("mana_potential") > 0


# ----- 8. LIVE shadow: zero effect on the Policy ---------------------------------------------------------------------


@pytest.fixture
def texts():
    return load_texts(ROOT)


def test_the_strategy_shadow_changes_nothing_the_player_or_the_policy_journal_sees(tmp_path, recommender, texts):
    policy, _ = recommender
    log = two_decision_log()
    split = next(i for i, line in enumerate(log.lines) if "SendOption" in line)
    directory = record_log(tmp_path, log.lines, pause_at=split)
    plain = replay.run_runtime(directory, policy, texts, tmp_path / "off", shadow=False)
    shadowed = replay.run_runtime(directory, policy, texts, tmp_path / "on", shadow=False, strategy=StrategyShadow(texts))
    comparison = replay.compare_runs(directory, plain, shadowed)
    assert all(v for k, v in comparison.items() if isinstance(v, bool)), comparison
    assert plain.emitted == shadowed.emitted and plain.events == shadowed.events and plain.journal == shadowed.journal
    assert not plain.strategy_rows
    rows = [r for r in shadowed.strategy_rows if r["event"] == "STRATEGY_SHADOW"]
    assert len(rows) == shadowed.scored >= 1
    recommendations = [r for r in shadowed.journal if r["event"] == "RECOMMENDATION"]
    for row, recommendation in zip(rows, recommendations):
        assert row["decision_id"] == recommendation["decision_id"] and row["schema"] == STRATEGY_SCHEMA
        assert [a["index"] for a in row["actions"]] == list(range(row["menu_size"]))          # menu order, not Policy
        assert row["complete"] and row["top3"] and row["top3"][0]["rank"] == 1
    invalidated = [r for r in shadowed.strategy_rows if r["event"] == "STRATEGY_SHADOW_INVALIDATION"]
    assert invalidated and {r["decision_id"] for r in invalidated} <= {r["decision_id"] for r in rows}
    assert shadowed.strategy_summary.startswith("strategy shadow: ")
    again = replay.run_runtime(directory, policy, texts, tmp_path / "on2", shadow=False, strategy=StrategyShadow(texts))
    assert replay._strip(again.strategy_rows) == replay._strip(shadowed.strategy_rows)


def test_the_strategy_ranking_does_not_depend_on_the_policy_order(texts):
    state = _threat_position()
    actions = [sc.end_turn(), sc.play("T_KILL", 0, "SPELL", 4, sc.target_minion("OPPONENT", 2, "D")),
               sc.play("T_WALL", 1, "MINION", 3, play_position=3)]
    snapshot = SimpleNamespace(state=json.loads(json.dumps(_state_dict(state))), observed=None)
    item = lambda i, score: SimpleNamespace(index=i, score=score, action=actions[i])   # noqa: E731
    one = StrategyShadow(TEXTS).score(snapshot, SimpleNamespace(menu=(item(0, 3.0), item(1, 2.0), item(2, 1.0))))
    two = StrategyShadow(TEXTS).score(snapshot, SimpleNamespace(menu=(item(2, 9.0), item(1, -1.0), item(0, -5.0))))
    assert replay._strip(one) == replay._strip(two)
    with pytest.raises(StrategyFailed) as refused:
        StrategyShadow(TEXTS).score(snapshot, SimpleNamespace(menu=()))
    assert refused.value.reason == "NO_MENU"


def _state_dict(state):
    from manamind.live.snapshot import state_to_dict
    return state_to_dict(state)


def test_a_failing_strategy_shadow_leaves_the_policy_untouched(tmp_path, recommender, texts, monkeypatch):
    policy, _ = recommender
    directory = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines)
    plain = replay.run_runtime(directory, policy, texts, tmp_path / "off", shadow=False)
    monkeypatch.setattr(StrategyShadow, "score", lambda *_: (_ for _ in ()).throw(RuntimeError("private log text")))
    shadow = StrategyShadow(texts)
    broken = replay.run_runtime(directory, policy, texts, tmp_path / "on", shadow=False, strategy=shadow)
    assert broken.emitted == plain.emitted and broken.events == plain.events and broken.journal == plain.journal
    assert shadow.stats.failed == 1 and dict(shadow.stats.reasons) == {"SHADOW_RUNTIME_ERROR": 1}
    assert [r["event"] for r in broken.strategy_rows] == ["STRATEGY_SHADOW_ERROR"]
    assert "private" not in json.dumps(broken.strategy_rows)


def test_an_unwritable_strategy_journal_does_not_disturb_the_policy(tmp_path, recommender, texts, monkeypatch):
    policy, _ = recommender

    def refuse(self, event):
        raise PermissionError("private path")

    monkeypatch.setattr(PredictionJournal, "_append_strategy", refuse)
    directory = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines)
    shadow = StrategyShadow(texts)
    run = replay.run_runtime(directory, policy, texts, tmp_path / "on", shadow=False, strategy=shadow)
    assert run.scored == 1 and shadow.stats.journal_failures >= 1
    assert "strategy shadow warning: PermissionError" in run.emitted and "private" not in "\n".join(run.emitted)


def test_strategy_rows_hold_no_hidden_information_and_no_raw_text(tmp_path, recommender, texts):
    policy, _ = recommender
    log = LiveLog(canaries=True).create_game().mulligan()
    log.canary_reveals()
    log.opponent_hand_identity()
    log.self_decision(1)
    run = replay.run_runtime(record_log(tmp_path, log.lines), policy, texts, tmp_path / "on", shadow=False,
                             strategy=StrategyShadow(texts))
    assert [r for r in run.strategy_rows if r["event"] == "STRATEGY_SHADOW"]
    blob = json.dumps(run.strategy_rows)
    for canary in CANARIES:
        assert canary not in blob
    assert "handle" not in blob and "Opponent#" not in blob


def test_the_strategy_shadow_is_off_by_default_and_unreachable_from_live_and_apps():
    args = run_manamind.build_parser().parse_args([])
    assert args.strategy_shadow is False and args.outcome_shadow is False
    assert run_manamind.UnifiedRuntime(SimpleNamespace(session=None), None, None).strategy_shadow is None
    for path in list((ROOT / "src/manamind/live").rglob("*.py")) + list((ROOT / "apps").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:from|import)\s+manamind\.strategy", text, re.MULTILINE), path
        assert "StrategyShadow" not in text, path


@pytest.mark.parametrize("texts_fail", [False, True])
def test_the_launcher_wires_the_strategy_shadow_only_on_request(tmp_path, monkeypatch, capsys, texts_fail):
    constructed = []
    original = run_manamind.UnifiedRuntime

    class Spy(original):
        def __init__(self, *args, **kwargs):
            constructed.append(kwargs.get("strategy_shadow"))
            super().__init__(*args, **kwargs)

    def stop(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_manamind, "UnifiedRuntime", Spy)
    monkeypatch.setattr(run_manamind.time, "sleep", stop)
    if texts_fail:
        monkeypatch.setattr(run_manamind, "load_texts", lambda root: (_ for _ in ()).throw(FileNotFoundError("private")))
    base = ["--logs-root", str(tmp_path / "Logs"), "--data-root", str(tmp_path / "data"),
            "--checkpoint", str(tmp_path / "missing.pt")]
    assert run_manamind.main(base) == 0
    assert run_manamind.main([*base, "--strategy-shadow"]) == 0
    printed = capsys.readouterr().out
    assert constructed[0] is None
    if texts_fail:
        assert constructed[1] is None and "strategy shadow warning: FileNotFoundError" in printed
        assert "private" not in printed
    else:
        assert isinstance(constructed[1], StrategyShadow) and "strategy shadow: no decisions" in printed


# ----- 9. latency -----------------------------------------------------------------------------------------------------


def test_a_large_menu_is_scored_quickly(texts):
    board = tuple(sc.minion(f"M{i}", 2, 3, i, can_attack=True) for i in range(1, 8))
    enemies = tuple(sc.minion(f"E{i}", 3, 2, i) for i in range(1, 8))
    state = sc.position(self_side=sc.side(mana=10, board=board), opponent=sc.side(board=enemies),
                        hand=(sc.hand_card("CORE_EX1_309", "SPELL", 4),))
    actions = [sc.end_turn()] + [sc.attack(i, f"M{i}", sc.target_minion("OPPONENT", j, f"E{j}"))
                                 for i in range(1, 8) for j in range(1, 8)]
    actions += [sc.play("CORE_EX1_309", 0, "SPELL", 4, sc.target_minion("OPPONENT", j, f"E{j}")) for j in range(1, 8)]
    started = time.perf_counter()
    result = score_menu(state, actions, texts, budget_ms=10_000)
    assert result.computed == len(actions) == 57
    assert time.perf_counter() - started < 5.0       # generous for CI; the measured LIVE numbers are in the report
