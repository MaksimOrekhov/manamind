# ManaEngine Phase 3 — Meta capability candidate audit

Audit date: 2026-10-03  
Inputs: branch codex/manaengine-hardening at 550da819b7e21f26e2e5fccca526b303ded15d74; pinned RosettaStone f34da0d3fcb5ad312f7e2acf634d0536b044d29a; Standard profile standard_full_20261001_v1; Meta Profile meta_training_20261002_v1 (10 frozen decks, 156 unique Standard roots). Canonical profile facts were read from reports/meta_training_20261002_v1/card_matrix.json; printed card text and stats were cross-checked against vendor/RosettaStone/Resources/cards.standard_current.json and the card references linked below.

## Platform scope

Windows is the required primary target. Ubuntu/Linux is the required secondary portability target. macOS was present in historical hosted runs, but is removed from current CI and is not an acceptance platform. No macOS-specific support was added.

## Ranked capability candidates

| Rank | Package | Reviewed Meta roots | Existing prototype primitives | Shared work and dependencies | Expected reuse / profile gain | Risk and value |
|---|---|---|---|---|---|---|
| 1 | shaman_spell_threshold_hand_transform_v1 — per-hand-instance cast threshold, hand transform and resulting Battlecry | JAIL_801 Molten Gold, JAIL_803 Frostshatter, JAIL_805 Stormfury; 3/3 unsupported, six deck slots in wanted_mug_shaman | CardInstance.counters, clone copies complete EngineState, direct hand spell action path, generic EffectComposition, current observation/action descriptors | Reusable held-card event hook, generic declared transform target, typed Battlecry effect dispatch, enemy-character targeting and actual-damage Lifesteal; fixed dependencies JAIL_801t, JAIL_803t, JAIL_805t | 3 declarations; one deck advanced; 3 roots/6 slots. No closure or deck-readiness claim | Medium-high correctness risk due cast timing and token behaviors, but disputed non-hand internal cast paths can be explicitly unsupported. Best direct proof that counters belong to entity instances. |
| 2 | profile_discover_filtered_pool_v1 — Discover three runtime candidates from a complete declarative Standard pool, then continue after choice | CORE_GIL_836 Blazing Invocation (Battlecry-minion filter) and CAP_407 Wanted Poster (minion cost >= 5); 2/2 unsupported, same Shaman deck. TLC_464 Mountain Map is excluded: it adds type-not-played history and a second choice after playing the selected minion. | PendingChoice, ChooseCard action, option descriptors, deterministic RNG and deep clone are present only for a native test fixture | Declarative candidate-pool filter over the full pinned catalog; sample 3 eligible cards with seeded RNG; preserve all eligible outcomes including unsupported definitions; selecting unsupported outcome invalidates the branch. Target minions with cost >= 5 are broad dependencies for Wanted Poster. | 2 declaration consumers plus possible reuse by other profile Discover cards; 2 roots/4 slots | High pool completeness and option-identity risk. Good proof of real runtime-derived choice, but meaningful implementation work and must not reduce outcomes. |
| 3 | profile_endturn_effect_lifecycle_v1 — temporary turn-end effects with generated/deck-summoned entities | JAIL_327 Reinforcement Aura, TIME_700 Chronological Aura, CATA_999 Earthen Drake; 3 Meta roots, one already represented by an existing end-turn primitive, two lack scoped ManaEngine verification | FIFO trigger queue, end-turn dispatch, temporary effect list, deterministic full-deck minion predicate, summon, visible current state | Declarative event schedule + duration, fixed generated token for TIME_700, full eligible-deck selection for JAIL_327, hero damage for CATA_999; test expiry, board full, simultaneous trigger ordering, unsupported selected deck result | Up to 3 roots across profile decks; shared duration and event path | Medium event-order risk. Better than CATA_567 as the initial real lifecycle proof: Ascendance introduces a random cost+1 minion pool, replacement provenance and death-triggered resummon, with unresolved full-pool/history interactions, so it is not the minimum honest package. |

### Package A semantic decision

Independent contract held_spell_threshold_transform_v1:

1. A qualifying event in this prototype is the active player successfully submitting a PlayCard action for a spell from their own hand. A generated spell that is first added to hand and later played by that action qualifies. The spell card being played has already left the hand before other hand instances are updated.
2. Every matching held instance advances once for that event. The threshold is 3. Opponent spells and spells resolved internally without a player PlayCard action do not advance it.
3. At the third qualifying action, transformation is committed before resolving the played spell's effect, matching the ordering of the pinned Rosetta CAST_SPELL hook. A card drawn by that resolving spell starts at zero because the held-card update precedes spell resolution.
4. Copies are independent because progress is stored in each CardInstance; cloning copies each counter and subsequent branches can advance separately. This prototype has no general hand-copy or hand-bounce operation; if introduced, those paths remain unsupported until their progress-copy semantics are reviewed. A transformed entity preserves its entity handle and hand position, changes card definition, clears the threshold counter, and exports transformed type/cost/target legality.
5. Replayed/extra/auto/nested spells count only if they pass through a separate explicit player-hand PlayCard action. Internal spell resolution, countered spell handling, and other external paths are not modeled by this capability. The current selected cards and prototype's supported spell routes do not implement these paths; any future route that resolves spells internally while a tracker is held must invalidate the branch until wired into the reviewed event contract. We do not infer a global cast definition from NumSpellsCastThisTurn.

This is a deliberately bounded ManaEngine prototype contract, not a claim of full Hearthstone cast-path coverage. No global event ordering is changed. The card-specific effect data stays declarative; there is no card-ID runtime branch.

## Chosen order

1. Implement A first as the most direct validation of the new per-instance model. Candidate token data and Battlecry behavior are checked independently below.
2. Implement B only with a complete, version-pinned eligible pool and fail-closed choice selection. No unsupported option may be silently removed.
3. Implement C on the smallest real shared lifecycle family. If event tracing shows the FIFO/death model cannot produce correct outcomes for those roots, stop for architecture review instead of adding card-specific exceptions.

CATA_567 Ascendance remains a deferred stress candidate. Its wording requires transforming each friendly minion to a randomly selected minion costing one more, retaining enough original identity to summon the original on the transformed minion's later death. The complete eligible pool, enchantment/provenance preservation, board-full summon behavior and interaction with simultaneous deaths need a separate audited contract. It is not included in C's minimum closure.

## A reviewed dependencies and rules references

Pinned collectible metadata describes the three root effects and their Cast 3 spells to turn into a minion! text. The token forms are absent from the pinned Rosetta overlay, so they are declared from reviewed card data rather than inferred from token IDs. Community card reference pages state: Molten Gold (https://hearthstone.wiki.gg/wiki/Molten_Gold) → Molten Gold Elemental (https://hearthstone.wiki.gg/wiki/Molten_Gold_Elemental), Frostshatter (https://hearthstone.wiki.gg/wiki/Frostshatter) → Frostshatter Elemental (https://hearthstone.wiki.gg/wiki/Frostshatter_Elemental), and Stormfury (https://hearthstone.wiki.gg/wiki/Stormfury) → Stormfury Elemental (https://hearthstone.wiki.gg/wiki/Stormfury_Elemental). These support the fixed token definitions (3/3, 5/5, 7/7 Elementals and respective Battlecries); they do not prove complete cast-event ordering.

| Root → token | Token contract |
|---|---|
| JAIL_801 → JAIL_801t | 3 mana, 3/3 Elemental; Battlecry: deal 4 damage to a character. |
| JAIL_803 → JAIL_803t | 5 mana, 5/5 Elemental; Battlecry: Freeze an enemy character, then draw 2. |
| JAIL_805 → JAIL_805t | 7 mana, 7/7 Elemental with Lifesteal; Battlecry: deal 2 damage to all enemy minions and heal for damage actually dealt. |

The new ManaEngine evidence remains prototype-only. No canonical Standard registry rules status, deck closure, training eligibility, or production migration status is promoted by this report.

## Phase 3 implementation progress

- **Package A complete:** `shaman_spell_threshold_hand_transform_v1`; see [PACKAGE_A_COMPLETION.md](PACKAGE_A_COMPLETION.md).
- **Package B complete:** `profile_discover_battlecry_minion_v1`; the honest first consumer is `CORE_GIL_836` only. Its exact pool and support limitations are in [PACKAGE_B_COMPLETION.md](PACKAGE_B_COMPLETION.md). `CAP_407` and `TLC_464` remain deferred.
- **Package C complete:** verification-only `profile_endturn_simultaneous_death_lifecycle_v1`; no production card/event implementation. The actual combined scenario passed under the documented FIFO/death-set contract. Details and explicit parity limits are in [PACKAGE_C_COMPLETION.md](PACKAGE_C_COMPLETION.md).
- The final decision is **KEEP_EXPERIMENTAL**. See [PHASE3_FINAL_REPORT.md](PHASE3_FINAL_REPORT.md) for the acceptance gaps and hosted CI requirement.
