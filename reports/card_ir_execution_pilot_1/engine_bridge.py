"""Execute translated Card IR through the existing ManaEngine (CARD-IR-EXECUTION-PILOT-1, experimental).

The bridge adds no rule and no card handler. It (1) gates a declaration through strict v0.2 acceptance and the pure
translator, (2) builds a *fresh* native ``CardDefinition`` for that card from pinned metadata plus the translated steps
only - the card's legacy declaration in ``card_abilities.json`` is not read for it - and (3) starts an ordinary
prototype session over a catalog in which that row replaces the legacy one. Everything else (legality, damage and
healing pipelines, deaths, Overload, failure funnel, clones, attempts) is unchanged ManaEngine.

Execution here is not rules verification and never training admission: sessions keep
``training_eligible == False`` and attempts keep the ordinary ``SimulationAttempt`` outcomes.

Location: this is pilot research code, deliberately outside ``src/``. The package rules keep ``manamind.card_ir`` and
``manamind.card_metadata`` isolated (nothing else in ``src/`` may import them), and this bridge needs both plus the
ManaEngine adapter. Moving it into ``src/`` would need an explicit decision to change that boundary.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from manamind.card_ir.engine_translate import EngineSpec, TranslationRefused, translate
from manamind.card_ir.strict_v02 import validate_strict_v02
from manamind.card_metadata.snapshot import strip_text_artifacts
from manamind.domain.card import CardFeatures
from manamind.integrations.manaengine.engine import (
    _ROOT, ManaEngineSession, _load_definitions, _load_native, _parse_effect_steps, _wrap_native,
)
from manamind.integrations.manaengine.pool_manifest import load_dark_gift_option_manifest, load_pool_manifest

# The engine's own pinned metadata snapshot (the one `_load_definitions` reads); the IR text must equal its card text.
_ENGINE_SNAPSHOT = _ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
# Metadata-only fields copied from the engine's catalog row; every behaviour field comes from the translated spec.
_METADATA_FIELDS = ("card_id", "name", "card_type", "card_class", "race", "spell_school", "collectible", "cost", "attack",
                    "health", "durability", "minion_types")


def compile_declaration(doc: Mapping[str, Any], meta: Any) -> EngineSpec:
    """Strict v0.2 acceptance (FULL, no errors or warnings), then translation. Both gates fail closed."""
    report = validate_strict_v02(doc, meta)
    if not report.accepted or report.status != "FULL":
        detail = "; ".join([*report.errors, *report.warnings]) or f"status {report.status}"
        raise TranslationRefused("VALIDATION", "doc", detail)
    return translate(doc)


@dataclass(frozen=True)
class IRCatalog:
    """A native catalog in which each installed spec replaces its card's legacy row, plus that catalog's metadata."""

    native_catalog: Any
    card_metadata: Mapping[str, CardFeatures]
    installed: Mapping[str, EngineSpec]


def _engine_texts() -> dict[str, str]:
    rows = json.loads(_ENGINE_SNAPSHOT.read_text(encoding="utf-8"))
    return {str(row["id"]): str(row.get("text", "")) for row in rows}


def _definition(native: Any, spec: EngineSpec, base: Any, engine_text: str | None) -> Any:
    if base.card_type != "SPELL":
        raise TranslationRefused("CARD_TYPE", "doc/card_id", "only spells are executable in this pilot")
    if engine_text is None or hashlib.sha256(strip_text_artifacts(engine_text).encode("utf-8")).hexdigest() != spec.text_sha256:
        raise TranslationRefused("ENGINE_TEXT_MISMATCH", "doc/text", "the engine's pinned card text differs from the IR text")
    row = native.CardDefinition()
    for name in _METADATA_FIELDS:
        setattr(row, name, getattr(base, name))
    # Rebuild the card's printed mechanics: the engine row omits OVERLOAD exactly when its metadata carries an amount.
    mechanics = list(base.required_mechanics) + (["OVERLOAD"] if base.overload > 0 else [])
    row.required_mechanics = [m for m in mechanics if m != "OVERLOAD" or spec.overload <= 0]
    row.overload = spec.overload
    row.ability = spec.ability
    try:
        row.effects = _parse_effect_steps(native, spec.card_id, [step.declaration() for step in spec.steps])
    except ValueError as exc:
        raise TranslationRefused("ENGINE_STEP_REJECTED", "doc", str(exc)) from exc
    row.support_state = "SUPPORTED"
    # The engine's authoring guard: reviewed text equals card text. Here that is the strict IR text check above.
    row.rules_contract_reviewed = True
    return row


def build_catalog(specs: Iterable[EngineSpec]) -> IRCatalog:
    """Fresh native catalog: ordinary rows for every card, translated rows for the installed specs."""
    native = _load_native()
    installed = {}
    for spec in specs:
        if spec.card_id in installed:
            raise TranslationRefused("DUPLICATE_CARD", "doc/card_id", "one spec per card")
        installed[spec.card_id] = spec
    rows, metadata = _load_definitions()
    by_id = {row.card_id: i for i, row in enumerate(rows)}
    texts = _engine_texts()
    for card_id, spec in installed.items():
        if card_id not in by_id:
            raise TranslationRefused("CARD_NOT_IN_ENGINE_CATALOG", "doc/card_id", card_id)
        rows[by_id[card_id]] = _definition(native, spec, rows[by_id[card_id]], texts.get(card_id))
    # Same pool manifests as ManaEngineSession uses for its default catalog.
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
    try:
        catalog = native.CardCatalog(rows, [fire_pool.to_native(native)], fire_pool.metadata_snapshot_id,
                                     fire_pool.metadata_snapshot_sha256, [option_manifest.to_native(native)])
    except ValueError as exc:  # native catalog validation (unrepresented mechanic, malformed step, ...)
        raise TranslationRefused("ENGINE_CATALOG_REJECTED", "doc", str(exc)) from exc
    return IRCatalog(catalog, metadata, MappingProxyType(installed))


def start_session(catalog: IRCatalog, player1_deck: Sequence[str], player2_deck: Sequence[str], *,
                  player1_class: str, player2_class: str, shuffle: bool = False, random_seed: int = 0) -> ManaEngineSession:
    """An ordinary prototype session over `catalog`; same construction as ``ManaEngineSession.__init__``."""
    native = _load_native()
    session = object.__new__(ManaEngineSession)
    session._unsupported_exception = native.UnsupportedSimulationError
    session._card_metadata = catalog.card_metadata
    try:
        session._native = native.GameSession(list(player1_deck), list(player2_deck), catalog.native_catalog,
                                             random_seed, shuffle, player1_class.upper(), player2_class.upper())
    except native.UnsupportedSimulationError as exc:
        raise _wrap_native(exc) from exc
    return session
