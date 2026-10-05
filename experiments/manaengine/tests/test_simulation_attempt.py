"""Real native clone/action/evidence boundary checks for Phase 4K.1."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

from manamind.integrations.manaengine import (
    AttemptReason, ManaEngineSession, SimulationOutcome, UnsupportedSimulationError,
    acting_seat, attempt_action,
)
from manamind.integrations.manaengine.engine import _definition_rows, _load_native
from manamind.integrations.manaengine.pool_manifest import load_dark_gift_option_manifest

ROOT = Path(__file__).resolve().parents[3]
FILLER = "CORE_EX1_145"
FIRE = ("FIRE_POOL_MEMBERSHIP_INFERRED",)


def session(deck=None, opponent=None, seed=0):
    return ManaEngineSession(deck or ["CORE_DRG_107"] * 30, opponent or [FILLER] * 30,
                             player1_class="MAGE", player2_class="MAGE", shuffle=False, random_seed=seed)


def end(parent):
    return next(a for a in parent.legal_actions() if a["type"] == "END_TURN")


def snapshot(parent):
    return (parent.observation("PLAYER1"), parent.observation("PLAYER2"), parent.legal_actions(),
            parent.evidence_constraints, parent.is_valid, parent.diagnostic_trace)


def test_sa01_sa02_sa03_supported_attempt_parent_unchanged_and_retained_branch():
    parent = session()
    parent.set_diagnostic_trace(True)
    action = next(a for a in parent.legal_actions() if a["type"] == "PLAY_CARD")
    before = snapshot(parent)
    result = attempt_action(parent, action)
    assert result.completed and result.perspective == "PLAYER1"
    assert len(result.state.self_player.board) == 1 and len(before[0].self_player.board) == 0
    assert result.child is not parent and snapshot(parent) == before
    followup = attempt_action(result.child, end(result.child), perspective=result.perspective)
    assert followup.completed and followup.state.active_player == "OPPONENT"
    assert snapshot(parent) == before and result.child.observation("PLAYER1") == result.state


def test_sa04_sa15_sa23_sa24_end_turn_fixed_root_and_existing_apply_active_view():
    parent = session()
    p1_hand = parent.observation("PLAYER1").self_hand
    assert acting_seat(parent) == "PLAYER1"
    result = attempt_action(parent, end(parent))
    assert result.perspective == "PLAYER1" and result.state.active_player == "OPPONENT"
    assert result.state.self_hand == p1_hand
    assert result.state.opponent_known_cards == ()
    assert FILLER not in json.dumps(asdict(result.state))
    assert result.state.opponent.hand_size > 0
    assert acting_seat(result.child) == "PLAYER2"
    explicit = attempt_action(parent, end(parent), perspective="PLAYER2")
    assert explicit.completed and explicit.state.active_player == "SELF"
    assert all(card.card_id in {FILLER, "GAME_005"} for card in explicit.state.self_hand)
    direct = parent.clone()
    active_state = direct.apply_action(end(direct))
    assert active_state == direct.observation("PLAYER2")
    assert active_state != result.state
    assert direct.observation("PLAYER1") == result.state


def plume_parent(seed):
    parent = session(["CATA_488", *([FILLER] * 29)], seed=seed)
    parent.set_diagnostic_trace(True)
    for _ in range(24):
        # Keep room for both real Plume samples using ordinary supported plays.
        # Passing every turn fills the hand and tests the pre-RNG capacity guard instead.
        while True:
            filler = next((a for a in parent.legal_actions() if a.get("card_id") in {FILLER, "GAME_005"}), None)
            if filler is None:
                break
            parent.apply_action(filler)
        action = next((a for a in parent.legal_actions() if a.get("card_id") == "CATA_488"), None)
        if action is not None:
            parent.apply_action(action)
            return parent
        parent.apply_action(end(parent))
    pytest.fail("Vulcanos did not become playable within fixture bound")


def test_sa02_sa05_sa06_sa07_sa08_sa12_sa13_sa14_real_fire_seed_scan():
    manifest = json.loads((ROOT / "experiments/manaengine/data/pools/fire_spell_standard_253932_inferred_v1.json").read_text())
    found = set()
    for seed in range(128):
        parent = plume_parent(seed)
        before = snapshot(parent)
        action = end(parent)
        result = attempt_action(parent, action)
        repeated = attempt_action(parent, action)
        assert result == repeated and snapshot(parent) == before
        assert parent.is_valid and parent.evidence_constraints == ()
        direct = parent.clone()
        if result.completed:
            direct.apply_action(action)
            assert result.state == direct.observation(result.perspective)
            assert result.child.diagnostic_trace == direct.diagnostic_trace
            assert result.state.evidence_constraints == result.evidence_constraints == result.child.evidence_constraints == FIRE
            assert not result.fallback_eligible and result.has_evidence_debt
            assert not result.child.training_eligible
            with pytest.raises(UnsupportedSimulationError):
                result.child.require_training_admission()
            found.add("completed")
        else:
            assert result.outcome == SimulationOutcome.UNSIMULATABLE
            assert result.reason == AttemptReason.NATIVE_UNSUPPORTED and result.fallback_eligible
            assert result.state is result.child is None and result.evidence_constraints == ()
            assert result.diagnostics.evidence_at_failure == FIRE
            match = re.search(r"selected generated outcome is unsupported: (\w+)", result.diagnostics.unsupported_outcome)
            assert match and match.group(1) in manifest["card_ids"]
            sample_rows = [row for row in result.diagnostics.trace_tail if row.startswith("POOL_SAMPLE ")]
            # Two distinct Plumes may each sample once; the failing sample is
            # final, not rerolled into a supported alternative.
            assert 1 <= len(sample_rows) <= 2 and f"card={match.group(1)}" in sample_rows[-1]
            with pytest.raises(UnsupportedSimulationError):
                direct.apply_action(action)
            assert not direct.is_valid and direct.unsupported_outcome == result.diagnostics.unsupported_outcome
            assert direct.diagnostic_trace[-32:] == result.diagnostics.trace_tail
            found.add("unsupported")
        # Reusing this root after attempts produces the same RNG-derived outcome.
        assert snapshot(parent) == before
        if found == {"completed", "unsupported"}:
            break
    assert found == {"completed", "unsupported"}, "bounded scan must see both real Fire paths"


def test_sa09_sa10_sa19_illegal_and_state_only_native_attempts():
    parent = session()
    before = snapshot(parent)
    for malformed in ({"type": "END_TURN", "target_entity_id": True}, {"type": "PLAY_CARD", "hand_index": "0"}):
        result = attempt_action(parent, malformed)
        assert result.reason == AttemptReason.ILLEGAL_MALFORMED and not result.fallback_eligible
    for illegal in ({"type": "PLAY_CARD", "hand_index": 999},
                    {"type": "HERO_POWER", "target_entity_id": 999}, {"type": "CHOOSE_CARD", "choice_index": 9}):
        result = attempt_action(parent, illegal)
        assert result.reason == AttemptReason.ILLEGAL_NOT_LEGAL and not result.fallback_eligible
    state_only = attempt_action(parent, end(parent), retain_child=False)
    retained = attempt_action(parent, end(parent))
    assert state_only.child is None and state_only.state == retained.state
    assert snapshot(parent) == before


def test_sa16_hidden_unsupported_next_draw_only_poisons_clone():
    parent = session(opponent=[FILLER] * 4 + ["TLC_222"] + [FILLER] * 25)
    before = snapshot(parent)
    result = attempt_action(parent, end(parent))
    assert result.outcome == SimulationOutcome.UNSIMULATABLE and result.reason == AttemptReason.NATIVE_UNSUPPORTED
    assert result.state is result.child is None and result.fallback_eligible
    assert "unsupported" in result.diagnostics.unsupported_outcome.lower()
    assert snapshot(parent) == before


def assert_native_keys_and_attempts(parent):
    expected = {}
    for action in parent._native.legal_actions():
        # Independent native defaults from Action in engine.hpp, not from the Python helper.
        key = (action["type"], *(action.get(name, -1) for name in (
            "hand_index", "attacker_entity_id", "target_entity_id", "choice_index")), action.get("choose_one", 0))
        expected[key] = dict(action)
    assert parent._legal_execution_keys() == expected
    for key, action in expected.items():
        caller = {"type": key[0], "hand_index": key[1], "attacker_entity_id": key[2],
                  "target_entity_id": key[3], "choice_index": key[4], "choose_one": key[5],
                  "card_cost": object(), "card_id": ["malformed caller metadata"]}
        result = attempt_action(parent, caller)
        assert result.completed, (action, result)
        direct = parent.clone()
        direct._apply_raw(action)
        assert direct.observation(result.perspective) == result.state
    return {key[0] for key in expected}


def test_sa17_native_execution_equal_shapes_and_choose_one():
    ordinary = session()
    types = assert_native_keys_and_attempts(ordinary)
    ordinary.apply_action(next(a for a in ordinary.legal_actions() if a["type"] == "PLAY_CARD"))
    ordinary.apply_action(end(ordinary))
    ordinary.apply_action(end(ordinary))
    types |= assert_native_keys_and_attempts(ordinary)
    choice = session(["CORE_AT_037"] * 30)
    choice.apply_action(next(a for a in choice.legal_actions() if a["type"] == "PLAY_CARD"))
    types |= assert_native_keys_and_attempts(choice)
    mode = next(a for a in choice.legal_actions() if a["choose_one"] == 1)
    missing_mode = {k: v for k, v in mode.items() if k != "choose_one"}
    assert attempt_action(choice, missing_mode).reason == AttemptReason.ILLEGAL_NOT_LEGAL
    choice.apply_action(mode)
    types |= assert_native_keys_and_attempts(choice)
    assert types == {"PLAY_CARD", "END_TURN", "ATTACK", "HERO_POWER", "CHOOSE_CARD"}


def test_sa17_prepare_execution_key_with_test_only_native_catalog():
    native = _load_native()
    filler, power, prepared = (native.CardDefinition() for _ in range(3))
    filler.card_id, filler.card_type, filler.support_state = "TEST_FILLER", "SPELL", "VERIFIED_VANILLA"
    power.card_id, power.card_type, power.ability, power.cost = "HERO_08bp", "HERO_POWER", "TARGET_DAMAGE", 2
    power.damage, power.support_state = 1, "SUPPORTED"
    prepared.card_id, prepared.card_type, prepared.ability = "TEST_PREPARE", "SPELL", "TARGET_DAMAGE"
    prepared.cost, prepared.damage, prepared.prepare, prepared.support_state = 5, 2, True, "SUPPORTED"
    for row in (filler, power, prepared):
        row.rules_contract_reviewed = True
    deck = ["TEST_PREPARE"] + ["TEST_FILLER"] * 29
    parent = object.__new__(ManaEngineSession)
    parent._unsupported_exception, parent._card_metadata = native.UnsupportedSimulationError, {}
    parent._native = native.GameSession(deck, deck, native.CardCatalog([filler, power, prepared]), 13, False, "MAGE", "MAGE")
    action = next(a for a in parent.legal_actions() if a["type"] == "PREPARE_CARD")
    before = snapshot(parent)
    result = attempt_action(parent, {"type": "PREPARE_CARD", "hand_index": action["hand_index"]})
    assert result.completed and result.state.self_hand[0].prepare_locked
    assert snapshot(parent) == before


def test_sa18_complete_native_match_rejects_action_without_clone():
    parent = session([FILLER] * 30)
    for _ in range(200):
        if parent.is_complete:
            break
        parent.apply_action(end(parent))
    assert parent.is_complete
    before = snapshot(parent)
    result = attempt_action(parent, {"type": "END_TURN"})
    assert result.reason == AttemptReason.ILLEGAL_NOT_LEGAL and snapshot(parent) == before


def test_sa11_actual_postmutation_std_exception_is_engine_defect():
    native = _load_native()
    definitions = _definition_rows()
    secret = next(d for d in definitions if d.card_id == "CORE_LOOT_101")
    secret.ability, secret.support_state, secret.rules_contract_reviewed = "NONE", "VERIFIED_VANILLA", True
    secret.required_mechanics, secret.cost, secret.secret = [], 1, True
    secret.secret_trigger, secret.secret_effect = "OPPONENT_PLAYS_MINION", "INVALID_TEST_EFFECT"
    dark = load_dark_gift_option_manifest(
        ROOT / "experiments/manaengine/data/pools/dark_gift_launch_review_20261004_v1.json",
        ROOT / "experiments/manaengine/data/dark_gift_option_metadata.json",
    ).to_native(native)
    deck = ["CORE_LOOT_101"] + ["CORE_DRG_107"] * 29
    parent = session(deck, ["CORE_DRG_107"] * 30)
    parent._native = native.GameSession(deck, ["CORE_DRG_107"] * 30,
                                      native.CardCatalog(definitions, [], "", "", [dark]), 31, False, "MAGE", "MAGE")
    parent.apply_action(next(a for a in parent.legal_actions() if a.get("card_id") == "CORE_LOOT_101"))
    parent.apply_action(end(parent))
    action = next(a for a in parent.legal_actions() if a.get("card_id") == "CORE_DRG_107")
    before = snapshot(parent)
    result = attempt_action(parent, action)
    assert result.outcome == SimulationOutcome.ENGINE_DEFECT
    assert result.reason == AttemptReason.NATIVE_EXCEPTION_NORMALIZED and not result.fallback_eligible
    assert result.state is result.child is None
    assert "unknown Secret effect" in result.diagnostics.exception_message
    assert "action failed after mutation: " in result.diagnostics.unsupported_outcome
    assert snapshot(parent) == before
