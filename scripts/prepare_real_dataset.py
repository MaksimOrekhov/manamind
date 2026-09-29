"""Validate, deduplicate, and split imported real matches by whole game."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from manamind.training.synthetic import LabeledState, load_labeled_dataset, save_synthetic_dataset


SPLIT_FRACTIONS = (0.60, 0.20, 0.20)
SPLIT_NAMES = ("train", "validation", "test")
EXPECTED_SOURCE = "power_log_ranked_standard"


def _match_fingerprint(examples: list[LabeledState]) -> str:
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


def _largest_remainder_counts(total: int) -> list[int]:
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


def _split_matches(
    matches: dict[str, list[LabeledState]], seed: int,
) -> dict[str, list[LabeledState]]:
    by_target: dict[float, list[tuple[str, list[LabeledState]]]] = {}
    for game_id, examples in matches.items():
        by_target.setdefault(examples[0].target, []).append((game_id, examples))

    rng = random.Random(seed)
    split_matches: dict[str, list[tuple[str, list[LabeledState]]]] = {
        name: [] for name in SPLIT_NAMES
    }
    for target in sorted(by_target):
        groups = by_target[target]
        rng.shuffle(groups)
        counts = _largest_remainder_counts(len(groups))
        cursor = 0
        for name, count in zip(SPLIT_NAMES, counts, strict=True):
            split_matches[name].extend(groups[cursor:cursor + count])
            cursor += count

    result = {
        name: [example for _, examples in groups for example in examples]
        for name, groups in split_matches.items()
    }
    game_sets = [
        {game_id for game_id, _ in split_matches[name]} for name in SPLIT_NAMES
    ]
    if any(game_sets[left] & game_sets[right] for left in range(3) for right in range(left + 1, 3)):
        raise RuntimeError("A match was assigned to more than one split")
    if any(not result[name] for name in SPLIT_NAMES):
        raise ValueError("Not enough matches to populate train, validation, and test")
    return result


def prepare_dataset(input_dir: Path, output_dir: Path, seed: int) -> dict[str, Any]:
    files = sorted(input_dir.glob("*.jsonl"))
    if not files:
        raise ValueError(f"No imported JSONL files found in {input_dir}")

    matches: dict[str, list[LabeledState]] = {}
    rows_loaded = 0
    for path in files:
        examples = load_labeled_dataset(path)
        rows_loaded += len(examples)
        for example in examples:
            if not example.game_id:
                raise ValueError(f"Missing game_id in {path}")
            if example.perspective != "SELF":
                raise ValueError(f"Expected SELF perspective in {path}")
            if example.source != EXPECTED_SOURCE:
                raise ValueError(f"Unexpected data source in {path}: {example.source}")
            matches.setdefault(example.game_id, []).append(example)

    duplicate_match_count = 0
    unique_matches: dict[str, list[LabeledState]] = {}
    fingerprints: dict[str, str] = {}
    for game_id, examples in matches.items():
        targets = {example.target for example in examples}
        if len(targets) != 1:
            raise ValueError(f"Match {game_id} contains inconsistent outcome labels")
        sample_ids = [example.sample_id for example in examples]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError(f"Match {game_id} contains duplicate sample IDs")

        fingerprint = _match_fingerprint(examples)
        if fingerprint in fingerprints:
            duplicate_match_count += 1
            continue
        fingerprints[fingerprint] = game_id
        unique_matches[game_id] = examples

    if len(unique_matches) < 3:
        raise ValueError("At least three unique matches are needed for data splits")

    splits = _split_matches(unique_matches, seed)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, examples in splits.items():
        save_synthetic_dataset(output_dir / f"{name}.jsonl", examples)

    split_summary = {}
    for name, examples in splits.items():
        target_by_game = {example.game_id: example.target for example in examples}
        split_summary[name] = {
            "matches": len(target_by_game),
            "examples": len(examples),
            "match_outcomes": {
                "wins": sum(1 for target in target_by_game.values() if target == 1.0),
                "losses": sum(1 for target in target_by_game.values() if target == 0.0),
                "draws": sum(1 for target in target_by_game.values() if target == 0.5),
            },
        }

    report = {
        "input_files": len(files),
        "rows_loaded": rows_loaded,
        "match_groups_before_deduplication": len(matches),
        "duplicate_matches_removed": duplicate_match_count,
        "unique_matches": len(unique_matches),
        "unique_examples": sum(len(examples) for examples in unique_matches.values()),
        "outcomes": {
            "wins": sum(1 for examples in unique_matches.values() if examples[0].target == 1.0),
            "losses": sum(1 for examples in unique_matches.values() if examples[0].target == 0.0),
            "draws": sum(1 for examples in unique_matches.values() if examples[0].target == 0.5),
        },
        "seed": seed,
        "split_summary": split_summary,
        "note": "Small pilot dataset; held-out metrics are highly uncertain and do not show playing strength.",
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/processed_real"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed_real/pilot_splits"),
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        report = prepare_dataset(args.input_dir, args.output_dir, args.seed)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
