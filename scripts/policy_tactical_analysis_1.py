"""Reproduce the 295-decision tactical audit without training or holdout access.

The input is the already-researched NEW-MATCHES-EVAL-2 cohort. This script
strictly recovers the 91 repeated Outcome Shadow joins, then compares pinned
checkpoints and writes full states only under ignored ``data/``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import live_join_coverage_1 as join_audit  # noqa: E402
import live_join_coverage_1_recheck as recheck  # noqa: E402
import new_matches_eval_1 as base  # noqa: E402
import new_matches_eval_2 as eval2  # noqa: E402
from manamind.live.snapshot import canonical_json  # noqa: E402
from manamind.live.snapshot_join import collapse_identical_main_action_snapshots  # noqa: E402
from manamind.live.journal_join import outcome_journal_signature  # noqa: E402
from manamind.training.real_policy import validate_example  # noqa: E402

PRIVATE = ROOT / "data/processed_policy_tactical_analysis_1"
REPORT = ROOT / "reports/policy_tactical_analysis_1"
EXPECTED_DECISIONS = 295
EXPECTED_MATCHES = 12
EXPECTED_RECOVERED = 91
ANALYSIS_SCHEMA = "manamind.policy_tactical_analysis_1/1"
DOCUMENTED_RECHECK_CODE_SHA256 = {
    "scripts/live_join_coverage_1.py": "645ed5f9743488d21bdf2577740079b8bd05f9291175e2057849ef9ee620e7ff",
    "scripts/new_matches_eval_2.py": "8daae02c9e73cfca5b77d0d6df607ce0fa5ac575174c1740ff6966694fbf183a",
}

CODE_PATHS = (
    "scripts/policy_tactical_analysis_1.py",
    "scripts/live_join_coverage_1_recheck.py",
    "scripts/new_matches_eval_2.py",
    "scripts/new_matches_eval_1.py",
    "scripts/live_join_coverage_1.py",
    "src/manamind/live/journal_join.py",
    "src/manamind/live/snapshot_join.py",
    "src/manamind/training/policy_checkpoint.py",
    "src/manamind/training/real_policy.py",
    "src/manamind/models/policy_v2.py",
    "src/manamind/models/policy_v3.py",
)

INPUT_PATHS = (
    "data/processed_new_matches_eval_2/protocol.private.json",
    "data/processed_new_matches_eval_2/decisions.private.jsonl",
    "data/processed_new_matches_eval_2/diagnostic.private.jsonl",
    "data/processed_new_matches_eval_2/logits.private.jsonl",
    "reports/new_matches_eval_2/results.json",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def _new_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(canonical_json(row) + "\n")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _source_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


def _verify_locked_eval2_inputs(protocol: dict, rows: list[dict]) -> list[str]:
    """Verify EVAL-2's pinned data/checkpoints, allowing only the documented join fix."""
    changed_code = []
    for path, expected in protocol["code_sha256"].items():
        actual = sha256_file(ROOT / path)
        if actual == expected:
            continue
        if DOCUMENTED_RECHECK_CODE_SHA256.get(path) != actual:
            raise ValueError(f"unexpected EVAL-2 code change: {path}")
        changed_code.append(path)
    if set(changed_code) != set(DOCUMENTED_RECHECK_CODE_SHA256):
        raise ValueError("the documented strict-join recheck source set changed")

    for path, key in ((ROOT / base.SPLIT_PLAN, "split_plan_sha256"),
                      (ROOT / base.CARDS, "catalog_sha256"),
                      (ROOT / base.USAGE_REGISTRY, "usage_registry_sha256"),
                      (ROOT / eval2.PRIOR, "prior_protocol_sha256")):
        if sha256_file(path) != protocol["inputs"][key]:
            raise ValueError(f"locked EVAL-2 metadata changed: {path.name}")
    split = _read_json(ROOT / base.SPLIT_PLAN)
    heldout = set(split.get("parts", {}).get("fresh_holdout", []))
    if len(heldout) != 9 or sorted(heldout) != protocol["protected_fresh_holdout"].get("ids"):
        raise ValueError("protected fresh_holdout ID lock changed")
    eval2.assert_independent(rows, heldout, protocol["history_ids"], protocol["prior_match_ids"])

    for path, expected in protocol["inputs"]["raw_log_sha256"].items():
        if sha256_file(ROOT / path) != expected:
            raise ValueError(f"locked EVAL-2 raw source changed: {path}")
    for path, expected in protocol["inputs"]["live_snapshot_sha256"].items():
        if sha256_file(ROOT / path) != expected:
            raise ValueError(f"locked EVAL-2 LIVE snapshot changed: {path}")
    prefixes = {Path(path).stem for path in protocol["inputs"]["raw_log_sha256"]}
    _, shadow_hashes = base._load_shadow_rows(prefixes, heldout)
    if shadow_hashes != protocol["inputs"]["candidate_shadow_rows_sha256"]:
        raise ValueError("locked EVAL-2 shadow journals changed")

    matches = sorted({row["example"]["game_id"] for row in rows})
    decisions = sorted(row["example"]["decision_id"] for row in rows)
    if matches != protocol["eligible_match_ids"] or decisions != protocol["eligible_decision_ids"]:
        raise ValueError("locked EVAL-2 membership changed")
    identity = digest({"matches": matches, "decisions": decisions, "inputs": protocol["inputs"]})
    if identity != protocol["dataset_identity_sha256"]:
        raise ValueError("locked EVAL-2 data identity changed")
    old_decisions = ROOT / eval2.PRIVATE / "decisions.private.jsonl"
    if sha256_file(old_decisions) != protocol["private_decisions_sha256"]:
        raise ValueError("locked EVAL-2 decisions changed")
    for model in base.MODELS:
        metadata = protocol["models"][model["name"]]
        if sha256_file(ROOT / model["path"]) != metadata["sha256"]:
            raise ValueError(f"locked checkpoint changed: {model['name']}")
        if sha256_file(ROOT / model["metrics"]) != metadata["metrics_sha256"]:
            raise ValueError(f"locked checkpoint metadata changed: {model['name']}")
    return sorted(changed_code)


def _strict_rows() -> tuple[dict, list[dict], dict[str, str]]:
    """Rebuild the exact 295 using the locked EVAL-2 cohort and strict join."""
    protocol, decisions, diagnostic, heldout = recheck._read_cohort()
    _verify_locked_eval2_inputs(protocol, decisions)

    candidates = decisions + diagnostic
    game_ids = {row["example"]["game_id"] for row in candidates}

    shadow_rows, _ = base._load_shadow_rows(game_ids, heldout)
    groups = base._group_shadows(shadow_rows)
    snapshots_by_game: dict[str, dict[tuple, list[dict]]] = {}
    for game_id in sorted(game_ids):
        snapshots, _, parse_error = join_audit._read_candidate_snapshots(game_id)
        if parse_error:
            raise ValueError(f"snapshot parse failed: {parse_error}")
        snapshots_by_game[game_id] = snapshots

    raw_counts = Counter(recheck._key(row) for row in candidates)
    recovered: list[dict] = []
    rejected: Counter = Counter()
    for item in diagnostic:
        if item.get("exclusion_reason") != "CONFLICTING_OUTCOME_ROWS":
            continue
        example = item["example"]
        key = recheck._key(item)
        snapshot_rows = snapshots_by_game[key[0]].get(key, [])
        reason = eval2.join_reason(example, key, snapshot_rows, groups, raw_counts[key])
        if reason:
            rejected[reason] += 1
        else:
            recovered.append(item)
    if rejected or len(recovered) != EXPECTED_RECOVERED:
        raise ValueError(f"strict recovery changed: {len(recovered)} recovered, rejects={dict(rejected)}")

    selected = decisions + recovered
    eval2.assert_independent(selected, heldout, protocol["history_ids"], protocol["prior_match_ids"])
    if len(selected) != EXPECTED_DECISIONS or len({x["example"]["game_id"] for x in selected}) != EXPECTED_MATCHES:
        raise ValueError("strict cohort must contain exactly 295 decisions from 12 matches")

    output: list[dict] = []
    for item in selected:
        example = item["example"]
        validate_example(example, allow_prepare=True)
        state_hash = digest(example["state"])
        if state_hash != example.get("provenance", {}).get("state_hash"):
            raise ValueError("state hash does not match the serialized state")
        key = recheck._key(item)
        snapshot_rows = snapshots_by_game[key[0]].get(key, [])
        if eval2.join_reason(example, key, snapshot_rows, groups, raw_counts[key]):
            raise ValueError("a selected decision no longer passes the full strict join")
        collapsed = collapse_identical_main_action_snapshots(snapshot_rows)
        if collapsed.snapshot is None or canonical_json(collapsed.snapshot["state"]) != canonical_json(example["state"]):
            raise ValueError("full state differs from the matched LIVE snapshot")

        prediction_rows = groups["prediction"].get(key, [])
        strategy_rows = groups["strategy"].get(key, [])
        outcome_rows = groups["outcome"].get(key, [])
        recommendation, reason = base._one_record(prediction_rows, "prediction")
        if reason:
            raise ValueError(f"strict prediction join failed: {reason}")
        strategy, reason = base._one_record(strategy_rows, "strategy")
        if reason:
            raise ValueError(f"strict strategy join failed: {reason}")
        if len({outcome_journal_signature(row) for row in outcome_rows}) != 1:
            raise ValueError("Outcome Shadow semantic rows disagree")
        outcome = outcome_rows[0]
        output.append({"example": example, "recommendation": recommendation,
                       "strategy": strategy, "outcome": outcome,
                       "analysis_origin": "RECOVERED_91" if item in recovered else "LOCKED_204"})

    output.sort(key=lambda row: row["example"]["decision_id"])
    ids = [row["example"]["decision_id"] for row in output]
    keys = [recheck._key(row) for row in output]
    if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
        raise ValueError("duplicate decision identity or strict join key")
    if {row["example"]["game_id"] for row in output} != set(protocol["eligible_match_ids"]):
        raise ValueError("selected decisions do not match the 12 locked eligible games")
    if any(row["example"]["game_id"] in heldout for row in output):
        raise ValueError("protected fresh_holdout row found")
    source_hashes = {
        path: sha256_file(ROOT / path)
        for path in (*INPUT_PATHS, *CODE_PATHS)
    }
    for model in base.MODELS:
        for path in (model["path"], model["metrics"]):
            source_hashes[path] = sha256_file(ROOT / path)
    return protocol, output, source_hashes


def _public_protocol(protocol: dict, rows: list[dict], source_hashes: dict[str, str]) -> dict:
    examples = [row["example"] for row in rows]
    game_ids = sorted({row["game_id"] for row in examples})
    decision_ids = sorted(row["decision_id"] for row in examples)
    recovered_ids = sorted(row["example"]["decision_id"] for row in rows
                           if row["analysis_origin"] == "RECOVERED_91")
    recovered_sha = digest(recovered_ids)
    selected_sha = digest(decision_ids)
    data_identity = digest({"locked_eval_2_identity": protocol["dataset_identity_sha256"],
                            "selected_decisions_sha256": selected_sha,
                            "recovered_decisions_sha256": recovered_sha,
                            "inputs_sha256": source_hashes})
    games_by_class: dict[str, set[str]] = defaultdict(set)
    decisions_by_class: Counter = Counter()
    for example in examples:
        player_class = example["state"]["self_player"].get("player_class") or "UNKNOWN"
        games_by_class[player_class].add(example["game_id"])
        decisions_by_class[player_class] += 1
    baseline_results = _read_json(ROOT / "reports/new_matches_eval_2/results.json")
    baseline_metrics = {
        name: baseline_results["evaluation_sets"]["ordinary_menus"]["models"][name]["metrics"]
        for name in ("frozen_v2", "retrained_v2", "policy_v3")
    }
    changed_code = sorted(path for path, expected in protocol["code_sha256"].items()
                          if sha256_file(ROOT / path) != expected)
    private = {
        "schema": ANALYSIS_SCHEMA,
        "status": "PROTOCOL_LOCKED",
        "created_from_commit": _source_head(),
        "source_code_sha256": source_hashes["scripts/policy_tactical_analysis_1.py"],
        "locked_eval_2_identity_sha256": protocol["dataset_identity_sha256"],
        "data_identity_sha256": data_identity,
        "selected_decisions_sha256": selected_sha,
        "recovered_decisions_sha256": recovered_sha,
        "counts": {"matches": len(game_ids), "decisions": len(examples),
                   "previously_scored": len(examples) - len(recovered_ids),
                   "recovered_for_this_analysis": len(recovered_ids)},
        "classes": {name: {"matches": len(games_by_class[name]), "decisions": decisions_by_class[name]}
                    for name in sorted(games_by_class)},
        "models": {model["name"]: {"checkpoint_sha256": model["sha256"],
                                    "metrics_sha256": source_hashes[model["metrics"]]}
                   for model in base.MODELS},
        "source_hashes": source_hashes,
        "documented_post_lock_code_changes": changed_code,
        "hypothesis": "Восстановление 91 строго сопоставленного решения может изменить картину имитации. Проверить, сохраняется ли относительный результат Policy v3 против Frozen v2 и Retrained v2 на тех же данных при равном весе матчей и при исключении по одному матчу или классу.",
        "selected_rows_sha256": digest(rows),
        "baseline": {"primary": "frozen_v2", "historical_204_metrics": baseline_metrics,
                     "historical_note": "The 204-decision EVAL-2 result is already researched and is not an independent holdout."},
        "analysis": {
            "metrics": ["top1", "top3 (menus >= 3)", "cross_entropy", "mrr", "top1 confidence", "chosen-action probability", "top3 probability mass", "entropy"],
            "uncertainty": "Paired whole-match bootstrap; also report match-balanced and leave-one-match/class-out differences.",
            "behavior_review": "Descriptive only. A player choice is an imitation label, not a strategic oracle. Strategy Scorer is heuristic. Outcome Shadow PARTIAL/UNSUPPORTED is not an exact result. Lethal claims require an EXACT one-action forecast; no multi-step search.",
            "inference": "Existing seven checkpoints only; offline CPU inference; no training or fine-tuning.",
            "protected_fresh_holdout": {"opened": False, "inference_run": False},
            "live_policy_changed": False,
        },
    }
    public = {
        "schema": ANALYSIS_SCHEMA,
        "status": "PROTOCOL_LOCKED",
        "data_identity_sha256": data_identity,
        "source_commit": private["created_from_commit"],
        "source_code_sha256": private["source_code_sha256"],
        "locked_eval_2_identity_sha256": protocol["dataset_identity_sha256"],
        "counts": private["counts"],
        "classes": private["classes"],
        "models": private["models"],
        "documented_post_lock_code_changes": private["documented_post_lock_code_changes"],
        "hypothesis": private["hypothesis"],
        "baseline": private["baseline"],
        "analysis": private["analysis"],
        "privacy": "Match IDs, states, legal menus, logits, per-decision outcomes and player names remain in ignored data/.",
    }
    return private, public


def preflight() -> dict:
    if PRIVATE.exists() or REPORT.exists():
        raise FileExistsError("refusing to overwrite a prior tactical-analysis output")
    protocol, rows, source_hashes = _strict_rows()
    private, public = _public_protocol(protocol, rows, source_hashes)
    _new_jsonl(PRIVATE / "decisions.private.jsonl", rows)
    _new_json(PRIVATE / "protocol.private.json", private)
    _new_json(REPORT / "protocol.json", public)
    private["public_protocol_sha256"] = sha256_file(REPORT / "protocol.json")
    (PRIVATE / "protocol.private.json").write_text(
        json.dumps(private, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    (REPORT / "README.md").write_text(_render_protocol(public), encoding="utf-8")
    return {"status": "PROTOCOL_LOCKED", "counts": private["counts"],
            "data_identity_sha256": private["data_identity_sha256"]}


def relock() -> dict:
    """Preserve and supersede a pre-inference lock after an analysis-code repair."""
    old_path = PRIVATE / "protocol.private.json"
    new_path = PRIVATE / "protocol.private.v2.json"
    old_public = REPORT / "protocol.json"
    old_readme = REPORT / "README.md"
    for path in (new_path, REPORT / "protocol.v1.json", REPORT / "README.protocol.v1.md",
                 REPORT / "protocol.v2.lock.json"):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite prior protocol artifact: {path}")
    if any((PRIVATE / name).exists() for name in (
        "logits.private.jsonl", "recovered_inference.private.jsonl", "cases.private.json", "results.private.json"
    )):
        raise ValueError("cannot relock after inference has produced results")

    old_private = _read_json(old_path)
    old_rows = _read_jsonl(PRIVATE / "decisions.private.jsonl")
    for path, expected in old_private["source_hashes"].items():
        if path == "scripts/policy_tactical_analysis_1.py":
            continue
        if sha256_file(ROOT / path) != expected:
            raise ValueError(f"cannot relock because a pinned input changed: {path}")

    cohort_protocol, rows, source_hashes = _strict_rows()
    if canonical_json(rows) != canonical_json(old_rows):
        raise ValueError("strictly reconstructed 295 rows differ from the original lock")
    private, public = _public_protocol(cohort_protocol, rows, source_hashes)
    private["protocol_revision"] = 2
    private["previous_protocol_sha256"] = sha256_file(old_path)
    public["protocol_revision"] = 2
    public["supersedes_protocol_sha256"] = private["previous_protocol_sha256"]
    public["revision_reason"] = "Исправлена отсутствовавшая запись сравнения в анализаторе до записи результатов; все 295 выбранных строк побайтно совпадают с исходной фиксацией."

    shutil.copyfile(old_public, REPORT / "protocol.v1.json")
    shutil.copyfile(old_readme, REPORT / "README.protocol.v1.md")
    (REPORT / "protocol.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    shutil.copyfile(REPORT / "protocol.json", REPORT / "protocol.v2.lock.json")
    private["public_protocol_lock_path"] = "reports/policy_tactical_analysis_1/protocol.v2.lock.json"
    private["public_protocol_sha256"] = sha256_file(REPORT / "protocol.v2.lock.json")
    _new_json(new_path, private)
    (REPORT / "README.md").write_text(_render_protocol(public), encoding="utf-8")
    return {"status": "PROTOCOL_RELOCKED", "revision": 2,
            "data_identity_sha256": private["data_identity_sha256"],
            "counts": private["counts"], "decision_rows_unchanged": True}


def _verify_locked(private: dict, rows: list[dict]) -> None:
    if private.get("schema") != ANALYSIS_SCHEMA or private.get("status") != "PROTOCOL_LOCKED":
        raise ValueError("invalid tactical-analysis protocol")
    for path, expected in private["source_hashes"].items():
        if sha256_file(ROOT / path) != expected:
            raise ValueError(f"locked source changed: {path}")
    lock_path = ROOT / private.get("public_protocol_lock_path", "reports/policy_tactical_analysis_1/protocol.json")
    if sha256_file(lock_path) != private.get("public_protocol_sha256"):
        raise ValueError("public analysis protocol changed after lock")
    if private.get("selected_rows_sha256") and digest(rows) != private["selected_rows_sha256"]:
        raise ValueError("locked decision contents changed")
    ids = sorted(row["example"]["decision_id"] for row in rows)
    recovered_ids = sorted(row["example"]["decision_id"] for row in rows
                           if row["analysis_origin"] == "RECOVERED_91")
    if digest(ids) != private["selected_decisions_sha256"] or digest(recovered_ids) != private["recovered_decisions_sha256"]:
        raise ValueError("locked decision membership changed")
    if len(ids) != EXPECTED_DECISIONS or len(recovered_ids) != EXPECTED_RECOVERED:
        raise ValueError("locked cohort count changed")


def _probability_summary(logits: list[float], chosen: int) -> dict:
    if not logits or not 0 <= chosen < len(logits) or not all(math.isfinite(x) for x in logits):
        raise ValueError("invalid model logits or chosen index")
    order = sorted(range(len(logits)), key=lambda index: (-logits[index], index))
    maximum = max(logits)
    exp_values = [math.exp(value - maximum) for value in logits]
    normalizer = sum(exp_values)
    probabilities = [value / normalizer for value in exp_values]
    return {
        "top_index": order[0],
        "chosen_probability": probabilities[chosen],
        "top_probability": probabilities[order[0]],
        "top3_probability_mass": sum(probabilities[index] for index in order[:3]),
        "entropy_nats": -sum(value * math.log(value) for value in probabilities if value > 0),
        "top1_matches_player": order[0] == chosen,
        "order": order,
        "probabilities": probabilities,
    }


def _confidence_analysis(predictions: list[dict]) -> dict:
    names = [model["name"] for model in base.MODELS]
    edges = (0.0, 0.25, 0.50, 0.75, 1.0000001)
    out = {}
    for name in names:
        summaries = []
        for item in predictions:
            score = item["model_scores"].get(name, {})
            if "logits" not in score:
                continue
            summaries.append(_probability_summary(score["logits"], item["example"]["chosen_action_index"]))
        bins = []
        for lower, upper in zip(edges, edges[1:]):
            selected = [row for row in summaries if lower <= row["top_probability"] < upper]
            bins.append({"interval": [lower, min(upper, 1.0)], "decisions": len(selected),
                         "mean_confidence": _mean([row["top_probability"] for row in selected]),
                         "observed_player_match_rate": _mean([float(row["top1_matches_player"]) for row in selected])})
        correct = [row for row in summaries if row["top1_matches_player"]]
        incorrect = [row for row in summaries if not row["top1_matches_player"]]
        out[name] = {
            "decisions": len(summaries),
            "mean_top1_confidence_when_matching_player": _mean([r["top_probability"] for r in correct]),
            "mean_top1_confidence_when_not_matching_player": _mean([r["top_probability"] for r in incorrect]),
            "mean_probability_on_player_action": _mean([r["chosen_probability"] for r in summaries]),
            "mean_top3_probability_mass": _mean([r["top3_probability_mass"] for r in summaries]),
            "mean_entropy_nats": _mean([r["entropy_nats"] for r in summaries]),
            "high_confidence_mismatches_ge_0_75": sum(
                not r["top1_matches_player"] and r["top_probability"] >= 0.75 for r in summaries),
            "confidence_bins": bins,
        }
    return out


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _match_alias(game_id: str) -> str:
    return hashlib.sha256(game_id.encode("utf-8")).hexdigest()[:8]


def _metric_record_map(predictions: list[dict], name: str) -> dict[str, dict]:
    return {item["example"]["decision_id"]: item["model_scores"][name]
            for item in predictions if "logits" in item["model_scores"].get(name, {})}


def _robustness(predictions: list[dict]) -> dict:
    ordinary = [row for row in predictions if not any(
        action["type"] == "PREPARE_CARD" for action in row["example"]["legal_actions"])]
    games = sorted({row["example"]["game_id"] for row in ordinary})
    classes = sorted({row["example"]["state"]["self_player"].get("player_class") or "UNKNOWN"
                      for row in ordinary})
    result: dict[str, Any] = {"matches": len(games), "models": {}}
    for spec in base.MODELS:
        name = spec["name"]
        per_match: dict[str, dict[str, float]] = {}
        for game in games:
            subset = [row for row in ordinary if row["example"]["game_id"] == game]
            records = [row["model_scores"][name] for row in subset]
            sizes = [len(row["example"]["legal_actions"]) for row in subset]
            stats = base._metric_stats(records, sizes)["metrics"]
            per_match[_match_alias(game)] = {
                "player_class": subset[0]["example"]["state"]["self_player"].get("player_class") or "UNKNOWN",
                "decisions": len(subset), "cross_entropy": stats["cross_entropy"],
                "top1": stats["top1"], "top3": stats["top3"], "mrr": stats["mrr"]}
        result["models"][name] = {"per_match": per_match}

    frozen = _metric_record_map(ordinary, "frozen_v2")
    def delta(subset: list[dict], name: str) -> dict[str, float] | None:
        if not subset:
            return None
        recs = [row["model_scores"][name] for row in subset]
        refs = [frozen[row["example"]["decision_id"]] for row in subset]
        return {metric: _mean([float(a[metric]) - float(b[metric]) for a, b in zip(recs, refs)])
                for metric in ("cross_entropy", "top1")}

    for name in ("retrained_v2", "policy_v3", "control_v3_seed42", "prepare_v2_seed42", "prepare_v3_seed42"):
        by_game = {}
        for game in games:
            subset = [row for row in ordinary if row["example"]["game_id"] == game]
            by_game[game] = delta(subset, name)
        balanced = {metric: _mean([value[metric] for value in by_game.values() if value is not None])
                    for metric in ("cross_entropy", "top1")}
        leave_one_game = {}
        for removed in games:
            leave_one_game[_match_alias(removed)] = delta(
                [row for row in ordinary if row["example"]["game_id"] != removed], name)
        leave_one_class = {}
        for removed in classes:
            leave_one_class[removed] = delta(
                [row for row in ordinary if (row["example"]["state"]["self_player"].get("player_class")
                                              or "UNKNOWN") != removed], name)
        result["models"][name].update({"match_balanced_difference_vs_frozen_v2": balanced,
                                       "leave_one_match_out": leave_one_game,
                                       "leave_one_class_out": leave_one_class})
    return result


def _behavior_summary(predictions: list[dict]) -> dict:
    result = {}
    for spec in base.MODELS:
        name = spec["name"]
        rows = [row for row in predictions if "logits" in row["model_scores"].get(name, {})]
        actual_end = [row for row in rows if row["example"]["legal_actions"][row["example"]["chosen_action_index"]]["type"] == "END_TURN"]
        top_end = [row for row in rows if row["model_scores"][name]["predicted_type"] == "END_TURN"]
        false_end = [row for row in top_end if row not in actual_end]
        score_non_end = 0
        exact_non_end = 0
        for row in false_end:
            strategy = row["strategy"]
            if strategy.get("complete") is True and strategy.get("top3"):
                indices = strategy["top3"][0].get("indices", [])
                if any(row["example"]["legal_actions"][i]["type"] != "END_TURN" for i in indices):
                    score_non_end += 1
            outcome_by_index = {int(item["index"]): item for item in row["outcome"].get("actions", [])
                                if isinstance(item, dict) and "index" in item}
            if any(index != row["model_scores"][name]["top_index"]
                   and action["type"] != "END_TURN"
                   and outcome_by_index.get(index, {}).get("status") == "EXACT"
                   for index, action in enumerate(row["example"]["legal_actions"])
                   if index < len(row["example"]["legal_actions"])):
                exact_non_end += 1
        result[name] = {
            "top1_end_turn": len(top_end),
            "top1_end_turn_player_continued": len(false_end),
            "top1_not_end_turn_when_player_ended": sum(row in actual_end and row not in top_end for row in rows),
            "player_hero_power_top1_other": sum(
                row["example"]["legal_actions"][row["example"]["chosen_action_index"]]["type"] == "HERO_POWER"
                and row["model_scores"][name]["predicted_type"] != "HERO_POWER" for row in rows),
            "top1_hero_power_player_chose_other": sum(
                row["model_scores"][name]["predicted_type"] == "HERO_POWER"
                and row["example"]["legal_actions"][row["example"]["chosen_action_index"]]["type"] != "HERO_POWER"
                for row in rows),
            "among_premature_end_turn_mismatches": {
                "scorer_top_set_contains_non_end_turn": score_non_end,
                "at_least_one_other_exact_one_action_forecast": exact_non_end,
                "interpretation": "Both are investigation signals only; they do not establish that ending the turn was wrong.",
            },
        }
    return result


def _safe_action_label(action: dict) -> str:
    kind = str(action.get("type", "UNKNOWN"))
    if kind == "PLAY_CARD":
        parts = [kind]
        card_type = action.get("card_type")
        if card_type:
            parts.append(str(card_type))
        cost = action.get("card_cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            parts.append(f"cost {int(cost)}")
        return f"{kind} ({', '.join(parts[1:])})" if len(parts) > 1 else kind
    if kind == "ATTACK":
        source = "hero" if action.get("source_is_hero") is True else "minion"
        target = "hero" if action.get("target_is_hero") is True else "minion"
        return f"ATTACK {source} → {target}"
    return kind


def _safe_effects(outcome_row: dict | None) -> list[str]:
    if not outcome_row or outcome_row.get("status") != "EXACT":
        return []
    effects = outcome_row.get("effects", [])
    safe = []
    for effect in effects:
        if not isinstance(effect, list) or len(effect) < 4:
            continue
        entity, field, before, after = effect[:4]
        entity_text = str(entity).lower()
        if "self hero" in entity_text:
            side = "SELF hero"
        elif "opponent hero" in entity_text:
            side = "opponent hero"
        elif "self" in entity_text:
            side = "SELF entity"
        elif "opponent" in entity_text:
            side = "opponent entity"
        else:
            side = "visible entity"
        field_text = str(field)
        if field_text not in {"health", "armor", "attack", "mana", "durability", "destroyed", "hand_size", "board_count"}:
            continue
        safe.append(f"{side} {field_text}: {before}→{after}")
    return safe[:2]


def _ranked_actions(logits: list[float], menu: list[dict], chosen: int,
                    outcomes: dict[int, dict]) -> list[dict]:
    info = _probability_summary(logits, chosen)
    result = []
    for index in info["order"][:3]:
        forecast = outcomes.get(index)
        result.append({"action": _safe_action_label(menu[index]), "probability": info["probabilities"][index],
                       "matches_player": index == chosen,
                       "outcome_status": forecast.get("status") if forecast else "MISSING",
                       "exact_effects": _safe_effects(forecast)})
    return result


def _public_case(item: dict, exact_lethals: dict[str, Any]) -> dict:
    example = item["example"]
    state = example["state"]
    self_player = state["self_player"]
    decision_id = example["decision_id"]
    by_index = {int(row["index"]): row for row in item["outcome"].get("actions", [])
                if isinstance(row, dict) and "index" in row}
    chosen = int(example["chosen_action_index"])
    scores = item["model_scores"]

    model_rankings = {}
    for name in ("frozen_v2", "policy_v3"):
        record = scores.get(name, {})
        if "logits" in record:
            model_rankings[name] = _ranked_actions(record["logits"], example["legal_actions"], chosen, by_index)

    outcome_actions = []
    for forecast in sorted(by_index.values(), key=lambda row: (int(row.get("rank", 999)), int(row.get("index", 999))))[:5]:
        index = int(forecast["index"])
        outcome_actions.append({"action": _safe_action_label(example["legal_actions"][index]),
                                "status": forecast.get("status"), "effects": _safe_effects(forecast),
                                "unknown_count": len(forecast.get("unknowns", []))})
    strategy_top = []
    for rank, group in enumerate(item["strategy"].get("top3", []), 1):
        indices = group.get("indices", []) if isinstance(group, dict) else []
        for index in indices:
            if isinstance(index, int) and 0 <= index < len(example["legal_actions"]):
                action_score = next((row.get("score") for row in item["strategy"].get("actions", [])
                                     if isinstance(row, dict) and row.get("index") == index), None)
                strategy_top.append({"rank_group": rank, "action": _safe_action_label(example["legal_actions"][index]),
                                     "score": action_score,
                                     "outcome_status": by_index.get(index, {}).get("status", "MISSING"),
                                     "exact_effects": _safe_effects(by_index.get(index))})
                if len(strategy_top) >= 3:
                    break
        if len(strategy_top) >= 3:
            break

    lethal_rows = exact_lethals.get(decision_id, [])
    return {
        "match": _match_alias(example["game_id"]),
        "class": self_player.get("player_class") or "UNKNOWN",
        "visible_position": {
            "turn": state.get("turn_number"), "self_mana": self_player.get("available_mana"),
            "self_health": self_player.get("hero_health"), "opponent_health": state.get("opponent", {}).get("hero_health"),
            "self_board_count": len(self_player.get("board", [])),
            "opponent_board_count": len(state.get("opponent", {}).get("board", [])),
            "self_known_hand_count": state.get("self_hand_known_count"), "legal_menu_size": len(example["legal_actions"]),
        },
        "player_action": _safe_action_label(example["legal_actions"][chosen]),
        "model_top3": model_rankings,
        "strategic_scorer_top3": strategy_top,
        "outcome_shadow_sample": outcome_actions,
        "exact_one_action_lethal_outside_top3": [row["model"] for row in lethal_rows if row.get("status") == "CONFIRMED"],
        "interpretation": "The recorded player action is an imitation reference. Scorer ranks are heuristic; non-EXACT forecasts do not establish effects.",
    }


def _select_public_cases(predictions: list[dict], selected: dict, lethal_review: dict) -> list[dict]:
    private_examples = selected.get("private_examples", {})
    wanted = (
        "frozen_ends_others_continue",
        "all_models_disagree",
        "neural_vs_strategy_scorer",
        "confident_disagreement:policy_v3",
        "model_top1_hero_power_player_did_not",
        "attack_target_or_source_disagreement",
    )
    by_id = {row["example"]["decision_id"]: row for row in predictions}
    lethal_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in lethal_review.get("private_rows", []):
        lethal_by_id[row["decision_id"]].append(row)
    cases = []
    used_ids: set[str] = set()
    used_matches: set[str] = set()
    for category in wanted:
        for candidate in private_examples.get(category, []):
            decision_id = candidate["decision_id"]
            item = by_id.get(decision_id)
            if item is None or decision_id in used_ids:
                continue
            game_id = item["example"]["game_id"]
            if game_id in used_matches:
                continue
            used_ids.add(decision_id)
            used_matches.add(game_id)
            cases.append(_public_case(item, lethal_by_id))
            break
        if len(cases) >= 5:
            break
    return cases


def _confidence_value(value: Any) -> str:
    return "—" if value is None else f"{value:.3f}"


def _render_report(report: dict, cases: list[dict], protocol: dict) -> str:
    ordinary = report["evaluation_sets"]["ordinary_menus"]
    model_data = ordinary["models"]
    lines = [
        "# POLICY-TACTICAL-ANALYSIS-1",
        "",
        f"Статус: **COMPLETE**. Выборка `{protocol['data_identity_sha256']}` — "
        f"{ordinary['matches']} уже исследованных матчей и {ordinary['decisions']} решений.",
        "Это расширение EVAL-2 с 204 до 295 решений, а не независимый контрольный набор.",
        "",
        "## 1. Сравнение моделей",
        "",
        "Все семь закреплённых checkpoint оценены на одинаковых полных legal menu. Top-3 считается только для меню от трёх действий.",
        "Действие игрока — метка имитации, не эталон тактической правильности.",
        "",
        "| Модель | CE ↓ | Top-1 | Top-3 | MRR | равный вес матчей: CE / Top-1 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("frozen_v2", "retrained_v2", "policy_v3", "control_v2_seed42", "control_v3_seed42",
                 "prepare_v2_seed42", "prepare_v3_seed42"):
        item = model_data[name]
        metric = item["metrics"]
        balanced = item["mean_across_matches"]
        lines.append(f"| {name} | {metric['cross_entropy']:.4f} | {metric['top1']:.3f} | "
                     f"{metric['top3']:.3f} | {metric['mrr']:.3f} | "
                     f"{balanced['cross_entropy']['mean']:.4f} / {balanced['top1']['mean']:.3f} |")
    lines += ["", f"Top-3 denominator: {model_data['frozen_v2']['metrics']['top3_decisions']} решений с меню ≥3. "
              "Основные парные интервалы — bootstrap по целым матчам (не по отдельным решениям); "
              "никакая модель не объявляется победителем по малому отличию.", "",
              "### Уверенность и распределение вероятностей", "",
              "| Модель | P(top-1), совпал / не совпал с игроком | P(действие игрока) | масса Top-3 | энтропия | mismatch с уверенностью ≥0.75 |",
              "|---|---:|---:|---:|---:|---:|"]
    confidence = report["confidence"]
    for name in ("frozen_v2", "retrained_v2", "policy_v3"):
        item = confidence[name]
        lines.append(f"| {name} | {_confidence_value(item['mean_top1_confidence_when_matching_player'])} / "
                     f"{_confidence_value(item['mean_top1_confidence_when_not_matching_player'])} | "
                     f"{_confidence_value(item['mean_probability_on_player_action'])} | "
                     f"{_confidence_value(item['mean_top3_probability_mass'])} | "
                     f"{_confidence_value(item['mean_entropy_nats'])} | {item['high_confidence_mismatches_ge_0_75']} |")
    lines += ["", "Профили уверенности в [`data/processed_policy_tactical_analysis_1/results.private.json`](../../data/processed_policy_tactical_analysis_1/results.private.json): "
              "открытые средние и калибровочные интервалы описывают совпадение с выбором игрока, не шанс выиграть игру.", "",
              "### Неопределённость и чувствительность", "",
              "| Кандидат − Frozen v2 | ΔCE | 95% ДИ CE | ΔTop-1 | 95% ДИ Top-1 | 99% совместный ДИ: CE / Top-1 | ΔCE при равном весе матчей |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for name in ("retrained_v2", "policy_v3", "control_v3_seed42", "prepare_v2_seed42", "prepare_v3_seed42"):
        comparison = report["paired_comparisons"][f"{name}_minus_frozen_v2_ordinary"]
        ce = comparison["metrics"]["cross_entropy"]
        top = comparison["metrics"]["top1"]
        ci99 = comparison.get("simultaneous_primary_ci") or {}
        ce99 = ci99.get("cross_entropy", {}).get("ci99")
        top99 = ci99.get("top1", {}).get("ci99")
        jointly = "—" if ce99 is None or top99 is None else f"[{ce99[0]:.3f},{ce99[1]:.3f}] / [{top99[0]:.3f},{top99[1]:.3f}]"
        balanced = report["robustness"]["models"][name]["match_balanced_difference_vs_frozen_v2"]["cross_entropy"]
        lines.append(f"| {name} | {ce['difference']:.3f} | [{ce['ci95'][0]:.3f},{ce['ci95'][1]:.3f}] | "
                     f"{top['difference']:.3f} | [{top['ci95'][0]:.3f},{top['ci95'][1]:.3f}] | {jointly} | {balanced:.3f} |")
    lines += ["", "Per-match результаты анонимизированы hash-псевдонимами ниже; для каждого кандидата приведены leave-one-match-out и leave-one-class-out в private JSON. "
              "Классовые группы содержат только 2–4 матча, поэтому их знаки и разницы нестабильны.", "",
              "| Класс SELF | Матчей | Решений | Frozen v2 Top-1 / CE | Retrained v2 Top-1 / CE | Policy v3 Top-1 / CE |",
              "|---|---:|---:|---:|---:|---:|"]
    for player_class, item in report["stratified_metrics"]["by_self_class"].items():
        models = item["models"]
        def pair(name: str) -> str:
            m = models[name]["metrics"]
            return f"{m['top1']:.3f} / {m['cross_entropy']:.3f}"
        lines.append(f"| {player_class} | {item['matches']} | {item['decisions']} | {pair('frozen_v2')} | "
                     f"{pair('retrained_v2')} | {pair('policy_v3')} |")
    lines += ["", "Разбивка по ходу, типу фактического действия и размеру legal menu находится в private JSON вместе с таблицей по каждому матчу. "
              "Публичные короткие коды матчей не содержат исходных match ID.", "",
              "### Расхождения Frozen v2 и Policy v3", "",
              f"Top-1 совпал между Frozen v2 и Policy v3 в {report['model_disagreement']['frozen_policy_v3_top1_agreement']:.1%} решений. "
              f"На {report['model_disagreement']['policy_v3_imitation_only']} решениях Policy v3 совпал с игроком, а Frozen v2 нет; "
              f"на {report['model_disagreement']['frozen_imitation_only']} — наоборот. Эти категории измеряют только имитацию.", "",
              "## 2. Поведение и тактические гипотезы", "",
              "Проверенные наблюдения не равны доказанным ошибкам. Для трёх основных моделей:", "",
              "| Модель | Top-1 END_TURN, игрок продолжил | Игрок выбрал Hero Power, модель — другое | Модель выбрала Hero Power, игрок — другое |",
              "|---|---:|---:|---:|"]
    for name in ("frozen_v2", "retrained_v2", "policy_v3"):
        item = report["behavior_summary"][name]
        lines.append(f"| {name} | {item['top1_end_turn_player_continued']} | {item['player_hero_power_top1_other']} | "
                     f"{item['top1_hero_power_player_chose_other']} |")
    lines += ["", "Среди случаев `END_TURN`, где игрок продолжил, рядом сохранены два диагностических сигнала: scorer предпочёл не завершать ход и/или "
              "Outcome Shadow имел хотя бы один другой EXACT прогноз. Это не доказывает полезность действия: scorer — эвристика, "
              "а точное одношаговое изменение не оценивает будущую позицию.", "",
              "- **END_TURN, атака, розыгрыш и Hero Power.** Матрица типов действий показывает семейство рекомендации; точный Top-1 также зависит от выбора карты, источника и цели. Расхождение с игроком отмечает лишь различие поведения.",
              "- **Порядок действий и выгодные размены.** В наборе есть отдельные состояния, но нет контрфактических продолжений для всех альтернатив. Нельзя объявить порядок неправильным по тому, что модель и игрок атаковали разными объектами.",
              "- **Мана и тексты карт.** Модели получают видимое состояние, признаки действия и card ID embedding; текста правил в Policy входе нет. Неизвестный ID не сообщает модели текст эффекта. Это объясняет ограничение на новые/сложные карты как гипотезу о представлении, но не доказывает причину каждой ошибки.",
              "- **Летал.** Проверялись только отобранные спорные случаи и только точный lethal за одно действие. Итог: "
              f"{report['outcome_decision_review']['confirmed_one_action_lethals_outside_top3']} подтверждённых случаев lethal вне Top-3; многошаговый летал не искался.",
              "- **Outcome Shadow.** Его статусы PARTIAL/UNSUPPORTED ограничивают проверку механики. Проверка полного меню не делает частичный прогноз полным.",
              "",
              "В прежней ручной проверке EVAL-2 было 20 выбранных случаев: 19 с недостаточным покрытием, один — только расхождение без вывода, подтверждённых ошибок не было. Повторялись темы END_TURN против продолжения, разные атакующий/цель, карта против Hero Power и непрочитанные эффекты. Это уже исследованные примеры, а не оценка частоты ошибок.", "",
              "### Обезличенные примеры", ""]
    if cases:
        for index, case in enumerate(cases, 1):
            pos = case["visible_position"]
            lines += [f"**Ситуация {index}** — матч `{case['match']}`, {case['class']}, ход {pos['turn']}, "
                      f"мана {pos['self_mana']}, здоровье SELF/противника {pos['self_health']}/{pos['opponent_health']}, "
                      f"стол {pos['self_board_count']}/{pos['opponent_board_count']}, меню {pos['legal_menu_size']}",
                      f"Действие игрока: `{case['player_action']}`."]
            for name in ("frozen_v2", "policy_v3"):
                ranked = case["model_top3"].get(name, [])
                text_ranked = "; ".join(
                    f"{i}. {x['action']} (p={x['probability']:.2f}; Outcome {x['outcome_status']}"
                    f"{'; ' + ', '.join(x['exact_effects']) if x['exact_effects'] else ''}"
                    f"{'; совпало с игроком' if x['matches_player'] else ''})"
                    for i, x in enumerate(ranked, 1))
                lines.append(f"{name} Top-3: {text_ranked or 'нет'}.")
            scorer = "; ".join(
                f"{x['rank_group']}. {x['action']} (score={x['score']}; Outcome {x['outcome_status']}"
                f"{'; ' + ', '.join(x['exact_effects']) if x['exact_effects'] else ''})"
                for x in case["strategic_scorer_top3"])
            outcome = "; ".join(f"{x['action']}: {x['status']}" +
                                  (f"; {'; '.join(x['effects'])}" if x["effects"] else "")
                                  for x in case["outcome_shadow_sample"][:3])
            lines.append(f"Strategic Scorer: {scorer or 'нет'}. Outcome Shadow: {outcome or 'нет доступной строки'}.")
            if case["exact_one_action_lethal_outside_top3"]:
                lines.append("Строгое подтверждение: точный lethal за одно действие находится вне Top-3 у "
                             + ", ".join(case["exact_one_action_lethal_outside_top3"]) + ".")
            else:
                lines.append("Оценка силы хода не установлена: игрок, scorer и частичные прогнозы не являются эталоном.")
            lines.append("")
    else:
        lines += ["В протоколе не нашлось нескольких пригодных расхождений для компактного публичного разбора. Полные выбранные случаи остаются в ignored data/.", ""]
    lines += ["## 3. Что объясняет разницу моделей", "",
              "Policy v3 и Retrained v2 — парное сравнение с теми же данными обучения, split и seed 42; их отличие в архитектуре. Policy v3 кодирует сущности совместно и оценивает действие в контексте остальных legal actions. Frozen v2 против v3 одновременно меняет обучение и архитектуру, поэтому это не чистая оценка архитектуры.",
              "",
              "Для общей когорты v3 обучался на несбалансированном историческом корпусе: 79 матчей / 3 010 решений, включая Priest 45 матчей / 2 018 решений, Warrior 17/466, Demon Hunter 10/317, Death Knight 5/158 и Warlock 2/51. В исследуемой строгой выборке четыре класса и всего 2–4 матча на класс. Следовательно, разница по классам чувствительна к одной игре; данных недостаточно, чтобы приписать её архитектуре или назвать устойчивый class-specific эффект.",
              "",
              "Более прямое объяснение ограничений Policy — imitation learning: loss учится распределять высокий score на выбранное игроком действие. В нём нет цели выиграть матч, оценить будущую ценность позиции или провести поиск продолжений. Дополнительное внимание v3 помогает сопоставлять видимые объекты и альтернативы, но не добавляет правила карт и причинный прогноз.",
              "",
              "## 4. Ограничения данных", "",
              "- Все 295 решений принадлежат тем же 12 матчам EVAL-2; значения коррелируют внутри матча.",
              "- Игрок мог видеть рекомендации Frozen v2; это может влиять на сами метки.",
              "- В выборке мало матчей на класс, нет подтверждённых архетипов колод и нет метки оптимального действия.",
              "- Стратегический scorer — экспериментальная эвристика. Outcome Shadow умеет проверить только описанные эффекты; PARTIAL и UNSUPPORTED не подтверждают итоговую позицию.",
              "- Анализ не измеряет win rate или игровую силу и не открывает fresh_holdout.", "",
              "## 5. Следующий эксперимент", "",
              "**Приоритет 1 — маленькая абляция разрешения цели для ATTACK.** ML-POLICY-V3-1 уже показал, что v3 может выбирать правильный корень действия, не улучшая точность цели относительно контрольной v2. Новая выборка должна подтвердить, что на этих 295 повторяется разрыв между выбором семейства и точной цели. Если подтвердится, сравнить текущий action scorer с маленьким иерархическим вариантом: сначала корень (атака/карта/сила героя), затем источник и цель при одинаковом легальном меню. Обучить не более 3 seed на существующих данных, матчами разделить train/validation, evaluation; сохранить независимые новые real matches. Успех: улучшение exact ATTACK Top-1 и общего CE без ухудшения action-family accuracy, устойчивое по матчам и на новом независимом control. Опровержение: gain исчезает при равном весе матчей, достигается лишь на тех же классах/картах или ухудшает остальные типы действий. Риск — мало точных целевых примеров и переобучение на класс/карту.",
              "",
              "**Приоритет 2 — текст карты как проверяемая абляция для неизвестных эффектов.** Сейчас Policy не получает текст; случайные ошибки на незнакомых/непрочитанных картах — гипотеза, не установленная причина. После отдельного замораживания нового независимого набора сравнить ID-only и ID+текст на одних match-level split, отдельно на unseen-card ситуациях. Минимальный пилот — ограниченная группа карт из реальных матчей и один фиксированный text encoder; без массовой реализации карточных правил. Успех — преимущество на unseen-card CE/Top-1, без потери на известных картах и при фиксированном seed-протоколе. Опровержение — эффект исчезает вне тренировочных карт либо ухудшает ID-only набор. Риски — утечка карт между матчами, неполные тексты и рост уверенности без лучшего выбора.",
              "",
              "Не начинать обучение в рамках этого аудита. EVAL-1/EVAL-2 не использовать повторно как независимый финальный тест; перед следующим обучающим пилотом закрепить новую независимую проверку.",
              "",
              "## Воспроизведение", "",
              "1. `.venv/Scripts/python.exe scripts/policy_tactical_analysis_1.py --preflight` — строгий join и фиксация протокола.",
              "2. Сохранить протокол до inference.",
              "3. `.venv/Scripts/python.exe scripts/policy_tactical_analysis_1.py --evaluate` — offline inference существующих checkpoint и отчёт.",
              "",
              "Полные состояния, меню, logits и разборы находятся только в ignored `data/processed_policy_tactical_analysis_1/`. "
              "Inference не изменяет checkpoint или LIVE Policy.", ""]
    return "\n".join(lines)


def _render_protocol(public: dict) -> str:
    metrics = public["baseline"]["historical_204_metrics"]
    rows = "\n".join(
        f"| {name} | {metrics[name]['cross_entropy']:.4f} | {metrics[name]['top1']:.3f} | "
        f"{metrics[name]['top3']:.3f} | {metrics[name]['mrr']:.3f} |"
        for name in ("frozen_v2", "retrained_v2", "policy_v3"))
    return (
        "# POLICY-TACTICAL-ANALYSIS-1\n\n"
        f"Статус: **{public['status']}**. Идентификатор выборки: `{public['data_identity_sha256']}`.\n\n"
        "## Гипотеза и baseline до inference\n\n"
        f"{public['hypothesis']}\n\n"
        "Baseline — Frozen v2. Прежние метрики на 204 решениях уже исследованы и не являются независимым holdout.\n\n"
        "| Модель | CE | Top-1 | Top-3 | MRR |\n|---|---:|---:|---:|---:|\n"
        f"{rows}\n\n"
        f"Размер зафиксированной выборки: {public['counts']['matches']} матчей, {public['counts']['decisions']} решений; "
        f"из них восстановлено {public['counts']['recovered_for_this_analysis']}.\n\n"
        f"После фиксации EVAL-2 изменились только файлы join-check: {', '.join(public['documented_post_lock_code_changes'])}. "
        "Данные и checkpoint проверяются по старым pin; новые версии join-кода закреплены в этом протоколе.\n\n"
        "Методы и границы описаны в `protocol.json`. Обучение и fine-tuning не выполняются; "
        "fresh_holdout закрыт, LIVE Policy не меняется.\n"
    )


def evaluate() -> dict:
    versioned_protocol = PRIVATE / "protocol.private.v2.json"
    if not versioned_protocol.exists():
        original = _read_json(PRIVATE / "protocol.private.json")
        if sha256_file(ROOT / "scripts/policy_tactical_analysis_1.py") != original["source_hashes"]["scripts/policy_tactical_analysis_1.py"]:
            raise ValueError("analysis code changed after protocol lock; run --relock before inference")
    private_protocol = _read_json(versioned_protocol if versioned_protocol.exists()
                                  else PRIVATE / "protocol.private.json")
    rows = _read_jsonl(PRIVATE / "decisions.private.jsonl")
    _verify_locked(private_protocol, rows)
    if any((PRIVATE / name).exists() for name in (
        "logits.private.jsonl", "recovered_inference.private.jsonl", "cases.private.json", "results.private.json"
    )):
        raise FileExistsError("refusing to overwrite tactical-analysis inference outputs")

    eval2_protocol, baseline_rows, _, _ = recheck._read_cohort()
    _verify_locked_eval2_inputs(eval2_protocol, baseline_rows)
    recovered_rows = [row for row in rows if row["analysis_origin"] == "RECOVERED_91"]
    if len(recovered_rows) != EXPECTED_RECOVERED:
        raise ValueError("expected 91 recovered rows for offline inference")

    report, predictions, selected = base._run_evaluation(eval2_protocol, rows)
    report["data_identity_sha256"] = private_protocol["data_identity_sha256"]
    original_logits = _read_jsonl(ROOT / "data/processed_new_matches_eval_2/logits.private.jsonl")
    old_by_id = {row["example"]["decision_id"]: row for row in original_logits}
    new_by_id = {row["example"]["decision_id"]: row for row in predictions}
    if len(old_by_id) != 204 or set(old_by_id) != {row["example"]["decision_id"] for row in baseline_rows}:
        raise ValueError("EVAL-2 baseline inference does not match its locked 204 decisions")
    parity = {"compared_decisions": len(old_by_id), "compared_model_logits": 0,
              "exactly_identical_model_logits": 0, "max_abs_logit_difference": 0.0}
    for decision_id, old in old_by_id.items():
        current = new_by_id[decision_id]
        for model in base.MODELS:
            name = model["name"]
            previous = old["model_scores"][name].get("logits")
            present = current["model_scores"][name].get("logits")
            if not isinstance(previous, list) or not isinstance(present, list) or len(previous) != len(present):
                raise ValueError("baseline logit/menu shape mismatch")
            parity["compared_model_logits"] += 1
            parity["exactly_identical_model_logits"] += previous == present
            if previous:
                parity["max_abs_logit_difference"] = max(
                    parity["max_abs_logit_difference"],
                    max(abs(float(a) - float(b)) for a, b in zip(previous, present)))

    for name in base.MODELS:
        if sha256_file(ROOT / name["path"]) != name["sha256"]:
            raise ValueError(f"checkpoint changed during inference: {name['name']}")

    # Keep paired comparisons against Frozen v2 for all checkpoints, not only the
    # original EVAL-2 primary list. Bootstrap blocks are whole matches.
    subset = [row for row in predictions if not any(
        action["type"] == "PREPARE_CARD" for action in row["example"]["legal_actions"])]
    for name in (model["name"] for model in base.MODELS if model["name"] != "frozen_v2"):
        key = f"{name}_minus_frozen_v2_ordinary"
        if key not in report["paired_comparisons"]:
            report["paired_comparisons"][key] = base._paired_cluster_bootstrap(
                subset, [row["model_scores"][name] for row in subset],
                [row["model_scores"]["frozen_v2"] for row in subset])
        comparison = report["paired_comparisons"][key]
        left = [row["model_scores"][name] for row in subset]
        right = [row["model_scores"]["frozen_v2"] for row in subset]
        comparison["simultaneous_primary_ci"] = (eval2.simultaneous_bootstrap(subset, left, right)
                                                  if name in eval2.PRIMARY else None)

    report["confidence"] = _confidence_analysis(predictions)
    report["robustness"] = _robustness(predictions)
    report["behavior_summary"] = _behavior_summary(predictions)
    report["baseline_204_inference_parity"] = parity
    ordinary = [row for row in predictions if not any(
        action["type"] == "PREPARE_CARD" for action in row["example"]["legal_actions"])]
    model_names = [model["name"] for model in base.MODELS]
    frozen_map = _metric_record_map(ordinary, "frozen_v2")
    policy_map = _metric_record_map(ordinary, "policy_v3")
    shared_ids = set(frozen_map) & set(policy_map)
    report["model_disagreement"] = {
        "shared_decisions": len(shared_ids),
        "frozen_policy_v3_top1_agreement": sum(frozen_map[sid]["top_index"] == policy_map[sid]["top_index"]
                                                for sid in shared_ids) / len(shared_ids),
        "policy_v3_imitation_only": sum(
            policy_map[sid]["top1"] and not frozen_map[sid]["top1"] for sid in shared_ids),
        "frozen_imitation_only": sum(
            frozen_map[sid]["top1"] and not policy_map[sid]["top1"] for sid in shared_ids),
    }
    report["models_analyzed"] = model_names
    cases = _select_public_cases(predictions, selected, {"private_rows": selected.get("decision_review", [])})
    report["analysis_protocol"] = private_protocol

    private_results = {
        "report": report,
        "selected_cases": selected,
        "public_cases": cases,
        "predictions": predictions,
    }
    recovered_inference = [
        {"decision_id": row["example"]["decision_id"], "game_id": row["example"]["game_id"],
         "model_logits": {name: row["model_scores"][name]["logits"] for name in model_names}}
        for row in predictions if row["analysis_origin"] == "RECOVERED_91"
    ]
    _new_jsonl(PRIVATE / "logits.private.jsonl", predictions)
    _new_jsonl(PRIVATE / "recovered_inference.private.jsonl", recovered_inference)
    _new_json(PRIVATE / "cases.private.json", {"cases": selected, "public_examples": cases})
    _new_json(PRIVATE / "results.private.json", private_results)

    public_protocol = _read_json(REPORT / "protocol.json")
    public_protocol["status"] = "COMPLETE"
    public_protocol["results_sha256"] = sha256_file(PRIVATE / "results.private.json")
    (REPORT / "protocol.json").write_text(json.dumps(public_protocol, ensure_ascii=False, indent=2,
                                                      sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    (REPORT / "README.md").write_text(_render_report(report, cases, private_protocol), encoding="utf-8")
    return {"status": "COMPLETE", "decisions": len(predictions), "models": len(model_names),
            "outcome_review": report["outcome_decision_review"], "metrics": {
                name: report["evaluation_sets"]["ordinary_menus"]["models"][name]["metrics"]
                for name in ("frozen_v2", "retrained_v2", "policy_v3")}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--relock", action="store_true")
    modes.add_argument("--evaluate", action="store_true")
    args = parser.parse_args(argv)
    result = preflight() if args.preflight else relock() if args.relock else evaluate()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
