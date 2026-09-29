from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from hearthstone.enums import CardType, GameTag

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from import_power_log import (  # noqa: E402
    _board_entity,
    _mana_values,
    _visible_hand_cards,
)
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.domain.card import CardFeatures  # noqa: E402


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
