# Phase 4H.3 — Sonnet remediation of DamageGroupLocalV1

## Verdict

**DAMAGE_GROUP_LOCAL_V1_REMEDIATED.** No architecture change: mutation barrier, outer death boundary, frame stack,
`DirectSpell` accounting, Reborn contract, Fire pool, Arcane Barrage, training eligibility and registry/closure are
untouched. No Fire/Whelp work was started.

- Starting HEAD: `6cd3c83b612759f77b22c242c9bc7629e288aa90` (production tree identical to `e77d985`).
- Implementation commit: `d5ed84e1efd15a6a576ca6f38ae6682a92291006` (pushed to `codex/manaengine-first-deck` manually by the
  user after the push permission was denied to the agent; the pushed tree equals the locally validated tree, checked with
  `git diff d5ed84e` returning no difference).
- Final HEAD: the documentation commit that adds this file; its SHA cannot appear in itself.
- Source of required fixes: the Phase 4H.2 audit.

## Failure-funnel policy (public boundary)

- `apply_action()` calls `legal_actions()` first and rejects an illegal action with `std::invalid_argument` **before any
  mutation**; the session stays valid and usable.
- Once `execute_action()` starts, **any** escaping exception (`UnsupportedSimulationError`, other `std::exception`, unknown)
  sets `state_.unsupported` when still empty (`action failed after mutation: <original reason>`), clears
  `damage_frames`, and rethrows the original exception. A reason already set by `reject_unsupported` is preserved.
  Consumed RNG and diagnostic mutations are kept, nothing is rerolled or rolled back.
- Bare throws reachable after mutation (about 17 sites in `resolve_spell`/`resolve_effects`/`resolve_play`/Battlecry
  handlers, plus the ChooseCard `pending_choice` reset) are now covered by this one funnel instead of being converted one by
  one.
- Poisoned-session policy:

| Accessor | Poisoned session |
|---|---|
| `legal_actions`, `clone`, `observation`, `result`, `is_complete`, `needs_choice`, `choice_options`, `begin_prototype_choice`, `apply_action` | throw `UnsupportedSimulationError` (Python adapter: `UnsupportedSimulationError`) |
| `is_valid`, `unsupported_outcome`, `evidence_constraints`, `diagnostic_trace`, `seed` | available, explicit diagnostics only |

Principle: a poisoned session is never a successful simulator state, terminal episode, training sample or branch
continuation. Before: `result()`/`is_complete()` returned `nullopt`/false for a poisoned session whose hero was already dead.

## MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED

- Native `EvidenceConstraint::MortalQueuedEotSourceUnverified`, canonical ID `MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED`,
  registered in `evidence_constraint_id` and `EVIDENCE_CONSTRAINT_IDS` (`src/manamind/domain/game_state.py`).
- Raised whenever a queued EOT source (`CATA_488`, `CATA_475`, `CATA_999`) resolves with `health <= 0`.
- The phase-model behavior is kept; the branch stays valid. The debt blocks canonical training admission through the
  existing `require_canonical_training_admission`. It is **not** promoted as rules-verified until replay/client evidence exists.
- Winner-flip regressions: `CATA_999` (enemy hero 4 to 0) and `CATA_475` (enemy hero 2 to 0), each with a mortal case
  (PLAYER1_WIN plus debt; the pre-4H.1 engine skipped these sources) and a healthy control (same result, no debt). The
  existing mortal-Vulcanos test additionally asserts the debt, and the two-healthy-Vulcanos test asserts none.

## Raincaller / reaction guards

Reasoning: generation (`SelfTakesDamageV1`) consumes RNG and fills a hand; the first-spell-damage attack gain does neither,
so the two never need an ordering contract. The scalar-only guard now rejects only generation reactions.

| Case | Before 4H.3 | Now |
|---|---|---|
| Hellfire (hero area) + Raincaller | rejected | **supported** (attack gain once, 4 counted packets) |
| Enemy-character Shatter fragment + Raincaller | rejected | **supported** |
| Explosive Trap + Raincaller on the Secret side | rejected | **supported** |
| Explosive Runes + Raincaller, with and without Shield | rejected | **supported** (restored `attack==3` control; excess still from pre-hit Health) |
| One generation consumer + Raincaller in a minion area or single packet | rejected after mutation | **supported** (both reactions) |
| Generation consumer inside hero area / combat / compound Secret (with or without Raincaller) | rejected before mutation | still guarded (generation ordering unreviewed) |
| One entity that is both consumer and spell-damage watcher | rejected | still guarded (narrowest remaining guard) |

Two earlier negative controls (DG24 mixed order, DG25 Runes+Raincaller) were converted to positive controls because
the audit showed the rejection was unnecessary; every other negative control is unchanged.

## F1–F10 final disposition

| # | Finding | Final |
|---|---|---|
| F1 | mortal queued EOT source | **FIXED as bounded debt**: behavior kept, `MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED`, winner-flip tests; still not rules-verified |
| F2 | poison/failure boundary | **FIXED**: public-boundary funnel, poisoned result/is_complete/choice accessors refused, native and Python tests |
| F3 | frame stack | **OBSOLETE** (no change; audit found no lifetime defect) |
| F4 | mortality policy | **FIXED as documentation**: [MORTALITY_POLICY.md](MORTALITY_POLICY.md); Explosive Trap's `health>0` filter noted, not changed |
| F5 | conditional Spell Damage guard | **STILL_VALID (conservative, documented)**: undamaged conditional provider targeted by a *spell* area still fails closed; static, Effect and Sleet cases unaffected. Not in this remediation's scope |
| F6 | omitted consumers | **FIXED as documentation**: matrix update and policy notes for `JAIL_805`, `JAIL_805t`, `CORE_EX1_129`, `CATA_999`, `CATA_475`; behavior was already preserved |
| F7 | caller completeness | **STILL_VALID (MINOR)**: audit complete, no mechanical rename; unchanged by design |
| F8 | Secrets | **FIXED** earlier; Runes excess contract intact, Runes+Raincaller coverage restored |
| F9 | entry-order events | **STILL_VALID (MINOR)**: now pinned by a cross-side RNG-order test; an evidence constraint is deferred to Fire pool admission |
| F10 | Raincaller guards | **FIXED**: table above |

## Tests

| | Before (6cd3c83) | After (d5ed84e) |
|---|---|---|
| Native `--damage-group` | 8 groups / 100 assertions | **10 groups / 160 assertions** |
| Native full | 65 groups / 1707 assertions | **67 groups / 1770 assertions** |
| CTest | 1/1 | 1/1 |
| Python adapter + pipeline + policy | 66 passed | **68 passed** |
| Full pytest | 92 passed | **92 passed** |

New or restored native coverage: T01 (hero already lethal, reaction failure), T02 (Fire-pool failure), T03 (bare throw
after area mutation, stable diagnostic), RNG preserved across a later bare throw, illegal input not poisoning, full poisoned
surface (observation/clone/legal_actions/result/is_complete/needs_choice/choice_options/choice start/apply), winner flips and
debt, Raincaller positives and remaining negatives, same-entity guard, entry-order generation with independently replayed
RNG draws, restored `effective_cost==9` and Runes `attack==3` assertions. The shared `check()` helper now takes a
`std::string` so dynamic labels work. Python adds the registry/admission test and a real-session poisoned-accessor test.

Mutation checks: removing the funnel, removing the debt, and restoring the Raincaller guard each fail a specific new
assertion (verified locally, restored afterwards).

## Local validation (before the push)

Native MSVC (focused, full), CMake/Ninja Release build with CTest 1/1, adapter and policy tests 68, full pytest 92, Ruff
(`src tests scripts experiments/manaengine/tests`), generic card-branch guard (201 reviewed exceptions),
`check_generated_artifacts.py` (36 pinned outputs reproduced after regeneration), `git diff --check`.

## Schema, registry, closure, training deltas

- Observation/encoder schema: unchanged (16). The evidence ID is session-level and not an encoder feature.
- **`observation_source_sha256` changed** (`9ec9e5a1...` to `0d1b2dfc...`) in
  `data/cards/standard_registry_20261001_enUS.json` and `reports/standard_registry_20261001/summary.json`, one line each,
  because the registry's observation fingerprint hashes `src/manamind/domain`, where the new ID is registered. The 4H.1
  statement that canonical registry bytes were unchanged does not hold for this commit; the regenerated files are committed.
- Registry statuses, roots, dynamic closures, Fire pool membership and training eligibility: **delta 0**. Training admission
  remains blocked globally and now also by the new debt where it applies.
- Arcane Barrage, Fire pool, Whelp, training and search: untouched.

## Hosted CI (implementation `d5ed84e`)

Run records: [HOSTED_ACCEPTANCE_REMEDIATION.json](HOSTED_ACCEPTANCE_REMEDIATION.json). All four jobs completed `success`
with no step skipped other than the platform-inapplicable configure step.

| Job | Evidence |
|---|---|
| [Source](https://github.com/MaksimOrekhov/manamind/actions/runs/37290734716) Windows | Ruff, card-identity guard, `check_generated_artifacts.py`, `git diff --exit-code`, `python -m pytest -q`: all success |
| Source Ubuntu | same five steps: all success |
| [ManaEngine](https://github.com/MaksimOrekhov/manamind/actions/runs/37290734711) Windows | MSVC configure, Release build, **CTest**, **Python adapter and policy schema tests**: success |
| ManaEngine Ubuntu | Unix configure, Release build, **CTest**, **Python adapter and policy schema tests**: success |

Limit: GitHub withholds job logs without authentication (HTTP 403), so the executed test counts could not be read from the
hosted logs. The pytest and CTest steps ran and succeeded; they execute the same commands that produced 92, 68 and 1/1
locally. This record does not claim hosted counts.

## Remaining limits

The mortal-source behavior and event ordering rest on the independent research rulebook, not on a client replay. Stronger
generation ordering for hero areas, combat and compound Secrets, and the entry-order evidence constraint, belong to Fire pool
admission and were not started.
