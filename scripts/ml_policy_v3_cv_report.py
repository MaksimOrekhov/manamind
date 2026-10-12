"""ML-POLICY-V3-1 supplementary: pool the held-out folds of ``ml_policy_v3_cv.py`` and compare v2-control vs v3.

For each seed every decision of all 79 matches is predicted exactly once by a model that never saw its match. Metrics
are pooled per seed, then averaged over seeds; the paired v3-minus-control difference gets a match-level bootstrap
(matches resampled, seeds averaged inside each draw).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ml_policy_v3_compare import METRICS, decision_record, summarize  # noqa: E402
from train_policy_v3 import load_split  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cv_dir", type=Path)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/processed_policy_v3/dataset")
    parser.add_argument("--split", type=Path, default=ROOT / "data/processed_policy_v3/frozen_split.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draws", type=int, default=2000)
    args = parser.parse_args()
    rows, _, _ = load_split(args.dataset, args.split)
    by_id = {r["decision_id"]: r for r in rows}
    records = defaultdict(lambda: defaultdict(list))  # (arch, seed) -> game -> records
    for path in sorted(args.cv_dir.glob("fold*_seed*/heldout_logits.json")):
        _, arch, seed = path.parent.name.split("_")
        for decision_id, logits in json.loads(path.read_text(encoding="utf-8")).items():
            record = decision_record(by_id[decision_id], logits)
            records[(arch, seed)][record["game_id"]].append(record)
    keys = sorted(records)
    for key in keys:
        if sum(map(len, records[key].values())) != len(rows):
            raise SystemExit(f"{key}: held-out folds do not cover every decision exactly once")
    seeds = sorted({s for _, s in keys})
    games = sorted({g for key in keys for g in records[key]})
    result = {"matches": len(games), "decisions": len(rows), "seeds": seeds, "per_seed": {}, "mean_over_seeds": {}}
    for arch, seed in keys:
        flat = [r for g in games for r in records[(arch, seed)][g]]
        result["per_seed"][f"{arch}_{seed}"] = {"overall": summarize(flat),
                                                "by_class": {c: summarize([r for r in flat if r["class"] == c])
                                                             for c in sorted({r["class"] for r in flat})}}
    for arch in ("v2", "v3"):
        result["mean_over_seeds"][arch] = {k: float(np.mean([result["per_seed"][f"{arch}_{s}"]["overall"][k]
                                                              for s in seeds])) for k in METRICS}
    rng = np.random.default_rng(20261013)
    diffs = {k: [] for k in METRICS}
    for _ in range(args.draws):
        picked = [games[i] for i in rng.choice(len(games), size=len(games), replace=True)]
        stats = {arch: [summarize([r for g in picked for r in records[(arch, s)][g]]) for s in seeds]
                 for arch in ("v2", "v3")}
        for k in METRICS:
            diffs[k].append(np.mean([a[k] for a in stats["v3"]]) - np.mean([a[k] for a in stats["v2"]]))
    result["v3_minus_control"] = {k: {"mean": result["mean_over_seeds"]["v3"][k] - result["mean_over_seeds"]["v2"][k],
                                      "ci95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]}
                                  for k, v in diffs.items()}
    for arch in ("v2", "v3"):
        result["per_class_mean_over_seeds_" + arch] = {
            c: {k: float(np.mean([result["per_seed"][f"{arch}_{s}"]["by_class"][c][k] for s in seeds]))
                for k in METRICS} | {"decisions": result["per_seed"][f"{arch}_{seeds[0]}"]["by_class"][c]["decisions"],
                                     "matches": result["per_seed"][f"{arch}_{seeds[0]}"]["by_class"][c]["matches"]}
            for c in sorted(result["per_seed"][f"{arch}_{seeds[0]}"]["by_class"])}
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"mean_over_seeds": result["mean_over_seeds"], "v3_minus_control": result["v3_minus_control"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
