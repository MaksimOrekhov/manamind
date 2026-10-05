# TIME_855 Arcane Barrage — Phase 4I.1 bounded targeting implementation: completion

Authoritative specification: `ARCANE_BARRAGE_RULES_EVIDENCE.md` (Revision 3, verdict `ARCANE_BARRAGE_BOUNDED_WITH_EVIDENCE_DEBT`). The rules
contract was implemented as accepted; no source contradiction was found, so nothing was re-opened.

## 1. Identity

| | |
|---|---|
| Starting HEAD (= canonical remote HEAD) | `0de862116821301730a4dc7d13de3dcdb6ef04fb` |
| Implementation commit | `826499e9c0da6dc04a5646acf854094bd0bd5dfd` (`feat(manaengine): implement bounded Arcane Barrage targeting`) |
| Final HEAD | the commit that adds this file, directly on top of `826499e`; a document cannot embed its own hash, so the exact SHA is stated in the hand-off message and in `git log -1 codex/manaengine-first-deck` |
| Branch | pushed fast-forward to `codex/manaengine-first-deck` (`0de8621..826499e`), no force |

Preflight: worktree clean, `HEAD == origin/codex/manaengine-first-deck == 0de8621`, recent history matched the five commits named in the task.

## 2. Exact declarative shape

`experiments/manaengine/data/card_abilities.json`, `TIME_855`:

```json
{
  "ability": "EFFECT_COMPOSITION", "support_state": "SUPPORTED",
  "reviewed_rules_text": "Deal $3 damage to an enemy and $2 damage to two other random ones.",
  "effects": [
    {"kind": "DAMAGE", "target": "EXPLICIT_ENEMY_CHARACTER", "amount": 3},
    {"kind": "DAMAGE", "target": "RANDOM_DISTINCT_ENEMY_CHARACTERS", "amount": 2,
     "random_count": 2, "exclude_previous_target": true,
     "evidence_constraint": "ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED"}
  ]
}
```

New typed surface (all append-only, defaults inert, so every existing declaration is unchanged):

| Where | Addition |
|---|---|
| `TargetSelector` | `RandomDistinctEnemyCharacters`, `RandomDistinctEnemyMinions` (appended after `FriendlyWeapon`) |
| `EffectStep` | `int random_count=0`, `bool exclude_previous_target=false`, `std::optional<EvidenceConstraint> evidence_constraint` |
| `EvidenceConstraint` | `ArcaneBarrageTargetingContractUnverified` (appended) |
| pybind | selector values, a new `EvidenceConstraint` enum, and the three `EffectStep` fields |
| Python | `_parse_effect_steps` (hoisted from a closure, otherwise a pure move) copies the new fields **strictly**: `random_count` must be a real `int` (not `bool`/`float`/`str`), `exclude_previous_target` a real `bool`, `evidence_constraint` an exact canonical ID present in `EVIDENCE_CONSTRAINT_IDS` and in the native enum |

Two interpretation notes, for the reviewer:

1. **Two selector values instead of one.** The task asked to "append one suitable TargetSelector". Barrage needs the hero in its pool and the
   required synthetic control is minions-only, and the audit says the selector "decides hero inclusion, never inferred". A single value would need a
   third pool field, so the pool lives in the selector: `…_CHARACTERS` / `…_MINIONS`. This is a declaration-shape choice only; it changes no rules.
2. **The constraint is a declared property of the step, not engine knowledge of a card.** The task requires the constraint to appear when TIME_855
   executes its extras instruction and *not* for the synthetic fixture or any unrelated random-distinct consumer, with no card-ID branch. The only
   mechanism satisfying all three is for the declaration to name the constraint and the generic routine to record whatever the executing step names.
   Catalog validation allowlists exactly one value for this operation, so a future consumer cannot silently attach an unrelated constraint.

## 3. Selector contract (`resolve_random_distinct_damage`, `engine.cpp`)

Catalog validation (fails closed at load with `std::invalid_argument`, one reason per case, 20 rejected shapes plus 7 accepted controls in tests):

- `random_count`, `exclude_previous_target`, `evidence_constraint` are valid **only** on a `RandomDistinct*` selector; ordinary selectors reject them.
- A `RandomDistinct*` selector requires a **Damage** step on a **spell** with `amount > 0` and no Lifesteal; `random_count` within 1..3.
- `exclude_previous_target` requires an **earlier explicit-target Damage step** in the same effect list.
- `evidence_constraint` must be `ArcaneBarrageTargetingContractUnverified`; at most one random-distinct step per card; not valid in Choose One modes.

Runtime, in order:

1. Record the step's declared constraint (reaching the instruction is what carries the debt, so this happens before the pool is built).
2. Candidate snapshot, **stable order**: enemy hero (only for the `Characters` selector), then enemy board left to right. Remove minions with `health <= 0`
   and, when declared, the explicit target **by entity id**. Stealth, Immune and Divine Shield stay candidates; nothing is filtered by implementation support.
3. `k = min(random_count, n)`; sample as below.
4. If `k == 0`: emit nothing, open no group, evaluate no amount. Otherwise one `evaluate_spell_damage` (`CURRENT_AT_STEP`, never `MISSILE_TOTAL`) and
   one `ApplyAll` group for all selected targets, no inner stabilize.
5. Group order: all selected minions → existing `MinionEntrySequence`; a hero among them → existing `ScalarOnly` (its existing guard rejects a generation
   consumer beside it before any extras mutation).

## 4. Exact partial Fisher-Yates

```
candidates = [hero?] + enemy board left-to-right (health > 0), explicit target removed   # n = len
for i in 0 .. min(k, n) - 1:
    j = i + bounded_random(n - i)        # uniform in [i, n-1]; one u64 draw (rejection only if value < (2^64-b) mod b)
    swap(candidates[i], candidates[j])
    selected.append(candidates[i])       # selection order
```

Simulator-owned `std::mt19937_64`; deliberately not Blizzard's PRNG. No reroll, no retry after an unsupported outcome, no support filtering.

| Candidates n | Sampler draws | Extra packets | Constraint recorded | Branch |
|---|---|---|---|---|
| 0 | **0** | 0 (no group, no amount evaluation) | **yes** | valid |
| 1 | 1 | 1 | yes | valid |
| ≥ 2 | 2 | 2 (distinct) | yes | valid |

The constraint is recorded in all three rows, never poisons the branch, is retained by clones, and blocks canonical admission (§8). It is **absent** when
Barrage is only in a deck/hand, when an unrelated spell is cast, when Barrage is countered, when the primary's reaction fails before the extras instruction
(unsupported branch), and for the synthetic and other unrelated random-distinct consumers.

## 5. Reference topology T2 and remaining uncertainty

T2: the explicit primary uses the ordinary single-packet path and completes with its currently admitted reactions; only then are the extras selected and
damaged as one group. Death and Reborn stay at the outer spell boundary.

Not proven, and deliberately not made an EvidenceConstraint (per the accepted audit): whether Blizzard scripts Barrage as T1, T2 or T3. For the two admitted
reaction families the topologies give the same successful outcomes and distributions. They can still differ in **failure-path/diagnostic** behavior: where
each generation draw sits relative to the selection draws (same seed → different generated card), where an unsupported reaction stops the cast, and trace
order. G2 (client experiment) is required before a board-changing or damage-dealing `ReactionKind` is admitted.

One nuance worth a reviewer's attention. The task says both "selection order is event order" and "reuse the current reviewed minion-entry event ordering".
These coincide except for two generation consumers among minion-only extras: the sampler records selection order (trace row `selected=`), while the
existing `MinionEntrySequence` dispatches reactions in entry-sequence order. I followed the explicit instruction to reuse the reviewed ordering. The two
generation draws are independent and exchangeable, so the distribution of what each consumer generates is identical; only which draw goes to which
consumer differs. This is asserted explicitly (BB11, 16 seeds) rather than left implicit.

## 6. ReactionKind tripwire (BB16)

`TestAccess::barrage_topology_review` in `native_tests.cpp` is a deliberately **exhaustive `switch` with no `default`**, promoted to an error for the test
translation unit (`#pragma warning(error:4062)` on MSVC, `-Wswitch` as error on Clang/GCC). Adding a `ReactionKind` member stops the native test target from
building until the Arcane Barrage topology is reviewed for it. Production code is untouched; no enum count is assumed anywhere in runtime behavior.

Verified by experiment on MSVC: temporarily adding `TripwireProbeV1` to `ReactionKind` made the test TU fail with
`error C4062: enumerator 'TripwireProbeV1' in switch of enum 'ReactionKind' is not handled`; the header was restored byte-for-byte (hash compared).
**Not verified locally:** the GCC/Clang half (no Linux toolchain available on this machine). Ubuntu CI compiles it, but a probe member was not pushed to
confirm that GCC actually errors; treat that half as compile-checked only.

## 7. BB01–BB19 disposition

All native tests are in `experiments/manaengine/tests/arcane_barrage_tests.hpp` (run alone with `manaengine_tests --arcane-barrage`); BB18 and parts of
BB14/BB19 are also in `experiments/manaengine/tests/test_adapter.py`.

| ID | Disposition | Where / how it is asserted |
|---|---|---|
| BB01 | covered | `test_barrage_candidate_counts_targets_and_constraint`: M takes 3 once, hero takes the single 2, 1 draw, constraint present |
| BB02 | covered | same: hero 3, lone minion 2, no repeat, 1 draw |
| BB03 | covered | same: hero 3 only, no extra packet, 0 draws, one `DAMAGE_BOUNDARY`, one group, constraint present, branch valid |
| BB04 | covered | 240-seed sweep, hero + 4 minions: exactly two distinct extras, never the primary, hero and every other minion reached, 2 draws |
| BB05 | covered | `test_barrage_distribution_and_rng_replay`: 3000 seeds each for n=3 and n=6; every pair, every marginal (2/n) and the first pick within 6σ. Seeds are fixed and `mt19937_64`/`bounded_random` are deterministic, so the check cannot flake |
| BB06 | covered | `test_barrage_spell_damage_and_prevention`: +2 Spell Damage → 5/4/4, two `CURRENT_AT_STEP` evaluations, no `MISSILE_TOTAL` |
| BB07 | covered | 64-seed sweep, paired with an unshielded control: shield pops without damage, Immune keeps health, no event for either, identical selection, identical draw count |
| BB08 | covered | `test_barrage_mortality_and_outer_boundary`: lethal primary on Murmy; excluded by identity; new Reborn identity at the outer boundary; never selected or damaged |
| BB09 | covered | lethal Deathrattle extra and lethal Reborn extra: `DEATH` after every packet, deathrattle after `DEATH`, no inner drain |
| BB10 | covered, **primitive level** | selector primitive called directly with a pre-mortal enemy; labelled in the test as contract coverage, not a reachable Barrage position |
| BB11 | covered | `test_barrage_reactions_and_clone_determinism`: TakesDamage consumer as primary (generation draw precedes selection draws; reaction before selection), as only extra, as two extras; clone gives identical trace, RNG and card |
| BB12 | covered | `test_barrage_fail_closed_paths`: scalar guard fires before any extras mutation; primary-step mutation retained; first reason kept; exactly the 2 selection draws; poisoned surface intact. Not described as "before mutation" |
| BB13 | covered | Raincaller gains Attack once; its reaction precedes selection; extras still sampled; 3 packets counted |
| BB14 | covered | unresolved Fire pool as primary (extras never reached, no constraint) and as the only extra (1 draw, mutations retained, first reason kept, no reroll) |
| BB15 | covered | 80-seed independent replay over raw `bounded_random` draws on a clone predicts selection, order and RNG position; plus a hand-derived seed-7 golden |
| BB16 | covered | compile-time tripwire (§6) plus runtime coverage check |
| BB17 | covered | present for n = 0,1,2,3 (valid, cloned, canonical ID); absent for deck/hand only, unrelated spell, end turn, countered Barrage, failed primary reaction, both synthetic consumers. Admission rejection is in the adapter test |
| BB18 | covered | native: generic targeted `PlayCard` on enemy characters only. Adapter: real Mage session, generic legal actions, constraint crosses native → Python → `GameState`, round-trips through serialization, blocks `require_training_admission` and `require_canonical_training_admission` on its own, no policy feature, schema constants unchanged, unsupported branch normalizes to `UnsupportedSimulationError` |
| BB19 | covered | k=3 `EnemyMinions` control (n = 0,1,2,3,5) and a hero-pool control: same routine, no constraint, no promotion; a Python source scan asserts no engine source names `TIME_855` or the five unpromoted cards |

**Mutation sanity (not part of the suite, run once and discarded):** ten deliberate faults in the engine routine were each killed by the Barrage family
and none survived: no exclusion, wrong sampler bound, constraint skipped at n=0, mortal minions kept, Spell Damage ignored, extras applied one packet at a
time, hero dropped from the pool, constraint raised for every consumer, remove-from-list selection instead of swap, and hero extras forced onto minion order.

## 8. Test, build and artifact results

| Check | Before | After |
|---|---|---|
| Native full suite (`manaengine_tests`) | 67 groups, 1783 assertions | **77 groups, 1925 assertions** (+10 groups, +142 assertions) |
| `--damage-group` family | 10 groups, 173 assertions | 10 groups, 173 assertions (unchanged) |
| `--arcane-barrage` family | n/a | 10 groups, 142 assertions |
| CTest | 1/1 | 1/1 passed |
| `test_adapter.py` | 42 | **48** (+6) |
| ManaEngine-workflow pytest set (adapter + `test_pipeline.py` + `test_policy_action_semantics.py`) | 69 (adapter 42 measured; the other two files, 27 tests, are untouched by this change) | **75** |
| Full `python -m pytest -q` (`testpaths = tests`) | 92 | 92 (the new Python tests live under `experiments/`, which that run does not collect) |
| Ruff (`src tests scripts`) | pass | pass |
| Card-identity branch guard | n/a | PASS (201 reviewed AST exceptions; Python generators only) |
| Generated artifacts | n/a | 36 pinned outputs reproduced on the second run |
| `git diff --check` | clean | clean |

Local build: MSVC 19.44 Release + Ninja, a fresh configure into an ignored build directory. No new compiler warnings; the three pre-existing `C4456`
shadowing warnings in `engine.cpp` are unchanged. The submodule `vendor/RosettaStone` was populated from the main checkout at its pinned commit
`f34da0d` to run the generator checks (no network, no change to the pin).

Generated artifacts changed: exactly two files, one line each — `data/cards/standard_registry_20261001_enUS.json` and
`reports/standard_registry_20261001/summary.json`.

`observation_source_sha256`: `0d1b2dfcea73b7b678a9f035126893194f0653097b15e15d20a398e0015281e1` → `db7ffe601f46414d0a288ea155163b41295200ab02aa3aae25d9a34abf20a046`.
This is a **source-identity change only**: the canonical domain evidence-ID set (`src/manamind/domain/game_state.py`) gained one entry. Root count, known
non-root nodes, unresolved pools, registration counts and admission status in the regenerated report are unchanged. It is not card coverage growth.

## 9. Status dimensions for TIME_855 (independent)

| Dimension | State |
|---|---|
| Metadata known | yes (pinned snapshot, dbfId 119528) |
| Declaration implemented | yes (`card_abilities.json`, typed, allowlisted) |
| Runtime executable | yes (native session and Python adapter session) |
| Rules verified | **no** — `BOUNDED_WITH_EVIDENCE_DEBT`; no current-client evidence exists. Passing tests do not change this |
| Evidence constrained | yes — `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED` (plus any existing constraints a branch accrues) |
| Dependencies closed | not claimed; no manual promotion; generated registry content unchanged apart from the hash |
| Canonical training eligible | **no** |

Global deltas: canonical dependency closure Δ 0; training eligibility Δ 0; Fire pool unchanged; Whelp unchanged; no other real card declared
(`FIR_909`, `TIME_441`, `CATA_498`, `CORE_CATA_007`, `TIME_611` stay undeclared and unsupported). Policy action schema stays 3 and state encoding schema
stays 16; no TIME_855-specific policy feature exists.

## 10. Declaration / catalog / bindings audit

Every path touched by the new fields was checked: C++ structs; catalog validation; pybind `EffectStep` and enum exposure; Python declaration → native
conversion (strict, round-trip asserted field by field against the raw JSON); `EVIDENCE_CONSTRAINT_IDS` ↔ native enum parity (one generic test, so a
future constraint registered on only one side fails); the native canonical-ID switch; test fixtures. **Fingerprints:** nothing in the pinned
registry fingerprints hashes `experiments/manaengine` declarations or native sources (`engine_source_sha256`, `rules_source_sha256` and
`scenario_source_sha256` are RosettaStone-route inputs and did not change); only `observation_source_sha256` moved, because it hashes `src/manamind/domain`.
**Generated card definitions:** the RosettaStone `effect_composition` generator route does not declare TIME_855 and was not touched.

## 11. Effort and correction cycles (per the package process)

One session. Correction cycles: 5 defects found in my own draft test file by review before it was first compiled (a nonexistent helper, a
`none_of` over two different temporaries, junk statements, and ordering predicates that would pass when a trace row was absent); 1 compile error (a private
enum, fixed with a `TestAccess` alias); 1 wrong assertion (damage-event sequence numbering); 1 adapter test that did not raise, which exposed the
unrelated cache bug below. Builds: 1 baseline, 6 incremental, 10 mutation rebuilds, 1 tripwire probe.

## 12. Remaining evidence debt, blockers and observations

- **G1** (one game: opponent with a single minion + hero, Barrage on the minion) removes `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED`.
- **G2** (Imp Gang Boss topology experiment) and the conditional-Spell-Damage experiment are required before any board-changing or damage-dealing
  `ReactionKind` is admitted; the tripwire enforces the review.
- Existing constraints unchanged: `MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED`, `REBORN_MULTI_DEATH_SLOT_UNVERIFIED`, Dark Gift constraints.
- Canonical training remains blocked by the global admission gate; Fire pool and Whelp are untouched; a generation consumer beside a hero extra stays
  guarded (optional later `DamageEventOrder` change, explicitly out of scope).
- **Unrelated latent bug found, not fixed here:** in `_definition_rows` the cache key `key` is overwritten by the later `for key, value in spec.items()`
  loop, so the cache is stored under a card-field name and never hits; every call rebuilds all rows. Behavior is unaffected today, but fixing it will
  expose tests that mutate returned rows in place. Flagged as a separate follow-up task.

## 13. Hosted CI

Both workflows ran on implementation commit `826499e` and concluded `success`; every job and every step below was read from the GitHub Actions jobs API
(not inferred).

**Source and generated artifact checks** — run 37300984479, jobs `source (windows-latest)` and `source (ubuntu-latest)`, both `success`. Steps, identical on
both: checkout, setup-python, `pip install -e ".[dev,replays]"`, **Python correctness diagnostics (Ruff)**, **Generator card-identity guard**,
**`scripts/check_generated_artifacts.py`** (generated artifact reproduction), **`git diff --exit-code`** (cleanliness), **`python -m pytest -q`** (full pytest) —
all `success`.

**ManaEngine experimental** — run 37300984529, jobs `windows-latest / ManaEngine` and `ubuntu-latest / ManaEngine`, both `success`. Windows: MSVC configure,
**Release build**, **CTest**, **Python adapter and policy schema tests** `success` (Unix configure skipped). Ubuntu: Unix configure, **Release build**,
**CTest**, **Python adapter and policy schema tests** `success` (MSVC steps skipped).

What this does and does not add: the Ubuntu **Release build** compiling the test target is the first compile of the GCC/Clang branch of the `ReactionKind`
tripwire pragmas, so that half is now compile-checked on a second toolchain; it has still not been shown to *trip* on GCC. Hosted numeric test counts are
not claimed: the step conclusions are readable through the public API but the logs that contain counts are not.

The report commit that follows adds only this file under `reports/`; the ManaEngine workflow's path filter does not cover it, so only the Source workflow
runs again for it.

## 14. Verdict

**ARCANE_BARRAGE_BOUNDED_IMPLEMENTATION_ACCEPTED**

Basis: the accepted contract was implemented without redesign (no DamageGroup, scheduler, lifecycle, general random-effects framework, card-ID branch or
schema change were needed); BB01–BB19 are covered; local and hosted gates pass on Windows and Ubuntu; generated outputs reproduce with only the expected
source-identity hash change. "Accepted" describes the implementation against the audited contract. It does **not** mean TIME_855 is rules-verified: it remains
`BOUNDED_WITH_EVIDENCE_DEBT`, evidence constrained, and not canonical-training eligible.

Stopped here as instructed: no Fire pool, Whelp, other random-distinct cards, self-play, training or search work was started.
