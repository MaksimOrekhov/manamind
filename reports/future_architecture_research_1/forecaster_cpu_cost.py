"""Read-only: CPU cost of the Python outcome forecaster per legal action on real non-protected positions.

Measures one-step forecasts only (no search, no Policy). Run from the main checkout root. Prints aggregates only.
"""

import glob
import json
import statistics
import sys
import time
from collections import Counter

sys.path.insert(0, "src")
from manamind.domain import game_state_from_dict  # noqa: E402
from manamind.outcome.forecast import forecast_action  # noqa: E402
from manamind.outcome.texts import TextSource  # noqa: E402

held = set(json.load(open("data/processed_policy_prepare_1/split_plan.json", encoding="utf-8"))["parts"]["fresh_holdout"])
texts = TextSource.from_files("data/cards/standard_current_enUS.json",
                              "data/cards/source_snapshots/cards_collectible_20261001_enUS.json")
rows = []
for path in sorted(glob.glob("data/processed_policy_real/collected/*.jsonl")):
    if path.replace("\\", "/").rsplit("/", 1)[-1][:64] in held:
        continue
    with open(path, encoding="utf-8") as handle:
        rows += [json.loads(line) for line in handle if line.strip()][::10]   # every 10th decision
rows = rows[:300]
per_action, statuses, failures = [], Counter(), 0
for row in rows:
    try:
        state = game_state_from_dict(row["state"])
    except Exception:  # older rows may predate current fields; skip, do not repair
        failures += 1
        continue
    for action in row["legal_actions"]:
        start = time.perf_counter()
        forecast = forecast_action(state, action, texts)
        per_action.append((time.perf_counter() - start) * 1e3)
        statuses[forecast.status.name] += 1
q = statistics.quantiles(per_action, n=20)
print(f"decisions={len(rows) - failures} (state load failures {failures}) actions={len(per_action)}")
print(f"forecast per action: median {statistics.median(per_action):.3f} ms, p95 {q[18]:.3f} ms, "
      f"mean {statistics.mean(per_action):.3f} ms (1 thread)")
print("status share:", {k: f"{v / len(per_action):.1%}" for k, v in statuses.most_common()})
