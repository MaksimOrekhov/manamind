"""ENGINE-STATE-IMPORT-0: read-only readiness diagnostics for a player-visible position.

Answers "what stands between this visible GameState and a faithful native ManaEngine session"
without building one. It never changes a state, never infers hidden information and never turns a
missing field into a value. Outputs are diagnostics, not admissions: ``faithful_import_possible_today``
is always False because no native from-state constructor exists, and canonical training stays blocked.

A position may carry many blockers; each is typed by one of seven categories and tagged with the
independent axis it belongs to (source completeness, native capability, rules evidence).
The native-state facts used here (what ``PlayerState``/``CardInstance`` can hold) are recorded in
``NATIVE_STATE_CONTRACT`` and verified against ``engine.hpp`` by a test.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from manamind.domain.serialization import game_state_from_dict
from manamind.integrations.manaengine.state_import_capability import CapabilityIndex

ANALYZER_VERSION = "state-import-0/2"
NATIVE_HERO_MAX_HEALTH = 30
SEATS = ("SELF", "OPPONENT")

# Fields of the native state and what it cannot hold today (engine.hpp PlayerState/CardInstance).
# Kept explicit so the diagnostic is auditable; tests compare these against the header text.
NATIVE_STATE_CONTRACT = {
    "player_fields": ("player_class", "hero_power_id", "hero_health", "hero_max_health", "healing_bonus", "armor", "hero_attack",
                      "hero_temp_attack", "spells_cast_this_turn", "spell_discount", "demon_discount", "overloaded_mana",
                      "pending_overload", "hero_attacked", "hero_power_used_this_turn", "hero_frozen"),
    "minion_keywords": ("rush", "charge", "taunt", "divine_shield", "lifesteal", "stealth", "silenced", "immune", "frozen", "reborn"),
    "missing": ("location_zone", "windfury", "poisonous", "dormant", "targeting_restrictions", "hero_divine_shield",
                "hero_power_cost_modifier", "hero_power_extra_use", "imbue", "quests", "from_state_constructor"),
}
# Hero Power identities whose mechanic is documented in repository evidence (not a support list).
REVIEWED_MECHANIC_IDENTITIES = {
    "EDR_449p": ("IMBUE", "reports/mechanic_discovery/EVIDENCE0A_REAL_CARD_MECHANIC_DISCOVERY.md (hero-power lane, Imbue)"),
}
_UNKNOWN_IDS = {"", "UNKNOWN_CARD"}
# Defaulted numeric PlayerObservation fields: when a raw snapshot lacks the key it is UNKNOWN, never zero.
_DEFAULTED_PLAYER_FIELDS = ("armor", "hero_attack", "max_mana", "available_mana", "overloaded_mana", "pending_overload",
                            "deck_size", "hand_size", "fatigue", "secret_count")
# How the existing extractor fills PlayerObservation fields (visible_state.py / live/visibility.py).
FIELD_PROVENANCE = {
    "hero_health": "EXTRACTED", "armor": "EXTRACTED", "hero_attack": "EXTRACTED", "max_mana": "EXTRACTED",
    "available_mana": "EXTRACTED", "overloaded_mana": "EXTRACTED", "pending_overload": "EXTRACTED", "deck_size": "EXTRACTED",
    "hand_size": "EXTRACTED", "fatigue": "EXTRACTED", "secret_count": "EXTRACTED_BY_LIVE_PROJECTION", "player_class": "EXTRACTED",
    "weapon": "EXTRACTED", "hero_power": "EXTRACTED", "board": "EXTRACTED", "locations": "EXTRACTED",
    "hero_power_ready": "EXPLICIT_TAG_OR_SERVER_OPTION_ELSE_NONE", "hero_divine_shield": "NONE_WHEN_TAG_ABSENT",
    "hero_frozen": "EXPLICIT_TAG_ELSE_NONE", "hero_max_health": "EXTRACTED_WHEN_TAG_VALID_ELSE_NONE",
    "hero_freeze_turns_remaining": "NEVER_POPULATED", "spells_cast_this_turn": "NEVER_POPULATED", "spell_discount": "NEVER_POPULATED",
    "demon_discount": "NEVER_POPULATED", "current_turn_minion_types_played": "NEVER_POPULATED",
    "previous_turn_minion_types_played": "NEVER_POPULATED", "healing_bonus": "NEVER_POPULATED",
    "known_secrets": "NEVER_POPULATED_DEFAULTS_EMPTY", "spell_damage": "NEVER_POPULATED_DEFAULTS_ZERO",
    "active_effects": "NEVER_POPULATED_DEFAULTS_EMPTY",
}


class Category(str, Enum):
    UNKNOWN = "UNKNOWN"
    NOT_REPRESENTED = "NOT_REPRESENTED"
    UNSUPPORTED_MECHANIC = "UNSUPPORTED_MECHANIC"
    UNSUPPORTED_CARD = "UNSUPPORTED_CARD"
    RULE_UNRESOLVED = "RULE_UNRESOLVED"
    INCONSISTENT = "INCONSISTENT"


RESOLUTIONS = ("IMPORT_CONTRACT", "OBSERVATION_EXTRACTION", "ENGINE_PRIMITIVE", "CARD_DECLARATION", "RULES_EVIDENCE",
               "HIDDEN_INFORMATION_DESIGN", "DEFER")
# SOURCE: the visible state / extractor lacks it. NATIVE: the engine cannot hold or execute it. RULES: semantics unestablished.
# BOTH: both the visible state and the native contract lack a faithful representation.
AXES = ("SOURCE", "NATIVE", "RULES", "BOTH")
NATURES = ("OBSERVABLE", "INHERENTLY_HIDDEN", "NOT_APPLICABLE")


@dataclass(frozen=True, slots=True)
class BlockerSpec:
    category: Category
    subsystem: str
    axis: str
    resolution: str
    nature: str
    applicability: tuple
    family: str
    description: str


def _s(category, subsystem, axis, resolution, nature, applicability, family, description) -> BlockerSpec:
    return BlockerSpec(Category(category), subsystem, axis, resolution, nature, applicability, family, description)


WHOLE = ("WHOLE",)
ENTITY = ("ENTITY",)
ROTATION = ("TURN_ROTATION",)
# An entity's own actions plus whatever it does when the turn rotates (end-of-turn triggers, opponent-turn attacks).
ENTITY_OR_ROTATION = ("ANY", ENTITY, ROTATION)
# Applicability = which next actions the blocker can stop. Hydration of the whole position is blocked by every blocker.
BLOCKER_SPECS: dict[str, BlockerSpec] = {
    # --- INCONSISTENT ----------------------------------------------------------------------------------------------
    "INTEGRITY_STATE_REJECTED": _s("INCONSISTENT", "INTEGRITY", "SOURCE", "OBSERVATION_EXTRACTION", "NOT_APPLICABLE", WHOLE, "INTEGRITY", "GameState invariants reject this snapshot."),
    "INTEGRITY_FIELD_MISSING": _s("INCONSISTENT", "INTEGRITY", "SOURCE", "OBSERVATION_EXTRACTION", "NOT_APPLICABLE", WHOLE, "INTEGRITY", "A required top-level field is absent."),
    "INTEGRITY_BOARD_ORDER": _s("INCONSISTENT", "BOARD", "SOURCE", "OBSERVATION_EXTRACTION", "NOT_APPLICABLE", WHOLE, "INTEGRITY", "Shared board slots are duplicated, gapped, out of range or listed out of order."),
    "INTEGRITY_ENTITY_RANGE": _s("INCONSISTENT", "INTEGRITY", "SOURCE", "OBSERVATION_EXTRACTION", "NOT_APPLICABLE", WHOLE, "INTEGRITY", "A numeric value is outside its legal range (health, mana, hand size, turn)."),
    "INTEGRITY_TRUST": _s("INCONSISTENT", "INTEGRITY", "SOURCE", "DEFER", "NOT_APPLICABLE", WHOLE, "INTEGRITY", "The snapshot's trust metadata violates the live-capture contract."),
    "INTEGRITY_EVIDENCE_DEBT_IN_VISIBLE_STATE": _s("INCONSISTENT", "INTEGRITY", "SOURCE", "DEFER", "NOT_APPLICABLE", WHOLE, "INTEGRITY", "A real visible state carries simulator evidence constraints, which only the simulator produces."),
    "INTEGRITY_OPPONENT_IDENTITY_EXPOSED": _s("INCONSISTENT", "INTEGRITY", "SOURCE", "DEFER", "NOT_APPLICABLE", WHOLE, "INTEGRITY", "Opponent hand identities appear under an opponent_identity_policy of none."),
    # --- UNKNOWN -----------------------------------------------------------------------------------------------------
    "SOURCE_FIELD_ABSENT": _s("UNKNOWN", "GAME_TURN", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "LEGACY_SCHEMA", "A legacy numeric field is absent from the raw snapshot; absence is not zero."),
    "HERO_POWER_ID_UNKNOWN": _s("UNKNOWN", "HERO_POWER", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "IDENTITY", "The current Hero Power identity is missing; the class never proves it."),
    "HERO_POWER_COST_UNKNOWN": _s("UNKNOWN", "HERO_POWER", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", ("ENTITY",), "IDENTITY", "The current Hero Power cost is missing."),
    "HERO_POWER_READINESS_UNKNOWN": _s("UNKNOWN", "HERO_POWER", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", ("ENTITY",), "ABSENT_TAG", "hero_power_ready is None: no explicit EXHAUSTED tag and no server statement (validated option or REQ_NOT_EXHAUSTED_HERO_POWER) settles the exhausted status, or the sources conflict or a modifier tag applies."),
    "TURN_COUNTERS_UNKNOWN": _s("UNKNOWN", "GAME_TURN", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "NEVER_POPULATED", "Spells cast this turn / spell or Demon discounts are never populated by the extractor."),
    "MINION_TYPE_HISTORY_UNKNOWN": _s("UNKNOWN", "GAME_TURN", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "NEVER_POPULATED", "Current/previous own-turn minion-type history is never populated by the extractor."),
    "HERO_FREEZE_UNKNOWN": _s("UNKNOWN", "HERO", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "ABSENT_TAG", "The hero Frozen state is unknown (no explicit FROZEN tag), or the hero is frozen and the remaining freeze duration, which the log does not carry, is unknown."),
    "HERO_DIVINE_SHIELD_UNKNOWN": _s("UNKNOWN", "HERO", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "ABSENT_TAG", "hero_divine_shield is None because the DIVINE_SHIELD tag is absent."),
    "HEALING_BONUS_UNKNOWN": _s("UNKNOWN", "HERO", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", ("EFFECT", "HEAL"), "NEVER_POPULATED", "The persistent healing bonus is unknown (never populated by the extractor); 0 would be a known value."),
    "HERO_MAX_HEALTH_UNKNOWN": _s("UNKNOWN", "HERO", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "ABSENT_TAG", "The hero maximum Health is not observed (hero_max_health is None or absent, e.g. a historical state); it is never taken from 30 or the hero class."),
    "SPELL_DAMAGE_UNOBSERVED": _s("UNKNOWN", "BOARD", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", ("EFFECT", "SPELL_DAMAGE"), "NEVER_POPULATED", "A Spell Damage minion is on board but its amount is not extracted (current_spell_damage is None)."),
    "MINION_TARGETING_FLAGS_UNOBSERVED": _s("UNKNOWN", "BOARD", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "ABSENT_TAG", "cant_be_targeted_* is None when the tag is absent; absence is not proven False."),
    "WEAPON_STATE_UNKNOWN": _s("UNKNOWN", "WEAPON", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", ENTITY_OR_ROTATION, "IDENTITY", "Current weapon attack or durability is missing."),
    "LOCATION_ACTIVATION_STATE_UNKNOWN": _s("UNKNOWN", "LOCATION", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", ENTITY_OR_ROTATION, "NEVER_POPULATED", "can_activate is never populated for a Location; only the cooldown flag is extracted."),
    "SELF_HAND_IDENTITIES_UNKNOWN": _s("UNKNOWN", "HAND", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "IDENTITY", "Some SELF hand cards have no known identity."),
    "SELF_HAND_ORDER_UNPROVEN": _s("UNKNOWN", "HAND", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "PROVENANCE", "The source orders the SELF hand by entity table, not by on-screen zone position."),
    "PLAYER_EFFECTS_NOT_EXTRACTED": _s("UNKNOWN", "EFFECTS", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "NEVER_POPULATED", "Player-level enchantments (active_effects, spell_damage) are never extracted, so an empty list/0 is a default, not knowledge."),
    "SECRET_COUNT_NOT_EXTRACTED": _s("UNKNOWN", "SECRET", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "PROVENANCE", "The source profile never extracts secret_count, so the stored 0 is a default, not knowledge."),
    "SELF_SECRET_IDENTITIES_UNKNOWN": _s("UNKNOWN", "SECRET", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", WHOLE, "NEVER_POPULATED", "SELF has entities in the SECRET zone whose identities are not extracted (known_secrets is never populated); the zone is not limited to Secrets."),
    "SELF_DECK_COMPOSITION_UNKNOWN": _s("UNKNOWN", "DECK", "SOURCE", "IMPORT_CONTRACT", "OBSERVABLE", ("EFFECT", "DRAW"), "DECK", "SELF deck contents are not in the visible state; a decklist input would have to be part of the import contract."),
    "OPPONENT_HAND_IDENTITIES_UNKNOWN": _s("UNKNOWN", "HAND", "SOURCE", "HIDDEN_INFORMATION_DESIGN", "INHERENTLY_HIDDEN", ROTATION, "HIDDEN", "Opponent hand cards have no visible identity (hand_size minus revealed cards)."),
    "OPPONENT_SECRET_IDENTITIES_UNKNOWN": _s("UNKNOWN", "SECRET", "SOURCE", "HIDDEN_INFORMATION_DESIGN", "INHERENTLY_HIDDEN", WHOLE, "HIDDEN", "Opponent Secrets are hidden; any action may trigger one."),
    "OPPONENT_DECK_COMPOSITION_UNKNOWN": _s("UNKNOWN", "DECK", "SOURCE", "HIDDEN_INFORMATION_DESIGN", "INHERENTLY_HIDDEN", ROTATION, "HIDDEN", "Opponent deck contents are hidden."),
    "SELF_DECK_ORDER_UNKNOWN": _s("UNKNOWN", "DECK", "SOURCE", "HIDDEN_INFORMATION_DESIGN", "INHERENTLY_HIDDEN", ("EFFECT", "DRAW"), "HIDDEN", "SELF deck order is hidden; a draw needs a determinization design."),
    "OPPONENT_DECK_ORDER_UNKNOWN": _s("UNKNOWN", "DECK", "SOURCE", "HIDDEN_INFORMATION_DESIGN", "INHERENTLY_HIDDEN", ROTATION, "HIDDEN", "Opponent deck order is hidden."),
    # --- NOT_REPRESENTED ------------------------------------------------------------------------------------------
    "HERO_ATTACK_READINESS_NOT_REPRESENTED": _s("NOT_REPRESENTED", "HERO", "SOURCE", "OBSERVATION_EXTRACTION", "OBSERVABLE", ("HERO_ATTACK",), "NEVER_POPULATED", "Hero attack > 0 but GameState has no hero attacked-this-turn/readiness flag."),
    "PENDING_CHOICE_CONTINUATION_NOT_REPRESENTED": _s("NOT_REPRESENTED", "PENDING_CHOICE", "BOTH", "IMPORT_CONTRACT", "NOT_APPLICABLE", WHOLE, "CONTRACT", "A pending choice is visible but its source card and continuation are not part of GameState."),
    "ACTIVE_EFFECT_NOT_REPRESENTED": _s("NOT_REPRESENTED", "EFFECTS", "BOTH", "IMPORT_CONTRACT", "NOT_APPLICABLE", WHOLE, "CONTRACT", "A visible player enchantment has no reviewed native mapping."),
    "HERO_DIVINE_SHIELD_NOT_NATIVE": _s("NOT_REPRESENTED", "HERO", "NATIVE", "ENGINE_PRIMITIVE", "NOT_APPLICABLE", WHOLE, "NATIVE_LACKS", "The hero has Divine Shield; the native player state has no such field."),
    "HERO_POWER_COST_MODIFIED": _s("NOT_REPRESENTED", "HERO_POWER", "NATIVE", "ENGINE_PRIMITIVE", "NOT_APPLICABLE", ("ENTITY",), "NATIVE_LACKS", "Current Hero Power cost differs from the printed cost; the engine has no cost-modifier state."),
    "LOCATION_NOT_REPRESENTED_NATIVE": _s("NOT_REPRESENTED", "LOCATION", "NATIVE", "ENGINE_PRIMITIVE", "NOT_APPLICABLE", WHOLE, "NATIVE_LACKS", "A Location occupies a shared board slot; the native state has no Location zone or activation."),
    "MINION_KEYWORD_NOT_NATIVE": _s("NOT_REPRESENTED", "BOARD", "NATIVE", "ENGINE_PRIMITIVE", "NOT_APPLICABLE", ENTITY_OR_ROTATION, "NATIVE_LACKS", "A board minion has Windfury, Poisonous or Dormant; the native minion state has no such field."),
    "MINION_TARGETING_RESTRICTION_NOT_NATIVE": _s("NOT_REPRESENTED", "BOARD", "NATIVE", "ENGINE_PRIMITIVE", "NOT_APPLICABLE", ENTITY_OR_ROTATION, "NATIVE_LACKS", "A minion cannot be targeted by spells/Hero Powers; native targeting has no such restriction."),
    "MINION_MODIFIER_PROVENANCE_NOT_REPRESENTED": _s("NOT_REPRESENTED", "BOARD", "BOTH", "OBSERVATION_EXTRACTION", "OBSERVABLE", ENTITY_OR_ROTATION, "PROVENANCE", "Current stats differ from base; GameState carries no enchantment list, durations or aura/permanent split."),
    "HAND_CARD_MODIFIER_PROVENANCE_NOT_REPRESENTED": _s("NOT_REPRESENTED", "HAND", "BOTH", "OBSERVATION_EXTRACTION", "OBSERVABLE", ENTITY, "PROVENANCE", "A SELF hand card's current cost/stats differ from base without a modifier source."),
    # --- UNSUPPORTED_MECHANIC ------------------------------------------------------------------------------------------
    "HERO_POWER_IMBUE": _s("UNSUPPORTED_MECHANIC", "HERO_POWER", "NATIVE", "ENGINE_PRIMITIVE", "NOT_APPLICABLE", WHOLE, "UNSUPPORTED", "The current Hero Power is a documented Imbue power; Imbue is not implemented."),
    "HERO_MAX_HEALTH_UNSUPPORTED_NATIVE": _s("UNSUPPORTED_MECHANIC", "HERO", "NATIVE", "ENGINE_PRIMITIVE", "NOT_APPLICABLE", WHOLE, "UNSUPPORTED", "The observed hero maximum Health differs from the native fixed 30 (for example 40); the native healing cap and hero state are only exercised at 30."),
    "HERO_HEALTH_EXCEEDS_NATIVE_MAX": _s("UNSUPPORTED_MECHANIC", "HERO", "NATIVE", "ENGINE_PRIMITIVE", "NOT_APPLICABLE", WHOLE, "UNSUPPORTED", "Hero Health is above the native fixed maximum of 30; the healing pipeline would use the wrong cap."),
    # --- UNSUPPORTED_CARD ------------------------------------------------------------------------------------------
    "HERO_POWER_UNSUPPORTED": _s("UNSUPPORTED_CARD", "HERO_POWER", "NATIVE", "CARD_DECLARATION", "NOT_APPLICABLE", WHOLE, "UNSUPPORTED", "The observed Hero Power is described by metadata but is not a reviewed, executable declaration."),
    "UNSUPPORTED_CARD_SELF_HAND": _s("UNSUPPORTED_CARD", "HAND", "NATIVE", "CARD_DECLARATION", "NOT_APPLICABLE", WHOLE, "UNSUPPORTED", "An unsupported card is in the active SELF hand; native legal-action enumeration throws."),
    "UNSUPPORTED_CARD_BOARD": _s("UNSUPPORTED_CARD", "BOARD", "NATIVE", "CARD_DECLARATION", "NOT_APPLICABLE", ENTITY_OR_ROTATION, "UNSUPPORTED", "An unsupported minion is on the board; its triggers/auras cannot be executed."),
    "UNSUPPORTED_CARD_LOCATION": _s("UNSUPPORTED_CARD", "LOCATION", "NATIVE", "CARD_DECLARATION", "NOT_APPLICABLE", ENTITY_OR_ROTATION, "UNSUPPORTED", "A Location card has no executable declaration."),
    "UNSUPPORTED_CARD_WEAPON": _s("UNSUPPORTED_CARD", "WEAPON", "NATIVE", "CARD_DECLARATION", "NOT_APPLICABLE", ENTITY_OR_ROTATION, "UNSUPPORTED", "An equipped weapon has no executable declaration."),
    "UNSUPPORTED_CARD_SECRET": _s("UNSUPPORTED_CARD", "SECRET", "NATIVE", "CARD_DECLARATION", "NOT_APPLICABLE", WHOLE, "UNSUPPORTED", "A known SELF Secret has no executable declaration."),
    "UNSUPPORTED_CARD_OPPONENT_REVEALED": _s("UNSUPPORTED_CARD", "HAND", "NATIVE", "CARD_DECLARATION", "NOT_APPLICABLE", ROTATION, "UNSUPPORTED", "A revealed opponent card has no executable declaration."),
    "UNSUPPORTED_CARD_NOT_IN_CATALOG": _s("UNSUPPORTED_CARD", "CARD_CAPABILITY", "NATIVE", "CARD_DECLARATION", "NOT_APPLICABLE", ENTITY_OR_ROTATION, "UNSUPPORTED", "A visible card ID is absent from the engine catalog and every local metadata source."),
    # --- RULE_UNRESOLVED ---------------------------------------------------------------------------------------------
    "HERO_POWER_IDENTITY_UNREVIEWED": _s("RULE_UNRESOLVED", "HERO_POWER", "RULES", "RULES_EVIDENCE", "NOT_APPLICABLE", WHOLE, "IDENTITY", "The Hero Power identity is observed but appears in no local metadata; its semantics are not established and it is never aliased to the base power."),
}
# Priority for "what is the next required capability": earlier entries must be done first.
_RESOLUTION_ORDER = {name: index for index, name in enumerate(RESOLUTIONS)}


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    seat: str | None = None
    entity: tuple | None = None
    card_id: str | None = None
    detail: str | None = None
    applicability: tuple | None = None

    @property
    def spec(self) -> BlockerSpec:
        return BLOCKER_SPECS[self.code]

    @property
    def effective_applicability(self) -> tuple:
        return self.applicability or self.spec.applicability


@dataclass(frozen=True, slots=True)
class ActionContext:
    """The next action as entity keys, built from an already-sanitized legal action (handles never leave memory)."""

    type: str
    involved: frozenset
    source_card_id: str | None = None


def action_context_from_policy_action(action: Mapping[str, Any], seat: str = "SELF") -> ActionContext:
    kind = str(action.get("type"))
    involved: set[tuple] = set()
    if kind == "PLAY_CARD" and action.get("hand_index") is not None:
        involved.add(("HAND", seat, int(action["hand_index"])))
    elif kind == "HERO_POWER":
        involved.add(("HERO_POWER", seat))
    elif kind == "ATTACK":
        if action.get("source_is_hero"):
            involved.update({("HERO", seat), ("WEAPON", seat)})
        elif action.get("source_board_position") is not None:
            involved.add(("BOARD", seat, int(action["source_board_position"])))
    elif kind == "ACTIVATE_LOCATION" and action.get("source_board_position") is not None:
        involved.add(("LOCATION", seat, int(action["source_board_position"])))
    side = action.get("target_side")
    if side in SEATS:
        if action.get("target_is_hero"):
            involved.add(("HERO", side))
        elif action.get("target_board_position") is not None and int(action["target_board_position"]) >= 0:
            position = int(action["target_board_position"])
            involved.update({("BOARD", side, position), ("LOCATION", side, position)})
    return ActionContext(kind, frozenset(involved), action.get("source_card_id") or action.get("card_id"))


def _rule_effect(rule: tuple, blocker: Blocker, context: ActionContext, capability: CapabilityIndex) -> str:
    kind = rule[0]
    if kind == "WHOLE":
        return "BLOCKS"
    if kind == "ANY":
        results = [_rule_effect(sub, blocker, context, capability) for sub in rule[1:]]
        return "BLOCKS" if "BLOCKS" in results else "UNDETERMINED" if "UNDETERMINED" in results else "NOT_INVOLVED"
    if kind == "ENTITY":
        return "BLOCKS" if blocker.entity in context.involved else "NOT_INVOLVED"
    if kind == "TURN_ROTATION":
        return "BLOCKS" if context.type == "END_TURN" else "NOT_INVOLVED"
    if kind == "HERO_ATTACK":
        return "BLOCKS" if ("HERO", "SELF") in context.involved and context.type == "ATTACK" else "NOT_INVOLVED"
    if kind == "EFFECT":
        effect_class = rule[1]
        if context.type == "END_TURN":
            return "BLOCKS" if effect_class == "DRAW" else "UNDETERMINED"
        if effect_class == "SPELL_DAMAGE" and context.type != "PLAY_CARD":
            return "NOT_INVOLVED"
        card = capability.card(context.source_card_id) if context.source_card_id else None
        if card is None or not card.supported:
            return "UNDETERMINED"
        return "BLOCKS" if capability.has_effect(card.card_id, effect_class) else "NOT_INVOLVED"
    return "UNDETERMINED"


def _applicability_label(rule: tuple) -> str:
    if rule[0] == "ANY":
        return "+".join(_applicability_label(sub) for sub in rule[1:])
    return rule[0] if rule[0] != "EFFECT" else f"EFFECT_{rule[1]}"


def _chosen_effect(blocker: Blocker, context: ActionContext | None, capability: CapabilityIndex) -> str:
    """Does this blocker stop the specific next action? BLOCKS / NOT_INVOLVED / UNDETERMINED / NOT_ASSESSED.

    NOT_INVOLVED means the blocker's entity or effect class is provably not part of the action. For a card whose behavior is
    unknown (unsupported cards, unresolved rules) non-involvement cannot be proven, because passive triggers of unsupported
    cards are not classified (Phase 4K.1c), so it is reported as UNDETERMINED instead.
    """
    if context is None:
        return "NOT_ASSESSED"
    result = _rule_effect(blocker.effective_applicability, blocker, context, capability)
    if result == "NOT_INVOLVED" and blocker.spec.category in (Category.UNSUPPORTED_CARD, Category.RULE_UNRESOLVED):
        return "UNDETERMINED"
    return result


@dataclass(frozen=True, slots=True)
class PositionDiagnostic:
    structurally_valid: bool
    blockers: tuple[Blocker, ...]
    known: dict
    hero_power: dict
    chosen_action: dict | None
    capability_fingerprint: str
    chosen_effects: tuple[str, ...]

    def categories(self) -> set[str]:
        return {blocker.spec.category.value for blocker in self.blockers}

    def codes(self) -> set[str]:
        return {blocker.code for blocker in self.blockers}

    def to_dict(self) -> dict:
        rows = []
        for blocker, effect in zip(self.blockers, self.chosen_effects):
            spec = blocker.spec
            row = {"code": blocker.code, "category": spec.category.value, "subsystem": spec.subsystem, "axis": spec.axis,
                   "resolution": spec.resolution, "nature": spec.nature, "family": spec.family, "chosen_action_effect": effect,
                   "applies_to": _applicability_label(blocker.effective_applicability)}
            for name in ("seat", "card_id", "detail"):
                if getattr(blocker, name) is not None:
                    row[name] = getattr(blocker, name)
            if blocker.entity is not None:
                row["entity"] = list(blocker.entity)
            rows.append(row)
        next_steps = sorted({row["resolution"] for row in rows}, key=_RESOLUTION_ORDER.__getitem__)
        effects = set(self.chosen_effects)
        return {
            "structurally_valid": self.structurally_valid,
            "analyzer_version": ANALYZER_VERSION,
            "capability_fingerprint": self.capability_fingerprint,
            "faithful_native_import_possible_today": False,
            "faithful_native_import_blocked_by": ["NO_FROM_STATE_CONSTRUCTOR", *sorted({row["code"] for row in rows})],
            "axes": {
                "source_completeness": ("INCONSISTENT" if "INCONSISTENT" in self.categories() else
                                        "INCOMPLETE" if any(b.spec.axis in ("SOURCE", "BOTH") and b.spec.nature != "INHERENTLY_HIDDEN" for b in self.blockers)
                                        else "COMPLETE_VISIBLE_FIELDS"),
                "hidden_information": "GAPS_PRESENT" if any(b.spec.nature == "INHERENTLY_HIDDEN" for b in self.blockers) else "NO_GAPS_DETECTED",
                "native_capability": "INCAPABLE" if any(b.spec.axis in ("NATIVE", "BOTH") for b in self.blockers) else "NO_KNOWN_GAP",
                "rules_evidence": "UNRESOLVED" if "RULE_UNRESOLVED" in self.categories() else "NO_UNRESOLVED_FOUND_REVIEWED_DECLARATIONS_ONLY",
                "native_hydration": "BLOCKED_NO_FROM_STATE_CONSTRUCTOR",
                "chosen_action_simulation": (
                    "NOT_ASSESSED" if self.chosen_action is None else
                    "BLOCKED" if "BLOCKS" in effects else
                    "UNDETERMINED" if "UNDETERMINED" in effects else "NO_DIRECT_BLOCKER_BUT_HYDRATION_BLOCKED"),
                "canonical_training": "BLOCKED_GLOBAL_GATE",
            },
            "known": self.known,
            "hero_power": self.hero_power,
            "chosen_action": self.chosen_action,
            "blockers": rows,
            "next_required": next_steps,
        }


class _Collector:
    def __init__(self) -> None:
        self.items: list[Blocker] = []

    def add(self, code: str, **kwargs: Any) -> None:
        if code not in BLOCKER_SPECS:
            raise KeyError(code)
        blocker = Blocker(code, **kwargs)
        if blocker not in self.items:
            self.items.append(blocker)


def _card_of(entity: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = entity.get("card")
    return nested if isinstance(nested, Mapping) else entity


def _card_id(card: Mapping[str, Any] | None) -> str:
    return str((card or {}).get("card_id", (card or {}).get("id", "UNKNOWN_CARD")))


def _check_cards(out: _Collector, capability: CapabilityIndex, card_id: str, *, code: str, seat: str, entity: tuple) -> None:
    """Typed unsupported-card blocker for one visible card. ``code`` is the zone-specific UNSUPPORTED_CARD code."""
    if card_id in _UNKNOWN_IDS:
        return
    cap = capability.card(card_id)
    if cap.supported:
        return
    if cap.reason == "NOT_IN_CATALOG" and not capability.has_metadata(card_id):
        out.add("UNSUPPORTED_CARD_NOT_IN_CATALOG", seat=seat, entity=entity, card_id=card_id, detail=cap.reason)
        return
    out.add(code, seat=seat, entity=entity, card_id=card_id, detail=cap.reason)


def _classify_hero_power(out: _Collector, capability: CapabilityIndex, seat: str, player: Mapping[str, Any], *, active: bool) -> dict:
    power = player.get("hero_power")
    entity = ("HERO_POWER", seat)
    card_id = _card_id(power) if isinstance(power, Mapping) else None
    info: dict[str, Any] = {"identity_observed": False, "status": "MISSING", "class_is_not_evidence": True}
    if card_id is None or card_id in _UNKNOWN_IDS:
        out.add("HERO_POWER_ID_UNKNOWN", seat=seat, entity=entity)
        return info
    info["identity_observed"] = True
    mechanic = REVIEWED_MECHANIC_IDENTITIES.get(card_id)
    cap = capability.card(card_id)
    if mechanic is not None:
        info["status"] = "IMBUE_UNSUPPORTED"
        out.add("HERO_POWER_IMBUE", seat=seat, entity=entity, card_id=card_id, detail=mechanic[0])
    elif cap.supported and cap.card_type == "HERO_POWER":
        info["status"] = "PROVEN_SUPPORTED_BASE"
    elif capability.has_metadata(card_id):
        info["status"] = "UNSUPPORTED_KNOWN_METADATA"
        out.add("HERO_POWER_UNSUPPORTED", seat=seat, entity=entity, card_id=card_id, detail=cap.reason)
    else:
        info["status"] = "UNREVIEWED_IDENTITY"
        out.add("HERO_POWER_IDENTITY_UNREVIEWED", seat=seat, entity=entity, card_id=card_id)
    current = power.get("current_cost")
    printed = capability.printed_cost(card_id)
    if current is None:
        out.add("HERO_POWER_COST_UNKNOWN", seat=seat, entity=entity, card_id=card_id)
    elif printed is not None and int(current) != printed:
        out.add("HERO_POWER_COST_MODIFIED", seat=seat, entity=entity, card_id=card_id, detail=f"current={current} printed={printed}")
    if active and player.get("hero_power_ready") is None:
        out.add("HERO_POWER_READINESS_UNKNOWN", seat=seat, entity=entity, card_id=card_id)
    return info


def _check_hero_max_health(out: _Collector, seat: str, player: Mapping[str, Any], health: Any) -> str:
    """Four separate outcomes: unknown, known and valid, known but unsupported natively, and inconsistent.

    Returns UNKNOWN, INCONSISTENT, KNOWN_UNSUPPORTED_NATIVE or KNOWN_SUPPORTED_NATIVE for the report.
    """
    maximum = player.get("hero_max_health")
    if maximum is None:
        out.add("HERO_MAX_HEALTH_UNKNOWN", seat=seat)
        return "UNKNOWN"
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
        out.add("INTEGRITY_ENTITY_RANGE", seat=seat, detail="hero_max_health is not a positive integer")
        return "INCONSISTENT"
    if isinstance(health, int) and not isinstance(health, bool) and health > maximum:
        out.add("INTEGRITY_ENTITY_RANGE", seat=seat, detail=f"hero_health={health} exceeds hero_max_health={maximum}")
        return "INCONSISTENT"
    if maximum != NATIVE_HERO_MAX_HEALTH:
        out.add("HERO_MAX_HEALTH_UNSUPPORTED_NATIVE", seat=seat, detail=f"hero_max_health={maximum}")
        return "KNOWN_UNSUPPORTED_NATIVE"
    return "KNOWN_SUPPORTED_NATIVE"


def _check_board_geometry(out: _Collector, seat: str, player: Mapping[str, Any]) -> None:
    minions = list(player.get("board") or ())
    locations = list(player.get("locations") or ())
    positions = [int(_entity_value(e, "board_position", 0)) for e in minions] + [int(_entity_value(e, "board_position", 0)) for e in locations]
    if not positions:
        return
    ordered = sorted(positions)
    base = ordered[0]
    contiguous = base in (0, 1) and ordered == list(range(base, base + len(ordered)))
    in_range = all(0 <= p <= 7 for p in positions) and len(positions) <= 7
    listed_in_order = [int(_entity_value(e, "board_position", 0)) for e in minions] == sorted(int(_entity_value(e, "board_position", 0)) for e in minions)
    if not (contiguous and in_range and listed_in_order):
        out.add("INTEGRITY_BOARD_ORDER", seat=seat, detail=f"positions={positions}")


def _entity_value(entity: Mapping[str, Any], name: str, default: Any = None) -> Any:
    if name in entity:
        return entity[name]
    return _card_of(entity).get(name, default)


def _check_player(out: _Collector, capability: CapabilityIndex, state: Mapping[str, Any], seat: str, player: Mapping[str, Any],
                  *, active: bool) -> tuple[dict, str]:
    known: dict[str, Any] = {}
    for name in _DEFAULTED_PLAYER_FIELDS:
        if name not in player:
            out.add("SOURCE_FIELD_ABSENT", seat=seat, detail=name)
    health = player.get("hero_health")
    if isinstance(health, int) and not isinstance(health, bool):
        if health <= 0:
            out.add("INTEGRITY_ENTITY_RANGE", seat=seat, detail="hero_health<=0 at a decision boundary")
        if health > NATIVE_HERO_MAX_HEALTH:
            out.add("HERO_HEALTH_EXCEEDS_NATIVE_MAX", seat=seat, detail=f"hero_health={health}")
        known["hero_health"] = True
    known["hero_max_health"] = _check_hero_max_health(out, seat, player, health)
    if int(player.get("max_mana", 0) or 0) > 10 or int(player.get("hand_size", 0) or 0) > 10:
        out.add("INTEGRITY_ENTITY_RANGE", seat=seat, detail="max_mana or hand_size above 10")

    hero_power = _classify_hero_power(out, capability, seat, player, active=active)
    shield = player.get("hero_divine_shield", "ABSENT")
    if shield is True:
        out.add("HERO_DIVINE_SHIELD_NOT_NATIVE", seat=seat)
    elif shield in (None, "ABSENT"):
        out.add("HERO_DIVINE_SHIELD_UNKNOWN", seat=seat)
    frozen = player.get("hero_frozen")
    if frozen is None:
        out.add("HERO_FREEZE_UNKNOWN", seat=seat, detail="frozen state unknown")
    elif frozen is True and player.get("hero_freeze_turns_remaining") is None:
        # An explicitly unfrozen hero has no duration to know; a frozen one needs it to expire correctly.
        out.add("HERO_FREEZE_UNKNOWN", seat=seat, detail="frozen, duration unknown")
    if player.get("healing_bonus") is None:
        applicability = ("EFFECT", "HEAL") if seat == "SELF" else ROTATION
        out.add("HEALING_BONUS_UNKNOWN", seat=seat, applicability=applicability)
    if player.get("spell_discount") is None or player.get("demon_discount") is None or (
            active and player.get("spells_cast_this_turn") is None):
        out.add("TURN_COUNTERS_UNKNOWN", seat=seat)
    if player.get("previous_turn_minion_types_played") is None or (active and player.get("current_turn_minion_types_played") is None):
        out.add("MINION_TYPE_HISTORY_UNKNOWN", seat=seat)
    if active and int(player.get("hero_attack", 0) or 0) > 0:
        out.add("HERO_ATTACK_READINESS_NOT_REPRESENTED", seat=seat)

    weapon = player.get("weapon")
    if isinstance(weapon, Mapping):
        entity = ("WEAPON", seat)
        _check_cards(out, capability, _card_id(weapon), code="UNSUPPORTED_CARD_WEAPON", seat=seat, entity=entity)
        if weapon.get("current_attack") is None or (weapon.get("current_durability") is None and weapon.get("durability") is None):
            out.add("WEAPON_STATE_UNKNOWN", seat=seat, entity=entity, card_id=_card_id(weapon))
        known["weapon"] = True

    _check_board(out, capability, seat, player, known)
    _check_board_geometry(out, seat, player)

    if (player.get("secret_count") or 0) > len(player.get("known_secrets") or ()):
        out.add("SELF_SECRET_IDENTITIES_UNKNOWN" if seat == "SELF" else "OPPONENT_SECRET_IDENTITIES_UNKNOWN", seat=seat,
                detail=f"count={player.get('secret_count')} known={len(player.get('known_secrets') or ())}")
    for index, secret in enumerate(player.get("known_secrets") or ()):
        _check_cards(out, capability, _card_id(secret if isinstance(secret, Mapping) else {"card_id": secret}),
                     code="UNSUPPORTED_CARD_SECRET", seat=seat, entity=("SECRET", seat, index))
    for index, effect in enumerate(player.get("active_effects") or ()):
        out.add("ACTIVE_EFFECT_NOT_REPRESENTED", seat=seat, entity=("EFFECT", seat, index), card_id=_card_id(effect))
    if (player.get("deck_size") or 0) > 0:
        out.add("SELF_DECK_COMPOSITION_UNKNOWN" if seat == "SELF" else "OPPONENT_DECK_COMPOSITION_UNKNOWN", seat=seat)
        out.add("SELF_DECK_ORDER_UNKNOWN" if seat == "SELF" else "OPPONENT_DECK_ORDER_UNKNOWN", seat=seat)
    known.update({"hero_power_identity_observed": hero_power["identity_observed"], "board_minions": len(player.get("board") or ()),
                  "locations": len(player.get("locations") or ()), "hand_size": player.get("hand_size"), "deck_size": player.get("deck_size")})
    return hero_power, known["hero_max_health"]


def _check_board(out: _Collector, capability: CapabilityIndex, seat: str, player: Mapping[str, Any], known: dict) -> None:
    minions = list(player.get("board") or ())
    unobserved_targeting = False
    for entity in minions:
        card = _card_of(entity)
        position = int(_entity_value(entity, "board_position", 0))
        key = ("BOARD", seat, position)
        card_id = _card_id(card)
        _check_cards(out, capability, card_id, code="UNSUPPORTED_CARD_BOARD", seat=seat, entity=key)
        keywords = [name for name in ("windfury", "poisonous", "dormant") if entity.get(name)]
        if keywords:
            out.add("MINION_KEYWORD_NOT_NATIVE", seat=seat, entity=key, card_id=card_id, detail=",".join(keywords))
        for name in ("cant_be_targeted_by_spells", "cant_be_targeted_by_hero_powers"):
            if name in entity and entity[name] is True:
                out.add("MINION_TARGETING_RESTRICTION_NOT_NATIVE", seat=seat, entity=key, card_id=card_id, detail=name)
            elif entity.get(name) is None:
                unobserved_targeting = True
        attack, health, maximum = (_entity_value(entity, n) for n in ("current_attack", "current_health", "max_health"))
        if any(not isinstance(v, int) or isinstance(v, bool) for v in (attack, health, maximum)) or health <= 0 or maximum < health or attack < 0:
            out.add("INTEGRITY_ENTITY_RANGE", seat=seat, entity=key, card_id=card_id, detail="minion attack/health/max_health out of range")
        elif (card.get("attack") is not None and attack != card.get("attack")) or (card.get("health") is not None and maximum != card.get("health")):
            out.add("MINION_MODIFIER_PROVENANCE_NOT_REPRESENTED", seat=seat, entity=key, card_id=card_id,
                    detail=f"attack {card.get('attack')}->{attack}, max_health {card.get('health')}->{maximum}")
        if "SPELLPOWER" in tuple(card.get("mechanics") or ()) and card.get("current_spell_damage") is None:
            out.add("SPELL_DAMAGE_UNOBSERVED", seat=seat, entity=key, card_id=card_id)
    if unobserved_targeting:
        out.add("MINION_TARGETING_FLAGS_UNOBSERVED", seat=seat)
    for entity in list(player.get("locations") or ()):
        card = _card_of(entity)
        key = ("LOCATION", seat, int(_entity_value(entity, "board_position", 0)))
        out.add("LOCATION_NOT_REPRESENTED_NATIVE", seat=seat, entity=key, card_id=_card_id(card))
        _check_cards(out, capability, _card_id(card), code="UNSUPPORTED_CARD_LOCATION", seat=seat, entity=key)
        if entity.get("can_activate") is None:
            out.add("LOCATION_ACTIVATION_STATE_UNKNOWN", seat=seat, entity=key, card_id=_card_id(card))
        health, maximum = _entity_value(entity, "current_health"), _entity_value(entity, "max_health")
        if not isinstance(health, int) or not isinstance(maximum, int) or health <= 0 or maximum < health:
            out.add("INTEGRITY_ENTITY_RANGE", seat=seat, entity=key, detail="location health out of range")


def _check_hands(out: _Collector, capability: CapabilityIndex, state: Mapping[str, Any], active: str, hand_order: str) -> None:
    hand = list(state.get("self_hand") or ())
    self_player = state["self_player"]
    if len(hand) < int(self_player.get("hand_size", 0) or 0):
        out.add("SELF_HAND_IDENTITIES_UNKNOWN", seat="SELF", detail=f"known={len(hand)} hand_size={self_player.get('hand_size')}")
    if hand_order != "ZONE_POSITION" and hand:
        out.add("SELF_HAND_ORDER_UNPROVEN", seat="SELF", detail=hand_order)
    for index, card in enumerate(hand):
        card_id = _card_id(card)
        if active == "SELF":
            _check_cards(out, capability, card_id, code="UNSUPPORTED_CARD_SELF_HAND", seat="SELF", entity=("HAND", "SELF", index))
        elif card_id not in _UNKNOWN_IDS and not capability.card(card_id).supported:
            # The unsupported card is not enumerated this turn; it bites when the turn rotates to SELF.
            out.add("UNSUPPORTED_CARD_SELF_HAND", seat="SELF", entity=("HAND", "SELF", index), card_id=card_id,
                    detail=capability.card(card_id).reason, applicability=ROTATION)
        if card.get("current_cost") is not None and card.get("cost") is not None and card["current_cost"] != card["cost"]:
            out.add("HAND_CARD_MODIFIER_PROVENANCE_NOT_REPRESENTED", seat="SELF", entity=("HAND", "SELF", index), card_id=card_id,
                    detail=f"cost {card['cost']}->{card['current_cost']}")
        elif card.get("card_type") == "MINION" and card.get("current_attack") is not None and card.get("attack") is not None and (
                card["current_attack"] != card["attack"] or (card.get("current_health") is not None and card.get("health") is not None and card["current_health"] != card["health"])):
            out.add("HAND_CARD_MODIFIER_PROVENANCE_NOT_REPRESENTED", seat="SELF", entity=("HAND", "SELF", index), card_id=card_id,
                    detail="hand minion stats differ from base")
    revealed = list(state.get("opponent_known_cards") or ())
    hidden = int(state["opponent"].get("hand_size", 0) or 0) - len(revealed)
    if hidden > 0:
        out.add("OPPONENT_HAND_IDENTITIES_UNKNOWN", seat="OPPONENT", detail=f"hidden={hidden}")
    for index, card in enumerate(revealed):
        _check_cards(out, capability, _card_id(card), code="UNSUPPORTED_CARD_OPPONENT_REVEALED", seat="OPPONENT", entity=("HAND", "OPPONENT", index))


# FULLY_POPULATED is for synthetic states that claim every defaultable field was really observed (tests, future extractors).
SOURCE_PROFILES = ("LIVE_SANITIZED", "OFFLINE_PARITY", "FULLY_POPULATED")


def analyze_position(state: Mapping[str, Any] | Any, capability: CapabilityIndex, *, action: Mapping[str, Any] | None = None,
                     snapshot: Mapping[str, Any] | None = None, source_profile: str = "LIVE_SANITIZED") -> PositionDiagnostic:
    """Diagnose one visible state. ``state`` is a raw JSON-decoded mapping (preferred: keeps absent keys absent) or a GameState.

    ``action`` is the sanitized legal action actually taken (policy-corpus shape) when known. ``snapshot`` is the optional
    live-snapshot envelope used for trust checks. ``source_profile`` says how the extractor produced the state: LIVE_SANITIZED
    (zone-position hand order, secret counts) or OFFLINE_PARITY (entity-order hand, no secret counts); neither extracts player
    enchantments. FULLY_POPULATED asserts all of that was observed. Never raises on malformed content; it reports INCONSISTENT
    blockers.
    """
    if source_profile not in SOURCE_PROFILES:
        raise ValueError(f"unknown source_profile: {source_profile}")
    if not isinstance(state, Mapping):
        from manamind.live.snapshot import state_to_dict  # lazy: only needed for domain objects
        state = state_to_dict(state)
    out = _Collector()
    missing = [key for key in ("turn_number", "active_player", "self_player", "opponent") if key not in state]
    for key in missing:
        out.add("INTEGRITY_FIELD_MISSING", detail=key)
    structurally_valid = True
    if not missing:
        try:
            game_state_from_dict(dict(state))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            structurally_valid = False
            out.add("INTEGRITY_STATE_REJECTED", detail=f"{type(error).__name__}: {error}"[:200])
    else:
        structurally_valid = False

    known: dict[str, Any] = {}
    hero_power = {"SELF": {"identity_observed": False, "status": "NOT_ANALYZED"}, "OPPONENT": {"identity_observed": False, "status": "NOT_ANALYZED"}}
    max_health = {"SELF": "NOT_ANALYZED", "OPPONENT": "NOT_ANALYZED"}
    context = action_context_from_policy_action(action) if action is not None else None
    if not missing and isinstance(state["self_player"], Mapping) and isinstance(state["opponent"], Mapping):
        try:
            active = str(state["active_player"]).upper()
            if int(state["turn_number"]) < 1:
                out.add("INTEGRITY_ENTITY_RANGE", detail="turn_number<1")
            for seat, key in (("SELF", "self_player"), ("OPPONENT", "opponent")):
                hero_power[seat], max_health[seat] = _check_player(out, capability, state, seat, state[key], active=(seat == active))
            _check_hands(out, capability, state, active, "ENTITY_ORDER" if source_profile == "OFFLINE_PARITY" else "ZONE_POSITION")
            for seat in SEATS:
                if source_profile == "OFFLINE_PARITY":
                    out.add("SECRET_COUNT_NOT_EXTRACTED", seat=seat)
                if source_profile != "FULLY_POPULATED":
                    out.add("PLAYER_EFFECTS_NOT_EXTRACTED", seat=seat)
            if state.get("pending_choice_owner") is not None or state.get("pending_choice_options"):
                out.add("PENDING_CHOICE_CONTINUATION_NOT_REPRESENTED", seat=state.get("pending_choice_owner"))
            if state.get("evidence_constraints"):
                out.add("INTEGRITY_EVIDENCE_DEBT_IN_VISIBLE_STATE", detail=",".join(sorted(map(str, state["evidence_constraints"]))))
            known.update({"hero_max_health": max_health, "active_player": active, "turn_number": state["turn_number"],
                          "self_hand_known_count": len(state.get("self_hand") or ()),
                          "opponent_revealed_cards": len(state.get("opponent_known_cards") or ())})
        except (TypeError, ValueError, KeyError, AttributeError) as error:
            structurally_valid = False
            out.add("INTEGRITY_STATE_REJECTED", detail=f"unreadable content: {type(error).__name__}")
    if snapshot is not None:
        _check_snapshot_trust(out, snapshot, state)

    blockers = tuple(out.items)
    effects = tuple(_chosen_effect(blocker, context, capability) for blocker in blockers)
    chosen = None if action is None else {"type": context.type if context else None}
    return PositionDiagnostic(structurally_valid, blockers, known, hero_power, chosen, capability.fingerprint, effects)


def _check_snapshot_trust(out: _Collector, snapshot: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    """Live-capture trust contract: ranked Standard, settled READY snapshot at a SELF decision, no opponent identities."""
    problems = []
    if snapshot.get("status") != "READY":
        problems.append(f"status={snapshot.get('status')}")
    if snapshot.get("game_type") != "GT_RANKED" or snapshot.get("format") != "FT_STANDARD":
        problems.append("mode is not ranked Standard")
    if snapshot.get("phase") != "SELF_DECISION" or str(state.get("active_player")).upper() != "SELF":
        problems.append("not a SELF decision position")
    if problems:
        out.add("INTEGRITY_TRUST", detail="; ".join(problems))
    if snapshot.get("opponent_identity_policy") == "none" and state.get("opponent_known_cards"):
        out.add("INTEGRITY_OPPONENT_IDENTITY_EXPOSED")


def canonical_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
