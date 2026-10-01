# Standard capability pilot: Sizzling Cinder chain (2026-10-01)

## Scope

Added two registered Standard roots as one dependency package:

- `TLC_225` Cinderfin: its Deathrattle summons one `TLC_249` Sizzling Cinder.
- `TLC_249` Sizzling Cinder: its Deathrattle deals two 1-damage pings to random enemy entities. Each ping selects independently, so both may hit the same enemy.

The effect-composition generator gained the narrowly constrained `RANDOM_SPLIT_DAMAGE` operation. It is accepted only for a Deathrattle with exactly two pings. It uses RosettaStone's existing random-target damage tasks, repeated twice. The declared dependency is checked against the pinned Standard metadata and package ownership.

## Evidence

- Independent native scenario plays and destroys Cinderfin, checks the summoned Cinder's identity and stats, destroys it, then checks exactly two total health damage across the enemy hero and Boulderfist Ogre.
- Focused effect-composition suite: 32 cases / 209 assertions passed.
- Bridge smoke passed for both cards: Standard deck validation, Shaman session, opening hand, and legal actions.
- Standard registry tests: 14/14 passed.

## Limits and registry result

This scenario covers one death/summon chain and aggregate damage only. It does not test every target-selection edge, board-space limit, or Deathrattle interaction, and the registry does not yet consume this package's scenario output as fingerprinted `VERIFIED_SCOPED` admission evidence. Both roots remain `IMPLEMENTED_UNVERIFIED`; training stays blocked.

The registry contains 1,185 roots: 167 direct and 115 generated registrations, with 903 roots lacking detected rules registrations, 171 known non-root nodes, and 317 heuristic dynamic-pool signals. Complete dependency closures and training-eligible roots remain zero.
