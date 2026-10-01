# Standard package: exact-text CardDef reuse

Date: 2026-10-01. Pool snapshot: `standard_registry_20261001_v1`.

## Change

Extended the existing audited alias generator with eight explicit current-Standard-to-registered-CardDef mappings:

| Standard root | Reused CardDef | Rule family |
|---|---|---|
| `CORE_AT_052` Totem Golem | `EX1_247` | Overload metadata |
| `CORE_WON_096` Dark Peddler | `LOE_023` | Battlecry Discover |
| `CORE_WON_337` Ironforge Portal | `KAR_091` | Armor and random minion summon |
| `Core_LOE_115` Raven Idol | `LOE_115` | Choose One / Discover |
| `Core_UNG_072` Stonehill Defender | `ULD_195` | Taunt and Battlecry Discover |
| `TIME_603` Ticking Timebomb | `REV_251` | Deathrattle destroy random enemy minion |
| `TIME_720` Soldier of the Bronze | `ULD_189` | Taunt and double Health |
| `TLC_483` Vault Breaker | `ULD_309` | After-Discover cost reduction |

The route requires explicit allowlisting, membership in the pinned Standard root pool, collectible current metadata, a registered base CardDef, exact normalized rules-text equality, no direct target definition or competing generated owner, and resolvable literal source dependencies. The manifest records whether a mapping came from a linked DBF, derived Core ID or exact-text review. This does not infer mappings dynamically.

## Evidence

- Generator: **64 total aliases**, including the eight additions. Fourteen entries have unresolved dynamic-pool signals.
- Native parity: **1 focused test / 768 assertions passed** across all 64 mappings.
- Bridge smoke: all eight new roots passed Standard deck validation, session creation, opening hand and legal-action enumeration.
- Registry builder and focused suite: **14/14 passed**. Current inventory: 1,185 roots, 167 direct + 102 generated registrations, 916 text-bearing roots without detected registration, 171 known non-root nodes, 317 heuristic dynamic-pool signals, 6 current `VERIFIED_SCOPED` roots, 5 historical stale-evidence entries, 0 complete root closures and 0 training-eligible roots.

## Limits

Exact text and CardDef parity establish a bounded registration path, not independent semantic verification. The Discover and random-minion aliases retain unresolved pool dependencies; Vault Breaker and other trigger mappings need scenario coverage. All eight new entries remain `IMPLEMENTED_UNVERIFIED`, and the Standard training gate remains blocked.
