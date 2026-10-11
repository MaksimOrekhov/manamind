"""OBSERVATION-EXT-1a: SELF facts read from the live entity table (history coverage, privacy, side-channel isolation)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import live_fixtures  # noqa: E402
from hearthstone.enums import GameTag  # noqa: E402
from live_fixtures import CANARY_OPP_HAND, LiveLog  # noqa: E402

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.domain.card import CardFeatures  # noqa: E402
from manamind.integrations.powerlog.lines import split_games  # noqa: E402
from manamind.integrations.powerlog.observed_facts import (  # noqa: E402
    COMPLETE, KEYWORD_TAGS, PARTIAL_DUMP, RESET, SPELL_DAMAGE_NONE_SEEN, SPELL_DAMAGE_PRESENT, SPELL_DAMAGE_UNKNOWN,
    ObservationHistory, ObservedFacts, extract_observed_facts,
)
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.live.session import LiveSession  # noqa: E402
from manamind.live.snapshot import Snapshot, state_hash  # noqa: E402
from manamind.outcome.world import BODY_FLAGS  # noqa: E402

CATALOG = CardCatalog.from_json(ROOT / "data" / "cards" / "standard_current_enUS.json")
SANCTUM_EFFECT = ["FULL_ENTITY - Creating ID=70 CardID=CATA_301e", "    tag=ZONE value=PLAY",
                  "    tag=CONTROLLER value=1", "    tag=CARDTYPE value=ENCHANTMENT", "    tag=ATTACHED value=2",
                  "    tag=ENTITY_ID value=70"]


def decide(extra=(), *, turn_in_header: int | None = None, catalog: CardCatalog = CATALOG, log: LiveLog | None = None):
    """A real LiveSession over a synthetic log; returns (session, the single emitted snapshot)."""
    log = log or LiveLog(turn_in_header=turn_in_header).create_game().mulligan()
    if extra:
        log.batch(list(extra)).finish_list()
    log.self_decision(turn_in_header or 1)
    session = LiveSession(catalog)
    events = session.feed(log.lines, 1000) + session.tick(1150)
    snapshots = [event for event in events if isinstance(event, Snapshot)]
    assert len(snapshots) == 1
    return session, snapshots[0]


def facts(extra=(), **kwargs) -> ObservedFacts:
    snapshot = decide(extra, **kwargs)[1]
    assert snapshot.observed is not None
    return snapshot.observed


# ----- history coverage: when may an unset tag be read as zero ---------------------------------------------------

def test_a_game_followed_from_its_start_reads_unset_tags_as_zero():
    found = facts()
    assert found.coverage == COMPLETE and found.unknown == {}
    assert found.self_hero_divine_shield is False and found.opponent_hero_divine_shield is False
    assert found.healing_does_damage is False and found.healing_bonus == 0
    assert found.spell_healing_doubled is False and found.all_healing_doubled is False
    assert found.spell_damage_doubled is False
    assert (found.spell_damage_status, found.spell_damage) == (SPELL_DAMAGE_NONE_SEEN, 0)
    assert [(card.card_id, card.keywords) for card in found.hand] == [
        ("CS2_029", ()), ("CS2_023", ()), ("CS2_024", ())]


def test_a_reconnect_dump_keeps_logged_values_but_never_reads_an_unset_tag_as_zero():
    extra = ["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=2", "TAG_CHANGE Entity=6 tag=TAUNT value=1"]
    found = facts(extra, turn_in_header=3)
    assert found.coverage == PARTIAL_DUMP
    assert found.healing_bonus == 2                       # a logged value is a fact
    assert found.self_hero_divine_shield is None and found.opponent_hero_divine_shield is None
    assert found.healing_does_damage is None and found.spell_healing_doubled is None
    assert found.spell_damage_doubled is None and found.all_healing_doubled is None
    assert (found.spell_damage_status, found.spell_damage) == (SPELL_DAMAGE_UNKNOWN, None)
    assert [card.keywords for card in found.hand] == [None, None, None]     # the card ids stay, the keywords do not
    assert found.unknown["healing_does_damage"] == "HISTORY_PARTIAL" and found.unknown["hand_keywords"] == "HISTORY_PARTIAL"
    assert "healing_bonus" not in found.unknown


def test_a_logged_zero_is_a_fact_even_in_a_reconnect_dump():
    extra = ["TAG_CHANGE Entity=4 tag=DIVINE_SHIELD value=0", "TAG_CHANGE Entity=5 tag=DIVINE_SHIELD value=1",
             "TAG_CHANGE Entity=2 tag=SPELLPOWER_DOUBLE value=0"]
    found = facts(extra, turn_in_header=3)
    assert (found.self_hero_divine_shield, found.opponent_hero_divine_shield) == (False, True)
    assert found.spell_damage_doubled is False


def test_a_rewind_invalidates_everything_even_positively_logged_values():
    log = LiveLog().create_game().mulligan()
    log.batch(["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=2", "TAG_CHANGE Entity=5 tag=DIVINE_SHIELD value=1"])
    log.finish_list()
    log.batch(["BLOCK_START BlockType=GAME_RESET Entity=GameEntity EffectCardId= EffectIndex=0 Target=0 SubOption=-1",
               "BLOCK_END"]).finish_list()
    found = decide(log=log)[1].observed
    assert found.coverage == RESET
    assert found.healing_bonus is None and found.opponent_hero_divine_shield is None
    assert found.self_hero_divine_shield is None and found.healing_does_damage is None
    assert found.spell_damage_status == SPELL_DAMAGE_UNKNOWN and all(card.keywords is None for card in found.hand)
    assert set(found.unknown.values()) == {"HISTORY_RESET"}


def test_a_session_attached_mid_game_replays_the_whole_section_and_keeps_the_complete_history():
    log = LiveLog().create_game().mulligan()
    log.batch(["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=4"]).finish_list()
    log.self_decision(1)
    session = LiveSession(CATALOG)
    events = session.feed(log.lines, 1000, catchup=True) + session.tick(1150)       # the overlay starts late
    snapshots = [e for e in events if isinstance(e, Snapshot)]
    assert len(snapshots) == 1                                  # only the current, settled decision is emitted
    assert snapshots[0].observed.coverage == COMPLETE and snapshots[0].observed.healing_bonus == 4
    assert snapshots[0].observed.healing_does_damage is False   # an unset flag is zero: the section started at turn 0


def test_chunked_and_one_shot_feeding_give_identical_facts():
    log = LiveLog().create_game().mulligan()
    log.batch(["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=2"]).finish_list()
    log.self_decision(1)
    whole = LiveSession(CATALOG)
    one = [e for e in whole.feed(log.lines, 1000) + whole.tick(1150) if isinstance(e, Snapshot)][0]
    chunked = LiveSession(CATALOG)
    events = []
    for index in range(0, len(log.lines), 7):
        events += chunked.feed(log.lines[index:index + 7], 1000 + index)
    events += chunked.tick(5000)
    assert [e for e in events if isinstance(e, Snapshot)][0].observed == one.observed


# ----- what each fact reads ------------------------------------------------------------------------------------

def test_ruby_sanctum_is_active_while_its_effect_lasts_even_after_the_location_has_left_the_board():
    location = ["FULL_ENTITY - Creating ID=71 CardID=CATA_301", "    tag=ZONE value=PLAY", "    tag=CONTROLLER value=1",
                "    tag=CARDTYPE value=LOCATION", "    tag=ENTITY_ID value=71"]
    flag = ["TAG_CHANGE Entity=2 tag=HEALING_DOES_DAMAGE value=1"]
    assert facts(location + SANCTUM_EFFECT + flag).healing_does_damage is True
    gone = ["TAG_CHANGE Entity=71 tag=ZONE value=GRAVEYARD"]
    assert facts(location + SANCTUM_EFFECT + flag + gone).healing_does_damage is True
    spent = ["TAG_CHANGE Entity=2 tag=HEALING_DOES_DAMAGE value=0", "TAG_CHANGE Entity=70 tag=ZONE value=GRAVEYARD"]
    assert facts(location + SANCTUM_EFFECT + flag + gone + spent).healing_does_damage is False


def test_a_flag_without_its_effect_or_an_effect_without_the_flag_is_unknown_not_a_guess():
    flag = facts(["TAG_CHANGE Entity=2 tag=HEALING_DOES_DAMAGE value=1"])
    assert flag.healing_does_damage is None and flag.unknown["healing_does_damage"] == "FLAG_EFFECT_DISAGREE"
    effect = facts(SANCTUM_EFFECT)
    assert effect.healing_does_damage is None and effect.unknown["healing_does_damage"] == "FLAG_EFFECT_DISAGREE"


def test_healing_bonus_and_both_doubling_flags_come_from_the_player_tags():
    found = facts(["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=6",
                   "TAG_CHANGE Entity=2 tag=SPELL_HEALING_DOUBLE value=1",
                   "TAG_CHANGE Entity=2 tag=SPELLPOWER_DOUBLE value=1"])
    assert (found.healing_bonus, found.spell_healing_doubled, found.all_healing_doubled) == (6, True, False)
    assert found.spell_damage_doubled is True
    assert facts(["TAG_CHANGE Entity=2 tag=ALL_HEALING_DOUBLE value=1"]).all_healing_doubled is True


def test_a_flag_with_a_value_other_than_zero_or_one_is_not_interpreted():
    found = facts(["TAG_CHANGE Entity=2 tag=SPELLPOWER_DOUBLE value=2"])
    assert found.spell_damage_doubled is None and found.unknown["spell_damage_doubled"] == "UNEXPECTED_VALUE"


def test_both_heroes_divine_shield_comes_from_their_own_public_tag():
    found = facts(["TAG_CHANGE Entity=5 tag=DIVINE_SHIELD value=1"])
    assert (found.self_hero_divine_shield, found.opponent_hero_divine_shield) == (False, True)
    found = facts(["TAG_CHANGE Entity=4 tag=DIVINE_SHIELD value=1", "TAG_CHANGE Entity=5 tag=DIVINE_SHIELD value=1",
                   "TAG_CHANGE Entity=5 tag=DIVINE_SHIELD value=0"])
    assert (found.self_hero_divine_shield, found.opponent_hero_divine_shield) == (True, False)


def test_spell_damage_zero_needs_the_whole_history_and_every_source_to_be_silent():
    assert facts().spell_damage_status == SPELL_DAMAGE_NONE_SEEN
    minion = facts(["TAG_CHANGE Entity=41 tag=SPELLPOWER value=2"])
    assert (minion.spell_damage_status, minion.spell_damage) == (SPELL_DAMAGE_PRESENT, 2)
    player = facts(["TAG_CHANGE Entity=2 tag=CURRENT_SPELLPOWER value=1"])
    assert (player.spell_damage_status, player.spell_damage) == (SPELL_DAMAGE_PRESENT, 1)
    silenced = facts(["TAG_CHANGE Entity=41 tag=SPELLPOWER value=0"])
    assert silenced.spell_damage_status == SPELL_DAMAGE_NONE_SEEN
    # an opponent's Spell Damage does not change SELF's
    opponent = facts(["TAG_CHANGE Entity=50 tag=SPELLPOWER value=3"])
    assert opponent.spell_damage_status == SPELL_DAMAGE_NONE_SEEN


def test_a_card_that_prints_spell_damage_but_shows_no_tag_makes_the_value_unknown():
    printed = CardCatalog([CardFeatures(card_id="CS2_231", card_type="MINION", mechanics=("SPELLPOWER",))])
    found = facts(catalog=printed)
    assert found.spell_damage_status == SPELL_DAMAGE_UNKNOWN and found.unknown["spell_damage"] == "PRINTED_WITHOUT_TAG"


def test_hand_keywords_follow_each_instance_and_ignore_the_catalog(monkeypatch):
    monkeypatch.setattr(live_fixtures, "SELF_HAND", {6: "CS2_029", 7: "CS2_029", 8: "CS2_024"})
    found = facts(["TAG_CHANGE Entity=6 tag=TAUNT value=1", "TAG_CHANGE Entity=7 tag=REBORN value=1",
                   "TAG_CHANGE Entity=7 tag=LIFESTEAL value=1"])
    assert [(c.position, c.card_id, c.keywords) for c in found.hand] == [
        (0, "CS2_029", ("taunt",)), (1, "CS2_029", ("lifesteal", "reborn")), (2, "CS2_024", ())]


def test_hand_positions_follow_the_zone_position_not_the_entity_order(monkeypatch):
    monkeypatch.setattr(live_fixtures, "SELF_HAND", {6: "CS2_029", 7: "CS2_023", 8: "CS2_024"})
    found = facts(["TAG_CHANGE Entity=6 tag=ZONE_POSITION value=3", "TAG_CHANGE Entity=8 tag=ZONE_POSITION value=1",
                   "TAG_CHANGE Entity=6 tag=TAUNT value=1"])
    assert [c.card_id for c in found.hand] == ["CS2_024", "CS2_023", "CS2_029"]
    assert found.hand[2].keywords == ("taunt",)


def test_keyword_vocabulary_matches_the_forecaster_body_flags():
    assert set(KEYWORD_TAGS) == set(BODY_FLAGS.values())


# ----- privacy ---------------------------------------------------------------------------------------------------

class Recording(dict):
    """Tag dict that remembers every key read."""

    def __init__(self, data):
        super().__init__(data)
        self.read: set = set()

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self.read.add(key)
        return super().__contains__(key)


def test_only_the_opponent_heros_divine_shield_is_read_among_the_opponents_non_structural_tags():
    log = LiveLog(canaries=True).create_game().mulligan()
    log.opponent_hand_identity()
    session, snapshot = decide(log=log)
    game = session.game.reducer.game
    spies = {}
    for entity in list(game.entities):
        if entity.tags.get(GameTag.CONTROLLER) == 2 or entity.id == 3:
            spies[entity.id] = entity.tags = Recording(entity.tags)
    again = extract_observed_facts(game, 1, ObservationHistory(0, 0), CATALOG)
    assert again == snapshot.observed
    structural = {GameTag.CONTROLLER, GameTag.ZONE, GameTag.CARDTYPE, GameTag.PLAYER_ID, GameTag.HERO_ENTITY}
    extra = {entity_id: spy.read - structural for entity_id, spy in spies.items() if spy.read - structural}
    assert extra == {5: {GameTag.DIVINE_SHIELD}}            # the opponent hero, nothing else, no identity, no hand


def test_hidden_opponent_information_does_not_move_a_single_fact():
    plain = LiveLog(canaries=False).create_game().mulligan()
    loud = LiveLog(canaries=True).create_game().mulligan()
    loud.canary_reveals().opponent_hand_identity()
    assert decide(log=plain)[1].observed == decide(log=loud)[1].observed


def test_the_serialized_facts_carry_no_card_identity_of_the_opponent():
    log = LiveLog(canaries=True).create_game().mulligan()
    log.canary_reveals().opponent_hand_identity()
    text = json.dumps(decide(log=log)[1].observed.to_dict())
    assert "CANARY" not in text and CANARY_OPP_HAND not in text


# ----- isolation from the state, the snapshot and the decision --------------------------------------------------

def test_the_facts_never_enter_the_snapshot_json_or_the_state_hash(monkeypatch):
    with_facts = decide(["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=2"])[1]
    monkeypatch.setattr("manamind.live.session.extract_observed_facts", lambda *args, **kwargs: None)
    without = decide(["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=2"])[1]
    assert with_facts.observed is not None and without.observed is None
    assert with_facts.to_json() == without.to_json()
    assert with_facts.state_hash == without.state_hash == state_hash(with_facts.state)
    assert "observed" not in with_facts.to_dict()
    assert with_facts == without                            # excluded from equality too


def test_an_extraction_failure_costs_nothing_but_the_facts(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("x")

    monkeypatch.setattr("manamind.live.session.extract_observed_facts", boom)
    session, snapshot = decide()
    assert snapshot.observed is None and snapshot.status == "READY" and snapshot.decision["legal"]


def test_policy_import_hands_the_facts_to_an_observer_without_changing_a_row():
    from test_hero_state_extraction import policy_log

    seen: dict = {}
    rows, summary = extract_match(policy_log().lines, CATALOG, lambda decision, found: seen.__setitem__(decision, found))
    plain_rows, plain_summary = extract_match(policy_log().lines, CATALOG)
    assert rows == plain_rows and summary == plain_summary
    assert set(seen) == {row["decision_id"] for row in rows}
    assert all(isinstance(found, ObservedFacts) and found.coverage == COMPLETE for found in seen.values())
    assert split_games(policy_log().lines)


def test_facts_round_trip_and_an_unknown_schema_is_refused():
    found = facts(["TAG_CHANGE Entity=2 tag=CURRENT_HEALING_POWER value=2"])
    assert ObservedFacts.from_dict(json.loads(json.dumps(found.to_dict()))) == found
    with pytest.raises(ValueError):
        ObservedFacts.from_dict({**found.to_dict(), "schema": 99})


def test_nothing_that_feeds_the_overlay_or_the_recommendation_reads_a_forecast():
    """Action Outcome stays out of user recommendations: the live package and the apps never import it."""
    paths = list((ROOT / "src" / "manamind" / "live").rglob("*.py")) + list((ROOT / "apps").rglob("*.py"))
    paths += list((ROOT / "src" / "manamind" / "integrations" / "powerlog").rglob("*.py"))
    assert paths
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:from|import)\s+manamind\.outcome", text, re.MULTILINE), path
        assert "forecast_action" not in text, path
