# CAPABILITY PACKAGE PROPOSAL — `profile_deck_minion_cost_threshold_v1`

Revision 1 — 2026-10-03. Inputs: `standard_full_20261001_v1`, refreshed `standard_registry_20261001_v1`, and `meta_training_20261002_v1` at RosettaStone revision `78136d4`.

## Package decision

Proceed with two unsupported Paladin roots from `beatrix_pure_paladin`: `JAIL_327` and `JAIL_516`. Both use the same semantic selector: choose up to N minions currently in the controller's deck whose effective current mana cost is at most a declared threshold, remove them from the deck, and summon them. Activation timing, count, duration, and post-summon Rush are declaration parameters around that shared operation.

The Cannoneer-theme candidates were re-reviewed and split into different contracts (turn-end random shot, shot after a hero attack, persistent Pirate damage modifier, and Discover/summon). Their shared theme does not justify one capability package. They remain in the queue for separate review.

## Semantic capability

Contract: `deck_minion_cost_threshold_summon`, version 1, implementation kind `REUSABLE_CAPABILITY`.

- Filter the controller's current deck at resolution time; a card already drawn, summoned, or otherwise removed from that zone is not a candidate.
- Candidate must be a minion with effective current cost `<= max_cost`.
- Select up to `count` distinct eligible minion instances uniformly through RosettaStone's random selection primitive, remove selected instances from the deck, then summon them in the selected order subject to ordinary board capacity.
- `JAIL_327` activates at the controller's end step three times after the spell resolves, selecting one minion each time; no Rush is granted.
- `JAIL_516` activates once as a Battlecry, selects up to two minions, then gives Rush to those summoned minions.
- If fewer than `count` eligible minions exist, summon all eligible results. An empty filtered set produces no summons. These expectations require independent native confirmation.

No card ID dispatch is permitted. A future consumer with the same selector and different declared threshold/count/activation/post-summon keyword must use the same renderer unchanged.

## Existing RosettaStone primitives

- `SimpleTasks::IncludeTask(EntityType::DECK)` and `FilterStackTask`.
- `SelfCondition::IsMinion()` and `SelfCondition::IsCost(value, RelaSign::LEQ)`; `IsCost` reads `Playable::GetCost()` at filter time.
- `SimpleTasks::RandomTask(EntityType::STACK, amount)` and `SummonStackTask(true)`.
- `Trigger(TriggerType::TURN_END)` with `lastTurn = 3` for the three end-step activations.
- `Effects::Rush` / existing enchant primitives for the Battlecry's post-summon keyword.

Relevant source: `Includes/Rosetta/PlayMode/Tasks/ComplexTask.hpp` (deck filtering compositions), `Sources/Rosetta/PlayMode/Conditions/SelfCondition.cpp` (`IsCost`), `Sources/Rosetta/PlayMode/Triggers/Trigger.cpp` (`lastTurn`), and `Sources/Rosetta/PlayMode/Tasks/SimpleTasks/SummonStackTask.cpp`.

The existing convenience task only matches exact cost and summons one result. The lower-level primitives appear sufficient for a shared `<=` / count contract, but `RandomTask` ordering, board-cap behavior, and attaching Rush to the selected instances need focused tests.

## Candidate roots

| Root ID | Card | Contract parameters | Current support | Review |
|---|---|---|---|---|
| `JAIL_327` | Reinforcement Aura | `max_cost=2`, `count=1`, `activation=TURN_END`, `duration=3`, `rush=false` | No detected registration; no scoped evidence | In scope |
| `JAIL_516` | Scarlet Recruiter | `max_cost=2`, `count=2`, `activation=BATTLECRY`, `duration=1`, `rush=true` | No detected registration; no scoped evidence | In scope |

Both appear in `beatrix_pure_paladin`; the package advances one frozen deck. Initial pinned root-list membership in that deck contains two copies each of `CORE_ICC_038` (1-cost Righteous Protector) and `TLC_438` (2-cost Violet Treasuregill), the only listed minion IDs matching the threshold. The live selector must remain zone/predicate-driven; these four profile copies are an audit snapshot, not a hardcoded runtime pool.

## Dependencies

- Runtime outcomes are selected from the controller's own current deck, not a global collectible/Discover pool.
- Initial profile membership snapshot: `CORE_ICC_038 ×2`, `TLC_438 ×2`. Membership changes as cards leave the deck or their effective costs change.
- `TLC_438` has its own independent Battlecry/deck-spell behavior when played. It does not resolve when summoned by these cards; its other reachable outcomes remain separate closure dependencies of the deck root.
- No tokens, options, transforms, or generated-card pool are required by this selector itself.
- Full Beatrix deck closure remains blocked by other profile roots, Fabled seeds, unresolved pools, and session/match evidence.

## Required engine/generator changes

- Add one strict, versioned declaration contract and shared C++ renderer for deck filtering, random selection, summoning, optional Rush, and either Battlecry or bounded end-of-turn activation.
- Declarations for both roots must go through the same renderer. No `card_id == ...` check or generated-source hand branch is allowed.
- If trigger activation/duration cannot be represented without an ID-specific branch or a broad lifecycle change, stop and defer `JAIL_327` rather than widening the contract.
- This two-consumer package is the independent reuse proof; second declaration varies activation, count, and Rush with no renderer code change.

## Expected unlock count

- Newly registerable roots: 2 (`JAIL_327`, `JAIL_516`).
- Roots targeted for current scoped verification: 2.
- Frozen decks directly advanced: 1 (`beatrix_pure_paladin`).
- Candidate dependency identities in the initial deck snapshot: 2 unique IDs / 4 copies; no additional identity is expected if both are already listed roots.
- Complete closures/training admission: expected 0 from this package alone. The exact dependency predicate and family behavior can be verified, but unrelated deck roots and session/match gates remain.

## Test strategy

1. Independent native scenario for `JAIL_327`: exactly one eligible minion is summoned at each of three consecutive controller end steps; a cost-3 minion is never selected; the effect expires after the third trigger.
2. Independent native scenario for `JAIL_516`: two distinct eligible minion instances leave the deck and are summoned with Rush; a cost-3 minion is excluded.
3. Boundary/interactions: no eligible minions; one eligible minion for a requested count of two; one selected minion drawn before resolution; a current-cost-changing enchant crosses the threshold; full board behavior; duplicate copies remain distinct selectable instances.
4. Actual bridge scenarios using the frozen Beatrix list check action visibility, deck/board/hand counts, current costs, Rush flags, and trigger timing.
5. Verify exact profile predicate snapshot without narrowing the runtime filter; update package evidence and meta audit separately from canonical Standard admission.

## Custom outliers

None forecast for the two reviewed consumers. If bounded-trigger lifecycle requires a package-wide engine/session redesign, defer `JAIL_327`; do not add an ID-specific custom branch. `CAP_102`, `CAP_103`, `CAP_104`, `CAP_106`, and `CAP_107` remain unselected and are not implementation work for this package.

## Completion record

Completed 2026-10-03 against Standard profile `standard_full_20261001_v1` and Meta profile `meta_training_20261002_v1`.

| Metric | Result |
|---|---|
| Elapsed time | 41m 30s from proposal creation through verification and registry update |
| RosettaStone package revision | `945d891` |
| Candidate cards | `JAIL_327` Reinforcement Aura; `JAIL_516` Scarlet Recruiter |
| Declaration-only consumers | 2/2 (100%) |
| CUSTOM / deferred package outliers | 0 / 0 |
| Shared implementation | Strict Python contract renderer: 44 LOC; generator/schema validation and C++ emission: 193 LOC; generated C++: 44 LOC plus 10-line header; `CardDefs` registration. No new core engine primitive. Existing Include, FilterStack/IsCost, RandomTask, AddEnchantmentTask, SummonStack and bounded TURN_END trigger were reused. |
| Native family verification | 3 scenarios, 54/54 assertions: two eligible minions with Rush and cost-3 exclusion; three bounded end-step summons; live current-cost boundary, one available eligible minion and empty selection. |
| Bridge verification | Both consumers passed against the loaded Python bridge. Recruiter summoned exactly two minions with effective cost <=2 and Rush. Aura summoned once on each of three controller end steps and not on the fourth. The synthetic legal fixture did not contain the unsupported profile root `TLC_438`, so this is scoped behavior evidence, not frozen-deck closure evidence. |
| Correction cycles / builds | 4 focused correction cycles; 3 substantive native build attempts (one repaired stale Ninja object, then successful Ninja and py312 consumer builds). |
| Registry delta | +2 generated registrations (`GENERATED_PROFILE_DECK_MINION_COST_SUMMON`); profile unregistered roots 68 vs 70 before; profile current scoped roots 4 vs 2 before. Standard-wide generated registrations 186 vs 184; unresolved pools remain 318; known non-root dependency nodes remain 192. |
| Verified roots gained | +2 current Meta-profile scoped roots. Canonical Standard scoped-current evidence remains 0. |
| Dependency closures gained | 0 complete Meta closures; the Beatrix deck still has unresolved `JAIL_327`/`JAIL_516` selector pools, `TLC_438` and other dependencies. |
| Training eligibility delta | 0; no deck is fully closed or eligible, and no training was run. |
| Checks | Native family 3/3; Python suite 80/80; generated outputs 36/36 reproducible; Ruff and generator AST guard pass. The full native suite was not run. |

The package requires no card-ID behavioral branch. Its shared selector filters the live deck by minion type and current cost, then samples without replacement up to the declared count. The static profile snapshot remains `CORE_ICC_038 ×2` and `TLC_438 ×2`; the runtime renderer does not hardcode this membership.
