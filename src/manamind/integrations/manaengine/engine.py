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
    global _CARD_METADATA
    native = _load_native()
    catalog_file = Path(catalog_path) if catalog_path else _ROOT / "data/cards/standard_current_enUS.json"
    key = str(catalog_file.resolve())
    if key in _DEFINITION_CACHE:
        rows, metadata = _DEFINITION_CACHE[key]
        _CARD_METADATA = metadata
        return rows
    catalog = CardCatalog.from_json(catalog_file)
    extras = {
        "EX1_277": CardFeatures(card_id="EX1_277", cost=1, card_type="SPELL", card_class="MAGE"),
        "SW_108t": CardFeatures(card_id="SW_108t", cost=1, card_type="SPELL", card_class="MAGE"),
        "HERO_08bp": CardFeatures(card_id="HERO_08bp", cost=2, attack=0, health=0, durability=0, card_type="HERO_POWER", card_class="MAGE"),
    }
    records = {c.card_id: c for c in catalog}
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
        d.cost = card.cost or 0
        d.attack = card.attack or 0
        d.health = card.health or 0
        d.durability = card.durability or 0
        d.rush = "RUSH" in card.mechanics
        d.taunt = "TAUNT" in card.mechanics
        spec = overrides.get(card.card_id, {})
        for key, value in spec.items():
            setattr(d, key, value)
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
            mechanics = {str(item).upper() for item in (base.mechanics or ())}
            for field, mechanic in (
                ("taunt", "TAUNT"), ("divine_shield", "DIVINE_SHIELD"), ("stealth", "STEALTH"),
                ("charge", "CHARGE"), ("windfury", "WINDFURY"),
                ("lifesteal", "LIFESTEAL"), ("poisonous", "POISONOUS"), ("reborn", "REBORN"),
                ("dormant", "DORMANT"), ("immune", "IMMUNE"),
                ("cant_be_targeted_by_spells", "CANT_BE_TARGETED_BY_SPELLS"),
                ("cant_be_targeted_by_hero_powers", "CANT_BE_TARGETED_BY_HERO_POWERS"),
            ):
                row[field] = mechanic in mechanics
        if in_hand:
            if str(row.get("card_type", "")).upper() == "MINION":
                row["current_attack"] = row.get("attack")
                row["current_health"] = row.get("health")
            else:
                row["current_attack"] = None
                row["current_health"] = None
            row["current_durability"] = None

    for player_key in ("self_player", "opponent"):
        player = raw[player_key]
        player.setdefault("hero_divine_shield", False)
        for card in player.get("board", ()):
            enrich(card)
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
        for raw in self._native.legal_actions():
            action = dict(raw)
            if action["type"] == "PLAY_CARD":
                hand_index = int(action["hand_index"])
                card = state.self_hand[hand_index]
                action.update({
                    "card_id": card.card_id,
                    "card_type": card.card_type,
                    "card_cost": card.current_cost if card.current_cost is not None else card.cost or 0,
                    "card_attack": card.attack or 0,
                    "card_health": card.health or 0,
                    "field_position": -1,
                })
            actions.append(action)
        return tuple(actions)

    def apply_action(self, action: dict[str, Any]) -> GameState:
        return _export_state(dict(self._native.apply_action(dict(action))))

    def clone(self) -> "ManaEngineSession":
        duplicate = object.__new__(ManaEngineSession)
        duplicate._native = self._native.clone()
        return duplicate

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
    def needs_choice(self) -> bool:
        return bool(self._native.needs_choice)

    @property
    def result(self) -> str | None:
        return self._native.result

    @property
    def seed(self) -> int:
        return int(self._native.seed)
