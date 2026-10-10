"""TACTICAL-DECISION-1 overlay: state rules and the no-future-packets guarantee, without a real Power.log."""
from types import SimpleNamespace

import pytest
from hearthstone.enums import GameTag, Zone
from hslog.packets import Block, Options

from manamind.research import decision_overlay as module
from manamind.research.decision_overlay import ACTIVE, INACTIVE, UNKNOWN, healing_state, own_hand, own_quests


def entity(entity_id, card_id=None, zone=Zone.PLAY, controller=None, **tags):
    return SimpleNamespace(id=entity_id, card_id=card_id, zone=zone, controller=controller,
                           tags={getattr(GameTag, name.upper()): value for name, value in tags.items()})


def game_with(*entities):
    return SimpleNamespace(entities=list(entities))


def test_sanctum_state_needs_flag_and_enchantment_to_agree():
    player = entity(2, healing_does_damage=1)
    effect = entity(30, "CATA_301e", attached=2)
    assert healing_state(game_with(player, effect), player) == ACTIVE
    assert healing_state(game_with(entity(2), ), entity(2)) == INACTIVE
    assert healing_state(game_with(player), player) == UNKNOWN  # flag without the enchantment
    quiet = entity(2)
    assert healing_state(game_with(quiet, entity(30, "CATA_301e", attached=2)), quiet) == UNKNOWN  # enchantment alone
    # An enchantment attached to somebody else (or already in the graveyard) does not count.
    other = entity(31, "CATA_301e", attached=99)
    spent = entity(32, "CATA_301e", zone=Zone.GRAVEYARD, attached=2)
    assert healing_state(game_with(quiet, other, spent), quiet) == INACTIVE


def test_only_real_quests_of_the_player_count():
    me, foe = entity(2), entity(3)
    mine = entity(10, "TLC_817t", Zone.SECRET, me, quest=1, quest_progress=2, quest_progress_total=4)
    fresh = entity(11, "TLC_817t2", Zone.SECRET, me, quest=1, quest_progress_total=4)
    aura = entity(12, "END_011", Zone.SECRET, me, quest=0, quest_progress=3)
    theirs = entity(13, "TLC_817t", Zone.SECRET, foe, quest=1, quest_progress=3, quest_progress_total=4)
    quests = own_quests(game_with(mine, fresh, aura, theirs), me)
    assert [(q.card_id, q.progress, q.total) for q in quests] == [("TLC_817t", 2, 4), ("TLC_817t2", 0, 4)]


def test_hand_is_ordered_by_zone_position_and_excludes_the_opponent():
    me, foe = entity(2), entity(3)
    first = entity(20, "A", Zone.HAND, me, zone_position=1, quest_contributor=1)
    second = entity(21, "B", Zone.HAND, me, zone_position=2)
    hidden = entity(22, "C", Zone.HAND, foe, zone_position=1, quest_contributor=1)
    deck = entity(23, "D", Zone.DECK, me, zone_position=1)
    assert [e.card_id for e in own_hand(game_with(second, first, hidden, deck), me)] == ["A", "B"]


def test_overlay_is_read_before_the_options_packet_and_later_packets_are_not_visible(monkeypatch):
    me = entity(2, player_id=1)
    foe = entity(3, player_id=2)
    log = []

    class FakeExporter:
        def __init__(self, tree):
            self.game = SimpleNamespace(players=[me, foe], entities=[me, foe])

        def export_packet(self, packet):
            log.append(("export", packet.name))
            if packet.name == "spend":  # applied only after the Options packet
                self.game.entities.append(entity(30, "CATA_301e", attached=2))
                me.tags[GameTag.HEALING_DOES_DAMAGE] = 1

    class Marked(Options):
        name = "options"

    class Spend(Block):
        name = "spend"
        packets = ()

    options = Marked.__new__(Marked)
    options.id = 7
    options.name = "options"
    spend = Spend.__new__(Spend)
    spend.name = "spend"
    spend.packets = []
    monkeypatch.setattr(module, "PacketExporter", FakeExporter)
    walker = module._Walker(SimpleNamespace(packets=[options, spend]), self_id=1, key="K")
    walker.run()
    assert walker.overlays["K:7"].healing_does_damage == INACTIVE  # the later packet is not visible
    assert log == [("export", "options"), ("export", "spend")]
    assert me.tags[GameTag.HEALING_DOES_DAMAGE] == 1  # and it did happen afterwards
    assert healing_state(walker.exporter.game, me) == ACTIVE


def test_unknown_labels_never_reach_the_overlay_constructor():
    with pytest.raises(TypeError):
        module.DecisionOverlay("d", INACTIVE)  # every field is explicit: nothing defaults to a guessed value
