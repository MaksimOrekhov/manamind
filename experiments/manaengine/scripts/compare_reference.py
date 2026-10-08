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
            key: None if key == "race" and item == "" else _without_catalog_mechanics(item)
            for key, item in value.items()
            # Rosetta's current bridge does not export hero-freeze state, and
            # ManaEngine intentionally reports unknown hero shield where it has
            # no implementation. Rosetta's bridge also has no healing-bonus export (unknown, None), whereas
            # ManaEngine reports the exact value. Compare the shared observation contract only.
            if key not in {
                "mechanics", "hero_frozen", "hero_divine_shield", "healing_bonus",
                "cant_be_targeted_by_spells", "cant_be_targeted_by_hero_powers",
            }
            and not (key == "current_durability" and value.get("card_type") != "WEAPON")
        }
    if isinstance(value, (list, tuple)):
        return [_without_catalog_mechanics(item) for item in value]
    return value


def _make_deck(root_order: tuple[str, ...] = REFERENCE_ROOTS) -> list[str]:
    selection = json.loads((ROOT / "experiments/manaengine/data/root_selection.json").read_text(encoding="utf-8"))
    selected_ids = {row["card_id"] for row in selection["cards"]}
    if any(card_id not in selected_ids for card_id in root_order):
        raise RuntimeError("Reference fixture roots are no longer in the current Tier A/B selection")

    catalog = {card.card_id: card for card in CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")}
    registry = json.loads((ROOT / "data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))["cards"]
    overrides = json.loads((ROOT / "experiments/manaengine/data/card_abilities.json").read_text(encoding="utf-8"))["cards"]
    deck = list(root_order)
    counts = {card_id: deck.count(card_id) for card_id in set(deck)}
    supported: list[tuple[int, str]] = []
    filler: list[tuple[int, str]] = []
    for card_id, row in registry.items():
        card = catalog.get(card_id)
        if (
            card is not None
            and row["metadata"]["collectible"]
            and card.card_class in {"MAGE", "NEUTRAL"}
            and card.card_type in {"MINION", "SPELL", "WEAPON"}
            and "TRADEABLE" not in card.mechanics
            and row["implementation"]["registration_status"] not in {"NO_DETECTED_RULE_REGISTRATION", "UNKNOWN"}
        ):
            filler.append((card.cost or 0, card_id))
            if overrides.get(card_id, {}).get("support_state") in {"SUPPORTED", "VERIFIED_VANILLA"}:
                supported.append((card.cost or 0, card_id))
    for _, card_id in sorted(supported):
        while len(deck) < 10 and counts.get(card_id, 0) < 2:
            deck.append(card_id)
            counts[card_id] = counts.get(card_id, 0) + 1
    for _, card_id in sorted(filler):
        if len(deck) >= 30:
            break
        if counts.get(card_id, 0) < 2:
            deck.append(card_id)
            counts[card_id] = counts.get(card_id, 0) + 1
    if len(deck) != 30:
        raise RuntimeError("Could not construct the 30-card reference fixture")
    errors = validate_deck(deck, player_class="MAGE")
    if errors:
        raise RuntimeError(f"Reference fixture failed Rosetta deck validation: {errors}")
    return deck


def _action_signature(action: dict[str, Any]) -> tuple[Any, ...]:
    return (
        action.get("type"),
        (action.get("card_id") or "") if action.get("type") == "PLAY_CARD" else "",
        action.get("hand_index"),
        bool(action.get("source_is_hero")),
        action.get("source_board_position"),
        action.get("target_board_position"),
        bool(action.get("target_is_hero")),
        action.get("choice_card_id") or "",
        action.get("choice_index"),
    )


def _paired_sessions(deck: list[str]) -> tuple[ManaEngineSession, SimulatorSession]:
    return (
        ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False, random_seed=7),
        SimulatorSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False, random_start=False, random_seed=7),
    )


def _assert_checkpoint(label: str, mana: ManaEngineSession, rosetta: SimulatorSession) -> None:
    mana_state = _without_catalog_mechanics(asdict(mana.observation()))
    rosetta_state = _without_catalog_mechanics(asdict(rosetta.observation()))
    if mana_state != rosetta_state:
        for key in mana_state:
            if mana_state[key] != rosetta_state[key]:
                print(f"DIFF {label} {key}: ManaEngine={mana_state[key]} RosettaStone={rosetta_state[key]}")
        raise AssertionError(f"{label} observable GameState mismatch")
    mana_actions = sorted(_action_signature(row) for row in mana.legal_actions())
    rosetta_actions = sorted(_action_signature(row) for row in rosetta.legal_actions())
    if mana_actions != rosetta_actions:
        raise AssertionError(f"{label} legal action mismatch: {mana_actions} != {rosetta_actions}")
    print(f"PASS {label}: visible state and semantic legal-action set match")


def _apply_pair(label: str, mana: ManaEngineSession, rosetta: SimulatorSession, choose) -> None:
    mana_action = next(row for row in mana.legal_actions() if choose(row))
    rosetta_action = next(row for row in rosetta.legal_actions() if choose(row))
    mana.apply_action(mana_action)
    rosetta.apply_action(rosetta_action)
    _assert_checkpoint(label, mana, rosetta)


def _end_turn(row: dict[str, Any]) -> bool:
    return row.get("type") == "END_TURN"


def _sequence_targeted_spell() -> None:
    mana, rosetta = _paired_sessions(_make_deck())
    _assert_checkpoint("targeted_spell/opening", mana, rosetta)
    for turn in range(3):
        _apply_pair(f"targeted_spell/p1_end_{turn + 1}", mana, rosetta, _end_turn)
        _apply_pair(f"targeted_spell/p2_end_{turn + 1}", mana, rosetta, _end_turn)
    _apply_pair("targeted_spell/fireball", mana, rosetta, lambda row: row.get("type") == "PLAY_CARD" and row.get("card_id") == "CORE_CS2_029" and row.get("target_is_hero"))


def _sequence_combat_and_generated_card() -> None:
    mana, rosetta = _paired_sessions(_make_deck())
    _assert_checkpoint("combat/opening", mana, rosetta)
    _apply_pair("combat/p1_violet", mana, rosetta, lambda row: row.get("type") == "PLAY_CARD" and row.get("card_id") == "CORE_DRG_107")
    _apply_pair("combat/p1_end", mana, rosetta, _end_turn)
    _apply_pair("combat/p2_violet", mana, rosetta, lambda row: row.get("type") == "PLAY_CARD" and row.get("card_id") == "CORE_DRG_107")
    _apply_pair("combat/p2_end", mana, rosetta, _end_turn)
    _apply_pair("combat/minion_trade_and_deathrattle", mana, rosetta, lambda row: row.get("type") == "ATTACK" and row.get("source_board_position") == 0 and row.get("target_board_position") == 0)
    _apply_pair("combat/play_generated_arcane_missiles", mana, rosetta, lambda row: row.get("type") == "PLAY_CARD" and row.get("card_id") == "EX1_277")


def _sequence_end_turn_trigger() -> None:
    # Earthen Drake is a neutral Meta Profile root, so this remains a legal Mage deck.
    roots = ("CATA_999", "CORE_DRG_107", "CORE_SW_108", "CORE_CS2_024")
    mana, rosetta = _paired_sessions(_make_deck(roots))
    _assert_checkpoint("end_turn_trigger/opening", mana, rosetta)
    for turn in range(8):
        playable = [row for row in mana.legal_actions() if row.get("type") == "PLAY_CARD" and row.get("card_id") == "CATA_999"]
        if playable:
            break
        _apply_pair(f"end_turn_trigger/p1_end_{turn + 1}", mana, rosetta, _end_turn)
        _apply_pair(f"end_turn_trigger/p2_end_{turn + 1}", mana, rosetta, _end_turn)
    _apply_pair("end_turn_trigger/play_earthen_drake", mana, rosetta, lambda row: row.get("type") == "PLAY_CARD" and row.get("card_id") == "CATA_999")
    _apply_pair("end_turn_trigger/resolve_earthen_drake", mana, rosetta, _end_turn)


def main() -> None:
    _sequence_targeted_spell()
    _sequence_combat_and_generated_card()
    _sequence_end_turn_trigger()


if __name__ == "__main__":
    main()
