# ManaEngine Phase 4E.2 — Dark Gift evidence safety

This record describes the bounded prototype changes. It does not promote
Dark Gift membership, sampler behavior, canonical evidence, or training
eligibility.

This is a dated Phase 4E.2 evidence record; its historical findings and
statuses remain unchanged. For the current primary ManaEngine role and the
separation between runtime execution, evidence debt and canonical training,
see [Partial Simulator Architecture](PARTIAL_SIMULATOR_ARCHITECTURE.md).

## Session evidence constraints

`GameSession` stores a typed set with stable IDs
`DARK_GIFT_RUNTIME_MEMBERSHIP_UNRESOLVED` and
`DARK_GIFT_SAMPLER_UNVERIFIED`. A successful Discover offer records each
constraint whose provisional assumption it actually exercised. Loading a
manifest alone records nothing. These constraints do not invalidate a
mechanically executable session and are copied as part of the complete native
session state.

The ManaEngine adapter exposes the sorted IDs on `ManaEngineSession` and in
the domain `GameState` serialization boundary. `GameState` validates IDs;
unknown values fail deserialization. The state encoder does not consume this
field. Evidence constraints independently block canonical training admission,
even if the global admission gate is later opened. Global ManaEngine training
admission remains blocked, and `training_eligible` remains false.

## Policy action schema v3

Policy action features now distinguish `play_dark_gift_N` from
`choice_dark_gift_N`. Version 2's single `dark_gift_N` family represented a
selected Discover gift in the Rosetta action contract. Its checkpoint columns
migrate explicitly into `choice_dark_gift_N`; new PLAY columns start at zero.
This preserves the reviewed v2 meaning and does not reinterpret old weights as
having learned PLAY-gift effects.

ManaEngine PLAY actions encode the gift attached to the played hand instance.
Both ManaEngine's `choice_dark_gift` and Rosetta's numeric `dark_gift_id` encode
the selected CHOICE gift. Numeric IDs use Rosetta's stable 1–10 DarkGift enum
ordering and are normalized to canonical card IDs for observations.

The pinned RosettaStone source stores the chosen gift on the entity in
`MANAMIND_DARK_GIFT_ID`. `integrations/rosettastone/bridge.cpp` exports the
singular numeric `dark_gift_id` for SELF hand cards, board minions, and selected
choice actions. The serializer maps that 1–10 value through Rosetta's
`DarkGift` enum ordering into the canonical `CardFeatures.dark_gifts` tuple.
Opponent hand identities remain hidden; only public board entities and SELF
hand cards are normalized.

## Scope limits

Runtime option membership remains unresolved and the assignment sampler
remains unverified. No runtime-derived choice is training eligible. Dark Gift
still applies only to minion options. Prepare is a spell-card action in the
reviewed fixture, so a single instance cannot legally carry both a Dark Gift
and Prepare; their existing independent cost and hand-instance regressions
remain in place. No new game mechanic is added by this checkpoint.
