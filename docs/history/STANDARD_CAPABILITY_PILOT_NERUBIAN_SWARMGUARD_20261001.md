# Nerubian Swarmguard self-summon — 2026-10-01

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Added `CORE_RLK_062` to the allowlisted effect-composition generator as a narrow self-reference case. Its Battlecry summons two more copies of the same 1/3 Taunt minion. A self-reference is allowed only for this explicit ID; other text-bearing dependencies still need a reviewed source CardDef or the specifically checked metadata-only Rush-token contract.

## Verification

- Native scenario played the card in a test game and confirmed three 1/3 Taunt Nerubians: included in the 14-case / 93-assertion composition suite.
- Bridge deck validation passed for a Standard Death Knight list containing `CORE_RLK_062`.
- The combined bridge verifier intentionally skips match session creation for Death Knight because the engine still lacks default Death Knight hero and hero-power mappings.
- Latest registry: 1,185 roots; 167 direct + 86 generated registrations; 932 text-bearing roots without detected registration; 158 known non-root nodes; 310 heuristic dynamic-pool signals; zero complete root closures and zero training-eligible roots.

## Limits

`CORE_RLK_062` remains `IMPLEMENTED_UNVERIFIED`. Native behavior was exercised under a Warrior test session because standard Death Knight game setup is unavailable. Deck legality is confirmed, but DK session/action and match gates remain open.
