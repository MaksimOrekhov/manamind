"""Pad variable-size encoded zones and collect states into a tensor batch."""

from dataclasses import dataclass

import numpy as np
import torch
from torch import Tensor

from manamind.encoding.entity_encoder import EncodedZone
from manamind.encoding.state_encoder import EncodedGameState


ZONE_NAMES = (
    "self_hand",
    "self_known_secrets",
    "self_board",
    "opponent_board",
    "self_locations",
    "opponent_locations",
    "opponent_known_cards",
    "self_weapon",
    "opponent_weapon",
    "self_hero_power",
    "opponent_hero_power",
    "self_active_effects", "opponent_active_effects", "pending_choice_options",
)


@dataclass(frozen=True, slots=True)
class TensorZone:
    card_ids: Tensor
    card_type_ids: Tensor
    card_class_ids: Tensor
    race_ids: Tensor
    mechanics: Tensor
    numeric: Tensor
    numeric_present: Tensor
    state_flags: Tensor
    hand_semantic_features: Tensor
    mask: Tensor


@dataclass(frozen=True, slots=True)
class EncodedBatch:
    global_features: Tensor
    self_class_ids: Tensor
    opponent_class_ids: Tensor
    zones: dict[str, TensorZone]


def _pad_zone(zones: list[EncodedZone], device: torch.device | str | None) -> TensorZone:
    batch_size = len(zones)
    max_items = max(1, max(zone.size for zone in zones))
    mechanics_size = zones[0].mechanics.shape[1]

    card_ids = np.zeros((batch_size, max_items), dtype=np.int64)
    card_type_ids = np.zeros_like(card_ids)
    card_class_ids = np.zeros_like(card_ids)
    race_ids = np.zeros_like(card_ids)
    mechanics = np.zeros((batch_size, max_items, mechanics_size), dtype=np.float32)
    numeric = np.zeros((batch_size, max_items, zones[0].numeric.shape[1]), dtype=np.float32)
    numeric_present = np.zeros_like(numeric)
    state_flags = np.zeros((batch_size, max_items, zones[0].state_flags.shape[1]), dtype=np.float32)
    hand_semantic_features = np.zeros((batch_size, max_items, 6), dtype=np.float32)
    mask = np.zeros((batch_size, max_items), dtype=np.bool_)

    for row, zone in enumerate(zones):
        if zone.mechanics.shape[1] != mechanics_size:
            raise ValueError("All states in a batch must use the same mechanics vocabulary")
        count = zone.size
        if not count:
            continue
        card_ids[row, :count] = zone.card_ids
        card_type_ids[row, :count] = zone.card_type_ids
        card_class_ids[row, :count] = zone.card_class_ids
        race_ids[row, :count] = zone.race_ids
        mechanics[row, :count] = zone.mechanics
        numeric[row, :count] = zone.numeric
        numeric_present[row, :count] = zone.numeric_present
        state_flags[row, :count] = zone.state_flags
        hand_semantic_features[row, :count] = zone.hand_semantic_features
        mask[row, :count] = True

    return TensorZone(
        card_ids=torch.as_tensor(card_ids, device=device),
        card_type_ids=torch.as_tensor(card_type_ids, device=device),
        card_class_ids=torch.as_tensor(card_class_ids, device=device),
        race_ids=torch.as_tensor(race_ids, device=device),
        mechanics=torch.as_tensor(mechanics, device=device),
        numeric=torch.as_tensor(numeric, device=device),
        numeric_present=torch.as_tensor(numeric_present, device=device),
        state_flags=torch.as_tensor(state_flags, device=device),
        hand_semantic_features=torch.as_tensor(hand_semantic_features, device=device),
        mask=torch.as_tensor(mask, device=device),
    )


def collate_encoded_states(
    states: list[EncodedGameState] | tuple[EncodedGameState, ...],
    device: torch.device | str | None = None,
) -> EncodedBatch:
    """Create a padded batch; empty zones receive one masked padding row."""
    if not states:
        raise ValueError("Cannot create a batch from zero states")

    zones = {
        name: _pad_zone([getattr(state, name) for state in states], device)
        for name in ZONE_NAMES
    }
    global_features = np.stack([state.global_features for state in states]).astype(np.float32)

    return EncodedBatch(
        global_features=torch.as_tensor(global_features, device=device),
        self_class_ids=torch.as_tensor(
            [state.self_class_id for state in states], dtype=torch.long, device=device
        ),
        opponent_class_ids=torch.as_tensor(
            [state.opponent_class_id for state in states], dtype=torch.long, device=device
        ),
        zones=zones,
    )
