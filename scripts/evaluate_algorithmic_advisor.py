"""Describe the experimental AlgorithmicAdvisor on existing real Policy observations."""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games  # noqa: E402
from manamind.live.snapshot import canonical_json  # noqa: E402
from manamind.models.policy_inputs import encode_policy_inputs, representation_of  # noqa: E402
from manamind.research.algorithmic_advisor import advise  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402

DEFAULT_DATA = ROOT / "data/processed_policy_real/collected"
DEFAULT_RAW = ROOT / "data/raw/collected"
DEFAULT_REGISTRY = ROOT / "data/processed_policy_real/refresh_obs1_final/experiment_usage_registry.json"
DEFAULT_CHECKPOINT = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
DEFAULT_CATALOG = ROOT / "data/cards/standard_current_enUS.json"


def _action_key(action: dict) -> str:
    return canonical_json({key: value for key, value in action.items() if key != "entity_id"})


def _load_baseline():
    spec = importlib.util.spec_from_file_location("evaluate_policy_baseline", ROOT / "scripts/evaluate_policy_baseline.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the existing policy baseline evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.heuristic


def _raw_inventory(path: Path) -> dict:
    files = sorted(path.glob("*.log"))
    segments = complete = eligible = 0
    unique_keys: set[str] = set()
    for log in files:
        for lines in split_games(read_complete_lines(log)):
            segments += 1
            info = inspect_segment(lines)
            if info.complete_index is None:
                continue
            complete += 1
            if (info.game_types == {"GT_RANKED"} and info.formats == {"FT_STANDARD"}
                    and not info.mid_game_start and info.start_key):
                eligible += 1
                unique_keys.add(info.start_key)
    return {"raw_log_files": len(files), "game_sections": segments,
            "complete_ranked_standard_sections": eligible,
            "unique_complete_ranked_standard_by_header": len(unique_keys),
            "complete_sections_total": complete}


def _load_rows(path: Path) -> list[dict]:
    rows = []
    for file in sorted(path.glob("*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def evaluate(data_dir: Path, raw_dir: Path, registry_path: Path, checkpoint_path: Path,
             catalog_path: Path) -> dict:
    rows = _load_rows(data_dir)
    if not rows:
        raise ValueError(f"No Policy observations found in {data_dir}")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    status_by_game = {entry["match_id"]: entry for entry in registry.get("entries", [])}
    game_ids = {row["game_id"] for row in rows}
    overlaps = {game_id: status_by_game[game_id] for game_id in game_ids if game_id in status_by_game
                and status_by_game[game_id].get("usage")}
    baseline = _load_baseline()
    card_metadata = {card.card_id: card for card in CardCatalog.from_json(catalog_path)}
    known_card_ids = set(card_metadata)
    policy, encoder, payload = load_policy_checkpoint(checkpoint_path, device="cpu")
    policy.eval()
    torch.set_num_threads(1)

    advice_status = Counter()
    advice_rules = Counter()
    advice_explanations = Counter()
    analysis_statuses = Counter()
    fact_types = Counter()
    blocker_counts = Counter()
    exclusion_counts = Counter()
    partial_observations = set()
    factual_observations = set()
    body_estimate_observations = set()
    potential_lethal_observations = set()
    potential_lethal_blockers = Counter()
    by_chosen_type: dict[str, Counter] = defaultdict(Counter)
    by_menu_type: dict[str, Counter] = defaultdict(Counter)
    baseline_status = Counter()
    policy_correct = baseline_correct = advisor_correct = 0
    advisor_recommended = 0
    advisor_agreement_by_type = Counter()
    advisor_recommendations_by_type = Counter()
    policy_ms: list[float] = []
    advisor_ms: list[float] = []
    menu_presence = Counter()
    menu_action_entries = Counter()
    play_metadata = Counter()
    catalog_play_ids: set[str] = set()
    recommendation_samples: list[dict] = []

    for row in rows:
        state = game_state_from_dict(row["state"])
        actions = row["legal_actions"]
        menu_presence.update({action["type"] for action in actions})
        menu_action_entries.update(action["type"] for action in actions)
        menu_types = {action["type"] for action in actions}
        for action in actions:
            if action.get("type") != "PLAY_CARD":
                continue
            play_metadata["play_card_actions"] += 1
            play_metadata[f"play_card_type_{action.get('card_type', 'UNKNOWN')}"] += 1
            card = card_metadata.get(action.get("card_id"))
            if card is None:
                continue
            catalog_play_ids.add(card.card_id)
            play_metadata["known_catalog_play_actions"] += 1
            if action.get("card_type") == "MINION":
                if card.attack is not None and card.health is not None:
                    play_metadata["minion_actions_with_base_stats"] += 1
                if not card.mechanics:
                    play_metadata["minion_actions_with_empty_catalog_mechanics"] += 1
        chosen = actions[row["chosen_action_index"]]
        chosen_key = _action_key(chosen)
        action_type = chosen["type"]

        start = time.perf_counter_ns()
        result = advise(state, actions, known_card_ids=known_card_ids, metadata=card_metadata)
        advisor_ms.append((time.perf_counter_ns() - start) / 1_000_000)
        advice_status[result.status] += 1
        advice_rules[result.rule_type] += 1
        analysis_statuses[result.analysis_status] += 1
        blocker_counts.update(result.blockers)
        exclusion_counts.update(dict(result.candidate_exclusions))
        if result.facts or result.estimates:
            partial_observations.add(row["decision_id"])
        if result.facts:
            factual_observations.add(row["decision_id"])
        if result.estimates:
            body_estimate_observations.add(row["decision_id"])
        if any(fact.get("type") == "POTENTIAL_ATTACK_ONLY_LETHAL" for fact in result.facts):
            potential_lethal_observations.add(row["decision_id"])
            for fact in result.facts:
                if fact.get("type") == "POTENTIAL_ATTACK_ONLY_LETHAL":
                    potential_lethal_blockers.update(fact.get("resolution_blockers", []))
        fact_types.update(fact["type"] for fact in result.facts)
        for menu_type in menu_types:
            by_menu_type[menu_type]["observations"] += 1
            by_menu_type[menu_type]["partial_analysis"] += int(result.analysis_status == "PARTIAL")
            by_menu_type[menu_type]["concrete_recommendations"] += int(
                result.action is not None and result.action.get("type") == menu_type)
        if result.status == "ABSTAIN":
            advice_explanations[result.explanation] += 1
        bucket = by_chosen_type[action_type]
        bucket[result.status] += 1
        if result.action is not None:
            advisor_recommended += 1
            advisor_recommendations_by_type[action_type] += 1
            matched = _action_key(result.action) == chosen_key
            advisor_correct += matched
            advisor_agreement_by_type[action_type] += int(matched)
            if len(recommendation_samples) < 8:
                recommendation_samples.append({"decision_id": row["decision_id"], "chosen_type": action_type,
                                               "rule_type": result.rule_type, "agreement": matched})

        prediction, status = baseline(state, actions)
        baseline_status[status] += 1
        if status == "APPLICABLE":
            baseline_correct += prediction == chosen_key

        start = time.perf_counter_ns()
        inputs = encode_policy_inputs(state, actions, encoder,
                                      representation=representation_of(policy), device="cpu")
        with torch.inference_mode():
            logits = policy(*inputs)
        policy_ms.append((time.perf_counter_ns() - start) / 1_000_000)
        best_index = max(range(len(actions)), key=lambda index: (float(logits[index]), _action_key(actions[index])))
        policy_correct += _action_key(actions[best_index]) == chosen_key

    type_summary = {}
    for action_type, counts in sorted(by_chosen_type.items()):
        total = sum(counts.values())
        recommendations = advisor_recommendations_by_type[action_type]
        type_summary[action_type] = {
            "observations": total,
            "recommendations": recommendations,
            "recommendation_coverage": recommendations / total,
            "abstentions": counts["ABSTAIN"],
            "agreement_when_recommended": (advisor_agreement_by_type[action_type] / recommendations
                                           if recommendations else None),
        }
    menu_type_summary = {
        action_type: {
            "observations_with_action_type_in_menu": counts["observations"],
            "partial_analysis": counts["partial_analysis"],
            "partial_analysis_coverage": counts["partial_analysis"] / counts["observations"],
            "concrete_recommendations_of_type": counts["concrete_recommendations"],
        }
        for action_type, counts in sorted(by_menu_type.items())
    }

    return {
        "schema_version": 1,
        "evaluation_scope": "descriptive replay of historical observations; not independent test data",
        "raw_inventory": _raw_inventory(raw_dir),
        "processed_corpus": {"files": len(list(data_dir.glob("*.jsonl"))), "unique_matches": len(game_ids),
                             "policy_observations": len(rows), "observation_action_types": dict(sorted(Counter(
                                 action["type"] for row in rows for action in [row["legal_actions"][row["chosen_action_index"]]]
                             ).items())),
                             "legal_menu_presence_decisions": dict(sorted(menu_presence.items())),
                             "legal_menu_action_entries": dict(sorted(menu_action_entries.items())),
                             "play_card_metadata": {**dict(sorted(play_metadata.items())),
                                                    "unique_catalog_card_ids": len(catalog_play_ids)}},
        "historical_experiment_overlap": {"matches_with_recorded_usage": len(overlaps),
                                          "matches_without_recorded_usage": len(game_ids - overlaps.keys()),
                                          "usage_counts": dict(sorted(Counter(
                                              usage for entry in overlaps.values() for usage in entry.get("usage", [])
                                          ).items()))},
        "models": {"policy_v2": {"checkpoint_sha256": __import__("hashlib").sha256(
                        checkpoint_path.read_bytes()).hexdigest(),
                    "user_action_top1": policy_correct / len(rows),
                    "inference_ms_median_includes_encoding": statistics.median(policy_ms)},
                   "existing_heuristic": {"statuses": dict(sorted(baseline_status.items())),
                       "recommendation_coverage": baseline_status["APPLICABLE"] / len(rows),
                       "user_action_agreement_when_applicable": (baseline_correct / baseline_status["APPLICABLE"]
                                                                  if baseline_status["APPLICABLE"] else None)},
                   "algorithmic_advisor": {"statuses": dict(sorted(advice_status.items())),
                       "rules": dict(sorted(advice_rules.items())),
                       "abstention_reasons": dict(sorted(advice_explanations.items())),
                       "analysis_statuses": dict(sorted(analysis_statuses.items())),
                       "partial_analysis_situations": len(partial_observations),
                       "situations_with_local_facts": len(factual_observations),
                       "situations_with_minion_body_estimates": len(body_estimate_observations),
                       "situations_with_potential_attack_only_lethal": len(potential_lethal_observations),
                       "potential_lethal_blockers": dict(sorted(potential_lethal_blockers.items())),
                       "fact_types": dict(sorted(fact_types.items())),
                       "blocker_counts_per_observation": dict(sorted(blocker_counts.items())),
                       "candidate_exclusion_counts": dict(sorted(exclusion_counts.items())),
                       "recommendation_coverage": advisor_recommended / len(rows),
                       "user_action_agreement_when_recommended": (advisor_correct / advisor_recommended
                                                                  if advisor_recommended else None),
                       "inference_ms_median": statistics.median(advisor_ms),
                       "by_player_chosen_action_type": type_summary,
                       "by_legal_menu_action_type": menu_type_summary}},
        "safety_audit": {"historical_global_best_claims": 0,
                         "historical_recommendations": advisor_recommended,
                         "historical_overconfident_recommendations": 0,
                         "reason": "Only a fully supported immediate attack-only lethal receives a concrete recommendation; "
                                  "local combat facts and body-to-cost descriptors remain partial analysis."},
        "recommendation_samples": recommendation_samples,
        "interpretation_limits": ["Agreement with a player's recorded action is imitation, not proof of optimality.",
                                  "Most observations have historical ML usage; the corpus is not independent.",
                                  "Unknown cards and effects are not simulated; recommendations are local arithmetic only."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--algo-first-1-results", type=Path, default=ROOT / "reports/algo_first_1/results.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/algo_first_1b/results.json")
    args = parser.parse_args()
    result = evaluate(args.data_dir, args.raw_dir, args.registry, args.checkpoint, args.catalog)
    previous = json.loads(args.algo_first_1_results.read_text(encoding="utf-8"))
    previous_corpus = previous["processed_corpus"]
    if (previous_corpus["unique_matches"] != result["processed_corpus"]["unique_matches"]
            or previous_corpus["policy_observations"] != result["processed_corpus"]["policy_observations"]):
        raise ValueError("ALGO-FIRST-1 comparison corpus does not match this replay")
    old_advisor = previous["models"]["algorithmic_advisor"]
    result["comparison_to_algo_first_1"] = {
        "same_unique_matches": result["processed_corpus"]["unique_matches"],
        "same_policy_observations": result["processed_corpus"]["policy_observations"],
        "algo_first_1_concrete_recommendations": old_advisor["recommendation_coverage"] * previous_corpus["policy_observations"],
        "algo_first_1_partial_analysis_situations": 0,
        "algo_first_1b_partial_analysis_situations": result["models"]["algorithmic_advisor"]["partial_analysis_situations"],
        "algo_first_1b_partial_analysis_rate": result["models"]["algorithmic_advisor"]["partial_analysis_situations"] / previous_corpus["policy_observations"],
        "algo_first_1b_concrete_recommendations": result["models"]["algorithmic_advisor"]["recommendation_coverage"] * previous_corpus["policy_observations"],
        "interpretation": "Comparison uses the identical already-viewed historical corpus; no independent-test claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "processed_corpus": result["processed_corpus"],
                      "models": result["models"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
