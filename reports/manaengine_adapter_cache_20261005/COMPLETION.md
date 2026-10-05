# ManaEngine adapter: `_definition_rows` cache isolation — completion

Focused adapter-correctness / test-isolation fix. No card behavior, native code, declaration, registry, schema or training change.

| | |
|---|---|
| Starting HEAD (= canonical remote HEAD) | `92121deb717cd01f784f3f435eb52ecb33e88671` |
| Fix commit | `161ec386a804686926197993a195cac9d20d9009` (`fix(manaengine): isolate definition rows and bind catalog metadata per session`) |
| Final HEAD | the commit that adds this file, directly on top of `161ec38` (a document cannot embed its own hash; see `git log -1 codex/manaengine-first-deck`) |

Preflight: worktree clean, `HEAD == origin/codex/manaengine-first-deck == 92121de`. Pushed fast-forward, no force.

## 1. Root cause

In `_definition_rows()` the cache key was `key = str(catalog_file.resolve())`, but the function body later runs `for key, value in spec.items(): …`, which
rebinds `key`. The final `_DEFINITION_CACHE[key] = (result, records)` therefore stored the entry under a declaration field name (observed: the only key was
`'kindred_copy_contract'`), and the lookup `if key in _DEFINITION_CACHE` at the top could never hit. Every call rebuilt all 1213 native rows (~0.12 s), and —
because `ManaEngineSession.__init__` called `_definition_rows()` again on every native-catalog cache hit, only to refresh a global — every new session cost
~0.11 s even though its native catalog was already cached.

Renaming the loop variable alone would have been wrong: the cache stored `list[native.CardDefinition]`, and those objects are mutable (`def_readwrite`
fields). Tests build synthetic catalogs by editing rows returned from `_definition_rows()`, so a working cache of those objects would have leaked edits
between tests, sessions and later catalog construction.

## 2. Caller / ownership audit

| Caller | Class | Needs |
|---|---|---|
| `ManaEngineSession.__init__`, cache miss | runtime session path; builds the native `CardCatalog` | rows once per catalog path |
| `ManaEngineSession.__init__`, cache hit | called `_definition_rows()` only for its side effect on the global `_CARD_METADATA` | the catalog's metadata, nothing else |
| `test_adapter.py` at 199, 237, 259, 299, 361, 1194, 1412 (`_definition_rows`) | read-only | any consistent rows |
| 721, 985 | builds a native `CardCatalog` from rows (721 also used the global metadata through `_export_state`) | rows (721: metadata) |
| 1307 (post-mutation exception test), 1565 (Arcane Barrage unsupported-outcome test) | **test-only synthetic mutation** of returned rows | private fresh rows |
| 883 (`_export_state` on a hand-built dict) | enrichment-independent | none |
| `scripts/`, `reports/`, other `src/` | no references to any of the three names | — |

A second, related hazard surfaced by the audit: `_CARD_METADATA` was a module global overwritten by whichever catalog was loaded last, and
`_export_state` read it. A session on catalog A would enrich its observations with catalog B's `race`/`mechanics` as soon as a session or row load for B
happened afterwards. With the cache never hitting this was masked for the single default catalog but real for any alternate `catalog_path`.

**Ownership decision: A — fresh, caller-owned mutable rows on every call.** The native `CardCatalog` copies the rows at construction (pybind by-value),
so the catalog that sessions share is already isolated from any later edit of the rows it was built from; a cache of the mutable rows added no value and
all the risk.

## 3. Chosen design (`src/manamind/integrations/manaengine/engine.py`)

- `_DEFINITION_CACHE` is **removed**. `_load_definitions(path) -> (rows, metadata)` builds fresh rows and the metadata of that same catalog (the metadata is
  returned as a read-only `MappingProxyType` of frozen `CardFeatures`). `_definition_rows(path)` is `_load_definitions(path)[0]`.
- `_NATIVE_CATALOG_CACHE` is the **only** process-wide cache: resolved catalog path → `_RuntimeCatalog(native_catalog, card_metadata)`, never modified after
  insertion. A session on a cache hit does no row building at all.
- Each session binds `self._card_metadata` from its own catalog's entry (`clone()` copies it), and passes it to `_export_state(raw, evidence_constraints,
  card_metadata)`. The globals `_CARD_METADATA` (last-writer-wins) and `_COLLECTIBLE_IDS` (only ever used inside the builder) are removed. `_export_state`
  called without metadata does not enrich; there is no hidden fallback to a previously loaded catalog.
- Considered and not done: caching the parsed JSON sources to speed up repeated `_definition_rows()` calls. The runtime path builds once per catalog path per
  process, so it has little value, and tests already paid this cost on every call before the fix.

## 4. Why mutable objects cannot leak

1. No `CardDefinition` object is ever stored in a module-level structure: the builder returns new objects each call and the runtime cache stores the
   *constructed native catalog*, which owns its own copies.
2. Metadata is the only shared data; its values are frozen dataclasses and the mapping is read-only (`TypeError` on assignment, asserted).
3. A session holds a reference to its catalog's metadata, not to a module global, so loading another catalog cannot change what it enriches.

## 5. Tests

Added (all in `experiments/manaengine/tests/test_adapter.py`, using a fixture that gives each test a private `_NATIVE_CATALOG_CACHE`):

| Required regression | Test |
|---|---|
| 1 default-path stability | `test_definition_rows_default_path_is_stable_and_caller_owned` — equal field-by-field fingerprints and metadata across calls, fresh objects each time, read-only metadata |
| 2 mutation isolation | `test_mutating_returned_definition_rows_never_reaches_other_callers` — edits `support_state`, `ability`, nested `effects` (assigned back, since the property returns copies), `takes_damage_pool_id`, `required_mechanics` and the row list itself; later independent calls are unchanged |
| 3 catalog isolation and 6 metadata | `test_distinct_catalog_paths_keep_separate_rows_metadata_and_runtime_catalogs` — an alternate catalog changes only Murmy's `race`; sessions on default/same-content/alternate catalogs are created interleaved and observed afterwards, then again after cache hits and via `clone()`; three distinct runtime entries |
| 4 native catalog cache | `test_ordinary_sessions_share_one_native_catalog_per_path` — controlled instrumentation of `_load_definitions`: three sessions build once, another path builds exactly once more, games stay independent; no object identity assumed |
| 6 explicit enrichment | `test_export_state_enrichment_uses_only_explicit_catalog_metadata` |
| 5 order independence and 7 Barrage | `test_synthetic_mutation_and_ordinary_sessions_are_order_independent` — runs the full Arcane Barrage scenario (fixed seed, trace on) after a synthetic mutation, then first-then-synthetic, then again on a cache hit; states, traces and evidence constraints are identical |

Changed: the direct `_export_state(raw)` test at 721 now passes the metadata it loaded explicitly (it had relied on the global); the Phase 4I unsupported-outcome
test drops its restore-in-`finally` workaround because row ownership is now the stated contract. The six Phase 4I adapter tests pass unchanged in behavior,
alone and in the full run.

Mutation sanity (run once and discarded; real file restored byte-for-byte): (M1) the naive fix, a shared mutable row cache — killed by 5 of the 6 new tests,
including mutation isolation and order independence; (M2) metadata from a last-loaded global — killed; (M3) one constant native-cache key for every path —
killed; (M4) no runtime catalog cache — killed. No survivors.

## 6. Local validation

| Check | Result |
|---|---|
| `test_adapter.py` | 48 → **54** passed; also 54 passed with every test run in **reversed** order |
| Phase 4I adapter tests alone | 6 passed |
| Workflow set (adapter + `test_pipeline.py` + `test_policy_action_semantics.py`) | 75 → **81** passed |
| Full `python -m pytest -q` | 92 passed (unchanged; `testpaths = tests`) |
| Ruff `src tests scripts` | pass |
| Card-identity branch guard | PASS |
| `scripts/check_generated_artifacts.py` | 36 pinned outputs reproduced, no file changed |
| `git diff --check` | clean |
| Cost | `_definition_rows()` ≈ 0.12 s per call (unchanged, fresh by design); a new session on a cached catalog ≈ **0.0002 s** instead of ≈ 0.11 s; adapter test file ≈ 6 s instead of ≈ 14 s |

The native module was not touched, so no native rebuild was needed locally (the existing Release build is of unchanged native sources; hosted CI rebuilds it).

## 7. Hosted CI

Both workflows ran on the fix commit `161ec38` and concluded `success`; every job and step was read from the GitHub Actions jobs API.

**Source and generated artifact checks** — run 37302887062, jobs `source (ubuntu-latest)` and `source (windows-latest)`, both `success`; steps on both:
checkout, setup-python, `pip install -e ".[dev,replays]"`, **Python correctness diagnostics (Ruff)**, **Generator card-identity guard**,
**`scripts/check_generated_artifacts.py`**, **`git diff --exit-code`**, **`python -m pytest -q`** — all `success`.

**ManaEngine experimental** (triggered because `src/manamind/integrations/manaengine/**` and `experiments/manaengine/**` changed) — run 37302887229, jobs
`ubuntu-latest / ManaEngine` and `windows-latest / ManaEngine`, both `success`. Each: configure (Unix on Ubuntu, MSVC on Windows), **Release build**,
**CTest**, **Python adapter and policy schema tests** — all `success`. The native sources are unchanged, so the build and CTest steps confirm the unchanged
native side still builds and passes on both platforms; the adapter step is where the new isolation tests run.

Hosted numeric test counts are not claimed (step conclusions are public; the logs with counts are not readable without authentication). The report commit
that follows changes only this file under `reports/`, which the ManaEngine workflow's path filter does not cover, so only the Source workflow runs for it.

## 8. Deltas and notes

- Generated artifacts Δ 0; registry, dependency closure, training eligibility Δ 0; policy action schema (3) and state encoding schema (16) unchanged; no card
  support state, Arcane Barrage semantics, DamageGroup, RNG or evidence-constraint change. Only `engine.py` and `test_adapter.py` changed in the fix commit.
- Residual, unchanged behavior: `_NATIVE_CATALOG_CACHE` is keyed by the resolved catalog path, so rewriting a catalog file in place within one process is not
  re-read. That matches the pre-existing runtime-cache semantics and is not a regression; distinct paths are fully isolated (tested).

## 9. Verdict

**DEFINITION_ROWS_CACHE_ISOLATION_ACCEPTED**

Basis: the shadowed-key bug is fixed by removing the mutable row cache rather than activating it; row ownership is explicit (fresh, caller-owned) and tested,
including mutation isolation, catalog-path isolation, per-session metadata, one native catalog per path and order independence; the mutants of the new design
(including the naive shared-row cache) are all killed; local and hosted gates pass on Windows and Ubuntu; generated artifacts, registry, closure, training
eligibility and both schemas are unchanged (Δ 0).

Stopped here as instructed: no Fire pool, Whelp or card work was started.
