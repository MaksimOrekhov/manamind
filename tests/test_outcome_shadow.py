# ruff: noqa: F811
"""ACTION-OUTCOME-2: the LIVE outcome shadow must not change the Policy path and must record honest, reproducible rows."""
from __future__ import annotations

import json
import sys
from collections import Counter
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
from test_hero_state_extraction import policy_log  # noqa: E402
from test_live_recommendation import CATALOG, recommender  # noqa: E402,F401
from test_live_tail import Clock, append, write  # noqa: E402

from manamind.live.prediction_journal import PredictionJournal  # noqa: E402
from manamind.live.recorder import Recorder  # noqa: E402
from manamind.live.runner import LiveRunner  # noqa: E402
from manamind.live.session import LiveSession  # noqa: E402
from manamind.outcome import ObservedContext, Status, TextSource, forecast_action  # noqa: E402
from manamind.outcome import scenario as sc  # noqa: E402
from manamind.outcome import shadow as shadow_module  # noqa: E402
from manamind.outcome.live_shadow import OutcomeShadow, ShadowFailed, load_texts  # noqa: E402
from manamind.outcome.shadow import (  # noqa: E402
    ERROR, NOT_COMPUTED, action_digest, compact_forecast, context_from_dict, context_to_dict, forecast_digest,
    forecast_menu,
)
from manamind.outcome.shadow_analysis import (  # noqa: E402
    LabeledGame, coverage_summary, find_recordings, group_decisions, invariant_violations,
    read_shadow_rows, verify_recordings,
)
from manamind.outcome.verify import LoggedDecision  # noqa: E402

TEXTS = TextSource.from_records([
    {"id": "T_HOLD", "type": "SPELL", "mechanics": [], "text": "<b>Prepare</b>\nGive a minion +5/+5 and <b>Lifesteal</b>."},
    {"id": "T_NOVA", "type": "SPELL", "mechanics": [], "text": "Deal $2 damage to all minions."},
    {"id": "T_ODD", "type": "SPELL", "mechanics": [], "text": "Summon a plant that dreams of electric sheep."},
    *({"id": card, "type": "MINION", "mechanics": [], "text": ""} for card in ("A", "B", "C"))])
TRUSTED = ObservedContext(trust_spell_damage=True, spell_healing_doubled=False)


def _position():
    state = sc.position(
        self_side=sc.side(mana=6, board=(sc.minion("B", 2, 2, 1),)),
        opponent=sc.side(board=(sc.minion("A", 3, 4, 1), sc.minion("C", 1, 1, 2))),
        hand=(sc.hand_card("T_HOLD", "SPELL", 5), sc.hand_card("T_NOVA", "SPELL", 2), sc.hand_card("T_ODD", "SPELL", 1)))
    actions = [
        sc.end_turn(),
        sc.play("T_NOVA", 1, "SPELL", 2),
        sc.play("T_HOLD", 0, "SPELL", 5, sc.target_minion("OPPONENT", 1, "A")),
        sc.play("T_ODD", 2, "SPELL", 1),
        sc.attack(1, "B", sc.target_minion("OPPONENT", 2, "C")),
    ]
    return state, actions


def _menu(actions):
    return [(index, index + 1, action) for index, action in enumerate(actions)]


def _stable(value):
    return replay._strip(value)


# ----- pure record -------------------------------------------------------------------------------------------------


def test_context_round_trip_keeps_an_observed_false_and_drops_defaults():
    context = ObservedContext(healing_does_damage=False, spell_damage=0, trust_spell_damage=True,
                              hand_keywords=(frozenset({"taunt"}), None, frozenset()))
    data = context_to_dict(context)
    assert data["healing_does_damage"] is False and data["spell_damage"] == 0     # observed zeros are facts
    assert "self_hero_divine_shield" not in data and "assume_zero_healing_bonus" not in data
    assert context_from_dict(json.loads(json.dumps(data))) == context
    assert context_to_dict(ObservedContext()) == {}


def test_menu_forecast_is_deterministic_independent_and_leaves_the_state_alone():
    state, actions = _position()
    before = repr(state)
    first = forecast_menu(state, _menu(actions), TEXTS, TRUSTED)
    second = forecast_menu(state, list(reversed(_menu(actions))), TEXTS, TRUSTED)
    assert repr(state) == before
    assert first["complete"] and first["computed"] == len(actions) and first["errors"] == 0
    by_index = {r["index"]: _stable(r) for r in second["actions"]}
    # each action is forecast from the same pre-action state: neither order nor neighbours change a row
    assert {r["index"]: _stable(r) for r in first["actions"]} == by_index
    for row, action in zip(first["actions"], actions):
        assert row["action"] == action_digest(action)
        assert row["digest"] == forecast_digest(forecast_action(state, action, TEXTS, TRUSTED))


def test_partial_is_recorded_as_partial_and_unknowns_are_tags_not_free_text():
    state, actions = _position()
    record = forecast_menu(state, _menu(actions), TEXTS, TRUSTED)
    rows = {r["index"]: r for r in record["actions"]}
    odd = rows[3]
    assert odd["status"] != Status.EXACT.value and odd["unknowns"]
    assert all(":" in item or item.isupper() for item in odd["unknowns"])
    assert all("sheep" not in item for item in odd["unknowns"])                     # the card text is not stored
    assert rows[0]["status"] == Status.EXACT.value and rows[0]["unknowns"] == []   # END_TURN: nothing to forecast
    assert invariant_violations({"schema": shadow_module.SHADOW_SCHEMA, **record}) == []


def test_invariants_catch_a_partial_that_pretends_to_be_exact():
    state, actions = _position()
    row = {"schema": shadow_module.SHADOW_SCHEMA, **forecast_menu(state, _menu(actions), TEXTS, TRUSTED)}
    odd = next(a for a in row["actions"] if a["index"] == 3)
    assert odd["status"] == "PARTIAL"
    forged = json.loads(json.dumps(row))
    next(a for a in forged["actions"] if a["index"] == 3).update(status="EXACT", tier="EXACT")
    assert "EXACT_WITH_OPEN_UNKNOWNS" in invariant_violations(forged)
    quiet = json.loads(json.dumps(row))
    next(a for a in quiet["actions"] if a["index"] == 3).update(unknowns=[])
    assert "PARTIAL_WITHOUT_OPEN_UNKNOWNS" in invariant_violations(quiet)
    short = json.loads(json.dumps(row))
    short["actions"].pop()
    assert {"MENU_SIZE", "RANK_SET"} <= set(invariant_violations(short)) or "COUNTERS" in invariant_violations(short)


def test_one_failing_action_costs_only_itself(monkeypatch):
    state, actions = _position()
    original = shadow_module.forecast_action

    def flaky(state_, action, texts, context):
        if action["type"] == "ATTACK":
            raise RuntimeError("private card text")
        return original(state_, action, texts, context)

    monkeypatch.setattr(shadow_module, "forecast_action", flaky)
    record = forecast_menu(state, _menu(actions), TEXTS, TRUSTED)
    broken = [r for r in record["actions"] if r["status"] == ERROR]
    assert len(broken) == 1 and broken[0]["error"] == "RuntimeError"
    assert "private" not in json.dumps(record)
    assert record["errors"] == 1 and record["computed"] == len(actions) - 1 and record["complete"]


def test_exhausted_budget_marks_the_rest_not_computed_and_says_so():
    state, actions = _position()
    ticks = iter(range(0, 10**12, 400_000_000))                  # every clock read advances 400 ms
    record = forecast_menu(state, _menu(actions), TEXTS, TRUSTED, budget_ms=500, clock=lambda: next(ticks))
    assert record["not_computed"] > 0 and not record["complete"]
    assert record["computed"] + record["not_computed"] == len(actions)
    skipped = [r for r in record["actions"] if r["status"] == NOT_COMPUTED]
    assert all(set(r) == {"index", "rank", "label", "action", "status"} for r in skipped)   # no invented forecast


def test_large_effect_lists_are_cut_but_the_digest_still_covers_everything(monkeypatch):
    state, actions = _position()
    forecast = forecast_action(state, actions[1], TEXTS, TRUSTED)                 # the Nova hits three minions
    full = compact_forecast(forecast)
    assert len(full["effects"]) >= 2
    monkeypatch.setattr(shadow_module, "MAX_EFFECTS_PER_ACTION", 1)
    cut = compact_forecast(forecast)
    assert len(cut["effects"]) == 1 and cut["effects_more"] == len(full["effects"]) - 1
    assert cut["digest"] == full["digest"]


# ----- the journal ---------------------------------------------------------------------------------------------------


def _snapshot(seq=1, options_id=7):
    return SimpleNamespace(game_key="g" * 64, seq=seq, decision={"options_id": options_id}, state_hash="h" * 64)


def test_shadow_rows_go_to_their_own_file_and_leave_the_recommendation_stream_alone(tmp_path):
    plain = PredictionJournal(tmp_path / "a" / "journal.jsonl")
    shadowed = PredictionJournal(tmp_path / "b" / "journal.jsonl")
    snapshot = _snapshot()
    recommendation = SimpleNamespace(ranked=[SimpleNamespace(action={"type": "END_TURN", "play_position": 0})])
    for journal in (plain, shadowed):
        journal.recommendation(snapshot, recommendation, "c" * 64)
        journal.invalidation(snapshot, "DECISION_CHANGED")
    shadowed.outcome_shadow(snapshot, {"schema": "x", "actions": []})
    shadowed.outcome_shadow_error(snapshot, "NO_MENU")
    shadowed.outcome_shadow_invalidation(snapshot, "DECISION_CHANGED")
    assert not plain.shadow_path.exists()
    assert shadowed.shadow_path.name == "journal.outcome_shadow.jsonl"
    keep = lambda path: [{k: v for k, v in json.loads(x).items() if not k.endswith("_utc")}  # noqa: E731
                         for x in path.read_text(encoding="utf-8").splitlines()]
    assert keep(plain.path) == keep(shadowed.path)
    rows = [json.loads(x) for x in shadowed.shadow_path.read_text(encoding="utf-8").splitlines()]
    assert [r["event"] for r in rows] == ["OUTCOME_SHADOW", "OUTCOME_SHADOW_ERROR", "OUTCOME_SHADOW_INVALIDATION"]
    assert all(r["decision_id"] == f"{'g' * 64}:1:7:{'h' * 64}" and r["state_hash"] == "h" * 64 for r in rows)
    assert rows[0]["seq"] == 1 and rows[0]["options_id"] == 7 and rows[0]["match_id"] == "g" * 64


def test_the_shadow_file_rotates_instead_of_growing_without_bound_or_losing_rows(tmp_path):
    journal = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=600)
    for seq in range(1, 9):
        journal.outcome_shadow(_snapshot(seq=seq), {"actions": ["x" * 80]})
    files = sorted(tmp_path.glob("journal.outcome_shadow*.jsonl"))
    assert len(files) > 1 and all(f.stat().st_size < 600 + 400 for f in files)
    seqs = sorted(json.loads(line)["seq"] for f in files for line in f.read_text(encoding="utf-8").splitlines())
    assert seqs == list(range(1, 9))


# ----- the runtime ---------------------------------------------------------------------------------------------------


def record_log(tmp_path: Path, lines: list[str], name: str = "rec", *, pause_at: int | None = None) -> Path:
    """Write ``lines`` through the real tail + recorder; returns the recording directory.

    ``pause_at``: the first ``pause_at`` lines arrive alone and settle (a decision there is displayed) before the rest.
    """
    logs = tmp_path / f"Logs_{name}"
    power = write(logs / "Power.log", [""], newline=False)
    clock = Clock()
    live = LiveRunner(logs, LiveSession(CATALOG), Recorder(tmp_path / f"raw_{name}", catalog_path=None), clock=clock)
    parts = [lines] if pause_at is None else [lines[:pause_at], lines[pause_at:]]
    for part in parts:
        for start in range(0, len(part), 9):
            append(power, "\n".join(part[start:start + 9]) + "\n")
            for _ in range(4):
                live.step()
                clock.advance(0.05)
        for _ in range(6):
            live.step()
            clock.advance(0.05)
    found = list((tmp_path / f"raw_{name}").rglob("meta.json"))
    assert len(found) == 1
    return found[0].parent


def two_decision_log() -> LiveLog:
    log = LiveLog().create_game().mulligan().self_decision(1)
    log.send_option(1)
    log.begin_turn(2)
    log.options()
    return log


@pytest.fixture
def texts():
    return load_texts(ROOT)


def test_shadow_changes_nothing_the_player_or_the_journal_sees(tmp_path, recommender, texts):
    scorer, _ = recommender
    log = two_decision_log()
    split = next(i for i, line in enumerate(log.lines) if "SendOption" in line)
    directory = record_log(tmp_path, log.lines, pause_at=split)
    plain = replay.run_runtime(directory, scorer, texts, tmp_path / "off", shadow=False)
    shadowed = replay.run_runtime(directory, scorer, texts, tmp_path / "on", shadow=True)
    assert shadowed.scored == plain.scored >= 1
    comparison = replay.compare_runs(directory, plain, shadowed)
    assert all(v for k, v in comparison.items() if isinstance(v, bool)), comparison
    assert comparison["info_state_hashes_match_recording"]            # a fresh recording replays to its own hashes
    assert plain.emitted == shadowed.emitted and plain.events == shadowed.events
    assert plain.journal == shadowed.journal and not plain.shadow_rows
    assert any(e[0] == "recommendation" for e in plain.events)
    rows = [r for r in shadowed.shadow_rows if r["event"] == "OUTCOME_SHADOW"]
    assert len(rows) == shadowed.scored
    recommendations = [r for r in shadowed.journal if r["event"] == "RECOMMENDATION"]
    for row, recommendation in zip(rows, recommendations):
        # tied to exactly the decision that was displayed, and the Top-3 it was ranked against is that Top-3
        assert row["decision_id"] == recommendation["decision_id"] and row["state_hash"] == recommendation["state_hash"]
        assert [a["rank"] for a in row["actions"]] == list(range(1, row["menu_size"] + 1))   # Policy rank order
        assert row["menu_size"] == len(row["actions"]) and row["complete"]
        assert invariant_violations(row) == []
    invalidated = [r for r in shadowed.shadow_rows if r["event"] == "OUTCOME_SHADOW_INVALIDATION"]
    assert {r["decision_id"] for r in invalidated} <= {r["decision_id"] for r in rows}
    assert invalidated and all(r["reason"] for r in invalidated)
    # the shadow is reproducible from the same input events
    again = replay.run_runtime(directory, scorer, texts, tmp_path / "on2", shadow=True)
    assert _stable(again.shadow_rows) == _stable(shadowed.shadow_rows)


def test_the_shadow_menu_is_the_policy_menu_in_policy_rank_order(tmp_path, recommender, texts):
    scorer, _ = recommender
    directory = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines)
    captured = []
    live = replay.RecordedLive(directory, scorer.encoder.catalog)
    runtime = run_manamind.UnifiedRuntime(live, replay._NoCollector(), scorer, emit=lambda _: None, collector_seconds=1,
                                          on_recommendation=captured.append)
    while not live.exhausted:
        live.fresh = True
        runtime.step(now=0.0)
    result, = captured
    assert [item.index for item in result.menu[:3]] == [item.index for item in result.ranked]
    assert [item.score for item in result.menu] == sorted((item.score for item in result.menu), reverse=True)
    assert sorted(item.index for item in result.menu) == list(range(result.menu_size))
    assert result.menu[:3] == result.ranked


def _runtime(tmp_path, scorer, shadow, journal=None):
    directory = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines)
    live = replay.RecordedLive(directory, scorer.encoder.catalog)
    emitted = []
    journal = journal or PredictionJournal(tmp_path / "j" / "prediction_journal.jsonl")
    runtime = run_manamind.UnifiedRuntime(live, replay._NoCollector(), scorer, emit=emitted.append,
                                          collector_seconds=1, journal=journal, outcome_shadow=shadow)
    while not live.exhausted:
        live.fresh = True
        runtime.step(now=0.0)
    return runtime, emitted, journal


@pytest.mark.parametrize("failure", [RuntimeError("private log text"), ShadowFailed("NO_MENU")])
def test_a_failing_shadow_leaves_the_policy_untouched_and_is_diagnosed(tmp_path, recommender, texts, monkeypatch, failure):
    scorer, _ = recommender
    baseline, base_out, base_journal = _runtime(tmp_path / "base", scorer, None)
    shadow = OutcomeShadow(texts)
    monkeypatch.setattr(OutcomeShadow, "forecast", lambda *_: (_ for _ in ()).throw(failure))
    runtime, emitted, journal = _runtime(tmp_path / "bad", scorer, shadow)
    assert runtime.decisions_scored == baseline.decisions_scored == 1 and not runtime.live_failed
    visible = [x for x in emitted if not x.startswith("outcome shadow:")]
    assert visible == base_out
    assert shadow.stats.failed == 1 and shadow.stats.recorded == 0
    expected = failure.reason if isinstance(failure, ShadowFailed) else "SHADOW_RUNTIME_ERROR"
    assert dict(shadow.stats.reasons) == {expected: 1}
    rows = [json.loads(x) for x in journal.shadow_path.read_text(encoding="utf-8").splitlines()]
    assert [(r["event"], r["reason"]) for r in rows] == [("OUTCOME_SHADOW_ERROR", expected)]
    assert "private" not in journal.shadow_path.read_text(encoding="utf-8")
    assert [json.loads(x)["event"] for x in journal.path.read_text(encoding="utf-8").splitlines()] == \
        [json.loads(x)["event"] for x in base_journal.path.read_text(encoding="utf-8").splitlines()]


def test_an_unwritable_shadow_journal_does_not_disturb_the_policy(tmp_path, recommender, texts, monkeypatch):
    scorer, _ = recommender

    def refuse(self, event):
        raise PermissionError("private path")

    monkeypatch.setattr(PredictionJournal, "_append_shadow", refuse)
    shadow = OutcomeShadow(texts)
    runtime, emitted, journal = _runtime(tmp_path, scorer, shadow)
    assert runtime.decisions_scored == 1 and shadow.stats.journal_failures >= 1
    assert any(x == "outcome shadow warning: PermissionError" for x in emitted)
    assert "private" not in "\n".join(emitted)
    assert [json.loads(x)["event"] for x in journal.path.read_text(encoding="utf-8").splitlines()][:1] == ["RECOMMENDATION"]


def test_the_shadow_is_off_by_default_and_nothing_in_live_or_apps_can_reach_it():
    assert run_manamind.build_parser().parse_args([]).outcome_shadow is False
    runtime = run_manamind.UnifiedRuntime(SimpleNamespace(session=None), None, None)
    assert runtime.outcome_shadow is None
    for path in list((ROOT / "src/manamind/live").rglob("*.py")) + list((ROOT / "apps").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "live_shadow" not in text and "OutcomeShadow" not in text, path


def test_shadow_rows_hold_no_hidden_information_and_no_raw_text(tmp_path, recommender, texts):
    scorer, _ = recommender
    log = LiveLog(canaries=True).create_game().mulligan()
    log.canary_reveals()
    log.opponent_hand_identity()
    log.self_decision(1)
    directory = record_log(tmp_path, log.lines)
    run = replay.run_runtime(directory, scorer, texts, tmp_path / "on", shadow=True)
    assert [r for r in run.shadow_rows if r["event"] == "OUTCOME_SHADOW"]
    blob = json.dumps(run.shadow_rows)
    for canary in CANARIES:
        assert canary not in blob
    assert "handle" not in blob and "Opponent#" not in blob


def test_a_forecast_depends_only_on_the_decision_not_on_what_happened_afterwards(tmp_path, recommender, texts):
    scorer, _ = recommender
    short = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines, "short")
    longer_log = LiveLog().create_game().mulligan().self_decision(1)
    prefix = len(longer_log.lines)
    longer_log.send_option(1)
    longer_log.batch(["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=4"]).finish_list()
    longer_log.begin_turn(2)
    longer_log.options()
    longer = record_log(tmp_path, longer_log.lines, "longer", pause_at=prefix)
    first = replay.run_runtime(short, scorer, texts, tmp_path / "s", shadow=True)
    second = replay.run_runtime(longer, scorer, texts, tmp_path / "l", shadow=True)
    one = [r for r in first.shadow_rows if r["event"] == "OUTCOME_SHADOW"][0]
    two = [r for r in second.shadow_rows if r["event"] == "OUTCOME_SHADOW"][0]
    assert one["decision_id"] == two["decision_id"]
    assert _stable(one) == _stable(two)


# ----- analysis ------------------------------------------------------------------------------------------------------


def _rows_for(state, actions, *, game="g" * 64, number=1, context=TRUSTED, state_hash="s" * 64):
    record = forecast_menu(state, _menu(actions), TEXTS, context)
    decision = f"{game}:1:{number}:{state_hash}"
    return {"event": "OUTCOME_SHADOW", "decision_id": decision, "match_id": game, "options_id": number, "seq": 1,
            "state_hash": state_hash, "schema": shadow_module.SHADOW_SCHEMA, "coverage": "COMPLETE",
            "context": context_to_dict(context), **record}


def test_coverage_separates_end_turn_and_counts_exact_effects_inside_partial_forecasts():
    state, actions = _position()
    rows = [_rows_for(state, actions)]
    rows += [{"event": "OUTCOME_SHADOW_INVALIDATION", "decision_id": rows[0]["decision_id"],
              "reason": "DECISION_CHANGED"},
             {"event": "OUTCOME_SHADOW_ERROR", "decision_id": "other", "reason": "NO_MENU"}]
    summary = coverage_summary(group_decisions(rows))
    assert summary["decisions"] == 2 and summary["decisions_with_record"] == 1
    assert summary["decisions_with_error_only"] == 1 and summary["error_reasons"] == {"NO_MENU": 1}
    everything, without_end = summary["all_computed_actions"], summary["excluding_end_turn"]
    assert everything["actions"] == without_end["actions"] + 1
    assert everything["status"]["EXACT"] == without_end["status"].get("EXACT", 0) + 1       # END_TURN is the free one
    assert summary["invariant_violations"] == {} and summary["invalidation_reasons"] == {"DECISION_CHANGED": 1}
    assert summary["actions_slower_than_20ms"] == 0
    partial = [a for a in rows[0]["actions"] if a["status"] == "PARTIAL"]
    assert without_end["partial_with_exact_effect"] == sum(bool(a["effects"]) for a in partial)
    assert without_end["with_exact_effect"] >= without_end["partial_with_exact_effect"]


def _labeled(state, actions, truth, chosen, *, number=1):
    first = LoggedDecision("g", number, f"g:{number}", state, actions[chosen], tuple(actions))
    second = LoggedDecision("g", number + 1, f"g:{number + 1}", truth, actions[0], (actions[0],))
    return LabeledGame({number: first, number + 1: second}, {number: None, number + 1: None},
                       {number: "s" * 64, number + 1: "t" * 64}, [(first, second)])


def test_only_the_taken_action_is_scored_and_alternatives_are_only_counted(monkeypatch, tmp_path):
    state, actions = _position()
    truth = replace(state, self_player=replace(state.self_player, available_mana=4, hand_size=2),
                    self_hand=(state.self_hand[0], state.self_hand[2]), self_hand_known_count=2)
    game = _labeled(state, actions, truth, chosen=1)
    row = _rows_for(state, actions, context=ObservedContext())       # the recording supplies no facts: all unknown
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    decisions = group_decisions([row])
    recordings = {("g" * 64)[:16]: [tmp_path]}
    report = verify_recordings(decisions, recordings, CATALOG, TEXTS)
    assert report["joined_to_recording"] == 1 and report["not_joined"] == {}
    assert report["alternatives"] == {"alternatives_no_observed_outcome": len(actions) - 1}
    assert report["chosen_action"]["decisions"] == 1 and report["chosen_action"]["policy_rank"] == {"2": 1}
    assert report["chosen_action"]["imitation_top1"] == 0 and "not evidence" in report["chosen_action"]["note"]
    assert report["reproduction"]["action_digest_mismatch"] == 0 and report["reproduction"]["context_reproduced"] == 1
    assert report["scored_pairs"] == 1
    assert report["exact_forecasts_contradicted"] == 0


def test_a_forecast_that_cannot_be_reproduced_is_not_scored(monkeypatch, tmp_path):
    state, actions = _position()
    game = _labeled(state, actions, state, chosen=1)
    row = _rows_for(state, actions, context=ObservedContext())
    next(a for a in row["actions"] if a["index"] == 1)["digest"] = "0" * 64        # a different code version
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    report = verify_recordings(group_decisions([row]), {("g" * 64)[:16]: [tmp_path]}, CATALOG, TEXTS)
    assert report["reproduction"]["action_digest_mismatch"] == 1
    assert report["chosen_action"]["unscorable"] == {"CHOSEN_FORECAST_NOT_REPRODUCED": 1}
    assert report["scored_pairs"] == 0


def test_rows_that_cannot_be_joined_say_why(monkeypatch, tmp_path):
    state, actions = _position()
    game = _labeled(state, actions, state, chosen=0)
    good, = (_rows_for(state, actions, context=ObservedContext()),)
    wrong_hash = _rows_for(state, actions, number=1, state_hash="x" * 64)
    unlabeled = _rows_for(state, actions, number=9)
    other_game = _rows_for(state, actions, game="f" * 64)
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    rows = [good, wrong_hash, unlabeled, other_game]
    report = verify_recordings(group_decisions(rows), {("g" * 64)[:16]: [tmp_path]}, CATALOG, TEXTS)
    assert report["joined_to_recording"] == 1
    assert report["not_joined"] == {"STATE_HASH_MISMATCH": 1, "DECISION_NOT_LABELED": 1, "NO_RECORDING": 1}


def test_real_recording_joins_reproduces_and_has_no_observation_after_the_last_action(tmp_path, recommender, texts):
    scorer, _ = recommender
    lines = policy_log().lines
    split = next(i for i, line in enumerate(lines) if "SendOption" in line)
    directory = record_log(tmp_path, lines, pause_at=split)
    run = replay.run_runtime(directory, scorer, texts, tmp_path / "on", shadow=True)
    rows = [r for r in run.shadow_rows if r["event"] == "OUTCOME_SHADOW"]
    assert len(rows) == 1
    path = tmp_path / "shadow.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in run.shadow_rows), encoding="utf-8")
    parsed, bad = read_shadow_rows([path])
    assert bad == 0
    recordings = find_recordings(directory.parent.parent)
    assert recordings
    report = verify_recordings(group_decisions(parsed), recordings, CATALOG, texts)
    assert report["joined_to_recording"] == 1 and report["not_joined"] == {}
    assert report["reproduction"]["action_digest_mismatch"] == 0
    assert report["reproduction"]["context_reproduced"] == 1 and report["reproduction"]["menu_identical"] == 1
    assert report["chosen_action"]["unscorable"] == {"NO_OBSERVATION_AFTER_ACTION": 1}
    assert coverage_summary(group_decisions(parsed))["invariant_violations"] == {}


def test_unreadable_lines_are_counted_not_trusted(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{"event":"OUTCOME_SHADOW","decision_id":"d"}\nnot json\n[1]\n\n', encoding="utf-8")
    rows, bad = read_shadow_rows([path])
    assert len(rows) == 1 and bad == 2


def test_shadow_rows_are_compact(tmp_path, recommender, texts):
    scorer, _ = recommender
    directory = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines)
    run = replay.run_runtime(directory, scorer, texts, tmp_path / "on", shadow=True)
    size = Counter(len(json.dumps(r)) for r in run.shadow_rows if r["event"] == "OUTCOME_SHADOW")
    assert max(size) < 12_000


def test_a_recommendation_without_a_menu_cannot_be_shadowed(tmp_path, recommender, texts):
    scorer, _ = recommender
    directory = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines)
    live = replay.RecordedLive(directory, scorer.encoder.catalog)
    captured = []
    runtime = run_manamind.UnifiedRuntime(live, replay._NoCollector(), scorer, emit=lambda _: None, collector_seconds=1,
                                          on_recommendation=captured.append)
    while not live.exhausted:
        live.fresh = True
        runtime.step(now=0.0)
    result, = captured
    with pytest.raises(ShadowFailed) as refused:
        OutcomeShadow(texts).forecast(SimpleNamespace(state={}, observed=None), replace(result, menu=()))
    assert refused.value.reason == "NO_MENU"


def test_the_shadow_runs_only_after_the_recommendation_is_displayed_and_journaled(tmp_path, recommender, texts, monkeypatch):
    scorer, _ = recommender
    seen = {}
    original = OutcomeShadow.forecast

    def spy(self, snapshot, recommendation):
        journal_rows = journal.path.read_text(encoding="utf-8").splitlines() if journal.path.exists() else []
        seen["displayed"] = any("EXPERIMENTAL_NEURAL_POLICY" in line for line in emitted)
        seen["journaled"] = [json.loads(x)["event"] for x in journal_rows]
        seen["presented"] = any(event[0] == "recommendation" for event in events)
        return original(self, snapshot, recommendation)

    directory = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines)
    live = replay.RecordedLive(directory, scorer.encoder.catalog)
    emitted, events = [], []
    journal = PredictionJournal(tmp_path / "j" / "prediction_journal.jsonl")
    monkeypatch.setattr(OutcomeShadow, "forecast", spy)
    runtime = run_manamind.UnifiedRuntime(live, replay._NoCollector(), scorer, emit=emitted.append, collector_seconds=1,
                                          journal=journal, outcome_shadow=OutcomeShadow(texts),
                                          on_event=lambda event: events.append(replay._event_view(event)))
    while not live.exhausted:
        live.fresh = True
        runtime.step(now=0.0)
    assert seen == {"displayed": True, "journaled": ["RECOMMENDATION"], "presented": True}


@pytest.mark.parametrize("known,chosen,expected,heal_text", [
    (True, 1, {"decisions": 1, "decisions_offering_one": 1, "taken_by_player": 0, "policy_top1_is_one": 1,
               "policy_top1_gift_taken_by_player": 0, "policy_top1_gift_with_non_gift_in_top3": 1,
               "policy_top1_gift_replacement_is_players_choice": 1,
               "policy_top1_gift_same_card_alternative_exists": 0,
               "policy_top1_gift_same_card_alternative_is_players_choice": 0}, "Restore #4 Health."),
    (True, 0, {"decisions": 1, "decisions_offering_one": 1, "taken_by_player": 1, "policy_top1_is_one": 1,
               "policy_top1_gift_taken_by_player": 1, "policy_top1_gift_with_non_gift_in_top3": 1,
               "policy_top1_gift_replacement_is_players_choice": 0,
               "policy_top1_gift_same_card_alternative_exists": 0,
               "policy_top1_gift_same_card_alternative_is_players_choice": 0}, "Restore #4 Health."),
    (False, 1, {"decisions": 1}, "Restore #4 Health."),   # Ruby Sanctum unobserved: the heal may be damage, no known gift
    (True, 1, {"decisions": 1}, "Restore #4 Health. Summon a plant that dreams of electric sheep."),  # own text not understood
])
def test_gifts_are_counted_as_a_bookkeeping_pattern(monkeypatch, tmp_path, known, chosen, expected, heal_text):
    texts = TextSource.from_records([
        {"id": "T_HEAL", "type": "SPELL", "mechanics": [], "text": heal_text},
        {"id": "T_HIT", "type": "SPELL", "mechanics": [], "text": "Deal $3 damage to a minion."},
        {"id": "A", "type": "MINION", "mechanics": [], "text": ""}, {"id": "B", "type": "MINION", "mechanics": [], "text": ""}])
    ctx = (ObservedContext(healing_does_damage=False, healing_bonus=0, spell_healing_doubled=False, trust_spell_damage=True)
           if known else ObservedContext(trust_spell_damage=True))
    state = sc.position(self_side=sc.side(mana=5, board=(sc.minion("B", 2, 2, 1),)),
                        opponent=sc.side(board=(sc.minion("A", 3, 5, 1, max_health=7),)),
                        hand=(sc.hand_card("T_HEAL", "SPELL", 1), sc.hand_card("T_HIT", "SPELL", 1)))
    actions = [sc.play("T_HEAL", 0, "SPELL", 1, sc.target_minion("OPPONENT", 1, "A")),
               sc.play("T_HIT", 1, "SPELL", 1, sc.target_minion("OPPONENT", 1, "A")), sc.end_turn()]
    game = _labeled(state, actions, state, chosen=chosen)
    row = _rows_for(state, actions, context=ctx)
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    monkeypatch.setattr("manamind.outcome.shadow_analysis.context_from_observed", lambda facts, state: ctx)
    report = verify_recordings(group_decisions([row]), {("g" * 64)[:16]: [tmp_path]}, CATALOG, texts)
    gifts = report["opponent_only_improvement"]
    assert {k: v for k, v in gifts.items() if k in expected} == expected
    assert set(gifts) - set(expected) <= {"gift_inside_policy_top3", "without_gifts_players_choice_enters_top1",
                                          "without_gifts_players_choice_enters_top3"}
    assert sum(report["policy_top1_gift_actions"].values()) == expected.get("policy_top1_is_one", 0)


def test_report_cli_passes_on_a_clean_journal_fails_on_a_forged_one_and_never_overwrites(tmp_path, recommender, texts, capsys):
    import outcome_shadow_report as cli

    scorer, _ = recommender
    lines = policy_log().lines
    split = next(i for i, line in enumerate(lines) if "SendOption" in line)
    directory = record_log(tmp_path, lines, pause_at=split)
    run = replay.run_runtime(directory, scorer, texts, tmp_path / "on", shadow=True)
    clean = tmp_path / "clean.jsonl"
    clean.write_text("".join(json.dumps(r) + "\n" for r in run.shadow_rows), encoding="utf-8")
    out = tmp_path / "out" / "report.json"
    argv = ["--shadow", str(clean), "--recordings-root", str(directory.parent.parent), "--out", str(out)]
    assert cli.main(argv) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["gates"]["pass"] and report["against_recordings"]["joined_to_recording"] == 1
    with pytest.raises(SystemExit):
        cli.main(argv)                                             # an existing report is never overwritten
    forged = [json.loads(json.dumps(r)) for r in run.shadow_rows]
    row = next(r for r in forged if r["event"] == "OUTCOME_SHADOW")
    partial = next((a for a in row["actions"] if a["status"] == "PARTIAL"), row["actions"][0])
    partial.update(status="EXACT", tier="EXACT", unknowns=["POSSIBLE_REACTION:BOARD_TRIGGER"])
    bad = tmp_path / "bad.jsonl"
    bad.write_text("".join(json.dumps(r) + "\n" for r in forged), encoding="utf-8")
    assert cli.main(["--shadow", str(bad), "--out", str(tmp_path / "out" / "bad.json")]) == 1
    assert json.loads((tmp_path / "out" / "bad.json").read_text(encoding="utf-8"))["gates"]["invariant_violations"] >= 1
    capsys.readouterr()


def test_a_target_side_correction_is_counted_when_the_same_card_has_a_better_aim(monkeypatch, tmp_path):
    texts = TextSource.from_records([
        {"id": "T_HEAL", "type": "SPELL", "mechanics": [], "text": "Restore #4 Health."},
        {"id": "A", "type": "MINION", "mechanics": [], "text": ""}, {"id": "B", "type": "MINION", "mechanics": [], "text": ""}])
    ctx = ObservedContext(healing_does_damage=False, healing_bonus=0, spell_healing_doubled=False)
    state = sc.position(self_side=sc.side(mana=5, board=(sc.minion("B", 2, 1, 1, max_health=4),)),
                        opponent=sc.side(board=(sc.minion("A", 3, 5, 1, max_health=7),)),
                        hand=(sc.hand_card("T_HEAL", "SPELL", 1),))
    actions = [sc.play("T_HEAL", 0, "SPELL", 1, sc.target_minion("OPPONENT", 1, "A")),
               sc.play("T_HEAL", 0, "SPELL", 1, sc.target_minion("SELF", 1, "B")), sc.end_turn()]
    game = _labeled(state, actions, state, chosen=1)
    row = _rows_for(state, actions, context=ctx)
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    monkeypatch.setattr("manamind.outcome.shadow_analysis.context_from_observed", lambda facts, state: ctx)
    report = verify_recordings(group_decisions([row]), {("g" * 64)[:16]: [tmp_path]}, CATALOG, texts)
    gifts = report["opponent_only_improvement"]
    assert gifts["policy_top1_is_one"] == 1 and gifts["taken_by_player"] == 0
    assert gifts["policy_top1_gift_same_card_alternative_exists"] == 1
    assert gifts["policy_top1_gift_same_card_alternative_is_players_choice"] == 1
    assert gifts["gift_inside_policy_top3"] == 1
    assert gifts["without_gifts_players_choice_enters_top1"] == 1      # rank 2 behind the gift becomes rank 1
    assert gifts["without_gifts_players_choice_enters_top3"] == 0      # it was in the Top-3 already
    assert report["policy_top1_gift_actions"] == {"PLAY_CARD T_HEAL -> OPPONENT minion #1 A": 1}


def test_dropping_gifts_moves_the_players_choice_up_the_ranking(monkeypatch, tmp_path):
    texts = TextSource.from_records([
        {"id": "T_HEAL", "type": "SPELL", "mechanics": [], "text": "Restore #4 Health."},
        {"id": "A", "type": "MINION", "mechanics": [], "text": ""}, {"id": "B", "type": "MINION", "mechanics": [], "text": ""}])
    ctx = ObservedContext(healing_does_damage=False, healing_bonus=0, spell_healing_doubled=False)
    state = sc.position(self_side=sc.side(mana=5, board=(sc.minion("B", 2, 2, 1),)),
                        opponent=sc.side(board=(sc.minion("A", 3, 5, 1, max_health=7),)),
                        hand=(sc.hand_card("T_HEAL", "SPELL", 1),))
    actions = [sc.play("T_HEAL", 0, "SPELL", 1, sc.target_minion("OPPONENT", 1, "A")), sc.end_turn(),
               sc.attack(1, "B", sc.target_minion("OPPONENT", 1, "A")),
               sc.attack(1, "B", sc.target_minion("OPPONENT", 1, "A")) | {"source_board_position": 2}]
    game = _labeled(state, actions, state, chosen=3)                  # the player's choice sits at Policy rank 4
    row = _rows_for(state, actions, context=ctx)
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    monkeypatch.setattr("manamind.outcome.shadow_analysis.context_from_observed", lambda facts, state: ctx)
    gifts = verify_recordings(group_decisions([row]), {("g" * 64)[:16]: [tmp_path]}, CATALOG, texts)["opponent_only_improvement"]
    assert gifts["gift_inside_policy_top3"] == 1
    assert gifts["without_gifts_players_choice_enters_top3"] == 1 and gifts["without_gifts_players_choice_enters_top1"] == 0


@pytest.mark.parametrize("ending,reason_prefix", [
    ("unknown_entity", "TRUST_LOST:SYNCING:AWAITING_DECISION"),
    ("game_reset", "TRUST_LOST:SYNCING:GAME_RESET"),
    ("game_over", "GAME_OVER"),
    ("next_options", "TRUST_LOST:SYNCING:AWAITING_DECISION"),
])
def test_trust_changes_end_a_shadow_exactly_as_they_end_the_recommendation(tmp_path, recommender, texts, ending, reason_prefix):
    scorer, _ = recommender
    log = LiveLog().create_game().mulligan().self_decision(1)
    split = len(log.lines)
    if ending == "unknown_entity":
        log.send_option(1)
        log.begin_turn(2)
        log.lines.append("D 20:30:00.0000000 GameState.DebugPrintPower() - TAG_CHANGE Entity=999 tag=ZONE value=HAND")
        log.options()
    elif ending == "game_reset":
        log.batch(["BLOCK_START BlockType=GAME_RESET Entity=GameEntity EffectCardId= EffectIndex=0 Target=0 SubOption=-1",
                   "BLOCK_END"]).finish_list()
    elif ending == "game_over":
        log.complete()
    else:
        log.send_option(1)
        log.begin_turn(2)
        log.options()
    directory = record_log(tmp_path, log.lines, pause_at=split)
    plain = replay.run_runtime(directory, scorer, texts, tmp_path / "off", shadow=False)
    shadowed = replay.run_runtime(directory, scorer, texts, tmp_path / "on", shadow=True)
    assert all(v for k, v in replay.compare_runs(directory, plain, shadowed).items()
               if isinstance(v, bool) and not k.startswith("info_"))
    first = next(r for r in shadowed.journal if r["event"] == "INVALIDATION")
    assert first["reason"].startswith(reason_prefix)
    stopped = [r for r in shadowed.shadow_rows if r["event"] == "OUTCOME_SHADOW_INVALIDATION"][0]
    assert stopped["decision_id"] == first["decision_id"] and stopped["reason"] == first["reason"]
    rows = [r for r in shadowed.shadow_rows if r["event"] == "OUTCOME_SHADOW"]
    assert [r["decision_id"] for r in rows] == [first["decision_id"]]       # an untrusted decision is never shadowed
    if ending == "unknown_entity":
        assert any(line.startswith("status: UNTRUSTED") for line in shadowed.emitted)


def test_unreadable_facts_mean_unknown_facts_not_a_lost_shadow(tmp_path, recommender, texts, monkeypatch):
    scorer, _ = recommender

    def boom(*args, **kwargs):
        raise RuntimeError("private")

    monkeypatch.setattr("manamind.outcome.live_shadow.context_from_observed", boom)
    run = replay.run_runtime(record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines),
                             scorer, texts, tmp_path / "on", shadow=True)
    row = next(r for r in run.shadow_rows if r["event"] == "OUTCOME_SHADOW")
    assert row["context_failed"] is True and row["context"] == {} and row["complete"]
    assert "private" not in json.dumps(run.shadow_rows)


def test_the_session_summary_counts_what_was_recorded(tmp_path, recommender, texts):
    scorer, _ = recommender
    log = two_decision_log()
    split = next(i for i, line in enumerate(log.lines) if "SendOption" in line)
    run = replay.run_runtime(record_log(tmp_path, log.lines, pause_at=split), scorer, texts, tmp_path / "on", shadow=True)
    n = run.scored
    assert n >= 1
    assert run.shadow_summary.startswith(f"outcome shadow: {n}/{n} decisions recorded, 0 failed, 0 incomplete, 0 journal failures; forecast ")


def test_unexplained_discrepancies_are_listed_and_bucketed_by_what_is_known():
    from manamind.outcome.shadow_analysis import _discrepancy_buckets, _unexplained_examples

    result = SimpleNamespace(
        decision_id="abcdefghij:7", action_label="PLAY_CARD X", tier=SimpleNamespace(value="OWN_EFFECT_KNOWN"),
        contradicted={"p.a": (1, 2), "p.b": (3, 4)}, missed={"p.c": (0, 1), "p.d": (0, 1), "p.e": (0, 1), "p.f": (0, 1)},
        explanations={"p.a": ("DECLARED_GAP", "x", ""), "p.b": ("UNEXPLAINED", "", ""), "p.c": ("CONFIRMED_REACTION", "", ""),
                      "p.d": ("OBSERVATION_GAP", "", ""), "p.e": ("COMPARISON_LIMIT", "", "")})   # p.f has no explanation
    assert [(e["kind"], e["path"], e["decision"]) for e in _unexplained_examples([result])] == [
        ("contradicted", "p.b", "abcdefgh:7"), ("missed", "p.f", "abcdefgh:7")]
    assert len(_unexplained_examples([result] * 30, limit=5)) == 5
    buckets = _discrepancy_buckets([result])
    assert buckets["contradicted_claims"] == {"unknown_reaction_or_declared_gap": 1, "observation_or_comparison_limit": 0,
                                              "unexplained": 1}
    assert buckets["missed_changes"] == {"unknown_reaction_or_declared_gap": 1, "observation_or_comparison_limit": 2,
                                         "unexplained": 1}


def test_bookkeeping_is_counted_not_listed():
    state, actions = _position()
    rows = {r["index"]: r for r in forecast_menu(state, _menu(actions), TEXTS, TRUSTED)["actions"]}
    assert rows[0]["bookkeeping"] == 0 and rows[1]["bookkeeping"] >= 2           # END_TURN pays nothing, a spell pays mana and hand
    assert all("BOOKKEEPING" not in json.dumps(r["effects"]) for r in rows.values())


def test_a_spent_budget_is_visible_in_the_session_summary_and_the_row(tmp_path, recommender, texts):
    scorer, _ = recommender
    directory = record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines)
    run = replay.run_runtime(directory, scorer, texts, tmp_path / "on", shadow=True, budget_ms=-1.0)
    row = next(r for r in run.shadow_rows if r["event"] == "OUTCOME_SHADOW")
    assert row["complete"] is False and row["computed"] == 0 and row["not_computed"] == row["menu_size"]
    assert "1 incomplete" in run.shadow_summary


def test_facts_that_could_not_be_read_are_recorded_as_such(tmp_path, recommender, texts, monkeypatch):
    scorer, _ = recommender

    def boom(*args, **kwargs):
        raise RuntimeError("private")

    monkeypatch.setattr("manamind.live.session.extract_observed_facts", boom)
    run = replay.run_runtime(record_log(tmp_path, LiveLog().create_game().mulligan().self_decision(1).lines),
                             scorer, texts, tmp_path / "on", shadow=True)
    row = next(r for r in run.shadow_rows if r["event"] == "OUTCOME_SHADOW")
    assert row["coverage"] == "NONE" and row["context"] == {}


def _coverage_row(actions):
    return {"event": "OUTCOME_SHADOW", "decision_id": "d", "schema": shadow_module.SHADOW_SCHEMA, "menu_size": len(actions),
            "computed": len(actions), "not_computed": 0, "errors": 0, "complete": True, "elapsed_ms": 1.0, "coverage": "COMPLETE",
            "actions": [{"index": i, "rank": i + 1, "label": label, "action": f"a{i}", "digest": "d", "us": 5, **rest}
                        for i, (label, rest) in enumerate(actions)]}


def test_coverage_separates_a_known_effect_from_exact_effects_inside_a_partial_forecast():
    partial = {"status": "PARTIAL", "unknowns": ["POSSIBLE_REACTION:BOARD_TRIGGER"], "bounds": [], "reason": None}
    row = _coverage_row([
        ("PLAY_CARD A", {**partial, "tier": "OWN_EFFECT_KNOWN", "own": 1, "effects": []}),
        ("PLAY_CARD A2", {**partial, "tier": "OWN_EFFECT_KNOWN", "own": 1, "effects": []}),
        ("PLAY_CARD B", {**partial, "tier": "PARTIAL_LOCAL", "own": 0, "effects": [["OPPONENT hero", "health", 30, 27]]}),
        ("END_TURN", {"status": "EXACT", "unknowns": [], "tier": "EXACT", "own": 1, "effects": []})])
    summary = coverage_summary(group_decisions([row]))
    played = summary["excluding_end_turn"]
    assert (played["with_exact_effect"], played["partial_with_exact_effect"]) == (1, 1)
    assert (played["own_effect_known"], played["partial_own_effect_known"]) == (2, 2)
    assert summary["decisions_with_a_useful_known_effect"] == 0              # no action has both a known own effect and an effect


def test_actions_that_were_not_computed_are_skipped_not_reproduced(monkeypatch, tmp_path):
    state, actions = _position()
    game = _labeled(state, actions, state, chosen=0)
    ticks = iter(range(0, 10**12, 400_000_000))
    record = forecast_menu(state, _menu(actions), TEXTS, ObservedContext(), budget_ms=500, clock=lambda: next(ticks))
    assert record["not_computed"] > 0 and record["computed"] > 0
    row = {"event": "OUTCOME_SHADOW", "decision_id": f"{'g' * 64}:1:1:{'s' * 64}", "match_id": "g" * 64, "options_id": 1,
           "seq": 1, "state_hash": "s" * 64, "schema": shadow_module.SHADOW_SCHEMA, "coverage": "COMPLETE", "context": {}, **record}
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    report = verify_recordings(group_decisions([row]), {("g" * 64)[:16]: [tmp_path]}, CATALOG, TEXTS)
    assert report["reproduction"]["action_digest_match"] == record["computed"]
    assert report["reproduction"]["action_digest_mismatch"] == 0


def test_a_gift_at_rank_three_counts_as_inside_the_top_three_and_a_missing_top3_alternative_is_visible(monkeypatch, tmp_path):
    texts = TextSource.from_records([
        {"id": "T_HEAL", "type": "SPELL", "mechanics": [], "text": "Restore #4 Health."},
        {"id": "A", "type": "MINION", "mechanics": [], "text": ""}, {"id": "B", "type": "MINION", "mechanics": [], "text": ""}])
    ctx = ObservedContext(healing_does_damage=False, healing_bonus=0, spell_healing_doubled=False)
    state = sc.position(self_side=sc.side(mana=5, board=(sc.minion("B", 2, 2, 1),)),
                        opponent=sc.side(board=(sc.minion("A", 3, 5, 1, max_health=7), sc.minion("A", 3, 5, 2, max_health=7),
                                                sc.minion("A", 3, 5, 3, max_health=7))),
                        hand=(sc.hand_card("T_HEAL", "SPELL", 1),))
    heals = [sc.play("T_HEAL", 0, "SPELL", 1, sc.target_minion("OPPONENT", n, "A")) for n in (1, 2, 3)]
    game = _labeled(state, [*heals, sc.end_turn()], state, chosen=3)
    row = _rows_for(state, [*heals, sc.end_turn()], context=ctx)
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    monkeypatch.setattr("manamind.outcome.shadow_analysis.context_from_observed", lambda facts, state: ctx)
    gifts = verify_recordings(group_decisions([row]), {("g" * 64)[:16]: [tmp_path]}, CATALOG, texts)["opponent_only_improvement"]
    assert gifts["gift_inside_policy_top3"] == 1 and gifts["policy_top1_is_one"] == 1
    assert gifts["policy_top1_gift_with_non_gift_in_top3"] == 0              # the only non-gift sits at rank 4
    assert gifts["policy_top1_gift_replacement_is_players_choice"] == 1
    assert gifts["without_gifts_players_choice_enters_top1"] == 1


def test_a_gift_exactly_at_rank_three_is_inside_the_top_three(monkeypatch, tmp_path):
    texts = TextSource.from_records([
        {"id": "T_HEAL", "type": "SPELL", "mechanics": [], "text": "Restore #4 Health."},
        {"id": "A", "type": "MINION", "mechanics": [], "text": ""}, {"id": "B", "type": "MINION", "mechanics": [], "text": ""}])
    ctx = ObservedContext(healing_does_damage=False, healing_bonus=0, spell_healing_doubled=False)
    state = sc.position(self_side=sc.side(mana=5, board=(sc.minion("B", 2, 2, 1),)),
                        opponent=sc.side(board=(sc.minion("A", 3, 5, 1, max_health=7),)),
                        hand=(sc.hand_card("T_HEAL", "SPELL", 1),))
    actions = [sc.end_turn(), sc.attack(1, "B", sc.target_minion("OPPONENT", 1, "A")),
               sc.play("T_HEAL", 0, "SPELL", 1, sc.target_minion("OPPONENT", 1, "A"))]
    game = _labeled(state, actions, state, chosen=0)
    row = _rows_for(state, actions, context=ctx)
    monkeypatch.setattr("manamind.outcome.shadow_analysis.label_recording", lambda directory, catalog: ({"g" * 64: game}, None))
    monkeypatch.setattr("manamind.outcome.shadow_analysis.context_from_observed", lambda facts, state: ctx)
    gifts = verify_recordings(group_decisions([row]), {("g" * 64)[:16]: [tmp_path]}, CATALOG, texts)["opponent_only_improvement"]
    assert gifts["gift_inside_policy_top3"] == 1 and "policy_top1_is_one" not in gifts
