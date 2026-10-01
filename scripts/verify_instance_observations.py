"""Compare independently specified current instance stats across bridge and log import."""
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.enums import CardType, GameTag
from scripts.import_power_log import _card_features
from manamind.cards.catalog import CardCatalog
from manamind.domain.serialization import _card
from manamind.integrations.rosettastone.rosettastone import _load_bridge


def main() -> None:
    raw = _load_bridge().make_instance_observation_fixture()
    for key, kind, tags in (
        ("hand_card", CardType.MINION, {GameTag.COST: 1, GameTag.ATK: 5, GameTag.HEALTH: 5}),
        ("weapon", CardType.WEAPON, {GameTag.COST: 3, GameTag.ATK: 5, GameTag.DURABILITY: 1}),
    ):
        bridge = _card(raw[key])
        base = {k: v for k, v in raw[key].items() if not k.startswith("current_")}
        catalog = CardCatalog([_card(base)])
        entity = SimpleNamespace(card_id=bridge.card_id, type=kind, tags=tags)
        imported = _card_features(entity, catalog)
        assert imported == bridge, (key, imported, bridge)
        assert bridge.current_attack == 5
        if key == "hand_card":
            assert (bridge.current_cost, bridge.current_health) == (1, 5)
        else:
            assert bridge.current_durability == 1
        print(f"PASS {key}: base metadata and current instance state match across native bridge/Power.log import")


if __name__ == "__main__":
    main()
