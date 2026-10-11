"""The demo scenarios and the CLI that prints them."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from manamind.outcome import ObservedContext, Status, TextSource, forecast_alternatives
from manamind.outcome import demo

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "cards" / "standard_current_enUS.json"
SYNTHETIC = ObservedContext(healing_does_damage=False, hand_keywords_match_card=True, trust_spell_damage=True)


def _forecasts(scenario: demo.Scenario):
    texts = demo.demo_texts(TextSource.from_files(CATALOG))
    return forecast_alternatives(scenario.state, scenario.actions, texts, SYNTHETIC)


def test_hold_them_off_scenario_alternatives_have_distinct_independent_outcomes():
    scenario = demo.hold_them_off()
    forecasts = _forecasts(scenario)
    assert [f.status for f in forecasts] == [Status.EXACT] * len(scenario.actions)
    outcomes = [tuple(sorted((c.ref.label(), c.field, c.after) for c in f.changes)) for f in forecasts]
    assert len(set(outcomes)) == len(outcomes)                       # every alternative is visibly different
    big = forecasts[0].after_state.opponent.board[0]
    assert (big.current_attack, big.current_health, big.max_health, big.lifesteal) == (11, 11, 11, True)
    fireball_on_big = forecasts[3]
    assert fireball_on_big.after_state.opponent.board[0].card.card_id == "DEMO_ENEMY_2_2"   # the 6/6 is gone
    assert forecasts[7].changes == ()                                # END_TURN changes nothing directly


def test_sequencing_scenarios_resolve_in_rules_order():
    shield, lifesteal, poison, regrant, battlecry = (_forecasts(s)[0] for s in demo.sequencing())
    assert not [c for c in shield.changes if c.ref.zone == "HERO"]            # shield absorbed, so 'if it dies' is off
    assert [c.after for c in lifesteal.changes if c.ref.zone == "HERO" and c.field == "health"] == [23]
    assert {c.ref.side for c in poison.changes if c.field == "present"} == {"SELF"}   # poison found no damage to use
    assert not [c for c in regrant.changes if c.field == "lifesteal"]
    assert battlecry.status is Status.PARTIAL


def test_cli_prints_the_comparison_and_json_for_the_default_scenario():
    script = ROOT / "scripts" / "action_outcome_demo.py"
    text = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8",
                          check=True, cwd=ROOT).stdout
    assert "Hold Them Off!" in text and "attack: 6 -> 11" in text and "lifesteal: False -> True" in text
    data = json.loads(subprocess.run([sys.executable, str(script), "--json"], capture_output=True, text=True,
                                     encoding="utf-8", check=True, cwd=ROOT).stdout)
    assert data[0]["forecasts"][0]["status"] == "EXACT"
