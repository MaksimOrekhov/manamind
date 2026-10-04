# CAPABILITY PACKAGE PROPOSAL — `manaengine_overload_turn_lock_v1`

## Semantic contract

For a directly played, non-countered spell with printed Overload `X`, record `X` as pending for its owner. On that player's next turn start, grow the permanent crystal count, lock the pending amount for that turn, and refill only the unlocked crystals. Multiple spells in one turn add. A spell countered by Counterspell does not add its Overload because Overload is resolved in the spell phase after the counter window. State is public as `overloaded_mana` and `pending_overload` for both perspectives.

## Existing primitives

- `PlayerState.max_mana` / `mana`, turn transition and legal play affordability.
- `CardDefinition` currently lacks the imported Overload number; pinned Standard card JSON exposes it.
- `PlayerObservation` already defines `overloaded_mana` and `pending_overload`; encoder includes both fields, so no public schema change is expected.
- `SUMMON_FIXED` + Rush token metadata for Voltaic Burst.
- `TARGET_DAMAGE` for Lightning Bolt.

## Reviewed candidates

| Root | Contract | Current support | Fixed dependency |
|---|---|---:|---|
| `CORE_EX1_238` Lightning Bolt | deal 3 to an explicit character; Overload 1 | unsupported | none |
| `CORE_BOT_451` Voltaic Burst | summon two 1/1 Rush Sparks; Overload 1 | unsupported | `BOT_102t` Spark (1/1 Elemental, Rush) |

Official Blizzard Core Card Library lists both with Overload; the pinned metadata carries exact printed amount 1. Current rules reference documents next-turn lock/refill and Counterspell phase interaction. No client replay captured.

## Dependencies and changes

- Add `CardDefinition.overload` imported from pinned metadata; constrain this prototype capability to directly played spells.
- Add internal pending/current locked counters and public adapter fields; apply the lock/refill at owner turn start.
- Add two declarations and exact non-collectible Spark metadata.
- No changes to global trigger/death scheduling, player class/session model, or observation feature schema.

## Expected reuse and outliers

- Two declaration-only roots; one generic Overload state transition.
- No CUSTOM outliers in the reviewed two-card family.
- Other Overload interactions such as mana unlock effects, Overload minions, temporary crystals and overflow accounting stay outside this package and must fail closed if encountered.

## Verification strategy

- Native scenarios: pending amount after multiple overload spells, next owner turn lock/refill, intervening opponent turns, Counterspell prevents Overload, non-countered Lightning Bolt and Voltaic Burst, and clone determinism.
- Adapter: public pending/current values survive conversion; legal actions respect locked available mana; fixed Rush tokens cross the boundary.
- Full native/adapter suites after implementation. Do not promote canonical registry or training status.

## Evidence

- [Blizzard Core Card Library](https://hearthstone.blizzard.com/en-us/cards?set=core&viewMode=table) for official names/text/keyword display.
- Pinned `standard_current_enUS.json` for card IDs, Overload amount and root mechanics.
- Current rules source: [Overload rules reference](https://hearthstone.wiki.gg/wiki/Overload-generating); Counterspell ordering detail is secondary evidence and will be treated as scoped rules evidence, not as a canonical rules status.
- `vendor/RosettaStone/Resources/cards.json` resolves `BOT_102t` as a 1/1 Elemental Spark with Rush; reference evidence only.
