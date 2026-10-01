# Standard capability pilot: Fortify (2026-10-01)

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

## Scope

Added `TLC_620` Fortify. It grants 3 Armor, then deals damage to a chosen enemy minion equal to the hero's current Armor. Its declaration uses the existing `ArmorTask` followed by a narrow `ARMOR_DAMAGE` task sequence (`GetGameTagTask(HERO, ARMOR)` and `DamageNumberTask(TARGET, spell damage)`). The generator only accepts that sequence for a targeted enemy-minion spell and requires a preceding explicit `ARMOR` effect. It also adds the enemy-target play requirement.

## Evidence

- Native scenario starts the hero at 2 Armor, casts Fortify, then confirms 5 Armor and 5 damage to an enemy Boulderfist Ogre, leaving it at 2 Health.
- Focused effect-composition suite: 31 cases / 199 assertions passed.
- Bridge smoke: Warrior Standard deck validation, session, opening hand, and legal actions passed.
- Standard registry tests: 14/14 passed.

## Limits and registry result

The test confirms this fixed case, not every Armor interaction or full-pool dependency closure. The registry has 1,185 roots: 167 direct and 113 generated registrations, 905 roots without detected rules registrations, 171 known non-root nodes, and 317 heuristic dynamic-pool signals. Complete closures and training-eligible roots remain zero; training stays blocked.
