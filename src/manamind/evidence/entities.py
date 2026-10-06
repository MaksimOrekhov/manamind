"""Point-in-time entity views and the visibility/redaction policy.

Default deny: an identity leaves this module only when SELF could see it. Opponent identities in
HAND, DECK, SECRET, SETASIDE or REMOVEDFROMGAME are redacted to ``None`` even though the raw log
carries them, unless the entity was publicly revealed (it entered PLAY or GRAVEYARD, or its play
started). Redaction removes the identity; the fact is then labelled ``OFFLINE_ONLY_HIDDEN``.
"""

from __future__ import annotations

from dataclasses import dataclass

from hearthstone.enums import CardType, GameTag, Zone
from hslog.player import coerce_to_entity_id

PUBLIC_ZONES = frozenset({"PLAY", "GRAVEYARD"})


@dataclass(frozen=True)
class EntityView:
    handle: int
    card_id: str
    controller: int | None
    zone: str | None
    card_type: str | None
    creator: int | None
    attached: int | None
    last_affected_by: int | None
    health: int | None
    damage: int | None


def to_id(reference) -> int | None:
    """Entity id of an hslog reference, never touching names."""
    try:
        return int(coerce_to_entity_id(reference))
    except Exception:  # noqa: BLE001 - any failure means "unknown"; no text is propagated
        return None


def _enum_name(enum_cls, value):
    if value is None:
        return None
    try:
        return enum_cls(int(value)).name
    except ValueError:
        return str(int(value))


def _int_tag(tags, tag) -> int | None:
    value = tags.get(tag)
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def view_of(game, handle: int | None) -> EntityView | None:
    if handle is None:
        return None
    try:
        entity = game.find_entity_by_id(handle)
    except Exception:  # noqa: BLE001
        return None
    if entity is None:
        return None
    tags = entity.tags
    return EntityView(
        handle=handle,
        card_id=getattr(entity, "card_id", "") or "",
        controller=_int_tag(tags, GameTag.CONTROLLER),
        zone=_enum_name(Zone, tags.get(GameTag.ZONE)),
        card_type=_enum_name(CardType, tags.get(GameTag.CARDTYPE)),
        creator=_int_tag(tags, GameTag.CREATOR) or None,
        attached=_int_tag(tags, GameTag.ATTACHED) or None,
        last_affected_by=_int_tag(tags, GameTag.LAST_AFFECTED_BY) or None,
        health=_int_tag(tags, GameTag.HEALTH),
        damage=_int_tag(tags, GameTag.DAMAGE),
    )


class Redactor:
    """Builds EntityRefs and visibility labels for one game from SELF's perspective."""

    def __init__(self, self_id: int, inventory) -> None:
        self.self_id = self_id
        self.inventory = inventory
        self.public_ids: set[int] = set()
        self.redactions = 0

    def side(self, controller: int | None) -> str:
        if controller is None:
            return "NEUTRAL"
        return "SELF" if controller == self.self_id else "OPPONENT"

    def _public_identity(self, view: EntityView, forced_hidden: bool) -> bool:
        if self.side(view.controller) == "SELF":
            return True
        if forced_hidden:
            return False
        return view.zone in PUBLIC_ZONES or view.handle in self.public_ids

    def ref(self, view: EntityView | None, *, raw_card_id: str | None = None,
            forced_hidden: bool = False, handle: int | None = None) -> tuple[dict, str]:
        """(EntityRef, visibility). ``raw_card_id`` overrides the view's id (a reveal's new id)."""
        if view is None:
            return {"handle": handle if handle is not None else -1, "side": "NEUTRAL"}, "PUBLIC_TO_SELF"
        raw = view.card_id if raw_card_id is None else raw_card_id
        side = self.side(view.controller)
        ref: dict = {"handle": view.handle, "side": side, "zone": view.zone}
        in_public_zone = view.zone in PUBLIC_ZONES
        if not raw:
            ref.update(card_id=None, card_type=view.card_type if side != "OPPONENT" or in_public_zone else None)
            visibility = "SELF_PRIVATE" if side == "SELF" and not in_public_zone else "PUBLIC_TO_SELF"
            return ref, visibility
        if self._public_identity(view, forced_hidden and side != "SELF"):
            from .sanitize import safe_card_id

            card_id = safe_card_id(raw)
            ref.update(card_id=card_id, card_type=view.card_type)
            if card_id is not None:
                ref["support_state"] = self.inventory.state(card_id)
            visibility = "SELF_PRIVATE" if side == "SELF" and not in_public_zone else "PUBLIC_TO_SELF"
            return ref, visibility
        self.redactions += 1
        ref.update(card_id=None, card_type=None)
        return ref, "OFFLINE_ONLY_HIDDEN"

    def public_card_id(self, view: EntityView | None) -> str | None:
        """The card id of an entity only when SELF could see it, else None."""
        if view is None:
            return None
        from .sanitize import safe_card_id

        if not view.card_id:
            return None
        return safe_card_id(view.card_id) if self._public_identity(view, False) else None


WEAKEST = {"PUBLIC_TO_SELF": 0, "SELF_PRIVATE": 1, "OFFLINE_ONLY_HIDDEN": 2}


def weakest(labels) -> str:
    result = "PUBLIC_TO_SELF"
    for label in labels:
        if WEAKEST[label] > WEAKEST[result]:
            result = label
    return result
