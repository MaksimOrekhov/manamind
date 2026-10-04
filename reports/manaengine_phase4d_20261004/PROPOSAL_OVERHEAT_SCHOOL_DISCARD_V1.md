# CAPABILITY PACKAGE PROPOSAL — `manaengine_school_discard_minion_buff_v1`

## Semantic contract

Add typed effect steps to buff all currently controlled minions on board, discard one uniformly selected eligible spell from the acting player's current hand, and condition a later effect step on whether that discard succeeded. The package uses `Nature` as the supported discard-school parameter for the reviewed root and a Fire-school test control. The random pool is every matching spell in hand; no outcome is filtered by support status.

`FIR_906` Overheat resolves in text order:

1. Give each friendly minion on board +1/+1.
2. Select and discard one random Nature spell from the remaining hand.
3. If one was discarded, give the friendly board minions another +1/+1.

No matching Nature spell means step 2 discards nothing and step 3 is skipped; step 1 still resolves. Source spell has already left hand before its effects start. Hand state is inspected at step 2. The board does not change between the two buffs.

## Candidate cards

- Reviewed root: `FIR_906` — Overheat.
- Unsupported prototype roots before this package: 1.
- Fixed/generated dependencies: none.
- Expected declaration-only consumers: 1; CUSTOM outliers: none. A test-only Fire-school declaration is an independent parameter variation, not a supported root.

## Existing primitives

- Typed effect composition, board instances with attack/current Health/max Health, actual hand instances, metadata spell-school tags, deterministic bounded RNG, graveyard transfer and cloning.

## Required shared changes

- `BUFF_FRIENDLY_MINIONS`: apply attack and health bonus to living friendly board minions, preserving damage and increasing maximum/current Health by the same amount.
- `DISCARD_RANDOM_SPELL`: choose uniformly from the complete actual-hand spell-school predicate and move the selected instance to its owner's graveyard.
- `requires_previous_discard`: typed conditional continuation, validated to follow a discard step.
- Fail closed if the selected card has an unresolved discard-trigger mechanic. The complete candidate pool remains intact.

## Rules evidence

- Official Blizzard Card Library page: [Overheat](https://hearthstone.blizzard.com/en-us/cards/115630-overheat/). Its script-rendered page identifies the card; the rules line is retained in the pinned `standard_current_enUS.json` metadata snapshot and cross-checked against current card references.
- Pinned text: `Give your minions +1/+1. Discard a random Nature spell to give them +1/+1 more.`
- Rules reference confirms the school restriction is on the discarded spell, not the source card. No client replay/Power.log captured.
- Timing boundary: each declarative effect step resolves in order; no target or death scheduler is involved. The random set is snapshotted immediately before discard from the then-current hand.

## Tests

- Eligible Nature spells and ineligible Fire/non-spell cards in the same hand; deterministic seeded selection stays within the complete eligible set.
- No eligible spell: first buff occurs, no discard, no conditional buff.
- Successful discard: exactly one matching card leaves hand, enters graveyard and enables the second buff.
- Damaged minion retains its damage amount while max/current Health both rise; attack and health cap are unaffected.
- Empty board and multiple-minion board; independent Fire-school test declaration; clone/RNG determinism.
- Unknown school, dangling conditional buff and incompatible effect fields rejected by parser/catalog.

## CUSTOM / deferred outliers

- `FIR_910` Scorching Winds remains deferred: its second damage instruction targets the same chosen entity, and inter-packet lethal/death timing is not established. It may reuse the discard selector only after that damage boundary is separately reviewed.
- Cards with unresolved on-discard triggers are not removed from the random pool. If such a card is present in the eligible pool, that branch fails closed.

## Completion record

Pending implementation and family verification.
