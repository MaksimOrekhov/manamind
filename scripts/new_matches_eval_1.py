"""Protocol lock and independent, inference-only evaluation for NEW-MATCHES-EVAL-1.

Run --preflight first. It inventories only new, non-overlapping matches, verifies the
LIVE-to-import joins, writes private inputs under the ignored processed data tree,
and freezes the protocol. Commit that report before running --evaluate.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.lines import read_complete_lines, split_games  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match  # noqa: E402
from manamind.live.snapshot import canonical_json  # noqa: E402
from manamind.models.policy_inputs import representation_of  # noqa: E402
from manamind.outcome.shadow import action_digest, context_from_dict  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402
from manamind.training.real_policy import encode_example, validate_example  # noqa: E402


SPLIT_PLAN = Path("data/processed_policy_prepare_1/split_plan.json")
USAGE_REGISTRY = Path("data/processed_policy_prepare_1/usage_registry.json")
CARDS = Path("data/cards/standard_current_enUS.json")
PRIVATE_DIR = Path("data/processed_new_matches_eval_1")
PRIVATE_PROTOCOL = PRIVATE_DIR / "protocol.private.json"
PRIVATE_DECISIONS = PRIVATE_DIR / "decisions.private.jsonl"
PRIVATE_LOGITS = PRIVATE_DIR / "logits.private.jsonl"
PRIVATE_EXAMPLES = PRIVATE_DIR / "examples.private.json"
REPORT_DIR = Path("reports/new_matches_eval_1")
README = REPORT_DIR / "README.md"
RESULTS = REPORT_DIR / "results.json"

# All choices below are fixed before inference. The two Prepare control checkpoints
# are included to measure the Prepare-specific ablation on ordinary menus.
MODELS = (
    {"name": "frozen_v2", "path": "data/processed_policy_ml2a/seed42_v2/policy.pt",
     "sha256": "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d",
     "metrics": "data/processed_policy_ml2a/seed42_v2/metrics.json", "supports_prepare": False,
     "role": "live_baseline"},
    {"name": "retrained_v2", "path": "data/processed_policy_v3/experiment_1/final/architecturev2_seed42/policy.pt",
     "sha256": "9358f932fc7846d6a436e2a1e6c7ff6cffda1f2929fac5521710f973e14a05e3",
     "metrics": "data/processed_policy_v3/experiment_1/final/architecturev2_seed42/metrics.json",
     "supports_prepare": False, "role": "primary_candidate"},
    {"name": "policy_v3", "path": "data/processed_policy_v3/experiment_1/final/architecturev3_seed42/policy.pt",
     "sha256": "d874d196d9c2f1e12c6d697ad2de57883a29352976dbb1ee9dbd6ba63af84f82",
     "metrics": "data/processed_policy_v3/experiment_1/final/architecturev3_seed42/metrics.json",
     "supports_prepare": False, "role": "primary_candidate"},
    {"name": "prepare_v2_seed42", "path": "data/processed_policy_prepare_train_1/prepare_v2_seed42/policy.pt",
     "sha256": "a9dd7c1eee8c9f4bbe23b3447e4aa02b5f06019f421ad27e7240ab2ae3a89c9e",
     "metrics": "data/processed_policy_prepare_train_1/prepare_v2_seed42/metrics.json",
     "supports_prepare": True, "role": "primary_candidate"},
    {"name": "prepare_v3_seed42", "path": "data/processed_policy_prepare_train_1/prepare_v3_seed42/policy.pt",
     "sha256": "3541ac74840491491a5ae07a9d1be9ea068d61aaf158ad6016d8b3fab7680d12",
     "metrics": "data/processed_policy_prepare_train_1/prepare_v3_seed42/metrics.json",
     "supports_prepare": True, "role": "primary_candidate"},
    {"name": "control_v2_seed42", "path": "data/processed_policy_prepare_train_1/control_v2_seed42/policy.pt",
     "sha256": "4671710a50b3f13fbde2bbbee39f5c51b1abfc2f3e2c53a16b92f55c4d46aaf0",
     "metrics": "data/processed_policy_prepare_train_1/control_v2_seed42/metrics.json",
     "supports_prepare": False, "role": "prepare_ablation_control"},
    {"name": "control_v3_seed42", "path": "data/processed_policy_prepare_train_1/control_v3_seed42/policy.pt",
     "sha256": "314232188cc042e837de81ae7865c5d3d1fc0896dc8978ce681fcf25dcc26d7a",
     "metrics": "data/processed_policy_prepare_train_1/control_v3_seed42/metrics.json",
     "supports_prepare": False, "role": "prepare_ablation_control"},
)

PRIMARY_NAMES = ("frozen_v2", "retrained_v2", "policy_v3", "prepare_v2_seed42", "prepare_v3_seed42")
PREPARE_NAMES = ("prepare_v2_seed42", "prepare_v3_seed42")
NO_PREPARE_NAMES = tuple(m["name"] for m in MODELS)
METRIC_NAMES = ("cross_entropy", "top1", "top3", "mrr")
BOOTSTRAP_DRAWS = 5000
BOOTSTRAP_SEED = 20261018
CONFIDENCE_EXAMPLE_THRESHOLD = 0.60
SCORER_MAJOR_GAP = 3.0


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


def _decision_key(row: dict) -> tuple[str, int, str]:
    return row["match_id"], int(row["options_id"]), row["state_hash"]


def _decision_id_parts(row: dict) -> tuple[str, int, str] | None:
    parts = str(row.get("decision_id", "")).split(":")
    if len(parts) != 4:
        return None
    try:
        if parts[0] != row.get("match_id") or parts[3] != row.get("state_hash"):
            return None
        return parts[0], int(parts[2]), parts[3]
    except (TypeError, ValueError):
        return None


def _load_history(heldout: set[str]) -> tuple[dict[str, set[str]], dict[str, dict]]:
    """Collect match IDs from locked splits, use registry and every fixed checkpoint."""
    plan = _read_json(ROOT / SPLIT_PLAN)
    history: dict[str, set[str]] = defaultdict(set)
    for part in ("train", "validation", "test_seen"):
        for match_id in plan.get("parts", {}).get(part, []):
            if match_id not in heldout:
                history[match_id].add(f"prepare_data:{part}")
    registry = _read_json(ROOT / USAGE_REGISTRY)
    for entry in registry.get("entries", []):
        if not isinstance(entry, dict):
            continue
        match_id = entry.get("match_id")
        # For protected matches the split-plan ID is the only information used.
        if match_id in heldout:
            continue
        if entry.get("status") == "TRAINED_OR_SELECTED":
            history[match_id].add("usage_registry:trained_or_selected")
        elif entry.get("status") == "EVALUATED_ONLY":
            history[match_id].add("usage_registry:evaluated_only")
    model_metadata = {}
    for spec in MODELS:
        path = ROOT / spec["path"]
        data = path.read_bytes()
        digest = _sha256_bytes(data)
        if digest != spec["sha256"]:
            raise ValueError(f"checkpoint SHA-256 mismatch: {spec['name']}")
        metrics_path = ROOT / spec["metrics"]
        metrics = _read_json(metrics_path)
        if metrics.get("checkpoint_sha256") != digest:
            raise ValueError(f"metrics/checkpoint identity mismatch: {spec['name']}")
        _, _, payload = load_policy_checkpoint(io.BytesIO(data), device="cpu", allow_prepare=True)
        groups = payload.get("experiment", {}).get("split", {}).get("game_ids", {})
        for part, match_ids in groups.items():
            # The reserved fresh_holdout part is never read from a checkpoint.
            if part == "fresh_holdout" or not isinstance(match_ids, list):
                continue
            for match_id in match_ids:
                if match_id not in heldout:
                    history[match_id].add(f"checkpoint:{spec['name']}:{part}")
        model_metadata[spec["name"]] = {
            "path": spec["path"], "sha256": digest, "metrics_path": spec["metrics"],
            "metrics_sha256": sha256_file(metrics_path), "supports_prepare": spec["supports_prepare"],
            "role": spec["role"], "architecture": metrics.get("architecture"),
            "label": metrics.get("label"), "selected_epoch": metrics.get("selected_epoch"),
            "split_sha256": metrics.get("split_sha256"),
        }
    return history, model_metadata


def _load_shadow_rows(prefixes: set[str], heldout: set[str]) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Read only rows whose match key is in the candidate set; heldout rows are skipped by ID first."""
    live = ROOT / "data/raw/live"
    prediction_paths = [p for p in live.glob("prediction_journal*.jsonl")
                        if ".outcome_shadow" not in p.name and ".strategy_shadow" not in p.name
                        and ".model_shadow" not in p.name]
    sources = {
        "prediction": sorted(prediction_paths),
        "outcome": sorted(live.glob("prediction_journal.outcome_shadow*.jsonl")),
        "strategy": sorted(live.glob("prediction_journal.strategy_shadow*.jsonl")),
    }
    rows: dict[str, list[dict]] = {name: [] for name in sources}
    fingerprints: dict[str, list[str]] = defaultdict(list)
    for kind, paths in sources.items():
        for path in paths:
            if not path.is_file():
                continue
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    # Exclude protected lines before JSON parsing or inspecting their fields.
                    if any(match_id in line for match_id in heldout):
                        continue
                    if not any(f'"match_id":"{prefix}' in line for prefix in prefixes):
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    match_id = row.get("match_id", "")
                    if not any(match_id.startswith(prefix) for prefix in prefixes):
                        continue
                    rows[kind].append(row)
                    fingerprint_key = f"{kind}:{path.name}:{match_id[:16]}"
                    fingerprints[fingerprint_key].append(canonical_json(row))
    return rows, {name: _sha256_bytes("\n".join(sorted(values)).encode("utf-8"))
                  for name, values in sorted(fingerprints.items())}


def _journal_signature(kind: str, row: dict) -> str:
    if kind == "prediction":
        value = {"event": row.get("event"), "checkpoint_sha256": row.get("checkpoint_sha256"),
                 "top3": row.get("top3")}
    elif kind == "strategy":
        value = {k: row.get(k) for k in ("schema", "scorer", "params", "forecaster_rev", "texts_sha256",
                                         "context", "complete", "menu_size", "top3", "actions")}
    else:
        value = {k: row.get(k) for k in ("schema", "forecaster_rev", "texts_sha256", "context",
                                         "complete", "menu_size", "actions")}
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _group_shadows(rows: dict[str, list[dict]]) -> dict[str, dict[tuple, list[dict]]]:
    groups: dict[str, dict[tuple, list[dict]]] = {kind: defaultdict(list) for kind in rows}
    expected = {"prediction": {"RECOMMENDATION"}, "strategy": {"STRATEGY_SHADOW"},
                "outcome": {"OUTCOME_SHADOW"}}
    for kind, values in rows.items():
        for row in values:
            if row.get("event") not in expected[kind]:
                continue
            key = _decision_id_parts(row)
            if key is None:
                try:
                    key = _decision_key(row)
                except (KeyError, TypeError, ValueError):
                    continue
            groups[kind][key].append(row)
    return groups


def _one_record(group: list[dict], kind: str) -> tuple[dict | None, str | None]:
    if not group:
        return None, f"NO_{kind.upper()}_ROW"
    signatures = {_journal_signature(kind, row) for row in group}
    if len(signatures) != 1:
        return None, f"CONFLICTING_{kind.upper()}_ROWS"
    return group[0], None


def _match_menu_actions(row: dict, actions: list[dict]) -> bool:
    try:
        size = int(row["menu_size"])
        indexed = {int(item["index"]): item["action"] for item in row["actions"]}
        return (size == len(actions) and len(indexed) == size and set(indexed) == set(range(size))
                and [indexed[i] for i in range(size)] == [action_digest(action) for action in actions])
    except (KeyError, TypeError, ValueError):
        return False


def _find_live_snapshots(match_id: str) -> list[Path]:
    return sorted((ROOT / "data/raw/live").glob(f"Hearthstone_*/{match_id[:16]}/snapshots.jsonl"))


def _snapshot_keys(paths: list[Path], match_id: str) -> tuple[set[tuple], Counter, dict[str, str]]:
    found: set[tuple] = set()
    counts: Counter = Counter()
    fingerprints: dict[str, str] = {}
    for path in paths:
        fingerprints[str(path.relative_to(ROOT))] = sha256_file(path)
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("game_key") != match_id:
                    continue
                decision = row.get("decision", {})
                try:
                    key = (match_id, int(decision["options_id"]), row["state_hash"])
                except (KeyError, TypeError, ValueError):
                    continue
                if decision.get("kind") == "MAIN_ACTION":
                    found.add(key)
                    counts[key] += 1
    return found, counts, fingerprints


def _load_match_rows(path: Path, catalog: CardCatalog, *, prepare_actions: bool = True) -> tuple[list[dict], dict]:
    lines = read_complete_lines(path)
    segments = split_games(lines)
    if len(segments) != 1:
        raise PolicyImportError("EXPECTED_ONE_MATCH")
    return extract_match(segments[0], catalog, prepare_actions=prepare_actions)


def _inventory_and_pair() -> tuple[dict, list[dict]]:
    plan = _read_json(ROOT / SPLIT_PLAN)
    heldout = set(plan.get("parts", {}).get("fresh_holdout", []))
    if len(heldout) != 9:
        raise ValueError("expected nine protected fresh_holdout IDs in split plan")
    history, model_metadata = _load_history(heldout)
    raw_root = ROOT / "data/raw/collected"
    raw_files = sorted(raw_root.glob("*.log"))
    live_dirs = [d for session in (ROOT / "data/raw/live").glob("Hearthstone_*") if session.is_dir()
                 for d in session.iterdir() if d.is_dir()]
    keyed: list[Path] = []
    inventory: list[dict] = []
    prefix_sources: dict[str, set[str]] = defaultdict(set)
    for match_id, sources in history.items():
        prefix_sources[match_id[:16]].update(sources)
    for path in raw_files:
        is_key = len(path.stem) == 16 and all(c in "0123456789abcdef" for c in path.stem.lower())
        if not is_key:
            inventory.append({"source": str(path.relative_to(ROOT)), "category": "UNVERIFIED",
                              "reason": "LEGACY_FILENAME_WITHOUT_MATCH_KEY"})
            continue
        if any(match_id.startswith(path.stem) for match_id in heldout):
            inventory.append({"source": str(path.relative_to(ROOT)), "category": "PREVIOUSLY_USED",
                              "reason": "PROTECTED_FRESH_HOLDOUT_ID_ONLY"})
            continue
        collisions = [match_id for match_id in history if match_id.startswith(path.stem)]
        if collisions:
            inventory.append({"source": str(path.relative_to(ROOT)), "category": "PREVIOUSLY_USED",
                              "reason": "MATCH_ID_IN_PRIOR_SPLIT_OR_EVALUATION",
                              "usage_sources": sorted({s for match_id in collisions for s in history[match_id]})})
            continue
        keyed.append(path)

    # Collector pending slices are counted by file name only and never treated as complete.
    pending_files = [p for p in (raw_root / ".pending").rglob("*") if p.is_file() and p.suffix.lower() == ".log"]
    for path in pending_files:
        if any(match_id.startswith(path.stem) for match_id in heldout):
            continue
        inventory.append({"source": str(path.relative_to(ROOT)), "category": "INCOMPLETE",
                          "reason": "COLLECTOR_PENDING_SLICE"})

    prefixes = {path.stem for path in keyed}
    collected_prefixes = {p.stem for p in raw_files if len(p.stem) == 16}
    live_only = sorted({d.name for d in live_dirs if d.name not in collected_prefixes
                        and not any(match_id.startswith(d.name) for match_id in heldout)})
    shadow_rows, journal_fingerprints_all = _load_shadow_rows(prefixes | set(live_only), heldout)
    journal_fingerprints = {key: value for key, value in journal_fingerprints_all.items()
                            if key.rsplit(":", 1)[-1] in prefixes}
    journal_groups = _group_shadows(shadow_rows)
    catalog = CardCatalog.from_json(ROOT / CARDS)
    matched_rows: list[dict] = []
    duplicate_ids: dict[str, str] = {}
    parsed_summaries = []
    source_fingerprints: dict[str, str] = {}
    live_snapshot_fingerprints: dict[str, str] = {}
    decision_exclusions: Counter = Counter()
    prepare_menu_exclusions: Counter = Counter()
    importer_skip_reasons: Counter = Counter()
    prepare_menu_imported = 0
    prepare_menu_live_matched = 0
    prepare_chosen_live_matched = 0
    match_records = []

    for path in keyed:
        source = str(path.relative_to(ROOT))
        source_fingerprints[source] = sha256_file(path)
        try:
            examples, summary = _load_match_rows(path, catalog)
        except PolicyImportError as error:
            category = "INCOMPLETE" if error.reason == "INCOMPLETE" else "IMPORT_FAILED"
            inventory.append({"source": source, "category": category, "reason": error.reason})
            match_records.append({"match_id_prefix": path.stem, "category": category, "reason": error.reason})
            continue
        except Exception as error:  # privacy: keep error type only
            inventory.append({"source": source, "category": "IMPORT_FAILED", "reason": type(error).__name__})
            match_records.append({"match_id_prefix": path.stem, "category": "IMPORT_FAILED",
                                 "reason": type(error).__name__})
            continue
        match_id = summary["game_id"]
        if not match_id.startswith(path.stem):
            inventory.append({"source": source, "category": "UNVERIFIED", "reason": "FILENAME_ID_MISMATCH"})
            match_records.append({"match_id_prefix": path.stem, "category": "UNVERIFIED",
                                 "reason": "FILENAME_ID_MISMATCH"})
            continue
        if match_id in history:
            inventory.append({"source": source, "category": "PREVIOUSLY_USED",
                              "reason": "EXACT_MATCH_ID_IN_PRIOR_SPLIT_OR_EVALUATION",
                              "usage_sources": sorted(history[match_id])})
            match_records.append({"match_id_prefix": match_id[:16], "category": "PREVIOUSLY_USED",
                                 "reason": "EXACT_MATCH_ID_IN_PRIOR_SPLIT_OR_EVALUATION"})
            continue
        if match_id in duplicate_ids:
            inventory.append({"source": source, "category": "PREVIOUSLY_USED", "reason": "DUPLICATE_RAW_MATCH"})
            match_records.append({"match_id_prefix": match_id[:16], "category": "PREVIOUSLY_USED",
                                 "reason": "DUPLICATE_RAW_MATCH"})
            continue
        duplicate_ids[match_id] = source
        importer_skip_reasons.update(summary["skip_reasons"])
        for example in examples:
            validate_example(example, allow_prepare=True)
        snapshots = _find_live_snapshots(match_id)
        snapshot_keys, snapshot_counts, snapshot_hashes = _snapshot_keys(snapshots, match_id)
        live_snapshot_fingerprints.update(snapshot_hashes)
        paired = 0
        per_match_exclusions: Counter = Counter()
        per_match_prepare_exclusions: Counter = Counter()
        prepared = 0
        chosen_prepare = 0
        prepare_menu_imported += sum(any(action["type"] == "PREPARE_CARD" for action in example["legal_actions"])
                                     for example in examples)
        for example in examples:
            prepared_here = any(action["type"] == "PREPARE_CARD" for action in example["legal_actions"])

            def exclude_decision(reason: str) -> None:
                per_match_exclusions[reason] += 1
                if prepared_here:
                    per_match_prepare_exclusions[reason] += 1

            option = int(example["decision_id"].rsplit(":", 1)[1])
            key = (match_id, option, example["provenance"]["state_hash"])
            if key not in snapshot_keys:
                exclude_decision("LIVE_SNAPSHOT_NOT_MATCHED")
                continue
            if snapshot_counts[key] != 1:
                exclude_decision("DUPLICATE_LIVE_SNAPSHOT")
                continue
            recommendation, reason = _one_record(journal_groups["prediction"].get(key, []), "prediction")
            if reason:
                exclude_decision(reason)
                continue
            if recommendation.get("checkpoint_sha256") != MODELS[0]["sha256"]:
                exclude_decision("LIVE_CHECKPOINT_MISMATCH")
                continue
            action_by_json = {canonical_json(action): i for i, action in enumerate(example["legal_actions"])}
            try:
                top3 = recommendation["top3"]
                if not top3 or any(canonical_json(item["action"]) not in action_by_json for item in top3):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                exclude_decision("LIVE_RECOMMENDATION_MENU_MISMATCH")
                continue
            strategy, reason = _one_record(journal_groups["strategy"].get(key, []), "strategy")
            if reason:
                exclude_decision(reason)
                continue
            outcome, reason = _one_record(journal_groups["outcome"].get(key, []), "outcome")
            if reason:
                exclude_decision(reason)
                continue
            if not _match_menu_actions(strategy, example["legal_actions"]):
                exclude_decision("STRATEGY_MENU_MISMATCH")
                continue
            if not _match_menu_actions(outcome, example["legal_actions"]):
                exclude_decision("OUTCOME_MENU_MISMATCH")
                continue
            prepared += int(prepared_here)
            chosen_prepare += int(example["legal_actions"][example["chosen_action_index"]]["type"] == "PREPARE_CARD")
            prepare_menu_live_matched += int(prepared_here)
            prepare_chosen_live_matched += int(example["legal_actions"][example["chosen_action_index"]]["type"] == "PREPARE_CARD")
            paired += 1
            matched_rows.append({"example": example, "recommendation": recommendation,
                                 "strategy": strategy, "outcome": outcome})
        decision_exclusions.update(per_match_exclusions)
        prepare_menu_exclusions.update(per_match_prepare_exclusions)
        category = "NEW_ELIGIBLE" if paired else "UNVERIFIED"
        reason = None if paired else "NO_DECISION_WITH_EXACT_LIVE_MENU_JOIN"
        inventory.append({"source": source, "category": category, "reason": reason,
                          "matches": 1, "imported_decisions": len(examples), "decisions_total": summary["decisions_total"],
                          "decisions_skipped_by_importer": summary["decisions_skipped"],
                          "decisions_live_matched": paired, "decision_exclusions": dict(sorted(per_match_exclusions.items())),
                          "prepare_menus_live_matched": prepared, "prepare_chosen_live_matched": chosen_prepare,
                          "raw_sha256": source_fingerprints[source], "live_snapshot_files": len(snapshots),
                          "snapshot_event_count": sum(snapshot_counts.values())})
        match_records.append({"match_id_prefix": match_id[:16], "category": category, "reason": reason,
                              "imported_decisions": len(examples), "decisions_total": summary["decisions_total"],
                              "decisions_live_matched": paired,
                              "decision_exclusions": dict(sorted(per_match_exclusions.items())),
                              "prepare_menus": prepared, "prepare_chosen": chosen_prepare})
        parsed_summaries.append({"match_id": match_id, "summary": summary})

    # One uncollected LIVE-only recording predates this evaluation set and has prior recommendations/outcome rows.
    # It is counted by ID as previously observed; the slice and state data are not opened.
    live_only_prior = []
    for prefix in live_only:
        if any(match_id.startswith(prefix) for match_id in history):
            category, reason = "PREVIOUSLY_USED", "ID_IN_PRIOR_SPLIT_OR_EVALUATION"
        else:
            # The event journals are filtered by this exact non-protected ID and only event counts are retained.
            observed = Counter()
            for kind, rows in shadow_rows.items():
                for row in rows:
                    if row.get("match_id", "").startswith(prefix):
                        observed[row.get("event", "?")] += 1
            category, reason = (("PREVIOUSLY_USED", "PRE_EXISTING_LIVE_OBSERVATION") if observed
                                else ("UNVERIFIED", "LIVE_ONLY_NO_MATCHED_COLLECTED_LOG"))
        live_only_prior.append({"match_id_prefix": prefix, "category": category, "reason": reason})
        inventory.append({"source": f"data/raw/live/Hearthstone_*/{prefix}", "category": category,
                          "reason": reason, "raw_collected_match": False})

    eligible_ids = sorted({item["example"]["game_id"] for item in matched_rows})
    eligible_decision_ids = sorted(item["example"]["decision_id"] for item in matched_rows)
    if len(eligible_decision_ids) != len(set(eligible_decision_ids)):
        raise ValueError("duplicate decision IDs in exact LIVE join")
    prepare_decisions = [item for item in matched_rows
                         if any(a["type"] == "PREPARE_CARD" for a in item["example"]["legal_actions"])]
    source_code_sha = sha256_file(ROOT / "scripts/new_matches_eval_1.py")
    split_sha = sha256_file(ROOT / SPLIT_PLAN)
    catalog_sha = sha256_file(ROOT / CARDS)
    dataset_payload = {
        "matches": eligible_ids, "decision_ids": eligible_decision_ids,
        "raw_sha256": source_fingerprints, "live_snapshot_sha256": live_snapshot_fingerprints,
        "shadow_rows_sha256": journal_fingerprints, "split_sha256": split_sha, "catalog_sha256": catalog_sha,
    }
    dataset_identity = _sha256_bytes(canonical_json(dataset_payload).encode("utf-8"))
    protocol = {
        "schema": "manamind.new_matches_eval_1/private_protocol/1", "status": "PROTOCOL_LOCKED",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_commit": _git_head(),
        "source_code_sha256": source_code_sha, "dataset_identity_sha256": dataset_identity,
        "inputs": {"split_plan": str(SPLIT_PLAN), "split_plan_sha256": split_sha,
                   "catalog": str(CARDS), "catalog_sha256": catalog_sha,
                   "raw_log_sha256": source_fingerprints,
                   "live_snapshot_sha256": live_snapshot_fingerprints,
                   "candidate_shadow_rows_sha256": journal_fingerprints},
        "protected_fresh_holdout": {"count": len(heldout), "ids": sorted(heldout),
                                    "opened": False, "inference_run": False},
        "inventory": {"raw_collected_log_files": len(raw_files),
                      "keyed_collected_match_logs": sum(len(p.stem) == 16 for p in raw_files),
                      "legacy_filename_logs": sum(len(p.stem) != 16 for p in raw_files),
                      "protected_raw_log_prefixes_skipped": sum(
                          1 for p in raw_files if len(p.stem) == 16 and any(g.startswith(p.stem) for g in heldout)),
                      "new_nonoverlap_raw_candidates": len(keyed),
                      "completed_matches_imported": len(parsed_summaries),
                      "new_eligible_matches": len(eligible_ids),
                      "new_eligible_decisions": len(eligible_decision_ids),
                      "prepare_decisions": len(prepare_decisions),
                      "prepare_chosen": sum(item["example"]["legal_actions"][item["example"]["chosen_action_index"]]["type"] == "PREPARE_CARD"
                                             for item in prepare_decisions),
                      "prepare_menu_decisions_imported": prepare_menu_imported,
                      "prepare_menu_decisions_live_matched": prepare_menu_live_matched,
                      "prepare_chosen_live_matched": prepare_chosen_live_matched,
                      "prepare_menu_decision_exclusions": dict(sorted(prepare_menu_exclusions.items())),
                      "collector_pending_logs": len(pending_files),
                      "live_recording_directories_nonprotected": sum(
                          not any(match_id.startswith(d.name) for match_id in heldout) for d in live_dirs),
                      "importer_skip_reasons": dict(sorted(importer_skip_reasons.items())),
                      "decision_exclusions": dict(sorted(decision_exclusions.items())),
                      "live_only_records": live_only_prior},
        "matches": sorted(match_records, key=lambda row: row["match_id_prefix"]),
        "source_inventory": inventory,
        "eligible_match_ids": eligible_ids, "eligible_decision_ids": eligible_decision_ids,
        "models": model_metadata,
        "protocol": {
            "hypothesis": "Retrained Policy v2/v3 and Prepare-aware policies may better imitate recorded player actions than Frozen Policy v2 on new non-overlapping games.",
            "baseline": "frozen_v2",
            "primary_candidates": list(PRIMARY_NAMES),
            "prepare_controls": ["control_v2_seed42", "control_v3_seed42"],
            "main_comparison": "All seven fixed seed-42 checkpoints score the same exactly joined decisions without PREPARE_CARD; only Prepare v2/v3 score menus containing PREPARE_CARD.",
            "prepare_semantics": "Prepare models are loaded with allow_prepare=True. Older and control models are never scored on PREPARE_CARD menus.",
            "metrics": list(METRIC_NAMES) + ["uniform_random_baseline", "mean_and_spread_across_matches"],
            "top3_rule": "Only menus with at least three legal actions enter the Top-3 denominator.",
            "pairing": "Same game_id, options_id, state_hash, state snapshot, full ordered action digests in both Strategy and Outcome Shadow, and a Frozen v2 RECOMMENDATION row with legal Top-3 actions.",
            "live_prepare_actions_enabled": False,
            "prepare_menu_rule": "Evaluate a PREPARE_CARD menu only if the complete schema-2 menu exactly matches both LIVE shadow menus; otherwise exclude it with a reason.",
            "uncertainty": {"method": "paired nonparametric bootstrap resampling whole matches", "draws": BOOTSTRAP_DRAWS,
                            "seed": BOOTSTRAP_SEED},
            "confidence_examples_threshold": CONFIDENCE_EXAMPLE_THRESHOLD,
            "strategy_scorer_gap_threshold": SCORER_MAJOR_GAP,
            "model_selection_on_new_data": False,
            "training_or_finetuning": False,
        },
    }
    return protocol, matched_rows


def _write_new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _write_new_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(canonical_json(row) + "\n")


def _public_protocol(protocol: dict) -> dict:
    inventory = protocol["inventory"]
    excluded = Counter(row["category"] for row in protocol["source_inventory"])
    exclusion_reasons = Counter(row.get("reason", "UNSPECIFIED") for row in protocol["source_inventory"]
                                if row["category"] != "NEW_ELIGIBLE" and row.get("reason"))
    # Per-match opaque IDs stay private; the public report contains counts only.
    return {
        "schema": "manamind.new_matches_eval_1/results/1", "status": "PROTOCOL_LOCKED",
        "data_identity_sha256": protocol["dataset_identity_sha256"],
        "source_commit": protocol["source_commit"], "source_code_sha256": protocol["source_code_sha256"],
        "split_plan_sha256": protocol["inputs"]["split_plan_sha256"],
        "inventory": {k: inventory[k] for k in ("raw_collected_log_files", "keyed_collected_match_logs",
                      "legacy_filename_logs", "protected_raw_log_prefixes_skipped", "new_nonoverlap_raw_candidates",
                      "completed_matches_imported", "new_eligible_matches", "new_eligible_decisions",
                      "prepare_decisions", "prepare_chosen", "prepare_menu_decisions_imported",
                      "prepare_menu_decisions_live_matched", "prepare_chosen_live_matched",
                      "prepare_menu_decision_exclusions", "collector_pending_logs",
                      "live_recording_directories_nonprotected", "importer_skip_reasons",
                      "decision_exclusions")},
        "match_categories": dict(sorted(excluded.items())),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "protected_fresh_holdout": {"count": 9, "opened": False, "inference_run": False},
        "models": protocol["models"], "protocol": protocol["protocol"],
        "metrics": None, "strategic_analysis": None, "conclusion": "NOT_YET_EVALUATED",
    }


def _verify_locked_dataset(protocol: dict, heldout: set[str]) -> None:
    inputs = protocol["inputs"]
    if sha256_file(ROOT / SPLIT_PLAN) != inputs["split_plan_sha256"]:
        raise ValueError("split plan changed after protocol lock")
    if sha256_file(ROOT / CARDS) != inputs["catalog_sha256"]:
        raise ValueError("card catalog changed after protocol lock")
    for relative, digest in inputs["raw_log_sha256"].items():
        if sha256_file(ROOT / relative) != digest:
            raise ValueError("candidate Power.log changed after protocol lock")
    for relative, digest in inputs["live_snapshot_sha256"].items():
        if sha256_file(ROOT / relative) != digest:
            raise ValueError("candidate LIVE snapshots changed after protocol lock")
    prefixes = {Path(path).stem for path in inputs["raw_log_sha256"]}
    _, all_fingerprints = _load_shadow_rows(prefixes, heldout)
    current_fingerprints = {key: value for key, value in all_fingerprints.items()
                            if key.rsplit(":", 1)[-1] in prefixes}
    if current_fingerprints != inputs["candidate_shadow_rows_sha256"]:
        raise ValueError("candidate LIVE shadow rows changed after protocol lock")
    identity = _sha256_bytes(canonical_json({
        "matches": protocol["eligible_match_ids"],
        "decision_ids": protocol["eligible_decision_ids"],
        "raw_sha256": inputs["raw_log_sha256"],
        "live_snapshot_sha256": inputs["live_snapshot_sha256"],
        "shadow_rows_sha256": inputs["candidate_shadow_rows_sha256"],
        "split_sha256": inputs["split_plan_sha256"],
        "catalog_sha256": inputs["catalog_sha256"],
    }).encode("utf-8"))
    if identity != protocol["dataset_identity_sha256"]:
        raise ValueError("locked dataset identity does not match its inputs")


def _read_private_inputs() -> tuple[dict, list[dict]]:
    protocol = _read_json(ROOT / PRIVATE_PROTOCOL)
    if protocol.get("source_code_sha256") != sha256_file(ROOT / "scripts/new_matches_eval_1.py"):
        raise ValueError("evaluation script changed after protocol lock")
    if protocol.get("dataset_identity_sha256") is None:
        raise ValueError("missing locked dataset identity")
    split = _read_json(ROOT / SPLIT_PLAN)
    heldout = set(split.get("parts", {}).get("fresh_holdout", []))
    if len(heldout) != 9 or sorted(heldout) != protocol["protected_fresh_holdout"].get("ids"):
        raise ValueError("protected fresh_holdout IDs changed after protocol lock")
    _verify_locked_dataset(protocol, heldout)
    if sha256_file(ROOT / PRIVATE_DECISIONS) != protocol.get("private_decisions_sha256"):
        raise ValueError("private decision data differs from the locked protocol")
    rows = [json.loads(line) for line in (ROOT / PRIVATE_DECISIONS).read_text(encoding="utf-8").splitlines() if line.strip()]
    if sorted(r["example"]["decision_id"] for r in rows) != protocol["eligible_decision_ids"]:
        raise ValueError("private decision IDs differ from the locked protocol")
    if any(row["example"]["game_id"] in heldout for row in rows):
        raise ValueError("protected fresh_holdout data is present in the evaluation inputs")
    for spec in MODELS:
        if sha256_file(ROOT / spec["path"]) != spec["sha256"]:
            raise ValueError(f"checkpoint changed after protocol lock: {spec['name']}")
    return protocol, rows


def _model_logits(spec: dict, rows: list[dict]) -> dict[str, list[float]]:
    checkpoint = (ROOT / spec["path"]).read_bytes()
    policy, encoder, _ = load_policy_checkpoint(io.BytesIO(checkpoint), device="cpu", allow_prepare=True)
    representation = representation_of(policy)
    scores: dict[str, list[float]] = {}
    with torch.inference_mode():
        for row in rows:
            actions = row["legal_actions"]
            if any(action["type"] == "PREPARE_CARD" for action in actions) and not spec["supports_prepare"]:
                continue
            inputs = encode_example(row, encoder, representation=representation, allow_prepare=True)
            if len(inputs[3]) != len(actions):
                raise ValueError(f"encoded menu length mismatch for {spec['name']}")
            values = policy(*inputs)
            if values.ndim != 1 or values.shape[0] != len(actions) or not torch.isfinite(values).all():
                raise ValueError(f"invalid logits for {spec['name']}")
            scores[row["decision_id"]] = [float(value) for value in values.tolist()]
    return scores


def _record(logits: list[float], chosen: int, menu_size: int) -> dict:
    if not logits or not 0 <= chosen < len(logits) or len(logits) != menu_size:
        raise ValueError("logit/menu/chosen-index mismatch")
    order = sorted(range(len(logits)), key=lambda index: (-logits[index], index))
    shifted = [value - max(logits) for value in logits]
    log_z = math.log(sum(math.exp(value) for value in shifted))
    probabilities = [math.exp(value - log_z) for value in shifted]
    rank = order.index(chosen) + 1
    return {"cross_entropy": log_z - shifted[chosen], "top1": rank == 1,
            "top3": rank <= 3 if menu_size >= 3 else None, "mrr": 1.0 / rank,
            "rank": rank, "top_index": order[0], "top_probability": probabilities[order[0]],
            "predicted_type": None, "chosen_index": chosen}


def _metric_stats(records: list[dict], menu_sizes: list[int]) -> dict:
    if not records:
        return {"decisions": 0, "matches": 0, "metrics": None, "mean_across_matches": None}
    top3 = [(bool(row["top3"]), size) for row, size in zip(records, menu_sizes) if size >= 3]
    metrics = {
        "cross_entropy": float(np.mean([row["cross_entropy"] for row in records])),
        "top1": float(np.mean([row["top1"] for row in records])),
        "top3": float(np.mean([hit for hit, _ in top3])) if top3 else None,
        "top3_decisions": len(top3), "mrr": float(np.mean([row["mrr"] for row in records])),
        "uniform_random": {
            "cross_entropy": float(np.mean([math.log(size) for size in menu_sizes])),
            "top1": float(np.mean([1 / size for size in menu_sizes])),
            "top3": float(np.mean([min(3, size) / size for size in menu_sizes if size >= 3])) if top3 else None,
            "mrr": float(np.mean([sum(1 / rank for rank in range(1, size + 1)) / size for size in menu_sizes])),
        },
    }
    groups: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(records):
        groups[row["game_id"]].append(i)
    per_metric: dict[str, list[float]] = defaultdict(list)
    for game_id, indices in sorted(groups.items()):
        sub = [records[i] for i in indices]
        sizes = [menu_sizes[i] for i in indices]
        top3_sub = [r["top3"] for r, size in zip(sub, sizes) if size >= 3]
        m = {"decisions": len(indices), "cross_entropy": float(np.mean([r["cross_entropy"] for r in sub])),
             "top1": float(np.mean([r["top1"] for r in sub])),
             "top3": float(np.mean(top3_sub)) if top3_sub else None,
             "mrr": float(np.mean([r["mrr"] for r in sub]))}
        for name in METRIC_NAMES:
            if m[name] is not None:
                per_metric[name].append(m[name])
    mean_spread = {name: {"mean": float(np.mean(values)), "std": float(np.std(values)),
                          "min": float(np.min(values)), "max": float(np.max(values)),
                          "matches": len(values)} for name, values in per_metric.items()}
    return {"decisions": len(records), "matches": len(groups), "metrics": metrics,
            "mean_across_matches": mean_spread}


def _paired_cluster_bootstrap(rows: list[dict], left: list[dict], right: list[dict], *,
                              seed: int = BOOTSTRAP_SEED, draws: int = BOOTSTRAP_DRAWS) -> dict:
    if not rows:
        return {"matches": 0, "decisions": 0, "metrics": {}}
    games = sorted({row["example"]["game_id"] for row in rows})
    indices_by_game = {game: [i for i, row in enumerate(rows) if row["example"]["game_id"] == game]
                       for game in games}
    menu_sizes = [len(row["example"]["legal_actions"]) for row in rows]
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(games), size=(draws, len(games)))
    out = {}
    for metric in METRIC_NAMES:
        if metric == "top3":
            keep = [i for i, size in enumerate(menu_sizes) if size >= 3]
        else:
            keep = list(range(len(rows)))
        if not keep:
            out[metric] = {"difference": None, "ci95": None}
            continue
        keep_set = set(keep)
        point = float(np.mean([left[i][metric] - right[i][metric] for i in keep]))
        values = []
        for draw in samples:
            selected = []
            for game_index in draw:
                selected.extend(i for i in indices_by_game[games[int(game_index)]] if i in keep_set)
            if selected:
                values.append(float(np.mean([left[i][metric] - right[i][metric] for i in selected])))
        out[metric] = {"difference": point,
                       "ci95": [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))] if values else None}
    return {"matches": len(games), "decisions": len(rows), "draws": draws, "seed": seed, "metrics": out}


def _menu_bucket(size: int) -> str:
    if size == 1:
        return "1"
    if size == 2:
        return "2"
    if size <= 5:
        return "3-5"
    if size <= 10:
        return "6-10"
    return "11+"


def _run_evaluation(protocol: dict, private_rows: list[dict]) -> tuple[dict, list[dict], dict]:
    examples = [item["example"] for item in private_rows]
    ids = [row["decision_id"] for row in examples]
    no_prepare_ids = {row["decision_id"] for row in examples
                      if not any(a["type"] == "PREPARE_CARD" for a in row["legal_actions"])}
    prepare_ids = set(ids) - no_prepare_ids
    logits_by_model: dict[str, dict[str, list[float]]] = {}
    for spec in MODELS:
        candidate_rows = examples if spec["supports_prepare"] else [row for row in examples if row["decision_id"] in no_prepare_ids]
        logits_by_model[spec["name"]] = _model_logits(spec, candidate_rows)
    record_by_model: dict[str, dict[str, dict]] = {}
    private_predictions = []
    rows_by_id = {row["decision_id"]: row for row in examples}
    for spec in MODELS:
        name = spec["name"]
        record_by_model[name] = {}
        for decision_id, logits in logits_by_model[name].items():
            example = rows_by_id[decision_id]
            record = _record(logits, example["chosen_action_index"], len(example["legal_actions"]))
            record["predicted_type"] = example["legal_actions"][record["top_index"]]["type"]
            record["chosen_type"] = example["legal_actions"][example["chosen_action_index"]]["type"]
            record["game_id"] = example["game_id"]
            record_by_model[name][decision_id] = record
    for item in private_rows:
        example = item["example"]
        private_predictions.append({**item, "model_scores": {
            name: {"logits": logits_by_model[name][example["decision_id"]],
                   **record_by_model[name][example["decision_id"]]}
            if example["decision_id"] in logits_by_model[name] else {"status": "NOT_COMPATIBLE_PREPARE_MENU"}
            for name in logits_by_model}})

    metric_sets: dict[str, list[str]] = {
        "ordinary_menus": list(NO_PREPARE_NAMES),
        "prepare_menus": list(PREPARE_NAMES),
        "all_menus_prepare_models_only": list(PREPARE_NAMES),
    }
    result_sets = {}
    for set_name, names in metric_sets.items():
        wanted = no_prepare_ids if set_name == "ordinary_menus" else prepare_ids if set_name == "prepare_menus" else set(ids)
        decision_rows = [row for row in examples if row["decision_id"] in wanted]
        result_sets[set_name] = {"decisions": len(decision_rows), "matches": len({r["game_id"] for r in decision_rows}),
                                 "models": {name: _metric_stats([record_by_model[name][r["decision_id"]]
                                     for r in decision_rows if r["decision_id"] in record_by_model[name]],
                                     [len(r["legal_actions"]) for r in decision_rows if r["decision_id"] in record_by_model[name]])
                                            for name in names}}
    comparisons = {}
    pairs = [("retrained_v2", "frozen_v2"), ("policy_v3", "frozen_v2"),
             ("prepare_v2_seed42", "frozen_v2"), ("prepare_v3_seed42", "frozen_v2"),
             ("prepare_v2_seed42", "control_v2_seed42"),
             ("prepare_v3_seed42", "control_v3_seed42"),
             ("prepare_v3_seed42", "prepare_v2_seed42")]
    for left_name, right_name in pairs:
        shared = no_prepare_ids & set(record_by_model[left_name]) & set(record_by_model[right_name])
        subset = [item for item in private_rows if item["example"]["decision_id"] in shared]
        left = [record_by_model[left_name][item["example"]["decision_id"]] for item in subset]
        right = [record_by_model[right_name][item["example"]["decision_id"]] for item in subset]
        comparisons[f"{left_name}_minus_{right_name}_ordinary"] = _paired_cluster_bootstrap(subset, left, right)
    prepare_comp = [item for item in private_rows if item["example"]["decision_id"] in prepare_ids]
    for left_name, right_name in (("prepare_v2_seed42", "prepare_v3_seed42"),):
        comparisons[f"{left_name}_minus_{right_name}_prepare_menus"] = _paired_cluster_bootstrap(
            prepare_comp, [record_by_model[left_name][x["example"]["decision_id"]] for x in prepare_comp],
            [record_by_model[right_name][x["example"]["decision_id"]] for x in prepare_comp])

    # Stratified descriptions use the recorded player action, hero class, turn and menu size.
    stratified: dict[str, dict] = {"by_chosen_action_type": {}, "by_self_class": {}, "by_phase": {}, "by_menu_size": {}}
    def group_report(label: str, predicate) -> dict:
        chosen = [row for row in examples if predicate(row)]
        return {"decisions": len(chosen), "matches": len({r["game_id"] for r in chosen}),
                "models": {name: _metric_stats([record_by_model[name][r["decision_id"]] for r in chosen
                            if r["decision_id"] in record_by_model[name]],
                            [len(r["legal_actions"]) for r in chosen if r["decision_id"] in record_by_model[name]])
                           for name in NO_PREPARE_NAMES if any(r["decision_id"] in record_by_model[name] for r in chosen)}}
    action_types = sorted({row["legal_actions"][row["chosen_action_index"]]["type"] for row in examples})
    for kind in action_types:
        stratified["by_chosen_action_type"][kind] = group_report(kind, lambda row, k=kind:
            row["legal_actions"][row["chosen_action_index"]]["type"] == k)
    classes = sorted({row["state"]["self_player"].get("player_class", "UNKNOWN") for row in examples})
    for player_class in classes:
        stratified["by_self_class"][player_class] = group_report(player_class, lambda row, c=player_class:
            row["state"]["self_player"].get("player_class", "UNKNOWN") == c)
    phase_rules = {"early_turns_1_5": lambda row: 1 <= row["state"].get("turn_number", 0) <= 5,
                   "mid_turns_6_10": lambda row: 6 <= row["state"].get("turn_number", 0) <= 10,
                   "late_turns_11_plus": lambda row: row["state"].get("turn_number", 0) >= 11}
    for phase, predicate in phase_rules.items():
        report = group_report(phase, predicate)
        report["status"] = "OK" if report["matches"] >= 3 else "INSUFFICIENT_MATCHES"
        stratified["by_phase"][phase] = report
    for bucket in ("1", "2", "3-5", "6-10", "11+"):
        stratified["by_menu_size"][bucket] = group_report(bucket, lambda row, b=bucket:
            _menu_bucket(len(row["legal_actions"])) == b)

    confusion = {name: dict() for name in NO_PREPARE_NAMES}
    for name in NO_PREPARE_NAMES:
        c = defaultdict(Counter)
        for row in examples:
            decision_id = row["decision_id"]
            if decision_id not in record_by_model[name]:
                continue
            actual = row["legal_actions"][row["chosen_action_index"]]["type"]
            predicted = record_by_model[name][decision_id]["predicted_type"]
            c[actual][predicted] += 1
        confusion[name] = {actual: dict(counts) for actual, counts in sorted(c.items())}

    scorer_summary = _strategy_and_outcome(private_rows, record_by_model)
    disagreements = _select_private_examples(private_rows, record_by_model, logits_by_model, scorer_summary)
    disagreements["strategy_analysis"] = scorer_summary.pop("per_decision")
    lethal_review = _review_exact_lethals(private_rows, record_by_model, logits_by_model,
                                          disagreements["private_examples"])
    disagreements["decision_review"] = lethal_review["private_rows"]
    n_matches = len({row["game_id"] for row in examples})
    prepare_matches = len({row["game_id"] for row in examples if row["decision_id"] in prepare_ids})
    prepare_chosen = sum(row["legal_actions"][row["chosen_action_index"]]["type"] == "PREPARE_CARD"
                         for row in examples if row["decision_id"] in prepare_ids)
    game_results = {row["game_id"]: row.get("final_result") for row in examples}
    game_outcomes = Counter({"win": 0, "loss": 0, "draw": 0})
    for outcome in game_results.values():
        game_outcomes["win" if outcome == 1.0 else "loss" if outcome == 0.0 else "draw"] += 1
    if n_matches < 25:
        imitation_verdict = "INSUFFICIENT_DATA"
    else:
        main = comparisons["retrained_v2_minus_frozen_v2_ordinary"]["metrics"]
        ce_ci = main.get("cross_entropy", {}).get("ci95")
        top1_ci = main.get("top1", {}).get("ci95")
        gain = bool(ce_ci and ce_ci[1] < 0 and top1_ci and top1_ci[0] > 0)
        regression = bool(ce_ci and ce_ci[0] > 0)
        imitation_verdict = "EVIDENCE_FOR_IMPROVEMENT" if gain else "REGRESSION" if regression else "NO_CLEAR_WINNER"
    prepare_verdict = "INSUFFICIENT_DATA" if prepare_chosen < 20 else "DESCRIPTIVE_ONLY"
    report = {
        "schema": "manamind.new_matches_eval_1/results/1", "status": "COMPLETE",
        "data_identity_sha256": protocol["dataset_identity_sha256"],
        "source_commit": protocol["source_commit"], "source_code_sha256": protocol["source_code_sha256"],
        "split_plan_sha256": protocol["inputs"]["split_plan_sha256"],
        "inventory": _public_protocol(protocol)["inventory"],
        "match_categories": _public_protocol(protocol)["match_categories"],
        "exclusion_reasons": _public_protocol(protocol)["exclusion_reasons"],
        "protected_fresh_holdout": {"count": 9, "opened": False, "inference_run": False},
        "models": protocol["models"], "protocol": protocol["protocol"],
        "evaluation_sets": result_sets, "paired_comparisons": comparisons,
        "stratified_metrics": stratified, "action_type_confusion": confusion,
        "game_outcomes": {"matches": len(game_results), "counts": dict(game_outcomes),
                          "note": "Observed game results are descriptive and are not attributed to a checkpoint."},
        "technical_correctness": {"all_included_rows_passed_policy_validation": True,
                                   "live_full_menu_reconciled_against_strategy_and_outcome_shadow": True,
                                   "logit_count_matches_menu_and_values_are_finite": True,
                                   "model_decisions_scored": {name: len(values) for name, values in logits_by_model.items()},
                                   "checkpoints_unchanged_after_inference": True},
        "strategy_outcome": scorer_summary, "outcome_decision_review": lethal_review["summary"],
        "interesting_disagreements": disagreements["public_summary"],
        "conclusion": {
            "imitation_verdict": imitation_verdict,
            "prepare_out_of_corpus_verdict": prepare_verdict,
            "strategic_quality": "NOT_ESTABLISHED",
            "eligible_matches": n_matches, "eligible_decisions": len(examples),
            "prepare_menu_matches": prepare_matches, "prepare_chosen_actions": prepare_chosen,
            "interpretation": "The match count is below the prespecified target of 25; comparisons and intervals are descriptive and do not support choosing a winner.",
            "behavioral_independence_caveat": "The player may have seen Frozen Policy v2 LIVE recommendations while playing, so recorded actions are not behaviorally independent of the baseline.",
            "next_stage": "Collect at least 25 additional non-overlapping matches and at least 20 recorded PREPARE_CARD choices before making a Prepare-generalization claim; include choices made without seeing model advice or expert-reviewed tactical positions.",
        },
        "private_examples_file": str(PRIVATE_EXAMPLES),
    }
    return report, private_predictions, disagreements


def _strategy_and_outcome(private_rows: list[dict], record_by_model: dict[str, dict[str, dict]]) -> dict:
    total = len(private_rows)
    strategy_status = Counter()
    outcome_status = Counter()
    disagreements = Counter()
    by_model = {}
    detail = []
    for item in private_rows:
        row = item["example"]
        menu = row["legal_actions"]
        sid = row["decision_id"]
        strategy = item["strategy"]
        outcome = item["outcome"]
        strategy_status["complete" if strategy.get("complete") else "incomplete"] += 1
        outcome_status["complete" if outcome.get("complete") else "incomplete"] += 1
        outcome_actions = {int(x["index"]): x for x in outcome.get("actions", []) if isinstance(x, dict) and "index" in x}
        chosen = int(row["chosen_action_index"])
        chosen_forecast = outcome_actions.get(chosen, {}).get("status", "MISSING")
        outcome_status[f"chosen_action:{chosen_forecast}"] += 1
        all_status = Counter(x.get("status", "MISSING") for x in outcome.get("actions", []))
        outcome_status.update({f"menu_action:{key}": value for key, value in all_status.items()})
        for action_row in outcome.get("actions", []):
            if action_row.get("reason"):
                outcome_status[f"reason:{action_row['reason']}"] += 1
            for unknown in set(action_row.get("unknowns", [])):
                outcome_status[f"unknown:{unknown}"] += 1
        ready = strategy.get("complete") is True and len(strategy.get("actions", [])) == len(menu)
        ranked_group = strategy.get("top3", [])
        scorer_best = set(ranked_group[0].get("indices", [])) if ready and ranked_group else set()
        scorer_first = min(scorer_best) if scorer_best else None
        model_relations = {}
        for name in NO_PREPARE_NAMES:
            rec = record_by_model[name].get(sid)
            if rec is None:
                continue
            same = rec["top_index"] in scorer_best if scorer_best else None
            model_relations[name] = {"same_best_action_or_tie": same,
                                     "top1_type": menu[rec["top_index"]]["type"]}
            if ready and scorer_best:
                disagreements[f"{name}:{menu[rec['top_index']]['type']}->{menu[scorer_first]['type']}"] += int(not same)
        strategy_scores = {int(x["index"]): x for x in strategy.get("actions", [])
                           if isinstance(x, dict) and "index" in x}
        gap = None
        if ready and len(strategy_scores) == len(menu):
            ordered_scores = sorted((float(value.get("score", 0.0)) for value in strategy_scores.values()), reverse=True)
            gap = ordered_scores[0] - ordered_scores[1] if len(ordered_scores) > 1 else 0.0
        detail.append({"decision_id": sid, "strategy_ready": ready,
                       "scorer_top_indices": sorted(scorer_best), "scorer_gap": gap,
                       "scorer_gap_ge_3": bool(gap is not None and gap >= SCORER_MAJOR_GAP),
                       "outcome_complete": outcome.get("complete") is True,
                       "outcome_chosen_action_status": chosen_forecast,
                       "model_relations": model_relations})
    for name in NO_PREPARE_NAMES:
        supported = [row for row in detail if name in row["model_relations"] and row["strategy_ready"]]
        n = len(supported)
        agrees = sum(row["model_relations"][name]["same_best_action_or_tie"] is True for row in supported)
        disagreements_with_gap = sum(row["model_relations"][name]["same_best_action_or_tie"] is False
                                     and row["scorer_gap_ge_3"] for row in supported)
        by_model[name] = {"decisions_with_complete_strategy_menu": n,
                          "agrees_with_scorer_top_score_set": agrees,
                          "agreement_rate": agrees / n if n else None,
                          "disagrees_where_scorer_gap_at_least_3_points": disagreements_with_gap}
    return {"strategy_scorer": {"parameters_version": "from journal rows",
                                "major_gap_threshold": SCORER_MAJOR_GAP,
                                "complete_rows": strategy_status["complete"],
                                "incomplete_rows": strategy_status["incomplete"],
                                "decisions_with_gap_at_least_3_points": sum(
                                    row["scorer_gap_ge_3"] for row in detail),
                                "model_agreement": by_model,
                                "disagreement_type_pairs": dict(sorted(disagreements.items())),
                                "interpretation": "Descriptive comparison only; scorer ranks are heuristic and are not move-quality labels."},
            "outcome_shadow": {"complete_rows": outcome_status["complete"],
                                "incomplete_rows": outcome_status["incomplete"],
                                "forecast_statuses": dict(sorted(outcome_status.items())),
                                "interpretation": "Forecast coverage and exactness inform mechanical review. Outcome Shadow does not rank strategic value or prove a better move."},
            "per_decision": detail, "decisions": total}


def _select_private_examples(private_rows: list[dict], records: dict[str, dict[str, dict]],
                             logits: dict[str, dict[str, list[float]]], scorer_summary: dict) -> dict:
    by_id = {item["example"]["decision_id"]: item for item in private_rows}
    interesting: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for item in private_rows:
        row = item["example"]
        sid = row["decision_id"]
        supported = [name for name in records if sid in records[name]]
        tops = {records[name][sid]["top_index"] for name in supported}
        if len(tops) > 1:
            interesting["all_models_disagree"].append((float(len(tops)), sid))
        if "frozen_v2" in records and sid in records["frozen_v2"]:
            frozen_top = records["frozen_v2"][sid]["top_index"]
            if row["legal_actions"][frozen_top]["type"] == "END_TURN" and any(
                    row["legal_actions"][records[name][sid]["top_index"]]["type"] != "END_TURN"
                    for name in supported if name != "frozen_v2"):
                interesting["frozen_ends_others_continue"].append((1.0, sid))
        chosen_type = row["legal_actions"][row["chosen_action_index"]]["type"]
        for name in supported:
            rec = records[name][sid]
            top_type = row["legal_actions"][rec["top_index"]]["type"]
            if top_type == "HERO_POWER" and chosen_type != "HERO_POWER":
                interesting["model_top1_hero_power_player_did_not"].append((rec["top_probability"], sid))
            if top_type == "ATTACK" and chosen_type == "ATTACK" and rec["top_index"] != row["chosen_action_index"]:
                interesting["attack_target_or_source_disagreement"].append((rec["top_probability"], sid))
            if rec["top_index"] != row["chosen_action_index"] and rec["top_probability"] >= CONFIDENCE_EXAMPLE_THRESHOLD:
                interesting[f"confident_disagreement:{name}"].append((rec["top_probability"], sid))
        strategy = item["strategy"]
        scorer_top = set(strategy.get("top3", [{}])[0].get("indices", [])) if strategy.get("complete") and strategy.get("top3") else set()
        if scorer_top and any(records[name][sid]["top_index"] not in scorer_top for name in supported if sid in records[name]):
            gap = next((d["scorer_gap"] for d in scorer_summary["per_decision"] if d["decision_id"] == sid), None)
            interesting["neural_vs_strategy_scorer"].append((gap or 0.0, sid))
    selected: dict[str, list[dict]] = {}
    for category, values in sorted(interesting.items()):
        ordered = sorted(values, key=lambda pair: (-pair[0], pair[1]))[:6]
        selected[category] = []
        for score, sid in ordered:
            item = by_id[sid]
            row = item["example"]
            selected[category].append({"category": category, "decision_id": sid,
                                       "match_id": row["game_id"], "state": row["state"],
                                       "legal_actions": row["legal_actions"],
                                       "chosen_action_index": row["chosen_action_index"],
                                       "chosen_action": row["legal_actions"][row["chosen_action_index"]],
                                       "recommendation": item["recommendation"],
                                       "strategy_shadow": item["strategy"], "outcome_shadow": item["outcome"],
                                       "model_logits": {name: logits[name].get(sid) for name in logits},
                                       "model_metrics": {name: records[name].get(sid) for name in records},
                                       "selection_score": score})
    return {"public_summary": {name: len(rows) for name, rows in selected.items()}, "private_examples": selected}


def _review_exact_lethals(private_rows: list[dict], records: dict[str, dict[str, dict]],
                          logits: dict[str, dict[str, list[float]]], selected: dict[str, list[dict]]) -> dict:
    """Check exact one-action lethal only on a fixed, small set of disagreements."""
    candidate_ids = []
    for category in ("all_models_disagree", "frozen_ends_others_continue", "neural_vs_strategy_scorer"):
        for row in selected.get(category, []):
            if row["decision_id"] not in candidate_ids:
                candidate_ids.append(row["decision_id"])
    candidate_ids = candidate_ids[:12]
    if not candidate_ids:
        return {"summary": {"reviewed_decisions": 0, "reviewed_model_decisions": 0,
                            "confirmed_one_action_lethals_outside_top3": 0, "status": "NO_DISAGREEMENT_CASES"},
                "private_rows": []}
    from manamind.domain.serialization import game_state_from_dict
    from manamind.outcome.forecast import forecast_action
    from manamind.outcome.model import Status
    from manamind.outcome.live_shadow import load_texts

    texts = load_texts(ROOT)
    lookup = {item["example"]["decision_id"]: item for item in private_rows}
    summary = Counter()
    detailed = []
    for decision_id in candidate_ids:
        item = lookup[decision_id]
        example = item["example"]
        state = game_state_from_dict(example["state"])
        context = context_from_dict(item["outcome"].get("context", {}))
        forecasts = []
        for action in example["legal_actions"]:
            try:
                forecasts.append(forecast_action(state, action, texts, context))
            except Exception as error:
                forecasts.append(None)
                summary[f"forecast_error:{type(error).__name__}"] += 1
        exact = [index for index, forecast in enumerate(forecasts)
                 if forecast is not None and forecast.status is Status.EXACT]
        lethal = [index for index in exact
                  if forecasts[index].exact_state().opponent.hero_health
                  + forecasts[index].exact_state().opponent.armor <= 0]
        summary["menu_exact_one_action_lethals"] += len(lethal)
        summary["menu_exact_forecasts"] += len(exact)
        summary["menu_partial_forecasts"] += sum(f is not None and f.status is Status.PARTIAL for f in forecasts)
        summary["menu_unsupported_forecasts"] += sum(f is not None and f.status is Status.UNSUPPORTED for f in forecasts)
        for name in logits:
            values = logits[name].get(decision_id)
            if values is None:
                continue
            order = sorted(range(len(values)), key=lambda index: (-values[index], index))
            top3 = order[:3]
            missed = sorted(set(lethal) - set(top3))
            confirmed = bool(missed)
            summary["confirmed_one_action_lethals_outside_top3"] += int(confirmed)
            status = "CONFIRMED" if confirmed else (
                "INCONCLUSIVE" if any(forecast is None or forecast.status is not Status.EXACT
                                      for forecast in forecasts) else "NO_EXACT_LETHAL_MISSED")
            summary[f"status:{status}"] += 1
            summary["reviewed_model_decisions"] += 1
            detailed.append({"decision_id": decision_id, "model": name,
                             "status": status, "reason_codes": ["EXACT_ONE_ACTION_LETHAL_OUTSIDE_TOP3"] if confirmed else [],
                             "exact_lethal_indices": lethal, "missed_lethal_indices": missed,
                             "top3_indices": top3,
                             "coverage": {"menu_actions": len(forecasts), "exact": len(exact),
                                          "partial": sum(f is not None and f.status is Status.PARTIAL for f in forecasts),
                                          "unsupported": sum(f is not None and f.status is Status.UNSUPPORTED for f in forecasts),
                                          "errors": sum(f is None for f in forecasts)}})
    public = {"reviewed_decisions": len(candidate_ids), "reviewed_model_decisions": summary["reviewed_model_decisions"],
              "confirmed_one_action_lethals_outside_top3": summary["confirmed_one_action_lethals_outside_top3"],
              "status_counts": {key.removeprefix("status:"): value for key, value in summary.items()
                                if key.startswith("status:")},
              "menu_forecasts": {"exact": summary["menu_exact_forecasts"],
                                 "partial": summary["menu_partial_forecasts"],
                                 "unsupported": summary["menu_unsupported_forecasts"],
                                 "errors": sum(value for key, value in summary.items()
                                               if key.startswith("forecast_error:")),
                                 "exact_one_action_lethal_actions": summary["menu_exact_one_action_lethals"]},
              "method": "Existing Outcome forecast_action; a confirmation requires an EXACT one-action forecast.",
              "coverage_note": "Only up to 12 preselected disagreement decisions were inspected; no broader lethal rate is estimated."}
    return {"summary": public, "private_rows": detailed}


def _render_readme(report: dict, *, locked_only: bool = False) -> str:
    models = report["models"]
    model_lines = "\n".join(f"- `{name}` — `{item['sha256']}` ({item.get('architecture') or 'architecture from checkpoint'})."
                             for name, item in models.items())
    inventory = report["inventory"]
    categories = report.get("match_categories", {})
    if locked_only:
        return f"""# NEW-MATCHES-EVAL-1 — протокол и результаты

## Зафиксированный протокол

Цель — проверить, насколько существующие checkpoints повторяют решения игрока на новых завершённых матчах. Обучение и изменение LIVE Policy не выполняются. Позиции включаются только при совпадении полного match ID, options ID, state hash, записанного LIVE snapshot, полного упорядоченного меню из Strategy и Outcome Shadow и фактического выбранного действия из Power.log. Frozen v2 top-3 дополнительно проверяется на принадлежность этому меню.

Найдены **{inventory['new_eligible_matches']} пригодных матчей** и **{inventory['new_eligible_decisions']} решений**. Это ниже ожидаемых примерно 25 матчей; оценка будет техническим пилотом и не позволит уверенно выбрать победителя.

Приватный идентификатор входного набора: `{report['data_identity_sha256']}`. Split-plan SHA-256: `{report['split_plan_sha256']}`. Код протокола зафиксирован коммитом `{report['source_commit']}`; SHA-256 скрипта: `{report['source_code_sha256']}`.

Девять ID из `fresh_holdout` использованы только для исключения пересечений. Их игровые данные не открывались, inference не запускался.

### Checkpoints

{model_lines}

Основные сравнения: все кандидаты на одинаковых меню без Prepare; Prepare v2/v3 отдельно на меню с Prepare. Старые и контрольные модели на Prepare-меню не запускаются. Дополнительно включены control v2/v3 seed 42, чтобы сравнить Prepare и контрольные checkpoints на обычных меню.

Метрики: cross-entropy, Top-1, Top-3 (только меню 3+ действий), MRR и uniform random baseline. Неопределённость считается парным bootstrap по целым матчам, 5 000 повторов, seed 20261018. Модели и подмножества после просмотра результатов не выбираются.

## Инвентаризация до inference

- Файлов в `data/raw/collected`: {inventory['raw_collected_log_files']}; по ID именованы {inventory['keyed_collected_match_logs']}; legacy-файлы без ключа: {inventory['legacy_filename_logs']} (UNVERIFIED).
- Категории инвентаризации: {json.dumps(categories, ensure_ascii=False, sort_keys=True)}. Причины исключений: {json.dumps(report.get('exclusion_reasons', {}), ensure_ascii=False, sort_keys=True)}.
- Записей LIVE: {inventory['live_recording_directories_nonprotected']}; совпадающие и не собранные Power.log записи отдельно классифицированы по ID.
- По прежним split, registry или checkpoint использований исключено: {categories.get('PREVIOUSLY_USED', 0)}.
- Защищённые raw-префиксы `fresh_holdout`, пропущенные без чтения: {inventory['protected_raw_log_prefixes_skipped']}.
- Новые кандидаты после проверки пересечений: {inventory['new_nonoverlap_raw_candidates']}; импортировано завершённо: {inventory['completed_matches_imported']}.
- Пригодные после точной LIVE-сверки: {inventory['new_eligible_matches']} матчей; {inventory['new_eligible_decisions']} решений.
- Prepare-меню в повторном импорте: {inventory['prepare_menu_decisions_imported']}; точное совпадение полного LIVE-меню: {inventory['prepare_menu_decisions_live_matched']}; точных выбранных действий `PREPARE_CARD`: {inventory['prepare_chosen_live_matched']}.
- LIVE запуск не включал `--prepare-actions`; несовпавшие Prepare-меню исключены: `{json.dumps(inventory['prepare_menu_decision_exclusions'], ensure_ascii=False, sort_keys=True)}`.
- Оценённых Prepare-меню после точной сверки: {inventory['prepare_decisions']}; выбранных `PREPARE_CARD`: {inventory['prepare_chosen']}.
- Не сопоставленные LIVE-решения исключены по диагностике: `{json.dumps(inventory['decision_exclusions'], ensure_ascii=False, sort_keys=True)}`.
- Решения, пропущенные Power.log импортёром: `{json.dumps(inventory['importer_skip_reasons'], ensure_ascii=False, sort_keys=True)}`.

`results.json` пока содержит только зафиксированный протокол. Полные состояния, legal menu, оценки и приватные разборы хранятся в игнорируемом `data/processed_new_matches_eval_1/`.
"""

    ordinary = report["evaluation_sets"]["ordinary_menus"]
    prepare = report["evaluation_sets"]["prepare_menus"]
    concl = report["conclusion"]
    ordinary_lines = "\n".join(
        f"| {name} | {values['decisions']} | {values['matches']} | "
        f"{values['metrics']['cross_entropy']:.4f} | {values['metrics']['top1']:.3f} | "
        f"{values['metrics']['top3'] if values['metrics']['top3'] is not None else 'n/a'} | {values['metrics']['mrr']:.3f} |"
        for name, values in ordinary["models"].items() if values["metrics"])
    prep_lines = "\n".join(
        f"| {name} | {values['decisions']} | {values['matches']} | "
        f"{values['metrics']['cross_entropy']:.4f} | {values['metrics']['top1']:.3f} | "
        f"{values['metrics']['top3'] if values['metrics']['top3'] is not None else 'n/a'} | {values['metrics']['mrr']:.3f} |"
        for name, values in prepare["models"].items() if values["metrics"])
    random = ordinary["models"].get("frozen_v2", {}).get("metrics", {}).get("uniform_random", {})
    return f"""# NEW-MATCHES-EVAL-1 — протокол и результаты

## A. Насколько хорошо модели предсказывают действия игрока?

Итог для imitation: **{concl['imitation_verdict']}**. В выборке {concl['eligible_matches']} матчей и {concl['eligible_decisions']} решений, ниже цели около 25 матчей. В таблицах приведены описательные значения; неопределённость парно оценена bootstrap-перевыборкой целых матчей. Действия игрока — метка поведения, не эталон качества хода.

### Обычные меню без Prepare

Все модели оценены на одних и тех же {ordinary['decisions']} решениях из {ordinary['matches']} матчей.

| Модель | Решений | Матчей | CE ↓ | Top-1 ↑ | Top-3 ↑ | MRR ↑ |
|---|---:|---:|---:|---:|---:|---:|
{ordinary_lines}

Uniform random baseline: CE {random.get('cross_entropy')}, Top-1 {random.get('top1')}, Top-3 {random.get('top3')}, MRR {random.get('mrr')}.

### Меню с Prepare

Сравниваются только Prepare v2 и v3: старые и control модели не понимают это action schema и на этих меню не запускались.

| Модель | Решений | Матчей | CE ↓ | Top-1 ↑ | Top-3 ↑ | MRR ↑ |
|---|---:|---:|---:|---:|---:|---:|
{prep_lines}

Выборов `PREPARE_CARD`: {concl['prepare_chosen_actions']} из {concl['prepare_menu_matches']} матчей. Вердикт о переносе Prepare: **{concl['prepare_out_of_corpus_verdict']}**.

### Парные сравнения и срезы

Полные парные CI, разброс метрик по матчам, срезы по типу выбранного действия, классу, фазе и размеру меню находятся в `results.json`. Фазы с менее чем тремя матчами отмечены как недостаточные. Top-3 считается только для меню размером от трёх действий.

## B. Насколько хороши сами рекомендации?

Стратегическое качество: **{concl['strategic_quality']}**. Strategy Shadow — эвристический scorer, а Outcome Shadow — частичный forecaster; их согласие и расхождение не доказывают правильность хода. Сопоставление и покрытия приведены в `results.json`; ручные случаи с полным состоянием, меню, оценками и действием игрока лежат только в игнорируемом `data/processed_new_matches_eval_1/examples.private.json`.

Не выполнялась оценка win rate и не подтверждалась стратегическая сила. Любой точный one-action lethal отмечается только при `EXACT` forecast через существующий Outcome decision review; эвристическая оценка потенциального lethal не выдаётся за доказательство.

## Ограничения и вывод

- Игрок мог видеть LIVE-рекомендации Frozen v2 во время этих партий. Эти решения не обязательно поведенчески независимы от baseline.
- Имитационная метрика измеряет сходство с выбором игрока, а не оптимальность.
- Выборка меньше ожидаемой: результат технический пилот, без объявления победителя.
- В меню с Prepare мало игровых примеров; для отдельного вывода нужно не менее 20 реальных выборов Prepare.

Рекомендация: собрать ещё независимые матчи с точными LIVE-сопоставлениями и не менее 20 действий `PREPARE_CARD`; для поведенчески независимой проверки сохранить решения, сделанные без показанных рекомендаций, или экспертно разобранные позиции. Сейчас данных недостаточно, чтобы принять стратегическое решение в пользу Policy или Strategic Scorer.
"""


def run_preflight() -> int:
    if (ROOT / PRIVATE_PROTOCOL).exists() or (ROOT / RESULTS).exists() or (ROOT / README).exists():
        raise SystemExit("NEW-MATCHES-EVAL-1 output already exists; refusing to overwrite")
    protocol, matched_rows = _inventory_and_pair()
    private = [{"example": row["example"], "recommendation": row["recommendation"],
                "strategy": row["strategy"], "outcome": row["outcome"]} for row in matched_rows]
    _write_new_jsonl(ROOT / PRIVATE_DECISIONS, private)
    protocol["private_decisions_sha256"] = sha256_file(ROOT / PRIVATE_DECISIONS)
    _write_new_json(ROOT / PRIVATE_PROTOCOL, protocol)
    public = _public_protocol(protocol)
    _write_new_json(ROOT / RESULTS, public)
    README.parent.mkdir(parents=True, exist_ok=True)
    README.write_text(_render_readme(public, locked_only=True), encoding="utf-8", newline="\n")
    print(json.dumps({"status": "PROTOCOL_LOCKED", "eligible_matches": protocol["inventory"]["new_eligible_matches"],
                      "eligible_decisions": protocol["inventory"]["new_eligible_decisions"],
                      "prepare_decisions": protocol["inventory"]["prepare_decisions"],
                      "prepare_chosen": protocol["inventory"]["prepare_chosen"],
                      "dataset_identity_sha256": protocol["dataset_identity_sha256"],
                      "private_decisions_sha256": protocol["private_decisions_sha256"]}, sort_keys=True))
    return 0


def run_evaluation() -> int:
    if not (ROOT / RESULTS).is_file() or _read_json(ROOT / RESULTS).get("status") != "PROTOCOL_LOCKED":
        raise SystemExit("a committed PROTOCOL_LOCKED report is required before inference")
    protocol, private_rows = _read_private_inputs()
    report, private_predictions, private_examples = _run_evaluation(protocol, private_rows)
    for spec in MODELS:
        if sha256_file(ROOT / spec["path"]) != spec["sha256"]:
            raise ValueError(f"checkpoint bytes changed during evaluation: {spec['name']}")
    _write_new_jsonl(ROOT / PRIVATE_LOGITS, private_predictions)
    _write_new_json(ROOT / PRIVATE_EXAMPLES, {
        "public_summary": private_examples["public_summary"],
        "selected_examples": private_examples["private_examples"],
        "strategy_analysis_per_decision": private_examples["strategy_analysis"],
        "outcome_decision_review": private_examples["decision_review"],
    })
    report["private_logits_sha256"] = sha256_file(ROOT / PRIVATE_LOGITS)
    report["private_examples_sha256"] = sha256_file(ROOT / PRIVATE_EXAMPLES)
    # The report path is new to this experiment and has never contained model results.
    (ROOT / RESULTS).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
                                encoding="utf-8", newline="\n")
    README.write_text(_render_readme(report), encoding="utf-8", newline="\n")
    print(json.dumps({"status": "COMPLETE", "eligible_matches": report["conclusion"]["eligible_matches"],
                      "eligible_decisions": report["conclusion"]["eligible_decisions"],
                      "imitation_verdict": report["conclusion"]["imitation_verdict"],
                      "prepare_verdict": report["conclusion"]["prepare_out_of_corpus_verdict"],
                      "prepare_choices": report["conclusion"]["prepare_chosen_actions"],
                      "private_examples": private_examples["public_summary"]}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true", help="inventory, join and lock protocol; no inference")
    mode.add_argument("--evaluate", action="store_true", help="run the locked inference-only evaluation")
    args = parser.parse_args(argv)
    return run_preflight() if args.preflight else run_evaluation()


if __name__ == "__main__":
    raise SystemExit(main())
