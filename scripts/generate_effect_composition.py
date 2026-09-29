"""Validate an allowlisted effect-composition IR and emit ordinary C++."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_card_support_analysis import collect_card_blocks, norm_text, read_json, sha256, write_if_changed  # noqa: E402

DECLARATION = ROOT / "integrations/rosettastone/card_rules/effect_composition.v1.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
RESOURCES = ROOT / "vendor/RosettaStone/Resources/cards.json"
HEADER = ROOT / "vendor/RosettaStone/Includes/Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.hpp"
SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.cpp"
MANIFEST = ROOT / "integrations/rosettastone/card_rules/effect_composition.generated.json"

ALLOWLIST = {"CORE_CS2_004", "END_007", "CAP_801", "CORE_SW_066"}
ROOT_FIELDS = {"schema_version", "catalog_path", "catalog_sha256", "cards"}
CARD_FIELDS = {"card_id", "activation", "play_requirements", "dependencies", "effects"}
REQS = {"REQ_TARGET_TO_PLAY", "REQ_MINION_TARGET"}
TARGETS = {"TARGET": "EntityType::TARGET", "HERO": "EntityType::HERO"}
TAGS = {"REBORN": "GameTag::REBORN"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate():
    declaration = read_json(DECLARATION)
    require(set(declaration) == ROOT_FIELDS, "unexpected top-level IR fields")
    require(declaration["schema_version"] == 1, "unsupported IR schema")
    require(declaration["catalog_path"] == "data/cards/standard_current_enUS.json", "catalog is not allowlisted")
    catalog_hash = sha256(CATALOG)
    require(declaration["catalog_sha256"] == catalog_hash, "catalog fingerprint changed; re-review the package")
    catalog = {x["id"]: x for x in read_json(CATALOG)["cards"] if x.get("id")}
    resources = {x["id"]: x for x in read_json(RESOURCES) if x.get("id")}
    blocks = collect_card_blocks()
    rows = declaration["cards"]
    require(len(rows) == len(ALLOWLIST), "package must contain all and only the allowlisted IDs")
    seen = set()
    validated = []
    for row in rows:
        require(isinstance(row, dict) and set(row) == CARD_FIELDS, "unexpected card IR fields")
        card_id = row["card_id"]
        require(card_id in ALLOWLIST and card_id not in seen, f"card ID is duplicate or not allowlisted: {card_id}")
        seen.add(card_id)
        card = catalog.get(card_id)
        require(card is not None and card.get("text", "").strip(), f"current rules metadata missing: {card_id}")
        require(card_id not in blocks, f"direct manual/generated CardDef still owns {card_id}")
        activation = row["activation"]
        require((activation == "BATTLECRY" and card.get("type") == "MINION" and "battlecry" in card.get("text", "").lower()) or
                (activation == "SPELL_PLAY" and card.get("type") == "SPELL"), f"activation/card-type mismatch: {card_id}")
        reqs = row["play_requirements"]
        require(isinstance(reqs, list) and len(reqs) == len(set(reqs)) and set(reqs) <= REQS, f"invalid play requirements: {card_id}")
        dependencies = row["dependencies"]
        require(isinstance(dependencies, list) and len(dependencies) == len(set(dependencies)), f"invalid dependencies: {card_id}")
        for dep_id in dependencies:
            dep = resources.get(dep_id) or catalog.get(dep_id)
            require(dep is not None, f"dependency metadata missing: {card_id} -> {dep_id}")
            require(dep.get("type") == "ENCHANTMENT", f"only reviewed enchantment dependencies are allowed: {card_id} -> {dep_id}")
        effects = row["effects"]
        require(isinstance(effects, list) and effects, f"effects must be a non-empty list: {card_id}")
        normalized_effects = []
        for effect in effects:
            require(isinstance(effect, dict) and isinstance(effect.get("op"), str), f"invalid effect in {card_id}")
            op = effect["op"]
            if op == "DAMAGE":
                require(set(effect) == {"op", "target", "amount", "spell_damage"}, f"invalid DAMAGE fields in {card_id}")
                require(effect["target"] in TARGETS and isinstance(effect["amount"], int) and 1 <= effect["amount"] <= 30, f"invalid DAMAGE parameters in {card_id}")
                require(isinstance(effect["spell_damage"], bool), f"spell_damage must be explicit in {card_id}")
            elif op == "ENCHANT":
                require(set(effect) == {"op", "target", "id"}, f"invalid ENCHANT fields in {card_id}")
                require(effect["target"] in TARGETS and effect["id"] in dependencies, f"undeclared enchantment reference in {card_id}")
            elif op in {"DRAW", "ARMOR"}:
                require(set(effect) == {"op", "amount"} and isinstance(effect["amount"], int) and 1 <= effect["amount"] <= 10, f"invalid {op} parameters in {card_id}")
            elif op == "SET_TAG":
                require(set(effect) == {"op", "target", "tag", "value"}, f"invalid SET_TAG fields in {card_id}")
                require(effect["target"] == "TARGET" and effect["tag"] in TAGS and effect["value"] in (0, 1), f"unreviewed tag setting in {card_id}")
            elif op == "SILENCE":
                require(set(effect) == {"op", "target"} and effect["target"] == "TARGET", f"invalid SILENCE parameters in {card_id}")
            else:
                raise ValueError(f"unsupported operation {op!r} in {card_id}")
            normalized_effects.append(effect)
        referenced_enchantments = {effect["id"] for effect in normalized_effects if effect["op"] == "ENCHANT"}
        require(referenced_enchantments == set(dependencies), f"dependency list must exactly match declared enchantments: {card_id}")
        validated.append({"card_id": card_id, "name": card.get("name"), "activation": activation,
                          "rules_text_sha256": hashlib.sha256(norm_text(card.get("text", "")).encode()).hexdigest(),
                          "play_requirements": reqs, "dependencies": dependencies, "effects": normalized_effects,
                          "training_eligible": False})
    require(seen == ALLOWLIST, "declaration is missing allowlisted cards")
    return validated, catalog_hash


def task_expression(effect: dict) -> str:
    op = effect["op"]
    if op == "DAMAGE":
        return f'std::make_shared<DamageTask>(EntityType::TARGET, {effect["amount"]}, {str(effect["spell_damage"]).lower()})'
    if op == "ENCHANT":
        return f'std::make_shared<AddEnchantmentTask>("{effect["id"]}", {TARGETS[effect["target"]]})'
    if op == "DRAW":
        return f'std::make_shared<DrawTask>({effect["amount"]})'
    if op == "ARMOR":
        return f'std::make_shared<ArmorTask>({effect["amount"]})'
    if op == "SET_TAG":
        return f'std::make_shared<SetGameTagTask>(EntityType::TARGET, {TAGS[effect["tag"]]}, {effect["value"]})'
    if op == "SILENCE":
        return 'std::make_shared<SilenceTask>(EntityType::TARGET)'
    raise ValueError(op)


def generated_source(cards: list[dict]) -> str:
    blocks = []
    for card in cards:
        lines = [f'    if (cards.contains("{card["card_id"]}"))',
                 f'        throw std::logic_error("duplicate generated CardDef: {card["card_id"]}");',
                 '    {', '        CardDef cardDef;', '        cardDef.ClearData();']
        lines.extend(f'        cardDef.power.AddPowerTask({task_expression(effect)});' for effect in card["effects"])
        if card["play_requirements"]:
            reqs = ", ".join(f'{{ PlayReq::{req}, 0 }}' for req in card["play_requirements"])
            lines.append(f'        cardDef.property.playReqs = PlayReqs{{ {reqs} }};')
        lines.extend([f'        cards.emplace("{card["card_id"]}", std::move(cardDef));', '    }'])
        blocks.append("\n".join(lines))
    return '''// Generated by scripts/generate_effect_composition.py. Do not edit by hand.
#include <Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.hpp>
#include <Rosetta/PlayMode/Cards/CardPowers.hpp>

#include <Rosetta/PlayMode/Tasks/ITask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/AddEnchantmentTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/ArmorTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DamageTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DrawTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/SetGameTagTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/SilenceTask.hpp>

#include <stdexcept>
#include <memory>
#include <utility>

namespace RosettaStone::PlayMode
{
void ManaMindEffectCompositionGen::AddAll(std::map<std::string, CardDef>& cards)
{
using namespace SimpleTasks;

'''+"\n\n".join(blocks)+'''
}
}  // namespace RosettaStone::PlayMode
'''


def main():
    cards, catalog_hash = validate()
    header = '''// Generated by scripts/generate_effect_composition.py. Do not edit by hand.
#ifndef ROSETTASTONE_MANAMIND_EFFECT_COMPOSITION_GEN_HPP
#define ROSETTASTONE_MANAMIND_EFFECT_COMPOSITION_GEN_HPP
#include <Rosetta/PlayMode/Cards/CardDef.hpp>
#include <map>
#include <string>
namespace RosettaStone::PlayMode
{
class ManaMindEffectCompositionGen
{
 public:
    static void AddAll(std::map<std::string, CardDef>& cards);
};
}  // namespace RosettaStone::PlayMode
#endif  // ROSETTASTONE_MANAMIND_EFFECT_COMPOSITION_GEN_HPP
'''
    manifest = {"schema_version": 1, "declaration": DECLARATION.relative_to(ROOT).as_posix(),
                "declaration_sha256": sha256(DECLARATION), "catalog_sha256": catalog_hash,
                "generated_header": HEADER.relative_to(ROOT).as_posix(), "generated_source": SOURCE.relative_to(ROOT).as_posix(),
                "cards": cards, "training_eligible": False,
                "training_blockers": ["This package is a migration pilot, not a deck-complete proof.",
                                      "Generated card scenarios and deck dependency gates remain outstanding."]}
    write_if_changed(HEADER, header)
    write_if_changed(SOURCE, generated_source(cards))
    write_if_changed(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Generated {len(cards)} effect compositions; training remains disabled.")


if __name__ == "__main__":
    main()
