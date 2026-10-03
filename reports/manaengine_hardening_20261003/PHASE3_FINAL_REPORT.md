# ManaEngine Phase 3 — real Meta capability validation

Date: 2026-10-03  
Branch baseline: `550da819b7e21f26e2e5fccca526b303ded15d74`  
Pinned RosettaStone source: `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`  
Verdict: **KEEP_EXPERIMENTAL**

## Outcome

Phase 3 completed three real Meta capability slices without changing the production backend, canonical registry/evidence, datasets, checkpoints, or training path. The ManaEngine workflow now targets Windows and Ubuntu only. The separate Source CI remains the acceptance gate for generated artifacts and repository Python tests.

| Package | Real profile roots | Result |
|---|---|---|
| A `shaman_spell_threshold_hand_transform_v1` | `JAIL_801`, `JAIL_803`, `JAIL_805` | Reusable per-instance held-spell progression and transform; 3/3 declarations, no card-ID behavioral branches, 0 CUSTOM. See [Package A completion](PACKAGE_A_COMPLETION.md). |
| B `profile_discover_battlecry_minion_v1` | `CORE_GIL_836` | Typed Discover continuation with the complete pinned Shaman + Neutral Battlecry-minion candidate set (139 IDs); unsupported selected results invalidate the branch. 1 declaration-only consumer, no CUSTOM. 0 canonical roots or training eligibility gained because the remaining pool outcomes are unsupported. See [Package B completion](PACKAGE_B_COMPLETION.md). |
| C `profile_endturn_simultaneous_death_lifecycle_v1` | `CATA_475`, `CATA_999`, `CORE_DRG_107` | Verification-only stress of two end-turn triggers, simultaneous deaths, Deathrattle generation, hidden-hand boundary, and clone behavior. No new card code. See [Package C completion](PACKAGE_C_COMPLETION.md). |

Package B's pool was built from the full pinned snapshot and is not filtered by implementation support. Of its 139 candidates, only `CORE_SW_072` is currently represented as supported in ManaEngine; selecting other candidates fails closed. This makes the Choice control-flow test meaningful but leaves the capability unavailable for valid training episodes when an unsupported outcome is selected.

## Behavior and correctness evidence

- Native tests: Windows Release build and CTest pass; **23 scenario groups / 398 assertions**. The tests include real Shaman transform roots, full-pool Discover branch selection and cloning, event/death lifecycle, generated-card play, action semantics, entity invariants, deterministic RNG, and existing bounded fuzz checks.
- Python tests: **81/81 full repository tests passed**. After the final diagnostic-trace adapter test was added, the focused ManaEngine adapter/action pipeline passed **23 tests**.
- Generated-artifact check: **PASS**, all 36 pinned outputs reproduced and ownership remained unique. Generic-generator branch guard: **PASS**.
- Behavior-sequence Rosetta comparison: **26 checkpoints passed** for targeted Fireball, minion combat that kills both Violet Spellwings followed by generated Arcane Missiles play, and Earthen Drake's end-turn trigger. Comparison includes visible state and semantic legal-action set after each action. Field normalization is limited to existing bridge differences (empty race→unknown, omitted hero-power/source aliases, and shared position semantics).
- Rosetta full UnitTests on the pinned `f34da0d` build: **266/267 passed**, with the same established baseline failure `[Druid : Minion] - CORE_OG_044 : Fandral Staghelmh` (two assertions and existing crash). The exact test is also recorded by the prior source-reverification baseline in `reports/meta_training_20261002_v1/native_full_suite_945d891.txt`. No Rosetta source was changed.
- Optional deterministic event trace is off by default; it records actions, zone moves, effects, damage, trigger queue/resolution, deaths, deathrattles, and choices with entity/card IDs. Native and adapter checks verify default-off behavior and clone-local trace buffers.
- Matched ManaEngine benchmark fixture (`CORE_DRG_107 × 30`, seed 7, Release, pass-only terminal matches) showed no order-of-magnitude regression. Phase 3 medians and limits are in [BENCHMARKS.md](BENCHMARKS.md). The Rosetta fixture has different cards and is not used as an apples-to-apples speed claim.

## Explicit acceptance gaps

1. **Hosted CI:** PASS on Windows and Ubuntu for commit `5261bdf0442bb839a2b1ff760f0b33c2fd1d9a1b`. Source CI run [37148547862](https://github.com/MaksimOrekhov/manamind/actions/runs/37148547862) passed artifact regeneration, ownership diff, and `python -m pytest -q` on both systems. ManaEngine run [37148547875](https://github.com/MaksimOrekhov/manamind/actions/runs/37148547875) passed Release build, CTest, and adapter/policy tests on both systems.
2. **Weapon attack/durability parity is not covered.** The currently selected real roots can destroy a weapon but the fixture has no shared supported weapon-equip path. A future honest test needs a real supported weapon and legal deck fixture.
3. **Dynamic deck summon parity is not covered.** The full pool is not pruned; current Paladin deck fixtures contain unsupported low-cost outcomes and the supported ManaEngine catalog has no honest Paladin/Neutral minion of cost ≤2 for a same-outcome bridge fixture. The native fail-closed and predicate tests remain evidence only for ManaEngine's prototype contract.
4. **The event model remains an approximation.** Replacement effects, nuanced death ordering, aura recalculation/expiry, reborn, nested triggers, and modern complete ordering were not established. This package found no counterexample in its bounded selected sequence, but it does not authorize expanding the model beyond that contract.
5. **Choice/pool semantics are incomplete for training.** A real root and continuation are implemented, but 138 of 139 current outcomes lack ManaEngine support and therefore invalidate affected branches.
6. **No card/deck is training-ready.** Canonical registry evidence, dependency closure, action/session coverage, full match-to-terminal, repeated-match behavior, and all dynamic outcomes are not complete.

The `profile_endturn_simultaneous_death_lifecycle_v1` timer was not started at package entry, so its elapsed time cannot be reconstructed. Package A/B elapsed measurements remain in their completion records; total Phase 3 active time is not reported as a fabricated estimate. The observed work session completed below the previously accepted 12-hour hard limit.

## Decision

**KEEP_EXPERIMENTAL.** Phase 3 demonstrates reusable real-card handling for per-instance held progress and a typed Choice path, plus a real event/death stress case. It does not meet the migration gate: dynamic Discover outcomes remain mostly unsupported, two requested representative parity paths (weapon durability and successful dynamic deck summon) lack an honest supported fixture, and broader event-order semantics remain approximate. Hosted Source and ManaEngine CI are green on Windows and Ubuntu for the implementation commit. Do not start training, production backend migration, or mass Meta Profile migration from this result.
