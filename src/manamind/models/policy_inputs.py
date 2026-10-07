"""One explicit representation dispatch shared by offline training and LIVE."""
import torch

from manamind.models.policy import (
    PolicyNetwork, encode_action_card_ids, encode_hand_card_ids, encode_legal_actions, encode_policy_state,
)
from manamind.models.policy_v2 import PolicyNetworkV2, encode_policy_v2


def encode_policy_inputs(state, actions, encoder, *, representation=1, device="cpu") -> tuple:
    if representation == 2:
        return encode_policy_v2(state, actions, encoder, device)
    if representation != 1:
        raise ValueError("Unsupported policy representation")
    return tuple(torch.as_tensor(a, dtype=dtype, device=device) for a, dtype in (
        (encode_policy_state(state, encoder), torch.float32),
        (encode_legal_actions(actions), torch.float32),
        (encode_hand_card_ids(state, encoder), torch.long),
        (encode_action_card_ids(actions, encoder), torch.long)))


def representation_of(policy) -> int:
    if isinstance(policy, PolicyNetworkV2):
        return 2
    if isinstance(policy, PolicyNetwork):
        return 1
    raise ValueError("Unsupported policy architecture")
