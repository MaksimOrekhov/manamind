"""Forecast the immediate, observable consequences of one legal action.

The forecaster reads the player-visible ``GameState``, one handle-free action dictionary (the
shape produced by ``integrations.powerlog.policy_actions``) and the rules text of the cards
involved. It resolves effects with generic primitives driven by the text grammar; there is no
branch on a card ID. Everything outside the reviewed grammar is returned as an ``Unknown``.

Scope: the action's own resolution, up to the point where SELF can act again. The opponent's
following turn and any later decision are never modelled.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from manamind.domain.game_state import GameState
from manamind.outcome.grammar import Clause, Selector, board_profile, parse_text, trigger_events
from manamind.outcome.model import Forecast, Ref, Status, UnknownKind
from manamind.outcome.texts import TextSource
from manamind.outcome.world import BODY_FLAGS, Ent, ObservedContext, Obj, Unsupported, World

# Evidence behind each rule family, reported with every forecast that used it.
RULE_EVIDENCE = {
    "DAMAGE_PACKET": "public rules (Divine Shield, Immune, Armor, overkill); Lifesteal heals the damage dealt "
                     "(ManaEngine reviewed contract, docs/MANAENGINE_ADMISSION.md)",
    "HEALING_PACKET": "public rules; additive healing bonus per packet (ManaEngine healing pipeline v1)",
    "STAT_CHANGE": "public rules: +A/+H raises current and maximum Health together",
    "KEYWORD_GRANT": "public rules; re-granting a held keyword changes nothing",
    "DESTROY": "public rules; Immune targets excluded as unreviewed",
    "MANA_COST": "observed effective cost of the action (checked against the next observation)",
    "SUMMON": "public rules: a played minion enters at the chosen board position",
    "COMBAT": "public rules: simultaneous damage; heroes do not retaliate; Poisonous, Lifesteal, Stealth",
    "LOCATION_ACTIVATION": "public rules: an activation spends 1 durability and starts the cooldown",
    "PREPARE_AVAILABILITY_ONLY": "assumption: Prepare constrains when a card is castable; verified only "
                                 "as 'no extra change' on logged casts (reports/action_outcome_1)",
}

_BODY_FLAGS = BODY_FLAGS


def describe_action(state: GameState, action: dict[str, Any]) -> str:
    kind = action.get("type", "?")
    if kind == "END_TURN":
        return "END_TURN"
    source = action.get("card_id") or action.get("source_card_id") or "?"
    text = f"{kind} {source}"
    if action.get("source_board_position", -1) not in (None, -1) and kind != "PLAY_CARD":
        text += f"@{action['source_board_position']}"
    if action.get("target_kind"):
        where = "hero" if action["target_kind"] == "HERO" else f"#{action.get('target_board_position')}"
        text += f" -> {action['target_side']} {action['target_kind'].lower()} {where}"
        if action["target_kind"] != "HERO":
            text += f" {action.get('target_card_id')}"
    if action.get("play_position"):
        text += f" (position {action['play_position']})"
    return text


def forecast_action(state: GameState, action: dict[str, Any], texts: TextSource,
                    context: ObservedContext | None = None) -> Forecast:
    """Forecast one action. The input state is never modified."""
    label = describe_action(state, action)
    try:
        return _Run(state, action, texts, context or ObservedContext(), label).run()
    except Unsupported as exc:
        return Forecast(action=dict(action), label=label, status=Status.UNSUPPORTED,
                        unsupported_reason=exc.reason)


def forecast_alternatives(state: GameState, actions: Sequence[dict[str, Any]], texts: TextSource,
                          context: ObservedContext | None = None) -> list[Forecast]:
    """Independent forecasts of several actions from the same state (each starts from ``state``)."""
    return [forecast_action(state, action, texts, context) for action in actions]


class _Run:
    def __init__(self, state: GameState, action: dict[str, Any], texts: TextSource,
                 context: ObservedContext, label: str) -> None:
        self.state, self.action, self.texts, self.label = state, action, texts, label
        self.world = World(state, context, texts)
        self.classes: set[str] = set()
        self.involved: list[Ent] = []
        self.actor: Ent | None = None
        self.chosen: Obj | None = None
        self.chosen_used = False
        self.last_target: Obj | None = None
        self.lifesteal_spell = False
        self.damaging_source = ""            # SPELL | OTHER, decides the Spell Damage bonus
        self.immune_to_spellpower = False
        self.attack_weapon = None            # the weapon a hero attack swings, whose text may react

    # ----- driver -----------------------------------------------------------------------------

    def run(self) -> Forecast:
        if self.state.active_player != "SELF":
            raise Unsupported("NOT_SELF_TURN")
        if self.state.pending_choice_owner is not None:
            raise Unsupported("CHOICE_PENDING")
        kind = self.action.get("type")
        handler = {"PLAY_CARD": self._play, "HERO_POWER": self._hero_power,
                   "ACTIVATE_LOCATION": self._location, "ATTACK": self._attack,
                   "END_TURN": self._end_turn}.get(kind)
        if handler is None:
            raise Unsupported(f"ACTION_TYPE_{kind}")
        handler()
        casualties = self.world.settle()
        self._classify_events(casualties)
        self._reactions(casualties)
        world = self.world
        changes = tuple(world.changes())
        status = Status.EXACT if not world.unknowns else Status.PARTIAL
        try:
            after_state = world.to_game_state()
        except ValueError as error:
            after_state = None
            world.assumptions.append(f"no after-state: the result is not a valid GameState ({error})")
        return Forecast(
            action=dict(self.action), label=self.label, status=status, changes=changes,
            events=tuple(world.events), unknowns=tuple(world.unknowns),
            assumptions=tuple(world.assumptions), rules=tuple(world.rules),
            _candidate=after_state, _after_index=dict(world.after_index))

    # ----- target and selector helpers -------------------------------------------------------

    def _chosen_target(self) -> Obj | None:
        kind = self.action.get("target_kind")
        if kind is None:
            return None
        side = self.action["target_side"]
        if kind == "HERO":
            return self.world.hero(side)
        zone = "LOCATION" if kind == "LOCATION" else "BOARD"
        return self.world.find(side, zone, self.action["target_board_position"], self.action["target_card_id"])

    def _matches(self, target: Obj, selector: Selector) -> bool:
        is_minion = isinstance(target, Ent) and target.ref.zone == "BOARD"
        if selector.kinds == "MINION" and not is_minion:
            return False
        if selector.kinds == "HERO" and not target.is_hero:
            return False
        if selector.kinds == "CHARACTER" and not (is_minion or target.is_hero):
            return False
        side = target.ref.side
        return (selector.allegiance == "ANY"
                or (selector.allegiance == "FRIENDLY") == (side == "SELF"))

    def _targets(self, selector: Selector) -> list[Obj]:
        world = self.world
        if selector.mode == "CHOSEN":
            if self.chosen is None:
                raise Unsupported("NO_TARGET_FOR_CHOSEN_CLAUSE")
            if self.chosen_used:
                raise Unsupported("MULTIPLE_CHOSEN_CLAUSES")
            if not self._matches(self.chosen, selector):
                raise Unsupported("TARGET_DOES_NOT_MATCH_TEXT")
            self.chosen_used = True
            return [self.chosen]
        if selector.mode == "FIXED":
            side = "SELF" if selector.allegiance == "FRIENDLY" else "OPPONENT"
            return [world.hero(side)]
        sides = {"ANY": ("SELF", "OPPONENT"), "FRIENDLY": ("SELF",), "ENEMY": ("OPPONENT",)}[selector.allegiance]
        found: list[Obj] = []
        for side in sides:
            if selector.kinds == "CHARACTER":
                found.append(world.hero(side))
            found += world.minions(side)
        return found

    def _involve(self, target: Obj) -> None:
        if isinstance(target, Ent) and target not in self.involved:
            self.involved.append(target)

    # ----- clause execution -------------------------------------------------------------------

    def _run_text(self, card_id: str, text: str, *, damage_source: str) -> None:
        parsed = parse_text(text)
        self.damaging_source = damage_source
        self.lifesteal_spell = damage_source == "SPELL" and any(
            c.kind == "KEYWORDS" and "lifesteal" in c.keywords for c in parsed.clauses)
        for clause in parsed.clauses:
            self._clause(clause, card_id)
        if (self.chosen is not None and not self.chosen_used
                and not any(c.kind == "OPAQUE" or (c.kind == "COND" and c.inner.kind == "OPAQUE")
                            for c in parsed.clauses)):
            raise Unsupported("TARGET_NOT_USED_BY_TEXT")

    def _clause(self, clause: Clause, card_id: str) -> None:
        world = self.world
        cause = f"'{clause.text}'"
        kind = clause.kind
        if kind in ("KEYWORDS", "TRIGGER"):
            return
        if kind == "COST_ONLY":
            world.note_rule("MANA_COST")
            return
        if kind == "PREPARE":
            world.note_rule("PREPARE_AVAILABILITY_ONLY")
            world.assumptions.append("Prepare is treated as availability-only: it changes when the card can be "
                                     "cast, not what the cast does")
            return
        if kind == "OPAQUE":
            mapping = {"RANDOM_OUTCOME": UnknownKind.RANDOM_OUTCOME,
                       "KEYWORD_UNDEFINED": UnknownKind.KEYWORD_UNDEFINED}
            kind_ = mapping.get(clause.category, UnknownKind.UNPARSED_CLAUSE)
            tag = {UnknownKind.RANDOM_OUTCOME: "OWN_TEXT_RANDOM",
                   UnknownKind.KEYWORD_UNDEFINED: "OWN_TEXT_KEYWORD"}.get(kind_, "OWN_TEXT_UNPARSED")
            world.unknown(kind_, f"{card_id}: '{clause.text}'", tag=tag)
            return
        if kind == "COND":
            self._conditional(clause, card_id)
            return
        if kind == "ARMOR":
            hero = world.hero("SELF")
            hero.set("armor", hero.fields["armor"] + clause.amount, cause)
            world.event("ARMOR_GAIN", hero.ref, clause.amount, f"{cause}: +{clause.amount} Armor")
            self.classes.add("ARMOR_GAIN")
            return
        if kind == "HERO_ATTACK":
            hero = world.hero("SELF")
            hero.set("attack", hero.fields["attack"] + clause.amount, cause)
            world.event("BUFF", hero.ref, clause.amount, f"{cause}: hero +{clause.amount} Attack this turn")
            self.classes.add("BUFF")
            return
        if kind == "MANA_TEMP":
            player = world.players["SELF"]
            player.set("available_mana", player.fields["available_mana"] + clause.amount, cause)  # an effect
            world.event("MANA_GAIN", player.ref, clause.amount, f"{cause}: +{clause.amount} Mana this turn")
            return
        assert clause.selector is not None
        targets = self._targets(clause.selector)
        self.last_target = targets[0] if clause.selector.mode == "CHOSEN" else None
        if kind == "DESTROY_HIGHEST":
            self._destroy_highest(targets, cause)
            return
        if kind == "DAMAGE":
            self._damage(clause, targets, cause)
            return
        for target in targets:
            self._involve(target)
            if kind == "HEAL":
                world.heal(target, clause.amount, "SELF", cause, spell=self.damaging_source == "SPELL",
                           unverified_double=bool(world.context.spell_healing_doubled))
                self.classes.add("HEAL")
            elif kind in ("BUFF", "GRANT"):
                if target.is_hero or not isinstance(target, Ent):
                    raise Unsupported("BUFF_ON_HERO")
                if clause.attack or clause.health:
                    world.buff(target, clause.attack, clause.health, cause)
                    self.classes.add("BUFF")
                for keyword in clause.keywords:
                    world.grant(target, keyword, cause)
                    self.classes.add("KEYWORD_GAIN")
            elif kind == "DESTROY":
                if not isinstance(target, Ent):
                    raise Unsupported("DESTROY_ON_HERO")
                if clause.attack_filter is not None:
                    op, limit = clause.attack_filter
                    attack = target.fields["attack"]
                    if (attack < limit) if op == "GE" else (attack > limit):
                        continue
                world.destroy(target, cause)
                self.classes.add("DEATH")

    def _damage(self, clause: Clause, targets: list[Obj], cause: str) -> None:
        world = self.world
        context = world.context
        bonus, factor, unobserved = 0, 1, False
        if self.damaging_source == "SPELL" and "$" in clause.text and not self.immune_to_spellpower:
            if context.spell_damage is not None:
                bonus = context.spell_damage
            elif context.trust_spell_damage:
                bonus = world.spell_damage["SELF"]
            else:
                unobserved = True
                world.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                              "Spell Damage is not observed (a 0 in GameState may be a default); damage is a lower bound",
                              world.players["SELF"].ref, adds=False, tag="SPELL_DAMAGE_UNOBSERVED")
            doubled = context.spell_damage_doubled if context.spell_damage is not None else (
                False if context.trust_spell_damage else None)
            if not unobserved and doubled is None:
                unobserved = True
                world.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                              "whether SELF's spell damage is doubled is not observed; damage is a lower bound",
                              world.players["SELF"].ref, adds=False, tag="SPELL_DAMAGE_DOUBLING_UNOBSERVED")
            elif doubled:
                factor = 2
        amount = (clause.amount + bonus) * factor
        lifesteal_side = "SELF" if self.lifesteal_spell else None
        dealt_total = []
        for target in targets:
            self._involve(target)
            note = (f" (+{bonus} Spell Damage)" if bonus else "") + (" (doubled)" if factor == 2 else "")
            dealt_total.append(world.damage(target, amount, cause + note, at_least=unobserved))
        self.classes.add("DAMAGE")
        if lifesteal_side:
            for dealt in dealt_total:
                if dealt > 0:
                    world.heal(world.hero("SELF"), dealt, "SELF", "Lifesteal " + cause, lifesteal=True,
                               at_least=unobserved, unverified_double=bool(context.spell_healing_doubled))
                    self.classes.add("HEAL")

    def _destroy_highest(self, candidates: list[Obj], cause: str) -> None:
        minions = [c for c in candidates if isinstance(c, Ent)]
        if not minions:
            return
        top = max(m.fields["attack"] for m in minions)
        leaders = [m for m in minions if m.fields["attack"] == top]
        if len(leaders) > 1:
            self.world.unknown(UnknownKind.RANDOM_OUTCOME,
                               f"{cause}: {len(leaders)} enemy minions tie for highest Attack ({top})",
                               tag="OWN_TEXT_RANDOM")
            return
        self._involve(leaders[0])
        self.world.destroy(leaders[0], cause)
        self.classes.add("DEATH")

    def _conditional(self, clause: Clause, card_id: str) -> None:
        target = self.last_target
        if target is None:
            raise Unsupported("CONDITION_WITHOUT_TARGET")
        health = target.fields["health"]
        dies = bool(getattr(target, "destroyed", False)) or (health is not None and health <= 0)
        fires = dies if clause.condition == "IF_DIES" else not dies
        if target.unknown_fields and not (dies and clause.condition == "IF_DIES"):
            self.world.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                               f"'{clause.text}': the condition depends on a value that is not observed",
                               tag="CONDITION_UNOBSERVED")
            return
        if not fires:
            self.world.event("CONDITION", target.ref, None, f"'{clause.text}': condition false, clause skipped")
            return
        self.world.event("CONDITION", target.ref, None, f"'{clause.text}': condition true")
        assert clause.inner is not None
        self._clause(clause.inner, card_id)

    # ----- actions ----------------------------------------------------------------------------

    def _spend_mana(self, cost: int | None, hand_card_cost: int | None = None) -> None:
        player = self.world.players["SELF"]
        effective = cost if cost is not None else hand_card_cost
        self.world.note_rule("MANA_COST")
        if effective is None:
            self.world.unknown(UnknownKind.MODIFIER_UNOBSERVED, "the effective cost of the action is not observed",
                               player.ref, adds=False, tag="COST_UNOBSERVED")
            player.mark_unknown("available_mana", "cost unknown", role="BOOKKEEPING")
            return
        remaining = player.fields["available_mana"] - effective
        if remaining < 0:
            raise Unsupported("COST_EXCEEDS_AVAILABLE_MANA")
        player.set("available_mana", remaining, f"pays {effective} Mana", role="BOOKKEEPING")
        if effective:
            self.classes.add("MANA_SPENT")
            self.world.event("MANA_SPENT", player.ref, effective, f"pays {effective} Mana")

    def _hand_card(self):
        index = self.action.get("hand_index")
        hand = self.state.self_hand
        if index is None or not 0 <= index < len(hand) or hand[index].card_id != self.action.get("card_id"):
            raise Unsupported("HAND_CARD_MISMATCH")
        return index, hand[index]

    def _leave_hand(self, index: int, card_id: str) -> None:
        player = self.world.players["SELF"]
        self.world.hand_removed.append(Ref("SELF", "HAND", index, card_id))
        player.set("hand_size", player.fields["hand_size"] - 1, "card leaves hand", role="BOOKKEEPING")
        self.world.note_rule("HAND_REMOVAL")

    def _play(self) -> None:
        index, card = self._hand_card()
        card_type = self.action.get("card_type")
        if card_type not in ("SPELL", "MINION", "LOCATION"):
            raise Unsupported(f"PLAY_{card_type}_NOT_MODELLED")
        self.chosen = self._chosen_target()
        self._spend_mana(self.action.get("card_cost"), card.effective_cost)
        self._leave_hand(index, card.card_id)
        entry = self.texts.get(card.card_id)
        hand_keywords = None
        if card_type == "MINION":
            observed = self.world.context.hand_keywords
            if observed is not None and index < len(observed):
                hand_keywords = observed[index]
        if card_type == "MINION" and hand_keywords is None and not self.world.context.hand_keywords_match_card:
            self.world.unknown(UnknownKind.MODIFIER_UNOBSERVED,
                               "keyword enchantments on the hand instance are not observed; the keywords shown "
                               "come from the base card", Ref("SELF", "HAND", index, card.card_id), adds=False,
                               tag="HAND_KEYWORDS_UNOBSERVED")
        if card_type == "SPELL":
            self.classes.add("SPELL_CAST")
            self.immune_to_spellpower = bool(entry and "IMMUNETOSPELLPOWER" in entry.mechanics)
            if entry is None:
                self.world.unknown(UnknownKind.TEXT_UNAVAILABLE, f"no rules text for spell {card.card_id}",
                                   tag="OWN_TEXT_MISSING")
            else:
                self.lifesteal_spell = "LIFESTEAL" in entry.mechanics
                self._run_text(card.card_id, entry.text, damage_source="SPELL")
            return
        if card_type == "LOCATION":
            self._place_location(card)
            return
        self._summon(card, entry, hand_keywords)

    def _place_location(self, card) -> None:
        """A played Location enters at the chosen position; its text is an activation effect, not run now."""
        world = self.world
        self.classes |= {"MINION_PLAYED", "SUMMON"}      # conservative: any 'after you play/summon' trigger
        position = self.action.get("play_position")
        durability = card.current_health if card.current_health is not None else card.health
        if not position or durability is None:
            raise Unsupported("LOCATION_BODY_UNOBSERVED")
        fields = {"health": durability, "max_health": durability, "on_cooldown": False, "can_activate": None}
        place = Ent(Ref("SELF", "LOCATION", position, card.card_id), fields, card, new=True)
        place.causes["present"] = "played from hand"
        world.entities.append(place)
        world.note_rule("SUMMON")
        world.event("SUMMON", place.ref, None, f"{card.card_id} enters play at position {position} with "
                                               f"{durability} durability")

    def _summon(self, card, entry, hand_keywords: frozenset[str] | None = None) -> None:
        world = self.world
        self.classes |= {"MINION_PLAYED", "SUMMON"}
        position = self.action.get("play_position")
        attack = card.effective_attack
        health = card.current_health if card.current_health is not None else card.health
        if not position or attack is None or health is None:
            raise Unsupported("MINION_BODY_UNOBSERVED")
        mechanics = set(card.mechanics) | (set(entry.mechanics) if entry else set())
        fields = {"attack": attack, "health": health, "max_health": health,
                  "frozen": False, "silenced": False, "immune": False, "dormant": False,
                  "can_attack": "CHARGE" in mechanics or "RUSH" in mechanics}
        fields.update({flag: name in mechanics for name, flag in _BODY_FLAGS.items()})
        if hand_keywords is not None:                  # the hand instance's own keywords, as observed
            fields.update({flag: flag in hand_keywords for flag in _BODY_FLAGS.values()})
            fields["can_attack"] = bool(hand_keywords & {"charge", "rush"})
        minion = Ent(Ref("SELF", "BOARD", position, card.card_id), fields, card, new=True)
        minion.causes["present"] = "played from hand"
        world.entities.append(minion)
        world.note_rule("SUMMON")
        world.event("SUMMON", minion.ref, None, f"{card.card_id} enters play at position {position} as "
                                                f"{attack}/{health}")
        if entry is None:
            world.unknown(UnknownKind.TEXT_UNAVAILABLE, f"no rules text for minion {card.card_id}",
                          tag="OWN_TEXT_MISSING")
            return
        self._run_text(card.card_id, entry.text, damage_source="OTHER")

    def _hero_power(self) -> None:
        power = self.state.self_player.hero_power
        if power is None:
            raise Unsupported("HERO_POWER_UNOBSERVED")
        self.chosen = self._chosen_target()
        self._spend_mana(self.action.get("card_cost"), power.effective_cost)
        hero = self.world.hero("SELF")
        hero.set("hero_power_ready", False, "hero power used", role="BOOKKEEPING")
        self.classes.add("HERO_POWER_USED")
        entry = self.texts.get(power.card_id)
        if entry is None:
            self.world.unknown(UnknownKind.TEXT_UNAVAILABLE, f"no rules text for hero power {power.card_id}",
                               tag="OWN_TEXT_MISSING")
            return
        self._run_text(power.card_id, entry.text, damage_source="OTHER")

    def _location(self) -> None:
        position = self.action.get("source_board_position")
        place = self.world.find("SELF", "LOCATION", position, self.action.get("source_card_id"))
        self.actor = place
        self.chosen = self._chosen_target()
        self.world.note_rule("LOCATION_ACTIVATION")
        place.set("health", place.fields["health"] - 1, "activation uses 1 durability", role="BOOKKEEPING")
        place.set("on_cooldown", True, "activation starts the cooldown", role="BOOKKEEPING")
        place.set("can_activate", False, "activation starts the cooldown", role="BOOKKEEPING")
        self._involve(place)
        entry = self.texts.get(place.ref.card_id)
        if entry is None:
            self.world.unknown(UnknownKind.TEXT_UNAVAILABLE, f"no rules text for Location {place.ref.card_id}",
                               tag="OWN_TEXT_MISSING")
            return
        self._run_text(place.ref.card_id, entry.text, damage_source="OTHER")

    def _attack(self) -> None:
        world = self.world
        world.note_rule("COMBAT")
        defender = self._chosen_target()
        if defender is None:
            raise Unsupported("ATTACK_WITHOUT_TARGET")
        self.classes.add("ATTACK")
        if self.action.get("source_is_hero"):
            attacker: Obj = world.hero("SELF")
            weapon = world.weapons["SELF"]
        else:
            attacker = world.find("SELF", "BOARD", self.action.get("source_board_position"),
                                  self.action.get("source_card_id"))
            weapon = None
            self.actor = attacker  # type: ignore[assignment]
        attack = attacker.fields["attack"]
        counter = 0 if defender.is_hero else defender.fields["attack"]
        self._involve(attacker)
        self._involve(defender)
        hero_attacker = attacker.is_hero
        if hero_attacker and self.state.self_player.weapon is not None:
            weapon_card = self.state.self_player.weapon
            a_flags = {"lifesteal": "LIFESTEAL" in weapon_card.mechanics,
                       "poisonous": "POISONOUS" in weapon_card.mechanics}
            self.attack_weapon = weapon_card
        else:
            a_flags = {} if hero_attacker else attacker.fields
        d_flags = {} if defender.is_hero else defender.fields
        dealt = world.damage(defender, attack, "attack damage", poisonous=bool(a_flags.get("poisonous")))
        taken = world.damage(attacker, counter, "counter-attack damage", poisonous=bool(d_flags.get("poisonous")))
        self.classes.add("DAMAGE")
        if a_flags.get("lifesteal") and dealt > 0:
            world.heal(world.hero("SELF"), dealt, "SELF", "Lifesteal (attacker)", lifesteal=True)
            self.classes.add("HEAL")
        if d_flags.get("lifesteal") and taken > 0:
            world.heal(world.hero(defender.ref.side), taken, defender.ref.side, "Lifesteal (defender)", lifesteal=True)
            self.classes.add("HEAL")
        if not hero_attacker:
            if a_flags.get("stealth"):
                attacker.set("stealth", False, "attacking removes Stealth")
            if a_flags.get("windfury"):
                attacker.mark_unknown("can_attack", "Windfury: attacks already used are not observed",
                                      role="BOOKKEEPING")
                world.unknown(UnknownKind.MODIFIER_UNOBSERVED, "Windfury attacker: remaining attacks not observed",
                              attacker.ref, adds=False, tag="ATTACKS_USED_UNOBSERVED")
            else:
                attacker.set("can_attack", False, "the attack is spent", role="BOOKKEEPING")
        elif weapon is not None:
            durability = weapon.fields["durability"]
            if durability is None:
                world.unknown(UnknownKind.MODIFIER_UNOBSERVED, "weapon durability not observed", weapon.ref,
                              tag="WEAPON_UNOBSERVED")
            else:
                weapon.set("durability", durability - 1, "weapon loses 1 durability", role="BOOKKEEPING")
                if durability - 1 <= 0:
                    attacker.mark_unknown("attack", "weapon breaks: remaining hero Attack not observed")
                    world.unknown(UnknownKind.MODIFIER_UNOBSERVED, "weapon breaks: hero Attack afterwards",
                                  attacker.ref, adds=False, tag="WEAPON_UNOBSERVED")

    def _end_turn(self) -> None:
        self.classes.add("TURN_END")
        self.world.event("END_TURN", None, None, "SELF ends the turn; the opponent's turn is not modelled")

    # ----- reactions --------------------------------------------------------------------------

    def _classify_events(self, casualties: list[Ent]) -> None:
        for event in self.world.events:
            if event.kind in ("DAMAGE", "HEAL", "BUFF", "KEYWORD_GAIN", "ARMOR_GAIN"):
                self.classes.add(event.kind)
        if casualties:
            self.classes.add("DEATH")

    def _reactions(self, casualties: list[Ent]) -> None:
        world, state = self.world, self.state
        kind = self.action.get("type")
        if kind != "END_TURN" and state.opponent.secret_count > 0:
            world.unknown(UnknownKind.HIDDEN_SECRET,
                          f"opponent has {state.opponent.secret_count} Secret(s) that may trigger",
                          tag="OPPONENT_SECRET")
        if kind != "END_TURN" and state.self_player.secret_count > 0:
            world.unknown(UnknownKind.POSSIBLE_REACTION,
                          f"SELF has {state.self_player.secret_count} Secret/Quest object(s)", alters=False,
                          tag="OWN_SECRET_OR_QUEST")
        damaged = {e.subject for e in world.events if e.kind == "DAMAGE" and e.subject is not None}
        dead = {entity.ref for entity in casualties}
        attacker_ref = self.actor.ref if self.actor is not None else None
        for entity in world.entities:
            if entity.new:
                continue
            self_events = set()
            if entity.ref in dead:
                self_events.add("DEATH_SELF")
            if entity.ref in damaged:
                self_events.add("DAMAGE_SELF")
            if entity.ref == attacker_ref:
                self_events.add("ATTACK_SELF")
            self._entity_reactions(entity, self_events, casualties)
        if self.attack_weapon is not None:
            weapon = self.attack_weapon
            self._card_reactions(world.weapons["SELF"].ref, weapon.card_id, set(weapon.mechanics), {"ATTACK_SELF"},
                                 involved=True)

    def _entity_reactions(self, entity: Ent, self_events: set[str], casualties: list[Ent]) -> None:
        world = self.world
        entry = self.texts.get(entity.ref.card_id)
        mechanics = set(entity.card.mechanics) | (set(entry.mechanics) if entry else set())
        covered_death = False
        if "DEATH_SELF" in self_events and not entity.is_location and (
                mechanics & {"DEATHRATTLE", "INVISIBLEDEATHRATTLE"}):
            covered_death = True
            world.unknown(UnknownKind.POSSIBLE_REACTION,
                          f"{entity.ref.label()}: its Deathrattle resolves after death", entity.ref,
                          tag="DEATHRATTLE")
        self._card_reactions(entity.ref, entity.ref.card_id, mechanics, self_events,
                             involved=entity in self.involved, covered_death=covered_death,
                             enrage_possible="ENRAGED" in mechanics and (
                                 "DAMAGE_SELF" in self_events or (entity in self.involved and "HEAL" in self.classes)))

    def _card_reactions(self, ref: Ref, card_id: str, mechanics: set[str], self_events: set[str], *,
                        involved: bool, covered_death: bool = False, enrage_possible: bool = False) -> None:
        """Triggers and static rules of one object in play that the forecast does not model."""
        world = self.world
        entry = self.texts.get(card_id)
        if entry is None:
            if self.classes - {"MANA_SPENT"}:
                world.unknown(UnknownKind.TEXT_UNAVAILABLE,
                              f"{ref.label()}: no rules text, triggers and static rules unknown", ref,
                              tag="BOARD_TEXT_MISSING")
            return
        mechanics = mechanics | set(entry.mechanics)
        triggers, statics = board_profile(entry.text)
        active = self.classes | self_events
        for sentence in triggers:
            fires = trigger_events(sentence)
            hit = fires & active
            if covered_death and hit == {"DEATH_SELF"}:
                continue
            if "ANY" in fires or hit:
                world.unknown(UnknownKind.POSSIBLE_REACTION,
                              f"{ref.label()}: '{sentence}' may fire on {sorted(hit) or 'an unreadable condition'}",
                              ref, tag="BOARD_TRIGGER")
        aura = bool(mechanics & {"AURA", "SPELLPOWER", "ADJACENT_BUFF"})
        for sentence in statics:
            if aura and "DEATH_SELF" not in self_events and not involved:
                continue
            # a Location's text is its activation effect: it may be pending from an earlier activation
            what = "Location effect" if ref.zone == "LOCATION" else "static rule"
            world.unknown(UnknownKind.POSSIBLE_REACTION, f"{ref.label()}: {what} '{sentence}' is not modelled", ref,
                          tag="BOARD_STATIC_TEXT")
        if enrage_possible:
            world.unknown(UnknownKind.POSSIBLE_REACTION,
                          f"{ref.label()}: Enrage may change Attack with Health", ref, tag="BOARD_STATIC_TEXT")
