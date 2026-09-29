"""Build a reproducible RosettaStone card capability and dependency audit.

The report deliberately distinguishes source registration from verified rules.
Text-based strata are used only to select a small, repeatable extension sample.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor/RosettaStone"
STAMP = "20260929"
POOL_PATH = "data/samples/standard_meta_deck_pool_20260928.json"
CATALOG_PATH = "data/cards/standard_current_enUS.json"
COVERAGE_PATH = "reports/standard_meta_coverage_20260928.json"
CORE_ALIAS_MANIFEST = "integrations/rosettastone/card_rules/core_aliases.generated.json"
QUOTAS = {"choice_random_generated": 7, "triggered": 7, "composed": 6, "single_effect": 6}

ROUTE_GUIDANCE = {
    "AUTO": "Known metadata/keyword behavior or a constrained declarative mapping; still requires scenario verification.",
    "COMPOSABLE": "Existing Tasks/Power/targeting primitives appear sufficient; composition and dependencies need review.",
    "MISSING_PRIMITIVE": "A shared mechanic, event/state contract, or dependency behavior must be implemented/reviewed first.",
    "CUSTOM": "Card-specific or stateful behavior is a better fit for a named native implementation.",
    "UNKNOWN": "Text/ruling or source mapping is not clear enough to choose an implementation route.",
}

# Manual route decisions for cards in the stratified extension. These are engineering
# routes to investigate, not claims that the effect is currently implemented.
EXTENSION_ROUTES = {
    "TIME_436": ("UNKNOWN", "Advance to the Present is a named mechanic whose state transition needs ruling/source inspection."),
    "TIME_712": ("COMPOSABLE", "Destroy plus Combo random-minion generation; verify Combo hook and exact pool."),
    "EDR_570": ("COMPOSABLE", "Choose One effects appear expressible with existing destroy/summon operations."),
    "TLC_438": ("MISSING_PRIMITIVE", "Randomly select from own deck by cost and cast onto this minion; target and card-zone semantics need a contract."),
    "CORE_KAR_062": ("COMPOSABLE", "Hand condition plus Discover race filter; verify chooser continuation and race pool."),
    "CATA_498": ("MISSING_PRIMITIVE", "Repeated random target damage with an upgrade/state counter across turns."),
    "CORE_RLK_116": ("MISSING_PRIMITIVE", "Requires game-history tracking for friendly Undead deaths and rune-filtered Discover."),
    "CATA_724": ("COMPOSABLE", "Deathrattle unlocks overloaded mana and applies Overload; verify timing and resource semantics."),
    "EDR_845": ("MISSING_PRIMITIVE", "Start-of-game deck condition plus repeated Imbue progress from Nature spells."),
    "CORE_CATA_001": ("COMPOSABLE", "Battlecry plus a same-turn cost aura for the next Demon; verify hand-zone aura lifetime."),
    "CATA_553": ("CUSTOM", "Game-long Dragon Rush effect and conditional transformation of cards in hand require coordinated state handling."),
    "MEND_506": ("MISSING_PRIMITIVE", "Changes Leyline effects for the rest of the game; enumerate affected spell families first."),
    "CORE_EDR_003": ("MISSING_PRIMITIVE", "Corpse resource gain multiplier and an alternate corpse-spend draw action."),
    "JAIL_457": ("MISSING_PRIMITIVE", "Prepare timing plus a board-wide effect needs the exact Prepare contract."),
    "TIME_443": ("CUSTOM", "Summon two Hounds and force an attack selected by lowest enemy Health when deck has no minions."),
    "CATA_479": ("MISSING_PRIMITIVE", "Shatter keyword and its summon/buff interaction need source and timing review."),
    "DINO_432": ("COMPOSABLE", "Set stats, grant Stealth, then draw; verify silence/stat reset behavior."),
    "DINO_429": ("MISSING_PRIMITIVE", "Attaches a Deathrattle that sets the minion's stats; dynamic Deathrattle/enchantment needs review."),
    "TLC_819": ("MISSING_PRIMITIVE", "Discount checks whether both Holy and Shadow spells were cast this turn."),
    "CORE_BAR_801": ("COMPOSABLE", "Damage plus a fixed Rush token summon."),
    "CORE_EX1_145": ("COMPOSABLE", "Temporary discount to the next spell; verify existing aura implementation and lifetime."),
    "CORE_EX1_010": ("AUTO", "Keyword/stat-only minion candidate; verify metadata loader and registration status."),
    "CORE_LOOT_044": ("MISSING_PRIMITIVE", "Weapon Attack follows Armor dynamically and cannot attack heroes."),
    "TIME_027": ("MISSING_PRIMITIVE", "Split damage plus shuffle generated Shreds of Time into deck."),
    "CATA_475": ("COMPOSABLE", "End-of-turn trigger with area damage; verify trigger ownership and duration."),
    "CS3_007": ("AUTO", "Keyword/resource metadata candidate; verify metadata loader and Overload semantics."),
    "CORE_WC_042": ("COMPOSABLE", "After-Elemental-play trigger plus permanent Attack gain; verify event source and turn scope."),
    "CATA_452": ("MISSING_PRIMITIVE", "Discount depends on spell damage actually dealt this turn, requiring event history and cost recalculation."),
    "TIME_044": ("UNKNOWN", "Advance to the Present has no resolved source contract in this audit."),
}

SELECTED_MISSING_ROUTES = {
    "EDR_456": ("MISSING_PRIMITIVE", "Dark Gift Discover needs the exact gift-choice pool and application semantics."),
    "FIR_939": ("MISSING_PRIMITIVE", "Dark Gift Discover requires a Warrior-minion pool and a damage-then-choice continuation."),
    "EDR_856": ("MISSING_PRIMITIVE", "Discover from own deck followed by Dark Gift application needs deck-choice/gift semantics."),
    "TIME_034": ("MISSING_PRIMITIVE", "Rewind setup plus independent random weapon generation for both players needs timing and pool verification."),
    "CATA_139": ("MISSING_PRIMITIVE", "Colossal appendages exist as a property, but stat changes must propagate to the correct parent entity."),
    "MEND_046": ("CUSTOM", "Carve embeds 12 Mana of Nature spells into three generated Treants; likely requires a named stateful native handler."),
    "TLC_100": ("CUSTOM", "Builds a custom Location from the deck's starting cost distribution; dynamic output is card-specific."),
    "CAP_805": ("MISSING_PRIMITIVE", "Must preserve the set of each player's destroyed minions and produce per-player resummon spells."),
    "JAIL_912": ("MISSING_PRIMITIVE", "Prepare semantics and subsequent Deathrattle need an independently verified timing contract."),
    "TLC_817": ("MISSING_PRIMITIVE", "Two sequential school-specific Quest conditions and rewards require progression/order support."),
}

VERIFIED_SCOPES = {
    "CORE_SW_108": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp", "scope": "2 damage to minion and Second Flame added to hand"},
    "CORE_BAR_801": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp", "scope": "1 damage and 1/1 Rush token summon"},
    "CORE_SW_088": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp", "scope": "3 damage and two 1/3 Taunt token summons"},
    "CORE_EX1_278": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp", "scope": "1 damage and one card drawn"},
    "CORE_EX1_058": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp", "scope": "Battlecry grants Taunt to one adjacent minion"},
    "CORE_CS2_004": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp", "scope": "+2 Health enchantment then draw"},
    "END_007": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp", "scope": "target damage, temporary hero attack, draw, and armor"},
    "CAP_801": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp", "scope": "+2/+3, Taunt, and Reborn on one minion"},
    "CORE_SW_066": {"test": "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp", "scope": "Battlecry silence on selected minion"},
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm_text(value: str) -> str:
    return re.sub(r"<[^>]+>|\[[^]]+\]|[^a-z0-9]+", " ", value.lower()).strip()


def sample_stratum(card: dict) -> str:
    text = norm_text(card.get("text", ""))
    mechanics = set(card.get("mechanics", []))
    if re.search(r"discover|random|choose|cast .* card|add .* (to your|to their) hand|transform|copy|resurrect|resummon", text):
        return "choice_random_generated"
    if mechanics & {"BATTLECRY", "DEATHRATTLE", "SPELLBURST", "FRENZY", "COMBO", "START_OF_GAME_KEYWORD", "OUTCAST", "HONORABLE_KILL", "QUEST"} or re.match(r"(after|at the start|at the end|whenever|when)\b", text):
        return "triggered"
    ops = re.findall(r"\b(deal|draw|summon|give|gain|restore|destroy|freeze|silence|equip|add|reduce|set)\b", text)
    if len(ops) >= 2 or re.search(r"\b(if|then|for each|after you|while)\b", text):
        return "composed"
    return "single_effect"


def stable_sample(cards: list[dict], excluded: set[str]) -> list[dict]:
    strata: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for c in cards:
        if c.get("collectible") and c.get("text", "").strip() and c["id"] not in excluded:
            strata[sample_stratum(c)][c.get("cardClass", "NEUTRAL")].append(c)
    for classes in strata.values():
        for values in classes.values():
            values.sort(key=lambda c: hashlib.sha256(("ManaMind20260929:" + c["id"]).encode()).hexdigest())
    chosen: list[dict] = []
    class_counts: Counter[str] = Counter()
    for stratum, quota in QUOTAS.items():
        for _ in range(quota):
            available = [cl for cl, rows in strata[stratum].items() if rows]
            if not available:
                raise RuntimeError(f"sample quota unavailable: {stratum}")
            available.sort(key=lambda cl: (class_counts[cl], hashlib.sha256((stratum + cl + "ManaMind20260929").encode()).hexdigest()))
            cl = available[0]
            card = strata[stratum][cl].pop(0)
            card = dict(card)
            card["sampling_stratum"] = stratum
            chosen.append(card)
            class_counts[cl] += 1
    return chosen


def collect_card_blocks() -> dict[str, dict]:
    blocks = {}
    base = VENDOR / "Sources/Rosetta/PlayMode/CardSets"
    for path in sorted(base.glob("*CardsGen.cpp")):
        source = path.read_text(encoding="utf-8", errors="replace")
        clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
        matches = list(re.finditer(r"cards\.emplace\(\s*\"([^\"]+)\"", clean))
        for index, match in enumerate(matches):
            start = clean.rfind(".ClearData();", 0, match.start())
            if start < 0:
                start = max(0, match.start() - 1200)
            else:
                start = clean.rfind("\n", 0, start) + 1
            end = matches[index + 1].start() if index + 1 < len(matches) else min(len(clean), match.end() + 5000)
            # Limit each block to next clear: emplace order varies across files.
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


def git_fingerprint() -> dict:
    result = {"revision": None, "status": "unavailable", "note": "Git ownership check prevented reading revision; no global safe.directory setting was changed."}
    try:
        p = subprocess.run(["git", "-c", f"safe.directory={VENDOR.as_posix()}", "-C", str(VENDOR), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        if p.returncode == 0:
            result.update(revision=p.stdout.strip(), status="read", note=None)
            s = subprocess.run(["git", "-c", f"safe.directory={VENDOR.as_posix()}", "-C", str(VENDOR), "status", "--short"], capture_output=True, text=True, timeout=10)
            if s.returncode == 0:
                result["working_tree_status_lines"] = len([x for x in s.stdout.splitlines() if x.strip()])
                result["working_tree_status_sample"] = s.stdout.splitlines()[:30]
        else:
            result["note"] = p.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        result["note"] = str(e)
    return result


def build():
    catalog_doc = read_json(ROOT / CATALOG_PATH)
    catalog = {c["id"]: c for c in catalog_doc["cards"] if c.get("id")}
    pool = read_json(ROOT / POOL_PATH)
    coverage = read_json(ROOT / COVERAGE_PATH)
    blocks = collect_card_blocks()
    alias_manifest_path = ROOT / CORE_ALIAS_MANIFEST
    generated_aliases = {}
    if alias_manifest_path.exists():
        alias_manifest = read_json(alias_manifest_path)
        if alias_manifest.get("schema_version") == 1:
            generated_aliases = {x["card_id"]: x["base_card_id"] for x in alias_manifest.get("cards", [])}
    composition_manifest_path = ROOT / "integrations/rosettastone/card_rules/effect_composition.generated.json"
    generated_compositions = {}
    if composition_manifest_path.exists():
        composition_manifest = read_json(composition_manifest_path)
        if composition_manifest.get("schema_version") == 1:
            generated_compositions = {x["card_id"]: x for x in composition_manifest.get("cards", [])}
    all_card_ids = {c.get("id") for c in read_json(VENDOR / "Resources/cards.json") if c.get("id")}
    all_card_ids.update(catalog)
    resource_cards = {c.get("id"): c for c in read_json(VENDOR / "Resources/cards.json") if c.get("id")}
    for block in blocks.values():
        block["referenced_card_ids"] = [cid for cid in block["referenced_card_ids"] if cid in all_card_ids]
    alias_pairs = []
    for card_id, current in sorted(catalog.items()):
        if not card_id.startswith("CORE_"):
            continue
        base_id = card_id[5:]
        base = resource_cards.get(base_id) or catalog.get(base_id)
        if not base or base_id not in blocks or current.get("countAsCopyOfDbfId") != base.get("dbfId"):
            continue
        equal_text = norm_text(current.get("text", "")) == norm_text(base.get("text", ""))
        direct = card_id in blocks
        generated_alias = card_id in generated_aliases
        generated_composition = card_id in generated_compositions
        alias_pairs.append({"core_card_id": card_id, "base_card_id": base_id, "name": current.get("name"),
            "copy_of_dbf_id": current.get("countAsCopyOfDbfId"), "base_dbf_id": base.get("dbfId"),
            "rules_text_equal_after_markup_normalization": equal_text, "direct_core_definition_exists": direct,
            "generated_alias_registered": generated_alias, "effect_composition_registered": generated_composition,
            "candidate_for_alias": equal_text and not direct and not generated_alias and not generated_composition,
            "base_source": blocks[base_id],
            "reason_excluded": None if equal_text else "Core text differs from base; copying it would omit a current effect."})
    alias_by_id = {x["core_card_id"]: x for x in alias_pairs}
    remaining_alias_candidates = sum(x["candidate_for_alias"] for x in alias_pairs)
    alias_candidate_count = remaining_alias_candidates + len(generated_aliases)
    target_ids = {c["card_id"] for c in coverage["cards"]}
    extension = stable_sample(catalog_doc["cards"], target_ids)
    sample = []
    for c in coverage["cards"]:
        meta = catalog.get(c["card_id"], {})
        alias_base = generated_aliases.get(c["card_id"])
        composition = generated_compositions.get(c["card_id"])
        block = blocks.get(c["card_id"], blocks.get(alias_base, {}) if alias_base else {})
        direct_registered = c["card_id"] in blocks
        rules_registered = direct_registered or c["card_id"] in generated_aliases or composition is not None
        if not rules_registered or not norm_text(c.get("text", "")):
            route, reason = (SELECTED_MISSING_ROUTES.get(c["card_id"]) or ("UNKNOWN", "No direct rules registration was found; implementation route remains unassessed.")) if norm_text(c.get("text", "")) else ("AUTO", "No rules text in pinned catalog; metadata-only behavior candidate.")
        elif "CustomTask" in block.get("task_types", []):
            route, reason = "CUSTOM", "Source registration contains CustomTask; retain native implementation unless a measured common contract is proven."
        elif block.get("has_trigger") or block.get("has_aura") or len(block.get("task_types", [])) > 1:
            route, reason = "COMPOSABLE", "Registered source uses existing task/trigger/aura composition; classify route only, not correctness."
        else:
            route, reason = "AUTO", "Registered source appears metadata-only or uses a single task; validate exact contract before declarative inclusion."
        if composition:
            route, reason = "COMPOSABLE", "Generated effect composition is registered; rule status is limited to its scoped scenario evidence."
        sample.append({
            "card_id": c["card_id"], "name": c["name"], "card_class": meta.get("cardClass"), "type": meta.get("type"),
            "set": meta.get("set"), "text": c.get("text", ""), "mechanics": c.get("mechanics", []),
            "decks": c.get("decks", []), "metadata_present": bool(meta), "rules_registered": bool(rules_registered),
            "registration_status": "DIRECT" if direct_registered else ("GENERATED_COMPOSITION" if composition else ("GENERATED_ALIAS" if alias_base else "MISSING_RULES")),
            "equivalent_base_rules_id": alias_base,
            "route": route, "route_confidence": "source_heuristic_needs_manual_review", "route_reason": reason,
            "verification_status": ("VERIFIED_SCOPED" if c["card_id"] in VERIFIED_SCOPES else ("IMPLEMENTED_UNVERIFIED" if rules_registered and norm_text(c.get("text", "")) else ("UNSUPPORTED" if norm_text(c.get("text", "")) else "METADATA_ONLY_CANDIDATE"))),
            "verification_evidence": VERIFIED_SCOPES.get(c["card_id"]),
            "generated_effect_ir": composition,
            "dependency_status": "UNRESOLVED", "bridge_action_status": "NOT_AUDITED",
            "source_evidence": block,
        })
    for c in extension:
        route, reason = EXTENSION_ROUTES.get(c["id"], ("UNKNOWN", "No manual route assessment is available."))
        alias = alias_by_id.get(c["id"])
        base_id = alias["base_card_id"] if alias and alias["candidate_for_alias"] else None
        block = blocks.get(c["id"], blocks.get(generated_aliases.get(c["id"], base_id), {}) if (generated_aliases.get(c["id"]) or base_id) else {})
        generated_alias = c["id"] in generated_aliases
        composition = generated_compositions.get(c["id"])
        registered = c["id"] in blocks or generated_alias or composition is not None
        if registered:
            route = "COMPOSABLE" if composition else ("AUTO" if not block.get("task_types") else ("CUSTOM" if "CustomTask" in block.get("task_types", []) else "COMPOSABLE"))
            reason = ("Generated effect composition is registered; only its scoped scenario evidence is verified." if composition else
                      ("Generated Core alias is registered; confirm runtime rules and dependencies before admission." if generated_alias else "Direct Core-ID CardDef exists; confirm runtime rules and dependencies before admission."))
        elif alias and alias["candidate_for_alias"] and c["id"] not in EXTENSION_ROUTES:
            route = "CUSTOM" if "CustomTask" in block.get("task_types", []) else ("COMPOSABLE" if block.get("task_types") else "AUTO")
            reason = f"Exact Core copy metadata and equal rules text point to legacy `{base_id}` CardDef; alias wiring is absent and must be tested."
        sample.append({
            "card_id": c["id"], "name": c.get("name"), "card_class": c.get("cardClass"), "type": c.get("type"),
            "set": c.get("set"), "text": c.get("text", ""), "mechanics": c.get("mechanics", []),
            "decks": [], "metadata_present": True, "rules_registered": registered,
            "equivalent_base_rules_id": base_id,
            "registration_status": "DIRECT" if c["id"] in blocks else ("GENERATED_COMPOSITION" if composition else ("GENERATED_ALIAS" if generated_alias else ("MISSING_CORE_ALIAS" if base_id else "MISSING_RULES"))),
            "sampling_stratum": c["sampling_stratum"], "route": route,
            "route_confidence": "manual_route_hypothesis_needs_source_review", "route_reason": reason,
            "verification_status": "VERIFIED_SCOPED" if c["id"] in VERIFIED_SCOPES else ("IMPLEMENTED_UNVERIFIED" if registered or base_id else "UNSUPPORTED"),
            "verification_evidence": VERIFIED_SCOPES.get(c["id"]), "generated_effect_ir": composition,
            "dependency_status": "UNRESOLVED", "bridge_action_status": "NOT_AUDITED",
            "source_evidence": block,
        })
    route_counts = Counter(x["route"] for x in sample)
    source_roots = [
        "data/cards/standard_current_enUS.json", "data/cards/standard_sets.json", POOL_PATH, COVERAGE_PATH,
        CORE_ALIAS_MANIFEST, "integrations/rosettastone/card_rules/core_aliases.v1.json", "scripts/generate_core_card_aliases.py",
        "integrations/rosettastone/card_rules/effect_composition.generated.json", "integrations/rosettastone/card_rules/effect_composition.v1.json", "scripts/generate_effect_composition.py",
        "vendor/RosettaStone/Resources/cards.standard_current.json", "vendor/RosettaStone/Resources/cards.json",
        "vendor/RosettaStone/Includes/Rosetta/PlayMode/Cards/CardDef.hpp", "vendor/RosettaStone/Includes/Rosetta/PlayMode/Cards/CardProperty.hpp",
        "vendor/RosettaStone/Includes/Rosetta/PlayMode/Enchants/Power.hpp",
    ]
    fingerprints = {}
    for rel in source_roots:
        p = ROOT / rel
        if p.exists():
            fingerprints[rel] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    rules_files = set((VENDOR / "Sources/Rosetta/PlayMode/CardSets").glob("*CardsGen.cpp"))
    rules_files.update((VENDOR / "Includes/Rosetta/PlayMode/Tasks/SimpleTasks").glob("*.hpp"))
    rules_files.update((VENDOR / "Sources/Rosetta/PlayMode/Tasks/SimpleTasks").glob("*.cpp"))
    rules_files.update([VENDOR / "Sources/Rosetta/PlayMode/CardSets/ManaMindCoreAliasCardsGen.cpp",
                        VENDOR / "Sources/Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.cpp",
                        VENDOR / "Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp",
                        VENDOR / "Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp"])
    for rel in ["Includes/Rosetta/PlayMode/Cards/CardDef.hpp", "Includes/Rosetta/PlayMode/Cards/CardProperty.hpp",
                "Includes/Rosetta/PlayMode/Enchants/Power.hpp", "Includes/Rosetta/PlayMode/Loaders/TargetingPredicates.hpp",
                "Includes/Rosetta/Common/Enums/CardEnums.hpp", "Resources/GameTag.def", "Resources/GameTagCustom.def"]:
        p = VENDOR / rel
        if p.exists(): rules_files.add(p)
    rules_fingerprints = {p.relative_to(ROOT).as_posix(): {"sha256": sha256(p), "bytes": p.stat().st_size}
                          for p in sorted(rules_files)}
    task_dir = VENDOR / "Includes/Rosetta/PlayMode/Tasks/SimpleTasks"
    tasks = []
    for header in sorted(task_dir.glob("*.hpp")):
        stem = header.stem
        cpp = VENDOR / "Sources/Rosetta/PlayMode/Tasks/SimpleTasks" / f"{stem}.cpp"
        test_hits = [p.relative_to(ROOT).as_posix() for p in (VENDOR / "Tests/UnitTests/PlayMode").rglob(f"*{stem.replace('Task','')}*Tests.cpp")]
        low = stem.lower()
        if any(k in low for k in ("damage", "heal", "armor", "freeze", "silence")): category = "damage_healing_status"
        elif any(k in low for k in ("draw", "deck", "hand", "discard", "return", "move")): category = "card_zone_movement"
        elif any(k in low for k in ("summon", "destroy", "deathrattle", "transform", "control")): category = "summon_destroy_transform"
        elif any(k in low for k in ("discover", "random", "card", "choice", "quest", "stack")): category = "generation_choice_quest"
        elif any(k in low for k in ("enchant", "aura", "tag", "mana", "weapon", "attack")): category = "stats_resources_and_continuous_effects"
        else: category = "other_or_composition"
        tasks.append({"name": stem, "category_guess": category, "header": header.relative_to(ROOT).as_posix(), "implementation": cpp.relative_to(ROOT).as_posix() if cpp.exists() else None,
                      "test_file_candidates": test_hits[:10], "inventory_status": "file_presence_only", "semantics_reviewed": False})
    deck_summary = []
    for d in pool["decks"]:
        cov = next((x for x in coverage["decks"] if x["name"] == d["name"]), {})
        deck_ids = set(d.get("cards", []))
        deck_cards = [x for x in sample if x["card_id"] in deck_ids]
        unsupported = sorted(x["card_id"] for x in deck_cards if x["verification_status"] == "UNSUPPORTED")
        deck_summary.append({"name": d["name"], "player_class": d["player_class"], "published": d.get("published"),
                             "card_count": cov.get("card_count"), "unique_card_count": cov.get("unique_card_count"),
                             "registered_or_textless": sum(x["verification_status"] != "UNSUPPORTED" for x in deck_cards),
                             "unsupported_ids": unsupported,
                             "strict_gates": {"inventory_complete": True, "scenario_checked": False, "dependency_checked": False,
                                "match_smoke_passed_historically": d["name"] in {"Mother Drake Warlock", "Combo Drake Warlock"}, "training_eligible": False}})
    selected_cards = sample[:74]
    registered_selected_count = sum(x["verification_status"] != "UNSUPPORTED" for x in selected_cards)
    missing_selected_count = sum(x["verification_status"] == "UNSUPPORTED" and bool(norm_text(x.get("text", ""))) for x in selected_cards)
    # Use explicit 10 missing records from the pinned audit rather than assuming its deck summaries carry IDs.
    missing = [x for x in sample[:74] if not x["rules_registered"] and x["text"].strip()]
    # Initial static dependency graph: explicit CardDef string references only. Dynamic pools stay open/unknown.
    dep_edges = []
    for card in sample:
        if card.get("equivalent_base_rules_id"):
            dep_edges.append({"from": card["card_id"], "to": card["equivalent_base_rules_id"], "kind": "core_copy_of_legacy_rules", "verified": False})
        for dep in card.get("source_evidence", {}).get("referenced_card_ids", []):
            dep_edges.append({"from": card["card_id"], "to": dep, "kind": "source_card_id_reference", "verified": False})
    graph = {"method": "literal card ID strings inside nearest CardDef source block; excludes dynamic pool resolution", "edges": dep_edges,
             "dynamic_dependencies": [{"card_id": x["card_id"], "text": x["text"], "status": "UNKNOWN_POOL"} for x in sample if re.search(r"discover|random|from your deck|randomly|random enemy", norm_text(x["text"]))]}
    resource_cards = {c.get("id"): c for c in read_json(VENDOR / "Resources/cards.json") if c.get("id")}
    for edge in dep_edges:
        dep = resource_cards.get(edge["to"], catalog.get(edge["to"], {}))
        edge.update({"destination_name": dep.get("name"), "destination_type": dep.get("type"),
                     "destination_collectible": dep.get("collectible"),
                     "dependency_kind_guess": "enchantment" if dep.get("type") == "ENCHANTMENT" else ("noncollectible_generated_card" if dep and not dep.get("collectible") else "card_reference")})
    report = {
        "schema_version": 1, "audit_date": "2026-09-29", "as_of": STAMP,
        "inputs": {"catalog": CATALOG_PATH, "catalog_valid_as_of": catalog_doc.get("valid_as_of"), "deck_pool": POOL_PATH,
                   "deck_pool_catalog_valid_as_of": pool.get("catalog_valid_as_of"), "source_fingerprints": fingerprints,
                   "rosettastone_rules_file_count": len(rules_fingerprints), "rosettastone_rules_fingerprints": rules_fingerprints,
                   "rosettastone_git": git_fingerprint()},
        "baseline": {"selected_deck_count": len(pool["decks"]), "selected_unique_card_count": len(target_ids),
                     "rules_registered_or_textless": registered_selected_count,
                     "missing_text_rules_registration": missing_selected_count,
                     "stratified_extension_count": len(extension), "audited_card_count": len(sample),
                     "route_counts": dict(sorted(route_counts.items())), "deck_summary": deck_summary,
                     "core_alias_metadata_pairs": len(alias_pairs), "core_alias_candidates": alias_candidate_count,
                     "core_aliases_exact_text_missing_direct_definition": alias_candidate_count,
                     "generated_core_alias_count": len(generated_aliases),
                     "generated_effect_composition_count": len(generated_compositions),
                     "remaining_core_alias_candidates": remaining_alias_candidates},
        "route_definitions": ROUTE_GUIDANCE, "cards": sample, "dependency_graph": graph,
        "core_alias_audit": {"method": "CORE_ ID strips to a legacy ID with a CardDef; countAsCopyOfDbfId equals base dbfId; normalized current/base rules text equal",
            "pairs": alias_pairs, "eligible_missing_definition_count": alias_candidate_count,
            "proposed_first_package": ["CORE_BAR_801", "CORE_SW_108", "CORE_BT_072", "CORE_BAR_310", "CORE_AV_337", "CORE_BAR_541", "CORE_KAR_062", "CORE_BT_156"],
            "limits": ["Text equality does not prove all task-level behavior equivalent.", "Base implementations can contain ID assumptions or dynamic pools.", "Copying CardDef shares task pointers; lifetime and initialization order need tests.", "Keyword and numeric metadata continue to come from the current Core overlay."]},
        "capability_inventory": {"simple_task_header_count": len(tasks), "tasks": tasks,
            "surface_file_counts": {name: (sum(1 for _ in (VENDOR / path).rglob("*.hpp")) if (VENDOR / path).is_dir() else int((VENDOR / path).is_file())) for name, path in {
                "triggers": "Includes/Rosetta/PlayMode/Triggers", "auras": "Includes/Rosetta/PlayMode/Auras",
                "conditions": "Includes/Rosetta/PlayMode/Conditions", "targeting_predicates": "Includes/Rosetta/PlayMode/Loaders/TargetingPredicates.hpp",
                "play_requirements": "Includes/Rosetta/Common/Enums/CardEnums.hpp"}.items()},
            "contract_reviews": [
                {"capability": "DamageTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/DamageTask.hpp", "vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/DamageTask.cpp"], "contract": "Applies fixed or ranged damage to entities selected by EntityType; Spell Damage flag is explicit and passed to character damage handling.", "limits": "Target legality is separate; armor, immunity, lifesteal and death processing depend on downstream Generic/Character paths."},
                {"capability": "HealFullTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/HealFullTask.cpp", "vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/HealFullTask.hpp"], "contract": "Calls Character::TakeFullHeal on selected entities.", "limits": "Not interchangeable with an explicit HealTask amount without checking heal modifiers and source attribution; CATA_302 currently uses TakeHeal(damage)."},
                {"capability": "DrawTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/DrawTask.cpp", "vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/DrawTask.hpp"], "contract": "Repeats normal draw action for a requested amount; can alternatively push cards onto task stack.", "limits": "Fatigue, overdraw, and draw triggers are inherited from normal draw action; stack mode is not ordinary draw."},
                {"capability": "SummonTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/SummonTask.cpp", "vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/SummonTask.hpp"], "contract": "Summons a fixed card or stack entity with a requested side, position behavior, and amount.", "limits": "Board capacity, minion-plus-Location slots, ownership, source position, and partial summon failure affect results."},
                {"capability": "DestroyTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/DestroyTask.cpp", "vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/DestroyTask.hpp"], "contract": "Marks selected playables destroyed; optional flag explicitly processes death/aura resolution.", "limits": "Death ordering and simultaneous destruction require scenario coverage; DestroyAllTask has a different selection contract."},
                {"capability": "DiscoverTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/DiscoverTask.hpp", "vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/DiscoverTask.cpp"], "contract": "Builds choices from explicit IDs, a DiscoverType, or type/class/race/rarity predicates, then suspends task flow for choice resolution.", "limits": "Exact candidate population and post-choice continuation matter; selecting a card does not implement that card's effect."},
                {"capability": "RandomMinionTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/RandomMinionTask.hpp", "vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/RandomMinionTask.cpp"], "contract": "Filters the current format's standard or wild card pool by GameTag values and selects random candidates.", "limits": "The pool is format-wide and may include unsupported effects; never silently narrow it for strict Standard results."},
                {"capability": "AddEnchantmentTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/AddEnchantmentTask.hpp", "vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/AddEnchantmentTask.cpp"], "contract": "Looks up a named enchantment definition and applies it to selected entities; can consume task-stack parameters/entity IDs.", "limits": "The enchantment definition and expiry/removal behavior are separate dependencies; stack-driven parameters need explicit declarations."},
                {"capability": "QuestProgressTask", "status": "source_contract_reviewed", "evidence": ["vendor/RosettaStone/Includes/Rosetta/PlayMode/Tasks/SimpleTasks/QuestProgressTask.hpp", "vendor/RosettaStone/Sources/Rosetta/PlayMode/Tasks/SimpleTasks/QuestProgressTask.cpp"], "contract": "Advances configured quest progress and can resolve reward tasks or move to a next quest.", "limits": "ProgressType enum is finite; school-specific consecutive quest conditions are not implied by generic quest progress."},
            ],
            "caveat": "Header/implementation/test file presence is inventory evidence only. The listed source reviews describe contracts, not comprehensive behavioral verification."},
        "known_limitations": ["Five fixed published lists are a selected target pool, not a current meta-frequency sample.",
            "The 26 extension cards are a deterministic stratified sample selected by text heuristics; strata do not describe implementation complexity.",
            "Routes are triage hypotheses. Rules correctness, dependency closure, bridge actions, and match eligibility remain separate gates.",
            "Source regex captures literal ID strings and nearby task names; it does not resolve generated entities, runtime pools, or all C++ control flow.",
            "Dynamic Discover/random pools are explicitly UNKNOWN until predicates and format membership are resolved."],
    }
    return report, tasks, extension


def write_outputs(report, tasks, extension):
    report_path = ROOT / f"reports/card_support_analysis_{STAMP}.json"
    sample_path = ROOT / f"data/samples/card_support_analysis_sample_{STAMP}.json"
    capability_path = ROOT / "integrations/rosettastone/card_rules/capabilities.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    sample_content = json.dumps({"schema_version": 1, "source_report": report_path.relative_to(ROOT).as_posix(),
        "selection": {"selected_deck_cards": 74, "stratified_extension": len(extension), "audited_total": 74 + len(extension)},
        "cards": report["cards"]}, ensure_ascii=False, indent=2) + "\n"
    write_if_changed(sample_path, sample_content)
    write_if_changed(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    capability = {"schema_version": 1, "generated_from_report": report_path.relative_to(ROOT).as_posix(),
        "status_vocabulary": {"UNSUPPORTED": "No registered rules for non-empty text.", "PARTIAL": "Some behavior known, but material rule paths/dependencies remain unsupported.",
          "IMPLEMENTED_UNVERIFIED": "Rules source is registered, but no scoped scenario evidence was assessed by this inventory.",
          "VERIFIED_SCOPED": "Only permitted with an explicit tested scope and evidence."},
        "route_vocabulary": ROUTE_GUIDANCE, "simple_tasks": tasks,
        "source_contract_reviews": report["capability_inventory"]["contract_reviews"],
        "other_surfaces_inventory": [
          {"surface": "Triggers", "path": "vendor/RosettaStone/Includes/Rosetta/PlayMode/Triggers", "header_count": report["capability_inventory"]["surface_file_counts"]["triggers"], "status": "file_inventory_only"},
          {"surface": "Auras", "path": "vendor/RosettaStone/Includes/Rosetta/PlayMode/Auras", "header_count": report["capability_inventory"]["surface_file_counts"]["auras"], "status": "file_inventory_only"},
          {"surface": "Conditions", "path": "vendor/RosettaStone/Includes/Rosetta/PlayMode/Conditions", "header_count": report["capability_inventory"]["surface_file_counts"]["conditions"], "status": "file_inventory_only"},
          {"surface": "TargetingPredicates", "path": "vendor/RosettaStone/Includes/Rosetta/PlayMode/Loaders/TargetingPredicates.hpp", "header_count": 1, "status": "source_path_inventory_only"},
          {"surface": "PlayReq enum", "path": "vendor/RosettaStone/Includes/Rosetta/Common/Enums/CardEnums.hpp", "header_count": 1, "status": "source_path_inventory_only"},
          {"surface": "CardProperty", "path": "vendor/RosettaStone/Includes/Rosetta/PlayMode/Cards/CardProperty.hpp", "fields": ["playReqs", "chooseCardIDs", "entourages", "appendages", "corruptCardID", "infusedCardID", "questProgressTotal", "heroPowerDbfID", "numMinionsToInfuse"], "status": "source_reviewed"}],
        "notes": ["Task entries are a file inventory, not verified capabilities.", "Tests are listed by candidate filename only.", "Do not admit a card or deck based on this registry alone."]}
    capability_path.parent.mkdir(parents=True, exist_ok=True)
    write_if_changed(capability_path, json.dumps(capability, ensure_ascii=False, indent=2) + "\n")
    counts = report["baseline"]["route_counts"]
    lines = ["# Card support audit — 2026-09-29", "", "## Scope", "",
      "This is a reproducible triage inventory for five saved Standard lists plus a deterministic stratified extension sample. It does not establish metagame representativeness, rules correctness, or deck training eligibility.", "",
      f"Catalog snapshot: `{report['inputs']['catalog']}` (valid as of {report['inputs']['catalog_valid_as_of']}); saved list pool: `{report['inputs']['deck_pool']}`. RosettaStone revision status: `{report['inputs']['rosettastone_git']['status']}`.", "",
      "## Counts", "", "| Measure | Count |", "|---|---:|",
      f"| Selected lists | {report['baseline']['selected_deck_count']} |", f"| Unique selected-list cards | {report['baseline']['selected_unique_card_count']} |",
      f"| Selected-list cards registered or textless | {report['baseline']['rules_registered_or_textless']} |", f"| Selected-list cards missing nonempty-text registration | {report['baseline']['missing_text_rules_registration']} |",
      f"| Extension sample | {report['baseline']['stratified_extension_count']} |", f"| Total triaged cards | {report['baseline']['audited_card_count']} |", "",
      "Route counts (triage hypotheses): " + ", ".join(f"`{k}={v}`" for k,v in sorted(counts.items())) + ".", "",
      f"Legacy Core alias scan: {report['baseline']['core_alias_metadata_pairs']} metadata-linked base definitions; {report['baseline']['core_alias_candidates']} have equal normalized rules text and lack a direct Core CardDef. Generated aliases are accounted for separately: {report['baseline']['generated_core_alias_count']} registered by the current manifest, {report['baseline']['remaining_core_alias_candidates']} remaining candidates. Five linked entries have different text and are excluded.", "",
      "AUTO means a possible constrained declaration route, not proven correctness. COMPOSABLE means current RosettaStone constructs appear usable. MISSING_PRIMITIVE names a shared contract or mechanic that needs work. CUSTOM indicates named native handling is likely simpler. UNKNOWN preserves unresolved rules questions.", "",
      "## Selected decks", "", "| Deck | Class | Unique | Registered/textless | Missing IDs | Strict training gate |", "|---|---|---:|---:|---|---|"]
    for d in report["baseline"]["deck_summary"]:
        absent = ", ".join(f"`{x}`" for x in d["unsupported_ids"]) or "—"
        lines.append(f"| {d['name']} | {d['player_class']} | {d.get('unique_card_count','?')} | {d['registered_or_textless']} | {absent} | not eligible |")
    lines += ["", "## Missing registrations in selected lists", "", "| ID | Card | Route | Reason |", "|---|---|---|---|"]
    for x in sorted((x for x in report["cards"][:74] if not x["rules_registered"] and x["text"].strip()), key=lambda x:x["card_id"]):
      lines.append(f"| `{x['card_id']}` | {x['name']} | {x['route']} | {x['route_reason']} |")
    lines += ["", "## Extension sample", "", "The sampling strata are text heuristics only. Each route below is a manual engineering hypothesis to verify against source and rulings.", "", "| ID | Name | Stratum | Route | Next question |", "|---|---|---|---|---|"]
    for x in report["cards"][74:]:
        lines.append(f"| `{x['card_id']}` | {x['name']} | {x.get('sampling_stratum')} | {x['route']} | {x['route_reason']} |")
    lines += ["", "## Dependency graph and capability inventory", "", f"The initial source scan found {len(report['dependency_graph']['edges'])} literal CardDef references among audited registrations. They are unverified edges. It also lists {len(report['dependency_graph']['dynamic_dependencies'])} dynamic pool candidates as `UNKNOWN_POOL`; this is not dependency closure.", "",
      "Fixed references include generated tokens, enchantments, and choice objects. Their destination type and collectible status are in the JSON graph; each edge remains unverified until both definition and runtime path are checked. Dynamic Discover/random filters remain unresolved unless an exact predicate is recorded.", "",
      f"The inventory enumerates {report['capability_inventory']['simple_task_header_count']} SimpleTasks headers. Source contracts were inspected for {len(report['capability_inventory']['contract_reviews'])} high-use capabilities; summarized contracts and limitations are in `integrations/rosettastone/card_rules/capabilities.json`. Header, implementation, and test-file presence are not semantic contracts.", "",
      "The five deck inventories are complete against the pinned catalog. Scenario and dependency gates remain false. Alias registration changes the missing-ID count but does not complete those gates. The Warlock lists have historical match-smoke evidence, but do not pass the stricter gates; all five lists remain ineligible for training from this audit.", "",
      "## First implementation package", "", "The audit found a high-value reuse path before introducing operation-by-operation CardDefs: current Core IDs can point to a legacy card ID in metadata while RosettaStone only registers the legacy ID. A strict alias candidate must have a registered stripped-ID base, matching `countAsCopyOfDbfId`, and equal normalized rules text. Forty current Standard Core IDs meet this test and lack a direct Core definition. Five more metadata-linked copies have different text and are excluded.", "",
      "Start with eight alias declarations to cover token summon, damage, add-card, freeze, Deathrattle, healing, Discover, and Dormant: `CORE_BAR_801 → BAR_801`, `CORE_SW_108 → SW_108`, `CORE_BT_072 → BT_072`, `CORE_BAR_310 → BAR_310`, `CORE_AV_337 → AV_337`, `CORE_BAR_541 → BAR_541`, `CORE_KAR_062 → KAR_062`, `CORE_BT_156 → BT_156`. Generate aliases only after validating each pair and checking duplicate IDs, task references, and dependencies. Keep the other 32 candidates queued until correctness and measured package cost support expansion.", "",
      f"The current generated alias manifest contains {report['baseline']['generated_core_alias_count']} aliases from three additions (8 + 7 + 5); {report['baseline']['remaining_core_alias_candidates']} candidates remain. A separate allowlisted effect-composition IR now generates four migrated cards (`CORE_CS2_004`, `END_007`, `CAP_801`, `CORE_SW_066`) using ordered existing Tasks and explicit play requirements. `CATA_302` stays manual because its current CustomTask heals only the damage taken and needs a dedicated semantic contract. Scoped scenarios are recorded per card in the JSON report; no selected-deck training gate has changed.", "",
      "## Limits and provenance", ""]
    lines.extend(f"- {lim}" for lim in report["known_limitations"])
    lines += ["", "Raw card-by-card fields, SHA-256 fingerprints, source evidence, and the deterministic sample are in `reports/card_support_analysis_20260929.json` and `data/samples/card_support_analysis_sample_20260929.json`.", ""]
    markdown = "\n".join(lines)
    try:
        (ROOT / "docs/CARD_SUPPORT_ANALYSIS_20260929.md").write_text(markdown, encoding="utf-8")
    except PermissionError:
        # Some managed workspaces allow patch-based edits but block process writes
        # to docs/. Keep a generated copy available rather than failing after the
        # JSON artifacts were already updated.
        write_if_changed(ROOT / f"reports/card_support_analysis_{STAMP}.md", markdown)


if __name__ == "__main__":
    report, tasks, extension = build()
    write_outputs(report, tasks, extension)
    print(json.dumps({"cards": report["baseline"]["audited_card_count"], "routes": report["baseline"]["route_counts"],
                      "tasks": len(tasks), "extension": [x["id"] for x in extension]}, ensure_ascii=False, indent=2))
