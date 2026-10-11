"""Supplement a frozen protocol with later local experiment usage, without refitting."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import torch

from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games
from manamind.training.policy_checkpoint import identity
from manamind.training.real_policy import load_examples

try:
    from scripts.refresh_real_policy_dataset import input_fingerprint, raw_logs, read_dataset_unchecked, sha256_file
    from scripts.train_real_policy import write_json
except ModuleNotFoundError:
    from refresh_real_policy_dataset import input_fingerprint, raw_logs, read_dataset_unchecked, sha256_file
    from train_real_policy import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, action="append", default=[])
    parser.add_argument("--reviewed-corpus", type=Path, action="append", default=[])
    parser.add_argument("--prior-policy-corpus", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = load_examples(args.data)
    manifest_path = args.data / "retrain_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    registry = json.loads(args.registry.read_text())
    if identity(registry["entries"]) != registry["registry_identity_sha256"]:
        raise ValueError("Historical registry identity mismatch")
    usage = defaultdict(set)
    for entry in registry["entries"]:
        usage[entry["match_id"]].update(entry["usage"])
    sources = {str(args.registry): sha256_file(args.registry)}
    for path in args.checkpoint:
        payload = torch.load(path, map_location="cpu", weights_only=True)
        experiment = payload.get("experiment", payload)
        split = experiment["split"]
        if identity(split) != experiment["split_sha256"]:
            raise ValueError("Additional checkpoint split identity mismatch")
        sources[str(path)] = sha256_file(path)
        for part, games in split["game_ids"].items():
            for game in games:
                usage[game].add(f"ML_PILOT_1_{path.stem.upper()}_{part.upper()}")
    for path in args.reviewed_corpus:
        reviewed = read_dataset_unchecked(path)
        sources[str(path)] = identity(sorted(reviewed, key=lambda row: row["decision_id"]))
        for row in reviewed:
            # Same pinned corpus used by the later audit/forecast probes, not a new independent test.
            usage[row["game_id"]].add("DATA_CHECKPOINT_1_AND_LATER_DIAGNOSTICS_SEEN")
    games = {row["game_id"] for row in rows}
    prior_inventory = {}
    for path in args.prior_policy_corpus:
        old_rows = read_dataset_unchecked(path)
        prior_games = {row["game_id"] for row in old_rows}
        prior_inventory[str(path)] = {"matches": len(prior_games), "decisions": len(old_rows),
                                      "absent_from_canonical": sorted(prior_games - games)}
    paths = raw_logs(args.raw)
    segments = [inspect_segment(segment) for path in paths for segment in split_games(read_complete_lines(path))]
    raw_ids = {segment.start_key for segment in segments if segment.start_key}
    eligible_raw = {segment.start_key for segment in segments if segment.start_key
                    and segment.game_types == {"GT_RANKED"} and segment.formats == {"FT_STANDARD"}
                    and segment.complete_index is not None and not segment.mid_game_start}
    raw_meta = json.loads((args.data / "refresh_metadata.json").read_text())
    if input_fingerprint(paths) != raw_meta["input_corpus_fingerprint"]:
        raise ValueError("Raw source corpus changed after canonical rebuild")
    rejected = defaultdict(set)
    for entry in raw_meta["raw_match_registry"]:
        if entry.get("match_id") and entry["status"] == "REJECTED":
            rejected[entry["reason"]].add(entry["match_id"])
    known = games | {entry["match_id"] for entry in registry["entries"]}
    unknown = {entry["match_id"] for entry in registry["entries"] if entry["status"] == "UNKNOWN"}
    entries = [{"match_id": game, "usage": sorted(usage[game]),
                "status": "KNOWN_USED" if usage[game] else "UNKNOWN" if game in unknown else "NOT_KNOWN_USED"}
               for game in sorted(known)]
    summary = {}
    for part, members in (manifest["split"]["game_ids"] if manifest else {}).items():
        ids = set(members)
        reused = ids & {game for game in games if usage[game]}
        summary[part] = {"matches": len(ids), "decisions": sum(row["game_id"] in ids for row in rows),
                         "previously_used_matches": len(reused),
                         "previously_used_decisions": sum(row["game_id"] in reused for row in rows),
                         "no_known_previous_use_matches": len(ids - reused),
                         "usage_matches": dict(sorted(Counter(tag for game in ids for tag in usage[game]).items()))}
    result = {"schema": "manamind.retrain_supplementary_usage/1", "schema_version": 1,
              "eval_mapping_reliable": registry["eval_mapping_reliable"],
              "checkpoint_sha256": registry["checkpoint_sha256"],
              "registry_identity_sha256": identity(entries), "protocol_sha256": identity(manifest) if manifest else None,
              "sources": sources, "entries": entries, "entries_sha256": identity(entries),
              "prior_policy_inventory": prior_inventory, "split_summary": summary,
              "raw": {"files": len(paths), "segments": len(segments), "unique_matches": len(raw_ids),
                      "unique_completed_ranked_standard": len(eligible_raw),
                      "duplicate_segments": len(segments) - len(raw_ids),
                      "excluded_unique_reasons": {reason: len(ids) for reason, ids in rejected.items()}},
              "limitation": ("Later usage discovered after fitting; frozen split and checkpoint stay unchanged"
                             if manifest else "Pre-freeze usage audit; no model fitted")}
    write_json(args.output, result)
    print(json.dumps({"raw": result["raw"], "split_summary": summary, "prior_inventory": prior_inventory}))


if __name__ == "__main__":
    main()
