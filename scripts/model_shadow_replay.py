"""Replay LIVE recordings through the real ``UnifiedRuntime`` with the model shadow off and on (ML-POLICY-SHADOW-1).

Each recording is fed to a ``LiveSession`` exactly as the tail fed it (see ``outcome_shadow_replay``); the unchanged
runtime is stepped over it without the shadow and with it. The two runs are compared on everything the player or the
Policy journal can see (emitted text, presentation events with scores, state hashes, RECOMMENDATION/INVALIDATION rows).
The shadow rows are checked against the displayed decision (identity, menu, identical model inputs, primary re-run) and,
where the ML-1B dataset holds the same decision, against the training inputs of every model. Fault runs inject a
failing, NaN-producing or slow experimental model and a failing journal to prove the Policy path is unaffected.

  python scripts/model_shadow_replay.py <recording dir> [...] --out-dir <new dir> --report-json <new file> \
      [--admitted-dataset data/processed_policy_v3/dataset] [--threaded] [--pace-ms 0]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import torch  # noqa: E402

import run_manamind  # noqa: E402
from outcome_shadow_replay import RecordedLive, RunResult, _event_view, _NoCollector, _strip, read_jsonl  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.live.prediction_journal import PredictionJournal  # noqa: E402
from manamind.live.recommendation import PolicyRecommender  # noqa: E402
from manamind.policy_shadow.journal import ModelShadowJournal  # noqa: E402
from manamind.policy_shadow.models import load_models  # noqa: E402
from manamind.policy_shadow.shadow import ModelShadow, _inputs_sha  # noqa: E402
from manamind.policy_shadow.worker import ModelShadowWorker  # noqa: E402
from manamind.training.real_policy import encode_example, load_examples  # noqa: E402


class FaultyPolicy(torch.nn.Module):
    """Wraps a network and misbehaves on purpose: ``raise``, ``nan``, ``slow`` (sleep) or ``ok``."""

    def __init__(self, inner, mode: str, delay_s: float = 0.0) -> None:
        super().__init__()
        self.inner, self.mode, self.delay_s = inner, mode, delay_s

    def forward(self, *inputs):
        if self.mode == "raise":
            raise RuntimeError("injected failure")
        if self.mode == "slow":
            time.sleep(self.delay_s)
        out = self.inner(*inputs)
        return out * float("nan") if self.mode == "nan" else out


def load_pinned(catalog, args):
    specs = [("retrained_v2", args.retrained, args.retrained_sha256), ("policy_v3", args.v3, args.v3_sha256)]
    models, failures = load_models(specs, catalog, reserved_sha256={args.primary_sha256})
    if failures or len(models) != 2:
        raise SystemExit(f"experimental checkpoints unavailable: {failures}")
    return models


@dataclasses.dataclass
class ModelRun(RunResult):
    model_rows: list = dataclasses.field(default_factory=list)
    model_summary: str | None = None
    model_stats: object = None


def run_model_runtime(directory: Path, recommender, work: Path, *, models, threaded: bool, pace_ms: float = 0.0,
                      budget_ms: float = 250.0, break_journal: bool = False, shadow: bool = True) -> ModelRun:
    live = RecordedLive(directory, recommender.encoder.catalog)
    result = ModelRun()
    journal = PredictionJournal(work / "prediction_journal.jsonl")
    worker = None
    if shadow:
        shadow_journal = ModelShadowJournal.beside(journal.path)
        if break_journal:
            shadow_journal.path.parent.mkdir(parents=True, exist_ok=True)
            shadow_journal.path.mkdir()                      # a directory where the file should be: every write fails
        worker = ModelShadowWorker(
            ModelShadow(recommender.policy, recommender.encoder, recommender.checkpoint_sha256, models,
                        budget_ms=budget_ms), shadow_journal, threaded=threaded)
    runtime = run_manamind.UnifiedRuntime(
        live, _NoCollector(), recommender, emit=result.emitted.append, collector_seconds=3600, journal=journal,
        on_event=lambda event: result.events.append(_event_view(event)), model_shadow=worker)
    while not live.exhausted:
        before = runtime.decisions_scored
        live.fresh = True
        started = time.perf_counter_ns()
        runtime.step(now=0.0)
        if runtime.decisions_scored > before:
            result.decision_step_ms.append((time.perf_counter_ns() - started) / 1e6)
        if pace_ms:
            time.sleep(pace_ms / 1000)
    if worker is not None and threaded:
        worker.flush()
    runtime.finish()
    result.scored = runtime.decisions_scored
    result.policy_latency_ms = list(runtime.latencies_ms)
    result.hashes = live.hashes
    result.journal = _strip(read_jsonl(journal.path))
    if worker is not None:
        result.model_rows = read_jsonl(worker.journal.path) if worker.journal.path.is_file() else []
        result.model_summary = next((x for x in result.emitted if x.startswith("model shadow:")), None)
        result.emitted = [line for line in result.emitted if not line.startswith("model shadow")]
        result.model_stats = worker.shadow.stats
    return result


def same_player_view(plain: RunResult, shadowed: RunResult) -> dict:
    return {"emitted_identical": plain.emitted == shadowed.emitted, "events_identical": plain.events == shadowed.events,
            "hashes_identical": plain.hashes == shadowed.hashes,
            "policy_journal_identical": plain.journal == shadowed.journal,
            "decisions_identical": plain.scored == shadowed.scored}


def audit_rows(directory: Path, run: ModelRun, models, admitted: dict | None) -> dict:
    """Check every MODEL_SHADOW row against the Policy journal and (optionally) the ML-1B training inputs."""
    recommendations = {r["decision_id"]: r for r in run.journal if r["event"] == "RECOMMENDATION"}
    rows = [r for r in run.model_rows if r["event"] == "MODEL_SHADOW"]
    problems, checked_inputs, mismatched_inputs = Counter(), 0, 0
    by_model = {m.name: m for m in models}
    ids = Counter(r["decision_id"] for r in rows)
    problems["duplicate_decision_rows"] = sum(c - 1 for c in ids.values() if c > 1)
    for row in rows:
        rec = recommendations.get(row["decision_id"])
        if rec is None or rec["state_hash"] != row["state_hash"] or rec["match_id"] != row["match_id"]:
            problems["row_without_matching_recommendation"] += 1
            continue
        primary = row["models"][0]
        if primary["checkpoint_sha256"] != rec["checkpoint_sha256"]:
            problems["primary_sha_differs"] += 1
        if [t["action"] for t in primary["top3"]] != [t["action"] for t in rec["top3"]]:
            problems["primary_top3_differs_from_displayed"] += 1
        if primary.get("reproduced") is not True:
            problems["primary_not_reproduced"] += 1
        digests: dict = {}
        for e in row["models"]:
            if (e["status"] == "OK" or e["role"] == "primary") and e.get("inputs_sha256"):
                digests.setdefault(e.get("input_representation"), set()).add(e["inputs_sha256"])
        if any(len(v) > 1 for v in digests.values()):
            problems["models_saw_different_inputs"] += 1
        for entry in row["models"][1:]:
            if entry["status"] != "OK":
                problems[f"{entry['name']}_{entry['status']}_{entry.get('reason')}"] += 1
        if admitted is not None:
            example = admitted.get(f"{row['match_id']}:{row['options_id']}")
            if example is not None and example["provenance"]["state_hash"] == row["state_hash"]:
                for entry in row["models"]:
                    if entry["status"] != "OK" and entry["role"] != "primary":
                        continue
                    model = by_model.get(entry["name"])
                    if model is None:
                        continue
                    checked_inputs += 1
                    historical = encode_example(example, model.encoder, representation=model.representation)
                    if _inputs_sha(historical) != entry["inputs_sha256"]:
                        mismatched_inputs += 1
    return {"rows": len(rows), "problems": dict(problems), "inputs_checked_against_training_encoding": checked_inputs,
            "inputs_mismatched": mismatched_inputs}


def percentiles(values):
    if not values:
        return None
    return {"n": len(values), "p50": round(float(np.percentile(values, 50)), 3),
            "p95": round(float(np.percentile(values, 95)), 3), "max": round(float(max(values)), 3)}


def model_timing(rows):
    out = {}
    for row in rows:
        if row["event"] != "MODEL_SHADOW":
            continue
        bucket = "1-5" if row["menu_size"] <= 5 else "6-10" if row["menu_size"] <= 10 else \
            "11-20" if row["menu_size"] <= 20 else "21-40" if row["menu_size"] <= 40 else "41+"
        for entry in row["models"]:
            if entry["status"] == "OK" and "inference_ms" in entry:
                out.setdefault(entry["name"], {}).setdefault(bucket, []).append(entry["inference_ms"])
                out[entry["name"]].setdefault("all", []).append(entry["inference_ms"])
    return {name: {bucket: percentiles(v) for bucket, v in sorted(buckets.items())} for name, buckets in out.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--primary", type=Path, default=run_manamind.POLICY_V2_CHECKPOINT)
    parser.add_argument("--primary-sha256", default=run_manamind.POLICY_V2_SHA256)
    parser.add_argument("--retrained", type=Path, default=run_manamind.RETRAINED_V2_CHECKPOINT)
    parser.add_argument("--retrained-sha256", default=run_manamind.RETRAINED_V2_SHA256)
    parser.add_argument("--v3", type=Path, default=run_manamind.POLICY_V3_CHECKPOINT)
    parser.add_argument("--v3-sha256", default=run_manamind.POLICY_V3_SHA256)
    parser.add_argument("--admitted-dataset", type=Path)
    parser.add_argument("--threaded", action="store_true",
                        help="also run the production background-thread mode, paced like a game and as a zero-pause stress test")
    parser.add_argument("--pace-ms", type=float, default=60.0, help="sleep between runtime steps in the paced threaded mode")
    parser.add_argument("--fault-recordings", type=int, default=3, help="recordings used for each injected fault")
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    catalog = CardCatalog.from_json(args.cards)
    recommender = PolicyRecommender(args.primary, expected_sha256=args.primary_sha256)
    recommender.require_catalog(catalog)
    models = load_pinned(catalog, args)
    admitted = None
    if args.admitted_dataset:      # LIVE keys a decision by "<match>:<options id>", exactly the dataset's decision_id
        admitted = {r["decision_id"]: r for r in load_examples(args.admitted_dataset)}
    report = {"recordings": len(args.recordings), "models": {m.name: {"sha256": m.sha256, "schema": m.schema,
                                                                       "parameters": m.parameters} for m in models},
              "modes": {}, "faults": {}}
    modes = [("sync", False, 0.0)]
    if args.threaded:
        modes += [("threaded_paced", True, args.pace_ms), ("threaded_stress", True, 0.0)]
    for mode, threaded, pace in modes:
        plain_all, shadow_all, rows_all, audits = ModelRun(), ModelRun(), [], []
        view = {k: True for k in ("emitted_identical", "events_identical", "hashes_identical",
                                  "policy_journal_identical", "decisions_identical")}
        for i, directory in enumerate(args.recordings):
            work = args.out_dir / mode / f"{i:03d}"
            plain = run_model_runtime(directory, recommender, work / "plain", models=models, threaded=False, shadow=False)
            shadowed = run_model_runtime(directory, recommender, work / "shadow", models=models, threaded=threaded,
                                         pace_ms=pace)
            for key, value in same_player_view(plain, shadowed).items():
                view[key] = view[key] and value
            plain_all.policy_latency_ms += plain.policy_latency_ms
            shadow_all.policy_latency_ms += shadowed.policy_latency_ms
            plain_all.decision_step_ms += plain.decision_step_ms
            shadow_all.decision_step_ms += shadowed.decision_step_ms
            rows_all += shadowed.model_rows
            audits.append(audit_rows(directory, shadowed, models, admitted))
        total = Counter()
        for a in audits:
            total.update(a["problems"])
        report["modes"][mode] = {
            "player_visible_identical": view,
            "decisions": sum(a["rows"] for a in audits),
            "audit": {"problems": dict(total), "inputs_checked_against_training_encoding":
                      sum(a["inputs_checked_against_training_encoding"] for a in audits),
                      "inputs_mismatched": sum(a["inputs_mismatched"] for a in audits)},
            "policy_latency_ms": {"plain": percentiles(plain_all.policy_latency_ms),
                                  "with_shadow": percentiles(shadow_all.policy_latency_ms)},
            "decision_step_ms": {"plain": percentiles(plain_all.decision_step_ms),
                                 "with_shadow": percentiles(shadow_all.decision_step_ms)},
            "model_inference_ms": model_timing(rows_all),
            "events": dict(Counter(r["event"] for r in rows_all))}
    faults = [("retrained_raises", "retrained_v2", "raise", 0.0, False), ("v3_nan", "policy_v3", "nan", 0.0, False),
              ("v3_slow_400ms", "policy_v3", "slow", 0.4, False), ("journal_unwritable", None, "ok", 0.0, True)]
    for label, victim, mode, delay, broken in faults:
        broken_models = [dataclasses.replace(m, policy=FaultyPolicy(m.policy, mode, delay)) if m.name == victim else m
                         for m in models]
        view = {k: True for k in ("emitted_identical", "events_identical", "hashes_identical",
                                  "policy_journal_identical", "decisions_identical")}
        events, other_ok, stats, step_ms = Counter(), True, Counter(), []
        for i, directory in enumerate(args.recordings[:args.fault_recordings]):
            work = args.out_dir / "faults" / label / f"{i:03d}"
            plain = run_model_runtime(directory, recommender, work / "plain", models=models, threaded=False, shadow=False)
            faulty = run_model_runtime(directory, recommender, work / "shadow", models=broken_models, threaded=True,
                                       pace_ms=args.pace_ms, break_journal=broken, budget_ms=250.0)
            for key, value in same_player_view(plain, faulty).items():
                view[key] = view[key] and value
            for row in faulty.model_rows:
                events[row["event"]] += 1
                if row["event"] == "MODEL_SHADOW":
                    for entry in row["models"]:
                        stats[(entry["name"], entry["status"], entry.get("reason"))] += 1
                        if victim is not None and entry["name"] != victim and entry["role"] == "experimental" \
                                and entry["status"] != "OK":
                            other_ok = False
            step_ms += faulty.decision_step_ms
            if faulty.model_stats is not None and broken:
                stats[("journal_failures", "", "")] += faulty.model_stats.journal_failures
        report["faults"][label] = {"player_visible_identical": view, "other_experimental_models_unaffected": other_ok,
                                   "shadow_row_events": dict(events),
                                   "entries": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in sorted(stats.items(), key=str)},
                                   "decision_step_ms": percentiles(step_ms)}
    with args.report_json.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"modes": {m: {"player_visible_identical": v["player_visible_identical"],
                                    "decisions": v["decisions"], "audit": v["audit"],
                                    "policy_latency_ms": v["policy_latency_ms"]} for m, v in report["modes"].items()},
                      "faults": {k: {"identical": all(v["player_visible_identical"].values()),
                                     "others_ok": v["other_experimental_models_unaffected"],
                                     "events": v["shadow_row_events"]} for k, v in report["faults"].items()}},
                     indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
