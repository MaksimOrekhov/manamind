"""Which cards ManaEngine does not support, and where a card sits in the pinned registry.

The authoritative source is an exported *effective* support inventory (not produced here). Until
one exists the declaration file is used as a ``DECLARATION_PROXY``: it is only a proxy, in
either direction (a declared card can be downgraded by contract review; engine-native cards
without a declaration look unsupported), and the basis is a mandatory field of every record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SUPPORT_STATES = frozenset({
    "SUPPORTED", "VERIFIED_VANILLA", "UNSUPPORTED_DECLARED", "UNSUPPORTED_NO_DECLARATION",
    "UNSUPPORTED_CONTRACT_UNREVIEWED", "UNSUPPORTED_DEPENDENCY", "NOT_IN_ENGINE_CATALOG",
    "UNKNOWN_INVENTORY_MISSING",
})
SUPPORTED_STATES = frozenset({"SUPPORTED", "VERIFIED_VANILLA"})

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ABILITIES = REPO_ROOT / "experiments" / "manaengine" / "data" / "card_abilities.json"
DEFAULT_REGISTRY = REPO_ROOT / "data" / "cards" / "standard_registry_20261001_enUS.json"


class InventoryError(ValueError):
    """Raised with a stable message that never contains log text."""


def file_sha256(path: Path | None) -> str:
    if path is None:
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SupportInventory:
    def __init__(self, inventory_id: str, sha256: str, basis: str, states: dict[str, str]) -> None:
        self.inventory_id = inventory_id
        self.sha256 = sha256
        self.basis = basis
        self._states = states

    def state(self, card_id: str) -> str:
        known = self._states.get(card_id)
        if known is not None:
            return known
        return "NOT_IN_ENGINE_CATALOG" if self.basis == "ENGINE_EFFECTIVE_INVENTORY" else (
            "UNSUPPORTED_NO_DECLARATION"
        )

    def is_supported(self, card_id: str) -> bool:
        return self.state(card_id) in SUPPORTED_STATES


def load_inventory(path: Path | None = None, abilities_path: Path | None = None) -> SupportInventory:
    """``path``: exported inventory ``{inventory_id, cards: {id: {state, reason}}}``; otherwise the
    declaration file as a proxy."""
    if path is not None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        cards = payload.get("cards") if isinstance(payload, dict) else None
        if not isinstance(cards, dict) or not isinstance(payload.get("inventory_id"), str):
            raise InventoryError("INVENTORY_SHAPE")
        states: dict[str, str] = {}
        for card_id, record in cards.items():
            state = record.get("state") if isinstance(record, dict) else None
            if state not in SUPPORT_STATES:
                raise InventoryError("INVENTORY_STATE")
            states[card_id] = state
        return SupportInventory(payload["inventory_id"], file_sha256(Path(path)),
                                "ENGINE_EFFECTIVE_INVENTORY", states)
    abilities = Path(abilities_path) if abilities_path is not None else DEFAULT_ABILITIES
    declared = json.loads(abilities.read_text(encoding="utf-8")).get("cards", {})
    mapping = {"SUPPORTED": "SUPPORTED", "VERIFIED_VANILLA": "VERIFIED_VANILLA"}
    states = {
        card_id: mapping.get(record.get("support_state"), "UNSUPPORTED_DECLARED")
        for card_id, record in declared.items()
    }
    digest = file_sha256(abilities)
    return SupportInventory(f"declaration-proxy/{digest[:12]}", digest, "DECLARATION_PROXY", states)


class ScopeResolver:
    """Registry scope of a card id from the pinned registry (and optional collectible metadata)."""

    def __init__(self, roots: frozenset[str] = frozenset(), dependency_nodes: frozenset[str] = frozenset(),
                 collectible: frozenset[str] = frozenset(), known: frozenset[str] = frozenset()) -> None:
        self._roots = roots
        self._nodes = dependency_nodes
        self._collectible = collectible
        self._known = known

    @classmethod
    def from_files(cls, registry: Path | None, metadata: Path | None = None) -> ScopeResolver:
        roots: frozenset[str] = frozenset()
        nodes: frozenset[str] = frozenset()
        if registry is not None and Path(registry).exists():
            data = json.loads(Path(registry).read_text(encoding="utf-8"))
            roots = frozenset(data.get("cards", {}))
            nodes = frozenset(data.get("dependency_graph", {}).get("nodes", []))
        collectible: set[str] = set()
        known: set[str] = set()
        if metadata is not None and Path(metadata).exists():
            payload = json.loads(Path(metadata).read_text(encoding="utf-8-sig"))
            records = payload.get("cards", []) if isinstance(payload, dict) else payload
            for record in records:
                card_id = record.get("id")
                if card_id:
                    known.add(card_id)
                    if record.get("collectible"):
                        collectible.add(card_id)
        return cls(roots, nodes, frozenset(collectible), frozenset(known))

    def scope(self, card_id: str) -> str:
        if card_id in self._roots:
            return "STANDARD_ROOT"
        if card_id in self._nodes:
            return "DEPENDENCY_NODE"
        if card_id in self._collectible:
            return "COLLECTIBLE_NOT_STANDARD_ROOT"
        if card_id in self._known:
            return "NON_COLLECTIBLE"
        return "UNKNOWN_ID"
