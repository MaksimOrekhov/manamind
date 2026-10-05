# Phase 4K.1 — SimulationAttempt adapter boundary

Starting main SHA: `7268ff6e173c330e6456d4790296cf57916e43f1`

Implementation commit SHA: pending implementation commit.

Final publication revision: pending hosted checks and main promotion.

Verdict at this record revision: `PHASE_4K1_PARTIAL` (local acceptance passed;
hosted acceptance pending).

## Scope and implementation

Implemented the Python-only boundary in
[`simulation.py`](../../src/manamind/integrations/manaengine/simulation.py).
The optional implementation-design report was absent; the user's self-contained
Phase 4K.1 contract was used. Work occurred in a new clean isolated worktree;
the dirty primary checkout was not edited. RosettaStone was initialized only
in this new worktree at its existing gitlink for source checks. Its separate
administrative directory is under the task worktree metadata; no submodule
source or gitlink changes remain.

Production edits are restricted to `simulation.py`, two private helpers and
the preserved `apply_action` wrapper in `engine.py`, and exports in
`__init__.py`. Also added two test files, extended the existing ManaEngine
pytest invocation, and updated the three allowed status documents. No native
source, schema, encoder, policy, manifest, registry, held-card rules or training
gate changes were made. Existing `test_adapter.py` was not edited.

Public exports: `SimulationOutcome`, `AttemptReason`, `AttemptDiagnostics`,
`InvalidParentSession`, `SimulationAttempt`, `acting_seat`, `attempt_action`.

Signature: `attempt_action(parent, action, *, perspective=None,
retain_child=True)`.

## Outcome/reason contract

| Outcome | Reasons | State/child | Future fallback eligible |
|---|---|---|---|
| COMPLETED | none | State required; optional child | false |
| UNSIMULATABLE | NATIVE_UNSUPPORTED, ENUMERATION_UNAVAILABLE | neither | true |
| ILLEGAL | ILLEGAL_MALFORMED, ILLEGAL_NOT_LEGAL | neither | false |
| ENGINE_DEFECT | NATIVE_EXCEPTION_NORMALIZED, NATIVE_CATCH_ALL, ATTEMPT_INVARIANT_VIOLATED, CLONE_FAILED, EXPORT_FAILED, ADAPTER_FAILURE | neither | false |

All public result/diagnostic dataclasses are frozen with slots. Child is excluded
from repr/equality. Action snapshots retain only six scalar execution fields;
extra caller metadata is discarded. Integers reject bool, float and numeric
strings. Defaults match native `execution_equal`: -1 for indices/entities and
0 for `choose_one`. Native canonical legality dictionaries are submitted;
caller dictionaries never reach native apply through this API.

Invalid parent raises `InvalidParentSession`; invalid explicit perspective
raises `ValueError`. MemoryError/KeyboardInterrupt/SystemExit propagate.
Failure diagnostics contain only exception/unsupported strings, immutable
evidence strings and a trace tail of at most 32 rows. Diagnostic accessor
failures are best-effort snapshots and cannot expose an object handle.

## Perspective and parent/child guarantees

Default perspective resolves the acting parent seat once using a visible
PLAYER1 observation. Explicit perspective is PLAYER1 or PLAYER2. Completion
exports `child.observation(root_seat)`, ignoring `_apply_raw`'s ACTIVE result.
After PLAYER1 END_TURN, SELF remains PLAYER1 and active_player becomes OPPONENT.
Public `apply_action` retains its existing post-action ACTIVE-seat behavior.

Legality is checked before cloning/application. Execution happens on a deep
native clone. Parent observations, legal actions, validity, evidence, trace and
RNG progression are preserved. Only a valid safely exported child can complete;
return-with-poison, export failure and evidence mismatch fail closed. Successful
children can be used as simulator parents; `retain_child=False` discards the
handle without reexecuting the action. Failed children never escape.

## Inferred Fire paths

The real seed scan is bounded to 128 seeds and discovers both a completed
supported Fire path and an unsupported sampled Fire outcome. Fixture hand
space is obtained by ordinary supported card plays, not by pool changes.
Both Plumes may sample independently; a rejected sample is not rerolled.

A supported inferred outcome is COMPLETED, retains
FIRE_POOL_MEMBERSHIP_INFERRED in state/result/child evidence, and is not fallback
eligible. An unsupported sample is UNSIMULATABLE/NATIVE_UNSUPPORTED with no
state, child or transition evidence. Failure evidence and sampled identity
remain in diagnostics. Repeated attempts from the same parent RNG point agree;
the original parent stays valid. Training admission remains blocked.

## SA01–SA25 disposition

All rows passed locally. Source cases use private fake surfaces without loading
the native extension; native cases use the freshly built current checkout.

| Case | Coverage |
|---|---|
| SA01 | ordinary native/fake supported completion |
| SA02 | parent snapshots plus clone/RNG deterministic controls |
| SA03 | second attempt using retained native/fake child |
| SA04 | fixed root seat across native/fake END_TURN |
| SA05 | completed real inferred Plume result and evidence |
| SA06 | real/fake unsupported Fire, no state/child |
| SA07 | failed clone does not poison native/fake parent |
| SA08 | real sampled identity and immutable diagnostic provenance |
| SA09 | malformed shape and all five strict integer fields |
| SA10 | invalid target, stale index, impossible choice and unknown type |
| SA11 | real synthetic post-mutation std::exception plus fake exact catch-all reasons |
| SA12 | failed results contain no session handle |
| SA13 | parent/child/result evidence independence |
| SA14 | same native/fake RNG root produces deterministic attempt result |
| SA15 | existing apply_action ACTIVE behavior and unchanged test_adapter.py |
| SA16 | fake enumeration unavailable and real unsupported opponent next draw |
| SA17 | canonical dictionaries/defaults, all six native action types, choose_one, strict extras |
| SA18 | complete native/fake game rejects action before cloning |
| SA19 | state-only result does not rerun action |
| SA20 | fake invalid child return, export failure and evidence mismatch |
| SA21 | fake clone failure and clone-alias rejection |
| SA22 | MemoryError/KeyboardInterrupt/SystemExit propagate across four phases |
| SA23 | explicit PLAYER2 and invalid perspective/parent |
| SA24 | player-visible native state excludes opponent hidden identities; child repr/equality isolation |
| SA25 | centralized dataclass failures and immutable diagnostic fields |

## Local validation

- Source-only contract file: 80 passed.
- Real native attempt file: 9 passed.
- Full `pytest tests`: 172 passed.
- Required combined native adapter/pipeline/policy/contract invocation: 172 passed.
- CTest: 1/1 passed; existing native suite reported 78 groups / 2153 assertions.
- Ruff, generator identity guard, `git diff --check`: passed.
- Generated artifact check: all 36 pinned outputs reproduced, unique ownership;
  no generated-file or RosettaStone diff remained.

The initial fake observation fixture lacked self hand_size and was corrected.
The initial native pass-only fixture hit the existing pre-RNG full-hand guard;
it was corrected to clear filler cards through ordinary legal plays. These
were test-fixture corrections, not production rules fixes. Native configuration
used VsDevCmd after Developer PowerShell could not locate the installed tools.
No native source changes were needed.

## Hosted validation

Pending implementation branch publication. Required Source and ManaEngine
Windows/Ubuntu jobs must pass before normal fast-forward promotion of main.

## Known limitations and stop boundary

- ENGINE_DEFECT classification is a Python heuristic with incomplete recall
  until Phase 4K.1b. Some native reject/direct-throw paths may still emit a true
  defect as ordinary unsupported behavior.
- A full-information clone and even its attempt outcome may depend on hidden
  deck/RNG state; the unsupported opponent next-draw case demonstrates this.
- Chance execution returns one sampled outcome, not an expected value.
- No live-root use, fallback scoring, search or training consumer is added.
- Canonical training eligibility and existing evidence/registry gates are unchanged.

Stop after hosted acceptance, report publication, main promotion and removal
of the remote temporary task branch. No Phase 4K.1b/1c/2, new cards, held-card
semantics, Q fallback, training, self-play or live-state import is authorized.
