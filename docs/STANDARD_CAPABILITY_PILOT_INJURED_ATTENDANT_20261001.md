# Injured Attendant: self-damage with Lifesteal pilot

Date: 2026-10-01  
Card: `CATA_304` Injured Attendant (Priest, 3/8, Lifesteal)

## Implementation

Added the card to the allowlisted effect-composition generator. Its Battlecry runs `DamageTask(EntityType::SOURCE, 4, false)`, which applies the printed self-damage to the played minion. RosettaStone's existing Lifesteal behavior supplies the hero healing; no parallel healing effect was added.

## Verification

- Effect-composition generator: 23 allowlisted definitions generated.
- RosettaStone `UnitTests` build succeeded.
- Focused native suite: 23 cases, 156 assertions passed.
- Independent scenario confirmed the minion loses 4 Health, its controller heals for 4, and the opposing hero is unchanged.
- Bridge smoke: Standard deck validation, session, opening hand, and legal actions passed for Priest.
- Standard registry unit tests: 14/14 passed.

## Scope and remaining gaps

This scenario verifies the self-damage and Lifesteal result in a state where the hero can receive the full heal. It does not establish interactions with damage prevention, replacement effects, or a complete match/dependency profile. This registration does not make the root training-eligible; full Standard closure gates remain blocked.
