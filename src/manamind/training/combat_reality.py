"""Offline local attack facts; no new rules, state transition or production integration.

OBSERVED describes a relation between current numbers, never an outcome. CONDITIONAL
describes the existing forecaster's ordinary packet under explicit assumptions.
VERIFIED_LOCAL means no visible blocker to that packet in the forecaster contract;
it is not proof that every Hearthstone interaction is represented by this input.
"""
from __future__ import annotations

from manamind.domain.serialization import game_state_from_dict
from manamind.outcome import forecast_action
from manamind.outcome.model import Ref, Status

FLAGS = ("divine_shield", "immune", "poisonous", "reborn", "lifesteal", "windfury", "dormant", "silenced")
CONDITIONS = (
    "The attack reaches these same bodies with unchanged current stats and flags.",
    "No unmodelled prevention, replacement, redirection, trigger or aura alters the packets.",
    "Death means death of the original body, before Deathrattle or Reborn resolution.",
    "Health after packet is before any healing, resurrection or subsequent reaction.",
)


def fact(value=None, knownness="UNKNOWN", reasons=(), conditions=()):
    return {"value": value, "knownness": knownness, "reasons": sorted(set(reasons)),
            "conditions": list(conditions)}


def body(raw, side, position, card_id):
    hits = [m for m in raw[side]["board"] if m["board_position"] == position
            and m["card"]["card_id"] == card_id]
    return hits[0] if len(hits) == 1 else None


def legacy_reasons(row, action, metadata):
    """Nonexclusive explanation of the unchanged NCA gate, including board-wide refusal."""
    raw = row["state"]
    reasons = set()
    if action.get("source_kind") != "MINION" or action.get("target_kind") != "MINION":
        reasons.add("OUTSIDE_MINION_TO_MINION")
    for side in ("self_player", "opponent"):
        p = raw[side]
        for m in p["board"]:
            direct = ((side == "self_player" and m["board_position"] == action.get("source_board_position"))
                      or (side == "opponent" and m["board_position"] == action.get("target_board_position")))
            scope = "DIRECT" if direct else "OTHER_BOARD"
            record = metadata.get(m["card"]["card_id"])
            if record is None:
                reasons.add(scope + ":METADATA_MISSING")
            else:
                if record.get("type") != "MINION": reasons.add(scope + ":TYPE")
                if record.get("text") != "": reasons.add(scope + ":TEXT")
                if record.get("mechanics"): reasons.add(scope + ":MECHANICS")
            for k in FLAGS[:-1]:
                if type(m.get(k)) is not bool: reasons.add(scope + ":UNKNOWN_FLAG:" + k)
            for k in ("reborn", "lifesteal", "windfury", "dormant"):
                if m.get(k): reasons.add(scope + ":FLAG:" + k)
        if p.get("secret_count"): reasons.add(side.upper() + ":SECRET_OR_QUEST")
        if p.get("locations"): reasons.add(side.upper() + ":LOCATION")
        if p.get("active_effects"): reasons.add(side.upper() + ":ACTIVE_EFFECT")
    if raw.get("evidence_constraints"): reasons.add("EVIDENCE_CONSTRAINT")
    return sorted(reasons)


def extract_attack(row, action, texts, state=None):
    """Read only the pre-action visible state and action. Never read labels/successors."""
    out = {"schema": "manamind.combat_reality/1", "properties": {}, "blockers": [],
           "outcome_status": "NOT_CALLED", "outcome_unknowns": []}
    p = out["properties"]
    if action.get("type") != "ATTACK":
        out["blockers"] = ["NOT_ATTACK"]
        return out
    if (action.get("source_kind") != "MINION" or action.get("target_kind") != "MINION"
            or action.get("target_side") != "OPPONENT" or action.get("source_is_hero")):
        out["blockers"] = ["OUTSIDE_MINION_TO_MINION"]
        return out  # Hero/weapon attacks need a different set of observed prerequisites.
    raw = row["state"]
    source = body(raw, "self_player", action.get("source_board_position"), action.get("source_card_id"))
    target = body(raw, "opponent", action.get("target_board_position"), action.get("target_card_id"))
    if source is None or target is None:
        out["blockers"] = ["ACTION_BODY_MISMATCH"]
        return out
    nums = [source.get("current_attack"), source.get("current_health"),
            target.get("current_attack"), target.get("current_health")]
    if not all(type(v) is int for v in nums) or min(nums) < 0 or min(nums[1], nums[3]) <= 0:
        out["blockers"] = ["NUMERIC_VALUE_UNOBSERVED_OR_INVALID"]
        return out
    sa, sh, ta, th = nums
    for key, value in (("attack_ge_health", sa >= th), ("attack_health_margin", sa - th),
                       ("health_retaliation_margin", sh - ta), ("retaliation_attack", ta)):
        p[key] = fact(value, "OBSERVED")
    unknown_flags = sorted({k for side in ("self_player", "opponent") for m in raw[side]["board"]
                            for k in FLAGS if type(m.get(k)) is not bool})
    if unknown_flags:
        out["blockers"] = ["RAW_FLAG_UNOBSERVED:" + k for k in unknown_flags]
        # The production deserializer coerces some bool(None); do not send such input to Outcome.
        return out
    state = state or game_state_from_dict(raw)
    forecast = forecast_action(state, action, texts)
    out["outcome_status"] = forecast.status.value
    out["outcome_unknowns"] = [{"tag": u.tag, "kind": u.kind.value, "alters_listed": u.alters_listed,
                                "zone": u.subject.zone if u.subject else None} for u in forecast.unknowns]
    blockers = {u.tag or u.kind.value for u in forecast.unknowns if u.alters_listed
                and u.tag != "ATTACKS_USED_UNOBSERVED"}  # Only can_attack bookkeeping is unobserved.
    # Outcome skips some uninvolved auras because their current buffs are already observed.
    # Without a reviewed scope, an arbitrary aura may also prevent/replace attack damage.
    if any(set(m["card"].get("mechanics", ())) & {"AURA", "ADJACENT_BUFF"}
           or (texts.get(m["card"]["card_id"]) is not None and
               set(texts.get(m["card"]["card_id"]).mechanics) & {"AURA", "ADJACENT_BUFF"})
           for side in ("self_player", "opponent") for m in raw[side]["board"]):
        blockers.add("AURA_SCOPE_UNREVIEWED")
    if raw.get("evidence_constraints"): blockers.add("EVIDENCE_CONSTRAINT")
    for side in ("self_player", "opponent"):
        if raw[side].get("active_effects"): blockers.add("ACTIVE_EFFECT_UNMODELLED")
        weapon = raw[side].get("weapon")
        if weapon:
            entry = texts.get(weapon["card_id"])
            if entry is None or entry.text or entry.mechanics:
                blockers.add("PASSIVE_WEAPON_EFFECT_UNREVIEWED")
    if forecast.status == Status.UNSUPPORTED:
        blockers.add(forecast.unsupported_reason or "OUTCOME_UNSUPPORTED")
    out["blockers"] = sorted(blockers)
    level = "CONDITIONAL" if blockers else "VERIFIED_LOCAL"
    for label, side, m, hp in (("source", "SELF", source, sh), ("target", "OPPONENT", target, th)):
        ref = Ref(side, "BOARD", m["board_position"], m["card"]["card_id"])
        events = [e for e in forecast.events if e.subject == ref]
        packets = [e.amount for e in events if e.kind == "DAMAGE"]
        if len(packets) != 1 or packets[0] is None:
            for suffix in ("damage_packet", "shield_removed", "body_dies", "health_after_packet"):
                p[label + "_" + suffix] = fact(reasons=blockers or ["PACKET_UNAVAILABLE"])
            continue
        damage = packets[0]
        dead = any(e.kind == "DEATH" for e in events)
        shield = any(c.ref == ref and c.field == "divine_shield" and c.before is True and c.after is False
                     for c in forecast.changes)
        for suffix, value in (("damage_packet", damage), ("shield_removed", shield),
                              ("body_dies", dead), ("health_after_packet", hp - damage)):
            p[label + "_" + suffix] = fact(value, level, blockers, CONDITIONS)
    return out
