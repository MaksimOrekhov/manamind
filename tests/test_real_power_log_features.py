from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from hearthstone.enums import CardType, GameTag

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from import_power_log import (  # noqa: E402
    _board_entity,
    _location_entity,
    _mana_values,
    _card_features,
    _visible_hand_cards,
)
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.domain.card import CardFeatures  # noqa: E402
from manamind.training.synthetic import load_labeled_dataset  # noqa: E402
from scripts.import_power_log import import_power_log  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from power_log_fixtures import build_game, to_text  # noqa: E402

CATALOG_PATH = ROOT / "data" / "cards" / "standard_current_enUS.json"


def test_mana_uses_current_crystals_not_the_game_cap():
    total, available, locked = _mana_values({
        GameTag.RESOURCES: 3,
        GameTag.MAXRESOURCES: 10,
        GameTag.TEMP_RESOURCES: 1,
        GameTag.RESOURCES_USED: 1,
        GameTag.OVERLOAD_LOCKED: 1,
    })

    assert (total, available, locked) == (3, 2, 1)


def test_opponent_hand_excludes_hidden_cards_but_keeps_own_hand_known():
    catalog = CardCatalog([CardFeatures(card_id="EXAMPLE_MINION")])
    hidden_card = SimpleNamespace(
        card_id="EXAMPLE_MINION",
        type=SimpleNamespace(name="MINION"),
        tags={},
        revealed=False,
    )

    assert _visible_hand_cards([hidden_card], catalog, is_self=True)[0].card_id == "EXAMPLE_MINION"
    assert _visible_hand_cards([hidden_card], catalog, is_self=False) == []

    hidden_card.revealed = True
    assert _visible_hand_cards([hidden_card], catalog, is_self=False)[0].card_id == "EXAMPLE_MINION"


def test_base_stats_are_separate_from_current_board_stats():
    catalog = CardCatalog([CardFeatures(
        card_id="BUFFED_MINION",
        attack=2,
        health=3,
        card_type="MINION",
    )])
    entity = SimpleNamespace(
        id=12,
        card_id="BUFFED_MINION",
        type=CardType.MINION,
        tags={GameTag.ATK: 6, GameTag.HEALTH: 8, GameTag.DAMAGE: 2},
    )

    board_entity = _board_entity(entity, position=0, catalog=catalog)

    assert (board_entity.card.attack, board_entity.card.health) == (2, 3)
    assert (board_entity.current_attack, board_entity.current_health, board_entity.max_health) == (6, 6, 8)
    assert _card_features(entity, catalog).current_durability is None


def test_location_import_preserves_cooldown_without_guessing_full_playability():
    catalog = CardCatalog([CardFeatures(
        card_id="EXAMPLE_LOCATION", card_type="LOCATION", durability=3,
    )])
    entity = SimpleNamespace(
        card_id="EXAMPLE_LOCATION",
        type=CardType.LOCATION,
        tags={
            GameTag.HEALTH: 3,
            GameTag.DAMAGE: 1,
            GameTag.ZONE_POSITION: 2,
            GameTag.LOCATION_ACTION_COOLDOWN: 1,
        },
    )

    location = _location_entity(entity, catalog)

    assert (location.current_health, location.max_health, location.board_position) == (2, 3, 2)
    assert _card_features(entity, catalog).current_durability is None
    assert location.on_cooldown is True
    assert location.can_activate is None


def test_power_log_import_preserves_weapon_current_durability(tmp_path):
    lines = build_game(seed=901)
    marker = next(i for i, line in enumerate(lines) if "tag=STATE value=RUNNING" in line)
    lines[marker:marker] = [
        "D 20:00:00.0000000 GameState.DebugPrintPower() - FULL_ENTITY - Creating ID=40 CardID=EXAMPLE_WEAPON",
        "D 20:00:00.0000000 GameState.DebugPrintPower() -     tag=CARDTYPE value=WEAPON",
        "D 20:00:00.0000000 GameState.DebugPrintPower() -     tag=ZONE value=PLAY",
        "D 20:00:00.0000000 GameState.DebugPrintPower() -     tag=CONTROLLER value=1",
        "D 20:00:00.0000000 GameState.DebugPrintPower() -     tag=ENTITY_ID value=40",
        "D 20:00:00.0000000 GameState.DebugPrintPower() -     tag=ATK value=3",
        "D 20:00:00.0000000 GameState.DebugPrintPower() -     tag=HEALTH value=3",
        "D 20:00:00.0000000 GameState.DebugPrintPower() -     tag=DAMAGE value=1",
    ]
    raw_path = tmp_path / "synthetic_power.log"
    output_path = tmp_path / "preview" / "match.jsonl"
    raw_path.write_text(to_text(lines), encoding="utf-8")

    summary = import_power_log(raw_path, output_path, CATALOG_PATH)

    examples = load_labeled_dataset(output_path)
    assert summary["examples_written"] > 0
    assert examples[0].state.self_player.weapon.current_durability == 2
