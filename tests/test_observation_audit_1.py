import sys
from pathlib import Path
from types import SimpleNamespace

from hearthstone.enums import GameTag, Zone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from observation_audit_1 import ACTIVE, INACTIVE, UNKNOWN, quests, sanctum_state  # noqa: E402


def card(card_id, zone, controller, **tags):
    return SimpleNamespace(card_id=card_id, zone=zone, controller=controller,
                           tags={getattr(GameTag, name): value for name, value in tags.items()})


def game(player, *entities):
    return SimpleNamespace(entities=[player, *entities])


PLAYER = SimpleNamespace(id=2, tags={})


def with_flag(value):
    return SimpleNamespace(id=2, tags={GameTag.HEALING_DOES_DAMAGE: value})


def test_active_needs_both_the_player_flag_and_the_attached_effect_not_the_location():
    effect = card("CATA_301e", Zone.PLAY, PLAYER, ATTACHED=2)
    # The location already left play (last durability used): the effect is still active.
    hidden = sanctum_state(game(with_flag(1), effect), with_flag(1))
    assert hidden["state"] == ACTIVE and not hidden["location_in_play"]
    assert sanctum_state(game(PLAYER), PLAYER)["state"] == INACTIVE


def test_a_location_on_cooldown_alone_is_not_evidence_of_an_active_effect():
    location = card("CATA_301", Zone.PLAY, PLAYER, LOCATION_ACTION_COOLDOWN=1)
    result = sanctum_state(game(PLAYER, location), PLAYER)
    assert result["state"] == INACTIVE and result["location_on_cooldown"]


def test_disagreeing_signals_stay_unknown():
    assert sanctum_state(game(with_flag(1)), with_flag(1))["state"] == UNKNOWN
    effect = card("CATA_301e", Zone.PLAY, PLAYER, ATTACHED=2)
    assert sanctum_state(game(PLAYER, effect), PLAYER)["state"] == UNKNOWN
    other_target = card("CATA_301e", Zone.PLAY, PLAYER, ATTACHED=3)
    assert sanctum_state(game(with_flag(1), other_target), with_flag(1))["state"] == UNKNOWN


def test_quests_are_secret_zone_entities_with_the_quest_tag_only():
    quest = card("TLC_817t", Zone.SECRET, PLAYER, QUEST=1, QUEST_PROGRESS_TOTAL=4)
    quest.id = 90
    aura = card("END_011", Zone.SECRET, PLAYER, QUEST_PROGRESS=1)
    aura.id = 91
    assert quests(game(PLAYER, quest, aura), PLAYER) == {
        90: {"card_id": "TLC_817t", "progress": None, "total": 4}}
