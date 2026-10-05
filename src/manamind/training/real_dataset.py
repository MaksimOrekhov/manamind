"""Shared validation and whole-match partitioning for imported real games."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict

from manamind.training.synthetic import LabeledState


SPLIT_FRACTIONS = (0.60, 0.20, 0.20)
SPLIT_NAMES = ("train", "validation", "test")
EXPECTED_SOURCE = "power_log_ranked_standard"


def match_fingerprint(examples: list[LabeledState]) -> str:
    """Hash a complete ordered match trajectory without external identifiers."""
    rows = [
        {
            "state": asdict(example.state),
            "target": example.target,
            "perspective": example.perspective,
        }
        for example in examples
    ]
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def largest_remainder_counts(total: int) -> list[int]:
    exact = [total * fraction for fraction in SPLIT_FRACTIONS]
    counts = [int(value) for value in exact]
    remainder = total - sum(counts)
    order = sorted(
        range(len(exact)), key=lambda index: (exact[index] - counts[index], -index),
        reverse=True,
    )
    for index in order[:remainder]:
        counts[index] += 1
    return counts


def split_matches(
    matches: dict[str, list[LabeledState]], seed: int,
) -> dict[str, list[LabeledState]]:
    """Split whole games, stratified by each game's final target."""
    by_target: dict[float, list[tuple[str, list[LabeledState]]]] = {}
    for game_id, examples in matches.items():
        by_target.setdefault(examples[0].target, []).append((game_id, examples))

    rng = random.Random(seed)
    split_matches_by_name: dict[str, list[tuple[str, list[LabeledState]]]] = {
        name: [] for name in SPLIT_NAMES
    }
    for target in sorted(by_target):
        groups = by_target[target]
        rng.shuffle(groups)
        counts = largest_remainder_counts(len(groups))
        cursor = 0
        for name, count in zip(SPLIT_NAMES, counts, strict=True):
            split_matches_by_name[name].extend(groups[cursor:cursor + count])
            cursor += count

    result = {
        name: [example for _, examples in groups for example in examples]
        for name, groups in split_matches_by_name.items()
    }
    game_sets = [
        {game_id for game_id, _ in split_matches_by_name[name]}
        for name in SPLIT_NAMES
    ]
    if any(
        game_sets[left] & game_sets[right]
        for left in range(3) for right in range(left + 1, 3)
    ):
        raise RuntimeError("A match was assigned to more than one split")
    if any(not result[name] for name in SPLIT_NAMES):
        raise ValueError("Not enough matches to populate train, validation, and test")
    return result
