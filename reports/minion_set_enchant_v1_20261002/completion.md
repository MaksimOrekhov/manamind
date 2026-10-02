# Completion Record — minion_set_enchant_v1

Implementation and final checks completed 2026-10-02 17:17:13 UTC. Started
16:25:04 UTC: **52m09s elapsed wall clock**, including reading, semantic review,
authoring, debugging, build waits and verification. Completion documentation
was written afterwards. Active authoring/review/debug time and the first four
individual build durations were not instrumented: do not infer precise effort
or extrapolate future throughput from this number. Build invocations 5/6/7 were
measured at **7.414s / 8.878s / 10.995s**, final adjacent native regressions
at **19.399s**.

## Delivered scope and reuse

Roots: RLK_048, TLC_233, TIME_447. Dependencies: ICC_210e and ULD_191e,
with their existing owners preserved. Deferred outliers remain unimplemented.

- **3 declaration-only consumers**, one renderer. No consumer identity is passed
  into task rendering; no root-specific behavior branch was added in Python/C++.
- **0 new CUSTOM consumers/outliers**. An independent TARGET_MINION/+2 Health/
  Taunt parameter variation is tested without renderer changes; it is a control
  variation, not a fourth registered Standard root.
- Strict finite effects, fields/types/bounds, reviewed membership, metadata and
  owner fingerprints; dependency references and duplicate registration fail
  closed. New matching consumers change declarations; newly reviewed rules and
  evidence are still required. The evidence producer cannot silently expand its
  approved three-root/two-dependency scope.
- **4 new narrow METADATA_VALIDATION AST exceptions** for membership/duplicate
  checks and catalog lookups; no behavioral exception. Renderer inventory has
  zero card-identity findings. Existing baseline exceptions were preserved.

## Shared implementation size

Line counts include blank lines/comments, not just executable statements.

| Area | Actual change |
|---|---:|
| Shared finite renderer/parameter contract | 84 new Python lines |
| Schema/ownership validator and deterministic generator driver | 142 new Python lines |
| Existing native primitive corrections, 6 files | 39 added / 4 removed lines |
| Native registration + generated umbrella include | 3 added lines |
| Generated root C++ output | 47 source lines + 10 header lines |
| Bridge changes including controlled diagnostic fixture | 84 added lines |
| Domain/import/encoder parity, excluding bridge | 21 added / 2 removed lines |
| Canonical registry integration | 26 added / 1 removed lines |
| Package verifier | 176 new Python lines |
| Native independent family scenarios | 276 new C++ lines |
| Python package source tests | 96 new Python lines |

Existing primitive corrections were required by the approved semantics: hero
Shield must absorb damage before armor; spell/hero-power targeting must respect
Elusive; bounce must remove granted protections; fixed additive Attack/Health
must not bake in external aura bonuses. No new task, enum or ABI layout was
introduced. Attribute-header changes triggered rebuilding all affected native
consumers. Observation schema **v7** exposes hero Shield and both protections,
preserving unknown values; historical checkpoints are retained and rejected.

## Corrections and builds

**4 correction rounds after failing executions**:

1. First compile: corrected CardProperty/REQ namespace and test base-tag API.
2. First native family run: fixed the three shared targeting/reset/aura defects
   found by independent expectations. Numeric expectations were retained.
3. First bridge run: corrected the diagnostic absent-target assertion, which
   collided with valid hero entity ID 0. Production action behavior was unchanged.
4. Intrinsic protection boundary control: corrected the existing generic ELUSIVE
   metadata mapping to both spell/hero-power protections. The root owner/status
   of the Faerie Dragon control was not changed.

Separately: prebuild interface review corrected Battlecry task activation and
SelfCondition wrapping; source checks removed an unused import and required
explicitly reviewed metadata AST exceptions. Final review tightened malformed
schema rejection and fixed verifier scope, and added empty-hand/repeat cases.

**7 configured build invocations**: first failed; six passed. Invocations 2 and
3 rebuilt core/tests and relinked bridge; invocation 4 did no compilation and
recorded the changed scenario identity; invocation 5 rebuilt the enlarged
UnitTests family and recorded final identity. No clean build or per-card build.
Invocations 6/7 rebuilt the final bridge observation control and then core/tests/
bridge for intrinsic metadata legality. One explicit CMake configure discovered
the new source/test files. Native family producer ran six times: first native
failure, second boundary failure, then four successful executions as final
review extended/rechecked boundaries. The separate intrinsic protection verifier
failed once before the loader fix. Three full Python suite runs passed
(65, 68, 68 tests), plus an initial package-only run (21 tests).

## Final verification

| Check | Result |
|---|---|
| Full Python suite | **68 passed**, 9.09s |
| Package native scenarios | **17 cases / 195 assertions passed** |
| Production-boundary fixtures | **9 passed**, legal/illegal character targets, hands, Locations, visible flags and import/encoder parity |
| Adjacent native regressions | **70 cases / 425 assertions passed** |
| Existing four verification packages | **13 cases / 883 assertions passed**, all prior 11 scoped root entries refreshed by actual execution |
| Existing hand/weapon import parity + intrinsic protection control | PASS |
| Pinned regeneration/unique ownership | **30 outputs reproduced** |
| AST guard, Ruff, both Git diff checks | PASS |

Final native executions total 100 scenario executions / 1503 assertions. This is
package/regression evidence, not the whole native test suite or match coverage.
Actually loaded bridge matches the configured recorded build artifacts; hashes
and complete source/profile identity are in explicit package evidence.

## Canonical registry / closure delta

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Standard roots | 1185 | 1185 | 0 |
| Direct source registrations | 167 | 167 | 0 |
| Generated registrations | 176 | 179 | +3 |
| Roots without detected text rules | 842 | 839 | -3 |
| CURRENT scoped verified roots | 11 | 14 | +3 |
| Historical stale entries | 5 | 5 | 0 |
| Complete reviewed root effect closures | 0 | 3 | +3 |
| Unique known dependency nodes | 193 | 193 | 0 |
| Unresolved dynamic pool hypotheses | 318 | 318 | 0 |
| Training-eligible roots / decks | 0 / 0 | 0 / 0 | 0 |

Two existing enchantment nodes now have CURRENT scoped contract evidence.
Three new declared dependency edges remain labelled source candidates in the
general graph (+3 unreviewed candidate edges); root-level FULL_RULES dependency
reviews explicitly cover their exact graph fingerprints and certify the three
effect closures. Graph absence alone was not used to certify completeness.

The eleven old scoped entries became stale under conservative global identity
changes, then were refreshed by reproducible runs. Their limited scopes were
not promoted. Old five historical stale entries remain stale. Frozen expectations
and manifest identity capture the TLC_233 snapshot interpretation; official
client timing replay is not claimed.

## Remaining boundaries

CURRENT scoped rules/actions and reviewed fixed effect closure do **not** satisfy
FULL_PROFILE rule/dependency scope or session/match gates. DK hero setup remains
blocked: RLK_048 effect/legality is checked, its fixture uses an available hero,
and no playable DK session is claimed. Druid/Priest opening and invalid-handle
checks do not certify complete modern decks or full games. Full Standard remains
BLOCKED. No datasets/checkpoints/historical logs were overwritten; prior evidence
is archived here. No training, evaluation or next package was started.

Machine-readable measurements: [completion.json](completion.json).
