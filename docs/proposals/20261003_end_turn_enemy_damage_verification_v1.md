# Verification proposal — `end_turn_enemy_damage_verification_v1`

## Semantic scope

Verification-only pair with an existing shared timing boundary, not a claim that the effects share declarations:

- `CATA_999` Earthen Drake deals 4 damage to the enemy hero at the end of its controller's turn.
- `CATA_475` Scalebreaker Bulwark deals 2 damage to all enemy characters at the end of its controller's turn.

## Existing implementation and dependency review

Both roots already have `TURN_END` trigger implementations and fixed `DamageTask` targets. No card dependency, token, random/Discover pool, class/session requirement or new event ordering is involved. Existing trigger processing and damage primitives are sufficient.

## Verification

- Native: root-specific end-of-turn scenarios for both roots, with CATA_475 checking an enemy minion and the enemy hero and CATA_999 checking hero-only damage.
- Bridge: legal play, no immediate damage, then expected damage after the controller's end turn for each root.
- Write explicit scoped evidence for 2 roots, with no full closure/training claim. No production engine or declaration change.

## Completion record

## Completion record

Observed elapsed time: **342.877 seconds** (5 min 42.877 s), measured with `time.perf_counter_ns()` from before package review through evidence/profile regeneration. This includes the test-only CATA_999 native scenario and UnitTests rebuild, two bridge scenarios, and one build-environment correction. Results: 2 roots scoped-verified; 0 declaration-only consumers (verification-only); 0 CUSTOM/deferred outliers; 0 shared engine changes; 2 native cases / 11 assertions; 2 bridge scenarios passed; 0 static dependencies; root/closure registry delta 0; training eligibility delta 0.
