"""ACTION-OUTCOME-1B: the safe-consumption contract, Reborn, observed-fact contexts and scoring details."""

from __future__ import annotations

from dataclasses import replace

import pytest

from manamind.cards.catalog import CardCatalog
from manamind.domain.game_state import GameState
from manamind.encoding.state_encoder import StateEncoder
from manamind.outcome import (
    NotExactError, ObservedContext, PartialState, Status, TextSource, Tier, forecast_action,
)
from manamind.outcome import scenario as sc
from manamind.outcome.observation import context_from_facts
from manamind.outcome.verify import (
    LoggedDecision, align_observed, build_gain_associations, role_of, score_pair,
)


def _spell(card_id: str, text: str) -> dict:
    return {"id": card_id, "text": text, "type": "SPELL", "mechanics": []}


def _minion(card_id: str, attack: int, health: int, mechanics: tuple[str, ...] = (), text: str = "") -> dict:
    return {"id": card_id, "text": text, "type": "MINION", "mechanics": list(mechanics),
            "attack": attack, "health": health}


TEXTS = TextSource.from_records([
    _spell("S_HOLD", "<b>Prepare</b>\nGive a minion +5/+5 and <b>Lifesteal</b>."),
    _spell("S_BOLT", "Deal $3 damage to a minion."),
    _spell("S_HEAL", "Restore #4 Health."),
    _spell("S_POWER", "Restore #2 Health."),
    _spell("S_DRAW", "Draw a card."),
    _minion("R_PLAIN", 2, 3, ("TAUNT",)),
    _minion("R_DR", 2, 3, ("DEATHRATTLE",), "<b>Deathrattle:</b> Draw a card."),
    _minion("V", 1, 1),
    _minion("W", 4, 4),
])
FULL = ObservedContext(trust_spell_damage=True, spell_healing_doubled=False, healing_does_damage=False,
                       hand_keywords_match_card=True)


def _state(mine=(), theirs=(), hand=(), mana=10, **opponent):
    return sc.position(self_side=sc.side(board=tuple(mine), mana=mana),
                       opponent=sc.side(board=tuple(theirs), **opponent), hand=tuple(hand))


def _cast(card_id, target=None, cost=3, index=0):
    return sc.play(card_id, index, "SPELL", cost, target)


def _hold_forecast(**opponent):
    state = _state(theirs=[sc.minion("V", 6, 6, 1)], hand=[sc.hand_card("S_HOLD", "SPELL", 5)], mana=5, **opponent)
    return state, forecast_action(state, _cast("S_HOLD", sc.target_minion("OPPONENT", 1, "V"), 5), TEXTS, FULL)


# ----- the safe-consumption contract ---------------------------------------------------------------------

def test_exact_forecast_gives_a_real_position_and_no_partial_state():
    _, forecast = _hold_forecast()
    assert forecast.status is Status.EXACT and forecast.tier is Tier.EXACT
    position = forecast.exact_state()
    assert isinstance(position, GameState) and position.opponent.board[0].current_attack == 11
    assert forecast.partial_state() is None


def test_partial_forecast_refuses_exact_state_and_names_what_is_open():
    state, forecast = _hold_forecast(secret_count=1)
    assert forecast.status is Status.PARTIAL
    with pytest.raises(NotExactError, match="OPPONENT_SECRET"):
        forecast.exact_state()
    partial = forecast.partial_state()
    assert isinstance(partial, PartialState) and not isinstance(partial, GameState)
    assert {u.tag for u in partial.open_unknowns} == {"OPPONENT_SECRET"}
    # the local exact changes are all still there
    assert {(c.field, c.after) for c in forecast.effect_changes} >= {("attack", 11), ("health", 11), ("lifesteal", True)}
    assert partial.diagnostic_state().opponent.board[0].current_attack == 11
    assert state.opponent.board[0].current_attack == 6


def test_a_partial_state_cannot_reach_the_encoder_or_a_value_model_by_accident():
    _, forecast = _hold_forecast(secret_count=1)
    encoder = StateEncoder(CardCatalog())
    with pytest.raises(AttributeError):
        encoder.encode(forecast.partial_state())                       # type: ignore[arg-type]
    unsupported = forecast_action(_state(), {"type": "TRADE_CARD"}, TEXTS)
    assert unsupported.partial_state() is None
    with pytest.raises(NotExactError):
        unsupported.exact_state()


def test_tiers_separate_exact_known_own_effect_local_bookkeeping_and_unsupported():
    state = _state(theirs=[sc.minion("V", 2, 5, 1)], hand=[sc.hand_card("S_BOLT", "SPELL", 3),
                                                            sc.hand_card("S_DRAW", "SPELL", 1)])
    target = sc.target_minion("OPPONENT", 1, "V")
    assert forecast_action(state, _cast("S_BOLT", target), TEXTS, FULL).tier is Tier.EXACT
    secret = replace(state, opponent=replace(state.opponent, secret_count=1))
    assert forecast_action(secret, _cast("S_BOLT", target), TEXTS, FULL).tier is Tier.OWN_EFFECT_KNOWN
    draw = forecast_action(state, _cast("S_DRAW", None, 1, index=1), TEXTS, FULL)
    assert draw.tier is Tier.BOOKKEEPING_ONLY and not draw.effect_changes
    mixed = forecast_action(state, _cast("S_BOLT", target), TEXTS, ObservedContext())     # Spell Damage unobserved
    assert mixed.tier is Tier.PARTIAL_LOCAL and mixed.effect_changes == ()
    assert forecast_action(state, {"type": "TRADE_CARD"}, TEXTS).tier is Tier.UNSUPPORTED


def test_changes_carry_a_role_so_local_results_stay_measurable():
    _, forecast = _hold_forecast()
    roles = {(c.ref.zone, c.field): c.role for c in forecast.changes}
    assert roles[("PLAYER", "available_mana")] == "BOOKKEEPING" and roles[("HAND", "present")] == "BOOKKEEPING"
    assert roles[("BOARD", "attack")] == "EFFECT" and forecast.to_dict()["tier"] == "EXACT"
    assert role_of("SELF.mana") == "BOOKKEEPING" and role_of("OPPONENT.board[0:A].current_health") == "EFFECT"


# ----- Reborn ----------------------------------------------------------------------------------------------

def _kill(target_id, **minion_flags):
    state = _state(theirs=[sc.minion(target_id, 7, 2, 1, max_health=9, reborn=True, **minion_flags)],
                   hand=[sc.hand_card("S_BOLT", "SPELL", 3)])
    return forecast_action(state, _cast("S_BOLT", sc.target_minion("OPPONENT", 1, target_id)), TEXTS, FULL)


def test_reborn_minion_returns_in_place_with_printed_stats_and_one_health():
    forecast = _kill("R_PLAIN", taunt=True)
    assert forecast.status is Status.EXACT, forecast.unknowns
    returned = forecast.exact_state().opponent.board[0]
    assert (returned.current_attack, returned.current_health, returned.max_health) == (2, 1, 3)
    assert (returned.reborn, returned.taunt, returned.can_attack, returned.board_position) == (False, True, False, 1)
    assert not [c for c in forecast.changes if c.field == "present" and c.ref.zone == "BOARD"]


def test_reborn_with_a_deathrattle_still_reports_the_deathrattle():
    forecast = _kill("R_DR")
    assert forecast.status is Status.PARTIAL and any(u.tag == "DEATHRATTLE" for u in forecast.unknowns)
    assert forecast.partial_state().diagnostic_state().opponent.board[0].current_health == 1


def test_reborn_token_without_printed_stats_keeps_health_one_and_leaves_the_rest_open():
    forecast = _kill("NOT_IN_ANY_JSON")
    health = [c for c in forecast.changes if c.field == "health"][0]
    assert health.exact and health.after == 1
    assert {c.field for c in forecast.bounded_changes} >= {"attack", "max_health", "taunt"}
    assert any(u.tag == "REBORN_BASE_UNKNOWN" for u in forecast.unknowns)


# ----- observed-fact contexts --------------------------------------------------------------------------------

def test_doubled_spell_damage_and_a_given_bonus_follow_the_logged_formula():
    state = _state(theirs=[sc.minion("W", 1, 20, 1)], hand=[sc.hand_card("S_BOLT", "SPELL", 3)])
    target = sc.target_minion("OPPONENT", 1, "W")
    health = lambda ctx: [c for c in forecast_action(state, _cast("S_BOLT", target), TEXTS, ctx).changes  # noqa: E731
                          if c.field == "health"][0]
    assert health(ObservedContext(spell_damage=0, spell_damage_doubled=False)).after == 17
    assert health(ObservedContext(spell_damage=0, spell_damage_doubled=True)).after == 14          # (3 + 0) * 2
    assert health(ObservedContext(spell_damage=2, spell_damage_doubled=True)).after == 10          # (3 + 2) * 2
    unknown = health(ObservedContext(spell_damage=2))                                                # doubling not observed
    assert unknown.after is None and unknown.at_most == 15


def test_healing_bonus_and_doubling_come_from_the_context_when_the_state_has_none():
    mine = sc.minion("W", 1, 3, 1, max_health=30)
    state = sc.position(self_side=sc.side(board=(mine,), healing_bonus=None), opponent=sc.side(),
                        hand=(sc.hand_card("S_HEAL", "SPELL", 1),))
    target = sc.target_minion("SELF", 1, "W")

    def healed(ctx):
        change = [c for c in forecast_action(state, _cast("S_HEAL", target, 1), TEXTS, ctx).changes
                  if c.field == "health"][0]
        return change.after, change.at_least

    base = {"healing_does_damage": False}
    assert healed(ObservedContext(**base))[0] is None                                              # bonus unobserved
    assert healed(ObservedContext(healing_bonus=2, spell_healing_doubled=False, **base))[0] == 9   # 3 + 4 + 2
    assert healed(ObservedContext(healing_bonus=2, spell_healing_doubled=True, **base))[0] == 15   # 3 + (4 + 2) * 2
    assert healed(ObservedContext(healing_bonus=2, **base)) == (None, 9)                           # doubling open: bound


def test_a_non_spell_heal_under_the_doubling_flag_is_only_a_bound():
    power = sc.hand_card("S_POWER", "HERO_POWER", 2)
    mine = sc.minion("W", 1, 3, 1, max_health=30)
    state = sc.position(self_side=sc.side(board=(mine,), healing_bonus=0, hero_power=power), opponent=sc.side())
    action = sc.hero_power("S_POWER", 2, sc.target_minion("SELF", 1, "W"))
    plain = forecast_action(state, action, TEXTS, ObservedContext(healing_does_damage=False, spell_healing_doubled=False))
    assert [c.after for c in plain.changes if c.field == "health"] == [5]
    doubled = forecast_action(state, action, TEXTS, ObservedContext(healing_does_damage=False, spell_healing_doubled=True))
    assert any(u.tag == "HEALING_DOUBLING_UNVERIFIED" for u in doubled.unknowns)


def test_hero_shield_and_hand_keywords_from_the_context():
    shot = sc.hand_card("S_BOLT", "SPELL", 3)
    state = replace(_state(hand=[shot]), opponent=replace(_state().opponent, hero_divine_shield=None))
    hero = _cast("S_BOLT", sc.target_hero("OPPONENT"))
    target = forecast_action(state, hero, TEXTS, FULL)
    assert target.unsupported_reason == "TARGET_DOES_NOT_MATCH_TEXT"                               # "a minion" only
    bolt = TEXTS.extended([_spell("S_BOLT_ANY", "Deal $3 damage.")])
    state = replace(state, self_hand=(sc.hand_card("S_BOLT_ANY", "SPELL", 3),))
    unknown = forecast_action(state, _cast("S_BOLT_ANY", sc.target_hero("OPPONENT")), bolt, FULL)
    assert any(u.tag == "HERO_SHIELD_UNOBSERVED" for u in unknown.unknowns)
    known = forecast_action(state, _cast("S_BOLT_ANY", sc.target_hero("OPPONENT")), bolt,
                            replace(FULL, opponent_hero_divine_shield=False))
    assert known.status is Status.EXACT and known.exact_state().opponent.hero_health == 27

    minion_hand = (sc.hand_card("V", "MINION", 1, attack=1, health=1),)
    play = sc.play("V", 0, "MINION", 1, play_position=1)
    base = _state(hand=minion_hand)
    flagged = forecast_action(base, play, TEXTS, ObservedContext(hand_keywords=(frozenset({"taunt", "reborn"}),)))
    body = flagged.exact_state().self_player.board[0]
    assert (body.taunt, body.reborn, body.charge) == (True, True, False)
    assert not any(u.tag == "HAND_KEYWORDS_UNOBSERVED" for u in flagged.unknowns)


def test_context_from_facts_maps_logged_tags_and_drops_a_hand_that_disagrees():
    state = _state(hand=[sc.hand_card("V", "MINION", 1), sc.hand_card("W", "MINION", 2)])
    fact = {"sanctum": "ACTIVE", "spell_power": {"current_sum": 1, "player_current": 0, "doubled": True},
            "healing": {"bonus": 4, "spell_double": False, "all_double": True}, "hero_divine_shield": False,
            "opponent_hero_divine_shield": True,
            "hand": [{"card_id": "V", "keywords": ["taunt"]}, {"card_id": "OTHER", "keywords": []}]}
    context = context_from_facts(fact, state)
    assert (context.healing_does_damage, context.spell_damage, context.spell_damage_doubled) == (True, 1, True)
    assert (context.healing_bonus, context.spell_healing_doubled) == (4, True)
    assert (context.self_hero_divine_shield, context.opponent_hero_divine_shield) == (False, True)
    assert context.hand_keywords == (frozenset({"taunt"}), None)
    assert context_from_facts({"sanctum": "UNKNOWN"}, state).healing_does_damage is None


# ----- scoring details --------------------------------------------------------------------------------------

def _row(card_id, attack=1, health=1, **flags):
    return {"card_id": card_id, "current_attack": attack, "current_health": health, "max_health": health, **flags}


def test_alignment_picks_the_same_id_entity_that_looks_like_the_original():
    before = [_row("A", 3, 3), _row("A", 1, 1)]
    assert align_observed(before, [_row("A", 1, 1)]) == {1: 0}                      # the 1/1 is the one that remains
    assert align_observed(before, [_row("A", 3, 3)]) == {0: 0}
    assert align_observed(before, [_row("B"), _row("A", 3, 3), _row("A", 1, 1)]) == {0: 1, 1: 2}


def _decision(state, action, number=1):
    return LoggedDecision("g", number, f"g:{number}", state, action, (action,))


def test_identical_copies_in_hand_are_compared_as_a_multiset():
    hand = (sc.hand_card("S_BOLT", "SPELL", 3), sc.hand_card("S_BOLT", "SPELL", 3))
    state = _state(theirs=[sc.minion("V", 2, 9, 1)], hand=hand)
    action = _cast("S_BOLT", sc.target_minion("OPPONENT", 1, "V"), 3, index=1)
    truth = replace(state, self_hand=(hand[0],), self_hand_known_count=1,
                    self_player=replace(state.self_player, hand_size=1, available_mana=7),
                    opponent=replace(state.opponent, board=(sc.minion("V", 2, 6, 1, max_health=9),)))
    result = score_pair(_decision(state, action), _decision(truth, action, 2), TEXTS, FULL)
    assert result.verdict == "CONFIRMED", (result.contradicted, result.missed)
    assert result.confirmed["SELF.hand[S_BOLT].gone"] == 1


def test_reborn_return_is_scored_as_correct_and_a_countered_spell_is_explained_by_the_data():
    kill_state = _state(theirs=[sc.minion("R_PLAIN", 7, 2, 1, max_health=9, reborn=True, taunt=True)],
                        hand=[sc.hand_card("S_BOLT", "SPELL", 3)])
    action = _cast("S_BOLT", sc.target_minion("OPPONENT", 1, "R_PLAIN"))
    base = replace(kill_state, self_player=replace(kill_state.self_player, available_mana=7, hand_size=0),
                   self_hand=(), self_hand_known_count=0)
    returned = replace(base, opponent=replace(base.opponent, board=(sc.minion("R_PLAIN", 2, 1, 1, max_health=3,
                                                                              taunt=True),)))
    ok = score_pair(_decision(kill_state, action), _decision(returned, action, 2), TEXTS, FULL)
    assert ok.verdict == "CONFIRMED" and ok.confirmed["OPPONENT.board[0:R_PLAIN].current_health"] == 1
    # the same spell, but an opponent Secret was consumed and nothing happened
    secret = replace(kill_state, opponent=replace(kill_state.opponent, secret_count=1))
    countered = replace(base, opponent=replace(base.opponent, secret_count=0, board=kill_state.opponent.board))
    result = score_pair(_decision(secret, action), _decision(countered, action, 2), TEXTS, FULL)
    assert result.verdict == "CONTRADICTED"
    kinds = {k: v[:2] for k, v in result.explanations.items()}
    assert kinds["OPPONENT.board[0:R_PLAIN].current_health"] == ("CONFIRMED_REACTION",
                                                                 "SECRET_CONSUMED_SPELL_HAD_NO_EFFECT")


def test_a_card_that_only_ever_appears_after_one_kind_of_spell_is_called_an_observation_gap_not_a_reaction():
    texts = TEXTS.extended([{"id": "S_HOLY", "text": "Deal $1 damage to a minion.", "type": "SPELL", "mechanics": [],
                             "spellSchool": "HOLY"}])
    pairs = []
    for number in range(5):
        before = _state(theirs=[sc.minion("V", 1, 9, 1)], hand=[sc.hand_card("S_HOLY", "SPELL", 1)])
        before = replace(before, self_player=replace(before.self_player, secret_count=1))
        after = replace(before, self_hand=(sc.hand_card("REWARD", "SPELL", 0),), self_hand_known_count=1)
        action = _cast("S_HOLY", sc.target_minion("OPPONENT", 1, "V"), 1)
        pairs.append((_decision(before, action, number * 2 + 1), _decision(after, action, number * 2 + 2)))
    associations = build_gain_associations(pairs, texts)
    assert associations["REWARD"].appearances == 5 and associations["REWARD"].always_with_own_secret_object
    result = score_pair(pairs[0][0], replace(pairs[0][1], state=replace(
        pairs[0][1].state, self_player=replace(pairs[0][1].state.self_player, hand_size=1, available_mana=9),
        opponent=replace(pairs[0][1].state.opponent, board=(sc.minion("V", 1, 8, 1, max_health=9),)))),
        texts, FULL, associations)
    assert any(kind == "OBSERVATION_GAP" for kind, *_ in result.explanations.values()), result.explanations


def test_own_hero_shield_comes_from_the_context_too():
    bolt = TEXTS.extended([_spell("S_ANY", "Deal $3 damage.")])
    state = sc.position(self_side=sc.side(hero_divine_shield=None), opponent=sc.side(),
                        hand=(sc.hand_card("S_ANY", "SPELL", 3),))
    action = _cast("S_ANY", sc.target_hero("SELF"))
    assert any(u.tag == "HERO_SHIELD_UNOBSERVED" for u in forecast_action(state, action, bolt, FULL).unknowns)
    known = forecast_action(state, action, bolt, replace(FULL, self_hero_divine_shield=True))
    assert known.status is Status.EXACT and known.exact_state().self_player.hero_health == 30     # the shield pops


def test_a_consumed_secret_is_required_before_a_spell_counts_as_countered():
    kill_state = _state(theirs=[sc.minion("W", 4, 4, 1)], hand=[sc.hand_card("S_BOLT", "SPELL", 3)],
                        secret_count=1)
    action = _cast("S_BOLT", sc.target_minion("OPPONENT", 1, "W"))
    nothing = replace(kill_state, self_player=replace(kill_state.self_player, available_mana=7, hand_size=0),
                      self_hand=(), self_hand_known_count=0)
    result = score_pair(_decision(kill_state, action), _decision(nothing, action, 2), TEXTS, FULL)
    assert result.contradicted                                  # the spell visibly did nothing ...
    assert all(kind != "CONFIRMED_REACTION" for kind, *_ in result.explanations.values())   # ... but no Secret went


def test_a_field_the_state_did_not_observe_is_not_scored_even_if_the_context_filled_it():
    state = _state(theirs=[sc.minion("W", 4, 4, 1)], hand=[sc.hand_card("S_BOLT", "SPELL", 3)])
    state = replace(state, opponent=replace(state.opponent, hero_divine_shield=None))
    action = _cast("S_BOLT", sc.target_minion("OPPONENT", 1, "W"))
    truth = replace(state, self_player=replace(state.self_player, available_mana=7, hand_size=0), self_hand=(),
                    self_hand_known_count=0,
                    opponent=replace(state.opponent, board=(sc.minion("W", 4, 1, 1, max_health=4),)))
    result = score_pair(_decision(state, action), _decision(truth, action, 2), TEXTS,
                        replace(FULL, opponent_hero_divine_shield=False))
    assert result.verdict == "CONFIRMED" and "OPPONENT.hero.divine_shield" not in result.contradicted
