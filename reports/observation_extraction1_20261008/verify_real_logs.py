"""OBSERVATION-EXTRACTION-1: re-extract real raw logs with the new extractor and compare them with the old datasets.

Read-only on every input. Everything is written under ``--workdir`` (a new, git-ignored directory) and only sanitized
aggregates (counts, never game ids, names, handles or card trajectories) go to ``--summary``.

    python reports/observation_extraction1_20261008/verify_real_logs.py ^
        --raw-dir <data>/raw/collected --old-policy-dir <data>/processed_policy_real/collected ^
        --live-dir <data>/raw/live --workdir data/processed_obs1/run1 ^
        --summary reports/observation_extraction1_20261008/real_log_verification.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from hearthstone.enums import CardType, GameTag, Zone  # noqa: E402
from hslog import LogParser  # noqa: E402
from hslog.packets import Block  # noqa: E402

from import_policy_power_log import import_log  # noqa: E402
from import_power_log import import_power_log  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.exporter import CompatibleEntityTreeExporter  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError  # noqa: E402
from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.live.replay import replay_game  # noqa: E402
from manamind.live.snapshot import state_to_dict  # noqa: E402
from manamind.training.real_policy import load_examples  # noqa: E402

# Fields this package is allowed to change in a state. Anything else that differs is a regression.
EXPECTED_CHANGES = {
    "self_player.hero_max_health", "opponent.hero_max_health",
    "self_player.hero_frozen", "opponent.hero_frozen",
    "self_player.hero_power_ready", "opponent.hero_power_ready",
}
SEATS = ("self_player", "opponent")


def read_rows(directory: Path) -> dict[str, dict]:
    """Plain JSONL rows keyed by decision id, with no validation (older datasets fail the current strict check)."""
    rows = {}
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["decision_id"]] = row
    return rows


def normalized(state: dict) -> dict:
    """An older state read through the current domain: later-added fields appear as None, nothing else changes."""
    return state_to_dict(game_state_from_dict(state))


def leaves(value, prefix=""):
    if isinstance(value, dict):
        for key in sorted(value):
            yield from leaves(value[key], f"{prefix}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, f"{prefix}{index}.")
    else:
        yield prefix[:-1], value


def diff_states(old: dict, new: dict) -> dict[str, tuple]:
    old_leaves, new_leaves = dict(leaves(old)), dict(leaves(new))
    return {path: (old_leaves.get(path, "<absent>"), new_leaves.get(path, "<absent>"))
            for path in sorted(old_leaves.keys() | new_leaves.keys()) if old_leaves.get(path, "<absent>") != new_leaves.get(path, "<absent>")}


def transition(old, new) -> str:
    def name(v):
        return "absent" if v == "<absent>" else "None" if v is None else repr(v)
    return f"{name(old)}->{name(new)}"


def compare(pairs) -> dict:
    """pairs: iterable of (old_state, new_state). Returns counts of changed fields by path and by value transition."""
    by_path, by_transition, unexpected, total = Counter(), Counter(), Counter(), 0
    for old, new in pairs:
        total += 1
        for path, (before, after) in diff_states(old, new).items():
            if path in EXPECTED_CHANGES:
                by_path[path] += 1
                kind = "max" if path.endswith("max_health") else path.split(".")[-1]
                by_transition[f"{kind}:{transition(before, after)}"] += 1
            else:
                unexpected[path] += 1
    return {"pairs": total, "changed_by_path": dict(sorted(by_path.items())),
            "changed_by_transition": dict(sorted(by_transition.items())), "unexpected_changes": dict(sorted(unexpected.items()))}


def distribution(states) -> dict:
    out = {}
    for seat in SEATS:
        health = Counter()
        frozen, ready, max_values = Counter(), Counter(), Counter()
        for state in states:
            player = state[seat]
            maximum = player.get("hero_max_health")
            max_values["unknown" if maximum is None else maximum] += 1
            if maximum is not None:
                health["damaged" if player["hero_health"] < maximum else "undamaged"] += 1
                if player["hero_health"] > maximum:
                    health["VIOLATION_current_above_max"] += 1
            frozen[str(player.get("hero_frozen"))] += 1
            ready[str(player.get("hero_power_ready"))] += 1
            if player.get("hero_freeze_turns_remaining") is not None:
                frozen["VIOLATION_duration_invented"] += 1
        out[seat] = {"hero_max_health": {str(k): v for k, v in sorted(max_values.items(), key=str)}, "damage": dict(health),
                     "hero_frozen": dict(frozen), "hero_power_ready": dict(ready)}
    return out


def raw_hero_facts(path: Path) -> dict:
    """Independent of the extractor: the raw HEALTH values and FROZEN values of both heroes at every Block boundary."""
    parser = LogParser()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        parser.read(handle)
    health, frozen = set(), set()
    for game in parser.games:
        exporter = CompatibleEntityTreeExporter(game)
        for packet in game.packets:
            exporter.export_packet(packet)
            if exporter.game is None or not isinstance(packet, Block):
                continue
            for player in exporter.game.players:
                hero = next((e for e in exporter.game.entities if e.id == player.tags.get(GameTag.HERO_ENTITY)), None)
                if hero is not None and hero.type == CardType.HERO and hero.zone == Zone.PLAY:
                    health.add(hero.tags.get(GameTag.HEALTH))
                    frozen.add(hero.tags.get(GameTag.FROZEN, "absent"))
    return {"health": health, "frozen": frozen}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--old-policy-dir", type=Path)
    parser.add_argument("--canonical-baseline-dir", type=Path)
    parser.add_argument("--live-dir", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    args = parser.parse_args()
    if args.workdir.exists() and any(args.workdir.iterdir()):
        raise SystemExit(f"refusing to write into non-empty {args.workdir}")
    catalog = CardCatalog.from_json(args.cards)
    policy_dir, value_dir = args.workdir / "policy", args.workdir / "value"
    value_dir.mkdir(parents=True, exist_ok=True)

    logs = sorted(path for path in args.raw_dir.glob("*.log"))
    imported_policy, imported_value, skipped = 0, 0, Counter()
    raw_forty_games, raw_frozen_games = 0, 0
    for index, path in enumerate(logs):
        try:
            result = import_log(path, policy_dir, catalog)
            imported_policy += result["games_imported"]
            skipped.update({f"policy:{k}": v for k, v in result["game_skip_reasons"].items()})
        except (PolicyImportError, ValueError) as error:
            skipped[f"policy:{getattr(error, 'reason', type(error).__name__)}"] += 1
        try:
            import_power_log(path, value_dir / f"{index:03d}.jsonl", args.cards)
            imported_value += 1
        except (ValueError, FileExistsError) as error:
            skipped[f"value:{type(error).__name__}"] += 1
        facts = raw_hero_facts(path)
        raw_forty_games += int(any(h not in (None, 30) for h in facts["health"]))
        raw_frozen_games += int(any(f != "absent" for f in facts["frozen"]))

    new_rows = {row["decision_id"]: row for row in load_examples(policy_dir)}
    summary: dict = {
        "inputs": {"raw_logs": len(logs), "policy_games_imported": imported_policy, "value_matches_imported": imported_value,
                   "skips": dict(sorted(skipped.items()))},
        "raw_log_facts_independent_of_the_extractor": {"games_with_a_hero_health_other_than_30": raw_forty_games,
                                                        "games_with_an_explicit_hero_frozen_tag": raw_frozen_games},
        "new_policy_dataset": {"self_decision_rows": len(new_rows),
                               "distinct_games": len({row["game_id"] for row in new_rows.values()}),
                               "fields": distribution([row["state"] for row in new_rows.values()])},
    }
    games_forty = {row["game_id"] for row in new_rows.values()
                   if any(row["state"][seat].get("hero_max_health") not in (None, 30) for seat in SEATS)}
    summary["new_policy_dataset"]["games_with_a_maximum_other_than_30"] = len(games_forty)
    chosen_power = [row for row in new_rows.values() if row["legal_actions"][row["chosen_action_index"]]["type"] == "HERO_POWER"]
    summary["new_policy_dataset"]["chosen_hero_power_rows"] = {
        "rows": len(chosen_power),
        "self_ready_state": dict(Counter(str(row["state"]["self_player"].get("hero_power_ready")) for row in chosen_power)),
    }

    value_states = [json.loads(line)["state"] for path in sorted(value_dir.glob("*.jsonl"))
                    for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary["new_value_dataset"] = {"positions": len(value_states), "fields": distribution([normalized(s) for s in value_states])}

    if args.old_policy_dir and args.old_policy_dir.is_dir():
        old_rows = read_rows(args.old_policy_dir)
        common = sorted(old_rows.keys() & new_rows.keys())
        comparison = compare((normalized(old_rows[i]["state"]), new_rows[i]["state"]) for i in common)
        same_labels = sum(
            old_rows[i]["legal_actions"] == new_rows[i]["legal_actions"]
            and old_rows[i]["chosen_action_index"] == new_rows[i]["chosen_action_index"]
            and old_rows[i]["final_result"] == new_rows[i]["final_result"] for i in common)
        summary["old_vs_new_policy_rows"] = {
            "old_rows": len(old_rows), "new_rows": len(new_rows), "common_decision_ids": len(common),
            "only_in_old": len(old_rows.keys() - new_rows.keys()), "only_in_new": len(new_rows.keys() - old_rows.keys()),
            "actions_choices_and_results_identical": same_labels, **comparison,
            "old_dataset_fields": distribution([normalized(old_rows[i]["state"]) for i in common]),
        }
    if args.canonical_baseline_dir and args.canonical_baseline_dir.is_dir():
        # Rows written by the code before this change (canonical at that time) must still pass the strict validator.
        baseline = load_examples(args.canonical_baseline_dir)
        summary["rows_written_by_the_previous_code_still_validate"] = {
            "rows": len(baseline), "carry_hero_max_health": sum("hero_max_health" in row["state"]["self_player"] for row in baseline)}

    if args.live_dir and args.live_dir.is_dir():
        pairs, replays_identical, recordings = [], 0, 0
        for directory in sorted(p for p in args.live_dir.glob("*/*") if (p / "slice.log").exists()):
            recorded = [json.loads(row) for row in (directory / "snapshots.jsonl").read_text(encoding="utf-8").splitlines() if row.strip()]
            first = replay_game(directory, catalog)
            second = replay_game(directory, catalog)
            target = args.workdir / "live" / directory.parent.name / directory.name  # input for the readiness analyzer
            target.mkdir(parents=True)
            (target / "meta.json").write_bytes((directory / "meta.json").read_bytes())
            lines = [snapshot.to_json() for snapshot in first]
            (target / "snapshots.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            recordings += 1
            replays_identical += int([s.state_hash for s in first] == [s.state_hash for s in second])
            if len(first) == len(recorded):
                pairs.extend((normalized(old["state"]), new.state) for old, new in zip(recorded, first, strict=True))
        summary["live_replay_vs_recorded_snapshots"] = {
            "recordings": recordings, "replays_deterministic": replays_identical, **compare(pairs),
            "note": "recorded hashes differ from replayed hashes by construction: the extractor now adds the fields above",
        }

    text = json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False)
    if args.summary:
        args.summary.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
