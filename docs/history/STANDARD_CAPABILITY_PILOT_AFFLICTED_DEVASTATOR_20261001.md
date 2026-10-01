# Afflicted Devastator: dual Battlecry and Deathrattle pilot

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01  
Card: `EDR_459` Afflicted Devastator (Warrior, 6/6)

## Implementation

Added the card to the strict effect-composition allowlist. Its Battlecry uses `DamageTask(EntityType::MINIONS_NOSOURCE, 3, false)` so it damages only the controller's other minions; its Deathrattle uses `DamageTask(EntityType::ENEMY_MINIONS, 3, false)`. The IR records those as separate `BATTLECRY_DAMAGE` and `DEATHRATTLE_DAMAGE` operations under an explicit dual-trigger activation. No pool dependencies are declared.

The first independent scenario exposed that `ALL_MINIONS_NOSOURCE` would hit both sides for the Battlecry. It was replaced by `MINIONS_NOSOURCE`, and the scenario now verifies a friendly minion takes 3 on play, the opposing minion is untouched by that Battlecry, and the opposing minion takes 3 only when Afflicted Devastator dies.

## Verification

- Effect-composition generator: 22 allowlisted definitions generated.
- RosettaStone `UnitTests` build succeeded using the configured Visual Studio developer environment.
- Focused native suite: 22 cases, 151 assertions passed.
- Bridge smoke: Standard deck validation, simulator session, opening hand, and legal actions passed for Warrior.
- Standard registry unit tests: 14/14 passed.

## Scope and remaining gaps

The focused scenario verifies the two fixed damage phases, side selection, and exclusion of the source from Battlecry damage. It does not prove all interaction ordering, board-full behavior, or the full dependency/action profile. The registry records this as an implemented registration, not as a completed Standard closure or training-eligible card. Full-pool training remains blocked.
