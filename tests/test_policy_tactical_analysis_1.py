from __future__ import annotations

import math

import pytest

from scripts.policy_tactical_analysis_1 import _probability_summary, _safe_action_label, _safe_effects


def test_probability_summary_tracks_prediction_and_player_action_separately():
    result = _probability_summary([2.0, 1.0, 0.0], chosen=1)
    expected = math.exp(1.0) / sum(math.exp(value) for value in (2.0, 1.0, 0.0))
    assert result["top_index"] == 0
    assert result["top1_matches_player"] is False
    assert result["chosen_probability"] == pytest.approx(expected)
    assert result["top3_probability_mass"] == pytest.approx(1.0)
    assert result["entropy_nats"] > 0


def test_probability_summary_fails_closed_on_invalid_logits_or_action():
    with pytest.raises(ValueError, match="invalid"):
        _probability_summary([float("nan"), 1.0], chosen=0)
    with pytest.raises(ValueError, match="invalid"):
        _probability_summary([1.0], chosen=1)


def test_public_action_labels_do_not_expose_card_or_entity_ids():
    action = {"type": "PLAY_CARD", "card_type": "MINION", "card_cost": 3,
              "card_id": "PRIVATE_CARD_ID", "entity_id": 4271}
    label = _safe_action_label(action)
    assert label == "PLAY_CARD (MINION, cost 3)"
    assert "PRIVATE_CARD_ID" not in label
    assert "4271" not in label


def test_public_effects_only_include_exact_sanitized_visible_changes():
    partial = {"status": "PARTIAL", "effects": [["SELF hero", "health", 30, 29]]}
    exact = {"status": "EXACT", "effects": [["OPPONENT hero", "health", 30, 29],
                                             ["card entity private-name", "secret_text", "a", "b"]]}
    assert _safe_effects(partial) == []
    assert _safe_effects(exact) == ["opponent hero health: 30→29"]
