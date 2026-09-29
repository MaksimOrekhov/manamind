"""Train Value Network v1 on synthetic data or a prepared JSONL dataset."""

import argparse
from pathlib import Path

from manamind.training.pipeline import run_synthetic_training

ROOT = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2048)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "value_v1.yaml")
    parser.add_argument("--dataset-dir", type=Path, default=None,
                        help="Load train.jsonl, validation.jsonl, and test.jsonl from this directory")
    parser.add_argument("--cards", type=Path, default=None,
                        help="Card catalog used to encode IDs in a loaded dataset")
    parser.add_argument("--checkpoint", type=Path, default=None,
                        help="Output checkpoint path (default: checkpoints/value_v1_s4.pt)")
    args = parser.parse_args()

    run_synthetic_training(
        project_root=ROOT,
        sample_count=args.samples,
        config_path=args.config,
        epochs=args.epochs,
        batch_size=args.batch_size,
        seed=args.seed,
        dataset_dir=args.dataset_dir,
        cards_path=args.cards,
        checkpoint_path=args.checkpoint,
    )


if __name__ == "__main__":
    main()
