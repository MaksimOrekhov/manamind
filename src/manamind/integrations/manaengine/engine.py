"""Adapter from the experimental C++ ManaEngine to ManaMind's public domain."""
from __future__ import annotations

import importlib.util
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Mapping, NamedTuple, Sequence

from manamind.cards.catalog import CardCatalog
from manamind.domain.card import CardFeatures
from manamind.domain.game_state import EVIDENCE_CONSTRAINT_IDS, GameState
from manamind.domain.serialization import game_state_from_dict
from manamind.integrations.manaengine.pool_manifest import load_dark_gift_option_manifest, load_pool_manifest

_NATIVE: ModuleType | None = None
_ROOT = Path(__file__).resolve().parents[4]


class _RuntimeCatalog(NamedTuple):
    """The reusable runtime state of one catalog: the built native catalog and the metadata of that same catalog."""

    native_catalog: Any
    card_metadata: Mapping[str, CardFeatures]


# Ownership contract. `_definition_rows()` returns fresh, caller-owned mutable native CardDefinition rows on every call,
# so a caller (tests build synthetic catalogs this way) can never change what another caller or session sees.
# `native.CardCatalog` copies the rows when it is built, so a cached catalog is likewise isolated from later row edits.
# The only process-wide cache is this one: resolved catalog path -> immutable _RuntimeCatalog, read-only after insertion.
_NATIVE_CATALOG_CACHE: dict[str, _RuntimeCatalog] = {}


def _rules_coverage(metadata: dict[str, Any], spec: dict[str, Any]) -> bool:
    """Authoring guard; reviewed text coverage is independent of test evidence."""
    text = re.sub(r"<[^>]+>|\[x\]", "", str(metadata.get("text", "")))
    text = " ".join(text.split())
    if spec.get("ability", "NONE") == "NONE":
        keywords = {"TAUNT", "RUSH", "LIFESTEAL", "REBORN"}
        words = set(text.upper().replace(",", " ").split())
        return words <= keywords and set(metadata.get("mechanics", ())) <= keywords
    return text == spec.get("reviewed_rules_text")


class FailureKind(str, Enum):
    UNSUPPORTED = "UNSUPPORTED"
    RULE_UNRESOLVED = "RULE_UNRESOLVED"
    BUDGET_LIMIT = "BUDGET_LIMIT"
    ENGINE_DEFECT = "ENGINE_DEFECT"


_FAILURE_CODE_KINDS = {
    "LEGACY_UNTYPED": FailureKind.ENGINE_DEFECT,
    "DAMAGE_DEPTH_BUDGET_EXCEEDED": FailureKind.BUDGET_LIMIT,
    "DAMAGE_PACKET_BUDGET_EXCEEDED": FailureKind.BUDGET_LIMIT,
    "DAMAGE_WORK_BUDGET_EXCEEDED": FailureKind.BUDGET_LIMIT,
    "CATALOG_REFERENCE_MISSING": FailureKind.ENGINE_DEFECT,
    "DAMAGE_FRAME_PROTOCOL_VIOLATION": FailureKind.ENGINE_DEFECT,
    "DAMAGE_TARGET_LOST": FailureKind.ENGINE_DEFECT,
    "DECLARATION_CONTRACT_VIOLATION": FailureKind.ENGINE_DEFECT,
    "INVALID_DAMAGE_PACKET": FailureKind.ENGINE_DEFECT,
    "INVARIANT_VIOLATION": FailureKind.ENGINE_DEFECT,
    "LEGALITY_EXECUTION_MISMATCH": FailureKind.ENGINE_DEFECT,
    "MISSING_DISPATCH_HANDLER": FailureKind.ENGINE_DEFECT,
    "NUMERIC_RANGE_VIOLATION": FailureKind.ENGINE_DEFECT,
    "QUIESCENCE_VIOLATED": FailureKind.ENGINE_DEFECT,
    "RESOURCE_EXHAUSTED": FailureKind.ENGINE_DEFECT,
    "UNEXPECTED_EXCEPTION": FailureKind.ENGINE_DEFECT,
    "UNKNOWN_EXCEPTION": FailureKind.ENGINE_DEFECT,
    "COLOSSAL_CAPACITY_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "COLOSSAL_TRANSFORM_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "CONTROL_CHANGE_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "DAMAGE_OUTCOME_TARGET_UNRESOLVED": FailureKind.RULE_UNRESOLVED,
    "DAMAGE_REACTION_ORDER_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "DAMAGE_SOURCE_BOUNDARY_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "DARK_GIFT_ASSIGNMENT_UNRESOLVED": FailureKind.RULE_UNRESOLVED,
    "DARK_GIFT_STACKING_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "DISCOVER_POOL_INCOMPLETE": FailureKind.RULE_UNRESOLVED,
    "EOT_SOURCE_BOUNDARY_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "GENERATION_HAND_FULL_ORDER_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "HEAL_MORTALLY_WOUNDED_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "HEALING_BONUS_SCOPE_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "INSTANCE_COPY_SOURCE_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "MODIFIER_LIFETIME_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "OVERLOAD_CAPACITY_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "POOL_EMPTY_SEMANTICS_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "POOL_IDENTITY_NOT_LOADED": FailureKind.RULE_UNRESOLVED,
    "POOL_MEMBERSHIP_CANDIDATE_ONLY": FailureKind.RULE_UNRESOLVED,
    "RANDOM_SECRET_POOL_MEMBERSHIP_MISMATCH": FailureKind.RULE_UNRESOLVED,
    "RANDOM_SELECTION_PENDING_DEATH_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "REBORN_ORDERING_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "SHATTER_MODIFIER_INHERITANCE_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "SHATTER_MODIFIER_MERGE_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "TAKES_DAMAGE_BOUNDARY_UNREVIEWED": FailureKind.RULE_UNRESOLVED,
    "UNSUPPORTED_CARD_BEHAVIOR": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_CARD_ENTERED_HAND": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_CARD_IN_ACTIVE_HAND": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_DARK_GIFT_OUTCOME": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_DISCARD_TRIGGER": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_DISCOVER_OUTCOME": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_GENERATED_CARD": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_GENERATED_CARD_UNDEFINED": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_HERO_CLASS": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_HERO_POWER": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_MINION_HISTORY_TYPE": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_RANDOM_SECRET_OUTCOME": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_SECRET_DEPENDENCY": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_SUMMONED_CARD": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_TRANSFORM_OUTCOME": FailureKind.UNSUPPORTED,
    "UNSUPPORTED_VANILLA_SPELL": FailureKind.UNSUPPORTED,
}


@dataclass(frozen=True, slots=True)
class NativeFailure:
    """Scalar native failure snapshot; code owns kind, never diagnostic text."""

    kind: FailureKind
    code: str
    detail: str
    context: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FailureKind) or _FAILURE_CODE_KINDS.get(self.code) != self.kind:
            raise ValueError("unknown native failure code or inconsistent kind/code")
        if not isinstance(self.detail, str) or not isinstance(self.context, str):
            raise ValueError("native failure detail/context must be strings")


class UnsupportedSimulationError(RuntimeError):
    """Compatibility base for all failures, including defects and policy gates.

    New consumers must inspect failure.kind; catching this base does not mean
    that a branch is eligible for fallback. Untyped exceptions are defects.
    """

    def __init__(self, detail: str, *, failure: NativeFailure | None = None) -> None:
        super().__init__(detail)
        if failure is not None and detail != failure.detail:
            raise ValueError("exception detail must equal native failure detail")
        self.failure = failure


class EngineDefectError(UnsupportedSimulationError):
    """Typed engine defect; remains catchable through the compatibility base."""


def _failure_from_native(raw: Mapping[str, Any]) -> NativeFailure:
    return NativeFailure(FailureKind(raw["kind"]), raw["code"], raw["detail"], raw["context"])


def _wrap_native(exc: Exception) -> UnsupportedSimulationError:
    try:
        failure = _failure_from_native({name: getattr(exc, name) for name in ("kind", "code", "detail", "context")})
    except MemoryError:
        raise
    except Exception:
        failure = NativeFailure(FailureKind.ENGINE_DEFECT, "LEGACY_UNTYPED", str(exc), "missing/invalid native failure payload")
    cls = EngineDefectError if failure.kind == FailureKind.ENGINE_DEFECT else UnsupportedSimulationError
    return cls(failure.detail, failure=failure)


_EXECUTION_FIELDS = ("type", "hand_index", "attacker_entity_id", "target_entity_id", "choice_index", "choose_one")


def _execution_key(action: Mapping[str, Any]) -> tuple[str, int, int, int, int, int]:
    """Match native Action::execution_equal, without coercion or semantic metadata."""
    if not isinstance(action, Mapping) or not isinstance(action.get("type"), str) or not action["type"]:
        raise ValueError("action must be a mapping with a nonempty string type")
    values = [action["type"]]
    for name in _EXECUTION_FIELDS[1:]:
        value = action.get(name, 0 if name == "choose_one" else -1)
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer (not bool, float or string)")
        values.append(value)
    return tuple(values)


def _load_native() -> ModuleType:
    global _NATIVE
    if _NATIVE is not None:
        return _NATIVE
    override = Path(os.environ["MANAMIND_MANAENGINE_BUILD"]) if "MANAMIND_MANAENGINE_BUILD" in os.environ else None
    build_dirs = [override] if override else [_ROOT / "experiments" / "manaengine" / name / "python" for name in ("build-release", "build-ninja", "build")]
    modules = []
    for build in build_dirs:
        if not build or not build.exists():
            continue
        modules = [p for p in build.iterdir() if p.name.startswith("manaengine_native") and any(p.name.endswith(s) for s in EXTENSION_SUFFIXES)]
        if modules:
            break
    if len(modules) != 1:
        raise RuntimeError(f"Build the experimental ManaEngine module first; found {len(modules)} modules in {build_dirs}")
    spec = importlib.util.spec_from_file_location("manaengine_native", modules[0])
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load ManaEngine extension: {modules[0]}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _NATIVE = module
    return module


_EFFECT_KINDS = {"DAMAGE", "DRAW", "GAIN_ARMOR", "MODIFY_HERO_ATTACK", "FREEZE", "SUMMON_FIXED", "DESTROY_MINION", "HEAL", "HEAL_MINION_TO_FULL", "BUFF_FRIENDLY_MINIONS", "DISCARD_RANDOM_SPELL", "BUFF_MINION", "MODIFY_WEAPON_ATTACK", "GRANT_HEALING_BONUS"}
_TARGET_SELECTORS = {"EXPLICIT_CHARACTER", "EXPLICIT_ENEMY_CHARACTER", "EXPLICIT_MINION", "EXPLICIT_DAMAGED_ENEMY_MINION", "EXPLICIT_FRIENDLY_MINION", "ENEMY_MINIONS", "ENEMY_CHARACTERS", "ALL_CHARACTERS", "ALL_MINIONS", "SELF_HERO", "SELF", "RANDOM_ENEMY_MINION", "EXPLICIT_DAMAGED_MINION", "FRIENDLY_WEAPON", "RANDOM_DISTINCT_ENEMY_CHARACTERS", "RANDOM_DISTINCT_ENEMY_MINIONS", "ALL_FRIENDLY_CHARACTERS", "EXPLICIT_FRIENDLY_CHARACTER", "ENEMY_HERO"}


def _parse_effect_steps(native: ModuleType, card_id: str, raw_effects: Any) -> list[Any]:
    """Declaration -> native EffectStep list; unknown fields and malformed typed values fail closed."""
    if not isinstance(raw_effects, list):
        raise ValueError(f"effects must be a list for {card_id}")
    native_effects = []
    for effect in raw_effects:
        if not isinstance(effect, dict) or not {"kind", "target", "amount"} <= set(effect) or set(effect) - {"kind", "target", "amount", "lifesteal", "summon_card", "summon_condition", "conditional_extra_count", "discard_school", "requires_previous_discard", "random_count", "exclude_previous_target", "evidence_constraint"}:
            raise ValueError(f"effect requires kind, target, amount, and only supported optional fields for {card_id}")
        kind = str(effect["kind"]).upper()
        target = str(effect["target"]).upper()
        if kind not in _EFFECT_KINDS or target not in _TARGET_SELECTORS:
            raise ValueError(f"unknown effect kind/target for {card_id}: {kind}/{target}")
        native_effect = native.EffectStep()
        native_effect.kind = getattr(native.EffectKind, kind)
        native_effect.target = getattr(native.TargetSelector, target)
        native_effect.amount = int(effect["amount"])
        native_effect.lifesteal = bool(effect.get("lifesteal", False))
        native_effect.summon_card = str(effect.get("summon_card", ""))
        summon_condition = str(effect.get("summon_condition", "NONE")).upper()
        if summon_condition not in {"NONE", "HOLDING_DRAGON"}:
            raise ValueError(f"unknown summon_condition for {card_id}: {summon_condition}")
        native_effect.summon_condition = getattr(native.SummonCondition, summon_condition)
        native_effect.conditional_extra_count = int(effect.get("conditional_extra_count", 0))
        discard_school = str(effect.get("discard_school", "NONE")).upper()
        if discard_school not in {"NONE", "NATURE", "FIRE"}:
            raise ValueError(f"unknown discard_school for {card_id}: {discard_school}")
        native_effect.discard_school = getattr(native.DiscardSpellSchool, discard_school)
        native_effect.requires_previous_discard = bool(effect.get("requires_previous_discard", False))
        # Random-distinct fields are copied strictly (no int()/bool() coercion) so a malformed declaration
        # fails here or in native catalog validation instead of being silently dropped or reinterpreted.
        random_count = effect.get("random_count", 0)
        if isinstance(random_count, bool) or not isinstance(random_count, int):
            raise ValueError(f"random_count must be an integer for {card_id}")
        native_effect.random_count = random_count
        exclude_previous = effect.get("exclude_previous_target", False)
        if not isinstance(exclude_previous, bool):
            raise ValueError(f"exclude_previous_target must be a boolean for {card_id}")
        native_effect.exclude_previous_target = exclude_previous
        if "evidence_constraint" in effect:
            constraint = effect["evidence_constraint"]
            if not isinstance(constraint, str) or constraint not in EVIDENCE_CONSTRAINT_IDS or not hasattr(native.EvidenceConstraint, constraint):
                raise ValueError(f"unknown evidence_constraint for {card_id}: {constraint!r}")
            native_effect.evidence_constraint = getattr(native.EvidenceConstraint, constraint)
        native_effects.append(native_effect)
    return native_effects


def _load_definitions(catalog_path: str | Path | None = None) -> tuple[list[Any], Mapping[str, CardFeatures]]:
    """Build fresh native definition rows and the metadata of the same catalog. Nothing here is cached or shared."""
    native = _load_native()
    catalog_file = Path(catalog_path) if catalog_path else _ROOT / "data/cards/standard_current_enUS.json"
    catalog = CardCatalog.from_json(catalog_file)
    raw_catalog = json.loads(catalog_file.read_text(encoding="utf-8-sig"))
    raw_cards = raw_catalog.get("cards", []) if isinstance(raw_catalog, dict) else raw_catalog
    spell_schools = {
        str(row.get("id") or row.get("card_id") or row.get("dbfId")): str(row.get("spellSchool") or "").upper()
        for row in raw_cards
        if isinstance(row, dict)
    }
    collectible_ids = {
        str(row.get("id") or row.get("card_id") or row.get("dbfId"))
        for row in raw_cards
        if isinstance(row, dict) and row.get("collectible") is True
    }
    dependencies_file = _ROOT / "experiments/manaengine/data/dependency_metadata_audit.json"
    dependency_files = [
        dependencies_file,
        _ROOT / "experiments/manaengine/data/fixed_summon_dependency_metadata.json",
        _ROOT / "experiments/manaengine/data/summon_condition_dependencies.json",
        _ROOT / "experiments/manaengine/data/overload_dependency_metadata.json",
        _ROOT / "experiments/manaengine/data/dark_gift_option_metadata.json",
        _ROOT / "experiments/manaengine/data/choice_mode_dependency_metadata.json",
        _ROOT / "experiments/manaengine/data/colossal_appendage_dependency_metadata.json",
        _ROOT / "experiments/manaengine/data/quick1_dependency_metadata.json",
        _ROOT / "experiments/manaengine/data/quick2_dependency_metadata.json",
        _ROOT / "experiments/manaengine/data/hero_power_dependency_metadata.json",
    ]
    extras = {card.card_id: card for path in dependency_files for card in CardCatalog.from_json(path)}
    records = {c.card_id: c for c in catalog}
    pinned_raw = {str(row["id"]): row for row in json.loads(
        (_ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json").read_text(encoding="utf-8")
    )}
    pinned_raw.update({str(row["id"]): row for row in raw_cards})
    for path in dependency_files:
        for row in json.loads(path.read_text(encoding="utf-8"))["cards"]:
            pinned_raw[str(row["id"])] = row
            spell_schools[str(row["id"])] = str(row.get("spellSchool", "")).upper()
    legacy_file = _ROOT / "vendor/RosettaStone/Resources/cards.json"
    if legacy_file.exists():
        for row in json.loads(legacy_file.read_text(encoding="utf-8")):
            pinned_raw.setdefault(str(row["id"]), row)
    records.update({key: records.get(key, value) for key, value in extras.items()})
    config = json.loads((_ROOT / "experiments/manaengine/data/card_abilities.json").read_text(encoding="utf-8"))
    overrides = config["cards"]
    result = []
    for card in sorted(records.values(), key=lambda c: c.card_id):
        d = native.CardDefinition()
        d.card_id = card.card_id
        d.name = card.card_id
        d.card_type = card.card_type.upper()
        d.card_class = card.card_class.upper()
        d.race = (card.race or "").upper()
        d.spell_school = spell_schools.get(card.card_id, "")
        d.collectible = card.card_id in collectible_ids
        d.battlecry = "BATTLECRY" in card.mechanics
        d.secret = "SECRET" in card.mechanics
        d.cost = card.cost or 0
        d.attack = card.attack or 0
        d.health = card.health or 0
        d.durability = card.durability or 0
        d.reborn = d.card_type == "MINION" and "REBORN" in card.mechanics
        d.rush = "RUSH" in card.mechanics
        d.taunt = "TAUNT" in card.mechanics
        spec = overrides.get(card.card_id, {})
        d.support_state = str(spec.get("support_state", "UNSUPPORTED"))
        d.ability = str(spec.get("ability", "NONE"))
        raw = pinned_raw.get(card.card_id)
        d.overload = int((raw or {}).get("overload", 0))
        d.minion_types = sorted(set((raw or {}).get("races", [d.race] if d.race else [])))
        d.rules_contract_reviewed = raw is not None and _rules_coverage(raw, spec)
        d.required_mechanics = [str(m).upper() for m in (raw or {}).get("mechanics", ()) if str(m).upper() != "OVERLOAD" or d.overload <= 0]
        if not d.rules_contract_reviewed:
            d.support_state = "UNSUPPORTED"
        d.battlecry = "BATTLECRY" in d.required_mechanics
        d.lifesteal = d.card_type == "MINION" and "LIFESTEAL" in d.required_mechanics
        allowed_fields = {
            "damage", "generated_card", "transform_card", "choice_pool", "choice_count", "choice_cost_delta",
            "shatter_left_card", "shatter_right_card", "secret_trigger", "secret_effect", "prepare",
            "random_cast_count", "duration", "pool_max_cost", "pool_count", "held_spell_threshold",
            "spell_cost_reduction_per_cast", "spell_damage", "damaged_spell_damage", "deathrattle_draw_count",
            "spell_damage_attack", "spell_damage_grant", "card_type", "cost", "attack", "health", "race", "lifesteal",
            "reviewed_random_secret_pool",
            "spell_damage_cost_reduction",
            "kindred_copy_contract",
            "damage_outcome_amount", "requires_friendly_weapon",
            "dark_gift_option_pool_id", "dark_gift_attack", "dark_gift_health", "dark_gift_cost",
            "dark_gift_keywords", "dark_gift_requires_battlecry", "dark_gift_requires_positive_attack",
            "colossal_appendages", "takes_damage_pool_id", "takes_damage_cost_delta",
        }
        unknown = set(spec) - allowed_fields - {"support_state", "ability", "effects", "choose_one_a", "choose_one_b", "deck_draw_filter", "reviewed_rules_text", "damage_outcome_condition", "damage_outcome_followup"}
        if unknown:
            raise ValueError(f"Unknown declaration fields for {card.card_id}: {sorted(unknown)}")
        if "deck_draw_filter" in spec:
            filters = {"ANY": "ANY", "SPELL": "SPELL", "FIRE_SPELL": "FIRE_SPELL"}
            filter_name = str(spec["deck_draw_filter"]).upper()
            if filter_name not in filters:
                raise ValueError(f"unknown deck_draw_filter for {card.card_id}: {filter_name}")
            d.deck_draw_filter = getattr(native.DeckDrawFilter, filters[filter_name])
        outcome_conditions = {"MORTALLY_WOUNDED", "SURVIVES", "ALWAYS"}
        outcome_followups = {"DRAW_SELF", "HEAL_ENEMY_HERO", "DRAW_TARGET_OWNER"}
        if "damage_outcome_condition" in spec:
            value = str(spec["damage_outcome_condition"]).upper()
            if value not in outcome_conditions:
                raise ValueError(f"unknown damage_outcome_condition for {card.card_id}: {value}")
            d.damage_outcome_condition = getattr(native.DamageOutcomeCondition, value)
        if "damage_outcome_followup" in spec:
            value = str(spec["damage_outcome_followup"]).upper()
            if value not in outcome_followups:
                raise ValueError(f"unknown damage_outcome_followup for {card.card_id}: {value}")
            d.damage_outcome_followup = getattr(native.DamageOutcomeFollowup, value)
        for key, value in spec.items():
            if key in allowed_fields:
                setattr(d, key, value)
        d.colossal_appendages = [str(value) for value in spec.get("colossal_appendages", ())]
        if "dark_gift_keywords" in spec:
            d.dark_gift_keywords = [str(value).upper() for value in spec["dark_gift_keywords"]]
        raw_effects = spec.get("effects", [])
        if not isinstance(raw_effects, list):
            raise ValueError(f"effects must be a list for {card.card_id}")
        raw_effects = spec.get("effects", [])
        d.effects = _parse_effect_steps(native, card.card_id, raw_effects)
        for field in ("choose_one_a", "choose_one_b"):
            if field in spec:
                setattr(d, field, _parse_effect_steps(native, card.card_id, spec[field]))
        result.append(d)
    by_id = {row.card_id: row for row in result}
    for definition in result:
        dependencies = (definition.shatter_left_card, definition.shatter_right_card, definition.transform_card, *definition.colossal_appendages)
        dependencies += tuple(effect.summon_card for effect in definition.effects if effect.summon_card)
        dependencies += tuple(effect.summon_card for effect in (*definition.choose_one_a, *definition.choose_one_b) if effect.summon_card)
        if any(dep and (dep not in by_id or by_id[dep].support_state == "UNSUPPORTED") for dep in dependencies):
            definition.support_state = "UNSUPPORTED"
    return result, MappingProxyType(records)


def _definition_rows(catalog_path: str | Path | None = None) -> list[Any]:
    """Fresh mutable definition rows for `catalog_path`; each call returns new objects owned by the caller."""
    return _load_definitions(catalog_path)[0]


def _export_state(raw: dict[str, Any], evidence_constraints: Sequence[str] = (),
                  card_metadata: Mapping[str, CardFeatures] | None = None) -> GameState:
    """Adapt engine observations to the shared domain schema and the metadata of the session's own catalog."""
    metadata = card_metadata if card_metadata is not None else {}

    def enrich(row: dict[str, Any], *, in_hand: bool = False) -> None:
        base = metadata.get(str(row.get("card_id", "")))
        if base is not None:
            row["race"] = base.race
            row["mechanics"] = list(base.mechanics)
        if in_hand:
            if str(row.get("card_type", "")).upper() == "MINION":
                row["current_attack"] = row.get("current_attack", row.get("attack"))
                row["current_health"] = row.get("current_health", row.get("health"))
            else:
                row["current_attack"] = None
                row["current_health"] = None
            row["current_durability"] = None
        elif str(row.get("card_type", "")).upper() != "WEAPON":
            row["current_durability"] = None

    for player_key in ("self_player", "opponent"):
        player = raw[player_key]
        player.setdefault("hero_divine_shield", None)
        player.setdefault("known_secrets", [])
        player["known_secrets"] = [
            {"card_id": secret} if isinstance(secret, str) else secret
            for secret in player["known_secrets"]
        ]
        for card in player.get("board", ()):
            enrich(card)
        for effect in player.get("active_effects", ()):
            enrich(effect)
        for secret in player.get("known_secrets", ()):
            enrich(secret)
        if player.get("hero_power") is not None:
            enrich(player["hero_power"], in_hand=True)
        if player.get("weapon") is not None:
            enrich(player["weapon"])
    for card in raw.get("self_hand", ()):
        enrich(card, in_hand=True)
    for option in raw.get("pending_choice_options", ()):
        enrich(option, in_hand=True)
    raw["evidence_constraints"] = list(evidence_constraints)
    return game_state_from_dict(raw)


def require_canonical_training_admission(
    evidence_constraints: Sequence[str], *, global_gate_blocked: bool
) -> None:
    """Apply evidence debt and global admission as independent gates."""
    if evidence_constraints:
        raise UnsupportedSimulationError(
            "Canonical training admission blocked by evidence constraints: "
            + ", ".join(sorted(set(evidence_constraints)))
        )
    if global_gate_blocked:
        raise UnsupportedSimulationError(
            "ManaEngine training admission is blocked: complete backend-specific dependency, "
            "dynamic outcome, session and match evidence is required for the selected environment"
        )


class ManaEngineSession:
    """Persistent prototype match. Internal state is private to the C++ backend."""

    def __init__(self, player1_deck: Sequence[str], player2_deck: Sequence[str], *,
                 player1_class: str = "UNKNOWN_CLASS", player2_class: str = "UNKNOWN_CLASS",
                 shuffle: bool = True, random_seed: int = 0, catalog_path: str | Path | None = None) -> None:
        native = _load_native()
        self._unsupported_exception = native.UnsupportedSimulationError
        catalog_file = Path(catalog_path) if catalog_path else _ROOT / "data/cards/standard_current_enUS.json"
        catalog_key = str(catalog_file.resolve())
        runtime = _NATIVE_CATALOG_CACHE.get(catalog_key)
        if runtime is None:
            option_manifest = load_dark_gift_option_manifest(
                _ROOT / "experiments/manaengine/data/pools/dark_gift_launch_review_20261004_v1.json",
                _ROOT / "experiments/manaengine/data/dark_gift_option_metadata.json",
            )
            fire_pool = load_pool_manifest(
                _ROOT / "experiments/manaengine/data/pools/fire_spell_standard_253932_inferred_v1.json",
                expected_profile_id="standard_full_20261001_v1",
                expected_as_of_date="2026-10-01",
                metadata_snapshot_path=_ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json",
                standard_roots_path=_ROOT / "data/cards/standard_roots_20261001_enUS.json",
                expected_metadata_snapshot_id="data/cards/source_snapshots/cards_collectible_20261001_enUS.json",
            )
            rows, metadata = _load_definitions(catalog_path)
            runtime = _NATIVE_CATALOG_CACHE[catalog_key] = _RuntimeCatalog(
                native.CardCatalog(rows, [fire_pool.to_native(native)], fire_pool.metadata_snapshot_id,
                                   fire_pool.metadata_snapshot_sha256, [option_manifest.to_native(native)]), metadata
            )
        # Enrichment always uses this session's own catalog metadata, never whichever catalog was loaded last.
        self._card_metadata = runtime.card_metadata
        # The native constructor owns the reviewed class -> starting Hero Power table; unsupported classes raise a typed failure.
        try:
            self._native = native.GameSession(list(player1_deck), list(player2_deck), runtime.native_catalog,
                                              random_seed, shuffle, player1_class.upper(), player2_class.upper())
        except self._unsupported_exception as exc:
            raise _wrap_native(exc) from exc

    def observation(self, perspective: str = "ACTIVE") -> GameState:
        if perspective not in {"ACTIVE", "PLAYER1", "PLAYER2"}:
            raise ValueError("perspective must be ACTIVE, PLAYER1, or PLAYER2")
        try:
            raw = self._native.observation(perspective)
        except self._unsupported_exception as exc:
            raise _wrap_native(exc) from exc
        return _export_state(dict(raw), self.evidence_constraints, self._card_metadata)

    def legal_actions(self) -> tuple[dict[str, Any], ...]:
        state = self.observation()
        actions = []
        try:
            raw_actions = self._native.legal_actions()
        except self._unsupported_exception as exc:
            raise _wrap_native(exc) from exc
        for raw in raw_actions:
            action = dict(raw)
            if action["type"] in {"PLAY_CARD", "PREPARE_CARD"}:
                hand_index = int(action["hand_index"])
                card = state.self_hand[hand_index]
                action.update({
                    "card_id": card.card_id,
                    "card_type": card.card_type,
                    "card_cost": card.current_cost if card.current_cost is not None else card.cost or 0,
                    "card_spell_damage": card.current_spell_damage or 0,
                    "card_attack": card.attack or 0,
                    "card_health": card.health or 0,
                    "field_position": -1,
                })
            actions.append(action)
        return tuple(actions)

    def _legal_execution_keys(self) -> dict[tuple[str, int, int, int, int, int], dict[str, Any]]:
        """Enumerate canonical native actions, without observation enrichment."""
        try:
            raw_actions = self._native.legal_actions()
        except self._unsupported_exception as exc:
            raise _wrap_native(exc) from exc
        result = {}
        for raw in raw_actions:
            action = dict(raw)
            key = _execution_key(action)
            if key in result:
                raise EngineDefectError("native legal actions contain a duplicate execution key", failure=NativeFailure(
                    FailureKind.ENGINE_DEFECT, "INVARIANT_VIOLATION", "native legal actions contain a duplicate execution key"))
            result[key] = action
        return result

    def _apply_raw(self, action: Mapping[str, Any]) -> None:
        """Apply without exporting an observation; the attempt exports its fixed seat later."""
        try:
            self._native.apply_action_unobserved(dict(action))
        except self._unsupported_exception as exc:
            raise _wrap_native(exc) from exc

    def apply_action(self, action: dict[str, Any]) -> GameState:
        """Mutate this session; return the post-action ACTIVE-seat view (also after END_TURN)."""
        self._apply_raw(action)
        return self.observation("ACTIVE")

    def clone(self) -> "ManaEngineSession":
        duplicate = object.__new__(ManaEngineSession)
        duplicate._unsupported_exception = self._unsupported_exception
        duplicate._card_metadata = self._card_metadata
        try:
            duplicate._native = self._native.clone()
        except self._unsupported_exception as exc:
            raise _wrap_native(exc) from exc
        return duplicate

    @property
    def training_eligible(self) -> bool:
        """No backend-specific complete closure/session evidence producer exists yet."""
        return False

    @property
    def evidence_constraints(self) -> tuple[str, ...]:
        """Sorted session-level evidence debt, separate from player-visible features."""
        return tuple(sorted(self._native.evidence_constraints))

    def require_training_admission(self) -> None:
        """Fail before collecting episodes, rather than filtering unsupported outcomes."""
        require_canonical_training_admission(
            self.evidence_constraints, global_gate_blocked=True
        )

    def set_diagnostic_trace(self, enabled: bool) -> None:
        """Enable the optional native event trace for debugging scenarios."""
        self._native.set_trace_enabled(bool(enabled))

    @property
    def diagnostic_trace(self) -> tuple[str, ...]:
        return tuple(self._native.diagnostic_trace)

    def begin_prototype_choice(self, max_attack: int = 2) -> None:
        """Enter the non-card-specific runtime-derived choice demo scenario."""
        self._native.begin_prototype_choice(max_attack)

    def _poison_checked(self, name: str) -> Any:
        """Read a native state accessor; a poisoned session is never a usable state."""
        try:
            return getattr(self._native, name)
        except self._unsupported_exception as exc:
            raise _wrap_native(exc) from exc

    @property
    def choice_options(self) -> tuple[int, ...]:
        return tuple(self._poison_checked("choice_options"))

    @property
    def is_complete(self) -> bool:
        return bool(self._poison_checked("is_complete"))

    @property
    def is_valid(self) -> bool:
        return bool(self._native.is_valid)

    @property
    def failure(self) -> NativeFailure | None:
        raw = getattr(self._native, "failure", None)
        return _failure_from_native(raw) if raw is not None else None

    @property
    def unsupported_outcome(self) -> str | None:
        return self._native.unsupported_outcome

    @property
    def needs_choice(self) -> bool:
        return bool(self._poison_checked("needs_choice"))

    @property
    def result(self) -> str | None:
        return self._poison_checked("result")

    @property
    def seed(self) -> int:
        return int(self._native.seed)
