"""Policy v3: contextual tokens and menu-aware candidate ranking over the unchanged v2 inputs.

The input tensors are exactly those of ``policy_v2.encode_policy_v2`` (visible state only), so a v2/v3 comparison
changes the network and nothing else. Two additions answer measured v2 limits:

* entity tokens never interact in v2 (each is projected alone); here the global state and all visible entities share
  one self-attention layer, so a token is read in the context of the board it sits on;
* v2 scores every legal action in isolation; here the candidates of one menu attend to each other (a permutation
  equivariant set layer), so a score can depend on the alternatives actually available.
"""
from __future__ import annotations

import torch
from torch import nn

from manamind.models.policy import CARD_EMBEDDING_DIM
from manamind.models.policy_v2 import ACTION_V2_FEATURE_NAMES

NETWORK_REPRESENTATION_VERSION = 3  # inputs stay representation 2


def _block(width, heads, dropout):
    return nn.TransformerEncoderLayer(width, heads, dim_feedforward=2 * width, dropout=dropout,
                                      activation="gelu", batch_first=True, norm_first=True)


class PolicyNetworkV3(nn.Module):
    representation_version = NETWORK_REPRESENTATION_VERSION

    def __init__(self, card_count, state_feature_count, entity_feature_count, hidden_size=64, dropout=0.1,
                 heads=4, entity_layers=1, menu_layers=1):
        super().__init__()
        if hidden_size % heads or entity_layers not in (0, 1, 2) or menu_layers not in (0, 1, 2):
            raise ValueError("Invalid policy v3 shape")
        self.state_feature_count, self.entity_feature_count = state_feature_count, entity_feature_count
        self.hidden_size, self.dropout, self.heads = hidden_size, dropout, heads
        self.entity_layers, self.menu_layers = entity_layers, menu_layers
        self.card_embedding = nn.Embedding(card_count, CARD_EMBEDDING_DIM, padding_idx=0)
        self.entity_in = nn.Sequential(nn.Linear(entity_feature_count + CARD_EMBEDDING_DIM, hidden_size),
                                       nn.LayerNorm(hidden_size), nn.GELU())
        self.global_in = nn.Sequential(nn.Linear(state_feature_count, hidden_size),
                                       nn.LayerNorm(hidden_size), nn.GELU())
        self.entity_blocks = nn.ModuleList(_block(hidden_size, heads, dropout) for _ in range(entity_layers))
        self.action_in = nn.Sequential(
            nn.Linear(len(ACTION_V2_FEATURE_NAMES) + 2 * CARD_EMBEDDING_DIM + 2 * hidden_size, hidden_size),
            nn.LayerNorm(hidden_size), nn.GELU())
        self.cross = nn.MultiheadAttention(hidden_size, heads, dropout=dropout, batch_first=True)
        self.menu_blocks = nn.ModuleList(_block(hidden_size, heads, dropout) for _ in range(menu_layers))
        self.scorer = nn.Sequential(nn.Linear(6 * hidden_size, hidden_size), nn.GELU(),
                                    nn.Dropout(dropout), nn.Linear(hidden_size, 1))

    def forward(self, state, ids, entities, actions, card_ids, links):
        n = actions.shape[0]
        if (state.shape != (self.state_feature_count,) or ids.ndim != 1 or len(ids) < 2
                or entities.shape != (len(ids), self.entity_feature_count)
                or actions.shape != (n, len(ACTION_V2_FEATURE_NAMES)) or n == 0
                or card_ids.shape != (n, 2) or links.shape != (n, 4)
                or bool((links < -1).any()) or bool((links >= len(ids)).any())):
            raise ValueError("Incompatible policy v3 input shapes or entity links")
        tokens = self.entity_in(torch.cat((entities, self.card_embedding(ids)), dim=-1))
        global_token = self.global_in(state)
        if self.entity_blocks:
            sequence = torch.cat((global_token[None], tokens), dim=0)[None]
            for block in self.entity_blocks:
                sequence = block(sequence)
            global_token, tokens = sequence[0, 0], sequence[0, 1:]
        gathered = tokens[links.clamp_min(0)] * links.ge(0).unsqueeze(-1)
        source, target, left, right = gathered.unbind(dim=1)
        query = self.action_in(torch.cat((actions, self.card_embedding(card_ids).flatten(1), source, target), dim=-1))
        memory = tokens[None]
        context = self.cross(query[None], memory, memory, need_weights=False)[0][0]
        candidates = (query + context)[None]
        for block in self.menu_blocks:
            candidates = block(candidates)
        candidates = candidates[0]
        return self.scorer(torch.cat((candidates, global_token.expand(n, -1), context, source * target, left, right),
                                     dim=-1)).squeeze(-1)
