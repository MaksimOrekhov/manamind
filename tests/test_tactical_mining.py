"""TACTICAL-DECISION-1 detectors: tiers must stay conservative."""
from manamind.research.decision_overlay import ACTIVE, INACTIVE, DecisionOverlay, QuestState
from manamind.research.tactical_context import assess_menu, heal_sources
from manamind.research.tactical_mining import (
    PROBABLE_STRATEGIC, PROVEN_LOCAL, UNCERTAIN, bad_trade, detect, good_trade, quest_completions,
)

RECORDS = {"FLASH": {"id": "FLASH", "type": "SPELL", "text": "Restore #5 Health.", "spellSchool": "HOLY"},
           "SHADOW": {"id": "SHADOW", "type": "SPELL", "text": "Deal $2 damage.", "spellSchool": "SHADOW"},
           "CORE_EX1_197": {"id": "CORE_EX1_197", "type": "SPELL", "spellSchool": "SHADOW"}}
SOURCES = heal_sources(list(RECORDS.values()))


def mini(position, attack, health, **flags):
    return {"board_position": position, "current_attack": attack, "current_health": health, "max_health": health,
            "taunt": False, "card": {"card_id": f"M{position}", "mechanics": []}, **flags}


def state(foe_hp=30, self_board=(), foe_board=(), hand=("FLASH",), foe_secrets=0):
    return {"turn_number": 6, "self_hand": [{"card_id": c, "current_cost": 1} for c in hand],
            "self_player": {"hero_health": 20, "hero_max_health": 30, "armor": 0, "available_mana": 5,
                            "board": list(self_board), "locations": [], "weapon": None},
            "opponent": {"hero_health": foe_hp, "hero_max_health": 30, "armor": 0, "secret_count": foe_secrets,
                         "board": list(foe_board), "locations": [], "weapon": None}}


def heal(side, kind="HERO"):
    return {"type": "PLAY_CARD", "source_card_id": "FLASH", "hand_index": 0, "card_type": "SPELL",
            "target_side": side, "target_kind": kind, "target_board_position": -1, "target_card_id": "HERO"}


def overlay(healing=INACTIVE, quests=(), contributors=(None,), hand=("FLASH",)):
    return DecisionOverlay("d", healing, tuple(quests), tuple(hand), tuple(contributors))


def run(st, actions, order, ov, texts=None):
    found = assess_menu(st, actions, ov, SOURCES)
    return detect(st, actions, order, 0, ov, found, RECORDS, texts or {})


def classes(hits):
    return {hit["class"]: hit["tier"] for hit in hits}


def test_missed_lethal_is_proven_unless_a_hidden_secret_exists():
    actions = [{"type": "END_TURN"}, heal("OPPONENT")]
    assert classes(run(state(foe_hp=4), actions, [0, 1], overlay(ACTIVE)))["HEAL_LETHAL_MISSED"] == PROVEN_LOCAL
    secret = classes(run(state(foe_hp=4, foe_secrets=1), actions, [0, 1], overlay(ACTIVE)))
    assert secret["HEAL_LETHAL_MISSED"] == UNCERTAIN
    assert "HEAL_LETHAL_MISSED" not in classes(run(state(foe_hp=4), actions, [1, 0], overlay(ACTIVE)))


def test_dominated_target_requires_a_strictly_better_sibling():
    actions = [heal("OPPONENT"), heal("SELF")]
    assert classes(run(state(), actions, [0, 1], overlay()))["HEAL_TARGET_DOMINATED"] == PROVEN_LOCAL
    assert "HEAL_TARGET_DOMINATED" not in classes(run(state(), actions, [1, 0], overlay()))
    full = state()
    full["self_player"]["hero_health"] = 30  # both targets are no-ops: nothing is dominated
    assert "HEAL_TARGET_DOMINATED" not in classes(run(full, actions, [0, 1], overlay()))


def test_sanctum_followup_is_not_flagged_when_top1_is_another_healing_action():
    records = {**RECORDS, "BREATH": {"id": "BREATH", "type": "SPELL", "text": "Deal $5 damage. If it dies, restore #5 Health."}}
    actions = [{"type": "PLAY_CARD", "source_card_id": "BREATH", "hand_index": 1}, heal("OPPONENT")]
    st = state(foe_hp=20, hand=("FLASH", "BREATH"))
    found = assess_menu(st, actions, overlay(ACTIVE, hand=("FLASH", "BREATH"), contributors=(None, None)), SOURCES)
    hits = detect(st, actions, [0, 1], 1, overlay(ACTIVE, hand=("FLASH", "BREATH"), contributors=(None, None)),
                  found, records, {})
    assert "SANCTUM_FOLLOWUP_MISSED" not in classes(hits)


def test_sanctum_followup_is_only_strategic():
    actions = [{"type": "END_TURN"}, heal("OPPONENT")]
    assert classes(run(state(foe_hp=20), actions, [0, 1], overlay(ACTIVE)))["SANCTUM_FOLLOWUP_MISSED"] == PROBABLE_STRATEGIC
    assert "SANCTUM_FOLLOWUP_MISSED" not in classes(run(state(foe_hp=20), actions, [1, 0], overlay(ACTIVE)))
    assert "SANCTUM_FOLLOWUP_MISSED" not in classes(run(state(foe_hp=20), actions, [0, 1], overlay(INACTIVE)))


def test_quest_completion_needs_school_progress_and_a_client_hint():
    quests = [QuestState("TLC_817t", 3, 4), QuestState("TLC_817t2", 0, 4)]
    st = state()
    act = {"type": "PLAY_CARD", "source_card_id": "FLASH", "hand_index": 0, "card_type": "SPELL"}
    assert quest_completions(st, [act], overlay(quests=quests, contributors=(1,)), RECORDS) == [0]
    assert quest_completions(st, [act], overlay(quests=quests, contributors=(None,)), RECORDS) == []
    shadow = {**act, "source_card_id": "SHADOW"}
    st["self_hand"] = [{"card_id": "SHADOW", "current_cost": 1}]
    assert quest_completions(st, [shadow], overlay(quests=quests, contributors=(1,), hand=("SHADOW",)), RECORDS) == []


def test_ruin_without_targets_is_proven_only_when_the_quest_and_triggers_are_ruled_out():
    ruin = {"type": "PLAY_CARD", "source_card_id": "CORE_EX1_197", "hand_index": 0, "card_type": "SPELL"}
    st = state(self_board=[mini(1, 4, 4)], foe_board=[mini(1, 2, 2)], hand=("CORE_EX1_197",))
    texts = {"M1": "vanilla"}
    clean = run(st, [ruin, {"type": "END_TURN"}], [0, 1], overlay(hand=("CORE_EX1_197",)), texts)
    assert classes(clean)["AOE_RUIN_NO_TARGET"] == PROVEN_LOCAL
    progress = run(st, [ruin, {"type": "END_TURN"}], [0, 1], overlay(contributors=(1,), hand=("CORE_EX1_197",)), texts)
    assert classes(progress)["AOE_RUIN_NO_TARGET"] == UNCERTAIN
    finishing = run(st, [ruin, {"type": "END_TURN"}], [0, 1], overlay(quests=[QuestState("TLC_817t2", 3, 4)],
                                                                      contributors=(1,), hand=("CORE_EX1_197",)), texts)
    assert classes(finishing)["AOE_RUIN_NO_TARGET"] == UNCERTAIN
    assert [h for h in finishing if h["class"] == "AOE_RUIN_NO_TARGET"][0]["facts"]["quest_effect"] == "COMPLETES_QUEST"
    unknown_text = run(st, [ruin, {"type": "END_TURN"}], [0, 1], overlay(hand=("CORE_EX1_197",)), {})
    assert classes(unknown_text)["AOE_RUIN_NO_TARGET"] == UNCERTAIN
    big = state(self_board=[mini(1, 5, 5)], hand=("CORE_EX1_197",))
    assert "AOE_RUIN_NO_TARGET" not in classes(run(big, [ruin, {"type": "END_TURN"}], [0, 1],
                                                   overlay(hand=("CORE_EX1_197",)), texts))


def attack(target_position, attack_value, health, target_attack, target_health):
    return {"type": "ATTACK", "source_kind": "MINION", "source_board_position": 1, "source_card_id": "M1",
            "source_attack": attack_value, "source_health": health, "target_kind": "MINION", "target_side": "OPPONENT",
            "target_board_position": target_position, "target_card_id": f"M{target_position}"}


def test_trade_arithmetic_ignores_any_keyword_complication():
    st = state(self_board=[mini(1, 2, 2)], foe_board=[mini(2, 3, 5), mini(3, 1, 2)])
    assert bad_trade(st, attack(2, 2, 2, 3, 5)) == "DIES_WITHOUT_KILL"
    assert good_trade(st, attack(3, 2, 2, 1, 2)) and not good_trade(st, attack(2, 2, 2, 3, 5))
    shielded = state(self_board=[mini(1, 2, 2)], foe_board=[mini(2, 3, 5, divine_shield=True)])
    assert bad_trade(shielded, attack(2, 2, 2, 3, 5)) is None
    assert bad_trade(st, {"type": "END_TURN"}) is None
