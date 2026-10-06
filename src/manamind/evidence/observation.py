"""Assemble sanitized observation records: one per (root window, subject card)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from . import EVIDENCE_LIMITS, OBSERVATION_SCHEMA
from .attribution import relative
from .confounders import build_confounders
from .entities import Redactor
from .facts import SEMANTIC_KINDS, RawFact, build_facts
from .inferences import build_inferences
from .support import SupportInventory
from .walker import Unit, Window

FACT_CAP = 300
SYSTEM_TYPES = frozenset({"GAME", "PLAYER"})
CLAIM_KINDS = (
    "DAMAGE_AMOUNT", "HEAL_AMOUNT", "TARGET_CLASS_OBSERVED", "TARGET_LEGALITY_REQUIREMENT", "SUMMON_OUTCOME",
    "TRANSFORM_OUTCOME", "GENERATED_OUTCOME_SET", "ENCHANTMENT_APPLIED", "STAT_DELTA", "COST_MODIFICATION",
    "CONDITIONAL_EFFECT", "TRIGGER_STEP", "DEATHRATTLE_OUTCOME", "CHOICE_OFFER", "ZONE_MOVE", "NO_VISIBLE_EFFECT",
)
TURN_PHASE_STEPS = frozenset({"MAIN_START", "MAIN_START_TRIGGERS", "MAIN_END", "MAIN_CLEANUP", "MAIN_NEXT", "MAIN_READY"})
TAG_BASES = frozenset({"CREATOR_TAG", "LAST_AFFECTED_BY_SAME_UNIT"})
OWN_BASES = TAG_BASES | {"UNIT_OWNER"}
DELTA_FIELDS = ("hero_health", "armor", "available_mana", "hand_size", "deck_size", "secret_count")


@dataclass
class GameContext:
    game_key16: str
    client_build: int | None
    game_type: str
    format_type: str
    rules_scope: str
    source_kind: str
    catalog_sha256: str
    extractor_version: str
    parser_versions: dict
    redactor: Redactor
    inventory: SupportInventory
    scope: object
    max_control_samples: int = 3
    control_counts: dict[str, int] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def bump(self, key: str, amount: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + amount


def _role(window: Window, unit: Unit, view) -> str:
    root = window.units[0]
    if unit.unit_id == "u0" or (unit.owner == root.owner and root.block_type in ("PLAY", "ATTACK")):
        if root.block_type == "PLAY":
            return {"HERO_POWER": "HERO_POWER_USE", "LOCATION": "LOCATION_ACTIVATION"}.get(
                view.card_type or "", "PLAYED_CARD")
        if root.block_type == "ATTACK":
            return "ATTACKER"
    if unit.keyword in ("DEATHRATTLE", 217):
        return "DEATHRATTLE_SOURCE"
    if view.card_type == "ENCHANTMENT":
        return "ENCHANTMENT_SOURCE"
    if view.zone == "SECRET":
        return "SECRET_OR_QUEST_SOURCE"
    if window.root_type == "TRIGGER" and window.step in TURN_PHASE_STEPS:
        return "TURN_PHASE_TRIGGER_SOURCE"
    return "TRIGGER_SOURCE"


def _public_delta(before: dict | None, after: dict | None) -> list[str]:
    if before is None or after is None:
        return []
    lines: list[str] = []
    for label, key in (("SELF", "self_player"), ("OPP", "opponent")):
        for name in DELTA_FIELDS:
            a, b = before[key].get(name), after[key].get(name)
            if a != b:
                lines.append(f"{label}.{name}: {a} -> {b}")
        boards = []
        for state in (before, after):
            boards.append([f"{e['card']['card_id']} {e['current_attack']}/{e['current_health']}"
                           for e in state[key].get("board", [])])
        if boards[0] != boards[1]:
            lines.append(f"{label}.board: [{', '.join(boards[0])}] -> [{', '.join(boards[1])}]")
    return lines[:40]


def _fact_dict(fact: RawFact, window: Window, subject: int, redactor: Redactor) -> dict:
    basis = relative(fact.basis, fact.attributed, subject)
    attribution: dict = {"basis": basis}
    if basis != "UNATTRIBUTED" and fact.attributed is not None:
        ref, _ = redactor.ref(window.final.get(fact.attributed), handle=fact.attributed)
        attribution["attributed_to"] = ref
        if len(fact.chain) > 1:
            attribution["via_creator_chain"] = fact.chain
    return {
        "fact_id": fact.fact_id, "kind": fact.kind, "unit_id": fact.unit_id, "visibility": fact.visibility,
        "raw_ref": {"packet_ordinal": fact.ordinal}, "attribution": attribution, "data": fact.data,
    }


def _legality(window: Window, subject: int, redactor: Redactor, start: int) -> list[RawFact]:
    out: list[RawFact] = []
    options = window.options
    root = window.units[0]
    if options is None or root.block_type != "PLAY" or root.owner != subject:
        return out
    for entry in options.entries:
        if entry.main != subject:
            continue
        main_view = window.final.get(subject)
        if main_view is None or redactor.side(main_view.controller) != "SELF":
            continue
        card_ref, _ = redactor.ref(main_view, handle=subject)
        base = {"option_card": card_ref, "options_id": options.options_id, "option_accepted": entry.accepted}
        rows = entry.targets or [(None, None, None, None)]
        for handle, view, code, parent in rows:
            target_ref = redactor.ref(view, handle=handle)[0] if handle is not None else None
            out.append(RawFact(
                fact_id=f"f{start + len(out)}", kind="TARGET_LEGALITY", unit_id="u0", ordinal=root.ordinal,
                visibility="SELF_PRIVATE", basis="UNIT_OWNER", attributed=subject,
                data={**base, "target": target_ref, "accepted": code is None and entry.accepted,
                      "server_error_code": code, "sub_option_of": parent},
                handle=subject,
            ))
    return out


def build_observations(window: Window, ctx: GameContext) -> list[dict]:
    redactor, inventory = ctx.redactor, ctx.inventory
    facts_all = build_facts(window, redactor)
    units = {u.unit_id: u for u in window.units}
    semantic_units = {e.unit for e in window.events if e.semantic and e.unit}
    if not window.units:
        return []
    root = window.units[0]

    candidates: dict[int, Unit] = {}
    if root.block_type in ("PLAY", "ATTACK") and root.owner is not None:
        candidates[root.owner] = root
    for unit in window.units:
        if unit.owner is not None and unit.unit_id in semantic_units and unit.owner not in candidates:
            candidates[unit.owner] = unit

    observations: list[dict] = []
    for handle, first_unit in candidates.items():
        view = window.final.get(handle)
        if view is None or view.card_type in SYSTEM_TYPES or not view.card_id:
            continue
        card_id = redactor.public_card_id(view)
        if card_id is None:
            ctx.bump("subjects_skipped_hidden_identity")
            continue
        state = inventory.state(card_id)
        supported = inventory.is_supported(card_id)
        if supported:
            if ctx.control_counts.get(card_id, 0) >= ctx.max_control_samples:
                continue
            ctx.control_counts[card_id] = ctx.control_counts.get(card_id, 0) + 1
        role = "CONTROL_SAMPLE" if supported else _role(window, first_unit, view)
        own_ids = {u.unit_id for u in window.units if u.owner == handle}
        observations.append(_assemble(window, ctx, handle, card_id, state, role, view, own_ids,
                                      facts_all, semantic_units, units))
    return observations


def _assemble(window, ctx, handle, card_id, state, role, view, own_ids, facts_all, semantic_units, units) -> dict:
    redactor, inventory = ctx.redactor, ctx.inventory
    first_own = min(own_ids, key=lambda u: units[u].ordinal)
    facts = list(facts_all)
    next_id = len(facts) + 1
    for unit_id in sorted(own_ids, key=lambda u: units[u].ordinal):
        unit = units[unit_id]
        facts.append(RawFact(
            fact_id=f"f{next_id}", kind="BLOCK_STRUCTURE", unit_id=unit_id, ordinal=unit.ordinal,
            visibility="PUBLIC_TO_SELF", basis="UNIT_OWNER", attributed=handle,
            data={"block_type": unit.block_type, "owner_handle": handle, "parent_unit_id": unit.parent,
                  "depth": unit.depth, "trigger_keyword": unit.keyword},
        ))
        next_id += 1
    legality = _legality(window, handle, redactor, next_id)
    facts.extend(legality)
    truncated = max(0, len(facts_all) - FACT_CAP)
    if truncated:
        keep = {f.fact_id for f in facts_all[:FACT_CAP]}
        facts = [f for f in facts if f.fact_id in keep or f.kind in ("BLOCK_STRUCTURE", "TARGET_LEGALITY")]
    facts.sort(key=lambda f: (f.ordinal, int(f.fact_id[1:])))

    inferences = build_inferences(window, facts, sorted(own_ids), view.card_type)
    confounders = build_confounders(window, redactor, handle, own_ids, facts, semantic_units)
    if ctx.rules_scope != "STANDARD_PRIMARY":
        confounders.append({"kind": "MODE_OR_BUILD_OUTSIDE_SCOPE", "affects_claim_kinds": list(CLAIM_KINDS),
                            "note": "not Ranked/Casual Standard; never mixed into primary aggregates"})

    fact_dicts = [_fact_dict(f, window, handle, redactor) for f in facts]
    effects = [f for f in fact_dicts if _is_effect(f, handle)]
    own_effects = [f for f in effects if f["attribution"]["basis"] in OWN_BASES]
    unattributed_own = [f for f in effects if f["attribution"]["basis"] == "UNATTRIBUTED" and f["unit_id"] in own_ids]
    own_kinds = {k for f in own_effects for k in _claim_kinds(f)}
    confounded_kinds = sorted({k for c in confounders for k in c["affects_claim_kinds"]})
    if any(f["attribution"]["basis"] in TAG_BASES for f in own_effects):
        tier = "CREATOR_OR_SAME_UNIT"
    elif own_effects:
        tier = "UNIT_OWNER_ONLY"
    else:
        tier = "NO_ATTRIBUTED_EFFECTS"
    summary = {
        "tier": tier,
        "own_effect_facts": len(own_effects),
        "nested_only_facts": sum(1 for f in effects if f["attribution"]["basis"] == "NESTED_ONLY"),
        "unattributed_effect_facts": sum(1 for f in effects if f["attribution"]["basis"] == "UNATTRIBUTED"),
        "ambiguous": bool(unattributed_own) or bool(own_kinds & set(confounded_kinds)),
        "confounded_claim_kinds": confounded_kinds,
    }

    stored: set[str] = set(own_ids) | {"u0"} | (semantic_units & set(units))
    for unit_id in list(stored):
        parent = units[unit_id].parent
        while parent is not None:
            stored.add(parent)
            parent = units[parent].parent
    unit_dicts, empty_watchers = [], 0
    related: set[str] = set()
    for unit in window.units:
        if unit.unit_id not in stored:
            if unit.block_type == "TRIGGER":
                empty_watchers += 1
            continue
        owner_view = window.final.get(unit.owner) if unit.owner is not None else None
        owner_ref, _ = redactor.ref(owner_view, handle=unit.owner)
        if unit.unit_id == "u0":
            relation = "ROOT"
        elif unit.owner == handle:
            relation = "SUBJECT_OWN"
        elif owner_view is None or not owner_view.card_id:
            relation = "SYSTEM"
        else:
            relation = "REACTION"
        if owner_ref.get("card_id") and unit.owner != handle:
            related.add(owner_ref["card_id"])
        unit_dicts.append({
            "unit_id": unit.unit_id, "block_type": unit.block_type, "owner": owner_ref,
            "parent_unit_id": unit.parent, "depth": unit.depth, "trigger_keyword": unit.keyword,
            "has_semantic_effects": unit.unit_id in semantic_units, "relation_to_subject": relation,
        })
    for fact in fact_dicts:
        for key in ("entity", "enchantment"):
            ref = fact["data"].get(key)
            if isinstance(ref, dict) and ref.get("card_id") and fact["kind"] in (
                    "ENTITY_CREATED", "ENCHANTMENT_ATTACHED", "ENTITY_TRANSFORMED"):
                related.add(ref["card_id"])
    related.discard(card_id)
    unsupported_ids = sorted(c for c in related | {card_id} if not inventory.is_supported(c))
    hidden_count = sum(1 for f in fact_dicts if f["visibility"] == "OFFLINE_ONLY_HIDDEN")

    key = f"{ctx.game_key16}|{window.ordinal}|{first_own}|{ctx.extractor_version}|{handle}"
    observation_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    unknown = sorted(window.unknown_tag_ids)
    return {
        "schema": OBSERVATION_SCHEMA,
        "observation_id": observation_id,
        "subject": {
            "card_id": card_id, "role": role, "side": redactor.side(view.controller),
            "registry_scope": ctx.scope.scope(card_id), "related_card_ids": sorted(related),
        },
        "provenance": {
            "source": "POWER_LOG", "source_kind": ctx.source_kind, "game_key16": ctx.game_key16,
            "client_build": ctx.client_build, "game_type": ctx.game_type, "format_type": ctx.format_type,
            "rules_scope": ctx.rules_scope, "turn": window.turn, "step": window.step,
            "root_packet_ordinal": window.root_ordinal, "extractor_version": ctx.extractor_version,
            "catalog_sha256": ctx.catalog_sha256, "hslog_version": ctx.parser_versions["hslog"],
            "hearthstone_pkg_version": ctx.parser_versions["hearthstone"], "unknown_tag_ids_in_window": unknown,
        },
        "window": {
            "root_block_type": window.root_type if window.root_type in (
                "PLAY", "ATTACK", "TRIGGER", "DEATHS", "POWER", "DECK_ACTION") else "OTHER",
            "root_ordinal": window.ordinal, "units": unit_dicts,
            "empty_watcher_trigger_count": empty_watchers, "facts_truncated": truncated,
        },
        "public_states": {
            "before_hash": window.before_hash, "after_hash": window.after_hash,
            "public_delta": _public_delta(window.before_state, window.after_state),
        },
        "support_detection": {
            "inventory_id": inventory.inventory_id, "inventory_sha256": inventory.sha256,
            "basis": inventory.basis, "subject_support_state": state, "window_unsupported_card_ids": unsupported_ids,
        },
        "facts": fact_dicts,
        "inferences": inferences,
        "confounders": confounders,
        "attribution_summary": summary,
        "triage": "NOVEL_OBSERVATION" if role != "CONTROL_SAMPLE" else "CONTROL_UNCOMPARED",
        "evidence_limits": list(EVIDENCE_LIMITS),
        "privacy": {
            "contains_offline_only_hidden": hidden_count > 0, "hidden_fact_count": hidden_count,
            "model_input_allowed": False, "names_removed": True,
        },
    }


def _is_effect(fact: dict, subject: int) -> bool:
    """A semantic fact; the subject's own zone move (hand to play, play to graveyard) is bookkeeping."""
    if fact["kind"] not in SEMANTIC_KINDS:
        return False
    return not (fact["kind"] == "ZONE_MOVE" and fact["data"]["entity"]["handle"] == subject)


def _claim_kinds(fact: dict) -> list[str]:
    from .confounders import KIND_TO_CLAIMS

    if fact["kind"] == "STAT_DELTA" and fact["data"].get("tag") == "COST":
        return ["COST_MODIFICATION"]
    return KIND_TO_CLAIMS.get(fact["kind"], [])
