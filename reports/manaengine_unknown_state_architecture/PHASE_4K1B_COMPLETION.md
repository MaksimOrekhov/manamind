# Phase 4K.1b — Completion

Verdict: **PHASE_4K1B_ACCEPTED**

## Identity and authority

- Implementation base: `bc647a001b76c5731133ae2f28a168d02ba64179`.
- Accepted audit/inventory snapshot: `a03591ab1f97395e2761f66ff9f74359477fc77a`. Before migration its scanner matched the base: 310 native sites / 128 native rows / zero problems.
- Pinned RosettaStone: `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`; unchanged.
- Branch: `codex/phase-4k1b-typed-native-failures`; isolated managed worktree. The primary `E:\ManaMind` working files were not edited, reset, stashed or cleaned.
- Authority: the accepted Phase 4K.1b audit and the user's explicit authorization for B0, B1, B2, B3a, B3b, B3c, B4, B5a, B5b and B5c. No medium-confidence row was reclassified.

Implementation commits:

| SHA | Work |
|---|---|
| `1bc1e423407ccc3618af6caed9d28ce0932191dc` | Append-only failure kinds/codes, record, compatibility exception |
| `1037e65` | Audited native migration, binding/adapter policy, regression suites, inventory/source guard |
| `fe0ecef68cb3b8938960e237a64eef886036e9bd` | Authoritative documentation realignment |
| `8fdca711ddd18f1fb7f7778aa5c9a21d8114884d` | Both declaration false negatives reproduced through real `attempt_action` |
| `042518bc7d51617bb14a7706fb7985a4108550d4` | Audited NF-103 split: structural zero activation takes precedence when ownership is also unreviewed |

## Contract and migration

Four kinds; **57 explicit append-only codes**:

| Kind | Codes | Attempt outcome | Fallback eligible |
|---|---:|---|---|
| `UNSUPPORTED` | 15 | `UNSIMULATABLE / NATIVE_UNSUPPORTED` | yes |
| `RULE_UNRESOLVED` | 25 | `UNSIMULATABLE / NATIVE_RULE_UNRESOLVED` | yes |
| `BUDGET_LIMIT` | 3 | `UNSIMULATABLE / NATIVE_BUDGET_LIMIT` | **no** |
| `ENGINE_DEFECT` | 14, including `LEGACY_UNTYPED` | `ENGINE_DEFECT` | **no** |

Code determines kind; diagnostic text never determines classification. Native exceptions carry kind/code/detail/context and the session exposes its effective stored record. Python snapshots are frozen scalar `NativeFailure` values. `EngineDefectError` subclasses the compatibility `UnsupportedSimulationError`. Missing/untyped payloads default to engine defects. Deprecated `NATIVE_EXCEPTION_NORMALIZED` and `NATIVE_CATCH_ALL` names remain import-compatible but are never emitted.

All **310 baseline sites** have explicit dispositions:

- 153 typed conditions;
- 13 typed echoes;
- 12 typed funnels/wrappers;
- 127 deliberately unchanged load-time sites;
- 5 deliberately unchanged caller/illegal-action sites.

Thus **178 sites migrated**, 132 left unchanged by design, **unmigrated = 0**. Three additional child routes implement only the audit-approved NF-078, NF-103 and NF-122 splits. The inventory preserves baseline snippets/hashes, classifications/confidence and selectors, alongside current migration markers, normalized source hashes and dispositions. New typed infrastructure and narrow B6/echo exceptions are explicitly checked. UTF-8/universal-newline hash normalization gives the same identity on Git LF and Windows CRLF checkouts.

One writer keeps the first failure; a defect supersedes a non-defect and retains the previous cause in context. Later causes cannot downgrade a defect. Guarded accessors rethrow the effective stored record exactly. Damage wrappers unwind frames and append provenance without changing codes; only the execution funnel converts untyped exceptions. Unexpected standard exceptions retain type and original detail. Native `std::bad_alloc` poisons the session and rethrows the original so Python receives `MemoryError`.

The internal apply/export seam avoids incidental ACTIVE export during attempts; public `apply_action` still returns ACTIVE. Binding perspective errors and illegal actions remain non-poisoning caller errors. No runtime invocation of `validate_invariants` was added.

## Reproductions and verification

Before results below are the accepted audit §3.4 reproductions, not invented new baseline results. After results are real native-backed `attempt_action` regressions.

| Case | Before | After |
|---|---|---|
| Supported declaration with unmodelled LOCATION type, NF-067 | `UNSIMULATABLE / NATIVE_UNSUPPORTED`; fallback eligible | `ENGINE_DEFECT / NATIVE_ENGINE_DEFECT`, `MISSING_DISPATCH_HANDLER`; no fallback |
| Supported spell ability without a spell dispatcher, NF-048 | `UNSIMULATABLE / NATIVE_UNSUPPORTED`; fallback eligible | Same exact defect/code outcome; no fallback |
| Earlier soft coverage failure, then unexpected standard exception | Earlier coverage reason could mask the defect | Defect upgrade retains original type/detail and earlier cause |
| Real native `std::bad_alloc` | Could become UnsupportedSimulationError | Python `MemoryError`; `RESOURCE_EXHAUSTED` poison; attempt propagates the resource exception |

Local verification of the final implementation:

| Check | Result |
|---|---|
| Full ManaEngine native executable | **79 scenario groups / 2609 assertions PASS** |
| CTest | **1/1 PASS** |
| Full source pytest, initialized pinned RosettaStone | **273 PASS** |
| Exact ManaEngine CI adapter/policy/attempt/typed-failure selection | **257 PASS** |
| Ruff: `src tests scripts`; additional new guard/native Python tests | PASS |
| Audit inventory check | 310 baseline sites / 128 rows / unmigrated=0 / zero problems |
| Typed failure source guard | 310 sites + 3 approved splits / zero problems |
| Generator identity guard | PASS; existing 201 reviewed AST exceptions |
| Generated artifact check | **36 pinned outputs reproduced**, unique ownership |
| `git diff --check` against base | PASS |

Test coverage follows T01–T22: ordinary coverage failures, reviewed-rule fences, retained unsupported samples/no reroll, all three real budget guards, corrupted packet/structural guards, unexpected/unknown exceptions, mutation/reaction wrapper provenance, enumeration separation, accessor echo identity, public API/load-time compatibility, misleading-message classification controls, explicit fallback allowlist, deterministic parent/clone guarantees, real C++ allocation failure through Python and attempts, severity precedence, exact payload identity, independent code-ID/kind tables, legacy fail-safe behavior, guard negative controls and typed test-only invariant validation. Existing card/gameplay regression families remain enabled. Mechanical migration completeness does not mean every error site was dynamically exercised or that all card rules are verified.

A localized MSVC include-dependency issue exposed mixed old/new ABI objects during local iteration. All consumers were rebuilt together; local final checks and hosted clean builds passed. This is not a new native baseline failure.

## Hosted evidence

Verified implementation SHA: **`042518bc7d51617bb14a7706fb7985a4108550d4`**.

| Workflow | Windows | Ubuntu | Evidence |
|---|---|---|---|
| Source/generated checks | success | success | [run 37354810305](https://github.com/MaksimOrekhov/manamind/actions/runs/37354810305) |
| ManaEngine experimental | success | success | [run 37354810315](https://github.com/MaksimOrekhov/manamind/actions/runs/37354810315) |

Both Source jobs actually completed `python -m pytest -q`, after the inventory guard, regeneration and clean-diff steps. Both ManaEngine jobs completed Release build, CTest and Python adapter/policy schema tests. Results were checked from GitHub's live Actions REST job/step data; an empty connector snapshot was not treated as evidence.

This completion commit changes the report only; final pushed-report HEAD checks are confirmed separately in the task's final response. No automatic merge or branch promotion is authorized.

## Boundaries and remaining limits

- No card/gameplay semantics, pool memberships, manifests, encoder schemas or canonical registry statuses changed. Generated outputs remain reproducible and the registry/admission delta is zero.
- **Q_fallback does not exist.** BudgetLimit remains ineligible. Phase 4K.1c held-card semantics, live-root import/search and training were not implemented or started.
- Typed diagnostics may include hidden identities; they remain internal evidence and never become model inputs or visible afterstates. Existing information-set/live-root restrictions and blocked training admission remain in force.
- The source guard is token/identity based, not a complete C++ control-flow proof. Classification confidence/reachability remains that of the accepted audit. Future source changes require an explicit inventory delta review; existing medium-confidence rows were not promoted.
- If a real OOM also prevents diagnostic formatting, an allocation-free preconstructed resource record still poisons the branch and the original allocation exception propagates. Detailed preceding context is best effort under actual memory exhaustion.
- Core/extension ABI consumers must be rebuilt together; old native binaries are not certified by these tests. Legacy/untyped failures remain fail-safe defects.

STOP after completion push and green final HEAD CI. No merge to main, new card work, fallback or training.
