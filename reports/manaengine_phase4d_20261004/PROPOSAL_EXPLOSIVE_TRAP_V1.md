# Capability proposal: enemy-area Secret damage v1

## Package

`manaengine_enemy_area_secret_damage_v1`, profile `standard_full_20261001_v1`, base `43aadac`.

## Reviewed card

`CORE_EX1_610` Explosive Trap — [Blizzard Card Library](https://hearthstone.blizzard.com/en-gb/cards/585-explosive-trap?class=hunter&collectible=1&set=classic&viewMode=grid): “Secret: When your hero is attacked, deal 2 damage to all enemies.” The pinned Core card metadata carries the same text. The rules documentation cross-check reports that direct-damage Secrets use current Spell Damage when they trigger; this is supporting rules evidence, not an official Blizzard rules statement.

## Contract

Reuse the existing `FRIENDLY_HERO_ATTACKED` Secret window. Add one typed `ENEMY_AREA_DAMAGE` Secret effect, with positive base `damage` from the declaration. At resolution, snapshot the Secret owner's living enemy minions and opposing hero, evaluate base amount plus current Spell Damage on the Secret owner's board, and route each packet through existing `deal_damage` as direct spell damage. This can update existing direct-spell damage counters/attack reactions. Death processing remains at the existing attack boundary.

The trigger occurs when an opposing character attacks the Secret owner's hero. Its effect does not cancel the attack merely because an attacker survives; a minion killed before combat should no longer perform that attack under the existing attack resolution contract.

## Scope/risk

No new scheduler, action, observation or session state. No random/dynamic dependencies. The implementation is a generic typed Secret effect, not a card-ID branch. Exact Secret-to-Secret interleaving remains whatever the established activation-sequence Secret window already implements; this package will test one active Explosive Trap at a time and will not claim broader multi-Secret parity.

## Verification

Native tests will cover attack-trigger legality/timing, all-enemy target set, Spell Damage measured at trigger time, attack cancellation when the attacking minion dies, and secret consumption. Adapter tests will validate the declaration and public legal actions. Confidence remains scoped; no canonical registry evidence is promoted.
