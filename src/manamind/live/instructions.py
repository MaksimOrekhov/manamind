"""Action → source → target from the matching visible LIVE snapshot.

Zone positions count board slots (minions AND Locations). Missing/inconsistent
coordinates are omitted; ambiguous coordinates stay unsafe. A separate narrow
text check can warn about direct positive effects on enemy minions; it never
changes Policy order or predicts strategy/outcomes.
"""
from __future__ import annotations

import re

from .localization import CardNames


def _integer(value) -> bool:
    return type(value) is int and value >= 0


def board_slots(state: dict, side: str) -> list[dict] | None:
    player = state.get("self_player" if side == "SELF" else "opponent", {})
    slots = [*player.get("board", []), *player.get("locations", [])]
    positions = [item.get("board_position") for item in slots]
    if any(type(p) is not int or p <= 0 for p in positions):
        return None
    if sorted(positions) != list(range(1, len(slots) + 1)):
        return None
    return sorted(slots, key=lambda item: item["board_position"])


def _stats(attack, health) -> str:
    if _integer(attack) and _integer(health):
        return f"{attack}/{health}"
    return ""


def instruction(action: dict, state: dict | None, names: CardNames, language: str = "ru") -> dict:
    ru = language == "ru"
    state = state or {}
    kind = action.get("type")
    verbs = {"ATTACK": ("АТАКОВАТЬ", "ATTACK"), "PLAY_CARD": ("РАЗЫГРАТЬ", "PLAY"),
             "HERO_POWER": ("СИЛА ГЕРОЯ", "HERO POWER"),
             "ACTIVATE_LOCATION": ("АКТИВИРОВАТЬ ЛОКАЦИЮ", "ACTIVATE LOCATION"),
             "END_TURN": ("ЗАВЕРШИТЬ ХОД", "END TURN")}
    result = {"verb": verbs.get(kind, ("ДЕЙСТВИЕ", "ACTION"))[0 if ru else 1],
              "source": "", "target": "", "placement": "", "warning": ""}
    if kind == "END_TURN":
        return result

    def entity(prefix: str, side: str, entity_kind: str | None, card_id: str | None) -> str:
        own = side == "SELF"
        if entity_kind == "HERO":
            label = ("ТВОЙ ГЕРОЙ" if own else "ГЕРОЙ ПРОТИВНИКА") if ru else (
                "YOUR HERO" if own else "ENEMY HERO")
            health = action.get(prefix + "_health")
            stats = (_stats(action.get(prefix + "_attack"), health) if prefix == "source" and kind == "ATTACK"
                     else (f"{health} " + ("здоровья" if ru else "Health") if _integer(health) else ""))
            return " · ".join(filter(None, [label, stats]))
        if entity_kind == "HERO_POWER":
            label = "ТВОЯ СИЛА ГЕРОЯ" if ru else "YOUR HERO POWER"
            return f"{label}: {names.get(card_id, language)}"
        location = entity_kind == "LOCATION"
        label = (("ТВОЯ ЛОКАЦИЯ" if own else "ЛОКАЦИЯ ПРОТИВНИКА") if location else
                 ("ТВОЁ СУЩЕСТВО" if own else "СУЩЕСТВО ПРОТИВНИКА")) if ru else (
                     ("YOUR LOCATION" if own else "ENEMY LOCATION") if location else
                     ("YOUR MINION" if own else "ENEMY MINION"))
        stats = _stats(action.get(prefix + "_attack"), action.get(prefix + "_health"))
        if location and _integer(action.get(prefix + "_health")):
            stats = f"{action[prefix + '_health']} " + ("прочности" if ru else "durability")
        position = action.get(prefix + "_board_position")
        slots = board_slots(state, side)
        matched = (slots[position - 1] if slots is not None and type(position) is int
                   and 1 <= position <= len(slots) else None)
        coordinate = ""
        if matched and matched.get("card", {}).get("card_id") == card_id:
            coordinate = f"{position}-е слева" if ru else f"{position} from left"
            # Use actual current instance stats, never base card stats.
            stats = _stats(matched.get("current_attack"), matched.get("current_health"))
            if location and _integer(matched.get("current_health")):
                stats = f"{matched['current_health']} " + ("прочности" if ru else "durability")
        else:
            coordinate = "позиция не подтверждена" if ru else "position unverified"
            result["warning"] = ("Проверь цель и источник на экране: позиция не подтверждена."
                                 if ru else "Check source and target on screen: position unverified.")
        return " · ".join(filter(None, [f"{label}: {names.get(card_id, language)}", stats, coordinate]))

    source_id = action.get("source_card_id") or action.get("card_id")
    if kind == "PLAY_CARD":
        source = ("ИЗ РУКИ: " if ru else "FROM HAND: ") + names.get(source_id, language)
        index = action.get("hand_index")
        hand = state.get("self_hand", [])
        if (_integer(index) and index < len(hand) and hand[index].get("card_id") == source_id
                and len(hand) == state.get("self_player", {}).get("hand_size")):
            source += f" · {index + 1}-я карта слева" if ru else f" · card {index + 1} from left"
        else:
            source += " · позиция в руке не подтверждена" if ru else " · hand position unverified"
            result["warning"] = "Проверь карту в руке." if ru else "Check the card in your hand."
        result["source"] = source
        position = action.get("play_position")
        if type(position) is int and position > 0:
            slots = board_slots(state, "SELF")
            if slots is None or position > len(slots) + 1:
                result["placement"] = "Размещение не подтверждено" if ru else "Placement unverified"
                result["warning"] = "Проверь размещение на экране." if ru else "Check placement on screen."
            elif not slots:
                result["placement"] = "На свой пустой стол" if ru else "On your empty board"
            elif position == 1:
                result["placement"] = "Слева от всех своих карт на столе" if ru else "Left of all your board cards"
            elif position == len(slots) + 1:
                result["placement"] = "Справа от всех своих карт на столе" if ru else "Right of all your board cards"
            else:
                result["placement"] = (f"Между {position - 1}-й и {position}-й своими картами на столе"
                                       if ru else f"Between your board cards {position - 1} and {position}")
    else:
        source_kind = "HERO" if action.get("source_is_hero") else action.get("source_kind")
        result["source"] = entity("source", "SELF", source_kind, source_id)
    if action.get("target_kind"):
        side = action.get("target_side")
        if side in {"SELF", "OPPONENT"}:
            result["target"] = entity("target", side, action["target_kind"], action.get("target_card_id"))
        else:
            result["target"] = "Цель не подтверждена" if ru else "Target unverified"
            result["warning"] = result["target"]
    return result


_EFFECT_TEXT = re.compile(
    r"^give (?:a |your |a friendly )?minion (?:\+\d+(?:/\+\d+| attack| health)|divine shield|lifesteal)\b"
    r"|^restore \d+ health to (?:a |your |a friendly )?minion\b",
    re.IGNORECASE,
)
_HTML = re.compile(r"<[^>]*>")
_NEGATIVE_IN_SAME_SENTENCE = re.compile(
    r"\b(?:deal \d+ damage|destroy|silence|transform|return|remove|reduce)\b", re.IGNORECASE
)


def _positive_target_effects(text: str) -> tuple[str, ...]:
    """Recognize only explicit, direct positive minion text; unknown prose stays unclassified."""
    effects = set()
    plain = _HTML.sub("", text)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", plain):
        sentence = sentence.strip()
        if _EFFECT_TEXT.search(sentence) is None or _NEGATIVE_IN_SAME_SENTENCE.search(sentence):
            continue
        lowered = sentence.lower()
        if lowered.startswith("restore "):
            effects.add("heal")
        if re.match(r"^give (?:a |your |a friendly )?minion \+\d+", lowered):
            effects.add("stats")
        if "divine shield" in lowered:
            effects.add("shield")
        if "lifesteal" in lowered:
            effects.add("lifesteal")
    return tuple(effect for effect in ("stats", "shield", "lifesteal", "heal") if effect in effects)


def enemy_benefit_warning(action: dict, state: dict, names: CardNames, language: str) -> str:
    """Warn on a verified, explicit minion benefit; never changes action ranking."""
    if action.get("type") not in {"PLAY_CARD", "HERO_POWER", "ACTIVATE_LOCATION"}:
        return ""
    if action.get("target_side") != "OPPONENT" or action.get("target_kind") != "MINION":
        return ""
    position = action.get("target_board_position")
    slots = board_slots(state, "OPPONENT")
    if slots is None or type(position) is not int or not 1 <= position <= len(slots):
        return ""
    target = slots[position - 1]
    if target.get("card", {}).get("card_id") != action.get("target_card_id"):
        return ""
    for field, current_field in (("target_attack", "current_attack"), ("target_health", "current_health")):
        observed = action.get(field)
        current = target.get(current_field)
        if type(observed) is int and type(current) is int and observed != current:
            return ""
    effects = _positive_target_effects(names.text(action.get("source_card_id") or action.get("card_id")))
    if not effects:
        return ""
    effects = tuple(effect for effect in effects
                    if not (effect == "shield" and target.get("divine_shield") is True)
                    and not (effect == "lifesteal" and target.get("lifesteal") is True))
    if "heal" in effects:
        health, maximum = target.get("current_health"), target.get("max_health")
        if type(health) is not int or type(maximum) is not int or health >= maximum:
            effects = tuple(effect for effect in effects if effect != "heal")
    if not effects:
        return ""
    if language == "ru":
        details = {
            "stats": "может увеличить характеристики существа противника",
            "shield": "может дать существу противника Божественный щит",
            "lifesteal": "может дать существу противника Похищение жизни",
            "heal": "может вылечить существо противника",
        }
        reason = "; ".join(details[effect] for effect in effects)
        return f"Внимание: действие {reason}. Возможно, это часть комбинации — проверь цель."
    details = {
        "stats": "may increase an enemy minion's stats",
        "shield": "may give an enemy minion Divine Shield",
        "lifesteal": "may give an enemy minion Lifesteal",
        "heal": "may heal an enemy minion",
    }
    reason = "; ".join(details[effect] for effect in effects)
    return f"Warning: this action {reason}. It may be part of a combo; check the target."
