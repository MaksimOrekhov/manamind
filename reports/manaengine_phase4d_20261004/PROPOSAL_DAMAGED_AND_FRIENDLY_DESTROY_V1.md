# Capability proposal: constrained minion destruction v1

## Package

`manaengine_constrained_minion_destroy_v1`, profile `standard_full_20261001_v1`, base `09e61e686f9a1a086d086e1bc24f475defd5c63b`.

## Reviewed consumers and sources

- `CORE_CS2_108` Execute — [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/69535-execute?class=warrior&set=core): “Destroy a damaged enemy minion.”
- `EDR_531` Siphoning Growth — [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/116684-siphoning-growth/): “Destroy a friendly minion to gain 8 Armor.”

## Shared contract

Add a typed `DESTROY_MINION` effect, with typed target selectors `DAMAGED_ENEMY_MINION` and `FRIENDLY_MINION`. Execute's selector admits only an enemy minion with current Health below maximum Health. Siphoning Growth's selector admits any friendly minion, including undamaged minions. Both are explicit minion targets; neither can target heroes. Destruction sets the selected minion to lethal health and then uses the existing post-effect death stabilization, so deathrattles follow normal engine handling. Destruction is not damage and does not use damage attribution.

Siphoning Growth's composition is destroy friendly minion, then gain 8 Armor. Lack of an eligible friendly minion means there is no playable action. No death processing is introduced between steps.

## Reuse and boundaries

Reuse explicit-target action handles, effect composition, armor gain, minion death stabilization and existing deathrattle queue. Add no card-ID code and no dependencies, dynamic pools or observation fields. Exclude damage-result follow-ups, destruction triggers during the effect list, and cards with target replacement or death processing between effect steps.

## Verification

Native family scenarios check side/damaged target legality, minion-only targeting, exact destruction (not damage), Siphoning Growth's 8 Armor, deathrattle processing after the composition, and no-target legality. Adapter parity checks exported declarations and legal actions. No canonical rules evidence promotion is implied by this scoped prototype test.

## Expected gain

Two candidate roots, both declaration-driven under one reusable typed operation. No CUSTOM outliers.
