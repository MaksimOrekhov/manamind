# CAPABILITY PACKAGE PROPOSAL — `profile_enemy_board_damage_verification_v1`

## Semantic contract

Verify existing profile roots that deal fixed damage over a bounded enemy-board/character target set, preserving each card's exact target boundary and any fixed draw behavior. This is a verification family, not a shared renderer or implementation package.

## Reviewed candidates

- `CORE_CS2_062` Hellfire — fixed damage to all characters.
- `CORE_EX1_129` Fan of Knives — fixed damage to enemy minions, then draw.

Both roots already have CardDefs. Their scenarios must verify distinct target sets; the grouping is a shared audit priority, not a claim that the effects have identical semantics.

## Existing primitives, dependencies, changes, and checks

- Existing RosettaStone primitives: `DamageTask`, target-set selection and draw task.
- Dependencies/dynamic pools: none identified in reviewed effects.
- Required engine/generator changes: none. Declaration changes: none.
- Expected unlock: 2 profile-scoped roots across Warlock and Rogue; this does not imply closure or admission.
- Test strategy: one existing root-specific native behavior scenario per card, plus configured bridge deck validation, visible SELF identity and legal-action enumeration per root.
- CUSTOM/deferred outliers: none expected; preserve Hellfire's all-character boundary and Fan of Knives' enemy-minion boundary.

# Completion Record — `profile_enemy_board_damage_verification_v1`

## Outcome

- Reviewed candidates: `CORE_CS2_062` Hellfire and `CORE_EX1_129` Fan of Knives.
- Existing declarative roots scoped-verified: 2/2. No declarations or production rules changed.
- CUSTOM/deferred outliers: 0. Both use existing damage/draw behavior; their distinct target boundaries are covered by separate scenarios. No dynamic pools were found in scope.
- Shared Python/C++ changes: 0 production changes; reused the sibling fixed spell-damage audit runner.
- Correction cycles/builds: 0 semantic correction cycles; 0 builds (used the existing configured build and bridge).
- Native scenarios: 2 independent card-specific scenarios, 8 assertions each; **2 cases / 16 assertions passed**.
- Bridge/parity: 2 configured sessions passed Standard deck validation, visible SELF-hand identity and legal-action enumeration.
- Registry/profile delta: +2 current Meta Profile scoped roots; +0 canonical Standard-current roots; dependency closure +0; training eligibility +0.
- Elapsed time: not captured by the execution tooling; no duration is inferred.

Evidence: `integrations/rosettastone/card_rules/profile_enemy_board_damage.evidence.json`.

This evidence verifies the two existing implementations in the pinned Meta Profile scope only. It does not establish transitive closure, full-deck readiness, or training eligibility.
