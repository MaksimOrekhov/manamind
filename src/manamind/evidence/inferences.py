"""Derived statements. Each names the facts it was computed from and its assumptions.

An inference never replaces a fact and is never stored as one; it always has non-empty
``inputs``. Predicate evaluation over card text (conditions) is deliberately not implemented
here: it needs an independently reviewed predicate, not a guess from the log.
"""

from __future__ import annotations

from .entities import weakest
from .facts import RawFact
from .walker import Window

RULE_VERSION = 1
EXPLAINABLE_TAGS = frozenset({"ATK", "HEALTH", "COST", "DURABILITY"})


def build_inferences(window: Window, facts: list[RawFact], own_units: list[str],
                     subject_card_type: str | None) -> list[dict]:
    by_id = {fact.fact_id: fact for fact in facts}
    out: list[dict] = []

    def emit(kind, rule, inputs, result, status="DERIVED", assumptions=()):
        inputs = [i for i in inputs if i in by_id]
        if not inputs:
            return
        out.append({
            "inference_id": f"i{len(out) + 1}", "kind": kind,
            "derivation": {"rule_id": rule, "rule_version": RULE_VERSION},
            "inputs": inputs, "assumptions": list(assumptions), "result": result, "status": status,
            "visibility": weakest(by_id[i].visibility for i in inputs),
        })

    damage = [f for f in facts if f.kind == "DAMAGE_PACKET"]
    for fact in damage:
        if fact.data["divine_shield_popped"] and fact.data["amount"] == 0:
            emit("DIVINE_SHIELD_ABSORBED", "damage_zero_with_shield_pop", [fact.fact_id], {"absorbed": True})

    for death in (f for f in facts if f.kind == "DEATH"):
        earlier = [d for d in damage if d.handle == death.handle and d.ordinal < death.ordinal]
        health = death.data.get("health")
        damage_tag = death.data.get("damage_tag")
        if earlier and health is not None and damage_tag is not None and damage_tag >= health:
            emit("DEATH_BY_DAMAGE", "damage_tag_ge_health_after_damage_packet",
                 [death.fact_id] + [d.fact_id for d in earlier],
                 {"entity": death.handle}, "ASSUMPTION_DEPENDENT",
                 ["no unobserved lethal source exists outside the packets of this window"])
        elif not earlier and health is not None and (damage_tag or 0) < health:
            emit("DESTROY_WITHOUT_DAMAGE", "death_without_damage_packet_or_lethal_damage_tag",
                 [death.fact_id], {"entity": death.handle}, "ASSUMPTION_DEPENDENT",
                 ["damage taken before this window is read from the entity's own DAMAGE tag at death"])

    attachments = [f for f in facts if f.kind in ("ENCHANTMENT_ATTACHED", "ENCHANTMENT_REMOVED")]
    for stat in (f for f in facts if f.kind == "STAT_DELTA" and f.data["tag"] in EXPLAINABLE_TAGS):
        linked = [a for a in attachments if _attached_handle(a) == stat.handle]
        if linked:
            emit("STAT_CHANGE_EXPLAINED_BY_ENCHANTMENT", "enchantment_lifecycle_on_same_entity",
                 [stat.fact_id] + [a.fact_id for a in linked], {"entity": stat.handle}, "ASSUMPTION_DEPENDENT",
                 ["an enchantment created or removed on the entity in this window accounts for the change"])
        else:
            emit("STAT_CHANGE_UNEXPLAINED", "no_enchantment_lifecycle_in_window", [stat.fact_id],
                 {"entity": stat.handle})

    if own_units:
        powers = [f for f in facts if f.kind == "BLOCK_STRUCTURE" and f.unit_id in own_units
                  and f.data["block_type"] == "POWER" and f.data["parent_unit_id"] == "u0"]
        if subject_card_type == "MINION" and powers:
            emit("BATTLECRY_FROM_OWN_POWER_BLOCK", "minion_play_with_own_power_child",
                 [powers[0].fact_id], {"own_power_block": True}, "ASSUMPTION_DEPENDENT",
                 ["battlecry versus other on-play text is told from card metadata, not from the log"])
        triggers = [f for f in facts if f.kind == "BLOCK_STRUCTURE" and f.unit_id in own_units
                    and f.data["block_type"] == "TRIGGER"]
        if len(triggers) > 1:
            emit("REPEATED_TRIGGER_COUNT", "own_trigger_units_in_window", [f.fact_id for f in triggers],
                 {"count": len(triggers)}, "ASSUMPTION_DEPENDENT",
                 ["N blocks versus one block with N effects cannot be told apart without card text"])
    return out


def _attached_handle(fact: RawFact) -> int | None:
    if fact.kind == "ENCHANTMENT_ATTACHED":
        return fact.handle
    attached = fact.data.get("attached_to")
    return attached if isinstance(attached, int) else None
