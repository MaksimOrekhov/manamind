# Verification proposal — `spider_rider_hero_attack_draw_verification_v1`

## Semantic contract

`JAIL_872` Spider Rider: after its controller's hero attacks, draw exactly one card. The existing CardDef has an `AFTER_ATTACK` trigger sourced from `HERO` with `DrawTask(1)`. No fixed dependency or outcome pool is involved.

## Existing implementation and verification

- Reuse the current trigger source filtering, attack event and DrawTask. No production code/declaration changes.
- Added one root-specific native scenario in `ManaMindEffectCompositionTests.cpp`: play Spider Rider, use the Druid hero power, attack the enemy hero and assert hand size increases exactly once.
- Existing bridge scenario verifies the legal hero attack and exactly one added hand card.
- Scoped evidence only; this does not establish the full Druid deck closure or training admission.

## Completion record

Observed elapsed time: **295.115 seconds** (4 min 55.115 s), using a `time.perf_counter_ns()` marker created before review and stopped after evidence and profile audit regeneration. Results: 1 scoped-verified root, 0 declaration-only consumers (verification-only), 0 CUSTOM/deferred outliers, 0 shared engine changes, 1 test-only change / 1 focused native case / 3 assertions, 1 bridge scenario, 0 registry root or dependency-closure delta, 0 training-eligibility delta. One UnitTests build was required; no production engine changes or native regressions were observed in the focused suite.
