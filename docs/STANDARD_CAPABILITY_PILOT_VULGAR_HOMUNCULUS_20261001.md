# Standard capability batch: simple damage effects

Date: 2026-10-01. Snapshot: `standard_registry_20261001_v1`.

## Change

Added two cards to the bounded effect-composition manifest. `CORE_LOOT_013` Vulgar Homunculus deals 2 damage to its controller's hero on Battlecry. `RLK_024` Death Strike deals 6 damage to a minion and its metadata supplies Lifesteal. Both generated CardDefs use the existing `DamageTask`, explicit targets, and no Spell Damage scaling; no new simulator primitive or dependency was needed.

The declaration remains pinned to the Standard catalog fingerprint and the generator's explicit allowlist. No other generated route owns this card.

## Evidence

- Native effect-composition suite: **16 test cases / 99 assertions passed**. Independent scenarios check Homunculus deals exactly 2 damage to its controller and Death Strike deals 6 to a minion while healing its controller for 6.
- Bridge smoke: Standard deck validation, session creation, opening hand and legal actions passed for `CORE_LOOT_013`. `RLK_024` passed Standard deck validation; session creation remains blocked by the known Death Knight default hero/power gap.
- Registry builder and focused registry suite: **13/13 tests passed**. Inventory is 1,185 roots, 167 direct + 88 generated definitions, 930 text-bearing roots without detected rule registration, 158 known non-root nodes and 310 heuristic dynamic-pool signals. There are still zero complete closures and zero training-eligible roots.
- The shared effect-composition suite checks 16 cards; these cards' addition does not verify the other cards beyond their recorded scenario scopes.

## Exclusions and limits

An initial Death Strike scenario crashed because the card had metadata but no CardDef. After its declaration was added to the generator, the independent native scenario passed. The Standard metadata record is present in the separate overlay; the base `Resources/cards.json` does not contain the ID. Bridge-level DK session checks remain unavailable because the engine lacks DK default hero/power setup.

Both cards remain `IMPLEMENTED_UNVERIFIED` in the full-pool registry. The scoped scenarios do not verify every damage interaction or root dependency closure, and full Standard training remains blocked.
