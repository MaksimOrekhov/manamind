"""Batch inference helpers for a trained value network."""

from dataclasses import dataclass

import torch

from manamind.domain.game_state import GameState
from manamind.encoding.batch import collate_encoded_states
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.value_network import ValueNetwork


@dataclass(frozen=True, slots=True)
class PredictionResult:
    win_probability: float
    model_version: str
    unknown_cards: tuple[str, ...]


def _state_card_ids(state: GameState) -> set[str]:
    cards = list(state.self_hand) + list(state.opponent_known_cards)
    for player in (state.self_player, state.opponent):
        cards.extend(entity.card for entity in player.board)
        cards.extend(card for card in (player.weapon, player.hero_power) if card is not None)
    return {card.card_id for card in cards}


def predict_win_probabilities(
    states: list[GameState] | tuple[GameState, ...],
    encoder: StateEncoder,
    model: ValueNetwork,
) -> list[float]:
    """Return one P(win) estimate per state using the model's current device."""
    return [result.win_probability for result in predict_game_states(states, encoder, model)]


def predict_game_states(
    states: list[GameState] | tuple[GameState, ...],
    encoder: StateEncoder,
    model: ValueNetwork,
) -> list[PredictionResult]:
    """Predict probabilities and report card IDs without trained catalog features."""
    if not states:
        return []

    model_device = next(model.parameters()).device
    encoded_states = [encoder.encode(state) for state in states]
    batch = collate_encoded_states(encoded_states, device=model_device)

    was_training = model.training
    model.eval()
    try:
        with torch.inference_mode():
            probabilities = model.predict_probability(batch)
    finally:
        model.train(was_training)

    model_version = "value_v1"
    unknown_token = encoder.vocabulary.UNKNOWN_CARD
    return [
        PredictionResult(
            win_probability=float(value),
            model_version=model_version,
            unknown_cards=tuple(sorted(
                card_id for card_id in _state_card_ids(state)
                if encoder.vocabulary.card_id(card_id) == unknown_token
            )),
        )
        for state, value in zip(states, probabilities.cpu().tolist(), strict=True)
    ]
