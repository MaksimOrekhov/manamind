"""Read-only technical audit of repeated LIVE snapshots for NEW-MATCHES-EVAL-1.

This checks source and shadow joins only. It does not score or run a model, write
evaluation inputs, or modify the locked NEW-MATCHES-EVAL-1 protocol/results.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import new_matches_eval_1 as eval1  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.live.snapshot_join import collapse_identical_main_action_snapshots  # noqa: E402


PRIVATE_DIR = ROOT / "data/processed_live_join_coverage_1"
PRIVATE_RESULT = PRIVATE_DIR / "diagnostic.private.json"


def _candidate_raw_paths(heldout: set[str], history: dict[str, set[str]]) -> list[Path]:
    root = ROOT / "data/raw/collected"
    candidates = []
    for path in sorted(root.glob("*.log")):
        stem = path.stem
        keyed = len(stem) == 16 and all(char in "0123456789abcdef" for char in stem.lower())
        if not keyed:
            continue
        if any(match_id.startswith(stem) for match_id in heldout):
            continue
        if any(match_id.startswith(stem) for match_id in history):
            continue
        candidates.append(path)
    return candidates


def _read_candidate_snapshots(match_id: str) -> tuple[dict[tuple, list[dict]], int, str | None]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    count = 0
    for path in eval1._find_live_snapshots(match_id):
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("game_key") != match_id:
                        continue
                    decision = row.get("decision", {})
                    if decision.get("kind") != "MAIN_ACTION":
                        continue
                    try:
                        key = (match_id, int(decision["options_id"]), row["state_hash"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    groups[key].append(row)
                    count += 1
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return {}, count, type(error).__name__
    return groups, count, None


def _seq_in_snapshot_group(row: dict, snapshot_rows: list[dict]) -> bool:
    parts = str(row.get("decision_id", "")).split(":")
    if len(parts) != 4 or parts[0] != row.get("match_id"):
        return False
    try:
        seq = int(parts[1])
        options_id = int(parts[2])
    except (TypeError, ValueError):
        return False
    if "seq" in row and row.get("seq") != seq:
        return False
    if "options_id" in row and row.get("options_id") != options_id:
        return False
    return seq in {snapshot.get("seq") for snapshot in snapshot_rows}


def _diagnose_candidate(path: Path, catalog: CardCatalog, journal_groups: dict,
                       heldout: set[str], history: dict[str, set[str]]) -> dict:
    examples, summary = eval1._load_match_rows(path, catalog)
    match_id = summary["game_id"]
    if match_id in heldout:
        raise ValueError("candidate raw content resolves to a protected ID; stopping")
    if match_id in history:
        raise ValueError("candidate raw content overlaps prior history; stopping")
    if not match_id.startswith(path.stem):
        return {"status": "FILENAME_ID_MISMATCH", "imported_decisions": len(examples)}
    alias = hashlib.sha256(match_id.encode("utf-8")).hexdigest()[:12]
    snapshots, snapshot_count, parse_error = _read_candidate_snapshots(match_id)
    if parse_error:
        return {"alias": alias, "status": f"SNAPSHOT_{parse_error}",
                "imported_decisions": len(examples), "snapshots": snapshot_count}

    raw_key_counts: Counter = Counter()
    for example in examples:
        option = int(example["decision_id"].rsplit(":", 1)[1])
        raw_key_counts[(match_id, option, example["provenance"]["state_hash"])] += 1

    reasons: Counter = Counter()
    collapsed_keys = 0
    duplicate_decisions = 0
    recovered_decisions = 0
    old_eligible_decisions = 0
    old_eligible_keys = set()
    new_eligible_keys = set()
    duplicate_seq_conflicts: Counter = Counter()
    duplicate_failure_reasons: Counter = Counter()
    duplicate_conflicting_fields: Counter = Counter()

    for example in examples:
        option = int(example["decision_id"].rsplit(":", 1)[1])
        key = (match_id, option, example["provenance"]["state_hash"])
        snapshot_rows = snapshots.get(key, [])
        duplicate = len(snapshot_rows) > 1
        if duplicate:
            duplicate_decisions += 1
        elif not snapshot_rows:
            reasons["LIVE_SNAPSHOT_NOT_MATCHED"] += 1
            continue

        old_snapshot_ok = len(snapshot_rows) == 1
        if raw_key_counts[key] != 1:
            reasons["AMBIGUOUS_RAW_DECISION_KEY"] += 1
            if duplicate:
                duplicate_failure_reasons["AMBIGUOUS_RAW_DECISION_KEY"] += 1
            continue

        join_result = collapse_identical_main_action_snapshots(snapshot_rows)
        if join_result.snapshot is None:
            reason = join_result.reason or "INVALID_SNAPSHOT"
            reasons[reason] += 1
            if duplicate:
                duplicate_seq_conflicts[reason] += 1
                duplicate_failure_reasons[reason] += 1
            continue
        if duplicate:
            collapsed_keys += 1

        if old_snapshot_ok:
            if _pair_reason(example, key, snapshot_rows, journal_groups) is None:
                old_eligible_decisions += 1
                old_eligible_keys.add(key)

        reason = _pair_reason(example, key, snapshot_rows, journal_groups,
                              require_snapshot_sequence_membership=duplicate)
        if reason:
            reasons[reason] += 1
            if duplicate:
                duplicate_failure_reasons[reason] += 1
                if reason.startswith("CONFLICTING_"):
                    kind = reason.removeprefix("CONFLICTING_").removesuffix("_ROWS").lower()
                    duplicate_conflicting_fields.update(_conflicting_signature_fields(kind, key, journal_groups))
            continue
        if duplicate:
            recovered_decisions += 1
        new_eligible_keys.add(key)

    return {
        "alias": alias,
        "status": "OK",
        "imported_decisions": len(examples),
        "main_action_snapshots": snapshot_count,
        "snapshot_join_keys": len(snapshots),
        "duplicate_snapshot_keys": sum(len(rows) > 1 for rows in snapshots.values()),
        "raw_decisions_with_duplicate_snapshots": duplicate_decisions,
        "identical_snapshot_keys_collapsed": collapsed_keys,
        "recoverable_duplicate_decisions": recovered_decisions,
        "baseline_exact_join_decisions_recomputed": old_eligible_decisions,
        "new_exact_join_decisions": len(new_eligible_keys),
        "newly_eligible_matches": int(bool(new_eligible_keys) and not old_eligible_keys),
        "raw_decisions": len(examples),
        "importer_skipped_decisions": summary["decisions_skipped"],
        "exclusions": dict(sorted(reasons.items())),
        "duplicate_exclusions": dict(sorted(duplicate_failure_reasons.items())),
        "duplicate_conflicting_signature_fields": dict(sorted(duplicate_conflicting_fields.items())),
        "duplicate_snapshot_group_failures": dict(sorted(duplicate_seq_conflicts.items())),
    }


def _pair_reason(example: dict, key: tuple, snapshot_rows: list[dict], journal_groups: dict,
                 *, require_snapshot_sequence_membership: bool = False) -> str | None:
    kinds = ("prediction", "strategy", "outcome")
    records = {}
    for kind in kinds:
        group = journal_groups[kind].get(key, [])
        if not group:
            return f"NO_{kind.upper()}_ROW"
        if require_snapshot_sequence_membership and any(
                not _seq_in_snapshot_group(row, snapshot_rows) for row in group):
            return f"{kind.upper()}_SEQ_NOT_IN_SNAPSHOT_GROUP"
        record, reason = eval1._one_record(group, kind)
        if reason:
            return reason
        records[kind] = record

    recommendation = records["prediction"]
    if recommendation.get("checkpoint_sha256") != eval1.MODELS[0]["sha256"]:
        return "LIVE_CHECKPOINT_MISMATCH"
    action_by_json = {eval1.canonical_json(action): i for i, action in enumerate(example["legal_actions"])}
    try:
        top3 = recommendation["top3"]
        if not top3 or any(eval1.canonical_json(item["action"]) not in action_by_json for item in top3):
            return "LIVE_RECOMMENDATION_MENU_MISMATCH"
    except (KeyError, TypeError):
        return "LIVE_RECOMMENDATION_MENU_MISMATCH"
    if not eval1._match_menu_actions(records["strategy"], example["legal_actions"]):
        return "STRATEGY_MENU_MISMATCH"
    if not eval1._match_menu_actions(records["outcome"], example["legal_actions"]):
        return "OUTCOME_MENU_MISMATCH"
    return None


def _conflicting_signature_fields(kind: str, key: tuple, journal_groups: dict) -> list[str]:
    fields = {
        "prediction": ("event", "checkpoint_sha256", "top3"),
        "strategy": ("schema", "scorer", "params", "forecaster_rev", "texts_sha256", "context",
                     "complete", "menu_size", "top3", "actions"),
        "outcome": ("schema", "forecaster_rev", "texts_sha256", "context", "complete", "menu_size", "actions"),
    }[kind]
    rows = journal_groups[kind].get(key, [])
    return [field for field in fields
            if len({eval1.canonical_json(row.get(field)) for row in rows}) > 1]


def run_diagnostic() -> dict:
    split_plan = eval1._read_json(ROOT / eval1.SPLIT_PLAN)
    heldout = set(split_plan.get("parts", {}).get("fresh_holdout", []))
    if len(heldout) != 9:
        raise ValueError("expected nine protected fresh_holdout IDs")
    history, _ = eval1._load_history(heldout)
    paths = _candidate_raw_paths(heldout, history)
    if len(paths) != 14:
        raise ValueError(f"expected 14 nonoverlap keyed raw candidates, found {len(paths)}")

    candidate_ids = {path.stem for path in paths}
    shadow_rows, _ = eval1._load_shadow_rows(candidate_ids, heldout)
    journal_groups = eval1._group_shadows(shadow_rows)
    catalog = CardCatalog.from_json(ROOT / eval1.CARDS)
    candidates = []
    for path in paths:
        candidates.append(_diagnose_candidate(path, catalog, journal_groups, heldout, history))

    duplicate_exclusions: Counter = Counter()
    conflicting_signature_fields: Counter = Counter()
    duplicate_count = recovered = duplicate_keys = new_match_count = 0
    baseline_exact = total_raw = total_snapshot_rows = 0
    for item in candidates:
        total_raw += item.get("raw_decisions", item.get("imported_decisions", 0))
        total_snapshot_rows += item.get("main_action_snapshots", 0)
        duplicate_count += item.get("raw_decisions_with_duplicate_snapshots", 0)
        recovered += item.get("recoverable_duplicate_decisions", 0)
        duplicate_keys += item.get("duplicate_snapshot_keys", 0)
        baseline_exact += item.get("baseline_exact_join_decisions_recomputed", 0)
        new_match_count += item.get("newly_eligible_matches", 0)
        duplicate_exclusions.update(item.get("duplicate_exclusions", {}))
        conflicting_signature_fields.update(item.get("duplicate_conflicting_signature_fields", {}))

    result = {
        "scope": "14 new nonoverlap keyed raw matches, candidate-specific snapshots, and shadow rows filtered by heldout ID before JSON parsing",
        "method": "technical join verification only; no model loading for scoring, training, inference, or evaluation metrics",
        "candidate_matches": len(candidates),
        "raw_decisions": total_raw,
        "main_action_snapshots": total_snapshot_rows,
        "duplicate_snapshot_keys": duplicate_keys,
        "duplicate_raw_decisions": duplicate_count,
        "safe_duplicate_decisions_recovered": recovered,
        "duplicate_decisions_still_excluded": duplicate_count - recovered,
        "duplicate_exclusion_reasons": dict(sorted(duplicate_exclusions.items())),
        "conflicting_shadow_signature_fields": dict(sorted(conflicting_signature_fields.items())),
        "existing_exact_joins_recomputed_for_parity": baseline_exact,
        "additional_matches_with_exact_join": new_match_count,
        "candidates": candidates,
    }
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_RESULT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    result = run_diagnostic()
    public_summary = {key: value for key, value in result.items() if key != "candidates"}
    print(json.dumps(public_summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
