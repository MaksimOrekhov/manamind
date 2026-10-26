"""Check that existing checkpoints and the LIVE runtime are untouched by the new metadata layer (inference-only).

For every LIVE-pinned Policy checkpoint: its SHA-256 equals the digest pinned in ``scripts/run_manamind.py``, the strict
loader accepts it, and the runtime catalog built from ``data/cards/standard_current_enUS.json`` passes the checkpoint's
own catalog identity check. Also records the digests of the pinned model-side artifacts and asserts that loading the
LIVE recommender does not import ``manamind.card_metadata``. Nothing is trained or written except the output file.

    python -I reports/card_metadata_2/verify_compatibility.py --main-checkout E:/ManaMind --output <new json path>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

PINNED = (
    "data/cards/standard_current_enUS.json", "data/cards/source_snapshots/cards_collectible_20261001_enUS.json",
    "data/cards/standard_roots_20261001_enUS.json", "data/cards/standard_scope_20261001.json",
    "data/cards/standard_sets.json", "configs/standard_profile.json", "data/localization/card_names_253932.json",
)


def sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def live_pins(script: Path) -> dict[str, tuple[str, str]]:
    text = script.read_text(encoding="utf-8")
    names = {"policy_v2": "POLICY_V2", "retrained_v2": "RETRAINED_V2", "policy_v3": "POLICY_V3"}
    result = {}
    for name, prefix in names.items():
        path = re.search(rf'{prefix}_CHECKPOINT = ROOT / "([^"]+)"', text).group(1)
        digest = re.search(rf'{prefix}_SHA256 = "([0-9a-f]{{64}})"', text).group(1)
        result[name] = (path, digest)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-checkout", type=Path, required=True, help="checkout that holds the ignored checkpoints")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; refusing to overwrite")

    from manamind.cards.catalog import CardCatalog
    from manamind.live.recommendation import PolicyRecommender, RecommendationUnavailable

    catalog = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")
    result: dict = {"pinned_artifact_sha256": {rel: sha256_lf(ROOT / rel) for rel in PINNED}, "live_checkpoints": {}}
    for name, (rel, digest) in live_pins(ROOT / "scripts/run_manamind.py").items():
        path = args.main_checkout / rel
        entry = {"path": rel, "pinned_sha256": digest, "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        entry["sha_matches_pin"] = entry["file_sha256"] == entry["pinned_sha256"]
        try:
            recommender = PolicyRecommender(path, expected_sha256=digest)
            recommender.require_catalog(catalog)
            entry["strict_loader_and_catalog_identity"] = "PASS"
        except RecommendationUnavailable as error:
            entry["strict_loader_and_catalog_identity"] = f"REFUSED:{error}"
        result["live_checkpoints"][name] = entry
    result["card_metadata_imported_by_live_path"] = any(m == "manamind.card_metadata" or m.startswith("manamind.card_metadata.")
                                                         for m in sys.modules)
    result["model_checkpoint_files"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted((args.main_checkout / "checkpoints").glob("*.pt"))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
