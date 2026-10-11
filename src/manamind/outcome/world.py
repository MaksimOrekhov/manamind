"""A mutable working copy of the visible position and the resolution primitives.

``World`` is built from a ``GameState`` that it never modifies. Primitives (damage, healing,
stat changes, keyword grants, destruction) mutate the copy in resolution order and append events;
the net difference to the original becomes the change list. Where a needed value is not observed
the primitive records an ``Unknown`` and leaves that field untouched instead of inventing a value.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity, LocationEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.outcome.model import Change, Event, Ref, Unknown, UnknownKind

_ENTITY_FIELDS = (
    "attack", "health", "max_health", "taunt", "divine_shield", "stealth", "frozen", "silenced",
    "immune", "rush", "charge", "windfury", "lifesteal", "poisonous", "reborn", "dormant", "can_attack",
)
_LOCATION_FIELDS = ("health", "max_health", "on_cooldown", "can_activate")


class Unsupported(Exception):
    """The action or an effect on it is outside the modelled rules; no forecast is produced."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ObservedContext:
    """Facts that the player-visible ``GameState`` does not carry but a caller may observe.

    ``None`` means "not observed": the forecaster then reports the dependent value as unknown.
    The ``assume_*`` and ``hand_keywords_match_card`` switches let a caller vouch for a default
    explicitly (a what-if, recorded in the forecast's assumptions); nothing assumes them silently.
    """

    healing_does_damage: bool | None = None
    # Spell Damage: ``spell_damage`` is SELF's bonus and ``spell_damage_doubled`` whether SELF's spell damage is
    # doubled (Power.log flag SPELLPOWER_DOUBLE). ``trust_spell_damage`` vouches that the value in GameState is
    # real and that nothing doubles it.
    spell_damage: int | None = None
    spell_damage_doubled: bool | None = None
    trust_spell_damage: bool = False
    # Healing: SELF's additive bonus (CURRENT_HEALING_POWER) and whether SELF's spell healing is doubled
    # (SPELL_HEALING_DOUBLE); both only matter when GameState carries no healing_bonus.
    healing_bonus: int | None = None
    spell_healing_doubled: bool | None = None
    self_hero_divine_shield: bool | None = None
    opponent_hero_divine_shield: bool | None = None
    # Keyword flags of each card in SELF's hand, aligned with ``GameState.self_hand`` (None: not observed).
    hand_keywords: tuple[frozenset[str] | None, ...] | None = None
    hand_keywords_match_card: bool = False
    assume_no_hero_divine_shield: bool = False
    assume_zero_healing_bonus: bool = False

    @classmethod
    def assuming_common_defaults(cls) -> "ObservedContext":
        return cls(healing_does_damage=False, trust_spell_damage=True, spell_healing_doubled=False,
                   hand_keywords_match_card=True, assume_no_hero_divine_shield=True, assume_zero_healing_bonus=True)


class Obj:
    """A bag of tracked fields with their pre-action values and the cause of each write."""

    def __init__(self, ref: Ref, fields: dict[str, Any]) -> None:
        self.ref = ref
        self.fields = dict(fields)
        self.original = dict(fields)
        self.causes: dict[str, str] = {}
        self.roles: dict[str, str] = {}
        self.unknown_fields: dict[str, tuple[str, int | None, int | None]] = {}

    def set(self, name: str, value: Any, cause: str, role: str = "EFFECT") -> None:
        self.fields[name] = value
        self.causes[name] = cause
        self.roles[name] = role

    def mark_unknown(self, name: str, cause: str, at_least: int | None = None, at_most: int | None = None,
                     role: str = "EFFECT") -> None:
        """The field was touched but its value is not determined; the bound, if any, is all that is known."""
        self.unknown_fields[name] = (cause, at_least, at_most)
        self.roles[name] = role

    def changes(self) -> list[Change]:
        found = [Change(self.ref, name, self.original[name], value, self.causes.get(name, "?"),
                        role=self.roles.get(name, "EFFECT"))
                 for name, value in self.fields.items()
                 if value != self.original[name] and name not in self.unknown_fields]
        found += [Change(self.ref, name, self.original[name], None, cause, low, high,
                         role=self.roles.get(name, "EFFECT"))
                  for name, (cause, low, high) in self.unknown_fields.items()]
        return found


class Ent(Obj):
    def __init__(self, ref: Ref, fields: dict[str, Any], card: CardFeatures, new: bool = False,
                 extra: dict[str, Any] | None = None) -> None:
        super().__init__(ref, fields)
        self.card = card
        self.new = new
        self.extra = extra or {}
        self.destroyed = False
        self.dead = False
        self.sort_key = float(ref.position or 0) - (0.5 if new else 0.0)

    @property
    def side(self) -> str:
        return self.ref.side

    @property
    def is_location(self) -> bool:
        return self.ref.zone == "LOCATION"

    @property
    def is_hero(self) -> bool:
        return False


class HeroObj(Obj):
    @property
    def side(self) -> str:
        return self.ref.side

    @property
    def is_hero(self) -> bool:
        return True


# Keyword flags that a card's printed mechanics give back to a minion that is returned by Reborn.
BODY_FLAGS = {"TAUNT": "taunt", "DIVINE_SHIELD": "divine_shield", "RUSH": "rush", "CHARGE": "charge",
              "WINDFURY": "windfury", "STEALTH": "stealth", "LIFESTEAL": "lifesteal",
              "POISONOUS": "poisonous", "REBORN": "reborn"}


class World:
    def __init__(self, state: GameState, context: ObservedContext, texts: Any = None) -> None:
        self.state = state
        self.context = context
        self.texts = texts
        self.events: list[Event] = []
        self.unknowns: list[Unknown] = []
        self.assumptions: list[str] = []
        self.rules: list[str] = []
        self.heroes: dict[str, HeroObj] = {}
        self.players: dict[str, Obj] = {}
        self.weapons: dict[str, Obj | None] = {}
        self.entities: list[Ent] = []
        self.healing_bonus: dict[str, int | None] = {}
        self.spell_damage: dict[str, int] = {}
        self.hand_removed: list[Ref] = []
        # (side, zone, pre-action position) -> index in the same side's board / Location tuple of the result
        self.after_index: dict[tuple[str, str, int], int] = {}
        self._flagged: set[tuple[str, str]] = set()
        for side, player in (("SELF", state.self_player), ("OPPONENT", state.opponent)):
            self._load_side(side, player)

    def _load_side(self, side: str, player: PlayerObservation) -> None:
        self.heroes[side] = HeroObj(Ref(side, "HERO", None, "HERO"), {
            "health": player.hero_health, "max_health": player.hero_max_health, "armor": player.armor,
            "attack": player.hero_attack,
            "divine_shield": (player.hero_divine_shield if player.hero_divine_shield is not None
                              else self.context.self_hero_divine_shield if side == "SELF"
                              else self.context.opponent_hero_divine_shield),
            "hero_power_ready": player.hero_power_ready,
        })
        self.players[side] = Obj(Ref(side, "PLAYER", None, "PLAYER"), {
            "available_mana": player.available_mana, "hand_size": player.hand_size,
        })
        weapon = player.weapon
        self.weapons[side] = None if weapon is None else Obj(
            Ref(side, "WEAPON", None, weapon.card_id), {"durability": weapon.effective_durability})
        self.healing_bonus[side] = (player.healing_bonus if player.healing_bonus is not None
                                    else self.context.healing_bonus if side == "SELF" else None)
        self.spell_damage[side] = player.spell_damage
        for item in player.board:
            fields = {name: getattr(item, "current_" + name if name in ("attack", "health") else name)
                      for name in _ENTITY_FIELDS}
            extra = {"cant_be_targeted_by_spells": item.cant_be_targeted_by_spells,
                     "cant_be_targeted_by_hero_powers": item.cant_be_targeted_by_hero_powers}
            self.entities.append(
                Ent(Ref(side, "BOARD", item.board_position, item.card.card_id), fields, item.card, extra=extra))
        for place in player.locations:
            fields = {"health": place.current_health, "max_health": place.max_health,
                      "on_cooldown": place.on_cooldown, "can_activate": place.can_activate}
            self.entities.append(Ent(Ref(side, "LOCATION", place.board_position, place.card.card_id), fields, place.card))

    # ----- lookup ---------------------------------------------------------------------------

    def hero(self, side: str) -> HeroObj:
        return self.heroes[side]

    def find(self, side: str, zone: str, position: int, card_id: str) -> Ent:
        hits = [e for e in self.entities
                if e.side == side and e.ref.zone == zone and e.ref.position == position and not e.new]
        if len(hits) != 1 or hits[0].ref.card_id != card_id:
            raise Unsupported("TARGET_UNRESOLVED")
        return hits[0]

    def minions(self, side: str | None = None) -> list[Ent]:
        return [e for e in self.entities if e.ref.zone == "BOARD" and not e.dead
                and (side is None or e.side == side)]

    def other_side(self, side: str) -> str:
        return "OPPONENT" if side == "SELF" else "SELF"

    # ----- bookkeeping ------------------------------------------------------------------------

    def event(self, kind: str, subject: Ref | None, amount: int | None, note: str) -> None:
        self.events.append(Event(kind, subject, amount, note))

    def unknown(self, kind: UnknownKind, detail: str, subject: Ref | None = None,
                alters: bool = True, adds: bool = True, tag: str = "") -> None:
        key = (kind.value, detail)
        if key not in self._flagged:
            self._flagged.add(key)
            self.unknowns.append(Unknown(kind, detail, subject, alters, adds, tag))

    def note_rule(self, rule: str) -> None:
        if rule not in self.rules:
            self.rules.append(rule)

    # ----- primitives -------------------------------------------------------------------------

    def damage(self, target: Obj, amount: int, cause: str, *, lifesteal_side: str | None = None,
               poisonous: bool = False, at_least: bool = False) -> int:
        """Resolve one damage packet; returns the damage dealt (for Lifesteal), 0 if prevented.

        ``at_least`` says the real amount may be larger than ``amount`` (an unobserved Spell Damage bonus):
        prevention by Divine Shield or Immune is still exact and a lethal packet stays lethal, but
        remaining Health, Armor and what Lifesteal returns are then only bounds.
        """
        self.note_rule("DAMAGE_PACKET")
        if amount <= 0:
            self.event("DAMAGE", target.ref, 0, f"{cause}: no damage")
            return 0
        if target.is_hero:
            shield = target.fields["divine_shield"]
            if shield is None and self.context.assume_no_hero_divine_shield:
                shield = False
                self.assumptions.append(f"{target.ref.side} hero has no Divine Shield (not observed)")
            if shield is None:
                self.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                             f"{target.ref.side} hero Divine Shield state is not observed", target.ref,
                             tag="HERO_SHIELD_UNOBSERVED")
                target.mark_unknown("health", cause)
                target.mark_unknown("armor", cause)
                return 0
            if shield:
                target.set("divine_shield", False, cause)
                self.event("DAMAGE", target.ref, 0, f"{cause}: hero Divine Shield absorbed {amount}")
                return 0
            absorbed = min(target.fields["armor"], amount)
            if at_least:
                target.mark_unknown("armor", cause, at_most=target.fields["armor"] - absorbed)
                target.mark_unknown("health", cause, at_most=target.fields["health"] - (amount - absorbed))
            else:
                target.set("armor", target.fields["armor"] - absorbed, cause)
                target.set("health", target.fields["health"] - (amount - absorbed), cause)
            self.event("DAMAGE", target.ref, amount, f"{cause}: {absorbed} absorbed by armor")
            dealt = amount
        else:
            if target.fields["immune"]:
                self.event("DAMAGE", target.ref, 0, f"{cause}: Immune, no damage")
                return 0
            if target.fields["divine_shield"]:
                target.set("divine_shield", False, cause)
                self.event("DAMAGE", target.ref, 0, f"{cause}: Divine Shield absorbed {amount}, no health lost")
                return 0
            if at_least:
                target.mark_unknown("health", cause, at_most=target.fields["health"] - amount)
                target.destroyed = target.destroyed or target.fields["health"] - amount <= 0
            else:
                target.set("health", target.fields["health"] - amount, cause)
            if poisonous:
                target.destroyed = True
            self.event("DAMAGE", target.ref, amount, f"{cause}: {amount} damage")
            dealt = amount
        if lifesteal_side is not None and dealt > 0:
            self.heal(self.hero(lifesteal_side), dealt, lifesteal_side, f"Lifesteal ({cause})", lifesteal=True)
        return dealt

    def heal(self, target: Obj, base: int, healer_side: str, cause: str, *, lifesteal: bool = False,
             at_least: bool = False, spell: bool = False, unverified_double: bool = False) -> None:
        """One healing packet. ``spell`` heals are doubled when SELF's spell healing is (verified in logs);
        a non-spell heal under a doubling flag is only a lower bound, because that case has no sample yet."""
        self.note_rule("HEALING_PACKET")
        factor = 1
        if spell:
            doubled = self.context.spell_healing_doubled
            if doubled is None:
                at_least = True
                self.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                             "whether SELF's spell healing is doubled is not observed; healing is a lower bound",
                             target.ref, adds=False, tag="HEALING_DOUBLING_UNOBSERVED")
            elif doubled:
                factor = 2
        elif unverified_double:
            at_least = True
            self.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                         "spell healing is doubled and this heal is not a spell: the effect on it is unverified",
                         target.ref, adds=False, tag="HEALING_DOUBLING_UNVERIFIED")
        if self.context.healing_does_damage is None:
            self.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                         "healing-to-damage conversion (Ruby Sanctum) is not exposed by GameState", target.ref,
                         adds=False, tag="SANCTUM_UNOBSERVED")
        elif self.context.healing_does_damage:
            raise Unsupported("HEALING_DOES_DAMAGE_ACTIVE")
        bonus = self.healing_bonus[healer_side]
        if bonus is None and self.context.assume_zero_healing_bonus:
            bonus = 0
            self.assumptions.append(f"{healer_side} healing bonus is 0 (not observed)")
        missing = None if target.fields["max_health"] is None else (
            target.fields["max_health"] - target.fields["health"])
        if bonus is None or missing is None:
            what = "healing bonus" if bonus is None else f"{target.ref.side} hero maximum Health"
            self.unknown(UnknownKind.MODIFIER_UNOBSERVED, f"{healer_side} {what} is not observed", target.ref,
                         adds=False, tag="HEALING_BONUS_UNOBSERVED" if bonus is None else "HERO_MAX_HEALTH_UNOBSERVED")
            target.mark_unknown("health", cause, at_least=target.fields["health"])
            self.event("HEAL", target.ref, None, f"{cause}: amount unknown (base {base})")
            return
        restored = max(0, min((base + bonus) * factor, missing))
        if at_least:                          # the healed amount comes from damage that may be larger
            target.mark_unknown("health", cause, at_least=target.fields["health"] + restored)
            self.event("HEAL", target.ref, None, f"{cause}: restores at least {restored}")
            return
        target.set("health", target.fields["health"] + restored, cause)
        self.event("HEAL", target.ref, restored,
                   f"{cause}: restores {restored} (base {base}, bonus {bonus}"
                   f"{', doubled' if factor == 2 else ''}, missing {missing})")

    def buff(self, target: Ent, attack: int, health: int, cause: str) -> None:
        self.note_rule("STAT_CHANGE")
        if target.is_location:
            raise Unsupported("BUFF_ON_LOCATION")
        if attack:
            target.set("attack", target.fields["attack"] + attack, cause)
        if health:
            target.set("health", target.fields["health"] + health, cause)
            target.set("max_health", target.fields["max_health"] + health, cause)
        self.event("BUFF", target.ref, None, f"{cause}: +{attack}/+{health}")

    def grant(self, target: Ent, keyword: str, cause: str) -> None:
        self.note_rule("KEYWORD_GRANT")
        if target.fields.get(keyword):
            self.event("KEYWORD_GAIN", target.ref, 0, f"{cause}: already has {keyword}, nothing changes")
            return
        target.set(keyword, True, cause)
        self.event("KEYWORD_GAIN", target.ref, 1, f"{cause}: gains {keyword}")

    def destroy(self, target: Ent, cause: str) -> None:
        self.note_rule("DESTROY")
        if target.fields.get("immune"):
            raise Unsupported("DESTROY_ON_IMMUNE_UNREVIEWED")
        target.destroyed = True
        self.event("DESTROY", target.ref, None, f"{cause}: destroyed")

    def settle(self) -> list[Ent]:
        """Resolve deaths; returns the casualties in board order (a Reborn minion is a casualty that stays)."""
        casualties = []
        for entity in sorted(self.entities, key=lambda e: (e.side, e.sort_key)):
            if entity.dead:
                continue
            health = entity.fields["health"]
            if entity.destroyed or (health is not None and health <= 0):
                casualties.append(entity)
                self.event("DEATH", entity.ref, None, f"{entity.ref.label()} dies")
                if entity.fields.get("reborn") and not entity.is_location:
                    self._revive(entity)
                else:
                    entity.dead = True
        for side, hero in self.heroes.items():
            if hero.fields["health"] <= 0 < hero.original["health"]:
                self.event("HERO_DEATH", hero.ref, None, f"{side} hero reaches 0 Health")
        return casualties

    def _revive(self, entity: Ent) -> None:
        """Reborn: the minion returns in place with 1 Health, without Reborn and without its enchantments.

        Printed attack, Health and keywords come back only from a card JSON that carries them. A token that
        no JSON describes keeps health 1 and ``reborn`` False, and everything else is left undetermined.
        (Logged: 14 of 14 returns with a catalog card matched; the observed card features are no substitute,
        because for tokens they are current values, not printed ones.)
        """
        cause = "Reborn: returns with 1 Health"
        self.note_rule("REBORN")
        entity.destroyed = False
        entity.unknown_fields.pop("health", None)
        entity.set("health", 1, cause)
        entity.set("reborn", False, cause)
        for name in ("frozen", "silenced", "immune", "dormant"):
            entity.set(name, False, cause)
        entry = self.texts.get(entity.ref.card_id) if self.texts is not None else None
        base_attack = entry.attack if entry else None
        base_health = entry.health if entry else None
        flags = [flag for flag in BODY_FLAGS.values() if flag != "reborn"]
        if base_attack is None or base_health is None:
            for name in ("attack", "max_health", *flags):
                entity.mark_unknown(name, "Reborn: printed stats and keywords are not known")
            entity.set("can_attack", False, cause, role="BOOKKEEPING")
            self.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                         f"{entity.ref.label()}: returns by Reborn but its printed stats are not in any card JSON",
                         entity.ref, adds=False, tag="REBORN_BASE_UNKNOWN")
            self.event("REBORN", entity.ref, 1, f"{entity.ref.label()} returns with 1 Health (base unknown)")
            return
        mechanics = set(entity.card.mechanics) | set(entry.mechanics)
        entity.set("attack", base_attack, cause)
        entity.set("max_health", base_health, cause)
        for mechanic, flag in BODY_FLAGS.items():
            if flag != "reborn":
                entity.set(flag, mechanic in mechanics, cause)
        if mechanics & {"RUSH", "CHARGE"}:
            entity.mark_unknown("can_attack", "Reborn: whether a returned Rush/Charge minion can attack",
                                role="BOOKKEEPING")
        else:
            entity.set("can_attack", False, cause, role="BOOKKEEPING")
        self.event("REBORN", entity.ref, 1, f"{entity.ref.label()} returns as {base_attack}/1 (max {base_health})")

    # ----- results ----------------------------------------------------------------------------

    def changes(self) -> list[Change]:
        found: list[Change] = []
        for hero in self.heroes.values():
            found += hero.changes()
        for player in self.players.values():
            found += player.changes()
        for weapon in self.weapons.values():
            if weapon is not None:
                found += weapon.changes()
        for entity in sorted(self.entities, key=lambda e: (e.side, e.sort_key)):
            if entity.new:
                found.append(Change(entity.ref, "present", False, True, entity.causes.get("present", "summon")))
                body = (f"{entity.fields['health']} durability" if entity.is_location
                        else f"{entity.fields['attack']}/{entity.fields['health']}")
                found.append(Change(entity.ref, "body", None, body, "summon"))
                continue
            found += entity.changes()
            if entity.dead:
                found.append(Change(entity.ref, "present", True, False, "death"))
        found += [Change(ref, "present", True, False, "card leaves hand", role="BOOKKEEPING")
                  for ref in self.hand_removed]
        return found

    def to_game_state(self) -> GameState:
        sides = {}
        for side, player in (("SELF", self.state.self_player), ("OPPONENT", self.state.opponent)):
            alive = sorted((e for e in self.entities if e.side == side and not e.dead), key=lambda e: e.sort_key)
            board, locations = [], []
            for position, entity in enumerate(alive, start=1):
                target = locations if entity.is_location else board
                if not entity.new:
                    self.after_index[(side, entity.ref.zone, entity.ref.position)] = len(target)
                target.append(self._rebuilt(entity, position))
            hero, mana = self.heroes[side].fields, self.players[side].fields
            weapon = self.weapons[side]
            sides[side] = replace(
                player, board=tuple(board), locations=tuple(locations),
                hero_health=max(0, hero["health"]), armor=hero["armor"], hero_attack=hero["attack"],
                hero_divine_shield=hero["divine_shield"], hero_power_ready=hero["hero_power_ready"],
                available_mana=mana["available_mana"], hand_size=mana["hand_size"],
                weapon=player.weapon if weapon is None else self._weapon_card(player, weapon),
            )
        removed = {ref.position for ref in self.hand_removed}
        hand = tuple(card for index, card in enumerate(self.state.self_hand) if index not in removed)
        known = max(0, (self.state.self_hand_known_count or 0) - len(removed))
        return replace(self.state, self_player=sides["SELF"], opponent=sides["OPPONENT"], self_hand=hand,
                       self_hand_known_count=known)

    @staticmethod
    def _weapon_card(player: PlayerObservation, weapon: Obj) -> CardFeatures | None:
        if player.weapon is None:
            return None
        return replace(player.weapon, current_durability=weapon.fields["durability"])

    @staticmethod
    def _rebuilt(entity: Ent, position: int) -> BoardEntity | LocationEntity:
        fields = entity.fields
        if entity.is_location:
            return LocationEntity(
                card=entity.card, current_health=fields["health"], max_health=fields["max_health"],
                board_position=position, on_cooldown=fields["on_cooldown"], can_activate=fields["can_activate"])
        card = entity.card
        card = replace(
            card,
            current_attack=fields["attack"] if card.current_attack is not None or entity.new else card.current_attack,
            current_health=fields["health"] if card.current_health is not None or entity.new else card.current_health)
        flags = {name: fields[name] for name in _ENTITY_FIELDS if name not in ("attack", "health", "max_health")}
        return BoardEntity(
            card=card, current_attack=fields["attack"], current_health=fields["health"],
            max_health=fields["max_health"], board_position=position,
            cant_be_targeted_by_spells=entity.extra.get("cant_be_targeted_by_spells"),
            cant_be_targeted_by_hero_powers=entity.extra.get("cant_be_targeted_by_hero_powers"), **flags)

