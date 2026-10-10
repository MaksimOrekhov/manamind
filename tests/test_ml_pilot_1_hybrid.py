"""The experimental text path must respect its mask and alter candidate scores."""

import torch

from manamind.models.policy_v2 import ACTION_V2_FEATURE_NAMES, PolicyNetworkV2
from manamind.research.hybrid_policy import HybridPolicyV2


def test_hybrid_text_mask_and_logit_sensitivity():
    torch.manual_seed(4)
    base = PolicyNetworkV2(card_count=3, state_feature_count=2, entity_feature_count=3,
                           hidden_size=8, dropout=0.0)
    hybrid = HybridPolicyV2(base, text_width=4).eval()
    state = torch.zeros(2)
    ids = torch.tensor([1, 2])
    entities = torch.zeros((2, 3))
    actions = torch.zeros((2, len(ACTION_V2_FEATURE_NAMES)))
    card_ids = torch.tensor([[1, 0], [2, 0]])
    links = torch.full((2, 4), -1)
    text = torch.tensor([[1.0, 0, 0, 0], [0, 1.0, 0, 0]])
    base_inputs = (state, ids, entities, actions, card_ids, links)
    with torch.no_grad():
        hybrid.text_score[0].weight.zero_()
        hybrid.text_score[0].weight[0, 0] = 1
        hybrid.text_score[2].weight.zero_()
        hybrid.text_score[2].weight[0, 0] = 1
        base_logits = base(*base_inputs)
        masked = hybrid(*base_inputs, text, torch.zeros(2))
        usable = hybrid(*base_inputs, text, torch.ones(2))
    assert torch.equal(masked, base_logits)
    assert usable[0] > base_logits[0]
    assert usable[1] == base_logits[1]
