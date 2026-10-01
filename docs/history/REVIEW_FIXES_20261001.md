# Corrections after the latest code review

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

The confirmed findings were addressed without replacing RosettaStone or building another rules interpreter.

## Source reproducibility

RosettaStone is maintained in the user-owned `MaksimOrekhov/RosettaStone` fork on `codex/manamind-engine`. The upstream remote remains `utilForever/RosettaStone`. The superproject gitlink pins the exact published engine commit. Binary/build directories remain local. Recursive checkout in source CI validates fetchability.

## Registry and admission

Blockers use each card's evidence rather than a variable retained from an earlier loop. Admission requires current rules evidence with full-profile scope, an explicitly reviewed complete closure, current full-scope rules for reachable dependencies, audited bridge actions, pinned legality and current session/match gates. Empty profiles cannot pass. Eligible root/deck counts, closure counts and report admission derive from these inputs; a positive fixture checks the BLOCKED-to-ELIGIBLE transition.

The graph remains a lower bound. Missing heuristic signals are not reviewed proof of an empty closure. No current package is admitted for full Standard training.

## Shared pinned profile

`configs/standard_profile.json` owns the date, metadata archive, scope, roots, bans, catalog, engine overlay, output paths and evidence inputs. `build_standard_profile.py` produces roots/catalog/overlay together. The three excluded future event records were removed from the generator catalog and engine overlay. Existing declaration cards were compared against the previous catalog before re-pinning checksums; their metadata/rules were unchanged.

Dates and profile IDs are data. A temporary 2026-10-02 test builds roots and registry without modifying Python. Outputs use recorded capture provenance, relative project references, canonical text checksums and fixed LF output rather than runtime timestamps or machine-local absolute paths.

## Execution evidence

The canonical registry consumes explicit schema-v2 evidence and current source/profile fingerprints. It does not read local `.lib`, `.pyd`, `UnitTests.exe` or `CMakeCache.txt`. Schema-v1 pilot evidence remains historical/incomplete until scenarios are rerun.

`build_native_identity.py` builds configured core/bridge consumers, confirms sources did not change during the build, and records artifact checksums in ignored `build/execution_identity.json`. Verifiers require this matching build identity and check the bridge actually loaded by their process before recording successful native/scenario results. Source identity excludes evidence outputs themselves to avoid self-invalidating hashes. Canonical evidence can therefore be consumed on a clean source checkout without local binaries.

## Composition boundary

The previous generator was split into declaration validation, parameterized operations/activation rendering, and frozen reviewed custom emitters. Custom operations and card-specific branches are honestly classified CUSTOM in manifests/registry. Generic rendering has no card-ID branches. Existing C++ output was preserved; the retained custom emitters are not counted as a scalable generic capability. Add new special cases as native/custom work; extract a shared operation only after its contract and consumers justify it.

## Observations

Base card cost/attack/health/durability and current instance values are separate. Both native bridge and Power.log import preserve current hand stats and weapon state, including modified cost. Effective-value accessors serve gameplay consumers. Catalog enrichment and serialization retain current values. Unknown hero-power/location booleans survive JSON round trips as unknown.

Encoder schema v6 adds current cost/durability features and uses current attack/health channels for visible hand/weapon instances. Existing incompatible checkpoints are preserved and rejected. Policy/model training was not started.

## Checks and process

CI checks recursive submodules, Ruff correctness diagnostics, source-based regeneration/ownership and Python tests on Linux and Windows. Native scenarios remain separately recorded Windows checks; CUDA training is not part of CI. `check_generated_artifacts.py` regenerates the pinned outputs and fails on stale content or duplicate ownership. `AGENTS.md` points to generated coverage reports instead of copying rapidly changing counts.

Tests cover per-card stale blockers, closure/dependency/session gates, positive admission, evidence invalidation, schema round trips, modified hand/weapon parity, parameterized profiles and registry/report rebuilds. Independent native scenarios and an actual bridge instance fixture supplement the source tests.

### Recorded local results

- Ruff: passed.
- Python suite: 44 tests passed.
- Pinned regeneration: all 27 outputs reproduced, unique registration ownership.
- Effect-composition native suite: 57 cases, 361 assertions passed; batch bridge smoke passed.
- After-attack draw: 5 cases, 42 assertions passed.
- Repeated-trigger draw: 4 cases, 34 assertions passed.
- Filtered-school draw: 3 cases, 27 assertions passed.
- Core alias: 1 case, 780 assertions passed.
- Actual native hand/weapon observation parity and the two M.O.T.H.E.R. scenarios passed.

The regenerated report contains 1,185 roots, 167 direct and 176 generated registrations, 11 current scoped-verification entries, and zero training-eligible roots. Scoped checks do not certify full Standard rules or closure.
