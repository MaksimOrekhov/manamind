"""OBSERVATION-EXTRACTION-1: hero maximum Health, hero Frozen state and Hero Power readiness.

Tag semantics asserted here were checked against real Power.log files (see
reports/observation_extraction1_20261008/README.md). Cases the real corpus does not contain are built from
synthetic logs and are marked as not verified against a real match.
"""
from __future__ import annotations

import copy
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from hearthstone.enums import CardType, GameTag, Zone

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from import_power_log import import_power_log  # noqa: E402
from live_fixtures import CANARIES, LiveLog, desc  # noqa: E402
from power_log_fixtures import build_game, to_text  # noqa: E402

from manamind.cards import CardCatalog  # noqa: E402
from manamind.domain import game_state_from_dict  # noqa: E402
from manamind.domain.game_state import PlayerObservation  # noqa: E402
from manamind.encoding import StateEncoder  # noqa: E402
from manamind.encoding.state_encoder import (  # noqa: E402
    GLOBAL_FEATURE_NAMES, PLAYER_NUMERIC_FEATURE_NAMES, STATE_ENCODING_SCHEMA_VERSION,
)
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.integrations.powerlog.visible_state import _player_observation  # noqa: E402
from manamind.live.session import LiveSession  # noqa: E402
from manamind.live.snapshot import Snapshot, state_hash, state_to_dict  # noqa: E402
from manamind.training.readiness import _validate_visible_state_shape  # noqa: E402
from manamind.training.real_policy import validate_example  # noqa: E402
from manamind.training.synthetic import load_labeled_dataset  # noqa: E402

CATALOG_PATH = ROOT / "data" / "cards" / "standard_current_enUS.json"
CATALOG = CardCatalog.from_json(CATALOG_PATH)
T = GameTag


# -- a log entity table without hslog: one side ------------------------------------------------------------------------


def side(hero=None, power=None, *, power_id="HERO_09bp", player=None, hero_card="HERO_09", is_self=True, extra=()):
    """PlayerObservation of one side. ``hero``/``power`` are tag dicts; None omits that entity."""
    owner = SimpleNamespace(tags={T.HERO_ENTITY: 4, **(player or {})})
    entities = []
    if hero is not None:
        entities.append(SimpleNamespace(id=4, controller=owner, zone=Zone.PLAY, type=CardType.HERO,
                                        card_id=hero_card, tags=dict(hero), revealed=True))
    if power is not None:
        entities.append(SimpleNamespace(id=40, controller=owner, zone=Zone.PLAY, type=CardType.HERO_POWER,
                                        card_id=power_id, tags=dict(power), revealed=True))
    entities.extend(extra)
    observation, _ = _player_observation(owner, entities, CATALOG, is_self=is_self)
    return observation


# -- 1. hero maximum Health --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tags,current,maximum", [
    ({T.HEALTH: 30, T.DAMAGE: 10}, 20, 30),   # damaged ordinary hero
    ({T.HEALTH: 30}, 30, 30),                  # undamaged: DAMAGE is simply not logged
    ({T.HEALTH: 40, T.DAMAGE: 5}, 35, 40),    # legitimate 40-Health hero, damaged
    ({T.HEALTH: 40}, 40, 40),
    ({T.HEALTH: 30, T.DAMAGE: 46}, 0, 30),    # overkill: current floors at 0, the maximum is not touched
])
def test_current_and_maximum_health_are_separate(tags, current, maximum):
    for is_self in (True, False):
        observation = side(tags, is_self=is_self)
        assert (observation.hero_health, observation.hero_max_health) == (current, maximum)


def test_maximum_health_tracks_the_log_not_the_hero_card_or_class():
    # The same hero card is 30 before and 40 after a mid-game change; the extractor only follows the tag.
    assert side({T.HEALTH: 30}, hero_card="HERO_09").hero_max_health == 30
    assert side({T.HEALTH: 40}, hero_card="HERO_09").hero_max_health == 40
    assert side({T.HEALTH: 12}, hero_card="HERO_01").hero_max_health == 12  # nothing forces 30 for any class


@pytest.mark.parametrize("hero", [None, {}, {T.DAMAGE: 3}, {T.HEALTH: 0}, {T.HEALTH: -5}, {T.HEALTH: True},
                                  {T.HEALTH: "30"}, {T.HEALTH: 30.0}])
def test_unobserved_or_impossible_maximum_health_is_none_never_a_default(hero):
    assert side(hero).hero_max_health is None  # not 30, not clamped to 1


@pytest.mark.parametrize("invalid", [0, -1, True, False, 1.5, 30.0, "30"])
def test_domain_rejects_invalid_maximum_health(invalid):
    with pytest.raises(ValueError, match="hero_max_health"):
        PlayerObservation(hero_health=1, hero_max_health=invalid)


def test_domain_rejects_current_health_above_maximum_instead_of_clamping():
    with pytest.raises(ValueError, match="cannot exceed"):
        PlayerObservation(hero_health=31, hero_max_health=30)
    assert PlayerObservation(hero_health=40, hero_max_health=40).hero_max_health == 40
    assert PlayerObservation(hero_health=0, hero_max_health=1).hero_max_health == 1
    assert PlayerObservation(hero_health=55).hero_max_health is None  # unknown stays unknown, no cross-check


# -- 2. hero Frozen -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("hero,expected", [
    ({T.HEALTH: 30, T.FROZEN: 1}, True),
    ({T.HEALTH: 30, T.FROZEN: 0}, False),      # the log wrote an explicit thaw
    ({T.HEALTH: 30}, None),                    # no tag: not evidence of False
    ({T.HEALTH: 30, T.FROZEN: 2}, None),       # not a boolean value
    ({T.HEALTH: 30, T.FROZEN: True}, None),
])
def test_hero_frozen_is_tri_state(hero, expected):
    for is_self in (True, False):
        observation = side(hero, is_self=is_self)
        assert observation.hero_frozen is expected
        assert observation.hero_freeze_turns_remaining is None  # the duration is never invented


def test_frozen_state_belongs_to_the_right_side():
    owner_self = SimpleNamespace(tags={T.HERO_ENTITY: 4})
    owner_opp = SimpleNamespace(tags={T.HERO_ENTITY: 5})
    entities = [
        SimpleNamespace(id=4, controller=owner_self, zone=Zone.PLAY, type=CardType.HERO, card_id="HERO_01",
                        tags={T.HEALTH: 30, T.FROZEN: 0}, revealed=True),
        SimpleNamespace(id=5, controller=owner_opp, zone=Zone.PLAY, type=CardType.HERO, card_id="HERO_08",
                        tags={T.HEALTH: 30, T.DAMAGE: 4, T.FROZEN: 1}, revealed=True),
    ]
    mine, _ = _player_observation(owner_self, entities, CATALOG, is_self=True)
    theirs, _ = _player_observation(owner_opp, entities, CATALOG, is_self=False)
    assert (mine.hero_frozen, theirs.hero_frozen) == (False, True)
    assert (mine.hero_health, theirs.hero_health) == (30, 26)


# -- 3. Hero Power readiness --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("power,expected", [
    ({T.EXHAUSTED: 0}, True),
    ({T.EXHAUSTED: 1}, False),
    ({}, None),                                                     # no tag: unknown, not "unused"
    ({T.EXHAUSTED: 0, T.HEROPOWER_ACTIVATIONS_THIS_TURN: 0}, True),
    ({T.EXHAUSTED: 1, T.HEROPOWER_ACTIVATIONS_THIS_TURN: 1}, False),
    ({T.EXHAUSTED: 0, T.HEROPOWER_ACTIVATIONS_THIS_TURN: 1}, None),  # sources disagree: unverified rule
    ({T.EXHAUSTED: 1, T.HEROPOWER_ACTIVATIONS_THIS_TURN: 0}, None),
    ({T.EXHAUSTED: 0, T.HEROPOWER_ACTIVATIONS_THIS_TURN: 2}, None),
    ({T.EXHAUSTED: 2}, None),
    ({T.EXHAUSTED: 1, T.HEROPOWER_ADDITIONAL_ACTIVATIONS: 1}, None),  # not in the real corpus: not verified
    ({T.EXHAUSTED: 0, T.HEROPOWER_UNLIMITED_USES: 1}, None),
    ({T.EXHAUSTED: 0, T.HERO_POWER_DISABLED: 1}, None),
    ({T.EXHAUSTED: 0, T.HERO_POWER_DISABLED: 0}, True),               # a modifier set to zero changes nothing
])
def test_hero_power_ready_is_tri_state(power, expected):
    for is_self in (True, False):
        assert side({T.HEALTH: 30}, power, is_self=is_self).hero_power_ready is expected


def test_player_level_modifiers_also_make_readiness_unknown():
    assert side({T.HEALTH: 30}, {T.EXHAUSTED: 0}, player={T.HEROPOWER_ADDITIONAL_ACTIVATIONS: 1}).hero_power_ready is None
    assert side({T.HEALTH: 30}, {T.EXHAUSTED: 0}, player={T.HEROPOWER_ACTIVATIONS_THIS_TURN: 0}).hero_power_ready is True


def test_readiness_is_exhausted_status_not_mana_or_cost():
    # Ready but unaffordable and exhausted-with-plenty-of-mana are both reported by the exhausted tag alone.
    broke = {T.RESOURCES: 3, T.RESOURCES_USED: 3}
    rich = {T.RESOURCES: 10}
    assert side({T.HEALTH: 30}, {T.EXHAUSTED: 0, T.COST: 2}, player=broke).hero_power_ready is True
    assert side({T.HEALTH: 30}, {T.EXHAUSTED: 1, T.COST: 2}, player=rich).hero_power_ready is False
    assert side({T.HEALTH: 30}, {T.COST: 1}, player=rich).hero_power_ready is None  # cost and mana are not evidence
    assert side({T.HEALTH: 30}, {T.EXHAUSTED: 0, T.COST: 2}, player=broke).available_mana == 0


def test_no_hero_power_is_unknown_and_the_class_supplies_nothing():
    observation = side({T.HEALTH: 30}, None, hero_card="HERO_09")
    assert observation.hero_power is None and observation.hero_power_ready is None


def test_two_live_powers_during_a_replacement_leave_readiness_unknown():
    # Not verified against a real match: the real corpus always shows exactly one power in play at block boundaries.
    owner = SimpleNamespace(tags={T.HERO_ENTITY: 4})
    hero = SimpleNamespace(id=4, controller=owner, zone=Zone.PLAY, type=CardType.HERO, card_id="HERO_09",
                           tags={T.HEALTH: 30}, revealed=True)
    old = SimpleNamespace(id=40, controller=owner, zone=Zone.PLAY, type=CardType.HERO_POWER, card_id="HERO_09bp",
                          tags={T.EXHAUSTED: 1}, revealed=True)
    new = SimpleNamespace(id=41, controller=owner, zone=Zone.PLAY, type=CardType.HERO_POWER, card_id="EDR_449p",
                          tags={T.EXHAUSTED: 0}, revealed=True)
    during, _ = _player_observation(owner, [hero, old, new], CATALOG, is_self=True)
    assert during.hero_power_ready is None
    after, _ = _player_observation(owner, [hero, replace_zone(old, Zone.SETASIDE), new], CATALOG, is_self=True)
    assert (after.hero_power.card_id, after.hero_power_ready) == ("EDR_449p", True)


def replace_zone(entity, zone):
    clone = copy.copy(entity)
    clone.zone = zone
    return clone


@pytest.mark.parametrize("power_id,exhausted,expected", [
    ("EDR_449p", 1, False),   # Imbued power: identity kept, only the exhausted flag is read
    ("EDR_449p", 0, True),
    ("HERO_09dbp", 0, True),  # a replacement / skin identity is never aliased to the base power
    ("HERO_09dbp", None, None),
    ("HERO_03bp", 1, False),  # not the class's own power: the class decides nothing
])
def test_changed_replaced_and_imbued_powers_keep_their_identity(power_id, exhausted, expected):
    tags = {} if exhausted is None else {T.EXHAUSTED: exhausted}
    observation = side({T.HEALTH: 30}, tags, power_id=power_id, hero_card="HERO_09")
    assert observation.hero_power.card_id == power_id
    assert observation.hero_power_ready is expected


# -- 4. serialization and hashes ----------------------------------------------------------------------------------------


def make_state(self_extra=None, opponent_extra=None):
    return game_state_from_dict({
        "turn_number": 4, "active_player": "SELF",
        "self_player": {"hero_health": 25, **(self_extra or {})},
        "opponent": {"hero_health": 30, **(opponent_extra or {})},
    })


def test_historical_dictionary_deserializes_to_none_never_to_thirty():
    state = make_state()
    assert state.self_player.hero_max_health is None and state.opponent.hero_max_health is None
    explicit_null = make_state({"hero_max_health": None})
    assert explicit_null.self_player.hero_max_health is None
    known = make_state({"hero_max_health": 40, "hero_health": 35}, {"hero_max_health": 30})
    assert (known.self_player.hero_max_health, known.opponent.hero_max_health) == (40, 30)


@pytest.mark.parametrize("invalid", [0, -3, True, 12.5, "40"])
def test_serialization_keeps_strict_validation(invalid):
    with pytest.raises(ValueError, match="hero_max_health"):
        make_state({"hero_max_health": invalid})
    with pytest.raises(ValueError, match="hero_max_health"):
        make_state(opponent_extra={"hero_max_health": invalid})


def test_canonical_round_trip_is_exact_for_old_and_new_forms():
    for state in (make_state(), make_state({"hero_max_health": 40, "hero_health": 40}, {"hero_max_health": 30})):
        data = state_to_dict(state)
        assert game_state_from_dict(data) == state
        assert state_to_dict(game_state_from_dict(data)) == data
        assert json.loads(json.dumps(data)) == data
        assert state_hash(data) == state_hash(copy.deepcopy(data))
    # asdict (used by older writers) keeps null and still loads to the same state.
    assert game_state_from_dict(asdict(make_state({"hero_max_health": 40, "hero_health": 40}))) == \
        make_state({"hero_max_health": 40, "hero_health": 40})
    assert game_state_from_dict(asdict(make_state())) == make_state()


def test_unknown_maximum_keeps_the_historical_dictionary_and_hash():
    unknown = state_to_dict(make_state())
    assert "hero_max_health" not in unknown["self_player"] and "hero_max_health" not in unknown["opponent"]
    # The pre-change canonical form is exactly this dictionary: same content, same hash.
    assert state_to_dict(game_state_from_dict(unknown)) == unknown
    known = state_to_dict(make_state({"hero_max_health": 30, "hero_health": 25}))
    assert known["self_player"]["hero_max_health"] == 30 and "hero_max_health" not in known["opponent"]
    assert state_hash(known) != state_hash(unknown)  # observing the maximum is a real change of the state


def test_visible_state_schema_check_accepts_old_and_new_player_dictionaries():
    _validate_visible_state_shape(state_to_dict(make_state()))
    _validate_visible_state_shape(state_to_dict(make_state({"hero_max_health": 40, "hero_health": 40})))
    smuggled = state_to_dict(make_state())
    smuggled["opponent"]["hero_max_health_source_entity"] = 5
    with pytest.raises(ValueError, match="outside its visible schema"):
        _validate_visible_state_shape(smuggled)


def test_encoder_features_and_schema_are_unchanged_by_the_maximum():
    assert STATE_ENCODING_SCHEMA_VERSION == 16
    assert not any("max_health" in name for name in PLAYER_NUMERIC_FEATURE_NAMES)
    assert len(GLOBAL_FEATURE_NAMES) == 3 + 2 * len(PLAYER_NUMERIC_FEATURE_NAMES) + 5
    encoder = StateEncoder(CardCatalog([]))
    assert encoder.global_feature_names == GLOBAL_FEATURE_NAMES
    base = encoder.encode(make_state())
    for maximum in (30, 40, 99):
        state = make_state()
        state = replace(state, self_player=replace(state.self_player, hero_max_health=maximum),
                        opponent=replace(state.opponent, hero_max_health=maximum))
        encoded = encoder.encode(state)
        assert (encoded.global_features == base.global_features).all()
        assert encoded.global_features.shape == base.global_features.shape


def test_policy_v2_hero_features_ignore_the_maximum():
    from manamind.models.policy_v2 import HERO_FEATURES
    assert not any("max_health" in name for name in HERO_FEATURES)


# -- end to end: offline importer ---------------------------------------------------------------------------------------


def add_tags(lines, entity_id, tags, *, after="tag=HEALTH value=30"):
    marker = next(i for i, line in enumerate(lines) if f"Creating ID={entity_id} " in line)
    insert = next(i for i in range(marker, len(lines)) if after in lines[i]) + 1
    prefix = lines[insert - 1].split("-", 1)[0] + "- "
    lines[insert:insert] = [f"{prefix}    tag={name} value={value}" for name, value in tags.items()]


def add_hero_power(lines, entity_id, controller, card_id, tags):
    marker = next(i for i, line in enumerate(lines) if "tag=STATE value=RUNNING" in line)
    prefix = lines[marker].split("-", 1)[0] + "- "
    body = [f"FULL_ENTITY - Creating ID={entity_id} CardID={card_id}", "    tag=CARDTYPE value=HERO_POWER",
            "    tag=ZONE value=PLAY", f"    tag=CONTROLLER value={controller}", f"    tag=ENTITY_ID value={entity_id}",
            *[f"    tag={name} value={value}" for name, value in tags.items()]]
    lines[marker:marker] = [prefix + text for text in body]


def import_states(tmp_path, lines):
    raw = tmp_path / "match.log"
    out = tmp_path / "out" / "match.jsonl"
    raw.write_text(to_text(lines), encoding="utf-8")
    import_power_log(raw, out, CATALOG_PATH)
    return [example.state for example in load_labeled_dataset(out)]


def test_offline_import_extracts_hero_state_for_both_perspectives(tmp_path):
    lines = build_game(seed=4101)
    add_tags(lines, 4, {"DAMAGE": 5, "FROZEN": 0})              # SELF: hero card is 30 Health; 40 below
    add_tags(lines, 5, {"FROZEN": 1})                           # OPPONENT frozen
    add_hero_power(lines, 40, 1, "HERO_09bp", {"EXHAUSTED": 1})
    add_hero_power(lines, 41, 2, "EDR_449p", {"EXHAUSTED": 0})
    states = import_states(tmp_path, lines)
    for state in states:
        assert (state.self_player.hero_health, state.self_player.hero_max_health) == (25, 30)
        assert (state.opponent.hero_health, state.opponent.hero_max_health) == (30, 30)
        assert (state.self_player.hero_frozen, state.opponent.hero_frozen) == (False, True)
        assert (state.self_player.hero_power_ready, state.opponent.hero_power_ready) == (False, True)
        assert (state.self_player.hero_power.card_id, state.opponent.hero_power.card_id) == ("HERO_09bp", "EDR_449p")
        assert state.self_player.hero_freeze_turns_remaining is None


def test_offline_import_handles_forty_health_and_missing_tags(tmp_path):
    lines = build_game(seed=4102)
    marker = next(i for i, line in enumerate(lines) if "Creating ID=4 " in line)
    health = next(i for i in range(marker, len(lines)) if "tag=HEALTH value=30" in lines[i])
    lines[health] = lines[health].replace("value=30", "value=40")
    add_tags(lines, 4, {"DAMAGE": 5}, after="tag=HEALTH value=40")
    states = import_states(tmp_path, lines)
    assert all((s.self_player.hero_health, s.self_player.hero_max_health) == (35, 40) for s in states)
    assert all(s.self_player.hero_frozen is None and s.opponent.hero_frozen is None for s in states)
    assert all(s.self_player.hero_power_ready is None and s.self_player.hero_power is None for s in states)


def test_offline_import_is_deterministic(tmp_path):
    first = import_states(tmp_path / "a", _prepare(tmp_path / "a", build_game(seed=4103)))
    second = import_states(tmp_path / "b", _prepare(tmp_path / "b", build_game(seed=4103)))
    assert [asdict(s) for s in first] == [asdict(s) for s in second]


def _prepare(path, lines):
    path.mkdir(parents=True, exist_ok=True)
    add_tags(lines, 4, {"DAMAGE": 3, "FROZEN": 1})
    add_hero_power(lines, 40, 1, "HERO_09bp", {"EXHAUSTED": 0})
    return lines


# -- end to end: live session -------------------------------------------------------------------------------------------


HERO_POWER_ID = "HERO_POWER_X"


def live_decision(error=None, *, drop_exhausted_tag=False, changes=(), canaries=False):
    """A SELF decision with the Hero Power (entity 40) offered with ``error`` (None omits the option)."""
    log = LiveLog(canaries=canaries).create_game().mulligan()
    if canaries:
        log.canary_reveals().opponent_hand_identity()
    if drop_exhausted_tag:
        log.lines = [line for line in log.lines if "tag=EXHAUSTED value=0" not in line]
    if changes:
        log.batch(list(changes))
        log.finish_list()
    log.self_decision(1)
    if error is not None:
        log.raw("GameState", "DebugPrintOptions",
                f"option 4 type=POWER mainEntity={desc(40, 'PLAY', 0, HERO_POWER_ID, 1)} error={error} errorParam=")
    return log


def live_snapshot(log):
    session = LiveSession(CATALOG)
    events = session.feed(log.lines, 1000) + session.tick(1150)
    snapshots = [event for event in events if isinstance(event, Snapshot)]
    assert len(snapshots) == 1
    return snapshots[0]


@pytest.mark.parametrize("error,tag_present,expected", [
    ("NONE", True, True),                         # tag EXHAUSTED=0 and a validated option
    ("NONE", False, True),                        # tag missing, the server validated the power: not exhausted
    ("REQ_NOT_EXHAUSTED_HERO_POWER", False, False),  # tag missing, the server says it is exhausted
    ("REQ_ENOUGH_MANA", False, None),             # unaffordable says nothing about exhaustion
    ("REQ_ENOUGH_MANA", True, True),              # the explicit tag still decides
    ("REQ_HAND_NOT_FULL", False, None),
    ("REQ_YOUR_TURN", False, None),
    (None, False, None),                          # no option for the power, no tag
    (None, True, True),
])
def test_live_hero_power_readiness_uses_only_explicit_evidence(error, tag_present, expected):
    snapshot = live_snapshot(live_decision(error, drop_exhausted_tag=not tag_present))
    assert snapshot.state["self_player"]["hero_power_ready"] is expected
    assert snapshot.state["self_player"]["hero_power"]["card_id"] == HERO_POWER_ID


def test_live_conflicting_tag_and_option_make_readiness_unknown():
    exhausted = ["TAG_CHANGE Entity=40 tag=EXHAUSTED value=1"]
    assert live_snapshot(live_decision("NONE", changes=exhausted)).state["self_player"]["hero_power_ready"] is None
    refused = live_decision("REQ_NOT_EXHAUSTED_HERO_POWER")  # tag says EXHAUSTED=0
    assert live_snapshot(refused).state["self_player"]["hero_power_ready"] is None
    agree = live_decision("REQ_NOT_EXHAUSTED_HERO_POWER", changes=exhausted)
    assert live_snapshot(agree).state["self_player"]["hero_power_ready"] is False


def test_live_options_never_touch_the_opponent_power_or_other_entities():
    snapshot = live_snapshot(live_decision("NONE"))
    assert snapshot.state["opponent"]["hero_power_ready"] is None  # no power in the fixture; nothing is invented
    other = LiveLog().create_game().mulligan().self_decision(1)  # the option of a hand card is not a Hero Power
    assert live_snapshot(other).state["self_player"]["hero_power_ready"] is True  # from the EXHAUSTED=0 tag only


def test_live_hero_state_comes_through_the_snapshot_for_both_sides():
    changes = ["TAG_CHANGE Entity=4 tag=FROZEN value=1", "TAG_CHANGE Entity=4 tag=DAMAGE value=7",
               "TAG_CHANGE Entity=5 tag=HEALTH value=40", "TAG_CHANGE Entity=5 tag=DAMAGE value=2",
               "TAG_CHANGE Entity=5 tag=FROZEN value=0"]
    state = live_snapshot(live_decision("NONE", changes=changes)).state
    assert (state["self_player"]["hero_health"], state["self_player"]["hero_max_health"]) == (23, 30)
    assert (state["opponent"]["hero_health"], state["opponent"]["hero_max_health"]) == (38, 40)
    assert (state["self_player"]["hero_frozen"], state["opponent"]["hero_frozen"]) == (True, False)
    assert state["self_player"]["hero_freeze_turns_remaining"] is None
    assert game_state_from_dict(state).opponent.hero_max_health == 40


def test_live_snapshot_is_deterministic_and_hash_matches_its_state():
    first, second = live_snapshot(live_decision("NONE")), live_snapshot(live_decision("NONE"))
    assert first.to_json() == second.to_json()
    assert first.state_hash == state_hash(first.state) == second.state_hash


def test_live_privacy_boundary_holds_with_the_new_fields():
    log = live_decision("NONE", canaries=True)
    session = LiveSession(CATALOG)
    events = session.feed(log.lines, 1000) + session.tick(1150)
    text = "".join(event.to_json() for event in events if isinstance(event, Snapshot))
    assert text and not any(canary in text for canary in CANARIES)
    state = live_snapshot(live_decision("NONE")).state
    assert "entity" not in json.dumps(state).lower().replace("hero_power", "")  # no entity handles in the state


# -- historical datasets stay valid -------------------------------------------------------------------------------------


def policy_log():
    log = LiveLog().create_game().mulligan()
    log.begin_turn(1)
    log.raw("GameState", "DebugPrintOptions", "id=1")
    log.raw("GameState", "DebugPrintOptions", "option 0 type=END_TURN mainEntity= error=INVALID errorParam=")
    log.raw("GameState", "DebugPrintOptions",
            f"option 1 type=POWER mainEntity={desc(40, 'PLAY', 0, HERO_POWER_ID, 1)} error=NONE errorParam=")
    log.raw("GameState", "SendOption", "selectedOption=1 selectedSubOption=-1 selectedTarget=0 selectedPosition=0")
    log.p(f"BLOCK_START BlockType=PLAY Entity={desc(40, 'PLAY', 0, HERO_POWER_ID, 1)} "
          "EffectCardId= EffectIndex=0 Target=0 SubOption=-1")
    log.p("BLOCK_END")
    log.p("TAG_CHANGE Entity=2 tag=PLAYSTATE value=WON")
    log.p("TAG_CHANGE Entity=3 tag=PLAYSTATE value=LOST")
    log.complete()
    return log


def test_new_policy_rows_validate_and_carry_the_observed_values():
    rows, _ = extract_match(policy_log().lines, CATALOG)
    row = rows[0]
    validate_example(row)
    assert row["state"]["self_player"]["hero_max_health"] == 30
    assert row["state"]["opponent"]["hero_max_health"] == 30
    assert row["state"]["self_player"]["hero_power_ready"] is True


def test_historical_policy_row_without_the_field_still_validates():
    row = copy.deepcopy(extract_match(policy_log().lines, CATALOG)[0][0])
    for side_name in ("self_player", "opponent"):
        row["state"][side_name].pop("hero_max_health")
    row["provenance"]["state_hash"] = state_hash(row["state"])  # what the pre-change code stored for such a state
    validate_example(row)
    state = game_state_from_dict(row["state"])
    assert state.self_player.hero_max_health is None
    tampered = copy.deepcopy(row)
    tampered["state"]["self_player"]["hero_max_health"] = None  # an explicit null is not the canonical form
    tampered["provenance"]["state_hash"] = state_hash(tampered["state"])
    with pytest.raises(ValueError, match="noncanonical"):
        validate_example(tampered)
