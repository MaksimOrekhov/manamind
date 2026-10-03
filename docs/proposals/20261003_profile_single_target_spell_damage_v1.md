# CAPABILITY PACKAGE PROPOSAL — `profile_single_target_spell_damage_verification_v1`

## Semantic contract

Verify existing profile roots whose executable effect deals fixed damage to a selected legal target. Preserve each card's independently declared target restriction and any additional fixed effect (Freeze or Lifesteal). This is a verification family, not a shared renderer or implementation package.

## Reviewed candidates

- `CORE_CS2_029` Fireball — fixed damage to a legal character.
- `CORE_CS2_072` Backstab — fixed damage to a damaged minion.
- `CORE_CS2_024` Frostbolt — fixed damage and Freeze on a legal character.
- `CORE_ICC_055` Drain Soul — fixed damage and Lifesteal on a legal minion.

All four roots already have CardDefs. The intended family is bounded by these existing target/effect primitives; it does not claim that their individual target rules are interchangeable.

## Existing primitives, dependencies, changes, and checks

- Existing RosettaStone primitives: `DamageTask`, existing target requirements, Freeze and Lifesteal.
- Dependencies/dynamic pools: none identified in reviewed effects.
- Required engine/generator changes: none. Declaration changes: none.
- Expected unlock: 4 profile-scoped roots across Mage, Rogue and Warlock; this does not imply closure or admission.
- Test strategy: one existing root-specific native behavior scenario per card, plus configured bridge deck validation, visible SELF identity and legal-action enumeration per root.
- CUSTOM/deferred outliers: none expected; stop if the existing target/effect behavior does not match a root.

# Completion Record — `profile_single_target_spell_damage_verification_v1`

## Outcome

- Reviewed candidates: `CORE_CS2_029` Fireball, `CORE_CS2_072` Backstab, `CORE_CS2_024` Frostbolt, `CORE_ICC_055` Drain Soul.
- Existing declarative roots scoped-verified: 4/4. No declarations or production rules changed.
- CUSTOM/deferred outliers: 0. The family uses existing target legality, `DamageTask`, Freeze and Lifesteal primitives; no dynamic pools or card-specific behavior were found in scope.
- Shared Python/C++ changes: 0 production changes; the verification runner is shared audit tooling for this family and the sibling fixed board-damage family.
- Correction cycles/builds: 0 semantic correction cycles; 0 builds (used the existing configured build and bridge).
- Native scenarios: 4 independent card-specific scenarios, 4 assertions each; **4 cases / 16 assertions passed**.
- Bridge/parity: 4 configured sessions passed Standard deck validation, visible SELF-hand identity and legal-action enumeration.
- Registry/profile delta: +4 current Meta Profile scoped roots; +0 canonical Standard-current roots; dependency closure +0; training eligibility +0.
- Elapsed time: not captured by the execution tooling; no duration is inferred.

Evidence: `integrations/rosettastone/card_rules/profile_single_target_spell_damage.evidence.json`.

This evidence verifies the four existing implementations in the pinned Meta Profile scope only. It does not establish transitive closure, full-deck readiness, or training eligibility.
