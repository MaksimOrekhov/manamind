from dataclasses import asdict
from types import SimpleNamespace

from hearthstone.enums import CardType, GameTag

from scripts.import_power_log import _card_features
from manamind.cards.catalog import CardCatalog
from manamind.cards.vocabulary import CardVocabulary
from manamind.domain.card import CardFeatures
from manamind.domain.serialization import _card, game_state_from_dict
from manamind.encoding.entity_encoder import EntityEncoder, NUMERIC_FEATURES


def test_buffed_hand_and_cost_preserve_base_and_instance_stats_through_serialization_and_encoding():
    catalog = CardCatalog([CardFeatures(card_id="M", card_type="MINION", cost=4, attack=3, health=3)])
    entity = SimpleNamespace(card_id="M", type=CardType.MINION, tags={GameTag.ATK: 5, GameTag.HEALTH: 5, GameTag.COST: 1})
    observed = _card_features(entity, catalog)
    assert (observed.cost, observed.attack, observed.health) == (4, 3, 3)
    assert (observed.current_cost, observed.current_attack, observed.current_health) == (1, 5, 5)
    assert _card(asdict(observed)) == observed
    assert catalog.enrich(observed) == observed
    encoded = EntityEncoder(catalog, CardVocabulary(catalog)).encode_zone((observed,), ordered=True)
    for name in ("current_cost", "current_attack", "current_health"):
        assert encoded.numeric_present[0, NUMERIC_FEATURES.index(name)] == 1
    assert encoded.numeric[0, NUMERIC_FEATURES.index("current_attack")] > encoded.numeric[0, NUMERIC_FEATURES.index("base_attack")]
    enchanted_spell = CardFeatures(card_id="S", card_type="SPELL", current_spell_damage=1)
    assert _card(asdict(enchanted_spell)) == enchanted_spell
    assert catalog.enrich(enchanted_spell) == enchanted_spell
    spell_encoding = EntityEncoder(catalog, CardVocabulary(catalog)).encode_zone((enchanted_spell,), ordered=True)
    spell_damage_column = NUMERIC_FEATURES.index("current_spell_damage")
    assert spell_encoding.numeric_present[0, spell_damage_column] == 1
    assert spell_encoding.numeric[0, spell_damage_column] > 0


def test_modified_weapon_matches_bridge_instance_payload():
    catalog = CardCatalog([CardFeatures(card_id="W", card_type="WEAPON", cost=3, attack=3, durability=4)])
    entity = SimpleNamespace(card_id="W", type=CardType.WEAPON, tags={GameTag.COST: 3, GameTag.ATK: 5, GameTag.DURABILITY: 2})
    observed = _card_features(entity, catalog)
    bridge_payload = {**asdict(catalog.get("W")), "current_cost": 3, "current_attack": 5, "current_durability": 2}
    assert observed == _card(bridge_payload)
    assert (observed.attack, observed.durability) == (3, 4)
    assert (observed.effective_attack, observed.effective_durability) == (5, 2)


def test_unknown_tristate_survives_json_roundtrip():
    state = game_state_from_dict({"turn_number": 1, "active_player": "SELF", "self_player": {"hero_health": 30, "hero_power_ready": None, "locations": [{"card": {"card_id": "L"}, "current_health": 2, "can_activate": None}]}, "opponent": {"hero_health": 30}})
    restored = game_state_from_dict(asdict(state))
    assert restored.self_player.hero_power_ready is None
    assert restored.self_player.locations[0].can_activate is None
