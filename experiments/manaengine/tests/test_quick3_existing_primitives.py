"""ENGINE-QUICK-3: declaration-only minions and a spell built from existing reviewed primitives.

Expectations come from the printed card text and Hearthstone rules, not from running the declaration.
Sessions use the Mage mirror required by the engine; the other classes' cards are semantic fixtures here.
"""
from __future__ import annotations

from manamind.integrations.manaengine import ManaEngineSession
from manamind.models.policy import encode_legal_actions

FILLER = "CORE_EX1_145"
FIRE_ELEMENTAL = "CORE_CS2_042"
GLACIAL_SHARD = "CORE_UNG_205"
LOOT_HOARDER = "CORE_EX1_096"
VOODOO_DOCTOR = "CORE_EX1_011"
CHAOS_STRIKE = "CORE_BT_035"
ASSAULT = "CORE_SW_088"
VOIDWALKER = "CS2_065"


def _session(deck1: list[str], deck2: list[str] | None = None) -> ManaEngineSession:
    pad = lambda cards: [*cards, *([FILLER] * (30 - len(cards)))]  # noqa: E731
    return ManaEngineSession(pad(deck1), pad(deck2 or []), player1_class="MAGE", player2_class="MAGE", shuffle=False)


def _end_turns(session: ManaEngineSession, count: int) -> None:
    for _ in range(count):
        session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))


def _select(session: ManaEngineSession, kind: str, card_id: str, *, hero: bool = False, own: bool = False, minion: str = ""):
    def matches(action: dict) -> bool:
        if action["type"] != kind or action.get("card_id") != card_id:
            return False
        if minion:
            return action["target_card_id"] == minion and action["target_is_self"] == own and not action["target_is_hero"]
        return action["target_is_hero"] == hero and action["target_is_self"] == own

    return next(a for a in session.legal_actions() if matches(a))


def _play(session: ManaEngineSession, card_id: str, **target) -> None:
    session.apply_action(_select(session, "PLAY_CARD", card_id, **target))


def _power(session: ManaEngineSession, **target) -> None:
    session.apply_action(_select(session, "HERO_POWER", "HERO_08bp", **target))


def _obs(session: ManaEngineSession, seat: str = "PLAYER1"):
    return session.observation(seat)


def _targets(session: ManaEngineSession, card_id: str) -> set[tuple[bool, bool, str]]:
    return {(a["target_is_hero"], a["target_is_self"], a["target_card_id"]) for a in session.legal_actions() if a.get("card_id") == card_id}


def test_declarations_reach_native_catalog_and_neighbours_stay_unsupported() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows

    definitions = {row.card_id: row for row in _definition_rows()}
    for card_id in (FIRE_ELEMENTAL, GLACIAL_SHARD, LOOT_HOARDER, VOODOO_DOCTOR, CHAOS_STRIKE):
        assert definitions[card_id].support_state == "SUPPORTED" and definitions[card_id].rules_contract_reviewed
    assert definitions[FIRE_ELEMENTAL].required_mechanics == ["BATTLECRY"] and definitions[FIRE_ELEMENTAL].effects[0].amount == 4
    assert definitions[LOOT_HOARDER].ability == "DEATHRATTLE_DRAW" and definitions[LOOT_HOARDER].deathrattle_draw_count == 1
    assert definitions[CHAOS_STRIKE].card_type == "SPELL" and [e.amount for e in definitions[CHAOS_STRIKE].effects] == [2, 1]
    # Nearby cards with a different condition, count, type filter or target stay explicitly unsupported.
    for card_id in ("RLK_511", "CATA_612", "EDR_468", "CORE_OG_047", "TIME_431", "RLK_708"):
        assert definitions[card_id].support_state == "UNSUPPORTED"


def test_fire_elemental_battlecry_targets_any_character_and_deals_exactly_four() -> None:
    # The opponent's Voodoo Doctor (2/1) gives a minion target. Our side has no minion before the battlecry.
    def scenario(**target):
        session = _session([FIRE_ELEMENTAL], [VOODOO_DOCTOR])
        _end_turns(session, 1)
        _play(session, VOODOO_DOCTOR, hero=True, own=True)  # opponent heals its own hero (no effect at full health)
        _end_turns(session, 9)  # our sixth turn: six mana
        actions = session.legal_actions()
        assert encode_legal_actions(actions).shape[0] == len(actions)
        assert _targets(session, FIRE_ELEMENTAL) == {(True, False, ""), (True, True, ""), (False, False, VOODOO_DOCTOR)}
        _play(session, FIRE_ELEMENTAL, **target)
        return session, _obs(session)

    session, state = scenario(hero=True)
    assert state.opponent.hero_health == 26 and state.self_player.hero_health == 30 and len(state.opponent.board) == 1
    elemental = state.self_player.board[0]
    assert (elemental.card.card_id, elemental.current_attack, elemental.current_health, elemental.can_attack) == (FIRE_ELEMENTAL, 6, 5, False)
    assert not session.training_eligible
    _, state = scenario(hero=True, own=True)
    assert state.self_player.hero_health == 26 and state.opponent.hero_health == 30
    _, state = scenario(minion=VOODOO_DOCTOR)
    assert state.opponent.board == () and state.opponent.hero_health == 30 and len(state.self_player.board) == 1


def test_glacial_shard_freezes_only_enemy_characters() -> None:
    session = _session([GLACIAL_SHARD], [ASSAULT])
    _end_turns(session, 7)
    _play(session, ASSAULT, hero=True)  # opponent: damage our hero, two Voidwalkers
    _end_turns(session, 1)  # our fifth turn
    assert _targets(session, GLACIAL_SHARD) == {(True, False, ""), (False, False, VOIDWALKER)}  # no own hero, no own minions
    _play(session, GLACIAL_SHARD, minion=VOIDWALKER)
    state = _obs(session)
    assert [m.frozen for m in state.opponent.board] == [True, False]
    assert state.opponent.hero_frozen in (False, None) and len(state.self_player.board) == 1
    assert not state.self_player.board[0].frozen and (state.self_player.board[0].current_attack, state.self_player.board[0].current_health) == (2, 1)
    # Opponent-side execution: its Glacial Shard freezes our hero, and nothing on its own side.
    session = _session([], [GLACIAL_SHARD])
    _end_turns(session, 1)
    _play(session, GLACIAL_SHARD, hero=True)
    state = _obs(session)
    assert state.self_player.hero_frozen is True and not state.opponent.hero_frozen
    assert [(m.card.card_id, m.frozen) for m in state.opponent.board] == [(GLACIAL_SHARD, False)]


def test_loot_hoarder_draws_one_card_only_when_it_dies() -> None:
    session = _session([LOOT_HOARDER])
    _end_turns(session, 2)  # our second turn: two mana
    before = _obs(session)
    _play(session, LOOT_HOARDER)
    played = _obs(session)
    assert (played.self_player.hand_size, played.self_player.deck_size) == (before.self_player.hand_size - 1, before.self_player.deck_size)
    _end_turns(session, 1)
    assert _obs(session).self_player.hand_size == played.self_player.hand_size  # alive: nothing drawn
    _power(session, minion=LOOT_HOARDER)  # opponent's hero power kills the 2/1
    dead = _obs(session)
    assert dead.self_player.board == ()
    assert (dead.self_player.hand_size, dead.self_player.deck_size) == (played.self_player.hand_size + 1, played.self_player.deck_size - 1)
    # Opponent-side: its Loot Hoarder dies to our hero power and the opponent, not us, draws.
    session = _session([], [LOOT_HOARDER])
    _end_turns(session, 3)
    _play(session, LOOT_HOARDER)
    before = _obs(session, "PLAYER2")
    _end_turns(session, 1)
    ours = _obs(session, "PLAYER1").self_player
    _power(session, minion=LOOT_HOARDER)
    after = _obs(session, "PLAYER2")
    assert after.self_player.hand_size == before.self_player.hand_size + 1 and after.self_player.deck_size == before.self_player.deck_size - 1
    mine = _obs(session, "PLAYER1").self_player  # our own hand and deck are untouched by the opponent's Deathrattle
    assert (mine.hand_size, mine.deck_size) == (ours.hand_size, ours.deck_size)


def test_voodoo_doctor_restores_exactly_two_capped_at_maximum() -> None:
    session = _session([VOODOO_DOCTOR, VOODOO_DOCTOR], [ASSAULT])
    _end_turns(session, 7)
    _play(session, ASSAULT, hero=True)  # our hero 27; opponent has two Voidwalkers
    _end_turns(session, 1)  # our fifth turn: five mana
    assert _targets(session, VOODOO_DOCTOR) == {(True, False, ""), (True, True, ""), (False, False, VOIDWALKER)}
    _power(session, minion=VOIDWALKER)  # 1 damage: 1/3 -> 1/2
    assert sorted(m.current_health for m in _obs(session).opponent.board) == [2, 3]
    _play(session, VOODOO_DOCTOR, hero=True, own=True)
    state = _obs(session)
    assert state.self_player.hero_health == 29  # exactly +2 on a damaged hero
    _play(session, VOODOO_DOCTOR, minion=VOIDWALKER)
    state = _obs(session)
    assert sorted(m.current_health for m in state.opponent.board) == [3, 3]  # +2 capped at maximum Health 3
    assert state.opponent.hero_health == 30 and state.self_player.hero_health == 29 and len(state.self_player.board) == 2
    # A full-health hero is not overhealed, and the opponent side can execute the same battlecry.
    session = _session([], [VOODOO_DOCTOR])
    _end_turns(session, 1)
    _play(session, VOODOO_DOCTOR, hero=True, own=True)
    assert _obs(session).opponent.hero_health == 30


def test_chaos_strike_hero_attack_lasts_one_turn_and_draws_one_card() -> None:
    session = _session([CHAOS_STRIKE], [CHAOS_STRIKE])
    _end_turns(session, 2)
    before = _obs(session)
    assert before.self_player.hero_attack == 0
    _play(session, CHAOS_STRIKE)
    state = _obs(session)
    assert state.self_player.hero_attack == 2
    assert (state.self_player.hand_size, state.self_player.deck_size) == (before.self_player.hand_size, before.self_player.deck_size - 1)
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "ATTACK" and a["source_is_hero"] and a["target_is_hero"]))
    assert _obs(session).opponent.hero_health == 28
    _end_turns(session, 1)
    assert _obs(session, "PLAYER1").self_player.hero_attack == 0  # expired with the end of our turn
    # Opponent-side execution on its own turn, then expiry again; our hero takes the two damage.
    _end_turns(session, 1)
    _end_turns(session, 1)
    _play(session, CHAOS_STRIKE)
    assert _obs(session, "PLAYER2").self_player.hero_attack == 2
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "ATTACK" and a["source_is_hero"] and a["target_is_hero"]))
    assert _obs(session, "PLAYER1").self_player.hero_health == 28
    _end_turns(session, 1)
    assert _obs(session, "PLAYER2").self_player.hero_attack == 0
