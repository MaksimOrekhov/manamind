# Capability Package Proposal — profile_discover_battlecry_minion_v1

Status: implementation candidate, bounded to one real Meta Profile root.

## Package contract

`CORE_GIL_836` resolves a three-option Discover at runtime. Build the eligible pool from the pinned `standard_full_20261001_v1` collectible snapshot using these declarative conditions:

- card type is minion;
- card has the Battlecry mechanic;
- card class is the active player's class or neutral;
- a card ID appears at most once in this snapshot pool.

Sample three distinct options without replacement using the session's deterministic RNG. Keep every eligible card in the pool regardless of ManaEngine support state. The source card is then resolved and the selected card is generated into its owner's hand with the declared cost delta. A supported selected card continues normally. Selecting a definition marked `UNSUPPORTED` invalidates that branch; it must remain visible as a choice and must never be filtered out to make simulation succeed. If the hand is full, the selected card is burned according to the hand cap. Choice completion returns to normal legal-action generation. Cloning a pending choice copies options, continuation, hand capacity state and RNG state independently.

The supported input scope for this package is the profile's Shaman use of `CORE_GIL_836`. Cross-class casting and the fallback-to-source-card-class rule are not claimed. Choice eligibility uses the active player's class; neutral options are always eligible. No current deck, implementation-support, or training-eligibility predicate may narrow the card pool.

## Existing primitives

- Typed `PendingChoice` state and `ChooseCard` action.
- Semantic choice option descriptors, including card ID/type/cost/stats.
- Deep `GameSession::clone()` and deterministic session RNG.
- `CardInstance` hand zone, effective cost delta, entity ID allocation and hand-cap handling.
- Python adapter's pinned Standard collectible metadata and ManaMind action dictionary boundary.

## Reviewed candidates

| Candidate | Disposition | Reason |
|---|---|---|
| `CORE_GIL_836` Blazing Invocation | In scope | One real Meta Profile root; current pinned text is “Discover a Battlecry minion. It costs (1) less.” |
| `CAP_407` Wanted Poster | Deferred | Its “give it Prepare” rider requires a reusable one-time same-turn mana reduction/hand action state. It is not an honest declaration-only consumer of this pool-and-add-card continuation yet. |
| `TLC_464` Mountain Map | Deferred | Requires minion-type history, a history-sensitive pool and a second choice after playing the selected card. |

Expected direct profile delta: one root and its actual deck slots become prototype-supported only where a supported option is selected; unsupported selections remain invalid. This package does not claim complete deck closure or training eligibility.

## Dependencies and pool identity

- Dependency: the immutable full collectible card catalog belonging to `standard_full_20261001_v1`, including all eligible Shaman and neutral Battlecry minions.
- Choice outputs are generated cards, not deck draws; they do not remove any deck entry.
- Pool identity/fingerprint will be recorded from the ordered eligible card IDs plus cost/type/class/mechanics used by the predicate.
- Unsupported eligible definitions stay in the pool and descriptors. No support-state filtering or replacement sampling is permitted.

## Required implementation changes

- Add generic declarative Discover pool fields to `CardDefinition` and schema validation.
- Add a typed continuation that generates the selected card into hand with a declarative cost delta.
- Preserve card ID and printed metadata in `ChooseCard` semantic action descriptors without using entity IDs as card identities.
- Load collectible and Battlecry flags from the pinned Standard snapshot for every candidate definition.
- Keep `CORE_GIL_836` behavior data-only; no card-ID branch in runtime code.

## Test strategy

- Focused native cases: exact class/neutral/type/Battlecry pool membership, complete unsupported candidates retained, three distinct options, deterministic same-seed options, source-card declaration, pending-choice clone and independently diverging branches, selected-card generated provenance and cost delta, hand-full burn, unsupported selection invalidation.
- Adapter sequence: real `CORE_GIL_836` action → pending `CHOOSE_CARD` actions with card descriptors → clone pending state → choose/continue a supported option where sampled; separately select an unsupported option and assert fail-closed.
- Python suite, Release CMake build/CTest, policy/action schema checks, RNG golden checks and Windows/Ubuntu CI.

## Expected reuse and outliers

- One declaration-only consumer now (`CORE_GIL_836`); the operation is reusable for other Discover effects with equivalent pool predicates and generated-hand continuations.
- `CAP_407` and `TLC_464` remain deferred outliers until their additional semantics receive separate proposals.
- No CUSTOM implementation is currently proposed.

## Risk and estimate

Correctness risk is high around pool membership, class eligibility, sampling without replacement and unsupported branch handling. Expected cost is a compact cross-layer change plus native/adapter verification; if exact pool membership or choice continuation cannot be established from the pinned catalog, stop and leave the root unsupported.
