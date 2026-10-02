"""Strict renderer for current-hand-gated fixed Battlecry effects."""
from __future__ import annotations

import re
import hashlib
import json

from card_rules.minion_set_enchant import fields, require

CARD_ID = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\Z")
PREDICATES = {"MINION_HAS_RACE", "SPELL_HAS_SCHOOL", "SPELL_CURRENT_COST_AT_LEAST"}
EFFECTS = {"REFRESH_MANA", "ADD_SELF_ENCHANT", "SET_SELF_TAG", "DAMAGE_TARGET"}
RACES = {"DRAGON"}
SCHOOLS = {"SHADOW"}
TAGS = {"TAUNT", "DIVINE_SHIELD", "LIFESTEAL"}


def validate(declaration: dict, catalog: dict, resources: dict) -> list[dict]:
    fields(declaration, {"schema_version", "package_id", "contract_id", "contract_version",
                         "implementation_kind", "reviewed_card_ids", "dependencies", "cards"})
    require(declaration["schema_version"] == declaration["contract_version"] == 1 and
            type(declaration["schema_version"]) is int, "unsupported schema version")
    require(declaration["package_id"] == "held_card_gate_fixed_battlecry_v1" and
            declaration["contract_id"] == "held_card_gate_fixed_battlecry", "contract identity mismatch")
    require(declaration["implementation_kind"] == "REUSABLE_CAPABILITY", "wrong implementation kind")
    dependencies = declaration["dependencies"]
    require(dependencies == ["BRM_033e"], "v1 dependency allowlist changed")
    require(resources.get("BRM_033e", {}).get("type") == "ENCHANTMENT", "missing +1/+1 enchantment")
    allowed = declaration["reviewed_card_ids"]
    require(isinstance(allowed, list) and len(allowed) == len(set(allowed)), "invalid reviewed IDs")
    seen = set()
    rows = declaration["cards"]
    require(isinstance(rows, list) and bool(rows), "cards required")
    for row in rows:
        fields(row, {"card_id", "metadata_sha256", "predicate", "effects"}, {"targeting"})
        cid = row["card_id"]
        require(isinstance(cid, str) and CARD_ID.fullmatch(cid) and cid in allowed and cid not in seen,
                "unreviewed or duplicate card")
        seen.add(cid)
        metadata = catalog.get(cid)
        require(metadata is not None and metadata.get("collectible") is True and metadata["type"] == "MINION",
                "expected collectible minion metadata")
        fingerprint = hashlib.sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False,
                                                  separators=(",", ":")).encode()).hexdigest()
        require(fingerprint == row["metadata_sha256"], "stale card metadata fingerprint")
        pred = row["predicate"]
        require(isinstance(pred, dict) and pred.get("kind") in PREDICATES, "unsupported predicate")
        if pred["kind"] == "MINION_HAS_RACE":
            fields(pred, {"kind", "race"})
            require(pred["race"] in RACES, "unsupported minion race")
        elif pred["kind"] == "SPELL_HAS_SCHOOL":
            fields(pred, {"kind", "school"})
            require(pred["school"] in SCHOOLS, "unsupported spell school")
        else:
            fields(pred, {"kind", "minimum_cost"})
            require(type(pred["minimum_cost"]) is int and 0 <= pred["minimum_cost"] <= 10,
                    "invalid current-cost threshold")
        effects = row["effects"]
        require(isinstance(effects, list) and 1 <= len(effects) <= 3, "one to three fixed effects required")
        for effect in effects:
            require(isinstance(effect, dict) and effect.get("op") in EFFECTS, "unsupported effect")
            op = effect["op"]
            if op == "REFRESH_MANA":
                fields(effect, {"op", "amount"})
                require(type(effect["amount"]) is int and 1 <= effect["amount"] <= 10, "invalid mana amount")
            elif op == "ADD_SELF_ENCHANT":
                fields(effect, {"op", "enchantment_ref"})
                require(effect["enchantment_ref"] == "BRM_033e", "unreviewed enchantment")
            elif op == "SET_SELF_TAG":
                fields(effect, {"op", "tag", "value"})
                require(effect["tag"] in TAGS and effect["value"] in (0, 1), "unsupported self tag")
            else:
                fields(effect, {"op", "amount"})
                require(type(effect["amount"]) is int and 1 <= effect["amount"] <= 10, "invalid damage")
        if "targeting" in row:
            targeting = row["targeting"]
            fields(targeting, {"mode", "predicate_ref", "target_type"})
            require(targeting == {"mode": "OPTIONAL_WHEN_PREDICATE_TRUE", "predicate_ref": "same", "target_type": "CHARACTER"} and
                    any(e["op"] == "DAMAGE_TARGET" for e in effects), "unsupported targeting contract")
        require(("targeting" in row) == any(e["op"] == "DAMAGE_TARGET" for e in effects),
                "target damage needs a shared optional-target contract")
    require(seen == set(allowed), "review allowlist must equal declarations")
    return sorted(rows, key=lambda row: row["card_id"])


def condition_expression(predicate: dict) -> str:
    kind = predicate["kind"]
    if kind == "MINION_HAS_RACE":
        return f"SelfCondition::IsHoldingRace(Race::{predicate['race']})"
    if kind == "SPELL_HAS_SCHOOL":
        return f"SelfCondition::IsHoldingSpellSchool(SpellSchool::{predicate['school']})"
    return f"SelfCondition::HasSpellInHandWithCostAtLeast({predicate['minimum_cost']})"


def task_expression(effect: dict) -> str:
    op = effect["op"]
    if op == "REFRESH_MANA":
        return f"std::make_shared<RefreshManaTask>({effect['amount']})"
    if op == "ADD_SELF_ENCHANT":
        return f"std::make_shared<AddEnchantmentTask>(\"{effect['enchantment_ref']}\", EntityType::SOURCE)"
    if op == "SET_SELF_TAG":
        return f"std::make_shared<SetGameTagTask>(EntityType::SOURCE, GameTag::{effect['tag']}, {effect['value']})"
    return f"std::make_shared<DamageTask>(EntityType::TARGET, {effect['amount']})"


def render(rows: list[dict]) -> tuple[str, str]:
    header = """// Generated by scripts/generate_held_card_gate_fixed_battlecry.py. Do not edit.\n#pragma once\n#include <Rosetta/PlayMode/Cards/CardDef.hpp>\n#include <map>\n#include <string>\nnamespace RosettaStone::PlayMode {\nclass ManaMindHeldCardGateFixedBattlecryGen { public: static void AddAll(std::map<std::string, CardDef>& cards); };\n}\n"""
    blocks = []
    for row in rows:
        cid = row["card_id"]
        req = ""
        if "targeting" in row:
            req = "        cardDef.property.playReqs.emplace(PlayReq::REQ_TARGET_IF_AVAILABLE_AND_SPELL_COST_AT_LEAST_IN_HAND, " + str(row["predicate"]["minimum_cost"]) + ");\n"
        tasks = ",\n                    ".join(task_expression(effect) for effect in row["effects"])
        condition = condition_expression(row["predicate"])
        blocks.append(f'''    if (cards.contains("{cid}")) throw std::logic_error("duplicate generated CardDef: {cid}");
    {{
        CardDef cardDef;
        cardDef.ClearData();
{req}        cardDef.power.AddPowerTask(std::make_shared<ConditionTask>(
            EntityType::SOURCE,
            std::vector<std::shared_ptr<SelfCondition>>{{std::make_shared<SelfCondition>({condition})}}));
        cardDef.power.AddPowerTask(std::make_shared<FlagTask>(true, TaskList{{
                    {tasks}}}));
        cards.emplace("{cid}", std::move(cardDef));
    }}''')
    source = '''// Generated by scripts/generate_held_card_gate_fixed_battlecry.py. Do not edit.
#include <Rosetta/PlayMode/CardSets/ManaMindHeldCardGateFixedBattlecryGen.hpp>
#include <Rosetta/PlayMode/Conditions/SelfCondition.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/ConditionTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/FlagTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/RefreshManaTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/AddEnchantmentTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/SetGameTagTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DamageTask.hpp>
#include <stdexcept>
#include <utility>
namespace RosettaStone::PlayMode {
void ManaMindHeldCardGateFixedBattlecryGen::AddAll(std::map<std::string, CardDef>& cards) {
    using namespace SimpleTasks;
''' + "\n\n".join(blocks) + "\n}\n}\n"
    return header, source
