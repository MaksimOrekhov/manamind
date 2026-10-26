"""Census of all 125 ManaEngine declarations against Card IR v0.1, plus a cross-check of the 26 family representatives.

Every ManaEngine construct (ability family, effect kind, target, card-specific field and its value) is mapped by hand to
the IR elements that express it. ``MISSING:<element>`` marks a construct that needs an element v0.1 does not have;
``METADATA`` marks data HearthstoneJSON already carries; ``EVIDENCE`` marks evidence bookkeeping that belongs to the
declaration's decisions, not to the effect. The mapping table is the reviewed claim; the script only applies it.

    python -I reports/card_ir_pilot_1/engine_mapping.py --output reports/card_ir_pilot_1/engine_mapping.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from manamind.card_ir import ELEMENTS, validate_declaration  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402

ENGINE = ROOT / "experiments/manaengine/data/card_abilities.json"
GENERIC_KEYS = {"ability", "support_state", "reviewed_rules_text", "effects"}

FAMILIES = {
    "NONE": set(),
    "EFFECT_COMPOSITION": set(),
    "TARGET_DAMAGE": {"ability:play", "pick:CHOSEN", "op:DEAL_DAMAGE", "value:spell_damage_literal"},
    "DEATHRATTLE_DRAW": {"ability:deathrattle", "op:DRAW"},
    "END_TURN_ENEMY_AREA_DAMAGE": {"ability:trigger", "event:TURN_END", "timing:AT", "op:DEAL_DAMAGE", "pick:ALL"},
    "END_TURN_ENEMY_HERO_DAMAGE": {"ability:trigger", "event:TURN_END", "timing:AT", "op:DEAL_DAMAGE", "selector:ENEMY_HERO"},
    "END_TURN_OTHER_MINIONS_DAMAGE": {"ability:trigger", "event:TURN_END", "timing:AT", "op:DEAL_DAMAGE", "pick:ALL",
                                      "selector:exclude", "selector:SELF"},
    "NEXT_DEMON_DISCOUNT": {"ability:play", "op:ADD_PLAYER_EFFECT", "modifier:cost", "pred:race", "pred:card_type",
                            "duration:UNTIL_USED"},
    "NEXT_SPELL_DISCOUNT": {"ability:play", "op:ADD_PLAYER_EFFECT", "modifier:cost", "pred:card_type", "duration:THIS_TURN"},
    "SECRET": {"ability:trigger", "label:SECRET", "keyword:SECRET", "timing:WHEN"},
    "BACKSTAB": {"ability:play", "pick:CHOSEN", "pred:damaged", "op:DEAL_DAMAGE", "value:spell_damage_literal"},
    "DEATHRATTLE_GENERATE": {"ability:deathrattle", "op:ADD_TO_HAND", "card_source:card"},
    "DISCOVER": {"ability:play", "op:DISCOVER"},
    "LIFESTEAL_DAMAGE": {"ability:play", "keyword:LIFESTEAL", "pick:CHOSEN", "op:DEAL_DAMAGE", "value:spell_damage_literal"},
    "DESTROY_ENEMY_WEAPON": {"ability:play", "op:DESTROY", "selector:ENEMY_WEAPON"},
    "MINION_DAMAGE_GENERATE": {"ability:play", "pick:CHOSEN", "op:DEAL_DAMAGE", "value:spell_damage_literal"},
    "SPELL_DAMAGE_AURA": {"ability:aura", "cond:is", "pred:damaged", "modifier:spell_damage", "selector:SELF"},
    "SPELL_DAMAGE_GAINS_ATTACK": {"ability:trigger", "event:DAMAGE_DEALT", "timing:WHENEVER", "pred:card_type",
                                  "trigger_limit:FIRST_EACH_TURN", "op:ENCHANT", "selector:SELF"},
    "SPELL_DAMAGE_HAND_DECK": {"ability:play", "op:ENCHANT", "pick:ALL", "zone:HAND", "zone:DECK"},
    "RANDOM_MISSILES": {"ability:play", "control:repeat", "value:spell_damage_literal", "pick:RANDOM", "op:DEAL_DAMAGE"},
    "CAST_RANDOM_SECRETS": {"ability:play", "control:if", "cond:cmp", "value:counter", "counter:SPELL_CAST",
                            "scope:THIS_TURN", "op:CAST", "card_source:random_from", "pred:card_class", "pred:keyword"},
    "REINFORCEMENT_AURA": {"ability:play", "op:ADD_PLAYER_EFFECT", "ability:trigger", "event:TURN_END", "timing:AT",
                           "op:SUMMON", "card_source:from_zone", "pick:RANDOM", "zone:DECK", "pred:cost"},
    "RECRUITER_SUMMON_RUSH": {"ability:play", "op:SUMMON", "card_source:from_zone", "pick:RANDOM", "zone:DECK",
                              "pred:cost", "op:ENCHANT", "keyword:RUSH", "selector:ref"},
    "HERO_ATTACK_DRAW": {"ability:trigger", "event:HERO_ATTACK", "timing:AFTER", "op:DRAW"},
    "DARK_GIFT_OPTION": {"ability:enchantment_template", "keyword:DARK_GIFT"},
    "TAKES_DAMAGE_GENERATE": {"ability:trigger", "event:DAMAGE_TAKEN", "timing:WHENEVER", "selector:SELF",
                              "op:ADD_TO_HAND", "card_source:random_from", "op:MODIFY_COST"},
}
EFFECT_KINDS = {
    "DAMAGE": {"op:DEAL_DAMAGE"},
    "DRAW": {"op:DRAW"},
    "HEAL": {"op:RESTORE_HEALTH"},
    "SUMMON_FIXED": {"op:SUMMON", "card_source:card"},
    "GAIN_ARMOR": {"MISSING:op:GAIN_ARMOR"},
    "MODIFY_HERO_ATTACK": {"op:ENCHANT", "MISSING:selector:FRIENDLY_HERO", "duration:THIS_TURN"},
    "FREEZE": {"MISSING:op:FREEZE"},
    "BUFF_FRIENDLY_MINIONS": {"op:ENCHANT", "pick:ALL"},
    "DESTROY_MINION": {"op:DESTROY"},
    "DISCARD_RANDOM_SPELL": {"control:pay", "pay:discard", "pick:RANDOM", "zone:HAND", "pred:spell_school"},
    "HEAL_MINION_TO_FULL": {"op:RESTORE_HEALTH", "MISSING:value:missing_health"},
    "MODIFY_WEAPON_ATTACK": {"op:ENCHANT", "MISSING:selector:FRIENDLY_WEAPON"},
    "GRANT_HEALING_BONUS": {"op:ADD_PLAYER_EFFECT", "modifier:rule", "MISSING:rule:HEALING_BONUS"},
    "BUFF_MINION": {"op:ENCHANT", "pick:CHOSEN"},
}
TARGETS = {
    "SELF": set(), "EXPLICIT_CHARACTER": {"pick:CHOSEN"}, "EXPLICIT_MINION": {"pick:CHOSEN"},
    "EXPLICIT_ENEMY_CHARACTER": {"pick:CHOSEN"}, "EXPLICIT_FRIENDLY_MINION": {"pick:CHOSEN"},
    "EXPLICIT_FRIENDLY_CHARACTER": {"pick:CHOSEN"}, "EXPLICIT_DAMAGED_ENEMY_MINION": {"pick:CHOSEN", "pred:damaged"},
    "EXPLICIT_DAMAGED_MINION": {"pick:CHOSEN", "pred:damaged"}, "ENEMY_CHARACTERS": {"pick:ALL"},
    "ENEMY_MINIONS": {"pick:ALL"}, "ALL_FRIENDLY_CHARACTERS": {"pick:ALL"}, "ALL_MINIONS": {"pick:ALL"},
    "ALL_CHARACTERS": {"pick:ALL"}, "RANDOM_ENEMY_MINION": {"pick:RANDOM"},
    "RANDOM_DISTINCT_ENEMY_CHARACTERS": {"pick:RANDOM", "selector:exclude"}, "ENEMY_HERO": {"selector:ENEMY_HERO"},
    "SELF_HERO": {"MISSING:selector:FRIENDLY_HERO"}, "FRIENDLY_WEAPON": {"MISSING:selector:FRIENDLY_WEAPON"},
}
FIELDS = {
    "damage": set(), "damage_outcome_amount": set(), "deathrattle_draw_count": set(), "choice_count": set(),
    "pool_count": set(), "random_cast_count": set(), "dark_gift_attack": set(), "dark_gift_health": set(),
    "deck_draw_filter": {"pred:card_type"},
    "damage_outcome_condition": {"control:if", "MISSING:cond:mortally_wounded"},
    "choice_pool": {"op:DISCOVER"}, "choice_cost_delta": {"op:MODIFY_COST"},
    "held_spell_threshold": {"ability:trigger", "MISSING:event:SPELL_CAST", "value:counter", "op:TRANSFORM"},
    "transform_card": {"op:TRANSFORM", "card_source:card"},
    "card_type": {"METADATA"}, "cost": {"METADATA"}, "attack": {"METADATA"}, "health": {"METADATA"},
    "race": {"METADATA"},
    "generated_card": {"op:ADD_TO_HAND", "card_source:card"},
    "pool_max_cost": {"pred:cost"},
    "choose_one_a": {"MISSING:control:choose_one"}, "choose_one_b": {"MISSING:control:choose_one"},
    "takes_damage_pool_id": {"card_source:random_from"}, "takes_damage_cost_delta": {"op:MODIFY_COST"},
    "kindred_copy_contract": {"ability:play", "label:KINDRED", "cond:mechanic", "op:SUMMON", "card_source:copy_of"},
    "spell_damage_cost_reduction": {"ability:aura", "modifier:cost", "value:counter",
                                    "MISSING:counter:SPELL_DAMAGE_DEALT"},
    "shatter_left_card": {"MISSING:keyword:SHATTER"}, "shatter_right_card": {"MISSING:keyword:SHATTER"},
    "spell_damage": {"ability:aura", "modifier:spell_damage"},
    "damaged_spell_damage": {"modifier:spell_damage"},
    "spell_damage_attack": set(), "spell_damage_grant": set(),
    "prepare": {"keyword:PREPARE"}, "reviewed_random_secret_pool": {"card_source:random_from"},
    "duration": {"duration:N_TURNS"}, "lifesteal": {"keyword:LIFESTEAL"},
    "dark_gift_keywords": set(), "dark_gift_cost": {"MISSING:modifier:cost_in_template"},
    "dark_gift_requires_positive_attack": {"MISSING:pred:stat"}, "dark_gift_requires_battlecry": {"pred:has_mechanic"},
    "dark_gift_option_pool_id": {"keyword:DARK_GIFT"},
    "requires_friendly_weapon": {"cond:exists", "MISSING:selector:FRIENDLY_WEAPON"},
    "colossal_appendages": {"keyword:COLOSSAL"},
}
FIELD_VALUES = {
    ("damage_outcome_condition", "ALWAYS"): set(),
    ("damage_outcome_followup", "HEAL_ENEMY_HERO"): {"op:RESTORE_HEALTH", "selector:ENEMY_HERO"},
    ("damage_outcome_followup", "DRAW_SELF"): {"op:DRAW"},
    ("damage_outcome_followup", "DRAW_TARGET_OWNER"): {"op:DRAW", "MISSING:player:owner_of"},
    ("secret_trigger", "FRIENDLY_MINION_ATTACKED"): {"event:ATTACK_DECLARED"},
    ("secret_trigger", "FRIENDLY_HERO_ATTACKED"): {"event:ATTACK_DECLARED", "MISSING:selector:FRIENDLY_HERO"},
    ("secret_trigger", "ENEMY_MINION_ATTACKS"): {"event:ATTACK_DECLARED"},
    ("secret_trigger", "OPPONENT_CASTS_SPELL"): {"MISSING:event:SPELL_CAST"},
    ("secret_trigger", "OPPONENT_PLAYS_MINION"): {"MISSING:event:CARD_PLAYED"},
    ("secret_trigger", "OPPONENT_TURN_ENDS"): {"event:TURN_END"},
    ("secret_effect", "OASIS_ALLY"): {"op:SUMMON", "card_source:card"},
    ("secret_effect", "ENEMY_AREA_DAMAGE"): {"op:DEAL_DAMAGE", "pick:ALL"},
    ("secret_effect", "COUNTERSPELL"): {"MISSING:op:COUNTER"},
    ("secret_effect", "ICE_BARRIER"): {"MISSING:op:GAIN_ARMOR"},
    ("secret_effect", "EXPLOSIVE_RUNES"): {"op:DEAL_DAMAGE", "value:arith", "value:stat", "selector:ENEMY_HERO"},
    ("secret_effect", "MYSTIC_MISDIRECTION"): {"op:TRANSFORM", "card_source:card"},
    ("secret_effect", "FLAMES_OF_INFINITY"): {"op:DEAL_DAMAGE", "MISSING:pred:extremum", "MISSING:value:infinite"},
}
EFFECT_FIELDS = {
    "summon_card": set(), "random_count": set(), "lifesteal": {"keyword:LIFESTEAL"},
    "discard_school": {"pred:spell_school"}, "requires_previous_discard": {"control:pay"},
    "conditional_extra_count": {"control:if"}, "exclude_previous_target": {"selector:exclude"},
    "evidence_constraint": {"EVIDENCE"},
    ("summon_condition", "HOLDING_DRAGON"): {"control:if", "cond:exists", "zone:HAND", "pred:race"},
}
# Top-level fields that the C++ CardDefinition carries for one card or one family (not part of the generic effect list).
CARD_SPECIFIC_FIELDS = {"damage_outcome_condition", "damage_outcome_followup", "damage_outcome_amount",
                        "held_spell_threshold", "transform_card", "shatter_left_card", "shatter_right_card",
                        "choose_one_a", "choose_one_b", "spell_damage_cost_reduction", "kindred_copy_contract",
                        "requires_friendly_weapon", "lifesteal", "card_type", "cost", "attack", "health", "race"}


def map_declaration(decl: dict) -> tuple[set[str], list[str]]:
    """Mapped markers (IR elements, MISSING:, METADATA, EVIDENCE) and the constructs that had no mapping."""
    mapped = set(FAMILIES.get(decl["ability"], {f"UNMAPPED:{decl['ability']}"}))
    unmapped = []
    for key, value in decl.items():
        if key in GENERIC_KEYS:
            continue
        if isinstance(value, str) and (key, value) in FIELD_VALUES:
            mapped |= FIELD_VALUES[(key, value)]
        elif key in FIELDS:
            mapped |= FIELDS[key]
            if key == "dark_gift_keywords":
                mapped |= {f"keyword:{k}" if f"keyword:{k}" in ELEMENTS else f"MISSING:keyword:{k}" for k in value}
            if key == "deck_draw_filter" and value == "FIRE_SPELL":
                mapped |= {"pred:spell_school"}
        else:
            unmapped.append(f"{key}={value}")
    effect_lists = [decl.get("effects", []), decl.get("choose_one_a", []), decl.get("choose_one_b", [])]
    for effects in effect_lists:
        for effect in effects:
            mapped |= EFFECT_KINDS.get(effect["kind"], {f"UNMAPPED:{effect['kind']}"})
            mapped |= TARGETS.get(effect["target"], {f"UNMAPPED:{effect['target']}"})
            for key, value in effect.items():
                if key in ("kind", "target", "amount"):
                    continue
                if isinstance(value, str) and (key, value) in EFFECT_FIELDS:
                    mapped |= EFFECT_FIELDS[(key, value)]
                elif key in EFFECT_FIELDS:
                    mapped |= EFFECT_FIELDS[key]
                else:
                    unmapped.append(f"effect.{key}={value}")
    if len(decl.get("effects", [])) > 1:
        mapped.add("control:seq")
    return mapped, unmapped


def classify(decl: dict, mapped: set[str]) -> str:
    if decl["ability"] == "NONE" and not decl.get("effects"):
        return "METADATA_ONLY"
    if decl["ability"] != "EFFECT_COMPOSITION":
        return "NAMED_HANDLER"
    return "COMPOSITION_WITH_CARD_FIELDS" if set(decl) & CARD_SPECIFIC_FIELDS else "DATA_COMPOSITION"


def engine_numbers(decl: dict) -> list[int]:
    numbers = []
    for key, value in decl.items():
        if isinstance(value, int) and not isinstance(value, bool) and key not in ("cost", "attack", "health") and value:
            numbers.append(abs(value))
    for effect in decl.get("effects", []):
        if effect.get("amount"):
            numbers.append(abs(effect["amount"]))
    return sorted(numbers)


def ir_numbers(node) -> list[int]:
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, int) and not isinstance(value, bool) and value and key not in ("factor",):
                found.append(abs(value))
            else:
                found += ir_numbers(value)
    elif isinstance(node, list):
        for item in node:
            found += ir_numbers(item)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; refusing to overwrite")
    meta = CardMetadata.load()
    cards = json.loads(ENGINE.read_text(encoding="utf-8"))["cards"]
    protocol = json.loads((PILOT / "protocol.json").read_text(encoding="utf-8"))

    census, missing_users = {}, {}
    for card_id, decl in cards.items():
        mapped, unmapped = map_declaration(decl)
        missing = sorted(m.removeprefix("MISSING:") for m in mapped if m.startswith("MISSING:"))
        unknown = sorted(m for m in mapped if m.startswith("UNMAPPED:") or (":" in m and not m.startswith(
            ("MISSING:", "UNMAPPED:")) and m not in ELEMENTS))
        census[card_id] = {"ability": decl["ability"], "support_state": decl["support_state"],
                           "class": classify(decl, mapped), "missing_elements": missing,
                           "unmapped_constructs": unmapped + unknown,
                           "metadata_duplicated": "METADATA" in mapped, "evidence_field": "EVIDENCE" in mapped}
        for element in missing:
            missing_users.setdefault(element, []).append(card_id)
    classes = Counter(row["class"] for row in census.values())
    # An UNSUPPORTED declaration may carry no semantics at all (e.g. EDR_100t5), so it is not counted as mapped.
    supported = [c for c, row in census.items() if row["support_state"] != "UNSUPPORTED"]
    fully = [c for c in supported if not census[c]["missing_elements"] and not census[c]["unmapped_constructs"]]
    by_class_full = Counter(census[c]["class"] for c in fully)

    reps = []
    for row in protocol["engine_validation"]["cards"]:
        card_id = row["id"]
        doc = json.loads((PILOT / "declarations" / f"{card_id}.json").read_text(encoding="utf-8"))
        report = validate_declaration(doc, meta)
        ir_elements = set(report.elements)
        mapped, _ = map_declaration(cards[card_id])
        mapped_elements = {m for m in mapped if m in ELEMENTS}
        reps.append({
            "card": card_id, "ability": row["ability"], "engine_support_state": row["support_state"],
            "ir_status": doc["status"],
            "engine_constructs_not_in_text_ir": sorted(mapped_elements - ir_elements),
            "engine_constructs_missing_from_v0_1": sorted(m.removeprefix("MISSING:") for m in mapped if m.startswith("MISSING:")),
            "text_ir_elements_beyond_engine": sorted(ir_elements - mapped_elements - {
                "value:literal", "selector:ref", "control:seq", "label:SPELL", "label:BATTLECRY", "label:LOCATION"}),
            "engine_numbers": engine_numbers(cards[card_id]),
            "ir_numbers_cover_engine_numbers": not (Counter(engine_numbers(cards[card_id]))
                                                    - Counter(ir_numbers(doc["abilities"]) + ir_numbers(doc.get("keywords", [])))),
        })
    payload = {
        "declarations": len(cards),
        "families": len({d["ability"] for d in cards.values()}),
        "classes": dict(sorted(classes.items())),
        "supported_declarations": len(supported),
        "classes_supported": dict(sorted(Counter(census[c]["class"] for c in supported).items())),
        "fully_mapped_to_v0_1": len(fully),
        "fully_mapped_by_class": dict(sorted(by_class_full.items())),
        "supported_needing_missing": sum(1 for c in supported if census[c]["missing_elements"]),
        "missing_elements_for_supported": dict(sorted(Counter(
            m for c in supported for m in census[c]["missing_elements"]).items(), key=lambda kv: (-kv[1], kv[0]))),
        "missing_elements": {k: {"declarations": len(v), "examples": v[:6]} for k, v in sorted(
            missing_users.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "declarations_needing_missing": sum(1 for row in census.values() if row["missing_elements"]),
        "unmapped_constructs": sorted({u for row in census.values() for u in row["unmapped_constructs"]}),
        "metadata_duplicated_in_declarations": sorted(c for c, row in census.items() if row["metadata_duplicated"]),
        "engine_unsupported_declarations": sorted(c for c, d in cards.items() if d["support_state"] == "UNSUPPORTED"),
        "card_ids_hardcoded_in_cpp": ["CORE_CS2_033 (Oasis Ally's Water Elemental)", "GAME_005 (The Coin)"],
        "representatives": reps,
        "census": census,
    }
    args.output.write_bytes((json.dumps(payload, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(json.dumps({k: payload[k] for k in ("declarations", "families", "classes", "supported_declarations",
                                              "classes_supported", "fully_mapped_to_v0_1", "fully_mapped_by_class",
                                              "supported_needing_missing", "unmapped_constructs")}, indent=1))
    print("missing elements:", {k: v["declarations"] for k, v in payload["missing_elements"].items()})
    for rep in reps:
        print(rep["card"], rep["ir_status"], "| engine-not-in-ir:", rep["engine_constructs_not_in_text_ir"],
              "| ir-beyond:", rep["text_ir_elements_beyond_engine"], "| numbers ok:", rep["ir_numbers_cover_engine_numbers"])


if __name__ == "__main__":
    main()
