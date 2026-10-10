"""One-command local runtime: trusted LIVE ranking, recording and independent raw collection."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import warnings
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.cards.catalog import CardCatalog
from manamind.live.recorder import Recorder
from manamind.live.recommendation import (
    PolicyRecommender, Recommendation, RecommendationUnavailable, render_recommendation,
)
from manamind.live.prediction_journal import PredictionJournal
from manamind.live.runner import LiveRunner
from manamind.live.session import LiveSession
from manamind.live.trust import LiveStatus, StatusEvent

from collect_power_logs import Collector

DEFAULT_LOGS_ROOT = Path("D:/Games/Hearthstone/Logs")  # CLI-only local default; override via flag/env.
POLICY_V2_CHECKPOINT = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
POLICY_V2_SHA256 = "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"


class UnifiedRuntime:
    """Poll the two existing lanes; all model and collection state remain separate."""

    def __init__(self, live: LiveRunner, collector: Collector, recommender: PolicyRecommender | None,
                 *, emit: Callable[[str], None] = print, collector_seconds: float = 5.0,
                 journal: PredictionJournal | None = None,
                 on_recommendation: Callable[[Recommendation], None] | None = None) -> None:
        if collector_seconds <= 0:
            raise ValueError("Collector poll interval must be positive")
        self.live = live
        self.collector = collector
        self.recommender = recommender
        self.recommender_unavailable = None
        self.emit = emit
        self.journal = journal
        self.on_recommendation = on_recommendation
        self.collector_seconds = collector_seconds
        self.next_collect = float("-inf")
        self.active_identity: tuple | None = None
        self.active_snapshot = None
        self.attempted_identity: tuple | None = None
        self.live_failed = False
        self.latencies_ms: list[float] = []
        self.decisions_scored = 0

    def _invalidate(self, reason: str = "DECISION_CHANGED") -> None:
        if self.active_identity is not None:
            if self.journal is not None:
                # Keep the exact displayed snapshot; the session may already have cleared it.
                snapshot = self.active_snapshot
                if snapshot is not None:
                    try:
                        self.journal.invalidation(snapshot, reason)
                    except OSError as error:
                        self.emit(f"prediction journal warning: {type(error).__name__}")
            self.emit(f"recommendation #{self.active_identity[1]} invalidated")
            self.active_identity = None
            self.active_snapshot = None

    def _events(self, events) -> None:
        for event in events:
            if isinstance(event, StatusEvent):
                reason = f" ({event.reason})" if event.reason else ""
                self.emit(f"status: {event.status.value}{reason}")
        snap = self.live.session.current_snapshot
        if (self.active_identity is not None
                and (snap is None or snap.game_key != self.active_identity[0]
                     or snap.seq != self.active_identity[1]
                     or snap.decision["options_id"] != self.active_identity[2]
                     or snap.state_hash != self.active_identity[3]
                     or self.live.session.status is not LiveStatus.READY)):
            status = self.live.session.status
            reason = "GAME_OVER" if status is LiveStatus.GAME_OVER else (
                f"TRUST_LOST:{status.value}:{self.live.session.reason or 'UNKNOWN'}"
                if status is not LiveStatus.READY else "DECISION_CHANGED"
            )
            self._invalidate(reason)

    def step(self, now: float | None = None) -> None:
        if now is None:
            now = time.monotonic()
        if not self.live_failed:
            try:
                events = self.live.step()
                self._events(events)
                snap = self.live.session.current_snapshot
                identity = ((snap.game_key, snap.seq, snap.decision["options_id"], snap.state_hash)
                            if snap is not None else None)
                if (self.recommender is not None and snap is not None
                        and identity != self.attempted_identity and self.active_identity is None):
                    self.attempted_identity = identity
                    try:
                        result = self.recommender.score(snap, self.live.session)
                        # Read any lines that appeared during inference before displaying the result.
                        self._events(self.live.step())
                        if self.live.session.current_snapshot is snap and self.live.session.status is LiveStatus.READY:
                            self.emit(render_recommendation(result))
                            self.active_identity = result.identity
                            self.active_snapshot = snap
                            if self.journal is not None:
                                try:
                                    self.journal.recommendation(snap, result, self.recommender.checkpoint_sha256)
                                except OSError as error:
                                    self.emit(f"prediction journal warning: {type(error).__name__}")
                            if self.on_recommendation is not None:
                                self.on_recommendation(result)
                            self.latencies_ms.append(result.latency_ms)
                            self.decisions_scored += 1
                        else:
                            self.emit("no recommendation: DECISION_CHANGED_DURING_INFERENCE")
                            if self.journal is not None:
                                try:
                                    self.journal.discarded(snap, "DECISION_CHANGED_DURING_INFERENCE")
                                except OSError as error:
                                    self.emit(f"prediction journal warning: {type(error).__name__}")
                    except RecommendationUnavailable as error:
                        self.emit(f"no recommendation: {error}")
                        if self.journal is not None:
                            try:
                                self.journal.unavailable(snap, str(error))
                            except OSError as journal_error:
                                self.emit(f"prediction journal warning: {type(journal_error).__name__}")
            except Exception as error:  # no raw exception text from private logs
                self._invalidate()
                self.live_failed = True
                self.emit(f"LIVE warning: {type(error).__name__}; recommendations disabled")
        if now >= self.next_collect:
            self.next_collect = now + self.collector_seconds
            try:
                failures_before = self.collector.stats.parse_failures
                self.collector.scan_once()
                if self.collector.stats.parse_failures > failures_before:
                    self.emit("collection warning: failed scan or import; will retry")
            except Exception as error:
                self.emit(f"collection warning: {type(error).__name__}; will retry")

    def finish(self) -> None:
        self._invalidate("APP_STOP")
        try:
            self.collector.write_summary()
        except Exception as error:
            self.emit(f"collection summary warning: {type(error).__name__}")
        stats = self.collector.stats
        self.emit(f"session: {self.decisions_scored} recommendations; "
                  f"{stats.matches_imported} matches retained; {stats.parse_failures} collection failures")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-root", type=Path,
                        default=Path(os.environ.get("MANAMIND_HEARTHSTONE_LOGS", DEFAULT_LOGS_ROOT)))
    parser.add_argument("--checkpoint", type=Path, default=POLICY_V2_CHECKPOINT)
    parser.add_argument("--checkpoint-sha256", default=POLICY_V2_SHA256,
                        help="SHA-256 pin for the frozen Policy v2 checkpoint")
    parser.add_argument("--data-root", type=Path,
                        default=Path(os.environ.get("MANAMIND_DATA_ROOT", ROOT / "data")))
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--poll-ms", type=int, default=50)
    parser.add_argument("--collector-seconds", type=float, default=5.0)
    parser.add_argument("--ui", action="store_true", help="Show the Windows always-on-top recommendation panel")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.poll_ms < 10 or args.collector_seconds <= 0:
        raise SystemExit("poll-ms must be >=10 and collector-seconds must be positive")
    # hslog warnings and exceptions may contain raw log text or player identifiers.
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    catalog = CardCatalog.from_json(args.cards)
    recommender_error = None
    try:
        recommender = PolicyRecommender(args.checkpoint, expected_sha256=args.checkpoint_sha256)
        recommender.require_catalog(catalog)
    except Exception as error:
        recommender = None
        recommender_error = type(error).__name__
        print(f"recommendation warning: {type(error).__name__}; collection remains active", flush=True)
    session = LiveSession(catalog)
    recorder = Recorder(args.data_root / "raw/live", catalog_path=args.cards)
    live = LiveRunner(args.logs_root, session, recorder)
    collector = Collector(args.logs_root, args.data_root / "raw/collected",
                          args.data_root / "processed_real", args.cards)
    runtime = UnifiedRuntime(live, collector, recommender, emit=lambda text: print(text, flush=True),
                             collector_seconds=args.collector_seconds,
                             journal=PredictionJournal(args.data_root / "raw/live/prediction_journal.jsonl"))
    runtime.recommender_unavailable = recommender_error
    print("ManaMind experimental read-only policy. Ctrl+C to stop.", flush=True)
    runtime.emit(f"status: {session.status.value}")
    if args.ui:
        try:
            from manamind.live.panel import launch_overlay

            launch_overlay(runtime, args.cards, args.poll_ms)
        except KeyboardInterrupt:
            pass
        finally:
            runtime.finish()
        return 0
    try:
        while True:
            runtime.step()
            time.sleep(args.poll_ms / 1000)
    except KeyboardInterrupt:
        return 0
    finally:
        runtime.finish()


if __name__ == "__main__":
    sys.exit(main())
