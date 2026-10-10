"""TACTICAL-DECISION-1 evaluator: expected outcomes are written down before the code is called."""
from manamind.research.decision_overlay import ACTIVE, INACTIVE, UNKNOWN, DecisionOverlay, QuestState
from manamind.research.tactical_context import (
    ENEMY_DAMAGE, ENEMY_HEAL, ENEMY_NO_EFFECT, LETHAL, SELF_DAMAGE, SELF_HEAL, SELF_NO_EFFECT, UNRESOLVED, VARIANTS,
    assess_heal, assess_menu, committed_effect_first, heal_sources, lethal_first, rerank, target_dominance,
)

RECORDS = [
    {"id": "FLASH", "type": "SPELL", "text": "Restore #5 Health."},
    {"id": "EMBRACE", "type": "SPELL", "text": "Restore #4 Health.\n\xa0Get a card."},
    {"id": "MOONWELL", "type": "SPELL", "text": "Deal $4 damage to all enemy characters. Restore #4 Health to all friendly characters."},
    {"id": "ALLHEAL", "type": "SPELL", "text": "Restore #3 Health to all friendly characters."},
    {"id": "MINION", "type": "MINION", "text": "Restore #2 Health."},
]
SOURCES = heal_sources(RECORDS)


def hero_state(self_hp=20, foe_hp=17, foe_armor=0, foe_secrets=0, board=None):
    return {
        "turn_number": 5,
        "self_hand": [{"card_id": "FLASH"}],
        "self_player": {"hero_health": self_hp, "hero_max_health": 30, "armor": 0, "board": list((board or {}).get("self", []))},
        "opponent": {"hero_health": foe_hp, "hero_max_health": 30, "armor": foe_armor, "secret_count": foe_secrets,
                     "board": list((board or {}).get("opponent", []))},
    }


def minion(position, card_id="M", health=3, maximum=4, **flags):
    return {"board_position": position, "card": {"card_id": card_id}, "current_health": health, "max_health": maximum, **flags}


def flash(side, kind="HERO", position=-1, card_id="HERO", hand_index=0, source="FLASH"):
    return {"type": "PLAY_CARD", "source_card_id": source, "hand_index": hand_index, "target_side": side,
            "target_kind": kind, "target_board_position": position, "target_card_id": card_id}


def overlay(state=INACTIVE, quests=(), contributors=(None,), hand=("FLASH",)):
    return DecisionOverlay("d", state, tuple(quests), tuple(hand), tuple(contributors))


def test_supported_sources_are_exact_templates_only():
    assert set(SOURCES) == {"FLASH", "EMBRACE", "HERO_09dbp", "HERO_09bp"}  # not all-friendly, not Moonwell, not a minion
    assert SOURCES["FLASH"].amount == 5 and not SOURCES["FLASH"].extra_effect
    assert SOURCES["EMBRACE"].amount == 4 and SOURCES["EMBRACE"].extra_effect
    assert SOURCES["HERO_09dbp"].kind == "HERO_POWER" and SOURCES["HERO_09dbp"].amount == 2


def test_inactive_directions():
    state = hero_state(self_hp=20, foe_hp=30)
    assert assess_heal(state, flash("SELF"), overlay(), SOURCES).outcome == SELF_HEAL
    assert assess_heal(state, flash("OPPONENT"), overlay(), SOURCES).outcome == ENEMY_NO_EFFECT
    state["opponent"]["hero_health"] = 17
    assert assess_heal(state, flash("OPPONENT"), overlay(), SOURCES).outcome == ENEMY_HEAL
    state["self_player"]["hero_health"] = 30
    assert assess_heal(state, flash("SELF"), overlay(), SOURCES).outcome == SELF_NO_EFFECT


def test_active_conversion_flips_every_direction():
    state = hero_state(self_hp=20, foe_hp=17)
    active = overlay(ACTIVE)
    assert assess_heal(state, flash("SELF"), active, SOURCES).outcome == SELF_DAMAGE
    assert assess_heal(state, flash("OPPONENT"), active, SOURCES).outcome == ENEMY_DAMAGE
    # A full-health enemy still takes the converted damage: no "full health" exemption while converted.
    assert assess_heal(hero_state(foe_hp=30), flash("OPPONENT"), active, SOURCES).outcome == ENEMY_DAMAGE


def test_lethal_uses_health_plus_armor_and_flags_hidden_secret():
    active = overlay(ACTIVE)
    assert assess_heal(hero_state(foe_hp=5), flash("OPPONENT"), active, SOURCES).outcome == LETHAL
    assert assess_heal(hero_state(foe_hp=6), flash("OPPONENT"), active, SOURCES).outcome == ENEMY_DAMAGE
    assert assess_heal(hero_state(foe_hp=3, foe_armor=3), flash("OPPONENT"), active, SOURCES).outcome == ENEMY_DAMAGE
    secret = assess_heal(hero_state(foe_hp=4, foe_secrets=1), flash("OPPONENT"), active, SOURCES)
    assert secret.outcome == LETHAL and "OPPONENT_SECRET_PRESENT" in secret.caveats
    # A minion that would die is not a lethal claim.
    board = {"opponent": [minion(1, "M", 3, 4)]}
    assert assess_heal(hero_state(foe_hp=4, board=board), flash("OPPONENT", "MINION", 1, "M"), active,
                       SOURCES).outcome == ENEMY_DAMAGE


def test_shields_unknown_state_and_unresolved_targets_make_no_claim():
    active = overlay(ACTIVE)
    shielded = {"opponent": [minion(1, "M", 3, 4, divine_shield=True)]}
    assert assess_heal(hero_state(board=shielded), flash("OPPONENT", "MINION", 1, "M"), active,
                       SOURCES).outcome == UNRESOLVED
    assert assess_heal(hero_state(), flash("OPPONENT"), overlay(UNKNOWN), SOURCES).outcome == UNRESOLVED
    assert assess_heal(hero_state(), flash("OPPONENT", "MINION", 9, "M"), active, SOURCES).outcome == UNRESOLVED
    hero = hero_state()
    hero["opponent"]["hero_divine_shield"] = True
    assert assess_heal(hero, flash("OPPONENT"), active, SOURCES).outcome == UNRESOLVED
    hero = hero_state()
    hero["opponent"]["hero_max_health"] = None  # unknown maximum is never replaced by 30
    assert assess_heal(hero, flash("OPPONENT"), overlay(), SOURCES).outcome == UNRESOLVED


def test_quest_progress_needs_an_aligned_client_hint():
    quest = [QuestState("TLC_817t", 2, 4)]
    state = hero_state()
    assert assess_heal(state, flash("SELF"), overlay(quests=quest, contributors=(1,)), SOURCES).quest_progress == 1
    assert assess_heal(state, flash("SELF"), overlay(quests=quest, contributors=(None,)), SOURCES).quest_progress == 0
    assert assess_heal(state, flash("SELF"), overlay(), SOURCES).quest_progress == 0  # no Quest owned
    misaligned = overlay(quests=quest, contributors=(1,), hand=("OTHER",))
    assert assess_heal(state, flash("SELF"), misaligned, SOURCES).quest_progress is None
    power = {"type": "HERO_POWER", "source_card_id": "HERO_09dbp", "target_side": "SELF", "target_kind": "HERO",
             "target_board_position": -1, "target_card_id": "HERO"}
    assert assess_heal(state, power, overlay(quests=quest, contributors=(1,)), SOURCES).quest_progress == 0


def test_unsupported_actions_are_not_assessed():
    state = hero_state()
    assert assess_heal(state, {"type": "END_TURN"}, overlay(), SOURCES) is None
    assert assess_heal(state, flash("SELF", source="MOONWELL"), overlay(), SOURCES) is None
    untargeted = {"type": "PLAY_CARD", "source_card_id": "FLASH", "hand_index": 0}
    assert assess_heal(state, untargeted, overlay(), SOURCES) is None


def _menu():
    state = hero_state(self_hp=20, foe_hp=30)
    actions = [{"type": "END_TURN"}, flash("OPPONENT"), {"type": "PLAY_CARD", "source_card_id": "OTHER"},
               flash("SELF"), flash("OPPONENT", "MINION", 1, "M")]
    state["opponent"]["board"] = [minion(1, "M", 2, 4)]
    return state, actions


def test_target_dominance_moves_only_targets_inside_the_source():
    state, actions = _menu()
    found = assess_menu(state, actions, overlay(), SOURCES)
    # Policy order: enemy hero (no effect) first, END_TURN, other card, then SELF hero (real heal), enemy minion (heals it)
    order = [1, 0, 2, 3, 4]
    result = target_dominance(order, found)
    assert result[1:3] == [0, 2]  # END_TURN and the unrelated card keep their slots
    assert sorted(result) == sorted(order)
    slots = [0, 3, 4]  # the three Flash Heal slots stay the same set
    assert sorted(i for i, a in enumerate(result) if a in (1, 3, 4)) == slots
    assert [result[i] for i in slots] == [3, 1, 4]  # GAIN, then NEUTRAL, then HARM


def test_siblings_of_different_hand_copies_are_not_mixed():
    state, _ = _menu()
    state["self_hand"] = [{"card_id": "FLASH"}, {"card_id": "FLASH"}]
    actions = [flash("OPPONENT", hand_index=0), flash("SELF", hand_index=1)]
    found = assess_menu(state, actions, overlay(hand=("FLASH", "FLASH"), contributors=(None, None)), SOURCES)
    assert target_dominance([0, 1], found) == [0, 1]


def test_lethal_and_committed_effect_layers():
    state = hero_state(self_hp=20, foe_hp=5)
    actions = [{"type": "END_TURN"}, flash("SELF"), flash("OPPONENT"), {"type": "PLAY_CARD", "source_card_id": "OTHER"}]
    found = assess_menu(state, actions, overlay(ACTIVE), SOURCES)
    assert found[2].outcome == LETHAL and found[1].outcome == SELF_DAMAGE
    assert lethal_first([0, 1, 2, 3], found) == [2, 0, 1, 3]
    deep = hero_state(foe_hp=17)
    found = assess_menu(deep, actions, overlay(ACTIVE), SOURCES)
    assert committed_effect_first([0, 3, 1, 2], found) == [2, 0, 3, 1]  # only enemy damage moves up


def test_rerank_keeps_the_frozen_order_when_nothing_is_supported():
    state = hero_state()
    actions = [{"type": "END_TURN"}, {"type": "PLAY_CARD", "source_card_id": "OTHER"}]
    order = [1, 0]
    found = assess_menu(state, actions, overlay(), SOURCES)
    assert found == {} and all(rerank(order, found)[name] == order for name in VARIANTS)


def test_inactive_state_never_promotes_burn_or_lethal():
    state = hero_state(foe_hp=4)
    actions = [{"type": "END_TURN"}, flash("OPPONENT")]
    found = assess_menu(state, actions, overlay(INACTIVE), SOURCES)
    assert found[1].outcome == ENEMY_HEAL
    assert all(rerank([0, 1], found)[name] == [0, 1] for name in VARIANTS)
