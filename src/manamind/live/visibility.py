"""Exposure policy: what leaves the bridge.

Allowlist by (controller, zone, card type), default deny. Opponent HAND, DECK, SETASIDE
and SECRET contribute counts only, never identities, even when the raw log carries a
card id for them (including ``META_DATA Meta=OVERRIDE_HISTORY`` reveals). Entity ids
exist only in the ``decision`` side channel as action handles and never inside the
``GameState``.
"""

from __future__ import annotations

from dataclasses import replace

from hearthstone.enums import CardType, GameTag, Zone
from hslog.player import coerce_to_entity_id

from manamind.cards.catalog import CardCatalog
from manamind.domain.game_state import GameState
from manamind.integrations.powerlog.visible_state import to_visible_state

from .reducer import ReducerError
from .trust import Reason


def project_state(game, self_player_id: int, catalog: CardCatalog, *, parity_view: bool = False) -> GameState:
    """The sanitized GameState. ``parity_view`` reproduces the offline importer's exposure
    (revealed opponent hand cards, entity-order hand, no secret counts); tests only."""
    if parity_view:
        state = to_visible_state(game, self_player_id, catalog)
        if state is None:
            raise ReducerError(Reason.INVARIANT)
        return state
    state = to_visible_state(
        game, self_player_id, catalog,
        opponent_identity_policy="none",
        hand_order="zone_position",
    )
    if state is None:
        raise ReducerError(Reason.INVARIANT)  # not a running game with a current player

    secret_counts: dict[int, int] = {}
    for entity in game.entities:
        if entity.zone == Zone.SECRET:
            owner = entity.tags.get(GameTag.CONTROLLER)
            secret_counts[owner] = secret_counts.get(owner, 0) + 1
    opponent_id = next(
        (p.tags.get(GameTag.PLAYER_ID) for p in game.players
         if p.tags.get(GameTag.PLAYER_ID) not in (None, self_player_id)),
        None,
    )
    return replace(
        state,
        self_player=replace(state.self_player, secret_count=secret_counts.get(self_player_id, 0)),
        opponent=replace(state.opponent, secret_count=secret_counts.get(opponent_id, 0)),
    )


def _entity(game, entity_id):
    try:
        entity = game.find_entity_by_id(entity_id)
    except Exception:
        entity = None
    if entity is None:
        raise ReducerError(Reason.ENTITY_UNKNOWN)
    return entity


def _handle(game, entity_ref, self_player_id: int) -> dict:
    entity_id = int(coerce_to_entity_id(entity_ref))
    entity = _entity(game, entity_id)
    public = entity.tags.get(GameTag.CONTROLLER) == self_player_id or entity.zone == Zone.PLAY
    return {"handle": entity_id, "card_id": entity.card_id if public and entity.card_id else None}


def _kind(game, option) -> str:
    option_type = getattr(option.type, "name", "OPTION")
    if option_type == "END_TURN":
        return "END_TURN"
    if option.entity is None:
        return "OPTION"
    entity = _entity(game, int(coerce_to_entity_id(option.entity)))
    if entity.zone == Zone.HAND:
        return "PLAY_CARD"
    if entity.zone == Zone.PLAY:
        if entity.type == CardType.HERO_POWER:
            return "HERO_POWER"
        if entity.type == CardType.LOCATION:
            return "USE_LOCATION"
        if entity.type in (CardType.MINION, CardType.HERO, CardType.WEAPON):
            return "ATTACK"
    return "POWER"


def _is_end_turn(option) -> bool:
    return getattr(option.type, "name", None) == "END_TURN"


def has_named_option(options_packet) -> bool:
    """An option the server validated (error NONE)."""
    return any(option.error is None for option in options_packet.options)


def has_candidate_option(options_packet) -> bool:
    """A possible decision message: a validated option, or END_TURN.

    Real logs give END_TURN ``error=INVALID`` in every message, in the opponent's turn too, so
    its error cannot say whether it is legal. It is legal when the active player is SELF, which
    the session checks after the state is applied.
    """
    return has_named_option(options_packet) or any(_is_end_turn(o) for o in options_packet.options)


def option_controllers(game, options_packet) -> set[int]:
    """Controllers of the main entities of server-validated (error NONE) options.

    The server validates the local client's own options, so these entities are SELF's.
    """
    controllers: set[int] = set()
    for option in options_packet.options:
        if option.error is None and option.entity is not None:
            entity = _entity(game, int(coerce_to_entity_id(option.entity)))
            controllers.add(entity.tags.get(GameTag.CONTROLLER))
    return controllers


def build_decision(game, options_packet, self_player_id: int) -> dict:
    """The decision section: legal actions with the handles a later mapper needs."""
    legal = []
    for option in options_packet.options:
        if option.error is not None and not _is_end_turn(option):
            continue
        action = {"option_index": option.id, "kind": _kind(game, option)}
        if option.entity is not None:
            action["source"] = _handle(game, option.entity, self_player_id)
        targets, sub_options = [], []
        for item in option.options:
            if item.error is not None or item.entity is None:
                continue
            if item.optype == "subOption":
                sub_targets = [
                    _handle(game, t.entity, self_player_id)
                    for t in item.options if t.error is None and t.entity is not None
                ]
                sub_options.append({
                    "index": len(sub_options),
                    **_handle(game, item.entity, self_player_id),
                    "targets": sub_targets,
                })
            else:
                targets.append(_handle(game, item.entity, self_player_id))
        if targets:
            action["targets"] = targets
        if sub_options:
            action["sub_options"] = sub_options
        legal.append(action)
    return {"kind": "MAIN_ACTION", "options_id": options_packet.id, "legal": legal}
