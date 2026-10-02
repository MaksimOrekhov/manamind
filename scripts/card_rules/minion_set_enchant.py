"""Finite, versioned task composition; executable rules stay in RosettaStone."""
from __future__ import annotations

import re

SELECTORS = {
    "OWN_BOARD_MINIONS": "MINIONS",
    "OWN_BOARD_MINIONS_EXCLUDING_SOURCE": "MINIONS_NOSOURCE",
    "OWN_HAND_MINIONS": "MINIONS_HAND",
    "TARGET_MINION": "TARGET",
}
KEYWORDS = {
    "TAUNT": ("TAUNT",),
    "ELUSIVE": ("CANT_BE_TARGETED_BY_SPELLS", "CANT_BE_TARGETED_BY_HERO_POWERS"),
}
IDENTIFIER = re.compile(r"[A-Z][A-Z0-9]*_[A-Za-z0-9]+\Z")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def fields(row: dict, required: set[str], optional: set[str] | None = None) -> None:
    require(isinstance(row, dict), "object required")
    require(required <= row.keys() and row.keys() <= required | (optional or set()),
            "unknown or missing fields")


def validate_effects(activation: str, effects: list[dict], dependencies: dict) -> None:
    require(activation in {"SPELL", "BATTLECRY"}, "unsupported activation")
    require(isinstance(effects, list) and 1 <= len(effects) <= 2, "one or two effects required")
    require(all(isinstance(e, dict) for e in effects), "effects must be objects")
    require(len(effects) == 1 or effects[0].get("op") == "TARGET_CHARACTER_DIVINE_SHIELD", "only Shield may precede the minion-set operation")
    # A separate typed character operation may precede one minion-set effect.
    require(effects[-1].get("op") == "MINION_SET_ENCHANT", "minion set effect required last")
    for index, effect in enumerate(effects):
        op = effect.get("op")
        if op == "TARGET_CHARACTER_DIVINE_SHIELD":
            fields(effect, {"op"})
            require(index == 0 and len(effects) == 2 and activation == "SPELL",
                    "character Shield is a preceding spell operation")
        elif op == "MINION_SET_ENCHANT":
            fields(effect, {"op", "selector", "enchantment_ref", "keywords"}, {"max_current_attack"})
            selector = effect["selector"]
            require(selector in SELECTORS, "unsupported selector")
            require(effect["enchantment_ref"] in dependencies, "unreviewed enchantment")
            keywords = effect["keywords"]
            require(isinstance(keywords, list) and all(isinstance(k, str) for k in keywords), "keywords must be a list")
            require(len(keywords) == len(set(keywords)) and set(keywords) <= KEYWORDS.keys(), "unsupported/duplicate keyword")
            require(not keywords or selector != "OWN_HAND_MINIONS", "hand keywords unreviewed in v1")
            if "max_current_attack" in effect:
                threshold = effect["max_current_attack"]
                require(type(threshold) is int and 0 <= threshold <= 1000, "invalid Attack threshold")
                require(selector in {"OWN_BOARD_MINIONS", "OWN_BOARD_MINIONS_EXCLUDING_SOURCE"}, "threshold requires board minions")
            require(not (len(effects) == 2 and selector == "TARGET_MINION"), "character and minion target constraints conflict")
        else:
            raise ValueError("unsupported operation")


def render_tasks(effects: list[dict]) -> list[str]:
    """No consumer identity enters this renderer. Selection is made once."""
    tasks = []
    for effect in effects:
        if effect["op"] == "TARGET_CHARACTER_DIVINE_SHIELD":
            tasks.append("std::make_shared<SetGameTagTask>(EntityType::TARGET, GameTag::DIVINE_SHIELD, 1)")
            continue
        tasks.append(f"std::make_shared<IncludeTask>(EntityType::{SELECTORS[effect['selector']]})")
        if "max_current_attack" in effect:
            tasks.append("std::make_shared<FilterStackTask>(std::vector<std::shared_ptr<SelfCondition>>{"
                         f"std::make_shared<SelfCondition>(SelfCondition::IsAttack({effect['max_current_attack']}, RelaSign::LEQ))" + "})")
        tasks.append(f"std::make_shared<AddEnchantmentTask>(\"{effect['enchantment_ref']}\", EntityType::STACK)")
        for keyword in sorted(effect["keywords"]):
            for tag in KEYWORDS[keyword]:
                tasks.append(f"std::make_shared<SetGameTagTask>(EntityType::STACK, GameTag::{tag}, 1)")
    return tasks


def target_requirements(effects: list[dict]) -> list[str]:
    if any(effect["op"] == "TARGET_CHARACTER_DIVINE_SHIELD" for effect in effects):
        return ["TARGET_TO_PLAY"]
    if any(effect.get("selector") == "TARGET_MINION" for effect in effects):
        return ["TARGET_TO_PLAY", "MINION_TARGET"]
    return []
