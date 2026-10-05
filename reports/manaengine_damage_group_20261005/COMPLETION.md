# Phase 4H.1 — DamageGroupLocalV1 completion

## Verdict and revision boundary

**DAMAGE_GROUP_LOCAL_V1_PARTIAL** — local acceptance passed; hosted acceptance pending at the implementation commit.

- Branch: `codex/manaengine-first-deck`.
- Implementation baseline: `b659343f437e968bceb08041e9ac0b3893c16f73`.
- RosettaStone gitlink remains `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`; no RosettaStone production changes or native-evidence promotion.
- Implementation commit and final report HEAD: recorded after hosted verification below. A report cannot contain its own future Git hash; the report commit is the final document revision.

## Delivered contract

`DamageDispatch`, `DamageEventOrder`, `DamageFrameStage`, `ReactionKind`, `Prevention`, `EntityHandle`, `DamagePacketIntent`, `PacketOutcome`, `DamageReactionSnapshot`, and `DamageGroupFrame` are typed, private engine concepts. `EngineState` owns the value stack, independent group/event counters and bounded work counter. No frame or hidden continuation enters an observation.

Fixed admitted minion areas freeze targets and entry order, validate before damage/RNG, mutate every packet, emit `GROUP_MUTATIONS_COMPLETE` with group/parent/event identities, then discover each event's reaction list at that event's start. Only that list is frozen. Child work completes before the next parent event. A newly eligible watcher can participate in a later event without becoming a retroactive parent target.

Single-target instructions complete their packet and reactions before follow-up. Scalar DirectSpell accounting and bounded Lifesteal remain mutation-stage work; Raincaller attack is reaction-stage work. Self-generation retains positive-health, identity/controller/activation/silence/descriptor guards. Mixed self/Raincaller order is unsupported.

No `stabilize()` occurs inside a group or between sequential instructions. Existing outer batch death removal, FIFO Deathrattles and guarded intrinsic Reborn own death processing. Public actions, observations and cloning require quiescence; public copy construction is unavailable. Active Choice/suspension, 64-frame depth or 4096-work exhaustion reject the branch. These budgets are engineering bounds, not game rules.

Structural errors reject before group damage/RNG. Reaction-stage failures preserve all area mutations and earlier sampled RNG, never reroll, unwind frames, poison the session and preserve the first reason. Diagnostic trace/private test inspection remain available; public usable continuation does not.

No card-ID behavioral branch, declaration operation, global scheduler or new reactive-card mechanic was introduced. Nested state/lifetime fixtures use test-only typed frame access, not executable card declarations.

## Actual production diff

| File | Change |
|---|---|
| `experiments/manaengine/include/manaengine/engine.hpp` | Typed structures, owned stack/counters, private copy and shared helpers |
| `experiments/manaengine/src/damage_group.cpp` | 200-line shared preflight/mutation/barrier/dispatch/continuation implementation |
| `experiments/manaengine/src/engine.cpp` | Migrate callers, queued source lifetimes, quiescent APIs, preserve first failure; scope instance validation pointers before child work |
| `experiments/manaengine/CMakeLists.txt` | Link shared implementation into core |
| `src/manamind/integrations/manaengine/engine.py` | Consistent adapter UnsupportedSimulationError for observation/clone |

Shared production diff: approximately **312 added / 55 removed lines across five files**, including the new source (Git line counts; not a complexity or semantic-coverage metric). README documents the contract. Tests modify existing native and adapter suites and add `damage_group_tests.hpp`. Catalog/declarations/pool manifests remain unchanged.

## Caller audit

| Caller | Disposition |
|---|---|
| Vulcanos `END_TURN_OTHER_MINIONS_DAMAGE` | Fixed 3 Effect area, source excluded by identity, both sides, entry order; no Spell Damage boost. Queued source may be mortal while still in Play |
| `CORE_CS2_032`, `CATA_582`, `EDR_570` damage mode | Ordinary minion-area shared path in reviewed modifier states; conditional Spell Damage activation rejects before mutation |
| Targeted damage / outcome follow-up / HeroPower | Single packet plus admitted reactions; follow-up waits for completed group |
| Sleet Storm | Two single instructions; current Spell Damage reevaluated between them; mortality/provider guards preserved, no intermediate death drain |
| Arcane Missiles | MISSILE_TOTAL count once; each packet completes before live next-target selection; mortal targets excluded; deterministic RNG retained |
| Hero-containing areas / enemy-area EOT / Explosive Trap | Scalar-only grouped mutations where no reactive ambiguity; self/Raincaller reactive combinations explicitly reject |
| Combat | Paired scalar mutation path; reactive pairs reject before either damage packet/RNG; no claimed general combat reaction ordering |
| Explosive Runes | Reviewed scalar compound and Bookkeeper control preserved; reactive minion OR excess-hero variants preflight reject; Secret ordering unchanged |
| Single hero damage / fatigue | Shared single packet path; attribution/prevention/accounting preserved; no new hero reaction capability |
| Highest-health Secret damage | Existing live selection then single packet; unsupported outcome consumes its actual selection RNG, never rerolls |
| Arcane Barrage | No implementation; `BLOCKED_DESIGN_REVIEW / MORE_RULES_EVIDENCE_REQUIRED` |

Static Spell Damage captured for one area remains fixed when its provider is wounded in that area; outer deaths occur later. Undamaged conditional contribution activation within an area is guarded. Existing mortal-provider-before-instruction and Sleet pending-mortality guards remain. Removed/transformed/control-changed/silenced queued sources fail closed; current health is not a universal cancellation rule.

## Historical corrections

The Phase 4G record remains historical; no old PASS/fingerprint was rewritten.

1. Missing/candidate Fire generation: **both Plumes 5 -> 2 before the first reaction fails**, not left 2/right 5. RNG remains unchanged before that generation.
2. A later queued Vulcanos wounded from 1 to mortal still resolves while in Play: earlier body ends at **5**, not 8; outer phase then removes the mortal body.
3. Old scalar/reactive CATA_475 and shielded Runes/Raincaller combinations are now explicit negative controls for unreviewed hero/compound ordering. Ordinary Runes Shield/excess remains a positive control; dedicated reactive negatives remain tested. Invalid attribution now poisons the branch instead of allowing continuation.

All **57 baseline native group calls remain, in their original order**; including finite-pool, TakesDamage, Dark Gift and Reborn coverage. Eight new group calls run before them. Baseline 1607 assertions plus 100 new assertions = 1707. Semantic corrections replace reviewed expectations, not delete regression groups.

## Executed local verification

Final build: `experiments/manaengine/build-damage-group-v1`, Release / Ninja / MSVC 14.44 / Python 3.12. Loaded extension and test executable hashes are in [SOURCE_IDENTITY.json](SOURCE_IDENTITY.json).

| Check | Actual result |
|---|---|
| Native focused `manaengine_tests --damage-group` | **8 groups / 100 assertions PASS** |
| Full native `manaengine_tests` | **65 groups / 1707 assertions PASS** |
| CTest | **1/1 PASS**, invokes full native suite |
| Full pytest | **92 passed**, 10.55 s |
| Native adapter + pipeline + policy | **66 passed**, repeated after final pointer-lifetime cleanup |
| Ruff (including adapter tests) | PASS |
| Generic card-identity/CUSTOM ownership guard | PASS, 201 reviewed existing exceptions |
| `check_generated_artifacts.py` | PASS, **36 pinned outputs reproduced** |
| `git diff --check` | PASS |

Family mapping: DG01/02/07/08 area barrier/prevention/entry-order; DG03–06/09 lethal guards, batch deaths/Deathrattles and Reborn; DG10–12 child order/source/consumer lifetimes; DG13/14 existing EOT/Secret controls; DG15–17 Sleet accepted/guarded states; DG18 conditional-modifier preflight; DG19 missiles/live mortality; DG20/21 pool/RNG failure; DG22 clone; DG23 structural/budget/quiescence; DG24 Raincaller/accounting; DG25 retained Bookkeeper/Runes plus compound negatives; DG26 reactive combat negative. DG27 is evidence-only. No generalized missile-trigger candidate mutation or production nested-reaction mechanic was added just to manufacture a fixture.

Python adds real Mage-session Vulcanos failure/clone/poison boundary and minion-area adapter controls. Synthetic fixtures/test catalogs are regression evidence, not a full legal-deck or rules-admission claim.

## Correction/build effort

- Timer start: **2026-10-05 07:56:18 UTC**; excludes initial instruction/repository reading. Local work remains an observed elapsed interval, not a retroactively inferred CPU-time measurement. Final elapsed and CI waiting recorded below.
- **12 local build invocations**: eight incremental implementation iterations, one fresh diagnosed build, one prefix-reconfigure/no-op, one forced consumer rebuild to restore header dependency tracking, one final pointer-lifetime rebuild.
- One substantive semantic correction during implementation: initial area modifier guard overrejected an already admitted static-aura death case; refined it without relaxing conditional activation or next-step mortality guards.
- Test/fixture correction rounds: invalid-attribution poison expectations/public inspection; guarded hero/Runes mixed cases; adapter unsupported class -> supported Mage fixture and misplaced existing assertion restored. Final pointer-lifetime review tightened source code without changing intended outcomes.
- Local environment retries: sandbox temp/cache writes; dependency-free identity import needed its explicit native module directory; Russian MSVC include-prefix decoding prevented Ninja header tracking. VSLANG alone did not fix it. A separate build was preserved, its local configured prefix corrected, all consumers recompiled. `ninja -t deps` now lists `engine.hpp` and `damage_group_tests.hpp`; latest two assertions actually execute. No build directory/log/checkpoint was deleted and no project CI check bypassed.

## Identity and admission

[SOURCE_IDENTITY.json](SOURCE_IDENTITY.json) records normalized per-file identities and the aggregate source fingerprint, together with the actually loaded local binary hashes. Normalization: CRLF -> LF; SHA-256; aggregate sorted compact JSON of the listed production/catalog paths. This is an experiment-specific identity record, not a replacement for canonical evidence gates.

- Baseline: `fab29a32ab7a8c49cf205eb088102d9e2eab9585b20381eeb485b3a57349ea1f`.
- New source: `ac55f42e32bfda0890534814efae12894670c5283a3682fd89ff0348b4b6fef2`.
- Observation/encoder schema remains **16**. Public frame fields: none.
- Older ManaEngine scoped runtime claims are historical against their former identities, not automatically current under this contract. This family is reverified on the new build; no copied PASS or old fingerprint is used as current evidence.
- Canonical registry/report bytes after normal regeneration: **unchanged**. Its RosettaStone/generator evidence inputs did not change; ManaEngine is a separate experimental backend.
- Registry roots gained: **0**. Dynamic closures gained: **0**. Training eligibility delta: **0**.
- Fire runtime membership remains CANDIDATE/unloaded; Vulcanos full support, Barrage, `DECK_READY` and training remain blocked. Whelp/training/search were not started.

## Hosted acceptance and stop

Pending implementation push: Source Windows/Ubuntu must actually execute pytest and artifact checks; ManaEngine Windows/Ubuntu must actually execute Release build, CTest and adapter/policy steps. This section will record run IDs, commit SHA, URLs and individual step results after they finish. Final documentation-only HEAD can reuse implementation native CI only with identical production/test trees explicitly established, while its own Source CI must pass.

After hosted acceptance, push the final report and stop. No architecture stop-condition was encountered; remaining unsupported combinations are deliberate admission bounds, not a hidden scheduler redesign.
