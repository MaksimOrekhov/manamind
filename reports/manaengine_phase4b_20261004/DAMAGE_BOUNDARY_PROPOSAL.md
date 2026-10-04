# CAPABILITY PACKAGE PROPOSAL

package_id: local_damage_boundary_v1
implementation_kind: REUSABLE_CAPABILITY
contract_version: 1
baseline: ManaMind e9572dd3dfee44846c5368365e3f69c7fc308d4b; RosettaStone f34da0d3fcb5ad312f7e2acf634d0536b044d29a

## Reviewed contract

The user's architecture decision supplies the independent expectation: Sleet Storm first deals 2 to an undamaged friendly 1/3 Time-Twisted Seer; the second instruction deals 1 + the newly active 2 Spell Damage to an enemy minion.

CURRENT_AT_STEP evaluates base instruction amount + current friendly board Spell Damage + persistent source-instance bonus immediately before each Damage instruction. One area instruction evaluates once for all its packets. It does not drain triggers/deaths between instructions. The persistent bonus is captured from the actual played instance and never read from a replacement hand card.

MISSILE_TOTAL evaluates base missile count + board bonus + persistent bonus once; each missile still deals 1. It preserves the existing reviewed missile family. No general SNAPSHOT_SEQUENCE mode is needed or added.

A typed context carries owner, source entity, persistent bonus and evaluation contract. Contract version 1 is explicit in source/diagnostic traces. Non-spell Battlecry compositions remain unaffected by Spell Damage. Secret packets retain their existing fixed contracts.

## Consumers and primitives

- CATA_485: declaration-only composition, explicit character Damage(2), random enemy minion Damage(1).
- Independent test-only parameter variation: Damage(1) to an explicit character, then Damage(2) to a random enemy minion, using the same renderer without production ID dispatch.
- Existing ordinary damage spells and Arcane Flow compositions reuse CURRENT_AT_STEP; Arcane Missiles reuses MISSILE_TOTAL.
- Reuse deal_damage, spell_damage_for, typed effects/target legality, bounded deterministic RNG, clone, existing death/trigger processing, per-instance Kalec bonuses and Raincaller packet events.

Dependencies: runtime enemy board entities, existing Spell Damage auras and per-instance enchantments; no generated card or catalog random/Discover pool.

## Narrow changes and unresolved interactions

Append RANDOM_ENEMY_MINION to the selector surface; choose from the actual living enemy board at the instruction, allow reselection of a surviving first target, empty board is a no-op without consuming RNG. No support-based filtering.

Fail closed before a subsequent ordinary damage instruction if a mortally wounded unsilenced friendly Spell Damage source makes aura contribution unresolved. Fail closed before random minion selection if a previous instruction left pending board deaths: their removal/deathrattles versus candidate-selection timing is not independently established. Do not call stabilize to hide either gap. Such failures invalidate the session, not merely skip an effect.

CATA_485 therefore has scoped implementation with explicit mortality blockers until those interactions are reviewed. Expected full verified-root/deck-closure/training unlock count is zero; one scoped declaration is added. Canonical RosettaStone statuses are not promoted by experimental tests.

TIME_855 is deferred: when its other targets are selected, handling mortal candidates, without replacement and per-hit damage timing remain unresolved. It is not a consumer of this package. No CUSTOM implementation or card-ID behavior branch is planned.

## Verification

Independent native cases: undamaged/damaged/silenced Seer, no aura, static and multiple auras, real Kalec persistent grant, Divine Shield/Immune prevention, empty board/RNG, repeated same target, clone equality/independence, mortality fail-closed, area-instruction preservation, missile count preservation and parameter reuse. Existing Fireball/Frostbolt/First Flame/Arcane Flow/Secrets/Raincaller regression groups run together.

Adapter real-declaration test reproduces Seer + Sleet via legal actions, cloning and visible state; policy regression remains enabled. Rebuild affected C++ consumers once per correction cycle; run native suite, adapter/policy suite, full Python suite, pinned generation/guardrail/lint, then push and verify both Windows/Ubuntu workflow matrices actually reach pytest. Record observed counts/time, partial closure and CI identities in completion evidence. Stop after this package.
