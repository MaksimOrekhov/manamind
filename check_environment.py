"""Quick check for the ManaMind Python environment and GPU setup."""

import sys

import torch
from manamind.domain.game_state import GameState

print(f"Python: {sys.version.split()[0]}")
print(f"PyTorch: {torch.__version__}")
print(f"CUDA build: {torch.version.cuda}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GameState import: {GameState.__name__}")

if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    sample = torch.ones(2, device="cuda")
    print(f"Test tensor device: {sample.device}")
