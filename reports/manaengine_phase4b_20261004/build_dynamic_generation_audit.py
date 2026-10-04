"""Read-only source audit; writes derived planning artifacts in this report directory only.

Run with the pinned repository sources and the saved finite full-definition slice.
This does not generate engine declarations, schema, canonical registry or evidence.
"""
from __future__ import annotations
import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8", newline="\n")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ids_hash(ids):
    return hashlib.sha256(("\n".join(sorted(ids)) + "\n").encode("utf-8")).hexdigest()

def classes(card):
    return sorted(card.get("classes", [card.get("cardClass", "UNKNOWN")]))

roots_file = ROOT / "data/cards/standard_roots_20261001_enUS.json"
snapshot_file = ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
roots = read(roots_file)
metadata = {row["card_id"]: row["metadata"] for row in roots["roots"]}
registry = read(ROOT / "data/cards/standard_registry_20261001_enUS.json")
decl = read(ROOT / "experiments/manaengine/data/card_abilities.json")["cards"]
manual = read(OUT / "DYNAMIC_GENERATION_CARD_REVIEW.json")["card_reviews"]
full_slice = read(OUT / "DYNAMIC_GENERATION_FULL_DEFINITION_SLICE.json")
full_metadata = {c["id"]: c for c in full_slice["cards"]}
fire = sorted(i for i, c in metadata.items() if c.get("type") == "SPELL" and c.get("spellSchool") == "FIRE")
whelp_raw = sorted(i for i, c in metadata.items() if c.get("type") == "SPELL" and c.get("cost") == 1)
quests = sorted(i for i in whelp_raw if "QUEST" in metadata[i].get("mechanics", []))
neutral = sorted(i for i in whelp_raw if classes(metadata[i]) == ["NEUTRAL"])
whelp_nonquest = sorted(set(whelp_raw) - set(quests))
whelp_class_working = sorted(set(whelp_nonquest) - set(neutral))
union = sorted(set(fire) | set(whelp_raw))
if set(manual) != set(union):
    raise ValueError(f"Manual semantic review mismatch: {set(union) ^ set(manual)}")
if digest(snapshot_file) != roots["source_sha256"]:
    raise ValueError("Pinned metadata snapshot mismatch")
for i in union:
    if full_metadata.get(i) != metadata[i]:
        raise ValueError(f"Latest full-feed slice differs from pinned root {i}; review before replacing any source")

sources = {
    "metadata_snapshot": "data/cards/source_snapshots/cards_collectible_20261001_enUS.json",
    "metadata_snapshot_sha256": digest(snapshot_file),
    "root_membership_file": "data/cards/standard_roots_20261001_enUS.json",
    "root_membership_file_sha256": digest(roots_file),
    "full_definition_slice_sha256": digest(OUT / "DYNAMIC_GENERATION_FULL_DEFINITION_SLICE.json"),
    "fetched_full_feed_sha256": full_slice["source_sha256"],
    "rules_review_sha256": digest(OUT / "DYNAMIC_GENERATION_CARD_REVIEW.json"),
    "dark_gift_review_sha256": digest(OUT / "DARK_GIFT_OPTION_REVIEW.json"),
    "audit_builder_sha256": digest(Path(__file__)),
    "source_revision": "1686256493293459b6fa6f863832f887416025f7",
    "hash_contract": "Ordinal sorted unique card IDs, UTF-8 without BOM, LF after every ID including the last.",
}

def manifest(pool_id, ids, predicate, status):
    rows = []
    for i in ids:
        c = metadata[i]
        rows.append({"card_id": i, "name": c["name"], "classes": classes(c), "base_cost": c.get("cost"),
                     "spell_school": c.get("spellSchool", "NONE"), "collectible": c.get("collectible", False),
                     "set": c.get("set"), "dbf_id": c.get("dbfId"),
                     "rune_cost": c.get("runeCost"),
                     "alias_count_as_copy_of_dbf_id": c.get("countAsCopyOfDbfId"),
                     "current_manaengine_declaration": decl.get(i),
                     "manaengine_support_status": decl.get(i, {}).get("support_state", "NO_DECLARATION"),
                     "canonical_rules_status": registry["cards"][i]["rules_verification"]["status"],
                     "dependency_closure": "NOT_REVIEWED_COMPLETE",
                     "rules_review_status": status})
    return {"schema_version": 1, "pool_id": pool_id, "pool_contract_version": 1,
            "profile_id": "standard_full_20261001_v1", "as_of_date": "2026-10-01",
            "predicate_contract": predicate, "candidate_ids": ids, "count": len(ids),
            "sorted_lf_sha256": ids_hash(ids), "sources": sources, "rules_review_status": status,
            "runtime_admitted": False, "support_filter_applied": False,
            "rules_provenance": ["https://hearthstone.blizzard.com/en-us/news/23935323/26-0-4-patch-notes",
                                 "https://hearthstone.blizzard.com/en-us/news/24293284/36-2-2-patch-notes"],
            "members": rows}

dump("VULCANOS_FIRE_POOL_REVIEW.json", manifest(
    "SPELL_FIRE_STANDARD_ANY_CLASS_20261001_V1", fire,
    {"scope": "PINNED_STANDARD_COLLECTIBLE_ROOTS", "type": "SPELL", "spell_school": "FIRE",
     "classes": "ANY", "duplicate_policy": "ONE_CANONICAL_ROOT_ID_NO_LEGACY_ALIAS_EXPANSION",
     "rules_exclusions": ["QUEST_AND_QUESTLINE", "ANY_THREE_RUNE_REQUIREMENT", "REVIEWED_NOT_GENERATABLE_IDS"],
     "known_exclusion_hits": [], "format_ban_policy": "DO_NOT_INHERIT_DECKBUILDING_BANS",
     "open_question": "No full patch-specific not-generatable tag inventory or client outcome trace available; 33 is exact metadata-derived reviewed candidate membership, not certified complete runtime membership."},
    "METADATA_AND_CARD_TEXT_REVIEWED_RUNTIME_ELIGIBILITY_NOT_PROVEN"))

w = manifest("SPELL_BASE_COST_1_ANY_CLASS_20261001_PROVISIONAL", whelp_raw,
    {"scope": "PINNED_STANDARD_COLLECTIBLE_ROOTS", "type": "SPELL", "base_cost": 1,
     "classes": "ANY_CLASS_NEUTRAL_SEPARATE_REVIEW",
     "dynamic_instance_cost": "IGNORED_FOR_POOL_PREDICATE",
     "quest_exclusion_evidence": "DEVELOPER_STATEMENT_MIRROR_NOT_NEW_PRIMARY_REPLAY",
     "sidequest_policy": "NOT_EQUIVALENT_TO_QUEST", "runtime_eligibility": "PROVISIONAL"},
    "PROVISIONAL_WHELP_PREDICATE")
w["rules_provenance"].append("https://www.hearthpwn.com/news/2274-journey-to-ungoro-is-hearthstones-next-expansion?page=18")
w["working_exclusions"] = {"quest_ids": quests, "quest_exclusion_status": "REVIEWED_DEVELOPER_STATEMENT_MIRROR",
                            "neutral_ids": neutral, "neutral_exclusion_status": "PROVISIONAL_ANY_CLASS_INTERPRETATION",
                            "no_three_rune_candidate_hits": True}
w["variants"] = [
    {"name": "NONQUEST_INCLUDING_NEUTRAL_PENDING_CLASS_REVIEW", "count": len(whelp_nonquest),
     "ids": whelp_nonquest, "sorted_lf_sha256": ids_hash(whelp_nonquest)},
    {"name": "WORKING_CLASS_SPELLS_EXCLUDING_QUEST", "count": len(whelp_class_working),
     "ids": whelp_class_working, "sorted_lf_sha256": ids_hash(whelp_class_working)}]
dump("WHELP_ONE_COST_POOL_PROVISIONAL.json", w)
pool_lines = ["# Reviewed candidate memberships", "",
              "Source presence is not rules verification. Both pools have runtime_admitted=false.",
              "Fire = exact pinned metadata candidate set; Whelp = raw candidates with explicit working exclusions."]
for title, ids in [("Fire — 33", fire), ("Whelp raw — 77", whelp_raw)]:
    pool_lines.extend(["", "## " + title, "", "Sorted-LF SHA-256: `" + ids_hash(ids) + "`", "",
                       "| ID | Name | Classes | Base cost | School | Collectible | ManaEngine declaration state | Canonical Rosetta rules status | Working Whelp eligibility |",
                       "|---|---|---|---:|---|---|---|---|---|"])
    for i in ids:
        c = metadata[i]
        eligibility = "QUEST_EXCLUDED_WORKING" if i in quests else "NEUTRAL_PENDING" if i in neutral else "CLASS_CANDIDATE"
        pool_lines.append("| " + " | ".join(str(x).replace("|", "/") for x in [i, c["name"],
            ", ".join(classes(c)), c.get("cost"), c.get("spellSchool", "NONE"), c.get("collectible", False),
            decl.get(i, {}).get("support_state", "NO_DECLARATION"), registry["cards"][i]["rules_verification"]["status"],
            eligibility if i in whelp_raw else "OUTSIDE_WHELP_COST_PREDICATE"]) + " |")
(OUT / "POOL_MEMBERSHIP_TABLES.md").write_text("\n".join(pool_lines) + "\n", encoding="utf-8", newline="\n")
dump("POOL_OVERLAP_AND_UNION.json", {
    "sources": sources, "fire_count": len(fire), "whelp_raw_count": len(whelp_raw),
    "intersection": sorted(set(fire) & set(whelp_raw)), "intersection_count": len(set(fire) & set(whelp_raw)),
    "union_ids": union, "union_count": len(union), "union_sorted_lf_sha256": ids_hash(union),
    "working_whelp_class_count": len(whelp_class_working),
    "working_union_count": len(set(fire) | set(whelp_class_working)),
    "working_union_sorted_lf_sha256": ids_hash(set(fire) | set(whelp_class_working)),
    "rules_status": "COMPUTED_FROM_CANDIDATES_NOT_RUNTIME_MEMBERSHIP_PROOF"})

# Manual contracts choose dimensions; no keyword classifier selects a rules implementation.
existing = {
    "DAMAGE_CHARACTER": "TARGET_DAMAGE / EffectKind::Damage",
    "DAMAGE_MINION": "MINION_DAMAGE_GENERATE target legality / ExplicitMinion",
    "DAMAGE_ENEMY_MINIONS": "EffectKind::Damage / EnemyMinions",
    "DAMAGE_ALL_CHARACTERS": "EffectKind::Damage / AllCharacters",
    "RANDOM_ENEMY_MINION": "EffectKind::Damage / RandomEnemyMinion, scoped death guard",
    "DRAW_SELF": "EffectKind::Draw / draw()",
    "GAIN_ARMOR": "EffectKind::GainArmor",
    "HERO_ATTACK_THIS_TURN": "EffectKind::ModifyHeroAttack",
    "FREEZE_ENEMY": "EffectKind::Freeze, targeting extension review",
    "SUMMON_FIXED": "EffectKind::SummonFixed / summon_fixed",
    "SUMMON_FIXED_RUSH": "summon_fixed + CardDefinition.rush",
    "ADD_FIXED_HAND": "MinionDamageGenerate fixed outcome / enter_hand",
    "GENERATED_COST_REDUCTION": "CardInstance.cost_delta / effective_cost / existing Discover modifier",
    "HELD_SPELL_PROGRESS": "update_held_card_spell_progress, scoped hand-play gate",
    "TRANSFORM_HAND": "held_spell_threshold / transform_card, scoped combination only",
    "SECRET_AFTER_OPPONENT_MINION_PLAY": "Secret ExplosiveRunes window",
    "SECRET_OPPONENT_TURN_END": "Secret OpponentTurnEnds window",
}
def flags(caps, fragments):
    return [c for c in caps if any(fragment in c for fragment in fragments)]

matrix = []
families = defaultdict(list)
for i in union:
    c, audit = metadata[i], manual[i]
    caps = audit["capabilities"]
    fixed = []
    for dependency in audit["fixed_dependencies"]:
        d = full_metadata.get(dependency, metadata.get(dependency))
        fixed.append({"card_id": dependency, "identity_status": "METADATA_RESOLVED" if d else "UNRESOLVED",
                      "name": d.get("name") if d else None, "type": d.get("type") if d else None,
                      "rules_text": d.get("text", "") if d else None,
                      "edge_review": "MANUAL_CONTRACT_REFERENCE_REQUIRES_EXECUTABLE_PARITY",
                      "rules_verification": "NOT_VERIFIED_BY_THIS_AUDIT"})
    row = {"card_id": i, "name": c["name"], "classes": classes(c), "base_cost": c.get("cost"),
           "rules_text": c.get("text", ""), "pool_membership": {"fire_candidate": i in fire, "whelp_raw_candidate": i in whelp_raw,
                                                             "whelp_working_class_candidate": i in whelp_class_working},
           "semantic_family": audit["family"], "required_capabilities": caps,
           "existing_manaengine_primitives": {k: existing[k] for k in caps if k in existing},
           "new_or_unreviewed_capabilities": [k for k in caps if k not in existing],
           "fixed_generated_dependencies": fixed, "dynamic_generated_dependencies": audit["dynamic_dependencies"],
           "targeting": audit["targeting"], "randomness": flags(caps, ["RANDOM", "DISCOVER", "DRAW_DIFFERENT_MINION_TYPES"]),
           "choice_discover": flags(caps, ["DISCOVER", "CHOOSE_ONE", "CHOICE", "PICK_OTHER", "REWIND"]),
           "summon": flags(caps, ["SUMMON", "ZOMBEAST"]), "draw": flags(caps, ["DRAW"]),
           "buff_debuff": flags(caps, ["BUFF", "HEAL", "SET_HEALTH", "SHIELD", "STATS", "RUSH", "AURA", "FREEZE"]),
           "transform": flags(caps, ["TRANSFORM", "REPLACEMENT", "REPLACE_", "COPY"]),
           "history": flags(caps, ["HISTORY", "PROGRESS", "SHUFFLE_COUNT", "UNPLAYED_TYPE", "IF_PLAY", "STARTED_IN_DECK", "COMBO"]),
           "persistent_aura_state": flags(caps, ["AURA", "FUTURE_", "HAND_TURN", "THIS_TURN", "END_TURN", "HELD_", "ONE_TURN", "TWO_USE", "REWIND", "STARTED_IN_DECK"]),
           "resource_mechanic": flags(caps, ["CORPSES", "OVERLOAD", "HERO_POWER"]),
           "quest_long_lived_state": flags(caps, ["QUEST", "FUTURE_", "REPLACE_HERO_POWER"]),
           "unique_outlier_mechanic": audit["family"] in ["excess_damage_return_outlier", "refresh_discover_outlier", "sidequest_composite_minion"],
           "rules_uncertainty": audit["rules_uncertainty"], "current_support_declaration": decl.get(i),
           "canonical_rules_status": registry["cards"][i]["rules_verification"]["status"],
           "canonical_rosettastone_source_candidates": registry["cards"][i]["dependencies"]["known_source_candidates"],
           "dependency_closure_state": "NOT_REVIEWED_COMPLETE",
           "training_eligible": False}
    matrix.append(row)
    families[audit["family"]].append(row)
dump("DYNAMIC_GENERATION_CAPABILITY_MATRIX.json", {"schema_version": 1, "sources": sources,
     "classification": "MANUAL_TEXT_CONTRACT_AUDIT_NOT_IMPLEMENTATION_OR_VERIFICATION", "count": len(matrix), "cards": matrix})

high = {"temporary_hero_power_swap", "sidequest_composite_minion", "refresh_discover_outlier",
        "rewind_discover", "death_history_replay", "future_companion_override", "temporary_inherited_effect",
        "cast_when_drawn_shuffle", "discover_then_play_other_option", "future_generated_state",
        "hidden_zone_copy", "deck_draw_copy_summon", "corpses_dark_gift", "corpses_choose_one", "discover_dark_gift"}
low = {"fixed_damage", "fixed_hand_generation"}
packages = []
for family, rows in sorted(families.items()):
    dependency_ids = sorted({d["card_id"] for row in rows for d in row["fixed_generated_dependencies"]})
    pools = sorted({p for row in rows for p in row["dynamic_generated_dependencies"]})
    newcaps = sorted({p for row in rows for p in row["new_or_unreviewed_capabilities"]})
    model = "GPT-6.1 Sol High" if family in high else "GPT-6 Luna" if family in low and not newcaps else "GPT-6.1 Sol Medium"
    packages.append({"proposed_family": family, "candidate_ids": [row["card_id"] for row in rows],
        "fire_candidates_addressed": sum(row["pool_membership"]["fire_candidate"] for row in rows),
        "whelp_raw_candidates_addressed": sum(row["pool_membership"]["whelp_raw_candidate"] for row in rows),
        "whelp_working_candidates_addressed": sum(row["pool_membership"]["whelp_working_class_candidate"] for row in rows),
        "already_declared_consumers": sum(row["current_support_declaration"] is not None for row in rows),
        "fixed_dependency_candidates": dependency_ids, "dynamic_frontiers": pools,
        "expected_shared_changes": newcaps, "new_shared_primitives_count_upper_bound": len(newcaps),
        "rules_risk": "HIGH" if family in high or pools else "MEDIUM" if newcaps else "LOW",
        "implementation_complexity": "ARCHITECTURE_REVIEW" if family in high else "OUTCOME_CLOSURE_DOMINATES" if pools else "BOUNDED",
        "model_recommendation": model,
        "package_status": "FAMILY_PLANNING_CANDIDATE_NARROW_CONTRACT_AND_PROPOSAL_REQUIRED",
        "unlock_semantics": "Potential outcome rule implementations addressed, not verified roots or training gain; subcontracts and all listed dependencies still required.",
        "transitive_closure_unlock_count": None if pools else "NOT_VERIFIED",
        "verified_cards_gained_by_audit": 0})
dump("DYNAMIC_GENERATION_FAMILY_PLAN.json", {"schema_version": 1, "sources": sources,
     "families": packages, "count": len(packages),
     "warning": "Do not implement mixed facets as one behavioral dispatcher; split into reusable subcontracts. Counts address candidates, not guaranteed package unlocks."})

# Explicit pool envelopes, separate from admitted runtime manifests.
nodes = {}
edges = []
def edge(source, target, relation, status):
    edges.append({"from": source, "to": target, "relation": relation, "evidence_status": status})
def card_node(i, category="CARD"):
    c = metadata.get(i, full_metadata.get(i))
    nodes.setdefault(i, {"kind": category, "name": c.get("name") if c else None,
        "metadata_present": c is not None, "rules_text": c.get("text", "") if c else None,
        "manaengine_declaration_present": i in decl, "reviewed_closure": False})
def add_pool(name, members=None, predicate=None, limitations=None):
    if name in nodes: return
    members = sorted(set(members)) if members is not None else None
    nodes[name] = {"kind": "POOL", "membership_status": "METADATA_ENVELOPE_NOT_RUNTIME_REVIEWED" if members is not None else "UNRESOLVED_RUNTIME_OR_RULES_POOL",
                   "predicate": predicate or name, "members": members, "count": len(members) if members is not None else None,
                   "sorted_lf_sha256": ids_hash(members) if members is not None else None,
                   "limitations": limitations or ["Generation eligibility/actor class must be reviewed before admission."], "reviewed_closure": False}
    for i in members or []:
        card_node(i, "POOL_FRONTIER_CARD")
        edge(name, i, "candidate_pool_member", "METADATA_ENVELOPE_ONLY")

minions = [c for c in metadata.values() if c.get("type") == "MINION"]
spells = [c for c in metadata.values() if c.get("type") == "SPELL"]
def player_neutral(c):
    return "MAGE" in classes(c) or "NEUTRAL" in classes(c)
def candidate_ids(cards):
    return [c["id"] for c in cards]
add_pool("FIRE", fire, "Pinned collectible Fire spells, any class", ["Exact candidate manifest; runtime exclusion completeness not proven."])
add_pool("WHELP_RAW", whelp_raw, "Pinned collectible spells, base cost 1, raw all classes/neutral")
add_pool("WHELP_WORKING", whelp_class_working, "Working: base cost 1, class spell, not QUEST", ["Neutral and patch-specific exceptions remain review gates."])
add_pool("BATTLECRY_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in minions if player_neutral(c) and "BATTLECRY" in c.get("mechanics", [])]), "Mage-controlling-player hypothesis + Neutral + Battlecry")
add_pool("MINION_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in minions if player_neutral(c)]), "Mage-controlling-player hypothesis + Neutral")
add_pool("COMBO_BATTLECRY_STEALTH_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in minions if player_neutral(c) and set(c.get("mechanics", [])) & {"COMBO", "BATTLECRY", "STEALTH"}]))
add_pool("TAUNT_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in minions if player_neutral(c) and "TAUNT" in c.get("mechanics", [])]))
add_pool("STEALTH_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in minions if player_neutral(c) and "STEALTH" in c.get("mechanics", [])]))
add_pool("UNDEAD_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in minions if player_neutral(c) and "UNDEAD" in c.get("races", [c.get("race")])]))
add_pool("MURLOC_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in minions if player_neutral(c) and "MURLOC" in c.get("races", [c.get("race")])]))
add_pool("ODD_BASE_ATTACK_BEAST_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in minions if player_neutral(c) and "BEAST" in c.get("races", [c.get("race")]) and c.get("attack",0)%2==1]))
add_pool("WARRIOR_MINIONS", candidate_ids([c for c in minions if "WARRIOR" in classes(c)]), "Explicit Warrior class; neutral separate review")
add_pool("MINION_BASE_COST_1_ANY_CLASS", candidate_ids([c for c in minions if c.get("cost")==1]))
add_pool("MINION_BASE_COST_4_ANY_CLASS", candidate_ids([c for c in minions if c.get("cost")==4]))
add_pool("MINION_BASE_COST_AT_LEAST_8_ANY_CLASS", candidate_ids([c for c in minions if c.get("cost",0)>=8]))
add_pool("MINION_BASE_COST_EQUALS_DESTROYED", candidate_ids(minions), "Conservative reachable-cost envelope: all collectible minions; actual pool uses reviewed source-cost snapshot")
add_pool("SPELL_ANY_CLASS", candidate_ids([c for c in spells if "QUEST" not in c.get("mechanics", []) and sum(c.get("runeCost",{}).values()) <3]), "All Standard collectible spell classes, general exclusions only; neutral separate review")
for name, class_name in [("SPELL_MAGE","MAGE"),("SPELL_DRUID","DRUID"),("SPELL_PLAYER_CLASS","MAGE")]:
    add_pool(name, candidate_ids([c for c in spells if class_name in classes(c) and "QUEST" not in c.get("mechanics", [])]))
add_pool("SPELL_DISCOVER_PLAYER_CLASS_NEUTRAL", candidate_ids([c for c in spells if player_neutral(c) and "QUEST" not in c.get("mechanics", [])]), "Mage-controlling-player hypothesis; Quest excluded, neutral eligibility pending")
add_pool("FROST_SPELL_ANY_CLASS", candidate_ids([c for c in spells if c.get("spellSchool")=="FROST"]))
dark_gift = read(OUT / "DARK_GIFT_OPTION_REVIEW.json")
add_pool("DARK_GIFT_OPTIONS", dark_gift["official_launch_matching_option_ids"],
         "Official constructed launch ten matched to current full metadata; source-minion-dependent eligibility",
         ["Current runtime membership not proven; extra prefix spell objects remain unclassified.",
          "Minion eligibility and option pairing are conditional, not a uniform random-card pool."])
for option, capability in [("EDR_100t5", "ON_PLAY_COPY_WITH_ENCHANTMENTS"),
                           ("EDR_100t7", "BATTLECRY_MULTIPLICITY"),
                           ("EDR_100t8", "BACKWARD_ZONE_ENCHANTMENT_EXCEPTION"),
                           ("EDR_100t9", "REBORN_FULL_HEALTH_RETAIN_ENCHANTMENTS")]:
    nodes[capability] = {"kind": "SEMANTIC_REQUIREMENT", "reviewed_closure": False,
                         "status": "OFFICIAL_RULES_EVIDENCE_ENGINE_ARCHITECTURE_REVIEW_REQUIRED"}
    edge(option, capability, "persistent_effect_semantics", "OFFICIAL_LAUNCH_AND_32_2_RULES_REVIEW")
for row in matrix:
    i = row["card_id"];card_node(i)
    for dep in row["fixed_generated_dependencies"]:
        card_node(dep["card_id"], "FIXED_DEPENDENCY")
        edge(i, dep["card_id"], "fixed_effect_or_option_dependency", "METADATA_AND_MANUAL_TEXT_REVIEW_NOT_NATIVE_VERIFICATION")
    for pool in row["dynamic_generated_dependencies"]:
        add_pool(pool)
        edge(i, pool, "outcome_or_runtime_selector", "MANUAL_TEXT_CONTRACT_AUDIT_PREDICATE_REVIEW_PENDING")
    for candidate in row["canonical_rosettastone_source_candidates"]:
        card_node(candidate["to"], "SOURCE_CANDIDATE")
        edge(i, candidate["to"], candidate["kind"], candidate["evidence_status"])
for root in ["CATA_488","CATA_488t","CATA_488t2","CATA_484"]: card_node(root)
edge("CATA_488","CATA_488t","colossal_appendage","METADATA_IDENTITY_REVIEW_PLACEMENT_PENDING")
edge("CATA_488","CATA_488t2","colossal_appendage","METADATA_IDENTITY_REVIEW_PLACEMENT_PENDING")
edge("CATA_488t","FIRE","takes_damage_generate_spell","TEXT_REVIEW_EVENT_TIMING_PENDING")
edge("CATA_488t2","FIRE","takes_damage_generate_spell","TEXT_REVIEW_EVENT_TIMING_PENDING")
edge("CATA_484","WHELP_WORKING","discover_1_cost_class_spell","PROVISIONAL")
edge("TLC_249","RANDOM_SPLIT_DAMAGE_TARGETS","deathrattle_damage","MANUAL_FULL_DEFINITION_TEXT_REVIEW")
nodes["RANDOM_SPLIT_DAMAGE_TARGETS"]={"kind":"ACTION_TARGET_SELECTOR","predicate":"Dynamic enemy characters, not generated card pool","reviewed_closure":False}

# Recursion witnesses found in actual pinned contracts, not proof that the frontier is closed.
for i in ["JAIL_122","JAIL_986","CATA_EVENT_000","EDR_519","FIR_959","EDR_102","CATA_979"]:
    if i in nodes:
        c=metadata[i]; nodes[i]["architecture_witness"]=c.get("text","")
for i,pool in [("JAIL_122","MINION_BASE_COST_EQUALS_CAST_SPELL"),("JAIL_986","ANY_PLAYABLE_SPELL_TEMPORARY"),
               ("CATA_EVENT_000","COLOSSAL_FROM_PAST"),("CATA_979","SPELL_BASE_COST_EQUALS_SPLIT_SOURCE")]:
    if i in nodes:
        add_pool(pool)
        edge(i,pool,"frontier_text_reviewed_dynamic_dependency","MEMBERSHIP_UNRESOLVED")
# Actual Battlecry pool -> Whelp -> Blazing -> same Battlecry pool gives a definite candidate-graph cycle.
# Other frontier nodes retain canonical source-reference lower bounds with explicit unresolved status.
for i in list(nodes):
    if i in metadata and i not in union and i in registry["cards"]:
        d=registry["cards"][i]["dependencies"]
        for candidate in d["known_source_candidates"]:
            card_node(candidate["to"],"SOURCE_CANDIDATE")
            edge(i,candidate["to"],candidate["kind"],candidate["evidence_status"])
        for pool in d["dynamic_pool_ids"]:
            add_pool(pool, limitations=["Inherited canonical heuristic pool signal, not exhaustive or rules-reviewed."])
            edge(i,pool,"canonical_dynamic_signal","UNREVIEWED_SOURCE_CANDIDATE")

adj=defaultdict(list)
for e in edges: adj[e["from"]].append(e["to"])
def reachable(start):
    seen={start};queue=deque([start])
    while queue:
        for target in adj[queue.popleft()]:
            if target not in seen: seen.add(target);queue.append(target)
    return seen
fire_reach=reachable("FIRE");whelp_reach=reachable("WHELP_WORKING")
sccs=[]
# Iterative Kosaraju: candidate-graph SCCs do not assert executable rules closure.
seen=set();finished=[]
for start in sorted(nodes):
    if start in seen:continue
    stack=[(start,False)]
    while stack:
        node,done=stack.pop()
        if done:finished.append(node);continue
        if node in seen:continue
        seen.add(node);stack.append((node,True))
        stack.extend((target,False) for target in reversed(adj[node]) if target not in seen)
reverse=defaultdict(list)
for e in edges:reverse[e["to"]].append(e["from"])
seen=set()
for start in reversed(finished):
    if start in seen:continue
    component=[];stack=[start];seen.add(start)
    while stack:
        node=stack.pop();component.append(node)
        for target in reverse[node]:
            if target not in seen:seen.add(target);stack.append(target)
    if len(component)>1 or start in adj[start]:sccs.append(sorted(component))
frontier_cards=sorted(i for i in set(nodes)&set(metadata) if i not in union)
graph={"schema_version":1,"sources":sources,"graph_scope":"DIRECT_CONTRACTS + FINITE_POOL_ENVELOPES + CANONICAL_LOWER_BOUND + SELECTED_SECOND_ORDER_RULES_WITNESSES",
       "closure_complete":False, "nodes":nodes, "edges":edges,
       "cyclic_components":sccs,
       "fire_reachable_standard_card_envelope_count":len(set(metadata)&fire_reach),
       "whelp_reachable_standard_card_envelope_count":len(set(metadata)&whelp_reach),
       "union_reachable_standard_card_envelope_count":len(set(metadata)&(fire_reach|whelp_reach)),
       "frontier_card_ids_not_fully_audited":frontier_cards,
       "terminal_unresolved_pool_ids":sorted(i for i,n in nodes.items() if n.get("kind")=="POOL" and n.get("members") is None),
       "limits":["No full rules audit of all frontier cards", "No exact runtime/hidden-zone pool snapshot",
                 "No Wild 'from the past' predicate closure", "No current Dark Gift runtime option membership or execution verification",
                 "No implementation or evidence admission"]}
dump("DYNAMIC_GENERATION_DEPENDENCY_GRAPH.json",graph)

lines=["# Capability matrix — manual contract audit","","No implementation/rules status promotion. JSON retains all requested axes, exact text and declarations.",
       "F=Fire candidate; W=raw Whelp candidate; WC=working Whelp class candidate. Quest and neutral rows retained for exclusion review.","",
       "| ID | Name | Pools | Family | Targeting | New/unreviewed facets | Fixed deps | Dynamic frontier |",
       "|---|---|---|---|---|---|---|---|"]
def cell(s):return str(s).replace("|","/").replace("\n"," ")
for row in matrix:
    pools=("F " if row["pool_membership"]["fire_candidate"] else "")+("W " if row["pool_membership"]["whelp_raw_candidate"] else "")+("WC" if row["pool_membership"]["whelp_working_class_candidate"] else "")
    lines.append("| "+" | ".join(cell(s) for s in [row["card_id"],row["name"],pools,row["semantic_family"],row["targeting"],
        ", ".join(row["new_or_unreviewed_capabilities"]),", ".join(x["card_id"] for x in row["fixed_generated_dependencies"]),", ".join(row["dynamic_generated_dependencies"])])+" |")
(OUT/"DYNAMIC_GENERATION_CAPABILITY_MATRIX.md").write_text("\n".join(lines)+"\n",encoding="utf-8",newline="\n")

lines = ["# Family planning candidates", "",
         "Potential outcomes addressed, not verified cards gained. F/W = Fire/working-class Whelp. Counts overlap across pools.",
         "51 buckets are planning classifications, not 51 approved executable packages. Split mixed facets before a proposal.", "",
         "| Family | IDs | F/W | Shared facets to review/add | Fixed dependency IDs | Dynamic frontiers | Risk / complexity | Model |", 
         "|---|---|---|---|---|---|---|---|"]
for p in packages:
    lines.append("| " + " | ".join(cell(s) for s in [p["proposed_family"], ", ".join(p["candidate_ids"]),
        f'{p["fire_candidates_addressed"]}/{p["whelp_working_candidates_addressed"]}',
        ", ".join(p["expected_shared_changes"]) or "Existing facets; verification still required",
        ", ".join(p["fixed_dependency_candidates"]), ", ".join(p["dynamic_frontiers"]),
        f'{p["rules_risk"]} / {p["implementation_complexity"]}', p["model_recommendation"]]) + " |")
(OUT / "DYNAMIC_GENERATION_FAMILY_PLAN.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

summary={"fire_candidates":len(fire),"whelp_raw":len(whelp_raw),"whelp_quests_excluded_working":len(quests),
         "whelp_neutral_pending":len(neutral),"whelp_nonquest":len(whelp_nonquest),"whelp_class_working":len(whelp_class_working),
         "overlap":len(set(fire)&set(whelp_raw)),"union":len(union),"working_union":len(set(fire)|set(whelp_class_working)),
         "fire_declared":sum(i in decl for i in fire),"whelp_working_declared":sum(i in decl for i in whelp_class_working),
         "union_declared":sum(i in decl for i in union),"family_count":len(packages),"graph_nodes":len(nodes),"graph_edges":len(edges),
         "fire_reachable_envelope":graph["fire_reachable_standard_card_envelope_count"],
         "whelp_reachable_envelope":graph["whelp_reachable_standard_card_envelope_count"],
         "union_reachable_envelope":graph["union_reachable_standard_card_envelope_count"],
         "unresolved_pool_frontiers":len(graph["terminal_unresolved_pool_ids"]),
         "fire_hash":ids_hash(fire),"working_whelp_hash":ids_hash(whelp_class_working)}
dump("DYNAMIC_GENERATION_AUDIT_SUMMARY.json",summary)
print(json.dumps(summary,indent=2))
