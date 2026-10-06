"""Offline LIVE recording replay through the exact reviewed recommendation path."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import torch

from manamind.domain.serialization import game_state_from_dict
from manamind.integrations.powerlog.policy_actions import map_actions
from manamind.live.recommendation import PolicyRecommender, RecommendationUnavailable, _inputs
from manamind.live.replay import recorded_hashes
from manamind.live.session import LiveSession
from manamind.live.snapshot import Snapshot
from manamind.live.trust import ModePolicy
from manamind.training.real_policy import encode_example, load_examples


def replay_once(directory: Path, recommender: PolicyRecommender, admitted: dict | None = None) -> dict:
    """Replay read-batch boundaries; score only the snapshot still current at each batch end."""
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    policy = ModePolicy(frozenset(meta.get("extra_game_types", [])))
    lines = (directory / "slice.log").read_text(encoding="utf-8").splitlines()
    trace = [json.loads(x) for x in (directory / "tail_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    session = LiveSession(recommender.encoder.catalog, policy)
    hashes, ranks, latencies, reasons = [], [], [], Counter()
    parity = 0
    superseded = 0
    index = 0
    for row in trace:
        count = int(row["n"])
        chunk = lines[index:index + count]
        index += count
        events = session.feed(chunk, int(row["t"]), catchup=bool(row.get("catchup"))) if count else []
        events += session.tick(int(row["t"]))
        hashes.extend(event.state_hash for event in events if isinstance(event, Snapshot))
        snapshot = session.current_snapshot
        if snapshot is None or not any(event is snapshot for event in events):
            superseded += sum(isinstance(event, Snapshot) for event in events)
            continue
        superseded += sum(isinstance(event, Snapshot) and event is not snapshot for event in events)
        try:
            result = recommender.score(snapshot, session)
        except RecommendationUnavailable as error:
            reasons[str(error)] += 1
            continue
        ranks.append((result.identity, [(item.index, item.score) for item in result.ranked]))
        latencies.append(result.latency_ms)
        if admitted is not None:
            key = f"{snapshot.game_key}:{snapshot.decision['options_id']}"
            example = admitted.get(key)
            if example is not None:
                game = session.game
                mapped = map_actions(game.reducer.last_options(), game.reducer.game, game.self_player_id,
                                     game_state_from_dict(snapshot.state))
                current_inputs = _inputs(game_state_from_dict(snapshot.state), mapped.actions, recommender.encoder)
                historical_inputs = encode_example(example, recommender.encoder)
                if (example["provenance"]["state_hash"] != snapshot.state_hash
                        or example["legal_actions"] != mapped.actions
                        or any(not torch.equal(a, b) for a, b in zip(current_inputs, historical_inputs))):
                    raise ValueError("ML-1B/LIVE model input mismatch")
                parity += 1
    return {"recorded_hashes_match": hashes == recorded_hashes(directory),
            "snapshots": len(hashes), "superseded_in_batch": superseded,
            "scored": len(ranks), "rankings": ranks,
            "latencies_ms": latencies, "skips": dict(reasons), "ml1b_parity": parity}


def replay_summary(directories: list[Path], recommender: PolicyRecommender,
                   admitted: dict | None = None) -> dict:
    sessions = [replay_once(path, recommender, admitted) for path in directories]
    repeated = [replay_once(path, recommender, admitted) for path in directories]
    latencies = [time for session in sessions for time in session["latencies_ms"]]
    skips = Counter(reason for session in sessions for reason, count in session["skips"].items()
                    for _ in range(count))
    return {"recordings": len(sessions), "snapshots": sum(s["snapshots"] for s in sessions),
            "scored": sum(s["scored"] for s in sessions),
            "superseded_in_batch": sum(s["superseded_in_batch"] for s in sessions),
            "recorded_hashes_match": all(s["recorded_hashes_match"] for s in sessions),
            "ranking_replay_identical": all(a["rankings"] == b["rankings"] for a, b in zip(sessions, repeated)),
            "ml1b_parity": sum(s["ml1b_parity"] for s in sessions),
            "skips": dict(sorted(skips.items())),
            "latency_ms": ({"median": float(np.percentile(latencies, 50)),
                            "p90": float(np.percentile(latencies, 90)),
                            "p99": float(np.percentile(latencies, 99))} if latencies else None)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--checkpoint", type=Path,
                        default=ROOT / "data/processed_policy_ml1c/baseline_seed42_v1/policy.pt")
    parser.add_argument("--admitted-dataset", type=Path)
    args = parser.parse_args()
    try:
        recommender = PolicyRecommender(args.checkpoint)
        admitted = ({row["decision_id"]: row for row in load_examples(args.admitted_dataset)}
                    if args.admitted_dataset else None)
        summary = replay_summary(args.recordings, recommender, admitted)
    except Exception as error:  # privacy: raw log errors may include names
        print(json.dumps({"result": "FAILED", "reason": type(error).__name__}))
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["recorded_hashes_match"] and summary["ranking_replay_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
