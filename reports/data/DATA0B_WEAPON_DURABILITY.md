# DATA-0B — Power.log weapon durability

Date: 2026-10-06

Base SHA: `71ef2ea817bf049d28bc731b3aa0eeec07fef154` (`origin/main`; verified by fetching `main` at task start)

Branch: `work/data0b-weapon-durability`

## Bug and fix

The importer previously read weapon `current_durability` only from `DURABILITY`. The LIVE-0A audit found `HEALTH` on all 19 observed weapon entities and `DURABILITY` on none; weapon wear is represented by `DAMAGE`. As a result, those imports serialized weapon current durability as `None`.

The importer now uses `max(0, HEALTH - DAMAGE)` when `HEALTH` is present, treating missing or malformed damage as zero. When `HEALTH` is absent it uses an explicit `DURABILITY` tag, and returns `None` if neither tag exists. It does not use catalog durability for the current value. CardFeatures and StateEncoder schemas, ValueNetwork, ManaEngine, and canonical card metadata are unchanged.

## Tests

Regression coverage exercises the three-point cases (3/0 → 3, 3/1 → 2, 3/3 → 0), missing, malformed and overlarge damage, explicit legacy `DURABILITY`, absent tags, unchanged minion and Location behavior, and a synthetic end-to-end Power.log import with a weapon in play. No private Power.log was added to the repository.

Focused importer, collector, pipeline, and readiness checks: **70 passed**. Ruff on all changed Python files: **passed**. Full pytest: **260 passed, 3 failed, 26 errors**; the failures/errors are in unrelated registry/profile and RosettaStone-dependent tests because this isolated worktree does not contain the `vendor/RosettaStone` submodule checkout. The changed importer tests pass in both focused and full runs.

## Local raw-data rebuild preview

The preview was built in the fresh, ignored directory `data/processed_real_durability_preview`; the existing `data/processed_real/` directory was not changed. Only aggregate counts are retained in this report.

- Raw log files found: 24.
- Eligible raw logs and distinct trajectories rebuilt: 22.
- Examples rebuilt: 1,618.
- Outcomes: 13 wins, 9 losses, 0 draws.
- Existing top-level processed data: 33 unique match trajectories.
- Existing trajectories recoverable from available raw logs: 6 of 33; complete recovery is **not** proven.
- Of those matched old trajectories, 2 serialize differently after the durability correction.

The remaining existing trajectories cannot be fabricated from the available logs. Therefore a complete replacement dataset is not recommended yet. Preserve the current dataset and retain the separate preview until the missing raw matches are recovered or the user chooses a deliberately partial dataset.

## Safe migration commands

First stage eligible, one-match raw logs into a separate input directory. Then use the existing batch importer with a fresh output path that does not exist yet:

```powershell
$output = "data/processed_real_durability_rebuild"
if (Test-Path -LiteralPath $output) { throw "Choose a fresh output path: $output" }
python scripts/import_power_logs.py `
  --input-dir data/raw/data0b_single_match_stage `
  --output-dir $output `
  --cards data/cards/standard_current_enUS.json
```

The batch importer accepts one-match logs from its input directory and skips duplicate corrected trajectories. Never point `--output-dir` at `data/processed_real/` or combine its pre-DATA-0B trajectories with corrected imports. Keep the raw staging directory ignored under `data/raw/`; verify source coverage before treating a rebuild as complete.

## Recommendation

Fix is ready. A full re-import is **not yet recommended** because only 6 of 33 existing unique processed matches are recoverable from currently available raw logs. Keep the new preview separate; recover the missing source matches before replacing the active dataset.
