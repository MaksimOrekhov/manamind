"""Generate JSONL train/validation/test files from synthetic positions."""

import argparse
from pathlib import Path

from manamind.cards import CardCatalog
from manamind.training import (
    create_synthetic_catalog,
    generate_synthetic_dataset,
    save_synthetic_dataset,
    split_dataset,
)


ROOT = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed")
    args = parser.parse_args()

    base_catalog = CardCatalog.from_json(ROOT / "data" / "samples" / "sample_cards.json")
    catalog = create_synthetic_catalog(base_catalog)
    examples = generate_synthetic_dataset(args.samples, catalog, seed=args.seed)
    splits = split_dataset(examples, seed=args.seed)
    save_synthetic_dataset(args.output / "train.jsonl", splits.train)
    save_synthetic_dataset(args.output / "validation.jsonl", splits.validation)
    save_synthetic_dataset(args.output / "test.jsonl", splits.test)
    print(
        f"Saved {len(splits.train)} train, {len(splits.validation)} validation, "
        f"and {len(splits.test)} test examples to {args.output}"
    )


if __name__ == "__main__":
    main()
