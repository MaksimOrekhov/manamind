# CAPABILITY PACKAGE PROPOSAL — `card_spell_damage_hand_deck_v1`

Status: completed as `card_spell_damage_hand_deck_v1` on the Phase 4 ManaEngine branch.

## Semantic contract

When a minion with this declared Battlecry is played, add its configured Spell Damage amount to every spell instance currently in its controller's hand and deck. Store the modifier on each individual `CardInstance`. It remains with that instance when drawn, survives cloning, and affects only that spell when cast; later spells still receive ordinary board Spell Damage. Cards that enter the hand/deck after the Battlecry are not retroactively modified. Non-spells are unchanged.

The player-visible SELF hand exports each spell's current Spell Damage. The deck's card identities and modifiers remain hidden; a modified spell carries its value into the visible hand only when drawn. No simulator bookkeeping enters observation.

## Reviewed candidate

| Card | Semantics | ManaEngine status | Treatment |
|---|---|---|---|
| `CATA_458` Archmage Kalec | Battlecry gives all hand/deck spells Spell Damage +1 | Unsupported | Root; parameterized card-instance modifier applied to the existing zones. |

## Existing primitives and changes

- Existing: internal deck/hand card instances, Battlecry lifecycle, per-instance cloning, static/aura Spell Damage snapshots, player-visible ordered SELF hand and encoder schema migration gate.
- New shared surface: typed hand/deck spell-damage grant parameter; persistent per-instance Spell Damage modifier; current Spell Damage in card/action observation and the numeric entity encoder.
- No card-ID branch. A native test fixture with a different configured amount validates the universal parameter contract.

## Dependencies, scope, and risks

- Fixed dependencies and dynamic pools: none.
- No class/session/action-type changes. Observation schema increased from 12 to 13 because SELF hand cards gain a numeric current Spell Damage feature; old checkpoints continue to reject incompatible schemas.
- Correctness risks: modifying minions or later-drawn generated spells, losing the modifier across draw/clone, omitting card-specific Spell Damage from a cast snapshot, or accidentally disclosing deck identities.
- Shatter fragments are spells and therefore are modified independently when present in hand/deck. Recombination must preserve the sum of the two instance modifiers, consistent with its existing per-instance enchantment/counter merge.

## Verification and expected delta

- Native scenarios: hand + deck spell modifiers, later draw, non-spell exclusion, clone divergence, combining base aura and per-card Spell Damage, Shatter fragment merge, and parameter variation.
- Adapter/schema checks: modified SELF hand value is visible and encoded, opponent/deck identities stay hidden, schema 13 is enforced, and play action descriptors report the modifier.
- Expected: +1 ManaEngine-supported profile root, 0 external dependencies, 0 CUSTOM outliers, no canonical Rosetta registry or training eligibility change.
- Observed: 1 declaration-only profile consumer, 0 CUSTOM outliers, 0 dependencies, 0 canonical registry changes. Native suite: 28 scenario groups / 482 assertions. Adapter and focused state/schema checks: 14 passed.
