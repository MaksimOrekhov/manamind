# Spirit Bomb composition — 2026-10-01

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Added `CORE_BOT_222` Spirit Bomb to the bounded effect-composition route. Its CardDef requires a minion target, deals 4 spell damage to that minion, then deals 4 spell damage to its controller's hero. The operation list uses existing `DamageTask` behavior; no new runtime mechanic was added.

## Verification

- Native scenario confirmed the enemy minion lost 4 Health and the casting hero lost 4 Health.
- Full effect-composition native suite: 12 cases / 71 assertions passed.
- Bridge smoke passed for all eight cards owned by this composition route, including Standard deck validation, session creation, opening hand and legal actions.
- Registry tests: 10 passed. Latest registry: 1,185 roots; 167 direct + 81 generated registrations; 157 known non-root nodes; 310 heuristic pool signals; 934 text-bearing roots without detected registration; zero complete closures and zero training-eligible roots.

## Limits

Spirit Bomb remains `IMPLEMENTED_UNVERIFIED` in the full-pool registry. The scenario does not cover interactions with Spell Damage bonuses or all target/death outcomes; full Standard closure and training gates remain blocked.
