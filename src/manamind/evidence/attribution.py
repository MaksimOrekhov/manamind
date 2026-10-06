"""Who does an effect belong to?

Precedence (EVIDENCE-0A section 5.4), applied to a fact *independently of any subject*:

1. ``CREATOR_TAG``                  the game's own statement of origin (creations, enchantments);
2. ``LAST_AFFECTED_BY_SAME_UNIT``   ``LAST_AFFECTED_BY`` set *inside the same unit* (the client logs it after
   the damage/stat packet, so order inside the unit is not required);
3. ``UNIT_OWNER``                   the block's source entity;
4. ``UNATTRIBUTED``                 system blocks, and the root ``PLAY``/``ATTACK`` block's own packets
   (R1: never credit a root block's content to its source by default).

``LAST_AFFECTED_BY`` is sticky; a value that was *not* set inside the unit is never used, and when
it names another entity than the unit owner it is reported as stale (a confounder), not used.

Relative to a subject, an attribution that points to any other entity becomes ``NESTED_ONLY``:
the fact sits inside the subject's window but is a reaction, never part of its effect profile.
"""

from __future__ import annotations

from .walker import ROOT_ATTRIBUTION_GUARD, Unit, Window

CREATOR_CHAIN_LIMIT = 5


def resolve_creator(window: Window, handle: int) -> tuple[int, list[int]]:
    """Follow ENCHANTMENT creators (an enchantment created by an enchantment created by X -> X)."""
    chain = [handle]
    view = window.final.get(handle)
    for _ in range(CREATOR_CHAIN_LIMIT):
        if view is not None and view.card_type == "ENCHANTMENT" and view.creator:
            handle = view.creator
            chain.append(handle)
            view = window.final.get(handle)
        else:
            break
    return handle, chain


def is_system_owner(window: Window, owner: int | None) -> bool:
    if owner is None:
        return True
    view = window.final.get(owner)
    return view is None or not view.card_id


def unit_default(window: Window, unit: Unit | None, entity: int | None) -> tuple[str, int | None]:
    if unit is None or is_system_owner(window, unit.owner):
        return "UNATTRIBUTED", None
    if unit.parent is None and unit.block_type in ROOT_ATTRIBUTION_GUARD and entity != unit.owner:
        return "UNATTRIBUTED", None
    return "UNIT_OWNER", unit.owner


def attribute_creation(window: Window, unit: Unit | None, handle: int | None) -> tuple[str, int | None, list[int]]:
    final = window.final.get(handle) if handle is not None else None
    if final is not None and final.creator:
        resolved, chain = resolve_creator(window, final.creator)
        return "CREATOR_TAG", resolved, chain
    basis, owner = unit_default(window, unit, handle)
    return basis, owner, []


def attribute_effect(window: Window, unit: Unit | None, target: int | None,
                     lab_in_unit: int | None) -> tuple[str, int | None]:
    """Damage, healing and stat/keyword effects on ``target``."""
    if lab_in_unit:
        return "LAST_AFFECTED_BY_SAME_UNIT", resolve_creator(window, lab_in_unit)[0]
    return unit_default(window, unit, target)


def relative(basis: str, attributed: int | None, subject: int) -> str:
    """The attribution basis as seen from ``subject``."""
    if basis == "UNATTRIBUTED" or attributed is None:
        return "UNATTRIBUTED"
    return basis if attributed == subject else "NESTED_ONLY"
