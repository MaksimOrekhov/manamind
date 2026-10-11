"""Small builders for controlled, fully specified positions (demo and tests).

These construct synthetic ``GameState`` values from explicit numbers. Nothing here reads a log; a
scenario built here proves the arithmetic of the forecaster, never anything about real play.
"""

from __future__ import annotations

from typing import Any

from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity
from manamind.domain.game_state import GameState, PlayerObservation


def minion(card_id: str, attack: int, health: int, position: int, *, max_health: int | None = None,
           mechanics: tuple[str, ...] = (), **flags: Any) -> BoardEntity:
    card = CardFeatures(card_id=card_id, card_type="MINION", attack=attack, health=health, cost=1,
                        current_attack=attack, current_health=health, mechanics=mechanics)
    return BoardEntity(card=card, current_attack=attack, current_health=health,
                       max_health=health if max_health is None else max_health, board_position=position, **flags)


def hand_card(card_id: str, card_type: str, cost: int | None, *, attack: int | None = None,
              health: int | None = None, mechanics: tuple[str, ...] = ()) -> CardFeatures:
    return CardFeatures(card_id=card_id, card_type=card_type, cost=cost, current_cost=cost, attack=attack,
                        health=health, mechanics=mechanics)


def side(*, hero_health: int = 30, armor: int = 0, mana: int = 10, board: tuple[BoardEntity, ...] = (),
         hand_size: int = 0, secret_count: int = 0, spell_damage: int = 0, healing_bonus: int | None = 0,
         hero_max_health: int | None = 30, hero_divine_shield: bool | None = False,
         hero_power: CardFeatures | None = None, **extra: Any) -> PlayerObservation:
    return PlayerObservation(
        hero_health=hero_health, armor=armor, max_mana=10, available_mana=mana, board=board,
        hand_size=hand_size, secret_count=secret_count, spell_damage=spell_damage,
        healing_bonus=healing_bonus, hero_max_health=hero_max_health, hero_divine_shield=hero_divine_shield,
        hero_power=hero_power, hero_power_ready=True if hero_power else None, **extra)


def position(*, self_side: PlayerObservation, opponent: PlayerObservation,
             hand: tuple[CardFeatures, ...] = ()) -> GameState:
    return GameState(
        turn_number=6, active_player="SELF",
        self_player=PlayerObservation(**{**_fields(self_side), "hand_size": max(len(hand), self_side.hand_size)}),
        opponent=opponent, self_hand=hand)


def _fields(player: PlayerObservation) -> dict[str, Any]:
    from dataclasses import fields
    return {item.name: getattr(player, item.name) for item in fields(player)}


def play(card_id: str, hand_index: int, card_type: str, cost: int | None, target: dict[str, Any] | None = None,
         play_position: int = 0) -> dict[str, Any]:
    action: dict[str, Any] = {"type": "PLAY_CARD", "card_id": card_id, "card_type": card_type,
                              "source_kind": card_type, "source_card_id": card_id, "hand_index": hand_index,
                              "card_cost": cost, "play_position": play_position, "source_board_position": -1}
    action.update(target or {})
    return action


def target_minion(side_name: str, position_: int, card_id: str) -> dict[str, Any]:
    return {"target_kind": "MINION", "target_side": side_name, "target_card_id": card_id,
            "target_board_position": position_, "target_is_hero": False, "target_is_self": side_name == "SELF"}


def target_hero(side_name: str) -> dict[str, Any]:
    return {"target_kind": "HERO", "target_side": side_name, "target_card_id": "HERO",
            "target_board_position": -1, "target_is_hero": True, "target_is_self": side_name == "SELF"}


def end_turn() -> dict[str, Any]:
    return {"type": "END_TURN", "play_position": 0}


def attack(source_position: int, source_card_id: str, target: dict[str, Any]) -> dict[str, Any]:
    return {"type": "ATTACK", "source_kind": "MINION", "source_card_id": source_card_id,
            "source_board_position": source_position, "source_is_hero": False, "card_id": source_card_id,
            "play_position": 0, **target}


def hero_power(card_id: str, cost: int, target: dict[str, Any] | None = None) -> dict[str, Any]:
    action = {"type": "HERO_POWER", "card_id": card_id, "source_card_id": card_id, "source_kind": "HERO_POWER",
              "card_cost": cost, "play_position": 0, "source_board_position": -1}
    action.update(target or {})
    return action
