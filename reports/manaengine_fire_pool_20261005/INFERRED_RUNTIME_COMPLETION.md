# Phase 4J.1 — Inferred Fire pool runtime completion

## Decision and scope

**Runtime verdict: `INFERRED_SIMULATION_ENABLED; RULES_MEMBERSHIP_UNRESOLVED; TRAINING_BLOCKED`.**

The isolated implementation admits one pinned Fire-spell candidate manifest for bounded ManaEngine simulation. It does not change the audit verdict in `FIRE_POOL_RUNTIME_MEMBERSHIP_AUDIT.md`, claim exact Hearthstone pool membership, verify the 33 card rules, close dependencies, or grant training eligibility. It adds no Fire card implementations and changes no other card mechanics.

The untouched audit candidate remains `fire_spell_standard_20261001_candidate_v1`. The new runtime manifest is `fire_spell_standard_253932_inferred_v1`, scoped to Standard build 253932 and the 2026-10-01 metadata snapshot. Its exact sorted membership is the same 33 IDs as the candidate; its membership hash is `480f5971bdf90a339f08142a9f2e47c7650be1ddd6973241960885b20b3e0e87`. The pinned snapshot hash is `d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930`.

The candidate manifest's Git blob is unchanged from the baseline (`4998436236e924cfbb246c3626edcd4187a3776b`). The RosettaStone submodule remains pinned at `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`; this package did not modify it.

## Runtime and evidence contract

- Both Vulcanos Plume declarations now refer to the inferred manifest. The production Python adapter loads that manifest using the pinned snapshot and Standard roots, then passes it to the native catalog.
- `CANDIDATE` pools remain unusable. `MEMBERSHIP_REVIEWED` pools with unresolved exclusions now fail validation. `REVIEWED_INFERRED` is accepted only with the pinned pool/build/snapshot identity, exact membership and predicate hashes, an explicit unresolved exclusion referencing the audit, an open dependency status, and `training_eligible=false`.
- `FIRE_POOL_MEMBERSHIP_INFERRED` is attached only after the pool actually samples an outcome. It remains attached if that sampled outcome is unsupported. Unsupported outcomes are reported with the sampled ID, poison the branch, and are not rerolled or replaced.
- Existing full-hand and lethal-consumer guards run before pool sampling; these paths consume no pool RNG and acquire no pool evidence debt. Existing exact `MEMBERSHIP_REVIEWED` pools do not acquire inferred Fire debt.
- Native diagnostic trace records the exact sampled pool and card ID. Clone replay preserves sampled identity, evidence debt and RNG state.
- The canonical evidence constraint allowlist recognizes the new debt. Thus any sampled inferred outcome blocks canonical training admission; no training policy was relaxed.

The inference policy is limited to allowing this reviewed 33-card candidate for runtime experiments. It is **not** a proof that each member is in the live game's random pool, and it does not settle undocumented exclusions or the exact treatment of Standard bans. No client capture or Vulcanos-specific replay log was added.

## Tests and completion checks

Native cases F01–F15 exercise: candidate rejection before RNG; rejection of exact-review status while unresolved exclusions remain; inferred manifest admission only with evidence debt; pinned build/date/snapshot identity; exact member count/hash; one-time Fireball sampling with canonical identity and `cost_delta=-3`; deterministic RNG; clone replay; unsupported outcome fail-closed without reroll; full-hand pre-RNG guard; lethal-consumer pre-RNG guard; seed reachability of all 33 entries without support filtering; no inferred debt for an exact reviewed pool; Python/native manifest and canonical constraint gates; and rejection of changed identity/membership even when supplied hashes are recomputed. Fire-specific native group: **228 assertions passed**.

Final local checks in the isolated worktree:

| Check | Result |
|---|---:|
| MSVC 19.44.35207 Release CMake/Ninja build, including native library and Python extension | PASS |
| Full ManaEngine native executable | 78 scenario groups / 2,153 assertions passed |
| Focused inferred Fire native suite | 228 assertions passed |
| CTest | 1/1 passed |
| Python suite | 92 passed |
| Ruff | PASS |
| Pinned generated artifacts | 36 outputs reproduced; unique ownership PASS |
| Generic card branch guard | PASS; 201 reviewed AST exceptions, CUSTOM ownership checked |
| `git diff --check` | PASS |

The registry and summary regenerate only to refresh `observation_source_sha256` from `db7ffe601f46414d0a288ea155163b41295200ab02aa3aae25d9a34abf20a046` to `09aa3d3b2b5675b9d9efc965d57d3244196fe05f651571729f25c1481089eebe`. No verification status was promoted. The full pytest suite passes after regeneration.

## Remaining limits

1. Exact runtime membership is still unresolved; the source audit remains `FIRE_POOL_MEMBERSHIP_STILL_UNRESOLVED`.
2. Only `CORE_CS2_029` is supported by the focused runtime fixture. The other 32 remain unimplemented outcomes; sampling one intentionally invalidates that branch without reroll.
3. The manifest dependency closure is open and training eligibility remains false. Do not use this path for training or claim a rules-verified Vulcanos simulation.
4. Lethal Vulcanos consumers and full-hand generation continue to fail closed under existing guards.

## Provenance

- Requested baseline: `eb3715f5db8629bff226f0ad4630f33db4312090`.
- Work was performed in the isolated worktree `C:\Users\Максим\.codex\worktrees\phase-4j1-inferred-fire\ManaMind`; primary `E:\ManaMind` was not modified.
- Source audit and the old candidate manifest were preserved without edits.
- Hosted Source CI run [37313767634](https://github.com/MaksimOrekhov/manamind/actions/runs/37313767634) passed on Ubuntu and Windows, including generated-artifact reproduction and pytest.
- The first ManaEngine CI run [37313767660](https://github.com/MaksimOrekhov/manamind/actions/runs/37313767660) built and passed CTest on both Ubuntu and Windows, then exposed two Python assertions that still expected the Fire pool to be absent. The production adapter now loads the inferred manifest, so both tests were corrected to assert fail-closed handling of the deterministic unsupported sampled outcome `TLC_222`. The two focused tests and full local pytest passed after that correction. The post-correction hosted ManaEngine run is required to close this finding.
- After that correction, Source CI run [37314456093](https://github.com/MaksimOrekhov/manamind/actions/runs/37314456093) passed on Ubuntu and Windows; ManaEngine CI run [37314456121](https://github.com/MaksimOrekhov/manamind/actions/runs/37314456121) passed build, CTest, and adapter/policy tests on both Ubuntu and Windows.
