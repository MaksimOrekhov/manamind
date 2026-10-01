# Simple damage Battlecry package — 2026-10-01

## Scope

Added two Core minions that had current Standard metadata but no detected CardDef registration:

| Card | Expected effect | Implementation |
|---|---|---|
| `CORE_UNG_084` Fire Plume Phoenix | Battlecry deals 3 damage to the selected valid target | `DamageTask(TARGET, 3, false)` plus `REQ_TARGET_IF_AVAILABLE` and `REQ_NONSELF_TARGET` |
| `CORE_OG_149` Ravaging Ghoul | Battlecry deals 1 damage to all other minions | `DamageTask(ALL_MINIONS_NOSOURCE, 1, false)` |

Both declarations use the existing bounded effect-composition generator. Its allowlist now includes these IDs; the generator additionally rejects ownership by another generated manifest. `ALL_MINIONS_NOSOURCE` is a selector added to the reviewed target mapping, not a general user-extensible rules language.

## Verification

- Native focused suite: 6 cases, 30 assertions passed. The two new scenarios assert target damage and damage to both friendly/opponent minions while excluding the source minion.
- Bridge smoke: both cards passed Standard deck validation, session creation, opening hand visibility, and legal-action enumeration.
- Standard registry tests: 9 passed.
- Updated inventory: 1,185 roots; 167 direct + 58 generated registrations; 957 text-bearing roots without detected registration; 127 known non-root nodes; 306 heuristic pool signals; zero complete dependency closures and zero training-eligible roots.

## Limits

The native scenarios validate the declared effect in representative board states. Bridge smoke checks loading and action availability, not every target state or match interaction. These cards stay `IMPLEMENTED_UNVERIFIED`; full-profile admission still needs current fingerprinted evidence, dependency closure, complete action audit, and full-pool session/match gates.
