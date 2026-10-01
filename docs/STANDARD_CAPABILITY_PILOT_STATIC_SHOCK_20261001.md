# Standard capability pilot: Static Shock (2026-10-01)

## Scope

Added `TIME_218` Static Shock to the bounded effect-composition route. The current pinned rules text is “Deal 1 damage to a minion. Give your hero +1 Attack this turn.” The declaration composes the existing targeted `DamageTask` with the already registered one-turn `BTA_02pe` hero-attack enchantment. Its only declared dependency is that enchantment; the generator validates the dependency against RosettaStone metadata and registration.

This is one card, not a general hero-attack capability expansion. The route remains allowlisted and training-disabled.

## Evidence

- Native scenario: the selected enemy minion loses 1 Health and the caster's hero gains exactly 1 Attack.
- Focused effect-composition suite: 29 cases / 185 assertions passed.
- Bridge smoke: Standard deck validation, session creation, opening hand, and legal actions passed for `TIME_218`.
- Standard registry tests: 14/14 passed.

## Limits and registry result

These checks establish scoped effect behavior and bridge availability, not all interactions, the complete generated dependency closure, or training eligibility. The registry has 1,185 roots: 167 direct and 111 generated registrations, 907 roots without detected rules registrations, 171 known non-root nodes, and 317 heuristic dynamic-pool signals. Complete closures and training-eligible roots remain zero; pooled training stays blocked.

The normal `pyRosetta` relink in the RosettaStone build tree still fails because its configured linker cannot find `python312.lib`. The UnitTests executable and the separate ManaMind bridge were rebuilt successfully against the updated `RosettaStone.lib`, and the verification script used that bridge successfully.
