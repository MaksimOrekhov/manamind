"""STRATEGIC-SCORER-1: replay LIVE recordings through the real ``UnifiedRuntime`` with ``--strategy-shadow`` off and on.

Everything the player or the Policy journal sees (emitted text, presentation events with scores, state hashes,
RECOMMENDATION / INVALIDATION rows, number of scored decisions) must be identical; prints aggregate gates and timings.

  python scripts/strategy_shadow_replay.py [glob relative to the repository, default: recordings of 11-12 Oct 2026]
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

import outcome_shadow_replay as replay  # noqa: E402
import run_manamind  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.live.recommendation import PolicyRecommender  # noqa: E402
from manamind.outcome.live_shadow import load_texts  # noqa: E402
from manamind.strategy.live_shadow import StrategyShadow  # noqa: E402

catalog = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")
rec = PolicyRecommender(run_manamind.POLICY_V2_CHECKPOINT, expected_sha256=run_manamind.POLICY_V2_SHA256)
rec.require_catalog(catalog)
texts = load_texts(ROOT)
PATTERN = sys.argv[1] if len(sys.argv) > 1 else "data/raw/live/Hearthstone_2026_10_1[12]_*/*/slice.log"
dirs = sorted(p.parent for p in ROOT.glob(PATTERN))
summary = {"recordings": 0, "all_gates_true": 0, "failed_gates": {}, "decisions": 0, "strategy_rows": 0,
           "strategy_errors": 0, "incomplete": 0, "step_ms_plain": [], "step_ms_shadow": [], "strategy_ms": []}
for directory in dirs:
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        plain = replay.run_runtime(directory, rec, texts, work / "off", shadow=False)
        shadow = StrategyShadow(texts, budget_ms=250.0)
        on = replay.run_runtime(directory, rec, texts, work / "on", shadow=False, strategy=shadow)
        comparison = replay.compare_runs(directory, plain, on)
        gates = {k: v for k, v in comparison.items() if isinstance(v, bool) and not k.startswith("info_")}
        summary["recordings"] += 1
        if all(gates.values()):
            summary["all_gates_true"] += 1
        for k, v in gates.items():
            if not v:
                summary["failed_gates"][k] = summary["failed_gates"].get(k, 0) + 1
        summary["decisions"] += on.scored
        rows = [r for r in on.strategy_rows if r["event"] == "STRATEGY_SHADOW"]
        summary["strategy_rows"] += len(rows)
        summary["strategy_errors"] += sum(r["event"] == "STRATEGY_SHADOW_ERROR" for r in on.strategy_rows)
        summary["incomplete"] += sum(not r["complete"] for r in rows)
        summary["strategy_ms"] += [r["elapsed_ms"] for r in rows]
        summary["step_ms_plain"] += plain.decision_step_ms
        summary["step_ms_shadow"] += on.decision_step_ms
out = {k: v for k, v in summary.items() if not isinstance(v, list)}
for key in ("strategy_ms", "step_ms_plain", "step_ms_shadow"):
    values = summary[key]
    out[key] = {"n": len(values), "median": round(float(np.median(values)), 2),
                "p95": round(float(np.percentile(values, 95)), 2), "max": round(float(max(values)), 2)} if values else None
print(json.dumps(out, indent=1))
