# CAPABILITY PACKAGE PROPOSAL — `filtered_self_deck_draw_v1`

Status: implemented and verified on 2026-10-04; see `FILTERED_DECK_DRAW_COMPLETION_RECORD.md`.

## Semantic contract

On a draw trigger, choose uniformly from the cards currently in that player's deck that satisfy a declared typed predicate; remove only the selected instance and add it through the ordinary hand-entry path. If no card matches, the draw has no result. The selector evaluates actual deck contents and must never filter by ManaEngine support status.

## Reviewed candidate

| Card | Semantics | ManaEngine status | Treatment |
|---|---|---|---|
| `FIR_929` Living Flame | Deathrattle: draw a Fire spell | Unsupported | Root. Reuse the existing DeathrattleDraw and draw lifecycle with a declarative `FIRE_SPELL` predicate. |

`TLC_226` Conjured Bookkeeper also draws a spell from the deck, but its Kindred condition and self-copy effect form separate unresolved contracts; it is deferred rather than partially declared as supported.

## Existing primitives and changes

- Existing: FIFO Deathrattle resolution, hand capacity/burn, fatigue, deterministic RNG, cloned deck instances, card type and current deck vectors.
- New shared surface: typed `DeckDrawFilter` metadata, internal `spell_school` sourced from the pinned card catalog, and uniform filtered selection from the full eligible deck subset.
- No card-ID behavioral branch. A test declaration with a different filter predicate will exercise the same operation independently.

## Dependency and verification plan

There is no external generated-card pool; candidates come from the actual current deck. The frozen profile's Fire-spell subset is `CORE_SW_108` ×1 and `CORE_CS2_029` ×2, but runtime filtering must work for any deck contents. Native checks cover empty and single-member pools, mixed eligible/non-eligible cards, clone/RNG reproducibility, hand cap, fatigue on an empty eligible subset, and ordinary draw regression. Adapter checks exercise the profile card end-to-end.

Expected profile unlock: +1 root, 0 CUSTOM outliers. This does not close `TLC_226` or claim the whole deck is ready.
