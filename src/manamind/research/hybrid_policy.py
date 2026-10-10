"""Experimental Policy v2 with a masked card-rules-text score channel."""

from __future__ import annotations

import torch
from torch import nn

from manamind.models.policy_v2 import PolicyNetworkV2


class HybridPolicyV2(nn.Module):
    """Add a small text-only score to the unchanged Policy v2 logits."""

    def __init__(self, base: PolicyNetworkV2, text_width: int):
        super().__init__()
        if text_width <= 0:
            raise ValueError("The text vocabulary must be nonempty")
        self.base = base
        self.text_width = text_width
        self.text_score = nn.Sequential(
            nn.Linear(text_width, 32, bias=False), nn.Tanh(), nn.Linear(32, 1, bias=False),
        )

    def forward(self, *inputs: torch.Tensor) -> torch.Tensor:
        if len(inputs) != 8:
            raise ValueError("Hybrid inputs require Policy v2 inputs, text, and a usable mask")
        *base_inputs, text, usable = inputs
        actions = base_inputs[3]
        if text.shape != (len(actions), self.text_width) or usable.shape != (len(actions),):
            raise ValueError("Incompatible hybrid text inputs")
        if not torch.isfinite(text).all() or not torch.isfinite(usable).all():
            raise ValueError("Nonfinite text input")
        return self.base(*base_inputs) + self.text_score(text).squeeze(-1) * usable
