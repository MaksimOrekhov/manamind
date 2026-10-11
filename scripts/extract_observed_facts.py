"""Re-extract SELF observed facts for every labeled decision of the raw Power.log corpus (OBSERVATION-EXT-1a).

Each completed match is replayed through the same ``LiveSession`` that built the policy corpus (``extract_match``); the
facts are the ones LIVE would have attached to the decision's snapshot, read from the packets applied so far. Nothing is
written back to the corpus: the output is a new JSONL (one row per decision) in an ignored data directory, plus a
manifest that also compares every regenerated ``state_hash`` with the corpus row, which proves the facts did not move the
state.

  python scripts/extract_observed_facts.py --raw data/raw --corpus data/processed_data_checkpoint_1_20261010/canonical
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match  # noqa: E402


def find(path: str) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    return next((p / path for p in ROOT.parents if (p / path).exists()), candidate)


def corpus_state_hashes(directory: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            hashes[row["decision_id"]] = row["provenance"]["state_hash"]
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--catalog", default="data/cards/standard_current_enUS.json")
    parser.add_argument("--corpus", default="data/processed_data_checkpoint_1_20261010/canonical")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "processed_observation_ext_1a")
    args = parser.parse_args()

    raw, corpus = find(args.raw), find(args.corpus)
    catalog = CardCatalog.from_json(find(args.catalog))
    corpus_hashes = corpus_state_hashes(corpus) if corpus.exists() else {}

    facts: dict[str, dict] = {}
    seen, game_skips, decision_skips, imported = set(), Counter(), Counter(), 0
    state_hash_match = Counter()
    state_hash_by_id: dict[str, str] = {}
    paths = sorted(raw.rglob("*.log"))
    for path in paths:
        for segment in split_games(read_complete_lines(path)):
            key = inspect_segment(segment).start_key
            if key in seen:
                game_skips["DUPLICATE_MATCH"] += 1
                continue
            seen.add(key)
            collected: dict[str, object] = {}
            try:
                rows, summary = extract_match(segment, catalog, lambda decision, found: collected.__setitem__(decision, found))
            except PolicyImportError as error:
                game_skips[error.reason] += 1
                continue
            imported += 1
            decision_skips.update(summary["skip_reasons"])
            for row in rows:
                decision = row["decision_id"]
                found = collected[decision]
                facts[decision] = found.to_dict() if found is not None else None
                state_hash_by_id[decision] = row["provenance"]["state_hash"]
    for decision, regenerated in state_hash_by_id.items():
        if decision in corpus_hashes:
            state_hash_match["same" if corpus_hashes[decision] == regenerated else "DIFFERENT"] += 1
        else:
            state_hash_match["not_in_corpus"] += 1

    ordered = sorted(facts)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "observed_facts.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for decision in ordered:
            stream.write(json.dumps({"decision_id": decision, "facts": facts[decision]}, sort_keys=True) + "\n")
    coverage = Counter((facts[d] or {}).get("coverage", "NONE") for d in ordered)
    manifest = {
        "schema": 1, "raw_log_files": len(paths), "matches_imported": imported,
        "game_skips": dict(sorted(game_skips.items())), "decision_skip_reasons": dict(sorted(decision_skips.items())),
        "labeled_decisions": len(ordered), "decision_ids_sha256": hashlib.sha256("\n".join(ordered).encode()).hexdigest(),
        "coverage": dict(coverage), "facts_missing": sum(facts[d] is None for d in ordered),
        "state_hash_vs_corpus": dict(state_hash_match), "catalog": str(find(args.catalog).name),
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                                newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
