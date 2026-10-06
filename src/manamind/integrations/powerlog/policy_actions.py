"""Exact server selections mapped to visible, handle-free policy actions.

Handles exist only in MatchActions.keys and never in its model-facing actions.
Placement is one-based, like SendOption; non-placement actions use zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter

from hearthstone.enums import GameTag, Zone
from hslog.player import coerce_to_entity_id

from manamind.domain.game_state import GameState



class ActionMappingError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def visible_entity(game, handle: int, self_id: int, state: GameState) -> dict:
    """Resolve only SELF hand and public in-play characters/Locations/powers."""
    try:
        entity = game.find_entity_by_id(handle)
    except Exception:
        entity = None
    if entity is None:
        raise ActionMappingError("TARGET_UNRESOLVED")
    owner = entity.tags.get(GameTag.CONTROLLER)
    if owner not in {player.tags.get(GameTag.PLAYER_ID) for player in game.players}:
        raise ActionMappingError("TARGET_UNRESOLVED")
    side = "SELF" if owner == self_id else "OPPONENT"
    kind = getattr(entity.type, "name", "UNKNOWN_TYPE")
    if entity.zone == Zone.HAND and side == "SELF":
        index = entity.tags.get(GameTag.ZONE_POSITION, 0) - 1
        if not 0 <= index < len(state.self_hand):
            raise ActionMappingError("TARGET_UNRESOLVED")
        card = state.self_hand[index]
        if not entity.card_id or entity.card_id != card.card_id:
            raise ActionMappingError("TARGET_UNRESOLVED")
        return {"kind": kind, "card_id": card.card_id, "side": side,
                "hand_index": index, "card_cost": card.effective_cost,
                "card_attack": card.effective_attack,
                "card_health": card.current_health if card.current_health is not None else card.health,
                "card_spell_damage": card.current_spell_damage, "card_durability": card.effective_durability}
    if entity.zone != Zone.PLAY or kind not in {"HERO", "HERO_POWER", "MINION", "LOCATION"}:
        raise ActionMappingError("TARGET_UNRESOLVED")
    player = state.self_player if side == "SELF" else state.opponent
    if kind == "HERO":
        return {"kind": kind, "side": side, "card_id": entity.card_id or "UNKNOWN_CARD",
                "attack": player.hero_attack, "health": player.hero_health, "position": -1,
                "taunt": False}
    if kind == "HERO_POWER":
        if side != "SELF" or player.hero_power is None:
            raise ActionMappingError("TARGET_UNRESOLVED")
        return {"kind": kind, "side": side, "card_id": player.hero_power.card_id,
                "attack": None, "health": None, "position": -1, "taunt": False,
                "card_cost": player.hero_power.effective_cost}
    position = entity.tags.get(GameTag.ZONE_POSITION, 0)
    items = player.locations if kind == "LOCATION" else player.board
    matches = [item for item in items if item.board_position == position]
    if len(matches) != 1 or matches[0].card.card_id != entity.card_id:
        raise ActionMappingError("TARGET_UNRESOLVED")
    item = matches[0]
    return {"kind": kind, "side": side, "card_id": item.card.card_id,
            "attack": getattr(item, "current_attack", None), "health": item.current_health,
            "position": position, "taunt": getattr(item, "taunt", False),
            "can_attack": getattr(item, "can_attack", False), "mechanics": item.card.mechanics}


@dataclass
class MatchActions:
    actions: list[dict]
    keys: list[tuple[int, int, int, int]]

    def select(self, option: int, sub: int, target: int, position: int) -> int:
        if sub != -1:
            raise ActionMappingError("CHOICE_UNRESOLVED")
        key = (option, sub, target, position)
        hits = [i for i, value in enumerate(self.keys) if value == key]
        if len(hits) != 1:
            reason = "AMBIGUOUS_SELECTION" if len(hits) > 1 else "TARGET_UNRESOLVED"
            raise ActionMappingError(reason)
        return hits[0]


def map_actions(packet, game, self_id: int, state: GameState) -> MatchActions:
    """Enumerate the whole supported MAIN_ACTION menu; never prune unknown options."""
    actions, keys, sources = [], [], set()
    # Invalid PLAY variants still disambiguate alternate HAND powers (Trade/Forge).
    # Counting only legal roots would misclassify an affordable alternate power
    # when the normal play itself is unaffordable.
    all_sources = Counter(int(coerce_to_entity_id(o.entity)) for o in packet.options if o.entity is not None)
    for option in packet.options:
        end_turn = getattr(option.type, "name", None) == "END_TURN"
        if option.error is not None and not end_turn:
            continue
        if end_turn:
            actions.append({"type": "END_TURN", "play_position": 0})
            keys.append((option.id, -1, 0, 0))
            continue
        if option.entity is None:
            raise ActionMappingError("UNSUPPORTED_DECISION_KIND")
        handle = int(coerce_to_entity_id(option.entity))
        if handle in sources or all_sources[handle] != 1:
            raise ActionMappingError("AMBIGUOUS_SELECTION")
        sources.add(handle)
        source = visible_entity(game, handle, self_id, state)
        if source["side"] != "SELF":
            raise ActionMappingError("SELF_AMBIGUOUS")
        if "hand_index" in source:
            entity = game.find_entity_by_id(handle)
            card = state.self_hand[source["hand_index"]]
            if (any(getattr(tag, "name", "") in {"TRADEABLE", "FORGE", "FORGEABLE"} and value
                    for tag, value in entity.tags.items())
                    or set(card.mechanics) & {"TRADEABLE", "FORGE", "FORGEABLE"}):
                raise ActionMappingError("UNSUPPORTED_DECISION_KIND")
            if source["kind"] not in {"MINION", "SPELL", "WEAPON", "LOCATION", "HERO"}:
                raise ActionMappingError("UNSUPPORTED_DECISION_KIND")
            kind = "PLAY_CARD"
        else:
            kind = {"HERO": "ATTACK", "MINION": "ATTACK", "HERO_POWER": "HERO_POWER",
                    "LOCATION": "ACTIVATE_LOCATION"}.get(source["kind"])
        if kind is None:
            raise ActionMappingError("UNSUPPORTED_DECISION_KIND")
        if kind == "ATTACK" and source["kind"] == "MINION":
            entity = game.find_entity_by_id(handle)
            if (not source["can_attack"] or "TITAN" in source["mechanics"]
                    or any(getattr(tag, "name", "") == "TITAN" and value for tag, value in entity.tags.items())):
                raise ActionMappingError("UNSUPPORTED_DECISION_KIND")
        if any(item.optype == "subOption" for item in option.options):
            raise ActionMappingError("CHOICE_UNRESOLVED")
        base = {"type": kind, "card_id": source["card_id"], "card_type": source["kind"],
                "source_kind": source["kind"], "source_card_id": source["card_id"],
                "source_is_hero": source["kind"] == "HERO",
                "source_attack": source.get("attack"), "source_health": source.get("health"),
                "source_board_position": source.get("position", -1)}
        for key in ("hand_index", "card_cost", "card_attack", "card_health", "card_spell_damage", "card_durability"):
            if key in source:
                base[key] = source[key]
        positions = [0]
        if kind == "PLAY_CARD" and source["kind"] in {"MINION", "LOCATION"}:
            count = len(state.self_player.board) + len(state.self_player.locations)
            if count >= 7:
                raise ActionMappingError("UNSUPPORTED_DECISION_KIND")
            positions = list(range(1, count + 2))
        targets = [item for item in option.options if item.optype == "target"]
        valid = [item for item in targets if item.error is None]
        # A root with target records but no legal target is not an untargeted action.
        for item in valid if targets else [None]:
            target_handle = 0 if item is None else int(coerce_to_entity_id(item.entity))
            fields = {}
            if target_handle:
                target = visible_entity(game, target_handle, self_id, state)
                if "hand_index" in target or target["kind"] == "HERO_POWER":
                    raise ActionMappingError("TARGET_UNRESOLVED")
                fields = {"target_kind": target["kind"], "target_side": target["side"],
                          "target_card_id": target["card_id"],
                          "target_is_hero": target["kind"] == "HERO",
                          "target_is_self": target["side"] == "SELF",
                          "target_attack": target["attack"], "target_health": target["health"],
                          "target_board_position": target["position"], "target_taunt": target["taunt"]}
            elif item is not None:
                raise ActionMappingError("TARGET_UNRESOLVED")
            for position in positions:
                actions.append({**base, **fields, "play_position": position})
                keys.append((option.id, -1, target_handle, position))
    if not actions or len(keys) != len(set(keys)):
        raise ActionMappingError("AMBIGUOUS_SELECTION")
    return MatchActions(actions, keys)
