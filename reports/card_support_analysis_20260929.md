# Card support audit — 2026-09-29

## Scope

This is a reproducible triage inventory for five saved Standard lists plus a deterministic stratified extension sample. It does not establish metagame representativeness, rules correctness, or deck training eligibility.

Catalog snapshot: `data/cards/standard_current_enUS.json` (valid as of 2026-09-27); saved list pool: `data/samples/standard_meta_deck_pool_20260928.json`. RosettaStone revision status: `read`.

## Counts

| Measure | Count |
|---|---:|
| Selected lists | 5 |
| Unique selected-list cards | 74 |
| Selected-list cards registered or textless | 67 |
| Selected-list cards missing nonempty-text registration | 7 |
| Extension sample | 26 |
| Total triaged cards | 100 |

Route counts (triage hypotheses, refreshed 2026-09-30): `AUTO=16`, `COMPOSABLE=34`, `CUSTOM=32`, `MISSING_PRIMITIVE=16`, `UNKNOWN=2`.

Legacy Core alias scan: 47 metadata-linked base definitions; 40 have equal normalized rules text and lack a direct Core CardDef. Generated aliases are accounted for separately: 20 registered by the current manifest, 20 remaining candidates. Five linked entries have different text and are excluded.

AUTO means a possible constrained declaration route, not proven correctness. COMPOSABLE means current RosettaStone constructs appear usable. MISSING_PRIMITIVE names a shared contract or mechanic that needs work. CUSTOM indicates named native handling is likely simpler. UNKNOWN preserves unresolved rules questions.

## Selected decks

| Deck | Class | Unique | Registered/textless | Missing IDs | Strict training gate |
|---|---|---:|---:|---|---|
| Dragon Warrior | WARRIOR | 17 | 14 | `EDR_456`, `FIR_939`, `TIME_034` | not eligible |
| Attack Druid | DRUID | 20 | 17 | `CATA_139`, `MEND_046`, `TLC_100` | not eligible |
| Quest Priest | PRIEST | 17 | 13 | `CAP_805`, `EDR_856`, `JAIL_912`, `TLC_817` | not eligible |
| Mother Drake Warlock | WARLOCK | 19 | 19 | — | not eligible |
| Combo Drake Warlock | WARLOCK | 19 | 19 | — | not eligible |

## Missing registrations in selected lists

| ID | Card | Route | Reason |
|---|---|---|---|
| `CAP_805` | Slime 'em! | MISSING_PRIMITIVE | Must preserve the set of each player's destroyed minions and produce per-player resummon spells. |
| `CATA_139` | Wickerfang | MISSING_PRIMITIVE | Colossal appendages exist as a property, but stat changes must propagate to the correct parent entity. |
| `EDR_456` | Darkrider | MISSING_PRIMITIVE | Dark Gift Discover needs the exact gift-choice pool and application semantics. |
| `EDR_856` | Nightmare Lord Xavius | MISSING_PRIMITIVE | Discover from own deck followed by Dark Gift application needs deck-choice/gift semantics. |
| `FIR_939` | Shadowflame Suffusion | MISSING_PRIMITIVE | Dark Gift Discover requires a Warrior-minion pool and a damage-then-choice continuation. |
| `JAIL_912` | Soothsayer | MISSING_PRIMITIVE | Prepare semantics and subsequent Deathrattle need an independently verified timing contract. |
| `MEND_046` | Bashana Runetotem | CUSTOM | Carve embeds 12 Mana of Nature spells into three generated Treants; likely requires a named stateful native handler. |
| `TIME_034` | Stadium Announcer | MISSING_PRIMITIVE | Rewind setup plus independent random weapon generation for both players needs timing and pool verification. |
| `TLC_100` | Elise the Navigator | CUSTOM | Builds a custom Location from the deck's starting cost distribution; dynamic output is card-specific. |
| `TLC_817` | Reach Equilibrium | MISSING_PRIMITIVE | Two sequential school-specific Quest conditions and rewards require progression/order support. |

## Extension sample

The sampling strata are text heuristics only. Each route below is a manual engineering hypothesis to verify against source and rulings.

| ID | Name | Stratum | Route | Next question |
|---|---|---|---|---|
| `TIME_436` | Past Conflux | choice_random_generated | UNKNOWN | Advance to the Present is a named mechanic whose state transition needs ruling/source inspection. |
| `TIME_712` | Dethrone | choice_random_generated | COMPOSABLE | Destroy plus Combo random-minion generation; verify Combo hook and exact pool. |
| `EDR_570` | Ominous Nightmares | choice_random_generated | COMPOSABLE | Choose One effects appear expressible with existing destroy/summon operations. |
| `TLC_438` | Violet Treasuregill | choice_random_generated | MISSING_PRIMITIVE | Randomly select from own deck by cost and cast onto this minion; target and card-zone semantics need a contract. |
| `CORE_KAR_062` | Netherspite Historian | choice_random_generated | COMPOSABLE | Generated Core alias is registered; confirm runtime rules and dependencies before admission. |
| `CATA_498` | Rafaams' Last Stand | choice_random_generated | MISSING_PRIMITIVE | Repeated random target damage with an upgrade/state counter across turns. |
| `CORE_RLK_116` | Necrotic Mortician | choice_random_generated | MISSING_PRIMITIVE | Requires game-history tracking for friendly Undead deaths and rune-filtered Discover. |
| `CORE_WC_042` | Wailing Vapor | triggered | COMPOSABLE | After-Elemental-play trigger plus permanent Attack gain; verify event source and turn scope. |
| `EDR_845` | Hamuul Runetotem | triggered | MISSING_PRIMITIVE | Start-of-game deck condition plus repeated Imbue progress from Nature spells. |
| `CORE_CATA_001` | Tichondrius | triggered | COMPOSABLE | Battlecry plus a same-turn cost aura for the next Demon; verify hand-zone aura lifetime. |
| `CATA_553` | Ebyssian | triggered | CUSTOM | Game-long Dragon Rush effect and conditional transformation of cards in hand require coordinated state handling. |
| `MEND_506` | Mystic Runesaber | triggered | MISSING_PRIMITIVE | Changes Leyline effects for the rest of the game; enumerate affected spell families first. |
| `CORE_EDR_003` | Falric | triggered | MISSING_PRIMITIVE | Corpse resource gain multiplier and an alternate corpse-spend draw action. |
| `CATA_724` | Stormbinder | triggered | COMPOSABLE | Deathrattle unlocks overloaded mana and applies Overload; verify timing and resource semantics. |
| `TIME_443` | Hounds of Fury | composed | CUSTOM | Summon two Hounds and force an attack selected by lowest enemy Health when deck has no minions. |
| `CATA_479` | Flight Maneuvers | composed | MISSING_PRIMITIVE | Shatter keyword and its summon/buff interaction need source and timing review. |
| `DINO_432` | Panther Mask | composed | COMPOSABLE | Set stats, grant Stealth, then draw; verify silence/stat reset behavior. |
| `CATA_452` | Spellweaver's Brilliance | composed | MISSING_PRIMITIVE | Discount depends on spell damage actually dealt this turn, requiring event history and cost recalculation. |
| `TLC_819` | Gladesong Siren | composed | MISSING_PRIMITIVE | Discount checks whether both Holy and Shadow spells were cast this turn. |
| `CORE_BAR_801` | Wound Prey | composed | COMPOSABLE | Generated Core alias is registered; confirm runtime rules and dependencies before admission. |
| `CORE_EX1_145` | Preparation | single_effect | COMPOSABLE | Direct Core-ID CardDef exists; confirm runtime rules and dependencies before admission. |
| `CORE_EX1_010` | Worgen Infiltrator | single_effect | AUTO | Direct Core-ID CardDef exists; confirm runtime rules and dependencies before admission. |
| `CORE_LOOT_044` | Bladed Gauntlet | single_effect | MISSING_PRIMITIVE | Weapon Attack follows Armor dynamically and cannot attack heroes. |
| `TIME_027` | Tachyon Barrage | single_effect | MISSING_PRIMITIVE | Split damage plus shuffle generated Shreds of Time into deck. |
| `TIME_044` | Past Gnomeregan | single_effect | UNKNOWN | Advance to the Present has no resolved source contract in this audit. |
| `CS3_007` | Novice Zapper | single_effect | AUTO | Direct Core-ID CardDef exists; confirm runtime rules and dependencies before admission. |

## Dependency graph and capability inventory

The initial source scan found 25 literal CardDef references among audited registrations. They are unverified edges. It also lists 29 dynamic pool candidates as `UNKNOWN_POOL`; this is not dependency closure.

Fixed references include generated tokens, enchantments, and choice objects. Their destination type and collectible status are in the JSON graph; each edge remains unverified until both definition and runtime path are checked. Dynamic Discover/random filters remain unresolved unless an exact predicate is recorded.

The inventory enumerates 107 SimpleTasks headers. Source contracts were inspected for 9 high-use capabilities; summarized contracts and limitations are in `integrations/rosettastone/card_rules/capabilities.json`. Header, implementation, and test-file presence are not semantic contracts.

The five deck inventories are complete against the pinned catalog. Scenario and dependency gates remain false. Alias registration changes the missing-ID count but does not complete those gates. The Warlock lists have historical match-smoke evidence, but do not pass the stricter gates; all five lists remain ineligible for training from this audit.

## First implementation package

The audit found a high-value reuse path before introducing operation-by-operation CardDefs: current Core IDs can point to a legacy card ID in metadata while RosettaStone only registers the legacy ID. A strict alias candidate must have a registered stripped-ID base, matching `countAsCopyOfDbfId`, and equal normalized rules text. Forty current Standard Core IDs meet this test and lack a direct Core definition. Five more metadata-linked copies have different text and are excluded.

Start with eight alias declarations to cover token summon, damage, add-card, freeze, Deathrattle, healing, Discover, and Dormant: `CORE_BAR_801 → BAR_801`, `CORE_SW_108 → SW_108`, `CORE_BT_072 → BT_072`, `CORE_BAR_310 → BAR_310`, `CORE_AV_337 → AV_337`, `CORE_BAR_541 → BAR_541`, `CORE_KAR_062 → KAR_062`, `CORE_BT_156 → BT_156`. Generate aliases only after validating each pair and checking duplicate IDs, task references, and dependencies. Keep the other 32 candidates queued until correctness and measured package cost support expansion.

The current generated alias manifest contains 20 aliases from three additions (8 + 7 + 5); 20 candidates remain. A separate allowlisted effect-composition IR now generates four migrated cards (`CORE_CS2_004`, `END_007`, `CAP_801`, `CORE_SW_066`) using ordered existing Tasks and explicit play requirements. `CATA_302` stays manual because its current CustomTask heals only the damage taken and needs a dedicated semantic contract. Scoped scenarios are recorded per card in the JSON report; no selected-deck training gate has changed.

## Limits and provenance

- Five fixed published lists are a selected target pool, not a current meta-frequency sample.
- The 26 extension cards are a deterministic stratified sample selected by text heuristics; strata do not describe implementation complexity.
- Routes are triage hypotheses. Rules correctness, dependency closure, bridge actions, and match eligibility remain separate gates.
- Source regex captures literal ID strings and nearby task names; it does not resolve generated entities, runtime pools, or all C++ control flow.
- Dynamic Discover/random pools are explicitly UNKNOWN until predicates and format membership are resolved.

Raw card-by-card fields, SHA-256 fingerprints, source evidence, and the deterministic sample are in `reports/card_support_analysis_20260929.json` and `data/samples/card_support_analysis_sample_20260929.json`.
