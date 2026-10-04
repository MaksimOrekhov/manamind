# CAPABILITY PACKAGE PROPOSAL

## package_id

`manaengine_damage_target_owner_draw_v1`, proposal revision 1, 2026-10-04. Pinned input: `standard_full_20261001_v1`.

## semantic capability

Extend the typed one-packet damage follow-up contract with an unconditional `ALWAYS → DRAW_TARGET_OWNER` pairing. After one explicit-minion spell damage packet, capture the selected entity's original owner before the normal spell-resolution death stabilization, then draw one card for that player. Damage prevention does not suppress this textually unconditional follow-up. Capture ownership before the damage packet so subsequent removal from the board cannot change the recipient. No controller-change rule is added; if an effect transfers control or changes owner in the future, it needs separate admission review.

Classification: `REUSABLE_CAPABILITY`. The operation names an owner-relative draw and can be declared by any spell matching this contract. It uses the existing minion-target legal action, damage, draw/fatigue, and death-stabilization paths.

## existing RosettaStone primitives

Use ManaEngine's explicit-minion action, `deal_damage`, existing direct-spell damage evaluation/attribution, `CardInstance.owner`, `draw`, and outer `stabilize()`. RosettaStone remains an implementation reference only. The timing expectation comes from current official card wording and the generic spell-resolution rule documentation; no Conflagrate-specific client replay is available.

## candidate cards using the same semantics

| Root ID | Rules/source fingerprint | Contract parameters | Existing/new support | Review status |
|---|---|---|---|---|
| `FIR_954` Conflagrate | [Blizzard Card Library](https://hearthstone.blizzard.com/en-us/cards/115753/): deal 5 damage to a minion; its owner draws a card | damage 5; `ALWAYS`; `DRAW_TARGET_OWNER` | target/damage/draw exist; recipient capture and typed owner follow-up are new | official text; scoped current rules review; no replay |

Independent control variation: the native family tests exercise each legal target side and a lethal target with its own Deathrattle, so owner selection and resolution timing are tested without an additional production root.

## dependencies

No generated cards or random pools. No fixed dependencies. Dynamic dependency set is empty. On fatigue, the target owner takes the draw operation's ordinary fatigue damage under existing rules.

## required engine/generator changes

Extend `DamageOutcomeCondition` with `ALWAYS`; extend the typed follow-up enum with `DRAW_TARGET_OWNER`; validate only this allowed pair for `FIR_954`. Capture target owner from the board instance before applying damage, then call existing `draw(captured_owner, 1)`. Declaration changes only. No ID-specific branch, session field, or observation schema change.

## expected unlock count

One root, `FIR_954`. No dependencies. Profile admission and canonical evidence remain separate gates.

## test strategy

Cover both owner sides; lethal and surviving targets; Divine Shield prevention while retaining unconditional draw; an owner-side Deathrattle showing that the text follow-up resolves before normal outer death stabilization; target-owner fatigue. Native suite, adapter declaration check, generic ID guard, declaration validation, and `git diff --check`. Do not promote canonical evidence.

## custom outliers

None. Any later mechanics that change the selected minion's owner/controller during damage resolution are deferred and must not alter this bounded contract silently.

## Completion record

Implemented as part of `manaengine_damage_outcome_followup_v1`'s typed contract extension. `FIR_954` is the first declaration using `ALWAYS → DRAW_TARGET_OWNER`; all four cards use declarations only. No custom outliers. Shared changes were 2 enum values, generic typed validation, owner capture before damage, existing draw call, pybind/Python allowlist support, and the card declaration. No card-ID branch, schema change, or canonical evidence promotion.

Verification: full ManaEngine native suite PASS, 40 groups / 706 assertions; adapter suite PASS, 22 tests; generator identity guard and `git diff --check` PASS. The package-specific timer began at 2026-10-04 15:39:58 UTC, after the preceding checkpoint, and ended at 15:45:44 UTC: 5m46s observed active work. One build attempt; zero correction cycles.
