"""Show how the sample position becomes arrays for a neural network."""

import json
from pathlib import Path

from manamind.cards import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.encoding import StateEncoder


PROJECT_ROOT = Path(__file__).parent

with (PROJECT_ROOT / "data/samples/example_state.json").open(encoding="utf-8") as file:
    game_state = game_state_from_dict(json.load(file))

catalog = CardCatalog.from_json(PROJECT_ROOT / "data/samples/sample_cards.json")
encoder = StateEncoder(catalog)
encoded = encoder.encode(game_state)

print(f"Global features: {len(encoder.global_feature_names)}")
print(f"Global vector shape: {encoded.global_features.shape}")
print(f"SELF class index: {encoded.self_class_id}")
print(f"OPPONENT class index: {encoded.opponent_class_id}")
print(f"Known hand cards: {encoded.self_hand.size}")
print(f"First card ID index: {encoded.self_hand.card_ids[0]}")
print(f"Second card (unknown identity) index: {encoded.self_hand.card_ids[1]}")
print(f"Unknown card structured properties: {encoded.self_hand.numeric[1].tolist()}")
print(f"Opponent hidden hand card rows: {encoded.opponent_known_cards.size}")
