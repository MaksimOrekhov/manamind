"""Action → source → target, using only the matching visible LIVE snapshot.

Zone positions count board slots (minions AND Locations). Missing/inconsistent
coordinates are omitted; a duplicate that cannot be identified is labelled unsafe.
No card effects, strategy or predicted outcomes are interpreted here.
"""
from __future__ import annotations

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
