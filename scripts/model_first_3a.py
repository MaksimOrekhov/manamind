"""Reproduce frozen MODEL-FIRST-3A diagnostics without fitting any model."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.models.policy_v2 import encode_policy_v2  # noqa: E402
from manamind.research.card_text_features import CardTextAdapter, sha256_file  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402
from manamind.training.real_policy import load_examples  # noqa: E402


def _ids(value, result=None):
    result = set() if result is None else result
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("card_id") and isinstance(item, str):
                result.add(item)
            else:
                _ids(item, result)
    elif isinstance(value, list):
        for item in value:
            _ids(item, result)
    return result


def _metric(rows, policy, encoder, id_mask=False):
    correct = top3 = 0
    reciprocal = 0.0
    types = Counter()
    by_type = defaultdict(lambda: [0, 0])
    by_match = defaultdict(lambda: [0, 0])
    elapsed = 0.0
    for row in rows:
        state = game_state_from_dict(row["state"])
        inputs = list(encode_policy_v2(state, row["legal_actions"], encoder))
        if id_mask:
            inputs[1] = inputs[1].clone()
            inputs[4] = inputs[4].clone()
            inputs[1][inputs[1] != 0] = 1
            inputs[4][inputs[4] != 0] = 1
        start = time.perf_counter()
        with torch.no_grad():
            logits = policy(*inputs)
        elapsed += time.perf_counter() - start
        order = torch.argsort(logits, descending=True, stable=True).tolist()
        chosen = row["chosen_action_index"]
        rank = order.index(chosen) + 1
        correct += rank == 1
        top3 += rank <= min(3, len(order))
        reciprocal += 1 / rank
        action_type = row["legal_actions"][chosen]["type"]
        types[action_type] += 1
        by_type[action_type][0] += rank == 1
        by_type[action_type][1] += 1
        by_match[row["game_id"]][0] += rank == 1
        by_match[row["game_id"]][1] += 1
    n = len(rows)
    return {"n": n, "top1": correct / n if n else None, "top1_count": correct,
            "top3": top3 / n if n else None, "mrr": reciprocal / n if n else None,
            "chosen_action_types": dict(sorted(types.items())),
            "by_chosen_action_type_top1": {kind: {"top1": hit / count, "correct": hit, "n": count}
                                           for kind, (hit, count) in sorted(by_type.items())},
            "match_cluster_range_top1": {"matches": len(by_match),
                "min": min((a / b for a, b in by_match.values() if b), default=None),
                "max": max((a / b for a, b in by_match.values() if b), default=None)},
            "seconds_per_decision": elapsed / n if n else None}


def _check_id_only(state, actions, encoder, policy):
    ordinary = encode_policy_v2(state, actions, encoder)
    changed = list(ordinary)
    changed[1] = ordinary[1].clone()
    changed[4] = ordinary[4].clone()
    changed[1][changed[1] != 0] = 1
    changed[4][changed[4] != 0] = 1
    assert all(torch.equal(a, b) for i, (a, b) in enumerate(zip(ordinary, changed)) if i not in (1, 4))
    with torch.no_grad():
        before, after = policy(*ordinary), policy(*changed)
    return float((before - after).abs().max()), int(before.argmax() != after.argmax())


def _counterfactual(path, policy, encoder):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if "counterfactual_card_id" in r.get("tags", [])
            and r.get("label_status") == "LABELED"]
    stats = {"rows": len(rows), "families": len({r["family_id"] for r in rows}),
             "models": {}, "max_abs_logit_delta": 0.0, "top_choice_changed": 0,
             "tensor_control": "PASS"}
    counts = Counter()
    policy.eval()
    for row in rows:
        state = game_state_from_dict(row["state"])
        delta, changed = _check_id_only(state, row["legal_actions"], encoder, policy)
        stats["max_abs_logit_delta"] = max(stats["max_abs_logit_delta"], delta)
        stats["top_choice_changed"] += changed
        inputs = list(encode_policy_v2(state, row["legal_actions"], encoder))
        inputs_masked = list(inputs)
        inputs_masked[1] = inputs[1].clone(); inputs_masked[1][inputs_masked[1] != 0] = 1
        inputs_masked[4] = inputs[4].clone(); inputs_masked[4][inputs_masked[4] != 0] = 1
        for label, batch in (("id", inputs), ("structural_id_masked", inputs_masked)):
            with torch.no_grad():
                order = torch.argsort(policy(*batch), descending=True, stable=True).tolist()
            wanted = {json.dumps(a, sort_keys=True, separators=(",", ":")) for a in row["correct_actions"]}
            chosen = json.dumps(row["legal_actions"][order[0]], sort_keys=True, separators=(",", ":"))
            counts[(label, "top1")] += chosen in wanted
            counts[(label, "n")] += 1
    for label in ("id", "structural_id_masked"):
        n = counts[(label, "n")]
        stats["models"][label] = {"top1": counts[(label, "top1")] / n if n else None,
                                  "top1_count": counts[(label, "top1")], "n": n}
    return stats


def run(dataset: Path, registry_path: Path, checkpoint: Path, catalog_path: Path,
        counterfactual: Path, output: Path, cache_dir: Path) -> dict:
    catalog_json = json.loads(catalog_path.read_text(encoding="utf-8"))
    text = CardTextAdapter(catalog_path)
    cache_path = text.cache(cache_dir)
    rows = load_examples(dataset)
    corpus_report = json.loads((dataset / "refresh_report.json").read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_unused = {e["match_id"] for e in registry["entries"] if e["status"] == "NOT_KNOWN_USED"}
    unused_rows = [r for r in rows if r["game_id"] in registry_unused]
    policy, encoder, payload = load_policy_checkpoint(checkpoint, device="cpu")
    if payload.get("schema") != "manamind.real_policy/2":
        raise ValueError("Frozen ablation requires Policy v2 checkpoint")
    policy.eval()
    train_games = set(payload["experiment"]["split"]["game_ids"]["train"])
    prior_test_games = set(payload["experiment"]["split"]["game_ids"]["test"])
    eval_rows = unused_rows if unused_rows else [r for r in rows if r["game_id"] in prior_test_games]
    eval_slice = "NOT_KNOWN_USED" if unused_rows else "PREVIOUSLY_USED_POLICY_V2_TEST"
    if not eval_rows:
        eval_rows = rows
        eval_slice = "HISTORICAL_USED_REPLAY"
    train_rows = [r for r in rows if r["game_id"] in train_games]
    train_ids = set().union(*(_ids(r["state"]) | _ids(r["legal_actions"]) for r in train_rows)) if train_rows else set()
    eval_ids = set().union(*(_ids(r["state"]) | _ids(r["legal_actions"]) for r in eval_rows))
    eval_missing = eval_ids - train_ids
    eval_seen_rows = [r for r in eval_rows if not ((_ids(r["state"]) | _ids(r["legal_actions"])) - train_ids)]
    eval_unseen_rows = [r for r in eval_rows if (_ids(r["state"]) | _ids(r["legal_actions"])) - train_ids]
    ids_with_text = {card_id for card_id in eval_ids if text.description_present.get(card_id, False)}
    ids_known_to_catalog = eval_ids & set(text.cards)
    action_counts = Counter(r["legal_actions"][r["chosen_action_index"]]["type"] for r in eval_rows)
    base = _metric(eval_rows, policy, encoder)
    struct = _metric(eval_rows, policy, encoder, id_mask=True)
    # Explicitly prove one encoded real decision changes only entity/action ID tensors.
    first = eval_rows[0]
    tensor_delta, argmax_changed = _check_id_only(game_state_from_dict(first["state"]),
                                                   first["legal_actions"], encoder, policy)
    result = {
        "status": "INCONCLUSIVE",
        "source": {"base_commit": "cfcc8197433a3c7fdb4bb92ff1077e09d2986fe6",
                   "checkpoint_sha256": sha256_file(checkpoint), "checkpoint_format": payload["schema"],
                   "checkpoint_train_matches": len(train_games),
                   "dataset_identity_sha256": corpus_report.get("dataset_identity_sha256"),
                   "catalog_sha256": text.catalog_sha256, "catalog_profile": catalog_json["profile_id"],
                   "registry_unused_match_count": len(registry_unused),
                   "unused_match_count_in_supplied_corpus": len({r["game_id"] for r in unused_rows}),
                   "evaluated_match_ids_sha256": hashlib.sha256("".join(sorted({r["game_id"] for r in eval_rows})).encode()).hexdigest()},
        "corpus_inventory": {"matches": corpus_report.get("matches"), "decisions": corpus_report.get("decisions"),
            "chosen_action_types": corpus_report.get("quality", {}).get("chosen_action_types", {}),
            "fresh_split_proposal": corpus_report.get("experiment_usage", {}).get("fresh_split_proposal"),
            "usage_status_counts": corpus_report.get("experiment_usage", {}).get("usage_status_counts", {})},
        "real_observations": {"decisions": len(eval_rows), "chosen_action_types": dict(sorted(action_counts.items())),
            "unique_visible_card_ids": len(eval_ids), "known_in_training_ids": len(eval_ids & train_ids),
            "absent_from_training_ids": len(eval_missing), "decisions_with_any_absent_training_id": len(eval_unseen_rows),
            "catalog_known_ids": len(ids_known_to_catalog), "catalog_rules_text_ids": len(ids_with_text),
            "models": {"ID": base, "Structural_ID_masked": struct},
            "by_training_id_presence": {
                "all_ids_seen_in_train": {"n": len(eval_seen_rows),
                    "ID": _metric(eval_seen_rows, policy, encoder),
                    "Structural_ID_masked": _metric(eval_seen_rows, policy, encoder, id_mask=True)},
                "at_least_one_id_absent_from_train": {"n": len(eval_unseen_rows),
                    "ID": _metric(eval_unseen_rows, policy, encoder),
                    "Structural_ID_masked": _metric(eval_unseen_rows, policy, encoder, id_mask=True)}},
            "evaluation_slice": eval_slice,
            "limitations": ("Registry unused matches only; small and not a full generalization estimate."
                            if unused_rows else
                            "This is the checkpoint's previously used test split, not an independent new holdout. Registry unused matches are absent from the supplied corpus; card-ID novelty is descriptive only.")},
        "id_ablation": {"control": "Only encoded entity IDs and action card IDs changed; all other tensors exactly equal.",
            "max_abs_logit_delta_one_evaluated_decision": tensor_delta, "top_choice_changed_one_evaluated_decision": argmax_changed,
            "prepared_2c_id_pairs": _counterfactual(counterfactual, policy, encoder)},
        "text_adapter": {"kind": "catalog-scoped TF-IDF unigrams+bigrams", "trained_policy": False,
            "features_evaluated_in_policy": False, "catalog_cards": len(text.cards),
            "unique_evaluated_ids": len(eval_ids), "evaluated_ids_with_rules_text": len(ids_with_text),
            "evaluated_ids_in_catalog": len(ids_known_to_catalog), "terms": len(text.terms),
            "sparse_cache_name": cache_path.name, "cache_key_sha256": text.cache_key(),
            "flavor_text_used": False, "policy_quality_claim": False},
        "representations": {"ID": "existing frozen v2 checkpoint", "Structural": "same frozen v2 checkpoint with only learned card IDs mapped to UNK; not independently trained",
            "Text": "NOT_EVALUATED: no adequate independent match-disjoint train/validation/test data",
            "Hybrid": "NOT_EVALUATED: no adequate independent match-disjoint train/validation/test data"},
        "training": {"started": False, "reason": "usage registry fresh split proposal has zero eligible matches/decisions; registry unused matches are absent from the supplied corpus; reused history is not a new holdout"},
        "text_adapter_contract": "Card IDs/type/base stats/mechanics are returned in separate fields; current instance data is passed through separately; adapter does not modify production schema or checkpoint.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--counterfactual", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/model_first_3a/results.json")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".tmp/model_first_3a")
    args = parser.parse_args()
    result = run(args.dataset, args.registry, args.checkpoint, args.catalog, args.counterfactual,
                 args.output, args.cache_dir)
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "real_observations": result["real_observations"],
                      "id_ablation": result["id_ablation"]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
