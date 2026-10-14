"""One-command local runtime: trusted LIVE ranking, recording and independent raw collection."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import threading
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
from manamind.outcome.live_shadow import OutcomeShadow, ShadowFailed, load_texts
from manamind.policy_shadow.journal import ModelShadowJournal
from manamind.policy_shadow.models import load_models
from manamind.policy_shadow.shadow import ModelShadow
from manamind.policy_shadow.worker import ModelShadowWorker
from manamind.strategy.live_shadow import StrategyFailed, StrategyShadow
from manamind.live.prediction_journal import PredictionJournal
from manamind.live.presentation import PresentationEvent
from manamind.live.runner import LiveRunner
from manamind.live.session import LiveSession
from manamind.live.trust import LiveStatus, StatusEvent

from collect_power_logs import Collector, safe_failure_code

DEFAULT_LOGS_ROOT = Path("D:/Games/Hearthstone/Logs")  # CLI-only local default; override via flag/env.
POLICY_V2_CHECKPOINT = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
POLICY_V2_SHA256 = "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"
# ML-POLICY-V3-1 experiment checkpoints for --model-shadow (local, ignored data; pinned by digest, never auto-promoted).
RETRAINED_V2_CHECKPOINT = ROOT / "data/processed_policy_v3/experiment_1/final/architecturev2_seed42/policy.pt"
RETRAINED_V2_SHA256 = "9358f932fc7846d6a436e2a1e6c7ff6cffda1f2929fac5521710f973e14a05e3"
POLICY_V3_CHECKPOINT = ROOT / "data/processed_policy_v3/experiment_1/final/architecturev3_seed42/policy.pt"
POLICY_V3_SHA256 = "d874d196d9c2f1e12c6d697ad2de57883a29352976dbb1ee9dbd6ba63af84f82"


class UnifiedRuntime:
    """Poll the two existing lanes; all model and collection state remain separate."""

    def __init__(self, live: LiveRunner, collector: Collector, recommender: PolicyRecommender | None,
                 *, emit: Callable[[str], None] = print, collector_seconds: float = 5.0,
                 journal: PredictionJournal | None = None,
                 on_recommendation: Callable[[Recommendation], None] | None = None,
                 on_event: Callable[[PresentationEvent], None] | None = None,
                 outcome_shadow: OutcomeShadow | None = None,
                 strategy_shadow: StrategyShadow | None = None,
                 model_shadow: ModelShadowWorker | None = None) -> None:
        if collector_seconds <= 0:
            raise ValueError("Collector poll interval must be positive")
        self.live = live
        self.collector = collector
        self.recommender = recommender
        self.recommender_unavailable = None
        self.emit = emit
        self.journal = journal
        self.on_recommendation = on_recommendation
        self.on_event = on_event
        self.outcome_shadow = outcome_shadow
        self.shadow_snapshot = None        # the displayed decision whose shadow row is in the shadow journal
        self.strategy_shadow = strategy_shadow
        self.strategy_snapshot = None      # the displayed decision whose row is in the strategy journal
        self.model_shadow = model_shadow   # background worker: hand-over only, it never touches the Policy path
        self.collector_seconds = collector_seconds
        self.next_collect = float("-inf")
        self.active_identity: tuple | None = None
        self.active_snapshot = None
        self.active_recommendation = None
        self.active_journaled = False
        self.active_feedback_saved = False
        self._decision_lock = threading.RLock()
        self.attempted_identity: tuple | None = None
        self.live_failed = False
        self.latencies_ms: list[float] = []
        self.decisions_scored = 0
        self._collection_warning_attempts: dict[tuple[str, str], int] = {}

    def _collection_warning(self, stage: str, error: Exception) -> None:
        code = safe_failure_code(error)
        key = (stage, code)
        attempts = self._collection_warning_attempts.get(key, 0) + 1
        self._collection_warning_attempts[key] = attempts
        if attempts == 1 or attempts % 12 == 0:
            self.emit(f"collection warning: stage={stage} code={code} attempt={attempts}; will retry")

    def _present(self, event: PresentationEvent) -> None:
        if self.on_event is not None:
            self.on_event(event)

    def _invalidate(self, reason: str = "DECISION_CHANGED") -> None:
        with self._decision_lock:
            active_identity = self.active_identity
            snapshot = self.active_snapshot
            self.active_identity = None
            self.active_snapshot = None
            self.active_recommendation = None
            self.active_journaled = False
            self.active_feedback_saved = False
        if active_identity is not None:
            if self.journal is not None:
                # Keep the exact displayed snapshot; the session may already have cleared it.
                if snapshot is not None:
                    try:
                        self.journal.invalidation(snapshot, reason)
                    except OSError as error:
                        self.emit(f"prediction journal warning: {type(error).__name__}")
            self._model_shadow_invalidated(snapshot, reason)
            self._shadow_invalidated(reason)
            self._strategy_invalidated(reason)
            self.emit(f"recommendation #{active_identity[1]} invalidated")
        status = self.live.session.status.value
        self._present(PresentationEvent("invalidated", status=status if status != "READY" else "SYNCING", reason=reason))

    def flag_active_recommendation(self) -> bool:
        """Capture only the exact still-current recommendation; no label is inferred."""
        with self._decision_lock:
            snapshot, recommendation = self.active_snapshot, self.active_recommendation
            if (not self.active_journaled or snapshot is None or recommendation is None or self.journal is None
                    or self.live.session.current_snapshot is not snapshot
                    or self.live.session.status is not LiveStatus.READY
                    or recommendation.identity != self.active_identity):
                return False
            if self.active_feedback_saved:
                return True
            try:
                self.journal.suspicious(snapshot, recommendation, self.recommender.checkpoint_sha256)
            except (OSError, ValueError):
                return False
            self.active_feedback_saved = True
            return True

    def _model_shadow_invalidated(self, snapshot, reason: str) -> None:
        if self.model_shadow is None or snapshot is None:
            return
        try:
            self.model_shadow.invalidate(snapshot, reason)
        except Exception:                      # the model shadow must never cost the Policy path anything
            pass

    def _run_model_shadow(self, snapshot, result: Recommendation) -> None:
        """Hand the displayed decision to the background model shadow. Constant time, never raises."""
        try:
            self.model_shadow.submit(snapshot, result)
        except Exception:
            self.model_shadow.shadow.stats.failed += 1

    def _shadow_invalidated(self, reason: str) -> None:
        snapshot, self.shadow_snapshot = self.shadow_snapshot, None
        if snapshot is None or self.journal is None:
            return
        try:
            self.journal.outcome_shadow_invalidation(snapshot, reason)
        except OSError:
            self.outcome_shadow.stats.journal_failures += 1

    def _run_shadow(self, snapshot, result: Recommendation) -> None:
        """Optional read-only consequence forecast of the displayed decision. Never raises, never delays the display."""
        shadow = self.outcome_shadow
        shadow.stats.decisions += 1
        try:
            try:
                record = shadow.forecast(snapshot, result)
            except ShadowFailed as error:
                shadow.fail(error.reason)
                self._shadow_error(snapshot, error.reason)
                return
            if self.journal is not None:
                self.journal.outcome_shadow(snapshot, record)
                self.shadow_snapshot = snapshot
            shadow.count(record)
        except OSError as error:
            shadow.stats.journal_failures += 1
            self.emit(f"outcome shadow warning: {type(error).__name__}")
        except Exception:                      # the shadow must never cost the Policy path anything
            shadow.fail("SHADOW_RUNTIME_ERROR")
            self._shadow_error(snapshot, "SHADOW_RUNTIME_ERROR")

    def _shadow_error(self, snapshot, reason: str) -> None:
        if self.journal is None:
            return
        try:
            self.journal.outcome_shadow_error(snapshot, reason)
        except OSError:
            self.outcome_shadow.stats.journal_failures += 1

    def _strategy_invalidated(self, reason: str) -> None:
        snapshot, self.strategy_snapshot = self.strategy_snapshot, None
        if snapshot is None or self.journal is None:
            return
        try:
            self.journal.strategy_shadow_invalidation(snapshot, reason)
        except OSError:
            self.strategy_shadow.stats.journal_failures += 1

    def _run_strategy(self, snapshot, result: Recommendation) -> None:
        """Optional independent Strategic Scorer ranking of the displayed menu. Never raises, never changes the display."""
        shadow = self.strategy_shadow
        shadow.stats.decisions += 1
        try:
            try:
                record = shadow.score(snapshot, result)
            except StrategyFailed as error:
                shadow.fail(error.reason)
                self._strategy_error(snapshot, error.reason)
                return
            if self.journal is not None:
                self.journal.strategy_shadow(snapshot, record)
                self.strategy_snapshot = snapshot
            shadow.count(record)
        except OSError as error:
            shadow.stats.journal_failures += 1
            self.emit(f"strategy shadow warning: {type(error).__name__}")
        except Exception:                      # the strategy shadow must never cost the Policy path anything
            shadow.fail("SHADOW_RUNTIME_ERROR")
            self._strategy_error(snapshot, "SHADOW_RUNTIME_ERROR")

    def _strategy_error(self, snapshot, reason: str) -> None:
        if self.journal is None:
            return
        try:
            self.journal.strategy_shadow_error(snapshot, reason)
        except OSError:
            self.strategy_shadow.stats.journal_failures += 1

    def _events(self, events) -> None:
        for event in events:
            if isinstance(event, StatusEvent):
                reason = f" ({event.reason})" if event.reason else ""
                self.emit(f"status: {event.status.value}{reason}")
                self._present(PresentationEvent("status", status=event.status.value, reason=event.reason))
                if event.status is LiveStatus.READY and self.recommender is None:
                    self._present(PresentationEvent("unavailable", reason="CHECKPOINT_UNAVAILABLE"))
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
                    self._present(PresentationEvent("thinking"))
                    try:
                        result = self.recommender.score(snap, self.live.session)
                        # Read any lines that appeared during inference before displaying the result.
                        self._events(self.live.step())
                        if self.live.session.current_snapshot is snap and self.live.session.status is LiveStatus.READY:
                            self.emit(render_recommendation(result))
                            journaled = False
                            if self.journal is not None:
                                try:
                                    self.journal.recommendation(snap, result, self.recommender.checkpoint_sha256)
                                    journaled = True
                                except OSError as error:
                                    self.emit(f"prediction journal warning: {type(error).__name__}")
                            with self._decision_lock:
                                self.active_identity = result.identity
                                self.active_snapshot = snap
                                self.active_recommendation = result
                                self.active_journaled = journaled
                                self.active_feedback_saved = False
                            if self.on_recommendation is not None:
                                self.on_recommendation(result)
                            self._present(PresentationEvent("recommendation", snapshot=snap, recommendation=result))
                            self.latencies_ms.append(result.latency_ms)
                            self.decisions_scored += 1
                            if self.model_shadow is not None:
                                self._run_model_shadow(snap, result)
                            if self.outcome_shadow is not None:
                                self._run_shadow(snap, result)
                            if self.strategy_shadow is not None:
                                self._run_strategy(snap, result)
                        else:
                            self.emit("no recommendation: DECISION_CHANGED_DURING_INFERENCE")
                            self._present(PresentationEvent("unavailable", reason="DECISION_CHANGED_DURING_INFERENCE"))
                            if self.journal is not None:
                                try:
                                    self.journal.discarded(snap, "DECISION_CHANGED_DURING_INFERENCE")
                                except OSError as error:
                                    self.emit(f"prediction journal warning: {type(error).__name__}")
                    except RecommendationUnavailable as error:
                        self.emit(f"no recommendation: {error}")
                        self._present(PresentationEvent("unavailable", reason=str(error)))
                        if self.journal is not None:
                            try:
                                self.journal.unavailable(snap, str(error))
                            except OSError as journal_error:
                                self.emit(f"prediction journal warning: {type(journal_error).__name__}")
            except Exception as error:  # no raw exception text from private logs
                self._invalidate()
                self.live_failed = True
                self.emit(f"LIVE warning: {type(error).__name__}; recommendations disabled")
                self._present(PresentationEvent("unavailable", reason="LIVE_FAILED"))
        if now >= self.next_collect:
            self.next_collect = now + self.collector_seconds
            try:
                failures_before = self.collector.stats.parse_failures
                self.collector.scan_once()
                if (self.collector.stats.parse_failures > failures_before
                        and not getattr(self.collector, "failure_diagnostics", False)):
                    self._collection_warning("SCAN", RuntimeError("collector reported a failure"))
            except Exception as error:
                self._collection_warning("SCAN", error)

    def finish(self) -> None:
        self._invalidate("APP_STOP")
        try:
            self.collector.write_summary()
        except Exception as error:
            self.emit(f"collection summary warning: {type(error).__name__}")
        stats = self.collector.stats
        if self.model_shadow is not None:
            try:
                self.model_shadow.close()
                self.emit(self.model_shadow.shadow.stats.summary())
            except Exception:
                self.emit("model shadow warning: close failed")
        if self.outcome_shadow is not None:
            self.emit(self.outcome_shadow.stats.summary())
        if self.strategy_shadow is not None:
            self.emit(self.strategy_shadow.stats.summary())
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
    parser.add_argument("--outcome-shadow", action="store_true",
                        help="Forecast the immediate consequences of every legal action next to the Policy ranking and "
                             "write them to <journal>.outcome_shadow.jsonl. Read-only: the Top-3 is unchanged")
    parser.add_argument("--outcome-shadow-budget-ms", type=float, default=250.0,
                        help="Wall-clock budget per decision; actions left over are recorded as NOT_COMPUTED")
    parser.add_argument("--strategy-shadow", action="store_true",
                        help="Rank every legal action with the experimental Strategic Scorer next to the Policy and "
                             "write it to <journal>.strategy_shadow.jsonl. Read-only: the Top-3 is unchanged")
    parser.add_argument("--strategy-shadow-budget-ms", type=float, default=250.0,
                        help="Wall-clock budget per decision; actions left over are scored from bookkeeping only")
    parser.add_argument("--model-shadow", action="store_true",
                        help="Score every displayed decision also with the retrained Policy v2 and Policy v3 "
                             "checkpoints (ML-POLICY-V3-1) in a background thread and write the comparison to "
                             "<journal>.model_shadow.jsonl. Journal only: the Top-3 is unchanged and never shown")
    parser.add_argument("--model-shadow-retrained", type=Path, default=RETRAINED_V2_CHECKPOINT)
    parser.add_argument("--model-shadow-retrained-sha256", default=RETRAINED_V2_SHA256)
    parser.add_argument("--model-shadow-v3", type=Path, default=POLICY_V3_CHECKPOINT)
    parser.add_argument("--model-shadow-v3-sha256", default=POLICY_V3_SHA256)
    parser.add_argument("--model-shadow-budget-ms", type=float, default=250.0,
                        help="Per-decision budget of the experimental models; models left over are recorded as SKIPPED")
    parser.add_argument("--prepare-actions", action="store_true",
                        help="EXPERIMENTAL: list a Prepare card's second root as PREPARE_CARD. No checkpoint was trained on that action, "
                             "so its score is unvalidated; without this flag such decisions stay 'no recommendation'")
    parser.add_argument("--ui", action="store_true", help="Show the Windows always-on-top recommendation panel")
    parser.add_argument("--overlay", action="store_true", help="Show the Vue / WebView2 desktop overlay")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.poll_ms < 10 or args.collector_seconds <= 0:
        raise SystemExit("poll-ms must be >=10 and collector-seconds must be positive")
    if args.ui and args.overlay:
        raise SystemExit("Choose --ui or --overlay")
    # hslog warnings and exceptions may contain raw log text or player identifiers.
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    catalog = CardCatalog.from_json(args.cards)
    recommender_error = None
    try:
        recommender = PolicyRecommender(args.checkpoint, expected_sha256=args.checkpoint_sha256,
                                        prepare_actions=args.prepare_actions)
        recommender.require_catalog(catalog)
    except Exception as error:
        recommender = None
        recommender_error = type(error).__name__
        print(f"recommendation warning: {type(error).__name__}; collection remains active", flush=True)
    shadow = None
    if args.outcome_shadow:
        try:
            shadow = OutcomeShadow(load_texts(ROOT), budget_ms=args.outcome_shadow_budget_ms)
        except Exception as error:
            print(f"outcome shadow warning: {type(error).__name__}; shadow disabled, Policy unaffected", flush=True)
    strategy = None
    if args.strategy_shadow:
        try:
            strategy = StrategyShadow(load_texts(ROOT), budget_ms=args.strategy_shadow_budget_ms)
        except Exception as error:
            print(f"strategy shadow warning: {type(error).__name__}; shadow disabled, Policy unaffected", flush=True)
    model_worker = None
    journal_path = args.data_root / "raw/live/prediction_journal.jsonl"
    if args.model_shadow:
        if recommender is None:
            print("model shadow warning: no primary Policy; shadow disabled", flush=True)
        else:
            try:
                models, failures = load_models(
                    [("retrained_v2", args.model_shadow_retrained, args.model_shadow_retrained_sha256),
                     ("policy_v3", args.model_shadow_v3, args.model_shadow_v3_sha256)],
                    catalog, reserved_sha256={recommender.checkpoint_sha256})
                for name, reason in sorted(failures.items()):
                    print(f"model shadow warning: {name} unavailable ({reason}); the other models are unaffected",
                          flush=True)
                if models:
                    model_worker = ModelShadowWorker(
                        ModelShadow(recommender.policy, recommender.encoder, recommender.checkpoint_sha256, models,
                                    budget_ms=args.model_shadow_budget_ms),
                        ModelShadowJournal.beside(journal_path))
                else:
                    print("model shadow warning: no experimental model available; shadow disabled", flush=True)
            except Exception as error:
                print(f"model shadow warning: {type(error).__name__}; shadow disabled, Policy unaffected", flush=True)
    session = LiveSession(catalog)
    recorder = Recorder(args.data_root / "raw/live", catalog_path=args.cards)
    live = LiveRunner(args.logs_root, session, recorder)
    collector = Collector(args.logs_root, args.data_root / "raw/collected",
                          args.data_root / "processed_real", args.cards)
    runtime = UnifiedRuntime(live, collector, recommender, emit=lambda text: print(text, flush=True),
                             collector_seconds=args.collector_seconds, outcome_shadow=shadow,
                             strategy_shadow=strategy, model_shadow=model_worker,
                             journal=PredictionJournal(journal_path))
    runtime.recommender_unavailable = recommender_error
    print("ManaMind experimental read-only policy. Ctrl+C to stop.", flush=True)
    runtime.emit(f"status: {session.status.value}")
    if args.ui or args.overlay:
        try:
            if args.overlay:
                from manamind.live.desktop import launch_desktop
                launch_desktop(runtime, ROOT, args.cards, args.poll_ms)
            else:
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
