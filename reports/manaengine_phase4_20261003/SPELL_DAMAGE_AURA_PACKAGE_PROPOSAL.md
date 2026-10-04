# CAPABILITY PACKAGE PROPOSAL — `spell_damage_aura_v1`

Status: implemented and verified; see `SPELL_DAMAGE_AURA_COMPLETION_RECORD.md`.

## Semantic contract

Active, unsilenced board minions may contribute a numeric Spell Damage aura. A source with a damaged-only condition contributes only while current Health is below maximum Health. Spell Damage is computed from the caster's board when a spell begins resolving and applies to that spell's damage instructions; it does not modify Battlecry or combat damage. Existing damage/spell implementations must be regression-tested because this is a shared modifier.

## Reviewed candidate cards

| Card | Semantics | ManaEngine status before package | Package treatment |
|---|---|---|---|
| `CORE_EX1_012` Bloodmage Thalnos | Spell Damage +1; Deathrattle: draw a card | Unsupported | Root; includes the small generic draw-deathrattle operation, reusing existing draw and deathrattle processing. |
| `END_022` Time-Twisted Seer | Spell Damage +2 while damaged | Unsupported | Root; independent magnitude/condition variation on the shared aura. |

Two additional profile roots use related but distinct semantics and are deferred: `CATA_458` grants Spell Damage to spells in hand/deck; `CATA_487` tracks the first spell-damage event and gains Attack. Their state and timing contracts do not fit this aura package.

## Existing primitives

- Existing spell resolver and damage helpers cover targeted, composed, freeze, lifesteal, random-missile, and damage-plus-generation paths.
- Minion instances already track current/maximum Health and silence.
- FIFO death processing and `draw()` already exist.

## Required shared changes

- Add declarative static and damaged-only Spell Damage fields to `CardDefinition`.
- Derive current Spell Damage from the caster's unsilenced board and expose the visible value through `GameState`/encoder.
- Snapshot the modifier at spell-resolution start; apply it consistently to each supported spell damage operation, including random missiles. Keep non-spell effects unchanged.
- Add a generic parameterized draw-count deathrattle operation; test an independent fixture declaration with a different count so this is not a one-card special case.
- Declare both roots without card-ID behavior branches.

## Dependencies and risk

There is no external dynamic pool. Bloodmage draws from its own deck; this reuses ordinary draw/fatigue/hand-capacity behavior. No session or hero-class dependency is new. The main correctness risk is applying the modifier to the wrong effect class or recalculating it midway through one spell; focused scenarios will hold a single cast snapshot and verify that Battlecry/combat damage stays unchanged.

## Verification plan and expected reuse

- Native: static +1, damaged-only +2, undamaged state, damage/restore transition, silence/removal, simultaneous spell source damage snapshot, Spell Damage across existing spell families, no bonus to Battlecry/combat, draw deathrattle count and fatigue/hand-cap interactions, clone.
- Adapter/parity: public Spell Damage observation and encoder schema; private/hidden boundaries unchanged.
- Expected profile unlock: 2 declaration-only roots, 0 CUSTOM outliers. `CATA_458` and `CATA_487` remain deferred for separate capability proposals.
- No canonical Rosetta registry/evidence status changes and no training eligibility changes.
