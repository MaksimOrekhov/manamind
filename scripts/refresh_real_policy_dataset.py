"""Rebuild an ignored real-policy corpus through the canonical Power.log importer.

This is data plumbing only: it never trains a model or rewrites an existing dataset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games
from manamind.live.snapshot import canonical_json
from manamind.models.policy import POLICY_ACTION_SCHEMA_VERSION
from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint
from manamind.training.real_policy import audit_dataset, load_examples, split_matches, validate_example

try:
    from scripts.import_policy_power_log import import_log
except ModuleNotFoundError:
    from import_policy_power_log import import_log

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_FILES = (
    "scripts/import_policy_power_log.py",
    "src/manamind/integrations/powerlog/policy_import.py",
    "src/manamind/integrations/powerlog/lines.py",
    "src/manamind/domain/serialization.py",
    "src/manamind/live/snapshot.py",
    "src/manamind/training/real_policy.py",
    "scripts/refresh_real_policy_dataset.py",
)
DEFAULT_V1 = ROOT / "data/processed_policy_ml1c/baseline_seed42_v1/policy.pt"
DEFAULT_V2 = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
DEFAULT_PREVIOUS = ROOT / "data/processed_policy_real/collected"
DEFAULT_EVAL_REPORT = ROOT / "reports/ml_eval0_real_policy_20261008/metrics.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_logs(raw_dir: Path) -> list[Path]:
    root = Path(raw_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Raw log directory does not exist: {root}")
    return [p for p in root.rglob("*.log") if p.is_file()]


def input_fingerprint(paths: list[Path]) -> str:
    """Content-set identity independent of path names, filesystem order, and timestamps."""
    items = sorted((p.stat().st_size, sha256_file(p)) for p in paths)
    return identity([{"bytes": size, "sha256": digest} for size, digest in items])


def dataset_identity(rows: list[dict]) -> str:
    return identity(sorted(rows, key=lambda row: row["decision_id"]))


def read_dataset_unchecked(directory: Path) -> list[dict]:
    """Read historical rows for identity/contamination comparison without repairing them."""
    rows = []
    for path in sorted(Path(directory).glob("*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return rows


def canonical_content_identity(directory: Path) -> str:
    rows = load_examples(directory)
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in Path(directory).glob("*.audit.json")]
    return identity({
        "rows": sorted(rows, key=lambda row: row["decision_id"]),
        "manifests": sorted(manifests, key=lambda item: item["game_id"]),
    })


def quality_summary(rows: list[dict], audit: dict, rejected_games: dict[str, int]) -> dict:
    by_game: dict[str, list[dict]] = defaultdict(list)
    chosen_types, menus, turns, selected_targeted = Counter(), Counter(), Counter(), 0
    for row in rows:
        by_game[row["game_id"]].append(row)
        chosen = row["legal_actions"][row["chosen_action_index"]]
        chosen_types[chosen["type"]] += 1
        menus[len(row["legal_actions"])] += 1
        turns[str(row["state"].get("turn", "UNKNOWN"))] += 1
        selected_targeted += "target_kind" in chosen
    outcome_names = {1.0: "WINS", 0.0: "LOSSES", 0.5: "DRAWS"}
    outcomes = Counter(outcome_names[decisions[0]["final_result"]] for decisions in by_game.values())
    match_sizes = [len(decisions) for decisions in by_game.values()]
    classes = Counter(decisions[0]["state"]["self_player"]["player_class"] for decisions in by_game.values())
    unknown_bonus = known_zero_bonus = known_nonzero_bonus = 0
    missing_player_fields = Counter()
    for row in rows:
        for side in ("self_player", "opponent"):
            player = row["state"][side]
            for name in ("hero_health", "armor", "available_mana", "max_mana", "healing_bonus"):
                if player.get(name) is None:
                    missing_player_fields[name] += 1
            bonus = player.get("healing_bonus")
            if bonus is None:
                unknown_bonus += 1
            elif bonus == 0:
                known_zero_bonus += 1
            else:
                known_nonzero_bonus += 1
    sizes = sorted(match_sizes)
    median = (sizes[(len(sizes) - 1) // 2] + sizes[len(sizes) // 2]) / 2 if sizes else None
    return {
        "matches": len(by_game),
        "decisions": len(rows),
        "outcomes_by_match": dict(sorted(outcomes.items())),
        "self_class_by_match": dict(sorted(classes.items())),
        "decisions_per_match": {
            "min": min(sizes) if sizes else None, "median": median, "max": max(sizes) if sizes else None,
        },
        "turn_decisions": dict(sorted(turns.items(), key=lambda pair: (pair[0] == "UNKNOWN", pair[0]))),
        "chosen_action_types": dict(sorted(chosen_types.items())),
        "selected_targeted_decisions": selected_targeted,
        "selected_targeted_rate": selected_targeted / len(rows) if rows else None,
        "legal_menu_sizes": dict(sorted(menus.items())),
        "unknown_public_card_identity_ratio": audit.get("unknown_card_id_ratio"),
        "missing_player_visible_fields": dict(sorted(missing_player_fields.items())),
        "healing_bonus_values": {
            "unknown": unknown_bonus, "known_zero": known_zero_bonus, "known_nonzero": known_nonzero_bonus,
        },
        "admitted_decisions_skipped": audit.get("decisions_skipped", 0),
        "admitted_decision_skip_reasons": audit.get("skip_reasons", {}),
        "raw_match_rejections": dict(sorted(rejected_games.items())),
        "deck_diversity": "not reliably inferable from visible hand snapshots; no deck identity reconstructed",
    }


def compare_datasets(previous_rows: list[dict], rebuilt_rows: list[dict]) -> dict:
    old_games = {row["game_id"] for row in previous_rows}
    new_games = {row["game_id"] for row in rebuilt_rows}
    old = {row["decision_id"]: row for row in previous_rows}
    new = {row["decision_id"]: row for row in rebuilt_rows}
    common = old.keys() & new.keys()
    changed_index = changed_action = changed_menu = non_schema_state = changed_outcome = 0
    schema_only = 0
    def without_bonus(state):
        result = json.loads(json.dumps(state))
        result.get("self_player", {}).pop("healing_bonus", None)
        result.get("opponent", {}).pop("healing_bonus", None)
        return result
    for key in common:
        before, after = old[key], new[key]
        changed_outcome += before["final_result"] != after["final_result"]
        changed_index += before["chosen_action_index"] != after["chosen_action_index"]
        before_action = before["legal_actions"][before["chosen_action_index"]]
        after_action = after["legal_actions"][after["chosen_action_index"]]
        changed_action += canonical_json(before_action) != canonical_json(after_action)
        changed_menu += canonical_json(before["legal_actions"]) != canonical_json(after["legal_actions"])
        state_changed = canonical_json(without_bonus(before["state"])) != canonical_json(without_bonus(after["state"]))
        non_schema_state += state_changed
        schema_only += not state_changed and canonical_json(before["state"]) != canonical_json(after["state"])
    return {
        "previous_matches": len(old_games), "rebuilt_matches": len(new_games),
        "matches_recovered": len(old_games & new_games), "previous_matches_missing": len(old_games - new_games),
        "rebuilt_matches_not_in_previous": len(new_games - old_games),
        "previous_decisions": len(previous_rows), "rebuilt_decisions": len(rebuilt_rows),
        "common_decisions": len(common), "common_decisions_missing": len(old.keys() - new.keys()),
        "common_decisions_added": len(new.keys() - old.keys()),
        "chosen_index_changed": changed_index, "chosen_action_semantics_changed": changed_action,
        "legal_menu_changed": changed_menu, "outcome_changed": changed_outcome,
        "non_schema_state_changed": non_schema_state,
        "state_only_healing_bonus_schema_changes": schema_only,
    }


def _source_hashes(repo_root: Path) -> dict[str, str]:
    return {name: sha256_file(repo_root / name) for name in IMPORTER_FILES}


def _git_sha(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _manifest_ids(directory: Path) -> set[str]:
    return {json.loads(path.read_text(encoding="utf-8"))["game_id"]
            for path in Path(directory).glob("*.audit.json")}


def _segment_ids(path: Path) -> list[str | None]:
    return [inspect_segment(segment).start_key for segment in split_games(read_complete_lines(path))]


def rebuild_once(
    raw_dir: Path,
    output_dir: Path,
    cards_path: Path,
    *,
    repo_root: Path = ROOT,
    source_sha: str | None = None,
) -> dict:
    raw_dir, output_dir, cards_path = Path(raw_dir), Path(output_dir), Path(cards_path)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output_dir}")
    paths = raw_logs(raw_dir)
    if not paths:
        raise ValueError("No raw Power.log files found")
    catalog = CardCatalog.from_json(cards_path)
    output_dir.mkdir(parents=True, exist_ok=False)
    results, rejected, imported_matches = [], Counter(), []
    for path in sorted(paths, key=lambda p: (p.stat().st_size, sha256_file(p))):
        digest = sha256_file(path)
        segment_ids = _segment_ids(path)
        before = _manifest_ids(output_dir)
        try:
            result = import_log(path, output_dir, catalog, segmented=True)
        except Exception as error:
            # Do not expose parser messages, which may contain private log text.
            result = {"games_inspected": len(segment_ids), "games_imported": 0,
                      "decisions_total": 0, "decisions_labeled": 0, "decisions_skipped": 0,
                      "decision_skip_reasons": {}, "game_skip_reasons": {type(error).__name__: 1}}
        after = _manifest_ids(output_dir)
        created = after - before
        imported_matches.extend(sorted(created))
        rejected.update(result.get("game_skip_reasons", {}))
        for game_id in segment_ids:
            if game_id in created:
                status, reason = "IMPORTED", None
            elif game_id in before:
                status, reason = "DUPLICATE", "DUPLICATE_MATCH"
            elif len(segment_ids) == 1 and len(result.get("game_skip_reasons", {})) == 1:
                status, reason = "REJECTED", next(iter(result["game_skip_reasons"]))
            else:
                status, reason = "UNKNOWN", None
            results.append({"match_id": game_id, "input_sha256": digest, "status": status, "reason": reason})
        results.append({
            "input_sha256": digest, "segments": len(segment_ids),
            "games_inspected": result.get("games_inspected", 0),
            "games_imported": result.get("games_imported", 0),
            "decisions_total": result.get("decisions_total", 0),
            "decisions_labeled": result.get("decisions_labeled", 0),
            "decisions_skipped": result.get("decisions_skipped", 0),
            "decision_skip_reasons": result.get("decision_skip_reasons", {}),
            "game_skip_reasons": result.get("game_skip_reasons", {}),
        })
    rows = load_examples(output_dir)
    for row in rows:
        validate_example(row)
    audit = audit_dataset(output_dir, catalog) if rows else {}
    raw_rejections = {reason: count for reason, count in rejected.items()}
    per_match_rows = {game: sum(row["game_id"] == game for row in rows)
                      for game in sorted({row["game_id"] for row in rows})}
    dataset_sha = dataset_identity(rows)
    content_sha = canonical_content_identity(output_dir) if rows else identity([])
    metadata = {
        "git_source_sha": source_sha or _git_sha(repo_root),
        "input_corpus_fingerprint": input_fingerprint(paths),
        "raw_log_files": len(paths),
        "raw_log_bytes": sum(path.stat().st_size for path in paths),
        "catalog_file_sha256": sha256_file(cards_path),
        "catalog_identity_sha256": identity(catalog.to_dict()),
        "schema_versions": {
            "state_encoding": STATE_ENCODING_SCHEMA_VERSION,
            "policy_action": POLICY_ACTION_SCHEMA_VERSION,
            "real_policy_dataset": 1,
            "semantic_action": 1,
        },
        "importer_source_hashes": _source_hashes(repo_root),
        "dataset_identity_sha256": dataset_sha,
        "canonical_content_identity_sha256": content_sha,
        "audit": audit,
        "quality": quality_summary(rows, audit, raw_rejections),
        "raw_match_registry": sorted(results, key=lambda item: (
            item.get("match_id") is None, item.get("match_id") or "", item["input_sha256"],
            item.get("status", ""),
        )),
        "admitted_match_decision_counts": per_match_rows,
    }
    (output_dir / "refresh_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return {
        "matches": len({row["game_id"] for row in rows}), "decisions": len(rows),
        "dataset_identity_sha256": dataset_sha, "canonical_content_identity_sha256": content_sha,
        "input_corpus_fingerprint": metadata["input_corpus_fingerprint"],
        "raw_log_files": len(paths), "raw_log_bytes": metadata["raw_log_bytes"],
        "imported_raw_matches": len(imported_matches), "raw_rejections": dict(sorted(rejected.items())),
        "validation": "PASS" if rows and len(rows) == audit.get("decisions_labeled") else "NO_ADMITTED_MATCHES",
        "quality": metadata["quality"],
    }


def frozen_experiment_usage(
    current_match_records: list[dict],
    current_rows: list[dict],
    eval_rows: list[dict],
    v1_payload: dict,
    v2_payload: dict,
    eval_report: dict,
) -> dict:
    usage: dict[str, set[str]] = defaultdict(set)
    split_membership = {}
    for label, payload in (("v1", v1_payload), ("v2", v2_payload)):
        experiment = payload["experiment"]
        split = experiment["split"]["game_ids"]
        split_membership[label] = split
        for part in ("train", "validation", "test"):
            for game_id in split[part]:
                usage[game_id].add(f"POLICY_{label.upper()}_{part.upper()}")
    if any(v1_payload["experiment"][key] != v2_payload["experiment"][key]
           for key in ("dataset_sha256", "split_sha256")):
        eval_mapping_reliable = False
    else:
        prior_sha = dataset_identity(eval_rows)
        expected = eval_report.get("current_dataset", {})
        eval_results = eval_report.get("fresh_game_id_disjoint_evaluation", {})
        eval_ids = {row["game_id"] for row in eval_rows}
        trained_ids = {game for split in split_membership.values() for part in split.values() for game in part}
        candidate_ids = eval_ids - trained_ids
        candidate_count = sum(row["game_id"] in candidate_ids for row in eval_rows)
        eval_mapping_reliable = (
            prior_sha == expected.get("identity_sha256")
            and len(candidate_ids) == 12 and candidate_count == 515
            and eval_results.get("v1", {}).get("top1_accuracy") is not None
            and eval_results.get("v2", {}).get("top1_accuracy") is not None
        )
    if eval_mapping_reliable:
        used_eval_ids = {row["game_id"] for row in eval_rows
                         if row["game_id"] not in {
                             game for split in split_membership.values() for part in split.values() for game in part
                         }}
        for game_id in used_eval_ids:
            usage[game_id].add("ML_EVAL_0_INFERENCE")
    known = {row["game_id"] for row in current_rows}
    known.update(record["match_id"] for record in current_match_records if record.get("match_id"))
    known.update(usage)
    unknown_ids = {record["match_id"] for record in current_match_records
                   if record.get("match_id") and record.get("status") == "UNKNOWN"}
    entries = []
    for game_id in sorted(known):
        categories = sorted(usage[game_id])
        if categories:
            status = "KNOWN_USED"
        elif not eval_mapping_reliable or game_id in unknown_ids:
            status = "UNKNOWN"
        else:
            status = "NOT_KNOWN_USED"
        entries.append({"match_id": game_id, "status": status, "usage": categories})
    return {
        "schema_version": 1,
        "eval_mapping_reliable": eval_mapping_reliable,
        "entries": entries,
        "status_counts": dict(sorted(Counter(entry["status"] for entry in entries).items())),
        "usage_counts": dict(sorted(Counter(tag for entry in entries for tag in entry["usage"]).items())),
        "registry_identity_sha256": identity(entries),
    }


def propose_unused_split(rows: list[dict], registry: dict, seed: int) -> dict:
    unused = {item["match_id"] for item in registry["entries"] if item["status"] == "NOT_KNOWN_USED"}
    eligible = [row for row in rows if row["game_id"] in unused]
    games = {row["game_id"] for row in eligible}
    if len(games) < 3:
        return {"seed": seed, "status": "NO_CLEAN_THREE_WAY_SPLIT",
                "eligible_matches": len(games), "eligible_decisions": len(eligible),
                "parts": {"train": [], "validation": [], "test": []}}
    parts = split_matches(eligible, seed=seed)
    memberships = {name: {row["game_id"] for row in selected} for name, selected in parts.items()}
    if any(memberships[a] & memberships[b] for a in memberships for b in memberships if a < b):
        raise ValueError("Whole-match split overlap")
    return {
        "seed": seed, "status": "PROPOSED",
        "eligible_matches": len(games), "eligible_decisions": len(eligible),
        "parts": {name: sorted(ids) for name, ids in memberships.items()},
        "decision_counts": {name: len(selected) for name, selected in parts.items()},
    }


def write_experiment_registry(
    output_dir: Path,
    current_rows: list[dict],
    match_records: list[dict],
    *,
    v1_checkpoint: Path,
    v2_checkpoint: Path,
    historical_dir: Path,
    previous_dir: Path,
    eval_report_path: Path,
    seed: int,
) -> dict:
    v1_model, _, v1_payload = load_policy_checkpoint(v1_checkpoint)
    v2_model, _, v2_payload = load_policy_checkpoint(v2_checkpoint)
    del v1_model, v2_model
    historical_rows = read_dataset_unchecked(historical_dir)
    historical_identity = dataset_identity(historical_rows)
    previous_rows = read_dataset_unchecked(previous_dir)
    if historical_identity != v1_payload["experiment"]["dataset_sha256"]:
        raise ValueError("Historical corpus identity differs from checkpoint provenance")
    historical_ids = {row["game_id"] for row in historical_rows}
    v1_ids = {game for part in v1_payload["experiment"]["split"]["game_ids"].values() for game in part}
    v2_ids = {game for part in v2_payload["experiment"]["split"]["game_ids"].values() for game in part}
    if historical_ids != v1_ids or historical_ids != v2_ids:
        raise ValueError("Historical match membership differs from checkpoint split provenance")
    report = json.loads(Path(eval_report_path).read_text(encoding="utf-8"))
    registry = frozen_experiment_usage(
        match_records, current_rows, previous_rows, v1_payload, v2_payload, report
    )
    split = propose_unused_split(current_rows, registry, seed)
    registry["split_proposal"] = split
    registry["checkpoint_sha256"] = {
        "v1": sha256_file(v1_checkpoint), "v2": sha256_file(v2_checkpoint),
    }
    (Path(output_dir) / "experiment_usage_registry.json").write_text(
        json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return {
        "historical_dataset_identity_sha256": historical_identity,
        "historical_matches": len({row["game_id"] for row in historical_rows}),
        "historical_decisions": len(historical_rows),
        "eval_corpus_identity_sha256": dataset_identity(previous_rows),
        "eval_corpus_matches": len({row["game_id"] for row in previous_rows}),
        "eval_corpus_decisions": len(previous_rows),
        "usage_registry_identity_sha256": registry["registry_identity_sha256"],
        "usage_status_counts": registry["status_counts"],
        "usage_counts": registry["usage_counts"],
        "eval_mapping_reliable": registry["eval_mapping_reliable"],
        "fresh_split_proposal": {
            "seed": split["seed"], "status": split["status"],
            "eligible_matches": split["eligible_matches"], "eligible_decisions": split["eligible_decisions"],
        },
    }


def verify_two_rebuilds(
    raw_dir: Path,
    output_dir: Path,
    cards_path: Path,
    *,
    repo_root: Path = ROOT,
    source_sha: str | None = None,
) -> dict:
    output_dir = Path(output_dir)
    first = output_dir.parent / f".{output_dir.name}.determinism-a"
    second = output_dir.parent / f".{output_dir.name}.determinism-b"
    for path in (output_dir, first, second):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing output: {path}")
    a = rebuild_once(raw_dir, first, cards_path, repo_root=repo_root, source_sha=source_sha)
    b = rebuild_once(raw_dir, second, cards_path, repo_root=repo_root, source_sha=source_sha)
    if a["canonical_content_identity_sha256"] != b["canonical_content_identity_sha256"]:
        raise ValueError("Independent canonical rebuilds differ")
    return {"runs": 2, "identical_content_identity": True,
            "canonical_content_identity_sha256": a["canonical_content_identity_sha256"],
            "dataset_identity_sha256": a["dataset_identity_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw/collected")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed_policy_real/refresh_20261008")
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--previous", type=Path, default=DEFAULT_PREVIOUS)
    parser.add_argument("--historical-dataset", type=Path,
                        default=ROOT / "data/processed_policy_ml2a/seed42_v2/dataset")
    parser.add_argument("--v1-checkpoint", type=Path, default=DEFAULT_V1)
    parser.add_argument("--v2-checkpoint", type=Path, default=DEFAULT_V2)
    parser.add_argument("--eval-report", type=Path, default=DEFAULT_EVAL_REPORT)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--verify-determinism", action="store_true")
    args = parser.parse_args()
    try:
        proof = verify_two_rebuilds(args.raw_dir, args.output_dir, args.cards) if args.verify_determinism else None
        result = rebuild_once(args.raw_dir, args.output_dir, args.cards)
        rows = load_examples(args.output_dir)
        meta = json.loads((args.output_dir / "refresh_metadata.json").read_text(encoding="utf-8"))
        usage = write_experiment_registry(
            args.output_dir, rows, meta["raw_match_registry"],
            v1_checkpoint=args.v1_checkpoint, v2_checkpoint=args.v2_checkpoint,
            historical_dir=args.historical_dataset,
            previous_dir=args.previous, eval_report_path=args.eval_report, seed=args.seed,
        )
        result["comparison"] = compare_datasets(read_dataset_unchecked(args.previous), rows)
        result["experiment_usage"] = usage
        result["determinism"] = proof or {"verified": False}
        (args.output_dir / "refresh_report.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8"
        )
    except Exception as error:
        print(json.dumps({"result": "FAILED", "reason": type(error).__name__}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
