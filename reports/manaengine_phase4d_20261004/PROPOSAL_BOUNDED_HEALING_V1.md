# Capability proposal: bounded healing v1

## Package

`manaengine_bounded_healing_v1`, profile `standard_full_20261001_v1`, base `09e61e686f9a1a086d086e1bc24f475defd5c63b`.

## Candidate cards and evidence

- `CORE_AT_055` Flash Heal — [Blizzard Card Library](https://hearthstone.blizzard.com/en-gb/cards/2582-flash-heal/): “Restore 5 Health.” The pinned card text confirms targetless-on-card-text targeted restoration; client legal actions choose a character.
- `CATA_302` Mend — pinned Standard metadata: “Restore a minion to full Health. Draw a card.” Blizzard's card route was not crawlable in this audit; [Hearthstone Wiki.gg](https://hearthstone.wiki.gg/wiki/Mend) is secondary confirmation for the card identity/text. Rules confidence for Mend is therefore medium; a client replay has not been captured.

## Contract

Add typed `HEAL` for a fixed positive amount to an explicit character, clamped to that character's current maximum health, and `HEAL_MINION_TO_FULL` for an explicit minion, setting current health to its current maximum health. Healing has no Spell Damage scaling and does not reduce Armor. At full health it is a no-op; Mend still proceeds to its unconditional draw step. Do not heal a minion already at lethal health inside this contract; reject that state as unsupported if reached during the instruction sequence.

Flash Heal can target either hero or any minion. Mend can target any minion on either side, never heroes. No damage/death boundary is added; scenarios exercise each as a single health operation, and Mend's unconditional draw follows in the same existing effect sequence.

## Existing primitives and scope

Reuse `EffectComposition`, explicit-character/minion legal actions and `draw()`. Add two small generic health operations and their typed validation/adapter mapping. No schema change, dependencies or card-ID behavior. The family does not claim healing multipliers, overheal triggers, healing lifesteal conversions, maximum-health modification, or healing after lethal pending damage.

## Verification

Native scenarios cover hero/minion targets, side legality, current maximum-health clamp, full-health no-op with draw, and Mend's draw on an undamaged target. Adapter verifies enum/declaration loading and a Flash Heal action through the public adapter. Rules confidence for Mend remains marked medium in the review ledger; no evidence status is promoted by tests.
