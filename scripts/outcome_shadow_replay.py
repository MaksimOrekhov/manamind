"""Replay LIVE recordings through the real ``UnifiedRuntime`` with the outcome shadow off and on (ACTION-OUTCOME-2).

Each recording (``slice.log`` + ``tail_trace.jsonl`` written by the LIVE recorder) is fed to a ``LiveSession`` exactly as
the tail fed it - the same read batches, the same recorded monotonic milliseconds - and the unchanged ``UnifiedRuntime``
is stepped over it twice: once without and once with ``OutcomeShadow``. The two runs are then compared on everything
the player can see or the journal records: emitted text, presentation events (rankings with scores), state hashes,
RECOMMENDATION / INVALIDATION rows. The shadow rows of the second run are written to ``--out-dir`` for the analyzer.

  python scripts/outcome_shadow_replay.py <recording dir> [...] --data-root <data> --out-dir <new dir> --report-json <new file>
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

import run_manamind  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.outcome.live_shadow import OutcomeShadow, load_texts  # noqa: E402
from manamind.live.prediction_journal import PredictionJournal  # noqa: E402
from manamind.live.recommendation import PolicyRecommender  # noqa: E402
from manamind.live.replay import recorded_hashes  # noqa: E402
from manamind.live.session import LiveSession  # noqa: E402
from manamind.live.snapshot import Snapshot  # noqa: E402
from manamind.live.trust import ModePolicy  # noqa: E402

VOLATILE_KEYS = {"at_utc", "recommended_at_utc", "invalidated_at_utc", "us", "elapsed_ms"}


@dataclass
class _CollectorStats:
    parse_failures: int = 0
    matches_imported: int = 0


class _NoCollector:
    stats = _CollectorStats()

    def scan_once(self) -> None:
        pass

    def write_summary(self) -> None:
        pass


class RecordedLive:
    """Stands in for ``LiveRunner``: one runtime step reads one recorded batch (feed + tick).

    ``UnifiedRuntime`` polls a second time right after inference to catch lines written meanwhile. A recording has
    no wall clock for that window, so the replay models "nothing arrived during inference" (the same convention as
    ``replay_live_recommendations.replay_once``): the second poll of a runtime step returns no events.
    """

    def __init__(self, directory: Path, catalog: CardCatalog) -> None:
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        self.session = LiveSession(catalog, ModePolicy(frozenset(meta.get("extra_game_types", []))))
        self.lines = (directory / "slice.log").read_text(encoding="utf-8").splitlines()
        self.trace = [json.loads(x) for x in (directory / "tail_trace.jsonl").read_text(encoding="utf-8").splitlines()]
        self.cursor = 0
        self.index = 0
        self.fresh = False
        self.hashes: list[str] = []

    @property
    def exhausted(self) -> bool:
        return self.cursor >= len(self.trace)

    def step(self) -> list:
        if self.exhausted or not self.fresh:
            return []
        self.fresh = False
        row = self.trace[self.cursor]
        self.cursor += 1
        count = int(row["n"])
        chunk = self.lines[self.index:self.index + count]
        self.index += count
        events = self.session.feed(chunk, int(row["t"]), catchup=bool(row.get("catchup"))) if count else []
        events += self.session.tick(int(row["t"]))
        self.hashes += [event.state_hash for event in events if isinstance(event, Snapshot)]
        return events


def _strip(value):
    """Drop measurements and timestamps so two replays of the same input compare equal."""
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def _event_view(event) -> tuple:
    recommendation = getattr(event, "recommendation", None)
    ranked = None if recommendation is None else (
        recommendation.identity, recommendation.turn, recommendation.menu_size,
        tuple((item.index, item.score, json.dumps(item.action, sort_keys=True)) for item in recommendation.ranked))
    return (event.kind, getattr(event, "status", None), getattr(event, "reason", None), ranked)


@dataclass
class RunResult:
    emitted: list[str] = field(default_factory=list)
    events: list[tuple] = field(default_factory=list)
    hashes: list[str] = field(default_factory=list)
    journal: list[dict] = field(default_factory=list)
    shadow_rows: list[dict] = field(default_factory=list)
    strategy_rows: list[dict] = field(default_factory=list)
    policy_latency_ms: list[float] = field(default_factory=list)
    decision_step_ms: list[float] = field(default_factory=list)
    scored: int = 0
    shadow_summary: str | None = None
    strategy_summary: str | None = None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_runtime(directory: Path, recommender: PolicyRecommender, texts, work: Path, *, shadow: bool,
                budget_ms: float = 250.0, shadow_factory=None, strategy=None) -> RunResult:
    """One pass of the unchanged runtime over a recording; ``work`` is a fresh directory for the journal files."""
    live = RecordedLive(directory, recommender.encoder.catalog)
    result = RunResult()
    journal = PredictionJournal(work / "prediction_journal.jsonl")
    outcome = None
    if shadow:
        outcome = shadow_factory() if shadow_factory else OutcomeShadow(texts, budget_ms=budget_ms)
    runtime = run_manamind.UnifiedRuntime(
        live, _NoCollector(), recommender, emit=result.emitted.append, collector_seconds=3600, journal=journal,
        on_event=lambda event: result.events.append(_event_view(event)), outcome_shadow=outcome,
        strategy_shadow=strategy)
    while not live.exhausted:
        before = runtime.decisions_scored
        live.fresh = True
        started = time.perf_counter_ns()
        runtime.step(now=0.0)
        if runtime.decisions_scored > before:
            result.decision_step_ms.append((time.perf_counter_ns() - started) / 1e6)
    runtime.finish()
    result.scored = runtime.decisions_scored
    result.policy_latency_ms = list(runtime.latencies_ms)
    result.hashes = live.hashes
    result.journal = _strip(read_jsonl(journal.path))
    result.shadow_rows = read_jsonl(journal.shadow_path)
    result.strategy_rows = read_jsonl(journal.strategy_path)
    if strategy is not None:
        result.strategy_summary = next((x for x in result.emitted if x.startswith("strategy shadow:")), None)
        result.emitted = [line for line in result.emitted if not line.startswith("strategy shadow:")]
    if outcome is not None:
        result.shadow_summary = next((x for x in result.emitted if x.startswith("outcome shadow:")), None)
        # The diagnostics line is the one deliberate difference in the output; the comparison ignores it.
        result.emitted = [line for line in result.emitted if not line.startswith("outcome shadow:")]
    return result


def compare_runs(directory: Path, plain: RunResult, shadowed: RunResult) -> dict:
    """Everything the shadow must leave untouched, as booleans, plus the counts they were checked on."""
    recorded = recorded_hashes(directory)
    plain_journal = [row for row in plain.journal]
    return {
        "emitted_text_identical": plain.emitted == shadowed.emitted,
        "presentation_events_identical": plain.events == shadowed.events,
        "state_hashes_identical": plain.hashes == shadowed.hashes,
        # Informational, not a gate: recordings made before a state-schema addition (hero_max_health, ...) keep the
        # hashes of the code that wrote them, and the unchanged main branch replays them to the same new hashes.
        "info_state_hashes_match_recording": shadowed.hashes == recorded,
        "journal_rows_identical": plain_journal == shadowed.journal,
        "shadow_file_absent_when_off": not plain.shadow_rows,
        "scored_identical": plain.scored == shadowed.scored,
        "decisions_scored": shadowed.scored,
        "snapshots": len(shadowed.hashes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--checkpoint-sha256", default=run_manamind.POLICY_V2_SHA256)
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="NEW directory: <out-dir>/<recording key>/outcome_shadow.jsonl for the analyzer")
    parser.add_argument("--report-json", type=Path, required=True, help="NEW file")
    parser.add_argument("--budget-ms", type=float, default=250.0)
    args = parser.parse_args(argv)
    if args.out_dir.exists() or args.report_json.exists():
        raise SystemExit("refusing to overwrite: choose new --out-dir / --report-json paths")
    checkpoint = args.checkpoint or args.data_root / "processed_policy_ml2a/seed42_v2/policy.pt"
    cards = ROOT / "data/cards/standard_current_enUS.json"
    catalog = CardCatalog.from_json(cards)
    recommender = PolicyRecommender(checkpoint, expected_sha256=args.checkpoint_sha256)
    recommender.require_catalog(catalog)
    texts = load_texts(ROOT)
    rows, latencies = [], {"plain": [], "shadowed": [], "plain_step": [], "shadowed_step": [], "shadow": []}
    for directory in args.recordings:
        with tempfile.TemporaryDirectory() as scratch:
            plain = run_runtime(directory, recommender, texts, Path(scratch) / "off", shadow=False)
            shadowed = run_runtime(directory, recommender, texts, Path(scratch) / "on", shadow=True,
                                   budget_ms=args.budget_ms)
            again = run_runtime(directory, recommender, texts, Path(scratch) / "on2", shadow=True,
                                budget_ms=args.budget_ms)
        compared = compare_runs(directory, plain, shadowed)
        compared["shadow_rows_reproducible"] = _strip(shadowed.shadow_rows) == _strip(again.shadow_rows)
        compared["shadow_rows"] = len(shadowed.shadow_rows)
        compared["recording"] = f"{directory.parent.name}/{directory.name}"
        rows.append(compared)
        latencies["plain"] += plain.policy_latency_ms
        latencies["shadowed"] += shadowed.policy_latency_ms
        latencies["plain_step"] += plain.decision_step_ms
        latencies["shadowed_step"] += shadowed.decision_step_ms
        latencies["shadow"] += [r["elapsed_ms"] for r in shadowed.shadow_rows if r["event"] == "OUTCOME_SHADOW"]
        if shadowed.shadow_rows:
            target = args.out_dir / directory.name
            target.mkdir(parents=True)
            (target / "outcome_shadow.jsonl").write_text(
                "".join(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
                        for r in shadowed.shadow_rows), encoding="utf-8", newline="\n")
    def pct(values):
        return ({"n": len(values), "median": round(float(np.percentile(values, 50)), 3),
                 "p95": round(float(np.percentile(values, 95)), 3), "max": round(max(values), 3)} if values else None)
    summary = {"recordings": len(rows), "per_recording": rows,
               "all_identical": all(all(v for k, v in row.items() if isinstance(v, bool) and not k.startswith("info_"))
                                    for row in rows),
               "recordings_matching_their_recorded_hashes": sum(row["info_state_hashes_match_recording"] for row in rows),
               "timing_ms": {name: pct(values) for name, values in latencies.items()}}
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "per_recording"}, sort_keys=True))
    return 0 if summary["all_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
