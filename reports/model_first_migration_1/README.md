# MODEL-FIRST-MIGRATION-1 — report

Base: `origin/main` = `596182297a761e1c56429dd6b6de436e58329bd3`. Branch: `claude/model-first-migration-1`. Nothing merged into `main`; `work/ui-overlay-shell`, `codex/ml2a-policy-v2` and the Codex branch were not touched (the shared main checkout was only read, to take pre-migration fingerprints).

**Status: COMPLETE** (one provenance caveat, see section 13).

## 1. Dependency inventory (before)

| Dependency | Kind | Needed by Model-first? | Meaning to keep independently | Decision |
|---|---|---|---|---|
| `.gitmodules`, gitlink `vendor/RosettaStone` | build input of the old engine | no | no | removed |
| `integrations/rosettastone/{bridge.cpp,CMakeLists.txt,patches/}` | C++ bridge + engine patch | no | no | removed |
| `integrations/rosettastone/card_rules/*` (declarations, generated manifests, scoped evidence) | inputs/outputs of the RosettaStone card generators, historical evidence | no | evidence of origin only | moved byte-for-byte to `docs/history/rosettastone_legacy/card_rules/` (inert) |
| `src/manamind/integrations/rosettastone/policy.py` | compatibility re-export of `manamind.models.policy` | no (pure alias) | the Policy API itself lives in `models/policy.py` | removed; all callers switched |
| `…/rosettastone.py`, `…/rollout.py` | native bridge adapter, baseline rollouts | no | no | removed |
| `train_selfplay.py`, `evaluate_policy.py` | RosettaStone self-play / policy-vs-baseline | no (no independent consumers) | no | removed |
| `scripts/generate_*.py` (10), `scripts/card_rules/` (7), `scripts/verify_*.py` (23), Rosetta-specific `scripts/audit_*` (10), `build_card_support_analysis.py`, `build_meta_training_profile_audit.py`, `build_native_identity.py`, `verification_evidence.py`, `registry_admission.py`, `sync_rosettastone_standard_metadata.py`, `check_generic_card_branches.py` + `configs/generator_branch_policy.json` | card generators, native scenario verifiers, evidence/identity tooling, AST guard for the generators | no | no | removed (recoverable from `5961822`) |
| `scripts/build_standard_registry.py` | scanned RosettaStone C++ CardSets sources | no | registry output kept as snapshot | removed; registry JSON frozen |
| `scripts/standard_profile.py`, `build_standard_profile.py`, `check_generated_artifacts.py` | profile loader/catalog builder; the checker ran the Rosetta generators and hashed the vendor tree | catalog part yes | pinned catalog | kept, reduced to the catalog/roots path |
| `configs/standard_profile.json` | had `engine_overlay` (a file inside the submodule) and a RosettaStone evidence list | catalog part yes | pinned inputs | rewritten (section 7) |
| ManaEngine `engine.py` + `state_import_capability.py` | optional read of `vendor/RosettaStone/Resources/cards.json` as a gap filler | no | pinned HearthstoneJSON | read removed (section 6) |
| `experiments/manaengine/scripts/{compare_reference,benchmark}.py` | side-by-side parity / benchmark vs RosettaStone | no | ManaEngine-only benchmark | `compare_reference.py` removed; `benchmark.py` is ManaEngine-only |
| `experiments/manaengine/scripts/select_roots.py` | historical selector reading Rosetta evidence | no | – | path repointed to the archive |
| Tests importing `…rosettastone.policy` (`test_pipeline`, `test_policy_action_semantics`, 6 ManaEngine test files) | active Policy API contract | yes | yes | repointed to `manamind.models.policy` |
| Tests of the removed stack: `test_review_registry`, `test_standard_registry`, `test_minion_set_enchant`, `test_profile_deck_minion_cost_summon` | removed builders/generators | no | – | removed (section 4) |
| `.github/workflows/*` | `submodules: recursive`, generator guard, generators in `check_generated_artifacts` | – | real checks stay | updated (section 12) |
| `data/cards/standard_registry_20261001_enUS.json`, `reports/standard_registry_20261001`, `data/cards/standard_scope_*`, `data/samples/*`, `reports/**`, `docs/history/**`, `docs/proposals/**`, `configs/training_profiles/meta_training_20261002_v1.json` | historical artifacts | no | evidence of origin | untouched (text mentions remain; section 10) |

Registry consumers kept working: `src/manamind/evidence/support.py` and the ManaEngine report scripts read the frozen registry JSON as data.

## 2. Removed components

Git submodule `vendor/RosettaStone` and `.gitmodules`; the C++ bridge and engine patch; `MANAMIND_ROSETTA_BRIDGE` and the bridge loader; `manamind.integrations.rosettastone` (4 files); RosettaStone self-play (`train_selfplay.py`, `evaluate_policy.py`); 51 scripts under `scripts/` plus `scripts/card_rules/` (7) and `configs/generator_branch_policy.json`; `experiments/manaengine/scripts/compare_reference.py`; `docs/ROSETTASTONE_INTEGRATION.md` (recoverable from Git history at `5961822`; no copy kept in `docs/history/`, because its build commands are meaningless without the engine); the registry builder and evidence tooling. The commit has 76 deletions and 32 renames.

## 3. Preserved components

Everything for the Model-first pipeline: `domain`, `cards`, `encoding`, `models` (Policy v1/v2, Value Network), `training`, `inference`, `evidence`, `integrations/powerlog`, `live`, their tests, the Power.log/dataset/LIVE scripts, ManaEngine (sources, adapter, tests, data), the pinned Standard catalog, the frozen registry snapshot, and all `reports/`, `docs/history/`, checkpoints and datasets (never touched).

## 4. Changed files (summary)

- Modified: `AGENTS.md`, `README.md`, `configs/standard_profile.json`, `scripts/{standard_profile,build_standard_profile,check_generated_artifacts}.py`, `src/manamind/integrations/manaengine/{engine.py,state_import_capability.py,__init__.py}`, `src/manamind/models/policy.py` (two comments only), both workflows, `experiments/manaengine/{README.md,scripts/benchmark.py,scripts/select_roots.py}`, `tests/{test_pipeline,test_policy_action_semantics,test_standard_profile}.py` and 6 ManaEngine test files (import path; in `test_adapter.py` the legacy-gift test and its variables were renamed `rosetta`→`legacy`, behaviour unchanged).
- Added: `docs/MODEL_FIRST_ROADMAP.md`, `docs/history/rosettastone_legacy/README.md`, `docs/proposals/README.md`, `tests/test_no_rosettastone_dependency.py`, this report.
- Deleted tests (all exercised only the removed stack): `tests/test_review_registry.py` (registry builder identity/evidence), `tests/test_standard_registry.py` (registry builder helpers and RosettaStone generator ownership assertions), `tests/test_minion_set_enchant.py` and `tests/test_profile_deck_minion_cost_summon.py` (RosettaStone generators and `vendor/.../cards.json`). Two functions in `test_standard_profile.py` (registry build; observation-source identity of the evidence tooling) were replaced by catalog-reproducibility tests.
- Encoding fix: `docs/PARTIAL_SIMULATOR_ARCHITECTURE.md` contained a stray cp1252 byte (0x97); replaced with `—` while editing.

## 5. Updated documents

`AGENTS.md` (compact Model-first rules; ManaEngine engineering rules moved to `experiments/manaengine/README.md`), new `docs/MODEL_FIRST_ROADMAP.md` (single priority source), `README.md` (architecture diagram, IMPLEMENTED/EXPERIMENTAL/PLANNED table, submodule-free install), `PARTIAL_SIMULATOR_ARCHITECTURE`, `STANDARD_REGISTRY`, `CAPABILITY_PACKAGE_PROCESS` (+ template), `MANAENGINE_ADMISSION`, `MANAENGINE_PHASE4E2_EVIDENCE_SAFETY` (note), `REAL_MATCH_DATA`, `experiments/manaengine/README.md`, `docs/history/README.md`. `docs/LIVE_BRIDGE.md` needed no change (its "bridge" is the live Power.log bridge, not RosettaStone). The ManaEngine-related documents carry a "frozen optional component" banner.

## 6. ManaEngine metadata and capability comparison

Old code: `pinned_raw.setdefault(id, row)` from the legacy `cards.json` after the pinned snapshot, catalog and dependency files were loaded; lookups happen only for engine record cards. Measured on the pre-migration inputs: 1218 engine records, **0** missing from the pinned files, so the legacy file never contributed. `CapabilityIndex` before (legacy file attached) vs after: all 1218 per-card (state, reason) pairs identical, summary identical (125 declarations, 113 non-hero-power supported, 4 hero powers; UNDECLARED 1093, DECLARED_UNSUPPORTED 8). Native rebuilt from this branch: 79 scenario groups / 18484 assertions pass; 332 Python adapter/policy tests pass. No coverage change and no rules change.

## 7. Standard catalog and generated artifacts

`data/cards/standard_current_enUS.json` SHA-256 `c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34` before and after; `check_generated_artifacts.py` also reproduces it and the roots snapshot (1185 roots) bit-for-bit offline. No snapshot was downloaded. Profile `standard_full_20261001_v1` changed only structurally: removed `engine_overlay`, `verification_evidence`, `session_match_evidence`, `registry_id`, `registry`, `reports`; added `historical_registry` (`FROZEN_HISTORICAL_SNAPSHOT`) pointing to the old registry JSON and report directory. The old registry cannot be regenerated without RosettaStone sources, so it is a frozen snapshot — **not** an admission gate and **not** ManaEngine coverage; the limit is stated in `docs/STANDARD_REGISTRY.md`. No new inventory or classification system was created (an independent registry would be a separate task). The removed overlay lived inside the submodule and was never tracked here.

## 8. Policy v1/v2 load and identity

Measured with the pre-migration code and again after, using the frozen checkpoints (read from the main checkout, not modified) and the current real-policy dataset `refresh_obs1_final` (1227 decisions, per-match JSONL files). Identical before/after: checkpoint SHA-256 v1 `5a5e3435c0dcda5ce69bcd0a48dc8521fb3696e2a7794e268b894efbf7e3e95e`, v2 `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`; `STATE_ENCODING_SCHEMA_VERSION` 16; `POLICY_ACTION_SCHEMA_VERSION` 4; hashes of `ACTION_FEATURE_NAMES`, `POLICY_STATE_FEATURE_NAMES` and the v2 feature contract; the dataset file hashes. Both checkpoints load through `load_policy_checkpoint` after the migration. No checkpoint, dataset or encoder file was changed or recreated. Checkpoint contents are not reproduced here.

## 9. Inference parity

For 40 evenly spaced decisions, the per-action logits of v1 and v2 (rounded to 1e-7, in menu order, same code path and the same menus) hash identically before and after: v1 `8db4ef9d71b2ade3…`, v2 `bdc46f7fbf9c36e9…`. Because menu order is unchanged, the action→score mapping is identical, so no reordering comparison was necessary. Legal-action semantics and the LIVE privacy contract were not edited; their tests pass (section 10).

## 10. Power.log, LIVE and full tests

Clean clone of the branch (no submodules): `ruff check src tests scripts` pass; `check_generated_artifacts.py` pass with a clean `git status`; `pytest tests` 589 passed, 1 skipped (the skip is not new). This covers Power.log parsing/import/policy-data validation, evidence extraction, LIVE replay/recommendation/session tests and Policy v1/v2 checkpoint tests. Failure-site audit: 310 baseline sites, 0 problems. An earlier local run with a custom `--basetemp` in the scratch directory showed 26 failures that disappear with the default basetemp (a harness path artifact); reported results use the default.

Repository-wide audit: `git grep -i rosetta` outside `docs/history/`, `reports/` and `docs/proposals/` finds only (a) deliberate statements that RosettaStone is retired (AGENTS, README, ManaEngine docs, the legacy README), (b) provenance strings in committed historical data (`configs/training_profiles/meta_training_20261002_v1.json`, `data/cards/standard_registry_*`, `standard_scope_*`, `data/samples/card_support_analysis_sample_*`, `experiments/manaengine/data/{root_selection,quick1_dependency_metadata,quick2_dependency_metadata,choice_mode_dependency_metadata}.json`), left unedited, and (c) text in `experiments/manaengine/scripts/{build_frontier_ledger,select_roots}.py`. `tests/test_no_rosettastone_dependency.py` now fails on a submodule/gitlink, a vendored engine, or `integrations.rosettastone`, `vendor/RosettaStone`, `MANAMIND_ROSETTA`, `mana_rosetta_bridge` or `submodules: recursive` in active code/CI.

## 11. ManaEngine tests

Local Windows (MSVC, Release, Ninja): native `manaengine_tests.exe` 79 groups / 18484 assertions; Python `experiments/manaengine/tests` + `test_native_failure_contract` + `test_pipeline` + `test_policy_action_semantics` + `test_simulation_attempt_contract`: 332 passed. CTest runs in CI.

## 12. CI

Commit `5564b55da94a23d5c3a69889eacd16c145894aac`, checkout without submodules.

| Workflow | Ubuntu | Windows |
|---|---|---|
| Source and generated artifact checks (ruff, failure-site audit, offline catalog regeneration, clean `git diff`, full pytest) | success | success |
| ManaEngine experimental (CMake build, CTest, adapter/policy tests) | success | success |

Runs: [source checks](https://github.com/MaksimOrekhov/manamind/actions/runs/37952863753), [ManaEngine](https://github.com/MaksimOrekhov/manamind/actions/runs/37952863702). The commit that adds this report changes only documentation.

## 13. Remaining caveats (no blocker for Model-first)

1. **Metadata provenance, unconfirmed.** `quick1_dependency_metadata.json` (`CS2_065`), `quick2_dependency_metadata.json` (`EDR_492t`) and `choice_mode_dependency_metadata.json` (one token) were captured from RosettaStone's bundled `cards.json`. They are committed data read by ManaEngine, so removing the submodule does not affect them, but their independent confirmation against HearthstoneJSON was **not** done (it needs a download that was not authorized). They are byte-identical to keep the capability fingerprint unchanged and are flagged in `experiments/manaengine/README.md`. Impact: only three fixed-token dependencies of the frozen ManaEngine; none on Policy, training or live.
2. The frozen registry and archived evidence can no longer be regenerated; this is intended.
3. `configs/training_profiles/meta_training_20261002_v1.json` and `experiments/manaengine/data/root_selection.json` still cite the old `integrations/rosettastone/card_rules/…` paths; the mapping is stated in the legacy README. Old reports were not rewritten.
4. The native build was run locally only on Windows; Ubuntu native results come from CI.

## 14. Running from a clean checkout

```powershell
git clone https://github.com/MaksimOrekhov/manamind.git
cd manamind
git checkout claude/model-first-migration-1   # until reviewed and merged
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,replays]"
python -m ruff check src tests scripts
python scripts/check_generated_artifacts.py
python -m pytest -q
```

No submodules and no native toolchain are required. ManaEngine (optional): see `experiments/manaengine/README.md` (CMake, C++20, pybind11).
