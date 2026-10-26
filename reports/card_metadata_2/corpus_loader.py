"""Shared loading of the permitted real-match corpus for the CARD-METADATA-2 report scripts (read-only).

Protected ``fresh_holdout`` matches are excluded by ID from file names *before* any game file is opened.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from manamind.card_metadata.coverage import EFFECT_ZONES, entities  # noqa: E402

HEX64 = re.compile(r"^[0-9a-f]{64}$")
BUILD = re.compile(rb"BuildNumber=(\d+)")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def collect(data: Path):
    plan = load_json(data / "processed_policy_prepare_1/split_plan.json")
    held = set(plan["parts"]["fresh_holdout"])
    usage = {entry["match_id"] for entry in load_json(data / "processed_policy_prepare_1/usage_registry.json")["entries"]}
    policy_dir = data / "processed_policy_real/collected"
    files = sorted(p for p in policy_dir.glob("*.jsonl") if HEX64.match(p.stem))
    protected_present = sum(p.stem in held for p in files)
    files = [p for p in files if p.stem not in held]          # protected files are never opened
    matches = {}
    for path in files:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            continue
        zones, decisions = Counter(), []
        for row in rows:
            items = entities(row["state"])
            zones.update(items)
            decisions.append(frozenset(c for z, c in items if z in EFFECT_ZONES))
        first = rows[0]["state"]
        matches[path.stem] = {
            "zones": zones, "decisions": decisions, "group": "OLDER" if path.stem in usage else "NEWER",
            "self_class": first["self_player"].get("player_class") or "UNKNOWN",
            "opp_class": first["opponent"].get("player_class") or "UNKNOWN",
        }
    return matches, held, protected_present


def client_builds(data: Path, game_ids: list[str]) -> Counter:
    """Client BuildNumber of each match that has a keyed raw log (non-protected only; only the number is kept)."""
    result: Counter = Counter()
    raw_dir = data / "raw/collected"
    for game_id in game_ids:
        path = raw_dir / f"{game_id[:16]}.log"
        if not path.exists():
            result[("?",)] += 1
            continue
        found = sorted({m.decode() for m in BUILD.findall(path.read_bytes())})
        result[tuple(found) or ("none",)] += 1
    return result


def weighted(matches, ids, effect_only=True):
    total: Counter = Counter()
    for g in ids:
        for (zone, card_id), n in matches[g]["zones"].items():
            if zone in EFFECT_ZONES or not effect_only:
                total[card_id] += n
    return total


def by_zone(matches, ids, zone):
    total: Counter = Counter()
    for g in ids:
        for (z, card_id), n in matches[g]["zones"].items():
            if z == zone:
                total[card_id] += n
    return total
