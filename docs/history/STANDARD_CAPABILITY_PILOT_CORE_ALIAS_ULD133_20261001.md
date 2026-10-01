# Bounded Core alias reuse check: Crystal Merchant

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01  
Registry snapshot: `standard_registry_20261001_v1`  
Status: **alias registration and fingerprinted scoped evidence are integrated**

## Hypothesis and source review

`CORE_ULD_133` Crystal Merchant can reuse the registered `ULD_133` CardDef because the pinned Core and legacy metadata have the same normalized rules text, `countAsCopyOfDbfId` points to the legacy DBF, and the source CardDef is narrowly composed from `TURN_END`, `IsUnspentMana()`, and `DrawTask(1)`. The source has no literal card dependencies or detected dynamic pools.

This exercises the existing bounded alias generator; it does not add a new reusable capability or establish general safety for the remaining Core candidates.

## Changes

- Added `CORE_ULD_133 -> ULD_133` to `scripts/generate_core_card_aliases.py` and `integrations/rosettastone/card_rules/core_aliases.v1.json`.
- Regenerated the alias CardDef and manifest. The generator accepted 21 explicitly allowlisted aliases; two manifests entries still report unresolved dynamic pools.
- Added the ID to the generic CardDef parity test and added a direct Core behavior scenario: it draws on turn end with unspent mana and does not produce an extra draw when all mana was spent.
- Updated an existing Sunfury Protector assertion from the retired `CS2_182` identity to the current `CORE_CS2_182` card ID. This fixed the only failure in the focused alias test group.
- Added `scripts/verify_core_alias_uld133.py` and `core_aliases.evidence.json`; the verifier checks that the generated manifest matches both the current Standard catalog and the registry snapshot's normalized rules text, runs the focused native suite and bridge smoke, and records declaration/generator/manifest/header/source/capability/library/executable/bridge/CMake-cache fingerprints plus revision and dirty-tree identity.
- Updated `scripts/build_standard_registry.py` to promote only aliases whose exact evidence fingerprints are current. Evidence for one alias does not promote the other 20 entries.

## Verification

- Core alias focused native group: **7 test cases, 288 assertions passed**; 2,518 unrelated cases skipped.
- The new Crystal Merchant scenario also passed individually (1 case, 3 assertions).
- Engine library relink and bridge module relink succeeded. Bridge smoke for `CORE_ULD_133` passed Standard deck legality, session creation, visible opening-hand identity, and legal-action enumeration.
- The two earlier generator package verifiers were rerun after the library fingerprint changed: after-attack/draw passed 3 cases and 25 assertions plus all 3 bridge smokes; repeated-trigger passed 4 cases and 34 assertions, with the documented Death Knight setup limit.
- Registry rebuild now reports 1,185 roots, 105 known non-root nodes, 300 heuristic dynamic-pool candidate signals under detector v2 (282 Standard roots and 2 dependency origins), 167 direct registrations, 31 generated registrations and 984 text-bearing roots without detected registration. Detector v2 filters known board-target/fixed-token/give-buff false-positive classes, but is neither exhaustive nor a verified pool inventory. Seven roots are `VERIFIED_SCOPED`; Crystal Merchant is current only for the documented native/bridge scope. No root closure is complete and training remains blocked.

## Measurement and limits

The incremental engine/library build call took about 5.6 seconds and the UnitTests-only rebuild about 4.1 seconds on this machine. These timings do not include authoring, review, test startup, bridge smoke, or the failed broad alias run before correcting the stale Sunfury expectation. Total authoring time and a manual baseline were not measured, so no labor-saving claim is made.

The test validates one specific Core alias. It does not verify all modes of Crystal Merchant, deck exhaustion/overdraw behavior, generated dependencies for the alias family, the remaining aliases, pool closure, deck-level correctness, or training readiness. The alias registration remains a proposal tied to exact text/DBF/source checks, not a full dependency proof.
