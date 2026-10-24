"""Compact per-match coverage diagnostics for completed collector matches."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .snapshot import state_hash
from .snapshot_join import collapse_identical_main_action_snapshots


def build_capture_report(match_id: str, policy_result: dict, recordings_root: Path,
                         journals_root: Path, policy_rows_path: Path,
                         *, live_observation: dict | None = None) -> dict:
    """Compare collected decisions with LIVE snapshots and existing optional journals.

    The report stores identities and counts only. It does not copy game states, raw log
    lines, player names, or opponent information.
    """
    total = _optional_int(policy_result.get("decisions_total"))
    labeled = _optional_int(policy_result.get("decisions_labeled"))
    skip_reasons = policy_result.get("decision_skip_reasons", {})
    policy_keys = _policy_keys(policy_rows_path, match_id)
    directories = _recording_directories(recordings_root, match_id)
    snapshots: list[dict] = []
    capture_summary = None
    recording_status = "NO_LIVE_RECORDING"
    recording_error = None
    if directories:
        recording_status = "RECORDED"
        if len(directories) > 1:
            recording_status = "MULTIPLE_RECORDINGS"
        for directory in directories:
            summary_path = directory / "capture_summary.json"
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    capture_summary = _merge_summaries(capture_summary, summary)
                except (OSError, ValueError, TypeError):
                    recording_error = "CAPTURE_SUMMARY_INVALID"
            snapshot_path = directory / "snapshots.jsonl"
            if snapshot_path.exists():
                try:
                    snapshots.extend(_read_jsonl(snapshot_path))
                except (OSError, ValueError, TypeError):
                    recording_error = "SNAPSHOTS_INVALID"
    elif live_observation is not None:
        capture_summary = live_observation
        recording_status = "LIVE_OBSERVED_NO_RECORDING"

    valid_snapshots: dict[tuple[str, int, str], dict] = {}
    grouped: dict[tuple[str, int, str], list[dict]] = defaultdict(list)
    invalid_snapshot_rows = 0
    for row in snapshots:
        key = _snapshot_key(row)
        if key is None:
            invalid_snapshot_rows += 1
        else:
            grouped[key].append(row)
    conflicting_snapshot_groups = 0
    for key, rows in grouped.items():
        result = collapse_identical_main_action_snapshots(rows)
        if result.snapshot is None:
            conflicting_snapshot_groups += 1
        else:
            valid_snapshots[key] = result.snapshot

    strict_matches = len(policy_keys & {
        (game_key, options_id, digest)
        for game_key, options_id, digest in valid_snapshots
    })
    strict_comparable = (policy_rows_path.exists() and labeled is not None
                         and len(policy_keys) == labeled)
    journal_counts, journal_decisions = _journal_counts(journals_root, match_id)
    matched_journals = {
        name: len(policy_keys & decisions)
        for name, decisions in journal_decisions.items()
    }

    missing_reasons: dict[str, int] = {}
    if recording_status == "NO_LIVE_RECORDING" and total is not None:
        missing_reasons["LIVE_NOT_OBSERVED_OR_NOT_RECORDED"] = total
    if capture_summary:
        for reason, count in capture_summary.get("trust_rejections", {}).items():
            if isinstance(count, int) and count > 0:
                missing_reasons[str(reason)] = count
        failures = capture_summary.get("recording_failures", {})
        if isinstance(failures, dict):
            for code, count in failures.items():
                if isinstance(count, int) and count > 0:
                    missing_reasons[f"RECORDING_{code}"] = count
        if recording_status == "LIVE_OBSERVED_NO_RECORDING":
            emitted = _summary_int(capture_summary, "trusted_snapshots_emitted") or 0
            saved = _summary_int(capture_summary, "snapshots_saved") or 0
            if emitted > saved:
                missing_reasons["SNAPSHOT_NOT_SAVED"] = emitted - saved
        superseded = capture_summary.get("superseded_menus")
        if isinstance(superseded, int) and superseded > 0:
            missing_reasons["OPTIONS_SUPERSEDED"] = superseded
    if recording_error:
        missing_reasons[recording_error] = max(1, missing_reasons.get(recording_error, 0))

    return {
        "schema": "manamind.live.capture_report/1",
        "match_id": match_id,
        "collector": {
            "status": policy_result.get("status", "UNKNOWN"),
            "power_log_decisions": total,
            "policy_labeled_decisions": labeled,
            "policy_skipped_decisions": _optional_int(policy_result.get("decisions_skipped")),
            "policy_skip_reasons": dict(sorted(skip_reasons.items())) if isinstance(skip_reasons, dict) else {},
        },
        "live": {
            "status": recording_status,
            "absence_reason": _absence_reason(recording_status, capture_summary),
            "options_packets_seen": _summary_int(capture_summary, "options_packets_seen"),
            "trusted_snapshots_emitted": _summary_int(capture_summary, "trusted_snapshots_emitted"),
            "snapshots_saved": len(snapshots),
            "valid_trusted_snapshots": len(valid_snapshots),
            "invalid_snapshot_rows": invalid_snapshot_rows,
            "conflicting_identity_groups": conflicting_snapshot_groups,
            "trust_rejections": (capture_summary or {}).get("trust_rejections", {}),
            "superseded_menus": _summary_int(capture_summary, "superseded_menus"),
            "recording_failures": (capture_summary or {}).get("recording_failures", {}),
        },
        "strict_identity": {
            "comparable_to_labeled_policy_decisions": strict_comparable,
            "labeled_policy_decisions_with_exact_snapshot": strict_matches if strict_comparable else None,
            "labeled_policy_decisions_without_exact_snapshot": (
                max(0, labeled - strict_matches) if strict_comparable else None
            ),
        },
        "journals": {
            "rows_by_kind": journal_counts,
            "strict_labeled_decisions_with_row": matched_journals if strict_comparable else None,
        },
        "missed_reason_counts": dict(sorted(missing_reasons.items())),
        "notes": [
            "No LIVE recording with no in-process observation cannot distinguish an app that was stopped from a failed recorder.",
            "Strict comparison uses labeled imported decisions; skipped Power.log decisions have no dataset identity row.",
            "Journal counts describe rows found on disk; zero can mean a shadow was disabled or its write failed.",
        ],
    }


def _recording_directories(root: Path, match_id: str) -> list[Path]:
    if not root.exists():
        return []
    result = []
    for path in root.glob(f"*/{match_id[:16]}"):
        try:
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("game_key") == match_id:
            result.append(path)
    return sorted(result)


def _snapshot_key(row: object) -> tuple[str, int, str] | None:
    if not isinstance(row, dict):
        return None
    decision, state = row.get("decision"), row.get("state")
    if not isinstance(decision, dict) or not isinstance(state, dict):
        return None
    match_id, digest = row.get("game_key"), row.get("state_hash")
    options_id = decision.get("options_id")
    legal = decision.get("legal")
    if (row.get("status") != "READY" or row.get("active_player") != "SELF"
            or decision.get("kind") != "MAIN_ACTION" or not isinstance(legal, list) or not legal
            or not isinstance(match_id, str) or not isinstance(options_id, int) or isinstance(options_id, bool)
            or not isinstance(digest, str) or state_hash(state) != digest):
        return None
    return match_id, options_id, digest


def _policy_keys(path: Path, match_id: str) -> set[tuple[str, int, str]]:
    keys: set[tuple[str, int, str]] = set()
    if not path.exists():
        return keys
    try:
        for row in _read_jsonl(path):
            if row.get("game_id") != match_id:
                continue
            decision_id = row.get("decision_id")
            provenance = row.get("provenance")
            digest = provenance.get("state_hash") if isinstance(provenance, dict) else None
            if not isinstance(decision_id, str) or not isinstance(digest, str):
                continue
            prefix, separator, option = decision_id.rpartition(":")
            if prefix == match_id and separator:
                try:
                    keys.add((match_id, int(option), digest))
                except ValueError:
                    continue
    except (OSError, ValueError, TypeError):
        return set()
    return keys


def _journal_counts(root: Path, match_id: str) -> tuple[dict[str, int], dict[str, set[tuple[str, int, str]]]]:
    counts = Counter()
    decisions: dict[str, set[tuple[str, int, str]]] = defaultdict(set)
    if root.exists():
        for path in sorted(root.glob("prediction_journal*.jsonl")):
            try:
                rows = _read_jsonl(path)
            except (OSError, ValueError, TypeError):
                continue
            for row in rows:
                if row.get("match_id") != match_id:
                    continue
                event = row.get("event")
                kind = {
                    "RECOMMENDATION": "prediction",
                    "OUTCOME_SHADOW": "outcome_shadow",
                    "STRATEGY_SHADOW": "strategy_shadow",
                    "MODEL_SHADOW": "model_shadow",
                }.get(event)
                if kind:
                    counts[kind] += 1
                    decision_id = row.get("decision_id")
                    digest = row.get("state_hash")
                    if isinstance(decision_id, str) and isinstance(digest, str):
                        parts = decision_id.split(":")
                        if len(parts) == 4 and parts[0] == match_id and parts[3] == digest:
                            try:
                                decisions[kind].add((match_id, int(parts[2]), digest))
                            except ValueError:
                                pass
    return dict(sorted(counts.items())), decisions


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for text in path.read_text(encoding="utf-8").splitlines():
        if text.strip():
            row = json.loads(text)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _merge_summaries(left: dict | None, right: dict) -> dict:
    if left is None:
        return right
    result = dict(left)
    for name in ("options_packets_seen", "trusted_snapshots_emitted", "superseded_menus"):
        if isinstance(right.get(name), int):
            result[name] = int(result.get(name, 0)) + int(right[name])
    for name in ("trust_rejections", "recording_failures"):
        merged = Counter(result.get(name, {}))
        merged.update(right.get(name, {}))
        result[name] = dict(sorted(merged.items()))
    return result


def _optional_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _summary_int(summary: dict | None, key: str) -> int | None:
    return _optional_int(summary.get(key)) if summary else None


def _absence_reason(status: str, summary: dict | None) -> str | None:
    if status == "NO_LIVE_RECORDING":
        return "LIVE_NOT_OBSERVED_OR_NOT_RECORDED"
    if status == "LIVE_OBSERVED_NO_RECORDING":
        return "RECORDING_WRITE_FAILED" if (summary or {}).get("recording_failures") else "RECORDING_UNAVAILABLE"
    return None
