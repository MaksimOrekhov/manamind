"""CONSEQUENCE-DIAGNOSTICS-1: the compound damage+buff shape, SIDE_MISDIRECTION and SELF_HARM (flags, abstentions, false positives)."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from manamind.outcome import ObservedContext, Status, TextSource, forecast_action
from manamind.outcome import scenario as sc
from manamind.outcome.diagnostics import (
    SELF_HARM, SIDE_MISDIRECTION, diagnose_menu, direct_vector, dominates,
)
from manamind.outcome.grammar import parse_text
from manamind.outcome.live_shadow import load_texts
from manamind.outcome.shadow import forecast_menu

ROOT = Path(__file__).parents[1]
SANGUINE = "Deal 1 damage to a minion and give it +2 Attack."
TRUSTED = ObservedContext(trust_spell_damage=True, healing_does_damage=False, healing_bonus=0, spell_healing_doubled=False,
                          self_hero_divine_shield=False, opponent_hero_divine_shield=False)
TEXTS = TextSource.from_records([
    {"id": "LOC", "type": "LOCATION", "mechanics": [], "text": SANGUINE, "health": 3},
    {"id": "BUFFER", "type": "SPELL", "mechanics": [], "text": "Give a minion +3/+3."},
    {"id": "HEALER", "type": "SPELL", "mechanics": [], "text": "Restore #4 Health."},
    {"id": "POKE", "type": "SPELL", "mechanics": [], "text": "Deal $1 damage to a minion."},
    {"id": "SWEEP", "type": "SPELL", "mechanics": [], "text": "Deal $2 damage to all minions."},
    {"id": "SPELLBOUND", "type": "SPELL", "mechanics": [], "text": "Summon a plant that dreams of electric sheep."},
    {"id": "WATCHER", "type": "MINION", "mechanics": [], "text": "Whenever a friendly minion dies, draw a card."},
    {"id": "AURA", "type": "MINION", "mechanics": ["AURA"], "text": "Your other minions have +1 Attack."},
    {"id": "DR", "type": "MINION", "mechanics": ["DEATHRATTLE"], "text": "Deathrattle: Draw a card."},
    {"id": "FRENZY", "type": "MINION", "mechanics": [], "text": "Frenzy: Gain +2 Attack."},
    *({"id": card, "type": "MINION", "mechanics": [], "text": ""} for card in ("A", "B", "C", "TOKEN"))])


def with_location(own=(), enemy=(), *, health=3, own_extra=None):
    from manamind.domain.card import CardFeatures
    from manamind.domain.entity import LocationEntity
    place = LocationEntity(card=CardFeatures(card_id="LOC", card_type="LOCATION"), current_health=health, max_health=3,
                           board_position=9, on_cooldown=False, can_activate=True)
    state = sc.position(self_side=sc.side(board=tuple(own), **(own_extra or {})), opponent=sc.side(board=tuple(enemy)), hand=())
    return replace(state, self_player=replace(state.self_player, locations=(place,)))


def activate(target):
    return {"type": "ACTIVATE_LOCATION", "card_id": "LOC", "source_card_id": "LOC", "source_kind": "LOCATION",
            "source_board_position": 9, "play_position": 0, **target}


# ----- grammar ------------------------------------------------------------------------------------------------------


def test_the_compound_shape_is_recognised_whole_and_nothing_near_it():
    (clause,) = parse_text(SANGUINE).clauses
    assert clause.kind == "DAMAGE_BUFF" and (clause.amount, clause.attack) == (1, 2)
    assert clause.selector.mode == "CHOSEN" and clause.selector.kinds == "MINION"
    for near in ("Deal 1 damage to a minion and give it +2 Attack this turn.",
                 "Deal 1 damage to a minion and give it +2/+2.",
                 "Deal 1 damage to a minion and give your hero +2 Attack.",
                 "Deal 1 damage to all minions and give it +2 Attack.",
                 "Deal 1 damage and give it +2 Attack.",
                 "Give it +2 Attack.",
                 "If you already have a weapon equipped, give it +2 Attack instead.",
                 "After a friendly minion survives damage, give it +1 Attack."):
        assert all(c.kind != "DAMAGE_BUFF" for c in parse_text(near).clauses), near


def test_only_cards_with_the_exact_shape_are_affected_in_the_whole_catalog():
    cards = json.loads((ROOT / "data/cards/standard_current_enUS.json").read_text(encoding="utf-8-sig"))
    cards = cards.get("cards", cards)
    found = {c["id"] for c in cards if c.get("text") and any(k.kind == "DAMAGE_BUFF" for k in parse_text(c["text"]).clauses)}
    assert found == {"CORE_REV_990", "EDR_468"}
    # the other 'give it +N Attack' sentences keep a different antecedent (a weapon, a damaged minion) and stay unparsed
    for card_id in ("END_002", "JAIL_029", "TLC_516"):
        text = next(c["text"] for c in cards if c["id"] == card_id)
        assert all(k.kind != "DAMAGE_BUFF" for k in parse_text(text).clauses)


def spell_state(*, enemy=(), own=(), hand_card, mana=5):
    return sc.position(self_side=sc.side(mana=mana, board=tuple(own)), opponent=sc.side(board=tuple(enemy)), hand=(hand_card,))


COMPOUND = TextSource.from_records([{"id": "COMBO", "type": "SPELL", "mechanics": [], "text": SANGUINE},
                                    *({"id": c, "type": "MINION", "mechanics": [], "text": ""} for c in ("A", "B")),
                                    {"id": "DR", "type": "MINION", "mechanics": ["DEATHRATTLE"], "text": "Deathrattle: Draw a card."}])


def cast(state, target):
    return forecast_action(state, sc.play("COMBO", 0, "SPELL", 1, target), COMPOUND, TRUSTED)


def change(forecast, ref_part, field):
    return next((c for c in forecast.changes if ref_part in c.ref.label() and c.field == field), None)


def test_damage_first_then_attack_for_a_survivor():
    state = spell_state(enemy=(sc.minion("A", 2, 4, 1),), hand_card=sc.hand_card("COMBO", "SPELL", 1))
    forecast = cast(state, sc.target_minion("OPPONENT", 1, "A"))
    assert change(forecast, "OPPONENT board#1", "health").after == 3 and change(forecast, "OPPONENT board#1", "attack").after == 4
    assert forecast.status is Status.PARTIAL or forecast.status is Status.EXACT
    assert [e.kind for e in forecast.events if e.kind in ("DAMAGE", "BUFF")] == ["DAMAGE", "BUFF"]


def test_a_minion_the_damage_kills_is_not_buffed():
    state = spell_state(own=(sc.minion("B", 1, 1, 1),), hand_card=sc.hand_card("COMBO", "SPELL", 1))
    forecast = cast(state, sc.target_minion("SELF", 1, "B"))
    assert change(forecast, "SELF board#1", "present").after is False
    assert change(forecast, "SELF board#1", "attack") is None


def test_divine_shield_absorbs_the_damage_and_the_buff_still_applies():
    state = spell_state(enemy=(sc.minion("A", 2, 1, 1, divine_shield=True),), hand_card=sc.hand_card("COMBO", "SPELL", 1))
    forecast = cast(state, sc.target_minion("OPPONENT", 1, "A"))
    assert change(forecast, "OPPONENT board#1", "divine_shield").after is False
    assert change(forecast, "OPPONENT board#1", "health") is None
    assert change(forecast, "OPPONENT board#1", "attack").after == 4
    assert change(forecast, "OPPONENT board#1", "present") is None


def test_a_deathrattle_of_the_target_keeps_the_forecast_open():
    state = spell_state(own=(sc.minion("DR", 2, 1, 1, mechanics=("DEATHRATTLE",)),), hand_card=sc.hand_card("COMBO", "SPELL", 1))
    forecast = cast(state, sc.target_minion("SELF", 1, "DR"))
    assert forecast.status is Status.PARTIAL
    assert "DEATHRATTLE" in {u.tag for u in forecast.unknowns}


def test_the_catalog_text_of_sanguine_depths_and_the_reviewed_tokens_load():
    texts = load_texts(ROOT)
    assert parse_text(texts.get("CORE_REV_990").text).clauses[0].kind == "DAMAGE_BUFF"
    token = texts.get("CAP_107t")
    assert token is not None and (token.attack, token.health) == (1, 1) and "random enemy" in token.text
    duck = texts.get("EDR_492t")
    assert duck is not None and "RUSH" in duck.mechanics
    reviewed = json.loads((ROOT / "data/outcome/reviewed_texts.json").read_text(encoding="utf-8"))["cards"]
    assert all(entry.get("provenance") for entry in reviewed if entry["id"] in ("CAP_107t", "EDR_492t"))


# ----- diagnostics -----------------------------------------------------------------------------------------------------


def menu_of(state, actions, texts=TEXTS, context=TRUSTED):
    return [(i, a, forecast_action(state, a, texts, context)) for i, a in enumerate(actions)]


def flags_of(state, actions, **kwargs):
    result = diagnose_menu(state, menu_of(state, actions, **kwargs), texts=kwargs.get("texts", TEXTS))
    return {(f.index, f.flag): f.against for f in result.flags}, result


def test_buffing_or_healing_the_opponent_instead_of_oneself_is_flagged():
    state = sc.position(self_side=sc.side(board=(sc.minion("A", 2, 2, 1),), hero_health=20),
                        opponent=sc.side(board=(sc.minion("B", 2, 2, 1),), hero_health=20),
                        hand=(sc.hand_card("BUFFER", "SPELL", 2), sc.hand_card("HEALER", "SPELL", 1)))
    actions = [sc.play("BUFFER", 0, "SPELL", 2, sc.target_minion("OPPONENT", 1, "B")),
               sc.play("BUFFER", 0, "SPELL", 2, sc.target_minion("SELF", 1, "A")),
               sc.play("HEALER", 1, "SPELL", 1, sc.target_hero("OPPONENT")),
               sc.play("HEALER", 1, "SPELL", 1, sc.target_hero("SELF")), sc.end_turn()]
    flags, _ = flags_of(state, actions)
    assert flags[(0, SIDE_MISDIRECTION)] == 1 and flags[(2, SIDE_MISDIRECTION)] == 3
    assert (1, SIDE_MISDIRECTION) not in flags and (3, SIDE_MISDIRECTION) not in flags      # only the opponent-aimed use


def test_a_removal_on_the_opponent_is_never_a_misdirection():
    state = sc.position(self_side=sc.side(board=(sc.minion("A", 2, 2, 1),)), opponent=sc.side(board=(sc.minion("B", 2, 2, 1),)),
                        hand=(sc.hand_card("POKE", "SPELL", 1),))
    actions = [sc.play("POKE", 0, "SPELL", 1, sc.target_minion("OPPONENT", 1, "B")),
               sc.play("POKE", 0, "SPELL", 1, sc.target_minion("SELF", 1, "A"))]
    flags, _ = flags_of(state, actions)
    assert (0, SIDE_MISDIRECTION) not in flags
    assert (1, SELF_HARM) in flags                         # damaging one's own vanilla minion for nothing


def test_the_tie_of_two_equal_uses_is_not_dominance():
    # the same buff on two own minions, and a position variant, never dominate each other
    own_two = sc.position(self_side=sc.side(board=(sc.minion("A", 2, 2, 1), sc.minion("C", 2, 2, 2))),
                          opponent=sc.side(board=(sc.minion("B", 2, 2, 1),)), hand=(sc.hand_card("BUFFER", "SPELL", 2),))
    actions = [sc.play("BUFFER", 0, "SPELL", 2, sc.target_minion("SELF", 1, "A")),
               sc.play("BUFFER", 0, "SPELL", 2, sc.target_minion("SELF", 2, "C"))]
    flags, _ = flags_of(own_two, actions)
    assert flags == {}


def test_removing_divine_shields_is_a_gain_not_self_harm():
    state = sc.position(
        self_side=sc.side(board=(sc.minion("A", 5, 5, 1),)),
        opponent=sc.side(board=(sc.minion("B", 6, 6, 1, divine_shield=True), sc.minion("C", 5, 5, 2, divine_shield=True))),
        hand=(sc.hand_card("SWEEP", "SPELL", 1),))
    flags, result = flags_of(state, [sc.play("SWEEP", 0, "SPELL", 1)])
    vector = direct_vector(state, forecast_action(state, sc.play("SWEEP", 0, "SPELL", 1), TEXTS, TRUSTED))
    assert vector[2] < 0 and vector[4] == 2        # own board loses Health, two enemy shields disappear
    assert flags == {}


def test_self_harm_on_a_vanilla_token_is_flagged_and_a_reasoned_alternative_is_not():
    own = (sc.minion("TOKEN", 1, 1, 1), sc.minion("A", 4, 5, 2))
    state = sc.position(self_side=sc.side(board=own), opponent=sc.side(board=(sc.minion("B", 2, 3, 1),)),
                        hand=(sc.hand_card("POKE", "SPELL", 1),))
    actions = [sc.play("POKE", 0, "SPELL", 1, sc.target_minion("SELF", 1, "TOKEN")),
               sc.play("POKE", 0, "SPELL", 1, sc.target_minion("OPPONENT", 1, "B")), sc.end_turn()]
    flags, _ = flags_of(state, actions)
    assert list(flags) == [(0, SELF_HARM)]


@pytest.mark.parametrize("extra,reason", [
    (sc.minion("WATCHER", 2, 3, 3), "BOARD_TRIGGER"),
    (sc.minion("AURA", 2, 3, 3, mechanics=("AURA",)), "AURA_ON_BOARD"),
    (sc.minion("MYSTERY", 2, 3, 3), "BOARD_TEXT_MISSING"),
])
def test_self_harm_abstains_when_something_visible_could_make_it_pay(extra, reason):
    own = (sc.minion("TOKEN", 1, 1, 1), extra)
    state = sc.position(self_side=sc.side(board=own), opponent=sc.side(board=()), hand=(sc.hand_card("POKE", "SPELL", 1),))
    actions = [sc.play("POKE", 0, "SPELL", 1, sc.target_minion("SELF", 1, "TOKEN"))]
    flags, result = flags_of(state, actions)
    assert flags == {} and (SELF_HARM, reason) in result.blocked, result.blocked


def test_the_death_of_the_target_with_a_deathrattle_is_an_abstention_not_a_flag():
    own = (sc.minion("DR", 1, 1, 1, mechanics=("DEATHRATTLE",)),)
    state = sc.position(self_side=sc.side(board=own), opponent=sc.side(board=()), hand=(sc.hand_card("POKE", "SPELL", 1),))
    flags, result = flags_of(state, [sc.play("POKE", 0, "SPELL", 1, sc.target_minion("SELF", 1, "DR"))])
    assert flags == {} and (SELF_HARM, "DEATHRATTLE_POSSIBLE") in result.blocked


def test_an_own_secret_or_quest_blocks_self_harm():
    state = sc.position(self_side=sc.side(board=(sc.minion("TOKEN", 1, 1, 1),), secret_count=1), opponent=sc.side(board=()),
                        hand=(sc.hand_card("POKE", "SPELL", 1),))
    flags, result = flags_of(state, [sc.play("POKE", 0, "SPELL", 1, sc.target_minion("SELF", 1, "TOKEN"))])
    assert flags == {} and (SELF_HARM, "OWN_SECRET_OR_QUEST") in result.blocked


def test_a_frenzy_style_self_damage_combo_is_not_called_harm():
    state = sc.position(self_side=sc.side(board=(sc.minion("FRENZY", 2, 4, 1),)), opponent=sc.side(board=()),
                        hand=(sc.hand_card("POKE", "SPELL", 1),))
    flags, result = flags_of(state, [sc.play("POKE", 0, "SPELL", 1, sc.target_minion("SELF", 1, "FRENZY"))])
    assert flags == {}                      # whatever the reason, the Frenzy text means no conclusion is drawn


def test_an_attack_that_costs_health_is_a_trade_not_self_harm():
    state = sc.position(self_side=sc.side(board=(sc.minion("A", 2, 1, 1),)), opponent=sc.side(board=(sc.minion("B", 3, 1, 1),)),
                        hand=())
    actions = [sc.attack(1, "A", sc.target_minion("OPPONENT", 1, "B")), sc.end_turn()]
    flags, _ = flags_of(state, actions)
    assert flags == {}


def test_unsupported_and_open_forecasts_give_no_conclusion_and_are_counted():
    state = sc.position(self_side=sc.side(board=(sc.minion("A", 2, 2, 1),), mana=0), opponent=sc.side(board=()),
                        hand=(sc.hand_card("POKE", "SPELL", 1), sc.hand_card("SPELLBOUND", "SPELL", 1)))
    actions = [sc.play("POKE", 0, "SPELL", 1, sc.target_minion("SELF", 1, "A")), sc.play("SPELLBOUND", 1, "SPELL", 1)]
    flags, result = flags_of(state, actions)
    assert flags == {} and result.insufficient[SELF_HARM] == 2           # too little mana; an unreadable text


def test_shadow_rows_carry_the_flags_and_the_abstentions_without_changing_forecast_digests():
    state = sc.position(self_side=sc.side(board=(sc.minion("A", 2, 2, 1),), hero_health=20),
                        opponent=sc.side(board=(sc.minion("B", 2, 2, 1),)), hand=(sc.hand_card("BUFFER", "SPELL", 2),))
    actions = [sc.play("BUFFER", 0, "SPELL", 2, sc.target_minion("OPPONENT", 1, "B")),
               sc.play("BUFFER", 0, "SPELL", 2, sc.target_minion("SELF", 1, "A")), sc.end_turn()]
    record = forecast_menu(state, [(i, i + 1, a) for i, a in enumerate(actions)], TEXTS, TRUSTED)
    rows = {r["index"]: r for r in record["actions"]}
    assert rows[0]["flags"] == {SIDE_MISDIRECTION: 1, SELF_HARM: None} and "flags" not in rows[1]   # a gift is both
    assert "diag" not in record or "flags" not in record["diag"]
    plain = forecast_action(state, actions[0], TEXTS, TRUSTED)
    from manamind.outcome.shadow import forecast_digest
    assert rows[0]["digest"] == forecast_digest(plain)


def test_a_failing_diagnostic_never_costs_the_forecasts(monkeypatch):
    import manamind.outcome.shadow as shadow_module

    def boom(*args, **kwargs):
        raise RuntimeError("private text")

    monkeypatch.setattr(shadow_module, "diagnose_menu", boom)
    state = sc.position(self_side=sc.side(), opponent=sc.side(), hand=())
    record = forecast_menu(state, [(0, 1, sc.end_turn())], TEXTS, TRUSTED)
    assert record["diag"] == {"error": "RuntimeError"} and record["computed"] == 1
    assert "private" not in json.dumps(record)


def test_the_diagnostics_know_no_card_ids():
    source = (ROOT / "src/manamind/outcome/diagnostics.py").read_text(encoding="utf-8")
    assert not re.search(r"\b[A-Z]{2,5}_[A-Za-z0-9_]*\d", source)
    assert dominates((1, 0), (0, 0)) and not dominates((1, 0), (1, 0)) and not dominates((1, -1), (0, 0))


def test_the_location_on_an_own_vanilla_token_is_self_harm_and_on_a_big_own_minion_is_not():
    state = with_location(own=(sc.minion("TOKEN", 1, 1, 1), sc.minion("A", 4, 5, 2)), enemy=(sc.minion("B", 2, 2, 1),))
    actions = [activate(sc.target_minion("SELF", 1, "TOKEN")), activate(sc.target_minion("SELF", 2, "A")),
               activate(sc.target_minion("OPPONENT", 1, "B")), sc.end_turn()]
    flags, result = flags_of(state, actions)
    assert flags == {(0, SELF_HARM): None, (2, SELF_HARM): None, (2, SIDE_MISDIRECTION): 1}
    forecasts = {i: f for i, _, f in menu_of(state, actions)}
    assert direct_vector(state, forecasts[1]) == (0, 0, 1, 0, 0, 0)         # +2 Attack, -1 Health on the big minion
    assert direct_vector(state, forecasts[0]) == (0, 0, -2, 0, 0, 0)        # a 1/1 dies: its Attack and Health are gone


def test_the_location_on_a_token_with_a_deathrattle_or_a_trigger_beside_it_abstains():
    cases = [((sc.minion("TOKEN", 1, 1, 1), sc.minion("WATCHER", 2, 3, 2)), "TOKEN", "BOARD_TRIGGER"),
             ((sc.minion("DR", 1, 1, 1, mechanics=("DEATHRATTLE",)), sc.minion("A", 2, 3, 2)), "DR", "DEATHRATTLE_POSSIBLE")]
    for own, target, reason in cases:
        state = with_location(own=own)
        flags, result = flags_of(state, [activate(sc.target_minion("SELF", 1, target))])
        assert flags == {} and (SELF_HARM, reason) in result.blocked, (target, result.blocked)


def test_a_hit_on_a_one_health_enemy_that_dies_is_progress_and_a_hit_that_only_buffs_it_is_not():
    state = with_location(own=(sc.minion("A", 3, 3, 1),), enemy=(sc.minion("B", 2, 1, 1), sc.minion("C", 2, 4, 2)))
    actions = [activate(sc.target_minion("OPPONENT", 1, "B")), activate(sc.target_minion("OPPONENT", 2, "C"))]
    flags, _ = flags_of(state, actions)
    assert flags == {(1, SELF_HARM): None}      # +2 Attack for the enemy against 1 damage: strictly worse for SELF
