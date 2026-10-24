"""Independent checks of the immediate-outcome forecaster.

Expected numbers are derived by hand from public Hearthstone rules, never by running the code under
test. Card texts are quoted into inline records so the arithmetic is isolated from catalog drift;
one test pins the real catalog text of the motivating card.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from manamind.outcome import (
    ObservedContext, Status, TextSource, UnknownKind, forecast_action, forecast_alternatives, render_comparison,
    summarise,
)
from manamind.outcome import scenario as sc
from manamind.outcome.grammar import trigger_events


def _ctx(**kwargs) -> ObservedContext:
    """These positions are written by hand, so their Spell Damage is known."""
    return ObservedContext(**{"trust_spell_damage": True, "spell_healing_doubled": False, **kwargs})

CATALOG = Path(__file__).resolve().parents[1] / "data" / "cards" / "standard_current_enUS.json"


def _spell(card_id: str, text: str, mechanics: tuple[str, ...] = ()) -> dict:
    return {"id": card_id, "text": text, "type": "SPELL", "mechanics": list(mechanics)}


def _body(card_id: str, text: str = "", mechanics: tuple[str, ...] = (), card_type: str = "MINION") -> dict:
    return {"id": card_id, "text": text, "type": card_type, "mechanics": list(mechanics)}


HOLD = "<b>Prepare</b>\nGive a minion +5/+5 and <b>Lifesteal</b>."
TEXTS = TextSource.from_records([
    _spell("T_HOLD", HOLD),
    _spell("T_BUFF", "Give a minion +2/+3 and <b>Taunt</b>."),
    _spell("T_BUFF_HP", "Give a minion +4 Health."),
    _spell("T_BOLT3", "Deal $3 damage to a minion."),
    _spell("T_BOLT5", "Deal $5 damage to a minion."),
    _spell("T_BOLT_ANY", "Deal $4 damage."),
    _spell("T_BOLT_NOSP", "Deal $3 damage to a minion.", ("IMMUNETOSPELLPOWER",)),
    _spell("T_LIFESTEAL", "<b>Lifesteal</b>\nDeal $8 damage to a minion."),
    _spell("T_HEAL", "Restore #4 Health."),
    _spell("T_NOVA", "Deal $2 damage to all minions."),
    _spell("T_BURN_ALL", "<b>Lifesteal</b>. Deal $3 damage to all characters."),
    _spell("T_PURGE", "Destroy all minions with 5 or more Attack."),
    _spell("T_KILL", "Destroy a minion."),
    _spell("T_KILL_DAMAGED", "Destroy a damaged enemy minion."),
    _spell("T_FREEZE", "Freeze an enemy."),
    _spell("T_COND", "Deal $3 damage to a minion. If it dies, restore #3 Health to the enemy hero."),
    _spell("T_COND_OPAQUE", "Deal $3 damage to a minion. If it dies, draw a card."),
    _spell("T_RANDOM", "Deal $2 damage to a random enemy."),
    _spell("T_EXTRA", "Deal $2 damage to a minion. Draw a card."),
    _spell("T_ARMOR", "Gain 5 Armor."),
    _spell("T_SHIELD", "Give a minion <b>Divine Shield</b>."),
    _spell("T_COIN", "Gain 1 Mana Crystal this turn only."),
    _spell("T_CHEAP", "Costs (0) if you control a minion. Deal $1 damage to a minion."),
    _body("T_WEAPON", "<b>Lifesteal</b>", ("LIFESTEAL",), "WEAPON"),
    _body("T_WEAPON_TRIGGER", "After your hero attacks, gain 1 Armor.", (), "WEAPON"),
    _body("T_VANILLA"),
    _body("T_TAUNT", "<b>Taunt</b>", ("TAUNT",)),
    _body("T_DR", "<b>Deathrattle:</b> Draw a card.", ("DEATHRATTLE",)),
    _body("T_ENDTURN", "At the end of your turn, gain +1 Attack."),
    _body("T_SPELLWATCH", "After you cast a spell, deal 1 damage to all enemies."),
    _body("T_FRENZY", "<b>Frenzy:</b> Gain +2 Attack.", ("TRIGGER_VISUAL",)),
    _body("T_AURA", "Your other minions have +1 Attack.", ("AURA",)),
    _body("T_BC", "<b>Battlecry:</b> Deal 1 damage to a minion.", ("BATTLECRY",)),
    _body("T_BC_DRAW", "<b>Battlecry:</b> Draw a card.", ("BATTLECRY",)),
    _body("T_RUSH", "<b>Rush</b>", ("RUSH",)),
    _body("T_FREEZE_TRIGGER", "Whenever a minion is Frozen, gain +1 Attack."),
    _body("T_FREEZE_SOURCE_TRIGGER", "<b>Battlecry:</b> Freeze an enemy. "
          "Whenever a minion is Frozen, gain +1 Attack.", ("BATTLECRY",)),
    _body("T_FREEZE_SOURCE_END_TRIGGER", "<b>Battlecry:</b> Freeze an enemy. "
          "At the end of your turn, gain +1 Attack.", ("BATTLECRY",)),
    _body("T_LOC", "Deal $1 damage to a minion.", (), "LOCATION"),
    {"id": "T_POWER_HEAL", "text": "Restore #2 Health.", "type": "HERO_POWER"},
    {"id": "T_POWER_DMG", "text": "Deal $1 damage.", "type": "HERO_POWER"},
    {"id": "T_POWER_ARMOR", "text": "Gain 2 Armor.", "type": "HERO_POWER"},
])
for _id in ("E1", "E2", "E3", "M1", "M2", "SIX", "Y"):
    TEXTS = TEXTS.extended([_body(_id)])


def _change(forecast, side, field, zone="BOARD", position=None):
    hits = [c for c in forecast.changes if c.ref.side == side and c.field == field and c.ref.zone == zone
            and (position is None or c.ref.position == position)]
    assert len(hits) == 1, (field, [c.describe() for c in forecast.changes])
    return hits[0]


def _state(*, mine=(), theirs=(), hand=(), mana=10, opponent_kwargs=None, **self_kwargs):
    return sc.position(
        self_side=sc.side(board=tuple(mine), mana=mana, **self_kwargs),
        opponent=sc.side(board=tuple(theirs), **(opponent_kwargs or {})),
        hand=tuple(hand))


def _pos(forecast):
    """The predicted position: the real one when EXACT, else the lower-bound diagnostic one."""
    if forecast.status is Status.EXACT:
        return forecast.exact_state()
    return forecast.partial_state().diagnostic_state()


def _cast(card_id, target=None, cost=3, index=0):
    return sc.play(card_id, index, "SPELL", cost, target)


def _forecast(state, action, context=None):
    return forecast_action(state, action, TEXTS, context or _ctx())


# ----- Hold Them Off! ----------------------------------------------------------------------------

def _hold_state():
    return _state(mine=[sc.minion("M1", 3, 3, 1)], theirs=[sc.minion("SIX", 6, 6, 1), sc.minion("E2", 2, 2, 2)],
                  hand=[sc.hand_card("T_HOLD", "SPELL", 5)], mana=5)


def test_hold_them_off_buffs_the_enemy_minion_exactly():
    state = _hold_state()
    forecast = _forecast(state, _cast("T_HOLD", sc.target_minion("OPPONENT", 1, "SIX"), 5))
    assert forecast.status is Status.EXACT, forecast.unknowns
    assert (_change(forecast, "OPPONENT", "attack").before, _change(forecast, "OPPONENT", "attack").after) == (6, 11)
    assert _change(forecast, "OPPONENT", "health").after == 11
    assert _change(forecast, "OPPONENT", "max_health").after == 11
    lifesteal = _change(forecast, "OPPONENT", "lifesteal")
    assert (lifesteal.before, lifesteal.after) == (False, True)
    assert _change(forecast, "SELF", "available_mana", "PLAYER").after == 0
    # nothing else of the opponent changes: the second minion and the hero are untouched
    assert not [c for c in forecast.changes if c.ref.side == "OPPONENT" and c.ref.position == 2]
    assert not [c for c in forecast.changes if c.ref.zone == "HERO"]
    after = _pos(forecast).opponent.board
    assert (after[0].current_attack, after[0].current_health, after[0].max_health, after[0].lifesteal) == (11, 11, 11, True)
    assert _pos(forecast).self_player.board[0].current_attack == 3      # SELF minion untouched
    summary = summarise(state, forecast)
    assert summary.deltas["OPPONENT"]["board_attack"] == 5 and summary.deltas["SELF"]["board_attack"] == 0
    assert "only improve OPPONENT-controlled" in summary.note
    assert any("Prepare" in text for text in forecast.assumptions)


def test_same_text_on_an_unrelated_card_id_gives_the_same_changes():
    state = _hold_state()
    real = _forecast(state, _cast("T_HOLD", sc.target_minion("OPPONENT", 1, "SIX"), 5))
    renamed_state = _state(mine=[sc.minion("M1", 3, 3, 1)], theirs=[sc.minion("SIX", 6, 6, 1)],
                           hand=[sc.hand_card("T_OTHER", "SPELL", 5)], mana=5)
    other = TEXTS.extended([_spell("T_OTHER", HOLD)])
    twin = forecast_action(renamed_state, _cast("T_OTHER", sc.target_minion("OPPONENT", 1, "SIX"), 5), other)
    key = lambda f: sorted((c.ref.side, c.field, c.before, c.after) for c in f.changes if c.ref.zone != "HAND")
    assert key(real) == key(twin)


def test_pinned_catalog_text_of_jail_913_parses_to_the_same_effect():
    texts = TextSource.from_files(CATALOG).extended([_body("SIX")])
    state = _state(theirs=[sc.minion("SIX", 6, 6, 1)], hand=[sc.hand_card("JAIL_913", "SPELL", 5)], mana=5)
    forecast = forecast_action(state, _cast("JAIL_913", sc.target_minion("OPPONENT", 1, "SIX"), 5), texts)
    assert forecast.status is Status.EXACT
    assert (_change(forecast, "OPPONENT", "attack").after, _change(forecast, "OPPONENT", "health").after) == (11, 11)
    assert _change(forecast, "OPPONENT", "lifesteal").after is True


def test_buffing_ones_own_minion_and_alternative_targets_are_independent():
    state = _hold_state()
    own = sc.target_minion("SELF", 1, "M1")
    enemy_small = sc.target_minion("OPPONENT", 2, "E2")
    forecasts = forecast_alternatives(state, [
        _cast("T_HOLD", sc.target_minion("OPPONENT", 1, "SIX"), 5), _cast("T_HOLD", own, 5),
        _cast("T_HOLD", enemy_small, 5), sc.end_turn()], TEXTS)
    assert [f.status for f in forecasts] == [Status.EXACT] * 4
    assert _change(forecasts[1], "SELF", "attack").after == 8
    assert _change(forecasts[2], "OPPONENT", "attack", position=2).after == 7
    assert not [c for c in forecasts[3].changes]
    assert render_comparison(state, forecasts)                         # renders without error
    # forecasting did not change the input and the order of alternatives does not matter
    assert state == _hold_state()
    again = forecast_alternatives(state, [sc.end_turn(), _cast("T_HOLD", own, 5)], TEXTS)
    assert again[1].changes == forecasts[1].changes


def test_regrant_of_a_held_keyword_changes_nothing():
    state = _state(theirs=[sc.minion("SIX", 6, 6, 1, lifesteal=True)], hand=[sc.hand_card("T_HOLD", "SPELL", 5)])
    forecast = _forecast(state, _cast("T_HOLD", sc.target_minion("OPPONENT", 1, "SIX"), 5))
    assert not [c for c in forecast.changes if c.field == "lifesteal"]
    assert any("already has lifesteal" in event.note for event in forecast.events)
    assert _change(forecast, "OPPONENT", "attack").after == 11


def test_health_buff_on_a_damaged_minion_raises_current_and_maximum_together():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1, max_health=6)], hand=[sc.hand_card("T_BUFF_HP", "SPELL", 1)])
    forecast = _forecast(state, _cast("T_BUFF_HP", sc.target_minion("OPPONENT", 1, "E1"), 1))
    assert (_change(forecast, "OPPONENT", "health").after, _change(forecast, "OPPONENT", "max_health").after) == (7, 10)


# ----- damage and its sequencing ------------------------------------------------------------------

def _damage(spell, defender, *, spell_damage=0, extra_theirs=(), target_hero=False, **opp):
    state = _state(theirs=[defender, *extra_theirs], hand=[sc.hand_card(spell, "SPELL", 3)],
                   spell_damage=spell_damage, opponent_kwargs=opp)
    target = sc.target_hero("OPPONENT") if target_hero else sc.target_minion("OPPONENT", 1, defender.card.card_id)
    return state, _forecast(state, _cast(spell, target))


def test_plain_damage_and_lethal_damage():
    _, hit = _damage("T_BOLT3", sc.minion("E1", 4, 4, 1))
    assert _change(hit, "OPPONENT", "health").after == 1 and hit.status is Status.EXACT
    _, kill = _damage("T_BOLT5", sc.minion("E1", 4, 4, 1))
    assert _change(kill, "OPPONENT", "present").after is False
    assert _pos(kill).opponent.board == ()
    assert kill.status is Status.EXACT


def test_spell_damage_applies_to_marked_spell_damage_only():
    _, boosted = _damage("T_BOLT3", sc.minion("E1", 4, 4, 1), spell_damage=2)
    assert _change(boosted, "OPPONENT", "present").after is False              # 3+2=5 kills the 4/4
    _, immune = _damage("T_BOLT_NOSP", sc.minion("E1", 4, 4, 1), spell_damage=2)
    assert _change(immune, "OPPONENT", "health").after == 1                    # card ignores Spell Damage


def test_divine_shield_and_immune_prevent_damage():
    _, shield = _damage("T_BOLT3", sc.minion("E1", 4, 4, 1, divine_shield=True))
    assert not [c for c in shield.changes if c.field == "health"]
    assert _change(shield, "OPPONENT", "divine_shield").after is False
    _, immune = _damage("T_BOLT3", sc.minion("E1", 4, 4, 1, immune=True))
    assert not [c for c in immune.changes if c.ref.side == "OPPONENT"]


def test_armor_absorbs_hero_damage_first():
    state = _state(hand=[sc.hand_card("T_BOLT_ANY", "SPELL", 3)], opponent_kwargs={"armor": 3, "hero_health": 20})
    forecast = _forecast(state, _cast("T_BOLT_ANY", sc.target_hero("OPPONENT")))
    assert _change(forecast, "OPPONENT", "armor", "HERO").after == 0
    assert _change(forecast, "OPPONENT", "health", "HERO").after == 19


def test_unobserved_hero_divine_shield_makes_hero_damage_partial():
    state = _state(hand=[sc.hand_card("T_BOLT_ANY", "SPELL", 3)], opponent_kwargs={"hero_divine_shield": None})
    forecast = _forecast(state, _cast("T_BOLT_ANY", sc.target_hero("OPPONENT")))
    assert forecast.status is Status.PARTIAL
    assert any(u.kind is UnknownKind.MODIFIER_UNOBSERVED and u.alters_listed for u in forecast.unknowns)
    assert not _change(forecast, "OPPONENT", "health", "HERO").exact


def test_lifesteal_heals_the_damage_dealt_including_overkill_but_not_a_shield_pop():
    state = _state(theirs=[sc.minion("E1", 2, 1, 1)], hand=[sc.hand_card("T_LIFESTEAL", "SPELL", 4)],
                   hero_health=20)
    forecast = _forecast(state, _cast("T_LIFESTEAL", sc.target_minion("OPPONENT", 1, "E1"), 4))
    assert _change(forecast, "SELF", "health", "HERO").after == 28            # 8 dealt, not 1 killed
    shielded = _state(theirs=[sc.minion("E1", 2, 1, 1, divine_shield=True)],
                      hand=[sc.hand_card("T_LIFESTEAL", "SPELL", 4)], hero_health=20)
    popped = _forecast(shielded, _cast("T_LIFESTEAL", sc.target_minion("OPPONENT", 1, "E1"), 4))
    assert not [c for c in popped.changes if c.ref.zone == "HERO"]


def test_aoe_lifesteal_heals_after_all_damage_is_dealt():
    # Own hero at full Health takes 3 and each of two enemy minions takes 3: heals total 9, capped by the
    # 3 missing Health -> back to 30. Healing before the hero is hit would leave it at 27.
    state = _state(theirs=[sc.minion("E1", 2, 5, 1), sc.minion("E2", 2, 5, 2)],
                   hand=[sc.hand_card("T_BURN_ALL", "SPELL", 6)])
    forecast = _forecast(state, _cast("T_BURN_ALL", None, 6))
    assert not [c for c in forecast.changes if c.ref.side == "SELF" and c.ref.zone == "HERO"
                and c.field == "health"], forecast.changes                        # 30 -> 27 -> 30: net zero
    assert _change(forecast, "OPPONENT", "health", position=1).after == 2
    assert _change(forecast, "OPPONENT", "health", "HERO").after == 27


def test_area_damage_hits_each_minion_with_its_own_protection():
    state = _state(theirs=[sc.minion("E1", 3, 2, 1), sc.minion("E2", 3, 2, 2, divine_shield=True),
                           sc.minion("E3", 3, 3, 3)], mine=[sc.minion("M1", 1, 2, 1)],
                   hand=[sc.hand_card("T_NOVA", "SPELL", 2)])
    forecast = _forecast(state, _cast("T_NOVA", None, 2))
    deaths = sorted((c.ref.side, c.ref.position) for c in forecast.changes
                    if c.field == "present" and c.ref.zone == "BOARD")
    assert deaths == [("OPPONENT", 1), ("SELF", 1)]
    assert _change(forecast, "OPPONENT", "divine_shield").after is False
    assert _change(forecast, "OPPONENT", "health", position=3).after == 1
    assert [e.card.card_id for e in _pos(forecast).opponent.board] == ["E2", "E3"]
    assert [e.board_position for e in _pos(forecast).opponent.board] == [1, 2]


def test_conditional_clause_follows_the_predicted_outcome():
    kill_state = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_COND", "SPELL", 2)],
                        opponent_kwargs={"hero_health": 20})
    killed = _forecast(kill_state, _cast("T_COND", sc.target_minion("OPPONENT", 1, "E1"), 2))
    assert _change(killed, "OPPONENT", "health", "HERO").after == 23            # restores 3 to the enemy hero
    survive_state = _state(theirs=[sc.minion("E1", 2, 4, 1)], hand=[sc.hand_card("T_COND", "SPELL", 2)],
                           opponent_kwargs={"hero_health": 20})
    survived = _forecast(survive_state, _cast("T_COND", sc.target_minion("OPPONENT", 1, "E1"), 2))
    assert not [c for c in survived.changes if c.ref.zone == "HERO" and c.ref.side == "OPPONENT"]
    shielded = _state(theirs=[sc.minion("E1", 2, 3, 1, divine_shield=True)], opponent_kwargs={"hero_health": 20},
                      hand=[sc.hand_card("T_COND", "SPELL", 2)])
    prevented = _forecast(shielded, _cast("T_COND", sc.target_minion("OPPONENT", 1, "E1"), 2))
    assert not [c for c in prevented.changes if c.ref.zone == "HERO" and c.ref.side == "OPPONENT"]


def test_conditional_opaque_clause_only_matters_when_its_condition_holds():
    dies = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_COND_OPAQUE", "SPELL", 2)])
    unknown = _forecast(dies, _cast("T_COND_OPAQUE", sc.target_minion("OPPONENT", 1, "E1"), 2))
    assert unknown.status is Status.PARTIAL
    assert any(u.kind is UnknownKind.UNPARSED_CLAUSE for u in unknown.unknowns)
    survives = _state(theirs=[sc.minion("E1", 2, 9, 1)], hand=[sc.hand_card("T_COND_OPAQUE", "SPELL", 2)])
    assert _forecast(survives, _cast("T_COND_OPAQUE", sc.target_minion("OPPONENT", 1, "E1"), 2)).status is Status.EXACT


# ----- healing ------------------------------------------------------------------------------------

def test_healing_is_capped_by_maximum_health_and_uses_the_bonus_per_packet():
    state = _state(mine=[sc.minion("M1", 2, 3, 1, max_health=5)], hand=[sc.hand_card("T_HEAL", "SPELL", 1)],
                   healing_bonus=0)
    capped = _forecast(state, _cast("T_HEAL", sc.target_minion("SELF", 1, "M1"), 1),
                       _ctx(healing_does_damage=False))
    assert _change(capped, "SELF", "health").after == 5 and capped.status is Status.EXACT
    boosted = replace(state, self_player=replace(state.self_player, healing_bonus=1,
                                                 board=(sc.minion("M1", 2, 1, 1, max_health=9),)))
    assert _change(_forecast(boosted, _cast("T_HEAL", sc.target_minion("SELF", 1, "M1"), 1),
                             _ctx(healing_does_damage=False)), "SELF", "health").after == 6   # 1 + 4 + 1


def test_unobserved_healing_modifiers_give_a_lower_bound_not_a_number():
    state = _state(mine=[sc.minion("M1", 2, 3, 1, max_health=9)], hand=[sc.hand_card("T_HEAL", "SPELL", 1)],
                   healing_bonus=None)
    forecast = _forecast(state, _cast("T_HEAL", sc.target_minion("SELF", 1, "M1"), 1),
                         _ctx(healing_does_damage=False))
    change = _change(forecast, "SELF", "health")
    assert change.after is None and change.at_least == 3 and forecast.status is Status.PARTIAL
    assert _pos(forecast).self_player.board[0].current_health == 3          # not invented


def test_sanctum_state_unobserved_or_active_is_not_hidden():
    state = _state(mine=[sc.minion("M1", 2, 3, 1, max_health=9)], hand=[sc.hand_card("T_HEAL", "SPELL", 1)])
    default = _forecast(state, _cast("T_HEAL", sc.target_minion("SELF", 1, "M1"), 1))
    assert default.status is Status.PARTIAL                                     # healing-to-damage not observed
    active = _forecast(state, _cast("T_HEAL", sc.target_minion("SELF", 1, "M1"), 1),
                       _ctx(healing_does_damage=True))
    assert active.status is Status.UNSUPPORTED and active.unsupported_reason == "HEALING_DOES_DAMAGE_ACTIVE"


# ----- destroy, keywords, armor, mana -------------------------------------------------------------

def test_conditional_mass_destroy_uses_current_attack_of_both_sides():
    state = _state(mine=[sc.minion("M1", 5, 5, 1), sc.minion("M2", 4, 4, 2)],
                   theirs=[sc.minion("E1", 6, 1, 1), sc.minion("E2", 4, 9, 2)],
                   hand=[sc.hand_card("T_PURGE", "SPELL", 4)])
    forecast = _forecast(state, _cast("T_PURGE", None, 4))
    gone = sorted((c.ref.side, c.ref.position) for c in forecast.changes if c.field == "present"
                  and c.ref.zone == "BOARD")
    assert gone == [("OPPONENT", 1), ("SELF", 1)]
    assert [e.card.card_id for e in _pos(forecast).self_player.board] == ["M2"]


def test_destroy_an_immune_minion_is_not_forecast():
    state = _state(theirs=[sc.minion("E1", 2, 2, 1, immune=True)], hand=[sc.hand_card("T_KILL", "SPELL", 3)])
    forecast = _forecast(state, _cast("T_KILL", sc.target_minion("OPPONENT", 1, "E1")))
    assert forecast.status is Status.UNSUPPORTED and forecast.partial_state() is None


def test_destroy_damaged_enemy_minion_uses_observed_current_health():
    state = _state(theirs=[sc.minion("E1", 2, 2, 1, max_health=3)],
                   hand=[sc.hand_card("T_KILL_DAMAGED", "SPELL", 1)])
    forecast = _forecast(state, _cast("T_KILL_DAMAGED", sc.target_minion("OPPONENT", 1, "E1"), 1))
    assert forecast.status is Status.EXACT
    assert _change(forecast, "OPPONENT", "present").after is False
    assert _pos(forecast).opponent.board == ()


def test_destroy_damaged_fails_closed_when_visible_target_is_not_damaged():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)],
                   hand=[sc.hand_card("T_KILL_DAMAGED", "SPELL", 1)])
    forecast = _forecast(state, _cast("T_KILL_DAMAGED", sc.target_minion("OPPONENT", 1, "E1"), 1))
    assert forecast.status is Status.UNSUPPORTED
    assert forecast.unsupported_reason == "TARGET_NOT_DAMAGED"
    assert forecast.partial_state() is None


def test_freeze_sets_the_observed_minion_flag_and_prevents_attack():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1, can_attack=True)],
                   hand=[sc.hand_card("T_FREEZE", "SPELL", 1)])
    forecast = _forecast(state, _cast("T_FREEZE", sc.target_minion("OPPONENT", 1, "E1"), 1))
    assert forecast.status is Status.EXACT
    assert _change(forecast, "OPPONENT", "frozen").after is True
    assert _change(forecast, "OPPONENT", "can_attack").after is False
    assert _pos(forecast).opponent.board[0].frozen
    assert not _pos(forecast).opponent.board[0].can_attack
    assert any(event.kind == "FREEZE" for event in forecast.events)


def test_freeze_sets_an_unobserved_enemy_hero_frozen_flag():
    state = _state(hand=[sc.hand_card("T_FREEZE", "SPELL", 1)],
                   opponent_kwargs={"hero_frozen": None})
    forecast = _forecast(state, _cast("T_FREEZE", sc.target_hero("OPPONENT"), 1))
    assert forecast.status is Status.EXACT
    assert _change(forecast, "OPPONENT", "frozen", "HERO").after is True
    assert _pos(forecast).opponent.hero_frozen is True
    assert _pos(forecast).opponent.hero_freeze_turns_remaining is None


def test_pinned_catalog_glacial_shard_freezes_its_selected_enemy():
    texts = TextSource.from_files(CATALOG).extended([_body("E1")])
    state = _state(theirs=[sc.minion("E1", 2, 3, 1, can_attack=True)],
                   hand=[sc.hand_card("CORE_UNG_205", "MINION", 1, attack=2, health=1)])
    context = _ctx(hand_keywords=(frozenset(),), hand_keywords_match_card=True)
    action = sc.play("CORE_UNG_205", 0, "MINION", 1,
                     sc.target_minion("OPPONENT", 1, "E1"), play_position=1)
    forecast = forecast_action(state, action, texts, context)
    assert forecast.status is Status.EXACT
    assert _change(forecast, "OPPONENT", "frozen").after is True
    assert _change(forecast, "OPPONENT", "can_attack").after is False
    assert _pos(forecast).self_player.board[0].card.card_id == "CORE_UNG_205"


def test_freeze_trigger_on_the_target_blocks_an_exact_forecast():
    texts = TEXTS.extended([_body("E1", "Whenever a minion is Frozen, gain +1 Attack.")])
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_FREEZE", "SPELL", 1)])
    forecast = forecast_action(state, _cast("T_FREEZE", sc.target_minion("OPPONENT", 1, "E1"), 1), texts, _ctx())
    assert forecast.status is Status.PARTIAL
    assert any(unknown.tag == "BOARD_TRIGGER" and "may fire on ['FREEZE']" in unknown.detail
               for unknown in forecast.unknowns)


def test_freeze_trigger_word_forms_are_classified_and_unknown_conditions_stay_any():
    for condition in (
        "Whenever you freeze a minion, gain +1 Attack.",
        "Whenever a minion freezes, gain +1 Attack.",
        "Whenever a minion is frozen, gain +1 Attack.",
        "After freezing a minion, gain +1 Attack.",
        "After you froze a minion, gain +1 Attack.",
    ):
        assert trigger_events(condition) == frozenset({"FREEZE"})
    assert trigger_events("Whenever the stars align, gain +1 Attack.") == frozenset({"ANY"})


def test_freeze_trigger_does_not_block_an_action_without_freeze():
    texts = TEXTS.extended([_body("E1", "Whenever a minion is Frozen, gain +1 Attack.")])
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_ARMOR", "SPELL", 2)])
    forecast = forecast_action(state, _cast("T_ARMOR", None, 2), texts, _ctx())
    assert forecast.status is Status.EXACT
    assert not any(unknown.tag == "BOARD_TRIGGER" for unknown in forecast.unknowns)


def test_new_minion_freeze_trigger_is_seen_when_its_battlecry_freezes():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)],
                   hand=[sc.hand_card("T_FREEZE_SOURCE_TRIGGER", "MINION", 1, attack=2, health=1)])
    action = sc.play("T_FREEZE_SOURCE_TRIGGER", 0, "MINION", 1,
                     sc.target_minion("OPPONENT", 1, "E1"), play_position=1)
    context = _ctx(hand_keywords=(frozenset(),), hand_keywords_match_card=True)
    forecast = forecast_action(state, action, TEXTS, context)
    assert forecast.status is Status.PARTIAL
    assert any(unknown.tag == "BOARD_TRIGGER" and "may fire on ['FREEZE']" in unknown.detail
               for unknown in forecast.unknowns)


def test_new_minion_non_freeze_trigger_is_not_activated_by_freeze():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)],
                   hand=[sc.hand_card("T_FREEZE_SOURCE_END_TRIGGER", "MINION", 1, attack=2, health=1)])
    action = sc.play("T_FREEZE_SOURCE_END_TRIGGER", 0, "MINION", 1,
                     sc.target_minion("OPPONENT", 1, "E1"), play_position=1)
    context = _ctx(hand_keywords=(frozenset(),), hand_keywords_match_card=True)
    forecast = forecast_action(state, action, TEXTS, context)
    assert forecast.status is Status.EXACT
    assert not any(unknown.tag == "BOARD_TRIGGER" for unknown in forecast.unknowns)


def test_unknown_trigger_condition_still_blocks_exact_conservatively():
    texts = TEXTS.extended([_body("E1", "Whenever the stars align, gain +1 Attack.")])
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_ARMOR", "SPELL", 2)])
    forecast = forecast_action(state, _cast("T_ARMOR", None, 2), texts, _ctx())
    assert forecast.status is Status.PARTIAL
    assert any(unknown.tag == "BOARD_TRIGGER" and "unreadable condition" in unknown.detail
               for unknown in forecast.unknowns)


def test_freeze_on_an_immune_minion_fails_closed():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1, immune=True)],
                   hand=[sc.hand_card("T_FREEZE", "SPELL", 1)])
    forecast = _forecast(state, _cast("T_FREEZE", sc.target_minion("OPPONENT", 1, "E1"), 1))
    assert forecast.status is Status.UNSUPPORTED
    assert forecast.unsupported_reason == "FREEZE_ON_IMMUNE_UNREVIEWED"
    assert forecast.partial_state() is None


def test_pinned_catalog_destroy_damaged_text_parses_generically():
    texts = TextSource.from_files(CATALOG).extended([_body("E1")])
    state = _state(theirs=[sc.minion("E1", 2, 2, 1, max_health=3)],
                   hand=[sc.hand_card("CORE_CS2_108", "SPELL", 1)])
    forecast = forecast_action(
        state, _cast("CORE_CS2_108", sc.target_minion("OPPONENT", 1, "E1"), 1), texts, _ctx())
    assert forecast.status is Status.EXACT
    assert _change(forecast, "OPPONENT", "present").after is False


def test_armor_divine_shield_grant_and_temporary_mana():
    state = _state(mine=[sc.minion("M1", 1, 1, 1)], hand=[sc.hand_card("T_ARMOR", "SPELL", 2),
                                                           sc.hand_card("T_SHIELD", "SPELL", 1),
                                                           sc.hand_card("T_COIN", "SPELL", 0)], mana=3)
    assert _change(_forecast(state, _cast("T_ARMOR", None, 2)), "SELF", "armor", "HERO").after == 5
    shield = _forecast(state, _cast("T_SHIELD", sc.target_minion("SELF", 1, "M1"), 1, index=1))
    assert _change(shield, "SELF", "divine_shield").after is True
    coin = _forecast(state, _cast("T_COIN", None, 0, index=2))
    assert _change(coin, "SELF", "available_mana", "PLAYER").after == 4


def test_cost_only_sentences_do_not_add_effects():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_CHEAP", "SPELL", 0)])
    forecast = _forecast(state, _cast("T_CHEAP", sc.target_minion("OPPONENT", 1, "E1"), 0))
    assert forecast.status is Status.EXACT and _change(forecast, "OPPONENT", "health").after == 2


# ----- unknowns and unsupported ---------------------------------------------------------------------

def test_unknown_text_and_extra_sentences_downgrade_but_keep_the_known_part():
    state = _state(theirs=[sc.minion("E1", 2, 5, 1)], hand=[sc.hand_card("T_EXTRA", "SPELL", 2)])
    extra = _forecast(state, _cast("T_EXTRA", sc.target_minion("OPPONENT", 1, "E1"), 2))
    assert extra.status is Status.PARTIAL and _change(extra, "OPPONENT", "health").after == 3
    assert [u for u in extra.unknowns if u.kind is UnknownKind.UNPARSED_CLAUSE and u.adds_unlisted]
    random = _forecast(_state(theirs=[sc.minion("E1", 2, 5, 1)], hand=[sc.hand_card("T_RANDOM", "SPELL", 2)]),
                       _cast("T_RANDOM", None, 2))
    assert [u.kind for u in random.unknowns] == [UnknownKind.RANDOM_OUTCOME]
    assert not [c for c in random.changes if c.ref.side == "OPPONENT"]
    ghost = _forecast(_state(hand=[sc.hand_card("T_MISSING", "SPELL", 2)]), _cast("T_MISSING", None, 2))
    assert ghost.status is Status.PARTIAL and ghost.unknowns[0].kind is UnknownKind.TEXT_UNAVAILABLE
    assert _change(ghost, "SELF", "available_mana", "PLAYER").after == 8         # the cost itself is still exact


def test_unsupported_actions_return_no_state():
    state = _state(hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    for action in ({"type": "TRADE_CARD"}, sc.play("T_BOLT3", 0, "WEAPON", 3),
                   sc.play("T_BOLT3", 5, "SPELL", 3), _cast("T_BOLT3", sc.target_minion("OPPONENT", 4, "E1"))):
        forecast = _forecast(state, action)
        assert forecast.status is Status.UNSUPPORTED and forecast.unsupported_reason
        assert forecast.partial_state() is None and forecast.changes == ()


def test_target_that_does_not_match_the_text_is_rejected():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    forecast = _forecast(state, _cast("T_BOLT3", sc.target_hero("OPPONENT")))
    assert forecast.status is Status.UNSUPPORTED and forecast.unsupported_reason == "TARGET_DOES_NOT_MATCH_TEXT"


def test_duplicate_card_ids_are_addressed_by_position():
    state = _state(theirs=[sc.minion("E1", 2, 4, 1), sc.minion("E1", 2, 4, 2)],
                   hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    second = _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 2, "E1")))
    assert [c.ref.position for c in second.changes if c.field == "health"] == [2]
    assert _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 3, "E1"))).status is Status.UNSUPPORTED


# ----- hidden reactions --------------------------------------------------------------------------

def test_opponent_secret_and_visible_triggers_are_reported_not_ignored():
    secret = _state(theirs=[sc.minion("E1", 2, 4, 1)], hand=[sc.hand_card("T_BOLT3", "SPELL", 3)],
                    opponent_kwargs={"secret_count": 1})
    forecast = _forecast(secret, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "E1")))
    assert forecast.status is Status.PARTIAL
    assert any(u.kind is UnknownKind.HIDDEN_SECRET for u in forecast.unknowns)
    assert _forecast(secret, sc.end_turn()).status is Status.EXACT

    watcher = _state(mine=[sc.minion("T_SPELLWATCH", 1, 1, 1)], theirs=[sc.minion("E1", 2, 4, 1)],
                     hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    cast = _forecast(watcher, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "E1")))
    assert any(u.kind is UnknownKind.POSSIBLE_REACTION for u in cast.unknowns)
    assert _forecast(watcher, sc.end_turn()).status is Status.EXACT              # it only reacts to spells


def test_end_of_turn_trigger_matters_only_when_the_turn_ends():
    state = _state(mine=[sc.minion("T_ENDTURN", 1, 1, 1)], hand=[sc.hand_card("T_BOLT3", "SPELL", 3)],
                   theirs=[sc.minion("E1", 2, 4, 1)])
    assert _forecast(state, sc.end_turn()).status is Status.PARTIAL
    assert _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "E1"))).status is Status.EXACT


def test_deathrattle_matters_only_when_that_minion_dies():
    state = _state(theirs=[sc.minion("T_DR", 2, 3, 1, mechanics=("DEATHRATTLE",)), sc.minion("E1", 2, 3, 2)],
                   hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    kills = _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "T_DR")))
    assert kills.status is Status.PARTIAL and any("Deathrattle" in u.detail for u in kills.unknowns)
    other = _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 2, "E1")))
    assert other.status is Status.EXACT


def test_reborn_minion_that_dies_is_reported_even_without_any_rules_text():
    state = _state(theirs=[sc.minion("NOT_IN_ANY_CATALOG", 2, 3, 1, reborn=True)],
                   hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    forecast = _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "NOT_IN_ANY_CATALOG")))
    assert any("Reborn" in u.detail for u in forecast.unknowns)


def test_frenzy_and_aura_react_only_to_their_own_event():
    state = _state(theirs=[sc.minion("T_FRENZY", 2, 5, 1), sc.minion("T_AURA", 1, 4, 2, mechanics=("AURA",))],
                   hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    assert _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "T_FRENZY"))).status is Status.PARTIAL
    aura_hit = _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 2, "T_AURA")))
    assert aura_hit.status is Status.PARTIAL                                     # the aura source is involved
    uninvolved = _state(theirs=[sc.minion("T_AURA", 1, 9, 1, mechanics=("AURA",)), sc.minion("E1", 2, 5, 2)],
                        hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    assert _forecast(uninvolved, _cast("T_BOLT3", sc.target_minion("OPPONENT", 2, "E1"))).status is Status.EXACT


def test_cards_without_any_rules_text_are_flagged_as_possible_reactions():
    state = _state(theirs=[sc.minion("NOT_IN_ANY_CATALOG", 2, 4, 1)], hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    forecast = _forecast(state, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "NOT_IN_ANY_CATALOG")))
    assert forecast.status is Status.PARTIAL
    assert forecast.unknowns[0].kind is UnknownKind.TEXT_UNAVAILABLE


# ----- combat ---------------------------------------------------------------------------------------

def _fight(attacker, defender, **opp):
    state = _state(mine=[attacker], theirs=[defender], opponent_kwargs=opp or None, hero_health=20)
    return state, _forecast(state, sc.attack(1, attacker.card.card_id, sc.target_minion("OPPONENT", 1,
                                                                                         defender.card.card_id)))


def test_minion_combat_is_simultaneous():
    _, fight = _fight(sc.minion("M1", 3, 3, 1, can_attack=True), sc.minion("E1", 2, 5, 1))
    assert _change(fight, "SELF", "health").after == 1 and _change(fight, "OPPONENT", "health").after == 2
    assert _change(fight, "SELF", "can_attack").after is False
    _, trade = _fight(sc.minion("M1", 3, 3, 1, can_attack=True), sc.minion("E1", 4, 3, 1))
    assert {(c.ref.side, c.field, c.after) for c in trade.changes if c.field == "present"} == {
        ("SELF", "present", False), ("OPPONENT", "present", False)}


def test_divine_shield_poison_and_lifesteal_in_combat():
    _, shield = _fight(sc.minion("M1", 5, 5, 1, divine_shield=True), sc.minion("E1", 4, 4, 1))
    assert _change(shield, "SELF", "divine_shield").after is False
    assert not [c for c in shield.changes if c.ref.side == "SELF" and c.field == "health"]
    _, poison = _fight(sc.minion("M1", 1, 1, 1, poisonous=True), sc.minion("E1", 2, 9, 1))
    assert {c.ref.side for c in poison.changes if c.field == "present"} == {"SELF", "OPPONENT"}
    _, blocked = _fight(sc.minion("M1", 1, 5, 1, poisonous=True), sc.minion("E1", 2, 9, 1, divine_shield=True))
    assert not [c for c in blocked.changes if c.ref.side == "OPPONENT" and c.field == "present"]   # no damage
    _, drain = _fight(sc.minion("M1", 4, 4, 1, lifesteal=True), sc.minion("E1", 1, 2, 1))
    assert _change(drain, "SELF", "health", "HERO").after == 24                                    # heals 4


def test_attacking_a_hero_has_no_counter_attack_and_removes_stealth():
    state = _state(mine=[sc.minion("M1", 3, 3, 1, stealth=True)], opponent_kwargs={"hero_health": 12})
    forecast = _forecast(state, sc.attack(1, "M1", sc.target_hero("OPPONENT")))
    assert _change(forecast, "OPPONENT", "health", "HERO").after == 9
    assert not [c for c in forecast.changes if c.field == "health" and c.ref.zone == "BOARD"]
    assert _change(forecast, "SELF", "stealth").after is False


def test_a_defending_hero_with_attack_does_not_hit_back():
    state = _state(mine=[sc.minion("M1", 3, 3, 1, can_attack=True)],
                   opponent_kwargs={"hero_health": 12, "hero_attack": 4})
    forecast = _forecast(state, sc.attack(1, "M1", sc.target_hero("OPPONENT")))
    assert not [c for c in forecast.changes if c.ref.side == "SELF" and c.field == "health"]


def test_windfury_attacks_remaining_are_unknown():
    state = _state(mine=[sc.minion("M1", 3, 3, 1, windfury=True)], opponent_kwargs={"hero_health": 12})
    forecast = _forecast(state, sc.attack(1, "M1", sc.target_hero("OPPONENT")))
    assert forecast.status is Status.PARTIAL and not _change(forecast, "SELF", "can_attack").exact


# ----- playing minions, hero powers, locations ----------------------------------------------------------

def test_playing_a_minion_inserts_it_and_renumbers_the_board():
    state = _state(mine=[sc.minion("M1", 1, 1, 1), sc.minion("M2", 2, 2, 2)],
                   hand=[sc.hand_card("T_TAUNT", "MINION", 3, attack=3, health=4, mechanics=("TAUNT",))], mana=5)
    unvouched = _forecast(state, sc.play("T_TAUNT", 0, "MINION", 3, play_position=2))
    assert unvouched.status is Status.PARTIAL
    assert [u.kind for u in unvouched.unknowns] == [UnknownKind.MODIFIER_UNOBSERVED]
    forecast = _forecast(state, sc.play("T_TAUNT", 0, "MINION", 3, play_position=2),
                         _ctx(hand_keywords_match_card=True))
    assert forecast.status is Status.EXACT
    board = _pos(forecast).self_player.board
    assert [(e.card.card_id, e.board_position) for e in board] == [("M1", 1), ("T_TAUNT", 2), ("M2", 3)]
    assert (board[1].current_attack, board[1].current_health, board[1].taunt, board[1].can_attack) == (3, 4, True, False)
    assert _pos(forecast).self_player.available_mana == 2 and _pos(forecast).self_player.hand_size == 0


def test_rush_minion_can_attack_but_unknown_battlecry_is_not_invented():
    state = _state(hand=[sc.hand_card("T_RUSH", "MINION", 2, attack=2, health=2, mechanics=("RUSH",)),
                         sc.hand_card("T_BC_DRAW", "MINION", 2, attack=2, health=2, mechanics=("BATTLECRY",))])
    vouched = _ctx(hand_keywords_match_card=True)
    rush = _forecast(state, sc.play("T_RUSH", 0, "MINION", 2, play_position=1), vouched)
    assert _pos(rush).self_player.board[0].can_attack is True
    draw = _forecast(state, sc.play("T_BC_DRAW", 1, "MINION", 2, play_position=1), vouched)
    assert draw.status is Status.PARTIAL and _pos(draw).self_player.board  # the body is still exact


def test_battlecry_damage_is_not_boosted_by_spell_damage():
    state = _state(theirs=[sc.minion("E1", 2, 5, 1)], spell_damage=3,
                   hand=[sc.hand_card("T_BC", "MINION", 2, attack=1, health=1, mechanics=("BATTLECRY",))])
    forecast = _forecast(state, sc.play("T_BC", 0, "MINION", 2, sc.target_minion("OPPONENT", 1, "E1"), 1),
                         _ctx(hand_keywords_match_card=True))
    assert _change(forecast, "OPPONENT", "health").after == 4


def test_hero_powers_use_text_but_ignore_spell_damage():
    power = sc.hand_card("T_POWER_DMG", "HERO_POWER", 2)
    state = _state(theirs=[sc.minion("E1", 2, 5, 1)], spell_damage=2, hero_power=power)
    forecast = _forecast(state, sc.hero_power("T_POWER_DMG", 2, sc.target_minion("OPPONENT", 1, "E1")))
    assert _change(forecast, "OPPONENT", "health").after == 4
    assert (_change(forecast, "SELF", "hero_power_ready", "HERO").before,
            _change(forecast, "SELF", "hero_power_ready", "HERO").after) == (True, False)
    armor_state = _state(hero_power=sc.hand_card("T_POWER_ARMOR", "HERO_POWER", 2))
    assert _change(_forecast(armor_state, sc.hero_power("T_POWER_ARMOR", 2)), "SELF", "armor", "HERO").after == 2


def test_location_activation_spends_durability_and_can_destroy_the_location():
    from manamind.domain.card import CardFeatures
    from manamind.domain.entity import LocationEntity
    place = LocationEntity(card=CardFeatures(card_id="T_LOC", card_type="LOCATION"), current_health=1, max_health=3,
                           board_position=1, on_cooldown=False, can_activate=True)
    state = _state(theirs=[sc.minion("E1", 2, 5, 1)])
    state = replace(state, self_player=replace(state.self_player, locations=(place,)))
    action = {"type": "ACTIVATE_LOCATION", "source_card_id": "T_LOC", "source_board_position": 1,
              "card_id": "T_LOC", **sc.target_minion("OPPONENT", 1, "E1")}
    forecast = _forecast(state, action)
    assert _change(forecast, "OPPONENT", "health").after == 4
    assert _change(forecast, "SELF", "present", "LOCATION").after is False
    assert _pos(forecast).self_player.locations == ()


def test_after_state_is_a_valid_new_state_and_leaves_the_original_alone():
    state = _hold_state()
    forecast = _forecast(state, _cast("T_HOLD", sc.target_minion("OPPONENT", 1, "SIX"), 5))
    after = _pos(forecast)
    assert after is not state and after.self_player.hand_size == 0 and after.self_hand == ()
    assert state.self_hand and state.opponent.board[0].current_attack == 6


# ----- hardening: referents, unused targets, weapons --------------------------------------------------------

def test_a_conditional_needs_a_single_chosen_target_to_refer_to():
    texts = TEXTS.extended([_spell("T_BAD_COND", "Deal $1 damage to all minions. If it dies, restore #3 Health.")])
    state = _state(theirs=[sc.minion("E1", 2, 1, 1)], hand=[sc.hand_card("T_BAD_COND", "SPELL", 1)])
    forecast = forecast_action(state, _cast("T_BAD_COND", None, 1), texts)
    assert forecast.status is Status.UNSUPPORTED and forecast.unsupported_reason == "CONDITION_WITHOUT_TARGET"


def test_a_target_the_text_never_uses_is_not_forecast():
    state = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_ARMOR", "SPELL", 2)])
    forecast = _forecast(state, _cast("T_ARMOR", sc.target_minion("OPPONENT", 1, "E1"), 2))
    assert forecast.status is Status.UNSUPPORTED and forecast.unsupported_reason == "TARGET_NOT_USED_BY_TEXT"


def _hero_with_weapon(card_id, durability=2):
    from manamind.domain.card import CardFeatures
    weapon = CardFeatures(card_id=card_id, card_type="WEAPON", attack=3, durability=durability,
                          current_durability=durability, mechanics=("LIFESTEAL",) if card_id == "T_WEAPON" else ())
    return _state(opponent_kwargs={"hero_health": 12}, hero_health=20, hero_attack=3, weapon=weapon)


def _hero_attack():
    return {"type": "ATTACK", "source_kind": "HERO", "source_card_id": "HERO", "source_board_position": -1,
            "source_is_hero": True, "card_id": "HERO", "play_position": 0, **sc.target_hero("OPPONENT")}


def test_hero_attack_spends_weapon_durability_and_uses_the_weapon_keywords():
    forecast = _forecast(_hero_with_weapon("T_WEAPON"), _hero_attack(), _ctx(healing_does_damage=False))
    assert _change(forecast, "OPPONENT", "health", "HERO").after == 9
    assert _change(forecast, "SELF", "health", "HERO").after == 23                 # Lifesteal weapon heals 3
    assert _change(forecast, "SELF", "durability", "WEAPON").after == 1
    assert forecast.status is Status.EXACT


def test_weapon_triggers_and_a_breaking_weapon_are_reported():
    triggered = _forecast(_hero_with_weapon("T_WEAPON_TRIGGER"), _hero_attack())
    assert triggered.status is Status.PARTIAL
    assert any("After your hero attacks" in u.detail for u in triggered.unknowns)
    breaking = _forecast(_hero_with_weapon("T_WEAPON", durability=1), _hero_attack())
    assert breaking.status is Status.PARTIAL and not _change(breaking, "SELF", "attack", "HERO").exact


# ----- Spell Damage is not observed by the importer ---------------------------------------------------------

def _unobserved(state, action):
    return forecast_action(state, action, TEXTS, ObservedContext(healing_does_damage=False, spell_healing_doubled=False))


def test_unobserved_spell_damage_turns_remaining_health_into_a_bound_but_keeps_lethal_and_shields_exact():
    survive = _state(theirs=[sc.minion("E1", 2, 6, 1)], hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    forecast = _unobserved(survive, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "E1")))
    health = _change(forecast, "OPPONENT", "health")
    assert forecast.status is Status.PARTIAL and health.after is None and health.at_most == 3
    assert any(u.kind is UnknownKind.MODIFIER_UNOBSERVED and "Spell Damage" in u.detail for u in forecast.unknowns)
    assert _pos(forecast).opponent.board[0].current_health == 6              # not invented
    kill = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    lethal = _unobserved(kill, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "E1")))
    assert _change(lethal, "OPPONENT", "present").after is False                   # extra damage cannot save it
    shield = _state(theirs=[sc.minion("E1", 2, 6, 1, divine_shield=True)], hand=[sc.hand_card("T_BOLT3", "SPELL", 3)])
    popped = _unobserved(shield, _cast("T_BOLT3", sc.target_minion("OPPONENT", 1, "E1")))
    assert _change(popped, "OPPONENT", "divine_shield").after is False
    assert not [c for c in popped.changes if c.field == "health"]                  # any amount is absorbed


def test_unobserved_spell_damage_makes_lifesteal_and_hero_damage_bounds():
    state = _state(theirs=[sc.minion("E1", 2, 20, 1)], hand=[sc.hand_card("T_LIFESTEAL", "SPELL", 4)], hero_health=20)
    forecast = _unobserved(state, _cast("T_LIFESTEAL", sc.target_minion("OPPONENT", 1, "E1"), 4))
    heal = _change(forecast, "SELF", "health", "HERO")
    assert heal.after is None and heal.at_least == 28                              # at least the unboosted 8
    hero = _state(hand=[sc.hand_card("T_BOLT_ANY", "SPELL", 3)], opponent_kwargs={"armor": 3, "hero_health": 20})
    hit = _unobserved(hero, _cast("T_BOLT_ANY", sc.target_hero("OPPONENT")))
    assert _change(hit, "OPPONENT", "health", "HERO").at_most == 19 and _change(hit, "OPPONENT", "armor", "HERO").at_most == 0


def test_a_lethal_lower_bound_still_fires_if_it_dies_but_a_survivor_is_unknown():
    kill = _state(theirs=[sc.minion("E1", 2, 3, 1)], hand=[sc.hand_card("T_COND", "SPELL", 2)],
                  opponent_kwargs={"hero_health": 20})
    killed = _unobserved(kill, _cast("T_COND", sc.target_minion("OPPONENT", 1, "E1"), 2))
    assert _change(killed, "OPPONENT", "health", "HERO").after == 23
    survive = _state(theirs=[sc.minion("E1", 2, 4, 1)], hand=[sc.hand_card("T_COND", "SPELL", 2)],
                     opponent_kwargs={"hero_health": 20})
    unsure = _unobserved(survive, _cast("T_COND", sc.target_minion("OPPONENT", 1, "E1"), 2))
    assert not [c for c in unsure.changes if c.ref.zone == "HERO" and c.ref.side == "OPPONENT"]
    assert any("condition depends" in u.detail for u in unsure.unknowns)


def test_hero_power_and_battlecry_damage_do_not_depend_on_spell_damage():
    power = sc.hand_card("T_POWER_DMG", "HERO_POWER", 2)
    state = _state(theirs=[sc.minion("E1", 2, 5, 1)], hero_power=power)
    forecast = _unobserved(state, sc.hero_power("T_POWER_DMG", 2, sc.target_minion("OPPONENT", 1, "E1")))
    assert forecast.status is Status.EXACT and _change(forecast, "OPPONENT", "health").after == 4


def test_playing_a_location_places_it_on_the_shared_board_without_running_its_activation_text():
    from manamind.domain.card import CardFeatures
    texts = TEXTS.extended([_body("T_PLACE", "Deal $1 damage to a minion.", (), "LOCATION")])
    state = _state(mine=[sc.minion("M1", 1, 1, 1), sc.minion("M2", 2, 2, 2)], theirs=[sc.minion("E1", 2, 5, 1)],
                   hand=[CardFeatures(card_id="T_PLACE", card_type="LOCATION", cost=2, current_cost=2, health=3)])
    forecast = forecast_action(state, sc.play("T_PLACE", 0, "LOCATION", 2, play_position=2), texts, _ctx())
    assert forecast.status is Status.EXACT
    after = _pos(forecast).self_player
    assert [(p.card.card_id, p.board_position, p.current_health, p.on_cooldown) for p in after.locations] == [
        ("T_PLACE", 2, 3, False)]
    assert [(e.card.card_id, e.board_position) for e in after.board] == [("M1", 1), ("M2", 3)]
    assert _pos(forecast).opponent.board[0].current_health == 5          # activation text did not run
    assert _change(forecast, "SELF", "body", "LOCATION").after == "3 durability"


def test_a_full_board_has_no_after_state_but_keeps_the_exact_changes():
    from manamind.domain.card import CardFeatures
    full = [sc.minion("M1", 1, 1, position) for position in range(1, 8)]
    state = _state(mine=full, hand=[CardFeatures(card_id="T_PLACE", card_type="LOCATION", cost=2, current_cost=2, health=3)])
    texts = TEXTS.extended([_body("T_PLACE", "", (), "LOCATION")])
    forecast = forecast_action(state, sc.play("T_PLACE", 0, "LOCATION", 2, play_position=8), texts, _ctx())
    assert forecast.partial_state() is None
    assert any("no after-state" in note for note in forecast.assumptions)
    assert _change(forecast, "SELF", "available_mana", "PLAYER").after == 8
