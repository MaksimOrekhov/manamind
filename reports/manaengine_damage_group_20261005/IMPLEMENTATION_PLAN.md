# Phase 4H — bounded implementation plan and acceptance gate

Report-only result: **DAMAGE_GROUP_LOCAL_CONTRACT_BOUNDED**.
No implementation started. This is a proposed next package, not a completed support package.

## CAPABILITY PACKAGE PROPOSAL

### package_id

`damage_group_local_v1`, proposal revision 1, 2026-10-05.
Inputs: ManaMind `af0a599399b0694f5f7ad92af5834f0be63b38bc`; RosettaStone `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`; pinned `standard_full_20261001_v1`.

### semantic capability

Proposed **REUSABLE_CAPABILITY**: separate ordinary area's apply-all mutation from successful damage reactions; single-packet reaction completion before next instruction; nested child completion before parent sibling; existing outer phase owns deaths. Exact typed specification/admission/failures are in [DAMAGE_GROUP_ARCHITECTURE.md](DAMAGE_GROUP_ARCHITECTURE.md).

Second independent declarative control: enemy minion area versus both-side minion area with source exclusion, same helper. Both must work without code/ID branches. Single-target continuation is a separate typed mode, not arbitrary executable declarations.

### existing primitives

ManaEngine `DamageKind`, `DamageAttribution`, `DamageOccurrence`, `EffectStep`, current SpellEffectContext evaluation contracts, state-owned RNG, entry sequences, batch death/guarded intrinsic Reborn and pool manifest validation. Shared scalar packet arithmetic already exists.

RosettaStone references: `DamageTask`, `ConsecutiveDamageTask`, `Generic::TakeDamageToCharacter`, Tasks/Triggers/Power. Their queue/death details are not copied as rules truth; see source audit in the rules review.

### candidates / dependencies

| Consumer family | Reviewed candidates / controls | Scope |
|---|---|---|
| Fixed minion-area Effect | `CATA_488`, independent fixture variation | Body damage barrier only; no Fire closure |
| Ordinary spell minion area | `CORE_CS2_032`, `CATA_582`, `EDR_570` damage branch | Only stable-modifier admitted states |
| Sequential targeted/random | `CATA_485`; existing damage-outcome families | Preserve accepted live second-step contract; no unreviewed mortality/lifetime admission |
| Split-total missiles | `EX1_277` | Existing count contract + complete per-hit reactions |
| Self damage consumers | `CATA_488t`, `CATA_488t2`, reviewed fixture pool | Existing v1 lifetime; production Fire pool still blocked |

Dependencies: Plume descriptors and candidate Fire pool remain unchanged; existing spell modifiers/Raincaller, target sets and intrinsic Reborn controls require interaction verification. No new dynamic pool is needed to test a barrier with independently reviewed test-only pool/consumer fixtures. No restricted production Fire pool substitution.

### required shared changes

1. Split scalar packet mutation/result from reaction execution.
2. Add value-owned frames, independent group/event identities, explicit dispatch/order and outer phase guard.
3. Dispatch events then their immutable reaction lists, depth first for child work.
4. Migrate admitted area/step/missile routes; preserve scalar accounting and attribution.
5. Correct queued-source/minion ordering assumptions using independently reviewed expectations.
6. Add strict contract fields/allowlists only where declaration-owned timing is needed; reject unknown combinations.
7. Audit every `deal_damage()` caller; none may bypass the barrier for reactive damage accidentally.

No behavioral card-ID condition is required. If an outlier demands one, defer/CUSTOM-first. No general scheduler, CardInstance rewrite, ML work or pool admission.

### expected unlock count / effort

New registered roots: **0 required**; these are already declared consumers. Verified root/dependency closure/training gains: **UNKNOWN, not forecast as >0**. Vulcanos remains Fire blocked, and scoped barrier verification does not close decks.

Expected reuse: one shared barrier serving multiple existing declarative minion areas and independent parameter controls. Actual accepted-consumer count must be measured after verification, not all IDs in this audit counted as supported.

Authoring/debug/build duration cannot be reliably estimated from this report. Start an active elapsed timer at implementation, split authoring/review/debug/build/evidence effort, record correction cycles and actual modified shared lines. Stop if uncertainty requires expanding architecture; no arbitrary deadline or coverage percentage.

### custom / deferred outliers

`TIME_855` selection/topology; compound Runes reactive ordering; hero-containing area event order; exceptional historical AoEs; intra-area changing Spell Damage; predamage replacements; forced death phases; active Choice; new cross-zone/global watchers. These are semantic differences or missing rules evidence, not reasons to create ID branches.

## Ordered migration points

| Step | Current source | Required change / guard |
|---|---|---|
| 1 | engine.hpp:247–261 state and occurrence | Typed value result/frame, distinct counters, no pointers, append identities |
| 2 | engine.cpp:213 packet arithmetic | `apply_damage_packet` performs mutation/scalar accounting only; returns result |
| 3 | engine.cpp:203, 433 reactions | Typed P3 self/first-spell event handlers. Review mixed trigger order; preserve v1 negative cases |
| 4 | engine.cpp:391–415 compositions | Area calls shared group; outcome checks/next effects after completion |
| 5 | engine.cpp:377 missiles | Recompute live targets after each completed single group; `MISSILE_TOTAL` once |
| 6 | engine.cpp:506–512 EOT | Capture source values, entry-order target events, complete source group before next queued source; no health-only cancellation |
| 7 | engine.cpp:473/484, combat/HeroPower/fatigue callers | Single wrappers where exact; explicit defer/guards for ambiguous reactive compound/hero/combat paths. No silent selector-wide migration |
| 8 | engine.cpp:550 `stabilize`, 525 Reborn | Assert frames empty at outer death drain; preserve batching/guards, never add per-packet drain |
| 9 | declaration parsing/bindings | Only needed typed fields/version; regenerate declared artifacts; no observation schema bump for synchronous hidden frames |

Combat can use a separately reviewed paired mutation profile with defender-first received-damage events, or reject unreviewed reactive combinations during initial rollout. Do not retain an unchecked immediate-reaction bypass while claiming all damage consumers migrated.

## Exact adversarial native scenarios

All are **planned**, not executed in this architecture task. Use independent expected traces, not renderer-derived smoke. Test-only fixtures do not add production card support or pretend Fire membership is solved.

| ID | Setup | Independent expectation / stage |
|---|---|---|
| DG01 | Two admitted TakesDamage fixtures, 5 health each, fixed 3 minion AoE | Both 2 before first reaction; one shared group ID, two ordered events; generation controller correct |
| DG02 | Same, board position reversed relative to entry sequence, on opposite sides | Event/reaction order follows entry sequence, not side/position; group membership identical |
| DG03 | Consumer 2 health + consumer 5, damage 3 | Both mutations first; v1 rejects lethal consumer at P3 before its RNG, no death/label; no 'survives' substitution |
| DG04 | Two consumers 2 health, damage 3 | Both -1 before first lethal-v1 rejection; no fabricated successful reaction/death phase |
| DG05 | Ordinary non-consumer 2 health + consumer 5 | Ordinary target remains mortal during surviving consumer reaction, then dies only at outer boundary |
| DG06 | Two ordinary lethal Deathrattle targets, same area | Both damage first; outer boundary batch-removes both, then FIFO supported Deathrattles. No first Deathrattle before second packet |
| DG07 | Shielded consumer 5 + ordinary consumer 5, damage 3 | Shield gone/health 5/no successful event; other health 2/event; prevention does not stop group |
| DG08 | Immune consumer + ordinary target; zero group variation | Immune untouched/no event; zero no Shield loss/event/RNG; ordinary positive packet preserved |
| DG09 | Intrinsic Murmy 1 health + ordinary 4, damage 3 | Original Murmy mortal and other 1 before phase end; guarded Reborn afterward: new ID, health 1, no second Reborn; existing slot debt unchanged |
| DG10 | Admitted reaction fixture damages current area source lethally | Parent area mutations already done; captured attribution retained; source removed only at outer phase boundary. Actual source removal/transform variant rejects |
| DG11 | Parent events A then B; A's test-only scripted handler creates child C | Trace parent mutations, A, complete C and its supported nested consequences, then B; no global FIFO child-after-B behavior |
| DG12 | Child changes/removes B consumer identity/controller | Revalidate B at its event/activation, fail before generation RNG; do not target replacement or silently skip |
| DG13 | Two EOT Vulcanos, Plumes silenced, later body's health 1 | Earlier area makes later body mortal; later queued body still damages earlier from 8 to 5; remove mortal only at phase end |
| DG14 | EOT sources physically reordered and mixed timed/Secret windows | Preserve activation order and independent existing Secret window; no area-local global trigger drain |
| DG15 | Own undamaged END_022 1/3, Sleet targets it; enemy ordinary 4 health | First packet 2 leaves Seer 1; second instruction sees +2 Spell Damage, deals 3 enemy. No death drain between instructions |
| DG16 | Sleet first hit kills sole ordinary enemy; random second set empty | For a subsequently reviewed ordinary-mortality extension: no second selection RNG, no Deathrattle/new Reborn target before spell phase end. Current blanket mortality guard remains until this extension is reviewed |
| DG17 | Sleet mortally wounds own Spell Damage provider | Preserve explicit unsupported guard before second amount/selection; no stale bonus or invented stabilize |
| DG18 | All-minion spell could activate/deactivate own conditional Spell Damage during area | Preflight rejects before mutation/RNG until intra-group rule reviewed; stable +2 control evaluates one amount |
| DG19 | EX1_277 with +2, reaction changes enemy living candidates between hits | Total count 5 once, each 1; each child reaction complete before next live target selection; mortal targets excluded, no per-hit count growth |
| DG20 | Missing/candidate pool, malformed count/hash, full hand after area | All ordinary area mutations visible before P3 rejection; no generation RNG; if earlier admitted sibling sampled, its prior draws retained |
| DG21 | Reviewed test pool samples unsupported outcome | RNG advances by actual sampler path; unsupported branch, no reroll, no replacement by supported card |
| DG22 | Pre-action clone, same area/nesting/random script applied to both | Equal final full state/trace/group IDs/counters/RNG; reversed replay order between clones independent; active-frame cloning rejected |
| DG23 | Invalid target/unknown contract and budget exhaustion | Structural error pre-mutation/pre-RNG; budget error poisons branch without fake terminal or continuation |
| DG24 | Existing Raincaller + ordinary spell area, shield/armor/overkill variations | Scalar DirectSpell turn accounting unchanged; attack reaction after mutation barrier, once/turn; Effect/Combat/HeroPower never mislabeled DirectSpell |
| DG25 | Unmodified Bookkeeper + Explosive Runes | Preserve original target identity and earlier reviewed Kindred/After Play order; Deathrattle remains outer-phase. Reactive compound variants stay guarded |
| DG26 | Reactive combat pair / hero-area profile | No first received-damage reaction before required paired mutations; use independent defender-first/profile expectations. If profile not delivered, explicit fail-closed test instead |
| DG27 | Barrage extra-target mortality/removal plus static/live modifier controls | Evidence-collection discriminator only until topology reviewed; do not encode guessed expected runtime outcome into production tests |

Nested test fixtures should drive typed frame execution through test-only access; do not introduce arbitrary executable declarations, card-ID branches or a production watcher solely to manufacture a test.

## Acceptance after a future implementation

1. Native full suite plus group family passes; known tests with challenged expectations changed only with reviewed rationale. Preserve all Phase 4E/4E.1, Reborn and Dark Gift groups/calls.
2. Real adapter/action-policy tests for migrated public paths; no hidden internal group data enters observations. Quiescent clone/RNG controls pass.
3. Explicit evidence from actual configured build/loaded extension. Changed fingerprints stale dependent records honestly. Fire/unknown consumers remain blocked; no blanket status restoration.
4. Full pytest, Ruff, generated artifacts, identity guard, branch guard, `git diff --check`; regenerate only changed authoritative outputs by standard ownership rules.
5. Source CI and ManaEngine CI green on Windows/Ubuntu, with actual pytest/CTest steps. Do not reuse historical runs as new implementation verification.
6. Completion record: actual consumers, shared lines, correction cycles/builds, active effort, changed traces/expectations, registry/closure/training deltas separately. No training.

## Implementation model recommendation

**Sol High** for the first implementation. The code change can be local, but phase ownership, nested ordering, source lifetimes, accounting and invalid-branch RNG need coordinated review across multiple callers. Sol Medium is reasonable only after this first contract and family suite are stable. Luna High is not recommended for the initial boundary correction; later declaration-only migrations under proven contracts can use it.

## This analysis completion

Deliverables: five architecture artifacts in this folder. Production/Catalog/tests/evidence/registry/pools unchanged. No builds/test suites run or new PASS claims made. Historical native 57 groups/1607 assertions is the Phase 4G result only. Report validation is limited to file/link/scope review and clean diff formatting. Commit and push this report, then stop.
