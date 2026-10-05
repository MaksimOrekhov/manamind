# Architecture documentation realignment completion

Date: 2026-10-05

Base: `main` at `a08a65a681cffff2245f66c4a5268aa615aebd6a`

Scope: documentation only

## Outcome

Added [the partial-simulator architecture contract](../../docs/PARTIAL_SIMULATOR_ARCHITECTURE.md)
as the current reference for ManaEngine's implemented boundaries, accepted
targets and future work. Aligned the repository overview and durable guidance
with ManaEngine as the primary forward simulator development backend and
RosettaStone as a reference/regression backend.

The docs now distinguish mechanical execution, rules/evidence basis,
dependency closure, model uncertainty and canonical training admission. They
record the bounded `REVIEWED_INFERRED` Fire-pool exception without treating it
as exact rules verification or training eligibility; document fail-closed
sampling, unsupported held-card behavior, poisoned-state handling, current
unknown-ID representation, the live-root limitation and the hidden-information
boundary; and mark `SimulationAttempt`, `Q_fallback`, unknown-ID robustness
training, live replay/evidence generation and drift detection as future or
unimplemented. Current schema versions are recorded as state encoding 16 and
Rosetta policy action 3.

Updated or added documentation in `AGENTS.md`, `README.md`, the ManaEngine
admission and Standard registry guides, capability package process/template,
Rosetta integration guide, real-match data guide, Phase 4E.2 evidence-safety
crosslink, ManaEngine guide and the dated prototype proposal banner. No code,
schema, registry, manifest, generated output, Rosetta submodule, dataset or
checkpoint was intentionally changed.

## Validation

- Markdown relative-link check across touched documentation: **PASS**.
- `git diff --check`: **PASS**.
- `scripts/check_generated_artifacts.py`: **INCOMPLETE**. It began its pinned
  generation sequence and then failed when `build_standard_profile.py` could
  not create `vendor/RosettaStone/Resources` in the isolated worktree
  (`PermissionError`). No permission change or regeneration retry was made.
  Follow-up status inspection found no changed generated files and no
  `vendor/RosettaStone/Resources` directory.
- Ruff: unavailable in this checkout (`python -m ruff` reports `No module
  named ruff`). No environment was installed or modified.
- No local Python or native suite was run; this change is documentation-only.
- Hosted workflows on commit `76b26e15c435a0470a1b7abe2fc2c8e1e6ef1b1e`
  completed successfully: Source CI on Windows and Ubuntu (including generated
  artifact check and pytest), and ManaEngine CI on Windows and Ubuntu (release
  build plus adapter/policy-schema checks). Their success verifies that
  documentation commit; the following report-only commit does not change
  executable or generated inputs.

## Remaining terminology debt

The source docstrings/messages in
`src/manamind/integrations/manaengine/__init__.py` and
`src/manamind/integrations/manaengine/engine.py` still call ManaEngine
“experimental” or a “prototype”. They were deliberately not edited because
the request is documentation-only and forbids source changes. This is a
source-level terminology mismatch, not evidence that the documented strict
runtime boundaries or training gate have changed.

## Boundary

This realignment does not implement Phase 4K, fallback scoring, live-root
import, a replay comparator, automatic rules discovery, or training. It does
not alter evidence or claim profile/deck readiness. Any later implementation
requires its own scoped review, verification and authorization under the
current architecture.
