# Partial Simulator Architecture

This document is the durable architecture contract for simulator gaps,
unknown cards and states, bounded inferred rules, and the future connection
between real matches and rule discovery. It distinguishes what works in the
current repository from accepted direction and unimplemented plans. It does
not authorize training or implement a new runtime path.

Related current contracts: [ManaEngine admission](MANAENGINE_ADMISSION.md),
[Standard registry](STANDARD_REGISTRY.md), [real match data](REAL_MATCH_DATA.md)
and [the ManaEngine guide](../experiments/manaengine/README.md).

## 1. Purpose

ManaMind must be able to improve while simulator coverage is incomplete. A
new or unsupported card, a rare unresolved interaction, an inferred pool
membership, or an out-of-distribution position does not require fabricating a
transition. At the same time, an unsupported simulator action need not be
permanently un-recommendable: a higher layer may eventually estimate its
action value from a valid visible state and legal action.

The simulator remains the authority for transitions it claims to execute.
Canonical training remains stricter than bounded runtime recommendation and
must never learn from poisoned or fabricated afterstates.

## 2. Architectural principles

1. **ManaEngine is the primary forward simulator development backend.** Its
   internal state is authoritative during simulation; its adapter exports a
   player-visible `GameState`. The engine is actively developed with bounded
   correctness and admission. It is not production-complete.
2. **RosettaStone is retained** as a reference and regression/parity backend,
   historical implementation source, and evidence/tooling dependency where
   still explicitly consumed. New simulator rules normally belong in
   ManaEngine unless a task requests RosettaStone.
3. **The engine is strict.** It must not guess a transition merely to continue
   search. Approximation and resilience to unsupported actions belong above
   the simulator.
4. **Status dimensions stay separate.** Mechanical execution, rules/evidence
   basis, dependency closure, and canonical training eligibility are not one
   confidence score.
5. **Information boundaries stay explicit.** Player-visible input excludes
   hidden opponent hand identities, deck order, unrevealed secrets, future RNG
   and unobserved generated choices.
6. **Runtime support does not redefine game rules.** Implementation coverage
   never shrinks a real dynamic pool or changes its probabilities.

## 3. Implemented now, accepted target, and future work

| Status | What it means here |
|---|---|
| **IMPLEMENTED** | A behavior exists in the current source and can be used only within its tested/support boundary. |
| **ACCEPTED TARGET** | An architectural direction approved for future work; it is not an API or implementation claim. |
| **FUTURE / NOT IMPLEMENTED** | A possible subsystem or experiment that must not be described as available today. |

### IMPLEMENTED

- ManaEngine has an isolated C++ state and exports observations and legal
  actions through a Python adapter. `GameState` remains the player-visible
  domain representation, not the engine's mutable state.
- ManaEngine sessions are created from two decks and game setup. The current
  adapter admits Mage mirror sessions because only that hero power is
  implemented. There is no general importer from an arbitrary live
  `GameState`, `PlayerObservation` or Power.log position into engine state.
- The engine executes only its supported, reviewed subset. Candidate
  generation pools fail closed; an unsupported sampled outcome invalidates
  that branch after sampling and is not rerolled or replaced.
- An explicitly bounded Fire pool has membership status
  `REVIEWED_INFERRED`. Its 33 pinned candidates are permitted for runtime
  sampling under project policy; sampling attaches
  `FIRE_POOL_MEMBERSHIP_INFERRED`. Membership is still unresolved, dependency
  status remains `OPEN`, and the pool is not eligible for canonical training.
- `ManaEngineSession.training_eligible` is always false today and
  `require_training_admission()` blocks before collection. No ManaEngine
  canonical training data producer exists.
- An illegal action is rejected before mutation. A failure escaping after
  action execution begins poisons the session; diagnostic state and trace are
  not valid afterstates. Supported observation/clone/action boundaries require
  a quiescent native state. Full-state clone is for authoritative simulation
  and deterministic branching, not authorization for live-game search.
- The current model includes a Value Network that estimates eventual win
  probability from a player-visible state, and a separate policy that scores
  currently enumerated actions. Policy logits are not Value estimates or
  action-value estimates. There is no `Q_fallback` today.
- Current state-encoding version is
  `STATE_ENCODING_SCHEMA_VERSION = 16`; the Python source constant is
  authoritative. Current Rosetta policy-action schema is
  `POLICY_ACTION_SCHEMA_VERSION = 3`. They version different contracts.
- Phase 4K.1 implements `attempt_action` and the typed `SimulationAttempt`
  adapter boundary: canonical legality check, isolated clone execution, fixed
  root-seat export, and four outcomes. Only completed valid branches expose a
  state/optional child. The native defect classifier is heuristic, not exact.

### ACCEPTED TARGET

- A supported transition may expose a child only after it completes in a
  valid, quiescent state. An unsimulatable action has no fabricated child
  state; a future evaluator may score the state/action pair directly.
- Future native failure typing must improve `ENGINE_DEFECT` separation beyond
  the implemented Phase 4K.1 Python heuristic, preserving evidence provenance
  and never exposing a poisoned child.
- Runtime may use explicitly approved finite, bounded inferred behavior while
  preserving evidence debt. This does not verify the rule or admit the result
  to canonical training.
- Unknown identities should retain every legitimate visible structured
  feature available to the pipeline. Future model work should distinguish
  different reasons for an unknown identity and support generalizing from
  features rather than requiring a learned embedding for every card ID.
- Real logs should eventually support both gameplay analysis and offline
  rules-evidence review. They must not automatically change rules, manifests
  or model weights.

### FUTURE / NOT IMPLEMENTED

There is no exact native failure taxonomy, `Q_fallback`, unknown-ID
robustness-training pipeline, arbitrary observed-live
state importer, belief/determinization layer, Beam/MCTS integration, live
replay comparator, automatic mechanic-discovery service, evidence-bundle
generator or patch-drift detector. The names and ordering in this document do
not freeze their future APIs.

## 4. ManaEngine boundary

ManaEngine is a strict rules backend, not an approximation engine. When it
cannot safely model an action or outcome, the action must fail closed under
the current contract. The engine must not substitute a supported card, prune
the game-defined candidate set, reroll, or emit a plausible-looking partial
child.

The adapter/evaluator may eventually recover decision coverage without
weakening this rule. Such a path consumes a valid pre-action visible state and
an action descriptor; it does not read poisoned simulator internals as if they
were an ordinary state.

RosettaStone remains useful as an implementation/reference and parity source.
Its presence or a Rosetta-scoped PASS does not establish ManaEngine behavior,
nor does it make RosettaStone the primary forward development target.

## 5. Unknown taxonomy

Use a typed reason in design and evidence records rather than a vague scalar
"confidence":

| Category | Meaning |
|---|---|
| `MODEL_UNKNOWN` | The model has not learned a card/state/combination; the simulator may still understand it. |
| `CARD_EFFECT_UNKNOWN` | The visible card/entity can be represented, but the relevant effect is not safely executable by ManaEngine. |
| `RULE_UNKNOWN` | The project has not established exact Hearthstone semantics for the behavior. |
| `TARGET_UNKNOWN` | Legality, topology, candidate construction or target eligibility cannot safely be inferred. |
| `ENGINE_DEFECT` | An invariant failure, implementation bug or unexpected internal error. This is not normal unsupported behavior and must not silently route to neural fallback. |

These categories answer different questions and can coexist. For example, a
known card may be `MODEL_UNKNOWN`, while its implemented transition is
mechanically executable; a generated outcome can have known identity but
`CARD_EFFECT_UNKNOWN`; an unexpected invariant break is `ENGINE_DEFECT`.

## 6. Orthogonal status axes

Record at least these axes independently:

| Axis | Examples | What it does not prove |
|---|---|---|
| Simulation outcome | `COMPLETED`, `UNSIMULATABLE`, `ILLEGAL`, `ENGINE_DEFECT` (implemented adapter contract) | Rules verification or model confidence |
| Rules/evidence basis | reviewed contract, `REVIEWED_INFERRED`, active `EvidenceConstraint` | Dependency closure or training permission |
| Dependency/training | dependency `OPEN`/`CLOSED`; canonical training allowed/blocked | That a single transition is mechanically executable |
| Model uncertainty | future OOD, epistemic uncertainty, calibration | Simulator correctness or rules evidence |

`SimulationAttempt` now exposes the typed action-attempt outcomes. Native
session APIs still use `is_valid`, `unsupported_outcome`, evidence constraints,
exceptions and `training_eligible`. Native reasons are not yet typed, so the
adapter's `ENGINE_DEFECT` classification has incomplete recall until Phase
4K.1b. Registry/dependency status and model confidence stay outside this result.

## 7. `REVIEWED_INFERRED`

`REVIEWED_INFERRED` means bounded runtime use has been explicitly approved
despite unresolved rules evidence. It never means rules-verified and never
silently enables canonical training. Dependency closure is a separate status.

The current Fire pool demonstrates this policy: pinned build/snapshot scope,
33 candidate identities, `REVIEWED_INFERRED` membership, unresolved
membership evidence, `OPEN` dependencies, runtime use allowed, evidence debt
attached when sampled, and `training_eligible: false`. This is a concrete
exception under explicit policy, not a universal rule that every inferred
pool must use the same dependency status or scope.

Do not attach an arbitrary numeric Value penalty to an inferred branch merely
because it is inferred. Preserve its provenance and evidence debt; establish
ranking policy separately through an evaluated design.

## 8. Dynamic generation pools

Implementation support must never define real pool membership or
probabilities.

- `CANDIDATE`: not admitted for runtime sampling.
- `MEMBERSHIP_REVIEWED`: membership is reviewed under the manifest contract;
  unresolved exclusions are not allowed by the current loader.
- `REVIEWED_INFERRED`: explicitly bounded runtime use may be allowed while
  membership uncertainty remains visible and canonical training remains
  blocked.

An unsupported sampled result is still a legitimate game outcome. Fail the
branch after sampling; do not reroll, substitute or remove that result. Keep
the actual set complete even when some outcomes lack implementation. Loading a
pool is not proof of dependency closure or rules correctness.

## 9. Safe failure semantics

Only a completed valid/quiescent transition can provide a simulator child to
an evaluator or future search. A branch that has partially mutated, consumed
RNG or retained diagnostic-only internal state is poisoned. It may be
inspected through explicitly diagnostic channels, but never serialized as an
ordinary observation, used as a search child or included in canonical
training.

An ordinary unsupported transition is distinct from an engine defect. Future
fallback may handle the former under explicit policy; it must not conceal or
score the latter as though it were expected model uncertainty.

## 10. `SimulationAttempt` adapter contract

**IMPLEMENTED — Phase 4K.1.** `attempt_action(parent, action,
perspective=None, retain_child=True)` checks the six native execution fields
strictly, selects the canonical action from native legality enumeration, then
applies it on a clone. Caller metadata does not reach native apply. The parent
state and RNG are unchanged. Invalid parents raise `InvalidParentSession`;
invalid perspectives raise `ValueError`; `MemoryError`, `KeyboardInterrupt`
and `SystemExit` propagate.

The default perspective resolves the acting root seat once. Explicit
perspectives are `PLAYER1`/`PLAYER2`. The returned state is always exported
from that fixed seat, including after `END_TURN`; public `apply_action`
continues returning the post-action ACTIVE-seat view.

| Outcome | Safe state/child | `fallback_eligible` |
|---|---|---|
| `COMPLETED` | State required; child optional with `retain_child=False` | false |
| `UNSIMULATABLE` | Neither exists; immutable diagnostics required | true |
| `ILLEGAL` | Neither exists | false |
| `ENGINE_DEFECT` | Neither exists | false |

Completion evidence equals the exported `GameState.evidence_constraints`.
Failure evidence exists only in `diagnostics.evidence_at_failure`, with no
transition evidence or usable child. Diagnostics retain scalar exception and
unsupported text, evidence strings and at most 32 trace rows; no session or
native object references.

The temporary defect heuristic recognizes normalized post-mutation exception
messages, exact damage-group catch-all reasons and violated validity/export
postconditions. Some native reject/direct-throw sites can still classify a true
defect as unsupported. This accepted incomplete recall belongs to Phase 4K.1b;
it is not exact native typing. No fallback routing/scoring is implemented.

A retained child is a full-information internal simulator handle, excluded
from result repr/equality, never a model input or live observation. Even an
attempt outcome may depend on hidden deck/RNG state: `END_TURN` can fail when
the opponent's next hidden draw is unsupported. A sampled chance transition
is one outcome, not an expected value. No live-root decision-making is
authorized; it needs a reviewed information-set/determinization boundary.

## 11. Neural fallback and action values

**ACCEPTED TARGET — not implemented.** A future fallback for a legal action
that cannot be simulated should estimate a semantic action value such as
`Q_fallback(state, action)`, aligned with expected match outcome or win
probability. It should not make up an afterstate.

The current Value Network estimates eventual win probability from a state.
The current policy produces action-selection logits. Neither is a substitute
for an action-conditioned Q estimate. A possible first design shares the
state/entity representation and has separate Value and action-conditioned Q
heads; that is a direction to test, not a frozen model API. A dueling
`Q = V + A` decomposition is not required.

For exactly simulated actions, future experiments may compare direct
`Q(state, action)` estimates with value estimates of valid afterstates or
rollouts. Any such consistency objective must use correct states and targets.

## 12. Unknown-card representation

The current domain can carry visible structured properties such as cost,
attack, health, durability, type, class, race, mechanics and current instance
values. The current state encoder uses a saved identity vocabulary plus
structured numeric/category/mechanic features and missing-value masks. An ID
absent from the saved vocabulary maps to the common unknown identity index;
available structured features can still contribute.

The current identity channel does not encode why a card ID is missing from
the saved vocabulary. In particular, a known noncollectible/token identity
outside that vocabulary can share the unknown identity embedding with a
genuinely new card. A future checkpoint-compatible design should distinguish
statuses equivalent to `KNOWN_COLLECTIBLE`, `KNOWN_TOKEN` /
`KNOWN_NONCOLLECTIBLE`, and `UNK_NEW` (or an `identity_status` feature). This
split is not currently implemented.

Do not treat an unknown ID as meaning “no information exists.” Preserve legal
visible card metadata supplied by the source where available. Do not infer
hidden text or hidden opponent-hand identity from it, and do not silently
change saved vocabulary indices when adding metadata.

## 13. Unsupported cards in hand

Do not assume that an unsupported card is inert until played. Held cards may
have passive effects, dynamic costs, draw/hand watchers or deck interactions.
The current ManaEngine conservatively invalidates a branch when an unsupported
card enters hand; it does not implement a general held-effect classifier.

**ACCEPTED TARGET — not implemented:** a future reviewed contract may
distinguish behavior such as `KNOWN_INERT`, `KNOWN_PASSIVE` and `UNKNOWN`.
Retaining an unsupported card in a valid session is safe only when all
relevant held/passive behavior is known under that contract. Unknown held
behavior may require strict fail-closed handling.

## 14. Live-root limitation

ManaEngine currently creates sessions from game setup and two decks, not from
an arbitrary live `GameState` or Power.log snapshot. The adapter additionally
requires Mage mirror sessions today. Exact ManaEngine search from a real game
root is therefore not implemented.

Current full-information cloning supports simulation branching and
deterministic tests. It does not establish that a cloned setup state matches a
real game, preserve an information set, or authorize live MCTS.

## 15. Future information-set and observed-state import

**ACCEPTED TARGET / FUTURE:** a live-root system needs an explicit boundary
from player-visible observation through observed-state import and an
information-set representation before any belief/determinization or search
state is created.

It must not fabricate opponent hand identities, deck order, unrevealed Secret
identities, future RNG outcomes or unknown generated choices. Hidden
information must remain hidden in simulator adapters, search state,
diagnostic export and model input. Whether an imported observation can be
advanced exactly is a separate question from whether it can be represented.

## 16. Training tiers

### Canonical training

Strict data for trusted policy/value targets. It must pass the applicable
rules/evidence, reachable dependency, hidden-information, valid-state and
profile/session/match gates. No poisoned or fabricated states. Under current
policy, `REVIEWED_INFERRED` branches remain excluded from canonical training.

### Robustness training

**FUTURE and explicitly authorized.** It may mask some inputs (for example,
replace selected known IDs with an unknown token) while retaining targets from
valid exact/reviewed trajectories. It must not create fake transitions to
force examples of unknown cards. No robustness-training pipeline is currently
implemented.

### Live inference

**FUTURE.** Runtime decision-making may eventually combine completed reviewed
simulation, completed inferred simulation with provenance, and neural values
for legal unsimulatable actions. Evidence status and model uncertainty remain
separate inputs to an evaluated ranking policy. There are no online rule,
manifest or model-weight updates after each match.

## 17. Live mechanic discovery

**FUTURE:** Power.log/HDT analysis should help surface unsupported identities,
unexpected generated outcomes, targeting behavior, trigger ordering,
damage/death timing, transform/copy behavior, patch drift and contradictions
between expected simulator behavior and a client observation.

Useful offline triage classes include:

- `KNOWN_EXPECTED` — observed behavior matches an established contract;
- `KNOWN_INFERRED_CONFIRMED` — compatible with a bounded inferred contract,
  but not exhaustive proof;
- `NOVEL_OBSERVATION` — behavior is not classified yet;
- `ENGINE_CONTRADICTION` — a valid reviewed engine expectation conflicts
  with the observed event; prioritize investigation;
- `PATCH_DRIFT_SUSPECTED` — behavior may have changed with client/data version.

These are proposed review classes, not current importer output. Repeated
matching observations can strengthen evidence, but do not prove exhaustive
pool membership or semantics.

## 18. Future rules-evidence bundle

A compact reproducible bundle may include game ID, client build, turn/time,
player-visible state before the event, involved card/entity IDs, the relevant
raw log slice, parsed event sequence, simulator support/fidelity, expected and
observed outcomes, active evidence constraints, failure reason and provenance
for offline replay/review.

Raw logs and hidden protocol fields must not leak into neural input. The
current importer creates gameplay examples and does not automatically compare
client replays with ManaEngine semantics. Bundle generation is not
implemented.

## 19. Patch drift

A stable `card_id` does not guarantee stable behavior. A future drift review
should consider client build, metadata/text hash, manifest version and
observed semantic mismatches. An observation outside an inferred manifest
contradicts or invalidates the current assumption and requires review; runtime
manifests never self-expand from one event.

## 20. Incremental roadmap

This is current planning direction, not a frozen interface or a promise that
each stage must be implemented in this exact order:

1. **Phase 4K.1 (implemented):** typed simulation result and safe adapter boundary.
2. **Phase 4K.1b:** typed unsupported reasons and `ENGINE_DEFECT` separation.
3. **Phase 4K.1c:** safe unsupported-held-card semantics.
4. **Phase 4K.2:** unknown/new identity and generic action representation.
5. **Phase 4K.3:** `Q_fallback` prototype.
6. **Phase 4K.4:** unknown-ID robustness training.
7. **Phase 4K.5:** mixed exact/inferred/fallback ranking and evaluation.
8. **Phase 4K.6:** live unknown-event/mechanic-discovery capture.
9. **Phase 4K.7:** observed live state to ManaEngine architecture.
10. **Phase 4K.8:** belief/determinization and Beam/MCTS integration.

Implementation evidence, model evaluations and information-boundary review
may change this sequence. This roadmap grants no training, search or live
integration authorization.

## 21. Explicit non-goals

- Do not weaken ManaEngine or invent partial child states to improve apparent
  simulator coverage.
- Do not equate registration, execution, evidence, dependency closure,
  training eligibility, policy score, Value estimate and Q estimate.
- Do not narrow random/Discover pools to supported results or reroll a failed
  sample.
- Do not expose hidden information in observations, logs used as model input,
  or search state.
- Do not let live observations automatically rewrite card rules, pool
  manifests, evidence status or model weights.
- This document does not start Phase 4K implementation, training, live replay
  comparison, Beam/MCTS work or another card-support package.
