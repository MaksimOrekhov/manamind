"""Entity-tree exporter that tolerates the player references real logs contain."""

from __future__ import annotations

from hslog.export import EntityTreeExporter
from hslog.player import coerce_to_entity_id


class CompatibleEntityTreeExporter(EntityTreeExporter):
    """Normalize player references in FULL_ENTITY packets before export.

    Some Hearthstone logs use a PlayerReference where hslog's exporter assumes
    an integer entity ID. hslog provides a safe coercion for this packet field.
    """

    def handle_full_entity(self, packet):
        entity_id = coerce_to_entity_id(packet.entity)
        existing_entity = self.game.find_entity_by_id(entity_id)
        if existing_entity is not None:
            existing_entity.card_id = packet.card_id
            existing_entity.tags = dict(packet.tags)
            return existing_entity

        entity = self.card_class(entity_id, packet.card_id)
        entity.tags = dict(packet.tags)
        self.game.register_entity(entity)
        return entity
