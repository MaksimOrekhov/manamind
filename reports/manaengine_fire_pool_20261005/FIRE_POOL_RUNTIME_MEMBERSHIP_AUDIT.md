# Phase 4J — Vulcanos Plume "random Fire spell": runtime-membership evidence audit

Read-only research and adversarial rules/data audit. **Local, uncommitted.** No production code, candidate manifest, runtime wiring, training eligibility or CI file was touched.

| Item | Value |
|---|---|
| Audit date | 2026-10-05 |
| Repository HEAD audited | `390053ef9842baa30f2a09f9aabd262eb79de0e8` (fast-forwarded from `0de8621` after `git fetch`; the worktree was clean and strictly behind) |
| Candidate under audit | `fire_spell_standard_20261001_candidate_v1`, 33 IDs, membership SHA-256 `480f5971…0e87` (recomputed: matches) |
| Pinned snapshot | `data/cards/source_snapshots/cards_collectible_20261001_enUS.json`, SHA-256 `d8c66168…b385a930` (recomputed: matches) |
| Independent game-data identity | HearthSim/hsdata commit `27fbd2323aec20cab1c6ecc7d5f55cf12729f956` ("Update to patch 36.6.3.253932", 2026-10-01T12:00Z), `CardDefs.xml` 69,276,033 bytes, SHA-256 `6d75f634…1f419`. The sorted ID list and sorted dbfId list of its 8,170 `COLLECTIBLE=1` entities hash to exactly the same values as the pinned snapshot (`96bcaf62…08ca`, `57909ad3…593b`), so **the pinned snapshot is the collectible slice of game build 253932**. |
| Evidence read in the browser pane only | `CardDefs.xml` was parsed in memory; no copy was saved to disk. |

---

## 0. Method, evidence grades and limits

Grades used in every table:

- **A** — Blizzard primary text, verified against the raw page body (not a summary). Blizzard's own article API (`/en-us/api/blog/articleList/`) was used so that patch-note bodies could be scanned as raw HTML-stripped text.
- **B** — reproducible game data (hsdata `CardDefs.xml` build 253932, identity-matched to the pinned snapshot above). Tag *names* come from the file; tag *semantics* are only as documented as the names are.
- **C** — community wiki (`hearthstone.wiki.gg`), structured pages with source attribution. Useful, demonstrably incomplete (see S3 note).
- **D** — analogy from card text; weakest.

What was **not** available: any current-client Power.log, replay or recording of a Plume (or any other unqualified "random Fire spell") generation; any Blizzard document that enumerates the generation exclusions exhaustively; the wiki's `Special:RunQuery/WikiBanPool` membership lists (Cloudflare challenge; **no bypass was attempted**).

Two `WebFetch` summaries were re-verified against raw text before use: the 2016 format FAQ (raw sentence quoted below) and the 26.0.4 three-rune sentence (raw API body). One search-engine claim ("Perfect Vision can no longer be randomly generated") turned out to be a *Battlegrounds* note and was discarded. The browser pane closed near the end of the session and a later navigation was refused; two minor re-checks (the infobox of Storm the Gates and the raw Inven Global article) were therefore not completed and the corresponding claims are worded narrowly. The wiki and hsdata work was finished before that point.

---

## 1. EXECUTIVE VERDICT

# **FIRE_POOL_MEMBERSHIP_STILL_UNRESOLVED**

The conclusion of the earlier review stands, but for sharper reasons and with a much smaller unresolved space.

1. **What is now established (grades A/B).** The 33-ID candidate is *exactly* the set of Standard-set collectible Fire spells in the build the pinned snapshot comes from (hsdata census: 199 Fire-school entities, 198 spells, 126 collectible, 33 in Standard sets, 93 Wild-only, 72 non-collectible). Across a census of all 402 Standard-set collectible spells, every game-data flag that correlates with a generation exclusion (`QUEST`/`SIDE_QUEST`/`QUESTLINE`, three-rune cost, `DONT_PICK_FROM_SUBSETS`, Herald references, `FABLED`, `COLOSSAL`, `TITAN`) hits **0 of 33** Fire spells. The same flags account for *every* Standard spell the wiki's `Generate` page lists as generation-excluded (11 Quests, Slice and Dice, Dragon Soul Shattered, Frostwyrm's Fury, Grave Strength, the four Herald spells) and additionally flag two Quests (Reach Equilibrium, Storm the Gates) that the wiki omits from those lists.
2. **Why it is still unresolved.** None of the three semantics that define runtime membership — *collectible-only*, *any class*, *no hidden per-card exclusions* — is proven for **this** effect by an authoritative source or a client trace. Blizzard publishes no exhaustive generation-exclusion inventory; the wiki's own presentation is demonstrably inconsistent (Reach Equilibrium is in the Quests ban list but not in its infobox or the `Generate` page list; the Event-set Quest Storm the Gates shows no ban list at all); the one tag that matches the "hard-coded" family (`DONT_PICK_FROM_SUBSETS`) is undocumented, and the project rule is not to treat undocumented tags as rules truth.
3. **The earlier review's class-scope evidence was mis-scoped.** The 26.2.2 "Fire spell" change is a **Duels passive treasure** (`PVPDR_AV_Passive16`, "Flames of the Kirin Tor"), not a Standard card. It is still weak *supporting* evidence (see §6) but it must not be cited as Standard behavior.
4. **Not an architecture problem.** The finite manifest, hash/fingerprint, exclusion ledger, uniform sampler, no-reroll/fail-after-sample behavior and −3 additive cost are all present and tested (§8). The gaps are a weak promotion gate and the absence of a per-controller-class pool (needed only if the class scope turned out to be class-bound).
5. **Evidence-constrained admission: NO** (§9). The unresolved item *is* membership, the coverage gain is small (14 of 33 outcomes have ManaEngine declarations), and training stays blocked on dependency closure regardless.

**Smallest useful next evidence (not a guaranteed unlock):** a small current-client Power.log sample of Plume generations (X1). One non-Mage-eligible result decisively falsifies the controller-class-only hypothesis and strongly supports the current any-class model, but does not prove exhaustive class membership. Positive sightings prove eligibility of the IDs seen, and an unexpected ID would be detected at once. None of this proves an exhaustive manifest: under the current strict exact-membership policy, promotion still needs authoritative runtime-generation rules, or an explicit project decision to admit an inferred finite pool with bounded evidence debt (§11). Any larger campaign belongs on a **newly pinned post-update build**, not on build 253932 (§10, §11).

---

## 2. EXACT PREDICATE

Best-supported runtime rule, at the pinned build/date:

```
Pool(Plume, build 253932, 2026-10-01) =
  { c : c is COLLECTIBLE
      ∧ c.set ∈ {CORE, EVENT, EMERALD_DREAM, THE_LOST_CITY, TIME_TRAVEL, CATACLYSM, ESCAPEFROM_VIOLET_HOLD}
      ∧ c.type = SPELL ∧ c.spellSchool = FIRE
      ∧ ¬Excluded(c) }
Sampling: uniform over Pool, independent of the controller's class, no de-duplication, no reroll, one draw per trigger.
Excluded(c) ⊇ Quest-family(c) ∪ {three-rune cost} ∪ {hard-coded / DONT_PICK_FROM_SUBSETS} ∪ Fabled ∪ Herald-conditional ∪ unknown
At the pinned build:  Pool = the 33 candidate IDs   ⇔   Excluded ∩ {33 IDs} = ∅  and no non-collectible/Wild card is eligible.
```

| Status | Statement | Source / grade |
|---|---|---|
| **PROVEN** | Random effects (including Discover, summoning, transformation "or any other similar effects") only produce cards eligible in the active format. Raw text: *"Random effects … will only summon cards that are eligible for the format you are playing."* | A — Blizzard, "A New Way to Play", 2016-02-02, <https://hearthstone.blizzard.com/en-gb/news/19995505> |
| **PROVEN** | All Death Knight cards with any three-rune requirement are removed from all Discover pools **and** random generation effects. Only the three-rune case is stated; one- and two-rune cards are not excluded by this sentence. | A — Blizzard 26.0.4 patch notes (article 23935323, API date 2023-04-24) |
| **PROVEN** | The 33 IDs are exactly the Standard-set collectible Fire spells of build 253932; none carries a Quest, rune, `DONT_PICK_FROM_SUBSETS`, Herald-reference, Fabled, Colossal or Titan flag; no two Standard spells share a name; all three Core aliases (`CORE_GIL_836`, `CORE_SW_108`, `CORE_WON_337`) count as copies of originals that are Wild-only (GILNEAS, STORMWIND, WONDERS). | B — hsdata build 253932, snapshot cross-hash |
| **PROVEN (negative, corpus-level, with the S1 limits)** | In the 118 Blizzard "Patch Notes" articles from 2022-01-13 to 2026-09-23 (patch 36.6.3), no sentence names any of the 33 cards in a generation/Discover exclusion context. The generation-exclusion statements that do exist concern other cards or other modes (§5). | A — Blizzard article API scan |
| **INFERRED (strong)** | Candidates are *collectible* cards only (the 72 non-collectible Fire spells are not eligible). No Blizzard sentence located says this; it is the universal observed behavior and the basis of every pool the project has built. | C/D |
| **INFERRED (strong)** | "get a random Fire spell" has **no class restriction** (any class, no Neutral Fire spells exist) and each card is one uniformly weighted ticket. Evidence: wording convention, Discover-vs-random contrast (§6–§7). No client trace. | C/D |
| **INFERRED** | No hidden per-card exclusion hits any of the 33: all four independent screens are clean, and every *known* hard-coded ban (Slice and Dice, King of the Underbelly, Dragon Soul Shattered, Zilliax Deluxe 3000, Fabled legends) carries `DONT_PICK_FROM_SUBSETS` while no Fire spell does. | B/C, undocumented tag |
| **UNRESOLVED** | Completeness of the exclusion mechanisms (an exhaustive list does not exist publicly); per-card inclusion in the *client's* pool; whether the newest set's cards (`JAIL_*`, shipped 2026-06-30) are active in the live pool (pool-inclusion bugs have happened: patch 35.6 fixed "Coldarra Drake could not be discovered in Wild"; 36.4.2 notes a bug that kept Escape from Violet Hold cards out of Arena drafts); the Standard-ban/generation policy conflict (§5 row 17). | — |

---

## 3. THE 33-CARD MEMBERSHIP TABLE

Screens (the same six were applied to every card; "clean" = no exclusion found):

- **S1** Blizzard patch-note corpus (118 notes, 2022-01-13 → 2026-09-23). Three scans: (i) a generation-phrase scan over all 118 notes (15 relevant sentences; none names a candidate; the context of each was read, including the list under 36.4.2's "removed from Arena's random generation pools": Chow Down, Captain Crowley); (ii) a same-line name + generation-keyword scan over all 118 notes (4 hits, all unrelated to generation); (iii) an *unfiltered* name scan over 2025-04 → 2026-09 (14 lines: Flames of Infinity bug fix 36.6, Shadowflame Suffusion and Torch in 36.4.2's **Arena draft appearance-rate** list, Blazing Invocation balance 36.0.3/36.2.2, Crowd Control 36.2.2, Smoldering Grove bug fix 35.4, Flight of the Firehawk 35.0.3, Shadowflame Suffusion 32.2.4, Vulcanos 36.2.2). *Limit:* an unfiltered name scan was not run on notes before 2025-04, so a list-style exclusion block that names an older Core card on a line without a generation keyword would be missed by (ii).
- **S2** Game-data tag screen on build 253932: no `QUEST`/`SIDE_QUEST`/`QUESTLINE`, no `COST_BLOOD/FROST/UNHOLY`, no `DONT_PICK_FROM_SUBSETS`, no `FABLED`, no `HERALD` tag/reference, no `COLOSSAL`/`TITAN`.
- **S3** Wiki screen: all 33 card pages fetched; none shows an `Exclusions:` infobox field or a "Ban lists" section. Positive controls on the same extraction code: Vulcanos (summoning pools), Slice and Dice and Frostwyrm's Fury and G'huun (card generation), Cataclysmic War Axe (default card generation), Timethief Rafaam (Fabled), Reach Equilibrium (Quests), Zilliax Deluxe 3000 (hard-coded bans). *Limit:* the wiki's flags are inconsistent (Reach Equilibrium is in the Quests ban list but not in its infobox or the `Generate` page list; Storm the Gates shows no ban list at all), so a clean S3 is weak evidence.
- **S4** Wiki patch history of the card: no generation-related entry.
- **S5** Standard legality: pinned set list + wiki "Standard format cards" category on every page + the wiki's Standard "Fire / Collectible" list (34 entries = the 33 + Flame Shock, which is *upcoming*, Reign of the Black Empire, 2026-10-20).
- **S6** Alias/duplicate-printing screen.

### 3a. Attributes

| # | ID | Name | Class | Set | Rarity | Cost | Collect. | School | Rune req. | Quest/QL/SQ | Legendary | Multi-class | In Standard pool since (wiki) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `CATA_303` | Purifying Breath | PRIEST | CATACLYSM | COMMON | 2 | yes | FIRE | none | none | no | no | 2026-03-10 |
| 2 | `CATA_581` | Decimation | WARRIOR | CATACLYSM | EPIC | 6 | yes | FIRE | none | none | no | no | 2026-03-10 |
| 3 | `CATA_582` | Searing Fissure | WARRIOR | CATACLYSM | COMMON | 2 | yes | FIRE | none | none | no | no | 2026-03-10 |
| 4 | `CATA_585` | Torch | WARRIOR | CATACLYSM | RARE | 1 | yes | FIRE | none | none | no | no | 2026-03-10 |
| 5 | `CORE_CS2_029` | Fireball | MAGE | CORE | COMMON | 4 | yes | FIRE | none | none | no | no | Core since 2021-03-25 |
| 6 | `CORE_CS2_032` | Flamestrike | MAGE | CORE | EPIC | 7 | yes | FIRE | none | none | no | no | Core 2024-03-19 (from reserve) |
| 7 | `CORE_CS2_062` | Hellfire | WARLOCK | CORE | COMMON | 3 | yes | FIRE | none | none | no | no | Core since 2021-03-25 |
| 8 | `CORE_EX1_610` | Explosive Trap | HUNTER | CORE | COMMON | 2 | yes | FIRE | none | none | no | no | Core since 2021-03-25 |
| 9 | `CORE_GIL_836` | Blazing Invocation | SHAMAN | CORE | RARE | 1 | yes | FIRE | none | none | no | no | Core 2025-03-25 (from reserve) |
| 10 | `CORE_LOOT_101` | Explosive Runes | MAGE | CORE | RARE | 3 | yes | FIRE | none | none | no | no | Core 2022-04-12 (from reserve) |
| 11 | `CORE_SW_108` | First Flame | MAGE | CORE | RARE | 1 | yes | FIRE | none | none | no | no | Core 2026-03-17 (from reserve) |
| 12 | `CORE_WON_337` | Ironforge Portal | WARRIOR | CORE | COMMON | 4 | yes | FIRE | none | none | no | no | Core 2026-03-17 (from reserve) |
| 13 | `DINO_406` | Fire Breath | SHAMAN | THE_LOST_CITY | COMMON | 3 | yes | FIRE | none | none | no | no | 2025-09-02 |
| 14 | `END_024` | Flames of Infinity | MAGE | TIME_TRAVEL | COMMON | 3 | yes | FIRE | none | none | no | no | 2026-01-13 |
| 15 | `END_025` | Eternal Firebolt | MAGE/PRIEST | TIME_TRAVEL | COMMON | 3 | yes | FIRE | none | none | no | **YES** | 2026-01-13 |
| 16 | `FIR_900` | Cremate | DEATHKNIGHT | EMERALD_DREAM | COMMON | 3 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 17 | `FIR_906` | Overheat | DRUID | EMERALD_DREAM | RARE | 3 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 18 | `FIR_909` | Bursting Shot | HUNTER | EMERALD_DREAM | COMMON | 2 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 19 | `FIR_910` | Scorching Winds | MAGE | EMERALD_DREAM | RARE | 3 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 20 | `FIR_911` | Smoldering Grove | MAGE | EMERALD_DREAM | RARE | 2 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 21 | `FIR_914` | Smoldering Strength | PALADIN | EMERALD_DREAM | COMMON | 1 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 22 | `FIR_916` | Smoldering Ascent | PRIEST | EMERALD_DREAM | COMMON | 2 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 23 | `FIR_920` | Smoke Bomb | ROGUE | EMERALD_DREAM | RARE | 2 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 24 | `FIR_923` | Flames of the Firelord | SHAMAN | EMERALD_DREAM | RARE | 2 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 25 | `FIR_939` | Shadowflame Suffusion | WARRIOR | EMERALD_DREAM | COMMON | 2 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 26 | `FIR_941` | Searing Reflection | PALADIN | EMERALD_DREAM | COMMON | 7 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 27 | `FIR_954` | Conflagrate | WARLOCK | EMERALD_DREAM | RARE | 1 | yes | FIRE | none | none | no | no | 2025-04-29 |
| 28 | `JAIL_307` | Crowd Control | WARRIOR | ESCAPEFROM_VIOLET_HOLD | RARE | 5 | yes | FIRE | none | none | no | no | 2026-06-30 |
| 29 | `JAIL_801` | Molten Gold | SHAMAN | ESCAPEFROM_VIOLET_HOLD | COMMON | 3 | yes | FIRE | none | none | no | no | 2026-06-30 |
| 30 | `TLC_221` | Sizzling Swarm | SHAMAN | THE_LOST_CITY | RARE | 6 | yes | FIRE | none | none | no | no | 2025-07-01 |
| 31 | `TLC_222` | Flight of the Firehawk | SHAMAN | THE_LOST_CITY | COMMON | 3 | yes | FIRE | none | none | no | no | 2025-07-01 |
| 32 | `TLC_227` | Lava Flow | SHAMAN | THE_LOST_CITY | EPIC | 3 | yes | FIRE | none | none | no | no | 2025-07-01 |
| 33 | `TLC_632` | Story of Sulfuras | WARRIOR | THE_LOST_CITY | RARE | 5 | yes | FIRE | none | none | no | no | 2025-07-01 |

Aggregates: class counts MAGE 8 (7 + the Mage/Priest card), WARRIOR 7, SHAMAN 7, PRIEST 3 (incl. multi), WARLOCK 2, HUNTER 2, PALADIN 2, DEATHKNIGHT 1, DRUID 1, ROGUE 1; rarity 17 common / 13 rare / 3 epic / **0 legendary**; **0 Neutral** (no collectible Neutral Fire spell exists in any set).

### 3b. Screens, evidence and final status

Inclusion evidence common to all 33: format (A, the 2016 FAQ), set + collectible Fire school (B), Standard list agreement (C: wiki Fire page). Exclusion evidence common to all 33: **none found** (S1–S6). Per-card notes only where something is non-default. The last column is *not* membership evidence; it records ManaEngine's declaration state.

| ID | Non-default note | Screens | Evidence for exclusion | **Final status** | ManaEngine (not membership) |
|---|---|---|---|---|---|
| `CATA_303` | - | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CATA_581` | - | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `CATA_582` | - | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CATA_585` | returns to hand on excess damage | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `CORE_CS2_029` | Core alias, original CS2_029 is LEGACY (Wild) | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CORE_CS2_032` | Core alias, original CS2_032 is LEGACY (Wild) | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CORE_CS2_062` | Core alias, original CS2_062 is LEGACY (Wild) | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CORE_EX1_610` | Secret; Core alias, original is LEGACY (Wild) | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CORE_GIL_836` | Discover; Core alias, original GIL_836 is GILNEAS (Wild) | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CORE_LOOT_101` | Secret; Core alias | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CORE_SW_108` | generates fixed Second Flame; Core alias, original SW_108 is STORMWIND (Wild) | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `CORE_WON_337` | random 4-cost summon; Core alias, original WON_337 is WONDERS (Wild) | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `DINO_406` | - | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `END_024` | Secret | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `END_025` | **multi-class** (Mage+Priest): one ticket assumed; Lifesteal | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_900` | **Death Knight card with no rune cost** (three-rune rule inapplicable); Discover/Dark Gift | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `FIR_906` | - | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `FIR_909` | - | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_910` | - | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_911` | Immolate (upgrades, discards) | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_914` | Immolate (upgrades, discards) | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_916` | Immolate (upgrades, discards) | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_920` | Discover/Dark Gift | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_923` | - | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_939` | Discover/Dark Gift | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_941` | Divine Shield summon | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `FIR_954` | - | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `JAIL_307` | newest set; no exclusion found | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `JAIL_801` | newest set; transforms in hand after casting spells | S1-S6 clean | none found | **UNRESOLVED** | SUPPORTED |
| `TLC_221` | - | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `TLC_222` | - | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `TLC_227` | Overload | S1-S6 clean | none found | **UNRESOLVED** | no declaration |
| `TLC_632` | - | S1-S6 clean | none found | **UNRESOLVED** | no declaration |

**Count: 33 IDs → 0 INCLUDED_PROVEN, 0 EXCLUDED_PROVEN, 33 UNRESOLVED.** "UNRESOLVED" here does *not* mean "suspected ineligible": it means no source proves eligibility, and the project rule forbids turning absence of a known exclusion into proof. Inclusion can only be proven by a client observation or an authoritative statement; neither exists.

Support split: 14 of 33 have a SUPPORTED ManaEngine declaration, 19 have none (an additional fail-closed-after-sampling cost, §8).

---

## 4. COMPLEMENT AUDIT

Counts from hsdata build 253932 (identical collectible slice to the pinned snapshot):

| Quantity | Count |
|---|---|
| Fire-school entities (all types) | 199 (198 spells + 1 enchantment) |
| **Raw Fire spell records** | **198** |
| Collectible Fire spells (all sets) | 126 |
| **Standard collectible Fire spells** | **33** |
| Candidate IDs | 33 (set-equal to the previous line) |
| Proven included (client/authoritative) | 0 |
| Proven excluded (non-candidates, by an authoritative rule) | 93 (format) — see below |
| Unresolved | 33 candidates + 72 non-collectible (collectible-only is inferred, not documented) |

**Omitted Fire spells, with reasons.**

- **93 collectible, Wild-only** — excluded by the format boundary (A: 2016 FAQ). By set: CORE_HIDDEN ("Core reserve") 5, EXPERT1 5, RETURN_OF_THE_LICH_KING 5, THE_SUNKEN_CITY 5, ISLAND_VACATION 5, LEGACY 4, WILD_WEST 4, DRAGONS 4, BATTLE_OF_THE_BANDS 4, LOOTAPALOOZA 4, STORMWIND 4, TITANS 4, UNGORO 4, THE_BARRENS 3, SPACE 3, ALTERAC_VALLEY 3, TROLL 3, TGT 2, BRM 2, GANGS 2, DARKMOON_FAIRE 2, GILNEAS 2, KARA 2, SCHOLOMANCE 2, ULDUM 2, WONDERS 2, and one each of DALARAN, GVG, LOE, REVENDRETH, OG, WHIZBANGS_WORKSHOP. Spot checks: Pyroblast, Firelands Portal, Arson Accusation, Fire Sale, Flame Geyser are the five `CORE_HIDDEN` cards; the wiki describes "Core reserve" (set 1810) as storage for rotated-out Core cards and lists it among the Wild sets.
- **72 non-collectible Fire spells** — tokens, adventure/boss/Tavern-Brawl/Duels/co-op cards, puzzle cards. By hsdata set id: 18 (Tavern Brawl/Duels) 22, 14 (Blackrock Mountain adventure) 6, 1004 (Lootapalooza) 7, 1905 (Perils in Paradise) 5, 20 (LOE) 4, 1130 (Dalaran Heist) 4, 1626 (Alterac/Onyxia) 3, **1637 (CORE set id, "Story" puzzle cards) 3**, 5 (tutorial) 2, 23 (Karazhan) 2, 1347 2, 1858 (TITANS) 2, and one each in 3, 13, 21, 1127, 1158, 1403, 1414, 1578 (`SW_108t` **Second Flame** — a Standard-reachable token that First Flame creates *by name*), 1646, 1658. Excluded **only by the inferred collectible-only rule**; no authoritative sentence was found. Any observed generation outside the 33 would falsify it (§10).
- **Upcoming:** Flame Shock (`UPCOMING_130974`, Reign of the Black Empire, 2026-10-20) is in the wiki's Standard list but is absent from build 253932. No Event-set (set 1941) or Reign-set (1994) Fire spell exists in the 2026-10-01 data. **The pool changes on 2026-10-06 (event cards) and 2026-10-20 (expansion)**; this manifest is valid only for the pinned build and must be re-derived after each.
- **Aliases:** none outside the 33 (no Standard-set duplicate names among 402 spells).

Conclusion: direction **B** (omissions correctly excluded) is proven for the 93 format exclusions and *inferred* for the 72 tokens; direction **A** (every included card eligible) is not proven for any card.

---

## 5. EXCLUSION RULES TABLE

Status values: APPLIES / DOES_NOT_APPLY / UNRESOLVED. "Hits" = how many of the 33 the family touches.

| # | Family | Status | Hits | Evidence (grade) |
|---|---|---|---|---|
| 1 | **Standard format** | APPLIES | defines the 33 | A (2016 FAQ, explicitly covers random and Discover); C (wiki "Standard format" page); pinned set list |
| 2 | **Collectible-only** | UNRESOLVED (lean APPLIES) | would remove 72 tokens | no authoritative sentence located; wiki Generate page says generation "can also create collectible cards" and is silent on a rule |
| 3 | Fire school | APPLIES | defines the 33 | B (`SPELL_SCHOOL=2`, one value per card) |
| 4 | **Player/source class restriction** | UNRESOLVED (lean DOES_NOT_APPLY) | 25 of 33 are not Mage-eligible | §6; no replay |
| 5 | Neutral | DOES_NOT_APPLY (moot) | 0 | B: no collectible Neutral Fire spell exists |
| 6 | Opponent class | DOES_NOT_APPLY | 0 | Plume text has no opponent reference; no source |
| 7 | Multi-class | DOES_NOT_APPLY as an exclusion; weighting = one ticket (INFERRED) | 1 (`END_025`) | no source describes class-first sampling |
| 8 | **Runes** (three-rune) | APPLIES (rule); 1- and 2-rune cards are **not** excluded by the stated rule | 0 | A (26.0.4). `FIR_900` Cremate is a Death Knight spell **without** a rune cost |
| 9 | **Quest / Questline / Sidequest** | APPLIES (rule) | 0 | C (wiki ban list "Quests and Questlines cannot be generated randomly") + B (13 Standard quest spells carry a quest tag; 12 of them also carry `DONT_PICK`, the exception being the Event-set quest Storm the Gates). No Blizzard note in the 2022–2026 corpus; the exclusion pre-dates it |
| 10 | Legendary | DOES_NOT_APPLY as a default (the Duels passive had to add "non-Legendary" explicitly) | 0 (no Legendary among the 33) | A (26.2.2 Duels), moot |
| 11 | **Hard-coded / non-generatable** (`DONT_PICK_FROM_SUBSETS`, wiki "Hard-coded card generation bans", Fabled) | APPLIES as a family; **completeness UNRESOLVED** | 0 | B + C. 94 entities carry the tag; Standard collectible spells with it: 14 (12 Quests, Slice and Dice, Dragon Soul Shattered), 0 Fire. The wiki's membership list could not be read |
| 12 | Conditional families (Herald, StarCraft/Galakrond/C'Thun "default card generation") | APPLIES as families | 0 | A (31.4 StarCraft sentence); C (Herald/Colossal); B (4 Herald spells, 0 Fire). Pool is deck-dependent for those, not for Fire |
| 13 | Summoning-only (Colossal/Dormant-battlecry) | DOES_NOT_APPLY | 0 | C: these cards "can be randomly generated … or replaced into in the hand"; Plume generates into hand |
| 14 | **Discover-only rules** (class+Neutral default, no duplicate options, no self-Discover, Arena class pool, card-specific pools) | DOES_NOT_APPLY (not transferable) | — | C; no Discover-only *card* exclusion found for Fire (UNRESOLVED only in the sense that no list exists) |
| 15 | Aliases / Core duplicates | DOES_NOT_APPLY | 0 | B (originals Wild); A (28.4: "certain Wild card with multiple versions could discover the other version of themselves" — a Wild bug fix, and Plume is not a Fire spell) |
| 16 | Self-generation prohibition | DOES_NOT_APPLY | 0 | C; Plume is a minion, not a Fire spell |
| 17 | **Format bans** (Standard list empty; Wild: Grove Shaper, Godfrey) | DOES_NOT_APPLY today; **policy conflict** | 0 | C (wiki "Ban": banned cards "cannot be generated during the course of any game") vs the repo's `standard_scope_20261001.json` policy that bans do not remove cards from generation pools. Single-source, no Blizzard confirmation; no effect while the Standard ban list is empty |
| 18 | Special / event / temporary | DOES_NOT_APPLY now; time-dependent | 0 | B: no Fire spell in the Event or Reign sets at 2026-10-01; Tavern Brawl pools differ (36.0: "Card Generation Pool: Escape from Violet Hold, Standard" is a Pre-Release Brawl rule) |
| 19 | Other-mode exclusions (Arena, Duels, BG) | DOES_NOT_APPLY | 0 | A: 36.4.2 (Arena pool), 34.4.2, 33.0.3, 28.0, 34.2.2 are not Standard Constructed |
| 20 | Client pool bugs | UNRESOLVED (risk class) | unknown | A: 35.6 Coldarra Drake (Wild Discover), 36.4.2 Violet Hold cards missing from Arena drafts. Visible only in the client |

---

## 6. CLASS POLICY VERDICT

**Best-supported scope: ANY_CLASS (INFERRED, strong; not proven).** Not "player's class + Neutral", not "player's class only", not "all classes except …".

| Analog | Wording | Mode | Equivalent to Plume? | What it shows |
|---|---|---|---|---|
| Plume of Vulcanos `CATA_488t/t2` | "get a random Fire spell" | Standard | — (target) | — |
| Pyrotechnician `ETC_540` (Neutral minion) | "add a random Fire spell to your hand" | Wild | yes (only add/get differs) | unqualified; Neutral source removes a source-class confound |
| Soot Spewer `GVG_123`/`WON_033` (Mage minion) | "get a random Fire spell" | Wild | yes | class source, no class note on the wiki |
| Supernova `GDB_301`, Blasteroid `GDB_303` | "random Fire spells" | Wild | yes | Mage cards |
| Fiddlefire Imp `JAM_032` | "a random Fire **Mage and Fire Warlock** spell" | Wild | **no** (class named) | class restriction is spelled out when intended |
| Sunken Scroll `TSC_772t` | "a Fire, Frost, and Nature spell **from your class**" | Wild | **no** | same convention |
| Flames of the Kirin Tor `PVPDR_AV_Passive16` | old: "add a random Fire spell"; new (26.2.2, 2023-05-19): "add a random **non-Legendary** Fire spell **from your class**" | **Duels** (set id 18, `Duels format cards`) | wording equal for the *old* text; mode differs | the change is a pure **narrowing**, so the unqualified wording admitted other classes and Legendaries *in Duels* |
| Discover default | "pool = eligible Neutral + your-class cards" | Standard | **no** (different effect family) | the wiki, citing a 2016 IGN developer interview, places Discover between card draw and "random generate effects like Unstable Portal", whose pool it describes as "extremely large and non-class limited" (the IGN article itself was not re-read) |

Why it matters: the 33 span 10 classes; only 8 are Mage-eligible. If the pool were class-bound for a Mage controller the pool would shrink from 33 to **8**, changing every probability.

**What is not available:** no Standard replay, no Blizzard statement for this wording. The Duels evidence is a different mode with its own buckets and must not be cited as Standard behavior (the earlier review did). **Architecture caveat:** `PoolClassPolicy` has only `AnyClass` and `NonNeutralClass`; a controller-class-dependent pool cannot be expressed. If the one-game test in §10 (X1) showed a class-bound pool, an extension would be needed (§8).

---

## 7. DISCOVER vs RANDOM-GENERATION VERDICT

| Property | Discover | "get / add a random X" | Random summon / transform | Named pool |
|---|---|---|---|---|
| Format-eligible only | yes (A: the FAQ lists Discover explicitly) | yes (A) | yes (A) | by wording |
| Default class scope | player class + Neutral (C, citing a 2016 dev interview); a 2019 patch removed the 4× class weighting (C, Inven Global 2019-09-10, WebFetch summary only) | not class-limited unless stated (INFERRED, C) | not class-limited unless stated | whatever the card names |
| Duplicates among options | three distinct options (C) | independent draw per instance | independent | — |
| Three-rune cards excluded | **yes** (A: 26.0.4) | **yes** (A: 26.0.4 lists "random generation effects") | **not stated** | — |
| "All generation" family (Quests, hard-coded, Fabled) | yes (C) | yes (C) | yes (C) | — |
| "Summoning-only" family (Colossal, Dormant-battlecry) | can still be Discovered into hand | can still be randomly generated into hand | **excluded** | — |
| Weighting | equal per card since 2019 | uniform "truly random" (Brode 2014 tweet, via C) | uniform | — |

**Rules that transfer to Plume (explicit in A or consistently in C):** the format boundary; the three-rune exclusion; the "All generation" family (Quests, hard-coded bans, Fabled). **Rules that must not transfer:** the class+Neutral default pool and its 2019 weighting history, no-duplicate-options, "cannot Discover itself", the Discover-into-battlefield/summon-only family, and every Arena/Duels/Brawl pool statement. No Discover-only exclusion that would *remove* a Fire spell was found, and no random-generation-only one either. Each exclusion used in the proposed manifest is therefore justified for this effect family by a source that names random generation: the format FAQ, 26.0.4, and the wiki's "All generation" definition.

---

## 8. CURRENT ENGINE READINESS

Source inspected: `experiments/manaengine/src/engine.cpp` (`generate_random_card_to_hand`, `resolve_damage_occurrence`, catalog validation), `src/pool_manifest.cpp`, `include/manaengine/engine.hpp`, `src/manamind/integrations/manaengine/pool_manifest.py`, `damage_group.cpp`, the native/pytest suites, `card_abilities.json`.

**A. If exact membership were known, can ManaEngine sample it correctly without architecture changes? → YES_WITH_SMALL_CHANGES**

| Question | Answer |
|---|---|
| Can `PoolPredicate`/`PoolExclusion` express exact Fire membership? | **Yes.** `STANDARD_SPELL_SCHOOL` / `FIRE` / `ANY_CLASS` plus the explicit sorted ID list. The predicate is descriptive; the ID list is authoritative at runtime. |
| Finite and hashable? | **Yes.** Sorted unique IDs, `count`, `sorted_membership_sha256`, `predicate_rules_fingerprint` (covers the exclusion ledger), metadata snapshot id+hash. Both the native validator and the Python loader reject mismatches. |
| Per-exclusion provenance? | **Yes**: each ledger row has `category` (`QUEST`, `RUNE`, `NON_GENERATABLE`, `ALIAS`, `BAN`, …), `status` (`REVIEWED_EXCLUDED`/`UNRESOLVED`), `card_ids`, `rationale`, `evidence_ref` (free strings). **No** per-*member* inclusion provenance or evidence grade, and no structured source digests. |
| Exact finite manifests sampled? | **Yes**: `bounded_random(pool.card_ids.size())` over the whole list, uniform, one draw (`engine.cpp:21`). |
| Full runtime membership, never support-filtered? | **Yes.** No support test precedes the draw. |
| No reroll? | **Yes.** An UNSUPPORTED or undefined sampled outcome throws `UnsupportedSimulationError` *after* the draw (`engine.cpp:22-24`); native tests (`native_tests.cpp:227-229`) show that a two-outcome pool reaches both supported and unsupported IDs, that the unsupported outcome invalidates the branch without inserting a card, and that it "consumes exactly one sample and does not reroll". |
| −3 applied to the generated instance? | **Yes**: `cost_delta += captured_cost_delta`; `effective_cost` = `max(0, base + delta)`. The TakesDamage descriptor (`takes_damage_pool_id`, −3) is captured at the damage packet and re-checked at the checkpoint. |
| Fail-before-RNG guards | candidate (non-reviewed) pool, missing pool id, empty pool, full hand (≥ 10: ordering unreviewed) — all before any draw. |

Small changes that *would* be needed (none touches the sampler):

1. **Promotion gate.** Neither `validate_pool_manifest` (native) nor `load_pool_manifest` (Python) rejects `MEMBERSHIP_REVIEWED` while any exclusion row is `UNRESOLVED`; the only thing keeping Fire blocked today is the status string. Add a validator rule before any promotion.
2. A new reviewed pool id/status instead of editing the candidate in place (the pool id appears in the predicate fingerprint, in `card_abilities.json`, in `build_pool_manifests.py`, in the Python test at `test_adapter.py:922-932` that asserts `CANDIDATE`/`OPEN` for the four candidate pool files, and in the "unresolved Fire pool fails closed" tests `T02` (`damage_group_tests.hpp:23`), the native `failure==2` case and `BB14` (`arcane_barrage_tests.hpp:212-219`), which would become reviewed-pool tests).
3. If the evidence-debt route were ever chosen: an appended `EvidenceConstraint` value (the enum is append-only), recorded when the pool is sampled, and a manifest field that carries it.
4. **Contingent:** a controller-class-dependent pool, only if class-dependent behavior is observed (for example, X1 contradicting the any-class model).

**B. Is any blocker besides membership still present? → Yes, three non-membership items (all fail closed, none is a rules claim):**

- **Executable outcomes.** 14 of 33 outcomes have a SUPPORTED declaration; for the other 19 the branch is invalidated after sampling (no reroll). Expected executable share per trigger = 14/33 = 42.4 %.
- **Plume lifetime.** Vulcanos deals 3 end-of-turn damage to its 5-health Plumes (36.2.2: 1/4 → 1/5, 2 → 3 damage; the repo matches). The first end of turn leaves 2 health; the next lethal hit reaches TakesDamage v1's "lethal consumer state", which fails closed. Hand-full generation ordering is likewise unreviewed.
- **Dependency closure/training:** `dependency_status` is OPEN and `training_eligible` false. Closure of the pool means every outcome's own rules, which is far from done.

Also noted, outside membership: the validity window. The pinned build is the 2026-10-01 collectible slice; the pool is wrong from 2026-10-20 (Flame Shock) and possibly 2026-10-06.

---

## 9. EVIDENCE-CONSTRAINT DECISION

**Can runtime Fire sampling be admitted with evidence debt? → NO.**

The condition in the task is that the debt may not change which cards belong to the pool. Here the debt *is* "which cards belong": an undiscovered hard-coded exclusion would remove a ticket, an undiscovered inclusion would add one, and a class-bound pool would cut 33 to 8. Arcane Barrage's constraint (Phase 4I) was bounded in kind — three named questions whose candidate set could be derived from the card text. This debt is open-ended: an unknown-unknown over 33 individual tickets plus the class scope. Under the rule set for this task (uncertainty that changes which cards belong to the pool is not enough for an `EvidenceConstraint` alone) the answer is NO.

Materiality, stated so the user can re-decide (arithmetic **under the 33-ticket uniform candidate hypothesis**, not evidence for it): if *h* of the 33 are secretly ineligible the manifest's total-variation error is *h*/33 (≈ 3.0 % per card; a single hidden exclusion moves every other outcome from 3.03 % to 3.13 %). That is small but unbounded in *h*, because no source can cap it, and the policy bars turning absence of evidence into proof.

Value of admitting it now is also low: 42 % of outcomes executable, one card (Vulcanos) as the only consumer, and training remains blocked on dependency closure. **Recommendation: keep Plume's Fire branch fail-closed before RNG.** This also holds *after* ordinary finite sampling or an X1 result: under the current policy the block is lifted only by authoritative/sufficiently complete runtime-generation rules (collectible, class and exclusion semantics) or by an explicit project decision to admit a finite inferred pool with bounded evidence debt after sufficient client evidence. If the user takes the second route, the work is item 3 of §8 plus the promotion gate — but that decision belongs to the user, not this audit.

---

## 10. MINIMAL CLIENT EXPERIMENTS

**Operational recommendation (build validity).** Do **not** spend ~200 samples trying to exhaustively validate build 253932. The audit date is 2026-10-05 and the pool can change on 2026-10-06 (event cards) and again on 2026-10-20 (Reign of the Black Empire). A **small** X1 experiment on the current build is still worthwhile because it can falsify class-only semantics, which does not depend on the exact build. Any larger membership campaign (X2/X3) must be run against a **newly pinned post-update build and its regenerated candidate set**.

**Probability convention.** Every probability below is a likelihood calculation **under the current hypothesis H33U** — the exact pool is these 33 IDs, all of them eligible, sampled uniformly per card. H33U is the thing under audit, so these numbers are *not* independent evidence for it; they only say how informative an experiment would be if H33U were true.

Use the **Standard** client in a mode whose pools are the format pools. Do **not** use Tavern Brawl, Duels or Arena: 36.0, 28.4 and 36.4.2 show their generation pools are explicitly different. Capture `Power.log` (the repo's `docs/REAL_MATCH_DATA.md` pipeline already imports it). A generated card appears as a `FULL_ENTITY` created under the source's `BLOCK_START` (source `CardID` = `CATA_488t` or `CATA_488t2`, `TRIGGER`/`POWER` block); read the created entity's `CardID`.

**X0 — mine existing logs (no new games).** Search any `data/raw/` Power.log for blocks whose source `CardID` is `CATA_488t`, `CATA_488t2` (Standard) or `ETC_540`, `GVG_123`, `WON_033`, `GDB_301`, `GDB_303` (Wild analogs). Each created entity under such a block is a free sample, but logs from older builds are evidence about the mechanism, not about build 253932 or the post-update pool. Self-generated cards show their `CardID`; the opponent's are hidden. *Negative result:* none found → nothing learned; the logs may simply not contain the cards.

**X1 — controller-class-only test (small, high value, one game).**
- SETUP: Standard, Mage deck containing Vulcanos (Legendary; the wiki lists a 1,600-dust craft). Play Vulcanos; let both Plumes take damage (end of turn: 3 each; Hero Power may be used once per turn on a Plume). Expected 3–5 triggers per game *(engineering estimate; assumes lethal-damage triggers fire, which is itself observable)*.
- OBSERVABLE: the `CardID` of each generated Fire spell.
- DISTINGUISHES: the controller-class-only (and source-card-class-only) hypothesis, whose pool for a Mage would be the 8 Mage-eligible IDs (`CORE_CS2_029`, `CORE_CS2_032`, `CORE_LOOT_101`, `CORE_SW_108`, `END_024`, `END_025`, `FIR_910`, `FIR_911`), from the current any-class model. It does **not** distinguish the any-class model from other broader-but-restricted policies (for example "any class except some cards" or "own class plus a subset"), because those also permit a non-Mage result.
- WHAT A POSITIVE RESULT PROVES: **one non-Mage-eligible ID decisively falsifies the controller-class-only hypothesis** and strongly supports the current any-class model, but does **not** prove exhaustive class membership.
- LIKELIHOOD (under H33U only): P(all *n* samples Mage-eligible) = (8/33)^n = 24.2 % at n = 1 and 5.9 % at n = 2 (uninformative), **≈ 1.4 % at n = 3**, 0.35 % at n = 4, 0.02 % at n = 6. This is a calculation conditional on exact size 33, all 33 eligible and uniform per-card sampling — none of which is proven — so it is not independent evidence for H33U.
- NEGATIVE RESULT: all samples Mage-eligible with n ≥ 4 is improbable under H33U and would point to a class-bound pool (changing the architecture need); it does not prove one, and it could equally mean H33U itself is wrong (different size or weighting).

**X2 — detect an unexpected card (post-update build only for bulk runs).** Pool every sample. Any `CardID` outside the candidate set (tokens, Wild cards) immediately falsifies direction B for that build. Absence is weak: *if* a hypothetical extra member existed with uniform weight 1/34 (a 34-ticket model, itself an assumption), P(unseen in *n* samples) = (33/34)^n, i.e. 4.9 % at n = 100; a rarer or differently weighted member would be missed far more often. Absence never proves the pool is closed, and it says nothing about collectible-only beyond "no such card appeared".

**X3 — positive per-card inclusion (post-update build only; evidence, not a proof of exhaustiveness).** A positive sighting *proves* eligibility of that ID in the tested build; an absence never proves exclusion. **Even observing all 33 would not prove** that no additional eligible card exists, collectible-only, the absence of a rare hidden extra member, completeness of the `NON_GENERATABLE` exclusions, or exact uniform weighting. X3 is therefore positive-inclusion evidence, not an exhaustive-manifest proof. Under H33U the expected number of distinct IDs after *n* samples is 33·(1 − (32/33)^n):

| n samples | expected distinct of 33 | P(a specific card seen) |
|---|---|---|
| 6 | 5.6 | 16.9 % |
| 10 | 8.7 | 26.5 % |
| 20 | 15.2 | 46.0 % |
| 60 | 27.8 | 84.2 % |
| 100 | 31.5 | 95.4 % |
| 150 | 32.7 | 99.0 % |
| 190 | 32.9 | 99.7 % |

Under the exact uniform-33 hypothesis, about 189 / 211 observations give roughly 90 % / 95 % probability (union bound) of having seen **every** one of the 33 members — a statement about how long it would take to *observe* the members, not a proof of anything about the pool. At ~4 triggers per game that is roughly 45–55 games, so **do not run this campaign on build 253932** (see the build-validity recommendation above); if X3 is ever run, harvest from X0 on the newly pinned build and from normal Vulcanos play. Note that **20 generations will normally leave about 18 of 33 cards unseen, which says nothing about their eligibility**. The Wild generators (Supernova fills a hand: up to ~10 per cast, from a 126-card pool) are efficient for class scope but *inefficient* for the 33: expected ≈2.6 of the 33 per 10 samples; they test the generic mechanism, not Standard activation of the newest cards.

**X4 — re-derive on the post-update build.** After 2026-10-06 and again after 2026-10-20 (event cards; Reign of the Black Empire), pin the new build, regenerate the candidate set and re-run S1–S6. Only then spend sampling effort on X2/X3.

An alternative sampler, with transfer uncertainty: Fyrakk the Blazing (`FIR_959`, "Cast 15 Mana worth of Fire spells at random enemies") consumes a Fire-spell pool too but under "cast", with targeting constraints, so it is not the same effect.

---

## 11. NEXT STEP / WHAT CAN AND CANNOT UNLOCK THE POOL

Membership is unresolved, so no implementation is proposed. **The smallest useful next evidence** is a small set of client-attested Plume generations (Power.log `CardID`s) in a current Standard client (X1). It is useful, but under the project's current strict exact-membership standard it is **not guaranteed to unlock the runtime manifest by itself**.

Client-attested generations can:

- falsify the controller-class-only hypothesis (one non-Mage-eligible ID), while only strongly supporting — not proving — the current any-class model;
- positively prove eligibility of each individual ID that is observed;
- detect an unexpected (non-candidate) card immediately;
- materially increase confidence in the 33-card hypothesis (all probabilities stay conditional on that hypothesis, see §10).

They cannot prove that no additional eligible card exists, collectible-only, absence of a rare hidden extra member, completeness of the `NON_GENERATABLE` exclusions or exact uniform weighting; this holds even if all 33 members are eventually seen.

**Promotion of an exact runtime manifest therefore still requires one of:**

- **A.** authoritative / sufficiently complete runtime-generation rules that establish the collectible, class and exclusion semantics; **or**
- **B.** an explicit project policy decision to admit a finite inferred pool with bounded evidence debt after sufficient client evidence.

Under the **current** policy (membership uncertainty cannot be hidden behind an `EvidenceConstraint`), Fire stays blocked even after ordinary finite sampling unless the missing exhaustive rule evidence (route A) is obtained. Because the pool and data can change from 2026-10-06 and 2026-10-20, any larger membership campaign must wait for a newly pinned post-update build and its regenerated candidate set (§10). Next justified work: targeted client evidence (X1) and post-update re-derivation, not bulk implementation.

Prepared (not started) package, only if route A or B is taken: reviewed manifest `fire_spell_standard_<build>_reviewed_vN` with per-member evidence refs and the exclusion rows resolved; validator rule "reviewed ⇒ no UNRESOLVED exclusion"; flip Plume's `takes_damage_pool_id`; replace the `T02`/`BB14`/native "unresolved Fire pool" tests with reviewed-pool, unsupported-outcome, hand-full, 14/33 executable-share and clone-determinism tests; keep `dependency_status` OPEN and `training_eligible` false.

---

## 12. FINAL ANSWERS

**A. Can Plume random Fire generation be wired now?** **NO.**

**B. Can the current 33-card candidate be promoted as-is?** **NO.** It may well be right, but nothing proves it.

**C. Is the current ManaEngine architecture sufficient?** **YES for the current any-class model** (sampler, TakesDamage reaction, finite hashed manifest and exclusion ledger are all sufficient; the small hardening in §8 is needed). **Conditional extension** only if class-dependent behavior is observed (for example, X1 showing a controller-class-bound pool), which the manifest cannot express today.

**D. Which model should handle the next task?** I have no benchmark knowledge of the GPT-6 family, so this is selected by task shape only. The next justified work is **targeted client evidence (X1) and post-update re-derivation of the pinned build and candidate set — not bulk implementation**. That is evidence handling with uncertainty bookkeeping (interpreting a Power.log sample, re-running the S1–S6 screens on the new build, advising on route A/B): **Claude Sonnet 5.5 Extra**. A mechanical manifest/validator/test package (GPT-6.1 Sol Medium would fit it) is not justified until route A or B is chosen.

---

## Appendix A — Evidence register (all fetched 2026-10-05)

| ID | Source | Grade | Proves | Does not prove |
|---|---|---|---|---|
| O1 | Blizzard, "A New Way to Play" (2016-02-02), <https://hearthstone.blizzard.com/en-gb/news/19995505>; raw sentence re-read | A | random effects incl. Discover/transforms/summons are format-restricted | collectible-only, class, exclusions |
| O2 | Blizzard 26.0.4 patch notes (article 23935323), <https://hearthstone.blizzard.com/en-us/news/23935323/26-0-4-patch-notes> | A | three-rune cards removed from all Discover pools **and random generation effects** | any other exclusion; 1–2-rune handling |
| O3 | Blizzard article API `/en-us/api/blog/articleList/` — 320 articles, 118 "Patch Notes" (2022-01-13 → 2026-09-23); regex scans for generation phrases and for the 33 names | A | no note names any of the 33 in an exclusion context; list of other exclusion statements (31.4 StarCraft, 28.4 versions, Arena/Duels/BG items) | nothing about unannounced behavior |
| O4 | Blizzard 36.2.2 notes (article 24293284) | A | Vulcanos 2→3 damage, Plume 1/4→1/5 (matches `card_abilities.json`, `colossal_appendage_dependency_metadata.json`) | pool |
| O5 | Blizzard 26.2.2 notes (article 23957164, 2023-05-19) + wiki card page `PVPDR_AV_Passive16` | A+C | Duels passive: "random Fire spell" → "random non-Legendary Fire spell from your class" | Standard behavior |
| D1 | hsdata <https://github.com/HearthSim/hsdata/commit/27fbd2323aec20cab1c6ecc7d5f55cf12729f956> `CardDefs.xml`, build 253932 | B | tag census (Fire 199/198/126/33/93/72; Standard-spell flag census 402) | tag semantics |
| W1 | wiki `Generate` (Excluded from card generation; patch 28.4.0 line) | C | the published exclusion families and lists | completeness |
| W2 | wiki `Discover` (class+Neutral default; development notes citing IGN 2016) | C | Discover differs from random generation | Standard replay |
| W3 | wiki `Random effect`, `Standard format`, `Ban`, `Core reserve`, `Fire`, `Flame Shock`, 33 card pages | C | format rule restated; Core reserve = Wild-side set; Standard Fire list; ban-list scan; Flame Shock is upcoming | exhaustiveness |
| T1 | Inven Global, 2019-09-10, <https://www.invenglobal.com/articles/9055/hearthstones-discover-mechanic-is-receiving-a-fundamental-change> (**WebFetch summary only; the underlying page could not be re-read because the browser pane was closed**) | C | Discover weighting history | random generation; only used as context |

## Appendix B — Reproduction (all read-only)

- Pool/snapshot identity: `python -c` over `data/cards/source_snapshots/cards_collectible_20261001_enUS.json` and the candidate manifest (counts, set/school/rune/class filters, `countAsCopyOfDbfId`).
- hsdata: in a browser tab on `hearthstone.wiki.gg` (CORS), `fetch('https://raw.githubusercontent.com/HearthSim/hsdata/27fbd2323aec20cab1c6ecc7d5f55cf12729f956/CardDefs.xml')`, `DOMParser`, index `Entity/Tag` by `enumID` (`SPELL_SCHOOL=1635`, `CARDTYPE=202`, `COLLECTIBLE=321`, `CARD_SET=183`, `DONT_PICK_FROM_SUBSETS=676`, `QUEST=462`, `SIDE_QUEST=1192`, `QUESTLINE=1725`, `COST_BLOOD/FROST/UNHOLY=2196/2197/2198`). Standard set ids: 1637 CORE, 1941 EVENT, 1946 EMERALD_DREAM, 1952 TLC, 1957 TIME_TRAVEL, 1980 CATACLYSM, 1988 VIOLET_HOLD.
- Patch notes: on `hearthstone.blizzard.com`, `fetch('/en-us/api/blog/articleList/?page=N&pageSize=20')`, strip HTML from `content`, regex. (`raw.githubusercontent.com` blocks `fetch` from its own pages by CSP; use another origin.)
- Wiki: `fetch('/wiki/<Card>')` → `DOMParser` → "Exclusions:" infobox and "Ban lists" section. `Special:RunQuery/WikiBanPool` returns a Cloudflare challenge and was not pursued.

## Appendix C — Corrections to earlier records

1. `reports/manaengine_vulcanos_20261005/FIRE_POOL_REVIEW.md` cites the 26.2.2 notes as showing a class-bound, non-Legendary pool for "some Fire-spell effects". That change is a **Duels** passive; it is not Standard evidence (§6). Its other claims (33 IDs; Standard boundary; three-rune rule; unresolved NON_GENERATABLE) are confirmed.
2. The manifest ledger rows `QUEST`, `RUNE`, `ALIAS` (`REVIEWED_EXCLUDED`, empty) are **now independently verified** by the tag census and the count-as-copy check; `NON_GENERATABLE` stays `UNRESOLVED` (correctly).
3. `standard_scope_20261001.json` says bans do not remove cards from generation pools; the wiki says the opposite for Constructed. No effect while the Standard ban list is empty, but the policy line should be re-checked before the first Standard ban.

## Appendix D — Observations outside the membership question

- Date-sensitive: the manifest is pinned to build 253932; both the 2026-10-06 event and the 2026-10-20 expansion can change the pool (§4).
- The wiki's Exclusions infobox and the game-data `DONT_PICK_FROM_SUBSETS` flag disagree on a few Standard cards (the 11 Fabled Across-the-Timeways legends and Reach Equilibrium carry the flag but show no infobox exclusion). The wiki's per-card "Ban lists" section does list them for the cards I checked (Timethief Rafaam, Broxigar and Garona Halforcen under Fabled; Reach Equilibrium under Quests), so the flag looks like the more complete signal — but its semantics remain undocumented.

*End of report. Not committed; nothing pushed.*
