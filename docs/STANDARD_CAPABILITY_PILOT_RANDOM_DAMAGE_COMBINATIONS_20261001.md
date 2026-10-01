# Standard capability pilot: random damage combinations (2026-10-01)

## Scope

Added two roots using the shared fixed `RANDOM_DAMAGE` operation:

- `EDR_110` Sporegnasher: its Deathrattle deals 1 damage to a random enemy minion. The native scenario confirms its Poisonous keyword is present, while its separate Deathrattle ping deals only 1 and does not destroy a 7-health minion.
- `CATA_485` Sleet Storm: deals 2 spell damage to a selected target and 1 spell damage to a random enemy minion. The declaration adds only `REQ_TARGET_TO_PLAY`; its two damage events are separate.

The generator now permits the previously scoped `RANDOM_DAMAGE` operation in Deathrattle activation, still requiring an explicit fixed target set, amount, hit count, and Spell Damage flag.

## Evidence

- Native Sporegnasher scenario verifies the Poisonous metadata tag, Deathrattle source execution, exactly 1 health damage to the random enemy minion, and no damage to the enemy hero.
- Native Sleet Storm scenario verifies exactly 3 aggregate damage to enemy minions across the selected and random damage events, with no friendly hero damage.
- Focused effect-composition suite: 36 cases / 236 assertions passed.
- Bridge smoke passed for both cards: Standard deck validation, session, opening hand, and legal actions.
- Standard registry tests: 14/14 passed.

## Limits and registry result

These cases do not cover all targeting restrictions, empty enemy boards, immunity, damage triggers, or dependency closure. The registry does not consume these scenarios as fingerprinted `VERIFIED_SCOPED` admission evidence. Both roots remain `IMPLEMENTED_UNVERIFIED`; training stays blocked.

The registry contains 1,185 roots: 167 direct and 119 generated registrations, with 899 roots lacking detected rules registrations, 171 known non-root nodes, and 317 heuristic dynamic-pool signals. Complete dependency closures and training-eligible roots remain zero.
