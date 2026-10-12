"""ML-POLICY-V3-1 supplementary: grouped 5-fold cross-validation of v2-control vs v3 over ALL matches.

Not used to select anything (configs are the ones fixed on train/validation before this was run). Each fold holds out
whole matches; inside the remaining matches a class/outcome-spread validation group (early stopping) is carved out
by seeded hash. Both architectures see identical folds. Held-out logits of every decision are pooled afterwards and
compared with a match-level bootstrap. Writes only to a NEW directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

FOLDS, VALIDATION_MATCHES, FOLD_SEED = 5, 8, 20261013


def make_folds(games, klass, outcome):
    """Per class, outcome-alternating hash order dealt round-robin to folds (balanced classes and outcomes)."""
    from ml_policy_v3_freeze import balanced_order
    folds = [[] for _ in range(FOLDS)]
    offset = 0
    for name in sorted(set(klass.values())):
        ordered = balanced_order([g for g in games if klass[g] == name], outcome, FOLD_SEED)
        for i, game in enumerate(ordered):
            folds[(i + offset) % FOLDS].append(game)
        offset += len(ordered)
    return [sorted(f) for f in folds]


def one(job):
    from train_policy_v3 import run
    dataset, split, cards, output, config, label, train, validation, test = job
    run(Path(dataset), Path(split), Path(cards), Path(output), config, label=label,
        train_games=train, validation_games=validation, test_games=test)
    return label


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/processed_policy_v3/dataset")
    parser.add_argument("--split", type=Path, default=ROOT / "data/processed_policy_v3/frozen_split.json")
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/policy_v3_1/final_candidates.json")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43])
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    from train_policy_v3 import load_split
    rows, _, _ = load_split(args.dataset, args.split)
    by_game = defaultdict(list)
    for r in rows:
        by_game[r["game_id"]].append(r)
    klass = {g: rs[0]["state"]["self_player"]["player_class"] for g, rs in by_game.items()}
    outcome = {g: rs[0]["final_result"] for g, rs in by_game.items()}
    folds = make_folds(sorted(by_game), klass, outcome)
    spec = json.loads(args.config.read_text(encoding="utf-8"))
    jobs = []
    for k, held in enumerate(folds):
        rest = sorted(set(by_game) - set(held))
        validation = sorted(sorted(rest, key=lambda g: hashlib.sha256(f"{FOLD_SEED}:v:{g}".encode()).hexdigest())
                            [:VALIDATION_MATCHES])
        train = sorted(set(rest) - set(validation))
        for variant in spec["variants"]:
            for seed in args.seeds:
                config = {**spec["base"], **variant, "seed": seed}
                if config["architecture"] == "v2":
                    for extra in ("heads", "entity_layers", "menu_layers"):
                        config.pop(extra)
                label = f"fold{k}_{config['architecture']}_seed{seed}"
                jobs.append((str(args.dataset), str(args.split), str(args.cards), str(args.output / label),
                             config, label, train, validation, held))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "folds.json").write_text(json.dumps(
        {"seed": FOLD_SEED, "folds": folds, "validation_matches_per_fold": VALIDATION_MATCHES}, indent=1), encoding="utf-8")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        print(json.dumps(list(pool.map(one, jobs))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
