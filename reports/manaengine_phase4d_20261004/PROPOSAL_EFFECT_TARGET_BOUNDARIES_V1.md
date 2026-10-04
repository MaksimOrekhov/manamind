# Capability proposal: effect target boundaries v1

## package_id

`manaengine_effect_target_boundaries_v1`, profile `standard_full_20261001_v1`, base `09e61e686f9a1a086d086e1bc24f475defd5c63b`.

## Semantic contract

Extend existing `EFFECT_COMPOSITION` damage with two universal selectors:

- `ALL_MINIONS`: one damage instruction snapshots every living minion on both boards and deals its evaluated amount to each; heroes are excluded.
- `SELF_HERO`: damage the effect controller's hero as an ordinary spell damage packet. It does not create an explicit player target; the root card's separate `EXPLICIT_MINION` instruction supplies the player-selected target where required.

These selectors change only target sets. They reuse the existing `deal_damage`, spell-damage evaluation, attribution, armor, lethal-state and batch death processing. The implementation must not add death resolution between packets or between members of the same area instruction.

## Independent reviewed contracts

| Root | Official card text | Declaration |
|---|---|---|
| `CATA_582` Searing Fissure | [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/123157-searing-fissure?set=cataclysm): deal 1 to all minions, then give your hero +3 Attack this turn. | `DAMAGE / ALL_MINIONS / 1`, then existing `MODIFY_HERO_ATTACK / SELF / 3` |
| `CORE_BOT_222` Spirit Bomb | [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/48113-spirit-bomb/): deal 4 to a minion and your hero. | `DAMAGE / EXPLICIT_MINION / 4`, then `DAMAGE / SELF_HERO / 4` |

The two consumers independently exercise board-wide and owner-relative target resolution. A non-card-identified native control declaration will vary the amounts and verify that selectors are not tied to either root ID.

## Existing primitives

`EffectComposition`, `EffectKind::Damage`, `TargetSelector::ExplicitMinion`, `TargetSelector::AllCharacters` (reference only; it includes heroes and is not equivalent), `deal_damage`, `evaluate_spell_damage`, `DamageAttribution::DirectSpell`, existing `ModifyHeroAttack`, `recompute_hero_attack` and stabilization/death batches.

## Dependencies / expected unlock

No generated dependencies or dynamic pools. Two Standard roots gain task-local scoped support. This alone does not close the wider `area_damage_hero_attack` family or affect runtime-pool admission.

## Changes and boundaries

Add two enum selectors, schema validation, resolution and focused family tests. No observation fields or Policy schema changes. No card-ID dispatch. The family does not claim support for packets that require inter-packet death processing, state-scaled values, random targetting or death-event follow-ups.

## Test strategy

Use real production declarations. Check legal minion target for Spirit Bomb, both sides' minions damaged by Searing Fissure, heroes unchanged by its area packet, exact spell-damage scaling and temporary hero attack expiry. Check Spirit Bomb damages only the chosen minion plus the caster's hero, never the opposing hero. Add a fixture variation that changes selector amounts without changing shared code. Run native family/full tests and adapter/policy parity for legal-action/observation export; run full final suites at the sprint checkpoint.

## Custom outliers

None for these two roots. `CATA_581`, `EDR_570` and `JAIL_307` are not included: they require a state-scaled amount, Choice continuation or repeated packet/death-order semantics respectively.
