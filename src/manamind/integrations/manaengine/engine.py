"""Adapter from the experimental C++ ManaEngine to ManaMind's public domain."""
from __future__ import annotations

import importlib.util
import json
import os
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

from manamind.cards.catalog import CardCatalog
from manamind.domain.card import CardFeatures
from manamind.domain.game_state import GameState
from manamind.domain.serialization import game_state_from_dict

_NATIVE: ModuleType | None = None
_ROOT = Path(__file__).resolve().parents[4]
_CARD_METADATA: dict[str, CardFeatures] = {}
_DEFINITION_CACHE: dict[str, tuple[list[Any], dict[str, CardFeatures]]] = {}
_NATIVE_CATALOG_CACHE: dict[str, Any] = {}
_COLLECTIBLE_IDS: set[str] = set()


class UnsupportedSimulationError(RuntimeError):
    """The requested branch reached card behavior without a verified implementation."""


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


def _definition_rows(catalog_path: str | Path | None = None) -> list[Any]:
    global _CARD_METADATA, _COLLECTIBLE_IDS
    native = _load_native()
    catalog_file = Path(catalog_path) if catalog_path else _ROOT / "data/cards/standard_current_enUS.json"
    key = str(catalog_file.resolve())
    if key in _DEFINITION_CACHE:
        rows, metadata = _DEFINITION_CACHE[key]
        _CARD_METADATA = metadata
        return rows
    catalog = CardCatalog.from_json(catalog_file)
    raw_catalog = json.loads(catalog_file.read_text(encoding="utf-8-sig"))
    raw_cards = raw_catalog.get("cards", []) if isinstance(raw_catalog, dict) else raw_catalog
    spell_schools = {
        str(row.get("id") or row.get("card_id") or row.get("dbfId")): str(row.get("spellSchool") or "").upper()
        for row in raw_cards
        if isinstance(row, dict)
    }
    _COLLECTIBLE_IDS = {
        str(row.get("id") or row.get("card_id") or row.get("dbfId"))
        for row in raw_cards
        if isinstance(row, dict) and row.get("collectible") is True
    }
    extras = {
        "EX1_277": CardFeatures(card_id="EX1_277", cost=1, card_type="SPELL", card_class="MAGE"),
        "SW_108t": CardFeatures(card_id="SW_108t", cost=1, card_type="SPELL", card_class="MAGE"),
        "CORE_SW_108t": CardFeatures(card_id="CORE_SW_108t", cost=1, card_type="SPELL", card_class="MAGE"),
        "JAIL_801t": CardFeatures(card_id="JAIL_801t", cost=3, attack=3, health=3, card_type="MINION", card_class="SHAMAN", race="ELEMENTAL"),
        "JAIL_803t": CardFeatures(card_id="JAIL_803t", cost=5, attack=5, health=5, card_type="MINION", card_class="SHAMAN", race="ELEMENTAL"),
        "JAIL_805t": CardFeatures(card_id="JAIL_805t", cost=7, attack=7, health=7, card_type="MINION", card_class="SHAMAN", race="ELEMENTAL", mechanics=("LIFESTEAL",)),
        "TEST_HELD_TRACKER": CardFeatures(card_id="TEST_HELD_TRACKER", cost=2, attack=4, health=4, card_type="MINION", card_class="MAGE"),
        "HERO_08bp": CardFeatures(card_id="HERO_08bp", cost=2, attack=0, health=0, durability=0, card_type="HERO_POWER", card_class="MAGE"),
        "CATA_489t": CardFeatures(card_id="CATA_489t", cost=4, card_type="SPELL", card_class="MAGE"),
        "CATA_489t2": CardFeatures(card_id="CATA_489t2", cost=4, card_type="SPELL", card_class="MAGE"),
        "CORE_CS2_033": CardFeatures(card_id="CORE_CS2_033", cost=4, attack=3, health=6, card_type="MINION", card_class="MAGE", race="ELEMENTAL"),
        "EX1_100t": CardFeatures(card_id="EX1_100t", cost=1, attack=1, health=1, card_type="MINION", card_class="MAGE"),
    }
    records = {c.card_id: c for c in catalog}
    records.update({key: records.get(key, value) for key, value in extras.items()})
    config = json.loads((_ROOT / "experiments/manaengine/data/card_abilities.json").read_text(encoding="utf-8"))
    overrides = config["cards"]
    effect_kinds = {"DAMAGE", "DRAW", "GAIN_ARMOR", "MODIFY_HERO_ATTACK", "FREEZE"}
    target_selectors = {"EXPLICIT_CHARACTER", "EXPLICIT_ENEMY_CHARACTER", "EXPLICIT_MINION", "ENEMY_MINIONS", "ENEMY_CHARACTERS", "ALL_CHARACTERS", "SELF"}
    result = []
    for card in sorted(records.values(), key=lambda c: c.card_id):
        d = native.CardDefinition()
        d.card_id = card.card_id
        d.name = card.card_id
        d.card_type = card.card_type.upper()
        d.card_class = card.card_class.upper()
        d.race = (card.race or "").upper()
        d.spell_school = spell_schools.get(card.card_id, "")
        d.collectible = card.card_id in _COLLECTIBLE_IDS
        d.battlecry = "BATTLECRY" in card.mechanics
        d.secret = "SECRET" in card.mechanics
        d.cost = card.cost or 0
        d.attack = card.attack or 0
        d.health = card.health or 0
        d.durability = card.durability or 0
        d.rush = "RUSH" in card.mechanics
        d.taunt = "TAUNT" in card.mechanics
        spec = overrides.get(card.card_id, {})
        d.support_state = str(spec.get("support_state", "UNSUPPORTED"))
        d.ability = str(spec.get("ability", "NONE"))
        if "deck_draw_filter" in spec:
            filters = {"ANY": "ANY", "SPELL": "SPELL", "FIRE_SPELL": "FIRE_SPELL"}
            filter_name = str(spec["deck_draw_filter"]).upper()
            if filter_name not in filters:
                raise ValueError(f"unknown deck_draw_filter for {card.card_id}: {filter_name}")
            d.deck_draw_filter = getattr(native.DeckDrawFilter, filters[filter_name])
        for key, value in spec.items():
            if key not in {"support_state", "ability", "effects", "deck_draw_filter"}:
                setattr(d, key, value)
        raw_effects = spec.get("effects", [])
        if not isinstance(raw_effects, list):
            raise ValueError(f"effects must be a list for {card.card_id}")
        native_effects = []
        for effect in raw_effects:
            if not isinstance(effect, dict) or not {"kind", "target", "amount"} <= set(effect) or set(effect) - {"kind", "target", "amount", "lifesteal"}:
                raise ValueError(f"effect requires kind, target, amount, and optional lifesteal for {card.card_id}")
            kind = str(effect["kind"]).upper()
            target = str(effect["target"]).upper()
            if kind not in effect_kinds or target not in target_selectors:
                raise ValueError(f"unknown effect kind/target for {card.card_id}: {kind}/{target}")
            native_effect = native.EffectStep()
            native_effect.kind = getattr(native.EffectKind, kind)
            native_effect.target = getattr(native.TargetSelector, target)
            native_effect.amount = int(effect["amount"])
            native_effect.lifesteal = bool(effect.get("lifesteal", False))
            native_effects.append(native_effect)
        d.effects = native_effects
        result.append(d)
    _CARD_METADATA = records
    _DEFINITION_CACHE[key] = (result, records)
    return result


def _export_state(raw: dict[str, Any]) -> GameState:
    """Adapt engine observations to the shared domain schema and catalog metadata."""
    def enrich(row: dict[str, Any], *, in_hand: bool = False) -> None:
        base = _CARD_METADATA.get(str(row.get("card_id", "")))
        if base is not None:
            row["race"] = base.race
            row["mechanics"] = list(base.mechanics)
        if in_hand:
            if str(row.get("card_type", "")).upper() == "MINION":
                row["current_attack"] = row.get("attack")
                row["current_health"] = row.get("health")
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
        for secret in player.get("known_secrets", ()):
            enrich(secret)
        if player.get("hero_power") is not None:
            enrich(player["hero_power"], in_hand=True)
        if player.get("weapon") is not None:
            enrich(player["weapon"])
    for card in raw.get("self_hand", ()):
        enrich(card, in_hand=True)
    return game_state_from_dict(raw)


class ManaEngineSession:
    """Persistent prototype match. Internal state is private to the C++ backend."""

    def __init__(self, player1_deck: Sequence[str], player2_deck: Sequence[str], *,
                 player1_class: str = "UNKNOWN_CLASS", player2_class: str = "UNKNOWN_CLASS",
                 shuffle: bool = True, random_seed: int = 0, catalog_path: str | Path | None = None) -> None:
        native = _load_native()
        self._unsupported_exception = native.UnsupportedSimulationError
        catalog_file = Path(catalog_path) if catalog_path else _ROOT / "data/cards/standard_current_enUS.json"
        catalog_key = str(catalog_file.resolve())
        if catalog_key not in _NATIVE_CATALOG_CACHE:
            _NATIVE_CATALOG_CACHE[catalog_key] = native.CardCatalog(_definition_rows(catalog_path))
        else:
            _definition_rows(catalog_path)
        self._native = native.GameSession(list(player1_deck), list(player2_deck), _NATIVE_CATALOG_CACHE[catalog_key],
                                          random_seed, shuffle, player1_class, player2_class)

    def observation(self, perspective: str = "ACTIVE") -> GameState:
        if perspective not in {"ACTIVE", "PLAYER1", "PLAYER2"}:
            raise ValueError("perspective must be ACTIVE, PLAYER1, or PLAYER2")
        return _export_state(dict(self._native.observation(perspective)))

    def legal_actions(self) -> tuple[dict[str, Any], ...]:
        state = self.observation()
        actions = []
        try:
            raw_actions = self._native.legal_actions()
        except self._unsupported_exception as exc:
            raise UnsupportedSimulationError(str(exc)) from exc
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

    def apply_action(self, action: dict[str, Any]) -> GameState:
        try:
            raw = self._native.apply_action(dict(action))
        except self._unsupported_exception as exc:
            raise UnsupportedSimulationError(str(exc)) from exc
        return _export_state(dict(raw))

    def clone(self) -> "ManaEngineSession":
        duplicate = object.__new__(ManaEngineSession)
        duplicate._unsupported_exception = self._unsupported_exception
        duplicate._native = self._native.clone()
        return duplicate

    def set_diagnostic_trace(self, enabled: bool) -> None:
        """Enable the optional native event trace for debugging scenarios."""
        self._native.set_trace_enabled(bool(enabled))

    @property
    def diagnostic_trace(self) -> tuple[str, ...]:
        return tuple(self._native.diagnostic_trace)

    def begin_prototype_choice(self, max_attack: int = 2) -> None:
        """Enter the non-card-specific runtime-derived choice demo scenario."""
        self._native.begin_prototype_choice(max_attack)

    @property
    def choice_options(self) -> tuple[int, ...]:
        return tuple(self._native.choice_options)

    @property
    def is_complete(self) -> bool:
        return bool(self._native.is_complete)

    @property
    def is_valid(self) -> bool:
        return bool(self._native.is_valid)

    @property
    def unsupported_outcome(self) -> str | None:
        return self._native.unsupported_outcome

    @property
    def needs_choice(self) -> bool:
        return bool(self._native.needs_choice)

    @property
    def result(self) -> str | None:
        return self._native.result

    @property
    def seed(self) -> int:
        return int(self._native.seed)
