# CAPABILITY PACKAGE PROPOSAL

## package_id

`manaengine_damage_outcome_followup_v1`, proposal revision 1, 2026-10-04. Inputs: Phase 4D candidate ledger and pinned `standard_full_20261001_v1` card metadata.

## semantic capability

Proposed `DamageOutcomeFollowupV1`: a single targeted spell damage packet to one explicit minion, followed during the same spell resolution by one typed follow-up selected from the target's post-packet current Health. `MORTALLY_WOUNDED` means current Health is at or below zero; `SURVIVES` means it remains above zero. This check is made before the existing outer spell-resolution death stabilization, consistent with Mortal Coil's reviewed rules ruling that the draw condition checks mortal wounding before the minion physically dies. Spell Damage is evaluated by the existing direct spell packet path. If damage is prevented, the condition is evaluated from unchanged target Health. The target entity must still be present on the board; unsupported interruption/state fails closed.

Candidate declarations may choose only the reviewed follow-ups `DRAW_SELF` or `HEAL_ENEMY_HERO` with a positive fixed amount. No repeated packets, destruction follow-up, nested choice, target reselection, or general condition DSL is included. No shared death scheduler or global event ordering change is proposed.

Classification: `REUSABLE_CAPABILITY`. A matching future card can declare target, damage amount, outcome predicate, and typed follow-up without source branches.

## existing RosettaStone primitives

ManaEngine already has explicit-minion targeting, `deal_damage`, Spell Damage evaluation, direct-spell attribution, draw, hero healing, and the established outer `stabilize()` death boundary. These provide implementation hooks only. Rules evidence is based on current official Blizzard card text and the current Hearthstone rules reference, not on ManaEngine behavior.

## candidate cards using the same semantics

| Root ID | Rules/source fingerprint | Contract parameters | Existing/new support | Review status |
|---|---|---|---|---|
| `CORE_EX1_302` Mortal Coil | [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/69553-mortal-coil?class=warlock&rarity=common&set=core): deal 1 to a minion; if it dies, draw | damage 1; `MORTALLY_WOUNDED`; `DRAW_SELF` | explicit-minion damage and draw exist; outcome predicate is new | official text; [current rules reference](https://hearthstone.wiki.gg/wiki/Mortal_Coil) documents that Mortal Coil checks mortal wounding before physical death |
| `CORE_EX1_391` Slam | [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/69638-slam/): deal 2 to a minion; if it survives, draw | damage 2; `SURVIVES`; `DRAW_SELF` | explicit-minion damage and draw exist; outcome predicate is new | official text; survival is post-packet Health > 0 |
| `CATA_303` Purifying Breath | [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/122774/): deal 5 to a minion; if it dies, restore 5 Health to the enemy hero | damage 5; `MORTALLY_WOUNDED`; `HEAL_ENEMY_HERO(5)` | explicit-minion damage and hero healing exist; outcome predicate is new | official text; same reviewed lethal-health test as Mortal Coil |

Confirmed candidates above. `FIR_954` Conflagrate is excluded: “its owner draws” is unconditional and refers to the minion's owner, so it needs a distinct target-owner continuation contract and is not the same outcome package.

## dependencies

No generated cards or random pools. Fixed dependency set is empty. Target legality is an explicit enemy minion for these spells; target entity identity is captured from the legal action. Purifying Breath's follow-up target is always the opposing hero relative to the caster.

## required engine/generator changes

Add a strict typed outcome/follow-up contract to `CardDefinition` and declaration parsing. The engine performs one existing damage packet, checks the same target's current Health before outer stabilization, then applies only the declared follow-up. Validate allowed field combinations and reject unsupported values. Add no card-ID behavior branch; the 3 roots are declarations under one contract. The primary family supplies independent condition/follow-up variations. No observation schema or adapter action shape change is expected.

## expected unlock count

Three root IDs: `CORE_EX1_302`, `CORE_EX1_391`, `CATA_303`. No fixed dependency IDs. This is a scoped prototype gain only; no canonical evidence promotion or training/deck admission is implied.

Estimated effort: 15–25 minutes authoring, 15 minutes rules review, 20–35 minutes debugging and native/adapter verification, 5–10 minutes incremental build and evidence notes.

## test strategy

Independent native cases cover lethal/nonlethal target Health, exact trigger suppression on a surviving/dead inverse condition, Divine Shield prevention, Spell Damage crossing the lethal threshold, Purifying Breath healing only the enemy hero and clamping at 30, and preservation of existing death stabilization. Verify the follow-up occurs while a mortally wounded minion is still in the board zone and its death occurs at the established outer stabilization. Adapter tests verify all three declarations and reject invalid combinations. Run full native suite and focused/full adapter suite; run generic card-ID guard and `git diff --check`. No canonical artifact status is promoted.

## custom outliers

- `FIR_954` Conflagrate: defer to a separate damage-plus-target-owner-draw contract; it does not condition on damage outcome.
- Any damage effect with repeated packets, random targets, destroy-pending markers, or between-packet triggers is out of scope.

## Completion record

To be filled after implementation and verification.
