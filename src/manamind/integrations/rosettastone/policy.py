"""A small masked action policy for RosettaStone self-play experiments."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import torch
from torch import Tensor, nn

from manamind.domain.game_state import GameState
from manamind.domain.dark_gift import DARK_GIFT_POLICY_INDEX
from manamind.encoding.state_encoder import GLOBAL_FEATURE_NAMES, StateEncoder

POLICY_STATE_FEATURE_NAMES = (
    *GLOBAL_FEATURE_NAMES,
    "self_board_count", "self_board_attack", "self_board_health",
    "self_ready_attackers", "self_taunts",
    "self_location_count", "self_location_health", "self_ready_locations",
    "opponent_board_count", "opponent_board_attack", "opponent_board_health",
    "opponent_ready_attackers", "opponent_taunts",
    "opponent_location_count", "opponent_location_health", "opponent_ready_locations",
    "self_hand_mean_cost", "self_hand_minions", "self_hand_spells", "self_hand_weapons",
    "self_hand_shatter_left", "self_hand_shatter_right", "self_hand_shatter_solo",
    "self_hand_shatter_intervening_cards_mean",
    "self_hand_prepare_locked_count", "self_hand_prepare_known_count",
)

POLICY_ACTION_SCHEMA_VERSION = 2

ACTION_FEATURE_NAMES = (
    "play_card", "attack", "hero_power", "end_turn",
    "card_minion", "card_spell", "card_weapon", "card_hero_power", "card_other",
    "card_cost", "card_attack", "card_health",
    "source_is_hero", "source_attack", "source_health", "source_board_position",
    "target_is_hero", "target_is_self", "target_attack", "target_health",
    "target_board_position", "target_taunt", "choose_card", "hand_index",
    "activate_location", "trade_card", "choose_one_a", "choose_one_b",
    "choice_index",
    *(f"dark_gift_{gift_id}" for gift_id in range(1, 11)),
    "shatter_left", "shatter_right", "shatter_solo", "shatter_partner_relative_position",
    "prepare_card",
    "card_spell_damage", "choice_card_cost",
    "card_spell_damage_known", "choice_card_cost_known",
)
MAX_HAND_SIZE = 10
CARD_EMBEDDING_DIM = 32

_ACTION_TYPES = {
    "PLAY_CARD": ACTION_FEATURE_NAMES.index("play_card"),
    "PREPARE_CARD": ACTION_FEATURE_NAMES.index("prepare_card"),
    "ATTACK": ACTION_FEATURE_NAMES.index("attack"),
    "HERO_POWER": ACTION_FEATURE_NAMES.index("hero_power"),
    "END_TURN": ACTION_FEATURE_NAMES.index("end_turn"),
    "ACTIVATE_LOCATION": ACTION_FEATURE_NAMES.index("activate_location"),
    "TRADE_CARD": ACTION_FEATURE_NAMES.index("trade_card"),
}
_CARD_TYPES = {name: index for index, name in enumerate((
    "MINION", "SPELL", "WEAPON", "HERO_POWER", "OTHER",
))}


def _scaled(value: Any) -> float:
    if value is None:
        return 0.0
    number = float(value)
    return float(np.sign(number) * np.log1p(min(abs(number), 10_000.0)) / np.log1p(10_000.0))


def encode_policy_state(state: GameState, encoder: StateEncoder) -> np.ndarray:
    """Encode public board totals and the viewed player's own hand, without hidden IDs."""
    self_board = state.self_player.board
    opponent_board = state.opponent.board
    self_locations = state.self_player.locations
    opponent_locations = state.opponent.locations
    hand_costs = [card.effective_cost for card in state.self_hand if card.effective_cost is not None]
    hand_types = [card.card_type for card in state.self_hand]
    values = [
        len(self_board), sum(entity.current_attack for entity in self_board),
        sum(entity.current_health for entity in self_board),
        sum(entity.can_attack for entity in self_board),
        sum(entity.taunt for entity in self_board),
        len(self_locations), sum(item.current_health for item in self_locations),
        sum(item.can_activate is True for item in self_locations),
        len(opponent_board), sum(entity.current_attack for entity in opponent_board),
        sum(entity.current_health for entity in opponent_board),
        sum(entity.can_attack for entity in opponent_board),
        sum(entity.taunt for entity in opponent_board),
        len(opponent_locations), sum(item.current_health for item in opponent_locations),
        sum(item.can_activate is True for item in opponent_locations),
        (sum(hand_costs) / len(hand_costs)) if hand_costs else 0.0,
        sum(card_type == "MINION" for card_type in hand_types),
        sum(card_type == "SPELL" for card_type in hand_types),
        sum(card_type == "WEAPON" for card_type in hand_types),
        sum(card.shatter_fragment == "LEFT" for card in state.self_hand),
        sum(card.shatter_fragment == "RIGHT" for card in state.self_hand),
        sum(card.shatter_fragment == "SOLO" for card in state.self_hand),
        (sum(abs(card.shatter_partner_hand_position - position) - 1
             for position, card in enumerate(state.self_hand)
             if card.shatter_partner_hand_position is not None) /
         sum(card.shatter_partner_hand_position is not None for card in state.self_hand))
        if any(card.shatter_partner_hand_position is not None for card in state.self_hand) else 0.0,
        sum(card.prepare_locked is True for card in state.self_hand),
        sum(card.prepare_locked is not None for card in state.self_hand),
    ]
    return np.concatenate((
        encoder.encode(state).global_features,
        np.asarray([_scaled(value) for value in values], dtype=np.float32),
    ))


def encode_legal_actions(actions: Sequence[dict[str, Any]]) -> np.ndarray:
    """Encode semantic action data; transient RosettaStone entity IDs are ignored."""
    if not actions:
        raise ValueError("Cannot encode an empty legal-action list")

    rows = np.zeros((len(actions), len(ACTION_FEATURE_NAMES)), dtype=np.float32)
    for row, action in enumerate(actions):
        action_type = action.get("type")
        if action_type not in _ACTION_TYPES and action_type != "CHOOSE_CARD":
            raise ValueError(f"Unsupported legal action type: {action_type!r}")
        if action_type == "CHOOSE_CARD":
            rows[row, ACTION_FEATURE_NAMES.index("choose_card")] = 1.0
        else:
            rows[row, _ACTION_TYPES[action_type]] = 1.0
        choose_one = int(action.get("choose_one", 0) or 0)
        if choose_one in (1, 2):
            feature = "choose_one_a" if choose_one == 1 else "choose_one_b"
            rows[row, ACTION_FEATURE_NAMES.index(feature)] = 1.0

        dark_gift_id = int(action.get("dark_gift_id", 0) or 0)
        if 1 <= dark_gift_id <= 10:
            rows[row, ACTION_FEATURE_NAMES.index(f"dark_gift_{dark_gift_id}")] = 1.0

        gifts = list(action.get("card_dark_gifts") or ())
        if action.get("choice_dark_gift"):
            gifts.append(str(action["choice_dark_gift"]))
        for gift in gifts:
            if gift not in DARK_GIFT_POLICY_INDEX:
                raise ValueError(f"Unreviewed Dark Gift identity: {gift}")
            rows[row, ACTION_FEATURE_NAMES.index(f"dark_gift_{DARK_GIFT_POLICY_INDEX[gift]}")] = 1.0

        card_type = action.get("card_type", "OTHER")
        card_type_index = _CARD_TYPES.get(card_type, _CARD_TYPES["OTHER"])
        rows[row, 4 + card_type_index] = 1.0

        numeric = (
            action.get("card_cost", 0), action.get("card_attack", 0),
            action.get("card_health", 0), action.get("source_is_hero", False),
            action.get("source_attack", 0), action.get("source_health", 0),
            action.get("source_board_position", -1), action.get("target_is_hero", False),
            action.get("target_is_self", False), action.get("target_attack", 0),
            action.get("target_health", 0), action.get("target_board_position", -1),
            action.get("target_taunt", False),
        )
        rows[row, 9:22] = [_scaled(value) for value in numeric]
        rows[row, ACTION_FEATURE_NAMES.index("hand_index")] = _scaled(
            action.get("hand_index", -1)
        )
        rows[row, ACTION_FEATURE_NAMES.index("choice_index")] = _scaled(
            action.get("choice_index", -1)
        )
        role = str(action.get("shatter_fragment", "")).upper()
        if role in {"LEFT", "RIGHT", "SOLO"}:
            rows[row, ACTION_FEATURE_NAMES.index(f"shatter_{role.lower()}")] = 1.0
        partner = action.get("shatter_partner_hand_position")
        hand_index = action.get("hand_index")
        if partner is not None and hand_index is not None and int(partner) >= 0:
            rows[row, ACTION_FEATURE_NAMES.index("shatter_partner_relative_position")] = _scaled(
                int(partner) - int(hand_index)
            )
        for feature in ("card_spell_damage", "choice_card_cost"):
            value = action.get(feature)
            known = value is not None and float(value) >= 0
            rows[row, ACTION_FEATURE_NAMES.index(feature)] = _scaled(value) if known else 0.0
            rows[row, ACTION_FEATURE_NAMES.index(f"{feature}_known")] = float(known)
    return rows


def encode_action_card_ids(
    actions: Sequence[dict[str, Any]], encoder: StateEncoder
) -> np.ndarray:
    """Return vocabulary indices for card-bearing actions, without transient IDs."""
    def semantic_card(action: dict[str, Any]) -> str:
        # The embedding is semantic: play card, selected choice card, or attack source.
        return str(
            action.get("shatter_original_card_id")
            or action.get("card_id")
            or action.get("choice_card_id")
            or action.get("source_card_id")
            or "UNKNOWN_CARD"
        )

    return np.asarray([
        encoder.vocabulary.card_id(semantic_card(action)) for action in actions
    ], dtype=np.int64)


def encode_hand_card_ids(state: GameState, encoder: StateEncoder) -> np.ndarray:
    """Encode the player's hand in order, padding to Hearthstone's hand limit."""
    if len(state.self_hand) > MAX_HAND_SIZE:
        raise ValueError(f"Self hand exceeds supported size {MAX_HAND_SIZE}")
    result = np.zeros(MAX_HAND_SIZE, dtype=np.int64)
    result[:len(state.self_hand)] = [
        encoder.vocabulary.card_id(card.shatter_original_card_id or card.card_id) for card in state.self_hand
    ]
    return result


def load_policy_weights(policy: PolicyNetwork, payload: dict[str, Any]) -> bool:
    """Load compatible policy weights; return whether a schema migration occurred."""
    version = payload.get("policy_action_schema_version")
    if version is not None and version not in (1, POLICY_ACTION_SCHEMA_VERSION):
        raise ValueError("Unsupported policy action schema version")
    feature_names = payload.get("action_feature_names")
    state = payload.get("policy_state_dict")
    if not isinstance(state, dict):
        raise TypeError("Checkpoint does not contain policy weights")
    if (feature_names == list(ACTION_FEATURE_NAMES)
            and payload.get("state_feature_names") == list(POLICY_STATE_FEATURE_NAMES)
            and "card_vocabulary" in payload):
        policy.load_state_dict(state)
        return False

    state_names = payload.get("state_feature_names")
    if (
        not isinstance(feature_names, list)
        or len(set(feature_names)) != len(feature_names)
        or any(name not in ACTION_FEATURE_NAMES for name in feature_names)
        or not isinstance(state_names, list)
        or len(set(state_names)) != len(state_names)
        or any(name not in POLICY_STATE_FEATURE_NAMES for name in state_names)
    ):
        raise ValueError("Checkpoint action features do not match this version")

    old_weight = state.get("scorer.0.weight")
    if old_weight is None:
        raise ValueError("Legacy policy weights do not match the expected feature schema")
    new_state = policy.state_dict()
    new_weight = new_state["scorer.0.weight"].clone().zero_()
    expected_without_embeddings = len(state_names) + len(feature_names)
    old_embedding_width = old_weight.shape[1] - expected_without_embeddings
    expected_embedding_width = (MAX_HAND_SIZE + 1) * CARD_EMBEDDING_DIM
    if old_embedding_width not in (0, expected_embedding_width):
        raise ValueError("Legacy policy weights do not match the expected feature schema")

    for name, value in state.items():
        if name != "scorer.0.weight" and name in new_state and new_state[name].shape == value.shape:
            new_state[name] = value

    for old_index, feature_name in enumerate(state_names):
        new_index = POLICY_STATE_FEATURE_NAMES.index(feature_name)
        new_weight[:, new_index] = old_weight[:, old_index]

    old_action_offset = len(state_names)
    new_action_offset = len(POLICY_STATE_FEATURE_NAMES)
    for old_index, feature_name in enumerate(feature_names):
        new_index = ACTION_FEATURE_NAMES.index(feature_name)
        new_weight[:, new_action_offset + new_index] = old_weight[
            :, old_action_offset + old_index
        ]

    if old_embedding_width:
        old_embedding_offset = expected_without_embeddings
        new_embedding_offset = len(POLICY_STATE_FEATURE_NAMES) + len(ACTION_FEATURE_NAMES)
        new_weight[:, new_embedding_offset:] = old_weight[:, old_embedding_offset:]

    new_state["scorer.0.weight"] = new_weight
    policy.load_state_dict(new_state)
    return True



class PolicyNetwork(nn.Module):
    """Score each legal action using the visible state and semantic action features."""

    def __init__(
        self,
        state_feature_count: int = len(POLICY_STATE_FEATURE_NAMES),
        card_count: int = 2,
        hidden_size: int = 128,
    ) -> None:
        super().__init__()
        self.state_feature_count = state_feature_count
        self.action_feature_count = len(ACTION_FEATURE_NAMES)
        self.card_embedding = nn.Embedding(card_count, CARD_EMBEDDING_DIM, padding_idx=0)
        self.hand_position_embedding = nn.Embedding(MAX_HAND_SIZE, CARD_EMBEDDING_DIM)
        self.scorer = nn.Sequential(
            nn.Linear(
                state_feature_count + self.action_feature_count
                + (MAX_HAND_SIZE + 1) * CARD_EMBEDDING_DIM,
                hidden_size,
            ),
            nn.Tanh(),
            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1),
        )

    def forward(
        self,
        state_features: Tensor,
        action_features: Tensor,
        hand_card_ids: Tensor,
        action_card_ids: Tensor,
    ) -> Tensor:
        if state_features.ndim != 1 or state_features.shape[0] != self.state_feature_count:
            raise ValueError("state_features must be one encoded global state vector")
        if action_features.ndim != 2 or action_features.shape[1] != self.action_feature_count:
            raise ValueError("action_features must contain one row per legal action")
        if hand_card_ids.shape != (MAX_HAND_SIZE,):
            raise ValueError(f"hand_card_ids must have shape ({MAX_HAND_SIZE},)")
        if action_card_ids.shape != (action_features.shape[0],):
            raise ValueError("action_card_ids must have one entry per legal action")
        state_rows = state_features.expand(action_features.shape[0], -1)
        positions = torch.arange(MAX_HAND_SIZE, device=hand_card_ids.device)
        hand_embeddings = self.card_embedding(hand_card_ids) + self.hand_position_embedding(positions)
        hand_embeddings = hand_embeddings * hand_card_ids.ne(0).unsqueeze(-1)
        hand_embeddings = hand_embeddings.flatten().expand(action_features.shape[0], -1)
        action_embeddings = self.card_embedding(action_card_ids)
        return self.scorer(torch.cat(
            (state_rows, action_features, hand_embeddings, action_embeddings), dim=-1
        )).squeeze(-1)


def policy_action_features(actions: Sequence[dict[str, Any]], device: torch.device) -> Tensor:
    return torch.as_tensor(encode_legal_actions(actions), dtype=torch.float32, device=device)
