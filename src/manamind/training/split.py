"""Deterministic train, validation, and test splitting."""

import random
from dataclasses import dataclass

from manamind.training.synthetic import LabeledState


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    train: list[LabeledState]
    validation: list[LabeledState]
    test: list[LabeledState]


def split_dataset(
    examples: list[LabeledState],
    seed: int = 42,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> DatasetSplit:
    """Split by game so positions from one match cannot leak across splits."""
    if len(examples) < 3:
        raise ValueError("At least three examples are needed for train/validation/test")
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("Train and validation fractions must be positive")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Train and validation fractions must sum to less than one")

    groups: dict[str, list[LabeledState]] = {}
    for index, example in enumerate(examples):
        groups.setdefault(example.game_id or f"__example_{index}", []).append(example)
    if len(groups) < 3:
        raise ValueError("At least three distinct game_id groups are needed for splitting")
    shuffled = list(groups.values())
    random.Random(seed).shuffle(shuffled)
    targets = (train_fraction, validation_fraction, 1 - train_fraction - validation_fraction)
    assigned: list[list[LabeledState]] = [[], [], []]
    total = len(examples)
    for group in shuffled:
        split_index = min(range(3), key=lambda i: len(assigned[i]) / total - targets[i])
        assigned[split_index].extend(group)
    if any(not group for group in assigned):
        # With at least three game groups, seed one game into each split.
        assigned = [[], [], []]
        for index, group in enumerate(shuffled):
            assigned[index % 3].extend(group)
    return DatasetSplit(
        train=assigned[0], validation=assigned[1], test=assigned[2],
    )
