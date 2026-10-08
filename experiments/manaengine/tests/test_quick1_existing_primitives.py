"""ENGINE-QUICK-1: declaration-only cards built from existing reviewed primitives.

Expectations come from the printed card text and the Hearthstone rules, not from running the declaration.
Sessions use the Mage mirror required by the engine; the other classes' cards are semantic fixtures here.
"""
from __future__ import annotations

import pytest

from manamind.integrations.manaengine import ManaEngineSession
from manamind.integrations.rosettastone.policy import encode_legal_actions

FILLER = "CORE_EX1_145"
HAMMER = "CORE_CS2_094"
CONSECRATION = "CORE_CS2_093"
VOID_SHARD = "CORE_SW_442"
ASSAULT = "CORE_SW_088"
VOIDWALKER = "CS2_065"


def _session(deck1: list[str], deck2: list[str] | None = None) -> ManaEngineSession:
    pad = lambda cards: [*cards, *([FILLER] * (30 - len(cards)))]  # noqa: E731
    return ManaEngineSession(pad(deck1), pad(deck2 or []), player1_class="MAGE", player2_class="MAGE", shuffle=False)


def _end_turns(session: ManaEngineSession, count: int) -> None:
    for _ in range(count):
        session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))


def _play(session: ManaEngineSession, card_id: str, *, hero: bool = False, own: bool = False, minion: str = "") -> None:
    def matches(action: dict) -> bool:
        if action["type"] != "PLAY_CARD" or action.get("card_id") != card_id:
            return False
        if minion:
            return action["target_card_id"] == minion and action["target_is_self"] == own and not action["target_is_hero"]
        return action["target_is_hero"] == hero and action["target_is_self"] == own

    session.apply_action(next(a for a in session.legal_actions() if matches(a)))


def _p1(session: ManaEngineSession):
    return session.observation("PLAYER1")


def test_declarations_reach_native_catalog_and_neighbours_stay_unsupported() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows

    definitions = {row.card_id: row for row in _definition_rows()}
    for card_id in (HAMMER, CONSECRATION, VOID_SHARD, ASSAULT):
        assert definitions[card_id].support_state == "SUPPORTED" and definitions[card_id].rules_contract_reviewed
        assert definitions[card_id].ability == "EFFECT_COMPOSITION" and definitions[card_id].card_type == "SPELL"
    assert [(e.amount, e.lifesteal) for e in definitions[VOID_SHARD].effects] == [(4, True)]
    assert definitions[ASSAULT].effects[1].summon_card == VOIDWALKER and definitions[ASSAULT].effects[1].amount == 2
    token = definitions[VOIDWALKER]
    assert token.support_state == "VERIFIED_VANILLA" and token.rules_contract_reviewed
    assert (token.card_type, token.cost, token.attack, token.health, token.race, token.taunt) == ("MINION", 1, 1, 3, "DEMON", True)
    # Similar-looking cards whose behavior is not expressible stay explicitly unsupported (never vanilla/no-op).
    # Land Ho! summons Cannoneers whose end-of-turn random-enemy damage has no reviewed primitive.
    # Moonwell and Holy Nova became declarations when the healing pipeline (ENGINE-PRIMITIVE-1) added friendly area healing.
    assert definitions["CAP_102"].support_state == "UNSUPPORTED"
    for card_id in ("EDR_476", "CORE_CS1_112"):
        assert definitions[card_id].support_state == "SUPPORTED"


def test_hammer_of_wrath_hits_either_hero_and_draws() -> None:
    session = _session([HAMMER])
    _end_turns(session, 4)  # own third turn: three mana
    actions = session.legal_actions()
    assert encode_legal_actions(actions).shape[0] == len(actions)
    targets = {(a["target_is_hero"], a["target_is_self"]) for a in actions if a.get("card_id") == HAMMER}
    assert targets == {(True, False), (True, True)}  # any character: both heroes, no minions exist yet
    before = _p1(session)
    _play(session, HAMMER, hero=True)
    after = _p1(session)
    assert after.opponent.hero_health == 27 and after.self_player.hero_health == 30
    assert len(after.self_hand) == len(before.self_hand)  # the spell leaves the hand and one card is drawn
    assert HAMMER not in {c.card_id for c in after.self_hand}
    assert not session.training_eligible


def test_void_shard_lifesteal_heals_hero_but_not_above_maximum() -> None:
    session = _session([VOID_SHARD])
    _end_turns(session, 6)  # own fourth turn: four mana
    _play(session, VOID_SHARD, own=True, hero=True)  # 30 - 4, then Lifesteal restores 4
    state = _p1(session)
    assert state.self_player.hero_health == 30 and state.opponent.hero_health == 30
    # An unhealed Lifesteal source would leave the hero at 26; a missing damage step would leave the enemy at 30.
    session = _session([VOID_SHARD])
    _end_turns(session, 6)
    _play(session, VOID_SHARD, hero=True)
    state = _p1(session)
    assert state.opponent.hero_health == 26 and state.self_player.hero_health == 30


def test_demonic_assault_damage_and_taunt_voidwalkers_on_both_sides() -> None:
    # Opponent casts it on our hero first, then we use Consecration, Hammer of Wrath and Void Shard on the result.
    session = _session([CONSECRATION, HAMMER, VOID_SHARD], [ASSAULT])
    _end_turns(session, 7)  # opponent's fourth turn: four mana
    before = _p1(session)
    assert before.opponent.hero_health == 30 and len(before.opponent.board) == 0
    _play(session, ASSAULT, hero=True, own=False)  # active seat is the opponent: its enemy is our hero
    state = _p1(session)
    assert state.self_player.hero_health == 27 and state.opponent.hero_health == 30
    assert [m.card.card_id for m in state.opponent.board] == [VOIDWALKER, VOIDWALKER]
    assert all((m.current_attack, m.current_health, m.can_attack) == (1, 3, False) for m in state.opponent.board)
    assert all("TAUNT" in m.card.mechanics and m.card.race == "DEMON" for m in state.opponent.board)
    assert len(state.self_player.board) == 0
    _end_turns(session, 1)  # our fifth turn: five mana

    # Consecration: two damage to every enemy character (hero and both Voidwalkers), nothing to our side.
    _play(session, CONSECRATION)
    state = _p1(session)
    assert state.opponent.hero_health == 28 and state.self_player.hero_health == 27
    assert [m.current_health for m in state.opponent.board] == [1, 1]
    _end_turns(session, 2)  # our sixth turn: six mana

    # Hammer of Wrath on one wounded Voidwalker kills it and still draws.
    hand_before = len(_p1(session).self_hand)
    _play(session, HAMMER, minion=VOIDWALKER)
    state = _p1(session)
    assert [m.card.card_id for m in state.opponent.board] == [VOIDWALKER] and state.opponent.hero_health == 28
    assert len(state.self_hand) == hand_before  # -1 played, +1 drawn
    _end_turns(session, 2)  # our seventh turn: seven mana

    # Void Shard to the face heals our damaged hero by the damage dealt.
    _play(session, VOID_SHARD, hero=True)
    state = _p1(session)
    assert state.opponent.hero_health == 24 and state.self_player.hero_health == 30
    assert [m.current_health for m in state.opponent.board] == [1]


def test_demonic_assault_own_side_summons_and_damages_selected_character() -> None:
    session = _session([ASSAULT])
    _end_turns(session, 6)  # four mana
    actions = session.legal_actions()
    assert any(a.get("card_id") == ASSAULT and a["target_is_hero"] and not a["target_is_self"] for a in actions)
    _play(session, ASSAULT, hero=True)
    state = _p1(session)
    assert state.opponent.hero_health == 27 and state.self_player.hero_health == 30
    assert [(m.card.card_id, m.current_attack, m.current_health, m.can_attack) for m in state.self_player.board] == [
        (VOIDWALKER, 1, 3, False)
    ] * 2
    # The summoned Taunt blockers constrain the opponent's attack target selection in the ordinary way.
    _end_turns(session, 1)
    assert not session.training_eligible


@pytest.mark.parametrize("card_id", [HAMMER, CONSECRATION, VOID_SHARD, ASSAULT])
def test_unaffordable_quick1_card_is_not_legal(card_id: str) -> None:
    session = _session([card_id])
    assert all(a.get("card_id") != card_id for a in session.legal_actions())  # no mana on turn one
