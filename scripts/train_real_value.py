"""Train the existing ValueNetwork from a fixed prepared real-data snapshot."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

from manamind.training.pipeline import _validate_game_disjoint_splits, run_synthetic_training
from manamind.training.synthetic import load_labeled_dataset


EXPECTED_SOURCE = "power_log_ranked_standard"


def validate_snapshot(dataset_dir: str | Path) -> dict[str, int]:
    """Validate all prepared files before allowing the training pipeline to run."""
    root = Path(dataset_dir)
    if not root.is_dir() or not (root / "report.json").is_file():
        raise ValueError("expected a completed prepared snapshot with report.json")
    splits = {}
    all_sample_ids: set[str] = set()
    for name in ("train", "validation", "test"):
        path = root / f"{name}.jsonl"
        if not path.is_file():
            raise ValueError(f"missing {name} split")
        examples = load_labeled_dataset(path)
        for example in examples:
            if not example.game_id.strip() or example.game_id == "None":
                raise ValueError(f"{name} split contains missing game_id")
            if not example.sample_id.strip() or example.sample_id == "None":
                raise ValueError(f"{name} split contains missing sample_id")
            if example.target not in (0.0, 0.5, 1.0):
                raise ValueError(f"{name} split contains invalid value target")
            if example.perspective != "SELF" or example.source != EXPECTED_SOURCE:
                raise ValueError(f"{name} split is not imported SELF Ranked Standard data")
            if example.sample_id in all_sample_ids:
                raise ValueError("sample_id values must be globally unique")
            all_sample_ids.add(example.sample_id)
        splits[name] = examples
    _validate_game_disjoint_splits(splits["train"], splits["validation"], splits["test"])
    return {name: len(examples) for name, examples in splits.items()}


def train_real_value(
    dataset_dir: str | Path,
    checkpoint: str | Path,
    *,
    cards: str | Path = "data/cards/standard_current_enUS.json",
    config: str | Path = "configs/value_v1.yaml",
    epochs: int | None = None,
    batch_size: int | None = None,
    seed: int | None = None,
    smoke: bool = False,
    overwrite_checkpoint: bool = False,
):
    """Validate a pinned snapshot and delegate training to training.pipeline."""
    counts = validate_snapshot(dataset_dir)
    checkpoint_path = Path(checkpoint)
    if checkpoint_path.exists() and not overwrite_checkpoint:
        raise FileExistsError("candidate checkpoint already exists; choose a new path")
    if smoke:
        epochs = 1
    project_root = Path(__file__).resolve().parents[1]
    if smoke:
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_synthetic_training(
                project_root,
                config_path=config,
                epochs=epochs,
                batch_size=batch_size,
                seed=seed,
                dataset_dir=dataset_dir,
                cards_path=cards,
                checkpoint_path=checkpoint_path,
            )
    else:
        result = run_synthetic_training(
            project_root,
            config_path=config,
            epochs=epochs,
            batch_size=batch_size,
            seed=seed,
            dataset_dir=dataset_dir,
            cards_path=cards,
            checkpoint_path=checkpoint_path,
        )
    return {"split_examples": counts, "checkpoint": str(checkpoint_path), "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--cards", type=Path, default=Path("data/cards/standard_current_enUS.json"))
    parser.add_argument("--config", type=Path, default=Path("configs/value_v1.yaml"))
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--smoke", action="store_true", help="run one epoch only")
    parser.add_argument("--overwrite-checkpoint", action="store_true")
    args = parser.parse_args()
    try:
        result = train_real_value(
            args.dataset_dir,
            args.checkpoint,
            cards=args.cards,
            config=args.config,
            epochs=args.epochs,
            batch_size=args.batch_size,
            seed=args.seed,
            smoke=args.smoke,
            overwrite_checkpoint=args.overwrite_checkpoint,
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"training": "REFUSED", "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "training": "COMPLETED",
        "split_examples": result["split_examples"],
        "candidate_checkpoint": result["checkpoint"],
        "quality_claim": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
