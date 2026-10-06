"""Typed facts: packets read directly, never interpreted.

A fact states what a packet said, with the entity identities SELF could see, its visibility, a
subject-independent attribution and a ``packet_ordinal`` into the game's pre-order walk (no raw
text is stored). Derived statements belong in ``inferences.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .attribution import attribute_creation, attribute_effect, unit_default
from .entities import Redactor, weakest
from .walker import Event, Unit, Window

SEMANTIC_KINDS = frozenset({
    "DAMAGE_PACKET", "HEALING_PACKET", "ENTITY_CREATED", "ENTITY_TRANSFORMED", "ENCHANTMENT_ATTACHED",
    "ENCHANTMENT_REMOVED", "STAT_DELTA", "KEYWORD_DELTA", "DEATH", "CHOICE_OFFERED", "CHOICE_MADE",
    "CONTROL_CHANGE", "ZONE_MOVE",
})
DEATH_TYPES = frozenset({"MINION", "LOCATION", "WEAPON", "HERO"})
CONSUMABLE_TAGS = ("DAMAGE", "ARMOR", "DIVINE_SHIELD")


@dataclass
class RawFact:
    fact_id: str
    kind: str
    unit_id: str
    ordinal: int
    visibility: str
    basis: str
    attributed: int | None
    data: dict
    handle: int | None = None  # the entity the fact is about (for explanation rules)
    chain: list[int] = field(default_factory=list)
    stale_lab: int | None = None  # a LAST_AFFECTED_BY value that was NOT set in this unit
    in_root_play: bool = False


def _units(window: Window) -> dict[str, Unit]:
    return {unit.unit_id: unit for unit in window.units}


def _associate(window: Window) -> dict[int, dict]:
    """Pair each META DAMAGE/HEALING with the tag changes it caused on its target, same unit."""
    packets: dict[int, dict] = {}
    events = window.events
    for index, event in enumerate(events):
        if event.kind != "META" or event.meta not in ("DAMAGE", "HEALING") or not event.targets:
            continue
        for target in event.targets:
            found: dict = {"consumed": []}
            for later in events[index + 1:]:
                if later.unit != event.unit:
                    break
                if later.kind == "META" and later.meta in ("DAMAGE", "HEALING"):
                    break
                if later.kind != "TAG" or later.entity != target:
                    continue
                if later.tag == "DAMAGE" and "damage" not in found:
                    found["damage"] = (later.old, later.new)
                    found["consumed"].append(later.ordinal)
                elif later.tag == "ARMOR" and "armor" not in found:
                    found["armor"] = (later.old, later.new)
                    found["consumed"].append(later.ordinal)
                elif later.tag == "DIVINE_SHIELD" and later.old == 1 and later.new == 0:
                    found["shield"] = True
                    found["consumed"].append(later.ordinal)
            packets[event.ordinal, target] = found  # type: ignore[index]
    return packets


def build_facts(window: Window, redactor: Redactor) -> list[RawFact]:
    units = _units(window)
    pairing = _associate(window)
    consumed = {ordinal for found in pairing.values() for ordinal in found["consumed"]}
    lab_map = {(e.unit, e.entity): e.new for e in window.events
               if e.kind == "TAG" and e.tag == "LAST_AFFECTED_BY" and e.new}
    hidden_after = {e.entity: e.ordinal for e in window.events if e.kind == "HIDE" and e.entity is not None}
    facts: list[RawFact] = []

    def add(kind, event, unit, visibility, basis, attributed, data, *, handle=None, chain=(), stale=None):
        facts.append(RawFact(
            fact_id=f"f{len(facts) + 1}", kind=kind, unit_id=unit.unit_id if unit else "u0",
            ordinal=event.ordinal, visibility=visibility, basis=basis, attributed=attributed, data=data,
            handle=handle, chain=list(chain), stale_lab=stale,
            in_root_play=bool(unit is not None and unit.parent is None and unit.block_type == "PLAY"),
        ))

    root = window.units[0] if window.units else None
    if root is not None:
        view = window.final.get(root.target) if root.target else None
        if root.target:
            ref, visibility = redactor.ref(view, handle=root.target)
            add("PLAY_TARGET", Event(root.ordinal, root.unit_id, "TAG", None), root, visibility,
                "UNIT_OWNER" if root.owner is not None else "UNATTRIBUTED", root.owner,
                {"target": ref}, handle=root.target)

    for event in window.events:
        unit = units.get(event.unit) if event.unit else None
        if unit is None:
            continue
        if event.kind == "META" and event.meta in ("DAMAGE", "HEALING"):
            for target in event.targets:
                view = event.target_views.get(target)
                ref, visibility = redactor.ref(view, handle=target)
                found = pairing.get((event.ordinal, target), {})
                lab_unit = lab_map.get((event.unit, target))
                basis, who = attribute_effect(window, unit, target, lab_unit)
                stale = None
                if not lab_unit and view is not None and view.last_affected_by:
                    stale = view.last_affected_by
                data = {
                    "target": ref, "amount": event.amount,
                    "damage_tag_before": found.get("damage", (None, None))[0],
                    "damage_tag_after": found.get("damage", (None, None))[1],
                    "armor_delta": (found["armor"][1] - found["armor"][0]) if "armor" in found
                    and found["armor"][0] is not None and found["armor"][1] is not None else 0,
                    "divine_shield_popped": bool(found.get("shield")),
                    "target_health": view.health if view is not None else None,
                }
                kind = "DAMAGE_PACKET" if event.meta == "DAMAGE" else "HEALING_PACKET"
                add(kind, event, unit, visibility, basis, who, data, handle=target, stale=stale)
        elif event.kind == "TAG":
            if event.ordinal in consumed:
                continue
            _tag_fact(window, redactor, event, unit, add, lab_map.get((event.unit, event.entity)))
        elif event.kind == "CREATE":
            final = window.final.get(event.entity)
            basis, who, chain = attribute_creation(window, unit, event.entity)
            ref, visibility = redactor.ref(final, handle=event.entity)
            creation_zone = event.view.zone if event.view is not None else None
            creator = window.final.get(final.creator) if final is not None and final.creator else None
            data: dict = {
                "entity": ref, "creation_zone": creation_zone,
                "creator": redactor.ref(creator, handle=final.creator)[0] if creator is not None else None,
                "creator_tag_present": bool(final is not None and final.creator),
            }
            if final is not None and final.card_type == "ENCHANTMENT":
                attached = window.final.get(final.attached) if final.attached else None
                data = {"enchantment": ref, "creation_zone": creation_zone, "creator": data["creator"],
                        "attached_to": redactor.ref(attached, handle=final.attached)[0] if attached is not None else None,
                        "creator_tag_present": data["creator_tag_present"]}
                add("ENCHANTMENT_ATTACHED", event, unit, visibility, basis, who, data,
                    handle=final.attached, chain=chain)
            else:
                add("ENTITY_CREATED", event, unit, visibility, basis, who, data, handle=event.entity, chain=chain)
        elif event.kind == "REVEAL":
            hidden = event.hidden_reveal or (
                event.entity in hidden_after and hidden_after[event.entity] > event.ordinal)
            basis, who = unit_default(window, unit, event.entity)
            ref, visibility = redactor.ref(event.view, raw_card_id=event.card_id, forced_hidden=hidden,
                                           handle=event.entity)
            add("ENTITY_REVEALED", event, unit, visibility, basis, who,
                {"entity": ref, "previously_known": bool(event.old_card_id)}, handle=event.entity)
        elif event.kind == "CHANGE":
            basis, who = unit_default(window, unit, event.entity)
            new_ref, visibility = redactor.ref(event.view, raw_card_id=event.card_id, handle=event.entity)
            old_ref, old_vis = redactor.ref(event.view, raw_card_id=event.old_card_id, handle=event.entity)
            add("ENTITY_TRANSFORMED", event, unit, weakest([visibility, old_vis]), basis, who,
                {"entity": new_ref, "from_card_id": old_ref.get("card_id"), "to_card_id": new_ref.get("card_id")},
                handle=event.entity)
        elif event.kind in ("CHOICES", "CHOSEN"):
            refs, labels = [], []
            for target in event.targets:
                ref, label = redactor.ref(event.target_views.get(target), handle=target)
                refs.append(ref)
                labels.append(label)
            basis, who = unit_default(window, unit, None)
            # Offered identities can be copies of the opponent's deck: never above SELF_PRIVATE.
            kind = "CHOICE_OFFERED" if event.kind == "CHOICES" else "CHOICE_MADE"
            add(kind, event, unit, weakest(labels + ["SELF_PRIVATE"]), basis, who,
                {"entities": refs}, handle=None)
    if root is not None:
        add("TURN_STEP_CONTEXT", Event(root.ordinal, root.unit_id, "TAG", None), root, "PUBLIC_TO_SELF",
            "UNATTRIBUTED", None, {"turn": window.turn, "step": window.step, "root_block_type": window.root_type})
    return facts


def _tag_fact(window: Window, redactor: Redactor, event: Event, unit: Unit, add, lab_unit) -> None:
    tag = event.tag
    view = event.view
    ref, visibility = redactor.ref(view, handle=event.entity)
    if tag == "ZONE":
        card_type = view.card_type if view is not None else None
        if card_type == "ENCHANTMENT" and event.new in ("GRAVEYARD", "REMOVEDFROMGAME"):
            kind = "ENCHANTMENT_REMOVED"
        elif card_type in DEATH_TYPES and event.old == "PLAY" and event.new == "GRAVEYARD":
            kind = "DEATH"
        elif event.semantic or (unit.parent is None and event.entity == unit.owner):
            kind = "ZONE_MOVE"
        else:
            return
        basis, who = unit_default(window, unit, event.entity)
        data = {"entity": ref, "from": event.old, "to": event.new}
        if kind == "DEATH" and view is not None:
            data.update(damage_tag=view.damage, health=view.health)
        if kind == "ENCHANTMENT_REMOVED":
            data["attached_to"] = view.attached if view is not None else None
        add(kind, event, unit, visibility, basis, who, data, handle=event.entity)
        return
    if tag in ("RESOURCES_USED", "TEMP_RESOURCES") and unit.parent is None and unit.block_type == "PLAY":
        side = redactor.side(view.controller) if view is not None else "NEUTRAL"
        add("COST_PAYMENT", event, unit, "PUBLIC_TO_SELF", "UNIT_OWNER", unit.owner,
            {"player_side": side, "tag": tag, "old": event.old, "new": event.new}, handle=event.entity)
        return
    if not event.semantic:
        return
    if tag == "CONTROLLER":
        basis, who = attribute_effect(window, unit, event.entity, lab_unit)
        add("CONTROL_CHANGE", event, unit, visibility, basis, who,
            {"entity": ref, "old_side": redactor.side(event.old), "new_side": redactor.side(event.new)},
            handle=event.entity)
        return
    kind = "STAT_DELTA" if tag in ("ATK", "HEALTH", "COST", "DURABILITY", "ARMOR", "DAMAGE") else "KEYWORD_DELTA"
    basis, who = attribute_effect(window, unit, event.entity, lab_unit)
    stale = None
    if not lab_unit and view is not None and view.last_affected_by:
        stale = view.last_affected_by
    # An effect attributed to the unit owner may sit on an entity another card last affected.
    add(kind, event, unit, visibility, basis, who, {"entity": ref, "tag": tag, "old": event.old, "new": event.new},
        handle=event.entity, stale=stale)
