# Standard capability pilot: repeated random damage (2026-10-01)

## Scope

Added two roots through the bounded effect-composition generator:

- `FIR_909` Bursting Shot: three independently selected random enemies take 2 spell damage each.
- `CORE_YOP_034` Runaway Blackwing: at the end of its controller's turn, one random enemy minion takes 10 damage.

The new `RANDOM_DAMAGE` operation requires an explicit allowed enemy selector, fixed damage amount, hit count, and Spell Damage flag. It emits repeated one-target `DamageRandomTargets` tasks, so selection is with replacement. The only selectors accepted are `ENEMIES` and `ENEMY_MINIONS`; the activation is limited to `SPELL_PLAY` and `TURN_END`.

## Evidence

- Native Bursting Shot scenario checks exactly 6 aggregate damage across the enemy hero and two 7-health minions after three 2-damage hits; friendly health stays unchanged and both minions survive.
- Native Runaway Blackwing scenario checks its end-of-turn trigger removes exactly one of two enemy minions while leaving the enemy hero and the other minion unchanged.
- Focused effect-composition suite: 34 cases / 223 assertions passed.
- Bridge smoke passed for both cards: Standard deck validation, session, opening hand, and legal actions.
- Standard registry tests: 14/14 passed.

## Limits and registry result

The scenarios establish those fixed cases and do not cover all target-death, immunity, armor, or damage-trigger interactions. The registry does not yet consume these scenarios as fingerprinted `VERIFIED_SCOPED` admission evidence. Both roots remain `IMPLEMENTED_UNVERIFIED`; training stays blocked.

The registry contains 1,185 roots: 167 direct and 117 generated registrations, with 901 roots lacking detected rules registrations, 171 known non-root nodes, and 317 heuristic dynamic-pool signals. Complete dependency closures and training-eligible roots remain zero.
