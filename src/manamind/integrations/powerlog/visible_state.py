"""Project the entities of a parsed Power.log game into the player-visible ``GameState``.

Shared by the offline importer and the live bridge. Behavior is unchanged from the
original ``scripts/import_power_log.py`` helpers except for the explicit
``opponent_identity_policy`` switch.
"""

from __future__ import annotations

from typing import Literal

from hearthstone.enums import CardType, GameTag, State, Zone

from manamind.cards.catalog import CardCatalog
from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity, LocationEntity
from manamind.domain.game_state import GameState, PlayerObservation

OpponentIdentityPolicy = Literal["revealed", "none"]


def infer_local_player_id(game) -> int:
    """Identify the client side from visible identities in the initial hands."""
    scores: dict[int, int] = {}
    for player in game.players:
        player_id = player.tags.get(GameTag.PLAYER_ID)
        if player_id is None:
            continue
        scores[player_id] = sum(
            1 for entity in game.entities
            if entity.zone == Zone.HAND
            and entity.controller == player
            and bool(entity.card_id)
        )
    if not scores:
        raise ValueError("could not identify the local player from visible hand cards")
    best = max(scores.values())
    winners = [player_id for player_id, score in scores.items() if score == best]
    if best == 0 or len(winners) != 1:
        raise ValueError("local player perspective is ambiguous; no data was written")
    return winners[0]


def find_player(game, player_id):
    for player in game.players:
        if player.tags.get(GameTag.PLAYER_ID) == player_id:
            return player
    return None


def to_visible_state(
    game,
    self_player_id: int,
    catalog: CardCatalog,
    *,
    opponent_identity_policy: OpponentIdentityPolicy = "revealed",
) -> GameState | None:
    turn_number = _integer(game.tags.get(GameTag.TURN), 0)
    if turn_number < 1 or game.tags.get(GameTag.STATE) != State.RUNNING:
        return None

    player_by_id = {
        player.tags.get(GameTag.PLAYER_ID): player
        for player in game.players
        if player.tags.get(GameTag.PLAYER_ID) is not None
    }
    opponent_player_id = next(
        (player_id for player_id in player_by_id if player_id != self_player_id), None
    )
    self_player = player_by_id.get(self_player_id)
    opponent_player = player_by_id.get(opponent_player_id)
    active_player = game.current_player
    if self_player is None or opponent_player is None or active_player is None:
        return None

    entities = list(game.entities)
    self_observation, self_hand = _player_observation(
        self_player, entities, catalog, is_self=True,
    )
    opponent_observation, opponent_hand = _player_observation(
        opponent_player, entities, catalog, is_self=False,
    )
    if opponent_identity_policy == "none":
        # Live boundary: no opponent hand identity, even if the log carries one.
        opponent_hand = []

    # Policy "revealed": Power.log is the local client's view, so card IDs in the
    # opposing hand are known/revealed to that client (offline training rows).
    return GameState(
        turn_number=turn_number,
        active_player=("SELF" if active_player == self_player else "OPPONENT"),
        self_player=self_observation,
        opponent=opponent_observation,
        self_hand=tuple(self_hand),
        self_hand_known_count=len(self_hand),
        opponent_known_cards=tuple(opponent_hand),
    )


def _player_observation(player, entities, catalog, *, is_self: bool):
    controlled = [entity for entity in entities if entity.controller == player]
    hero_id = player.tags.get(GameTag.HERO_ENTITY)
    hero = next((entity for entity in controlled if entity.id == hero_id), None)
    hero_card = _card_features(hero, catalog) if hero is not None else CardFeatures()

    hand_entities = [
        entity for entity in controlled if entity.zone == Zone.HAND
    ]
    hand_cards = _visible_hand_cards(hand_entities, catalog, is_self=is_self)

    board_entities = sorted(
        (
            entity for entity in controlled
            if entity.zone == Zone.PLAY and entity.type == CardType.MINION
        ),
        key=lambda entity: (
            _integer(entity.tags.get(GameTag.ZONE_POSITION), 0), entity.id
        ),
    )
    board = tuple(
        _board_entity(entity, position, catalog)
        for position, entity in enumerate(board_entities)
    )
    locations_entities = sorted(
        (entity for entity in controlled
         if entity.zone == Zone.PLAY and entity.type == CardType.LOCATION),
        key=lambda entity: (
            _integer(entity.tags.get(GameTag.ZONE_POSITION), 0), entity.id
        ),
    )
    locations = tuple(
        _location_entity(entity, catalog) for entity in locations_entities
    )
    weapon_entity = next(
        (entity for entity in controlled
         if entity.zone == Zone.PLAY and entity.type == CardType.WEAPON),
        None,
    )
    hero_power_entity = next(
        (entity for entity in controlled
         if entity.zone == Zone.PLAY and entity.type == CardType.HERO_POWER),
        None,
    )
    hero_power_ready = (
        None if hero_power_entity is None or GameTag.EXHAUSTED not in hero_power_entity.tags
        else not bool(hero_power_entity.tags[GameTag.EXHAUSTED])
    )

    max_mana, available_mana, locked = _mana_values(player.tags)
    armor = _integer(hero.tags.get(GameTag.ARMOR), 0) if hero else 0

    player_class = hero_card.card_class
    if player_class == "UNKNOWN_CLASS":
        player_class = _enum_tag_name(hero.tags.get(GameTag.CLASS)) if hero else "UNKNOWN_CLASS"

    observation = PlayerObservation(
        hero_health=_current_health(hero),
        armor=armor,
        hero_attack=_integer(hero.tags.get(GameTag.ATK), 0) if hero else 0,
        max_mana=max_mana,
        available_mana=available_mana,
        overloaded_mana=locked,
        pending_overload=_integer(player.tags.get(GameTag.OVERLOAD_OWED), 0),
        deck_size=sum(1 for entity in controlled if entity.zone == Zone.DECK),
        hand_size=len(hand_entities),
        fatigue=_integer(player.tags.get(GameTag.FATIGUE), 0),
        hero_power_ready=hero_power_ready,
        hero_divine_shield=(bool(hero.tags[GameTag.DIVINE_SHIELD]) if hero and GameTag.DIVINE_SHIELD in hero.tags else None),
        player_class=player_class,
        weapon=_card_features(weapon_entity, catalog) if weapon_entity else None,
        hero_power=_card_features(hero_power_entity, catalog) if hero_power_entity else None,
        board=board,
        locations=locations,
    )
    return observation, hand_cards


def _board_entity(entity, position: int, catalog: CardCatalog) -> BoardEntity:
    tags = entity.tags
    attack = _integer(tags.get(GameTag.ATK), 0)
    current_health = _current_health(entity)
    windfury = bool(tags.get(GameTag.WINDFURY, 0))
    attacks_made = _integer(tags.get(GameTag.NUM_ATTACKS_THIS_TURN), 0)
    can_attack = (
        attack > 0
        and not bool(tags.get(GameTag.EXHAUSTED, 0))
        and not bool(tags.get(GameTag.FROZEN, 0))
        and not bool(tags.get(GameTag.CANT_ATTACK, 0))
        and attacks_made < (2 if windfury else 1)
    )
    return BoardEntity(
        card=_card_features(entity, catalog),
        current_attack=attack,
        current_health=current_health,
        max_health=max(current_health, _integer(tags.get(GameTag.HEALTH), current_health)),
        board_position=_integer(tags.get(GameTag.ZONE_POSITION), position),
        taunt=bool(tags.get(GameTag.TAUNT, 0)),
        divine_shield=bool(tags.get(GameTag.DIVINE_SHIELD, 0)),
        stealth=bool(tags.get(GameTag.STEALTH, 0)),
        frozen=bool(tags.get(GameTag.FROZEN, 0)),
        silenced=bool(tags.get(GameTag.SILENCED, 0)),
        immune=bool(tags.get(GameTag.IMMUNE, 0)),
        rush=bool(tags.get(GameTag.RUSH, 0)),
        charge=bool(tags.get(GameTag.CHARGE, 0)),
        windfury=windfury,
        lifesteal=bool(tags.get(GameTag.LIFESTEAL, 0)),
        poisonous=bool(tags.get(GameTag.POISONOUS, 0)),
        reborn=bool(tags.get(GameTag.REBORN, 0)),
        dormant=bool(tags.get(GameTag.DORMANT, 0)),
        can_attack=can_attack,
        cant_be_targeted_by_spells=(bool(tags[GameTag.CANT_BE_TARGETED_BY_SPELLS]) if GameTag.CANT_BE_TARGETED_BY_SPELLS in tags else None),
        cant_be_targeted_by_hero_powers=(bool(tags[GameTag.CANT_BE_TARGETED_BY_HERO_POWERS]) if GameTag.CANT_BE_TARGETED_BY_HERO_POWERS in tags else None),
    )


def _location_entity(entity, catalog: CardCatalog) -> LocationEntity:
    tags = entity.tags
    health = _current_health(entity)
    cooldown = bool(tags.get(GameTag.LOCATION_ACTION_COOLDOWN, 0))
    return LocationEntity(
        card=_card_features(entity, catalog),
        current_health=health,
        max_health=max(health, _integer(tags.get(GameTag.HEALTH), health)),
        board_position=_integer(tags.get(GameTag.ZONE_POSITION), 0),
        on_cooldown=cooldown,
        # Power.log gives cooldown but not the engine's full turn/card-requirement predicate.
        can_activate=None,
    )


def _card_features(entity, catalog: CardCatalog) -> CardFeatures:
    if entity is None:
        return CardFeatures()
    base = catalog.get(entity.card_id or "UNKNOWN_CARD")
    tags = entity.tags
    card_type = entity.type.name
    if card_type in {"INVALID", "BLANK"}:
        card_type = base.card_type
    return CardFeatures(
        card_id=entity.card_id or "UNKNOWN_CARD",
        cost=base.cost,
        attack=(
            base.attack if base.attack is not None
            else _optional_int(tags.get(GameTag.ATK), None)
        ),
        health=(
            base.health if base.health is not None
            else _optional_int(tags.get(GameTag.HEALTH), None)
        ),
        durability=base.durability,
        current_cost=_optional_int(tags.get(GameTag.COST), None),
        current_attack=(_optional_int(tags.get(GameTag.ATK), None) if card_type in {"MINION", "WEAPON"} else None),
        current_health=(_current_health(entity) if GameTag.HEALTH in tags and card_type in {"MINION", "LOCATION"} else None),
        current_durability=(
            _current_weapon_durability(entity) if card_type == "WEAPON" else None
        ),
        card_type=card_type,
        card_class=base.card_class,
        race=base.race,
        mechanics=base.mechanics,
    )


def _visible_hand_cards(hand_entities, catalog: CardCatalog, *, is_self: bool):
    """Keep own hand identities and only currently revealed opponent identities."""
    return [
        _card_features(entity, catalog)
        for entity in hand_entities
        if entity.card_id and (is_self or entity.revealed)
    ]


def _mana_values(tags) -> tuple[int, int, int]:
    """Return total crystals, currently spendable mana, and locked overload."""
    total_mana = _integer(tags.get(GameTag.RESOURCES), 0)
    temporary = _integer(tags.get(GameTag.TEMP_RESOURCES), 0)
    used = _integer(tags.get(GameTag.RESOURCES_USED), 0)
    locked = _integer(tags.get(GameTag.OVERLOAD_LOCKED), 0)
    available = max(0, total_mana + temporary - used - locked)
    return total_mana, available, locked


def _current_health(entity) -> int:
    if entity is None:
        return 0
    maximum = _integer(entity.tags.get(GameTag.HEALTH), 0)
    damage = _integer(entity.tags.get(GameTag.DAMAGE), 0)
    return max(0, maximum - damage)


def _current_weapon_durability(entity) -> int | None:
    """Read current weapon durability from real Power.log health/damage tags.

    Older or synthetic inputs may provide only the explicit DURABILITY tag.
    Catalog durability is base metadata and is not a current instance value.
    """
    if entity is None:
        return None
    tags = entity.tags
    if GameTag.HEALTH in tags:
        health = _integer(tags.get(GameTag.HEALTH), 0)
        damage = _integer(tags.get(GameTag.DAMAGE), 0)
        return max(0, health - damage)
    return _optional_int(tags.get(GameTag.DURABILITY), None)


def _integer(value, fallback: int) -> int:
    try:
        return max(0, int(value)) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _optional_int(value, fallback: int | None) -> int | None:
    return _integer(value, fallback) if value is not None else fallback


def _enum_tag_name(value) -> str:
    return getattr(value, "name", "UNKNOWN_CLASS")
