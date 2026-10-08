"""Read-only view of which cards ManaEngine can execute, derived from its declarations.

ENGINE-STATE-IMPORT-0 diagnostic helper. It never loads the native module and never keeps a
second list of supported card IDs: support comes from ``card_abilities.json`` plus the same
authoring guards ``engine._load_definitions`` applies (reviewed rules text, dependency closure).
This is a declaration-level view: it does not prove that the native build was compiled from
these declarations and it is not rules verification.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from manamind.cards.catalog import CardCatalog
from manamind.integrations.manaengine.engine import _rules_coverage

ROOT = Path(__file__).resolve().parents[4]
ABILITIES_FILE = "experiments/manaengine/data/card_abilities.json"
CATALOG_FILE = "data/cards/standard_current_enUS.json"
PINNED_SNAPSHOT_FILE = "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
LEGACY_CARDS_FILE = "vendor/RosettaStone/Resources/cards.json"
# Same files, same order, as `engine._load_definitions`; a test keeps the two lists identical.
DEPENDENCY_FILES = (
    "experiments/manaengine/data/dependency_metadata_audit.json",
    "experiments/manaengine/data/fixed_summon_dependency_metadata.json",
    "experiments/manaengine/data/summon_condition_dependencies.json",
    "experiments/manaengine/data/overload_dependency_metadata.json",
    "experiments/manaengine/data/dark_gift_option_metadata.json",
    "experiments/manaengine/data/choice_mode_dependency_metadata.json",
    "experiments/manaengine/data/colossal_appendage_dependency_metadata.json",
    "experiments/manaengine/data/quick1_dependency_metadata.json",
    "experiments/manaengine/data/quick2_dependency_metadata.json",
    "experiments/manaengine/data/hero_power_dependency_metadata.json",
)
_SUPPORTED = ("SUPPORTED", "VERIFIED_VANILLA")
_DRAW_ABILITIES = {"DEATHRATTLE_DRAW", "HERO_ATTACK_DRAW"}
_DAMAGE_ABILITIES = {"TARGET_DAMAGE", "RANDOM_MISSILES", "LIFESTEAL_DAMAGE", "MINION_DAMAGE_GENERATE"}


@dataclass(frozen=True, slots=True)
class CardCapability:
    """Declaration-level execution status of one card ID. ``reason`` explains a non-supported status."""

    card_id: str
    card_type: str | None
    supported: bool
    reason: str
    declared_state: str | None = None
    evidence_constraints: tuple[str, ...] = ()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _rows(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("cards", []) if isinstance(payload, dict) else payload
    return [row for row in rows if isinstance(row, dict)]


class CapabilityIndex:
    """Answers "can ManaEngine execute this card ID" from declarations and pinned metadata."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else ROOT
        files = [self.root / ABILITIES_FILE, self.root / CATALOG_FILE, *(self.root / name for name in DEPENDENCY_FILES)]
        self._fingerprint = hashlib.sha256(b"".join(
            hashlib.sha256(path.read_bytes()).digest() for path in files
        )).hexdigest()
        self._overrides: dict[str, dict[str, Any]] = _read_json(self.root / ABILITIES_FILE)["cards"]
        self._metadata, self._record_ids = self._load_metadata()
        self._effective = self._resolve_support()

    @property
    def fingerprint(self) -> str:
        """Hash of the declaration and metadata inputs, to tell which capability view produced a result."""
        return self._fingerprint

    def _load_metadata(self) -> tuple[dict[str, dict[str, Any]], set[str]]:
        catalog_rows = _rows(_read_json(self.root / CATALOG_FILE))
        record_ids = {card.card_id for card in CardCatalog.from_json(self.root / CATALOG_FILE)}
        pinned = {str(row["id"]): row for row in _read_json(self.root / PINNED_SNAPSHOT_FILE)}
        pinned.update({str(row["id"]): row for row in catalog_rows})
        for name in DEPENDENCY_FILES:
            for row in _read_json(self.root / name)["cards"]:
                pinned[str(row["id"])] = row
                record_ids.add(str(row["id"]))
        return pinned, record_ids

    def _guard_metadata(self) -> dict[str, dict[str, Any]]:
        """Metadata for the rules-text guard, as the engine builds it: the optional legacy RosettaStone dump fills gaps only.

        Kept apart from ``_metadata`` so that which identities count as "described by pinned metadata" does not depend on
        whether the vendored submodule happens to be checked out (a diagnostic must give the same answer on every machine).
        """
        merged = dict(self._metadata)
        legacy = self.root / LEGACY_CARDS_FILE
        if legacy.exists():
            for row in _read_json(legacy):
                merged.setdefault(str(row["id"]), row)
        return merged

    def _dependencies(self, spec: dict[str, Any]) -> list[str]:
        steps = [*spec.get("effects", ()), *spec.get("choose_one_a", ()), *spec.get("choose_one_b", ())]
        deps = [spec.get("shatter_left_card", ""), spec.get("shatter_right_card", ""), spec.get("transform_card", ""),
                *spec.get("colossal_appendages", ()), *(step.get("summon_card", "") for step in steps)]
        return [str(dep) for dep in deps if dep]

    def _resolve_support(self) -> dict[str, tuple[str, str]]:
        """card_id -> (state, reason) with the engine's two guards, in the engine's sorted single pass."""
        state: dict[str, tuple[str, str]] = {}
        guard_metadata = self._guard_metadata()
        for card_id in sorted(self._record_ids):
            spec = self._overrides.get(card_id)
            raw = guard_metadata.get(card_id)
            if spec is None:
                state[card_id] = ("UNSUPPORTED", "UNDECLARED")
            elif spec.get("support_state", "UNSUPPORTED") not in _SUPPORTED:
                state[card_id] = ("UNSUPPORTED", "DECLARED_UNSUPPORTED")
            elif raw is None:
                state[card_id] = ("UNSUPPORTED", "METADATA_MISSING")
            elif not _rules_coverage(raw, spec):
                state[card_id] = ("UNSUPPORTED", "RULES_TEXT_GUARD_FAILED")
            else:
                state[card_id] = (str(spec["support_state"]), "SUPPORTED")
        for card_id in sorted(self._record_ids):
            if any(dep not in state or state[dep][0] == "UNSUPPORTED" for dep in self._dependencies(self._overrides.get(card_id, {}))):
                state[card_id] = ("UNSUPPORTED", "DEPENDENCY_UNSUPPORTED")
        return state

    def card(self, card_id: str) -> CardCapability:
        raw = self._metadata.get(card_id)
        card_type = str(raw["type"]).upper() if raw and raw.get("type") else None
        if card_id not in self._effective:
            return CardCapability(card_id, card_type, False, "NOT_IN_CATALOG")
        status, reason = self._effective[card_id]
        spec = self._overrides.get(card_id, {})
        constraints = tuple(sorted({str(step["evidence_constraint"]) for step in spec.get("effects", ()) if "evidence_constraint" in step}))
        return CardCapability(card_id, card_type, status != "UNSUPPORTED", reason, spec.get("support_state"), constraints)

    @property
    def declared_card_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._overrides))

    def has_metadata(self, card_id: str) -> bool:
        """True when the pinned snapshot, the catalog or a pinned dependency capture describes the identity."""
        return card_id in self._metadata

    def printed_cost(self, card_id: str) -> int | None:
        raw = self._metadata.get(card_id)
        return int(raw["cost"]) if raw and raw.get("cost") is not None else None

    @cached_property
    def supported_hero_power_ids(self) -> frozenset[str]:
        return frozenset(card_id for card_id in self._effective if self.card(card_id).supported and self.card(card_id).card_type == "HERO_POWER")

    def summary(self) -> dict:
        """Counts for reports: declarations, effective support after the engine's guards, and the reason split."""
        cards = [self.card(card_id) for card_id in sorted(self._record_ids)]
        supported = [c for c in cards if c.supported]
        reasons: dict[str, int] = {}
        for c in cards:
            if not c.supported:
                reasons[c.reason] = reasons.get(c.reason, 0) + 1
        return {
            "fingerprint": self.fingerprint,
            "engine_catalog_records": len(cards),
            "declarations": len(self._overrides),
            "effectively_supported_non_hero_power": sum(1 for c in supported if c.card_type != "HERO_POWER"),
            "effectively_supported_hero_powers": sorted(c.card_id for c in supported if c.card_type == "HERO_POWER"),
            "unsupported_by_reason": dict(sorted(reasons.items())),
            "basis": "declaration-level view; native build not loaded; not rules verification",
        }

    def has_effect(self, card_id: str, effect_class: str) -> bool:
        """Whether the declaration provably contains a DRAW / HEAL / SPELL_DAMAGE effect. Declared cards only."""
        spec = self._overrides.get(card_id)
        if spec is None:
            return False
        steps = [*spec.get("effects", ()), *spec.get("choose_one_a", ()), *spec.get("choose_one_b", ())]
        kinds = {str(step.get("kind", "")).upper() for step in steps}
        ability = str(spec.get("ability", "NONE")).upper()
        raw = self._metadata.get(card_id) or {}
        if effect_class == "DRAW":
            return bool("DRAW" in kinds or ability in _DRAW_ABILITIES or spec.get("deck_draw_filter")
                        or spec.get("deathrattle_draw_count") or spec.get("damage_outcome_followup") in ("DRAW_SELF", "DRAW_TARGET_OWNER"))
        if effect_class == "HEAL":
            return bool(kinds & {"HEAL", "HEAL_MINION_TO_FULL"} or ability == "LIFESTEAL_DAMAGE" or spec.get("lifesteal")
                        or "LIFESTEAL" in raw.get("mechanics", ()) or spec.get("damage_outcome_followup") == "HEAL_ENEMY_HERO")
        if effect_class == "SPELL_DAMAGE":
            return bool(str(raw.get("type", "")).upper() == "SPELL" and ("DAMAGE" in kinds or ability in _DAMAGE_ABILITIES or spec.get("damage")))
        raise ValueError(f"unknown effect class: {effect_class}")
