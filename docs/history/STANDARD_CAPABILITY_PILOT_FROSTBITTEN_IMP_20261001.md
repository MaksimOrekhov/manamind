# Frostbitten Imp: self-freeze Battlecry

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01  
Card: `CATA_612` Frostbitten Imp (2-cost Neutral minion)

## Implementation

Added the fixed Battlecry to the effect-composition allowlist as `FREEZE(SOURCE)`. The generator permits `SOURCE` for this explicit operation; no target-selection requirement or external dependency is added.

## Verification

- Effect-composition generator emitted 28 definitions.
- Focused native suite: 28 cases, 181 assertions passed. The new scenario confirms the played minion is frozen and the opposing hero is not.
- Bridge smoke passed Standard deck validation, session creation, opening-hand loading, and legal-action enumeration.
- Standard registry tests: 14/14 passed.

## Scope and remaining gaps

This checks the self-freeze on play. It does not verify later-turn thawing and attack eligibility across a complete match; full Standard dependency and training gates remain outstanding.
