"""Read-only strict-join recheck of the locked NEW-MATCHES-EVAL-2 cohort.

The original EVAL-2 evaluator and results stay unchanged. This follow-up only
rechecks the 91 outcome-row conflicts using a semantic signature that drops the
per-action timing measurement, while preserving the exact state, source line,
sequence membership, checkpoint and full ordered legal-menu checks.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import live_join_coverage_1 as join_audit  # noqa: E402
import new_matches_eval_1 as eval1  # noqa: E402
from manamind.live.journal_join import outcome_journal_signature  # noqa: E402
from manamind.live.snapshot import canonical_json  # noqa: E402
from manamind.live.snapshot_join import collapse_identical_main_action_snapshots  # noqa: E402

PRIVATE = ROOT / "data/processed_new_matches_eval_2"
EXPECTED_IDENTITY = "9522fcec5b3768d351703517ed6f557e4c352c8e537883df6a8a91819939a906"
EXPECTED_BASELINE = {
    "CONFLICTING_OUTCOME_ROWS": 91,
    "LIVE_SNAPSHOT_NOT_MATCHED": 694,
    "NO_PREDICTION_ROW": 5,
}


def _key(row: dict) -> tuple[str, int, str]:
    example = row["example"]
    return (example["game_id"], int(example["decision_id"].rsplit(":", 1)[1]),
            example["provenance"]["state_hash"])


def _read_cohort() -> tuple[dict, list[dict], list[dict], set[str]]:
    protocol = eval1._read_json(PRIVATE / "protocol.private.json")
    if protocol.get("status") != "PROTOCOL_LOCKED" or protocol.get("dataset_identity_sha256") != EXPECTED_IDENTITY:
        raise ValueError("local NEW-MATCHES-EVAL-2 protocol does not match the published cohort")
    decisions_path = PRIVATE / "decisions.private.jsonl"
    if eval1.sha256_file(decisions_path) != protocol.get("private_decisions_sha256"):
        raise ValueError("locked EVAL-2 decisions file changed")

    with decisions_path.open(encoding="utf-8") as stream:
        decisions = [json.loads(line) for line in stream if line.strip()]
    with (PRIVATE / "diagnostic.private.jsonl").open(encoding="utf-8") as stream:
        diagnostic = [json.loads(line) for line in stream if line.strip()]
    decision_ids = sorted(row["example"]["decision_id"] for row in decisions)
    if decision_ids != protocol.get("eligible_decision_ids"):
        raise ValueError("locked EVAL-2 decision identities changed")
    heldout = set(eval1._read_json(ROOT / eval1.SPLIT_PLAN)["parts"]["fresh_holdout"])
    if any(row["example"]["game_id"] in heldout for row in decisions + diagnostic):
        raise ValueError("protected fresh_holdout row found in the EVAL-2 artifacts")
    reasons = Counter(row.get("exclusion_reason") for row in diagnostic)
    if dict(sorted(reasons.items())) != EXPECTED_BASELINE:
        raise ValueError("EVAL-2 diagnostic exclusion counts differ from the locked report")
    return protocol, decisions, diagnostic, heldout


def _recoverable_outcome_conflict(example: dict, key: tuple, snapshots: list[dict], groups: dict,
                                  raw_count: int) -> tuple[bool, str | None]:
    if raw_count != 1:
        return False, "AMBIGUOUS_RAW_DECISION_KEY"
    collapsed = collapse_identical_main_action_snapshots(snapshots)
    if collapsed.snapshot is None:
        return False, collapsed.reason or "INVALID_SNAPSHOT"
    if canonical_json(collapsed.snapshot["state"]) != canonical_json(example["state"]):
        return False, "LIVE_STATE_MISMATCH"

    option_line = example.get("provenance", {}).get("options_line")
    source = collapsed.snapshot.get("source")
    source_line = source.get("line_in_game") if isinstance(source, dict) else None
    if (not isinstance(option_line, int) or isinstance(option_line, bool)
            or not isinstance(source_line, int) or isinstance(source_line, bool) or source_line != option_line):
        return False, "OPTIONS_SOURCE_LINE_MISMATCH"

    selected: dict[str, dict[tuple, list[dict]]] = {}
    for kind in ("prediction", "strategy", "outcome"):
        record_rows = groups[kind].get(key, [])
        if not record_rows:
            return False, f"NO_{kind.upper()}_ROW"
        if any(not join_audit._seq_in_snapshot_group(row, snapshots) for row in record_rows):
            return False, f"{kind.upper()}_SEQ_NOT_IN_SNAPSHOT_GROUP"
        selected[kind] = {key: record_rows}

    outcome_rows = selected["outcome"][key]
    if len({outcome_journal_signature(row) for row in outcome_rows}) != 1:
        return False, "CONFLICTING_OUTCOME_SEMANTICS"
    selected["outcome"] = {key: [outcome_rows[0]]}

    for kind in ("prediction", "strategy"):
        _, reason = eval1._one_record(selected[kind][key], kind)
        if reason:
            return False, reason

    recommendation = selected["prediction"][key][0]
    if recommendation.get("checkpoint_sha256") != eval1.MODELS[0]["sha256"]:
        return False, "LIVE_CHECKPOINT_MISMATCH"
    action_json = {canonical_json(action) for action in example["legal_actions"]}
    top3 = recommendation.get("top3")
    if not top3 or any(canonical_json(item.get("action")) not in action_json for item in top3):
        return False, "LIVE_RECOMMENDATION_MENU_MISMATCH"

    for kind in ("strategy", "outcome"):
        row = selected[kind][key][0]
        actions = example["legal_actions"]
        if not eval1._match_menu_actions(row, actions):
            return False, f"{kind.upper()}_MENU_MISMATCH"
        if len(row.get("actions", [])) != len(actions):
            return False, f"{kind.upper()}_MENU_DUPLICATE_INDEX"
    return True, None


def recheck() -> dict:
    protocol, decisions, diagnostic, heldout = _read_cohort()
    rows = decisions + diagnostic
    candidate_ids = {row["example"]["game_id"] for row in rows}
    shadow_rows, _ = eval1._load_shadow_rows(candidate_ids, heldout)
    groups = eval1._group_shadows(shadow_rows)
    snapshots_by_game = {}
    for game_id in candidate_ids:
        snapshots, _, parse_error = join_audit._read_candidate_snapshots(game_id)
        if parse_error:
            raise ValueError(f"snapshot parse failed: {parse_error}")
        snapshots_by_game[game_id] = snapshots

    raw_counts = Counter(_key(row) for row in rows)
    recovered = []
    rejected = Counter()
    exclusions_by_action: dict[str, Counter] = defaultdict(Counter)
    missing_by_game: dict[str, Counter] = defaultdict(Counter)
    missing_cross_refs = Counter()
    for item in diagnostic:
        reason = item.get("exclusion_reason")
        example = item["example"]
        action = example["legal_actions"][example["chosen_action_index"]]["type"]
        exclusions_by_action[action][reason] += 1
        if reason == "LIVE_SNAPSHOT_NOT_MATCHED":
            key = _key(item)
            all_snapshots = [snapshot for group in snapshots_by_game[key[0]].values() for snapshot in group]
            has_any_snapshot = bool(all_snapshots)
            missing_by_game[key[0]]["unmatched_decisions"] += 1
            missing_by_game[key[0]]["has_other_snapshots" if has_any_snapshot else "no_snapshots"] += 1
            missing_cross_refs["same_options_id"] += any(
                snapshot.get("decision", {}).get("options_id") == key[1] for snapshot in all_snapshots
            )
            missing_cross_refs["same_state_hash"] += any(
                snapshot.get("state_hash") == key[2] for snapshot in all_snapshots
            )
        if reason != "CONFLICTING_OUTCOME_ROWS":
            continue
        key = _key(item)
        passed, reason = _recoverable_outcome_conflict(
            example, key, snapshots_by_game[key[0]].get(key, []), groups, raw_counts[key]
        )
        if passed:
            recovered.append(item)
        else:
            rejected[reason or "UNKNOWN"] += 1

    by_action: Counter = Counter()
    by_class: Counter = Counter()
    for item in recovered:
        example = item["example"]
        action = example["legal_actions"][example["chosen_action_index"]]["type"]
        player_class = example["state"]["self_player"].get("player_class") or "UNKNOWN"
        by_action[action] += 1
        by_class[player_class] += 1

    baseline = len(decisions)
    result = {
        "cohort_identity_sha256": protocol["dataset_identity_sha256"],
        "cohort": {"matches": len(protocol["eligible_match_ids"]), "strict_decisions": baseline,
                   "diagnostic_decisions": len(diagnostic)},
        "baseline_exclusions": dict(sorted(Counter(item["exclusion_reason"] for item in diagnostic).items())),
        "baseline_exclusions_by_selected_action": {
            action: dict(sorted(counts.items())) for action, counts in sorted(exclusions_by_action.items())
        },
        "unmatched_snapshot_availability": {
            "matches_with_no_snapshots": sum(counts["no_snapshots"] > 0 for counts in missing_by_game.values()),
            "decisions_from_matches_with_no_snapshots": sum(counts["no_snapshots"] for counts in missing_by_game.values()),
            "matches_with_other_snapshots_only": sum(counts["has_other_snapshots"] > 0 for counts in missing_by_game.values()),
            "decisions_with_other_snapshots_only": sum(counts["has_other_snapshots"] for counts in missing_by_game.values()),
            "decisions_with_same_options_id": missing_cross_refs["same_options_id"],
            "decisions_with_same_state_hash": missing_cross_refs["same_state_hash"],
        },
        "outcome_conflict_recheck": {
            "examined": EXPECTED_BASELINE["CONFLICTING_OUTCOME_ROWS"],
            "recovered_strictly": len(recovered),
            "rejected": dict(sorted(rejected.items())),
            "by_selected_action": dict(sorted(by_action.items())),
            "by_player_class": dict(sorted(by_class.items())),
        },
        "after_exclusions": {
            "strict_decisions": baseline + len(recovered),
            "diagnostic_decisions": len(diagnostic) - len(recovered),
            "remaining": {
                "CONFLICTING_OUTCOME_ROWS": EXPECTED_BASELINE["CONFLICTING_OUTCOME_ROWS"] - len(recovered),
                "LIVE_SNAPSHOT_NOT_MATCHED": EXPECTED_BASELINE["LIVE_SNAPSHOT_NOT_MATCHED"],
                "NO_PREDICTION_ROW": EXPECTED_BASELINE["NO_PREDICTION_ROW"],
            },
        },
        "invariants": {
            "fresh_holdout_rows_opened": False,
            "model_inference_or_training": False,
            "state_and_ordered_menu_checks_unchanged": True,
            "outcome_timing_us_is_the_only_ignored_action_field": True,
        },
    }
    if sum(result["after_exclusions"]["remaining"].values()) != result["after_exclusions"]["diagnostic_decisions"]:
        raise AssertionError("after-exclusions counts do not balance")
    return result


if __name__ == "__main__":
    print(json.dumps(recheck(), ensure_ascii=False, indent=2))
