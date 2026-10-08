"""ENGINE-PRIMITIVE-1: healing pipeline v1 through real declarations and the Python session.

Expectations come from the printed card text and Hearthstone healing rules, never from running a declaration.
The engine only admits Mage mirrors, so the Priest cards are semantic fixtures; the opponent damages our hero with
Arcane Shot (2 damage to any character) so that healing is visible and never capped by the 30 Health maximum.
"""
from __future__ import annotations

import pytest

from manamind.integrations.manaengine import (
    AttemptReason, ManaEngineSession, SimulationOutcome, UnsupportedSimulationError, attempt_action,
)
from manamind.integrations.manaengine.engine import _definition_rows, _load_native, _parse_effect_steps
from manamind.integrations.rosettastone.policy import encode_legal_actions

FILLER = "CORE_EX1_145"
SHOT = "CORE_DS1_185"  # Arcane Shot: deal 2 damage
MOONWELL = "EDR_476"
NOVA = "CORE_CS1_112"
POTION = "CORE_CFM_604"
CLERIC = "CATA_216"
FLASH = "CORE_AT_055"
JAWS = "CS3_038"  # Razorjaw: vanilla 3/1 used as an enemy board presence


def _session(deck1: list[str], deck2: list[str]) -> ManaEngineSession:
    pad = lambda cards: [*cards, *([FILLER] * (30 - len(cards)))]  # noqa: E731
    return ManaEngineSession(pad(deck1), pad(deck2), player1_class="MAGE", player2_class="MAGE", shuffle=False)


def _end(session: ManaEngineSession) -> None:
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))


def _play(session: ManaEngineSession, card_id: str, *, hero: bool | None = None, own: bool = False) -> None:
    def matches(action: dict) -> bool:
        if action["type"] != "PLAY_CARD" or action.get("card_id") != card_id:
            return False
        return hero is None or (action["target_is_hero"] == hero and action["target_is_self"] == own)

    session.apply_action(next(a for a in session.legal_actions() if matches(a)))


def _hero(session: ManaEngineSession, seat: str = "PLAYER1") -> int:
    return session.observation(seat).self_player.hero_health


def _to_player_one_turn(session: ManaEngineSession, turn: int, shots: dict[int, int], enemy_minion_turn: int | None = None) -> None:
    """Pass until the first seat's `turn`-th turn; the opponent shoots our hero `shots[k]` times on its k-th turn."""
    for k in range(1, turn):
        _end(session)  # first seat's turn k
        if k == enemy_minion_turn:
            _play(session, JAWS)
        for _ in range(shots.get(k, 0)):
            _play(session, SHOT, hero=True, own=False)
        _end(session)  # second seat's turn k


def test_declarations_reach_the_native_catalog_and_neighbours_stay_unsupported() -> None:
    native = _load_native()
    rows = {row.card_id: row for row in _definition_rows()}
    for card_id in (MOONWELL, NOVA, POTION, CLERIC):
        assert rows[card_id].support_state == "SUPPORTED" and rows[card_id].rules_contract_reviewed
        assert rows[card_id].ability == "EFFECT_COMPOSITION"
    area = native.TargetSelector.ALL_FRIENDLY_CHARACTERS
    assert [(e.kind, e.target, e.amount) for e in rows[MOONWELL].effects] == [
        (native.EffectKind.DAMAGE, native.TargetSelector.ENEMY_CHARACTERS, 4), (native.EffectKind.HEAL, area, 4)]
    assert [(e.kind, e.target, e.amount) for e in rows[NOVA].effects] == [
        (native.EffectKind.DAMAGE, native.TargetSelector.ENEMY_MINIONS, 2), (native.EffectKind.HEAL, area, 2)]
    assert [(e.kind, e.target, e.amount) for e in rows[POTION].effects] == [
        (native.EffectKind.HEAL, native.TargetSelector.EXPLICIT_FRIENDLY_CHARACTER, 12), (native.EffectKind.DRAW, native.TargetSelector.SELF, 1)]
    assert [(e.kind, e.target, e.amount) for e in rows[CLERIC].effects] == [
        (native.EffectKind.GRANT_HEALING_BONUS, native.TargetSelector.SELF, 2)]
    # Healing-adjacent cards that need triggers, conversion, dynamic amounts or other primitives are not declared.
    for card_id in ("CORE_BAR_310", "CORE_BAR_313", "TIME_431", "CATA_301", "CAP_803", "CORE_EX1_309", "JAIL_912", "CATA_300"):
        assert rows[card_id].support_state == "UNSUPPORTED"


def test_declaration_parser_rejects_unknown_kinds_selectors_and_fields() -> None:
    native = _load_native()
    ok = [{"kind": "GRANT_HEALING_BONUS", "target": "SELF", "amount": 1}]
    assert len(_parse_effect_steps(native, "X", ok)) == 1
    for bad in (
        [{"kind": "GRANT_HEALING_BONUS", "target": "SELF", "amount": 1, "scope": "ENEMY"}],
        [{"kind": "HEAL", "target": "ALL_FRIENDLY_MINIONS", "amount": 1}],
        [{"kind": "RESTORE", "target": "ALL_FRIENDLY_CHARACTERS", "amount": 1}],
        [{"kind": "HEAL", "target": "ALL_FRIENDLY_CHARACTERS"}],
    ):
        with pytest.raises(ValueError):
            _parse_effect_steps(native, "X", bad)


def test_cleansing_cleric_adds_two_to_an_existing_healing_card_and_persists_after_it_dies() -> None:
    # Turn 4: Cleric; turn 5: Flash Heal on our own hero. Plain Flash Heal restores 5, with the Cleric 5 + 2.
    plan = {1: 1, 2: 2, 3: 3, 4: 2}
    with_cleric = _session([CLERIC, FLASH, FILLER, FILLER], [SHOT] * 30)
    _to_player_one_turn(with_cleric, 4, plan)
    _play(with_cleric, CLERIC)
    assert with_cleric.observation("PLAYER1").self_player.active_effects == ()  # the bonus is not an invented active effect
    _end(with_cleric)
    for _ in range(plan[4]):
        _play(with_cleric, SHOT, hero=True, own=False)
    _end(with_cleric)
    before = _hero(with_cleric)
    assert before <= 20
    _play(with_cleric, FLASH, hero=True, own=True)
    assert _hero(with_cleric) == before + 7

    control = _session([FILLER, FLASH, FILLER, FILLER], [SHOT] * 30)
    _to_player_one_turn(control, 4, plan)
    _end(control)
    for _ in range(plan[4]):
        _play(control, SHOT, hero=True, own=False)
    _end(control)
    before_control = _hero(control)
    _play(control, FLASH, hero=True, own=True)
    assert _hero(control) == before_control + 5
    assert before == before_control  # the Cleric changed nothing except healing


def test_holy_nova_damages_enemy_minions_only_and_heals_every_friendly_character() -> None:
    session = _session([NOVA, FILLER, FILLER, FILLER], [SHOT] * 30)
    _to_player_one_turn(session, 3, {1: 1, 2: 2}, enemy_minion_turn=None)
    before = session.observation("PLAYER1")
    assert before.self_player.hero_health == 24 and before.opponent.hero_health == 30
    _play(session, NOVA)
    after = session.observation("PLAYER1")
    assert after.self_player.hero_health == 26
    assert after.opponent.hero_health == 30  # the enemy hero is not an "enemy minion"
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())


def test_greater_healing_potion_targets_only_friendly_characters_and_draws_afterwards() -> None:
    session = _session([POTION, FILLER, FILLER, FILLER], [JAWS] + [SHOT] * 29)
    _to_player_one_turn(session, 4, {1: 1, 2: 0, 3: 3}, enemy_minion_turn=2)
    hand_before = len(session.observation("PLAYER1").self_hand)
    assert any(entity.card.card_id == JAWS for entity in session.observation("PLAYER1").opponent.board)
    targets = {(a["target_is_hero"], a["target_is_self"]) for a in session.legal_actions() if a.get("card_id") == POTION}
    assert targets == {(True, True)}  # own hero only: neither the enemy hero nor the enemy minion is offered
    before = _hero(session)
    assert before == 22
    _play(session, POTION, hero=True, own=True)
    assert _hero(session) == 30  # 22 + 12 is capped by the hero maximum of 30
    assert len(session.observation("PLAYER1").self_hand) == hand_before  # -1 played, +1 drawn


def test_moonwell_area_heal_with_and_without_the_bonus() -> None:
    def moonwell_delta(with_cleric: bool) -> tuple[int, int, int]:
        deck = [CLERIC if with_cleric else FILLER, MOONWELL, FILLER, FILLER, FILLER, FILLER]
        session = _session(deck, [SHOT] * 30)
        plan = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2}
        _to_player_one_turn(session, 4, plan)
        if with_cleric:
            _play(session, CLERIC)
        _end(session)
        for _ in range(plan[4]):
            _play(session, SHOT, hero=True, own=False)
        _end(session)
        _end(session)  # first seat, turn 5
        for _ in range(plan[5]):
            _play(session, SHOT, hero=True, own=False)
        _end(session)
        before = session.observation("PLAYER1")
        assert before.self_player.hero_health <= 20 and before.opponent.hero_health == 30
        _play(session, MOONWELL)
        after = session.observation("PLAYER1")
        return after.self_player.hero_health - before.self_player.hero_health, before.opponent.hero_health - after.opponent.hero_health, len(after.self_player.board)

    assert moonwell_delta(False) == (4, 4, 0)
    assert moonwell_delta(True) == (6, 4, 1)


def test_cross_side_healing_with_a_bonus_is_classified_rule_unresolved_not_guessed() -> None:
    session = _session([CLERIC, FLASH, FILLER, FILLER], [SHOT] * 30)
    _to_player_one_turn(session, 4, {})
    _play(session, CLERIC)
    _end(session)
    _end(session)
    action = next(a for a in session.legal_actions() if a.get("card_id") == FLASH and a["target_is_hero"] and not a["target_is_self"])
    enemy_before = _hero(session, "PLAYER2")
    attempt = attempt_action(session, action)
    assert attempt.outcome == SimulationOutcome.UNSIMULATABLE and attempt.reason == AttemptReason.NATIVE_RULE_UNRESOLVED
    assert attempt.diagnostics is not None and attempt.diagnostics.native_failure.code == "HEALING_BONUS_SCOPE_UNREVIEWED"
    assert attempt.fallback_eligible
    assert _hero(session, "PLAYER2") == enemy_before and session.is_valid  # the parent is untouched
    with pytest.raises(UnsupportedSimulationError):
        session.apply_action(action)
    assert not session.is_valid and session.failure.code == "HEALING_BONUS_SCOPE_UNREVIEWED"


def test_healing_bonus_is_public_and_distinguishes_states() -> None:
    session = _session([CLERIC, FILLER, FILLER, FILLER], [FILLER] * 30)
    _to_player_one_turn(session, 4, {})
    before = session.observation("PLAYER1")
    assert before.self_player.healing_bonus == 0 and before.opponent.healing_bonus == 0  # exact simulator knowledge, not None
    _play(session, CLERIC)
    mine, theirs = session.observation("PLAYER1"), session.observation("PLAYER2")
    assert (mine.self_player.healing_bonus, mine.opponent.healing_bonus) == (2, 0)
    assert (theirs.self_player.healing_bonus, theirs.opponent.healing_bonus) == (0, 2)
    assert mine != before and mine.self_player.active_effects == ()  # no fabricated enchantment identity
    assert session.clone().observation("PLAYER1") == mine


def test_restore_to_full_uses_the_healing_pipeline_on_either_side_with_a_bonus() -> None:
    mend = "CATA_302"
    # Our Cleric at turn 4, then Mend on the opponent's undamaged Razorjaw at turn 5: valid (no healing packet needed).
    session = _session([CLERIC, mend, FILLER, FILLER], [JAWS] + [FILLER] * 29)
    _to_player_one_turn(session, 4, {}, enemy_minion_turn=2)
    _play(session, CLERIC)
    _end(session)
    _end(session)
    action = next(a for a in session.legal_actions() if a.get("card_id") == mend and a["target_card_id"] == JAWS)
    attempt = attempt_action(session, action)
    assert attempt.completed and attempt.child.is_valid
    child = attempt.state
    assert [entity.current_health for entity in child.opponent.board] == [1] and child.opponent.healing_bonus == 0
    assert child.self_player.healing_bonus == 2
