"""Build a reproducible pool/dependency audit for selected Dark Gift cards."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_card_support_analysis import collect_card_blocks, sample_stratum  # noqa: E402

CATALOG = ROOT / "data/cards/standard_current_enUS.json"
DECKS = ROOT / "data/samples/standard_meta_deck_pool_20260928.json"
OUTPUT = ROOT / "reports/dark_gift_support_audit_20260929.json"
CARD_SOURCES = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets"
CARD_RULES = ROOT / "integrations/rosettastone/card_rules"
TARGETS = {"EDR_456", "FIR_939", "EDR_856"}
DECK_NAMES = {"Dragon Warrior", "Quest Priest"}
SOURCE_REVIEWED_POOL_ROOTS = {"CATA_140", "CATA_556", "EDR_456", "FIR_959"}
RULE_SOURCE_FILES = (
    "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/CoreCardsGen.cpp",
    "vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/RandomCardTask.cpp",
    "vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/CastRandomSpellTask.cpp",
    "vendor/RosettaStone/Sources/Rosetta/PlayMode/Loaders/CardLoader.cpp",
    "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindDarkGiftCardsGen.cpp",
    "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindDragonPoolCardsGen.cpp",
    "vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/DarkGiftDiscoverTask.cpp",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    catalog_doc = json.loads(CATALOG.read_text(encoding="utf-8"))
    cards = {card["id"]: card for card in catalog_doc["cards"] if card.get("id")}
    deck_doc = json.loads(DECKS.read_text(encoding="utf-8"))
    decks = {deck["name"]: deck for deck in deck_doc["decks"]}
    missing = TARGETS - cards.keys()
    if missing:
        raise SystemExit(f"catalog is missing selected Dark Gift cards: {sorted(missing)}")
    if not DECK_NAMES <= decks.keys():
        raise SystemExit(f"deck pool is missing expected lists: {sorted(DECK_NAMES - decks.keys())}")

    standard_minions = {
        card_id: card
        for card_id, card in cards.items()
        if card.get("collectible") and card.get("type") == "MINION"
    }
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(CARD_SOURCES.glob("*CardsGen.cpp"))
    )
    source_blocks = collect_card_blocks()
    direct_ids = set(re.findall(r'cards\.emplace\(\s*"([A-Za-z0-9_]+)"', source_text))
    generated_routes: dict[str, str] = {}
    generated_dependencies: dict[str, list[str]] = {}
    for manifest_name, route in (
        ("core_aliases.generated.json", "generated_core_alias"),
        ("effect_composition.generated.json", "generated_effect_composition"),
    ):
        manifest_path = CARD_RULES / manifest_name
        if manifest_path.exists():
            for item in json.loads(manifest_path.read_text(encoding="utf-8")).get("cards", []):
                generated_routes[item["card_id"]] = route
                dependencies = item.get("dependencies", [])
                generated_dependencies[item["card_id"]] = sorted({
                    dep["card_id"] if isinstance(dep, dict) else dep
                    for dep in dependencies
                    if isinstance(dep, str) or (isinstance(dep, dict) and dep.get("card_id"))
                })
    resource_doc = json.loads(
        (ROOT / "vendor/RosettaStone/Resources/cards.json").read_text(encoding="utf-8-sig")
    )
    metadata = {card["id"]: card for card in resource_doc if card.get("id")}
    metadata.update(cards)
    def node_dependencies(card_id: str) -> list[str]:
        if card_id in generated_dependencies:
            return generated_dependencies[card_id]
        return source_blocks.get(card_id, {}).get("referenced_card_ids", [])

    def node_inventory(card_id: str) -> dict:
        card = metadata.get(card_id, {})
        card_type = card.get("type")
        route = generated_routes.get(card_id)
        if route is None:
            if card_id in source_blocks:
                route = "direct_carddef"
            elif not card.get("text", "").strip():
                route = "textless_metadata" if card else "missing_metadata"
            else:
                route = "missing_carddef"
        return {
            "card_id": card_id,
            "name": card.get("name"),
            "card_type": card_type,
            "registration_route": route,
            "dependency_ids": node_dependencies(card_id),
            "task_types": source_blocks.get(card_id, {}).get("task_types", []),
        }

    def inspect_literal_closure(root_id: str) -> dict:
        queue = [root_id]
        visited: set[str] = set()
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            node = node_inventory(current)
            nodes[current] = node
            if node["registration_route"] not in {"direct_carddef", "generated_core_alias", "generated_effect_composition", "textless_metadata"}:
                continue
            for dependency_id in node["dependency_ids"]:
                dependency = node_inventory(dependency_id)
                ref_kind = "ENCHANTMENT_REFERENCE" if dependency.get("card_type") == "ENCHANTMENT" else "CARD_REFERENCE"
                edges.append({"from": current, "to": dependency_id, "kind": ref_kind})
                if ref_kind == "CARD_REFERENCE" and dependency["registration_route"] not in {"textless_metadata", "missing_metadata"}:
                    queue.append(dependency_id)
                elif ref_kind == "CARD_REFERENCE":
                    nodes.setdefault(dependency_id, dependency)
        unresolved = sorted(
            card_id for card_id, node in nodes.items()
            if node["card_type"] != "ENCHANTMENT"
            and node["registration_route"] in {"missing_carddef", "missing_metadata"}
        )
        dynamic_hints = []
        random_target_hints = []
        choice_hints = []
        for card_id, node in nodes.items():
            card = metadata.get(card_id, {})
            text = card.get("text", "").lower()
            tasks = node.get("task_types", [])
            task_text = " ".join(tasks).lower()
            card_pool_wording = bool(re.search(
                r"\b(discover|random)\b.{0,80}\b(cards?|minions?|dragons?|spells?|weapons?)\b",
                text,
            ))
            card_pool_task = any(
                marker in task_text
                for marker in ("randomcard", "discover", "castrandomspell", "darkgiftdiscover")
            )
            random_target_wording = bool(re.search(
                r"\brandom(?:ly)?\s+(?:enemy|opponent|friendly|allied)\b", text
            ))
            if card_pool_wording or card_pool_task or card_id in SOURCE_REVIEWED_POOL_ROOTS:
                dynamic_hints.append(card_id)
            elif random_target_wording:
                random_target_hints.append(card_id)
            if "choose" in text:
                choice_hints.append(card_id)
        return {
            "root_card_id": root_id,
            "literal_nodes": [nodes[key] for key in sorted(nodes)],
            "literal_edges": sorted(edges, key=lambda edge: (edge["from"], edge["to"])),
            "unresolved_literal_card_ids": unresolved,
            "dynamic_pool_review_card_ids": sorted(dynamic_hints),
            "random_target_review_card_ids": sorted(random_target_hints),
            "choice_rule_review_card_ids": sorted(choice_hints),
            "literal_closure_status": "MISSING_LITERAL_DEPENDENCY" if unresolved else "LITERAL_REFERENCES_RESOLVED",
            "dynamic_pool_status": "REQUIRES_RULE_REVIEW" if dynamic_hints else (
                "RANDOM_TARGET_ONLY" if random_target_hints else "NO_STATIC_DYNAMIC_HINT"
            ),
            "correctness_status": "UNVERIFIED",
        }
    dragons = sorted(
        card_id for card_id, card in standard_minions.items() if card.get("race") == "DRAGON"
    )
    warriors = sorted(
        card_id
        for card_id, card in standard_minions.items()
        if card.get("cardClass") == "WARRIOR"
    )
    low_cost_dragons = sorted(
        card_id for card_id in dragons if int(standard_minions[card_id].get("cost", 0)) <= 3
    )
    fire_spells = sorted(
        card_id
        for card_id, card in cards.items()
        if card.get("collectible")
        and card.get("type") == "SPELL"
        and str(card.get("spellSchool", card.get("spell_school", ""))).upper() in {"FIRE", "SPELLSCHOOL_FIRE"}
        and int(card.get("cost", 0)) > 0
        and "QUEST" not in {str(tag).upper() for tag in card.get("mechanics", [])}
    )

    def pool_evidence(card_ids: list[str]) -> dict:
        routes = [node_inventory(card_id)["registration_route"] for card_id in card_ids]
        return {
            "metadata_candidate_count": len(card_ids),
            "metadata_candidate_card_ids": card_ids,
            "registration_routes": {
                route: routes.count(route) for route in sorted(set(routes))
            },
            "membership_status": "METADATA_PREDICATE_ONLY_ENGINE_POOL_PARITY_UNVERIFIED",
        }

    dynamic_rule_profiles = {
        "CAP_107t": {
            "kind": "RANDOM_BOARD_TARGET",
            "predicate": "random enemy character currently legal for the token's 1 damage effect",
            "card_pool_dependency": False,
            "evidence": "CardDef uses the current opponent hero and minions; no random card selection.",
            "correctness_status": "UNVERIFIED",
        },
        "CATA_140": {
            "kind": "RANDOM_CARD_POOL",
            "predicate": "collectible Standard minion with race DRAGON",
            **pool_evidence(dragons),
            "extra_runtime_behavior": "Repeatedly add random results until hand is full; set each generated card Cost to 1 when source script data records at least 25 Mana spent while held.",
            "correctness_status": "UNVERIFIED",
        },
        "CATA_556": {
            "kind": "RANDOM_CARD_POOL",
            "predicate": "collectible Standard minion with race DRAGON and printed Cost <= 3",
            **pool_evidence(low_cost_dragons),
            "correctness_status": "UNVERIFIED",
        },
        "EDR_456": {
            "kind": "DARK_GIFT_DISCOVER_POOL",
            "predicate": "collectible Standard minion with race DRAGON, then gift compatibility and distinct-option constraints",
            **pool_evidence(dragons),
            "gift_eligibility_status": "SEE_SCOPED_DARK_GIFT_RULES; ALL_OUTCOME_RULES_UNVERIFIED",
            "correctness_status": "UNVERIFIED",
        },
        "FIR_959": {
            "kind": "RANDOM_CARD_POOL_WITH_STATE_DEPENDENT_FILTERS",
            "predicate": "collectible Standard spell of FIRE school, not a Quest, positive printed Cost, with a legal enemy target when the spell requires a target; each cast Cost must fit the remaining 15-Mana budget",
            **pool_evidence(fire_spells),
            "extra_runtime_behavior": "Cast random eligible spells until 15 Mana is spent or no candidate remains (hard cap 30 casts); random spell effects can open further choices/pools.",
            "correctness_status": "UNVERIFIED",
        },
    }
    quest_priest_minions = sorted(
        card_id
        for card_id in set(decks["Quest Priest"]["cards"])
        if card_id in cards and cards[card_id].get("type") == "MINION"
    )
    xavius_deck_candidates = [card_id for card_id in quest_priest_minions if card_id != "EDR_856"]
    selected = {
        card_id: {
            "name": cards[card_id].get("name"),
            "card_type": cards[card_id].get("type"),
            "text": cards[card_id].get("text"),
        }
        for card_id in sorted(TARGETS)
    }
    overlap = sorted(set(dragons) & set(warriors))
    candidate_inventory = []
    for card_id in sorted(set(dragons) | set(warriors)):
        card = standard_minions[card_id]
        has_text = bool(card.get("text", "").strip())
        if card_id in generated_routes:
            route = generated_routes[card_id]
        elif card_id in direct_ids:
            route = "direct_carddef"
        elif not has_text:
            route = "textless_metadata"
        else:
            route = "missing"
        candidate_inventory.append({
            "card_id": card_id,
            "name": card.get("name"),
            "dbf_id": card.get("dbfId"),
            "card_class": card.get("cardClass"),
            "set": card.get("set"),
            "dragon_candidate": card_id in dragons,
            "warrior_candidate": card_id in warriors,
            "card_type": card.get("type"),
            "text": card.get("text", ""),
            "mechanics": card.get("mechanics", []),
            "has_rules_text": has_text,
            "registration_route": route,
            "triage_stratum": sample_stratum(card),
            "rule_verification": "UNVERIFIED",
            "transitive_dependencies": "NOT_AUDITED",
            "source_evidence": source_blocks.get(card_id) if route == "direct_carddef" else None,
            "dependency_closure": (
                inspect_literal_closure(card_id)
                if route in {"direct_carddef", "generated_core_alias", "generated_effect_composition"}
                else {
                    "root_card_id": card_id,
                    "literal_closure_status": "BLOCKED_UNREGISTERED_ROOT",
                    "dynamic_pool_status": "NOT_AUDITED",
                    "correctness_status": "UNVERIFIED",
                }
            ),
        })
    report = {
        "schema_version": 2,
        "generated_for": "Dark Gift rules and candidate-pool scope; not a correctness or training-eligibility claim",
        "catalog_valid_as_of": catalog_doc.get("valid_as_of"),
        "catalog_sha256": sha256(CATALOG),
        "deck_pool_sha256": sha256(DECKS),
        "rule_source_sha256": {
            path: sha256(ROOT / path) for path in RULE_SOURCE_FILES if (ROOT / path).exists()
        },
        "selected_cards": selected,
        "gifts": [
            {"id": 1, "effect": "+3 Attack, Lifesteal"},
            {"id": 2, "effect": "+2/+2, Elusive"},
            {"id": 3, "effect": "Cost -2, Attack -2; resulting Attack must remain at least 1"},
            {"id": 4, "effect": "Charge"},
            {"id": 5, "effect": "Playing minion summons a 2/2 copy"},
            {"id": 6, "effect": "Battlecries trigger twice; Battlecry required"},
            {"id": 7, "effect": "+4 Health, Taunt"},
            {"id": 8, "effect": "Reborn; returns with full Health and enchantments"},
            {"id": 9, "effect": "+4/+5; put card on top of deck"},
            {"id": 10, "effect": "Divine Shield, Windfury"},
        ],
        "candidate_pools": {
            "EDR_456": {"predicate": "collectible Standard minion with race DRAGON", "count": len(dragons), "card_ids": dragons},
            "FIR_939": {"predicate": "collectible Standard minion with cardClass WARRIOR", "count": len(warriors), "card_ids": warriors},
            "EDR_856": {
                "predicate": "actual minion entities in saved Quest Priest deck, excluding played Xavius card ID",
                "count": len(xavius_deck_candidates),
                "card_ids": xavius_deck_candidates,
            },
        },
        "manual_dynamic_rule_review": {
            "profiles": dynamic_rule_profiles,
            "interpretation": "Source-reviewed predicates and catalog-derived member candidates; not proof that runtime and metadata pools match or that effects are correct.",
        },
        "candidate_rule_inventory": candidate_inventory,
        "candidate_rule_inventory_summary": {
            "total_unique_candidates": len(candidate_inventory),
            "by_registration_route": {
                route: sum(item["registration_route"] == route for item in candidate_inventory)
                for route in sorted({item["registration_route"] for item in candidate_inventory})
            },
            "unregistered_by_text_stratum": {
                stratum: sum(
                    item["registration_route"] == "missing"
                    and item["triage_stratum"] == stratum
                    for item in candidate_inventory
                )
                for stratum in sorted({item["triage_stratum"] for item in candidate_inventory})
            },
            "all_rule_verification": "UNVERIFIED",
            "registered_roots_with_missing_literal_dependencies": sum(
                item.get("dependency_closure", {}).get("literal_closure_status") == "MISSING_LITERAL_DEPENDENCY"
                for item in candidate_inventory
            ),
            "registered_roots_with_dynamic_pool_review": sum(
                item.get("dependency_closure", {}).get("dynamic_pool_status") == "REQUIRES_RULE_REVIEW"
                for item in candidate_inventory
            ),
            "dependency_closure": "LITERAL_REFERENCES_SCANNED_FOR_REGISTERED_ROOTS; DYNAMIC_RULE_POOLS_STILL_REQUIRE_MANUAL_REVIEW",
        },
        "pool_relationship": {"dragon_warrior_overlap_count": len(overlap), "dragon_warrior_overlap_ids": overlap, "union_count": len(set(dragons) | set(warriors))},
        "limitations": [
            "Candidate-pool metadata does not implement the Dark Gift choice or effect.",
            "Selected minion future behavior remains a transitive dependency; unsupported candidates cannot be hidden in strict training.",
            "Gift-specific card behavior is not inferred from rules text or metadata by this script.",
            "Dynamic card-pool membership is derived from the pinned metadata snapshot; compare it with the engine's loaded Standard pool and current ban rules before treating it as runtime closure.",
            "A random board target, such as CAP_107t, is not a dynamic card-pool dependency even though rules text contains the word random.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
        OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Dark Gift audit: Dragon pool={len(dragons)}, Warrior pool={len(warriors)}, union={report['pool_relationship']['union_count']}, Xavius deck pool={len(xavius_deck_candidates)}")
    print(f"Wrote {OUTPUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
