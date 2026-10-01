# Core alias batch: five current Standard cards

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01  
Registry: `standard_registry_20261001_v1`

## Selection

This is a bounded batch-expansion check for the existing Core-alias generator. Five of the remaining metadata-linked Core copies were selected because each has a registered legacy CardDef, matching `countAsCopyOfDbfId`, exactly matching normalized rules text, resolvable fixed dependencies, and no detected dynamic pool:

| Current Standard card | Reused CardDef | Effect family |
|---|---|---|
| `CORE_BAR_812` Oasis Ally | `BAR_812` | Secret trigger; fixed Water Elemental summon |
| `CORE_BAR_878` Veteran Warmedic | `BAR_878` | Holy-spell trigger; fixed Medic summon |
| `CORE_BT_510` Wrathspike Brute | `BT_510` | After-attacked damage to all enemies |
| `CORE_EX1_559` Archmage Antonidas | `EX1_559` | Spell trigger; add Fireball |
| `CORE_WC_042` Wailing Vapor | `WC_042` | Elemental-play trigger; gain Attack |

The common capability is exact, metadata-linked reuse of an existing CardDef. The effects themselves are not claimed to be one shared gameplay mechanic. Aliases with text mismatches, absent source definitions, unresolved dynamic pools, or custom behavior remain outside this batch.

## Implementation and verification

- Added five entries to the explicit allowlist and versioned declaration; the generator validated all 26 aliases and emitted ordinary C++ CardDefs.
- Expanded the native CardDef parity table to all 26 declarations. Focused suite: **7 cases, 348 assertions passed**.
- Rebuilt the RosettaStone library and UnitTests executable; relinked the Python bridge.
- Bridge smoke passed for each of the five new aliases and the existing Crystal Merchant check: Standard deck validation, session setup, visible opening-hand identity, and legal-action enumeration.
- Re-ran after-attack draw, repeated-trigger draw, filtered-school draw, and alias verifiers against the new binary so their evidence fingerprints are current. Registry admission tests: **7 passed**.
- Authoring/review/debug minutes were not captured for this batch, so it adds a tested batch result but no valid manual-effort or automation-ROI measurement. Do not use it to claim a speedup.

## Registry result and limits

The five new cards are registered as `GENERATED_CORE_ALIAS`, but remain `IMPLEMENTED_UNVERIFIED`: parity with the exact legacy CardDef and bridge setup do not replace independent effect scenarios. The registry now reports 1,185 roots, 167 direct registrations, 38 generated registrations, 977 text-bearing roots without detected registrations, 113 known non-root nodes, nine current `VERIFIED_SCOPED` roots, zero complete root closures, and zero training-eligible roots. The batch changed registration inventory; it did not unlock training.

This supports adding several audited aliases in one pass. It does not support automatically applying the alias route to every remaining candidate: each still needs the same DBF, text, source, dependency, duplicate-owner, and binary checks.
