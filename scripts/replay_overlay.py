"""Check real recorded LIVE recommendations → overlay without opening a window.

Reuses the existing replay and frozen Policy scorer; reads no future game event
while formatting a recommendation. Output is aggregate counts only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
import hashlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.live.localization import CardNames
from manamind.live.presentation import OverlayFeed, PresentationEvent
from manamind.live.recommendation import PolicyRecommender
from replay_live_recommendations import replay_once
from run_manamind import POLICY_V2_SHA256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    scorer = PolicyRecommender(args.checkpoint, expected_sha256=POLICY_V2_SHA256)
    names = CardNames.load(ROOT / "data/localization/card_names_253932.json")
    feed = OverlayFeed(names)
    counts = Counter()
    examples = {}

    def check(snapshot, result):
        feed.heartbeat()
        feed.publish(PresentationEvent("recommendation", snapshot=snapshot, recommendation=result))
        frame = feed.read()
        if frame["status"] != "READY":
            raise ValueError("Overlay rejected the current ranking")
        for item, row in zip(result.ranked, frame["recommendations"], strict=True):
            if row["action"] != item.action or row["logit"] != item.score:
                raise ValueError("Overlay changed ranking/action")
            counts[item.action["type"]] += 1
            counts["targeted"] += bool(item.action.get("target_kind"))
            counts["unverified_coordinates"] += bool(row["view"]["ru"]["warning"])
            for key in ("source_card_id", "target_card_id"):
                card_id = item.action.get(key)
                if card_id:
                    counts["named_entities"] += 1
                    counts["ru_name_missing"] += not bool(names.names.get(card_id, {}).get("ruRU"))
            examples.setdefault(item.action["type"], row["view"]["ru"])
            if item.action.get("target_kind"):
                examples.setdefault(item.action["type"] + "_TARGETED", row["view"]["ru"])
            if item.action.get("source_is_hero"):
                examples.setdefault("HERO_ATTACK", row["view"]["ru"])
            if item.action.get("play_position", 0) > 1:
                examples.setdefault("PLACEMENT", row["view"]["ru"])
        counts["rankings"] += 1
        feed.publish(PresentationEvent("invalidated"))
        if feed.read()["recommendations"]:
            raise ValueError("Invalidation retained advice")

    replay = []
    for meta in sorted(args.recordings.rglob("meta.json")):
        if not (meta.parent / "tail_trace.jsonl").exists():
            continue
        result = replay_once(meta.parent, scorer, on_recommendation=check)
        counts["recordings"] += 1
        hashes = [hashlib.sha256((meta.parent / name).read_bytes()).digest()
                  for name in ("meta.json", "slice.log", "tail_trace.jsonl", "snapshots.jsonl")]
        replay.append({**{k: result[k] for k in ("scored", "recorded_hashes_match", "skips")},
                       "input_sha256": hashlib.sha256(b"".join(hashes)).hexdigest()})
    payload = {"checkpoint_sha256": POLICY_V2_SHA256, "counts": dict(sorted(counts.items())),
               "replay": replay, "examples": examples}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
