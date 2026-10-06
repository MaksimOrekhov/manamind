"""Incremental hslog driver for one game section.

One ``GameReducer`` owns a fresh ``LogParser`` for exactly one ``CREATE_GAME`` section,
so mode metadata can never leak between games. Lines are parsed as they arrive. Packets
are applied to the entity table lazily, at decision time, one packet at a time in
registration order (a pre-order walk of the packet tree), which is exactly the order a
one-shot export uses.

Errors carry only a stable reason code, never log text.
"""

from __future__ import annotations

import itertools
import logging
import warnings
from contextlib import contextmanager

from hearthstone.enums import BlockType, GameTag
from hslog import LogParser
from hslog.exceptions import ExporterError, MissingPlayerData, NoSuchEnum
from hslog.export import EntityTreeExporter
from hslog.packets import Block, Options, SubSpell

from manamind.integrations.powerlog.exporter import CompatibleEntityTreeExporter

from .trust import Reason


class ReducerError(Exception):
    """Raised with a stable reason code only."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PacketExporter(CompatibleEntityTreeExporter):
    """Applies one packet per call; blocks and sub-spells are walked by the reducer.

    It also keeps hearthstone's entity code offline. ``Card.reveal``/``Card.change`` look the
    original card up in the card database when a packet carries ``TRANSFORMED_FROM_CARD``,
    and without the optional ``hearthstone_data`` package that lookup downloads the database
    from the web (seconds, and a network call inside live parsing). The bridge never reads
    ``initial_card_id``, so it is set up front and the lookup is skipped.
    """

    def _skip_card_database(self, packet) -> None:
        if not dict(packet.tags).get(GameTag.TRANSFORMED_FROM_CARD):
            return
        entity = self.game.find_entity_by_id(packet.entity)
        if entity is not None and not entity.initial_card_id:
            entity.initial_card_id = packet.card_id

    def handle_show_entity(self, packet):
        self._skip_card_database(packet)
        return super().handle_show_entity(packet)

    def handle_change_entity(self, packet):
        self._skip_card_database(packet)
        return super().handle_change_entity(packet)

    def handle_block(self, packet) -> None:
        if packet.type == BlockType.GAME_RESET:
            self.game.reset()

    def handle_sub_spell(self, packet) -> None:
        return None


@contextmanager
def quiet_parser():
    """hslog logs raw log text on warnings; keep it out of every output stream."""
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            yield
    finally:
        logging.disable(previous)


def preorder(packets):
    for packet in packets:
        yield packet
        if isinstance(packet, (Block, SubSpell)):
            yield from preorder(packet.packets)


class GameReducer:
    def __init__(self) -> None:
        self.parser = LogParser()
        self.exporter: PacketExporter | None = None
        self._cursor = 0
        self.skipped_unknown_tags = 0

    @property
    def tree(self):
        games = self.parser.games
        return games[-1] if games else None

    def read_line(self, line: str) -> None:
        with quiet_parser():
            try:
                self.parser.read_line(line)
            except NoSuchEnum as error:
                if error.enum is GameTag:
                    # A tag name this hearthstone package does not know cannot be one we
                    # read; count it and keep the line out of the entity table.
                    self.skipped_unknown_tags += 1
                    return
                raise ReducerError(Reason.PARSE_ERROR) from None
            except Exception:
                raise ReducerError(Reason.PARSE_ERROR) from None

    def last_options(self):
        tree = self.tree
        if tree is not None and tree.packets and isinstance(tree.packets[-1], Options):
            return tree.packets[-1]
        return None

    def commit(self) -> None:
        """Apply every parsed packet not applied yet. Call only when the tail is quiet."""
        tree = self.tree
        if tree is None:
            return
        if self.exporter is None:
            self.exporter = PacketExporter(tree)
        with quiet_parser():
            for packet in itertools.islice(preorder(tree.packets), self._cursor, None):
                try:
                    self.exporter.export_packet(packet)
                except EntityTreeExporter.EntityNotFound:
                    raise ReducerError(Reason.ENTITY_UNKNOWN) from None
                except (ExporterError, MissingPlayerData, NotImplementedError, AttributeError,
                        KeyError, TypeError, ValueError):
                    raise ReducerError(Reason.PARSE_ERROR) from None
                self._cursor += 1

    @property
    def game(self):
        return self.exporter.game if self.exporter is not None else None
