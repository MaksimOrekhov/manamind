"""Validate a pinned Core alias package and emit ordinary RosettaStone C++."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_card_support_analysis import collect_card_blocks, norm_text, read_json, sha256, write_if_changed  # noqa: E402

DECLARATION = ROOT / "integrations/rosettastone/card_rules/core_aliases.v1.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
RESOURCE_CARDS = ROOT / "vendor/RosettaStone/Resources/cards.json"
HEADER = ROOT / "vendor/RosettaStone/Includes/Rosetta/PlayMode/CardSets/ManaMindCoreAliasCardsGen.hpp"
SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindCoreAliasCardsGen.cpp"
MANIFEST = ROOT / "integrations/rosettastone/card_rules/core_aliases.generated.json"

PACKAGE_ALLOWLIST = {
    "CORE_BAR_801": "BAR_801", "CORE_SW_108": "SW_108", "CORE_BT_072": "BT_072",
    "CORE_BAR_310": "BAR_310", "CORE_AV_337": "AV_337", "CORE_BAR_541": "BAR_541",
    "CORE_KAR_062": "KAR_062", "CORE_BT_156": "BT_156",
    "CORE_SW_068": "SW_068", "CORE_SW_088": "SW_088", "CORE_EX1_131": "EX1_131",
    "CORE_EX1_278": "EX1_278", "CORE_DRG_107": "DRG_107", "CORE_WC_701": "WC_701",
    "CORE_BT_701": "BT_701",
    "CORE_BAR_313": "BAR_313", "CORE_EX1_058": "EX1_058", "CORE_ONY_018": "ONY_018",
    "CORE_SW_439": "SW_439", "CORE_TSC_650": "TSC_650",
}
ROOT_FIELDS = {"schema_version", "catalog_path", "catalog_sha256", "cards"}
CARD_FIELDS = {"card_id", "base_card_id"}


def canonical_rules(text: str) -> str:
    return norm_text(text)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate():
    declaration = read_json(DECLARATION)
    require(set(declaration) == ROOT_FIELDS, f"unexpected declaration fields: {sorted(set(declaration) ^ ROOT_FIELDS)}")
    require(declaration["schema_version"] == 1, "unsupported schema_version")
    require(declaration["catalog_path"] == "data/cards/standard_current_enUS.json", "catalog path is not allowlisted")
    actual_catalog_hash = sha256(CATALOG)
    require(declaration["catalog_sha256"] == actual_catalog_hash, "catalog fingerprint changed; re-audit declarations before regeneration")
    require(isinstance(declaration["cards"], list) and declaration["cards"], "cards must be a non-empty list")
    card_map = {card["id"]: card for card in read_json(CATALOG)["cards"] if card.get("id")}
    resource_map = {card["id"]: card for card in read_json(RESOURCE_CARDS) if card.get("id")}
    blocks = collect_card_blocks()
    seen = set()
    validated = []
    for row in declaration["cards"]:
        require(isinstance(row, dict) and set(row) == CARD_FIELDS, "each alias must contain only card_id and base_card_id")
        card_id, base_id = row["card_id"], row["base_card_id"]
        require(PACKAGE_ALLOWLIST.get(card_id) == base_id, f"alias is not allowlisted: {card_id} -> {base_id}")
        require(card_id not in seen, f"duplicate declaration: {card_id}")
        seen.add(card_id)
        current, base = card_map.get(card_id), resource_map.get(base_id)
        require(current is not None and current.get("collectible") is True and current.get("set") == "CORE", f"not a collectible Core card: {card_id}")
        require(base is not None, f"base metadata missing: {base_id}")
        require(base_id in blocks, f"base CardDef source is not registered: {base_id}")
        require(current.get("countAsCopyOfDbfId") == base.get("dbfId"), f"Core copy DBF link mismatch: {card_id}")
        current_text, base_text = canonical_rules(current.get("text", "")), canonical_rules(base.get("text", ""))
        require(current_text and current_text == base_text, f"rules text mismatch: {card_id} and {base_id}")
        require(card_id not in blocks, f"direct Core CardDef already exists: {card_id}")
        source = blocks[base_id]
        dependencies = []
        for dependency_id in source["referenced_card_ids"]:
            metadata = resource_map.get(dependency_id) or card_map.get(dependency_id)
            require(metadata is not None, f"fixed dependency metadata missing: {card_id} -> {dependency_id}")
            if metadata.get("text", "").strip():
                require(dependency_id in blocks, f"fixed dependency rules source missing: {card_id} -> {dependency_id}")
            dependencies.append({"card_id": dependency_id, "name": metadata.get("name"), "type": metadata.get("type"),
                                 "collectible": metadata.get("collectible"), "direct_rules_source": dependency_id in blocks})
        tasks = source["task_types"]
        validated.append({"card_id": card_id, "base_card_id": base_id,
            "copy_of_dbf_id": current.get("countAsCopyOfDbfId"), "base_dbf_id": base.get("dbfId"),
            "name": current.get("name"), "rules_text_sha256": hashlib.sha256(current_text.encode("utf-8")).hexdigest(),
            "base_source_file": source["source_file"], "task_types": tasks, "dependencies": dependencies,
            "dynamic_pool_status": "UNKNOWN_POOL" if any(t in tasks for t in ("DiscoverTask", "RandomMinionTask", "RandomCardTask", "RandomSpellTask", "CastRandomSpellTask")) else "NONE_DETECTED",
            "training_eligible": False})
    require(seen == set(PACKAGE_ALLOWLIST), f"package must contain the complete allowlist; missing {sorted(set(PACKAGE_ALLOWLIST) - seen)}")
    return validated, actual_catalog_hash


def generated_cpp(cards: list[dict]) -> str:
    rows = "\n".join(f'        Alias{{ "{x["card_id"]}", "{x["base_card_id"]}" }},' for x in cards)
    return f'''// Generated by scripts/generate_core_card_aliases.py. Do not edit by hand.
#include <Rosetta/PlayMode/CardSets/ManaMindCoreAliasCardsGen.hpp>

#include <array>
#include <stdexcept>
#include <string_view>

namespace RosettaStone::PlayMode
{{
void ManaMindCoreAliasCardsGen::AddAll(std::map<std::string, CardDef>& cards)
{{
    struct Alias {{ std::string_view current; std::string_view base; }};
    static constexpr Alias aliases[] = {{
{rows}
    }};

    for (const auto& alias : aliases)
    {{
        if (cards.contains(std::string(alias.current)))
        {{
            throw std::logic_error("duplicate generated Core CardDef: " + std::string(alias.current));
        }}

        const auto base = cards.find(std::string(alias.base));
        if (base == cards.end())
        {{
            throw std::logic_error("missing base CardDef for Core alias: " + std::string(alias.base));
        }}

        const bool inserted = cards.emplace(std::string(alias.current), base->second).second;
        if (!inserted)
        {{
            throw std::logic_error("failed to register generated Core CardDef: " + std::string(alias.current));
        }}
    }}
}}
}}  // namespace RosettaStone::PlayMode
'''


def generated_hpp() -> str:
    return '''// Generated by scripts/generate_core_card_aliases.py. Do not edit by hand.
#ifndef ROSETTASTONE_MANAMIND_CORE_ALIAS_CARDS_GEN_HPP
#define ROSETTASTONE_MANAMIND_CORE_ALIAS_CARDS_GEN_HPP

#include <Rosetta/PlayMode/Cards/CardDef.hpp>

#include <map>
#include <string>

namespace RosettaStone::PlayMode
{
class ManaMindCoreAliasCardsGen
{
 public:
    static void AddAll(std::map<std::string, CardDef>& cards);
};
}  // namespace RosettaStone::PlayMode

#endif  // ROSETTASTONE_MANAMIND_CORE_ALIAS_CARDS_GEN_HPP
'''


def main():
    cards, catalog_hash = validate()
    manifest = {"schema_version": 1, "declaration": DECLARATION.relative_to(ROOT).as_posix(),
        "declaration_sha256": sha256(DECLARATION), "catalog_sha256": catalog_hash,
        "generated_header": HEADER.relative_to(ROOT).as_posix(), "generated_source": SOURCE.relative_to(ROOT).as_posix(),
        "cards": cards, "strict_training_ready": False,
        "training_blockers": ["Dynamic pools remain unresolved for Discover cards.", "Alias behaviors still need focused scenarios and bridge action checks."]}
    # Validate all inputs before changing any generated output.
    write_if_changed(HEADER, generated_hpp())
    write_if_changed(SOURCE, generated_cpp(cards))
    write_if_changed(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Generated {len(cards)} aliases; {sum(x['dynamic_pool_status'] != 'NONE_DETECTED' for x in cards)} have unresolved dynamic pools.")


if __name__ == "__main__":
    main()
