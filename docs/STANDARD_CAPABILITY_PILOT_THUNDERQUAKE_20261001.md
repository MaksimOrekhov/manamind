# Standard capability pilot: Thunderquake (2026-10-01)

## Scope

Added `TIME_215` Thunderquake. It deals 1 spell damage to all minions, then adds `TIME_218` Static Shock to its controller's hand. The bounded composition now has an explicit `ADD_TO_HAND` operation for a declared, registered Standard spell dependency. Dependencies may refer to another card in the same validated composition package; the package still checks exact membership, current metadata, single ownership, and complete effect references before generation.

The dependency is `TIME_218`, added in the preceding pilot. No general card-discovery, copy, or random-generation behavior is implied by this operation.

## Evidence

- Independent native scenario confirms one damage to both friendly and enemy minions, unchanged hand size after the spell replaces itself with Static Shock, and the exact `TIME_218` ID in hand.
- Full focused effect-composition suite: 30 cases / 194 assertions passed.
- Bridge smoke: Standard deck validation, Shaman session, opening hand, and legal actions passed.
- Standard registry tests: 14/14 passed.

## Limits and registry result

This is scoped behavior evidence, not complete interaction, dependency-closure, or training evidence. The registry contains 1,185 roots: 167 direct and 112 generated registrations, 906 roots without detected rules registrations, 171 known non-root nodes, and 317 heuristic dynamic-pool signals. Complete closures and training-eligible roots remain zero; training stays blocked.
