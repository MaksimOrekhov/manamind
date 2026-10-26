"""CARD-IR-EXECUTION-PILOT-1 through the built native ManaEngine.

Scenario expectations are hand-written in reports/card_ir_execution_pilot_1/scenarios.py; this file checks that a
fresh run reproduces the committed RESULTS.json and covers the bridge's own guards and isolation.
"""
from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from manamind.card_ir.engine_translate import TranslationRefused, translate
from manamind.integrations.manaengine import ManaEngineSession, SimulationOutcome, attempt_action

ROOT = Path(__file__).resolve().parents[3]
HERE = ROOT / "reports/card_ir_execution_pilot_1"


def _load(name):
    sys.path.insert(0, str(HERE))
    try:
        spec = importlib.util.spec_from_file_location(f"native_execution_pilot_{name}", HERE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(HERE))


PILOT = _load("pilot")
SC = sys.modules["scenarios"]  # imported by pilot.py from its own directory
build_catalog, start_session = PILOT.build_catalog, PILOT.start_session  # reports/.../engine_bridge.py
FILLER = SC.FILLER
DECK = [SC.BOLT] + [FILLER] * 29


@pytest.fixture(scope="module")
def runner():
    return PILOT.Runner()


def _bolt_damage(session) -> int:
    action = next(a for a in session.legal_actions() if a.get("card_id") == SC.BOLT and a["target_is_hero"]
                  and not a["target_is_self"])
    attempt = attempt_action(session, action, perspective="PLAYER1")
    assert attempt.outcome == SimulationOutcome.COMPLETED
    return 30 - attempt.state.opponent.hero_health


def test_fresh_run_reproduces_the_committed_results():
    fresh = PILOT.build()
    committed = json.loads((HERE / "RESULTS.json").read_text(encoding="utf-8"))
    assert fresh == committed


def test_session_wrapper_matches_an_ordinary_session(runner):
    ordinary = ManaEngineSession(DECK, [FILLER] * 30, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    bridged = start_session(runner.catalog(), DECK, [FILLER] * 30, player1_class="MAGE", player2_class="MAGE")
    assert set(vars(bridged)) == set(vars(ordinary))
    assert bridged.training_eligible is False and bridged.evidence_constraints == ()
    assert bridged.observation("PLAYER1") == ordinary.observation("PLAYER1")


def test_an_ir_catalog_never_leaks_into_the_default_catalog(runner):
    mutation = SC.MUTATIONS["M-amount"]
    doc = copy.deepcopy(runner.declared[mutation.card])
    mutation.change(doc)
    mutated = start_session(runner.catalog({SC.BOLT: translate(doc)}), DECK, [FILLER] * 30,
                            player1_class="MAGE", player2_class="MAGE")
    ordinary = ManaEngineSession(DECK, [FILLER] * 30, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    assert (_bolt_damage(mutated), _bolt_damage(ordinary)) == (5, 3)


def test_bridge_refuses_cards_it_cannot_install(runner):
    bolt = runner.specs[SC.BOLT]
    with pytest.raises(TranslationRefused) as caught:
        build_catalog([dataclasses.replace(bolt, card_id="NOT_A_CARD_1")])
    assert caught.value.code == "CARD_NOT_IN_ENGINE_CATALOG"
    with pytest.raises(TranslationRefused) as caught:
        build_catalog([dataclasses.replace(bolt, text_sha256="0" * 64)])
    assert caught.value.code == "ENGINE_TEXT_MISMATCH"
    with pytest.raises(TranslationRefused) as caught:
        build_catalog([dataclasses.replace(bolt, card_id=SC.RAZORJAW)])
    assert caught.value.code == "CARD_TYPE"
    with pytest.raises(TranslationRefused) as caught:
        build_catalog([bolt, bolt])
    assert caught.value.code == "DUPLICATE_CARD"


def test_alternative_actions_from_one_parent_do_not_interfere(runner):
    session = start_session(runner.catalog(), DECK, [FILLER] * 30, player1_class="MAGE", player2_class="MAGE")
    before = session.observation("PLAYER1")
    actions = [a for a in session.legal_actions() if a.get("card_id") == SC.BOLT]
    results = [attempt_action(session, a, perspective="PLAYER1").state for a in actions]
    assert sorted((s.self_player.hero_health, s.opponent.hero_health) for s in results) == [(27, 30), (30, 27)]
    assert session.observation("PLAYER1") == before and session.is_valid
