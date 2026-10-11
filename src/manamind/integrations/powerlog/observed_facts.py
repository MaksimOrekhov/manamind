"""SELF facts that ``GameState`` does not carry, read from the entity table at a decision point.

OBSERVATION-EXT-1a. The facts feed ``manamind.outcome`` through a side channel (``ObservedContext``); nothing here
touches ``GameState``, the encoder, ``state_hash`` or any checkpoint. The same function runs in LIVE (at every emitted
decision, over the packets applied so far) and in the offline re-extraction of completed matches (which replays the same
``LiveSession``), so a fact can never depend on an event after the decision.

What may be read. SELF's player tags, SELF's hero, SELF's own hand and SELF's own entities in play, plus ONE public
tag of the opponent: Divine Shield on the opponent's hero. Nothing else of the opponent is read, and the opponent's hand,
deck, secrets and set-aside zone are never looked at.

How an unset tag is read. A tag the log never set is 0 only if the whole history of the game was observed: a section that
began at turn 0 and was never rewound (``Coverage.COMPLETE``, the rule OBSERVATION-AUDIT-1 verified for progress tags). A
section that began in the middle of a game (reconnect dump) or was rewound by ``GAME_RESET`` does not support that
inference; a value that is positively logged is still a fact, an unset tag is ``None`` (unknown), never 0 / False.
After a rewind nothing is trusted: the entity table is rebuilt from a dump whose completeness has not been verified.

Spell Damage has two channels in the log: the minions' own ``SPELLPOWER`` tag and SELF's player aggregate
(``CURRENT_SPELLPOWER``, logged as ``CURRENT_SPELLPOWER_BASE``). Both must be zero for "no Spell Damage source seen".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hearthstone.enums import GameTag, Zone

from .visible_state import _integer

SCHEMA = 1

COMPLETE = "COMPLETE"            # section began at turn 0, never rewound: an unset tag is 0
PARTIAL_DUMP = "PARTIAL_DUMP"    # section began mid-game (reconnect dump): only logged values are known
RESET = "RESET"                  # a GAME_RESET rewound the table: nothing is trusted
NOT_STARTED = "NOT_STARTED"      # no CREATE_GAME applied yet

# Ruby Sanctum: the player flag plus the attached effect entity were audited together (OBSERVATION-AUDIT-1, 0 contradictions).
SANCTUM_EFFECT_CARD = "CATA_301e"

SPELL_DAMAGE_NONE_SEEN = "NONE_SEEN"
SPELL_DAMAGE_PRESENT = "PRESENT_UNVERIFIED"
SPELL_DAMAGE_UNKNOWN = "UNKNOWN"

# Same vocabulary as ``outcome.world.BODY_FLAGS`` (a test keeps the two in step).
KEYWORD_TAGS: dict[str, GameTag] = {
    "taunt": GameTag.TAUNT, "divine_shield": GameTag.DIVINE_SHIELD, "rush": GameTag.RUSH, "charge": GameTag.CHARGE,
    "windfury": GameTag.WINDFURY, "stealth": GameTag.STEALTH, "lifesteal": GameTag.LIFESTEAL,
    "poisonous": GameTag.POISONOUS, "reborn": GameTag.REBORN,
}


@dataclass(frozen=True)
class ObservationHistory:
    """How much of the game the entity table has seen (see the module docstring)."""

    created_turn: int | None
    resets: int = 0

    @property
    def coverage(self) -> str:
        if self.resets:
            return RESET
        if self.created_turn is None:
            return NOT_STARTED
        return COMPLETE if self.created_turn == 0 else PARTIAL_DUMP


@dataclass(frozen=True)
class HandCardFact:
    """One card of SELF's hand, at the position the player sees it (the index of ``GameState.self_hand``)."""

    position: int
    card_id: str
    keywords: tuple[str, ...] | None     # the instance's own keywords; None = not reliably known


@dataclass(frozen=True)
class ObservedFacts:
    """``None`` always means unknown; ``unknown`` maps a fact name to the reason it is unknown."""

    coverage: str
    self_hero_divine_shield: bool | None = None
    opponent_hero_divine_shield: bool | None = None
    healing_does_damage: bool | None = None
    healing_bonus: int | None = None
    spell_healing_doubled: bool | None = None
    all_healing_doubled: bool | None = None
    spell_damage_doubled: bool | None = None
    spell_damage_status: str = SPELL_DAMAGE_UNKNOWN
    spell_damage: int | None = None          # the largest Spell Damage reading of SELF; 0 only for NONE_SEEN
    hand: tuple[HandCardFact, ...] = ()
    unknown: dict[str, str] = field(default_factory=dict)
    schema: int = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "coverage": self.coverage,
            "self_hero_divine_shield": self.self_hero_divine_shield,
            "opponent_hero_divine_shield": self.opponent_hero_divine_shield,
            "healing_does_damage": self.healing_does_damage, "healing_bonus": self.healing_bonus,
            "spell_healing_doubled": self.spell_healing_doubled, "all_healing_doubled": self.all_healing_doubled,
            "spell_damage_doubled": self.spell_damage_doubled, "spell_damage_status": self.spell_damage_status,
            "spell_damage": self.spell_damage,
            "hand": [{"position": card.position, "card_id": card.card_id,
                      "keywords": None if card.keywords is None else list(card.keywords)} for card in self.hand],
            "unknown": dict(sorted(self.unknown.items())),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObservedFacts:
        if data.get("schema") != SCHEMA:
            raise ValueError(f"unsupported observed-facts schema {data.get('schema')!r}")
        hand = tuple(HandCardFact(row["position"], row["card_id"],
                                  None if row["keywords"] is None else tuple(row["keywords"]))
                     for row in data["hand"])
        return cls(
            coverage=data["coverage"], self_hero_divine_shield=data["self_hero_divine_shield"],
            opponent_hero_divine_shield=data["opponent_hero_divine_shield"],
            healing_does_damage=data["healing_does_damage"], healing_bonus=data["healing_bonus"],
            spell_healing_doubled=data["spell_healing_doubled"], all_healing_doubled=data["all_healing_doubled"],
            spell_damage_doubled=data["spell_damage_doubled"], spell_damage_status=data["spell_damage_status"],
            spell_damage=data["spell_damage"], hand=hand, unknown=dict(data["unknown"]))


class _Reader:
    """Tag access that knows whether an unset tag may be read as 0."""

    def __init__(self, coverage: str) -> None:
        self.coverage = coverage
        self.unknown: dict[str, str] = {}

    @property
    def unset_is_zero(self) -> bool:
        return self.coverage == COMPLETE

    def _why(self) -> str:
        return {RESET: "HISTORY_RESET", PARTIAL_DUMP: "HISTORY_PARTIAL"}.get(self.coverage, "HISTORY_NOT_STARTED")

    def flag(self, name: str, tags: dict, tag: GameTag) -> bool | None:
        """A strict 0/1 flag. Any other value is not interpreted."""
        if self.coverage == RESET:
            self.unknown[name] = "HISTORY_RESET"
            return None
        if tag in tags:
            value = tags[tag]
            if isinstance(value, bool) or value in (0, 1):
                return bool(value)
            self.unknown[name] = "UNEXPECTED_VALUE"
            return None
        if self.unset_is_zero:
            return False
        self.unknown[name] = self._why()
        return None

    def count(self, name: str, tags: dict, tag: GameTag) -> int | None:
        if self.coverage == RESET:
            self.unknown[name] = "HISTORY_RESET"
            return None
        if tag in tags:
            value = tags[tag]
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
            self.unknown[name] = "UNEXPECTED_VALUE"
            return None
        if self.unset_is_zero:
            return 0
        self.unknown[name] = self._why()
        return None


def _player(game, player_id: int):
    return next((p for p in game.players if p.tags.get(GameTag.PLAYER_ID) == player_id), None)


def _hero(game, player):
    hero_id = player.tags.get(GameTag.HERO_ENTITY)
    return game.find_entity_by_id(hero_id) if hero_id is not None else None


def extract_observed_facts(game, self_player_id: int, history: ObservationHistory, catalog=None) -> ObservedFacts:
    """Facts at the decision point, from the packets applied to ``game`` so far.

    ``catalog`` (optional) is used only for a consistency check of Spell Damage: a card of SELF in play that prints Spell
    Damage but carries no Spell Damage tag makes the Spell Damage unknown instead of zero.
    """
    coverage = history.coverage
    reader = _Reader(coverage)
    me = _player(game, self_player_id)
    opponent = next((p for p in game.players
                     if p.tags.get(GameTag.PLAYER_ID) not in (None, self_player_id)), None)
    if me is None or opponent is None or coverage == NOT_STARTED:
        reason = "HISTORY_NOT_STARTED" if coverage == NOT_STARTED else "PLAYER_MISSING"
        return ObservedFacts(coverage, unknown={"all": reason})

    # --- heroes (the only opponent entity read, and only one of its tags) --------------------------------------
    self_hero, opponent_hero = _hero(game, me), _hero(game, opponent)
    shield = {}
    for name, hero in (("self_hero_divine_shield", self_hero), ("opponent_hero_divine_shield", opponent_hero)):
        if hero is None or hero.zone != Zone.PLAY:
            reader.unknown[name] = "HERO_MISSING"
            shield[name] = None
        else:
            shield[name] = reader.flag(name, hero.tags, GameTag.DIVINE_SHIELD)

    # --- Ruby Sanctum -------------------------------------------------------------------------------------------
    flag = reader.flag("healing_does_damage", me.tags, GameTag.HEALING_DOES_DAMAGE)
    effects = [e for e in game.entities if getattr(e, "card_id", None) == SANCTUM_EFFECT_CARD
               and e.zone == Zone.PLAY and e.tags.get(GameTag.ATTACHED) == me.id]
    sanctum: bool | None = None
    if flag is True and effects:
        sanctum = True
    elif flag is False and not effects:
        sanctum = False
    elif flag is not None:
        reader.unknown["healing_does_damage"] = "FLAG_EFFECT_DISAGREE"

    # --- healing ------------------------------------------------------------------------------------------------
    bonus = reader.count("healing_bonus", me.tags, GameTag.CURRENT_HEALING_POWER)
    spell_heal_double = reader.flag("spell_healing_doubled", me.tags, GameTag.SPELL_HEALING_DOUBLE)
    all_heal_double = reader.flag("all_healing_doubled", me.tags, GameTag.ALL_HEALING_DOUBLE)
    spell_dmg_double = reader.flag("spell_damage_doubled", me.tags, GameTag.SPELLPOWER_DOUBLE)

    # --- Spell Damage (SELF's entities in play), the hand --------------------------------------------------------
    in_play = [e for e in game.entities if getattr(e, "card_id", None) and e.zone == Zone.PLAY and e.controller == me]
    hand_entities = [e for e in game.entities if e.zone == Zone.HAND and e.controller == me]
    hand_entities.sort(key=lambda e: (_integer(e.tags.get(GameTag.ZONE_POSITION), 0), e.id))
    positive, inconsistent = [], False
    for entity in in_play:
        values = [entity.tags.get(GameTag.SPELLPOWER), entity.tags.get(GameTag.CURRENT_SPELLPOWER)]
        top = max((v for v in values if isinstance(v, int)), default=None)
        if top is not None and top > 0:
            positive.append(top)
        elif top is None and catalog is not None and "SPELLPOWER" in catalog.get(entity.card_id).mechanics:
            inconsistent = True
    aggregate = me.tags.get(GameTag.CURRENT_SPELLPOWER)       # SELF's player-level total (logged as ..._BASE)
    if isinstance(aggregate, int) and aggregate > 0:
        positive.append(aggregate)
    status, spell_damage = SPELL_DAMAGE_UNKNOWN, None
    if coverage == RESET:
        reader.unknown["spell_damage"] = "HISTORY_RESET"
    elif positive:
        status, spell_damage = SPELL_DAMAGE_PRESENT, max(positive)
    elif coverage != COMPLETE:
        reader.unknown["spell_damage"] = reader._why()
    elif inconsistent:
        reader.unknown["spell_damage"] = "PRINTED_WITHOUT_TAG"
    else:
        status, spell_damage = SPELL_DAMAGE_NONE_SEEN, 0

    hand = []
    for position, entity in enumerate(e for e in hand_entities if e.card_id):
        if reader.unset_is_zero:
            keywords: tuple[str, ...] | None = tuple(sorted(name for name, tag in KEYWORD_TAGS.items()
                                                            if entity.tags.get(tag)))
        else:
            keywords = None
        hand.append(HandCardFact(position, entity.card_id, keywords))
    if hand and reader.coverage != COMPLETE:
        reader.unknown["hand_keywords"] = reader._why()

    return ObservedFacts(
        coverage=coverage, self_hero_divine_shield=shield["self_hero_divine_shield"],
        opponent_hero_divine_shield=shield["opponent_hero_divine_shield"], healing_does_damage=sanctum,
        healing_bonus=bonus, spell_healing_doubled=spell_heal_double, all_healing_doubled=all_heal_double,
        spell_damage_doubled=spell_dmg_double, spell_damage_status=status, spell_damage=spell_damage,
        hand=tuple(hand), unknown=dict(reader.unknown))
