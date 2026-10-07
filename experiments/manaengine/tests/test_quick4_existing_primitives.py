"""ENGINE-QUICK-4: declaration-only cards built from existing reviewed primitives.

Expectations come from the printed card text and Hearthstone rules, not from running the declaration.
Sessions use the Mage mirror required by the engine; the other classes' cards are semantic fixtures here.
"""
from __future__ import annotations

from manamind.integrations.manaengine import ManaEngineSession
from manamind.integrations.rosettastone.policy import encode_legal_actions

FILLER = "CORE_EX1_145"
RAZORJAW = "CS3_038"
SHIV = "CORE_EX1_278"
BASH = "CORE_AT_064"
SHIELD_BLOCK = "CORE_EX1_606"
WINTER = "RLK_709"
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


def _obs(session: ManaEngineSession, seat: str = "PLAYER1"):
    return session.observation(seat)


def _targets(session: ManaEngineSession, card_id: str) -> set[tuple[bool, bool, str]]:
    return {(a["target_is_hero"], a["target_is_self"], a["target_card_id"]) for a in session.legal_actions() if a.get("card_id") == card_id}


def _attacks(session: ManaEngineSession, source: str) -> list[dict]:
    return [a for a in session.legal_actions() if a["type"] == "ATTACK" and a.get("source_card_id") == source]


def test_declarations_reach_native_catalog_and_neighbours_stay_unsupported() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows

    definitions = {row.card_id: row for row in _definition_rows()}
    token = definitions[RAZORJAW]
    assert token.support_state == "VERIFIED_VANILLA" and token.rules_contract_reviewed and token.ability == "NONE"
    assert (token.card_type, token.cost, token.attack, token.health, token.race, token.rush, token.taunt) == ("MINION", 2, 3, 1, "MURLOC", True, False)
    for card_id in (SHIV, BASH, SHIELD_BLOCK, WINTER):
        assert definitions[card_id].support_state == "SUPPORTED" and definitions[card_id].rules_contract_reviewed
        assert definitions[card_id].ability == "EFFECT_COMPOSITION" and definitions[card_id].card_type == "SPELL"
    # Neighbours with textless metadata, Divine Shield, area Freeze or friendly healing are not vanilla/no-op declarations.
    for card_id in ("TLC_248", "TIME_053", "TIME_056", "CORE_CS2_028", "RLK_067", "CORE_EX1_309"):
        assert definitions[card_id].support_state == "UNSUPPORTED"


def test_shiv_deals_one_to_any_character_and_draws_one() -> None:
    session = _session([SHIV], [RAZORJAW])
    _end_turns(session, 3)  # opponent's second turn: two mana
    session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == RAZORJAW))
    _end_turns(session, 1)  # our second turn: two mana
    actions = session.legal_actions()
    assert encode_legal_actions(actions).shape[0] == len(actions)
    assert _targets(session, SHIV) == {(True, False, ""), (True, True, ""), (False, False, RAZORJAW)}
    before = _obs(session)
    _play(session, SHIV, hero=True)
    after = _obs(session)
    assert after.opponent.hero_health == 29 and after.self_player.hero_health == 30
    assert (after.self_player.hand_size, after.self_player.deck_size) == (before.self_player.hand_size, before.self_player.deck_size - 1)
    assert len(after.opponent.board) == 1
    assert not session.training_eligible


def test_shiv_kills_a_one_health_minion_and_hits_our_own_hero() -> None:
    session = _session([SHIV, SHIV], [RAZORJAW])
    _end_turns(session, 3)
    session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == RAZORJAW))
    _end_turns(session, 1)
    _play(session, SHIV, minion=RAZORJAW)
    assert _obs(session).opponent.board == ()
    session = _session([SHIV])
    _end_turns(session, 2)
    _play(session, SHIV, hero=True, own=True)
    assert _obs(session).self_player.hero_health == 29


def test_bash_damage_and_armor_exact_and_opponent_side() -> None:
    session = _session([BASH])
    _end_turns(session, 2)
    assert _obs(session).self_player.armor == 0
    _play(session, BASH, hero=True)
    state = _obs(session)
    assert state.opponent.hero_health == 27 and state.self_player.armor == 3 and state.self_player.hero_health == 30
    assert state.opponent.armor == 0
    # Armor absorbs later damage first: the opponent's own Bash on our armored hero is not needed; use its hero power.
    session = _session([], [BASH])
    _end_turns(session, 3)
    _play(session, BASH, hero=True)  # opponent damages our hero by 3 and gains 3 armor
    state = _obs(session)
    assert state.self_player.hero_health == 27 and state.opponent.armor == 3 and state.self_player.armor == 0


def test_shield_block_armor_five_and_one_draw_without_damage() -> None:
    session = _session([SHIELD_BLOCK])
    _end_turns(session, 2)
    actions = session.legal_actions()
    assert all(a["target_is_hero"] is False and a["target_card_id"] == "" for a in actions if a.get("card_id") == SHIELD_BLOCK)
    before = _obs(session)
    _play(session, SHIELD_BLOCK)
    after = _obs(session)
    assert after.self_player.armor == 5 and after.self_player.hero_health == 30 and after.opponent.hero_health == 30
    assert (after.self_player.hand_size, after.self_player.deck_size) == (before.self_player.hand_size, before.self_player.deck_size - 1)
    # Opponent side: it gains its own armor, our armor stays zero.
    session = _session([], [SHIELD_BLOCK])
    _end_turns(session, 3)
    _play(session, SHIELD_BLOCK)
    state = _obs(session)
    assert state.opponent.armor == 5 and state.self_player.armor == 0


def test_remorseless_winter_hits_enemy_hero_and_minions_only_then_draws() -> None:
    # Both sides cast Demonic Assault first: we own two Voidwalkers, the opponent owns two, both heroes are damaged.
    session = _session([ASSAULT, WINTER], [ASSAULT])
    _end_turns(session, 6)
    _play(session, ASSAULT, hero=True)  # our four-mana turn: opponent hero 27
    _end_turns(session, 1)  # opponent's fourth turn
    _play(session, ASSAULT, hero=True)  # its Assault hits our hero: 27
    state = _obs(session)
    assert state.self_player.hero_health == 27 and len(state.opponent.board) == 2 and len(state.self_player.board) == 2
    _end_turns(session, 1)  # our fifth turn: five mana, Winter costs four
    actions = session.legal_actions()
    assert encode_legal_actions(actions).shape[0] == len(actions)
    assert all(not a["target_is_hero"] and a["target_card_id"] == "" for a in actions if a.get("card_id") == WINTER)  # untargeted
    before = _obs(session)
    _play_untargeted(session, WINTER)
    after = _obs(session)
    assert after.opponent.hero_health == 25  # 27 - 2
    assert [m.current_health for m in after.opponent.board] == [1, 1]  # 1/3 Voidwalkers took 2
    assert after.self_player.hero_health == 27  # friendly hero untouched
    assert [m.current_health for m in after.self_player.board] == [3, 3]  # friendly minions untouched
    assert (after.self_player.hand_size, after.self_player.deck_size) == (before.self_player.hand_size, before.self_player.deck_size - 1)


def _play_untargeted(session: ManaEngineSession, card_id: str) -> None:
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "PLAY_CARD" and a.get("card_id") == card_id))


def test_remorseless_winter_opponent_side_hits_our_side_only() -> None:
    session = _session([ASSAULT], [WINTER])
    _end_turns(session, 6)
    _play(session, ASSAULT, hero=True)  # we own two Voidwalkers; opponent hero 27
    _end_turns(session, 1)  # opponent's fourth turn: four mana
    _play_untargeted(session, WINTER)
    state = _obs(session)
    assert state.self_player.hero_health == 28 and state.opponent.hero_health == 27
    assert [m.current_health for m in state.self_player.board] == [1, 1]
    assert state.opponent.board == ()


def test_redgill_razorjaw_rush_attacks_minions_but_not_the_hero_on_its_summon_turn() -> None:
    # Summon turn with no enemy minion: Rush has no legal attack at all (it cannot hit the hero).
    session = _session([RAZORJAW])
    _end_turns(session, 2)
    _play_untargeted(session, RAZORJAW)
    state = _obs(session)
    jaw = state.self_player.board[0]
    assert (jaw.card.card_id, jaw.current_attack, jaw.current_health, jaw.can_attack) == (RAZORJAW, 3, 1, True)
    assert "RUSH" in jaw.card.mechanics and jaw.card.race == "MURLOC"
    assert _attacks(session, RAZORJAW) == []
    _end_turns(session, 2)  # next own turn: ordinary attacks, so the hero is a legal target
    assert {a["target_is_hero"] for a in _attacks(session, RAZORJAW)} == {True}
    session.apply_action(_attacks(session, RAZORJAW)[0])
    assert _obs(session).opponent.hero_health == 27

    # With an enemy minion present, the summoning-turn Rush attack may only target that minion.
    session = _session([RAZORJAW], [RAZORJAW])
    _end_turns(session, 3)
    _play_untargeted(session, RAZORJAW)  # opponent's Razorjaw (it was summoned on its own turn)
    _end_turns(session, 1)
    _play_untargeted(session, RAZORJAW)  # ours, this turn
    attacks = _attacks(session, RAZORJAW)
    assert len(attacks) == 1 and not attacks[0]["target_is_hero"] and attacks[0]["target_card_id"] == RAZORJAW
    session.apply_action(attacks[0])
    state = _obs(session)
    assert state.opponent.board == () and state.self_player.board == ()  # 3 damage kills the 3/1 both ways
    assert state.opponent.hero_health == 30
