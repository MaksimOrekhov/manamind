"""ML-POLICY-V3-1: compare Policy checkpoints on the frozen split (inference only, no training).

Every checkpoint scores every decision of the dataset once (logits are cached in the output directory); all tables are
then computed from the cache, so each model sees the identical menus. Metrics are Behavior-Cloning agreement with the
human choice: they are not move quality and not playing strength.

  python scripts/ml_policy_v3_compare.py data/processed_policy_v3/dataset --split data/processed_policy_v3/frozen_split.json \
      --model frozen_v2=data/processed_policy_ml2a/seed42_v2/policy.pt --model v3_s42=.../policy.pt --output reports/.../compare
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.models.policy_inputs import representation_of  # noqa: E402
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint  # noqa: E402
from manamind.training.policy_metrics import action_root  # noqa: E402
from manamind.training.real_policy import encode_example, load_examples  # noqa: E402

BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261012


def model_logits(path: Path, rows) -> dict[str, list[float]]:
    policy, encoder, _ = load_policy_checkpoint(path)
    representation = representation_of(policy)
    policy.eval()
    out = {}
    with torch.no_grad():
        for row in rows:
            logits = policy(*encode_example(row, encoder, representation=representation))
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite logits")
            out[row["decision_id"]] = logits.tolist()
    return out


def decision_record(row, logits) -> dict:
    actions, chosen = row["legal_actions"], row["chosen_action_index"]
    values = np.asarray(logits, dtype=np.float64)
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))  # stable, like policy_metrics
    rank = order.index(chosen) + 1
    shifted = values - values.max()
    loss = float(math.log(np.exp(shifted).sum()) - shifted[chosen])
    roots = [action_root(a) for a in actions]
    chosen_root = roots[chosen]
    top = actions[order[0]]
    state = row["state"]
    record = {
        "game_id": row["game_id"], "decision_id": row["decision_id"], "class": state["self_player"]["player_class"],
        "opponent_class": state["opponent"]["player_class"], "menu_size": len(actions), "rank": rank, "loss": loss,
        "chosen_kind": actions[chosen]["type"], "pred_kind": top["type"], "pred_index": order[0], "chosen_index": chosen,
        "n_roots": len(set(roots)), "mana": state["self_player"]["available_mana"],
        "root_correct": roots[order[0]] == chosen_root, "targeted": "target_kind" in actions[chosen],
        "kinds_in_menu": sorted({a["type"] for a in actions}),
        "top3_kinds": [actions[i]["type"] for i in order[:3]],
    }
    # Target choice once the source/card is fixed: argmax among the chosen root's targeted variants.
    if record["targeted"]:
        variants = [i for i, a in enumerate(actions) if roots[i] == chosen_root and "target_kind" in a]
        record["target_variants"] = len(variants)
        record["target_correct_given_root"] = max(variants, key=lambda i: (values[i], -i)) == chosen
    # Best-ranked PLAY_CARD above HERO_POWER?
    plays = [i for i, a in enumerate(actions) if a["type"] == "PLAY_CARD"]
    hp = [i for i, a in enumerate(actions) if a["type"] == "HERO_POWER"]
    if plays and hp:
        record["card_above_hero_power"] = order.index(min(plays, key=order.index)) < order.index(hp[0])
    record["hero_power_legal"] = bool(hp)
    return record


def summarize(records) -> dict:
    n = len(records)
    if not n:
        return {"decisions": 0}
    eligible = [r for r in records if r["menu_size"] >= 3]
    return {"decisions": n, "matches": len({r["game_id"] for r in records}),
            "cross_entropy": sum(r["loss"] for r in records) / n,
            "top1_accuracy": sum(r["rank"] == 1 for r in records) / n,
            "top3_accuracy": sum(r["rank"] <= 3 for r in eligible) / len(eligible) if eligible else None,
            "top3_decisions": len(eligible), "mean_reciprocal_rank": sum(1 / r["rank"] for r in records) / n}


METRICS = ("cross_entropy", "top1_accuracy", "top3_accuracy", "mean_reciprocal_rank")


def cluster_bootstrap(per_model: dict[str, list[dict]], pairs, seed=BOOTSTRAP_SEED, draws=BOOTSTRAP) -> dict:
    """Resample whole matches (decisions in a match are dependent); pooled-decision metrics per draw."""
    games = sorted({r["game_id"] for r in next(iter(per_model.values()))})
    by_model = {m: defaultdict(list) for m in per_model}
    for m, records in per_model.items():
        for r in records:
            by_model[m][r["game_id"]].append(r)
    rng = np.random.default_rng(seed)
    samples = {m: {k: [] for k in METRICS} for m in per_model}
    diffs = {pair: {k: [] for k in METRICS} for pair in pairs}
    for _ in range(draws):
        picked = rng.choice(len(games), size=len(games), replace=True)
        stats = {}
        for m in per_model:
            records = [r for i in picked for r in by_model[m][games[i]]]
            stats[m] = summarize(records)
            for k in METRICS:
                samples[m][k].append(stats[m][k])
        for a, b in pairs:
            for k in METRICS:
                if stats[a][k] is not None and stats[b][k] is not None:
                    diffs[(a, b)][k].append(stats[a][k] - stats[b][k])
    def ci(values):
        values = [v for v in values if v is not None]
        return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))] if values else None
    return {"models": {m: {k: ci(v) for k, v in s.items()} for m, s in samples.items()},
            "paired_differences": {f"{a}-{b}": {k: {"ci95": ci(v), "p_nonpositive_improvement": None}
                                                for k, v in s.items()} for (a, b), s in diffs.items()}}


def breakdown(records, field):
    groups = defaultdict(list)
    for r in records:
        groups[str(r[field])].append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}


def per_model_report(records) -> dict:
    nontrivial3 = [r for r in records if r["n_roots"] >= 3]
    nontrivial2 = [r for r in records if r["n_roots"] >= 2]
    targeted = [r for r in records if r["targeted"]]
    given = [r for r in targeted if r.get("target_variants", 0) > 1]
    confusion = Counter((r["chosen_kind"], r["pred_kind"]) for r in records)
    premature = [r for r in records if r["pred_kind"] == "END_TURN" and r["chosen_kind"] != "END_TURN"]
    return {
        "overall": summarize(records), "nontrivial_roots_ge2": summarize(nontrivial2),
        "nontrivial_roots_ge3": summarize(nontrivial3),
        "by_class": breakdown(records, "class"), "by_chosen_kind": breakdown(records, "chosen_kind"),
        "targeted": {"decisions": len(targeted), "top1_exact": sum(r["rank"] == 1 for r in targeted) / len(targeted)
                     if targeted else None,
                     "root_correct": sum(r["root_correct"] for r in targeted) / len(targeted) if targeted else None,
                     "target_correct_given_root": sum(r["target_correct_given_root"] for r in given) / len(given)
                     if given else None, "decisions_with_several_targets": len(given)},
        "pred_kind_counts": dict(Counter(r["pred_kind"] for r in records)),
        "chosen_kind_counts": dict(Counter(r["chosen_kind"] for r in records)),
        "confusion_chosen_to_predicted": {f"{a}->{b}": c for (a, b), c in sorted(confusion.items())},
        "end_turn": {"top1_end_turn_but_player_acted": len(premature),
                     "player_ended_but_top1_acted": sum(r["chosen_kind"] == "END_TURN" and r["pred_kind"] != "END_TURN"
                                                       for r in records)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--model", action="append", required=True, help="name=checkpoint path (first is the reference)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parts", nargs="+", default=["test", "validation"])
    parser.add_argument("--pair", action="append", default=[], help="a-b: extra paired difference a minus b")
    args = parser.parse_args()
    split = json.loads(args.split.read_text(encoding="utf-8"))
    rows = sorted(load_examples(args.dataset), key=lambda r: r["decision_id"])
    if identity(rows) != split["dataset_sha256"]:
        raise SystemExit("dataset differs from the frozen split")
    args.output.mkdir(parents=True, exist_ok=True)
    cache_path = args.output / "logits_cache.pkl"
    cache = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
    models = dict(item.split("=", 1) for item in args.model)
    for name, path in models.items():
        if name not in cache:
            cache[name] = model_logits(Path(path), rows)
    cache_path.write_bytes(pickle.dumps(cache))
    result = {"models": {n: str(p) for n, p in models.items()}, "parts": {}}
    reference = next(iter(models))
    for part in args.parts:
        games = set(split["game_ids"][part])
        part_rows = [r for r in rows if r["game_id"] in games]
        records = {n: [decision_record(r, cache[n][r["decision_id"]]) for r in part_rows] for n in models}
        pairs = [(n, reference) for n in models if n != reference] + [tuple(p.split("-", 1)) for p in args.pair]
        result["parts"][part] = {"matches": len(games), "decisions": len(part_rows),
                                 "models": {n: per_model_report(rs) for n, rs in records.items()},
                                 "bootstrap_by_match": cluster_bootstrap(records, pairs)}
    with (args.output / "comparison.json").open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    for part, body in result["parts"].items():
        print(f"== {part}: {body['matches']} matches / {body['decisions']} decisions")
        for n, rep in body["models"].items():
            o = rep["overall"]
            print(f"  {n:<22} CE {o['cross_entropy']:.4f}  top1 {o['top1_accuracy']:.4f}  top3 {o['top3_accuracy']:.4f}  "
                  f"MRR {o['mean_reciprocal_rank']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
