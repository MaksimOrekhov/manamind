# Phase 4H.4 — Normalize post-mutation failures

- Target branch: `codex/manaengine-first-deck`
- Base: `3e7a06c16d22ee618a476dcfdea688e73be20a37`
- Implementation commit: `4337bb07911b6b893f9a7d84e1d3d5460df6a43e`
- Result: after legal-action validation, standard and unknown exceptions from action execution clear pending damage frames, preserve the first diagnostic, poison the session, and surface `UnsupportedSimulationError`. Illegal actions remain outside this normalization path.

## Regression coverage

- Native T03 exercises a post-mutation standard exception, confirms the original diagnostic, retained mutation, cleared frames, poisoned API behavior, and clone/RNG behavior.
- Adapter regression exercises the same failure through the real action path and confirms invalid input before mutation remains an ordinary input error.
- No registry, schema, status, pool, or training artifacts changed.

## Verification

Local Windows build (MSVC 19.44, Release):

- Focused native damage-group suite: **10 groups / 173 assertions, PASS**.
- Full native suite: **67 groups / 1,783 assertions, PASS**.
- CTest: **1/1 PASS**.
- Adapter/policy subset: **69 passed**; focused new adapter test: **1 passed**.
- Ruff and card identity guard: **PASS**.
- `git diff --check`: passed before commit.

Local generated-artifact check and full pytest were attempted. Three registry tests (out of 92) could not access the linked RosettaStone Git metadata in this worktree; the other **89 passed**. The generated-artifact command stopped at the same metadata lookup. No outputs were regenerated or manually promoted. Clean hosted checkouts then completed the authoritative checks:

- Source CI: Windows **success**, Ubuntu **success** (including generated-artifact check and full pytest).
- ManaEngine experimental CI: Windows **success**, Ubuntu **success** (including build, CTest, and adapter/policy tests).

Runs: [Source CI](https://github.com/MaksimOrekhov/manamind/actions/runs/37294784902) · [ManaEngine CI](https://github.com/MaksimOrekhov/manamind/actions/runs/37294784870)

No new native failures. DamageGroup semantics and registry delta are unchanged.
