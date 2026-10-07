"""ENGINE-QUICK-5: exact vanilla and intrinsic-keyword card coverage."""
from __future__ import annotations

from manamind.integrations.manaengine import ManaEngineSession

FILLER = "CS2_065"
FLAME_IMP = "CORE_EX1_319"
SENJIN = "CORE_CS2_179"
SWAMP_LEECH = "CORE_GIL_558"
SCORCHING_OBSERVER = "EDR_486"
SLEEPY_DRAGON = "CORE_LOOT_137"
BOULDERFIST_OGRE = "Core_CS2_200"


def _session(deck1: list[str], deck2: list[str] | None = None) -> ManaEngineSession:
    pad = lambda cards: [*cards, *([FILLER] * (30 - len(cards)))]  # noqa: E731
    return ManaEngineSession(pad(deck1), pad(deck2 or []), player1_class="MAGE", player2_class="MAGE", shuffle=False)


def _end_turn(session: ManaEngineSession) -> None:
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))


def _end_turns(session: ManaEngineSession, count: int) -> None:
    for _ in range(count):
        _end_turn(session)


def _p1(session: ManaEngineSession):
    return session.observation("PLAYER1")


def _play(session: ManaEngineSession, card_id: str) -> None:
    action = next(a for a in session.legal_actions() if a["type"] == "PLAY_CARD" and a.get("card_id") == card_id)
    session.apply_action(action)


def _attack(session: ManaEngineSession, source_id: str, *, hero: bool = False, target_card_id: str = "") -> None:
    action = next(
        a for a in session.legal_actions()
        if a["type"] == "ATTACK" and a.get("source_card_id") == source_id
        and a.get("target_is_hero") == hero and a.get("target_card_id", "") == target_card_id
    )
    session.apply_action(action)


def test_exact_pinned_vanilla_definitions_and_neighbors() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows

    definitions = {row.card_id: row for row in _definition_rows()}
    expected = {
        SENJIN: (3, 5, True, False, False),
        SWAMP_LEECH: (2, 1, False, True, False),
        SCORCHING_OBSERVER: (7, 9, False, True, True),
        SLEEPY_DRAGON: (6, 12, True, False, False),
        BOULDERFIST_OGRE: (6, 7, False, False, False),
    }
    for card_id, (attack, health, taunt, lifesteal, rush) in expected.items():
        row = definitions[card_id]
        assert row.support_state == "VERIFIED_VANILLA" and row.rules_contract_reviewed, card_id
        assert row.ability == "NONE" and row.card_type == "MINION", card_id
        assert (row.attack, row.health, row.taunt, row.lifesteal, row.rush) == (
            attack, health, taunt, lifesteal, rush
        ), card_id
    assert BOULDERFIST_OGRE in definitions
    assert "CORE_CS2_200" not in definitions  # preserve the pinned mixed-case ID exactly
    assert definitions[SCORCHING_OBSERVER].required_mechanics == ["LIFESTEAL", "RUSH"]
    assert definitions[SWAMP_LEECH].required_mechanics == ["LIFESTEAL"]
    assert definitions[SENJIN].required_mechanics == ["TAUNT"]
    assert definitions[SLEEPY_DRAGON].required_mechanics == ["TAUNT"]
    assert definitions[BOULDERFIST_OGRE].required_mechanics == []
    for card_id in ("EDR_485", "EDR_487"):
        assert definitions[card_id].support_state == "UNSUPPORTED"


def test_swamp_leech_lifesteal_heals_its_controller() -> None:
    session = _session([FLAME_IMP, SWAMP_LEECH])
    _play(session, FLAME_IMP)  # its Battlecry leaves our hero at 27
    _end_turns(session, 2)
    _attack(session, FLAME_IMP, hero=True)  # opponent hero to 27
    _end_turns(session, 2)
    _play(session, SWAMP_LEECH)
    _end_turns(session, 4)
    _attack(session, SWAMP_LEECH, hero=True)
    state = _p1(session)
    assert state.self_player.hero_health == 29  # 27, then 2 Lifesteal healing
    assert state.opponent.hero_health == 25


def test_scorching_observer_rush_lifesteal_and_summon_turn_targeting() -> None:
    session = _session([FLAME_IMP, SCORCHING_OBSERVER], [SLEEPY_DRAGON])
    _play(session, FLAME_IMP)  # damage our hero so Lifesteal is observable
    _end_turns(session, 17)  # opponent's ninth turn
    _play(session, SLEEPY_DRAGON)
    _end_turn(session)  # our tenth turn, enough mana for Scorching Observer
    _play(session, SCORCHING_OBSERVER)
    actions = [a for a in session.legal_actions() if a["type"] == "ATTACK" and a.get("source_card_id") == SCORCHING_OBSERVER]
    assert actions
    assert all(not a.get("target_is_hero") for a in actions)
    assert any(a.get("target_card_id") == SLEEPY_DRAGON for a in actions)
    _attack(session, SCORCHING_OBSERVER, target_card_id=SLEEPY_DRAGON)
    state = _p1(session)
    assert state.self_player.hero_health == 30
    dragon = next(m for m in state.opponent.board if m.card.card_id == SLEEPY_DRAGON)
    observer = next(m for m in state.self_player.board if m.card.card_id == SCORCHING_OBSERVER)
    assert dragon.current_health == 5 and observer.current_health == 3


def test_taunt_minions_and_keywordless_ogre_play_with_exact_stats() -> None:
    session = _session([SENJIN, BOULDERFIST_OGRE], [FILLER])
    _end_turns(session, 6)  # own fourth turn
    _play(session, SENJIN)
    minion = next(m for m in _p1(session).self_player.board if m.card.card_id == SENJIN)
    assert (minion.current_attack, minion.current_health, minion.card.mechanics) == (3, 5, ("TAUNT",))
    _end_turns(session, 4)  # own sixth turn
    _play(session, BOULDERFIST_OGRE)
    ogre = next(m for m in _p1(session).self_player.board if m.card.card_id == BOULDERFIST_OGRE)
    assert (ogre.current_attack, ogre.current_health, ogre.card.mechanics) == (6, 7, ())
