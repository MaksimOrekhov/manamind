"""Run the extractor over Power.log files and write a new, versioned output directory."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games

from . import EXTRACTOR_VERSION, GAME_SUMMARY_SCHEMA, MANIFEST_SCHEMA
from .extract import VERSIONS, extract_game
from .privacy import PrivacyError, collect_sentinels, scan_files
from .schema import validate_observation
from .support import DEFAULT_REGISTRY, ScopeResolver, file_sha256, load_inventory


def dumps(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def collect_games(inputs: list[Path], source_kind: str | None = None) -> tuple[list[tuple[str, list[str], str]], list[str]]:
    """(start_key, lines, source_kind) per distinct game, sorted by key; plus all lines read."""
    files: list[Path] = []
    for item in inputs:
        item = Path(item)
        if item.is_dir():
            files.extend(sorted(p for p in item.rglob("*.log") if not any(
                part.startswith(".") for part in p.relative_to(item).parts)))
        else:
            files.append(item)
    best: dict[str, tuple[bool, int, list[str], str]] = {}
    all_lines: list[str] = []
    for path in files:
        lines = read_complete_lines(path)
        all_lines.extend(lines)
        sections = split_games(lines)
        kind = source_kind or ("COLLECTED_SLICE" if len(sections) == 1 else "RAW_POWER_LOG")
        for section in sections:
            info = inspect_segment(section)
            key = info.start_key or f"nokey-{len(best)}"
            rank = (info.complete_index is not None, len(section))
            if key not in best or rank > best[key][:2]:
                best[key] = (rank[0], rank[1], section, kind)
    games = [(key, value[2], value[3]) for key, value in sorted(best.items())]
    return games, all_lines


def summarize(observations: list[dict]) -> dict:
    """Aggregate counts only; nothing here can carry a name or an identity."""
    roles = Counter(o["subject"]["role"] for o in observations)
    tiers = Counter(o["attribution_summary"]["tier"] for o in observations)
    states = Counter(o["support_detection"]["subject_support_state"] for o in observations)
    confounders = Counter(c["kind"] for o in observations for c in o["confounders"])
    fact_kinds = Counter(f["kind"] for o in observations for f in o["facts"])
    bases = Counter(f["attribution"]["basis"] for o in observations for f in o["facts"])
    inference_kinds = Counter(i["kind"] for o in observations for i in o["inferences"])
    return {
        "observations": len(observations),
        "distinct_subject_cards": len({o["subject"]["card_id"] for o in observations}),
        "by_role": dict(sorted(roles.items())),
        "attribution_tier": dict(sorted(tiers.items())),
        "ambiguous_observations": sum(1 for o in observations if o["attribution_summary"]["ambiguous"]),
        "unconfounded_observations": sum(1 for o in observations if not o["confounders"]),
        "subject_support_state": dict(sorted(states.items())),
        "confounder_kinds": dict(sorted(confounders.items())),
        "fact_kinds": dict(sorted(fact_kinds.items())),
        "fact_attribution_basis": dict(sorted(bases.items())),
        "inference_kinds": dict(sorted(inference_kinds.items())),
        "legality_facts": fact_kinds.get("TARGET_LEGALITY", 0),
        "observations_with_hidden_facts": sum(1 for o in observations if o["privacy"]["contains_offline_only_hidden"]),
    }


def run_extraction(inputs: list[Path], output_dir: Path, *, inventory_path: Path | None = None,
                   catalog_path: Path | None = None, registry_path: Path | None = DEFAULT_REGISTRY,
                   metadata_path: Path | None = None, include_secondary: bool = False,
                   max_control_samples: int = 3, source_kind: str | None = None,
                   extractor_version: str = EXTRACTOR_VERSION) -> dict:
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError("OUTPUT_EXISTS")
    inventory = load_inventory(inventory_path)
    scope = ScopeResolver.from_files(registry_path, metadata_path)
    catalog = CardCatalog.from_json(catalog_path) if catalog_path else CardCatalog()
    catalog_sha = file_sha256(Path(catalog_path)) if catalog_path else file_sha256(None)

    games, all_lines = collect_games([Path(p) for p in inputs], source_kind)
    control_counts: dict[str, int] = {}
    observations: list[dict] = []
    summaries: list[dict] = []
    for _key, lines, kind in games:
        result = extract_game(
            lines, source_kind=kind, inventory=inventory, scope=scope, catalog=catalog, catalog_sha256=catalog_sha,
            include_secondary=include_secondary, control_counts=control_counts,
            max_control_samples=max_control_samples, extractor_version=extractor_version,
        )
        result.summary["schema"] = GAME_SUMMARY_SCHEMA
        summaries.append(result.summary)
        observations.extend(result.observations)

    for observation in observations:
        validate_observation(observation)

    output_dir.mkdir(parents=True)
    obs_path, games_path, manifest_path = (output_dir / n for n in ("observations.jsonl", "games.jsonl", "manifest.json"))
    _write_lines(obs_path, [dumps(o) for o in observations])
    _write_lines(games_path, [dumps(s) for s in summaries])

    skipped = Counter(s["reason"] for s in summaries if s["status"] == "SKIPPED")
    walker_totals: Counter = Counter()
    for summary in summaries:
        walker_totals.update(summary.get("walker_stats", {}))
        walker_totals.update({f"root_{k}": v for k, v in summary.get("root_blocks_by_type", {}).items()})
    manifest = {
        "schema": MANIFEST_SCHEMA, "extractor_version": extractor_version, "parser_versions": VERSIONS,
        "support": {"inventory_id": inventory.inventory_id, "inventory_sha256": inventory.sha256,
                    "basis": inventory.basis},
        "catalog_sha256": catalog_sha, "include_secondary": include_secondary,
        "max_control_samples": max_control_samples,
        "games": {"seen": len(summaries), "processed": sum(1 for s in summaries if s["status"] == "PROCESSED"),
                  "skipped": dict(sorted(skipped.items()))},
        "windows": sum(s["windows"] for s in summaries),
        "walker_totals": dict(sorted(walker_totals.items())),
        "summary": summarize(observations),
    }
    sentinels = collect_sentinels(all_lines)
    scan = scan_files([obs_path, games_path], sentinels)
    manifest["privacy_scan"] = scan
    _write_lines(manifest_path, [dumps(manifest)])
    leaks = scan["leaks"] + scan_files([manifest_path], sentinels)["leaks"]
    if leaks:
        for path in (obs_path, games_path, manifest_path):
            path.unlink()
        output_dir.rmdir()
        raise PrivacyError("PRIVACY_SCAN_FAILED")
    return manifest


def _write_lines(path: Path, lines: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for line in lines:
            file.write(line + "\n")
