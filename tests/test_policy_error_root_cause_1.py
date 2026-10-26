"""Privacy boundaries and control selection for the read-only audit."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import policy_error_root_cause_1 as audit  # noqa: E402


def test_protected_identity_and_raw_prefix_are_rejected():
    held = {"a" * 64}
    with pytest.raises(ValueError, match="protected"):
        audit.require_disjoint(held, held)
    with pytest.raises(ValueError, match="protected"):
        audit.require_disjoint({"a" * 16 + "b" * 48}, held)
    audit.require_disjoint({"b" * 64}, held)


def _record(case, ordinal, policy_ok, scorer_bad):
    return {
        "case": case, "ordinal": ordinal, "game_id": "PRIVATE_CANARY",
        "labels": {"comment": "PRIVATE_CANARY"}, "state": {"hidden": "PRIVATE_CANARY"},
        "policy_ranking": [0, 1], "scorer_ranking": [1, 0],
        "entity_unknown": 3, "entity_total": 5,
        "cards": {"card": {"vocabulary_index": 1}},
        "candidate_label_collisions": [], "menu_invariance_error": 0.0,
        "actions": [
            {"action": {"type": "ATTACK", "source_card_id": "card"},
             "acceptable": policy_ok, "blunder": not policy_ok},
            {"action": {"type": "PLAY_CARD", "card_type": "SPELL", "source_card_id": "TLC_451"},
             "acceptable": not scorer_bad, "blunder": scorer_bad},
        ],
    }


def test_public_projection_drops_sensitive_payload_and_excludes_synthetic_heroes():
    result = audit.aggregate([_record("E01", 1, False, False), _record("C01", 2, True, True)])
    assert "PRIVATE_CANARY" not in json.dumps(result)
    assert "state" not in result and "game_id" not in result
    assert result["errors"]["nonhero_unknown_tokens"] == 1
    assert result["errors"]["nonhero_tokens"] == 3
    assert result["paired_scorer"]["fixes_policy_blunder_with_acceptable"] == 1
    assert result["paired_scorer"]["policy_acceptable_to_scorer_blunder"] == 1


def test_controls_follow_frozen_ordinal_even_if_input_is_reordered():
    first = _record("C01", 1, True, False)
    later = _record("C02", 2, True, False)
    error = _record("E01", 3, False, True)
    left = audit.aggregate([later, error, first])["controls_selected"]
    right = audit.aggregate([first, later, error])["controls_selected"]
    assert left == right
    assert left["both_acceptable"] == "C01"
    assert left["attack_with_available_draw_discover_or_buff"] == "C01"


def test_exact_action_comparison_keeps_attacker_target_and_ordered_hand():
    action = {"type": "PLAY_CARD", "source_card_id": "card", "hand_index": 0,
              "target_board_position": 1, "play_position": 1}
    assert audit.exact_signature(action) == audit.exact_signature(dict(action, play_position=2))
    assert audit.exact_signature(action) != audit.exact_signature(dict(action, hand_index=1))
    assert audit.exact_signature(action) != audit.exact_signature(dict(action, target_board_position=2))
