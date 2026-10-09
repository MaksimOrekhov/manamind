"""ENGINE-GATE-0: multi-class base Hero Power support through the real catalog and the Python session.

Expectations come from the printed Hero Power texts (Fireblast 1 damage, Lesser Heal restore 2, Steady Shot 2 damage to
the enemy hero, Armor Up! gain 2 Armor), the 2-Mana cost and the once-per-turn rule, never from running a declaration.
Class is not proof of the current Hero Power: the native session stores the power identity (see hero_power_tests.hpp).
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import pytest

from manamind.cards.catalog import CardCatalog
from manamind.cards.vocabulary import CardVocabulary
from manamind.encoding import StateEncoder
from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION
from manamind.integrations.manaengine import ManaEngineSession, UnsupportedSimulationError
from manamind.integrations.manaengine.engine import FailureKind, _definition_rows, _load_native
from manamind.models.policy import encode_legal_actions
from manamind.models.policy import ACTION_FEATURE_NAMES

ROOT = Path(__file__).resolve().parents[3]
FILLER = "CORE_EX1_145"
SHOT = "CORE_DS1_185"  # Arcane Shot: deal 2 damage
CLERIC = "CATA_216"
POWERS = {"MAGE": "HERO_08bp", "PRIEST": "HERO_09bp", "HUNTER": "HERO_05bp", "WARRIOR": "HERO_01bp"}
CLASSES = tuple(POWERS)


def _session(first: str, second: str, deck1: list[str] | None = None, deck2: list[str] | None = None) -> ManaEngineSession:
    pad = lambda cards: [*cards, *([FILLER] * (30 - len(cards)))]  # noqa: E731
    return ManaEngineSession(pad(deck1 or []), pad(deck2 or []), player1_class=first, player2_class=second, shuffle=False)


def _end(session: ManaEngineSession) -> None:
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))


def _powers(session: ManaEngineSession) -> list[dict]:
    return [a for a in session.legal_actions() if a["type"] == "HERO_POWER"]


def _to_turn(session: ManaEngineSession, turn: int) -> None:
    """Pass until the first seat's `turn`-th turn (two END_TURN per round)."""
    for _ in range(turn - 1):
        _end(session)
        _end(session)


def _health(session: ManaEngineSession, seat: str) -> int:
    return session.observation(seat).self_player.hero_health


def test_base_hero_power_definitions_are_reviewed_traceable_and_not_standard_collectibles() -> None:
    rows = {row.card_id: row for row in _definition_rows()}
    for player_class, card_id in POWERS.items():
        row = rows[card_id]
        assert (row.card_type, row.card_class, row.cost) == ("HERO_POWER", player_class, 2)
        assert row.support_state == "SUPPORTED" and row.rules_contract_reviewed and not row.collectible
        assert row.ability == "EFFECT_COMPOSITION" and len(row.effects) == 1
    native = _load_native()
    step = lambda card_id: (rows[card_id].effects[0].kind, rows[card_id].effects[0].target, rows[card_id].effects[0].amount)  # noqa: E731
    assert step("HERO_08bp") == (native.EffectKind.DAMAGE, native.TargetSelector.EXPLICIT_CHARACTER, 1)
    assert step("HERO_09bp") == (native.EffectKind.HEAL, native.TargetSelector.EXPLICIT_CHARACTER, 2)
    assert step("HERO_05bp") == (native.EffectKind.DAMAGE, native.TargetSelector.ENEMY_HERO, 2)
    assert step("HERO_01bp") == (native.EffectKind.GAIN_ARMOR, native.TargetSelector.SELF, 2)
    # Replacement/skin variants and the other classes' powers have no reviewed mechanics and stay unsupported.
    for card_id in ("HERO_01dbp", "HERO_05dbp", "HERO_09dbp", "HERO_08aabp", "HERO_07bp", "HERO_06bp"):
        assert card_id not in rows or rows[card_id].support_state == "UNSUPPORTED"
    # Provenance: the new metadata file carries rows copied from the capture the project already pins for dependencies.
    data = ROOT / "experiments/manaengine/data"
    new = json.loads((data / "hero_power_dependency_metadata.json").read_text(encoding="utf-8"))
    audit = json.loads((data / "dependency_metadata_audit.json").read_text(encoding="utf-8"))
    assert new["source_sha256"] == audit["source_sha256"] and new["source_url"] == audit["source_url"]
    assert sorted(row["id"] for row in new["cards"]) == ["HERO_01bp", "HERO_05bp", "HERO_09bp"]
    assert all(row["type"] == "HERO_POWER" and row["cost"] == 2 for row in [*new["cards"], next(r for r in audit["cards"] if r["id"] == "HERO_08bp")])
    # The collectible Standard pool is untouched: none of these ids is a collectible Standard row.
    snapshot = ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
    collectible_ids = {row["id"] for row in json.loads(snapshot.read_text(encoding="utf-8"))}
    assert not set(POWERS.values()) & collectible_ids
    registry = (ROOT / "data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8")
    assert not any(f'"{card_id}"' in registry for card_id in POWERS.values())
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest()  # snapshot is present and readable


@pytest.mark.parametrize(("first", "second"), list(itertools.product(CLASSES, CLASSES)))
def test_supported_pairings_export_their_own_power_from_both_perspectives(first: str, second: str) -> None:
    session = _session(first, second)
    p1, p2 = session.observation("PLAYER1"), session.observation("PLAYER2")
    assert p1.self_player.hero_power.card_id == POWERS[first] == p2.opponent.hero_power.card_id
    assert p2.self_player.hero_power.card_id == POWERS[second] == p1.opponent.hero_power.card_id
    for power in (p1.self_player.hero_power, p1.opponent.hero_power):
        assert power.card_type == "HERO_POWER" and power.cost == 2 and power.current_cost == 2
    assert p1.self_player.hero_power_ready is p1.opponent.hero_power_ready is p2.self_player.hero_power_ready is True
    assert p1.self_player.player_class == first and p1.opponent.player_class == second
    # Hidden-information boundary: the hero-power export adds no opponent hand/deck identity.
    assert p1.opponent_known_cards == () and p1.opponent.hand_size > 0


@pytest.mark.parametrize("bad", ["WARLOCK", "SHAMAN", "DRUID", "UNKNOWN_CLASS", "NEUTRAL", ""])
def test_unknown_or_unsupported_classes_are_rejected_with_a_typed_failure(bad: str) -> None:
    for first, second in ((bad, "MAGE"), ("PRIEST", bad)):
        with pytest.raises(UnsupportedSimulationError, match="hero powers") as caught:
            _session(first, second)
        failure = caught.value.failure
        assert failure is not None and failure.kind == FailureKind.UNSUPPORTED and failure.code == "UNSUPPORTED_HERO_CLASS"
    with pytest.raises(UnsupportedSimulationError):
        _session("PRIEST", "WARLOCK")  # a supported seat never legitimises an unsupported one


def test_native_rejects_an_unreviewed_current_power_instead_of_using_the_base_power() -> None:
    native = _load_native()
    assert native.FailureCode.UNSUPPORTED_HERO_POWER is not None
    wanted = {*POWERS.values(), FILLER}
    rows = [row for row in _definition_rows() if row.card_id in wanted]
    assert {row.card_id for row in rows} == wanted
    for row in rows:
        if row.card_id == "HERO_09bp":
            row.support_state = "UNSUPPORTED"
    catalog = native.CardCatalog(rows)
    deck = [FILLER] * 30
    with pytest.raises(native.UnsupportedSimulationError) as caught:
        native.GameSession(deck, deck, catalog, 0, False, "PRIEST", "MAGE")
    assert caught.value.code == "UNSUPPORTED_HERO_POWER" and caught.value.kind == "UNSUPPORTED"
    native.GameSession(deck, deck, catalog, 0, False, "MAGE", "WARRIOR")  # the unaffected reviewed pairs still start


def test_hunter_and_warrior_actions_are_untargeted_and_round_trip_through_the_session() -> None:
    session = _session("HUNTER", "WARRIOR")
    _to_turn(session, 2)
    (action,) = _powers(session)
    assert "target_entity_id" not in action and action["card_id"] == "HERO_05bp" and action["card_cost"] == 2
    assert action["card_type"] == "HERO_POWER" and action["target_is_hero"] is False and action["target_card_id"] == ""
    state = session.apply_action(action)  # the dict form returned by legal_actions() is accepted verbatim
    assert state.self_player.available_mana == 0 and state.self_player.hero_power_ready is False
    assert _health(session, "PLAYER2") == 28 and _health(session, "PLAYER1") == 30
    assert _powers(session) == []
    _end(session)
    (armor,) = _powers(session)
    assert "target_entity_id" not in armor and armor["card_id"] == "HERO_01bp"
    after = session.apply_action(armor)
    assert after.self_player.armor == 2 and after.self_player.hero_health == 28 and after.self_player.available_mana == 0
    assert session.observation("PLAYER1").opponent.armor == 2 and session.observation("PLAYER1").opponent.hero_health == 28


def _fireblast_enemy_hero(session: ManaEngineSession) -> None:
    session.apply_action(next(a for a in _powers(session) if a["target_is_hero"] and not a["target_is_self"]))


def test_priest_targets_every_character_and_heals_exactly_two() -> None:
    session = _session("PRIEST", "MAGE")
    for turn in range(1, 5):  # the Mage seat fireblasts the Priest hero on its turns 2..4: 30 -> 27
        _end(session)
        if turn >= 2:
            _fireblast_enemy_hero(session)
        _end(session)
    assert _health(session, "PLAYER1") == 27
    actions = _powers(session)
    assert {(a["target_is_hero"], a["target_is_self"]) for a in actions} == {(True, True), (True, False)}  # no minions yet
    assert all(a["card_id"] == "HERO_09bp" and a["card_cost"] == 2 and "target_entity_id" in a for a in actions)
    enemy = session.clone()
    heal_enemy = next(a for a in _powers(enemy) if not a["target_is_self"])
    enemy.apply_action(heal_enemy)  # an enemy hero at full Health: permitted, nothing to restore
    assert _health(enemy, "PLAYER2") == 30 and _health(enemy, "PLAYER1") == 27
    assert enemy.observation("PLAYER1").self_player.available_mana == 3 and _powers(enemy) == []
    state = session.apply_action(next(a for a in actions if a["target_is_self"]))
    assert state.self_player.hero_health == 29 and state.self_player.armor == 0 and state.self_player.available_mana == 3
    assert _health(session, "PLAYER2") == 30


def test_priest_healing_bonus_reaches_lesser_heal_and_cross_side_bonus_fails_closed() -> None:
    def own_heal_after(deck: list[str]) -> int:
        session = _session("PRIEST", "MAGE", deck)
        for turn in range(1, 6):  # the Mage seat fireblasts the Priest hero on its turns 2..5: 30 -> 26
            if turn == 4 and CLERIC in deck:
                session.apply_action(next(a for a in session.legal_actions() if a["type"] == "PLAY_CARD" and a["card_id"] == CLERIC))
            _end(session)
            if turn >= 2:
                _fireblast_enemy_hero(session)
            _end(session)
        before = _health(session, "PLAYER1")
        assert before == 26
        own = next(a for a in _powers(session) if a["target_is_hero"] and a["target_is_self"])
        session.apply_action(own)
        return _health(session, "PLAYER1") - before

    assert own_heal_after([FILLER] * 4) == 2
    assert own_heal_after([CLERIC, FILLER, FILLER, FILLER]) == 4  # Restore #2 + the Cleric's 2, through the shared pipeline

    session = _session("PRIEST", "MAGE", [CLERIC, FILLER, FILLER, FILLER], [FILLER] * 30)
    _to_turn(session, 6)
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "PLAY_CARD" and a["card_id"] == CLERIC))
    enemy = next(a for a in _powers(session) if a["target_is_hero"] and not a["target_is_self"])
    with pytest.raises(UnsupportedSimulationError) as caught:
        session.apply_action(enemy)
    assert caught.value.failure is not None and caught.value.failure.code == "HEALING_BONUS_SCOPE_UNREVIEWED"
    assert not session.is_valid and session.failure.code == "HEALING_BONUS_SCOPE_UNREVIEWED"


def test_mage_mirror_behaviour_is_unchanged() -> None:
    session = _session("MAGE", "MAGE")
    _to_turn(session, 2)
    actions = _powers(session)
    assert {(a["target_is_hero"], a["target_is_self"]) for a in actions} == {(True, True), (True, False)}
    assert all("target_entity_id" in a and a["card_id"] == "HERO_08bp" for a in actions)
    session.apply_action(next(a for a in actions if not a["target_is_self"]))
    assert _health(session, "PLAYER2") == 29 and _health(session, "PLAYER1") == 30
    assert _powers(session) == []


def test_clone_independence_and_turn_boundary_for_every_class() -> None:
    for player_class in CLASSES:
        session = _session(player_class, "MAGE")
        _to_turn(session, 2)
        clone = session.clone()
        session.apply_action(_powers(session)[0])
        assert _powers(session) == [] and len(_powers(clone)) >= 1
        assert clone.observation("PLAYER1").self_player.hero_power_ready is True
        assert session.observation("PLAYER1").self_player.hero_power_ready is False
        _end(session)
        assert session.observation("PLAYER2").opponent.hero_power_ready is False  # exhausted while the opponent plays
        _end(session)
        assert len(_powers(session)) >= 1 and session.observation("PLAYER1").self_player.hero_power_ready is True


def test_training_eligibility_and_canonical_admission_are_unchanged() -> None:
    session = _session("PRIEST", "HUNTER")
    assert session.training_eligible is False
    with pytest.raises(UnsupportedSimulationError, match="backend-specific"):
        session.require_training_admission()
    # Unsupported cards still invalidate the branch: a Priest session does not relax the unsupported-card-in-hand gate.
    with pytest.raises(UnsupportedSimulationError):
        _session("PRIEST", "MAGE", ["CORE_BAR_310"]).legal_actions()


def test_policy_value_encoders_and_checkpoint_schema_are_unaffected_by_new_power_identities() -> None:
    catalog = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")
    encoder = StateEncoder(catalog)
    vocabulary = CardVocabulary(catalog)
    # The vocabulary (and therefore every trained checkpoint index) is built from the Standard catalog only.
    unknown = vocabulary.card_id("DOES_NOT_EXIST")
    assert all(vocabulary.card_id(card_id) == unknown for card_id in POWERS.values())
    assert STATE_ENCODING_SCHEMA_VERSION == 16
    reference = None
    for player_class in CLASSES:
        session = _session(player_class, "MAGE")
        _to_turn(session, 2)
        state = session.observation("PLAYER1")
        encoded = encoder.encode(state)
        assert encoded.global_features.shape[0] > 0
        if reference is None:
            reference = encoded.global_features.shape
        assert encoded.global_features.shape == reference
        assert int(encoded.self_hero_power.card_ids[0]) == unknown
        actions = session.legal_actions()
        matrix = encode_legal_actions(actions)
        assert matrix.shape[0] == len(actions) and matrix.shape[1] == len(ACTION_FEATURE_NAMES)
