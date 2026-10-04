# CAPABILITY PACKAGE PROPOSAL

## package_id

`ordered_random_distinct_damage_v1`, proposal 2026-10-04; ManaMind 8413065 / Rosetta f34da0d; pinned `standard_full_20261001_v1`, frozen `tricky_burn_mage`. Status: `BLOCKED_DESIGN_REVIEW`. No production implementation started.

## semantic capability

Proposed REUSABLE_CAPABILITY: ordered damage instructions, deterministic runtime candidate construction, random selection, explicit exclusion/distinctness parameters and shared damage attribution/prevention. Entity IDs are execution handles, not ML features. Targeting pools are runtime entities, not generated-card pools.

Reviewed card-text contracts: Sleet targeted-character 2 then random enemy-minion 1, with no exclusion of first target specified. Barrage selected enemy 3 then two distinct other random enemy characters 2. Target-pool timing, aura refresh and death/trigger interleaving remain unresolved; see the architecture checkpoint.

## existing RosettaStone primitives

DamageTask, RandomTask, IncludeTask, ComplexTask::DamageRandomTargets, ConsecutiveDamageTask, Generic::TakeDamageToCharacter, Game::ProcessDestroyAndUpdateAura. Existing ManaEngine EffectStep/TargetSelector, bounded RNG, clone, deal_damage and stabilization are reusable after boundary review. Registration/helpers do not independently verify card semantics.

## candidate cards using the same semantics

| Root | Pinned parameters | Review |
|---|---|---|
| CATA_485 | selected character 2; random enemy minion 1; first target can be friendly | Amount/target kinds reviewed; aura/phase boundaries blocked |
| TIME_855 | selected enemy 3; two distinct other enemy characters 2 | Amount/exclusion reviewed; sampling/phase boundaries blocked |

## dependencies

No generated outcomes from these spells. Relevant interactions: END_022 conditional aura, CORE_EX1_012 aura/deathrattle, CATA_487 event progression, prevention and Secret cancellation. Full deck closure still needs all generated outcomes transitively.

## required engine/generator changes

Finite allowlisted random selectors and count/distinct/exclude-selected fields; explicit reviewed damage-boundary policy; one shared renderer, no behavioral ID branches. Candidate order and bounded RNG remain deterministic. Clone branches remain independent. Do not alter global snapshots or drain unrelated trigger queues without review. A second independent control declaration varies amount/count/empty-pool parameters without generator/native changes.

## expected unlock count

Potential declaration-only consumers: two roots/four frozen slots. New outcome IDs: zero. Verified closure/training delta: UNKNOWN until boundary evidence; registration cannot establish it. Cost forecast deferred until design is settled.

## test strategy

Independent amounts/target legality; zero/one/two/many additional targets; selected hero/minion; Sleet can revisit a surviving first target, Barrage excludes it and has no repeats; deterministic seeds/clone independence; shield/Immune; same-spell Seer activation; aura death; lethal/fatigue/draw/reaction ordering before sampling; Counterspell; adapter/Policy parity; full native/Python/regeneration/Win-Ubuntu checks. Timing expectations require decisive independent evidence, not declarations or old prototype assertions.

## custom outliers

No ID-specific behavior needed for target/amount contract. Any exceptional timing consumer must be deferred or explicitly CUSTOM. Do not introduce a branch for either candidate.

## Completion record

Proposal only: zero implementation/declarations, zero registry/evidence promotions, zero training gain. Blocked by a shared semantic timing decision, not card count.
