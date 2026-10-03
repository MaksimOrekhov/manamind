from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from manamind.cards.catalog import CardCatalog
from manamind.integrations.manaengine import ManaEngineSession
from manamind.integrations.rosettastone.rosettastone import SimulatorSession, validate_deck

ROOT = Path(__file__).resolve().parents[3]
REFERENCE_ROOTS = ("CORE_DRG_107", "CORE_SW_108", "CORE_CS2_024", "CORE_CS2_029")


def _without_catalog_mechanics(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_catalog_mechanics(item)
            for key, item in value.items()
            # Rosetta's current bridge does not export hero-freeze state, and
            # ManaEngine intentionally reports unknown hero shield where it has
            # no implementation. Compare the shared observation contract only.
            if key not in {
                "mechanics", "hero_frozen", "hero_divine_shield",
                "cant_be_targeted_by_spells", "cant_be_targeted_by_hero_powers",
            }
            and not (key == "current_durability" and value.get("card_type") != "WEAPON")
        }
    if isinstance(value, (list, tuple)):
        return [_without_catalog_mechanics(item) for item in value]
    return value


def _make_deck() -> list[str]:
    selection = json.loads((ROOT / "experiments/manaengine/data/root_selection.json").read_text(encoding="utf-8"))
    selected_ids = {row["card_id"] for row in selection["cards"]}
    if any(card_id not in selected_ids for card_id in REFERENCE_ROOTS):
        raise RuntimeError("Reference fixture roots are no longer in the current Tier A/B selection")

    catalog = {card.card_id: card for card in CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")}
    registry = json.loads((ROOT / "data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))["cards"]
    filler: list[tuple[int, str]] = []
    for card_id, row in registry.items():
        card = catalog.get(card_id)
        if (
            card is not None
            and card_id not in REFERENCE_ROOTS
            and row["metadata"]["collectible"]
            and card.card_class in {"MAGE", "NEUTRAL"}
            and card.card_type in {"MINION", "SPELL", "WEAPON"}
            and row["implementation"]["registration_status"] not in {"NO_DETECTED_RULE_REGISTRATION", "UNKNOWN"}
        ):
            filler.append((card.cost or 0, card_id))
    deck = [*REFERENCE_ROOTS, *(card_id for _, card_id in sorted(filler)[:26])]
    if len(deck) != 30 or len(set(deck)) != 30:
        raise RuntimeError("Could not construct the 30-card reference fixture")
    errors = validate_deck(deck, player_class="MAGE")
    if errors:
        raise RuntimeError(f"Reference fixture failed Rosetta deck validation: {errors}")
    return deck


def _action_signature(action: dict[str, Any]) -> tuple[Any, ...]:
    return (
        action.get("type"),
        action.get("card_id") or "",
        action.get("hand_index"),
        action.get("field_position"),
        action.get("target_entity_id"),
    )


def main() -> None:
    deck = _make_deck()
    mana = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False, random_seed=7)
    rosetta = SimulatorSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_start=False,
        random_seed=7,
    )
    for phase in ("opening", "after_violet_spellwing"):
        mana_state = _without_catalog_mechanics(asdict(mana.observation()))
        rosetta_state = _without_catalog_mechanics(asdict(rosetta.observation()))
        if mana_state != rosetta_state:
            for key in mana_state:
                if mana_state[key] != rosetta_state[key]:
                    print(f"DIFF {phase} {key}: ManaEngine={mana_state[key]} RosettaStone={rosetta_state[key]}")
            raise AssertionError(f"{phase} observable GameState mismatch")
        mana_actions = sorted(_action_signature(row) for row in mana.legal_actions())
        rosetta_actions = sorted(_action_signature(row) for row in rosetta.legal_actions())
        if mana_actions != rosetta_actions:
            raise AssertionError(f"{phase} legal action mismatch: {mana_actions} != {rosetta_actions}")
        print(f"PASS {phase}: GameState and legal action set match")
        if phase == "opening":
            mana_action = next(row for row in mana.legal_actions() if row.get("card_id") == "CORE_DRG_107")
            rosetta_action = next(row for row in rosetta.legal_actions() if row.get("card_id") == "CORE_DRG_107")
            mana.apply_action(mana_action)
            rosetta.apply_action(rosetta_action)


if __name__ == "__main__":
    main()
