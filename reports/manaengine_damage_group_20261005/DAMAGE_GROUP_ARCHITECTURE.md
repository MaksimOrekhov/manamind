# DamageGroupLocalV1 — proposed architecture

Analysis only. Baseline `af0a599399b0694f5f7ad92af5834f0be63b38bc`.
Evidence/limits: [rules review](DAMAGE_GROUP_RULES_REVIEW.md).

## Decision / alternatives

**DAMAGE_GROUP_LOCAL_CONTRACT_BOUNDED**: B plus C, with an explicit correction to B: group close is not generally a death checkpoint.

| Option | Appropriate use | Problem / decision |
|---|---|---|
| A: immediate packet reactions | Single-target packet | Wrong ordinary-area barrier; retain only single-packet mode |
| B: local apply-all DamageGroup | Ordinary area instruction | Choose mutation/reaction barrier; remove automatic group-local death drain |
| C: instruction continuation | Sequential effects / live missiles | Choose typed local child execution; children must finish before parent siblings |
| D: broad scheduler | Cross-zone priorities, forced phases, suspended Choice | No admitted counterexample proves necessary; defer architecture expansion |

No card-text interpreter, generic task language or behavioral card-ID branches. Parameters govern current native handlers.

## Initial admission

Allow ordinary fixed-amount minion areas with reviewed snapshot membership/order; spells only if relevant Spell Damage is stable during apply-all. Allow single-target packets, then admitted reactions, condition/follow-up or next instruction. Allow split-total missiles under `MISSILE_TOTAL`, one completed packet group before each live selection. Preserve self TakesDamage v1's positive-health, unchanged-identity bounds and current intrinsic Reborn outer-pipeline guards.

Do not silently admit distinct-random splash, exceptional areas, excess damage, predamage interception, global watchers, cross-zone priority, active-frame Choice or new lifecycle semantics. Hero-containing areas require an explicit event-order profile, not heroes inserted first by vector construction. First-spell-damage attack reactions require ordering review when combined with another reaction.

## Proposed typed structures

Specification, not implemented source:

```cpp
enum class DamageDispatch { ApplyAllThenReact, SinglePacketThenReact };
enum class DamageEventOrder { MinionEntrySequence, SingleTarget };
enum class DamageFrameStage { Apply, DispatchEvent, DispatchReaction, Complete };
enum class ReactionKind { SelfTakesDamageV1, FirstSpellDamageAttackV1 };
enum class Prevention { None, Zero, Immune, DivineShield };
struct EntityHandle { int entity_id, controller; uint64_t entry_sequence; };
struct DamagePacketIntent {
  int source_entity, source_controller;
  EntityHandle target;
  int amount;
  DamageKind kind;
  DamageAttribution attribution;
  bool lifesteal;
  uint32_t ordinal;
};
struct PacketOutcome {
  DamagePacketIntent intent;
  Prevention prevention;
  int reported_damage;
  int64_t health_delta, armor_delta;
  uint64_t event_sequence;
};
struct DamageReactionSnapshot {
  ReactionKind kind;
  EntityHandle consumer;
  uint64_t trigger_sequence;
  // Typed variant: generation pool/cost OR attack/counter payload.
};
struct DamageGroupFrame {
  uint64_t group_id, parent_group_id, outer_phase_id;
  DamageDispatch dispatch;
  DamageEventOrder order;
  DamageFrameStage stage;
  vector<DamagePacketIntent> packets;
  vector<PacketOutcome> outcomes;
  vector<DamageReactionSnapshot> current_event_reactions;
  size_t packet_cursor, event_cursor, reaction_cursor;
};
```

Separate monotonic `next_damage_group_id` from `next_damage_sequence`. Every successful packet gets an event ID even without a self consumer; prevented outcomes are diagnostic, not successful events. Append enum values. Existing `DamageOccurrence` can become a self-reaction payload derived from the outcome; retain source/controller, actual health delta, activation identity and pool/cost descriptor.

### Ownership, clone and observation

`EngineState` owns counters/RNG and a value-owned frame stack. Executors use index/ID, reacquire after child pushes, and hold no CardInstance pointer/vector iterator across a reaction. Catalog stays immutable/shared. Lookup uses reviewed entity identity/controller checks.

Execution stays synchronous. Public actions/observations/clone occur only at quiescent boundaries with an empty frame stack. Full-state clone copies RNG/counters and all simulator state. Copying frame vectors alone does not capture C++ continuations; active-frame resume/serialization and Choice inside a frame remain unsupported. New external suspension requires architecture review. No encoder/schema change is needed for hidden synchronous frames.

Failure poisons the session: partial mutation is diagnostic only. Preserve first unsupported reason, unwind safely, reject further usable action/clone output. No catch-and-continue, fabricated terminal result or reroll. Branch from a pre-action clone instead.

## Exact checkpoints

### P0 — preflight

Validate amount/controller/attribution, contract combinations, unique targets, explicit ordering, lifetime/modifier bounds and integer limits. Reserve value buffers before gameplay mutation. Freeze ordinary-area targets. No RNG for area preflight.

For `CURRENT_AT_STEP`, evaluate once. If area's targets may change a friendly conditional Spell Damage contribution, reject before mutation; retain mortal-Spell-Damage guard. This conservative bound does not settle intra-area live-modifier rules.

Structural errors may reject pre-mutation. Outcome-dependent reaction validation belongs later: unresolved Plume pool fails at its actual reaction, after the group's damage barrier. Do not require a pool to sample merely to preflight damage.

### P1 — packet mutation

Apply frozen minion packets in entry-sequence order. Resolve zero/Immune/Shield, health/armor mutation and existing saturation behavior. Capture value outcomes. Scalar `DirectSpell` accounting increments once by reported successful packet amount, preserving current armor/overkill contract.

Do not publish reactions yet. `record_spell_damage_event()` mutates Raincaller attack and belongs to P3, unlike scalar turn accounting. Preserve scalar Lifesteal only within current fixed-hero/no-heal-reaction bounds; grouped combinations with observable healing-event ordering are deferred.

No summon, RNG, death removal, global trigger drain or target reselection during area's P1. Unexpected removed/replaced target is unsupported; negative health alone does not remove a frozen AoE target.

### P2 — mutation barrier

Every P1 outcome exists before the first reaction. Trace group ID and ordered event IDs at `GROUP_MUTATIONS_COMPLETE`. A prevented packet does not cancel later area packets.

### P3 — dispatch events and reactions

For each successful event in explicit event order:

1. Build its reviewed responding-trigger list when that event starts; freeze that list for the event. Do not freeze all future event lists at the start of the whole spell.
2. Revalidate self v1 identity/controller/entry sequence/descriptor, current positive health and silence bounds. Unreviewed change rejects rather than pretending no reaction occurred.
3. Dispatch the event's triggers under their explicit priority/order contract. Event target order and internal consumer order are separate; one global consumer sort is insufficient.
4. Finish one reaction's child group and all admitted nested consequences before the next parent trigger/event. No child appended behind parent siblings.
5. A future survives-damage family would recheck survival at activation. Do not change self TakesDamage v1 into that family today.

Current admitted self consumers do not spawn new damage watchers. If a future reaction introduces one, eligibility for later events requires its own reviewed window; this architecture does not silently freeze it out or allow it into the current event.

### P4 — instruction continuation

Return complete outcomes. Evaluate damage-outcome condition/follow-up or next instruction now. A missile rebuilds its living candidates and selects its next target here. Children are complete; outer phase can still be open.

### P5 — outer phase/death boundary

Only the existing reviewed caller's outer phase end invokes `stabilize()` with no active damage frames. Never invoke it at P1–P4. Preserve current batch removal, deathrattle FIFO, intrinsic Reborn and all evidence-debt/fail-closed guards. Forced intermediate death phases are outside v1.

This separates group boundaries from multi-step spell/EOT boundaries without certifying all current global play/Secret/deathrattle phase placements.

## Lifetimes / EOT

- An already-started group continues with captured source attribution even if source becomes mortal.
- Snapshot EOT source eligibility; dispatch by activation order, revalidate identity/descriptor. A queued source still in Play is not automatically cancelled at nonpositive health. Proposed ordinary two-Vulcanos expectation: second queued body executes before phase-end removal.
- Actual removal/transform/control change/silence after capture has no universal skip rule. Reject unreviewed states.
- Live random hits exclude mortal/pending-destroy targets under their reviewed contract. Never shrink candidate sets to implemented outcomes.
- No intermediate hero-terminal shortcut is introduced. New interactions after lethal hero damage require independent phase review.

## RNG / failures

Area barriers consume no RNG. Child generation shares the parent's deterministic stream; parent resumes afterward. Preserve `bounded_random` algorithm and candidate order: one selection can consume multiple raw draws through rejection sampling.

| Failure stage | Required state |
|---|---|
| Bad contract/identity/modifier at P0 | Unsupported before mutation/RNG |
| Missing/candidate pool, invalid count/hash or full hand at P3 | Area mutations retained diagnostically; fail before this generation's RNG |
| Unsupported sampled result | Preserve consumed RNG; invalidate, never reroll |
| Lethal/stale/control-changed self consumer | Reject before its generation RNG; no evidence promotion |
| Child Choice/forced death/unreviewed lifetime | Reject; architecture review if profile-critical |
| Execution budget exhausted | Unsupported, never truncate into success |

Finite safeguards, e.g. depth 64 and 4096 events/action, are engineering policy only; validate limits and retain explicit exhaustion diagnostics. No new global scheduler is warranted by the admitted cases.

## Changes / evidence ownership

Small shared changes: typed result/frame, mutation/reaction split, local child executor, phase guard, explicit timing/order schema, migrated handlers. No CardInstance redesign, Fire admission or training. Stable observable schema does not preserve evidence freshness automatically: new semantic fingerprints require real affected-family verification.

See [consumer matrix](CONSUMER_MATRIX.md) and [implementation plan](IMPLEMENTATION_PLAN.md).
