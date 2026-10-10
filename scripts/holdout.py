"""Prepare an isolated LIVE collection lane without mutating the regular collector state."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import torch

from collect_power_logs import (
    IMPORTED,
    SKIPPED_ALREADY_IMPORTED,
    STATE_VERSION,
    TERMINAL_STATUSES,
)
from manamind.integrations.powerlog.lines import read_complete_lines, split_games, inspect_segment

GAME_ID = re.compile(r"[0-9a-f]{64}\Z")
HOLDOUT_NAME = "holdout_checkpoint_2"
MANIFEST_NAME = "holdout_manifest.json"
BACKUP_NAME = "regular_collector_state.backup.json"


class HoldoutError(ValueError):
    """Safe-to-display reason for refusing an unproven holdout setup."""


@dataclass(frozen=True)
class HoldoutPreparation:
    root: Path
    raw_output: Path
    processed_output: Path
    policy_output: Path
    evidence_output: Path
    state_path: Path
    manifest_path: Path
    source_state_path: Path

    def summary(self) -> dict[str, int]:
        manifest = _read_json(self.manifest_path)
        state = _read_json(self.state_path)
        games = state["games"]
        baseline = set(manifest["excluded_game_ids"])
        new_imported = sum(game_id not in baseline and status == IMPORTED
                           for game_id, status in games.items())
        policy_matches = policy_decisions = 0
        for path in self.policy_output.glob("*.audit.json"):
            audit = _read_json(path)
            if audit.get("game_id") not in baseline:
                policy_matches += 1
                policy_decisions += int(audit.get("decisions_labeled", 0))
        return {"matches_collected": new_imported,
                "policy_matches": policy_matches,
                "policy_decisions": policy_decisions}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HoldoutError(f"INVALID_LOCAL_FILE:{path.name}") from error


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _validate_game_ids(values, label: str) -> set[str]:
    if not isinstance(values, list):
        raise HoldoutError(f"INVALID_{label.upper()}_GAME_IDS")
    if any(not isinstance(value, str) or GAME_ID.fullmatch(value) is None for value in values):
        raise HoldoutError(f"INVALID_{label.upper()}_GAME_ID")
    return set(values)


def _historical_policy_ids(data_root: Path) -> tuple[set[str], dict[str, int]]:
    """Read policy datasets, experiment registries and frozen checkpoint splits."""
    ids: set[str] = set()
    counts = {"datasets": 0, "registries": 0, "checkpoint_splits": 0}
    policy_roots = sorted(path for path in data_root.glob("processed_policy*") if path.is_dir())
    for root in policy_roots:
        for path in sorted(root.rglob("*.jsonl")):
            try:
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        game_id = row.get("game_id") if isinstance(row, dict) else None
                        if game_id is not None:
                            ids.update(_validate_game_ids([game_id], "dataset"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise HoldoutError(f"INVALID_POLICY_DATASET:{path.name}") from error
            counts["datasets"] += 1

        for path in sorted(root.rglob("experiment_usage_registry.json")):
            registry = _read_json(path)
            entries = registry.get("entries")
            if not isinstance(entries, list):
                raise HoldoutError(f"INVALID_USAGE_REGISTRY:{path.name}")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise HoldoutError(f"INVALID_USAGE_REGISTRY:{path.name}")
                ids.update(_validate_game_ids([entry.get("match_id")], "registry"))
            counts["registries"] += 1

    checkpoint_paths = (
        data_root / "processed_policy_ml1c/baseline_seed42_v1/policy.pt",
        data_root / "processed_policy_ml2a/seed42_v2/policy.pt",
    )
    for path in checkpoint_paths:
        if not path.is_file():
            raise HoldoutError(f"MISSING_FROZEN_CHECKPOINT:{path.name}")
        try:
            payload = torch.load(path, map_location="cpu", weights_only=True)
            parts = payload["experiment"]["split"]["game_ids"]
            if set(parts) != {"train", "validation", "test"}:
                raise ValueError("split")
            for part in ("train", "validation", "test"):
                ids.update(_validate_game_ids(parts[part], "checkpoint"))
        except Exception as error:
            raise HoldoutError(f"INVALID_FROZEN_CHECKPOINT:{path.name}") from error
        counts["checkpoint_splits"] += 1
    return ids, counts


def _raw_collected_ids(raw_dir: Path) -> tuple[set[str], dict[str, int]]:
    if not raw_dir.is_dir():
        raise HoldoutError("MISSING_REGULAR_RAW_CORPUS")
    ids: set[str] = set()
    files = 0
    for path in sorted(raw_dir.glob("*.log")):
        try:
            segments = split_games(read_complete_lines(path))
        except OSError as error:
            raise HoldoutError(f"UNREADABLE_REGULAR_RAW:{path.name}") from error
        if len(segments) != 1:
            raise HoldoutError(f"AMBIGUOUS_REGULAR_RAW:{path.name}")
        info = inspect_segment(segments[0])
        if info.start_key is None or info.complete_index is None:
            raise HoldoutError(f"INCOMPLETE_REGULAR_RAW:{path.name}")
        ids.add(info.start_key)
        files += 1
    if not ids:
        raise HoldoutError("EMPTY_REGULAR_RAW_CORPUS")
    return ids, {"files": files, "matches": len(ids)}


def _existing_log_ids(logs_root: Path) -> tuple[set[str], int]:
    if not logs_root.is_dir():
        raise HoldoutError("MISSING_HEARTHSTONE_LOGS_ROOT")
    ids: set[str] = set()
    for path in sorted(logs_root.rglob("Power*.log")):
        try:
            before = path.stat()
            lines = read_complete_lines(path)
            after = path.stat()
        except OSError as error:
            raise HoldoutError(f"UNREADABLE_EXISTING_LOG:{path.name}") from error
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise HoldoutError("HEARTHSTONE_LOGS_CHANGED_DURING_HOLDOUT_SETUP")
        for segment in split_games(lines):
            info = inspect_segment(segment)
            if info.start_key is not None:
                ids.add(info.start_key)
    return ids, len(ids)


def _source_state(path: Path) -> tuple[bytes, dict[str, str]]:
    try:
        content = path.read_bytes()
        payload = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HoldoutError("INVALID_REGULAR_COLLECTOR_STATE") from error
    if (not isinstance(payload, dict) or set(payload) != {"version", "games"}
            or payload["version"] != STATE_VERSION or not isinstance(payload["games"], dict)):
        raise HoldoutError("INVALID_REGULAR_COLLECTOR_STATE")
    games = payload["games"]
    if any(not isinstance(game_id, str) or GAME_ID.fullmatch(game_id) is None
           or status not in TERMINAL_STATUSES
           for game_id, status in games.items()):
        raise HoldoutError("INVALID_REGULAR_COLLECTOR_STATE")
    return content, games


def _source_raw_fingerprint(raw_dir: Path) -> str:
    records = []
    for path in sorted(raw_dir.glob("*.log")):
        records.append({"bytes": path.stat().st_size, "sha256": _sha256(path.read_bytes())})
    payload = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return _sha256(payload)


def _validate_resume(prepared: HoldoutPreparation, source_hash: str, raw_hash: str) -> dict:
    manifest = _read_json(prepared.manifest_path)
    backup = prepared.root / "provenance" / BACKUP_NAME
    if (manifest.get("schema_version") != 1
            or manifest.get("source_state_sha256") != source_hash
            or manifest.get("source_raw_fingerprint_sha256") != raw_hash
            or not backup.is_file() or _sha256(backup.read_bytes()) != source_hash):
        raise HoldoutError("HOLDOUT_BASELINE_CHANGED_OR_BACKUP_INVALID")
    excluded = _validate_game_ids(manifest.get("excluded_game_ids"), "holdout_manifest")
    state = _read_json(prepared.state_path)
    if state.get("version") != STATE_VERSION or not isinstance(state.get("games"), dict):
        raise HoldoutError("INVALID_HOLDOUT_COLLECTOR_STATE")
    seeded = state["games"]
    if any(seeded.get(game_id) != SKIPPED_ALREADY_IMPORTED for game_id in excluded):
        raise HoldoutError("HOLDOUT_BLOCKLIST_MISSING_GAMES")
    if any(GAME_ID.fullmatch(game_id) is None or status not in TERMINAL_STATUSES
           for game_id, status in seeded.items()):
        raise HoldoutError("INVALID_HOLDOUT_COLLECTOR_STATE")
    return manifest


def prepare_holdout(data_root: Path, logs_root: Path) -> HoldoutPreparation:
    """Back up/verify the ordinary state and initialize or validate isolated holdout paths."""
    data_root, logs_root = Path(data_root).resolve(), Path(logs_root).resolve()
    root = data_root / "raw" / HOLDOUT_NAME
    raw_output = root / "raw" / "collected"
    processed_output = root / "processed_real"
    policy_output = root / "processed_policy_real" / "collected"
    evidence_output = root / "processed_evidence" / "collected"
    state_path = raw_output / "collector_state.json"
    manifest_path = root / "provenance" / MANIFEST_NAME
    source_state_path = data_root / "raw" / "collected" / "collector_state.json"
    prepared = HoldoutPreparation(root, raw_output, processed_output, policy_output,
                                  evidence_output, state_path, manifest_path, source_state_path)

    source_content, source_games = _source_state(source_state_path)
    source_hash = _sha256(source_content)
    raw_ids, raw_stats = _raw_collected_ids(source_state_path.parent)
    raw_hash = _source_raw_fingerprint(source_state_path.parent)

    if root.exists():
        if not manifest_path.is_file():
            raise HoldoutError("INCOMPLETE_EXISTING_HOLDOUT_DIRECTORY")
        manifest = _validate_resume(prepared, source_hash, raw_hash)
        if (set(manifest.get("source_state_game_ids", [])) != set(source_games)
                or set(manifest.get("source_raw_game_ids", [])) != raw_ids):
            raise HoldoutError("HOLDOUT_BASELINE_CHANGED_OR_BACKUP_INVALID")
        historical_ids = _validate_game_ids(manifest.get("historical_policy_game_ids"), "manifest")
        excluded = _validate_game_ids(manifest.get("excluded_game_ids"), "manifest")
        if not historical_ids <= excluded:
            raise HoldoutError("HOLDOUT_EXCLUSION_SET_INCOMPLETE")
        current_history_ids, _ = _historical_policy_ids(data_root)
        if current_history_ids != historical_ids:
            raise HoldoutError("HISTORICAL_POLICY_DATA_CHANGED_SINCE_HOLDOUT_SETUP")
        return prepared

    history_ids, history_counts = _historical_policy_ids(data_root)
    existing_log_ids, existing_log_count = _existing_log_ids(logs_root)
    excluded = set(source_games) | raw_ids | existing_log_ids | history_ids
    holdout_state = {"version": STATE_VERSION,
                     "games": {game_id: SKIPPED_ALREADY_IMPORTED for game_id in sorted(excluded)}}
    baseline = {
        "schema_version": 1,
        "source_state_sha256": source_hash,
        "source_raw_fingerprint_sha256": raw_hash,
        "source_state_game_ids": sorted(source_games),
        "source_raw_game_ids": sorted(raw_ids),
        "existing_log_game_ids": sorted(existing_log_ids),
        "historical_policy_game_ids": sorted(history_ids),
        "excluded_game_ids": sorted(excluded),
        "source_raw_files": raw_stats["files"],
        "source_raw_matches": raw_stats["matches"],
        "existing_log_matches": existing_log_count,
        "source_state_matches": len(source_games),
        "raw_ids_missing_from_source_state": len(raw_ids - set(source_games)),
        "historical_policy_sources": history_counts,
        "initial_holdout_matches": 0,
        "initial_holdout_policy_overlap": 0,
    }
    if _sha256(source_state_path.read_bytes()) != source_hash:
        raise HoldoutError("REGULAR_COLLECTOR_STATE_CHANGED_DURING_HOLDOUT_SETUP")

    try:
        root.mkdir(parents=True, exist_ok=False)
        backup_path = root / "provenance" / BACKUP_NAME
        _atomic_write(backup_path, source_content)
        if _sha256(backup_path.read_bytes()) != source_hash:
            raise HoldoutError("REGULAR_STATE_BACKUP_VERIFICATION_FAILED")
        _atomic_write(state_path, json.dumps(holdout_state, indent=1).encode("utf-8"))
        _atomic_write(manifest_path, json.dumps(baseline, indent=2, sort_keys=True).encode("utf-8"))
        if _sha256(source_state_path.read_bytes()) != source_hash:
            raise HoldoutError("REGULAR_COLLECTOR_STATE_CHANGED_DURING_HOLDOUT_SETUP")
    except OSError as error:
        raise HoldoutError("HOLDOUT_INITIALIZATION_FAILED") from error
    return prepared


def verify_holdout_disjoint(prepared: HoldoutPreparation) -> dict[str, int]:
    """Fail closed if any saved holdout Policy rows intersect historical Policy data."""
    manifest = _read_json(prepared.manifest_path)
    historical = _validate_game_ids(manifest.get("historical_policy_game_ids"), "manifest")
    excluded = _validate_game_ids(manifest.get("excluded_game_ids"), "manifest")
    state = _read_json(prepared.state_path)
    if state.get("version") != STATE_VERSION or not isinstance(state.get("games"), dict):
        raise HoldoutError("INVALID_HOLDOUT_COLLECTOR_STATE")
    state_ids = set(state["games"])
    if any(GAME_ID.fullmatch(game_id) is None for game_id in state_ids):
        raise HoldoutError("INVALID_HOLDOUT_COLLECTOR_STATE")
    if any(status not in TERMINAL_STATUSES for status in state["games"].values()):
        raise HoldoutError("INVALID_HOLDOUT_COLLECTOR_STATE")
    if (state_ids - excluded) & historical:
        raise HoldoutError("HOLDOUT_STATE_OVERLAPS_HISTORICAL_DATA")
    output_ids: set[str] = set()
    for path in sorted(prepared.policy_output.glob("*.jsonl")):
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        row = json.loads(line)
                        output_ids.update(_validate_game_ids([row.get("game_id")], "holdout"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise HoldoutError(f"INVALID_HOLDOUT_POLICY_DATASET:{path.name}") from error
    overlap = output_ids & historical
    if overlap:
        raise HoldoutError("HOLDOUT_POLICY_OVERLAPS_HISTORICAL_DATA")
    return {"policy_matches": len(output_ids), "historical_overlap": 0}
