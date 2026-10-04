"""Convert JSON-like mappings to the simulator-independent domain schema."""

from typing import Any

from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity, LocationEntity
from manamind.domain.game_state import GameState, PlayerObservation


def _card(data: dict[str, Any] | None) -> CardFeatures | None:
    if data is None:
        return None
    return CardFeatures(
        card_id=str(data.get("card_id", data.get("id", "UNKNOWN_CARD"))),
        cost=data.get("cost"),
        attack=data.get("attack"),
        health=data.get("health"),
        durability=data.get("durability"),
        card_type=str(data.get("card_type", data.get("type", "UNKNOWN_TYPE"))).upper(),
        card_class=str(data.get("card_class", data.get("cardClass", "UNKNOWN_CLASS"))).upper(),
        race=data.get("race"),
        mechanics=tuple(str(item).upper() for item in data.get("mechanics", ())),
        current_cost=data.get("current_cost"),
        current_spell_damage=data.get("current_spell_damage"),
        prepare_used=data.get("prepare_used"),
        held_spell_progress=data.get("held_spell_progress"),
        trigger_remaining=data.get("trigger_remaining"),
        effect_turns_remaining=data.get("effect_turns_remaining"),
        freeze_turns_remaining=data.get("freeze_turns_remaining"),
        current_attack=data.get("current_attack"),
        current_health=data.get("current_health"),
        current_durability=data.get("current_durability"),
        shatter_fragment=data.get("shatter_fragment") or None,
        shatter_original_card_id=data.get("shatter_original_card_id") or None,
        shatter_partner_hand_position=(
            int(data["shatter_partner_hand_position"])
            if data.get("shatter_partner_hand_position") is not None
            and int(data["shatter_partner_hand_position"]) >= 0 else None
        ),
        prepare_locked=(bool(data["prepare_locked"]) if data.get("prepare_locked") is not None else None),
    )


def _board_entity(data: dict[str, Any]) -> BoardEntity:
    card_data = data.get("card", data)
    card = _card(card_data)
    if card is None:
        raise ValueError("A board entity must include card features")
    flag_names = (
        "taunt", "divine_shield", "stealth", "frozen", "silenced", "immune",
        "rush", "charge", "windfury", "lifesteal", "poisonous", "reborn",
        "dormant", "can_attack",
    )
    current_attack = int(data.get("current_attack", data.get("attack", card.attack or 0)))
    current_health = int(data.get("current_health", data.get("health", card.health or 0)))
    max_health = int(data.get("max_health", data.get("health", card.health or current_health)))
    return BoardEntity(
        card=card,
        current_attack=current_attack,
        current_health=current_health,
        max_health=max_health,
        board_position=int(data.get("board_position", 0)),
        **{name: bool(data.get(name, False)) for name in flag_names},
        **{name: None if data.get(name) is None else bool(data[name]) for name in (
            "cant_be_targeted_by_spells", "cant_be_targeted_by_hero_powers")},
    )


def _location_entity(data: dict[str, Any]) -> LocationEntity:
    card = _card(data.get("card", data))
    if card is None:
        raise ValueError("A Location must include card features")
    health = int(data.get("current_health", data.get("health", card.durability or 0)))
    return LocationEntity(
        card=card,
        current_health=health,
        max_health=int(data.get("max_health", card.durability or health)),
        board_position=int(data.get("board_position", 0)),
        on_cooldown=bool(data.get("on_cooldown", False)),
        can_activate=(None if data.get("can_activate") is None else bool(data["can_activate"])),
    )


def _player(data: dict[str, Any]) -> PlayerObservation:
    if "hero_health" not in data:
        raise ValueError("Each player must include hero_health")
    return PlayerObservation(
        hero_health=int(data.get("hero_health", 0)),
        armor=int(data.get("armor", 0)),
        hero_attack=int(data.get("hero_attack", 0)),
        hero_divine_shield=(None if data.get("hero_divine_shield") is None else bool(data["hero_divine_shield"])),
        max_mana=int(data.get("max_mana", 0)),
        available_mana=int(data.get("available_mana", 0)),
        overloaded_mana=int(data.get("overloaded_mana", 0)),
        pending_overload=int(data.get("pending_overload", 0)),
        deck_size=int(data.get("deck_size", 0)),
        hand_size=int(data.get("hand_size", 0)),
        fatigue=int(data.get("fatigue", 0)),
        secret_count=int(data.get("secret_count", 0)),
        spell_damage=int(data.get("spell_damage", 0)),
        spells_cast_this_turn=data.get("spells_cast_this_turn"),
        current_turn_minion_types_played=data.get("current_turn_minion_types_played"),
        previous_turn_minion_types_played=data.get("previous_turn_minion_types_played"),
        spell_discount=data.get("spell_discount"),
        demon_discount=data.get("demon_discount"),
        hero_freeze_turns_remaining=data.get("hero_freeze_turns_remaining"),
        active_effects=tuple(_card(item) for item in data.get("active_effects", ())),
        known_secrets=tuple(
            card for item in data.get("known_secrets", ())
            if (card := _card(item if isinstance(item, dict) else {"card_id": item})) is not None
        ),
        hero_power_ready=(
            None if data.get("hero_power_ready") is None
            else bool(data["hero_power_ready"])
        ),
        hero_frozen=(None if data.get("hero_frozen") is None else bool(data["hero_frozen"])),
        player_class=str(data.get("player_class", "UNKNOWN_CLASS")).upper(),
        weapon=_card(data.get("weapon")),
        hero_power=_card(data.get("hero_power")),
        board=tuple(_board_entity(item) for item in data.get("board", ())),
        locations=tuple(_location_entity(item) for item in data.get("locations", ())),
    )


def game_state_from_dict(data: dict[str, Any]) -> GameState:
    """Build a GameState from a JSON-decoded mapping."""
    for key in ("turn_number", "active_player", "self_player", "opponent"):
        if key not in data:
            raise ValueError(f"Game state is missing required field: {key}")
    self_hand = tuple(_card(item) for item in data.get("self_hand", ()))
    opponent_known_cards = tuple(_card(item) for item in data.get("opponent_known_cards", ()))
    if any(card is None for card in (*self_hand, *opponent_known_cards)):
        raise ValueError("Cards in known zones must be objects")

    return GameState(
        turn_number=int(data.get("turn_number", 0)),
        active_player=str(data["active_player"]).upper(),
        self_player=_player(data["self_player"]),
        opponent=_player(data["opponent"]),
        self_hand=self_hand,
        self_hand_known_count=data.get("self_hand_known_count"),
        opponent_known_cards=opponent_known_cards,
        pending_choice_owner=data.get("pending_choice_owner"),
        pending_choice_options=tuple(_card(item) for item in data.get("pending_choice_options", ())),
    )
