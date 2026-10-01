# Standard capability batch: after-attack damage

Date: 2026-10-01. Snapshot: `standard_registry_20261001_v1`.

## Change

Added `TLC_478` Axe of the Forefathers and `TLC_840` Gorishi Tunneler to the bounded after-attack trigger generator. After the hero attacks, Axe deals 1 damage to all minions. After Tunneler itself attacks, it deals 2 damage to the enemy hero. The route reuses RosettaStone's `AFTER_ATTACK` trigger with reviewed `HERO` and `SELF` sources and existing `DamageTask` selectors. The generator permits these new operations only for these exact allowlisted cards and amounts; this does not generalize them to arbitrary declarations.

## Evidence

- Native after-attack suite: **5 test cases / 42 assertions passed**. One independent scenario equips the Axe and checks that friendly and enemy minions each lose 1 Health. Another attacks with Tunneler and checks total enemy hero damage includes both the minion attack and its 2-damage trigger.
- Bridge smoke: Standard deck validation, session creation, opening hand and legal actions passed for both cards.
- Registry builder: 1,185 roots, 167 direct + 90 generated definitions, 928 text-bearing roots without detected registration, 158 known non-root nodes and 310 heuristic dynamic-pool signals. Complete closures and training-eligible roots remain zero.
- Fingerprinted after-attack evidence promotes all five cards in this trigger package to `VERIFIED_SCOPED` for the tested behavior. This remains scoped status, not full dependency closure or Standard admission.
- The registry still has zero complete closures and zero training-eligible roots. Focused behavior and bridge smoke do not close transitive dependencies or full Standard profile gates.

## Scope

The tested scenarios establish trigger timing and damage target sets for both cards in controlled game states. They do not test interactions with immunity, damage prevention, minion death effects, damage modifiers, or complete match behavior. Full Standard training remains blocked.
