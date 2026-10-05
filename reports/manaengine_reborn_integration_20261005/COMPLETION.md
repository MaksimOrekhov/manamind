# Phase 4F.1 вЂ” Intrinsic Reborn integration completion

## Scope and result

- package_id: `intrinsic_reborn_v1`.
- baseline: `adbbc62edd664268ba30a4b267f2d3495bb49651`.
- reviewed reference: `a35ddc6f0b0bd736d6a3b30e2a31884e39204cc1`; selective port, no merge/cherry-pick.
- real consumer: `CORE_ULD_723` Murmy, declaration-only (1/1); independent synthetic Rush/keywords and draw Deathrattle controls.
- CUSTOM consumers enabled: 0. No card-ID behavior branches.
- one shared intrinsic Reborn capability. No granted Reborn or full-enchantment restoration.
- active implementation/verification interval: 2026-10-05 05:23:34вЂ“05:43:58 UTC, about 20m24s before report/commit/hosted CI. CI waiting excluded; final bookkeeping recorded below.
- verification correction cycles: 3 (reverse-order slot expectation, adapter test using domain entity_id rather than native action handle, and hosted-CI intrinsic-vs-granted metadata guard failure); production core semantic fixes: 0; shared adapter metadata fix: 1.
- builds: 4 incremental builds; no clean build and no Rosetta rebuild.

## Implementation boundary

Shared C++ changes: intrinsic/active flags, minimal RebornPending, ordered death handles and current-slot sequential removal, FIFO Deathrattles before batch returns, fresh definition construction, survivor membership/mortality guard, owner/controller and full-board fail-closed bounds, typed evidence constraint and binding export. Shared Python changes: intrinsic keyword authoring/metadata mapping and stable debt-ID validation. One declarative real card added.

Pending data stores owner/card ID/dead entity/current recorded slot/play order only. It is a local synchronous batch, not a CardInstance copy or hidden feature. Return uses fresh identity/activation/provenance `REBORN`, definition stats/keywords, Health 1, consumed Reborn, reset modifiers/counters/cost/Prepare/spell bonus/grants. Intrinsic Rush permits minion attacks. Silence suppresses return; Transform uses replacement intrinsic flags. INSTANCE_COPY_V1 rejects active or intrinsically Reborn sources.

Sequential model regression outcomes:
- A X B: A X-prime B, no new debt.
- A X B Y C, X older than Y: A X-prime Y-prime B C.
- A X B Y C, Y older than X: A X-prime B C Y-prime.
- D X B, only X has Reborn, D dies first: X-prime B.

Same-side >=2 deaths with an unsilenced active Reborn return records `REBORN_MULTI_DEATH_SLOT_UNVERIFIED`. Session remains valid; independent canonical admission rejects debt even with global gate disabled. Opposite-side single deaths, no-Reborn and silenced-Reborn batches remain debt-free. Clone preserves debt; an earlier clean branch remains clean. Unknown serialized debt IDs fail explicitly. Debt is excluded from gameplay features.

The provisional multi-death slots are mechanically tested, not claimed current-client replay verified. Cross-side ordering requires a future review once order-sensitive summon effects exist. Final survivor identity/card/order and mortality checks reject current unsupported intervening paths; future transient board mutation hooks require review before support.

## Executed local acceptance

| Check | Observed result |
|---|---|
| MSVC Release native executable | **55 groups / 1567 assertions PASS** (baseline 51 / 1494; +4 / +73) |
| Full pytest (`python -m pytest -q -p no:cacheprovider`) | **92 PASS** |
| Adapter + pipeline + Policy suite | **63 PASS** (including 2 new real Murmy integration cases and an intrinsic-vs-granted metadata regression) |
| Ruff src/tests/scripts/experimental tests/scripts | PASS |
| Generator identity guard | PASS; 201 reviewed exceptions unchanged |
| Generated artifacts, second regeneration | PASS; 36 pinned outputs reproduced |
| Fire/Whelp frontier ledger `--check` | PASS; 105 unique roots; memberships 33/77/65/63 unchanged |
| `git diff --check` | PASS |

All Phase 4E, 4E.1 Dark Gift and Phase 4F groups retained. Native coverage includes real reciprocal combat and typed damage packets, single/second death, full-board vacated-slot, Silence/Transform/terminal, reset Dark Gift grants, Rush, clone RNG, both multi-death activation orders, same/opposite-side debt granularity, all batch Deathrattles before any return, board mutation/secondary death/transform/full-board/control-change fail closed, and bounded copy rejection.

## Registry, identity and admission

Domain schema **16** and Policy **v3** unchanged. Existing public Reborn flag semantics retained; adapter now exports the active flag on both boards. Added stable evidence ID changes observation source fingerprint:

`33ce5685f7aa926a0f604e8e2f2d1efa1e52d11de9b2d9afbee0228664b7f8dd`
в†’ `9ec9e5a13c1a1aa54a3733bfed4513f13a2795b18ad85b3212a879baba13aaa5`.

Initial regeneration correctly reported registry/summary stale; both regenerated, subsequent check reproduced all outputs. No fingerprints copied into verification evidence and no status promoted. Canonical registry changed only current observation identity: 1185 roots, 0 current VERIFIED_SCOPED, 27 stale scoped evidence, 192 nonroot nodes, 318 unresolved pools, training eligibility 0 remain unchanged. Verified-root delta 0; closure delta 0; training delta 0.

Fire/Whelp manifests stay CANDIDATE/OPEN/training-disabled. `EDR_100t9` Persisting Horror remains selectable unsupported; `CAP_800` and all granted/full-enchantment Reborn remain unsupported. No pool expansion, training, or next package.

## Hosted acceptance

Initial implementation commit: `0f115a4e03e9d069075ceb3300fd08d459f0b31b`.
[Source run 37269136519](https://github.com/MaksimOrekhov/manamind/actions/runs/37269136519) passed Windows/Ubuntu including actual pytest. [ManaEngine run 37269136523](https://github.com/MaksimOrekhov/manamind/actions/runs/37269136523) found an adapter metadata error: Persisting Horror is a SPELL granting Reborn, and its tag had incorrectly been mapped to intrinsic Reborn. Both native CTest jobs passed; this adapter failure was corrected rather than made baseline.

The new minion-only native guard was rebuilt after the first local adapter run; that run was therefore insufficient for final acceptance. The final full adapter/Policy suite was rerun against the rebuilt module after correction: 63 PASS. Mapping now requires minion metadata; a regression proves Murmy intrinsic=true, Persisting Horror intrinsic=false and still UNSUPPORTED/selectable with REBORN grant metadata. This does not implement granted Reborn.

Observed timer: start 05:23:34 UTC; final local re-verification 05:49:47 UTC, 26m13s elapsed including hosted-CI discovery interval; explicit passive sleeps 60s within that interval. This is elapsed throughput, not a claim of precisely sampled CPU/active time. Hosted CI/report bookkeeping continues separately.

Corrected commit hosted Source + ManaEngine Windows/Ubuntu acceptance pending observation; results will be recorded below.
