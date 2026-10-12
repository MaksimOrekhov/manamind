"""ML-POLICY-V3-1: run many bounded train/validation configs in parallel CPU processes (no test labels).

A sweep file is JSON: {"name": ..., "base": {config}, "grid": {key: [values]}, "seeds": [..]} (v2 and v3 keys may be
mixed through "variants": [{"architecture": "v3", "entity_layers": 0, ...}, ...]). Every run goes to its own NEW
directory under --output; a summary table (validation only) is printed and written next to them.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))


def one(job):
    from train_policy_v3 import run  # imported in the worker
    dataset, split, cards, output, config, label, evaluate_test = job
    result = run(Path(dataset), Path(split), Path(cards), Path(output), config, label=label,
                 evaluate_test=evaluate_test)
    return {"label": label, "config": config, "selected_epoch": result["selected_epoch"],
            "epochs_run": result["epochs_run"], "seconds": result["training_seconds"],
            "val": result["validation"]["learned"], "train": result["train"]["learned"],
            "test": result["test"]["learned"] if evaluate_test else None,
            "best_val_ce": result["best_validation_cross_entropy"]}


def expand(spec):
    variants = spec.get("variants") or [{}]
    keys = sorted(spec.get("grid", {}))
    for variant in variants:
        for values in itertools.product(*(spec["grid"][k] for k in keys)):
            for seed in spec["seeds"]:
                config = {**spec["base"], **variant, **dict(zip(keys, values)), "seed": seed}
                if config["architecture"] == "v2":
                    for extra in ("heads", "entity_layers", "menu_layers"):
                        config.pop(extra, None)
                yield config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sweep", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/processed_policy_v3/dataset")
    parser.add_argument("--split", type=Path, default=ROOT / "data/processed_policy_v3/frozen_split.json")
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--evaluate-test", action="store_true", help="Final pre-registered candidates only")
    args = parser.parse_args()
    spec = json.loads(args.sweep.read_text(encoding="utf-8"))
    jobs = []
    for config in expand(spec):
        label = "_".join(f"{k}{config[k]}" for k in sorted(config)
                         if k in set(spec.get("grid", {})) | set(spec.get("label_keys", [])) | {"architecture", "seed"})
        jobs.append((str(args.dataset), str(args.split), str(args.cards), str(args.output / label), config, label, args.evaluate_test))
    args.output.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, jobs))
    summary = args.output / f"{spec['name']}_summary.json"
    with summary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(results, stream, indent=1, sort_keys=True)
    for r in sorted(results, key=lambda r: r["val"]["cross_entropy"]):
        print(f"{r['label']:<70} ep{r['selected_epoch']:>3}/{r['epochs_run']:>3} "
              f"valCE {r['val']['cross_entropy']:.4f} top1 {r['val']['top1_accuracy']:.3f} "
              f"top3 {r['val']['top3_accuracy']:.3f} | trainCE {r['train']['cross_entropy']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
