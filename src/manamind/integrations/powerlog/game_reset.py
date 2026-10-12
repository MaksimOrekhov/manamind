"""Which decisions after a GAME_RESET can be trusted (POLICY-GAME-RESET-RECOVERY-1).

A ``GAME_RESET`` block in Ranked Standard is the Rewind mechanic: the server rolls the table back and re-sends the
entities with ``FULL_ENTITY - Updating``. hslog applies that by first clearing every card's identity (``Card.reset``
keeps the other tags) and then replacing the tags of each entity the block re-sends. An entity the block does not
re-send keeps stale tags and loses its card ID - in real logs: equipped weapons, the Rewind enchantment, and cards
with no type at all, some in HAND or PLAY.

The rule: after the latest reset, a decision is trusted only if every entity in a zone the visible state is built
from (HAND, PLAY, DECK, SECRET - for either side) has been fully specified again since that reset by a FULL_ENTITY,
inside the reset block or later. Only FULL_ENTITY counts: it replaces all tags, while SHOW_ENTITY / CHANGE_ENTITY merge
new tags over stale ones. Anything else is skipped as ``GAME_RESET_STALE_STATE``; nothing is guessed. Before the first
reset nothing changes.
"""
from __future__ import annotations

from hearthstone.enums import BlockType, GameTag, Zone
from hslog import packets
from hslog.player import coerce_to_entity_id

STATE_ZONES = frozenset({Zone.HAND, Zone.PLAY, Zone.DECK, Zone.SECRET})
STALE_REASON = "GAME_RESET_STALE_STATE"
_SPECIFYING = (packets.FullEntity,)      # full tag replacement only; SHOW/CHANGE merge over stale tags


def _entity_id(value) -> int | None:
    try:
        return int(coerce_to_entity_id(value))
    except Exception:
        return None


def stale_state_entities(reducer) -> set[int] | None:
    """Entity IDs in state zones not re-specified since the latest applied GAME_RESET; ``None`` if there was none.

    An entity whose ID cannot be resolved from a specifying packet is not counted as specified (fail closed).
    """
    applied = list(reducer.applied_packets())
    last = None
    for index, packet in enumerate(applied):
        if isinstance(packet, packets.Block) and packet.type == BlockType.GAME_RESET:
            last = index
    if last is None:
        return None
    specified = set()
    for packet in applied[last + 1:]:
        if isinstance(packet, _SPECIFYING):
            identifier = _entity_id(packet.entity)
            if identifier is not None:
                specified.add(identifier)
    game = reducer.game
    return {entity.id for entity in game.entities
            if entity is not game and entity.id not in specified
            and entity.tags.get(GameTag.ZONE) in STATE_ZONES}
