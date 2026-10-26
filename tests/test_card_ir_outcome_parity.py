import copy
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from manamind.card_ir.engine_translate import translate
from manamind.outcome import scenario as sc
from manamind.outcome.forecast import forecast_action
from manamind.outcome.model import Status
from manamind.outcome.verify import LoggedDecision, score_pair

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "reports/card_ir_outcome_parity_1"
sys.path.insert(0, str(HERE))
try:
    spec = importlib.util.spec_from_file_location("parity_technical_tests", HERE / "technical.py")
    tech = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tech)
    from adapter import IRRun, forecast_ir
    from data_access import AllowedData
    from parity import direct_ready, score_section
    from scoring import score_precomputed
finally:
    sys.path.remove(str(HERE))


@pytest.fixture(scope="module")
def assets():
    return tech.resources()


@pytest.mark.parametrize("card", ["CORE_EX1_238", "CORE_AT_055", "CORE_ICC_055"])
def test_ir_and_text_share_resolver_on_fully_observed_positions(assets, card):
    meta, docs, texts = assets
    state, action = tech.position(card)
    before = copy.deepcopy(state)
    ctx = tech.complete_context()
    ir = forecast_ir(state, action, texts, ctx, docs[card], meta)
    baseline = forecast_action(state, action, texts, ctx)
    assert [(c.ref, c.field, c.after) for c in ir.changes] == [(c.ref, c.field, c.after) for c in baseline.changes]
    assert state == before


def test_public_ir_path_does_not_parse_original_own_card_text(assets):
    meta, docs, texts = assets
    card = "CORE_EX1_238"
    state, action = tech.position(card)
    misleading = texts.extended([dict(id=card, text="Draw seven cards.", type="SPELL", mechanics=[])])
    ir = forecast_ir(state, action, misleading, tech.complete_context(), docs[card], meta)
    baseline = forecast_action(state, action, misleading, tech.complete_context())
    assert ir.partial_state().diagnostic_state().opponent.board[0].current_health == 6  # partial only for Overload debt
    assert not [e for e in baseline.events if e.kind == "DAMAGE"]


def test_five_controlled_mutations_depend_on_ir():
    result = tech.build()
    assert result["real_events"] == 0
    assert len(result["cases"]) == 5
    assert result["all_public_gates_refuse"] and result["all_compiled_probes_change_or_refuse"]
    assert result["cases"][0]["compiled_probe"]["view"]["events"][-1]["amount"] == 5


def test_lifesteal_removal_overrides_printed_metadata_in_compiled_probe(assets):
    _, docs, texts = assets
    card = "CORE_ICC_055"
    state, action = tech.position(card)
    ctx = tech.complete_context()
    original = IRRun(state, action, texts, ctx, translate(docs[card])).run()
    doc = copy.deepcopy(docs[card]); doc["keywords"] = []
    removed = IRRun(state, action, texts, ctx, translate(doc)).run()
    assert original.exact_state().self_player.hero_health == 23
    assert removed.exact_state().self_player.hero_health == 20


@pytest.mark.parametrize("shield,immune", [(True, False), (False, True)])
def test_prevention_and_lifesteal_use_existing_damage_primitive(assets, shield, immune):
    meta, docs, texts = assets
    state, action = tech.position("CORE_ICC_055")
    state = replace(state, opponent=replace(state.opponent, board=(replace(state.opponent.board[0], divine_shield=shield, immune=immune),)))
    out = forecast_ir(state, action, texts, tech.complete_context(), docs["CORE_ICC_055"], meta)
    assert out.exact_state().self_player.hero_health == 20
    assert out.exact_state().opponent.board[0].current_health == 9


def test_overkill_lifesteal_and_healing_cap(assets):
    meta, docs, texts = assets
    state, action = tech.position("CORE_ICC_055", target_health=1, self_health=28)
    out = forecast_ir(state, action, texts, tech.complete_context(), docs["CORE_ICC_055"], meta)
    assert out.exact_state().opponent.board == ()
    assert out.exact_state().self_player.hero_health == 30
    assert any(e.kind == "DAMAGE" and e.amount == 3 for e in out.events)


def test_healing_bonus_doubling_and_missing_modifier_are_not_defaulted(assets):
    meta, docs, texts = assets
    state, action = tech.position("CORE_AT_055", target_health=2, target_max=30)
    ctx = tech.complete_context(healing_bonus=2, spell_healing_doubled=True)
    state = replace(state, self_player=replace(state.self_player, healing_bonus=None))
    out = forecast_ir(state, action, texts, ctx, docs["CORE_AT_055"], meta)
    assert out.exact_state().opponent.board[0].current_health == 16  # 2+(5+2)*2
    unknown = forecast_ir(state, action, texts, replace(ctx, healing_bonus=None), docs["CORE_AT_055"], meta)
    assert unknown.status is Status.PARTIAL and unknown.bounded_changes and not direct_ready(unknown)
    conversion = forecast_ir(state, action, texts, replace(ctx, healing_does_damage=True), docs["CORE_AT_055"], meta)
    assert conversion.status is Status.UNSUPPORTED and conversion.unsupported_reason == "HEALING_DOES_DAMAGE_ACTIVE"


def test_armor_spell_damage_and_overload_remain_separate(assets):
    meta, docs, texts = assets
    state, action = tech.position("CORE_EX1_238")
    action = dict(action, **sc.target_hero("OPPONENT"))
    state = replace(state, opponent=replace(state.opponent, armor=7))
    out = forecast_ir(state, action, texts, tech.complete_context(spell_damage=2), docs["CORE_EX1_238"], meta)
    candidate = out.partial_state().diagnostic_state()
    assert candidate.opponent.armor == 2 and candidate.opponent.hero_health == 30
    assert any(u.tag == "IR_RESOURCE_OVERLOAD_UNMODELLED" for u in out.unknowns)


@pytest.mark.parametrize("nature,expected", [(0, 3), (1, 4), (2, 3)])
def test_overheat_order_and_random_payment_are_bounded(assets, nature, expected):
    meta, docs, texts = assets
    state, action = tech.position("FIR_906", nature=nature)
    out = forecast_ir(state, action, texts, tech.complete_context(), docs["FIR_906"], meta)
    result = out.exact_state() if out.status is Status.EXACT else out.partial_state().diagnostic_state()
    assert result.self_player.board[0].current_attack == expected
    if nature == 2:
        assert out.status is Status.PARTIAL and any(u.tag == "IR_DISCARD_RANDOM" for u in out.unknowns)


def _logged(state, action, number):
    return LoggedDecision("synthetic_game", number, f"synthetic_game:{number}", state, action, (action,))


def test_precomputed_scorer_matches_production_verify(assets):
    _, _, texts = assets
    state, action = tech.position("CORE_AT_055")
    ctx = tech.complete_context()
    forecast = forecast_action(state, action, texts, ctx)
    truth = forecast.exact_state()
    current, following = _logged(state, action, 1), _logged(truth, action, 2)
    a, b = score_precomputed(current, following, forecast), score_pair(current, following, texts, ctx)
    assert (a.confirmed, a.contradicted, a.missed) == (b.confirmed, b.contradicted, b.missed)
    wrong_truth = replace(truth, opponent=replace(truth.opponent, board=(replace(truth.opponent.board[0], current_health=10),)))
    changed = _logged(wrong_truth, action, 2)
    a, b = score_precomputed(current, changed, forecast), score_pair(current, changed, texts, ctx)
    assert (a.confirmed, a.contradicted, a.missed) == (b.confirmed, b.contradicted, b.missed)


def test_unsupported_is_not_zero_missed_success(assets):
    _, _, texts = assets
    state, action = tech.position("CORE_AT_055")
    forecast = forecast_action(state, action, texts, tech.complete_context(healing_does_damage=True))
    actual = replace(state, opponent=replace(state.opponent, board=(replace(state.opponent.board[0], current_health=4),)))
    result = score_section(_logged(state, action, 1), _logged(actual, action, 2), forecast)
    assert result["uncovered_observed_direct_changes"] == 1 and result["declared_uncovered_direct_changes"] == 1
    assert result["direct_confirmed"] == 0 and not result["direct_ready"]


def test_protected_and_unknown_files_are_excluded_before_open(tmp_path, monkeypatch):
    plan = tmp_path / "data/processed_policy_prepare_1"
    plan.mkdir(parents=True)
    allowed, held, unknown = "a" * 64, "b" * 64, "c" * 64
    (plan / "split_plan.json").write_text(json.dumps(dict(parts=dict(train=[allowed], validation=[], test_seen=[], fresh_holdout=[held]))))
    dataset = plan / "dataset"; dataset.mkdir()
    (dataset / f"{allowed}.jsonl").write_text("")
    (dataset / f"{held}.jsonl").write_text("DO NOT READ")
    (dataset / f"{unknown}.jsonl").write_text("DO NOT READ")
    original = Path.read_bytes
    def guarded(path):
        assert path.stem not in (held, unknown)
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    games, _ = AllowedData(tmp_path).policy()
    assert set(games) == {allowed}


def test_isolation_keeps_experimental_adapter_outside_production():
    for folder in (ROOT / "src", ROOT / "apps", ROOT / "scripts"):
        for path in folder.rglob("*.py"):
            assert "card_ir_outcome_parity_1" not in path.read_text(encoding="utf-8")


def test_published_results_keep_unknowns_exclusions_and_packet_units_separate():
    result = json.loads((HERE / "RESULTS.json").read_text(encoding="utf-8"))
    assert result["analyzed_actions"] == 65 and result["identical_numerical_forecasts"] == 65
    assert result["summary"]["baseline"] == result["summary"]["candidate"]
    row = result["summary"]["candidate"]
    assert row["status"] == {"EXACT": 1, "PARTIAL": 36, "UNSUPPORTED": 28}
    assert row["next_state_pairs"] == 54
    assert row["checkable_exact_direct_events"] == 0 and row["exact_direct_claim_accuracy"] is None
    assert row["uncovered_observed_direct_changes"] == 31
    assert result["evidence"]["packet_summary"]["candidate"]["confirmed"] == 1
    assert result["by_card"]["FIR_906"]["candidate"]["actions"] == 0
    assert result["by_card"]["CORE_EX1_238"]["candidate"]["actions"] == 0
    text = json.dumps(result)
    for forbidden in ('"game_id":', '"decision_id":', '"BattleTag":', '"player_name":'):
        assert forbidden not in text


def test_no_resource_claim_is_treated_as_direct_effect_accuracy(assets):
    _, _, texts = assets
    state, action = tech.position("CORE_AT_055", target_health=20, target_max=20)
    ctx = tech.complete_context()
    forecast = forecast_action(state, action, texts, ctx)
    result = score_section(_logged(state, action, 1), _logged(forecast.exact_state(), action, 2), forecast)
    assert result["resource_confirmed"] > 0 and result["direct_confirmed"] == 0
