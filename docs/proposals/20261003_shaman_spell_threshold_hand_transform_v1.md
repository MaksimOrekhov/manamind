# CAPABILITY PACKAGE PROPOSAL — `shaman_spell_threshold_hand_transform_v1`

Revision 1 — 2026-10-03. Inputs: `standard_full_20261001_v1`, canonical registry `standard_registry_20261001_v1`, Meta profile `meta_training_20261002_v1`, RosettaStone `945d891`.

## Package decision

Review the three Shaman roots `JAIL_801`, `JAIL_803` and `JAIL_805` as one candidate family. Their shared contract is: while a particular card instance is in its controller's hand, count spells cast by that controller; after the third such spell, permanently replace that hand card with its fixed Elemental minion form. The transformed card retains its listed cost and gains a Battlecry matching the original spell effect. The current profile contains two copies of each in `wanted_mug_shaman`.

This proposal is **blocked before implementation** pending a core event/session design review. The engine currently processes held-card Infuse counters from minion-death handling; it has no equivalent per-card spell-cast counter. Implementing the proposed behavior appears to require new held-instance state and a precise insertion point in `PlaySpell` event processing. That falls under the user's stop condition for session state / event ordering. No implementation changes are authorized in this proposal.

## Semantic capability

`held_spell_threshold_transform`, contract version 1:

1. Each current hand instance of one of the declared roots independently observes spells cast by its controller while that instance remains in hand.
2. The third qualifying spell permanently transforms that instance to its declared minion form.
3. The card being cast is already leaving hand and is not counted as an in-hand observer. Opponent spells do not advance the controller's hand instances.
4. This counts spells, including generated/cast spells, rather than cards of a particular school. No Discover/random outcome pool is involved.
5. After transformation, the hand card is a minion and its Battlecry uses the token's declared effect and normal Battlecry target legality.

Items 1–4 are the proposed independent expectations. Native source review must establish when an in-hand transform is committed relative to `OnCastSpellTrigger`, nested casts and other current event processing before this contract can be implemented.

## Reviewed candidate cards

| Root | Current spell | Transformed form | Profile occurrence |
|---|---|---|---|
| `JAIL_801` Molten Gold | Cost 3; deal 4 damage | `JAIL_801t`, 3/3 Elemental; Battlecry: deal 4 damage | 2 copies |
| `JAIL_803` Frostshatter | Cost 5; Freeze an enemy; draw 2 | `JAIL_803t`, 5/5 Elemental; Battlecry: Freeze an enemy; draw 2 | 2 copies |
| `JAIL_805` Stormfury | Cost 7; Lifesteal; deal 2 to all enemy minions | `JAIL_805t`, 7/7 Elemental; Lifesteal; Battlecry: deal 2 to all enemy minions | 2 copies |

All three roots are currently `NO_DETECTED_RULE_REGISTRATION` / unverified in the canonical registry. The transformed token records are not present in the RosettaStone resource set and need explicit, traceable dependency declarations before executable registration.

External rules cross-checks: [Molten Gold and its transformed Elemental](https://hearthstone.wiki.gg/wiki/Molten_Gold), [Frostshatter Elemental](https://hearthstone.wiki.gg/wiki/Frostshatter_Elemental), [Stormfury and its transformed Elemental](https://hearthstone.wiki.gg/wiki/Stormfury), [Stormfury Elemental](https://hearthstone.wiki.gg/wiki/Stormfury_Elemental), and the general [transform-in-hand mechanics](https://hearthstone.wiki.gg/wiki/Transform_in_hand). These sources support the threshold and token records; event ordering still needs native design review.

## Existing primitives

- `Player` tracks spell counts this turn and this game; `PlaySpell` increments the spell counters and processes `PLAY_SPELL` / `AFTER_PLAY_SPELL` sequences.
- `Playable` has per-entity game tags and an existing transformed-state flag.
- `Game::ProcessGraveyard` iterates the owner's current hand and updates per-card Infuse counters, then replaces the held card when its threshold is met.
- `Generic::ChangeEntity` and `TransformTask` provide adjacent entity replacement primitives.

These are related implementation points, not evidence that spell-driven hand transforms already work. Infuse currently counts minion deaths and runs in death processing.

## Dependencies and dynamic pools

- Fixed transformation targets: `JAIL_801t`, `JAIL_803t`, `JAIL_805t`.
- Each token's minion metadata, Elemental race and Battlecry rules must be sourced and registered independently.
- No runtime Discover or random pool. Frostshatter's Freeze target set follows native Battlecry character legality.

## Required shared changes

- A reusable per-hand-instance spell-cast progress contract with threshold 3 and a declared transform target.
- A reviewed event-order integration point that counts each qualifying cast once, handles nested/generated spell casts and ignores instances not in hand at the contract's evaluation point.
- Declaration generation for all three root/token pairs; no root-ID branches.
- Exact observation, action and bridge behavior when the held card changes from SPELL to MINION, including target legality after transformation.

If this requires a broad session/history system or changes the engine's global spell-event order, stop and redesign before coding. Do not emulate the count by checking only total spells-cast-this-game: that would incorrectly count casts before the card entered hand.

## Expected reuse and Training Profile value

- Potential consumers: 3/3 declaration-only, subject to the shared event contract.
- Current profile roots: 3 across 1 deck; up to 6 listed copies can be affected.
- This would exercise both spell and minion states of each card in one archetype, but by itself would not close the Shaman deck or make it training-eligible.
- Complete dependency closures / training eligibility expected from this package alone: 0.

## Test strategy if the event-order design is approved

1. Each card remains a spell through casts 1 and 2 while in hand, and changes to the exact declared token after cast 3.
2. A copy drawn after two spells starts at zero; copies in hand advance independently.
3. A spell cast before a card is drawn and an opponent spell do not count.
4. Include a cast spell that is generated/resolved during another spell, with a pinned expected ordering.
5. Check exact transformed metadata, target legality, native effect and actual bridge observation/action parity for each token.
6. Preserve every other random/discover outcome pool and keep profile evidence separate from full deck closure/admission.

## Custom outliers

None forecast. If any root requires card-ID behavior or a token effect cannot be expressed by the same threshold-transform capability plus declarations, defer/classify it CUSTOM rather than widening the shared renderer.

## Completion record

Not started: stopped at proposal stage because the capability crosses the held-card spell-event/session boundary.
