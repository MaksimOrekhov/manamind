"""Print aggregate quality/readiness facts without private identities."""
import argparse
import json
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.training.real_policy import audit_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--cards", type=Path, default=Path("data/cards/standard_current_enUS.json"))
    args = parser.parse_args()
    try:
        summary = audit_dataset(args.directory, CardCatalog.from_json(args.cards))
    except Exception as error:
        print(json.dumps({"privacy_checks": "FAILED", "reason": type(error).__name__}))
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
