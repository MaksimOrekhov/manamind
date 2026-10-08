"""ENGINE-STATE-IMPORT-0: read-only readiness diagnostics for real player-visible positions.

Reads already-sanitized corpora (policy decision records, live snapshots, Value examples). It never parses
Power.log, never builds a native session and never writes into the input directories.
"""
import argparse
import json
import sys
from pathlib import Path

from manamind.integrations.manaengine.state_import_capability import CapabilityIndex
from manamind.integrations.manaengine.state_import_corpus import (
    aggregate, analyze_corpus, describe_sample, dumps, read_live_positions, read_policy_positions, read_value_positions, select_sample,
)
from manamind.integrations.manaengine.state_import_readiness import (
    ANALYZER_VERSION, BLOCKER_SPECS, FIELD_PROVENANCE, NATIVE_STATE_CONTRACT, analyze_position, canonical_dumps,
)

DEFAULT_SEED = 20261008
READERS = {"POLICY_DECISION": read_policy_positions, "LIVE_SNAPSHOT": read_live_positions, "VALUE_EXAMPLE": read_value_positions}


def _fresh_directory(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()) and not overwrite:
        raise SystemExit(f"refusing to write into non-empty {path}; choose a new path")
    path.mkdir(parents=True, exist_ok=True)


def _without_ranking(metrics: dict) -> dict:
    return {key: value for key, value in metrics.items() if key != "ranking"}


def analyze_single(path: Path, capability: CapabilityIndex) -> dict:
    """One JSON file: a GameState mapping, a live snapshot (has ``state``) or a policy record (has ``legal_actions``)."""
    record = json.loads(path.read_text(encoding="utf-8"))
    state = record.get("state", record)
    action = None
    if "legal_actions" in record and "chosen_action_index" in record:
        action = record["legal_actions"][int(record["chosen_action_index"])]
    envelope = {key: record.get(key) for key in ("status", "game_type", "format", "phase")} if "phase" in record else None
    return analyze_position(state, capability, action=action, snapshot=envelope).to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-dir", type=Path, help="ML-1B policy decision records (*.jsonl)")
    parser.add_argument("--live-dir", type=Path, help="LIVE-0 recording root (<session>/<game>/snapshots.jsonl)")
    parser.add_argument("--value-dir", type=Path, help="Value examples (*.jsonl); entity-order hand, legacy visibility")
    parser.add_argument("--state-json", type=Path, help="analyze one JSON file and print its diagnostic")
    parser.add_argument("--sample-size", type=int, default=48)
    parser.add_argument("--per-game-cap", type=int, default=3)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", type=Path, help="local per-position diagnostics (use a git-ignored data/ path)")
    parser.add_argument("--report-dir", type=Path, help="sanitized aggregate reports: coverage.json and blockers.json")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    capability = CapabilityIndex()
    if args.state_json:
        print(canonical_dumps(analyze_single(args.state_json, capability)))
        return 0
    selected = {"POLICY_DECISION": args.policy_dir, "LIVE_SNAPSHOT": args.live_dir, "VALUE_EXAMPLE": args.value_dir}
    selected = {kind: path for kind, path in selected.items() if path}
    if not selected:
        parser.error("give at least one of --policy-dir, --live-dir, --value-dir, or --state-json")

    availability, corpora, corpus_rankings, analyzed_by_kind = {}, {}, {}, {}
    for kind, path in selected.items():
        if not path.is_dir():
            availability[kind] = {"available": False, "reason": "directory does not exist"}
            continue
        positions, info = READERS[kind](path)
        decisions = [p for p in positions if p.is_self_decision and (p.envelope is None or p.envelope.get("status") == "READY")]
        analyzed = analyze_corpus(decisions, capability)
        analyzed_by_kind[kind] = analyzed
        metrics = aggregate(analyzed)
        availability[kind] = {"available": True, **info, "records_read": len(positions), "self_decision_positions": len(decisions),
                              "non_decision_or_not_ready_records": len(positions) - len(decisions), "distinct_games": metrics["unique_games"]}
        corpora[kind] = _without_ranking(metrics)
        corpus_rankings[kind] = metrics["ranking"]
    primary_kind = next((kind for kind in ("POLICY_DECISION", "LIVE_SNAPSHOT", "VALUE_EXAMPLE") if kind in analyzed_by_kind), None)
    primary, sample_analysis = None, []
    if primary_kind:
        pool = [a.position for a in analyzed_by_kind[primary_kind]]
        sample = select_sample(pool, args.sample_size, args.seed, args.per_game_cap)
        sample_analysis = analyze_corpus(sample, capability)
        sample_metrics = aggregate(sample_analysis)
        primary = {"source_kind": primary_kind, "composition": describe_sample(sample), "metrics": _without_ranking(sample_metrics),
                   "ranking": sample_metrics["ranking"]}

    strata = {}
    if primary_kind:
        groups: dict[str, list] = {}
        for item in analyzed_by_kind[primary_kind]:
            groups.setdefault(item.detail["hero_power"]["SELF"]["status"], []).append(item)
        for status, items in sorted(groups.items()):
            subset = aggregate(items)
            strata[status] = {key: subset[key] for key in ("unique_games", "decision_positions", "blocked_by", "next_action_assessment")}
            strata[status]["top6_blockers_below_universal"] = subset["top10_blockers_below_universal_by_distinct_positions"][:6]

    coverage = {
        "schema": "manamind.state_import0.coverage/1", "analyzer_version": ANALYZER_VERSION, "seed": args.seed, "sample_size_requested": args.sample_size,
        "capability": capability.summary(), "native_state_contract": NATIVE_STATE_CONTRACT, "extractor_field_provenance": FIELD_PROVENANCE,
        "data_availability": availability, "primary_sample": None if primary is None else {k: v for k, v in primary.items() if k != "ranking"},
        "full_corpora": corpora,
        "primary_corpus_by_self_hero_power_status": strata,
        "interpretation": ("Positions from one game are correlated; the game is the independent unit. Percentages over positions are not "
                           "additive across overlapping blocker categories. Nothing here is a rules, training or hydration admission."),
    }
    blockers = {
        "schema": "manamind.state_import0.blockers/1", "analyzer_version": ANALYZER_VERSION,
        "catalog": {code: {"category": spec.category.value, "subsystem": spec.subsystem, "axis": spec.axis, "nature": spec.nature,
                           "family": spec.family, "recommended_resolution": spec.resolution, "description": spec.description}
                    for code, spec in sorted(BLOCKER_SPECS.items())},
        "primary_sample_ranking": None if primary is None else primary["ranking"],
        "full_corpus_rankings": corpus_rankings,
    }
    if args.report_dir:
        _fresh_directory(args.report_dir, args.overwrite)
        (args.report_dir / "coverage.json").write_text(dumps(coverage), encoding="utf-8", newline="\n")
        (args.report_dir / "blockers.json").write_text(dumps(blockers), encoding="utf-8", newline="\n")
    if args.output_dir:
        _fresh_directory(args.output_dir, args.overwrite)
        with (args.output_dir / "sample_positions.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for item in sample_analysis:
                handle.write(canonical_dumps({"position": item.position.position_id, "source_kind": item.position.source_kind, "diagnostic": item.detail}) + "\n")
        for kind, analyzed in analyzed_by_kind.items():
            with (args.output_dir / f"all_{kind.lower()}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
                for item in analyzed:
                    handle.write(canonical_dumps({"position": item.position.position_id, "diagnostic": item.detail}) + "\n")
    print(dumps({"availability": availability, "primary_sample": None if primary is None else primary["composition"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
