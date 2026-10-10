import sys
from dataclasses import replace
from pathlib import Path

from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity, LocationEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.research.consequence_check import (
    DIRECT_EFFECT_PRESENT, NO_DIRECT_EFFECT, SIDE_NONE_VISIBLE, SIDE_POSSIBLE, SIDE_UNKNOWN, UNKNOWN, UNSUPPORTED,
    catalog_effects, catalog_texts, check_direct_effect, constrained_order, is_demotable,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from consequence_pilot_1 import observed_restore_evidence  # noqa: E402

RECORDS = [
    {"id": "HEAL", "type": "SPELL", "text": "Restore #5 Health."},
    {"id": "HEAL_DRAW", "type": "SPELL", "text": "Restore #4 Health.\nDraw a card."},
    {"id": "RUIN", "type": "SPELL", "text": "Destroy all minions with 5 or more Attack."},
    {"id": "VANILLA", "type": "MINION"},
    {"id": "SANCTUM", "type": "LOCATION", "text": "Your next Healing effect this turn deals damage instead."},
    {"id": "WYRM", "type": "MINION", "text": "Whenever you cast a spell, gain +1 Attack."},
]
EFFECTS = catalog_effects(RECORDS)
TEXTS = catalog_texts(RECORDS)


def minion(card_id="VANILLA", attack=2, health=3, maximum=3, position=1, **flags):
    return BoardEntity(CardFeatures(card_id=card_id, card_type="MINION"), attack, health, maximum, position, **flags)


def state(self_board=(), opponent_board=(), hero=(30, 30), locations=(), hand=(), secrets=0):
    self_player = PlayerObservation(hero_health=hero[0], hero_max_health=hero[1], board=tuple(self_board),
                                    locations=tuple(locations), hand_size=len(hand), secret_count=secrets)
    opponent = PlayerObservation(hero_health=30, hero_max_health=30, board=tuple(opponent_board))
    return GameState(turn_number=5, active_player="SELF", self_player=self_player, opponent=opponent,
                     self_hand=tuple(hand))


def heal(side="SELF", kind="HERO", position=-1, target="HERO_09", card="HEAL"):
    return {"type": "PLAY_CARD", "card_id": card, "source_card_id": card, "hand_index": 0, "play_position": 0,
            "target_side": side, "target_kind": kind, "target_board_position": position, "target_card_id": target}


RUIN = {"type": "PLAY_CARD", "card_id": "RUIN", "source_card_id": "RUIN", "hand_index": 0, "play_position": 0}


def test_catalog_effects_accept_only_exact_whole_text_templates():
    assert set(EFFECTS) == {"HEAL", "RUIN"}
    assert EFFECTS["HEAL"].value == 5 and EFFECTS["RUIN"].value == 5
    assert TEXTS["VANILLA"] == "" and "HEAL_DRAW" not in EFFECTS


def test_heal_distinguishes_full_damaged_and_unknown_maximum():
    full = check_direct_effect(state(), heal(), EFFECTS, TEXTS)
    assert (full.status, full.reason, full.side_effects) == (NO_DIRECT_EFFECT, "TARGET_AT_FULL_HEALTH",
                                                             SIDE_NONE_VISIBLE)
    assert is_demotable(full)
    damaged = check_direct_effect(state(hero=(27, 30)), heal(), EFFECTS, TEXTS)
    assert damaged.status == DIRECT_EFFECT_PRESENT and damaged.details["direct_restore_min"] == 3
    hidden_max = replace(state(), self_player=PlayerObservation(hero_health=30))
    assert check_direct_effect(hidden_max, heal(), EFFECTS, TEXTS).reason == "HERO_MAX_HEALTH_UNKNOWN"


def test_heal_minion_target_must_resolve_by_position_and_card():
    board = state(opponent_board=[minion(health=2, maximum=4)])
    assert check_direct_effect(board, heal("OPPONENT", "MINION", 1, "VANILLA"), EFFECTS, TEXTS).status == \
        DIRECT_EFFECT_PRESENT
    assert check_direct_effect(board, heal("OPPONENT", "MINION", 1, "OTHER"), EFFECTS, TEXTS).reason == \
        "TARGET_NOT_RESOLVED"


def test_visible_healing_modifier_or_unknown_text_blocks_a_zero_claim():
    location = LocationEntity(CardFeatures(card_id="SANCTUM", card_type="LOCATION"), 3, 3, 2, on_cooldown=True)
    result = check_direct_effect(state(locations=[location]), heal(), EFFECTS, TEXTS)
    assert (result.status, result.reason) == (UNKNOWN, "VISIBLE_HEALING_MODIFIER")
    token = check_direct_effect(state(self_board=[minion("TOKEN_NOT_PINNED")]), heal(), EFFECTS, TEXTS)
    assert (token.status, token.reason) == (UNKNOWN, "VISIBLE_ENTITY_TEXT_UNKNOWN")


def test_side_effects_never_allow_demotion_when_unverified():
    secret = check_direct_effect(state(secrets=1), heal(), EFFECTS, TEXTS)
    assert secret.status == NO_DIRECT_EFFECT and secret.side_effects == SIDE_UNKNOWN and not is_demotable(secret)
    reacting_hand = (CardFeatures(card_id="HEAL"), CardFeatures(card_id="HEAL"))
    reacting = check_direct_effect(state(hand=reacting_hand), heal(), EFFECTS, TEXTS)
    assert reacting.side_effects == SIDE_POSSIBLE and not is_demotable(reacting)


def test_unsupported_sources_and_untargeted_heals():
    assert check_direct_effect(state(), heal(card="HEAL_DRAW"), EFFECTS, TEXTS).status == UNSUPPORTED
    assert check_direct_effect(state(), {"type": "END_TURN", "play_position": 0}, EFFECTS, TEXTS).status == \
        UNSUPPORTED
    untargeted = {key: value for key, value in heal().items() if not key.startswith("target")}
    assert check_direct_effect(state(), untargeted, EFFECTS, TEXTS).reason == "UNTARGETED_RESTORE"


def test_ruin_checks_both_sides_and_conservative_modifiers():
    none = check_direct_effect(state([minion(attack=4)], [minion(attack=3)]), RUIN, EFFECTS, TEXTS)
    assert (none.status, none.reason) == (NO_DIRECT_EFFECT, "NO_MINION_MEETS_ATTACK_THRESHOLD")
    own = check_direct_effect(state([minion(attack=5)], [minion(attack=1)]), RUIN, EFFECTS, TEXTS)
    assert own.status == DIRECT_EFFECT_PRESENT and own.details["qualifying"] == {"SELF": 1, "OPPONENT": 0}
    dormant = check_direct_effect(state(opponent_board=[minion(attack=6, dormant=True)]), RUIN, EFFECTS, TEXTS)
    assert dormant.reason == "QUALIFYING_MINION_DORMANT_OR_IMMUNE"
    wyrm = check_direct_effect(state([minion("WYRM", attack=4)]), RUIN, EFFECTS, TEXTS)
    assert (wyrm.status, wyrm.reason) == (UNKNOWN, "VISIBLE_SPELL_TRIGGER")


def test_constrained_order_keeps_every_action_and_only_moves_demoted_ones():
    assert constrained_order([3, 0, 2, 1], {3, 2}) == [0, 1, 3, 2]
    assert constrained_order([1, 0], set()) == [1, 0]


def _evidence_rows(deltas):
    rows = []
    for index, (before, after) in enumerate(deltas):
        action = {"type": "HERO_POWER", "source_card_id": "HP", "target_side": "SELF", "target_kind": "HERO"}
        for offset, health in ((0, before), (1, after)):
            rows.append({"game_id": "g", "decision_id": f"g:{index * 3 + offset}", "chosen_action_index": 0,
                         "legal_actions": [action],
                         "state": {"turn_number": index, "self_player": {"hero_health": health,
                                                                         "hero_max_health": 30}}})
    return rows


def test_observed_hero_power_evidence_requires_one_consistent_amount():
    consistent = observed_restore_evidence(_evidence_rows([(20, 22), (29, 30), (30, 30)]), "HP")
    assert consistent["consistent"] and consistent["inferred_restore"] == 2
    # A damage outcome (e.g. a hidden heal-to-damage effect) or a second amount refuses verification.
    assert not observed_restore_evidence(_evidence_rows([(20, 22), (25, 20)]), "HP")["consistent"]
    assert not observed_restore_evidence(_evidence_rows([(20, 22), (10, 15)]), "HP")["consistent"]
