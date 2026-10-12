"""ML-POLICY-V3-1: audit a fresh Policy dataset and freeze an independent whole-match split.

Reads the dataset and the frozen v2 checkpoint only. The matches that Policy v2 trained on or was selected with
(its train/validation/test) can never enter the new validation/test; they are forced into train. Held-out matches
are chosen per SELF class, outcome-balanced, by a seeded hash order and fixed quotas written down before any
training. Output: one new JSON file (refuses to overwrite).

  python scripts/ml_policy_v3_freeze.py data/processed_policy_v3/dataset --output data/processed_policy_v3/frozen_split.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint  # noqa: E402
from manamind.training.real_policy import audit_dataset, load_examples  # noqa: E402

SPLIT_SEED = 20261012
TEST_QUOTA = {"PRIEST": 6, "WARRIOR": 3, "DEMONHUNTER": 3, "DEATHKNIGHT": 1, "WARLOCK": 0}
VALIDATION_QUOTA = {"PRIEST": 5, "WARRIOR": 2, "DEMONHUNTER": 2, "DEATHKNIGHT": 1, "WARLOCK": 0}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def order_by_hash(games, seed):
    return sorted(games, key=lambda g: hashlib.sha256(f"{seed}:{g}".encode()).hexdigest())


def balanced_order(games, outcome, seed):
    """Hash-ordered games of one class, alternating outcomes (larger outcome group first)."""
    queues = sorted((order_by_hash([g for g in games if outcome[g] == r], seed) for r in sorted({outcome[g] for g in games})),
                    key=len, reverse=True)
    result = []
    while any(queues):
        for queue in queues:
            if queue:
                result.append(queue.pop(0))
    return result


def freeze(dataset: Path, v2_checkpoint: Path, cards: Path, raw_dir: Path | None) -> dict:
    catalog = CardCatalog.from_json(cards)
    audit = audit_dataset(dataset, catalog)
    rows = sorted(load_examples(dataset), key=lambda r: r["decision_id"])
    by_game = defaultdict(list)
    for row in rows:
        by_game[row["game_id"]].append(row)
    outcome = {g: rs[0]["final_result"] for g, rs in by_game.items()}
    klass = {g: rs[0]["state"]["self_player"]["player_class"] for g, rs in by_game.items()}
    checks = {
        "unique_game_ids": len(by_game), "unique_decision_ids": len({r["decision_id"] for r in rows}),
        "decisions": len(rows),
        "state_hash_reused": len(rows) - len({r["provenance"]["state_hash"] for r in rows}),
        "identical_chosen_sequences": 0,
    }
    seqs = Counter(tuple((r["legal_actions"][r["chosen_action_index"]]["type"],
                          r["legal_actions"][r["chosen_action_index"]].get("card_id")) for r in rs)
                   for rs in by_game.values())
    checks["identical_chosen_sequences"] = sum(c - 1 for c in seqs.values() if c > 1)
    if raw_dir is not None:
        digests = Counter(sha256_file(p) for p in sorted(Path(raw_dir).glob("*.log")))
        checks["raw_logs"] = sum(digests.values())
        checks["duplicate_raw_log_files"] = sum(c - 1 for c in digests.values() if c > 1)
    if (checks["unique_decision_ids"] != len(rows) or checks["state_hash_reused"]
            or checks["identical_chosen_sequences"] or checks.get("duplicate_raw_log_files")):
        raise SystemExit(f"duplicate data detected: {checks}")
    _, _, payload = load_policy_checkpoint(v2_checkpoint)
    v2_games = set(sum(payload["experiment"]["split"]["game_ids"].values(), []))
    present_v2 = sorted(v2_games & set(by_game))
    eligible = sorted(set(by_game) - v2_games)
    test, validation = [], []
    for name in sorted({klass[g] for g in eligible}):
        ordered = balanced_order([g for g in eligible if klass[g] == name], outcome, SPLIT_SEED)
        n_test, n_val = TEST_QUOTA.get(name, 0), VALIDATION_QUOTA.get(name, 0)
        if n_test + n_val > len(ordered):
            raise SystemExit(f"quota exceeds matches of {name}")
        test += ordered[:n_test]
        validation += ordered[n_test:n_test + n_val]
    held = set(test) | set(validation)
    train = sorted(set(by_game) - held)
    parts = {"train": train, "validation": sorted(validation), "test": sorted(test)}
    if (set(train) & set(validation) or set(train) & set(test) or set(validation) & set(test)
            or held & v2_games or sum(map(len, parts.values())) != len(by_game)):
        raise SystemExit("split invariants violated")
    summary = {name: {"matches": len(g), "decisions": sum(len(by_game[x]) for x in g),
                      "classes": dict(sorted(Counter(klass[x] for x in g).items())),
                      "wins": sum(outcome[x] == 1.0 for x in g), "losses": sum(outcome[x] == 0.0 for x in g)}
               for name, g in parts.items()}
    return {
        "algorithm": "ml_policy_v3_1_class_outcome_balanced_hash_split/1", "seed": SPLIT_SEED,
        "quota": {"test": TEST_QUOTA, "validation": VALIDATION_QUOTA},
        "dataset_sha256": identity(rows), "audit": audit, "checks": checks,
        "v2_checkpoint_sha256": sha256_file(v2_checkpoint),
        "v2_historical_matches": len(v2_games), "v2_historical_matches_present_in_corpus": len(present_v2),
        "v2_historical_matches_absent_from_corpus": len(v2_games) - len(present_v2),
        "v2_matches_forced_to_train": present_v2,
        "catalog_sha256": identity(catalog.to_dict()),
        "files": {p.name: sha256_file(p) for p in sorted(Path(dataset).iterdir()) if p.is_file()},
        "game_ids": parts, "summary": summary,
        "decision_ids": {k: [r["decision_id"] for r in rows if r["game_id"] in set(v)] for k, v in parts.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--v2-checkpoint", type=Path, default=ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt")
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw/collected")
    args = parser.parse_args()
    result = freeze(args.dataset, args.v2_checkpoint, args.cards, args.raw_dir)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("dataset_sha256", "checks", "summary", "v2_historical_matches_present_in_corpus")},
                     indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
