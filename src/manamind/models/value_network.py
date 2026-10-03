"""A compact DeepSets-style value network for player-visible game states."""

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from manamind.cards.vocabulary import CardVocabulary
from manamind.encoding.batch import EncodedBatch, TensorZone, ZONE_NAMES
from manamind.encoding.entity_encoder import NUMERIC_FEATURES, PRESENCE_FEATURES, STATE_FLAG_NAMES
from manamind.encoding.state_encoder import GLOBAL_FEATURE_NAMES


@dataclass(frozen=True, slots=True)
class ValueNetworkConfig:
    card_embedding_dim: int = 32
    category_embedding_dim: int = 8
    entity_hidden_dim: int = 96
    global_hidden_dim: int = 96
    fusion_hidden_dim: int = 192


class CardEntityEncoder(nn.Module):
    """Share one card/entity encoder across every variable-length zone."""

    def __init__(self, vocabulary: CardVocabulary, config: ValueNetworkConfig) -> None:
        super().__init__()
        category_dim = config.category_embedding_dim
        self.card_id_embedding = nn.Embedding(vocabulary.card_count, config.card_embedding_dim, padding_idx=0)
        self.type_embedding = nn.Embedding(vocabulary.card_type_count, category_dim)
        self.class_embedding = nn.Embedding(vocabulary.card_class_count, category_dim)
        self.race_embedding = nn.Embedding(vocabulary.race_count, category_dim)

        input_size = (
            config.card_embedding_dim
            + 3 * category_dim
            + len(NUMERIC_FEATURES)
            + len(PRESENCE_FEATURES)
            + vocabulary.mechanics_count
            + len(STATE_FLAG_NAMES)
            + 6
        )
        self.layers = nn.Sequential(
            nn.Linear(input_size, config.entity_hidden_dim),
            nn.ReLU(),
            nn.Linear(config.entity_hidden_dim, config.entity_hidden_dim),
            nn.ReLU(),
        )

    def forward(self, zone: TensorZone) -> Tensor:
        features = torch.cat(
            (
                self.card_id_embedding(zone.card_ids),
                self.type_embedding(zone.card_type_ids),
                self.class_embedding(zone.card_class_ids),
                self.race_embedding(zone.race_ids),
                zone.numeric,
                zone.numeric_present,
                zone.mechanics,
                zone.state_flags,
                zone.hand_semantic_features,
            ),
            dim=-1,
        )
        return self.layers(features)


class ValueNetwork(nn.Module):
    """Estimate whether the perspective player eventually wins.

    The forward method returns logits. Apply sigmoid for win probabilities,
    or use ``predict_probability`` for inference.
    """

    def __init__(
        self,
        vocabulary: CardVocabulary,
        config: ValueNetworkConfig | None = None,
    ) -> None:
        super().__init__()
        self.config = config or ValueNetworkConfig()
        config = self.config

        self.entity_encoder = CardEntityEncoder(vocabulary, config)
        self.player_class_embedding = nn.Embedding(
            vocabulary.card_class_count, config.category_embedding_dim
        )
        self.global_encoder = nn.Sequential(
            nn.Linear(len(GLOBAL_FEATURE_NAMES), config.global_hidden_dim),
            nn.ReLU(),
            nn.Linear(config.global_hidden_dim, config.global_hidden_dim),
            nn.ReLU(),
        )

        zone_vector_size = 2 * config.entity_hidden_dim
        fusion_input_size = (
            config.global_hidden_dim
            + 2 * config.category_embedding_dim
            + len(ZONE_NAMES) * zone_vector_size
        )
        self.fusion = nn.Sequential(
            nn.Linear(fusion_input_size, config.fusion_hidden_dim),
            nn.ReLU(),
            nn.Linear(config.fusion_hidden_dim, config.fusion_hidden_dim),
            nn.ReLU(),
        )
        self.value_head = nn.Linear(config.fusion_hidden_dim, 1)

    def _pool_zone(self, zone: TensorZone) -> Tensor:
        entity_vectors = self.entity_encoder(zone)
        mask = zone.mask.unsqueeze(-1)

        counts = mask.sum(dim=1).clamp(min=1)
        mean_vectors = (entity_vectors * mask).sum(dim=1) / counts

        lowest = torch.finfo(entity_vectors.dtype).min
        max_vectors = entity_vectors.masked_fill(~mask, lowest).max(dim=1).values
        has_items = zone.mask.any(dim=1, keepdim=True)
        max_vectors = torch.where(has_items, max_vectors, torch.zeros_like(max_vectors))
        return torch.cat((mean_vectors, max_vectors), dim=-1)

    def forward(self, batch: EncodedBatch) -> Tensor:
        global_vector = self.global_encoder(batch.global_features)
        self_class = self.player_class_embedding(batch.self_class_ids)
        opponent_class = self.player_class_embedding(batch.opponent_class_ids)
        zone_vectors = [self._pool_zone(batch.zones[name]) for name in ZONE_NAMES]

        combined = torch.cat(
            (global_vector, self_class, opponent_class, *zone_vectors),
            dim=-1,
        )
        return self.value_head(self.fusion(combined)).squeeze(-1)

    def predict_probability(self, batch: EncodedBatch) -> Tensor:
        """Return win probabilities for inference (without changing train API)."""
        return torch.sigmoid(self.forward(batch))

