# Verification proposal — `cost_discount_expiry_verification_v1`

## Semantic contract

Verification-only family for two existing fixed-cost enchantment effects with different consumers and lifetimes:

- `CORE_EX1_145` Preparation applies a 2-mana hand aura to spells. The aura expires when the next spell is cast and at turn end; one cast consumes it for all remaining spells in hand.
- `CORE_BT_416` Raging Felscreamer applies a 2-mana hand aura to Demon minions. The aura is consumed by the first Demon minion played; non-Demons are unaffected.

The family boundary is existing hand-cost aura behavior plus exact consumer predicates and removal events. These are distinct scenarios, not a declaration-sharing claim.

## Reviewed candidates and static dependencies

| Root | Existing behavior | Dependency | Dynamic pool |
|---|---|---|---|
| `CORE_EX1_145` Preparation | Spell-only cost -2; remove on `CAST_SPELL`; end-of-turn expiry | `EX1_145o` | None |
| `CORE_BT_416` Raging Felscreamer | Demon-only cost -2; remove on first Demon `PLAY_MINION` | `BT_416e` | None |

The pinned native scenarios verify current cost values and reset timing, while the bridge scenarios independently inspect effective hand costs and legal actions around first use.

## Scope and expected outcome

- Reuse: existing aura, `SelfCondition::IsSpell`, `SelfCondition::IsRace(DEMON)`, and trigger removal behavior.
- Engine/generator/declaration changes: none expected.
- Expected scoped unlock: 2 Meta Profile roots across Rogue and Demon Hunter; dependency closure and training eligibility remain unclaimed.
- CUSTOM/deferred outliers: none forecast. Stop if bridge effective costs disagree with native expectations or if the exact first-use reset cannot be reproduced.

## Verification plan

- Run existing card-specific UnitTests filters for both roots.
- In configured bridge sessions, cast Preparation and verify a held spell becomes playable at reduced cost, then verify the aura is gone after that spell; play Felscreamer, verify only Demon hand cards are discounted, play one Demon, and verify remaining Demon discounts reset.
- Write explicit profile-scoped evidence under the already-listed harvest evidence path and regenerate the Meta Profile audit. No canonical Standard evidence or full-deck readiness is claimed.

## Completion record

Elapsed time observed with `time.perf_counter_ns()`: **798.898 seconds** (13 min 18.898 s), including proposal review, native/bridge checks, three bridge-scenario correction cycles, evidence write and Meta Profile regeneration. Shared manifest-rebinding setup is measured separately at 235.755 seconds.

Results: 2 roots scoped-verified; this verification-only package had 0 declaration-only consumers; 0 CUSTOM/deferred outliers; 0 shared Python/C++ or production changes; 3 bridge-scenario correction cycles; 2 native scenarios / 28 assertions; registry root/dependency-closure delta 0; training-eligibility delta 0. Preparation passed next-spell consumption and turn-end expiry. Felscreamer passed the Demon-only discount and first-Demon consumption checks, with `CORE_BT_480` (race `None`) as the non-Demon control.
