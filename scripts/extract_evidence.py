"""Extract sanitized unsupported-card evidence from completed Ranked Standard Power.log games.

Offline only. Reads logs read-only, writes a NEW output directory, prints aggregate counts and
exception class names, never names, identities or log text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.evidence import EXTRACTOR_VERSION  # noqa: E402
from manamind.evidence.pipeline import run_extraction  # noqa: E402
from manamind.evidence.privacy import PrivacyError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, nargs="+", type=Path,
                        help="Power.log, collector slice or a directory of slices (read-only)")
    parser.add_argument("--output", required=True, type=Path,
                        help=f"NEW directory, for example data/processed_evidence/{EXTRACTOR_VERSION}/<run>")
    parser.add_argument("--support-inventory", type=Path, default=None,
                        help="exported ManaEngine support inventory; default: declaration proxy")
    parser.add_argument("--catalog", type=Path, default=None, help="card catalog for the public-state projection")
    parser.add_argument("--card-metadata", type=Path, default=None,
                        help="full card metadata (collectible flags) for registry scope of non-root ids")
    parser.add_argument("--include-secondary", action="store_true",
                        help="also extract non-Ranked-Standard games, tagged OTHER_MODE_SECONDARY")
    parser.add_argument("--max-control-samples", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        manifest = run_extraction(
            args.input, args.output, inventory_path=args.support_inventory, catalog_path=args.catalog,
            metadata_path=args.card_metadata, include_secondary=args.include_secondary,
            max_control_samples=args.max_control_samples,
        )
    except FileExistsError:
        print("error: OUTPUT_EXISTS (choose a new directory)", file=sys.stderr)
        return 2
    except PrivacyError:
        print("error: PRIVACY_SCAN_FAILED (output removed)", file=sys.stderr)
        return 3
    except Exception as error:  # noqa: BLE001 - class name only; messages can contain player data
        print(f"error: {type(error).__name__}", file=sys.stderr)
        return 1
    print(json.dumps({k: manifest[k] for k in ("games", "windows", "summary", "privacy_scan")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
