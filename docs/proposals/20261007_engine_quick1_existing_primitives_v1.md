# ENGINE-QUICK-1: existing-primitive ManaEngine batch (proposal and completion record)

Date: 2026-10-07. Scope: declaration-only ManaEngine support for four Standard Core spells. No engine, generator or ABI change. Not a card-by-card queue: the package is "spells expressible entirely by the reviewed `EFFECT_COMPOSITION` steps `DAMAGE`, `DRAW`, `SUMMON_FIXED`".

## Selection method

Candidates were Standard roots absent from `experiments/manaengine/data/card_abilities.json` whose complete text is a concatenation of existing reviewed steps (or keyword-only minions inside the `NONE` ability keyword set). They were ranked by real-match appearances (`data/processed_evidence/collected`, count of games where the card was played; the corpus is one player's Priest-heavy sample, not meta frequency).

## Chosen cards

| Card | Real games / plays | State before | Existing contract | Dependencies |
|---|---|---|---|---|
| `CORE_SW_442` Void Shard | 4 / 5 | UNSUPPORTED (no declaration) | `DAMAGE` `EXPLICIT_CHARACTER` 4 with the step-level `lifesteal` flag (as Stormfury's area step; Lifesteal mechanic is represented by an effect flag) | none |
| `CORE_CS2_094` Hammer of Wrath | 2 / 3 | UNSUPPORTED | `DAMAGE` `EXPLICIT_CHARACTER` 3, `DRAW` 1 (same shape as Press the Advantage / Fan of Knives) | none |
| `CORE_SW_088` Demonic Assault | 1 / 2 | UNSUPPORTED | `DAMAGE` `EXPLICIT_CHARACTER` 3, `SUMMON_FIXED` 2 (as Wound Prey) | token `CS2_065` Voidwalker 1/3 Taunt Demon, `VERIFIED_VANILLA` |
| `CORE_CS2_093` Consecration | 1 / 1 | UNSUPPORTED | `DAMAGE` `ENEMY_CHARACTERS` 2 (as Arcane Flow's area step) | none |

Why no new primitive: every step, target selector, the Lifesteal damage flag and the fixed-summon dependency check already exist with catalog validation; the declarations only select parameters. Declaration text is pinned by `reviewed_rules_text`, so a Core text change fails closed.

Token identity: the pinned Demonic Assault creates `CS2_065` (RosettaStone `SW_088`; a real Power.log observation shows `CORE_SW_088` creating two `CS2_065` entities). `CORE_CS2_065` is a different ID and is not used. The token row is recorded in `experiments/manaengine/data/quick1_dependency_metadata.json` (vendor legacy `cards.json`, SHA recorded). It is not a Standard root and does not change the pinned scope. The identity evidence is a single observation; the declaration does not depend on it for rules, only for ID choice.

## Considered and rejected

- `CAP_102` Land Ho!: its `CAP_107t` Cannoneer tokens deal damage to a random enemy at end of turn; no reviewed end-of-turn random-enemy primitive.
- `EDR_476` Moonwell, `CORE_CS1_112` Holy Nova: "restore to all friendly characters" has no reviewed area-heal selector.
- `CORE_CS2_004` Power Word: Shield, `CORE_CFM_604` Greater Healing Potion: general minion buff and friendly-only Heal selectors do not exist (current Heal accepts any explicit character).
- `CATA_308` Medivh's Triumph, `TLC_816` Gravedawn Sunbloom, `TIME_702` Ebb and Flow: conditional cost/Kindred/held-while-playing history.
- `CORE_BAR_311` Devouring Plague, `TIME_611` Timestop: random split / random freeze selection and ordering unreviewed.
- Keyword-only minions seen in games (`TIME_056`, `TIME_045`, `CATA_558`): Divine Shield, Poisonous and Elusive are outside the `NONE` ability keyword set.
- Cards from the older selected-deck missing list were not considered as such.

Zero-appearance simple spells with the same shape (for example Shiv, Shield Block, Arcane Intellect, Bash, Remorseless Winter) were deliberately left for a later batch; they have no real-game demand.

## Evidence and debt

- Tests (`experiments/manaengine/tests/test_quick1_existing_primitives.py`) use independent expectations from the printed text, including cross-owner interactions (opponent Demonic Assault, our Consecration/Hammer/Void Shard on the result), the Lifesteal heal cap, and neighbour cards remaining UNSUPPORTED. Class-mixed decks are semantic fixtures in the Mage mirror.
- Status is SUPPORTED with a reviewed-text guard; not rules-verified, not verified-scoped registry evidence, not training eligible. `ManaEngineSession.training_eligible` stays false.
- Not covered: a full seven-minion board for Demonic Assault (reuses the existing `SUMMON_FIXED` capacity handling, covered by earlier summon tests), Spell Damage interactions with these spells beyond the existing `CURRENT_AT_STEP` rule, Lifesteal overkill on minions (rule not asserted).
- The canonical Standard registry and its reports consume RosettaStone declarations, not `card_abilities.json`; they are unchanged and reproduce.
