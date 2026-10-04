# CAPABILITY PACKAGE PROPOSAL — `spell_damage_event_attack_v1`

Status: implemented and verified on 2026-10-04; see `SPELL_DAMAGE_EVENT_ATTACK_COMPLETION_RECORD.md`.

## Semantic contract

An active friendly `spell_damage_event_attack_v1` source observes spell-attributed damage events while it is on board. On its first qualifying event during its controller's current turn, it gains the declared Attack amount once. Events before the minion entered play do not count. Each active source instance tracks its own turn stamp, so two Raincallers both react to the first spell-damage event they see. Damage from a non-spell source is excluded. Counterspelled spells and effects that deal no damage do not create a qualifying event.

The prototype's supported spell resolution path reports qualifying damage after target prevention/mitigation and before the normal post-action stabilization loop. For character targets, Armor absorbs damage as part of the damage packet; the tracked dealt amount follows the existing engine damage routine. This package does not add a general event dispatcher or change trigger/death ordering.

## Reviewed candidate

| Card | Semantics | ManaEngine status | Treatment |
|---|---|---|---|
| `CATA_487` Raincaller | First spell-damage event observed while active each turn grants +2 Attack | Unsupported | Root; one generic per-instance event observer with declarative Attack amount. |

`CATA_452` Spellweaver's Brilliance uses cumulative spell damage to modify held-card cost and summons a fixed token. It is deferred to a separate package until its token dependency and discount boundary have a local pinned-source record. No other profile root shares Raincaller's exact effect contract.

## Existing primitives and changes

- Existing: spell resolution, target damage functions, Spell Damage snapshot, minion Attack state, turn counter, clone of full engine state.
- New shared surface: explicit attribution of positive damage to the spell currently resolving; a per-instance last-triggered-turn stamp; typed source declaration and an Attack amount parameter.
- No card-ID behavioral branch. A test-only second declaration with another Attack amount and two active instances will verify the parameterized contract.

## Dependencies, pools, and risks

- Fixed dependencies: none. Dynamic pools: none.
- No class, session, or new action/observation fields. Internal trigger stamps are not exported.
- Main correctness risks: accidentally counting Battlecry/Secret/combat damage, counting countered/no-op spells, processing repeated damage packets more than once for a source in one turn, and handling multiple source instances independently.
- The source rule is pinned card text; Blizzard's 35.4 patch notes also document a fix so Raincaller does not gain stats from Deathwing's non-spell Raze ability: https://hearthstone.blizzard.com/en-us/news/24266874/35-4-patch-notes.

## Verification plan and expected delta

- Focused native scenarios: spell damage after Raincaller is active; a prior spell before play; two copies react independently; non-spell damage exclusion; countered and zero-damage spell exclusion; turn stamp permits a later turn; clone divergence; Spell Damage modified packet.
- Adapter/action checks: Raincaller gains +2 Attack in the observable board state and attack action descriptors reflect it.
- Expected: +1 ManaEngine-supported profile root, 0 external dependencies, 0 CUSTOM outliers, no canonical registry or training eligibility change.
- Estimate: modest shared change (damage attribution threaded through spell-resolution result paths plus a typed per-instance hook); one native/bridge build and family validation pass.
