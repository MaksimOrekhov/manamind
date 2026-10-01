# Voltaic Burst static summon — 2026-10-01

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Added `CORE_BOT_451` Voltaic Burst to the allowlisted composition route. It summons two existing `BOT_102t` Spark minions; the pinned card metadata supplies Overload 1, while the token metadata supplies its 1/1 stats, Elemental race, and Rush mechanic. The generator permits a dependency without a separate CardDef only for a noncollectible MINION whose sole mechanic is RUSH and whose complete text consists of the Rush keyword label. All other text-bearing dependencies still require an active source CardDef.

## Verification

- Native scenario confirmed two 1/1 Elemental Rush minions and one Overload owed: included in the 13-case / 82-assertion effect-composition suite.
- Bridge smoke passed Standard deck validation, session creation, opening-hand visibility and legal-action enumeration for `CORE_BOT_451`; the same run passed all nine composition cards.
- Latest registry: 1,185 roots; 167 direct + 85 generated registrations; 933 text-bearing roots without detected registration; 158 known non-root nodes; 310 heuristic dynamic-pool signals; zero complete root closures and zero training-eligible roots.

## Limits

`CORE_BOT_451` remains `IMPLEMENTED_UNVERIFIED`. Its fixed token edge is recorded but not independently reviewed for full dependency closure. The scenario does not establish all board-capacity or interaction cases, and the training profile remains blocked.
