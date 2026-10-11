"""Post-selection comparison, aggregate diagnostics and bounded outcome case review."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import torch

from manamind.domain.serialization import game_state_from_dict
from manamind.outcome import TextSource, forecast_action
from manamind.outcome.demo import board_summary
from manamind.outcome.forecast import describe_action
from manamind.outcome.verify import load_corpus, score_pair, successor_pairs
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint
from manamind.training.policy_metrics import evaluate, uniform_metrics
from manamind.training.real_policy import encode_example, load_examples
from manamind.training.retrain_metrics import agreement, grouped_metrics, paired_bootstrap

try:
    from scripts.evaluate_policy_baseline import (
        DEFAULT_SCENARIOS, action_key, evaluate_heuristic, evaluate_model, evaluate_random, heuristic, load_scenarios,
    )
    from scripts.prepare_policy_retrain import validate_manifest
    from scripts.refresh_real_policy_dataset import sha256_file
    from scripts.train_real_policy import write_json
except ModuleNotFoundError:
    from evaluate_policy_baseline import (
        DEFAULT_SCENARIOS, action_key, evaluate_heuristic, evaluate_model, evaluate_random, heuristic, load_scenarios,
    )
    from prepare_policy_retrain import validate_manifest
    from refresh_real_policy_dataset import sha256_file
    from train_real_policy import write_json

ROOT = Path(__file__).resolve().parents[1]


def predictions(policy, encoder, rows):
    metrics, records = evaluate(policy, rows, encoder)
    with torch.no_grad():
        for row, record in zip(rows, records):
            logits = policy(*encode_example(row, encoder, representation=2))
            record["prediction_index"] = torch.argsort(logits, descending=True, stable=True).tolist()[0]
    return {**metrics, "matches": len({row["game_id"] for row in rows}),
            "agreement": agreement(rows, records), "groups": grouped_metrics(rows, records)}, records


def suspicious_buff(forecast):
    return any(change.ref.side == "OPPONENT" and change.role == "EFFECT" and change.exact
               and ((change.field in {"attack", "health", "max_health"} and (change.delta or 0) > 0)
                    or (change.field in {"lifesteal", "taunt", "divine_shield", "windfury", "poisonous"}
                        and change.after is True and change.before is not True))
               for change in forecast.changes)


def forecast_diagnostics(rows, records, texts):
    statuses, tiers, suspicious = Counter(), Counter(), []
    targeted_opponent, non_end = 0, 0
    for index, (row, record) in enumerate(zip(rows, records)):
        action = row["legal_actions"][record["prediction_index"]]
        targeted_opponent += action.get("target_side") == "OPPONENT"
        if action["type"] == "END_TURN":
            continue
        non_end += 1
        forecast = forecast_action(game_state_from_dict(row["state"]), action, texts)
        statuses[forecast.status.value] += 1
        tiers[forecast.tier.value] += 1
        if suspicious_buff(forecast):
            suspicious.append(index)
    return {"matches": len({row["game_id"] for row in rows}), "decisions": len(rows),
            "non_end_predictions": non_end, "predictions_targeting_opponent": targeted_opponent,
            "forecast_status": dict(statuses), "forecast_tier": dict(tiers),
            "suspicious_opponent_buff_predictions": len(suspicious),
            "suspicious_matches": len({rows[i]["game_id"] for i in suspicious}),
            "meaning": "Exact local positive enemy effects are flags, not proof of a bad global decision"}, set(suspicious)


def bounded_cases(rows, old, new, old_flags, new_flags, texts, pairs=None, maximum=8):
    differing = [i for i, (a, b) in enumerate(zip(old, new)) if a["prediction_index"] != b["prediction_index"]]
    pools = {
        "old_buff_flag_removed": [i for i in differing if i in old_flags and i not in new_flags],
        "new_buff_flag_added": [i for i in differing if i in new_flags and i not in old_flags],
        "imitation_improved": [i for i in differing if old[i]["rank"] > 1 and new[i]["rank"] == 1],
        "imitation_worsened": [i for i in differing if old[i]["rank"] == 1 and new[i]["rank"] > 1],
        "both_disagree_with_player": [i for i in differing if old[i]["rank"] > 1 and new[i]["rank"] > 1],
    }
    selected, used = [], set()
    for _ in range(maximum):
        for category, indices in pools.items():
            candidate = next((i for i in indices if i not in used), None)
            if candidate is not None and len(selected) < maximum:
                used.add(candidate)
                selected.append((candidate, category))
    cases = []
    for index, category in selected:
        row = rows[index]
        state = game_state_from_dict(row["state"])
        actions = {"frozen": row["legal_actions"][old[index]["prediction_index"]],
                   "new": row["legal_actions"][new[index]["prediction_index"]],
                   "human": row["legal_actions"][row["chosen_action_index"]]}
        forecasts = {name: forecast_action(state, action, texts).to_dict() for name, action in actions.items()}
        observed = None
        if pairs and row["decision_id"] in pairs:
            current, following = pairs[row["decision_id"]]
            comparison = score_pair(current, following, texts)
            observed = {"next_visible_situation": board_summary(following.state),
                        "confirmed_local_claims": comparison.confirmed,
                        "contradicted_local_claims": comparison.contradicted,
                        "meaning": "Observed following chosen action only; no counterfactual outcome"}
        location_summary = "\n".join(
            f"{side} Locations: " + ", ".join(f"#{e.board_position} {e.card.card_id} durability {e.current_health}"
                                                for e in player.locations)
            for side, player in (("SELF", state.self_player), ("OPPONENT", state.opponent)))
        cases.append({"case": f"case_{len(cases) + 1:02}", "selection_category": category,
                      "turn": state.turn_number, "class": state.self_player.player_class,
                      "situation": board_summary(state) + "\n" + location_summary,
                      "self_hand": [{"index": i, "card_id": card.card_id, "current_cost": card.current_cost}
                                    for i, card in enumerate(state.self_hand)],
                      "actions": {name: describe_action(state, action) for name, action in actions.items()},
                      "forecasts": forecasts,
                      "observed_human_consequences": observed,
                      "conclusion": "Only imitation change/local effect is established; full alternative outcome is unobserved"})
    return {"different_top1_decisions": len(differing),
            "matches": len({rows[i]["game_id"] for i in differing}),
            "selection": "Round-robin categories; first decision_id in each; maximum eight; post-selection only",
            "category_counts": {key: len(value) for key, value in pools.items()}, "cases": cases}


def simple_baselines(rows, model_records):
    applicable, correct = [], 0
    for index, row in enumerate(rows):
        key, status = heuristic(game_state_from_dict(row["state"]), row["legal_actions"])
        if status == "APPLICABLE":
            applicable.append(index)
            correct += key == action_key(row["legal_actions"][row["chosen_action_index"]])
    count = len(applicable)
    return {"uniform_expected": {**uniform_metrics(rows), "matches": len({row["game_id"] for row in rows})},
            "heuristic": {"applicable_decisions": count,
                          "applicable_matches": len({rows[i]["game_id"] for i in applicable}),
                          "not_applicable_decisions": len(rows) - count,
                          "top1_accuracy": correct / count if count else None,
                          "correct": correct,
                          "model_top1_same_subset": {name: sum(records[i]["rank"] == 1 for i in applicable) / count
                                                     if count else None for name, records in model_records.items()},
                          "cross_entropy_top3_mrr": "Not applicable: heuristic selects one action, no probabilities/ranking"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--usage-audit", type=Path, required=True)
    parser.add_argument("--robustness-data", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    manifest = json.loads((args.data / "retrain_manifest.json").read_text())
    rows = sorted(load_examples(args.data), key=lambda row: row["decision_id"])
    parts = validate_manifest(manifest, rows, manifest["config"], args.baseline)
    new_model, new_encoder, payload = load_policy_checkpoint(args.run / "policy.pt")
    if payload["experiment"]["protocol_sha256"] != identity(manifest):
        raise ValueError("Checkpoint does not belong to the frozen protocol")
    old_model, old_encoder, old_payload = load_policy_checkpoint(args.baseline)
    if (payload["model_config"] != old_payload["model_config"]
            or payload["card_vocabulary"] != old_payload["card_vocabulary"]):
        raise ValueError("Model architecture/vocabulary changed")
    models = {"frozen_v2": (old_model, old_encoder), "new_v2": (new_model, new_encoder)}
    scored = {name: predictions(model, encoder, parts["test"]) for name, (model, encoder) in models.items()}
    records = {name: result[1] for name, result in scored.items()}
    texts = TextSource.from_files(ROOT / "data/cards/standard_current_enUS.json",
                                  ROOT / "data/outcome/reviewed_texts.json")
    outcomes = {name: forecast_diagnostics(parts["test"], items, texts) for name, items in records.items()}
    control = load_scenarios(DEFAULT_SCENARIOS)
    tactical = {name: evaluate_model(model, encoder, control, repeats=2)
                for name, (model, encoder) in models.items()}
    tactical["heuristic"] = evaluate_heuristic(control)
    tactical["uniform_expected"] = evaluate_random(control)
    # This test was published in 2C; it is a known regression probe, never a fresh real holdout.
    robustness_path = args.robustness_data or ROOT / "data/processed_synthetic/model_first_2c/test.jsonl"
    robustness = None
    if robustness_path.exists():
        scenarios = load_scenarios(robustness_path)
        robustness = {name: evaluate_model(model, encoder, scenarios, repeats=1)
                      for name, (model, encoder) in models.items()}
    usage_audit = json.loads(args.usage_audit.read_text())
    if (usage_audit["protocol_sha256"] != identity(manifest)
            or identity(usage_audit["entries"]) != usage_audit["registry_identity_sha256"]):
        raise ValueError("Supplementary usage audit identity mismatch")
    pairs = {current.decision_id: (current, following)
             for current, following in successor_pairs(load_corpus(args.data))}
    result = {"schema": "manamind.policy_retrain_comparison/1", "strength_claim": False,
              "data_sha256": manifest["split"]["dataset_sha256"], "split_sha256": manifest["split_sha256"],
              "protocol_sha256": identity(manifest), "split_summary": manifest["summary"],
              "supplementary_usage_summary": usage_audit["split_summary"],
              "supplementary_usage_sha256": sha256_file(args.usage_audit), "raw_inventory": usage_audit["raw"],
              "checkpoint_sha256": {"frozen_v2": sha256_file(args.baseline),
                                    "new_v2": sha256_file(args.run / "policy.pt")},
              "test": {name: result[0] for name, result in scored.items()},
              "baselines": simple_baselines(parts["test"], records),
              "paired_uncertainty": paired_bootstrap(parts["test"], records["frozen_v2"], records["new_v2"]),
              "outcome_diagnostics": {name: result[0] for name, result in outcomes.items()},
              "outcome_text_fingerprints": texts.fingerprints,
              "tactical_control": tactical, "known_2c_robustness_regression": robustness,
              "robustness_data_sha256": sha256_file(robustness_path) if robustness is not None else None,
              "changed_recommendations": bounded_cases(parts["test"], records["frozen_v2"], records["new_v2"],
                                                       outcomes["frozen_v2"][1], outcomes["new_v2"][1], texts, pairs)}
    write_json(args.output, result)
    # Detailed rows and game IDs are private, outside the public aggregate report.
    write_json(args.run / f"{args.output.stem}_test_predictions.json", records)
    print(json.dumps({"test": {name: {k: v for k, v in result[0].items() if k not in {"groups", "agreement"}}
                               for name, result in scored.items()}, "uncertainty": result["paired_uncertainty"]}))


if __name__ == "__main__":
    main()
