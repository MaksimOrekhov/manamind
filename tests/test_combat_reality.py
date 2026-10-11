"""Independent arithmetic and refusal checks for the offline extractor; no model/fit."""
from copy import deepcopy
import json

import pytest

from dataclasses import asdict
from manamind.outcome import TextSource
from manamind.outcome import scenario as sc
from manamind.training.combat_reality import extract_attack


def example(**flags):
    state = sc.position(self_side=sc.side(board=(sc.minion("A", 3, 5, 1),)),
                        opponent=sc.side(board=(sc.minion("B", 4, 3, 1, **flags),)))
    action = sc.attack(1, "A", sc.target_minion("OPPONENT", 1, "B"))
    return {"state": json.loads(json.dumps(asdict(state)))}, action


TEXTS = TextSource.from_records([{"id": c, "type": "MINION", "text": "", "mechanics": []} for c in ("A", "B", "C")])


@pytest.mark.parametrize("flags,damage,dead,shield", [
    ({}, 3, True, False), ({"divine_shield": True}, 0, False, True),
    ({"immune": True}, 0, False, False),
])
def test_exchange_with_protection(flags, damage, dead, shield):
    row, action = example(**flags)
    before = deepcopy(row)
    p = extract_attack(row, action, TEXTS)["properties"]
    assert p["attack_ge_health"] == {"value": True, "knownness": "OBSERVED", "reasons": [], "conditions": []}
    assert p["target_damage_packet"]["value"] == damage
    assert p["target_body_dies"]["value"] is dead
    assert p["target_shield_removed"]["value"] is shield
    assert p["source_health_after_packet"]["value"] == 1
    assert p["source_body_dies"]["value"] is False
    assert p["source_body_dies"]["knownness"] == "VERIFIED_LOCAL"
    assert row == before


def test_poisonous_death_is_separate_from_positive_health_after_packet():
    row, action = example()
    row["state"]["self_player"]["board"][0]["poisonous"] = True
    row["state"]["opponent"]["board"][0]["current_health"] = 10
    p = extract_attack(row, action, TEXTS)["properties"]
    assert p["attack_ge_health"]["value"] is False
    assert p["target_body_dies"]["value"] is True
    assert p["target_health_after_packet"]["value"] == 7


@pytest.mark.parametrize("field", ["divine_shield", "immune", "poisonous", "silenced"])
def test_unknown_boolean_is_not_deserialized_as_false(field):
    row, action = example()
    row["state"]["opponent"]["board"][0][field] = None
    r = extract_attack(row, action, TEXTS)
    assert r["outcome_status"] == "NOT_CALLED"
    assert "RAW_FLAG_UNOBSERVED:" + field in r["blockers"]
    assert r["properties"]["attack_ge_health"]["knownness"] == "OBSERVED"
    assert "target_body_dies" not in r["properties"]


@pytest.mark.parametrize("text,mechanics", [
    ("<b>Deathrattle:</b> Deal 3 damage to all minions.", ["DEATHRATTLE"]),
    ("After a minion takes damage, give it +1 Health.", []),
    ("This minion takes only 1 damage at a time.", []),
    ("Your other minions have +1 Attack.", ["AURA"]),
])
def test_unreviewed_reactions_keep_exchange_conditional(text, mechanics):
    row, action = example()
    texts = TEXTS.extended([{"id": "B", "type": "MINION", "text": text, "mechanics": mechanics}])
    r = extract_attack(row, action, texts)
    assert r["blockers"]
    assert r["properties"]["target_body_dies"]["knownness"] == "CONDITIONAL"
    assert r["properties"]["target_body_dies"]["conditions"]


def test_partial_with_only_own_quest_preserves_local_facts_without_complete_state():
    row, action = example()
    row["state"]["self_player"]["secret_count"] = 1
    r = extract_attack(row, action, TEXTS)
    assert r["outcome_status"] == "PARTIAL"
    assert r["properties"]["target_body_dies"]["knownness"] == "VERIFIED_LOCAL"
    assert "state" not in r and "candidate" not in r


@pytest.mark.parametrize("context", ["enemy_secret", "active_effect", "passive_weapon", "missing_text", "reborn"])
def test_context_blockers_do_not_hide_observed_math(context):
    row, action = example()
    texts = TEXTS
    if context == "enemy_secret": row["state"]["opponent"]["secret_count"] = 1
    elif context == "active_effect": row["state"]["self_player"]["active_effects"] = [{"card_id": "UNKNOWN_EFFECT"}]
    elif context == "passive_weapon":
        row["state"]["opponent"]["weapon"] = {"card_id": "W", "card_type": "WEAPON", "attack": 2, "durability": 3}
    elif context == "missing_text": texts = TextSource()
    else: row["state"]["opponent"]["board"][0]["reborn"] = True
    r = extract_attack(row, action, texts)
    assert r["blockers"]
    assert r["properties"]["attack_ge_health"]["knownness"] == "OBSERVED"
    assert all(v["knownness"] != "VERIFIED_LOCAL" for k, v in r["properties"].items() if k.startswith("target_"))


def test_other_battlecry_is_not_a_blanket_vanilla_requirement():
    row, action = example()
    other = deepcopy(row["state"]["self_player"]["board"][0])
    other["card"]["card_id"], other["board_position"] = "C", 2
    row["state"]["self_player"]["board"].append(other)
    texts = TEXTS.extended([{"id": "C", "type": "MINION", "text": "<b>Battlecry:</b> Draw a card.", "mechanics": ["BATTLECRY"]}])
    r = extract_attack(row, action, texts)
    assert not r["blockers"]
    assert r["properties"]["target_body_dies"]["knownness"] == "VERIFIED_LOCAL"


def test_labels_future_and_hidden_identity_are_not_inputs():
    row, action = example()
    original = extract_attack(row, action, TEXTS)
    row.update(chosen_action_index=999, correct_actions=[], future_state="DO NOT READ", hidden_hand=["LEAK"])
    assert extract_attack(row, action, TEXTS) == original


def test_hero_attack_is_explicitly_outside_this_prototype():
    row, action = example()
    action.update(source_is_hero=True, source_kind="HERO")
    assert extract_attack(row, action, TEXTS)["blockers"] == ["OUTSIDE_MINION_TO_MINION"]


def test_uninvolved_aura_with_unknown_scope_cannot_prove_local_exchange():
    row, action = example()
    other = deepcopy(row["state"]["self_player"]["board"][0])
    other["card"]["card_id"], other["board_position"] = "C", 2
    other["card"]["mechanics"] = ["AURA"]
    row["state"]["self_player"]["board"].append(other)
    texts = TEXTS.extended([{"id": "C", "type": "MINION", "text": "Your minions are Immune while attacking.", "mechanics": ["AURA"]}])
    r = extract_attack(row, action, texts)
    assert "AURA_SCOPE_UNREVIEWED" in r["blockers"]
    assert r["properties"]["source_body_dies"]["knownness"] == "CONDITIONAL"


def test_source_shield_and_enemy_poison_are_separate_from_health_margin():
    row, action = example(poisonous=True)
    row["state"]["self_player"]["board"][0]["divine_shield"] = True
    p = extract_attack(row, action, TEXTS)["properties"]
    assert p["source_damage_packet"]["value"] == 0
    assert p["source_shield_removed"]["value"] is True
    assert p["source_body_dies"]["value"] is False
    row["state"]["self_player"]["board"][0]["divine_shield"] = False
    p = extract_attack(row, action, TEXTS)["properties"]
    assert p["source_body_dies"]["value"] is True
    assert p["source_health_after_packet"]["value"] == 1


def test_windfury_bookkeeping_does_not_claim_remaining_attacks():
    row, action = example()
    row["state"]["self_player"]["board"][0]["windfury"] = True
    r = extract_attack(row, action, TEXTS)
    assert r["outcome_status"] == "PARTIAL"
    assert r["properties"]["target_body_dies"]["knownness"] == "VERIFIED_LOCAL"
    assert any(u["tag"] == "ATTACKS_USED_UNOBSERVED" for u in r["outcome_unknowns"])
