"""ML-PREPARE-TRAIN-1 analysis helpers: decision categories, paired bootstrap over matches and the registered verdict rules."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import ml_prepare_analyze as analysis  # noqa: E402
from test_policy_prepare_data import PLAY_AND_PREPARE, CHEAP_ONLY, prepare_rows, v1_row  # noqa: E402
from test_real_policy_dataset import CATALOG  # noqa: E402

from manamind.encoding.state_encoder import StateEncoder  # noqa: E402


def test_menu_categories_and_the_choice_flags():
    both, = prepare_rows(roots=PLAY_AND_PREPARE)
    only, = prepare_rows(seed=2, roots=CHEAP_ONLY)
    plain = v1_row()
    facts = [analysis.decision_facts(r) for r in (both, only, plain)]
    assert [f["category"] for f in facts] == ["play_and_prepare", "prepare_only", "no_prepare"]
    assert [f["has_prepare"] for f in facts] == [True, True, False]
    assert facts[0]["chose_prepare"] and facts[0]["chosen_prepare_card"] == both["legal_actions"][both["chosen_action_index"]]["card_id"]
    assert not facts[2]["chose_prepare"] and facts[2]["chosen_prepare_card"] is None


def test_record_matches_the_closed_form_for_a_flat_menu():
    row, = prepare_rows()
    n = len(row["legal_actions"])
    result = analysis.record(row, analysis.decision_facts(row), [0.0] * n)
    assert result["loss"] == pytest.approx(math.log(n))
    assert result["rank"] == row["chosen_action_index"] + 1  # ties break by menu order, like policy_metrics
    prepare_actions = sum(a["type"] == "PREPARE_CARD" for a in row["legal_actions"])
    assert result["prepare_mass"] == pytest.approx(prepare_actions / n)


def records(losses, top1=None):
    return [{"loss": x, "top1": bool(top1[i]) if top1 else x < 1, "rr": 1.0, "top3": None} for i, x in enumerate(losses)]


def test_paired_bootstrap_resamples_matches_and_is_exact_for_a_constant_shift():
    facts = [{"game_id": g} for g in "AABBBCCD"]
    base = records([1.0] * 8)
    shifted = records([1.5] * 8)
    mask = np.ones(8, dtype=bool)
    result = analysis.paired_bootstrap(facts, shifted, base, mask)
    assert result["matches"] == 4 and result["decisions"] == 8
    assert result["cross_entropy"]["difference"] == pytest.approx(0.5)
    assert result["cross_entropy"]["ci95"] == pytest.approx([0.5, 0.5])
    assert analysis.paired_bootstrap(facts, shifted, base, mask) == result  # fixed seed
    assert analysis.paired_bootstrap(facts, base, base, mask)["cross_entropy"]["ci95"] == [0.0, 0.0]
    assert analysis.paired_bootstrap(facts, shifted, base, np.zeros(8, dtype=bool)) == {}


def test_bootstrap_interval_widens_when_matches_disagree():
    facts = [{"game_id": g} for g in "AABBCCDD"]
    first = records([1.0, 1.0, 2.0, 2.0, 1.0, 1.0, 2.0, 2.0])
    second = records([1.5] * 8)
    spread = analysis.paired_bootstrap(facts, first, second, np.ones(8, dtype=bool))["cross_entropy"]
    assert spread["difference"] == pytest.approx(0.0)
    assert spread["ci95"][0] < 0 < spread["ci95"][1]


def test_seed_average_is_the_mean_of_per_seed_metrics():
    a, b = records([1.0, 3.0]), records([2.0, 5.0])
    mean = analysis.averaged([a, b])
    assert [r["loss"] for r in mean] == [1.5, 4.0]


def synthetic_report(prepare_diff=-0.3, prepare_ci=(-0.5, -0.1), other_diff=0.0, other_ci=(-0.03, 0.03),
                     top1_prepare=15, seeds=(42, 43, 44)):
    def entry(diff, ci):
        return {"cross_entropy": {"difference": diff, "ci95": list(ci)}}
    differences, per_seed = {}, {}
    for scope in ("pooled", "validation", "test"):
        differences[f"{scope}/prepare_in_menu"] = entry(prepare_diff, prepare_ci)
        differences[f"{scope}/no_prepare_in_menu"] = entry(other_diff, other_ci)
        for s in seeds:
            per_seed[f"{scope}/prepare_in_menu/seed{s}"] = {"cross_entropy": prepare_diff}
    report = {"paired": {"v2": {"seeds": list(seeds), "differences": differences, "per_seed": per_seed}},
              "behaviour": {f"prepare_v2_s{s}": {"pooled": {"prepare_menu_top1_prepare": top1_prepare,
                                                              "prepare_menu_decisions": 100}} for s in seeds},
              "player_prepare_rate_in_prepare_menus": {"pooled": {"chose_prepare": 0.1}}}
    return report


def test_registered_verdict_rules_are_applied_mechanically():
    assert analysis.verdict(synthetic_report(), (42, 43, 44))["architectures"]["v2"]["verdict"] == "PROMISING"
    assert analysis.verdict(synthetic_report(), (42, 43, 44))["overall"] == "PROMISING"
    unsure = analysis.verdict(synthetic_report(prepare_ci=(-0.5, 0.1)), (42, 43, 44))
    assert unsure["architectures"]["v2"]["verdict"] == "INCONCLUSIVE" and unsure["overall"] == "INCONCLUSIVE"
    noisy = analysis.verdict(synthetic_report(other_diff=0.04, other_ci=(-0.01, 0.06)), (42, 43, 44))
    assert noisy["architectures"]["v2"]["N1"] is False and noisy["overall"] == "INCONCLUSIVE"
    spammy = analysis.verdict(synthetic_report(top1_prepare=35), (42, 43, 44))
    assert spammy["architectures"]["v2"]["verdict"] == "REGRESSION" and spammy["overall"] == "REGRESSION"
    worse = analysis.verdict(synthetic_report(other_diff=0.06, other_ci=(0.02, 0.1)), (42, 43, 44))
    assert worse["overall"] == "REGRESSION"
    assert analysis.verdict(synthetic_report(), (42, 43, 44))["live_switch_authorised"] is False


def test_encoding_check_passes_on_real_menus_and_fails_when_the_flag_is_missing(monkeypatch):
    row, = prepare_rows(roots=PLAY_AND_PREPARE)
    encoder = StateEncoder(CATALOG)
    ok = analysis.encoding_check([row], encoder)
    assert ok["verdict"] == "PASS" and ok["prepare_actions"] == 1 and ok["play_prepare_pairs_of_one_hand_card"] >= 1
    monkeypatch.setattr(analysis, "PREPARE_FEATURE", analysis.PREPARE_FEATURE + 1)
    assert analysis.encoding_check([copy.deepcopy(row)], encoder)["verdict"] == "FAIL"


def test_integrity_check_flags_a_hand_card_mismatch():
    row, = prepare_rows()
    good = {row["decision_id"]: [0.0] * len(row["legal_actions"])}
    assert analysis.integrity([row], {"m": good}, None)["verdict"] == "PASS"
    broken = copy.deepcopy(row)
    broken["state"]["self_hand"][0]["card_id"] = "OTHER_CARD"
    assert analysis.integrity([broken], {"m": good}, None)["verdict"] == "FAIL"
    short = {row["decision_id"]: [0.0]}
    assert analysis.integrity([row], {"m": short}, None)["verdict"] == "FAIL"
