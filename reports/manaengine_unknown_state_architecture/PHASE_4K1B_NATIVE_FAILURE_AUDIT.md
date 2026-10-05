# Phase 4K.1b — Native failure taxonomy audit

Verdict: `4K1B_AUDIT_READY_FOR_IMPLEMENTATION`

| | |
|---|---|
| Mode | Read-only / report-first semantic audit. No engine, binding, adapter, test, card, manifest or registry file was changed. |
| Audited main | `a03591ab1f97395e2761f66ff9f74359477fc77a` (verified equal to `origin/main` at task start) |
| Main moved during the audit | `origin/main` is now `31614b30d43997a65bd82e567efd63c42533ab21` (three DATA-0A Power.log collector commits). None touches the audited paths: `git diff a03591a origin/main -- experiments/manaengine src/manamind/integrations/manaengine docs/PARTIAL_SIMULATOR_ARCHITECTURE.md reports/manaengine_unknown_state_architecture` is empty. The branch is based on the audited commit and was not rebased. |
| Branch | `audit/phase-4k1b-native-failure-taxonomy` |
| Artifacts | this report; [`PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json`](PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json); [`phase_4k1b_failure_site_audit.py`](phase_4k1b_failure_site_audit.py) (scan / check / instrument / hits helper) |
| Baseline | native 78 groups / 2153 assertions PASS; CI pytest file set 172 passed (details in §2) |

## 1. Summary

1. **The 4K.1 defect heuristic is wrong in one direction, and it is the dangerous one.** It mistakes a real engine defect for ordinary
   unsupported behaviour (fallback-eligible) at 47 of the 162 execution-scope failure sites (34 inventory rows). It
   (statically) never mistakes unsupported behaviour for a defect. Two such defects were reproduced on current `main` (§3.4). None of the 47
   sites is reachable by correctly declared content through the public API today; five of the rows fire only through test injection and the rest
   are structurally guarded. The exposure is therefore latent but real: any bug that lands on one of those sites will silently become
   a `Q_fallback` candidate.
2. **Typing has to be carried by the exception and the stored state, not recovered from text.** Three facts make the string heuristic
   unfixable by "adding more strings": the funnel adds its prefix only to the *stored* text of direct `throw`s and never to the rethrown
   exception; an exception escaping after an earlier soft poison is replaced by that earlier reason and its own type and message are
   discarded; and const/static callees (`ability_of`, `legal_actions`, `require_quiescent`, `observation`) cannot poison at all.
3. **Recommended contract** (§A): `FailureKind { Unsupported, RuleUnresolved, BudgetLimit, EngineDefect }` plus an append-only
   `FailureCode` whose kind is a pure function of the code; `UnsupportedSimulationError` stays the universal base and carries a
   `FailureRecord { code, detail, context }`; a legacy string-only throw defaults to `EngineDefect`/`LEGACY_UNTYPED`, so the default flips
   from "unsupported unless proven defect" to "defect unless proven typed". 57 codes map to current sites (BudgetLimit 3, EngineDefect 14, RuleUnresolved 25, Unsupported 15).
4. **No native prerequisite blocks 4K.1b.** Seven catalog-validation gaps (§6, F11) and one binding coupling (§6, F9) should be fixed in the
   same or an immediately following batch but do not gate the typed contract.
5. Only 52 of 162 execution-scope failure sites are ever fired by the existing native and Python suites, only 8 of the 71
   defect-class ones, and the damage-group scenarios assert `Unsupported + !is_valid` only, so a mistyped failure would pass them
   (§6, F10). The regression matrix (§D) therefore pins `(kind, code)` rather than "fails closed".

## 2. Baseline and method

**Baseline (current main, worktree built from scratch).**

| Check | Result |
|---|---|
| `git rev-parse HEAD` / `origin/main` | both `a03591ab1f97395e2761f66ff9f74359477fc77a` |
| Native build (Visual Studio 2022 Build Tools MSVC, Ninja, Release, `build-release/`, gitignored) | succeeded; C4456 shadowing warnings only |
| `manaengine_tests.exe` (default run covers the damage-group, Arcane Barrage and Fire-pool families) | **78 scenario groups, 2153 assertions passed** (same as the 4K.1 record) |
| CI ManaEngine pytest set (`test_adapter.py`, `test_simulation_attempt.py`, `tests/test_pipeline.py`, `tests/test_policy_action_semantics.py`, `tests/test_simulation_attempt_contract.py`) | **172 passed** |
| SimulationAttempt files only (contract 80, real native 9, adapter 56) | 145 passed |
| `git diff --check` | clean (run before the commit) |
| Ubuntu | not run locally (no Linux toolchain); parity is a CI obligation (§D, T15) |

A first `pytest tests` run stopped at `tests/test_minion_set_enchant.py` with `FileNotFoundError: vendor/RosettaStone/Resources/cards.json`.
That is the known empty-submodule worktree trap, not a baseline defect; the RosettaStone gitlink was not populated for this read-only audit.

**Method.**

* *Site enumeration is mechanical.* [`phase_4k1b_failure_site_audit.py`](phase_4k1b_failure_site_audit.py) tokenises the native
  sources (strings, chars and comments skipped, so the minified one-line style cannot hide a `throw`) and finds every
  `reject_unsupported(...)`, `throw`, `state_.unsupported = ...`, `catch`, catalog `reject(...)` call and `.at()`.
  An adjacent `state_.unsupported=…; throw Unsupported(…)` is one statement pair. The inventory JSON assigns every one of the
  310 sites to exactly one row through selectors; `check` fails on an unclassified or doubly classified site and on any
  change to the audited source hashes.
* *Dynamic evidence.* The helper's `instrument` command writes a scratch copy of the native sources that logs the first hit of every
  site (it never edits the repository). The existing native executable and the ManaEngine pytest files were run against it;
  results are identical to the uninstrumented run. `Ev` below is `PY` (fired by the Python suites: the real Standard catalog, occasionally a crafted one),
  `NAT` (fired by the native suite only, usually through `TestAccess` or a synthetic catalog) or `—`. This is existing-suite coverage,
  not reachability.
* *Static reasoning.* `Reach` (`pub` public API reachable by correct content, `inj` only through injection/crafted catalogs,
  `unr` structurally unreachable, `unt` reachable but untested) is argued from source and flagged `medium confidence` where the
  call is judgement (§E).
* *Empirical probes.* Binding translation and the two reproduced false negatives (§3.4, §12) were run on the freshly built module.

## 3. How a failure reaches Python today

### 3.1 The apply path

```
attempt_action(parent, action)                         simulation.py
  parent._legal_execution_keys()  -> native legal_actions()      const; any Unsupported -> UNSIMULATABLE / ENUMERATION_UNAVAILABLE
  child = parent.clone()          -> native clone()              require_quiescent()
  child._apply_raw(action)        -> binding apply_action        coupled: apply, then observation export, inside one binding call
       GameSession::apply_action(a)
         legal = legal_actions()                               may throw (const, cannot poison)
         not in legal  -> std::invalid_argument                ILLEGAL, non-poisoning (pre-mutation)
         try  execute_action(a)                                all simulated mutation happens here
         catch UnsupportedSimulationError e : clear frames; S0 ??= "action failed after mutation: " + e.what(); rethrow ORIGINAL (bare `throw;`)
         catch std::exception e             : clear frames; S0 ??= "action failed after mutation: " + e.what(); throw Unsupported(S0)
         catch (...)                        : clear frames; S0 ??= "... unknown exception";                  throw Unsupported(S0)
```

`S0` is `state_.unsupported`; `S0 ??= x` means "assign only if unset". `is_valid()` is `!S0`. Every escaping failure poisons the session; an illegal action does not.

### 3.2 What the 4K.1 adapter sees

| Native situation | `S0` before | Exception that escapes | 4K.1 result |
|---|---|---|---|
| `reject_unsupported(...)` (53 `RJ`) or explicit `S0=…; throw` (25 `WT`), plus the echo tails of soft writes | set by the site | `Unsupported(message == S0)` | `UNSIMULATABLE / NATIVE_UNSUPPORTED` |
| direct `throw Unsupported(msg)` with no write (27 `TU` sites) | unset | `Unsupported(msg)` unprefixed; funnel stores `S0 = prefix + msg` | `UNSIMULATABLE / NATIVE_UNSUPPORTED` (the `startswith(prefix)` test sees the bare `msg`) |
| any `std::exception` (including `std::bad_alloc`) | unset | `Unsupported(prefix + what)` | `ENGINE_DEFECT / NATIVE_EXCEPTION_NORMALIZED` |
| any `std::exception` after an earlier soft write | set | `Unsupported(S0)`; own type and `what()` are discarded | `UNSIMULATABLE / NATIVE_UNSUPPORTED` — defect masked |
| `catch (...)` | unset | `Unsupported("… unknown exception")` | `ENGINE_DEFECT / NATIVE_EXCEPTION_NORMALIZED` |
| damage-group wrapper writes `S0` (only for exceptions that bypassed `reject_unsupported`) | unset | original exception, then funnel throws `Unsupported(S0)` | `ENGINE_DEFECT / NATIVE_CATCH_ALL` — no real native path reaches it in any existing suite |
| exception from the binding's post-apply observation export | unset (session valid) | whatever the export threw | `ATTEMPT_INVARIANT_VIOLATED` or `ADAPTER_FAILURE` |
| any `Unsupported` from `legal_actions()` | n/a | `Unsupported` | `UNSIMULATABLE / ENUMERATION_UNAVAILABLE` |

### 3.3 Poison precedence is not what the comment says

The comment above `apply_action` promises "first reason kept". The code does not deliver it uniformly: **26 of the 35 direct writes assign
unconditionally** and overwrite an earlier reason (25 explicit `S0=…; throw` pairs and the `record_minion_play` catch), while 9 are
guarded first-wins (4 soft sites, 3 `apply_action` funnel writes, 2 damage-group wrappers) and so are all 53 `reject_unsupported` calls.
Four sites (`enter_hand`, `summon_from_deck`, `resolve_spell` generation, Deathrattle generation) write a *soft* poison and keep
executing; the exception only appears at the end of the action through the echo tails. Whatever the stored reason is at that moment
is what Python is told.

### 3.4 Reproduced on current main: defects reported as fallback-eligible

Using the same crafted-catalog technique as SA11 (a native catalog built from the real definition rows with one card edited, installed in
a session), `attempt_action` on a legal action returned:

| Declaration defect | Outcome |
|---|---|
| SUPPORTED card of an unmodelled `card_type` (`LOCATION`) — site NF-067 | `UNSIMULATABLE / NATIVE_UNSUPPORTED`, `fallback_eligible=True`, stored text `action failed after mutation: unsupported card type selected for play`, exception text without the prefix |
| SUPPORTED spell whose ability has no spell handler — site NF-048 | `UNSIMULATABLE / NATIVE_UNSUPPORTED`, `fallback_eligible=True`, stored text `action failed after mutation: effect handler is not implemented for selected card` |

Both are registry-contract violations (a SUPPORTED declaration must be executable), i.e. `ENGINE_DEFECT`, and both would be scored by a
future `Q_fallback` as if they were model uncertainty.

## 4. Classification rules

The taxonomy from the task is kept unchanged; the audit adds the rules used to apply it.

* **R1 — classify the condition, not the mechanism.** `reject_unsupported(...)` is an implementation convenience. Of its 53 call
  sites, **26 are `ENGINE_DEFECT`**, 24 are `RULE_UNRESOLVED` fences, 3 are `BUDGET_LIMIT` caps and none is a plain unsupported card; of the 27
  direct `throw UnsupportedSimulationError` statements without a write, 17 are defects, 6 `DESIGN_UNSUPPORTED` and 4 `RULE_UNRESOLVED`.
* **R2 — correct-declaration reachability test.** Ask: *can a correctly declared, registry-admitted card or action reach this
  site in a valid state?* If yes and the engine lacks the behaviour or branch ⇒ `DESIGN_UNSUPPORTED`. If yes and the engine
  deliberately refuses because ordering, lifetime, membership or evidence is unreviewed ⇒ `RULE_UNRESOLVED`. If only an inconsistent
  declaration, a legality/execution disagreement or a corrupted structure can reach it ⇒ `ENGINE_DEFECT`.
* **R3 — fences keep their meaning.** A guard whose message states an unreviewed interaction (`unreviewed`, `outside the reviewed
  contract`, `requires … verification`) stays `RULE_UNRESOLVED` even if no current content reaches it; a guard whose only possible trigger
  today is corruption (identity, enum validity, stack discipline, legality/execution agreement, catalog integrity) is `ENGINE_DEFECT`.
  When content that legitimately reaches a defect-class guard is later added, that package owns the reclassification.
* **R4 — sampled outcomes.** An unsupported result of a game-defined random pick is `DESIGN_UNSUPPORTED`; it is never rerolled, the RNG
  consumed by the sample is retained and the code is marked *sampled* because its occurrence may depend on hidden information.
* **R5 — budgets.** `BUDGET_LIMIT` is reserved for a deliberate bound on a valid branch (three damage-group caps). A numeric-range or counter
  guard that cannot be reached without corruption is a defect even though it is a "limit".
* **R6 — poison is independent of the mutation boundary.** Several refusals fire before any game-visible mutation (e.g. NF-022, NF-037
  at `resolve_play`, NF-086) and still poison the session.
* **R7 — split mixed conditions.** A call site that combines sub-conditions of different classes must be split before it is typed
  (NF-078, NF-103).

Legend for the tables: `M` mutation boundary (`PRE` no game-visible mutation yet, `POST` possibly partial, `CONST` const method,
`LOAD` no session), `RNG` (`N` no sampling yet in the operation containing the site, `P` possible, `Y` consumed immediately before;
any `POST` site may follow RNG use earlier in the same action). Mechanisms: `RJ` reject_unsupported, `WT` write+throw, `WS` soft write,
`EC` echo, `TU` direct Unsupported throw, `SL/SI/SO` `std::logic_error/invalid_argument/out_of_range`, `AT` `.at()`, `CT` catch, `CR` catalog
`reject()`. Python today: `U/NU` UNSIMULATABLE/NATIVE_UNSUPPORTED, `U/EU` …/ENUMERATION_UNAVAILABLE, `D/NEN` ENGINE_DEFECT/NATIVE_EXCEPTION_NORMALIZED,
`D/NCA` …/NATIVE_CATCH_ALL, `D/AF` …/ADAPTER_FAILURE. Class: `DU` DESIGN_UNSUPPORTED, `RU` RULE_UNRESOLVED, `BL` BUDGET_LIMIT, `ED` ENGINE_DEFECT,
`IL` ILLEGAL_OR_CALLER_ERROR, `ENV` ENVIRONMENT_OR_ADAPTER_FAILURE. FB = fallback eligible after 4K.1b.

## 5. Counts

Reproduce with `python reports/manaengine_unknown_state_architecture/phase_4k1b_failure_site_audit.py scan` (`check` verifies the inventory).

| Mechanism | engine.cpp | damage_group.cpp | pool_manifest.cpp | python_bindings.cpp | Total |
|---|---:|---:|---:|---:|---:|
| `reject_unsupported(...)` call (RJ) | 19 | 34 | 0 | 0 | 53 |
| `state_.unsupported=…; throw Unsupported(stored)` pair (WT) | 27 | 0 | 0 | 0 | 27 |
| `state_.unsupported=…` without a paired throw (WS) | 6 | 2 | 0 | 0 | 8 |
| `throw Unsupported(*state_.unsupported)` echo (EC) | 10 | 3 | 0 | 0 | 13 |
| direct `throw UnsupportedSimulationError(msg)` (TU) | 26 | 1 | 0 | 0 | 27 |
| `throw std::logic_error` (SL) | 23 | 0 | 0 | 0 | 23 |
| `throw std::invalid_argument` (SI) | 102 | 0 | 29 | 1 | 132 |
| `throw std::out_of_range` (SO) | 2 | 0 | 0 | 0 | 2 |
| `.at()` (implicit `std::out_of_range`) (AT) | 10 | 2 | 0 | 0 | 12 |
| `catch` clause (CT) | 4 | 2 | 0 | 0 | 6 |
| catalog `reject(...)` lambda call (CR) | 7 | 0 | 0 | 0 | 7 |
| **All sites** | 236 | 44 | 29 | 1 | **310** |

Requested counts:

| Item | Count |
|---|---:|
| `reject_unsupported` call sites | **53** (engine.cpp 19, damage_group.cpp 34) |
| `throw UnsupportedSimulationError` statements | **67** = 27 direct without a write + 27 behind a `state_.unsupported` write + 13 echoes of the stored reason (engine.cpp 63, damage_group.cpp 4) |
| `state_.unsupported` direct writes | **35** = 27 paired with a throw + 8 without (4 soft-continue sites, `record_minion_play`, the `apply_action` Unsupported branch, 2 damage-group wrappers); **26 overwrite, 9 first-wins** |
| explicit `throw std::…` reachable in execution | **12** (5 `invalid_argument` incl. the non-poisoning ILLEGAL guard, 5 `logic_error`, 2 `out_of_range`) + 2 `logic_error` in the prototype-choice demo API; plus **12 implicit `.at()`** (9 execution, 3 enumeration) |
| explicit `throw std::…` elsewhere | 16 `logic_error` in `validate_invariants` (test-only), 2 `invalid_argument` in observation/evidence export, 1 in the binding, 124 `invalid_argument` at load time |
| catch / normalisation funnels | **6** native `catch` clauses (`record_minion_play` 1, `apply_action` 3, damage-group wrappers 2) + **6** Python translation sites + 1 absent translator (the native exception carries no attributes) |
| invariant failure sites | **16** `std::logic_error` in `validate_invariants`; the function is called only by native tests |
| **Total audited semantic failure sites** | **326** = 310 native + 16 Python (`engine.py`) |

Counts by proposed semantic category (native sites; one row = one semantically distinct site or tightly identical group):

| Semantic class | Future FailureKind | Rows | Native sites |
|---|---|---:|---:|
| `DESIGN_UNSUPPORTED` | Unsupported | 17 | 17 |
| `RULE_UNRESOLVED` | RuleUnresolved | 35 | 42 |
| `BUDGET_LIMIT` | BudgetLimit | 3 | 3 |
| `ENGINE_DEFECT` | EngineDefect | 54 | 91 |
| `ILLEGAL_OR_CALLER_ERROR` | none (non-poisoning ILLEGAL) | 4 | 5 |
| `ENVIRONMENT_OR_ADAPTER_FAILURE` | none (load-time ValueError) | 3 | 127 |
| `ECHO` | rethrow of stored record | 6 | 13 |
| `FUNNEL` | typed funnel / wrapper | 6 | 12 |
| **Total** | | **128** | **310** |

`ENGINE_DEFECT` includes the 16 test-only invariant throws and the 4 impossible-enum name tables; excluding them 71 execution-scope
sites remain. `ENVIRONMENT_OR_ADAPTER_FAILURE` is load-time validation (`std::invalid_argument` → `ValueError` before any session
exists); its 127 sites are 102 in the `CardCatalog` constructor and 25 in the two manifest validators (families in the appendix).

How the 4K.1 heuristic reads those sites today (static, derived from §3.2):

| 4K.1 heuristic verdict (static, by site) | Rows | Sites |
|---|---:|---:|
| correct | 72 | 100 |
| **false negative** (classified ENGINE_DEFECT here, reported UNSIMULATABLE / fallback-eligible today) | 34 | 47 |
| false positive (unsupported here, reported ENGINE_DEFECT today) | 0 | 0 |
| not applicable (load-time, echo, funnel, illegal, construct/observe) | 22 | 163 |

Existing-suite coverage of the execution-scope sites (the 16 test-only invariant throws and the load-time validators are excluded):

| Class (execution-scope sites) | Sites | Fired by existing suites | Never fired |
|---|---:|---:|---:|
| `DESIGN_UNSUPPORTED` | 17 | 7 | 10 |
| `RULE_UNRESOLVED` | 42 | 26 | 16 |
| `BUDGET_LIMIT` | 3 | 2 | 1 |
| `ENGINE_DEFECT` | 71 | 8 | 63 |
| `ILLEGAL_OR_CALLER_ERROR` | 4 | 1 | 3 |
| `ECHO` | 13 | 3 | 10 |
| `FUNNEL` | 12 | 5 | 7 |
| **Total** | **162** | **52** | **110** |

## 6. Findings

**F1 — Misclassification is one-directional.** 47 sites in 34 rows are defects that surface as UNSIMULATABLE; no unsupported branch surfaces
as a defect (one corner case: an unwritten direct `ability_of` throw inside a damage reaction would hit the generic wrapper write, but
that needs an unsupported card on a board without a prior poison, which no flow produces). Examples: `death handle disappeared during batch
removal` (NF-080), every malformed-damage-packet reject (NF-105, NF-112, NF-115), `target identity is not in Play` (NF-104), `damage group: public
access requires quiescent state` surfaced as an *enumeration-unavailable* signal (NF-101), and the two reproduced declaration defects.

**F2 — The funnel is lossy in three ways.** (a) The prefix is on the stored text only for direct Unsupported throws; (b) after any
earlier poison the funnel replaces a later `std::exception` with the earlier reason and drops its type and `what()`; (c) `std::bad_alloc`
is a `std::exception`, so a native out-of-memory is normalised into `UnsupportedSimulationError` and never reaches the adapter as `MemoryError`, which the
4K.1 contract (SA22) says must propagate.

**F3 — Poison precedence is inconsistent** (§3.3): 26 overwriting writes against 9 first-wins writes plus 53 first-wins rejects.

**F4 — Four soft-poison sites keep executing.** Later code runs on a state already known to be non-authoritative; the derived failure
that follows is usually the same kind (`ability_of` on the unsupported card) but this is not guaranteed, which is why a severity rule is needed (§A, D3).

**F5 — The two generic wrapper strings are almost vestigial.** `damage group: mutation failed` and `damage group: reaction failed` are written only for
exceptions that bypassed `reject_unsupported` (an `out_of_range` from `card()`, `bad_alloc`, an unwritten direct Unsupported throw). No existing
suite makes that happen; they are exercised only by the FakeSession. They destroy the original type and message (§8).

**F6 — Const and static callees cannot poison.** `ability_of` (static), `legal_actions` line 192, `require_quiescent` (frames case) and
`observation` can only throw. They need a typed exception; the poison write can then be centralised in the funnel. Today the
`require_quiescent` frames case is a defect reported as an enumeration-unavailable (fallback-eligible) signal.

**F7 — `validate_invariants` is test-only.** No runtime path calls it, so the 16 invariant throws are inventory entries, not runtime guards.
Whether a completed child should be validated before it is exposed is an explicit open question (Q2).

**F8 — Typing must not depend on message text, but tests do.** Existing tests assert exception *text* (`match="selected generated outcome is
unsupported: TLC_222"`, `"pool identity is not loaded"`, `"unknown Secret effect"`, 26 `UnsupportedSimulationError` uses in `test_adapter.py`). The
migration therefore keeps `what()`/`detail` byte-identical while removing every consumer of it for classification.

**F9 — Apply and export are coupled in the binding.** `apply_action` returns `observation_dict(s.observation(...))`. Any export failure after a
successful apply escapes as the apply failure with a *valid* session, which is exactly the 4K.1 `ATTEMPT_INVARIANT_VIOLATED` case. `attempt_action` discards that
export and re-exports itself with a fixed seat, so the coupling is pure risk.

**F10 — Existing tests do not pin the reason.** `fails_closed` (native) accepts any `UnsupportedSimulationError` plus `!is_valid()`; the
damage-group scenarios (DG10/12/18/20/21/23) use it. DG23 injects a negative amount, a stale handle, controller 3 and a duplicate packet and asserts only
"fails closed". A mistyped failure would pass all of them.

**F11 — Catalog validation gaps make some defect paths reachable.** (1) `generated_card`, `transform_card` and `takes_damage_pool_id` are not
cross-checked against the catalog / loaded pools (NF-002, NF-015, NF-006); (2) a pool manifest's members are not checked against the
catalog definitions (NF-006); (3) hard-coded literal dependencies (`CS2_tk1`, `CORE_CS2_033`, `HERO_08bp`) are not validated (NF-015, NF-039, NF-069);
(4) `secret=true` with ability `NONE` bypasses the SECRET contract (reached by SA11, NF-013); (5) a SUPPORTED declaration is not checked against the
handler table for its card type and ability (NF-048, NF-067, NF-074); (6) a deck card id absent from the catalog surfaces as `IndexError` from the
session constructor (caller error, NF-015); (7) `validate_pool_manifest` accepts an empty reviewed pool (NF-004).

**F12 — Three conditions are mixed in single guards, and one message is misleading** (NF-078, NF-103, NF-122; "frozen target disappeared during
mutation", NF-108, has nothing to do with Freeze).

**F13 — The Python exception class is overloaded.** `UnsupportedSimulationError` is used for translated native failures, the non-Mage session guard
and the training-admission policy gate (`require_canonical_training_admission`, PB-07), and the native and Python classes share a name but not a base
(`Exception` versus `RuntimeError`). Only attributes, never class membership or text, can classify.

**F14 — Observation can throw a design-unsupported signal.** `observation()` calls `ability_of(...)` for every board minion (only to read the
Raincaller-style trigger counter), so exporting a state with an unsupported minion throws `Unsupported`. A valid-state export must never throw a
fallback-eligible signal; this call must become non-throwing (also required by Phase 4K.1c).

**F15 — Some legal actions are knowably unsimulatable before execution.** Playing a Colossal minion with too little board space (NF-037) and
choosing an unsupported Discover option (NF-086) fail at execution although the information is visible at enumeration time. Not addressed in 4K.1b.

**F16 — 6 codes describe sampled outcomes.** `DARK_GIFT_ASSIGNMENT_UNRESOLVED`, `UNSUPPORTED_DISCARD_TRIGGER`, `UNSUPPORTED_GENERATED_CARD`, `UNSUPPORTED_GENERATED_CARD_UNDEFINED`, `UNSUPPORTED_RANDOM_SECRET_OUTCOME`, `UNSUPPORTED_SUMMONED_CARD` depend on game RNG and therefore on hidden deck/RNG state (the SA16 opponent
next-draw case is the same phenomenon). The typed contract makes this visible; any live-root use needs the determinization design that 4K.1 already requires.

## 7. Inventory

One row per semantically distinct failure site or tightly identical group; `×n` is the number of source statements in the row. The same data,
with selectors, exact line lists, mutation/RNG flags, dynamic hit counts and complete notes, is in
[`PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json`](PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json). `Reach/Ev` is `reach/evidence` as defined in §2. Reason
codes are proposals mapped one-to-one to the sites listed here; final spelling belongs to the implementation task.

### G1 Generated-card pools

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-001 | `generate_random_card_to_hand` engine:14 | SI | owner outside 0..1 (callers pass handle controllers) | POST | N | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 | Impossible argument from engine-internal caller. |
| NF-002 | `generate_random_card_to_hand` engine:16 | WT | takes_damage_pool_id names a manifest absent from the catalog | POST | N | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `POOL_IDENTITY_NOT_LOADED` | yes | pub/PY | T02 | Catalog does not cross-check takes_damage_pool_id against loaded pools; a supported TakesDamage declaration can therefore reach it. |
| NF-003 | `generate_random_card_to_hand` engine:18 | WT | pool membership_status == CANDIDATE | POST | N | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `POOL_MEMBERSHIP_CANDIDATE_ONLY` | yes | pub/NAT | T02 |  |
| NF-004 | `generate_random_card_to_hand` engine:19 | WT | reviewed manifest with zero members | POST | N | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `POOL_EMPTY_SEMANTICS_UNREVIEWED` | yes | unr/— | T02 | (medium confidence) validate_pool_manifest accepts count 0, so the engine refuses at use; real empty-pool behaviour is unreviewed. |
| NF-005 | `generate_random_card_to_hand` engine:20 | WT | owner hand already holds 10 cards | POST | N | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `GENERATION_HAND_FULL_ORDER_UNREVIEWED` | yes | pub/NAT | T02 | 'failed before RNG consumption' is true for this generation only; earlier steps of the action may have consumed RNG. |
| NF-006 | `generate_random_card_to_hand` engine:25 | WT | sampled pool member has no CardDefinition | POST | Y | S0 overwrite + throw | U/NU | DU | Unsupported / `UNSUPPORTED_GENERATED_CARD_UNDEFINED` | yes | unr/— | T03 | (medium confidence) Manifest/catalog cross-check missing at load; if added the site becomes unreachable (then ENGINE_DEFECT). |
| NF-007 | `generate_random_card_to_hand` engine:26 | WT | sampled pool member has support_state UNSUPPORTED (no reroll) | POST | Y | S0 overwrite + throw | U/NU | DU | Unsupported / `UNSUPPORTED_GENERATED_CARD` | yes | pub/PY | T03 | The canonical A-class case: real Fire-pool sample, covered by SA06 and test_adapter TLC_222. |
| NF-008 | `generate_random_card_to_hand` engine:29 | WT | int overflow of fresh instance cost_delta + modifier | POST | Y | S0 overwrite + throw | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `NUMERIC_RANGE_VIOLATION` | no | unr/— | T05 | Unreachable: a fresh instance has cost_delta 0, so the sum always fits an int. |
| NF-009 | `generate_random_card_to_hand` engine:33 | EC | rethrow of state_.unsupported after enter_hand | POST | P | echo | U/NU | ECHO | (rethrow stored FailureRecord) | inherits | unr/— | T09 | Dead behind NF-007 for UNSUPPORTED cards; must become rethrow_stored(). |

_9 rows, 9 sites._


### G2 Dispatch and catalog-reference helpers

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-010 | `activate_secret` engine:35 | SL | non-Secret card routed to the Secret zone | POST | P | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 |  |
| NF-011 | `ability_of` engine:70 | TU | card with ability NONE that is not VERIFIED_VANILLA reached dispatch | POST | P | none (static); funnel adds prefix | U/NU (correct only by luck) | DU | Unsupported / `UNSUPPORTED_CARD_BEHAVIOR` | yes | unr/— | T01 | Called from legal_actions/observation (CONST), resolve_play, stabilize, end-turn reactions. |
| NF-012 | `ability_of` engine:71 | SI | ability string outside the catalog allowlist | POST | P | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 | Unreachable after CardCatalog validation. |
| NF-013 | `secret_effect_of` engine:77 | SI | secret_effect string outside the allowlist | POST | P | none (funnel normalises) | D/NEN (SA11) | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | inj/PY | T06 | Reached by SA11 through a crafted catalog: secret=true with ability NONE bypasses the SECRET contract validation (validation gap). |
| NF-014 | `GameSession` engine:132 | TU | player class is not MAGE | LOAD | N | none (no session exists) | n/a (adapter raises first) | DU | Unsupported / `UNSUPPORTED_HERO_CLASS` | yes | unt/— | T01 | The Python adapter raises its own UnsupportedSimulationError before the native constructor runs. |
| NF-015 | `card` engine:137 | SO | card id absent from the catalog | CONST | N | none (const) | D/AF in enumeration; D/NEN in execution | ED | EngineDefect / `CATALOG_REFERENCE_MISSING` | no | unr/— | T05 | (medium confidence) Dangling references: generated_card, transform_card and hard-coded CS2_tk1/CORE_CS2_033/HERO_08bp are not validated at load. |

_6 rows, 6 sites._


### G3 Hand entry, Shatter, Dark Gift and modifier lifetime

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-016 | `enter_hand` engine:141 | WS | an UNSUPPORTED card enters a hand (draw, generation, Discover, Deathrattle) | POST | P | S0 soft (first-wins), continues | U/NU (via the end-of-action echo) | DU | Unsupported / `UNSUPPORTED_CARD_ENTERED_HAND` | yes | pub/PY | T01 | Also fires inside the constructor's opening draw: the session is born poisoned. |
| NF-017 | `remove_card_from_hand` engine:143,144 ×2 | AT+SO | hand position out of range | POST | P | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 |  |
| NF-018 | `shatter_on_hand_entry` engine:151 | WT | Shatter source carries cost/damage/counter/enchant modifiers | POST | P | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `SHATTER_MODIFIER_INHERITANCE_UNREVIEWED` | yes | pub/NAT | T02 |  |
| NF-019 | `update_shatter_links` engine:153 | WT | recombining fragments carry modifiers | POST | P | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `SHATTER_MODIFIER_MERGE_UNREVIEWED` | yes | pub/NAT | T02 |  |
| NF-020 | `bounded_random` engine:155 | SI | empty candidate set reached the sampler | POST | N | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 | Every caller checks non-emptiness first; reaching it is a caller defect. |
| NF-021 | `apply_dark_gift` engine:173 | SL | gift is not a DARK_GIFT_OPTION or target is not a minion | PRE | N | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 |  |
| NF-022 | `apply_dark_gift` engine:173 | WT | selected launch-reviewed gift has support_state UNSUPPORTED (never rerolled) | PRE | N | S0 overwrite + throw | U/NU | DU | Unsupported / `UNSUPPORTED_DARK_GIFT_OUTCOME` | yes | pub/NAT | T03 | Fires before any game-visible mutation (only the entity-id counter has advanced), yet still poisons the session. |
| NF-023 | `apply_dark_gift` engine:173 | WT | gift applied to a non-fresh or non-hand instance | PRE | N | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `DARK_GIFT_STACKING_UNREVIEWED` | yes | inj/NAT | T02 | (medium confidence) Production ChooseCard builds a fresh instance, so only TestAccess reaches it; it is a deliberate v1 fence. |
| NF-024 | `apply_dark_gift` engine:173 | WT | supported gift declares a keyword outside {TAUNT,LIFESTEAL,CHARGE} | PRE | N | S0 overwrite + throw | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 | Unreachable: CardCatalog rejects it at load for supported gifts. |
| NF-025 | `require_supported_modifier_lifecycle` engine:174 | WT | persistent modifier in a deck / on a Secret / on a Silenced minion | POST | P | S0 overwrite + throw (lambda `fail`) | U/NU | RU | RuleUnresolved / `MODIFIER_LIFETIME_UNREVIEWED` | yes | pub/NAT | T02 | The statement pair is `state_.unsupported=reason; throw UnsupportedSimulationError(reason)`. |

_10 rows, 11 sites._


### G4 Action enumeration

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-026 | `legal_actions` engine:189 | EC | duplicate of require_quiescent's poison check | CONST | N | echo | U/EU | ECHO | (rethrow stored FailureRecord) | inherits | unr/— | T09 | Dead code: require_quiescent() on the previous line already threw. |
| NF-027 | `legal_actions` engine:192 | TU | active hand contains an UNSUPPORTED card | CONST | N | none (const; no poison) | U/EU | DU | Unsupported / `UNSUPPORTED_CARD_IN_ACTIVE_HAND` | yes | inj/NAT | T08 | Natural flows poison earlier via enter_hand (NF-016), so a non-poisoned session reaches it only through injected state. |
| NF-028 | `semantic_legal_actions` engine:215,218 ×3 | AT | hand/choice index out of range while describing actions | CONST | N | none (const) | D/AF | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T08 | std::out_of_range -> pybind IndexError, which 4K.1 labels ADAPTER_FAILURE. |

_3 rows, 5 sites._


### G5 TakesDamage, history, instance copy, board and Colossal

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-029 | `resolve_damage_occurrence` engine:230 | RJ | consumer died/left/changed controller/was silenced before its checkpoint (lethal consumer included) | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `TAKES_DAMAGE_BOUNDARY_UNREVIEWED` | yes | pub/NAT | T02 | native_tests 'lethal consumer invalidates bounded v1'. |
| NF-030 | `resolve_damage_occurrence` engine:233 | RJ | immutable catalog descriptor differs from the captured copy | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 | (medium confidence) |
| NF-031 | `played_types` engine:244 | TU | minion race outside the 12 tracked history types | POST | P | none (static); record_minion_play records it | U/NU (unprefixed) | DU | Unsupported / `UNSUPPORTED_MINION_HISTORY_TYPE` | yes | unr/— | T01 |  |
| NF-032 | `record_minion_play` engine:252 ×2 | CT+WS | catch UnsupportedSimulationError, assign e.what(), rethrow | POST | P | S0 overwrite (unguarded) | n/a | FUNNEL | (typed funnel) | n/a | unr/— | T01 | Unconditional assignment: overwrites an earlier stored reason, unlike reject_unsupported. |
| NF-033 | `validate_instance_copy_v1` engine:271 | WT | Kindred copy source carries modifiers/keywords or a pending death | PRE | N | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `INSTANCE_COPY_SOURCE_UNREVIEWED` | yes | pub/NAT | T02 |  |
| NF-034 | `validate_instance_copy_v1` engine:273 | WT | copy source is not the rightmost minion | POST | N | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `INSTANCE_COPY_SOURCE_UNREVIEWED` | yes | unr/— | T02 |  |
| NF-035 | `summon_instance_copy_v1` engine:279 | WT | source minion missing right after it entered the board | POST | N | S0 overwrite + throw | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 | (medium confidence) |
| NF-036 | `enter_board_with_appendages` engine:295 | SL | insertion position outside the board | POST | N | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 |  |
| NF-037 | `enter_board_with_appendages` engine:296,312,466 ×3 | RJ | board lacks room for the Colossal body plus every appendage | POST | P | S0 first-wins | U/NU | RU | RuleUnresolved / `COLOSSAL_CAPACITY_UNREVIEWED` | yes | pub/NAT | T02 | resolve_play's guard fires BEFORE the hand removal (PRE); legal_actions only checks board.size()>=7, so a legal action is later unsimulatable. |
| NF-038 | `summon_fixed` engine:307 | WT | fixed-summon dependency unsupported or not a minion | POST | P | S0 overwrite + throw | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 | CardCatalog validates SummonFixed dependencies at load, so this is unreachable. |
| NF-039 | `transform_board` engine:321 | WT | transform target token has support_state UNSUPPORTED | POST | P | S0 overwrite + throw | U/NU | DU | Unsupported / `UNSUPPORTED_TRANSFORM_OUTCOME` | yes | unt/— | T01 |  |
| NF-040 | `transform_board` engine:321 | RJ | transform into a Colossal definition | POST | P | S0 first-wins | U/NU | RU | RuleUnresolved / `COLOSSAL_TRANSFORM_UNREVIEWED` | yes | inj/NAT | T02 |  |

_12 rows, 15 sites._


### G6 Discover, summon and spell-damage boundaries

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-041 | `begin_discover` engine:331 | RJ | catalog-derived pool smaller than choice_count | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `DISCOVER_POOL_INCOMPLETE` | yes | inj/NAT | T02 | (medium confidence) Impossible with the full Standard catalog; reachable with partial test catalogs. |
| NF-042 | `begin_discover` engine:331 | RJ | Discover card names a manifest that is not loaded | POST | Y | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | inj/NAT | T05 | CardCatalog already validates this at load; native test drops the manifest after construction. |
| NF-043 | `begin_discover` engine:331 | RJ | sampled options admit no distinct eligible gift assignment | POST | Y | S0 first-wins | U/NU | RU | RuleUnresolved / `DARK_GIFT_ASSIGNMENT_UNRESOLVED` | yes | inj/NAT | T02 |  |
| NF-044 | `summon_from_deck` engine:333 | WS | dynamic deck pool sampled an UNSUPPORTED minion | POST | Y | S0 soft (guarded, continues) | U/NU | DU | Unsupported / `UNSUPPORTED_SUMMONED_CARD` | yes | unt/— | T03 |  |
| NF-045 | `evaluate_spell_damage` engine:342 | WT | mortally wounded Spell Damage source before the next instruction | POST | P | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED` | yes | pub/NAT | T02 |  |
| NF-046 | `resolve_spell` engine:365 | WS | MinionDamageGenerate produced an UNSUPPORTED card | POST | P | S0 soft (guarded, continues) | U/NU | DU | Unsupported / `UNSUPPORTED_GENERATED_CARD` | yes | pub/NAT | T03 |  |
| NF-047 | `resolve_spell` engine:373 | TU | VERIFIED_VANILLA spell resolved as an effect spell | POST | P | none (funnel prefixes) | U/NU (unprefixed) | DU | Unsupported / `UNSUPPORTED_VANILLA_SPELL` | yes | unt/— | T01 | (medium confidence) A reviewed no-effect spell is trivially simulable in the real game; the refusal is a deliberate non-implementation. |
| NF-048 | `resolve_spell` engine:374 | TU | SUPPORTED spell ability has no spell handler | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `MISSING_DISPATCH_HANDLER` | no | unr/— | T06 | (medium confidence) Correct-declaration test: a registry-admitted SUPPORTED card must be executable, so reaching this means a declaration/dispatch defect. |
| NF-049 | `resolve_effects` engine:397 | WT | RandomEnemyMinion with a mortally wounded minion on any board | POST | P | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `RANDOM_SELECTION_PENDING_DEATH_UNREVIEWED` | yes | pub/NAT | T02 |  |

_9 rows, 9 sites._


### G7 Effect steps

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-050 | `resolve_effects` engine:408 | TU | Damage step with a selector the catalog forbids | POST | N | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 |  |
| NF-051 | `resolve_effects` engine:416 | TU | damage-outcome card produced a target set other than {selected} | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 | Catalog guarantees a single explicit-minion Damage step. |
| NF-052 | `resolve_effects` engine:416 | TU | outcome check after damage cannot find the target | POST | P | none (funnel prefixes) | U/NU (unprefixed) | RU | RuleUnresolved / `DAMAGE_OUTCOME_TARGET_UNRESOLVED` | yes | unr/— | T02 | (medium confidence) Unreachable today (dead minions stay in Play until stabilize); a deliberate fence for future reactions. |
| NF-053 | `resolve_effects` engine:416 | TU | target owner outside 0..1 | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 |  |
| NF-054 | `resolve_effects` engine:425 | TU | requires_friendly_weapon card resolved without a weapon | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `LEGALITY_EXECUTION_MISMATCH` | no | unr/— | T06 | (medium confidence) legal_actions guards this; an earlier step or secret removing the weapon would make it a fence instead. |
| NF-055 | `resolve_effects` engine:426 | TU | BuffMinion with a non-damaged-minion selector | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 |  |
| NF-056 | `resolve_effects` engine:426 ×2 | TU | BuffMinion target dead/undamaged/gone after legality said it was valid | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `LEGALITY_EXECUTION_MISMATCH` | no | unr/— | T06 | (medium confidence) |
| NF-057 | `resolve_effects` engine:427 | TU | random discard picked a card with INVISIBLEDEATHRATTLE/DISCARD_TRIGGER | POST | Y | none (funnel prefixes) | U/NU (unprefixed) | DU | Unsupported / `UNSUPPORTED_DISCARD_TRIGGER` | yes | unt/— | T03 | Valid game outcome of a random pick; the engine does not model the trigger. |
| NF-058 | `resolve_effects` engine:428 | TU | DestroyMinion with an unconstrained selector | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 |  |
| NF-059 | `resolve_effects` engine:428 | TU | destroy target missing after legality | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `LEGALITY_EXECUTION_MISMATCH` | no | unr/— | T06 | (medium confidence) |
| NF-060 | `resolve_effects` engine:429 | TU | Heal with a non-explicit selector | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 |  |
| NF-061 | `resolve_effects` engine:430,431 ×2 | TU | Heal / HealMinionToFull on a minion with health <= 0 (two sites) | POST | P | none (funnel prefixes) | U/NU (unprefixed) | RU | RuleUnresolved / `HEAL_MORTALLY_WOUNDED_UNREVIEWED` | yes | pub/NAT | T02 | Reachable by multi-step effect cards whose earlier step makes the target mortal. |
| NF-062 | `resolve_effects` engine:430,431 ×2 | TU | heal target missing after legality (two sites) | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `LEGALITY_EXECUTION_MISMATCH` | no | unr/— | T06 | (medium confidence) |
| NF-063 | `resolve_effects` engine:431 | TU | HealMinionToFull with a non-minion selector | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 |  |
| NF-064 | `resolve_random_distinct_damage` engine:442 | RJ | RandomDistinct step on a non-spell | POST | P | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DECLARATION_CONTRACT_VIOLATION` | no | unr/— | T05 | CardCatalog already restricts it to spells. |
| NF-065 | `resolve_random_distinct_damage` engine:445 | RJ | exclude_previous_target without an explicit action target | POST | P | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `LEGALITY_EXECUTION_MISMATCH` | no | unr/— | T06 | (medium confidence) |

_16 rows, 19 sites._


### G8 Play, Secrets, triggers, Reborn and death processing

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-066 | `resolve_play` engine:466 | AT | hand index outside the hand (legality already verified) | PRE | N | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 |  |
| NF-067 | `resolve_play` engine:484 | TU | SUPPORTED card of a type that is not MINION/WEAPON/SPELL | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `MISSING_DISPATCH_HANDLER` | no | unr/— | T06 | (medium confidence) Fires after the card left the hand and mana was paid. |
| NF-068 | `resolve_secret_instance` engine:503 | WT | pending mortal Spell Damage source at an enemy-area Secret trigger | POST | P | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED` | yes | unt/— | T02 |  |
| NF-069 | `resolve_secret_instance` engine:505 | WT | Water Elemental token (CORE_CS2_033) is UNSUPPORTED | POST | P | S0 overwrite + throw | U/NU | DU | Unsupported / `UNSUPPORTED_SECRET_DEPENDENCY` | yes | inj/NAT | T01 |  |
| NF-070 | `resolve_secret_instance` engine:519 | SL | unreachable configured Secret effect | POST | P | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 |  |
| NF-071 | `resolve_end_turn_reactions` engine:547 | RJ | queued end-of-turn source left Play / changed controller / was silenced | POST | P | S0 first-wins | U/NU | RU | RuleUnresolved / `EOT_SOURCE_BOUNDARY_UNREVIEWED` | yes | unr/— | T02 | (medium confidence) Message begins 'damage group:' but the site lives in the end-turn orchestrator. |
| NF-072 | `resolve_trigger` engine:573 | TU | catalog-derived Mage Secret pool differs from the reviewed pinned membership | POST | N | none (funnel prefixes) | U/NU (unprefixed) | RU | RuleUnresolved / `RANDOM_SECRET_POOL_MEMBERSHIP_MISMATCH` | yes | unt/— | T02 |  |
| NF-073 | `resolve_trigger` engine:573 | WT | sampled Mage Secret has support_state UNSUPPORTED | POST | Y | S0 overwrite + throw | U/NU | DU | Unsupported / `UNSUPPORTED_RANDOM_SECRET_OUTCOME` | yes | unt/— | T03 |  |
| NF-074 | `resolve_trigger` engine:573 | TU | queued Battlecry ability with no handler case | POST | P | none (funnel prefixes) | **U/NU (unprefixed) ⚠ defect read as unsupported** | ED | EngineDefect / `MISSING_DISPATCH_HANDLER` | no | unr/— | T06 | (medium confidence) Only abilities with a handler are queued, so it is unreachable. |
| NF-075 | `resolve_trigger` engine:574 | WS | Deathrattle generated an UNSUPPORTED card | POST | P | S0 soft (guarded, continues) | U/NU | DU | Unsupported / `UNSUPPORTED_GENERATED_CARD` | yes | unt/— | T03 |  |
| NF-076 | `resolve_reborns` engine:584,587 ×2 | RJ | intervening death or board mutation between removal and Reborn return (two sites) | POST | P | S0 first-wins | U/NU | RU | RuleUnresolved / `REBORN_ORDERING_UNREVIEWED` | yes | inj/NAT | T02 |  |
| NF-077 | `resolve_reborns` engine:592 | RJ | Reborn return would exceed the board capacity | POST | P | S0 first-wins | U/NU | RU | RuleUnresolved / `REBORN_ORDERING_UNREVIEWED` | yes | inj/NAT | T02 |  |
| NF-078 | `resolve_reborns` engine:593 | RJ | mixed: structural (non-minion / no Reborn / health<=0) and coverage (UNSUPPORTED definition) | POST | P | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 | (medium confidence) SPLIT REQUIRED: only the support_state == UNSUPPORTED sub-condition could ever be DESIGN_UNSUPPORTED. |
| NF-079 | `stabilize` engine:604 | RJ | stabilize() entered with an open damage frame | POST | P | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DAMAGE_FRAME_PROTOCOL_VIOLATION` | no | inj/NAT | T05 |  |
| NF-080 | `stabilize` engine:617 | RJ | queued death entity missing from the board | POST | P | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 |  |
| NF-081 | `stabilize` engine:621 | RJ | dying Reborn minion changed controller | POST | P | S0 first-wins | U/NU | RU | RuleUnresolved / `CONTROL_CHANGE_UNREVIEWED` | yes | inj/NAT | T02 |  |

_16 rows, 17 sites._


### G9 apply_action / execute_action funnels and echoes

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-082 | `apply_action` engine:646 | SI | action is not in the legal set | PRE | N | none (documented non-poisoning) | n/a (ILLEGAL_NOT_LEGAL first) | IL | (not a FailureKind: non-poisoning ILLEG… | no | pub/PY | T10 | attempt_action pre-checks legality, so it never reaches this. |
| NF-083 | `apply_action` engine:648 ×2 | CT+WS | catch UnsupportedSimulationError: clear frames, store 'action failed after mutation: <what>' if unset, bare rethrow | POST | P | S0 first-wins; rethrow keeps original | n/a | FUNNEL | (typed funnel) | n/a | pub/PY | T06 | The stored text gets the prefix but the rethrown exception does not, so Python never sees the prefix for direct Unsupported throws. |
| NF-084 | `apply_action` engine:649 ×2 | CT+WT | catch std::exception: store prefix+what if unset, throw UnsupportedSimulationError(stored) | POST | P | S0 first-wins; original type/what lost | D/NEN (masked as U/NU if S0 already set) | FUNNEL | (typed funnel) / `UNEXPECTED_EXCEPTION` | n/a | pub/PY | T06 | std::bad_alloc is a std::exception, so out-of-memory is also normalised here and Python never sees MemoryError. |
| NF-085 | `apply_action` engine:650 ×2 | CT+WT | catch(...): store 'unknown exception', throw Unsupported | POST | P | S0 first-wins | D/NEN | FUNNEL | (typed funnel) / `UNKNOWN_EXCEPTION` | n/a | unr/— | T06 |  |
| NF-086 | `execute_action` engine:654 | WT | player chose a Discover option whose card is UNSUPPORTED | PRE | N | S0 overwrite + throw | U/NU | DU | Unsupported / `UNSUPPORTED_DISCOVER_OUTCOME` | yes | pub/PY | T03 | Pre-mutation, but the clone is poisoned; the decision depends only on visible data, so the unsimulatable status is known at enumeration time. |
| NF-087 | `execute_action` engine:654,655 ×5 | AT | choice/hand index out of range after legality (5 call sites) | PRE | N | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T05 |  |
| NF-088 | `execute_action` engine:654–667 (8) ×8 | EC | `if(state_.unsupported) throw ...` after stabilize / end of each action type (8 sites) | POST | P | echo | U/NU | ECHO | (rethrow stored FailureRecord) | inherits | pub/PY | T09 | This is what turns the four soft writes (NF-016/044/046/075) into exceptions at the end of the action. |
| NF-089 | `execute_action` engine:655 | SL | Prepare advertised without spendable mana | PRE | N | none (funnel normalises) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `LEGALITY_EXECUTION_MISMATCH` | no | unr/— | T06 |  |
| NF-090 | `execute_action` engine:667 | WT | pending/active overload exceeds the next turn's crystals | POST | P | S0 overwrite + throw | U/NU | RU | RuleUnresolved / `OVERLOAD_CAPACITY_UNREVIEWED` | yes | unt/— | T02 | (medium confidence) Reachable by a valid Overload play; not covered by any existing test (no dynamic hit). |

_9 rows, 23 sites._


### G10 Invariants and API preconditions

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-091 | `validate_invariants` engine:672,673 ×7 | SL | identity / zone / capacity / mana / weapon invariants | CONST | N | none (const) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T22 | validate_invariants() is called ONLY by native tests; no runtime path runs it. |
| NF-092 | `validate_invariants` engine:672 ×5 | SL | Shatter fragment metadata invariants (5 sites) | CONST | N | none (const) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T22 |  |
| NF-093 | `validate_invariants` engine:674 ×4 | SL | activation-sequence and terminal-action invariants (4 sites) | CONST | N | none (const) | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T22 |  |
| NF-094 | `begin_prototype_choice` engine:686 ×2 | SL | demo API precondition: choice unavailable / no candidates | CONST | N | none | n/a (demo API) | IL | (not a FailureKind: non-poisoning ILLEG… | no | unt/— | T10 | Prototype-only API; not on the attempt path. |
| NF-095 | `observation` engine:689 | SI | perspective outside 0..1 | CONST | N | none | n/a | IL | (not a FailureKind: non-poisoning ILLEG… | no | unr/— | T10 | Unreachable from Python: the binding maps any unknown perspective string to 0, and the adapter validates the three allowed values. |
| NF-096 | `evidence_constraint_id` engine:9 | SI | impossible EvidenceConstraint enumerator | CONST | N | none (const) | n/a | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T22 | Called by the evidence_constraints binding property (export path). |

_6 rows, 20 sites._


### G11 Damage group (damage_group.cpp)

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-100 | `require_quiescent` damage_group:11 | EC | any public accessor on a poisoned session | CONST | N | echo | U/EU | ECHO | (rethrow stored FailureRecord) | inherits | pub/PY | T09 | Guards legal_actions/observation/clone/is_complete/result/needs_choice/choice_options/begin_prototype_choice. |
| NF-101 | `require_quiescent` damage_group:12 | TU | public access while a damage frame is open (frames cleared on every escaping failure, so this is a leak) | CONST | N | none (const) | **U/EU ⚠ defect read as unsupported** | ED | EngineDefect / `QUIESCENCE_VIOLATED` | no | inj/NAT | T08 |  |
| NF-102 | `consume_damage_work` damage_group:15 | RJ | more than 4096 packets+reactions in one action | POST | P | S0 first-wins | U/NU | BL | BudgetLimit / `DAMAGE_WORK_BUDGET_EXCEEDED` | policy | unr/— | T04 | (medium confidence) No supported content nests or chains reactions, so a trip signals a runaway loop; fallback eligibility must stay false until reviewed (Q-B1). |
| NF-103 | `damage_target_handle` damage_group:21 | RJ | minion controller/owner differs, or activation_sequence == 0 | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `CONTROL_CHANGE_UNREVIEWED` | yes | inj/NAT | T02 | (medium confidence) SPLIT REQUIRED: control change is a rules fence; activation_sequence==0 is a structural defect. |
| NF-104 | `damage_target_handle` damage_group:24 | RJ | packet target is neither a hero nor on a board | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DAMAGE_TARGET_LOST` | no | inj/NAT | T05 | (medium confidence) |
| NF-105 | `guard_scalar_damage` damage_group:41 | RJ | packet source_controller outside 0..1 | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `INVALID_DAMAGE_PACKET` | no | unr/— | T05 |  |
| NF-106 | `guard_scalar_damage` damage_group:42 | RJ | combat/hero-area/compound damage to a TakesDamage consumer | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `DAMAGE_REACTION_ORDER_UNREVIEWED` | yes | pub/NAT | T02 |  |
| NF-107 | `guard_area_spell_modifiers` damage_group:48,54 ×2 | RJ | area spell with a mortal or conditionally changing Spell Damage source (2 sites) | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED` | yes | pub/NAT | T02 |  |
| NF-108 | `apply_damage_packet` damage_group:77 | RJ | target vanished between group open and mutation ('frozen target' message is misleading) | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DAMAGE_TARGET_LOST` | no | unr/— | T05 | (medium confidence) |
| NF-109 | `open_damage_group` damage_group:92 | EC | entry guard on a poisoned session | POST | N | echo | U/NU | ECHO | (rethrow stored FailureRecord) | inherits | unr/— | T09 |  |
| NF-110 | `open_damage_group` damage_group:93 | RJ | damage dealt while a Choice/suspension is pending | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `DAMAGE_REACTION_ORDER_UNREVIEWED` | yes | inj/NAT | T02 |  |
| NF-111 | `open_damage_group` damage_group:94 | RJ | 64 nested damage frames | POST | N | S0 first-wins | U/NU | BL | BudgetLimit / `DAMAGE_DEPTH_BUDGET_EXCEEDED` | policy | inj/NAT | T04 | (medium confidence) |
| NF-112 | `open_damage_group` damage_group:95,96,97 ×3 | RJ | unknown dispatch/order enumerator or packet-count contract (3 sites) | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DAMAGE_FRAME_PROTOCOL_VIOLATION` | no | unr/— | T05 |  |
| NF-113 | `open_damage_group` damage_group:98 | RJ | packet buffer larger than the remaining action budget | POST | N | S0 first-wins | U/NU | BL | BudgetLimit / `DAMAGE_PACKET_BUDGET_EXCEEDED` | policy | inj/NAT | T04 | (medium confidence) |
| NF-114 | `open_damage_group` damage_group:99 | RJ | 2^64 group/sequence counter exhausted | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `NUMERIC_RANGE_VIOLATION` | no | unr/— | T05 | Deliberate bound but unreachable in practice; reaching it implies a corrupted counter, so it is a defect, not a game branch. |
| NF-115 | `open_damage_group` damage_group:102–110 (7) ×7 | RJ | malformed packet: bad source/controller/amount, unknown kind/attribution, DirectSpell w/o Spell, duplicate/stale target… | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `INVALID_DAMAGE_PACKET` | no | inj/NAT | T05 | All seven are structural. |
| NF-116 | `open_damage_group` damage_group:111 | RJ | source minion's controller differs from the packet controller | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `CONTROL_CHANGE_UNREVIEWED` | yes | unr/— | T02 | (medium confidence) |
| NF-117 | `open_damage_group` damage_group:127 ×2 | CT+WS | catch(...) around the packet-mutation loop: pop frame, store 'damage group: mutation failed' if unset, rethrow | POST | P | S0 first-wins; original type/what lost | D/NCA (fake-only) | FUNNEL | (typed funnel) / `UNEXPECTED_EXCEPTION` | n/a | unr/— | T07 | The write never executes in any existing test: every exception reaching it already carries a stored reason. |
| NF-118 | `validate_damage_frame_sources` damage_group:134 | RJ | damage source left Play / changed controller or silence before a reaction | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `DAMAGE_SOURCE_BOUNDARY_UNREVIEWED` | yes | unr/— | T02 |  |
| NF-119 | `validate_damage_frame_sources` damage_group:131,140 ×2 | AT | frame index outside the frame stack (2 sites) | POST | N | none until wrapper stores 'reaction failed' | D/NEN (masked as U/NU if S0 already set) | ED | EngineDefect / `DAMAGE_FRAME_PROTOCOL_VIOLATION` | no | unr/— | T05 |  |
| NF-120 | `dispatch_damage_event` damage_group:138,141,178,185 ×4 | RJ | frame-stack / cursor discipline broken (4 sites) | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `DAMAGE_FRAME_PROTOCOL_VIOLATION` | no | unr/— | T05 |  |
| NF-121 | `dispatch_damage_event` damage_group:153 | RJ | damaged TakesDamage consumer is also its own first-spell-damage watcher | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `DAMAGE_REACTION_ORDER_UNREVIEWED` | yes | inj/NAT | T02 |  |
| NF-122 | `dispatch_damage_event` damage_group:161,168,174 ×3 | RJ | reaction consumer changed card/controller/silence or was removed (3 sites) | POST | N | S0 first-wins | U/NU | RU | RuleUnresolved / `DAMAGE_SOURCE_BOUNDARY_UNREVIEWED` | yes | inj/NAT | T02 | (medium confidence) NF 'spell reaction lifetime' also compares a catalog constant (spell_damage_attack); split that structural sub-condition out. |
| NF-123 | `dispatch_damage_event` damage_group:171 | RJ | int overflow adding spell-damage attack | POST | N | S0 first-wins | **U/NU ⚠ defect read as unsupported** | ED | EngineDefect / `NUMERIC_RANGE_VIOLATION` | no | unr/— | T05 |  |
| NF-124 | `dispatch_damage_event` damage_group:176 | EC | echo after a reaction | POST | P | echo | U/NU | ECHO | (rethrow stored FailureRecord) | inherits | unr/— | T09 |  |
| NF-125 | `dispatch_damage_event` damage_group:177 | RJ | a reaction opened a Choice/suspension | POST | P | S0 first-wins | U/NU | RU | RuleUnresolved / `DAMAGE_REACTION_ORDER_UNREVIEWED` | yes | unr/— | T02 |  |
| NF-126 | `run_damage_group` damage_group:194 ×2 | CT+WS | catch(...) around dispatch: pop frames to entry depth, store 'damage group: reaction failed' if unset, rethrow | POST | P | S0 first-wins; original type/what lost | D/NCA (fake-only) | FUNNEL | (typed funnel) / `UNEXPECTED_EXCEPTION` | n/a | pub/PY | T07 | The catch is entered by every damage failure; the write itself never executed in the existing suites. |

_27 rows, 44 sites._


### G12 Load-time validation and binding

| ID | Site (function, file:lines) | Mech | Condition / message | M | RNG | Poison today | Python sees today | Class | Future kind / code | FB | Reach/Ev | New test | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF-130 | `CardCatalog` engine:82–126 (27) ×102 | CR+SI | catalog declaration validation (shape/contract/dependency/allowlist checks) | LOAD | N | none (no session) | n/a | ENV | (load/adapter failure, not a session Fa… | no | pub/PY | T11 | Surfaces as ValueError from native.CardCatalog(...). |
| NF-131 | `validate_pool_manifest` pool_manifest:53–68 (15) ×18 | SI | pool manifest identity/hash/status validation | LOAD | N | none (no session) | n/a | ENV | (load/adapter failure, not a session Fa… | no | inj/NAT | T11 |  |
| NF-132 | `validate_dark_gift_option_manifest` pool_manifest:71–78 (7) ×7 | SI | Dark Gift manifest validation | LOAD | N | none (no session) | n/a | ENV | (load/adapter failure, not a session Fa… | no | inj/NAT | T11 |  |
| NF-133 | `predicate_name` pool_manifest:38,39,40,41 ×4 | SI | impossible pool enumerator reached a name table (4 sites) | LOAD | N | none | n/a | ED | EngineDefect / `INVARIANT_VIOLATION` | no | unr/— | T11 | Impossible-enum defaults: ENGINE_DEFECT in kind, but raised during manifest load, so they never reach a session. |
| NF-134 | `action_from_dict` python_bindings:15 | SI | unknown action type string in the apply_action binding | PRE | N | none | n/a (ILLEGAL_MALFORMED first) | IL | (not a FailureKind: non-poisoning ILLEG… | no | unr/— | T10 | Python adapter canonicalises actions first. |

_5 rows, 132 sites._


### 7.1 Reason-code catalogue

| Code | Kind | Rows | Sites | Sampled outcome | Meaning (first row) |
|---|---|---|---:|:---:|---|
| `DAMAGE_DEPTH_BUDGET_EXCEEDED` | BudgetLimit | NF-111 | 1 |  | 64 nested damage frames |
| `DAMAGE_PACKET_BUDGET_EXCEEDED` | BudgetLimit | NF-113 | 1 |  | packet buffer larger than the remaining action budget |
| `DAMAGE_WORK_BUDGET_EXCEEDED` | BudgetLimit | NF-102 | 1 |  | more than 4096 packets+reactions in one action |
| `CATALOG_REFERENCE_MISSING` | EngineDefect | NF-015 | 1 |  | card id absent from the catalog |
| `DAMAGE_FRAME_PROTOCOL_VIOLATION` | EngineDefect | NF-079, NF-112, NF-119, NF-120 | 10 |  | stabilize() entered with an open damage frame |
| `DAMAGE_TARGET_LOST` | EngineDefect | NF-104, NF-108 | 2 |  | packet target is neither a hero nor on a board |
| `DECLARATION_CONTRACT_VIOLATION` | EngineDefect | NF-012, NF-013, NF-021, NF-024, NF-038, NF-042, NF-050, NF-051, NF-055, NF-058, NF-060, NF-063, NF-064 | 13 |  | ability string outside the catalog allowlist |
| `INVALID_DAMAGE_PACKET` | EngineDefect | NF-105, NF-115 | 8 |  | packet source_controller outside 0..1 |
| `INVARIANT_VIOLATION` | EngineDefect | NF-001, NF-010, NF-017, NF-020, NF-028, NF-030, NF-035, NF-036, NF-053, NF-066, NF-070, NF-078, NF-080, NF-087, NF-091, NF-092, NF-093, NF-096, NF-133 | 42 |  | owner outside 0..1 (callers pass handle controllers) |
| `LEGACY_UNTYPED` | EngineDefect | (default) | 0 |  | infrastructure code: fail-safe default for any throw or reject that has not been migrated to a typed code |
| `LEGALITY_EXECUTION_MISMATCH` | EngineDefect | NF-054, NF-056, NF-059, NF-062, NF-065, NF-089 | 8 |  | requires_friendly_weapon card resolved without a weapon |
| `MISSING_DISPATCH_HANDLER` | EngineDefect | NF-048, NF-067, NF-074 | 3 |  | SUPPORTED spell ability has no spell handler |
| `NUMERIC_RANGE_VIOLATION` | EngineDefect | NF-008, NF-114, NF-123 | 3 |  | int overflow of fresh instance cost_delta + modifier |
| `QUIESCENCE_VIOLATED` | EngineDefect | NF-101 | 1 |  | public access while a damage frame is open (frames cleared on every escaping failure, so this is a leak) |
| `RESOURCE_EXHAUSTED` | EngineDefect | NF-084 | 0 |  | infrastructure code: std::bad_alloc reaches the std::exception funnel (NF-084); the funnel must record it and… |
| `UNEXPECTED_EXCEPTION` | EngineDefect | NF-084, NF-117, NF-126 | 6 |  | catch std::exception: store prefix+what if unset, throw UnsupportedSimulationError(stored) |
| `UNKNOWN_EXCEPTION` | EngineDefect | NF-085 | 2 |  | catch(...): store 'unknown exception', throw Unsupported |
| `COLOSSAL_CAPACITY_UNREVIEWED` | RuleUnresolved | NF-037 | 3 |  | board lacks room for the Colossal body plus every appendage |
| `COLOSSAL_TRANSFORM_UNREVIEWED` | RuleUnresolved | NF-040 | 1 |  | transform into a Colossal definition |
| `CONTROL_CHANGE_UNREVIEWED` | RuleUnresolved | NF-081, NF-103, NF-116 | 3 |  | dying Reborn minion changed controller |
| `DAMAGE_OUTCOME_TARGET_UNRESOLVED` | RuleUnresolved | NF-052 | 1 |  | outcome check after damage cannot find the target |
| `DAMAGE_REACTION_ORDER_UNREVIEWED` | RuleUnresolved | NF-106, NF-110, NF-121, NF-125 | 4 |  | combat/hero-area/compound damage to a TakesDamage consumer |
| `DAMAGE_SOURCE_BOUNDARY_UNREVIEWED` | RuleUnresolved | NF-118, NF-122 | 4 |  | damage source left Play / changed controller or silence before a reaction |
| `DARK_GIFT_ASSIGNMENT_UNRESOLVED` | RuleUnresolved | NF-043 | 1 | ● | sampled options admit no distinct eligible gift assignment |
| `DARK_GIFT_STACKING_UNREVIEWED` | RuleUnresolved | NF-023 | 1 |  | gift applied to a non-fresh or non-hand instance |
| `DISCOVER_POOL_INCOMPLETE` | RuleUnresolved | NF-041 | 1 |  | catalog-derived pool smaller than choice_count |
| `EOT_SOURCE_BOUNDARY_UNREVIEWED` | RuleUnresolved | NF-071 | 1 |  | queued end-of-turn source left Play / changed controller / was silenced |
| `GENERATION_HAND_FULL_ORDER_UNREVIEWED` | RuleUnresolved | NF-005 | 1 |  | owner hand already holds 10 cards |
| `HEAL_MORTALLY_WOUNDED_UNREVIEWED` | RuleUnresolved | NF-061 | 2 |  | Heal / HealMinionToFull on a minion with health <= 0 (two sites) |
| `INSTANCE_COPY_SOURCE_UNREVIEWED` | RuleUnresolved | NF-033, NF-034 | 2 |  | Kindred copy source carries modifiers/keywords or a pending death |
| `MODIFIER_LIFETIME_UNREVIEWED` | RuleUnresolved | NF-025 | 1 |  | persistent modifier in a deck / on a Secret / on a Silenced minion |
| `OVERLOAD_CAPACITY_UNREVIEWED` | RuleUnresolved | NF-090 | 1 |  | pending/active overload exceeds the next turn's crystals |
| `POOL_EMPTY_SEMANTICS_UNREVIEWED` | RuleUnresolved | NF-004 | 1 |  | reviewed manifest with zero members |
| `POOL_IDENTITY_NOT_LOADED` | RuleUnresolved | NF-002 | 1 |  | takes_damage_pool_id names a manifest absent from the catalog |
| `POOL_MEMBERSHIP_CANDIDATE_ONLY` | RuleUnresolved | NF-003 | 1 |  | pool membership_status == CANDIDATE |
| `RANDOM_SECRET_POOL_MEMBERSHIP_MISMATCH` | RuleUnresolved | NF-072 | 1 |  | catalog-derived Mage Secret pool differs from the reviewed pinned membership |
| `RANDOM_SELECTION_PENDING_DEATH_UNREVIEWED` | RuleUnresolved | NF-049 | 1 |  | RandomEnemyMinion with a mortally wounded minion on any board |
| `REBORN_ORDERING_UNREVIEWED` | RuleUnresolved | NF-076, NF-077 | 3 |  | intervening death or board mutation between removal and Reborn return (two sites) |
| `SHATTER_MODIFIER_INHERITANCE_UNREVIEWED` | RuleUnresolved | NF-018 | 1 |  | Shatter source carries cost/damage/counter/enchant modifiers |
| `SHATTER_MODIFIER_MERGE_UNREVIEWED` | RuleUnresolved | NF-019 | 1 |  | recombining fragments carry modifiers |
| `SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED` | RuleUnresolved | NF-045, NF-068, NF-107 | 4 |  | mortally wounded Spell Damage source before the next instruction |
| `TAKES_DAMAGE_BOUNDARY_UNREVIEWED` | RuleUnresolved | NF-029 | 1 |  | consumer died/left/changed controller/was silenced before its checkpoint (lethal consumer included) |
| `UNSUPPORTED_CARD_BEHAVIOR` | Unsupported | NF-011 | 1 |  | card with ability NONE that is not VERIFIED_VANILLA reached dispatch |
| `UNSUPPORTED_CARD_ENTERED_HAND` | Unsupported | NF-016 | 1 |  | an UNSUPPORTED card enters a hand (draw, generation, Discover, Deathrattle) |
| `UNSUPPORTED_CARD_IN_ACTIVE_HAND` | Unsupported | NF-027 | 1 |  | active hand contains an UNSUPPORTED card |
| `UNSUPPORTED_DARK_GIFT_OUTCOME` | Unsupported | NF-022 | 1 |  | selected launch-reviewed gift has support_state UNSUPPORTED (never rerolled) |
| `UNSUPPORTED_DISCARD_TRIGGER` | Unsupported | NF-057 | 1 | ● | random discard picked a card with INVISIBLEDEATHRATTLE/DISCARD_TRIGGER |
| `UNSUPPORTED_DISCOVER_OUTCOME` | Unsupported | NF-086 | 1 |  | player chose a Discover option whose card is UNSUPPORTED |
| `UNSUPPORTED_GENERATED_CARD` | Unsupported | NF-007, NF-046, NF-075 | 3 | ● | sampled pool member has support_state UNSUPPORTED (no reroll) |
| `UNSUPPORTED_GENERATED_CARD_UNDEFINED` | Unsupported | NF-006 | 1 | ● | sampled pool member has no CardDefinition |
| `UNSUPPORTED_HERO_CLASS` | Unsupported | NF-014 | 1 |  | player class is not MAGE |
| `UNSUPPORTED_MINION_HISTORY_TYPE` | Unsupported | NF-031 | 1 |  | minion race outside the 12 tracked history types |
| `UNSUPPORTED_RANDOM_SECRET_OUTCOME` | Unsupported | NF-073 | 1 | ● | sampled Mage Secret has support_state UNSUPPORTED |
| `UNSUPPORTED_SECRET_DEPENDENCY` | Unsupported | NF-069 | 1 |  | Water Elemental token (CORE_CS2_033) is UNSUPPORTED |
| `UNSUPPORTED_SUMMONED_CARD` | Unsupported | NF-044 | 1 | ● | dynamic deck pool sampled an UNSUPPORTED minion |
| `UNSUPPORTED_TRANSFORM_OUTCOME` | Unsupported | NF-039 | 1 |  | transform target token has support_state UNSUPPORTED |
| `UNSUPPORTED_VANILLA_SPELL` | Unsupported | NF-047 | 1 |  | VERIFIED_VANILLA spell resolved as an effect spell |

`●` marks codes whose triggering outcome is sampled with the game RNG (and may therefore depend on hidden information, F16); defect-class codes are never marked. Two
infrastructure codes have no single source site: `RESOURCE_EXHAUSTED` is the `std::bad_alloc` that reaches NF-084, and `LEGACY_UNTYPED` is the
fail-safe default for an unmigrated throw. ILLEGAL (`std::invalid_argument` from `apply_action`) and load-time validation are deliberately
not `FailureCode`s: they do not poison a session.

### 7.2 Python and binding boundary rows

| ID | File | Function | Lines | Sites | Behaviour | Class | Note |
|---|---|---|---|---:|---|---|---|
| PB-01 | `engine.py` | `_load_native` | 78-85 | 2 | RuntimeError/ImportError when the extension is missing/unloadable | ENVIRONMENT_OR_ADAPTER_FAILURE | not a simulation failure; attempt_action never reaches it |
| PB-02 | `engine.py` | `ManaEngineSession.__init__` | 355 | 1 | non-Mage class: Python-level UnsupportedSimulationError before the native constructor | DESIGN_UNSUPPORTED | same semantic as NF-014 (UNSUPPORTED_HERO_CLASS); pre-session |
| PB-03 | `engine.py` | `observation / legal_actions / _legal_execution_keys / _appl…` | 387,396,419,434,448,484 | 6 | except native.UnsupportedSimulationError -> raise Python UnsupportedSimulationError(str(exc)) from exc | TRANSLATION (information-losing) | 6 sites; today copy only the message. 4K.1b must copy kind/code/detail/context (or wrap) so no typing is lost |
| PB-04 | `engine.py` | `_legal_execution_keys` | 426 | 1 | RuntimeError: native legal actions contain a duplicate execution key | ENGINE_DEFECT | enumeration defect detected in Python; 4K.1 reports ADAPTER_FAILURE (defect outcome, correct) - give it a precise reason |
| PB-05 | `engine.py` | `legal_actions` | 400-411 | 1 | enrichment indexes state.self_hand[hand_index]; IndexError/KeyError if native/observation disagree | ENGINE_DEFECT | public legal_actions only; attempt path uses _legal_execution_keys |
| PB-06 | `engine.py` | `_export_state / game_state_from_dict` | 283-327 | 1 | malformed observation dict -> KeyError/ValueError during domain export | ENGINE_DEFECT | attempt maps it to EXPORT_FAILED (correct outcome) |
| PB-07 | `engine.py` | `require_canonical_training_admission` | 335,340 | 2 | raises UnsupportedSimulationError as a POLICY gate (evidence debt / global gate) | POLICY_GATE | reuses the simulation exception class; must never be consumed as an UNSIMULATABLE signal - another reason to classify only on typed attributes |
| PB-08 | `engine.py` | `_execution_key` | 58,63 | 2 | ValueError for malformed action mappings | ILLEGAL_OR_CALLER_ERROR | attempt maps to ILLEGAL_MALFORMED |
| PB-09 | `python_bindings.cpp` | `register_exception<UnsupportedSimulationError>` | 18 | 0 | native class derives from builtins.Exception (NOT RuntimeError) and carries no attributes | TRANSLATION | typed payload must be attached here (custom translator) |
| PB-10 | `python_bindings.cpp` | `apply_action lambda` | 44 | 0 | apply and observation export are coupled: any observation failure after a successful apply escapes as the apply failure | ENGINE_DEFECT (export) | yields the 4K.1 ATTEMPT_INVARIANT_VIOLATED case (valid child + exception); split apply from export |
| PB-11 | `python_bindings.cpp` | `observation lambda` | 44 | 0 | any perspective string other than PLAYER2/ACTIVE silently maps to seat 0 | ILLEGAL_OR_CALLER_ERROR | the Python adapter validates the three allowed values; the binding does not |
| PB-12 | `python_bindings.cpp` | `action_from_dict` | 15 | 0 | missing key -> KeyError; bad value type -> RuntimeError (cast); unknown type -> ValueError | ILLEGAL_OR_CALLER_ERROR | never reached by attempt_action (canonical dicts only) |

## 8. Damage group (`damage_group.cpp`, plus its engine call sites)

The 44 sites in this file (34 `reject_unsupported`, 1 direct and 3 echo Unsupported throws, 2 wrappers = 2 `catch` + 2 writes, 2 `.at()`) split as follows (rows whose
first site is in `damage_group.cpp`):

| Class | Rows | Sites | Reason codes |
|---|---:|---:|---|
| `RULE_UNRESOLVED` | 9 | 12 | `CONTROL_CHANGE_UNREVIEWED`, `DAMAGE_REACTION_ORDER_UNREVIEWED`, `DAMAGE_SOURCE_BOUNDARY_UNREVIEWED`, `SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED` |
| `BUDGET_LIMIT` | 3 | 3 | `DAMAGE_DEPTH_BUDGET_EXCEEDED`, `DAMAGE_PACKET_BUDGET_EXCEEDED`, `DAMAGE_WORK_BUDGET_EXCEEDED` |
| `ENGINE_DEFECT` | 10 | 22 | `DAMAGE_FRAME_PROTOCOL_VIOLATION`, `DAMAGE_TARGET_LOST`, `INVALID_DAMAGE_PACKET`, `NUMERIC_RANGE_VIOLATION`, `QUIESCENCE_VIOLATED` |
| `ECHO` | 3 | 3 | — |
| `FUNNEL` | 2 | 4 | `UNEXPECTED_EXCEPTION` |

**Call structure.** `run_damage_group` → `open_damage_group` (preflight, packet checks, mutation loop under `catch(...)` #1) →
`dispatch_damage_event` per event (reactions, nested `deal_damage` possible in principle) → `close_damage_group`; the outer
`catch(...)` #2 wraps the whole sequence. Both wrappers pop frames and, when `S0` is unset, store a fixed string and rethrow.

**What can reach each wrapper.**

| Wrapper | Exceptions that can reach it | Writes a string when | Real classification of those |
|---|---|---|---|
| #1 mutation (`open_damage_group`, `damage group: mutation failed`) | `reject_unsupported` from `consume_damage_work` / `apply_damage_packet` (S0 already set); `std::out_of_range` from `card(m.card_id)` in `apply_damage_packet`; `std::bad_alloc` from `push_back`/trace strings | only for the last two | defects (`CATALOG_REFERENCE_MISSING`, `RESOURCE_EXHAUSTED`) |
| #2 reaction (`run_damage_group`, `damage group: reaction failed`) | every `reject_unsupported` from open/dispatch/close (S0 set); `state_.damage_frames.at()` and `card()` `out_of_range`; `generate_random_card_to_hand` `invalid_argument`/`bounded_random` `invalid_argument`; a direct `ability_of` Unsupported throw (the only *unsupported-semantics* exception that can reach it unwritten, and only with an unsupported minion on a board with no prior poison); `bad_alloc` | only for the unwritten ones | defects, except the unreachable `ability_of` corner |

So the two generic strings are, in practice, a "some non-`reject_unsupported` exception happened somewhere in the damage group" marker, and they
overwrite nothing but also preserve nothing: the original exception type and `what()` are lost at the funnel (`catch(const std::exception&)`
throws `Unsupported(S0)` using the stored wrapper string).

**Recommended treatment.**

1. Remove both string writes. The wrappers keep their only essential job — popping frames to the entry depth — and, when a typed failure is in flight or
   stored, append a *context* (`damage_group.mutation group=<id> depth=<n>` / `damage_group.reaction group=<id> depth=<n> event=<i>`) without touching
   `code` or `detail`.
2. An untyped exception passing through is not converted by the wrapper; the single `apply_action` funnel converts it (`UNEXPECTED_EXCEPTION`,
   `RESOURCE_EXHAUSTED`, `UNKNOWN_EXCEPTION`) and records the exception type and original `what()`. If a caller ever catches between the wrapper
   and the funnel, the frames are already consistent.
3. Type the sites by class: RULE_UNRESOLVED → `CONTROL_CHANGE_UNREVIEWED`, `DAMAGE_REACTION_ORDER_UNREVIEWED`, `DAMAGE_SOURCE_BOUNDARY_UNREVIEWED`, `SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED`; BUDGET_LIMIT → `DAMAGE_DEPTH_BUDGET_EXCEEDED`, `DAMAGE_PACKET_BUDGET_EXCEEDED`, `DAMAGE_WORK_BUDGET_EXCEEDED`; ENGINE_DEFECT → `DAMAGE_FRAME_PROTOCOL_VIOLATION`, `DAMAGE_TARGET_LOST`, `INVALID_DAMAGE_PACKET`, `NUMERIC_RANGE_VIOLATION`, `QUIESCENCE_VIOLATED`. Split NF-103 (control change versus `activation_sequence == 0`) and the structural sub-condition of NF-122.
4. The three budget caps become `BudgetLimit` codes and never the generic defect string; their fallback eligibility is a policy-table entry (Q1).

## 9. The 4K.1 heuristic against the native source paths

| 4K.1 reason | What the adapter tests | Native paths it actually recovers | Recall / precision problem | After 4K.1b |
|---|---|---|---|---|
| `NATIVE_UNSUPPORTED` | `Unsupported`, child invalid, no prefix, not a wrapper string | every S0-writing site (53 `RJ`, 25 `WT`, soft-write echoes) **and** the 27 `TU` sites | includes 47 defect sites; cannot tell a fence from a defect or a budget cap | **replaced** by `NATIVE_UNSUPPORTED` (kind `Unsupported`), `NATIVE_RULE_UNRESOLVED`, `NATIVE_BUDGET_LIMIT` taken from the typed kind |
| `ENUMERATION_UNAVAILABLE` | any `Unsupported` from `legal_actions()` | NF-027 (correct), NF-100 echo (impossible for a valid parent), NF-101 frames case (defect) | NF-101 is a defect reported as fallback-eligible | **kept** for kinds `Unsupported`/`RuleUnresolved` only; typed defects become `ENUMERATION_DEFECT` |
| `NATIVE_EXCEPTION_NORMALIZED` | message starts with `action failed after mutation: ` | only `std::exception`/`catch(...)` with `S0` unset (NF-084/085) | misses the 27 `TU` sites and every masked case; matches arbitrary text | **replaced** by `NATIVE_ENGINE_DEFECT` + code `UNEXPECTED_EXCEPTION`/`UNKNOWN_EXCEPTION`/`RESOURCE_EXHAUSTED`; **unnecessary** |
| `NATIVE_CATCH_ALL` | message equals one of two wrapper strings and `S0` | NF-117/126 writes (never executed natively) | covered only by FakeSession; hides the original | **unnecessary** (strings removed; originals survive with context) |
| `ATTEMPT_INVARIANT_VIOLATED` | `Unsupported` raised while the child is still valid; invalid child after apply; export/evidence mismatch | PB-10 (export failure inside the apply binding); adapter postconditions | the first trigger disappears once apply and export are split | **kept** for adapter postconditions; add stored-vs-thrown mismatch |
| `ADAPTER_FAILURE` | any non-`Unsupported` exception from enumeration/apply/diagnostics | raw `IndexError`/`ValueError`/`RuntimeError` from the binding (NF-028 `.at()`, PB-04 duplicate key, binding casts) | native defects thrown as `std::*` outside the funnel are filed under "adapter" | **kept, narrowed**: native const-path defects are typed `EngineDefect` first |
| `CLONE_FAILED`, `EXPORT_FAILED` | clone/export raised or returned invalid | unchanged | none found | unchanged |

## 10. Failure-state contract

* **Is a defected session always invalid? Is an unsupported session always invalid?** Yes to both. Today every escaping failure poisons the session
  and nothing un-poisons it; keep that. Kind decides reporting and eligibility, never validity. Neither kind may be a simulation root; both fail
  `InvalidParentSession`.
* **Should native state carry `failure_kind`, `failure_code`, `failure_detail` instead of one string?** Yes — as one `FailureRecord` in
  `std::optional<FailureRecord> failure_`. `is_valid()` becomes `!failure_`; `unsupported_outcome()` stays and returns `failure_->detail` unchanged.
* **Precedence.** One writer, `record_failure()`: first record wins, except an `EngineDefect` supersedes a non-defect record (the prior record is kept in
  `context`); nothing downgrades. This replaces the 26 overwrites and keeps "defect never silently becomes unsupported".
* **`require_quiescent`.** Rethrows the stored record exactly (same code, detail, context). The frames-open case throws a fresh `EngineDefect`
  (`QUIESCENCE_VIOLATED`); being const it cannot store it.
* **Accessors on a failed session.** `legal_actions`, `observation`, `clone`, `is_complete`, `result`, `needs_choice`, `choice_options` throw the stored
  record; `is_valid`, `failure`, `unsupported_outcome`, `seed`, `evidence_constraints`, `diagnostic_trace` never throw (probe in §12 confirms the current split).
* **Clone.** Public `clone()` already refuses a failed session through `require_quiescent`, so a failure is never copied. Keep: a clone always has
  `failure() == nullopt`; evidence, trace and RNG copy as today; a failed child never escapes and the parent is never touched (4K.1 SA07/SA21 unchanged).
* **Diagnostics and provenance.** `detail` is today's text byte for byte (existing tests match on it), `context` is the wrapper/funnel context, `code`
  is the stable identity. Session evidence constraints stay a separate set; the adapter snapshots them into `evidence_at_failure`, which is how
  `RULE_UNRESOLVED` provenance stays visible.
* **Invariants to test.** I1 the thrown record equals the stored record; I2 `kind == failure_kind_of(code)`; I3 first record wins except defect
  upgrade; I4 a record is never cleared or copied into a clone.

## 11. Enumeration, observation and export

**Enumeration** (`legal_actions` / `semantic_legal_actions`). Failures here cannot poison (const). Three distinct situations: a valid parent whose
active hand holds an unsupported card (NF-027, `UNSUPPORTED_CARD_IN_ACTIVE_HAND`, `Unsupported`, stays `UNSIMULATABLE / ENUMERATION_UNAVAILABLE` and is the
Phase 4K.1c integration point); a leaked damage frame (NF-101, `EngineDefect`); and an out-of-range index while describing actions (NF-028, `EngineDefect`,
today a raw `IndexError` filed under `ADAPTER_FAILURE`). The echo of an existing poison (NF-100) is impossible for a valid parent.
A failure to enumerate because a valid mechanic is unknown is therefore distinguishable from an invariant failure only through the typed kind, which is
the whole point of the contract.

**Observation / export.** Every native failure while exporting a state must be `EngineDefect` and never fallback-eligible. The audit found three
export-path hazards: `ability_of` inside `observation()` (F14), `card()` inside `base_card` (NF-015), and the evidence-ID name table (NF-096, impossible
enumerator). Fixes: make the board-minion trigger lookup non-throwing, type the rest as `EngineDefect`, and split apply from export in the binding so a failed
export can never masquerade as an apply failure (F9). Python-side `_export_state`/`game_state_from_dict` failures stay `EXPORT_FAILED`.

## 12. Python and pybind boundary

Probed on the freshly built module (this worktree, release build):

| Situation | What Python receives |
|---|---|
| deck card id absent from the catalog (native constructor) | `IndexError: Card missing from prototype catalog: NO_SUCH_CARD` (std::out_of_range) |
| catalog without the Dark Gift manifest | `ValueError: Dark Gift option manifest is not loaded: EDR_488` (load-time validation) |
| non-Mage class, native constructor | native `UnsupportedSimulationError`; the adapter raises its own Python `UnsupportedSimulationError` first |
| stale / illegal action | `ValueError: action is not legal in the current position` (non-poisoning) |
| unknown action type / missing key / wrong value type | `ValueError` / `KeyError` / `RuntimeError` (pybind cast) |
| `observation("NOPE")` | succeeds (maps to seat 0; no validation in the binding) |
| `END_TURN` that draws an unsupported card | Python `UnsupportedSimulationError('unsupported card entered player hand; simulation branch invalid')`; `is_valid=False` |
| poisoned session | `legal_actions`, `observation`, `clone`, `is_complete` raise the stored text; `seed`, `evidence_constraints`, `is_valid`, `unsupported_outcome` do not |
| native exception class | MRO `UnsupportedSimulationError → Exception`; the Python adapter class is `UnsupportedSimulationError → RuntimeError` |

| Native exception | What Python receives |
|---|---|
| UnsupportedSimulationError (registered; base builtins.Exception) | manaengine_native.UnsupportedSimulationError; the adapter re-raises manamind...UnsupportedSimulationError(RuntimeError) with only the message |
| std::invalid_argument | ValueError |
| std::out_of_range | IndexError |
| std::logic_error / std::runtime_error / other std::exception | RuntimeError |
| std::bad_alloc | MemoryError (but execute_action's catch(const std::exception&) normalises it first, so Python never sees it) |
| py::key_error / py::cast_error from action_from_dict | KeyError / RuntimeError |

## Appendix 1 — catalog-constructor validation families (load time)

| Catalog-constructor validation family (approximate, by first message literal) | Sites |
|---|---:|
| Dark Gift / Discover option manifests | 10 |
| Choose One | 8 |
| Shatter | 4 |
| Secret contracts | 3 |
| Colossal / Reborn / Kindred / Prepare | 5 |
| RandomDistinct (reject lambda) | 6 |
| Damage-outcome follow-ups | 5 |
| SummonFixed / dependencies | 4 |
| Spell Damage / Deathrattle / Lifesteal values | 13 |
| Effect-step shape (Heal/Freeze/Damage/Buff/Discard/Weapon…) | 27 |
| Pool / manifest identity | 3 |
| Ability / support-state / reviewed-contract allowlists | 8 |
| other declaration-shape checks | 6 |
| **CardCatalog constructor total** | **102** |

All are `std::invalid_argument` → `ValueError` raised by `CardCatalog(...)`; none can occur after a session exists. They are listed as families
because the 102 sites share one semantic (`ENVIRONMENT_OR_ADAPTER_FAILURE`, never a game branch). The F11 validation gaps are *missing* checks, not entries here.

## Appendix 2 — reproduction

```bash
python reports/manaengine_unknown_state_architecture/phase_4k1b_failure_site_audit.py scan
python reports/manaengine_unknown_state_architecture/phase_4k1b_failure_site_audit.py check
# dynamic evidence (scratch tree outside the repository; build with /FI<out>/site_trace.hpp on MSVC):
python reports/manaengine_unknown_state_architecture/phase_4k1b_failure_site_audit.py instrument <out_dir>
# then: MANA_SITE_HITS=<file> manaengine_tests.exe ; MANA_SITE_HITS=<file> pytest <ManaEngine files>
```

## A. IMPLEMENTATION DECISIONS

**D1 — Two-level contract: a stable kind and an append-only code, the kind derived from the code.** The repository already has this pattern
(`EvidenceConstraint` + `evidence_constraint_id()` + a pybind enum); reuse it.

```cpp
enum class FailureKind : std::uint8_t { Unsupported = 1, RuleUnresolved = 2, BudgetLimit = 3, EngineDefect = 4 };   // append-only
enum class FailureCode : std::uint16_t { LegacyUntyped = 1, /* explicit numeric values, append-only */ };
const char* failure_code_id(FailureCode);     // "UNSUPPORTED_GENERATED_CARD": the stable external identity
const char* failure_kind_id(FailureKind);     // "UNSUPPORTED"
FailureKind failure_kind_of(FailureCode);     // exhaustive switch without `default`: a missing kind is a compiler warning (/W4 C4062, -Wswitch)
struct FailureRecord { FailureCode code; std::string detail; std::string context; FailureKind kind() const { return failure_kind_of(code); } };
```

Kind alone cannot be asserted precisely by tests or diagnosed; a code alone makes policy depend on an ever-growing enum; deriving the kind from the code
removes any possibility of an inconsistent pair. `Illegal` is not a kind: an illegal action stays a non-poisoning `std::invalid_argument`. The proposed
codes are in §7.1 (57 mapped to current sites: BudgetLimit 3, EngineDefect 14, RuleUnresolved 25, Unsupported 15); their final spelling is the implementation's.

**D2 — One typed exception, `UnsupportedSimulationError` stays the universal base.**

```cpp
class UnsupportedSimulationError : public std::runtime_error {      // name, base and what() unchanged
 public:
  explicit UnsupportedSimulationError(const std::string& detail);                              // legacy string-only throw => LegacyUntyped
  UnsupportedSimulationError(FailureCode code, std::string detail, std::string context = {});
  const FailureRecord& record() const noexcept;                                                // what() == record().detail
};
```

The legacy constructor yields `LEGACY_UNTYPED`, kind `EngineDefect`. Any throw that migration misses therefore surfaces as a defect in tests rather than
hiding as a fallback candidate: the default flips from "unsupported unless proven a defect" to "defect unless proven typed". No per-kind C++ subclass is needed.

**D3 — Session state and the single writer.** Replace `std::optional<std::string> state_.unsupported` with `std::optional<FailureRecord> failure_`.
`is_valid()` is `!failure_`. Keep `unsupported_outcome()` returning `failure_->detail` byte for byte (existing tests match on it) and add `failure()`.
Replace `reject_unsupported(std::string)` with `[[noreturn]] void fail(FailureCode, std::string detail)`; add `record_failure(...)` (used by the four soft
sites and the funnel) and `[[noreturn]] rethrow_stored()` (the 13 echo sites). Precedence: first record wins, an `EngineDefect` supersedes a non-defect
record with the prior kept in `context`, nothing downgrades or clears. Invariants I1–I4 of §10 are tested.

**D4 — The funnel becomes the only converter of untyped exceptions.** In `apply_action`: `catch (UnsupportedSimulationError&)` records if absent, clears
frames and rethrows the *effective* stored record; `catch (std::bad_alloc&)` records `RESOURCE_EXHAUSTED`, clears frames and rethrows the original so pybind
raises `MemoryError` and SA22 holds end to end; `catch (std::exception&)` records `UNEXPECTED_EXCEPTION` with `detail = "action failed after mutation: " + type + ": " + what`
(prefix kept so existing text assertions survive) and throws the effective record; `catch (...)` records `UNKNOWN_EXCEPTION`. The original type and `what()` are always kept in
`detail` even when a prior record exists (severity rule applies).

**D5 — Damage-group wrappers lose their strings.** Remove the two `damage group: mutation/reaction failed` writes; keep frame cleanup; append a context to the stored/in-flight typed
failure (§8). Strings `NATIVE_CATCH_ALL` matched on disappear.

**D6 — Const and static callees throw typed exceptions directly.** `ability_of` (`UNSUPPORTED_CARD_BEHAVIOR` / defect for the unknown-ability branch), `legal_actions`
line 192 (`UNSUPPORTED_CARD_IN_ACTIVE_HAND`), `require_quiescent` frames (`QUIESCENCE_VIOLATED`), `card()` (`CATALOG_REFERENCE_MISSING`), `observation` (all `EngineDefect`; the
board-minion `ability_of` lookup becomes non-throwing, F14).

**D7 — Budget caps.** Three `BudgetLimit` codes. In the Python policy table `BUDGET_LIMIT` is *not* fallback-eligible until Q1 is decided, so the first release cannot route a possible
runaway to a neural estimate.

**D8 — Binding.** (a) A custom exception translator raises the Python class chosen by kind (`UnsupportedSimulationError`, or its subclass `EngineDefectError` for `EngineDefect`) and sets
`kind`, `code`, `detail`, `context` attributes; (b) `GameSession.failure` property returning a dict or `None`; (c) `apply_action_unobserved(dict) -> None` for the adapter, with the existing
`apply_action` unchanged for compatibility; (d) `observation` rejects an unknown perspective string instead of mapping it to seat 0; (e) `evidence_constraints` export path typed.

**D9 — Compatibility, answered explicitly.**

| Question | Decision |
|---|---|
| `EngineDefectError : UnsupportedSimulationError`? | **Yes**, on both the native-exposed and Python sides. Every existing `except UnsupportedSimulationError` / `pytest.raises(UnsupportedSimulationError, match=…)` keeps working for every kind (26 uses in `test_adapter.py`, 30 in `native_tests.cpp`, fire/damage-group suites). The only in-repo non-test consumer is `attempt_action`, which classifies on attributes first. |
| Hazard of old catchers | A caller that catches `UnsupportedSimulationError` and treats it as "skip this branch" would also skip defects. Documented in the class docstring; new code must read `.failure.kind`. No other production consumer exists today. |
| Message text | Unchanged (`detail == what()`), diagnostic only. After 4K.1b no classification code reads it; a test asserts `simulation.py` no longer contains the prefix/wrapper literals. |
| Public `apply_action` | Unchanged signature and ACTIVE-seat return; illegal still `ValueError`; failures still `UnsupportedSimulationError` (or its defect subclass) with the same text. |
| `SimulationAttempt` | Distinguishes the exact kind and code from typed attributes; untyped `UnsupportedSimulationError` ⇒ `ENGINE_DEFECT / NATIVE_FAILURE_UNTYPED`. |

**D10 — Outcome mapping (Python).**

| Native kind | `SimulationOutcome` | `AttemptReason` | `fallback_eligible` (policy table) |
|---|---|---|---|
| `Unsupported` | `UNSIMULATABLE` | `NATIVE_UNSUPPORTED` | true |
| `RuleUnresolved` | `UNSIMULATABLE` | `NATIVE_RULE_UNRESOLVED` (new; code and `evidence_at_failure` stay visible) | true |
| `BudgetLimit` | `UNSIMULATABLE` | `NATIVE_BUDGET_LIMIT` (new) | **false** until Q1 |
| `EngineDefect` | `ENGINE_DEFECT` | `NATIVE_ENGINE_DEFECT` (new; code in diagnostics) | false |
| enumeration `Unsupported`/`RuleUnresolved` | `UNSIMULATABLE` | `ENUMERATION_UNAVAILABLE` | true |
| enumeration `EngineDefect` | `ENGINE_DEFECT` | `ENUMERATION_DEFECT` (new) | false |
| no typing available | `ENGINE_DEFECT` | `NATIVE_FAILURE_UNTYPED` (new) | false |

`fallback_eligible` becomes `outcome == UNSIMULATABLE and reason in FALLBACK_ELIGIBLE_REASONS` instead of a bare outcome test.

**D11 — Out of scope for 4K.1b:** `Q_fallback`, unsupported-held-card semantics (4K.1c), search, runtime `validate_invariants` (Q2), the F11 catalog-hardening checks and the split of
legal-but-knowably-unsimulatable actions (F15). Source guard: a lint-style check forbids new `reject_unsupported(` calls and untyped `throw UnsupportedSimulationError(<string>)` outside an allowlist.

## B. SITE MIGRATION PLAN

Each batch compiles and passes on its own; unmigrated throws are fail-safe because of `LEGACY_UNTYPED`.

| Batch | Content | Rows | Sites | Row ids |
|---|---|---:|---:|---|
| B0 | Foundation: enums, `FailureRecord`, typed exception, `failure_`, `record_failure/fail/rethrow_stored`, funnel, binding translator and `failure` property, Python plumbing, code-table test (T19), legacy default (T20) | 0 | 0 | — |
| B1 | Echoes, funnels and wrappers (13 echo + 12 funnel/wrapper sites) and the leaked-frame defect NF-101; remove the two damage-group strings | 13 | 26 | NF-009, NF-026, NF-032, NF-083–085, NF-088, NF-100–101, NF-109, NF-117, NF-124, NF-126 |
| B2 | `DESIGN_UNSUPPORTED` sites, including the four soft writes and the static/const throws | 17 | 17 | NF-006–007, NF-011, NF-014, NF-016, NF-022, NF-027, NF-031, NF-039, NF-044, NF-046–047, NF-057, NF-069, NF-073, NF-075,… |
| B3a | `RULE_UNRESOLVED` — pools, hand, Shatter, Dark Gift, modifier lifetime (G1–G3) | 8 | 8 | NF-002–005, NF-018–019, NF-023, NF-025 |
| B3b | `RULE_UNRESOLVED` — TakesDamage, copy, Colossal, Discover, spell damage, effects (G5–G7) | 11 | 14 | NF-029, NF-033–034, NF-037, NF-040–041, NF-043, NF-045, NF-049, NF-052, NF-061 |
| B3c | `RULE_UNRESOLVED` — Secrets, Reborn, end-turn, Overload and damage-group fences (G8, G9, G11); split NF-103 and NF-122 | 16 | 20 | NF-068, NF-071–072, NF-076–077, NF-081, NF-090, NF-103, NF-106–107, NF-110, NF-116, NF-118, NF-121–122, NF-125 |
| B4 | `BUDGET_LIMIT` caps (3 sites) and the policy table entry | 3 | 3 | NF-102, NF-111, NF-113 |
| B5a | `ENGINE_DEFECT` in `engine.cpp` (execution scope; split NF-078) | 40 | 49 | NF-001, NF-008, NF-010, NF-012–013, NF-015, NF-017, NF-020–021, NF-024, NF-028, NF-030, NF-035–036, NF-038, NF-042, NF-… |
| B5b | `ENGINE_DEFECT` in `damage_group.cpp` | 9 | 21 | NF-104–105, NF-108, NF-112, NF-114–115, NF-119–120, NF-123 |
| B5c | `ENGINE_DEFECT` test-only invariants and impossible-enum name tables (typed, T22) | 4 | 20 | NF-091–093, NF-133 |
| B6 | Unchanged by design: `ILLEGAL_OR_CALLER_ERROR` (non-poisoning `std::invalid_argument`) and load-time validation (`ValueError`); inventory rows only gain an explicit disposition | 7 | 132 | NF-082, NF-094–095, NF-130–132, NF-134 |
| B7 | Optional hardening, no inventory rows: apply/export split (F9), non-throwing observation lookup (F14), catalog gaps (F11), perspective validation, deck-id validation at construction | — | — | — |

Rules for all batches: do not change message text (tests match it); a site that carries mixed conditions is split (NF-078, NF-103, NF-122) *before* typing; the inventory `check`
is re-run and its rows regenerated (`status` per row) so that `unmigrated == 0` is a CI-visible fact; Windows is built locally, Ubuntu through hosted CI.

## C. PYTHON ADAPTER MIGRATION

`engine.py`

1. Add `FailureKind(str, Enum)`, a frozen `NativeFailure(kind, code, detail, context)` and `EngineDefectError(UnsupportedSimulationError)`; give `UnsupportedSimulationError` an optional
   `failure: NativeFailure | None`.
2. Replace the six `except self._unsupported_exception as exc: raise UnsupportedSimulationError(str(exc)) from exc` translations (PB-03) by one helper `_wrap_native(exc)` that copies the native
   attributes and returns `EngineDefectError` for `ENGINE_DEFECT`; a native exception without attributes yields `EngineDefectError` with code `LEGACY_UNTYPED`.
3. `ManaEngineSession.failure -> NativeFailure | None` from the new native property; `unsupported_outcome` unchanged.
4. `_apply_raw` calls `apply_action_unobserved`; the public `apply_action` keeps its post-action ACTIVE view through a separate observation call.
5. Duplicate-execution-key detection raises a typed enumeration defect instead of a bare `RuntimeError`.

`simulation.py` — classification becomes a pure function of typed attributes:

```python
def _classify(exc_failure, child_failure, *, enumeration=False):   # typed attributes only; never message text
    if exc_failure is None and child_failure is None:               # no typing at all: fail safe
        return ENGINE_DEFECT, NATIVE_FAILURE_UNTYPED
    if exc_failure is not None and child_failure is not None and exc_failure != child_failure:
        return ENGINE_DEFECT, ATTEMPT_INVARIANT_VIOLATED            # invariant I1 broken
    failure = exc_failure or child_failure
    return KIND_TO_OUTCOME[failure.kind]                            # table in D10; enumeration variant when enumeration=True
```

* Delete the `startswith("action failed after mutation: ")` test, the two wrapper-string equality tests and the `child.is_valid → ATTEMPT_INVARIANT_VIOLATED` guess for `Unsupported`. Keep
  `ATTEMPT_INVARIANT_VIOLATED` only for real postconditions (valid child after an exception, invalid child after apply, export/evidence mismatch, stored-vs-thrown mismatch).
* `AttemptDiagnostics` gains `native_failure: NativeFailure | None`; `unsupported_outcome`/`exception_message` remain text for humans.
* `AttemptReason.NATIVE_EXCEPTION_NORMALIZED` and `NATIVE_CATCH_ALL` become unnecessary: keep the members one release as deprecated, never emitted, then remove in 4K.1c.
* **Heuristic remaining temporarily: none.** The only compatibility behaviour is the fail-safe default for untyped failures. `FakeSession` in `tests/test_simulation_attempt_contract.py` is rewritten to raise typed failures
  (its message strings become deliberately misleading to prove text is ignored).
* `tests/test_adapter.py` and `native_tests.cpp` are not edited for text; the new assertions are additions.

## D. TEST MATRIX

Native tests use `TestAccess` for injection and pin `(kind, code)` through a helper `fails_as(session, kind, code, fn)` that replaces the bare `fails_closed` where the reason matters;
Python tests add a `FakeSession` typed-failure family and real-native cases. "Rows" are inventory rows from the table in §7.

| ID | Case | Native assertion | Python / `attempt_action` assertion | Rows |
|---|---|---|---|---|
| T01 | ordinary unsupported card → typed unsupported | opponent draws UNSUPPORTED card (SA16 fixture): `failure()` kind `Unsupported`, code `UNSUPPORTED_CARD_ENTERED_HAND`; static `ability_of` throw typed; thrown record equals stored | `UNSIMULATABLE / NATIVE_UNSUPPORTED`, `fallback_eligible`, `diagnostics.native_failure.code` | NF-011, NF-014, NF-016, NF-031–032, NF-039, NF-047, NF-069 |
| T02 | unresolved/candidate pool and review fences → `RuleUnresolved` | candidate pool, unloaded pool (adapter `UNLOADED_POOL_FOR_ADAPTER_TEST`), hand-full generation, Shatter modifiers, Colossal capacity, lethal TakesDamage consumer, RandomEnemyMinion pending death each assert kind and code | `UNSIMULATABLE / NATIVE_RULE_UNRESOLVED`, eligible, `evidence_at_failure` preserved | NF-002–005, NF-018–019, NF-023, NF-025, NF-029, NF-033–034, NF-037, NF-040–041, NF-043, NF-045, NF-049, NF-052, NF-061, NF-068, NF-071–072, NF-076–077, NF-081, NF-090, NF-103, NF-106–107, NF-110, NF-116, NF-118, NF-121–122, NF-125 |
| T03 | unsupported selected/sampled outcome: typed, **no reroll** | DG21 and Discover/Dark Gift/summon/Deathrattle variants: code per site; RNG after the failure equals a shadow session that consumed exactly the one sample | SA06 real Fire seed scan additionally asserts the native code and the sampled identity | NF-006–007, NF-022, NF-044, NF-046, NF-057, NF-073, NF-075, NF-086 |
| T04 | deliberate budget exhaustion → `BudgetLimit` | DG23 depth (64 frames) and work (4096): kinds and three codes; first reason kept | fake typed `BudgetLimit` → `UNSIMULATABLE / NATIVE_BUDGET_LIMIT`, `fallback_eligible == False`; flipping the policy table flips the property | NF-102, NF-111, NF-113 |
| T05 | internal invalid damage packet / impossible state → `EngineDefect` | DG23 `bad=0..3` and the other injected structural cases assert `EngineDefect` and the exact code, not just "fails closed" | typed fake and (where reachable) real native → `ENGINE_DEFECT / NATIVE_ENGINE_DEFECT`, never eligible | NF-001, NF-008, NF-010, NF-012, NF-015, NF-017, NF-020–021, NF-024, NF-030, NF-035–036, NF-038, NF-042, NF-050–051, NF-053, NF-055, NF-058, NF-060, NF-063–064, NF-066, NF-070, NF-078–080, NF-087, NF-104–105, NF-108, NF-112, NF-114–115, NF-119–120, NF-123 |
| T06 | std::exception after mutation → `EngineDefect`, original reason kept | SA11 and `TEST_POST_MUTATION_LOGIC_ERROR`: code `UNEXPECTED_EXCEPTION`, `detail` holds type and original `what()`; crafted-catalog cases NF-048/NF-067 (§3.4) → `MISSING_DISPATCH_HANDLER`; `catch(...)` case via a thrown non-std type | SA11 now asserts the native code; the two §3.4 reproductions flip to `ENGINE_DEFECT` | NF-013, NF-048, NF-054, NF-056, NF-059, NF-062, NF-065, NF-067, NF-074, NF-083–085, NF-089 |
| T07 | damage-group wrapper preserves the original typed failure | inject `std::out_of_range` in the mutation loop and in a reaction (missing `card_id`): stored code is the funnel's `UNEXPECTED_EXCEPTION`/`CATALOG_REFERENCE_MISSING` with original text, `context` names the wrapper, no `damage group: … failed` string; a typed reject keeps its code with appended context | nested-frame typed failure arrives with code intact | NF-117, NF-126 |
| T08 | enumeration: unsupported versus defect | injected unsupported active hand → `UNSUPPORTED_CARD_IN_ACTIVE_HAND`, non-poisoning; open frame → `QUIESCENCE_VIOLATED`; out-of-range index → typed defect | `ENUMERATION_UNAVAILABLE` versus `ENUMERATION_DEFECT`; duplicate execution key → `ENUMERATION_DEFECT` | NF-027–028, NF-101 |
| T09 | `require_quiescent` / accessors return the typed stored failure | every poisoned accessor throws the identical record (code, detail, context); non-throwing accessors listed in §10 do not; clone refusal never replaces the first record (DG20 extended) | `InvalidParentSession` for any failed parent | NF-009, NF-026, NF-088, NF-100, NF-109, NF-124 |
| T10 | public `apply_action` compatibility | illegal action still `std::invalid_argument` and non-poisoning | existing `test_adapter.py` unchanged and green; `EngineDefectError` is an `UnsupportedSimulationError`; ACTIVE-seat return unchanged | NF-082, NF-094–095, NF-134 |
| T11 | load-time validation unchanged | catalog/manifest errors still `std::invalid_argument` (`ValueError`); unknown perspective rejected by the binding | `ValueError` surfaces unchanged | NF-130–133 |
| T12 | `SimulationAttempt` no longer reads text | — | fakes whose messages mimic the old prefix/wrapper strings but carry kind `Unsupported` ⇒ `UNSIMULATABLE`; messages without them but kind `EngineDefect` ⇒ `ENGINE_DEFECT`; untyped ⇒ `NATIVE_FAILURE_UNTYPED`; source test: `simulation.py` contains no prefix/wrapper literal | — |
| T13 | `fallback_eligible` iff the category authorises it | — | table-driven over every `(outcome, reason)`; inconsistent pairs rejected by `__post_init__` | — |
| T14 | parent/clone guarantees unchanged | failed clone has no failure, parent keeps `failure() == nullopt` | SA01–SA25 pass unmodified; repeated attempts yield identical typed records | — |
| T15 | Windows and Ubuntu parity | table totality and `-Wall -Wextra -Wpedantic` (`/W4`) clean for `failure_kind_of`; ctest | hosted CI ManaEngine workflow on both OSes plus the Source workflow | — |
| T16 | `std::bad_alloc` | injected allocation failure: session poisoned with `RESOURCE_EXHAUSTED`, original rethrown | Python receives `MemoryError`; `attempt_action` propagates it (SA22) | NF-084 |
| T17 | severity precedence | soft `Unsupported` then injected defect ⇒ stored `EngineDefect` with the prior in `context`; defect then `Unsupported` ⇒ defect kept | — | NF-032, NF-084 |
| T18 | thrown record equals stored record (I1) | property check over the T01–T07 fixtures | `exc.failure == child.failure` or `ATTEMPT_INVARIANT_VIOLATED` | — |
| T19 | code table | unique ids, `kind` total, numeric values golden list (append-only), every inventory code exists | — | — |
| T20 | legacy default | an untyped `throw UnsupportedSimulationError("x")` ⇒ `LEGACY_UNTYPED`, kind `EngineDefect` | attempt ⇒ `ENGINE_DEFECT` | — |
| T21 | source guard and inventory | script rejects new `reject_unsupported(` / untyped throws outside the allowlist; `phase_4k1b_failure_site_audit.py check` passes against the regenerated inventory | — | — |
| T22 | invariant validator typing | corrupt state through `TestAccess`; `validate_invariants` throws typed `INVARIANT_VIOLATION` per family | — | NF-091–093, NF-096 |

## E. RISKS / OPEN QUESTIONS

Only genuinely unresolved items; each has a safe default so none blocks the task.

* **Q1 — Fallback eligibility of `BudgetLimit`.** All three caps guard against runaway reaction recursion that no supported content can produce today, so a trip is more likely a loop
  defect than a "valid but large" branch. Default in D10: not eligible; revisit when a content package makes a cap reachable by design.
* **Q2 — Runtime `validate_invariants`.** It is test-only. Calling it on a completed child before exposing it would turn silent state corruption into `ENGINE_DEFECT` but costs O(state) per
  attempt and needs a measurement. Default: not in 4K.1b.
* **Q3 — 28 judgement-call classifications** (rows flagged `medium confidence`): NF-004, NF-006, NF-015, NF-023, NF-030, NF-035, NF-041, NF-047–048, NF-052, NF-054, NF-056, NF-059, NF-062, NF-065, NF-067, NF-071, NF-074, NF-078, NF-090, NF-102–104, NF-108, NF-111, NF-113, NF-116, NF-122. The codes can be kept; the reviewer should confirm the kind where
  "fence versus structural" was a close call (notably NF-052, NF-054/056/059/062/065, NF-067/074, NF-078, NF-103/104/108, NF-122).
* **Q4 — Hidden-information dependence.** 6 sampled-outcome codes (F16) mean an unsupported *outcome* can depend on hidden RNG/deck state. The typed contract exposes it; whether a live-root
  consumer may treat such a result as fallback-eligible belongs to the determinization design, not here.
* **Q5 — Scope of catalog hardening (F11).** Seven missing load-time checks make some defect paths reachable; recommended as an immediately following hardening task or a final optional batch.
* **Risk — text coupling.** If an implementation changes `detail` text, existing message assertions break (`test_adapter.py`, SA06/SA11/SA16, native `find("…")` checks); D9 forbids it.
* **Risk — translator complexity.** The pybind exception translator is the only non-mechanical native part; it needs a native test that attributes survive a round trip (T18).
* **Risk — Ubuntu.** Not verifiable locally; the hosted run is the evidence (T15).

## F. NEXT TASK

**Phase 4K.1b implementation — typed native failures** (for GPT-6.1 Sol High). Authority: this audit, `docs/PARTIAL_SIMULATOR_ARCHITECTURE.md`, AGENTS.md. New clean worktree/branch from `origin/main`.

*Do:* implement D1–D10 and B0–B5 exactly; regenerate the inventory (`unmigrated == 0`); rewrite the `FakeSession` family; add T01–T22; update `docs/PARTIAL_SIMULATOR_ARCHITECTURE.md` §§3, 6, 10 and the 4K.1b status
lines; add the source guard (T21). Keep `detail` text byte-identical.

*Also recommended inside the task if the diff stays small:* split apply from export (D8c), make the board-minion trigger lookup non-throwing (F14), validate perspective in the binding (D8d), validate deck ids at session construction.

*Do not:* implement `Q_fallback`, unsupported-held-card semantics, search or determinization; change card declarations, manifests, registry, DATA-0A, overlay or training; add runtime `validate_invariants` (Q2); change generated-card, pool or damage semantics; reclassify a row without recording it in the inventory.

*Acceptance:* native `manaengine_tests` and CTest green; ManaEngine pytest set green (172 + new); `ruff`, generator identity guard, `git diff --check` clean; hosted ManaEngine and Source workflows green on Windows and Ubuntu; every row of the inventory has a typed code or an
explicit non-poisoning/load-time disposition; `simulation.py` contains no message-prefix classification; a test proves an untyped throw is `ENGINE_DEFECT`.

*Stop after* hosted acceptance and a completion report; promotion to `main` only as the user directs, no follow-on phase.
