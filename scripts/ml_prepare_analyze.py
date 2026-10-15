"""ML-PREPARE-TRAIN-1: score the trained Prepare/control groups and the earlier checkpoints on the same menus.

Inference only. Scores ``validation`` and ``test_seen`` of the experiment split (never ``fresh_holdout``): every model
scores every decision once with its complete legal menu, and every table below is computed from those logits. The metrics
measure agreement with the player's recorded choice (behavior cloning), not move quality or playing strength.

  python scripts/ml_prepare_analyze.py --runs data/processed_policy_prepare_train_1 --output reports/ml_prepare_train_1
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import ml_prepare_train as experiment  # noqa: E402
from manamind.models.policy_inputs import representation_of  # noqa: E402
from manamind.models.policy_v2 import ACTION_V2_FEATURE_NAMES  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402
from manamind.training.real_policy import encode_example  # noqa: E402

PARTITIONS = ("validation", "test")  # "test" is the plan's test_seen: seen by earlier experiments, never independent
DRAWS, BOOTSTRAP_SEED = 2000, 20261015
SEEDS = (42, 43, 44)
GROUPS = ("prepare_v2", "control_v2", "prepare_v3", "control_v3")
# Earlier checkpoints, each pinned by SHA-256 and checked before inference. The first three are the models LIVE and
# Model Shadow pin (scripts/run_manamind.py); ``retrain_1_v2_older`` is a different, older retrained v2 kept only as an
# extra baseline. A test compares these pins with run_manamind.
OLD_CHECKPOINTS = {
    "frozen_v2": ("data/processed_policy_ml2a/seed42_v2/policy.pt",
                  "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"),
    "retrained_v2_model_shadow": ("data/processed_policy_v3/experiment_1/final/architecturev2_seed42/policy.pt",
                                  "9358f932fc7846d6a436e2a1e6c7ff6cffda1f2929fac5521710f973e14a05e3"),
    "policy_v3_ml_policy_v3_1": ("data/processed_policy_v3/experiment_1/final/architecturev3_seed42/policy.pt",
                                 "d874d196d9c2f1e12c6d697ad2de57883a29352976dbb1ee9dbd6ba63af84f82"),
    "retrain_1_v2_older": ("data/processed_policy_retrain_1/seed42_v2/policy.pt",
                           "d2f18737be46bc1773997ec5106d1e30fdf2caaf645a3a7c8998956f092d6377"),
}
REQUIRED_BASELINES = ("frozen_v2", "retrained_v2_model_shadow", "policy_v3_ml_policy_v3_1")
METRICS = ("cross_entropy", "top1", "top3", "mrr")
PREPARE_FEATURE = ACTION_V2_FEATURE_NAMES.index("prepare_card")


# -- decision-level facts that do not depend on any model ------------------------------------------------------------

def decision_facts(row: dict) -> dict:
    actions, chosen = row["legal_actions"], row["legal_actions"][row["chosen_action_index"]]
    prepare = [a for a in actions if a["type"] == "PREPARE_CARD"]
    plays = {a["hand_index"] for a in actions if a["type"] == "PLAY_CARD"}
    both = {a["hand_index"] for a in prepare} & plays
    only = {a["hand_index"] for a in prepare} - plays
    if prepare:
        category = "mixed" if both and only else "play_and_prepare" if both else "prepare_only"
    else:
        category = "no_prepare"
    chosen_hand = chosen.get("hand_index")
    return {"game_id": row["game_id"], "decision_id": row["decision_id"], "menu_size": len(actions),
            "has_prepare": bool(prepare), "category": category, "chosen_kind": chosen["type"],
            "chose_prepare": chosen["type"] == "PREPARE_CARD",
            "prepare_cards": sorted({a["card_id"] for a in prepare}),
            "chosen_prepare_card": chosen["card_id"] if chosen["type"] == "PREPARE_CARD" else None,
            "chosen_has_twin": chosen["type"] in ("PLAY_CARD", "PREPARE_CARD") and chosen_hand in both,
            "hero_power_legal": any(a["type"] == "HERO_POWER" for a in actions)}


SUBSETS = {
    "all": lambda f: True,
    "no_prepare_in_menu": lambda f: not f["has_prepare"],
    "prepare_in_menu": lambda f: f["has_prepare"],
    "play_and_prepare": lambda f: f["category"] == "play_and_prepare",
    "prepare_only": lambda f: f["category"] == "prepare_only",
    "mixed_play_and_prepare_only": lambda f: f["category"] == "mixed",
    "player_chose_prepare": lambda f: f["chose_prepare"],
    "player_chose_other_prepare_available": lambda f: f["has_prepare"] and not f["chose_prepare"],
}


# -- scoring ----------------------------------------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def score(path: Path, rows: list[dict], expected_sha256: str) -> tuple[dict, dict]:
    """Logits per decision from a checkpoint; also its payload. Prepare rows need the explicit flag everywhere.

    The bytes that were hashed are the bytes that are loaded, so the digest cannot describe a different file.
    """
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"{path} differs from its recorded SHA-256")
    policy, encoder, payload = load_policy_checkpoint(io.BytesIO(data), allow_prepare=True)
    representation = representation_of(policy)
    logits = {}
    with torch.no_grad():
        for row in rows:
            inputs = encode_example(row, encoder, representation=representation, allow_prepare=True)
            if len(inputs[3]) != len(row["legal_actions"]):
                raise ValueError("Encoded menu differs from the legal menu")
            value = policy(*inputs)
            if value.shape != (len(row["legal_actions"]),) or not torch.isfinite(value).all():
                raise ValueError("Bad logits")
            logits[row["decision_id"]] = value.tolist()
    return logits, payload


def record(row: dict, facts: dict, logits: list[float]) -> dict:
    values = np.asarray(logits, dtype=np.float64)
    chosen = row["chosen_action_index"]
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))  # stable, as policy_metrics
    rank = order.index(chosen) + 1
    shifted = values - values.max()
    log_norm = float(math.log(np.exp(shifted).sum()))
    probs = np.exp(shifted - log_norm)
    actions = row["legal_actions"]
    kinds = np.array([a["type"] for a in actions])
    top = actions[order[0]]
    result = {"loss": log_norm - float(shifted[chosen]), "rank": rank, "top1": rank == 1,
              "top3": rank <= 3 if len(values) >= 3 else None, "rr": 1 / rank, "pred_kind": top["type"],
              "prepare_mass": float(probs[kinds == "PREPARE_CARD"].sum()), "top_index": order[0]}
    return result


def metrics_of(items: list[tuple[dict, dict]]) -> dict:
    n = len(items)
    if not n:
        return {"decisions": 0}
    eligible = [r for _, r in items if r["top3"] is not None]
    return {"decisions": n, "matches": len({f["game_id"] for f, _ in items}),
            "cross_entropy": sum(r["loss"] for _, r in items) / n, "top1": sum(r["top1"] for _, r in items) / n,
            "top3": sum(r["top3"] for r in eligible) / len(eligible) if eligible else None,
            "top3_decisions": len(eligible), "mrr": sum(r["rr"] for _, r in items) / n}


def uniform_of(facts: list[dict]) -> dict:
    sizes = [f["menu_size"] for f in facts]
    n = len(sizes)
    if not n:
        return {"decisions": 0}
    eligible = [k for k in sizes if k >= 3]
    return {"decisions": n, "cross_entropy": sum(math.log(k) for k in sizes) / n,
            "top1": sum(1 / k for k in sizes) / n, "top3": sum(3 / k for k in eligible) / len(eligible) if eligible else None,
            "mrr": sum(sum(1 / j for j in range(1, k + 1)) / k for k in sizes) / n}


# -- paired bootstrap over whole matches ---------------------------------------------------------------------------------

def metric_arrays(records: list[dict]) -> dict:
    """Per-decision value and weight arrays; a metric is sum(weight * value) / sum(weight)."""
    n = len(records)
    top3 = np.array([0.0 if r["top3"] is None else float(r["top3"]) for r in records])
    return {"cross_entropy": (np.array([r["loss"] for r in records]), np.ones(n)),
            "top1": (np.array([float(r["top1"]) for r in records]), np.ones(n)),
            "top3": (top3, np.array([0.0 if r["top3"] is None else 1.0 for r in records])),
            "mrr": (np.array([r["rr"] for r in records]), np.ones(n))}


def averaged(per_seed: list[list[dict]]) -> list[dict]:
    """Seed-averaged per-decision records (mean of loss/top1/top3/rr is exactly the mean of the per-seed metrics)."""
    out = []
    for column in zip(*per_seed):
        has3 = column[0]["top3"] is not None
        out.append({"loss": float(np.mean([r["loss"] for r in column])),
                    "top1": float(np.mean([r["top1"] for r in column])), "rr": float(np.mean([r["rr"] for r in column])),
                    "top3": float(np.mean([r["top3"] for r in column])) if has3 else None})
    return out


def paired_bootstrap(facts, first, second, mask, seed=BOOTSTRAP_SEED, draws=DRAWS) -> dict:
    """first - second per metric over the masked decisions; resamples whole matches."""
    idx = np.flatnonzero(mask)
    if not len(idx):
        return {}
    games = sorted({facts[i]["game_id"] for i in idx})
    position = {g: k for k, g in enumerate(games)}
    group = np.array([position[facts[i]["game_id"]] for i in idx])
    a, b = metric_arrays([first[i] for i in idx]), metric_arrays([second[i] for i in idx])
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(len(games), np.full(len(games), 1 / len(games)), size=draws).astype(float)
    result = {"matches": len(games), "decisions": int(len(idx))}
    for name in METRICS:
        (va, weights), (vb, _) = a[name], b[name]  # eligibility weights are a property of the menu, identical for both
        num = np.bincount(group, weights=weights * (va - vb), minlength=len(games))
        den = np.bincount(group, weights=weights, minlength=len(games))
        total_den = counts @ den
        valid = total_den > 0
        diffs = (counts @ num)[valid] / total_den[valid]
        point = float(num.sum() / den.sum()) if den.sum() else None
        result[name] = {"difference": point,
                        "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))] if len(diffs) else None}
    return result


# -- behaviour counters -------------------------------------------------------------------------------------------------

def behaviour(rows, facts, records) -> dict:
    """Counts of the specific disagreements asked for; ``records`` are one model's per-decision results."""
    out = Counter()
    for row, f, r in zip(rows, facts, records):
        chosen, top = f["chosen_kind"], r["pred_kind"]
        actions = row["legal_actions"]
        out["decisions"] += 1
        if top == "PREPARE_CARD" and chosen == "PLAY_CARD":
            out["suggests_prepare_player_played_card"] += 1
            if f["chosen_has_twin"] and actions[r["top_index"]]["hand_index"] == actions[row["chosen_action_index"]]["hand_index"]:
                out["suggests_prepare_player_played_same_card"] += 1
        if top == "PREPARE_CARD" and chosen not in ("PLAY_CARD", "PREPARE_CARD"):
            out["suggests_prepare_player_did_other_action"] += 1
        if top == "PLAY_CARD" and chosen == "PREPARE_CARD":
            out["suggests_play_player_used_prepare"] += 1
            if actions[r["top_index"]]["hand_index"] == actions[row["chosen_action_index"]]["hand_index"]:
                out["suggests_play_of_the_same_card_player_used_prepare"] += 1
        if chosen == "PREPARE_CARD":
            out["player_prepare_decisions"] += 1
            out["player_prepare_top1_prepare"] += top == "PREPARE_CARD"
        if f["has_prepare"]:
            out["prepare_menu_decisions"] += 1
            out["prepare_menu_top1_prepare"] += top == "PREPARE_CARD"
            out["prepare_menu_mass_sum"] += r["prepare_mass"]
        if chosen == "ATTACK":
            out["player_attack_decisions"] += 1
            out["player_attack_top1_attack"] += top == "ATTACK"
            out["player_attack_top1_exact"] += r["top1"]
        if top == "ATTACK" and chosen != "ATTACK":
            out["suggests_attack_player_did_other"] += 1
        if top == "END_TURN" and chosen != "END_TURN":
            out["premature_end_turn"] += 1
        if chosen == "END_TURN":
            out["player_end_turn_decisions"] += 1
            out["refuses_to_end_turn"] += top != "END_TURN"
        if top == "HERO_POWER":
            out["top1_hero_power"] += 1
            out["top1_hero_power_player_did_other"] += chosen != "HERO_POWER"
        if chosen == "HERO_POWER":
            out["player_hero_power_decisions"] += 1
            out["player_hero_power_top1_hero_power"] += top == "HERO_POWER"
        if f["hero_power_legal"]:
            out["hero_power_legal_decisions"] += 1
            out["hero_power_legal_top1_hero_power"] += top == "HERO_POWER"
            out["hero_power_legal_player_hero_power"] += chosen == "HERO_POWER"
        out[f"top1_kind_{top}"] += 1
        out[f"player_kind_{chosen}"] += 1
    return dict(out)


def integrity(rows, logits_by_model, encoder_cache) -> dict:
    """Menu / hand card / target correspondence, checked for the data and for every model's top-1 action."""
    problems, checked = Counter(), Counter()
    for row in rows:
        hand = row["state"]["self_hand"]
        for a in row["legal_actions"]:
            checked["actions"] += 1
            if a["type"] in ("PLAY_CARD", "PREPARE_CARD"):
                if hand[a["hand_index"]]["card_id"] != a["card_id"]:
                    problems["hand_index_card_mismatch"] += 1
            if a["type"] == "PREPARE_CARD" and any(k.startswith("target_") for k in a):
                problems["prepare_with_target"] += 1
            if ("target_kind" in a) != ("target_card_id" in a or a.get("target_kind") == "HERO"):
                problems["target_fields_inconsistent"] += 1
    for name, logits in logits_by_model.items():
        for row in rows:
            values = logits[row["decision_id"]]
            checked["model_decisions"] += 1
            if len(values) != len(row["legal_actions"]):
                problems[f"{name}:menu_length"] += 1
                continue
            top = row["legal_actions"][max(range(len(values)), key=lambda i: (values[i], -i))]
            if top["type"] in ("PLAY_CARD", "PREPARE_CARD") and \
                    row["state"]["self_hand"][top["hand_index"]]["card_id"] != top["card_id"]:
                problems[f"{name}:top1_hand_card_mismatch"] += 1
    return {"checked": dict(checked), "problems": dict(problems), "verdict": "PASS" if not problems else "FAIL"}


def encoding_check(rows, encoder) -> dict:
    """prepare_card is 1 exactly on PREPARE_CARD actions; each one differs from every PLAY_CARD of the same hand card."""
    wrong, pairs, prepare_actions = 0, 0, 0
    for row in rows:
        actions = row["legal_actions"]
        features = encode_example(row, encoder, representation=2, allow_prepare=True)[3]
        for i, a in enumerate(actions):
            expected = float(a["type"] == "PREPARE_CARD")
            wrong += float(features[i, PREPARE_FEATURE]) != expected
            prepare_actions += expected > 0
            if a["type"] == "PREPARE_CARD":
                for j, b in enumerate(actions):
                    if b["type"] == "PLAY_CARD" and b["hand_index"] == a["hand_index"]:
                        pairs += 1
                        wrong += bool(torch.equal(features[i], features[j]))
    return {"prepare_actions": prepare_actions, "play_prepare_pairs_of_one_hand_card": pairs, "wrong": wrong,
            "verdict": "PASS" if not wrong else "FAIL"}


# -- driver -----------------------------------------------------------------------------------------------------------

def stats(values: list[float]) -> dict:
    values = [v for v in values if v is not None]
    return {"mean": float(np.mean(values)), "sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
            "min": float(min(values)), "max": float(max(values)), "values": [float(v) for v in values]} if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=Path, default=experiment.OUTPUT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    args = parser.parse_args()
    plan = experiment.load_plan()
    parts, _ = experiment.load_parts(experiment.CORPUS, plan)
    rows_by_part = {name: parts[name] for name in PARTITIONS}
    rows = [r for name in PARTITIONS for r in rows_by_part[name]]
    part_of = {r["decision_id"]: name for name in PARTITIONS for r in rows_by_part[name]}
    facts = [decision_facts(r) for r in rows]
    if {r["game_id"] for r in rows} & set(plan["parts"]["fresh_holdout"]):
        raise ValueError("fresh_holdout matches reached the analysis")

    models = {}  # name -> (group, seed, path)
    for group in GROUPS:
        for seed in args.seeds:
            path = args.runs / f"{group}_seed{seed}" / "policy.pt"
            if path.is_file():
                models[f"{group}_s{seed}"] = (group, seed, path)
    old = {name: ROOT / relative for name, (relative, _) in OLD_CHECKPOINTS.items()}
    expected = {name: sha for name, (_, sha) in OLD_CHECKPOINTS.items()}
    for name, (_, _, path) in models.items():  # new models: the digest their own training run recorded
        expected[name] = json.loads((path.parent / "metrics.json").read_text(encoding="utf-8"))["checkpoint_sha256"]
    logits, payloads, per_record = {}, {}, {}
    for name, (_, _, path) in {**models, **{k: (None, None, v) for k, v in old.items()}}.items():
        logits[name], payloads[name] = score(path, rows, expected[name])
        per_record[name] = [record(r, f, logits[name][r["decision_id"]]) for r, f in zip(rows, facts)]
        print("scored", name, flush=True)

    masks = {s: np.array([fn(f) for f in facts]) for s, fn in SUBSETS.items()}
    part_masks = {p: np.array([part_of[f["decision_id"]] == p for f in facts]) for p in PARTITIONS}
    scopes = {**{p: part_masks[p] for p in PARTITIONS}, "pooled": np.ones(len(rows), dtype=bool)}

    def subset_items(name, scope, subset):
        mask = masks[subset] & scopes[scope]
        return [(facts[i], per_record[name][i]) for i in np.flatnonzero(mask)]

    report = {"schema": "manamind.ml_prepare_train_1_results/1", "seeds": args.seeds,
              "partition_names": {"validation": "validation", "test": "test_seen (seen by earlier experiments)"},
              "fresh_holdout_opened": False, "bootstrap": {"draws": DRAWS, "seed": BOOTSTRAP_SEED,
                                                           "unit": "whole matches"}}
    report["data"] = {scope: {s: {"decisions": int((masks[s] & scopes[scope]).sum()),
                                  "matches": len({facts[i]["game_id"] for i in np.flatnonzero(masks[s] & scopes[scope])})}
                              for s in SUBSETS} for scope in scopes}
    report["data"]["prepare_cards_in_menu"] = {
        p: dict(Counter(c for f, m in zip(facts, part_masks[p]) if m for c in f["prepare_cards"])) for p in PARTITIONS}
    report["data"]["prepare_cards_chosen"] = {
        p: dict(Counter(f["chosen_prepare_card"] for f, m in zip(facts, part_masks[p]) if m and f["chose_prepare"]))
        for p in PARTITIONS}
    report["data"]["chosen_kinds"] = {p: dict(Counter(f["chosen_kind"] for f, m in zip(facts, part_masks[p]) if m))
                                      for p in PARTITIONS}
    report["uniform_random"] = {scope: {s: uniform_of([facts[i] for i in np.flatnonzero(masks[s] & scopes[scope])])
                                        for s in SUBSETS} for scope in scopes}
    base_rate = {scope: {"chose_prepare": float(np.mean([facts[i]["chose_prepare"] for i in
                                                         np.flatnonzero(scopes[scope] & masks["prepare_in_menu"])]))}
                 for scope in scopes}
    report["player_prepare_rate_in_prepare_menus"] = base_rate

    # per-model tables
    report["models"] = {}
    for name in [*models, *old]:
        report["models"][name] = {scope: {s: metrics_of(subset_items(name, scope, s)) for s in SUBSETS}
                                  for scope in scopes}
    # seed statistics per group
    report["groups"] = {}
    for group in GROUPS:
        members = [n for n, (g, _, _) in models.items() if g == group]
        if not members:
            continue
        report["groups"][group] = {"members": members, "tables": {
            scope: {s: {m: stats([report["models"][n][scope][s].get(m) for n in members]) for m in METRICS}
                    for s in SUBSETS} for scope in scopes}}

    # paired differences prepare - control, same seeds, seed-averaged, bootstrap over whole matches
    report["paired"] = {}
    for arch in ("v2", "v3"):
        seeds = [s for s in args.seeds if f"prepare_{arch}_s{s}" in models and f"control_{arch}_s{s}" in models]
        if not seeds:
            continue
        mean_p = averaged([per_record[f"prepare_{arch}_s{s}"] for s in seeds])
        mean_c = averaged([per_record[f"control_{arch}_s{s}"] for s in seeds])
        report["paired"][arch] = {"seeds": seeds, "differences": {}, "per_seed": {}}
        for scope in scopes:
            for s in ("all", "no_prepare_in_menu", "prepare_in_menu", "play_and_prepare", "prepare_only",
                      "player_chose_prepare", "player_chose_other_prepare_available"):
                mask = masks[s] & scopes[scope]
                report["paired"][arch]["differences"][f"{scope}/{s}"] = paired_bootstrap(facts, mean_p, mean_c, mask)
                for seed in seeds:
                    key = f"{scope}/{s}/seed{seed}"
                    a = metrics_of(subset_items(f"prepare_{arch}_s{seed}", scope, s))
                    b = metrics_of(subset_items(f"control_{arch}_s{seed}", scope, s))
                    report["paired"][arch]["per_seed"][key] = {
                        m: (a[m] - b[m]) if a.get(m) is not None and b.get(m) is not None else None for m in METRICS}

    # architecture effect (v3 - v2) inside each data condition, same seeds, same menus
    report["architecture_v3_minus_v2"] = {}
    for kind in ("prepare", "control"):
        seeds = [s for s in args.seeds if f"{kind}_v2_s{s}" in models and f"{kind}_v3_s{s}" in models]
        if not seeds:
            continue
        v3 = averaged([per_record[f"{kind}_v3_s{s}"] for s in seeds])
        v2 = averaged([per_record[f"{kind}_v2_s{s}"] for s in seeds])
        report["architecture_v3_minus_v2"][kind] = {
            f"pooled/{s}": paired_bootstrap(facts, v3, v2, masks[s])
            for s in ("all", "no_prepare_in_menu", "prepare_in_menu")}

    # earlier checkpoints on identical menus. Per checkpoint every match of ours is classified by the role it had in that
    # checkpoint's own recorded split; only matches in none of its parts are independent of it.
    report["earlier_checkpoints"] = {}
    ours = {p: {r["game_id"] for r in rows_by_part[p]} for p in PARTITIONS}
    our_matches = ours["validation"] | ours["test"]
    for name in old:
        split = payloads[name]["experiment"]["split"]["game_ids"]
        roles = {part: our_matches & set(ids) for part, ids in split.items()}
        known = set().union(*roles.values())
        subsets = {"all_decisions": np.ones(len(facts), dtype=bool),
                   "without_its_own_train_matches": np.array([f["game_id"] not in roles["train"] for f in facts]),
                   "independent_of_this_checkpoint": np.array([f["game_id"] not in known for f in facts])}
        report["earlier_checkpoints"][name] = {
            "checkpoint_sha256": expected[name], "prepare_card_feature_trained": False,
            "role": "pinned by LIVE / Model Shadow" if name in REQUIRED_BASELINES else "extra older baseline",
            "our_matches_by_role_in_its_own_split": {part: len(ids) for part, ids in roles.items()},
            "our_matches_in_none_of_its_parts": len(our_matches - known),
            "subsets": {sub: {
                "decisions": int((mask & scopes["pooled"]).sum()),
                "matches": len({facts[i]["game_id"] for i in np.flatnonzero(mask)}),
                "checkpoint": {scope: {s: metrics_of([(facts[i], per_record[name][i])
                                                      for i in np.flatnonzero(masks[s] & scopes[scope] & mask)])
                                       for s in ("all", "no_prepare_in_menu", "prepare_in_menu")} for scope in scopes},
                "new_groups_mean_over_seeds": {g: {s: {m: float(np.mean([metrics_of(
                    [(facts[i], per_record[n][i]) for i in np.flatnonzero(masks[s] & scopes["pooled"] & mask)])[m]
                    for n, (gg, _, _) in models.items() if gg == g])) for m in ("cross_entropy", "top1", "mrr")}
                    for s in ("all", "no_prepare_in_menu", "prepare_in_menu")}
                    for g in GROUPS if any(gg == g for gg, _, _ in models.values())}}
                for sub, mask in subsets.items()}}

    # behaviour counters per model (counts), averaged over seeds per group below
    report["behaviour"] = {}
    for name in [*models, *old]:
        report["behaviour"][name] = {scope: behaviour(
            [rows[i] for i in np.flatnonzero(scopes[scope])], [facts[i] for i in np.flatnonzero(scopes[scope])],
            [per_record[name][i] for i in np.flatnonzero(scopes[scope])]) for scope in scopes}

    # per Prepare card and per chosen action type, pooled partitions, seed-averaged per group
    report["by_prepare_card"], report["by_chosen_kind"] = {}, {}
    cards = sorted({c for f in facts for c in f["prepare_cards"]})
    kinds = sorted({f["chosen_kind"] for f in facts})
    for group in GROUPS:
        members = [n for n, (g, _, _) in models.items() if g == group]
        if not members:
            continue
        report["by_prepare_card"][group] = {}
        for card in cards:
            sel = [i for i, f in enumerate(facts) if card in f["prepare_cards"]]
            chosen = [i for i in sel if facts[i]["chosen_prepare_card"] == card]
            report["by_prepare_card"][group][card] = {
                "decisions_with_card_prepare_in_menu": len(sel), "player_chose_prepare": len(chosen),
                "cross_entropy": float(np.mean([np.mean([per_record[n][i]["loss"] for i in sel]) for n in members])),
                "top1": float(np.mean([np.mean([per_record[n][i]["top1"] for i in sel]) for n in members])),
                "top1_is_prepare": float(np.mean([np.mean([per_record[n][i]["pred_kind"] == "PREPARE_CARD" for i in sel])
                                                  for n in members])),
                "mean_prepare_probability_mass": float(np.mean([np.mean([per_record[n][i]["prepare_mass"] for i in sel])
                                                                for n in members])),
                "chosen_prepare_top1_exact": (float(np.mean([np.mean([per_record[n][i]["top1"] for i in chosen])
                                                             for n in members])) if chosen else None)}
        report["by_chosen_kind"][group] = {}
        for kind in kinds:
            sel = [i for i, f in enumerate(facts) if f["chosen_kind"] == kind]
            report["by_chosen_kind"][group][kind] = {
                "decisions": len(sel),
                "cross_entropy": float(np.mean([np.mean([per_record[n][i]["loss"] for i in sel]) for n in members])),
                "top1": float(np.mean([np.mean([per_record[n][i]["top1"] for i in sel]) for n in members]))}

    # per-match results (short ids), seed-averaged cross-entropy per group
    report["per_match"] = {}
    games = sorted({f["game_id"] for f in facts})
    for group in GROUPS:
        members = [n for n, (g, _, _) in models.items() if g == group]
        if not members:
            continue
        table = {}
        for game in games:
            idx = [i for i, f in enumerate(facts) if f["game_id"] == game]
            table[game[:8]] = {"partition": part_of[facts[idx[0]]["decision_id"]], "decisions": len(idx),
                               "prepare_menus": int(sum(facts[i]["has_prepare"] for i in idx)),
                               "cross_entropy": float(np.mean([np.mean([per_record[n][i]["loss"] for i in idx])
                                                               for n in members])),
                               "top1": float(np.mean([np.mean([per_record[n][i]["top1"] for i in idx]) for n in members]))}
        report["per_match"][group] = table

    # whole-match view of the Prepare-vs-control comparison (seed-averaged cross-entropy per match)
    report["per_match_comparison"] = {}
    for arch in ("v2", "v3"):
        a, b = report["per_match"].get(f"prepare_{arch}"), report["per_match"].get(f"control_{arch}")
        if not a or not b:
            continue
        def wins(keys):
            better = sum(a[k]["cross_entropy"] < b[k]["cross_entropy"] for k in keys)
            return {"matches": len(keys), "prepare_group_lower_cross_entropy": better}
        report["per_match_comparison"][arch] = {
            "all_matches": wins(list(a)),
            "matches_with_prepare_menu": wins([k for k in a if a[k]["prepare_menus"] > 0]),
            "matches_without_prepare_menu": wins([k for k in a if a[k]["prepare_menus"] == 0]),
            "largest_per_match_cross_entropy_changes": sorted(
                ((k, round(a[k]["cross_entropy"] - b[k]["cross_entropy"], 3)) for k in a), key=lambda x: x[1])[:2]
            + sorted(((k, round(a[k]["cross_entropy"] - b[k]["cross_entropy"], 3)) for k in a),
                     key=lambda x: x[1])[-2:]}

    # technical checks
    all_models = {**{n: logits[n] for n in models}, **{n: logits[n] for n in old}}
    first = next(iter(models.values()))[2]
    _, encoder, _ = load_policy_checkpoint(first, allow_prepare=True)
    report["integrity"] = integrity(rows, all_models, None)
    report["encoding_check"] = encoding_check(rows, encoder)
    report["checkpoints"] = {n: {"sha256": expected[n], "semantic_action_schema_version":
                                 payloads[n]["semantic_action_schema_version"],
                                 "selected_epoch": payloads[n]["experiment"].get("selected_epoch"),
                                 "parameters": payloads[n]["experiment"].get("parameters"),
                                 "dataset_sha256": payloads[n]["experiment"].get("dataset_sha256"),
                                 "split_sha256": payloads[n]["experiment"].get("split_sha256"),
                                 "config_sha256": payloads[n]["experiment"].get("config_sha256")}
                             for n, (_, _, p) in {**models, **{k: (None, None, v) for k, v in old.items()}}.items()}
    report["verdict"] = verdict(report, args.seeds)
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "results.json"
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    raw = args.runs / "analysis_logits.json"
    if not raw.exists():  # full logits stay local (ignored by git)
        raw.write_text(json.dumps({"decision_part": part_of, "logits": logits}, allow_nan=False), encoding="utf-8")
    print(json.dumps(report["verdict"], indent=1))
    return 0


def verdict(report: dict, seeds) -> dict:
    """The pre-registered rules in configs/ml_prepare_train_1/experiment.json, evaluated mechanically."""
    out = {"architectures": {}}
    for arch, paired in report["paired"].items():
        diffs, per_seed = paired["differences"], paired["per_seed"]
        n = len(paired["seeds"])
        need = math.ceil(2 * n / 3) if n else 0
        p1d = diffs["pooled/prepare_in_menu"]["cross_entropy"]
        p1 = p1d["difference"] is not None and p1d["difference"] < 0 and p1d["ci95"][1] < 0
        def seeds_better(part):
            return sum((per_seed[f"{part}/prepare_in_menu/seed{s}"]["cross_entropy"] or 0) < 0 for s in paired["seeds"])
        p2_parts = {part: diffs[f"{part}/prepare_in_menu"]["cross_entropy"]["difference"] for part in PARTITIONS}
        p2 = all(v is not None and v < 0 for v in p2_parts.values()) and all(seeds_better(p) >= need for p in PARTITIONS)
        n1d = diffs["pooled/no_prepare_in_menu"]["cross_entropy"]
        n1 = n1d["difference"] <= 0.03 and n1d["ci95"][1] <= 0.05
        members = [f"prepare_{arch}_s{s}" for s in paired["seeds"]]
        behaviours = [report["behaviour"][m]["pooled"] for m in members]
        top1_rate = float(np.mean([b["prepare_menu_top1_prepare"] / b["prepare_menu_decisions"] for b in behaviours]))
        player_rate = report["player_prepare_rate_in_prepare_menus"]["pooled"]["chose_prepare"]
        n2 = top1_rate <= 2 * player_rate
        regression = (all(diffs[f"{part}/no_prepare_in_menu"]["cross_entropy"]["difference"] >= 0.05 for part in PARTITIONS)
                      or top1_rate > 3 * player_rate)
        out["architectures"][arch] = {
            "P1_prepare_menu_ce_difference_pooled": p1d, "P1": p1,
            "P2_difference_by_partition": p2_parts, "P2_seeds_better": {p: seeds_better(p) for p in PARTITIONS},
            "P2_seeds_needed": need, "P2": p2, "N1_no_prepare_ce_difference_pooled": n1d, "N1": n1,
            "N2_top1_prepare_rate": top1_rate, "N2_player_prepare_rate": player_rate, "N2": n2,
            "verdict": "REGRESSION" if regression else "PROMISING" if p1 and p2 and n1 and n2 else "INCONCLUSIVE"}
    verdicts = [v["verdict"] for v in out["architectures"].values()]
    out["overall"] = ("REGRESSION" if "REGRESSION" in verdicts else "PROMISING" if verdicts and all(
        v == "PROMISING" for v in verdicts) else "INCONCLUSIVE")
    out["live_switch_authorised"] = False
    return out


if __name__ == "__main__":
    raise SystemExit(main())
