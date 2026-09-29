"""Run an untrained model once to demonstrate the complete tensor path."""

import json
from pathlib import Path

import torch

from manamind.cards import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.encoding import StateEncoder
from manamind.inference import predict_win_probabilities
from manamind.models import ValueNetwork


PROJECT_ROOT = Path(__file__).parent
with (PROJECT_ROOT / "data/samples/example_state.json").open(encoding="utf-8") as file:
    state = game_state_from_dict(json.load(file))

catalog = CardCatalog.from_json(PROJECT_ROOT / "data/samples/sample_cards.json")
encoder = StateEncoder(catalog)
model = ValueNetwork(encoder.vocabulary)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
probability = predict_win_probabilities([state], encoder, model)[0]

print(f"Model device: {device}")
print(f"Untrained model output: {probability:.3f}")
print("This number is only a pipeline demo; training data is required for a useful estimate.")

