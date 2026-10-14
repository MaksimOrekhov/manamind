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

PLAY_ROLE = "PLAY"
PREPARE_ROLE = "PREPARE"


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


def _tag_int(entity, tag) -> int | None:
    value = entity.tags.get(tag)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _error_name(option) -> str | None:
    return None if option.error is None else getattr(option.error, "name", str(option.error))


def _classify_prepare_roots(state: GameState, entity, roots) -> dict[int, str]:
    """Role (PLAY or PREPARE) of each *legal* root of one Prepare hand card, from observable facts only.

    Evidence (ranked Standard logs, 62 chosen selections; each label was checked against the following public block
    and the ``IS_USING_PREPARE_OPTION`` tag): a Prepare card always lists exactly two roots, both ``type=POWER`` with the
    same ``mainEntity``. Option order is not used. Nothing in the message names a root, so a role is accepted only where
    the message itself decides it:

    * neither root legal: the card contributes no action;
    * one legal root, the other ``REQ_ENOUGH_MANA``, with ``COST > available mana >= DECK_ACTION_COST``: the
      unaffordable root is the normal play, so the legal one is the Prepare action (42 of 42 chosen);
    * one legal root without targets, the other ``REQ_TARGET_TO_PLAY`` (the normal play of a spell that needs a target
      none exists for): the legal root is the Prepare action (1 of 1 chosen, 14 unchosen occurrences consistent);
    * both legal and exactly one of them lists targets: the root that needs a target is the normal play of a targeted
      spell and the target-free root is the Prepare action (16 of 16 chosen).

    Everything else (for example both legal minion roots, which only differ by their order) is refused.
    """
    legal = [o for o in roots if o.error is None]
    if not legal:
        return {}
    has_targets = [any(item.optype == "target" and item.error is None for item in o.options) for o in legal]
    if any(item.optype == "subOption" for o in roots for item in o.options):
        raise ActionMappingError("AMBIGUOUS_SELECTION")
    if len(legal) == 1:
        blocked = next(o for o in roots if o.error is not None)
        reason = _error_name(blocked)
        if reason == "REQ_TARGET_TO_PLAY" and not has_targets[0]:
            return {legal[0].id: PREPARE_ROLE}
        cost = _tag_int(entity, GameTag.COST)
        deck_action_cost = _tag_int(entity, GameTag.DECK_ACTION_COST)
        if (reason == "REQ_ENOUGH_MANA" and not has_targets[0] and None not in (cost, deck_action_cost)
                and cost > state.self_player.available_mana >= deck_action_cost):
            return {legal[0].id: PREPARE_ROLE}
        raise ActionMappingError("AMBIGUOUS_SELECTION")
    if sorted(has_targets) != [False, True]:
        raise ActionMappingError("AMBIGUOUS_SELECTION")
    return {o.id: PLAY_ROLE if targeted else PREPARE_ROLE for o, targeted in zip(legal, has_targets)}


def _prepare_roles(packet, game, state: GameState) -> dict[int, str]:
    """option id -> role for every legal root of a Prepare hand card (empty for menus without one)."""
    by_entity: dict[int, list] = {}
    for option in packet.options:
        if option.entity is not None:
            by_entity.setdefault(int(coerce_to_entity_id(option.entity)), []).append(option)
    roles: dict[int, str] = {}
    for handle, roots in by_entity.items():
        try:
            entity = game.find_entity_by_id(handle)
        except Exception:
            entity = None
        if entity is None or entity.zone != Zone.HAND or not entity.tags.get(GameTag.PREPARE):
            continue
        if len(roots) != 2 or entity.tags.get(GameTag.TRADEABLE):
            raise ActionMappingError("UNSUPPORTED_DECISION_KIND")
        roles.update(_classify_prepare_roots(state, entity, roots))
    return roles


def map_actions(packet, game, self_id: int, state: GameState, *, prepare_actions: bool = False) -> MatchActions:
    """Enumerate the whole supported MAIN_ACTION menu; never prune unknown options.

    ``prepare_actions`` (experimental, off by default) additionally maps the second root of a Prepare card to a
    ``PREPARE_CARD`` action. With it off, a Prepare card keeps being refused as ``AMBIGUOUS_SELECTION``.
    """
    actions, keys, sources = [], [], set()
    roles = _prepare_roles(packet, game, state) if prepare_actions else {}
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
        role = roles.get(option.id)
        if role is None and (handle in sources or all_sources[handle] != 1):
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
            kind = "PREPARE_CARD" if role == PREPARE_ROLE else "PLAY_CARD"
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
        if kind == "PREPARE_CARD" and targets:
            raise ActionMappingError("AMBIGUOUS_SELECTION")
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
