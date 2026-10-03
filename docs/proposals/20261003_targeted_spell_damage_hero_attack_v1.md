# CAPABILITY PACKAGE PROPOSAL — `targeted_spell_damage_hero_attack_v1`

Revision 1 — 2026-10-03. Inputs: `standard_full_20261001_v1`, `standard_registry_20261001_v1`, and `meta_training_20261002_v1`.

## Package decision

Proceed as a verification-focused package using the existing effect-composition contract. Both root declarations already exist. This package adds no card-ID behavior and is expected to need no shared Python/C++ implementation changes. It will establish independent family evidence for two roots appearing in three frozen decks.

## Semantic capability

Contract: `targeted_spell_damage_with_temporary_hero_attack`, version 1, implementation kind `GENERIC` by composition of existing allowlisted operations.

On spell resolution, deal 1 spell damage to the selected target, then grant the controller's hero +1 Attack until end of the current turn. Target legality is a declared card parameter:

- `END_007` (`Press the Advantage`) may target a character. Its text says “Deal 1 damage” without restricting the target to a minion; the existing independent native scenario targets the opposing hero.
- `TIME_218` (`Static Shock`) may target minions only. The pinned text explicitly says “to a minion”; its declaration includes `REQ_MINION_TARGET`.

`END_007` then draws one card and grants one Armor. It is the independent control variation with extra declarative effects. `TIME_218` has no draw or Armor effect. Damage uses spell damage rules. The enchant expires at end of turn.

## Existing RosettaStone primitives

- `DamageTask(EntityType::TARGET, 1, true)`
- `AddEnchantmentTask("BTA_02pe", EntityType::HERO)`
- `DrawTask(1)` and `ArmorTask(1)` for `END_007`
- `REQ_TARGET_TO_PLAY` and optional `REQ_MINION_TARGET`
- Strict effect-composition declaration validation and shared renderer

The declarations are in `integrations/rosettastone/card_rules/effect_composition.v1.json`; current native code is generated in `ManaMindEffectCompositionGen.cpp`. Existing independent native cases already cover `END_007` against the enemy hero and `TIME_218` against an enemy minion. This package must add missing negative-target and enchant-lifetime assertions before evidence is recorded.

## Candidate roots

| Root ID | Card | Target parameters | Current support | Review |
|---|---|---|---|---|
| `END_007` | Press the Advantage | Any character; damage, temporary hero attack, draw 1, Armor 1 | Existing effect-composition declaration; no current rules evidence in Meta Profile scope | In scope |
| `TIME_218` | Static Shock | Minion only; damage and temporary hero attack | Existing effect-composition declaration; no current rules evidence in Meta Profile scope | In scope |

Profile impact: `END_007` appears in Elise Attack Druid and Galaxy Brain Raza Demon Hunter; `TIME_218` appears in Wanted Mug Shaman. These two roots advance three decks.

## Dependencies

- `BTA_02pe`, the existing temporary +1 hero Attack enchantment. Confirm its exact effect and turn-end expiry independently in the focused native scenario.
- No card-generated outcomes or dynamic pools. This package does not claim full closure for either deck.

## Required implementation changes

- No engine, bridge, generator, declaration or generated card changes are expected.
- Add focused independent native coverage for both target contracts, rejection of a hero target by `TIME_218`, and end-of-turn expiry of `BTA_02pe` while retaining the existing `END_007` draw/Armor expectations.
- Add a bridge/action parity check that observes the correct legal target set for both cards and confirms current attack before and after turn end.
- If either target contract cannot be demonstrated without a card-ID behavior branch, stop and reclassify the affected behavior CUSTOM.

## Expected unlock count

- Newly registered roots: 0; both declarations already exist.
- Roots targeted for new current scoped rules/action evidence: 2 (`END_007`, `TIME_218`).
- Affected frozen decks: 3.
- `BTA_02pe` remains a separately reviewed dependency; registry closure and training eligibility remain blocked until its edge and all other reachable outcomes are reviewed.

## Test strategy

1. Native family scenario for `END_007`: select the enemy hero, deal exactly 1 damage, gain 1 hero Attack and 1 Armor, and draw one card.
2. Native family scenario for `TIME_218`: select a minion, deal exactly 1 spell damage and gain 1 hero Attack; a hero is not a legal target.
3. For the shared enchant, assert Attack is +1 during the turn and returns to baseline after turn end.
4. With no minions on either board, confirm the minion-only card has no legal target.
5. Bridge parity: loaded configured bridge, legal actions for the actual cards, current hero Attack observations and expiry after end turn.
6. Run focused native scenarios, effect-composition declaration/source ownership checks, bridge parity and applicable Python/source CI checks. Record explicit execution identity, then regenerate the pinned registry and Meta Profile reports.

## Custom outliers

None forecast. No new behavioral card-ID branch is permitted.

## Completion record

Completed 2026-10-03. Elapsed time was approximately 20 minutes from proposal creation through the final reproducible checks.

- Candidate cards: `END_007`, `TIME_218`; both declarations already existed.
- Declaration-only consumers: 2/2. No declaration changes were needed.
- Newly verified roots: 2 in Meta Profile scoped evidence; three frozen decks now have one current root each. This is not full deck closure.
- CUSTOM/deferred outliers: 0 / 0.
- Shared runtime implementation: 0 Python and 0 C++; native test assertions only (10 added C++ test lines). One profile-scoped bridge verifier was added.
- Corrections: 2 (runtime Card requirements API in native test; bridge target check aligned to the public action schema and Glacial Shard fixture).
- Builds: 3 configured identity/build invocations (first compile failed on the test API; two later invocations passed). Focused native family run: 57 cases, 365 assertions passed. Bridge parity: both card scenarios passed.
- Full Python suite: 68 passed. Ruff, generic branch guard, and effect-composition deterministic regeneration passed.
- Registry delta: canonical Standard outputs regenerated for the changed RosettaStone test-tree fingerprint. Five previous scoped results are now conservatively STALE; no evidence was rerun automatically. Standard registry remains 0 training-eligible roots. Meta profile audit reports 2 current scoped roots, separately.
- Dependency closure delta: 0 complete closures gained. The `BTA_02pe` temporary Attack dependency was verified only for this scoped contract; profile deck closures remain incomplete.
- Training eligibility delta: 0. No training was started.
