"""Build the dated Standard card registry, dependency inventory, admission report and queues."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.standard_profile import load_profile, profile_path, engine_identity, execution_identity
from scripts.verification_evidence import scoped_status
from scripts.registry_admission import training_blockers, derive_admission
PREVIOUS_AUDIT = ROOT / "reports/card_support_analysis_20260929.json"
CAPABILITIES = ROOT / "integrations/rosettastone/card_rules/capabilities.json"
ALIASES = ROOT / "integrations/rosettastone/card_rules/core_aliases.generated.json"
CORE_ALIAS_EVIDENCE = ROOT / "integrations/rosettastone/card_rules/core_aliases.evidence.json"
COMPOSITIONS = ROOT / "integrations/rosettastone/card_rules/effect_composition.generated.json"
AFTER_ATTACK_DRAW = ROOT / "integrations/rosettastone/card_rules/after_attack_draw.generated.json"
AFTER_ATTACK_DRAW_EVIDENCE = ROOT / "integrations/rosettastone/card_rules/after_attack_draw.evidence.json"
REPEATED_TRIGGER_DRAW = ROOT / "integrations/rosettastone/card_rules/repeated_trigger_draw.generated.json"
REPEATED_TRIGGER_DRAW_EVIDENCE = ROOT / "integrations/rosettastone/card_rules/repeated_trigger_draw.evidence.json"
FILTERED_SCHOOL_DRAW = ROOT / "integrations/rosettastone/card_rules/filtered_school_draw.generated.json"
FILTERED_SCHOOL_DRAW_EVIDENCE = ROOT / "integrations/rosettastone/card_rules/filtered_school_draw.evidence.json"
KEYWORD_ONLY = ROOT / "integrations/rosettastone/card_rules/keyword_only.generated.json"
METADATA_ONLY = ROOT / "integrations/rosettastone/card_rules/metadata_only.generated.json"
MINION_SET_ENCHANT = ROOT / "integrations/rosettastone/card_rules/minion_set_enchant.generated.json"
CARD_RESOURCE = ROOT / "vendor/RosettaStone/Resources/cards.json"
SOURCE_DIR = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets"

POOL_PATTERNS = [
    ("discover", re.compile(r"\bdiscover\b", re.I)),
    ("random_card_or_pool", re.compile(
        r"\b(?:random|randomly)\b.{0,60}\b(?:cards?|spells?|weapons?|dragons?|demons?|beasts?|deathrattles?|classes?|auras?)\b"
        r"|\b(?:summon|resurrect|create|generate|add|get|transform|cast|shuffle|put)\b.{0,60}"
        r"\b(?:random|randomly)\b.{0,40}\bminions?\b"
        r"|\b(?:random|randomly)\b(?!\s+(?:enemy|friendly|opposing|opponent|adjacent|other)\b)"
        r".{0,50}\bminions?\b", re.I)),
    ("generated_card", re.compile(
        r"\b(?:resurrect|summon|add|put|shuffle|copy|transform|return|recruit|draw|eat|devour|steal|trigger|discard|destroy)\b.{0,100}"
        r"\b(?:from (?:(?:your opponent[^\w]{0,2}s|your|opponent[^\w]{0,2}s) |the (?:opponent[^\w]{0,2}s )?)(?:hand|deck|graveyard)|"
        r"in (?:(?:your opponent[^\w]{0,2}s|your|opponent[^\w]{0,2}s) |the (?:opponent[^\w]{0,2}s )?)(?:hand|deck|graveyard)|"
        r"you(?:'ve| have) played|killed by|died this game|copy of|copy (?:into|to)|"
        r"each (?:minion|card)|lowest.cost (?:card|minion) in|last minion (?:your|your opponent|opponent) played)\b"
        r"|\bresurrect\b.{0,100}\bminions?\b", re.I)),
]
ACTION_PATTERNS = {
    "damage": re.compile(r"\bdeal(?:s)?\b", re.I),
    "summon": re.compile(r"\bsummon(?:s|ed)?\b", re.I),
    "draw": re.compile(r"\bdraw(?:s|n)?\b", re.I),
    "heal": re.compile(r"\brestore(?:s|d)?\b|\bheal(?:s|ed)?\b", re.I),
    "destroy": re.compile(r"\bdestroy(?:s|ed)?\b", re.I),
    "discover_choice": re.compile(r"\bdiscover\b|\bchoose\b|\bchoice\b", re.I),
    "transform_copy": re.compile(r"\btransform\b|\bcopy\b|\bcopies\b", re.I),
    "triggered": re.compile(r"\b(battlecry|deathrattle|after|whenever|when|at the start|at the end)\b", re.I),
    "resource_cost": re.compile(r"\b(cost|mana|armor|attack|health)\b", re.I),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value.replace(b"\r\n", b"\n")).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def reachable_closure(adjacency: dict[str, list[str]], start: str) -> set[str]:
    """Cycle-safe reachable node set; returns dependencies and excludes the start node."""
    seen: set[str] = set()
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for destination in adjacency.get(current, []):
            if destination not in seen:
                seen.add(destination)
                queue.append(destination)
    seen.discard(start)
    return seen


def evidence_freshness(evidence: dict[str, Any], current: dict[str, Any]) -> str:
    """Exact fingerprint match is required; predicate version matters even with equal membership."""
    keys = ("rules_fingerprint", "pool_membership_sha256", "pool_predicate_version", "capability_fingerprint", "engine_build_fingerprint", "scenario_fingerprint")
    if any(key not in evidence or key not in current for key in keys):
        return "STALE_OR_INCOMPLETE"
    return "CURRENT" if all(evidence[key] == current[key] for key in keys) else "STALE"


def norm_text(value: str) -> str:
    return re.sub(r"<[^>]+>|\[[^]]+\]|[^a-z0-9]+", " ", value.lower()).strip()


def dynamic_pool_hypotheses(text: str) -> list[str]:
    """Return candidate pool signals; random board targets and fixed tokens are not pools."""
    plain_text = re.sub(r"<[^>]*>", " ", text)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    clauses = [part.strip() for part in re.split(r"[.!?;:]|\b(?:or|then)\b", plain_text, flags=re.I) if part.strip()]
    return [kind for kind, pattern in POOL_PATTERNS if any(pattern.search(part) for part in clauses)]


def collect_card_blocks() -> dict[str, dict[str, Any]]:
    blocks: dict[str, dict[str, Any]] = {}
    for path in sorted(SOURCE_DIR.glob("*CardsGen.cpp")):
        source = path.read_text(encoding="utf-8", errors="replace")
        clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
        matches = list(re.finditer(r"cards\.emplace\(\s*\"([^\"]+)\"", clean))
        for index, match in enumerate(matches):
            start = clean.rfind(".ClearData();", 0, match.start())
            start = max(0, clean.rfind("\n", 0, start) + 1) if start >= 0 else max(0, match.start() - 1200)
            end = matches[index + 1].start() if index + 1 < len(matches) else min(len(clean), match.end() + 5000)
            next_clear = clean.find(".ClearData();", match.end())
            if next_clear >= 0:
                end = min(end, next_clear)
            block = clean[start:end]
            blocks[match.group(1)] = {
                "source_file": path.relative_to(ROOT).as_posix(),
                "task_types": sorted(set(re.findall(r"make_shared<([A-Za-z0-9_]+Task)>", block))),
                "has_trigger": "AddTrigger" in block or "GetTrigger()" in block,
                "has_aura": "AddAura" in block or "GetAura()" in block,
                "has_enchantment": "AddEnchantment" in block or "GetEnchant" in block,
                "referenced_card_ids": sorted(set(re.findall(r'"([A-Z][A-Z0-9]*_[A-Z0-9]+[a-zA-Z0-9]*)"', block)) - {match.group(1)}),
            }
    return blocks


def route_for(meta: dict[str, Any], block: dict[str, Any] | None, generated: str | None) -> tuple[str, str]:
    text = meta.get("text", "")
    if not norm_text(text):
        return "AUTO", "No rules text in the pinned source metadata; metadata-only route proposal, still requires runtime and interaction checks."
    if generated == "effect_composition":
        return "COMPOSABLE", "Present in the allowlisted effect-composition generated manifest; proposal does not certify full rule correctness."
    if generated == "core_alias":
        return "COMPOSABLE", "Present in the bounded generated Core-alias manifest; copy equivalence and dependency closure remain separately gated."
    if generated == "rule_alias":
        return "COMPOSABLE", "Present in the allowlisted exact-text CardDef reuse package; text equality and copy semantics remain separately gated."
    if generated == "after_attack_draw":
        return "COMPOSABLE", "Present in the narrow after-attack/draw generated manifest; scoped tests and deck-dependent draw outcomes remain separate gates."
    if generated == "repeated_trigger_draw":
        return "COMPOSABLE", "Present in the narrow Battlecry/Deathrattle draw manifest; scoped tests and deck-dependent draw outcomes remain separate gates."
    if generated == "filtered_school_draw":
        return "COMPOSABLE", "Present in the allowlisted Deathrattle spell-school draw package; deck membership and full profile gates remain separate."
    if generated == "minion_set_enchant":
        return "COMPOSABLE", "Versioned reusable minion-set contract; rules, closure and actions require independent current evidence."
    if generated == "keyword_only":
        return "AUTO", "Present in the strict keyword-only CardDef generator; keyword behavior and bridge actions remain separate verification gates."
    if generated == "metadata_only":
        return "AUTO", "Present in the textless, mechanic-free CardDef generator; metadata-only inference is not independent rules verification."
    if not block:
        return "UNKNOWN", "No direct source CardDef block or recognized generated registration was found by the source inventory."
    if "CustomTask" in block["task_types"]:
        return "CUSTOM", "Source block contains CustomTask; native route proposal, exact behavior still requires scoped review."
    if block["has_trigger"] or block["has_aura"] or len(block["task_types"]) > 1:
        return "COMPOSABLE", "Source inventory suggests multiple tasks, trigger, or aura composition; exact contracts are not certified."
    if len(block["task_types"]) <= 1:
        return "AUTO", "Source inventory suggests metadata-only or single-task handling; validate the exact contract before generator reuse."
    return "UNKNOWN", "Available source evidence is insufficient to propose a route."


def evidence_status(card_id: str, old_cards: dict[str, dict[str, Any]], current_text_hash: str) -> dict[str, Any]:
    old = old_cards.get(card_id)
    if not old:
        return {"status": "NO_SCOPED_EVIDENCE", "historical_status": None, "reason": "No entry in the 2026-09-29 scoped audit."}
    prior = old.get("verification_status")
    evidence = old.get("verification_evidence")
    if prior == "VERIFIED_SCOPED" and evidence:
        return {
            "status": "STALE", "historical_status": prior,
            "reason": "Historical scenario evidence lacks a complete reproducible execution/source fingerprint for this pinned registry build; retained as history, not current PASS.",
            "historical_evidence": evidence,
            "text_fingerprint_matches": old.get("rules_text_sha256") == current_text_hash if old.get("rules_text_sha256") else None,
        }
    if prior in {"IMPLEMENTED_UNVERIFIED", "UNSUPPORTED"}:
        return {"status": "NO_SCOPED_EVIDENCE", "historical_status": prior, "reason": "Prior inventory status is not scoped verification evidence."}
    return {"status": "NO_SCOPED_EVIDENCE", "historical_status": prior, "reason": "No valid scoped evidence in the historical audit."}


def build_registry(roots_doc: dict[str, Any], *, profile: dict | None = None, identity: dict | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = profile or load_profile()
    source_identity = engine_identity()
    identity = identity or execution_identity(profile)
    evidence_documents = [read_json(ROOT / path) for path in profile.get("verification_evidence", []) if (ROOT / path).exists()]
    card_evidence = {}
    for document in evidence_documents:
        for evidence_id in document.get("cards", {}):
            if evidence_id in card_evidence:
                raise ValueError(f"Conflicting evidence owners: {evidence_id}")
            card_evidence[evidence_id] = (document, scoped_status(document, evidence_id, identity))
    gate_path = profile.get("session_match_evidence")
    gate_doc = read_json(ROOT / gate_path) if gate_path and (ROOT / gate_path).exists() else {}
    session_match_current = gate_doc.get("execution_identity") == identity and gate_doc.get("scope") == "FULL_PROFILE" and gate_doc.get("session_status") == "PASS" and gate_doc.get("match_status") == "PASS"
    source_bytes = profile_path(profile, "metadata_snapshot").read_bytes()
    resource_cards_list = read_json(CARD_RESOURCE)
    resources = {c["id"]: c for c in resource_cards_list if c.get("id")}
    all_metadata = {row["id"]: row for row in json.loads(source_bytes.decode("utf-8-sig")) if row.get("id")}
    root_items = {entry["card_id"]: entry for entry in roots_doc["roots"]}
    root_ids = set(root_items)
    blocks = collect_card_blocks()
    alias_doc = read_json(ALIASES) if ALIASES.exists() else {"cards": []}
    composition_doc = read_json(COMPOSITIONS) if COMPOSITIONS.exists() else {"cards": []}
    attack_draw_doc = read_json(AFTER_ATTACK_DRAW) if AFTER_ATTACK_DRAW.exists() else {"cards": []}
    repeated_draw_doc = read_json(REPEATED_TRIGGER_DRAW) if REPEATED_TRIGGER_DRAW.exists() else {"cards": []}
    filtered_school_draw_doc = read_json(FILTERED_SCHOOL_DRAW) if FILTERED_SCHOOL_DRAW.exists() else {"cards": []}
    keyword_only_doc = read_json(KEYWORD_ONLY) if KEYWORD_ONLY.exists() else {"cards": []}
    metadata_only_doc = read_json(METADATA_ONLY) if METADATA_ONLY.exists() else {"cards": []}
    minion_set_doc = read_json(MINION_SET_ENCHANT) if MINION_SET_ENCHANT.exists() else {"cards": []}
    ban_path = profile_path(profile, "bans")
    ban_doc = read_json(ban_path) if ban_path.exists() else {"format_bans": {"STANDARD": []}}
    standard_bans = set(ban_doc.get("format_bans", {}).get("STANDARD", []))
    aliases = {c["card_id"]: c for c in alias_doc.get("cards", [])}
    compositions = {c["card_id"]: c for c in composition_doc.get("cards", [])}
    attack_draw = {c["card_id"]: c for c in attack_draw_doc.get("cards", [])}
    repeated_draw = {c["card_id"]: c for c in repeated_draw_doc.get("cards", [])}
    filtered_school_draw = {c["card_id"]: c for c in filtered_school_draw_doc.get("cards", [])}
    keyword_only = {c["card_id"]: c for c in keyword_only_doc.get("cards", [])}
    metadata_only = {c["card_id"]: c for c in metadata_only_doc.get("cards", [])}
    minion_set = {c["card_id"]: c for c in minion_set_doc.get("cards", [])}
    generated_card_ids = set(aliases) | set(compositions) | set(attack_draw) | set(repeated_draw) | set(filtered_school_draw) | set(keyword_only) | set(metadata_only) | set(minion_set)
    # Generated C++ is an output format, not independent source evidence. Parsing
    # neighboring generated IDs as literal dependencies creates false graph edges.
    blocks = {card_id: block for card_id, block in blocks.items() if card_id not in generated_card_ids}
    previous = read_json(PREVIOUS_AUDIT) if PREVIOUS_AUDIT.exists() else {"cards": []}
    old_cards = {c["card_id"]: c for c in previous.get("cards", [])}
    capabilities = read_json(CAPABILITIES) if CAPABILITIES.exists() else {}
    root_metadata_hash = canonical_hash([{"id": cid, "metadata": root_items[cid]["metadata"]} for cid in sorted(root_ids)])

    # Literal CardDef IDs are candidate edges only. They are never elevated to reviewed rule dependencies here.
    edge_map: dict[tuple[str, str], dict[str, Any]] = {}
    for source_id in sorted(root_ids):
        block = blocks.get(source_id)
        base_id = aliases.get(source_id, {}).get("base_card_id")
        if block is None and base_id:
            block = blocks.get(base_id)
        generated_deps: list[str] = []
        if source_id in aliases:
            generated_deps.extend(d.get("card_id") for d in aliases[source_id].get("dependencies", []) if d.get("card_id"))
        if source_id in compositions:
            generated_deps.extend(compositions[source_id].get("dependencies", []))
        if source_id in minion_set:
            generated_deps.extend(minion_set[source_id].get("dependencies", []))
        for dep_id in ((block or {}).get("referenced_card_ids", []) + generated_deps):
            if dep_id == source_id:
                continue
            dest = all_metadata.get(dep_id) or resources.get(dep_id)
            kind = "enchantment_or_object_reference" if dest and dest.get("type") == "ENCHANTMENT" else "literal_card_id_reference"
            key = (source_id, dep_id)
            edge_map[key] = {
                "from": source_id, "to": dep_id, "kind": kind,
                "evidence_status": "UNREVIEWED_SOURCE_CANDIDATE",
                "evidence_source": "generated_manifest" if dep_id in generated_deps else "nearest_CardDef_source_block",
                "destination_known": dest is not None,
                "destination_name": (dest or {}).get("name"),
                "destination_type": (dest or {}).get("type"),
                "destination_collectible": (dest or {}).get("collectible"),
                "destination_is_standard_root": dep_id in root_ids,
            }
    for alias in aliases.values():
        source_id = alias["card_id"]
        if source_id in root_ids:
            key = (source_id, alias["base_card_id"])
            exact_text_alias = alias.get("match_basis") == "EXPLICIT_EXACT_RULES_TEXT_MATCH"
            edge_map[key] = {"from": source_id, "to": alias["base_card_id"], "kind": "generated_exact_text_alias_base" if exact_text_alias else "generated_core_alias_base", "evidence_status": "DECLARATION_ALLOWLISTED_RULES_EQUIVALENCE_NOT_FULLY_VERIFIED", "evidence_source": "core_aliases.generated.json", "destination_known": alias["base_card_id"] in resources or alias["base_card_id"] in all_metadata, "destination_name": alias.get("name"), "destination_type": None, "destination_collectible": None, "destination_is_standard_root": alias["base_card_id"] in root_ids}

    # Follow source references recursively. This remains a lower bound because only
    # literal IDs and allowlisted generated manifests are discoverable statically.
    queued = deque(edge["to"] for edge in edge_map.values())
    expanded: set[str] = set()
    while queued:
        source_id = queued.popleft()
        if source_id in expanded:
            continue
        expanded.add(source_id)
        block = blocks.get(source_id)
        if block is None:
            continue
        for dep_id in block["referenced_card_ids"]:
            if dep_id == source_id:
                continue
            dest = all_metadata.get(dep_id) or resources.get(dep_id)
            key = (source_id, dep_id)
            if key not in edge_map:
                edge_map[key] = {
                    "from": source_id, "to": dep_id,
                    "kind": "enchantment_or_object_reference" if dest and dest.get("type") == "ENCHANTMENT" else "literal_card_id_reference",
                    "evidence_status": "UNREVIEWED_SOURCE_CANDIDATE", "evidence_source": "nearest_CardDef_source_block",
                    "destination_known": dest is not None, "destination_name": (dest or {}).get("name"),
                    "destination_type": (dest or {}).get("type"), "destination_collectible": (dest or {}).get("collectible"),
                    "destination_is_standard_root": dep_id in root_ids,
                }
                queued.append(dep_id)

    pool_defs: dict[str, dict[str, Any]] = {}
    node_pool_ids: dict[str, list[str]] = defaultdict(list)
    card_rows: dict[str, dict[str, Any]] = {}
    core_alias_ids = {card_id for card_id, entry in aliases.items()
                      if entry.get("match_basis") != "EXPLICIT_EXACT_RULES_TEXT_MATCH"}
    rule_alias_ids = set(aliases) - core_alias_ids
    for card_id in sorted(root_ids):
        entry = root_items[card_id]
        meta = entry["metadata"]
        block = blocks.get(card_id)
        generated_owner = next((owner for owner, entries in (
            ("effect_composition", compositions), ("core_alias", core_alias_ids), ("rule_alias", rule_alias_ids),
            ("after_attack_draw", attack_draw), ("repeated_trigger_draw", repeated_draw),
            ("filtered_school_draw", filtered_school_draw),
            ("keyword_only", keyword_only),
            ("metadata_only", metadata_only),
            ("minion_set_enchant", minion_set),
        ) if card_id in entries), None)
        generated = generated_owner
        registration = {
            "effect_composition": "GENERATED_EFFECT_COMPOSITION",
            "core_alias": "GENERATED_CORE_ALIAS",
            "rule_alias": "GENERATED_EXACT_TEXT_ALIAS",
            "after_attack_draw": "GENERATED_AFTER_ATTACK_DRAW",
            "repeated_trigger_draw": "GENERATED_REPEATED_TRIGGER_DRAW",
            "filtered_school_draw": "GENERATED_FILTERED_SCHOOL_DRAW",
            "keyword_only": "GENERATED_KEYWORD_ONLY",
            "metadata_only": "GENERATED_METADATA_ONLY",
            "minion_set_enchant": "GENERATED_MINION_SET_ENCHANT",
        }.get(generated_owner, "DIRECT_SOURCE_BLOCK" if block else ("NO_DETECTED_RULE_REGISTRATION" if norm_text(meta.get("text", "")) else "TEXTLESS_METADATA"))
        route, route_reason = route_for(meta, block, generated)
        text_hash = canonical_hash(norm_text(meta.get("text", "")))
        hist = evidence_status(card_id, old_cards, text_hash)
        if card_id in card_evidence:
            _, hist = card_evidence[card_id]
        if not norm_text(meta.get("text", "")):
            rules_status = "METADATA_ONLY_CANDIDATE"
        elif registration.startswith("GENERATED_") or registration == "DIRECT_SOURCE_BLOCK":
            rules_status = "IMPLEMENTED_UNVERIFIED"
        else:
            rules_status = "UNKNOWN" if route == "UNKNOWN" else "UNSUPPORTED"
        if hist["status"] == "CURRENT":
            rules_status = "VERIFIED_SCOPED"
        evidence_row = card_evidence.get(card_id, ({}, {}))[0].get("cards", {}).get(card_id, {})
        if card_id in compositions and compositions[card_id].get("implementation_route") == "CUSTOM":
            route, route_reason = "CUSTOM", "Reviewed card-specific emitter; generated registration is not a reusable capability."
        dynamic = []
        for pool_kind in dynamic_pool_hypotheses(meta.get("text", "")):
            pid = f"POOL:{card_id}:{pool_kind}"
            pool_defs[pid] = {
                "pool_id": pid, "origin_card_id": card_id, "pool_kind_hypothesis": pool_kind,
                "definition_status": "UNRESOLVED_HEURISTIC_CANDIDATE",
                "predicate": None, "resolved_card_ids": None, "membership_sha256": None,
                "predicate_version": None, "rules_source": "pinned metadata text heuristic only",
                "engine_parity": "NOT_AUDITED",
                "limitation": "Text matching may be false positive or incomplete; state/history-dependent filtering and exact candidate membership are unknown.",
            }
            dynamic.append(pid)
            node_pool_ids[card_id].append(pid)
        if (block or {}).get("referenced_card_ids"):
            pass
        linked_edges = [edge for edge in edge_map.values() if edge["from"] == card_id]
        tasks = sorted(set((block or {}).get("task_types", [])))
        if card_id in attack_draw:
            tasks = sorted({"ArmorTask" if effect["op"] == "ARMOR" else "DrawTask"
                            for effect in attack_draw[card_id].get("effects", [])})
        if card_id in repeated_draw:
            effect_tasks = {"DRAW_SELF": "DrawTask", "DRAW_OPPONENT": "DrawOpTask",
                            "ARMOR_SELF_6": "ArmorTask"}
            tasks = sorted({effect_tasks[effect]
                            for slot in ("battlecry_effects", "deathrattle_effects")
                            for effect in repeated_draw[card_id].get(slot, [])})
        if card_id in filtered_school_draw:
            tasks = ["DrawSpellTask"]
        if card_id in minion_set:
            tasks = minion_set[card_id]["task_types"]
        mechanics = meta.get("mechanics", []) or []
        action_signals = sorted(key for key, pattern in ACTION_PATTERNS.items() if pattern.search(meta.get("text", "")))
        card_rows[card_id] = {
            "card_id": card_id,
            "identity": {"name": meta.get("name"), "card_class": meta.get("cardClass"), "type": meta.get("type"), "set": meta.get("set"), "dbf_id": meta.get("dbfId")},
            "metadata": {"present": True, "source_sha256": roots_doc["source_sha256"], "card_record_sha256": canonical_hash(meta), "rules_text_sha256_normalized": text_hash, "rules_text": meta.get("text", ""), "mechanics": mechanics, "collectible": meta.get("collectible") is True},
            "legality": {"root_pool": "STANDARD_COLLECTIBLE", "membership_reason": entry["membership_reason"], "ban_snapshot": profile["bans"], "ban_snapshot_as_of": ban_doc.get("format_bans_checked_at"), "banned_in_standard_snapshot": card_id in standard_bans, "deck_legal_status": "BANNED_IN_PINNED_SNAPSHOT" if card_id in standard_bans else "STANDARD_ROOT_NOT_BANNED_IN_PINNED_SNAPSHOT"},
            "implementation": {"route_proposal": route, "route_confidence": "HEURISTIC_SOURCE_AND_METADATA_REVIEW_REQUIRED", "route_reason": route_reason, "registration_status": registration, "source_file": (block or {}).get("source_file"), "task_types_observed": tasks, "generated_owner": generated, "generated_manifest_entry_sha256": canonical_hash(compositions.get(card_id) or aliases.get(card_id) or attack_draw.get(card_id) or repeated_draw.get(card_id) or filtered_school_draw.get(card_id) or keyword_only.get(card_id) or metadata_only.get(card_id)) if generated else None, "required_capabilities": tasks, "semantic_contract_reviewed": False},
            "rules_verification": {"status": rules_status, "evidence_validity": hist["status"], "evidence": hist, "training_scope": evidence_row.get("training_scope", "SCOPED_PACKAGE_ONLY")},
            "dependencies": {"known_source_candidates": [{"to": edge["to"], "kind": edge["kind"], "evidence_status": edge["evidence_status"]} for edge in linked_edges], "dynamic_pool_ids": dynamic, "static_dependency_status": "UNREVIEWED" if linked_edges else "NO_STATIC_SOURCE_REFERENCE_DETECTED_NOT_PROOF_OF_NONE", "dynamic_dependency_status": "UNRESOLVED" if dynamic else "NOT_DETECTED_BY_HEURISTIC_NOT_PROOF_OF_NONE"},
            "bridge_action_support": {"status": evidence_row.get("bridge_action_status", "NOT_AUDITED") if hist["status"] == "CURRENT" else "NOT_AUDITED", "evidence": None},
            "classifier_features": {"mechanics": mechanics, "action_signals": action_signals, "has_trigger_mechanic_metadata": bool(set(mechanics) & {"BATTLECRY", "DEATHRATTLE", "SPELLBURST", "FRENZY", "COMBO", "QUEST", "START_OF_GAME_KEYWORD"}), "metadata_and_text_only": True},
            "blockers": [],
        }
        if card_id in minion_set:
            implementation = card_rows[card_id]["implementation"]
            implementation.update({"implementation_kind": minion_set_doc["implementation_kind"],
                                   "contract_id": minion_set_doc["contract_id"],
                                   "contract_version": minion_set_doc["contract_version"],
                                   "package_id": minion_set_doc["package_id"],
                                   "generated_manifest_entry_sha256": canonical_hash(minion_set[card_id]),
                                   "semantic_contract_reviewed": hist["status"] == "CURRENT" and evidence_row.get("contract_review") == {
                                       "contract_id": minion_set_doc["contract_id"], "contract_version": minion_set_doc["contract_version"]}})

    edges = sorted(edge_map.values(), key=lambda e: (e["from"], e["to"], e["kind"]))
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge["from"]].append(edge["to"])
    reachable_dependency_ids = {edge["to"] for edge in edges} - root_ids
    dependency_nodes: dict[str, dict[str, Any]] = {}
    for dep_id in sorted(reachable_dependency_ids):
        meta = all_metadata.get(dep_id) or resources.get(dep_id)
        block = blocks.get(dep_id)
        generated = "effect_composition" if dep_id in compositions else ("rule_alias" if dep_id in rule_alias_ids else ("core_alias" if dep_id in core_alias_ids else None))
        if meta:
            for pool_kind in dynamic_pool_hypotheses(meta.get("text", "")):
                pid = f"POOL:{dep_id}:{pool_kind}"
                pool_defs[pid] = {
                    "pool_id": pid, "origin_card_id": dep_id, "pool_kind_hypothesis": pool_kind,
                    "definition_status": "UNRESOLVED_HEURISTIC_CANDIDATE", "predicate": None,
                    "resolved_card_ids": None, "membership_sha256": None, "predicate_version": None,
                    "rules_source": "pinned metadata text heuristic only", "engine_parity": "NOT_AUDITED",
                    "limitation": "Text matching may be false positive or incomplete; state/history-dependent filtering and exact candidate membership are unknown.",
                }
                node_pool_ids[dep_id].append(pid)
        dependency_nodes[dep_id] = {
            "card_id": dep_id, "metadata_status": "PRESENT" if meta else "UNKNOWN",
            "name": (meta or {}).get("name"), "type": (meta or {}).get("type"),
            "collectible": (meta or {}).get("collectible"), "is_standard_root": dep_id in root_ids,
            "registration_status": "DIRECT_SOURCE_BLOCK" if block else ("GENERATED_MANIFEST" if generated else "NO_DETECTED_REGISTRATION"),
            "source_file": (block or {}).get("source_file"), "task_types_observed": sorted(set((block or {}).get("task_types", []))),
            "rules_status": "IMPLEMENTED_UNVERIFIED" if block or generated else "UNKNOWN",
            "dependency_status": "UNREVIEWED", "unresolved_dynamic_pool_ids": sorted(node_pool_ids.get(dep_id, [])),
            "rules_verification": {"status": "VERIFIED_SCOPED" if card_evidence.get(dep_id, ({}, {}))[1].get("status") == "CURRENT" else "IMPLEMENTED_UNVERIFIED", "evidence_validity": card_evidence.get(dep_id, ({}, {}))[1].get("status", "NO_SCOPED_EVIDENCE"), "training_scope": card_evidence.get(dep_id, ({}, {}))[0].get("cards", {}).get(dep_id, {}).get("training_scope", "SCOPED_PACKAGE_ONLY")},
        }
        dependency_contract = minion_set_doc.get("dependencies", {}).get(dep_id)
        if dependency_contract:
            dependency_nodes[dep_id]["registration_status"] = "DECLARED_EXISTING_FIXED_ENCHANT_OWNER"
            dependency_nodes[dep_id]["source_file"] = dependency_contract["source_owner"]
            dependency_nodes[dep_id]["reviewed_contract"] = dependency_contract
    # Static source-reference closure is explicitly a lower bound; unresolved pools remain separate.
    closures: dict[str, dict[str, Any]] = {}
    for root_id in sorted(root_ids):
        seen = reachable_closure(adjacency, root_id)
        unresolved_pools = []
        reachable_known = seen | {root_id}
        for node in list(reachable_known):
            unresolved_pools.extend(node_pool_ids.get(node, []))
        closure = {"known_source_candidate_ids": sorted(seen), "known_unique_closure_count_including_root": len(seen | {root_id}), "closure_completeness": "INCOMPLETE_UNRESOLVED_DYNAMIC" if unresolved_pools else "INCOMPLETE_UNREVIEWED_STATIC_AND_DYNAMIC_HEURISTICS", "unresolved_dynamic_pool_ids": sorted(set(unresolved_pools))}
        closures[root_id] = closure
        row = card_rows[root_id]
        graph_fingerprint = canonical_hash({"known_ids": sorted(seen), "edges": [e for e in edges if e["from"] in reachable_known], "pools": {p: pool_defs[p] for p in closure["unresolved_dynamic_pool_ids"]}})
        closure["graph_fingerprint"] = graph_fingerprint
        document, validity = card_evidence.get(root_id, ({}, {}))
        review = document.get("cards", {}).get(root_id, {}).get("dependency_review", {})
        if (validity.get("status") == "CURRENT" and review.get("scope") == "FULL_RULES" and review.get("graph_fingerprint") == graph_fingerprint and not unresolved_pools):
            closure["closure_completeness"] = "COMPLETE_REVIEWED"
        blocks_for_card = training_blockers(row, closure, {**dependency_nodes, **card_rows}, session_match_current=session_match_current)
        if any(e["evidence_status"] == "UNREVIEWED_SOURCE_CANDIDATE" for e in edges if e["from"] in reachable_known) and closure["closure_completeness"] != "COMPLETE_REVIEWED":
            blocks_for_card.append("dependency:static_edges_unreviewed")
        row["blockers"] = blocks_for_card
        row["dependency_closure"] = closure
        row["training_eligibility"] = {"profile_id": profile["profile_id"], "status": "BLOCKED" if blocks_for_card else "ELIGIBLE", "blockers": blocks_for_card}
    admission = derive_admission(card_rows, profile_id=profile["profile_id"], session_match_current=session_match_current, decks=gate_doc.get("decks", []) if session_match_current else [])

    registry = {
        "schema_version": 1,
        "registry_id": profile["registry_id"],
        "snapshot": {"format": "STANDARD", "as_of_date": roots_doc["as_of_date"], "root_manifest": profile["roots"], "root_membership_sha256": roots_doc["root_membership_sha256"], "metadata_source": roots_doc["source_name"], "metadata_source_sha256": roots_doc["source_sha256"], "root_metadata_sha256": root_metadata_hash, "ban_manifest": profile["bans"], "rules_engine_revision": source_identity["source_commit"], "engine_source_identity": source_identity, "execution_identity": identity},
        "ownership": {"registry_fields": "Generated consolidation only; do not hand edit generated card statuses.", "source_metadata": "HearthstoneJSON dated archive and scope manifest", "implementation_routes": "Source block scanner and generated manifests, heuristic proposals", "capability_contracts": "integrations/rosettastone/card_rules/capabilities.json; file inventory does not certify semantics", "evidence": "Historical audit preserved by reference; scoped evidence requires reproducible execution identity to become current PASS", "dependencies": "Source literals are candidates until reviewed; pool definitions require independent predicate validation"},
        "input_fingerprints": {"root_manifest_sha256": sha256_bytes(profile_path(profile, "roots").read_bytes()), "ban_snapshot_sha256": sha256_bytes(ban_path.read_bytes()) if ban_path.exists() else None, "capabilities_sha256": sha256_bytes(CAPABILITIES.read_bytes()) if CAPABILITIES.exists() else None, "alias_manifest_sha256": sha256_bytes(ALIASES.read_bytes()) if ALIASES.exists() else None, "composition_manifest_sha256": sha256_bytes(COMPOSITIONS.read_bytes()) if COMPOSITIONS.exists() else None, "after_attack_draw_manifest_sha256": sha256_bytes(AFTER_ATTACK_DRAW.read_bytes()) if AFTER_ATTACK_DRAW.exists() else None, "after_attack_draw_evidence_sha256": sha256_bytes(AFTER_ATTACK_DRAW_EVIDENCE.read_bytes()) if AFTER_ATTACK_DRAW_EVIDENCE.exists() else None, "repeated_trigger_draw_manifest_sha256": sha256_bytes(REPEATED_TRIGGER_DRAW.read_bytes()) if REPEATED_TRIGGER_DRAW.exists() else None, "repeated_trigger_draw_evidence_sha256": sha256_bytes(REPEATED_TRIGGER_DRAW_EVIDENCE.read_bytes()) if REPEATED_TRIGGER_DRAW_EVIDENCE.exists() else None, "filtered_school_draw_manifest_sha256": sha256_bytes(FILTERED_SCHOOL_DRAW.read_bytes()) if FILTERED_SCHOOL_DRAW.exists() else None, "filtered_school_draw_evidence_sha256": sha256_bytes(FILTERED_SCHOOL_DRAW_EVIDENCE.read_bytes()) if FILTERED_SCHOOL_DRAW_EVIDENCE.exists() else None, "keyword_only_manifest_sha256": sha256_bytes(KEYWORD_ONLY.read_bytes()) if KEYWORD_ONLY.exists() else None, "metadata_only_manifest_sha256": sha256_bytes(METADATA_ONLY.read_bytes()) if METADATA_ONLY.exists() else None, "core_alias_evidence_sha256": sha256_bytes(CORE_ALIAS_EVIDENCE.read_bytes()) if CORE_ALIAS_EVIDENCE.exists() else None, "pool_detector_sha256": sha256_bytes(Path(__file__).read_bytes()), "historical_audit_sha256": sha256_bytes(PREVIOUS_AUDIT.read_bytes()) if PREVIOUS_AUDIT.exists() else None},
        "policy": {"policy_id": profile["profile_id"], "scope": f"All {len(card_rows)} pinned collectible Standard roots plus recursively reachable outcomes", "require_rules_status": ["VERIFIED_SCOPED"], "require_fresh_evidence": True, "evidence_freshness_fingerprint_fields": ["rules_fingerprint", "pool_membership_sha256", "pool_predicate_version", "capability_fingerprint", "engine_build_fingerprint", "scenario_fingerprint"], "require_reviewed_dependency_closure": True, "require_no_unresolved_dynamic_pools": True, "require_bridge_action_status": "VERIFIED_SCOPED", "require_session_and_match_gates": True, "result": admission["status"], "training_started": False},
        "computed_admission": admission,
        "evidence_invalidation": {"strategy": "Compare per-evidence fingerprints; invalidate dependents when any relevant fingerprint changes, including pool predicate version even if resolved membership stays equal. Unknown impact scope invalidates conservatively.", "available_current_evidence_fingerprints": any(v[1]["status"] == "CURRENT" for v in card_evidence.values()), "reason": "Historical scenario evidence lacks complete build/scenario/dependency fingerprints; it is retained as stale history.", "impact_inputs": ["normalized rules text", "CardDef source block", "capability contracts", "generator declaration and output", "engine source/binary identity", "scenario fixture/expectations", "pool predicate version", "resolved pool membership hash", "bridge action schema"]},
        "classifier": {"route_vocabulary": ["AUTO", "COMPOSABLE", "MISSING_PRIMITIVE", "CUSTOM", "UNKNOWN"], "proposals_only": True, "route_counts": dict(sorted(Counter(row["implementation"]["route_proposal"] for row in card_rows.values()).items())), "route_method": "Pinned text, source-registration shape and bounded generated manifests; no route is correctness evidence.", "capability_inventory_sha256": canonical_hash(capabilities), "semantic_contract_reviewed_count": sum(bool(t.get("semantics_reviewed")) for t in capabilities.get("simple_tasks", []))},
        "counts": {"roots": len(card_rows), "metadata_present": sum(row["metadata"]["present"] for row in card_rows.values()), "direct_source_registered": sum(row["implementation"]["registration_status"] == "DIRECT_SOURCE_BLOCK" for row in card_rows.values()), "generated_registered": sum(row["implementation"]["registration_status"].startswith("GENERATED_") for row in card_rows.values()), "text_bearing_without_detected_registration": sum(bool(norm_text(row["metadata"]["rules_text"])) and row["implementation"]["registration_status"] == "NO_DETECTED_RULE_REGISTRATION" for row in card_rows.values()), "textless_metadata_candidates": sum(row["implementation"]["registration_status"] == "TEXTLESS_METADATA" for row in card_rows.values()), "rules_verified_scoped_current": sum(row["rules_verification"]["status"] == "VERIFIED_SCOPED" and row["rules_verification"]["evidence_validity"] == "CURRENT" for row in card_rows.values()), "stale_historical_scoped_evidence": sum(row["rules_verification"]["evidence_validity"] == "STALE" for row in card_rows.values()), "unresolved_dynamic_pool_definitions": len(pool_defs), "unique_known_edge_target_nodes_including_roots": len({e["to"] for e in edges}), "unreviewed_static_source_edges": sum(e["evidence_status"] == "UNREVIEWED_SOURCE_CANDIDATE" for e in edges), "roots_with_complete_dependency_closure": sum(c["closure_completeness"] == "COMPLETE_REVIEWED" for c in closures.values()), "roots_training_eligible": sum(row["training_eligibility"]["status"] == "ELIGIBLE" for row in card_rows.values())},
        "cards": card_rows,
        "dependency_graph": {"nodes": sorted(root_ids | {e["to"] for e in edges}), "dependency_node_records": dependency_nodes, "edges": edges, "pools": pool_defs, "pool_detector": {"version": "standard_pool_hypotheses_v2", "source_sha256": sha256_bytes(Path(__file__).read_bytes()), "random_board_targets_excluded": True, "fixed_named_token_summons_excluded": True, "completeness": "HEURISTIC_CANDIDATES_ONLY; unresolved dependencies may remain undetected"}, "unique_known_nonroot_dependency_nodes": len(reachable_dependency_ids), "known_closure_is_lower_bound": True},
        "deck_legality": {"bans": "Separate dated snapshot; Standard bans are applied to root records only. Root membership is not a generated-pool legality rule.", "status": "ROOT_MEMBERSHIP_AND_PINNED_BAN_SNAPSHOT_APPLIED", "standard_ban_count": len(standard_bans), "full_deck_validation": "NOT_A_DECK_LIST; deck/session profiles require separate validation"},
    }
    auxiliaries = {"roots": root_items, "edges": edges, "pools": pool_defs, "closures": closures, "cards": card_rows, "dependency_nodes": dependency_nodes}
    return registry, auxiliaries


def build_reports(registry: dict[str, Any], aux: dict[str, Any]) -> tuple[dict[str, Any], str]:
    cards = registry["cards"]
    counts = registry["counts"]
    package_cards: dict[str, set[str]] = defaultdict(set)
    for card_id, row in cards.items():
        for signal in row["classifier_features"]["action_signals"]:
            package_cards[signal].add(card_id)
    packages = []
    for signal, ids in sorted(package_cards.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        unregistered = {card_id for card_id in ids if cards[card_id]["implementation"]["registration_status"] == "NO_DETECTED_RULE_REGISTRATION" and cards[card_id]["metadata"]["rules_text"].strip()}
        packages.append({"capability_hypothesis": signal, "candidate_root_count": len(ids), "candidate_card_ids": sorted(ids), "unregistered_text_root_count": len(unregistered), "unregistered_text_root_ids": sorted(unregistered), "selection_signals": ["shared metadata/rules-text feature", "heuristic only"], "estimated_unlocks": None, "priority": "REVIEW_CANDIDATE_ONLY", "confidence": "LOW", "manual_or_meta_frequency": "UNKNOWN", "blocker_note": "Review contracts and actual dependency closure before treating these cards as one implementation package. Candidate count is not an unlock prediction."})
    dep_root_usage: Counter[str] = Counter()
    for root_id, closure in aux["closures"].items():
        for dep_id in closure["known_source_candidate_ids"]:
            if dep_id not in cards:
                dep_root_usage[dep_id] += 1
    shared_dependencies = [{"card_id": card_id, "known_roots_reaching_node": count, "metadata_status": aux["dependency_nodes"].get(card_id, {}).get("metadata_status", "UNKNOWN"), "registration_status": aux["dependency_nodes"].get(card_id, {}).get("registration_status", "UNKNOWN"), "priority": "REVIEW_CANDIDATE_ONLY"} for card_id, count in dep_root_usage.most_common(25)]
    dynamic_by_root: dict[str, list[str]] = defaultdict(list)
    for pool_id, pool in aux["pools"].items():
        dynamic_by_root[pool["origin_card_id"]].append(pool_id)
    pool_kind_counts = dict(sorted(Counter(pool["pool_kind_hypothesis"] for pool in aux["pools"].values()).items()))
    pool_origins = {pool["origin_card_id"] for pool in aux["pools"].values()}
    pool_root_origins = pool_origins & set(cards)
    report = {
        "schema_version": 1,
        "report_id": registry["registry_id"],
        "registry_id": registry["registry_id"],
        "snapshot": registry["snapshot"],
        "summary": {**counts, "known_dependency_closure": "LOWER_BOUND_ONLY; static source candidates unreviewed and dynamic pools unresolved", "full_standard_training": registry["computed_admission"]["status"], "meta_frequency_coverage": "UNKNOWN; no current meta-frequency source attached"},
        "registration_and_rules": {"route_counts": registry["classifier"]["route_counts"], "registration_counts": {"direct_source_block": counts["direct_source_registered"], "recognized_generated_manifest": counts["generated_registered"], "missing_detected_registration_with_text": counts["text_bearing_without_detected_registration"], "textless_metadata_candidates": counts["textless_metadata_candidates"]}, "current_rules_verified": counts["rules_verified_scoped_current"], "historical_scoped_evidence_marked_stale": counts["stale_historical_scoped_evidence"]},
        "dependencies": {"unique_known_nonroot_dependency_nodes": registry["dependency_graph"]["unique_known_nonroot_dependency_nodes"], "source_candidate_edges": len(aux["edges"]), "unreviewed_static_edges": counts["unreviewed_static_source_edges"], "unresolved_dynamic_pool_definitions": len(aux["pools"]), "pool_candidate_definitions_by_kind": pool_kind_counts, "roots_with_any_unresolved_dynamic_pool": len(pool_root_origins), "known_dependency_origins_with_pool_candidates": len(pool_origins - set(cards)), "known_closure_complete_roots": counts["roots_with_complete_dependency_closure"], "most_reused_known_nodes": shared_dependencies, "pool_candidate_detector": registry["dependency_graph"]["pool_detector"], "unknown_scope_warning": "Observed literal references and metadata heuristics are not complete rules dependencies; pool candidates are neither confirmed pools nor exhaustive."},
        "training_admission": registry["computed_admission"],
        "candidate_packages": packages,
        "missing_capability_review_queue": [p for p in packages if p["unregistered_text_root_count"]],
        "known_limitations": ["Route and action family counts are text/source heuristics, not verified mechanic counts.", "Source registration scanning does not prove the currently loaded RosettaStone binary contains those definitions.", "Dependency closure is incomplete: source literals are unreviewed and heuristic dynamic pool candidates have no exact members or runtime parity evidence; random board targets and fixed named-token summons are excluded by detector v2, but the candidate list is not exhaustive.", "Historical VERIFIED_SCOPED audit entries are retained but marked stale for current admission because reproducible build/source identity is absent.", "No 2026-10-01 meta-frequency dataset is attached, so package order cannot be described as current-meta priority.", "The bridge/action audit and session/match gates are not synthesized from old five-deck pilot claims."],
    }
    lines = [f"# Standard registry report — {registry['snapshot']['as_of_date']}", "", f"Registry: `{registry['registry_id']}`. Full Standard admission: **{registry['computed_admission']['status']}**.", "", "## Pool and implementation inventory", "", f"- Collectible roots: **{counts['roots']}**; metadata present: **{counts['metadata_present']}**.", f"- Source registration: **{counts['direct_source_registered']}** direct, **{counts['generated_registered']}** generated manifest entries, **{counts['text_bearing_without_detected_registration']}** text-bearing without detected registration, **{counts['textless_metadata_candidates']}** textless metadata candidates.", f"- Current rules verification: **{counts['rules_verified_scoped_current']}**; historical scoped evidence marked stale: **{counts['stale_historical_scoped_evidence']}**.", f"- Route proposals: `{json.dumps(registry['classifier']['route_counts'], ensure_ascii=False, sort_keys=True)}` (heuristic; not correctness status).", "", "## Dependency graph", "", f"- Unique edge-target nodes, including Standard roots: **{counts['unique_known_edge_target_nodes_including_roots']}**; unique known non-root dependency nodes: **{registry['dependency_graph']['unique_known_nonroot_dependency_nodes']}**.", f"- Static literal/reference candidates: **{len(aux['edges'])}**, all requiring review or limited declaration evidence.", f"- Unresolved dynamic pool candidate signals: **{len(aux['pools'])}** across **{len(pool_root_origins)}** Standard roots and **{len(pool_origins - set(cards))}** known dependency origins; by kind: `{json.dumps(pool_kind_counts, sort_keys=True)}`.", "- Detector v2 excludes random board targets and fixed named-token summons; pool candidates remain heuristic, not a confirmed or exhaustive pool inventory.", f"- Complete root closures: **{counts['roots_with_complete_dependency_closure']}**. The known graph is a lower bound; absent edges are not proof of no dependency.", "", "## Admission blockers", "", f"- Eligible roots: **{registry['computed_admission']['eligible_roots']}** in `{registry['policy']['policy_id']}`.", f"- Admission blockers: `{json.dumps(registry['computed_admission']['blockers'])}`.", "- This report does not authorize or start pooled training.", "", "## Candidate capability packages", "", "Priority is not inferred from metadata frequency. These are review groupings based on text signals; unlock counts remain unknown until capabilities and dependency closures are verified.", "", "| Signal | Candidate roots | Confidence |", "|---|---:|---|"]
    for package in packages:
        lines.append(f"| {package['capability_hypothesis']} | {package['candidate_root_count']} ({package['unregistered_text_root_count']} without detected rules registration) | {package['confidence']} |")
    lines += ["", "## Limits", "", *[f"- {item}" for item in report["known_limitations"]], ""]
    return report, "\n".join(lines)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--roots", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.roots = args.roots or profile_path(profile, "roots")
    args.output = args.output or profile_path(profile, "registry")
    args.reports_dir = args.reports_dir or profile_path(profile, "reports")
    if args.roots.resolve() != profile_path(profile, "roots").resolve():
        raise ValueError("Root input must belong to the selected profile; select --profile for a different pool")
    roots_doc = read_json(args.roots)
    registry, aux = build_registry(roots_doc, profile=profile)
    report, markdown = build_reports(registry, aux)
    write_json(args.output, registry)
    write_json(args.reports_dir / "summary.json", report)
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    md_path = args.reports_dir / "summary.md"
    if not md_path.exists() or md_path.read_text(encoding="utf-8") != markdown:
        md_path.write_text(markdown, encoding="utf-8", newline="\n")
    print(f"Registry: {args.output}")
    print(f"Report: {md_path}")
    print(f"Roots: {registry['counts']['roots']}; known non-root nodes: {registry['dependency_graph']['unique_known_nonroot_dependency_nodes']}; unresolved pools: {registry['counts']['unresolved_dynamic_pool_definitions']}")
    print(f"Registration: direct={registry['counts']['direct_source_registered']}, generated={registry['counts']['generated_registered']}, no detected text rules={registry['counts']['text_bearing_without_detected_registration']}")
    print(f"Training admission: {registry['computed_admission']['status']}")


if __name__ == "__main__":
    main()
