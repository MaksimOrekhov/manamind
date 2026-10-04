# Phase 4E.1a — Restore native Phase 4E regressions

The Phase 4E.1 Dark Gift native test adaptation had removed the two earlier Phase 4E regression suites. This change restores both suites and their fixtures against the current `CardCatalog` and typed `PoolManifest` API. The Dark Gift scenarios and implementation remain intact; no production files or runtime semantics changed.

Restored coverage:

- `test_finite_pool_generated_instance_v1`: reviewed and candidate manifests, unsupported outcomes without reroll, generated `cost_delta`, full-hand rejection before RNG, clone determinism, normal Shatter hand entry and modifier rejection, plus count/hash validation.
- `test_takes_damage_self_reaction_v1`: Effect, Spell, Combat and HeroPower packets; recipient controller; Divine Shield, zero damage, Immune and Silence; separate packets; lethal failure; removed/stale and controller-changed consumers; full-hand pre-RNG rejection and end-turn checkpoint behavior.

The combined native suite now reports **48 scenario groups / 810 assertions**. The current 46 / 766 count was missing these two Phase 4E groups; the earlier Phase 4E baseline was 46 / 785. All current assertions pass.

Local verification:

- MSVC native rebuild: PASS.
- CTest: 1/1 PASS.
- Full Python suite: 90 passed.
- Ruff: PASS.
- Generated artifacts: 36 pinned outputs reproduced.
- Generic card branch guard: PASS (201 reviewed AST exceptions).
- `git diff --check`: PASS.

Hosted Source CI and ManaEngine CI for Windows/Ubuntu: pending push.
