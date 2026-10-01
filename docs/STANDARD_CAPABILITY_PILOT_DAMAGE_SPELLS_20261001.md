# Damage spell package — 2026-10-01

## Scope

Added three Core spells with no detected CardDef registration:

| Card | Expected effect | Generated operations |
|---|---|---|
| `CORE_CS2_024` Frostbolt | Deal 3 spell damage to a selected character and Freeze it | `DAMAGE(TARGET, 3, spell_damage=true)`, `FREEZE(TARGET)` |
| `CORE_CS2_094` Hammer of Wrath | Deal 3 spell damage to a selected character and draw a card | `DAMAGE(TARGET, 3, spell_damage=true)`, `DRAW(1)` |
| `CORE_EX1_129` Fan of Knives | Deal 1 spell damage to all enemy minions and draw a card | `DAMAGE(ENEMY_MINIONS, 1, spell_damage=true)`, `DRAW(1)` |

These declarations extend the existing bounded effect-composition generator with one allowlisted `FREEZE` operation and one `ENEMY_MINIONS` selector. The generator validates exact fields, allowlisted IDs, metadata/card type, catalog fingerprint, declared dependencies, generated ownership, and supported operations. No dynamic pool is claimed complete; draw outcomes remain deck-dependent.

## Verification

- Native scenario suite: 9 cases, 46 assertions passed. New expectations cover damage plus freezing, damage plus draw, and damage to all enemy minions while a friendly minion remains undamaged.
- Bridge smoke passed for these three spells and the two Battlecry cards in the same effect-composition package.
- Standard registry suite: 9 tests passed.
- Registry after the package: 1,185 roots; 167 direct + 61 generated registrations; 954 text-bearing roots without detected registration; 127 known non-root dependency nodes; 306 heuristic dynamic-pool signals; zero complete root closures; zero training-eligible roots.

## Limits

Native cases cover selected representative states, not all spell-damage interactions, board edge cases, draw outcomes, or full matches. The five effect-composition additions remain `IMPLEMENTED_UNVERIFIED` pending current fingerprinted evidence and full-pool dependency/action/session gates.
