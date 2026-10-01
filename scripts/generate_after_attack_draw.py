"""Validate the bounded after-attack/draw package and emit ordinary C++."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_card_support_analysis import sha256, write_if_changed  # noqa: E402

DECLARATION = ROOT / "integrations/rosettastone/card_rules/after_attack_draw.v1.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
HEADER = ROOT / "vendor/RosettaStone/Includes/Rosetta/PlayMode/CardSets/ManaMindAfterAttackDrawGen.hpp"
SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindAfterAttackDrawGen.cpp"
MANIFEST = ROOT / "integrations/rosettastone/card_rules/after_attack_draw.generated.json"
EXPECTED = {
    "CAP_003": ("<b>Stealth</b> After this attacks, draw a card.", "SELF", [{"op": "DRAW", "amount": 1}]),
    "EDR_253": ("After your hero attacks, draw a card.", "HERO", [{"op": "DRAW", "amount": 1}]),
    "CORE_NX2_028": ("After your hero attacks, gain 4 Armor and draw a card.", "HERO",
                     [{"op": "ARMOR", "amount": 4}, {"op": "DRAW", "amount": 1}]),
    "TLC_478": ("After your hero attacks, deal 1 damage to all minions.", "HERO",
                [{"op": "DAMAGE_ALL_MINIONS", "amount": 1}]),
    "TLC_840": ("<b>Stealth</b> After this attacks, deal 2 damage to the enemy hero.", "SELF",
                [{"op": "DAMAGE_ENEMY_HERO", "amount": 2}]),
}


def normalized(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value or "")
    return " ".join(value.lower().split())


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def validate() -> tuple[list[dict], str]:
    catalog_hash = sha256(CATALOG)
    declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))
    require(set(declaration) == {"schema_version", "catalog_path", "catalog_sha256", "cards"},
            "unknown or missing root fields")
    require(declaration["schema_version"] == 1, "unsupported schema_version")
    require(declaration["catalog_path"] == CATALOG.relative_to(ROOT).as_posix(), "catalog path mismatch")
    require(declaration["catalog_sha256"] in ("", catalog_hash), "catalog fingerprint is stale")
    catalog = {card["id"]: card for card in json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]}
    require(len(declaration["cards"]) == len(EXPECTED), "package card count changed")
    seen: set[str] = set()
    validated = []
    for row in declaration["cards"]:
        require(set(row) == {"card_id", "trigger_source", "effects"}, "unknown or missing card fields")
        card_id = row["card_id"]
        require(card_id in EXPECTED and card_id not in seen, f"unreviewed or duplicate card: {card_id}")
        seen.add(card_id)
        card = catalog.get(card_id)
        require(card is not None and card.get("collectible") is True, f"missing collectible catalog card: {card_id}")
        expected_text, trigger_source, effects = EXPECTED[card_id]
        require(normalized(card.get("text", "")) == normalized(expected_text), f"rules text changed: {card_id}")
        require(row["trigger_source"] == trigger_source, f"actor does not match rules text: {card_id}")
        require(row["effects"] == effects, f"effects do not match reviewed contract: {card_id}")
        for effect in row["effects"]:
            require(set(effect) == {"op", "amount"} and type(effect["amount"]) is int, f"invalid effect: {card_id}")
            require((effect["op"] == "DRAW" and effect["amount"] == 1) or
                    (effect["op"] == "ARMOR" and effect["amount"] == 4 and card_id == "CORE_NX2_028") or
                    (effect["op"] == "DAMAGE_ALL_MINIONS" and effect["amount"] == 1 and card_id == "TLC_478") or
                    (effect["op"] == "DAMAGE_ENEMY_HERO" and effect["amount"] == 2 and card_id == "TLC_840"),
                    f"unreviewed operation: {card_id}")
        validated.append({"card_id": card_id, "name": card["name"], "trigger_source": trigger_source,
                          "effects": effects, "rules_text_sha256": hashlib.sha256(
                              normalized(card["text"]).encode()).hexdigest(), "training_eligible": False})
    require(seen == set(EXPECTED), "declaration does not exactly match the reviewed allowlist")

    # Protect against a second definition in source files or another generated package.
    roots = [(ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets", "*.cpp"),
             (ROOT / "vendor/RosettaStone/Includes/Rosetta/PlayMode/CardSets", "*.hpp")]
    for root, pattern in roots:
        for path in root.rglob(pattern):
            if path.name == "ManaMindAfterAttackDrawGen.cpp":
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            for card_id in EXPECTED:
                require(not re.search(rf'cards\.emplace\("{card_id}"', source),
                        f"existing direct registration found for {card_id} in {path.relative_to(ROOT)}")
    return validated, catalog_hash


def generate(cards: list[dict]) -> tuple[str, str]:
    header = '''// Generated by scripts/generate_after_attack_draw.py. Do not edit by hand.
#ifndef ROSETTASTONE_MANAMIND_AFTER_ATTACK_DRAW_CARDS_GEN_HPP
#define ROSETTASTONE_MANAMIND_AFTER_ATTACK_DRAW_CARDS_GEN_HPP
#include <Rosetta/PlayMode/Cards/CardDef.hpp>
#include <map>
#include <string>
namespace RosettaStone::PlayMode
{
class ManaMindAfterAttackDrawCardsGen
{
 public:
    static void AddAll(std::map<std::string, CardDef>& cards);
};
}  // namespace RosettaStone::PlayMode
#endif  // ROSETTASTONE_MANAMIND_AFTER_ATTACK_DRAW_CARDS_GEN_HPP
'''
    blocks = []
    for card in cards:
        cid = card["card_id"]
        tasks = []
        for effect in card["effects"]:
            if effect["op"] == "DRAW":
                task = f'std::make_shared<DrawTask>({effect["amount"]})'
            elif effect["op"] == "ARMOR":
                task = f'std::make_shared<ArmorTask>({effect["amount"]})'
            elif effect["op"] == "DAMAGE_ALL_MINIONS":
                task = 'std::make_shared<DamageTask>(EntityType::ALL_MINIONS_NOSOURCE, 1, false)'
            else:
                task = 'std::make_shared<DamageTask>(EntityType::ENEMY_HERO, 2, false)'
            tasks.append(task)
        block = [f'    if (cards.contains("{cid}"))',
                 f'        throw std::logic_error("duplicate generated CardDef: {cid}");',
                 '    {', '        CardDef cardDef;', '        cardDef.ClearData();',
                 '        cardDef.power.AddTrigger(std::make_shared<Trigger>(TriggerType::AFTER_ATTACK));',
                 f'        cardDef.power.GetTrigger()->triggerSource = TriggerSource::{card["trigger_source"]};',
                 '        cardDef.power.GetTrigger()->tasks = {']
        block.extend(f'            {task},' for task in tasks)
        block.extend(['        };', f'        cards.emplace("{cid}", std::move(cardDef));', '    }'])
        blocks.append("\n".join(block))
    source = '''// Generated by scripts/generate_after_attack_draw.py. Do not edit by hand.
#include <Rosetta/PlayMode/CardSets/ManaMindAfterAttackDrawGen.hpp>
#include <Rosetta/PlayMode/Cards/CardPowers.hpp>
#include <Rosetta/PlayMode/Triggers/Trigger.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/ArmorTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DrawTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DamageTask.hpp>
#include <memory>
#include <stdexcept>
#include <utility>
namespace RosettaStone::PlayMode
{
void ManaMindAfterAttackDrawCardsGen::AddAll(std::map<std::string, CardDef>& cards)
{
using namespace SimpleTasks;

'''+"\n\n".join(blocks)+'''
}
}  // namespace RosettaStone::PlayMode
'''
    return header, source


def main() -> None:
    cards, catalog_hash = validate()
    header, source = generate(cards)
    write_if_changed(HEADER, header)
    write_if_changed(SOURCE, source)
    declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))
    declaration["catalog_sha256"] = catalog_hash
    write_if_changed(DECLARATION, json.dumps(declaration, ensure_ascii=False, indent=2) + "\n")
    manifest = {"schema_version": 1, "declaration": DECLARATION.relative_to(ROOT).as_posix(),
                "declaration_sha256": sha256(DECLARATION), "catalog_sha256": catalog_hash,
                "generated_header": HEADER.relative_to(ROOT).as_posix(),
                "generated_source": SOURCE.relative_to(ROOT).as_posix(), "cards": cards,
                "training_eligible": False,
                "training_blockers": ["Only scoped trigger/effect behavior is tested; deck dependency and full-profile gates remain open."]}
    write_if_changed(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Validated and generated {len(cards)} cards (catalog {catalog_hash[:12]}).")


if __name__ == "__main__":
    main()
