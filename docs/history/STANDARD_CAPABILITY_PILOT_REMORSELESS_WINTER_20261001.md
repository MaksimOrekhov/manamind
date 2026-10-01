# Remorseless Winter: fixed enemy-wide damage and draw

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Date: 2026-10-01  
Card: `RLK_709` Remorseless Winter (Death Knight spell)

## Implementation

Added an allowlisted composition: deal 2 spell damage to all enemy characters, then draw one card. The declaration uses the existing `ENEMIES` selector, `DamageTask`, and `DrawTask`; it adds no token or pool dependency.

## Verification

- Effect-composition generator emitted 27 definitions.
- Focused native suite: 27 cases, 177 assertions passed. The independent scenario verifies damage to the enemy hero and minion and the draw.
- Standard deck validation passed for a Death Knight deck.
- Bridge session/opening-hand/action smoke is not available for Death Knight because the known DK setup gap remains; this card is not counted as having passed that gate.
- Standard registry unit tests: 14/14 passed.

## Scope and remaining gaps

This verifies the fixed spell effect in a native scenario and Standard deck legality. It does not establish Death Knight bridge session support or full-pool dependency, action, and match gates; the card remains ineligible for full-pool training.
