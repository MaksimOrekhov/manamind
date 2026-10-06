"""Why a window may mislead: typed confounders with the claim kinds they could affect."""

from __future__ import annotations

from .entities import Redactor
from .facts import RawFact
from .walker import Unit, Window

KIND_TO_CLAIMS = {
    "DAMAGE_PACKET": ["DAMAGE_AMOUNT"],
    "HEALING_PACKET": ["HEAL_AMOUNT"],
    "ENTITY_CREATED": ["SUMMON_OUTCOME", "GENERATED_OUTCOME_SET"],
    "ENTITY_TRANSFORMED": ["TRANSFORM_OUTCOME"],
    "ENCHANTMENT_ATTACHED": ["ENCHANTMENT_APPLIED"],
    "ENCHANTMENT_REMOVED": ["ENCHANTMENT_APPLIED"],
    "STAT_DELTA": ["STAT_DELTA"],
    "KEYWORD_DELTA": ["STAT_DELTA"],
    "DEATH": ["DEATHRATTLE_OUTCOME", "ZONE_MOVE"],
    "ZONE_MOVE": ["ZONE_MOVE"],
    "CHOICE_OFFERED": ["CHOICE_OFFER"],
    "CHOICE_MADE": ["CHOICE_OFFER"],
}
SUMMON_LIKE = ["DAMAGE_AMOUNT", "HEAL_AMOUNT", "STAT_DELTA"]


def _claims_for(facts: list[RawFact]) -> list[str]:
    claims: set[str] = set()
    for fact in facts:
        if fact.kind == "STAT_DELTA" and fact.data.get("tag") == "COST":
            claims.add("COST_MODIFICATION")
        else:
            claims.update(KIND_TO_CLAIMS.get(fact.kind, []))
    return sorted(claims)


def _descendant_of(window: Window, unit: Unit, ancestors: set[str]) -> bool:
    units = {u.unit_id: u for u in window.units}
    current = unit
    while current.parent is not None:
        if current.parent in ancestors:
            return True
        current = units[current.parent]
    return False


def build_confounders(window: Window, redactor: Redactor, subject: int, own_units: set[str],
                      facts: list[RawFact], semantic_units: set[str]) -> list[dict]:
    out: list[dict] = []
    by_unit: dict[str, list[RawFact]] = {}
    for fact in facts:
        by_unit.setdefault(fact.unit_id, []).append(fact)

    def add(kind, claims, handle=None, note=None):
        entry: dict = {"kind": kind, "affects_claim_kinds": sorted(set(claims))}
        if handle is not None:
            ref, _ = redactor.ref(window.final.get(handle), handle=handle)
            entry["entity"] = ref
        if note:
            entry["note"] = note
        out.append(entry)

    seen_foreign: set[int] = set()
    for unit in window.units:
        if unit.owner in (None, subject) or unit.unit_id not in semantic_units:
            continue
        if unit.owner in seen_foreign:
            continue
        owner_view = window.final.get(unit.owner)
        if owner_view is None or not owner_view.card_id:
            continue
        seen_foreign.add(unit.owner)
        claims = _claims_for([f for u in window.units if u.owner == unit.owner
                              for f in by_unit.get(u.unit_id, []) if f.kind in KIND_TO_CLAIMS])
        preexisting_enchantment = owner_view.card_type == "ENCHANTMENT" and unit.owner not in window.created
        if preexisting_enchantment and owner_view.creator != subject:
            if _descendant_of(window, unit, own_units):
                claims += ["DAMAGE_AMOUNT", "HEAL_AMOUNT"]
            add("FOREIGN_ENCHANTMENT_ACTIVE", claims, unit.owner,
                "another card's enchantment acted inside this window")
        else:
            add("FOREIGN_UNIT_WITH_EFFECTS_IN_WINDOW", claims, unit.owner,
                "a unit owned by another card has effects; they are not the subject's")
    for fact in facts:
        if fact.kind != "ENCHANTMENT_REMOVED" or fact.handle is None:
            continue
        view = window.final.get(fact.handle)
        if view is not None and fact.handle not in window.created and view.creator not in (None, subject):
            if not any(c["kind"] == "FOREIGN_ENCHANTMENT_ACTIVE" and c.get("entity", {}).get("handle") == fact.handle
                       for c in out):
                add("FOREIGN_ENCHANTMENT_ACTIVE", ["DAMAGE_AMOUNT", "HEAL_AMOUNT", "ENCHANTMENT_APPLIED"],
                    fact.handle, "another card's pre-existing enchantment was consumed in this window")

    stale = [f for f in facts if f.stale_lab and f.unit_id in own_units and f.basis == "UNIT_OWNER"
             and f.stale_lab != subject and f.attributed == subject]
    if stale:
        add("STALE_LAST_AFFECTED_BY", _claims_for(stale), stale[0].stale_lab,
            "LAST_AFFECTED_BY names another entity and was not set in the subject's unit; not used")

    own_blocks = [u for u in window.units if u.unit_id in own_units and u.parent is not None]
    types = [u.block_type for u in own_blocks]
    if any(types.count(t) > 1 for t in set(types)):
        add("MULTIPLE_OWNER_UNITS", [], note="the subject owns more than one unit of the same type")

    touched = {f.handle for f in facts if f.handle is not None}
    drift = [e for e in window.gap_events if e.entity in touched and e.tag in ("ATK", "HEALTH", "COST", "DURABILITY")]
    if drift:
        add("AURA_RECALC_OUTSIDE_BLOCK", ["STAT_DELTA"], note="stat changes outside any block touch the same entities")

    # UNKNOWN_TAG_IDS_IN_WINDOW is deliberately not emitted: on the audit corpus ids unknown to the installed
    # parser changed on about 77 percent of the entities a subject acts on (client bookkeeping), so as a
    # confounder it would mark nearly every observation. The ids stay in provenance.unknown_tag_ids_in_window.

    missing = [f for f in facts if f.kind in ("ENTITY_CREATED", "ENCHANTMENT_ATTACHED")
               and not f.data.get("creator_tag_present") and f.unit_id in own_units]
    if missing:
        add("MISSING_CREATOR_TAG", _claims_for(missing), note="a creation in the subject's unit has no CREATOR tag")
    return out
