"""Strict shared contract for selecting low-cost minions from the live deck."""
from __future__ import annotations

from .minion_set_enchant import fields, require


def validate_selection(row: dict) -> None:
    fields(row, {"max_cost", "count"})
    require(type(row["max_cost"]) is int and 0 <= row["max_cost"] <= 10,
            "invalid maximum minion cost")
    require(type(row["count"]) is int and 1 <= row["count"] <= 7,
            "invalid selected minion count")


def render_tasks(row: dict, rush_enchantment: str) -> list[str]:
    validate_selection(row["selection"])
    selection = row["selection"]
    tasks = [
        "std::make_shared<IncludeTask>(EntityType::DECK)",
        "std::make_shared<FilterStackTask>(std::vector<std::shared_ptr<SelfCondition>>{"
        "std::make_shared<SelfCondition>(SelfCondition::IsMinion()), "
        "std::make_shared<SelfCondition>(SelfCondition::IsCost("
        f"{selection['max_cost']}, RelaSign::LEQ))" + "})",
        "std::make_shared<RandomTask>(EntityType::STACK, "
        f"{selection['count']})",
    ]
    if row["grant_rush"]:
        tasks.append(
            f"std::make_shared<AddEnchantmentTask>(\"{rush_enchantment}\", EntityType::STACK)"
        )
    tasks.append("std::make_shared<SummonStackTask>(true)")
    return tasks


def validate_activation(activation: dict) -> None:
    fields(activation, {"type"}, {"trigger_limit"})
    if activation["type"] == "BATTLECRY":
        require("trigger_limit" not in activation, "Battlecry has no recurring trigger limit")
    elif activation["type"] == "TURN_END":
        require(type(activation.get("trigger_limit")) is int and
                1 <= activation["trigger_limit"] <= 10,
                "bounded TURN_END trigger limit required")
    else:
        raise ValueError("unsupported activation")
