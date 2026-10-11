"""Freeze a private whole-match retraining protocol before fitting or test scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from manamind.training.policy_checkpoint import identity, load_policy_checkpoint
from manamind.training.real_policy import load_examples

try:
    from scripts.refresh_real_policy_dataset import dataset_identity, sha256_file
    from scripts.train_real_policy import write_json
except ModuleNotFoundError:
    from refresh_real_policy_dataset import dataset_identity, sha256_file
    from train_real_policy import write_json


def select_stratified(games, candidates, count, seed):
    """Proportional class/outcome quotas, with hash ordering within each stratum."""
    buckets = defaultdict(list)
    for game in sorted(candidates):
        buckets[games[game]].append(game)
    if not 0 <= count <= len(candidates):
        raise ValueError("Insufficient eligible whole matches")
    quotas = {key: count * len(values) / len(candidates) for key, values in buckets.items()}
    allocated = {key: int(value) for key, value in quotas.items()}
    remainder = count - sum(allocated.values())
    for key in sorted(buckets, key=lambda key: (-(quotas[key] - allocated[key]), key))[:remainder]:
        allocated[key] += 1
    return {game for key, values in buckets.items() for game in sorted(
        values, key=lambda g: hashlib.sha256(f"{seed}:{g}".encode()).hexdigest())[:allocated[key]]}


def freeze(rows, registry, baseline_payload, config, *, test_matches=16, validation_matches=7,
           allow_reviewed_test=False):
    if not registry.get("eval_mapping_reliable") or identity(registry["entries"]) != registry["registry_identity_sha256"]:
        raise ValueError("Historical usage registry is unverified")
    games = {}
    for row in rows:
        facts = (row["state"]["self_player"]["player_class"], row["final_result"])
        if row["game_id"] in games and games[row["game_id"]] != facts:
            raise ValueError("Inconsistent class/outcome within match")
        games[row["game_id"]] = facts
    old_parts = baseline_payload["experiment"]["split"]["game_ids"]
    usage = {entry["match_id"]: entry["usage"] for entry in registry["entries"]}
    for part, ids in old_parts.items():
        if any(f"POLICY_V2_{part.upper()}" not in usage.get(game, []) for game in ids):
            raise ValueError("Registry and frozen checkpoint membership disagree")
    fresh = {game for game in games if not usage.get(game)}
    # Unknown historical usage is never promoted to an independent holdout.
    fresh -= {entry["match_id"] for entry in registry["entries"] if entry["status"] == "UNKNOWN"}
    if len(fresh) < test_matches and allow_reviewed_test:
        old = {game for members in old_parts.values() for game in members}
        test = set(fresh)
        test |= select_stratified(games, set(games) - old - test, test_matches - len(test), config["split_seed"])
    else:
        test = select_stratified(games, fresh, test_matches, config["split_seed"])
    remaining = set(games) - test
    validation = select_stratified(games, remaining, validation_matches, config["split_seed"] + 1)
    train = remaining - validation
    if not train or len(train) <= len(old_parts["train"]):
        raise ValueError("Expanded training corpus is too small")
    ids = {"train": sorted(train), "validation": sorted(validation), "test": sorted(test)}
    split = {"algorithm": "class_outcome_proportional_hash_fresh_test/1", "seed": config["split_seed"],
             "dataset_sha256": dataset_identity(rows), "game_ids": ids,
             "decision_ids": {part: sorted(row["decision_id"] for row in rows if row["game_id"] in members)
                              for part, members in ids.items()}}
    membership = {game: part for part, members in ids.items() for game in members}
    return {"schema": "manamind.real_policy_retrain/1", "split": split, "split_sha256": identity(split),
            "config": config, "config_sha256": identity(config), "fresh_matches": len(fresh),
            "historical_registry_sha256": registry["registry_identity_sha256"],
            "historical_usage": [{"game_id": game, "part": membership[game], "previous_usage": usage.get(game, [])}
                                 for game in sorted(games)],
            "summary": {part: {"matches": len(members),
                               "decisions": sum(row["game_id"] in members for row in rows),
                               "class_matches": dict(Counter(games[game][0] for game in members)),
                               "outcome_matches": dict(Counter(str(games[game][1]) for game in members)),
                               "previously_used_matches": sum(bool(usage.get(game)) for game in members)}
                        for part, members in ids.items()},
            "hypothesis": "Additional real matches improve imitation without architecture or loss changes",
            "selection": "minimum_validation_cross_entropy_with_min_delta",
            "test_policy": "Open once after checkpoint saved; never use for subsequent tuning",
            "strength_claim": False}


def validate_manifest(manifest, rows, config, baseline_path):
    split = manifest["split"]
    if (manifest.get("schema") != "manamind.real_policy_retrain/1"
            or manifest["config"] != config or identity(config) != manifest["config_sha256"]
            or identity(split) != manifest["split_sha256"]
            or dataset_identity(rows) != split["dataset_sha256"]
            or sha256_file(baseline_path) != manifest["baseline_sha256"]):
        raise ValueError("Frozen protocol/input identity mismatch")
    ids = split["game_ids"]
    if set(ids) != {"train", "validation", "test"}:
        raise ValueError("Invalid split parts")
    sets = [set(values) for values in ids.values()]
    if (any(not values or len(values) != len(ids[part]) for part, values in zip(ids, sets))
            or any(a & b for i, a in enumerate(sets) for b in sets[i + 1:])
            or set.union(*sets) != {row["game_id"] for row in rows}):
        raise ValueError("Whole-match coverage/overlap violation")
    parts = {part: [row for row in rows if row["game_id"] in members] for part, members in ids.items()}
    for part, selected in parts.items():
        if sorted(row["decision_id"] for row in selected) != split["decision_ids"][part]:
            raise ValueError("Frozen decision membership mismatch")
    test = set(ids["test"])
    if any(any(tag.startswith("POLICY_V2_") for tag in entry["previous_usage"])
           for entry in manifest["historical_usage"] if entry["game_id"] in test):
        raise ValueError("Test has frozen Policy v2 split usage")
    _, _, payload = load_policy_checkpoint(baseline_path)
    old = {game for members in payload["experiment"]["split"]["game_ids"].values() for game in members}
    if test & old:
        raise ValueError("Test intersects frozen Policy splits")
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--test-matches", type=int, default=16)
    parser.add_argument("--validation-matches", type=int, default=7)
    parser.add_argument("--allow-reviewed-test", action="store_true",
                        help="Allow already reviewed matches disjoint from frozen v2; report them as reused")
    args = parser.parse_args()
    rows = load_examples(args.directory)
    _, _, payload = load_policy_checkpoint(args.baseline)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    if registry["checkpoint_sha256"]["v2"] != sha256_file(args.baseline):
        raise ValueError("Registry belongs to another baseline")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    manifest = freeze(rows, registry, payload, config, test_matches=args.test_matches,
                      validation_matches=args.validation_matches, allow_reviewed_test=args.allow_reviewed_test)
    manifest["baseline_sha256"] = sha256_file(args.baseline)
    validate_manifest(manifest, rows, config, args.baseline)
    write_json(args.directory / "retrain_manifest.json", manifest)
    print(json.dumps(manifest["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
