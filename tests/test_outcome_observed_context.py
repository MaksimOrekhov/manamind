"""OBSERVATION-EXT-1a: how read facts reach the forecaster, and that they change numbers, not just warnings."""

from __future__ import annotations

from dataclasses import replace

from manamind.integrations.powerlog.observed_facts import (
    COMPLETE, SPELL_DAMAGE_NONE_SEEN, SPELL_DAMAGE_PRESENT, SPELL_DAMAGE_UNKNOWN, HandCardFact, ObservedFacts,
)
from manamind.outcome import ObservedContext, Status, TextSource, Tier, forecast_action
from manamind.outcome import scenario as sc
from manamind.outcome.observation import context_from_observed


def _spell(card_id: str, text: str) -> dict:
    return {"id": card_id, "text": text, "type": "SPELL", "mechanics": []}


def _minion(card_id: str, attack: int, health: int, mechanics: tuple[str, ...] = (), text: str = "") -> dict:
    return {"id": card_id, "text": text, "type": "MINION", "mechanics": list(mechanics),
            "attack": attack, "health": health}


TEXTS = TextSource.from_records([
    _spell("S_BOLT_ANY", "Deal $3 damage."),
    _spell("S_BOLT", "Deal $3 damage to a minion."),
    _spell("S_HEAL", "Restore #4 Health."),
    _minion("V", 1, 1),
    _minion("W", 4, 4),
    _minion("AURA", 2, 2, ("AURA",), "All enemy minions have <b>Taunt</b>."),
    _minion("COMBO", 2, 2, text="<b>Combo:</b> Gain <b>Windfury</b>."),
])


def _facts(**kwargs) -> ObservedFacts:
    base = dict(coverage=COMPLETE, self_hero_divine_shield=False, opponent_hero_divine_shield=False,
                healing_does_damage=False, healing_bonus=0, spell_healing_doubled=False, all_healing_doubled=False,
                spell_damage_doubled=False, spell_damage_status=SPELL_DAMAGE_NONE_SEEN, spell_damage=0)
    return ObservedFacts(**{**base, **kwargs})


def _state(mine=(), theirs=(), hand=(), mana=10, **opponent):
    return sc.position(self_side=sc.side(board=tuple(mine), mana=mana, healing_bonus=None, hero_divine_shield=None),
                       opponent=sc.side(board=tuple(theirs), hero_divine_shield=None, **opponent), hand=tuple(hand))


def _cast(card_id, target=None, cost=3, index=0):
    return sc.play(card_id, index, "SPELL", cost, target)


def _health(forecast, label_part: str):
    return [c for c in forecast.changes if c.field == "health" and label_part in c.ref.label()][0]


# ----- the mapping -----------------------------------------------------------------------------------------------

def test_no_facts_is_an_all_unknown_context():
    assert context_from_observed(None, _state()) == ObservedContext()


def test_every_group_maps_to_its_own_context_fields_and_can_be_switched_off():
    state = _state(hand=[sc.hand_card("V", "MINION", 1)])
    found = _facts(self_hero_divine_shield=True, healing_bonus=2, spell_healing_doubled=True,
                   hand=(HandCardFact(0, "V", ("taunt",)),))
    full = context_from_observed(found, state)
    assert full.healing_does_damage is False and full.healing_bonus == 2 and full.spell_healing_doubled is True
    assert full.self_hero_divine_shield is True and full.opponent_hero_divine_shield is False
    assert full.hand_keywords == (frozenset({"taunt"}),) and full.spell_damage == 0
    assert full.spell_damage_doubled is False and not full.spell_damage_unverified
    only_shield = context_from_observed(found, state, {"hero_shield"})
    assert only_shield == ObservedContext(self_hero_divine_shield=True, opponent_hero_divine_shield=False)


def test_healing_doubling_is_the_union_of_the_spell_and_all_healing_flags():
    ctx = lambda **kw: context_from_observed(_facts(**kw), _state()).spell_healing_doubled  # noqa: E731
    assert ctx(spell_healing_doubled=False, all_healing_doubled=False) is False
    assert ctx(spell_healing_doubled=False, all_healing_doubled=True) is True
    assert ctx(spell_healing_doubled=True, all_healing_doubled=False) is True
    assert ctx(spell_healing_doubled=False, all_healing_doubled=None) is None
    assert ctx(spell_healing_doubled=None, all_healing_doubled=None) is None


def test_hand_facts_stay_attached_to_their_own_instance_and_a_disagreeing_hand_is_dropped():
    state = _state(hand=[sc.hand_card("V", "MINION", 1), sc.hand_card("V", "MINION", 1), sc.hand_card("W", "MINION", 2)])
    found = _facts(hand=(HandCardFact(0, "V", ("taunt",)), HandCardFact(1, "V", ()), HandCardFact(2, "W", None)))
    assert context_from_observed(found, state).hand_keywords == (frozenset({"taunt"}), frozenset(), None)
    swapped = _facts(hand=(HandCardFact(0, "W", ()), HandCardFact(1, "V", ("rush",)), HandCardFact(2, "W", ())))
    assert context_from_observed(swapped, state).hand_keywords == (None, frozenset({"rush"}), frozenset())
    assert context_from_observed(_facts(hand=found.hand[:2]), state).hand_keywords is None      # different lengths


def test_spell_damage_status_becomes_a_number_a_bound_or_nothing():
    state = _state()
    none_seen = context_from_observed(_facts(spell_damage_doubled=True), state)
    assert none_seen.spell_damage == 0 and none_seen.spell_damage_doubled is True
    present = context_from_observed(_facts(spell_damage_status=SPELL_DAMAGE_PRESENT, spell_damage=2), state)
    assert present.spell_damage is None and present.spell_damage_unverified
    unknown = context_from_observed(_facts(spell_damage_status=SPELL_DAMAGE_UNKNOWN, spell_damage=None), state)
    assert unknown.spell_damage is None and not unknown.spell_damage_unverified


# ----- the facts change the computed numbers -----------------------------------------------------------------------

def test_the_observed_bonus_and_doubling_give_a_different_number_than_the_assumed_default():
    mine = sc.minion("W", 1, 3, 1, max_health=30)
    state = _state(mine=[mine], hand=[sc.hand_card("S_HEAL", "SPELL", 1)])
    action = _cast("S_HEAL", sc.target_minion("SELF", 1, "W"), 1)
    assumed = forecast_action(state, action, TEXTS, ObservedContext.assuming_common_defaults())
    observed = forecast_action(
        state, action, TEXTS, context_from_observed(_facts(healing_bonus=4, spell_healing_doubled=True), state))
    assert _health(assumed, "board").after == 7                       # 3 + 4: the default says the bonus is 0
    assert _health(observed, "board").after == 3 + (4 + 4) * 2        # 19: the logged bonus and doubling
    unobserved = forecast_action(state, action, TEXTS, ObservedContext())
    assert _health(unobserved, "board").after is None                 # without the fact there is only a bound


def test_a_known_hero_shield_decides_between_a_hit_and_an_absorbed_hit():
    state = _state(hand=[sc.hand_card("S_BOLT_ANY", "SPELL", 3)])
    action = _cast("S_BOLT_ANY", sc.target_hero("OPPONENT"))
    plain = forecast_action(state, action, TEXTS, context_from_observed(_facts(spell_damage_doubled=False), state))
    assert plain.status is Status.EXACT and plain.exact_state().opponent.hero_health == 27
    shielded = forecast_action(
        state, action, TEXTS, context_from_observed(_facts(opponent_hero_divine_shield=True), state))
    assert shielded.status is Status.EXACT and shielded.exact_state().opponent.hero_health == 30
    assert shielded.exact_state().opponent.hero_divine_shield is False
    unknown = forecast_action(
        state, action, TEXTS, context_from_observed(_facts(opponent_hero_divine_shield=None), state))
    assert any(u.tag == "HERO_SHIELD_UNOBSERVED" for u in unknown.unknowns) and unknown.status is Status.PARTIAL


def test_confirmed_spell_damage_doubling_is_exact_and_an_unverified_source_is_only_a_bound():
    target = sc.target_minion("OPPONENT", 1, "W")
    state = _state(theirs=[sc.minion("W", 1, 20, 1)], hand=[sc.hand_card("S_BOLT", "SPELL", 3)])
    action = _cast("S_BOLT", target)

    def run(**kw):
        return forecast_action(state, action, TEXTS, context_from_observed(_facts(**kw), state))

    assert _health(run(spell_damage_doubled=False), "board").after == 17
    assert _health(run(spell_damage_doubled=True), "board").after == 14                 # (3 + 0) * 2
    present = run(spell_damage_status=SPELL_DAMAGE_PRESENT, spell_damage=2, spell_damage_doubled=True)
    change = _health(present, "board")
    assert change.after is None and change.at_most == 14                                 # at least 3 * 2, never a number
    assert present.status is Status.PARTIAL and {u.tag for u in present.unknowns} >= {"SPELL_DAMAGE_UNVERIFIED"}
    plain = run(spell_damage_status=SPELL_DAMAGE_PRESENT, spell_damage=2)
    assert _health(plain, "board").at_most == 17
    unknown = run(spell_damage_status=SPELL_DAMAGE_UNKNOWN, spell_damage=None)
    assert {u.tag for u in unknown.unknowns} >= {"SPELL_DAMAGE_UNOBSERVED"} and _health(unknown, "board").after is None


def test_identical_copies_with_different_keywords_give_different_bodies():
    hand = [sc.hand_card("V", "MINION", 1, attack=1, health=1), sc.hand_card("V", "MINION", 1, attack=1, health=1)]
    state = _state(hand=hand)
    found = _facts(hand=(HandCardFact(0, "V", ("taunt",)), HandCardFact(1, "V", ("charge",))))
    context = context_from_observed(found, state)

    def body(index):
        play = sc.play("V", index, "MINION", 1, play_position=1)
        forecast = forecast_action(state, play, TEXTS, context)
        return forecast.exact_state().self_player.board[0], forecast

    first, _ = body(0)
    second, forecast = body(1)
    assert (first.taunt, first.charge, first.can_attack) == (True, False, False)
    assert (second.taunt, second.charge, second.can_attack) == (False, True, True)
    assert not any(u.tag == "HAND_KEYWORDS_UNOBSERVED" for u in forecast.unknowns)


# ----- the safeguards behind the three hand-keyword mismatches of the real corpus ---------------------------------

def test_an_enemy_aura_that_grants_a_keyword_on_play_keeps_the_forecast_from_being_exact():
    """Real case: the opponent's static text gave Taunt to SELF's minions as they entered play (hand showed none)."""
    state = _state(theirs=[sc.minion("AURA", 2, 2, 1)], hand=[sc.hand_card("V", "MINION", 1, attack=1, health=1)])
    context = context_from_observed(_facts(hand=(HandCardFact(0, "V", ()),)), state)
    forecast = forecast_action(state, sc.play("V", 0, "MINION", 1, play_position=1), TEXTS, context)
    assert forecast.status is Status.PARTIAL and forecast.tier is not Tier.EXACT
    assert {u.tag for u in forecast.unknowns} == {"AURA_ON_SUMMON"}
    # the same position without the aura is exact: the flag is what removes the certainty, nothing else
    clean = forecast_action(replace(state, opponent=replace(state.opponent, board=())),
                            sc.play("V", 0, "MINION", 1, play_position=1), TEXTS, context)
    assert clean.status is Status.EXACT


def test_a_battlecry_or_combo_that_grants_a_keyword_to_itself_is_not_an_exact_body():
    """Real case: Rush in hand, Rush and Windfury on the board after the Combo text ran."""
    state = _state(hand=[sc.hand_card("COMBO", "MINION", 1, attack=2, health=2)])
    context = context_from_observed(_facts(hand=(HandCardFact(0, "COMBO", ("rush",)),)), state)
    forecast = forecast_action(state, sc.play("COMBO", 0, "MINION", 1, play_position=1), TEXTS, context)
    assert forecast.status is Status.PARTIAL and not forecast.own_effect_known
    assert any(u.tag.startswith("OWN_TEXT") for u in forecast.unknowns)


def test_an_active_sanctum_is_unsupported_not_a_silent_heal():
    mine = sc.minion("W", 1, 3, 1, max_health=30)
    state = _state(mine=[mine], hand=[sc.hand_card("S_HEAL", "SPELL", 1)])
    action = _cast("S_HEAL", sc.target_minion("SELF", 1, "W"), 1)
    forecast = forecast_action(
        state, action, TEXTS, context_from_observed(_facts(healing_does_damage=True), state))
    assert forecast.status is Status.UNSUPPORTED and forecast.unsupported_reason == "HEALING_DOES_DAMAGE_ACTIVE"
    unknown = forecast_action(state, action, TEXTS, context_from_observed(_facts(healing_does_damage=None), state))
    assert any(u.tag == "SANCTUM_UNOBSERVED" for u in unknown.unknowns)


def test_the_state_keeps_priority_over_the_context_when_it_already_says_something():
    state = _state(hand=[sc.hand_card("S_BOLT_ANY", "SPELL", 3)])
    state = replace(state, opponent=replace(state.opponent, hero_divine_shield=False))
    shielded = context_from_observed(_facts(opponent_hero_divine_shield=True), state)
    forecast = forecast_action(state, _cast("S_BOLT_ANY", sc.target_hero("OPPONENT")), TEXTS, shielded)
    assert forecast.exact_state().opponent.hero_health == 27           # GameState saw "no shield" in an explicit tag


def test_the_aura_safeguard_reads_the_real_texts_of_the_pinned_catalog():
    from pathlib import Path

    from manamind.outcome.grammar import affects_minion_body, board_profile

    real = TextSource.from_files(Path(__file__).parents[1] / "data" / "cards" / "standard_current_enUS.json")

    def verdicts(card_id):
        entry = real.get(card_id)
        return "AURA" in entry.mechanics, [affects_minion_body(s) for s in board_profile(entry.text)[1]]

    assert verdicts("CATA_898") == (True, [True])          # "All enemy minions have Taunt": the real corpus mismatch
    assert verdicts("CORE_EDR_003") == (True, [False])     # Corpses
    assert verdicts("TIME_606") == (True, [False])         # Hero Power cost
    assert verdicts("END_036") == (True, [False])          # Rewinds
