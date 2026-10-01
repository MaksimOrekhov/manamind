# Fixed healing composition pilot

Date: 2026-10-01  
Cards: `CORE_CFM_604`, `EDR_476`, `EDR_971`

## Implementation

Extended the allowlisted effect-composition IR with `HEAL(target, amount)`, compiled to RosettaStone's existing `HealTask`. Added exact recipient selectors for a validated friendly target, all friendly characters, and both heroes.

- `CORE_CFM_604` Greater Healing Potion: heal the selected friendly character for 12, then draw one card. Its declaration requires both a target and a friendly target.
- `EDR_476` Moonwell: deal 4 spell damage to all enemy characters and restore 4 Health to all friendly characters.
- `EDR_971` Critter Caretaker: at the controller's turn end, restore 3 Health to both heroes.

## Verification

- Effect-composition generator: 26 allowlisted definitions generated.
- RosettaStone `UnitTests` build succeeded.
- Focused native suite: 26 cases, 171 assertions passed.
- Bridge smoke passed Standard deck validation, session creation, opening-hand loading, and legal-action enumeration for all three new cards.
- Standard registry unit tests: 14/14 passed.

## Scope and remaining gaps

Scenarios verify the selected healing recipients, fixed amounts, draw side effect, enemy damage, and end-of-turn timing. They do not cover every healing replacement/prevention interaction or full dependency and match gates. The generated registrations remain ineligible for full-pool training until the registry's profile gates pass.
