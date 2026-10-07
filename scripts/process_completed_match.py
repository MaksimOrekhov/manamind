"""Derive every supported training artifact from one saved raw (completed) match.

The raw one-game slice (``data/raw/collected/<key>.log``) is the source of truth. This module
runs deterministic processors over it, each isolated so that one failure never touches the
raw slice or another processor's output:

    raw slice -> Value examples      (import_power_log, one JSONL per match)
              -> Policy examples     (import_policy_power_log.import_log, same code as the manual CLI)
              -> mechanic evidence   (manamind.evidence.pipeline.run_extraction)

Every processor is idempotent: reprocessing the same match writes nothing new. The CLI
backfills a whole folder of previously collected raw slices without playing a new game.
Output contains only counts and statuses, never log text or names.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import uuid
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.evidence.pipeline import run_extraction

try:
    from scripts.import_policy_power_log import import_log as import_policy_log
    from scripts.import_power_log import import_power_log
except ModuleNotFoundError:
    from import_policy_power_log import import_log as import_policy_log
    from import_power_log import import_power_log

OK = "OK"
DUPLICATE = "DUPLICATE"
FAILED = "FAILED"
SKIPPED = "SKIPPED"  # expected rejection by the processor's own gate; backfill cannot change it


@dataclass
class Outputs:
    value: Path = Path("data/processed_real")
    policy: Path = Path("data/processed_policy_real/collected")
    evidence: Path = Path("data/processed_evidence/collected")


@dataclass
class ProcessorResult:
    status: str
    count: int = 0
    detail: dict = field(default_factory=dict)


def build_value_examples(raw_slice: Path, output_dir: Path, catalog_path: Path) -> ProcessorResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    part = output_dir / f"{uuid.uuid4().hex}.jsonl.part"
    try:
        result = import_power_log(raw_slice, part, catalog_path)
        if result.get("duplicate"):
            return ProcessorResult(DUPLICATE, 0, result)
        os.replace(part, output_dir / f"{uuid.uuid4().hex}.jsonl")
        return ProcessorResult(OK, int(result.get("examples_written", 0)), result)
    finally:
        try:
            part.unlink()
        except OSError:
            pass


def build_policy_examples(raw_slice: Path, output_dir: Path, catalog: CardCatalog | Path) -> ProcessorResult:
    if not isinstance(catalog, CardCatalog):
        catalog = CardCatalog.from_json(catalog)
    # segmented=True: a raw slice is one CREATE_GAME section; the importer re-checks mode/completion.
    # Its game_id duplicate check makes reprocessing a no-op (DUPLICATE_MATCH).
    result = import_policy_log(raw_slice, output_dir, catalog, segmented=True)
    if result["games_imported"]:
        return ProcessorResult(OK, int(result["decisions_labeled"]), result)
    if result["game_skip_reasons"].get("DUPLICATE_MATCH"):
        return ProcessorResult(DUPLICATE, 0, result)
    # Every importer rejection (GAME_RESET, MODE_INELIGIBLE, SELF_AMBIGUOUS, ...) is a deliberate gate.
    return ProcessorResult(SKIPPED, 0, result)


def build_mechanic_observations(raw_slice: Path, output_dir: Path, catalog_path: Path) -> ProcessorResult:
    target = Path(output_dir) / raw_slice.stem  # one directory per match; exists only when complete
    if target.exists():
        return ProcessorResult(DUPLICATE)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Extract into a hidden sibling and rename on success, so a crash never leaves a final
    # directory that looks like a finished extraction.
    partial = target.parent / f".partial-{uuid.uuid4().hex}"
    try:
        manifest = run_extraction([raw_slice], partial, catalog_path=catalog_path)
        os.replace(partial, target)
    finally:
        shutil.rmtree(partial, ignore_errors=True)
    return ProcessorResult(OK, int(manifest["summary"]["observations"]), manifest["games"])


def process_completed_match(
    raw_slice: Path, outputs: Outputs, catalog_path: Path, *, catalog: CardCatalog | None = None,
) -> dict[str, ProcessorResult]:
    """Run all processors on a saved raw slice. Each processor, including loading the card
    catalog for Policy, is isolated: a failure comes back as FAILED instead of raising."""
    raw_slice = Path(raw_slice)
    steps = {
        "value": lambda: build_value_examples(raw_slice, outputs.value, catalog_path),
        "policy": lambda: build_policy_examples(raw_slice, outputs.policy, catalog or catalog_path),
        "observations": lambda: build_mechanic_observations(raw_slice, outputs.evidence, catalog_path),
    }
    results: dict[str, ProcessorResult] = {}
    for name, step in steps.items():
        try:
            results[name] = step()
        except Exception as error:  # privacy: class name only, messages can carry log content
            results[name] = ProcessorResult(FAILED, 0, {"error": type(error).__name__})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill datasets from collected raw match slices.")
    parser.add_argument("raw", type=Path, nargs="+", help="raw slice .log files or folders of them")
    parser.add_argument("--cards", type=Path, default=Path("data/cards/standard_current_enUS.json"))
    parser.add_argument("--value-output", type=Path, default=Outputs.value)
    parser.add_argument("--policy-output", type=Path, default=Outputs.policy)
    parser.add_argument("--evidence-output", type=Path, default=Outputs.evidence)
    args = parser.parse_args()

    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    outputs = Outputs(args.value_output, args.policy_output, args.evidence_output)
    slices = []
    for item in args.raw:
        slices.extend(sorted(item.glob("*.log")) if item.is_dir() else [item])
    catalog = CardCatalog.from_json(args.cards)
    totals: dict[str, dict[str, int]] = {}
    for path in slices:
        for name, result in process_completed_match(path, outputs, args.cards, catalog=catalog).items():
            bucket = totals.setdefault(name, {OK: 0, DUPLICATE: 0, SKIPPED: 0, FAILED: 0, "count": 0})
            bucket[result.status] += 1
            bucket["count"] += result.count
    print(json.dumps({"matches": len(slices), "processors": totals}, sort_keys=True))
    return 1 if any(t[FAILED] for t in totals.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
