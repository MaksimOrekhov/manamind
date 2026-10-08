"""ENGINE-QUICK-2: focused semantics for declarations built from existing primitives."""
from __future__ import annotations

from manamind.integrations.manaengine import ManaEngineSession

FILLER = "CS2_065"
DUCK = "EDR_492"
DUCKLING = "EDR_492t"
FLASH = "CORE_TRL_307"
ARCANE = "CORE_CS2_023"
ARCHER = "CORE_CS2_189"
FLAME_IMP = "CORE_EX1_319"
VOIDWALKER = FILLER


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


def _play(session: ManaEngineSession, card_id: str, *, hero: bool = False, own: bool = False, minion: str = "") -> None:
    def matches(action: dict) -> bool:
        if action["type"] != "PLAY_CARD" or action.get("card_id") != card_id:
            return False
        if minion:
            return action["target_card_id"] == minion and action["target_is_self"] == own and not action["target_is_hero"]
        return action["target_is_hero"] == hero and action["target_is_self"] == own

    session.apply_action(next(a for a in session.legal_actions() if matches(a)))


def _fill_to(session: ManaEngineSession, count: int) -> None:
    for _ in range(80):
        if len(_p1(session).self_player.board) >= count:
            return
        if _p1(session).active_player == "SELF":
            filler = next((a for a in session.legal_actions() if a.get("card_id") == FILLER), None)
            if filler is not None:
                session.apply_action(filler)
                continue
        _end_turn(session)
    raise AssertionError(f"could not fill the board to {count}")


def _wait_for_mother_duck(session: ManaEngineSession) -> None:
    for _ in range(30):
        if _p1(session).active_player == "SELF" and any(
            a.get("card_id") == DUCK for a in session.legal_actions()
        ):
            return
        _end_turn(session)
    raise AssertionError("Mother Duck did not become playable within the bounded fixture")


def test_declarations_and_duckling_dependency_are_reviewed_without_expanding_neighbors() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows

    definitions = {row.card_id: row for row in _definition_rows()}
    for card_id in (DUCK, FLASH, ARCANE, ARCHER, FLAME_IMP):
        row = definitions[card_id]
        assert row.support_state == "SUPPORTED" and row.rules_contract_reviewed
        assert row.ability == "EFFECT_COMPOSITION"
    token = definitions[DUCKLING]
    assert token.support_state == "VERIFIED_VANILLA" and token.rules_contract_reviewed
    assert (token.card_type, token.cost, token.attack, token.health, token.race, token.rush) == (
        "MINION", 1, 1, 1, "BEAST", True
    )
    for card_id in ("EDR_463", "CORE_EX1_197"):
        assert definitions[card_id].support_state == "UNSUPPORTED"


def test_mother_duck_summons_three_correct_rush_tokens_and_respects_capacity() -> None:
    session = _session([DUCK])
    _end_turns(session, 6)
    _play(session, DUCK)
    board = _p1(session).self_player.board
    tokens = [m for m in board if m.card.card_id == DUCKLING]
    assert len(board) == 4 and len(tokens) == 3
    assert all((m.current_attack, m.current_health, m.card.race) == (1, 1, "BEAST") and "RUSH" in m.card.mechanics for m in tokens)
    assert not any(a.get("source_card_id") == DUCKLING and a.get("target_is_hero") for a in session.legal_actions())

    for preexisting, expected_tokens in ((4, 2), (6, 0)):
        session = _session([DUCK])
        _fill_to(session, preexisting)
        _wait_for_mother_duck(session)
        _play(session, DUCK)
        board = _p1(session).self_player.board
        assert len(board) == 7
        assert sum(m.card.card_id == DUCKLING for m in board) == expected_tokens


def test_flash_of_light_heals_the_selected_character_then_draws_one() -> None:
    session = _session([FLASH, VOIDWALKER])
    _play(session, VOIDWALKER)
    _end_turns(session, 2)  # own second turn
    hp = next(a for a in session.legal_actions() if a["type"] == "HERO_POWER" and not a["target_is_hero"])
    session.apply_action(hp)
    before = _p1(session)
    assert before.self_player.board[0].current_health == 2
    assert before.self_player.deck_size >= 1
    _end_turns(session, 2)  # own third turn
    before = _p1(session)
    deck_before = before.self_player.deck_size
    _play(session, FLASH, minion=VOIDWALKER, own=True)
    after = _p1(session)
    assert next(m for m in after.self_player.board if m.card.card_id == VOIDWALKER).current_health == 3
    assert after.self_player.deck_size == deck_before - 1
    assert after.self_player.hero_health == before.self_player.hero_health


def test_arcane_intellect_draws_exactly_two() -> None:
    session = _session([ARCANE])
    _end_turns(session, 4)  # own third turn
    before = _p1(session)
    _play(session, ARCANE)
    after = _p1(session)
    assert after.self_player.deck_size == before.self_player.deck_size - 2
    assert ARCANE not in {card.card_id for card in after.self_hand}


def test_elven_archer_legal_menu_and_battlecry_damage_one() -> None:
    session = _session([ARCHER], [FILLER])
    _play(session, FILLER)  # own first turn
    _end_turn(session)
    _play(session, FILLER)  # opponent first turn
    _end_turn(session)
    actions = session.legal_actions()
    targets = {(a["target_is_hero"], a["target_is_self"], a.get("target_card_id")) for a in actions if a.get("card_id") == ARCHER}
    assert (True, True, "") in targets and (True, False, "") in targets
    assert sum(not is_hero for is_hero, _, _ in targets) == 2
    before = _p1(session)
    enemy = next(m for m in before.opponent.board if m.card.card_id == FILLER)
    enemy_hp = enemy.current_health
    own_hp = before.self_player.hero_health
    opp_hero_hp = before.opponent.hero_health
    _play(session, ARCHER, minion=FILLER, own=False)
    after = _p1(session)
    assert next(m for m in after.opponent.board if m.card.card_id == FILLER).current_health == enemy_hp - 1
    assert after.self_player.hero_health == own_hp and after.opponent.hero_health == opp_hero_hp


def test_flame_imp_battlecry_hits_only_its_controllers_hero_on_either_side() -> None:
    session = _session([FLAME_IMP], [FLAME_IMP])
    _play(session, FLAME_IMP)
    state = _p1(session)
    assert (state.self_player.hero_health, state.opponent.hero_health) == (27, 30)
    _end_turn(session)
    _play(session, FLAME_IMP)
    state = _p1(session)
    assert (state.self_player.hero_health, state.opponent.hero_health) == (27, 27)
    assert state.opponent.board[-1].card.card_id == FLAME_IMP
