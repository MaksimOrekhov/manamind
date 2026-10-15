"""ML-PREPARE-ABLATION-1: compare Policy v2 with and without the ``prepare_card`` input on identical data (inference only).

Models (all seeds 42-44, Policy v2, validation + test_seen of the ML-PREPARE-TRAIN-1 split, never fresh_holdout):
  prepare_v2    ML-PREPARE-TRAIN-1 models, feature on                 (existing checkpoints, read only)
  ablated_v2    same data/seed/config, ``prepare_card`` forced to 0   (retrained here)
  control_v2    ML-PREPARE-TRAIN-1 control, schema 1 data only        (existing, read only)
Probes without training: prepare_v2 scored with the column zeroed; prepare_v2 / ablated_v2 scored with the JAIL_913 card
identity mapped to the unknown-card embedding. Metrics are agreement with the player's choice, not playing strength.

  python scripts/ml_prepare_ablation_analyze.py --output reports/ml_prepare_ablation_1
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import ml_prepare_analyze as base  # noqa: E402
import ml_prepare_train as experiment  # noqa: E402
from manamind.cards.vocabulary import CardVocabulary  # noqa: E402
from manamind.models.policy_inputs import representation_of  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402
from manamind.training.real_policy import encode_example  # noqa: E402

TRAIN_RUNS = experiment.OUTPUT
ABLATION_RUNS = ROOT / "data/processed_policy_prepare_ablation_1"
SEEDS = (42, 43, 44)
JAIL = "JAIL_913"
SUBSETS = {**base.SUBSETS,
           "prepare_menu_with_JAIL_913": lambda f: JAIL in f["prepare_cards"],
           "prepare_menu_without_JAIL_913": lambda f: f["has_prepare"] and JAIL not in f["prepare_cards"]}
SHOWN = tuple(SUBSETS)
PAIRED_SUBSETS = ("all", "no_prepare_in_menu", "prepare_in_menu", "play_and_prepare", "prepare_only",
                  "player_chose_prepare", "player_chose_other_prepare_available", "prepare_menu_with_JAIL_913",
                  "prepare_menu_without_JAIL_913")
FEATURE_USEFUL, WEAK, INCONCLUSIVE = "FEATURE_USEFUL", "FEATURE_WEAK_OR_REDUNDANT", "INCONCLUSIVE"


def unknown_card_encoder(encoder, token):
    """The same encoder with one card id mapped to the unknown-card embedding (stats and text metadata unchanged)."""
    vocabulary = CardVocabulary.from_dict(encoder.vocabulary.to_dict())
    vocabulary._card_ids.pop(token)
    encoder.vocabulary = vocabulary
    encoder.entity_encoder.vocabulary = vocabulary
    return encoder


def score(path: Path, rows, expected_sha256: str, *, mask=None, unknown_card=None) -> tuple[dict, dict]:
    """Logits per decision. ``mask`` None = as trained (ablated checkpoints are always masked), True/False = forced."""
    data = Path(path).read_bytes()
    if base.hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"{path} differs from its recorded SHA-256")
    policy, encoder, payload = load_policy_checkpoint(io.BytesIO(data), allow_prepare=True)
    if representation_of(policy) != 2:
        raise ValueError("This analysis is for Policy v2")
    if mask is None:
        mask = bool(payload["experiment"].get("ablate_prepare_feature"))
    if unknown_card:
        encoder = unknown_card_encoder(encoder, unknown_card)
    logits = {}
    with torch.no_grad():
        for row in rows:
            value = policy(*encode_example(row, encoder, representation=2, allow_prepare=True,
                                           mask_prepare_feature=mask))
            if value.shape != (len(row["legal_actions"]),) or not torch.isfinite(value).all():
                raise ValueError("Bad logits")
            logits[row["decision_id"]] = value.tolist()
    return logits, payload


def run_digest(directory: Path) -> str:
    return json.loads((directory / "metrics.json").read_text(encoding="utf-8"))["checkpoint_sha256"]


def verdict(report: dict) -> dict:
    """The rules registered in configs/ml_prepare_ablation_1/experiment.json."""
    diffs, per_seed = report["paired"]["prepare_v2_minus_ablated_v2"]["differences"], \
        report["paired"]["prepare_v2_minus_ablated_v2"]["per_seed"]
    seeds = report["seeds"]
    need = -(-2 * len(seeds) // 3)
    pm = diffs["pooled/prepare_in_menu"]["cross_entropy"]
    parts = {p: diffs[f"{p}/prepare_in_menu"]["cross_entropy"]["difference"] for p in base.PARTITIONS}
    seeds_ok = {p: sum((per_seed[f"{p}/prepare_in_menu/seed{s}"]["cross_entropy"] or 0) < 0 for s in seeds)
                for p in base.PARTITIONS}
    other = diffs["pooled/no_prepare_in_menu"]["cross_entropy"]
    useful = (pm["difference"] < 0 and pm["ci95"][1] < 0 and all(v < 0 for v in parts.values())
              and all(v >= need for v in seeds_ok.values()) and other["difference"] <= 0.03
              and other["ci95"][1] <= 0.05)
    weak = (-0.10 <= pm["ci95"][0] and pm["ci95"][1] <= 0.10) or pm["ci95"][0] > 0
    # The two registered rules can both hold (a tiny but very precise difference). The registered text for
    # FEATURE_WEAK_OR_REDUNDANT is the more specific statement about size, so it wins a tie; this is a clarification
    # made after the first run of this code produced the tie, and the tie is reported.
    final = WEAK if weak else FEATURE_USEFUL if useful else INCONCLUSIVE
    return {"registered_conditions_met": {"FEATURE_USEFUL": bool(useful), "FEATURE_WEAK_OR_REDUNDANT": bool(weak)},
            "rule_overlap_resolved_in_favour_of": WEAK if useful and weak else None,
            "share_of_total_prepare_v2_vs_control_gain_explained_by_the_column": None,
            "verdict_if_first_matching_rule_in_registration_order_were_used": FEATURE_USEFUL if useful else WEAK if weak else INCONCLUSIVE,
            "prepare_menu_ce_difference_pooled": pm, "by_partition": parts, "seeds_with_negative_difference": seeds_ok,
            "seeds_needed": need, "no_prepare_menu_ce_difference_pooled": other,
            "verdict": final, "strength_claim": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-runs", type=Path, default=TRAIN_RUNS)
    parser.add_argument("--ablation-runs", type=Path, default=ABLATION_RUNS)
    args = parser.parse_args()
    plan = experiment.load_plan()
    parts, _ = experiment.load_parts(experiment.CORPUS, plan)
    rows_by_part = {n: parts[n] for n in base.PARTITIONS}
    rows = [r for n in base.PARTITIONS for r in rows_by_part[n]]
    part_of = {r["decision_id"]: n for n in base.PARTITIONS for r in rows_by_part[n]}
    facts = [base.decision_facts(r) for r in rows]
    if {r["game_id"] for r in rows} & set(plan["parts"]["fresh_holdout"]):
        raise ValueError("fresh_holdout matches reached the analysis")

    variants = {}  # name -> (group, seed, directory, kwargs)
    for seed in SEEDS:
        prepare, control, ablated = (args.train_runs / f"prepare_v2_seed{seed}", args.train_runs / f"control_v2_seed{seed}",
                                     args.ablation_runs / f"ablated_v2_seed{seed}")
        variants[f"prepare_v2_s{seed}"] = ("prepare_v2", seed, prepare, {"mask": False})
        variants[f"control_v2_s{seed}"] = ("control_v2", seed, control, {"mask": False})
        variants[f"ablated_v2_s{seed}"] = ("ablated_v2", seed, ablated, {})
        variants[f"prepare_v2_masked_at_inference_s{seed}"] = ("prepare_v2_masked_at_inference", seed, prepare, {"mask": True})
        variants[f"prepare_v2_no_JAIL_913_identity_s{seed}"] = ("prepare_v2_no_JAIL_913_identity", seed, prepare,
                                                               {"mask": False, "unknown_card": JAIL})
        variants[f"ablated_v2_no_JAIL_913_identity_s{seed}"] = ("ablated_v2_no_JAIL_913_identity", seed, ablated,
                                                               {"unknown_card": JAIL})
    logits, payloads, records, digests = {}, {}, {}, {}
    for name, (_, _, directory, kwargs) in variants.items():
        digests[name] = run_digest(directory)
        logits[name], payloads[name] = score(directory / "policy.pt", rows, digests[name], **kwargs)
        records[name] = [base.record(r, f, logits[name][r["decision_id"]]) for r, f in zip(rows, facts)]
        print("scored", name, flush=True)
    groups = defaultdict(list)
    for name, (group, *_rest) in variants.items():
        groups[group].append(name)

    masks = {s: np.array([fn(f) for f in facts]) for s, fn in SUBSETS.items()}
    scopes = {**{p: np.array([part_of[f["decision_id"]] == p for f in facts]) for p in base.PARTITIONS},
              "pooled": np.ones(len(rows), dtype=bool)}

    def items(name, scope, subset):
        return [(facts[i], records[name][i]) for i in np.flatnonzero(masks[subset] & scopes[scope])]

    report = {"schema": "manamind.ml_prepare_ablation_1_results/1", "seeds": list(SEEDS), "fresh_holdout_opened": False,
              "partition_names": {"validation": "validation", "test": "test_seen (not independent)"},
              "bootstrap": {"draws": base.DRAWS, "seed": base.BOOTSTRAP_SEED, "unit": "whole matches"}}
    report["data"] = {sc: {s: {"decisions": int((masks[s] & scopes[sc]).sum()),
                               "matches": len({facts[i]["game_id"] for i in np.flatnonzero(masks[s] & scopes[sc])})}
                           for s in SHOWN} for sc in scopes}
    report["uniform_random"] = {sc: {s: base.uniform_of([facts[i] for i in np.flatnonzero(masks[s] & scopes[sc])])
                                     for s in SHOWN} for sc in scopes}
    report["models"] = {n: {sc: {s: base.metrics_of(items(n, sc, s)) for s in SHOWN} for sc in scopes} for n in variants}
    report["groups"] = {}
    for group, members in groups.items():
        report["groups"][group] = {sc: {s: {m: base.stats([report["models"][n][sc][s].get(m) for n in members])
                                            for m in base.METRICS} for s in SHOWN} for sc in scopes}

    def paired(first, second):
        mean_a = base.averaged([records[f"{first}_s{s}"] for s in SEEDS])
        mean_b = base.averaged([records[f"{second}_s{s}"] for s in SEEDS])
        out = {"differences": {}, "per_seed": {}}
        for sc in scopes:
            for s in PAIRED_SUBSETS:
                out["differences"][f"{sc}/{s}"] = base.paired_bootstrap(facts, mean_a, mean_b, masks[s] & scopes[sc])
                for seed in SEEDS:
                    a = base.metrics_of(items(f"{first}_s{seed}", sc, s))
                    b = base.metrics_of(items(f"{second}_s{seed}", sc, s))
                    out["per_seed"][f"{sc}/{s}/seed{seed}"] = {
                        m: (a[m] - b[m]) if a.get(m) is not None and b.get(m) is not None else None
                        for m in base.METRICS}
        return out

    report["paired"] = {
        "prepare_v2_minus_ablated_v2": paired("prepare_v2", "ablated_v2"),
        "ablated_v2_minus_control_v2": paired("ablated_v2", "control_v2"),
        "prepare_v2_minus_control_v2": paired("prepare_v2", "control_v2"),
        "prepare_v2_masked_at_inference_minus_prepare_v2": paired("prepare_v2_masked_at_inference", "prepare_v2"),
        "prepare_v2_no_JAIL_913_identity_minus_prepare_v2": paired("prepare_v2_no_JAIL_913_identity", "prepare_v2"),
        "ablated_v2_no_JAIL_913_identity_minus_ablated_v2": paired("ablated_v2_no_JAIL_913_identity", "ablated_v2")}

    # sensitivity of the trained prepare_v2 to the column (same checkpoint, same inputs, only the column differs)
    report["sensitivity_prepare_v2"] = {}
    for sc in ("pooled",):
        for subset in ("all", "no_prepare_in_menu", "prepare_in_menu", "prepare_menu_with_JAIL_913"):
            idx = np.flatnonzero(masks[subset] & scopes[sc])
            changed, shift_prepare, shift_other = [], [], []
            for seed in SEEDS:
                a, b = logits[f"prepare_v2_s{seed}"], logits[f"prepare_v2_masked_at_inference_s{seed}"]
                moved = 0
                for i in idx:
                    row = rows[i]
                    x, y = np.array(a[row["decision_id"]]), np.array(b[row["decision_id"]])
                    moved += int(np.argmax(x) != np.argmax(y))
                    kinds = np.array([act["type"] for act in row["legal_actions"]])
                    shift_prepare += list(np.abs(x - y)[kinds == "PREPARE_CARD"])
                    shift_other += list(np.abs(x - y)[kinds != "PREPARE_CARD"])
                changed.append(moved / len(idx))
            report["sensitivity_prepare_v2"][f"{sc}/{subset}"] = {
                "decisions": int(len(idx)), "top1_changes_by_seed": changed,
                "top1_change_rate_mean": float(np.mean(changed)),
                "mean_abs_logit_change_prepare_actions": float(np.mean(shift_prepare)) if shift_prepare else None,
                "mean_abs_logit_change_other_actions": float(np.mean(shift_other))}

    # behaviour counters per model (pooled), errors on HERO_POWER / END_TURN, Top-1 = Prepare
    report["behaviour"] = {n: base.behaviour(rows, facts, records[n]) for n in variants}
    report["by_chosen_kind"] = {}
    kinds = sorted({f["chosen_kind"] for f in facts})
    for group, members in groups.items():
        report["by_chosen_kind"][group] = {}
        for kind in kinds:
            sel = [i for i, f in enumerate(facts) if f["chosen_kind"] == kind]
            report["by_chosen_kind"][group][kind] = {
                "decisions": len(sel),
                "cross_entropy": float(np.mean([np.mean([records[n][i]["loss"] for i in sel]) for n in members])),
                "top1": float(np.mean([np.mean([records[n][i]["top1"] for i in sel]) for n in members]))}
    report["by_prepare_card"] = {}
    cards = sorted({c for f in facts for c in f["prepare_cards"]})
    for group in ("prepare_v2", "ablated_v2", "control_v2"):
        members = groups[group]
        report["by_prepare_card"][group] = {}
        for card in cards:
            sel = [i for i, f in enumerate(facts) if card in f["prepare_cards"]]
            chosen = [i for i in sel if facts[i]["chosen_prepare_card"] == card]
            report["by_prepare_card"][group][card] = {
                "menus": len(sel), "player_chose_prepare": len(chosen),
                "cross_entropy": float(np.mean([np.mean([records[n][i]["loss"] for i in sel]) for n in members])),
                "top1_is_prepare": float(np.mean([np.mean([records[n][i]["pred_kind"] == "PREPARE_CARD" for i in sel])
                                                  for n in members])),
                "chosen_prepare_top1_exact": (float(np.mean([np.mean([records[n][i]["top1"] for i in chosen])
                                                             for n in members])) if chosen else None)}
    report["per_match"] = {}
    games = sorted({f["game_id"] for f in facts})
    for first, second in (("prepare_v2", "ablated_v2"),):
        better, with_prepare, total_with = 0, 0, 0
        for game in games:
            idx = [i for i, f in enumerate(facts) if f["game_id"] == game]
            delta = np.mean([np.mean([records[n][i]["loss"] for i in idx]) for n in groups[first]]) \
                - np.mean([np.mean([records[n][i]["loss"] for i in idx]) for n in groups[second]])
            better += delta < 0
            if any(facts[i]["has_prepare"] for i in idx):
                total_with += 1
                with_prepare += delta < 0
        report["per_match"] = {"matches": len(games), "prepare_v2_lower_cross_entropy_than_ablated_v2": int(better),
                               "matches_with_prepare_menu": total_with,
                               "of_which_prepare_v2_lower": int(with_prepare)}

    # technical checks: identical data, shared identities, finite logits, unchanged references
    check = {"ablated_equals_prepare_in_dataset_split_config": all(
        payloads[f"ablated_v2_s{s}"]["experiment"][k] == payloads[f"prepare_v2_s{s}"]["experiment"][k]
        for s in SEEDS for k in ("dataset_sha256", "split_sha256", "config_sha256")),
        "same_model_config": all(payloads[f"ablated_v2_s{s}"]["model_config"] == payloads[f"prepare_v2_s{s}"]["model_config"]
                                 for s in SEEDS),
        "ablated_flag_recorded": all(payloads[f"ablated_v2_s{s}"]["experiment"].get("ablate_prepare_feature") is True
                                     for s in SEEDS),
        "reference_flag_absent": all("ablate_prepare_feature" not in payloads[f"prepare_v2_s{s}"]["experiment"]
                                     for s in SEEDS),
        "menus_scored": len(rows), "all_logits_finite_and_menu_length": True,
        "fresh_holdout_in_scored_rows": False}
    check["verdict"] = "PASS" if all(v for k, v in check.items() if isinstance(v, bool) and k != "fresh_holdout_in_scored_rows") else "FAIL"
    report["checks"] = check
    report["checkpoints"] = {n: {"sha256": digests[n], "selected_epoch": payloads[n]["experiment"].get("selected_epoch"),
                                 "ablate_prepare_feature": bool(payloads[n]["experiment"].get("ablate_prepare_feature"))}
                             for n in variants if "_s" in n and ("masked" not in n and "identity" not in n)}
    report["verdict"] = verdict(report)
    gain = report["paired"]["prepare_v2_minus_control_v2"]["differences"]["pooled/prepare_in_menu"]["cross_entropy"]["difference"]
    column = report["verdict"]["prepare_menu_ce_difference_pooled"]["difference"]
    report["verdict"]["share_of_total_prepare_v2_vs_control_gain_explained_by_the_column"] = column / gain
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "results.json"
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    raw = args.ablation_runs / "analysis_logits.json"
    if not raw.exists():
        raw.write_text(json.dumps({"decision_part": part_of, "logits": logits}, allow_nan=False), encoding="utf-8")
    print(json.dumps(report["verdict"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
