# EVIDENCE-0A — Real-log discovery of unsupported card mechanics

**Verdict: `EVIDENCE0A_READY`**

Mode: read-only architecture and real-log semantic audit. No ManaEngine, ML, policy, live-bridge, registry or overlay file was changed. Only two files were added, under `reports/mechanic_discovery/`: this report and [EVIDENCE_BUNDLE_SCHEMA_PROPOSAL.json](EVIDENCE_BUNDLE_SCHEMA_PROPOSAL.json).

---

## 0. Provenance and method

| Item | Value |
|---|---|
| ManaMind base | `origin/main` = `18e328a1365aa1c201924736376386f841c67b0e` ("fix(live): treat END_TURN as legal in SELF's turn"), re-checked at the end of the task. |
| Branch | `audit/evidence0a-real-card-mechanics`, created from that SHA. |
| Date | 2026-10-06 |
| Parser stack | `hslog` 1.20.0, `hearthstone` (python-hearthstone) 9.21.1, both as installed in the project venv. |
| Pinned scope | `standard_full_20261001_v1` (1,185 collectible Standard roots; 0 rules-verified; full admission BLOCKED). |
| ManaEngine support source read | `experiments/manaengine/data/card_abilities.json`: 92 declarations, 77 `SUPPORTED`, 7 `VERIFIED_VANILLA`, 8 `UNSUPPORTED`. The native module is **not built** in this worktree, so the engine's *effective* per-card `support_state` (after contract review and dependency downgrade, `engine.py` `_load_definitions`) could not be read. Every "supported" figure below uses the 84 declared supported ids and therefore **over-states support**. |

**Evidence tags** (same convention as LIVE-0A): **[M]** measured on the local logs, aggregate numbers only; **[S]** read from repository source or an installed package; **[I]** inference, not verified locally.

**Local data used [M].** `D:\Games\Hearthstone\Logs`, `E:\ManaMind\data\raw` (including `collected/`) and `E:\ManaMind\data\processed_real` were read read-only. After de-duplicating by the collector's `start_key` there are 40 complete games: 25 Ranked Standard, 10 solo-versus-AI (Wild), 4 Battlegrounds, 1 Tavern Brawl. **Only the 25 Ranked Standard games (744,509 log lines) are used** unless stated. All 40 carry `BuildNumber=253216`; the pinned snapshot is the collectible slice of hsdata "patch 36.6.3.253932" (per `FIRE_POOL_RUNTIME_MEMBERSHIP_AUDIT.md`), a different identity whose relationship to the log's number is not established (§14). **No LIVE recordings exist locally** (`E:\ManaMind\data\raw\live` is absent). The live recorder writes the same raw `slice.log` format, so an extractor can consume a recording unchanged, but that is unverified here [I].

**Privacy.** No player name, BattleTag, account id or raw log line appears in this report; every number is an aggregate and every example is reduced to public card ids and public card text. Two scratch outputs briefly printed a BattleTag or an account-id fragment into the local tool transcript while I was prototyping (the `repr()` of hslog's `PlayerReference`, and a `DebugPrintGame` header line). Nothing was written to a file and none of it is quoted here. This is itself a finding (§8, §14).

**Measurement code.** A scratch prototype (tree walker, entity table, window extractor, aggregate counters) lives outside the repository and is intentionally **not committed**, as the task asked for a report only; §0.1 describes each measurement precisely enough to re-run, and EVIDENCE-0B (§15) productises it under tests. The JSON schema was checked with a minimal in-scratch validator (the `jsonschema` package is not installed and nothing was installed or downloaded).

### 0.1 How each number was obtained

| Measurement | Method |
|---|---|
| Corpus inventory | The repository's own `split_games` / `inspect_segment` (`powerlog/lines.py`), de-duplicated by `start_key`; mode and format from the section's own `DebugPrintGame` lines. |
| Block structure | One fresh `hslog.LogParser` per game section (the collector rule), then a pre-order walk that **descends into `SubSpell`** and records a block stack, an incremental entity table and a flat event list. |
| SELF | Controller whose `HAND` entities carry card ids at the first root `PLAY`/`ATTACK` block (the importer's rule). A first attempt using the first `Choices` packet disagreed with it in 15 of 25 games; see §14. |
| Foreign vs own units | A unit is any nested block. "Own" = owner entity equals the root block's source entity. "Semantic effect" = damage/heal metadata, entity creation, transform, choice, or a named non-bookkeeping tag change (zone, resource and exhaustion tags excluded where stated). |
| CREATOR / ATTACHED / LAST_AFFECTED_BY | Final entity tags per created entity; `LAST_AFFECTED_BY` taken from the previous 40 events. |
| Public before/after | The project's own `to_visible_state(..., opponent_identity_policy="none", hand_order="zone_position")` run packet by packet with `CompatibleEntityTreeExporter`, snapshotting before each top-level packet. |
| Unsupported | Card id not in the 84 declared-supported ids; registry scope from `standard_registry_20261001_enUS.json` roots and the pinned collectible snapshot. |
| Decision points | Every `Options` packet (server-validated, SELF only) that has at least one `error=NONE` hand play, hero power or Location use, with the entity's zone taken **at message time** (an early version used final zones and was discarded). |
| Hidden identity exposure | At every root-block boundary: opponent entities with a non-empty card id in `HAND`, `DECK` or `SECRET`. |
| Legality channel | Per-target `error` of playable `Options` entries, grouped by card id. |

---

## 1. Executive recommendation

**Build an offline, post-match evidence extractor. Its unit is one root-block *window*; inside a window every effect is attributed to a *unit* (a nested block) by `CREATOR` tag, then same-unit `LAST_AFFECTED_BY`, then block owner, and never to the root. Collect observations only for subjects the ManaEngine support inventory marks unsupported, aggregate them per card and per typed claim with an ordinal evidence tier (never a proof), and feed a prioritised review queue that sits *in front of* the existing capability-package process. Nothing in this system mutates a rule, a manifest, a registry status or a model.**

What the real logs show that shapes the design (25 Ranked Standard games, all [M] unless noted):

1. **The simulator covers almost none of the real decision surface.** Of 1,450 `PLAY` windows, 974 are played Standard roots with no ManaEngine declaration, 229 are hero powers (19 distinct ids, only the Mage's is implemented), 140 are generated or non-collectible spells/minions/Locations/weapons, 94 are declared cards, and 13 are collectible non-roots or unclassified. Of 1,017 SELF decision points, 98.9 % offer at least one unsupported card-effect action and in 48.3 % every card-effect action is unsupported (§11). The neural fallback will carry most decisions for a long time, so evidence has to be *selective*.
2. **A `PLAY` block is not the card.** 99.9 % of `PLAY` roots (1,448 of 1,450) have no root-level block after them (consequences are nested inside), but 89 % contain at least one foreign `TRIGGER` child, 37 % of windows contain a semantic effect owned by another card, and 18.8 % of all semantic effects inside `PLAY` windows are foreign-owned (§5). Attributing the whole block to the played card is wrong in more than a third of windows.
3. **The log has a better attribution channel than nesting.** All 1,171 enchantment creations carry both `CREATOR` and `ATTACHED`; the innermost block owner equals `CREATOR` only 80 % of the time. 86 % of damage increases carry a recent `LAST_AFFECTED_BY`, which is *sticky* and misleads when stale.
4. **There is a direct, server-validated legality oracle for SELF.** Playable `Options` entries carry a per-target reason in the server's own vocabulary (`REQ_MINION_TARGET`, `REQ_ENEMY_TARGET`, `REQ_TARGET_TAUNTER`, ...): 13,463 target entries in these games, 6,718 of them rejections with a reason (§2.3). It is the only legitimate source of *negative* evidence the logs offer, and it resolves `TARGET_UNKNOWN` far better than watching effects.
5. **Single observations mislead.** Examples in §9: a healing spell logged as 8 damage because another card's enchantment rewrote it; a "1-Cost Demon" spell whose six outcomes all lie outside the metadata's 1-cost Demon list; a conditional battlecry whose 5 targets were never friendly although friendly targets were accepted in 6 server-validated target entries.
6. **Hidden information is present in the raw log.** At 17 % of root-block boundaries an opponent entity carried a known card id while in `HAND`, `DECK` or `SECRET` (21 distinct entities in 25 games; some may be legitimately known to SELF, for example a returned or revealed card, but the log does not say which). The evidence lane must therefore be one-way separated from model input and must tag every fact with its visibility (§8).
7. **Frequency from one user's games is a long tail with a short head.** 260 distinct unsupported collectible ids were played; 166 appear in exactly one game and only 45 in three or more. SELF-played cards are concentrated (top 10 = 57 % of SELF unsupported plays) because one user plays few decks; opponents are not (top 20 = 33 %). Rank by *decisions affected* and by *distinct games*, not by raw counts (§11).

Why the verdict is `READY` and not `NEEDS_PROTOTYPE`: the prototype measurements in this audit already answered the open design questions, and the remaining implementation is a bounded Python task with testable rules (§15). Residual risks are listed in §14; none blocks starting EVIDENCE-0B.

---

## 2. What Power.log can prove

Grades requested by the task: **DIRECT** (stated by packets), **DERIVABLE** (determined from direct values by a stated rule), **PARTIAL**, **AMBIGUOUS**, **NOT SAFE TO INFER**. Rough mapping to LIVE-0A's grades: DIRECT = `DIRECT`, DERIVABLE = `DERIVABLE`, PARTIAL/AMBIGUOUS = `UNRELIABLE`, NOT SAFE = `NOT AVAILABLE`/`UNRELIABLE`. "Hidden" means opponent-side identity that SELF cannot see.

### 2.1 Category table

| Category | Grade | What the log gives | Why not stronger |
|---|---|---|---|
| Card played | DIRECT | Root `PLAY` block; source entity; `ZONE HAND→PLAY`; target in the block header (`CARD_TARGET`). 1,450 roots: spells 622, minions 451, hero powers 229, Locations 123, weapons 24 [M]. | An opponent card's id is only known after the in-block `SHOW_ENTITY`. |
| Source card id | DIRECT | Owner of every block. | Hidden entities have no id until revealed; unknown numeric tags and trigger keywords remain numbers (§2.4). |
| Targets | DIRECT for the chosen target; PARTIAL for multi-target effects | Block target; `META TARGET` lists effect targets (of 1,210 such metas only 309 sit in a block that has a header target [M]); per-target `META DAMAGE`/`HEALING`. | `META TARGET` is not a legality statement. For *random* targets the outcome is visible but not that it was random (§7.3). |
| Damage packets | DIRECT | `META DAMAGE`: one packet per target (1,352 packets, always exactly one entity [M]); `DAMAGE` tag delta; `ARMOR` delta; Divine Shield pop as `amount 0` plus `DIVINE_SHIELD 1→0`. | The base amount is PARTIAL: a card text with "4" produced packets of 4, 0 (shield) and 8 (modifier) in the same card (§9.3). |
| Healing | DIRECT (packet) / PARTIAL (nominal) | `META HEALING` (224) plus `DAMAGE` decrease. | Overheal and conversion to damage by another card (§9.4) are visible only as the final packet. |
| Summons | DIRECT | `FULL_ENTITY` (minion, `ZONE=PLAY`) with `CREATOR`, position via `ZONE_POSITION`. | A summon that did *not* happen (full board, no space) leaves no packet: no-op and "condition false" look the same. |
| Destroyed entities | DIRECT (the move) / DERIVABLE (cause) | `ZONE→GRAVEYARD`, grouped in `DEATHS` blocks (346 nested, 166 root [M]). | Lethal damage vs. an explicit destroy is derivable only by checking `DAMAGE ≥ HEALTH` earlier in the window. |
| Draws | DIRECT for SELF, count only for the opponent | `ZONE DECK→HAND` with ids for SELF; opponent entities are 4-tag shells (LIVE-0A [M]); fatigue tag. | Filtered draws ("draw a spell") show only the outcome. |
| Generated cards | DIRECT (existence, identity when visible) | `FULL_ENTITY` in a SubSpell/POWER with `CREATOR`; 89 % of created spells and 91 % of created minions carry `CREATOR` [M]. | Pool membership and probabilities are **not** observable (§7.3). Opponent-bound identities are hidden. |
| Transforms | DIRECT | `CHANGE_ENTITY`: same entity id, new card id. Rare: 10 in 25 games [M]; a three-step chain appears in §9.6. | Result pools are not observable. |
| Enchantments / buffs | DIRECT | `ENCHANTMENT` entity with `ATTACHED` and `CREATOR`: 1,171 created in blocks, **all** carrying both [M]; stat effects are already folded into `ATK`/`HEALTH`. | Whether it is permanent, an aura, or time-limited is derivable only from its later lifecycle. |
| Stat changes | DIRECT (delta) / DERIVABLE (cause) | `ATK`/`HEALTH` tag changes. Of 684 in-block changes on pre-existing entities, 635 (93 %) coincide with an enchantment created or removed on that entity in the same root window, 49 do not [M]. | 296 stat changes occur **outside any block** (aura recalculation or lifecycle) and cannot be attributed to a window [M]. |
| Zone movement | DIRECT | `ZONE` tag changes (5,194 in blocks [M]). | Cause is the unit, not the tag. |
| Discard | PARTIAL | `HAND→GRAVEYARD` without a `PLAY`; `META BURNED_CARD` (26) marks burns. | I did not find a discard-specific marker in the aggregate scan [I]; discard vs. burn vs. mill must come from block context and card text. Opponent identity hidden. |
| Weapon changes | DIRECT | `WEAPON` entity enters `PLAY`; durability = `HEALTH − DAMAGE` (the importer's rule). | — |
| Hero power effects | DIRECT | Root `PLAY` whose source is a `HERO_POWER` entity (229 plays, 19 distinct ids [M]); effects nested. | The hero power id is non-collectible and not a registry root. |
| Deathrattles | DIRECT (source and order) | `TRIGGER` block with keyword `DEATHRATTLE (217)` nested in `DEATHS` (147 blocks [M]). | The keyword is absent on newer triggers whose numeric keyword is unknown to the package (§2.4). |
| Battlecries | DERIVABLE | A minion `PLAY` with an *own* `POWER` child (1,411 of 1,450 plays have one [M]). | The `BATTLECRY` keyword is not on the block; battlecry vs. other on-play text is told from card metadata, not from the log. |
| Start/end-of-turn triggers | DIRECT (occurrence, source, step) / DERIVABLE (whose turn) | Root `TRIGGER` blocks, 7,192 in 25 games, keyed by `GameEntity STEP`: `MAIN_END` 1,944, `MAIN_ACTION` 1,448, `MAIN_CLEANUP` 1,136, `MAIN_START_TRIGGERS` 693, `MAIN_START` 582, `MAIN_READY` 579, `MAIN_NEXT` 553 [M]. | 69 % are sourced by the game entity (no card-type tag), 13 % by the player entity; the rest by spell-type entities (756: quests, side-quests, secrets), minions (248), enchantments (230) and weapons (19) [M]. |
| Discover / choices | DIRECT | `Choices` / `ChosenEntities` inside the unit; SELF's offered ids are visible; the candidate entities are created `SETASIDE` with `CREATOR` (§9.7). | The three candidates are one draw from a pool, not the pool. Offered identities can be the *opponent's* deck cards (§8). |
| Repeated triggers | PARTIAL | N blocks, or one block with N effects. | "Triggers twice" vs. "one trigger with a doubled effect" is not distinguishable without card text. |
| Aura effects | PARTIAL / AMBIGUOUS | Enchantment entities with `CREATOR` (the source's own); the keyword `AURA (362)` on a few blocks. | Recalculations appear outside blocks or inside unrelated blocks (296 + 49 unexplained changes [M]). |
| Secrets | PARTIAL | Own: `SECRET` zone with id. Opponent: shell until the trigger block's `SHOW_ENTITY`. | The condition is not observable, only that it fired. `SECRET` zone also holds quests, so zone alone does not identify a secret [M: the two most common owners of empty foreign triggers, 2,705 of 3,030, are both spell-type `QUEST` entities of one card sitting in the `SECRET` zone]. |
| Random selections | NOT SAFE TO INFER | The outcome (target or identity) only. | No RNG marker, no candidate set, no probability (§7.3). |
| Conditional effects | PARTIAL | The outcome; the condition only when it can be evaluated from SELF-visible before-state. | A false condition often leaves an empty or absent `POWER` unit, indistinguishable from "effect with no visible result"; opponent conditions are hidden. |

### 2.2 What the structure itself proves

- **Order of resolution**, exactly as the client received it.
- **Ownership of each unit** (block source), and for creations/enchantments the `CREATOR` and `ATTACHED` chain (§5).
- **Whether the result was public**, per packet, by zone/controller and the project's allowlist (§8).
- **The server's own answer to "is this legal now"** for SELF's options (below).

### 2.3 The legality channel (`Options`), the one strong negative-evidence source [M]

`GameState.DebugPrintOptions` is the server's validation of SELF's own choices, parsed already by the live bridge (`build_decision`). In the 25 games: 1,165 messages, 18,159 option entries (5,980 `error=NONE`), and for the 2,143 playable options that carry a target list, **13,463 target entries: 6,745 accepted and 6,718 rejected with a reason**. The reasons seen: `REQ_ENEMY_TARGET` 2,420, `REQ_MINION_TARGET` 2,156, `REQ_HERO_OR_MINION_TARGET` 1,450, `REQ_TARGET_TAUNTER` 474, `REQ_CAN_BE_TARGETED_BY_SPELLS` 88, `REQ_ENEMY_TARGET_NOT_IMMUNE` 85, `REQ_DAMAGED_TARGET` 27, `REQ_TARGET_NOT_UNTOUCHABLE` 10, and a handful more. For unsupported cards alone: 62 cards, 8,503 entries.

Properties and limits:

- It is **state-specific**: it says what was legal in *that* state, not for the card in general.
- It is **SELF-only and own-turn-only**. There is no equivalent for opponent plays.
- Each target entry carries **one** `error`; a target that violates several requirements shows one. A rejection reason is a sound lower bound on the card's requirements, not the complete set [S: hslog `Option.error` is a single field].
- It is **conditional in practice**: for the gated battlecry in §9.1, the same (card, target class) pair is accepted in some states and rejected with `REQ_ENEMY_TARGET` in others (friendly hero: 4 accepted, 5 rejected). A static "target class" table would be wrong; hypotheses must keep the state predicate (§7).

### 2.4 Parser facts the extractor must respect [M]

- **Unnamed tag ids.** The installed `hearthstone` 9.21.1 does not know many current tags (for example `1068`, `1196`, `2245`, `4297`). Of 11,344 `TRIGGER` blocks, 7,124 have trigger keyword 0, **3,371 have the unnamed keyword 4297** and 65 more have 1724; only legacy keywords (`TRIGGER_VISUAL` 295, `LIFESTEAL` 245, `DEATHRATTLE` 147, `TAG_ONE_TURN_EFFECT` 30, `QUEST` 26, ...) are readable. Store tag and keyword values by name when known, else as the numeric id, plus the client build.
- **`SubSpell` groups hold real state changes.** 29.3 % of `FULL_ENTITY`, 28.1 % of `SHOW_ENTITY` and 11.6 % of `TAG_CHANGE` packets are nested inside `SUB_SPELL_START` groups, which `PacketTree.recursive_iter` does **not** descend into. A walker that uses it silently loses nearly a third of all creations (it cost me the identity of a generated spell in my first attempt). The live reducer's `preorder` handles it correctly [S].
- **Creation is a `FULL_ENTITY` followed by a `SHOW_ENTITY`.** `CARDTYPE`, `CREATOR` and `ATTACHED` often arrive in the `SHOW_ENTITY`; reading only the `FULL_ENTITY` loses them.
- **hslog objects carry names.** `PlayerReference.__repr__` includes a BattleTag; `DebugPrintGame` carries `PlayerName=`. Never `repr()` them, never print an exception message (LIVE-0A §5.2 class 7 says the same).

---

## 3. What Power.log cannot prove

1. **Card rules text or its version.** A stable `card_id` does not guarantee stable behaviour (PARTIAL_SIMULATOR_ARCHITECTURE §19). The log is silent about wording.
2. **Exhaustive target legality** from effect observations. The legality channel is state-specific, SELF-only, one-reason-per-target.
3. **Conditions that were not exercised**, and any condition over hidden state (the opponent's hand or deck).
4. **Random pool membership, probabilities and exhaustiveness.** Outcomes are visible; their sampling is not.
5. **Why**: nesting means "resolved inside", not "caused by"; the event that fired a trigger is not recorded (§5).
6. **That nothing happened.** A no-op, a failed condition and an effect with an unobservable result can all produce an empty unit.
7. **Edge cases**: full board, full hand, mortally-wounded sources, simultaneous triggers, silence, copies and transform interactions, unless a window happens to contain them.
8. **Future or hidden identities** (deck order, opponent hand, unrevealed secrets) as legitimate model input.
9. **Mode-independent rules.** Solo-versus-AI, Wild, Battlegrounds and Brawl games share the log format, not necessarily the rules.
10. **The mapping to engine implementation**: even a perfectly attributed effect profile is a behaviour sample, not a contract.

---

## 4. Causal-window design

### 4.1 Definitions

- **Root window**: one top-level `BLOCK_START … BLOCK_END` (types seen at root: `TRIGGER` 7,192, `PLAY` 1,450, `ATTACK` 454, `DEATHS` 166, `DECK_ACTION` 35, `GAME_RESET` 6 [M]). Nesting reaches depth 3.
- **Unit**: any block in the root's subtree. Each unit has an owner (its source entity), a type, a trigger keyword and its **direct** packets (those not inside a child block). `SubSpell` groups are *not* units; they are transparent containers whose packets belong to the enclosing block.
- **Subject**: the card whose behaviour an observation records (the played card; a trigger's owner; a deathrattle's owner; a turn-phase trigger's owner; a hero power; an attacker).
- **Before / after states**: the public SELF-perspective state immediately before the root block's first packet and immediately after its end, built with the project's existing projection and identity policy `none` (§8).
- **Drift channel**: packets *between* root blocks (296 stat changes plus `STEP` and per-turn counters [M]). They are outside every window; the diff between two window states excludes them by construction.

### 4.2 Why the root block is the right outer boundary [M]

After a `PLAY` root, **1,448 of 1,450 (99.9 %) are followed by no root-level block** before the next options message, step change, play, attack or choice; the two exceptions are chains of 2 and 3 root `TRIGGER`s. Deaths caused by a play sit *inside* it (282 `PLAY` roots contain a `DEATHS` child). So a root window already contains the card's consequences; there is no need to merge trailing root blocks. Where one does follow, the extractor links it as `follows` rather than merging.

### 4.3 The smallest useful window for a card

For subject X in a root window:

1. **Own units**: every unit whose owner is X (for a played card: the root `PLAY` unit and its own `POWER` child; for a trigger: the `TRIGGER` unit).
2. **Own effects**: the typed effects directly in those units, plus any entity whose `CREATOR` chain leads to X (an enchantment created by an enchantment created by X).
3. **Context, not claim material**: reaction units owned by *other* cards are recorded by owner id and relation (`REACTION`) with a count of empty watchers, but their effects are **never** in X's effect profile (§5).
4. **Public delta**: the state diff, restricted in the record to entities X's facts touch; full states are stored optionally (needed later for fixtures, §13).
5. **Active modifiers**: enchantments and auras present in the before-state that could alter X's effect, listed as confounders (§5.3).

### 4.4 Extraction procedure

```
for each game section (own LogParser; SELF resolved by project rule, cross-checked; disagreement => skip game)
  walk packets pre-order, descending into Block AND SubSpell
  maintain entity table: card_id, tags, controller, zone, created_in(unit), history
  for each root block R:
    units = flatten(R); drop empty watchers into a counter
    for each unit U: typed effects from its direct packets
        damage (META DAMAGE + DAMAGE/ARMOR/DIVINE_SHIELD deltas), healing, creation (FULL+SHOW pair),
        transform, zone move, stat/keyword delta, enchant attach/remove, choice offer/pick, reveal
    attribute each effect: CREATOR > LAST_AFFECTED_BY set in the SAME unit > unit owner > UNATTRIBUTED
    classify each unit relation to the subject: SUBJECT_OWN / REACTION / SYSTEM / ROOT
    detect confounders; build public before/after; compute inferences with inputs listed
    for each subject whose card is unsupported (or a control sample): emit one observation
```

`LAST_AFFECTED_BY` is **sticky** and only valid as corroboration when it was *set inside the same unit*: in a real window it stayed `EDR_449p` on the played card across zone and exhaustion changes that hero power had not caused, and it read `CATA_308` on health changes that do not match the enchantment chain that explains them (§9.3). Only same-unit, same-effect use is safe.

---

## 5. Trigger attribution

### 5.1 There is no simple stack in the log

What Power.log records is **resolution order and nesting**. It does not record the queue insertion order, the event that fired a trigger, the priority among simultaneous triggers, or whether nesting under a block is causal. `TriggerKeyword` only names legacy keyword triggers, and `META HISTORY_TRIGGER_SOURCE` (69 events) equals the enclosing block's owner in only 22 of them [M], so it is a UI hint, not an attribution source.

### 5.2 What can be reconstructed

| Question | Source | Strength |
|---|---|---|
| Who owns this effect? | Block owner; `CREATOR` on creations/enchantments (all enchantments, 89–91 % of created spells/minions); same-unit `LAST_AFFECTED_BY` (86 % of damage increases have one) | structural. Block owner and `CREATOR` disagree in 20 % of enchantment creations [M]; `CREATOR` is the game's own statement of origin, so it takes precedence |
| In what order did things resolve? | Pre-order position | direct |
| Did the outcome happen inside the card's own effect? | Own `POWER` child (battlecry/spell) | direct |
| Did a death follow from this damage? | `DEATHS` child + `DAMAGE ≥ HEALTH` in an earlier packet | derivable (`DEATH_BY_DAMAGE`), recorded as an inference with inputs |
| Which deathrattle fired and from whom? | `TRIGGER` with keyword 217 under `DEATHS`, owner = dying minion | direct for the legacy keyword |
| Was a turn trigger a start- or end-of-turn effect? | Root `TRIGGER` plus `STEP` (`MAIN_END`, `MAIN_START_TRIGGERS`) | derivable |

### 5.3 Where causality becomes uncertain [M]

- **Foreign triggers dominate the window.** 1,292 of 1,450 `PLAY` roots (89 %) contain at least one foreign `TRIGGER` child; 3,600 in total (2.5 per play). Only **22 %** of them contain any non-bookkeeping packet, so 78 % are empty watchers. But **37 % of windows** contain at least one semantic effect owned by another card, and **18.8 %** of all semantic effects in `PLAY` windows (1,280 of 6,803) are foreign-owned.
- **Stat deltas surface at the root level.** The health/attack changes of a mass-damage spell's victims appear as tag changes in the root `PLAY` unit while the enchantments that explain them were created in a nested foreign `TRIGGER` (§9.3). Position does not attribute a stat delta; the enchantment lifecycle does (93 % explained, 49 unexplained).
- **Modifiers are invisible in the card's own unit.** A persistent enchantment from another card rewrote a healing spell into damage; the only trace is a nested foreign unit consuming the enchantment (§9.4).
- **Reactions to the subject's own effect sit inside it.** A lifesteal trigger, a death, a deathrattle summon and an enchantment expiry are all nested under the played card's block (§9.8).
- **Auras and expiries are emitted wherever the client was.** 296 stat changes occur outside any block.
- **Truly simultaneous or chained triggers** can interleave across foreign units; the log gives the order, not the rule.

### 5.4 Attribution rules for the extractor

| Rule | Statement |
|---|---|
| R1 | Never attribute the root block's content to the root's source by default. |
| R2 | Basis precedence: `CREATOR_TAG` > `LAST_AFFECTED_BY_SAME_UNIT` > `UNIT_OWNER` > `UNATTRIBUTED`. |
| R3 | Effects in a unit owned by another entity get `NESTED_ONLY`: recorded as a reaction with relation, never counted in the subject's profile or claims. |
| R4 | Stat and keyword deltas are explained through enchantment lifecycle when possible (`STAT_CHANGE_EXPLAINED_BY_ENCHANTMENT`); otherwise `STAT_CHANGE_UNEXPLAINED`, kept but excluded from claims. |
| R5 | Any window containing a foreign unit with effects, an enchantment of another owner that touches the same effect, a stale `LAST_AFFECTED_BY`, an aura recalculation, or unknown tag ids gets an explicit confounder; confounded observations are stored and counted separately and do not enter aggregates as clean. |
| R6 | A causal link between two units is recorded as `DIRECT` (creator chain or same-unit `LAST_AFFECTED_BY`), `STRUCTURAL` (nesting only) or none. The extractor never upgrades `STRUCTURAL` to `DIRECT` on its own. |

---

## 6. Evidence bundle schema

The full proposal is [EVIDENCE_BUNDLE_SCHEMA_PROPOSAL.json](EVIDENCE_BUNDLE_SCHEMA_PROPOSAL.json) (JSON Schema 2020-12; two record types and two worked examples; checked with a minimal validator). It is a proposal, not a frozen contract.

**`manamind.evidence.observation/1`**, one per (game, root window, subject):

| Block | Content |
|---|---|
| `subject` | `card_id`, `role` (played card, hero power use, Location activation, attacker, trigger/deathrattle/turn-phase/enchantment/secret source, generated outcome, control sample), `side`, `registry_scope` (Standard root, dependency node, collectible-not-root, non-collectible, unknown id), related card ids. |
| `provenance` | `source: POWER_LOG`, `game_key16` (the collector's `start_key` prefix, no player data), `client_build`, `game_type`, `format_type`, `rules_scope` (`STANDARD_PRIMARY` vs `OTHER_MODE_SECONDARY`), turn, step, line range into the local slice, extractor version, catalog hash, parser versions, unknown tag ids seen. |
| `window` | Root type and ordinal; the units (owner, parent, depth, keyword, relation to subject); a count of empty watcher triggers. |
| `public_states` | Hashes of the public before/after state (mandatory); optional full states and a compact public delta. |
| `support_detection` | Inventory id and hash, basis (`ENGINE_EFFECTIVE_INVENTORY` or `DECLARATION_PROXY`), the subject's support state, other unsupported ids in the window. |
| **`facts`** | Typed packets read directly: damage, healing, zone move, creation, transform, reveal, enchant attach/remove, stat/keyword delta, death, choice offer/pick, target legality. Each has `visibility`, a `raw_ref` (line in the game section and packet ordinal, **no raw text**) and an `attribution` (basis and entity). |
| **`inferences`** | Derived statements (`CONDITION_EVALUATED_FROM_BEFORE_STATE`, `DEATH_BY_DAMAGE`, `STAT_CHANGE_EXPLAINED_BY_ENCHANTMENT`, `HIDDEN_CONDITION_IMPLIED_BY_OUTCOME`, ...), each with `rule_id`/`rule_version`, **the fact ids it used**, written-out assumptions, a status (`DERIVED` or `ASSUMPTION_DEPENDENT`) and the weakest visibility of its inputs. |
| `confounders` | Typed (`FOREIGN_ENCHANTMENT_ACTIVE`, `STALE_LAST_AFFECTED_BY`, `AURA_RECALC_OUTSIDE_BLOCK`, `HIDDEN_CONDITION_INPUT`, ...) with the claim kinds they affect. |
| `triage` | `NOVEL_OBSERVATION` for any unsupported card; the other classes need an engine expectation (§12). |
| `privacy` | `contains_offline_only_hidden`; `model_input_allowed` is the constant `false`; `names_removed` is the constant `true`. |

**Fact vs. inference** is a structural separation, not a convention: an inference can only exist with a non-empty `inputs` list, and a fact has no `inputs`. A condition evaluated from SELF's hand ("the predicate is true") is an inference with its predicate source stated as an assumption; the damage packet it explains is a fact.

**Determinism.** `observation_id` = first 16 hex of `sha256(game_key16 | root ordinal | subject unit | extractor_version)`. Re-running on the same slice reproduces the ids; a new extractor version writes to a new directory (the project already ignores `data/processed*/`).

**What is deliberately not stored**: raw log lines, names, account ids, opponent hidden identities in any field a model could read.

---

## 7. Aggregation across observations

### 7.1 Unit of independence and claim kinds

The unit of independence is the **game**, not the event. One game contributes at most one to `clean_games` however many windows it has: `END_025` has 61 plays in 14 games, `CATA_301` 62 in 19 [M]. Claims are *typed* (`DAMAGE_AMOUNT`, `TARGET_CLASS_OBSERVED`, `TARGET_LEGALITY_REQUIREMENT`, `SUMMON_OUTCOME`, `TRANSFORM_OUTCOME`, `GENERATED_OUTCOME_SET`, `ENCHANTMENT_APPLIED`, `COST_MODIFICATION`, `CONDITIONAL_EFFECT`, `TRIGGER_STEP`, `NO_VISIBLE_EFFECT`, ...), each with parameters, a context breakdown, and counts: clean games and observations, controlled positives/negatives, outcome-only positives/negatives (hidden condition), contradictions, confounded, unattributed.

### 7.2 Evidence-strength model

An **ordinal label, not a probability and never a proof**:

| Tier | Meaning |
|---|---|
| `T0_SINGLE_GAME` | One clean game. |
| `T1_REPEATED_GAMES` | At least 3 clean independent games, no contradiction, identical outcome (after documented modifiers). The number 3 is a review trigger, not a significance threshold. |
| `T2_CONTEXT_VARIED` | `T1`, and the claim held across at least 2 values of a *declared* context dimension (target kind, side, board-size bucket, build). |
| `T3_CONTROLLED_CONDITIONAL` | Conditional claims only. `T1`, at least 3 controlled positives and at least 2 controlled negatives with perfect agreement, with the predicate stated **independently of the data** (from pinned card metadata or review). |

Any contradiction moves the claim to `CONTRADICTED` regardless of tier. `REVIEWED_ACCEPTED/REJECTED` are set only by a review record, never by the aggregator, and a log-derived tier **never writes a registry or rules status**. In the project's existing vocabulary, log evidence tops out at a new label `DIRECT_REPLAY_OBSERVED`, strictly below `DIRECT_REPLAY_VERIFIED` (which needs an independent replay of the same before-state through the engine, not implemented) and unrelated to `REVIEWED_INFERRED` (a runtime policy decision). Every claim also carries a fixed `never_claimed` list (`EXHAUSTIVE_TARGET_LEGALITY`, `POOL_COMPLETENESS`, `POOL_PROBABILITIES`, `ABSENCE_OF_HIDDEN_CONDITIONS`, `EDGE_CASE_COVERAGE`, `RULES_VERIFIED`) so a reader cannot mistake it for proof.

**How little n tells.** If n clean observations all agree, the one-sided 95 % upper bound on the failure rate *in situations like the sampled ones* is 1 − 0.05^(1/n): 95 % at n = 1, 63 % at 3, 45 % at 5, 26 % at 10, 9.5 % at 30, 3.0 % at 100. It says nothing about unobserved contexts.

**Worked example** (all [M], one real card, Weaver of the Cycle `EDR_472`: "Battlecry: if you're holding a spell that costs 5 or more, deal 3 damage"). 7 plays in 6 games (5 SELF, 2 opponent).

| Claim | Support | Tier | Reading |
|---|---|---|---|
| Damage amount = 3 | 5 packets in 5 games, all 3; targets: enemy hero 4, enemy minion 1; both sides | `T2` | Amount is well supported in these contexts. Never observed hitting a friendly target. |
| Conditional: predicate ⇒ 3 damage | SELF controlled: 4 positives, 1 negative, all agree. Opponent outcome-only: 1 damage, 1 none | `T1` | One negative short of `T3`; the predicate evaluates from SELF's visible hand. |
| *Cannot* target friendly | **not a claim** | — | Server-validated options show a friendly hero accepted in 4 target entries and a friendly minion in 2: friendly targets are legal in some states (§7.4). |

### 7.3 RNG: outcomes discover candidates, never the pool

A single generated or random result is one draw. Repeated observations enumerate candidates and give an informational **unseen-mass estimate** (singletons / n, the Good–Turing estimate); neither can prove exhaustiveness, membership or probabilities. This matches the existing architecture: pool membership comes from reviewed rules and the pinned manifest, never from what happened to be sampled; `REVIEWED_INFERRED` is a bounded runtime policy, and "runtime manifests never self-expand from one event" (PARTIAL_SIMULATOR_ARCHITECTURE §19).

Concrete case, Void Soul `JAIL_732` ("Summon a random 1-Cost Demon. Improve your future Void Souls"): six plays in two games summoned 5 distinct Demons costing **2, 2, 7, 5, 6 and 7**. None is among the 25 collectible 1-cost Demons in the pinned snapshot. Four of the five outcomes are singletons, so the unseen-mass estimate is 4/6 ≈ 0.67. The static predicate is not the pool: the state-dependent "Improve" clause is not in the metadata predicate [I: plausibly it raises the cost tier of later summons]. The right output is a `CONTRADICTION_WITH_METADATA_PREDICATE` flag for review, **not** a learned pool. For board-target randomness the candidate set is derivable from the before-state (visible eligible entities), but the eligibility rule and uniformity are not (Petal Peddler, §9.9: one candidate in one window, two in another, the first chosen).

### 7.4 Negative evidence

"Absence in logs" is almost never proof. What is legitimate:

| Kind | Use | Rule |
|---|---|---|
| **N1 Unobserved value** (never targeted a friendly) | None | Store only as descriptive counts (`context_values`); never emit "cannot". The Weaver example above is a live counter-example: 0 of 5 friendly targets, yet legal in the server's own options. |
| **N2 Controlled negative** (a stated predicate is false in a fully visible SELF before-state and the effect did not occur) | Supports a **hypothesis proposed independently** (from card text or review) | Counts toward `T3`; meaningless without an independent predicate; opponent plays can only give outcome-only counts. |
| **N3 Falsification** (one observation violates a reviewed or inferred contract: an outcome outside an inferred pool, a target the contract forbids, a different amount) | Strongest negative use | Routes the claim to `CONTRADICTED`/`NEEDS_REVIEW`; candidates are patch drift, a confounder or a wrong contract. This is how an `ENGINE_CONTRADICTION` or `PATCH_DRIFT_SUSPECTED` arises once an engine expectation exists. |
| **N4 Server-validated rejection** (`Options` per-target `error`) | Direct, state-specific illegality | Store as `TARGET_LEGALITY` facts with the state predicates available; aggregate the *requirement codes seen*, never "the set of legal targets". One reason per target (lower bound). |

### 7.5 Scope of aggregation

Aggregates are keyed `(card_id, role)` and split by `rules_scope`. `STANDARD_PRIMARY` (Ranked/Casual Standard) never mixes with `OTHER_MODE_SECONDARY` (solo-versus-AI, Wild, Brawl). Client build is a context dimension; a build different from the build the pinned metadata/manifests were captured for (§14) produces a `PATCH_DRIFT_SUSPECTED` candidate, not a rejection.

**A concrete standing request this design serves.** `FIRE_POOL_RUNTIME_MEMBERSHIP_AUDIT.md` names "a small current-client Power.log sample of Plume generations" as its smallest useful next evidence: one non-Mage-eligible result would falsify the controller-class-only hypothesis, positive sightings prove eligibility of the ids seen, an unexpected id is detected at once, and none of it proves an exhaustive manifest. That is the N3-falsification plus outcome-set case above, with `REVIEWED_INFERRED` untouched. **None exists locally:** no entity with a `CATA_488*` id (the Plume tokens the declarations use) appears in the 25 games, so this corpus cannot serve it yet.

---

## 8. Hidden-information boundary

Two lanes that must never merge:

| Lane | May see | Output | Consumers |
|---|---|---|---|
| **RAW EVIDENCE PROCESSING** (offline) | Raw local slices, including identities SELF could not see | Evidence store under ignored `data/processed_evidence/<extractor_version>/` (the pattern `data/processed*/` is already ignored) | Humans and agents doing rules research; the review queue |
| **PLAYER-VISIBLE MODEL INPUT** | Only the allowlisted `GameState` (SELF hand, public entities, explicitly revealed cards) | Existing importer/live projection | Encoders, models, training, live recommendations |

**Measured exposure in the raw log [M].** At 1,563 of 9,303 root-block boundaries (17 %) at least one opponent entity carried a non-empty card id while in `HAND`, `DECK` or `SECRET`; over 25 games that is 21 distinct entities (hand 4, deck 5, secret 12). Some of these may be identities SELF legitimately knows (a returned or revealed card); the log does not say, which is exactly why the default is deny. This is in addition to the leakage classes LIVE-0A measured (OVERRIDE_HISTORY reveals, SHOW then HIDE, setaside/removed entities, pre-mulligan reveals). The log can be richer than the screen.

**Rules (H1–H8):**

1. **One-way dependency.** The evidence package may import the powerlog/live helpers; nothing under `manamind.encoding`, `models`, `training`, `inference` or `live` may import it. Enforce with a static import test, in the style of the existing generic-branch guard.
2. **Public states only via the live allowlist projection** (`opponent_identity_policy="none"`, zone-position hand order), never the importer's `revealed` policy.
3. **Default deny.** Every fact has a `visibility`; anything undecided is `OFFLINE_ONLY_HIDDEN` (LIVE-0A R-unknown).
4. **Reveals that SELF could not see stay offline-only**: `OVERRIDE_HISTORY` reveals, `SHOW_ENTITY` followed by `HIDE_ENTITY`, pre-mulligan reveals, opponent `DECK`/`SETASIDE`/`SECRET`/`REMOVEDFROMGAME` identities, even when the log carries an id.
5. **Inferences inherit the weakest input visibility.** "Opponent held a spell costing 5+" derived from an outcome is `OFFLINE_ONLY_HIDDEN` and `ASSUMPTION_DEPENDENT`.
6. **Discover options that show the opponent's deck contents to SELF** (§9.7) are visible to SELF at that moment, but using them anywhere outside the evidence lane needs a per-case review (the live bridge still sets `opponent_known_cards` to empty).
7. **No names, ever.** The extractor never reads `PlayerName=`/account lines into data, never calls `repr()` on hslog player objects, and surfaces only exception **class** names. A canary test must plant a sentinel BattleTag and assert it is absent from every output and every error string.
8. **What hidden data may be used for**: only offline rules research (for example, explaining why an opponent's gated battlecry fired). It never informs a live recommendation, a training row or a Value target. Outcome-only claims for opponent plays rest on *public outcome* facts and need no hidden input.

Entity ids in the store are per-game handles for intra-record references and are marked not-a-model-input (AGENTS.md).

---

## 9. Concrete sanitized real-log examples

All from Ranked Standard games, SELF perspective, public card ids and public text. "Gets" is what the proposed extractor would record; "infers" what it may derive; "cannot" what stays out of reach.

### 9.1 Conditional targeted damage: Weaver of the Cycle (`EDR_472`)

```
PLAY  owner=EDR_472 (minion)   target = enemy hero
  - TRIGGER owner=EDR_449e (expiring cost enchantment)   [REACTION: COST 0 -> 3 on the played card]
  - TRIGGER owner=GBL_999e (empty watcher)
  - POWER   owner=EDR_472 (own)   DAMAGE 3 -> enemy hero ; DAMAGE tag 8 -> 11 ; LAST_AFFECTED_BY = EDR_472
public delta: SELF hand 9 -> 8, board [] -> [EDR_472 3/3], OPP hp 22 -> 19
```

- **Gets**: the damage packet (3, enemy hero) as a fact attributed to the card by same-unit `LAST_AFFECTED_BY`; the `COST 0→3` as a *foreign* stat delta (the card's own cost enchantment expiring); one empty watcher counted.
- **Infers**: predicate "SELF holds a spell with current cost ≥ 5" evaluates true from the before-state hand (a card in that hand costs 5), `ASSUMPTION_DEPENDENT` on the predicate text coming from pinned metadata.
- **Across 7 plays** (§7.2): damage 3 in 5 of 5 where it occurred; conditional agreement 4/4 positive and 1/1 negative for SELF.
- **Legality**: of 9 option messages for this card, the enemy hero was accepted 9 times, friendly hero 4 accepted and 5 rejected with `REQ_ENEMY_TARGET`, friendly minion 2 accepted and 15 rejected, enemy minion 1 accepted, Locations always rejected with `REQ_HERO_OR_MINION_TARGET`.
- **Cannot**: why the friendly-target legality flips between states (cause unknown); exhaustiveness of the target set.

### 9.2 Conditional mana refresh, opponent only: Darkscale Broodmother (`CATA_111`)

Text: "Battlecry: if you're holding a Dragon, refresh 2 Mana Crystals."

```
PLAY  owner=CATA_111   TEMP_RESOURCES 1->0 ; RESOURCES_USED 0 -> 2        (paying 3)
  - POWER owner=CATA_111 (own)   RESOURCES_USED 2 -> 0                     (refresh 2)
```

- **Gets**: the resource refresh of exactly 2 as a fact (4 of 4 observations, all opponent plays).
- **Infers**: *outcome-only*: the opponent held a Dragon (hidden input implied by outcome; `OFFLINE_ONLY_HIDDEN`).
- **Cannot**: the negative case. No local SELF play exists, so there is no controlled negative; the claim is `T0` (4 plays, but only 2 games, below the 3-game `T1` threshold) and the condition is not evaluable.

### 9.3 Mass damage with modifiers: Medivh's Triumph (`CATA_308`)

Text: "Deal 4 damage to all minions. Costs (1) if you control a Legendary."

- 25 plays in 14 games, 86 damage packets: **4 ×69, 0 ×9, 8 ×8**; targets: enemy minions 76, friendly minions 10.
- **Gets**: one packet per target; `amount 0` coincides with `DIVINE_SHIELD 1→0` in the same unit (derivable `DIVINE_SHIELD_ABSORBED`); `amount 8` has no in-unit explanation (a damage modifier from the board, hand or another effect) and is kept as `UNEXPLAINED_VARIANT`, **not** averaged into the amount.
- **Gets (cost)**: in hand the `COST` tag was 1 (the discounted cost); at `HAND→PLAY` it returned to 5. A dynamic cost is therefore observable as a `COST` delta outside any effect.
- In one window the victims' `HEALTH 3→4` then `4→1`, `ATK 2→1` appeared in the root unit, while the three enchantments that explain the `+1` Health were created inside a nested foreign `TRIGGER` owned by `MEND_801` (a minion whose Divine Shield had just popped in the same spell). `LAST_AFFECTED_BY` on those health changes read the spell, which does not match that chain (§4.4). Stat deltas are explained through the enchantment chain, not by position or by that tag.
- **Infers**: "all minions" (both sides hit) is supported (friendly 10).
- **Cannot**: what the modifiers were; the base amount by averaging.

### 9.4 A rewritten effect: Holy Embrace (`JAIL_941`) under an active Ruby Sanctum enchantment

Text: "Restore #4 Health. Get a Dark Embrace that deals 4 damage."

```
PLAY  owner=JAIL_941   target = enemy hero
  - POWER   owner=JAIL_941   DAMAGE 8 -> enemy hero ; CREATE spell JAIL_941t zone=HAND creator=JAIL_941
    - TRIGGER owner=CATA_301e (enchantment from Ruby Sanctum)   ZONE PLAY -> GRAVEYARD   [consumed]
```

- **Gets**: a damage packet of 8 on a card whose text *restores* health, and a nested foreign unit consuming another card's enchantment.
- **Confounder**: `FOREIGN_ENCHANTMENT_ACTIVE` ("your next healing effect this turn deals damage instead"). Aggregating this as "JAIL_941 deals 8 damage" would be a wrong rule. The observation is stored, tagged confounded, and excluded from clean counts; the persistent enchantment is in the before-state's active modifiers.
- **Cannot**: why the amount is 8 and not 4 (a second modifier is present or the conversion doubles; unknown).

### 9.5 A Location creating a persistent enchantment: Ruby Sanctum (`CATA_301`)

```
PLAY  owner=CATA_301 (Location)   DAMAGE tag None -> 1 (durability) ; EXHAUSTED -> 1
  - POWER owner=CATA_301 (own)   CREATE enchantment CATA_301e (zone PLAY, creator CATA_301)
```

- 62 plays in 19 games (the most frequent unsupported card), and legal at 550 of the 1,017 SELF decision points (54 %).
- **Gets**: the enchantment creation as a fact; its later consumption in another card's window (§9.4) as a foreign unit. **Cannot**: that the effect is "next healing effect" without the card text; the log shows the entity, not its rule.

### 9.6 Transform chain with a foreign spawn: Devolving Missiles (`SCH_235`, opponent)

```
PLAY  owner=SCH_235   (3 missiles at random enemy minions, transforming them into ones that cost 1 less)
  - TRIGGER owner=GBL_002e   (expiring cost enchantment)   COST 0 -> 1 on the card
  - POWER   owner=SCH_235    TRANSFORM TIME_890 -> JAIL_118 -> CORE_SCH_181 -> TIME_704   (same entity, three steps)
  - TRIGGER owner=JAIL_122e5 (a foreign enchantment)       CREATE minion CORE_GIL_531   [on the opponent's board; CREATOR = JAIL_122e5]
```

- **Gets**: a three-step `CHANGE_ENTITY` chain on one entity; public delta: SELF board `TIME_890 7/7 → TIME_704 6/6`; OPP board gains `CORE_GIL_531 0/1`.
- **Attribution trap**: the new minion sits under the spell's `PLAY` block but belongs to the foreign enchantment unit. Its `CREATOR` tag (which arrives in the `SHOW_ENTITY` after the `FULL_ENTITY`) names that enchantment, so `CREATOR_TAG` attribution excludes the spell directly; block position alone would not.
- **Infers**: the three transforms hit the same minion (candidate set was the enemy minions in the before-state: derivable). **Cannot**: that selection was random or uniform; the result pools.

### 9.7 Discover and generated cards: Intertwined Fate (`TIME_432`)

Text: "Discover a copy of a card from your deck and one from your opponent's."

```
PLAY  owner=TIME_432
  - POWER  CREATE spell CATA_308 / minion TIME_890 / minion EDR_970   zone SETASIDE  creator TIME_432
           CHOICES (3)  CHOSEN
           CATA_308 ZONE SETASIDE -> HAND ; COST 5 -> 1
           CREATE minions/spell CORE_SW_047 / CORE_ICC_038 / MEND_900  zone SETASIDE  creator TIME_432
           CHOICES (3)  CHOSEN   CORE_ICC_038 ZONE SETASIDE -> HAND
```

- 44 plays in 17 games. **Gets**: two rounds; the three offered ids per round; the picked one moving to hand; each candidate attributed by `CREATOR`.
- **Hidden-information edge**: round two's offered ids are copies of the **opponent's deck** cards, visible to SELF as a choice but a deck identity all the same (rule H6).
- **Cannot**: the pool each triple was drawn from (two dynamic pools are unresolved in the registry for this card).

### 9.8 Nested chain with reactions: Eternal Firebolt (`END_025`)

Text: "Lifesteal. Deal 3 damage to a minion. If it dies, return this to your hand at the end of your turn."

```
PLAY  owner=END_025   target = enemy minion
  - POWER   owner=END_025   DAMAGE 3 -> minion ; CREATE enchantment END_025e ("return to hand")
      - TRIGGER owner=END_025 (kw 685 LIFESTEAL)   HEALING ; own hero DAMAGE 1 -> 0
  - DEATHS  (system)   minion ZONE PLAY -> GRAVEYARD ; DAMAGE reset
  - TRIGGER owner=JAIL_733 (kw 217 DEATHRATTLE)   CREATE spell JAIL_732 zone=HAND        [CREATOR = JAIL_733]
```

- **Gets**: damage, lifesteal healing, the death and a *foreign* deathrattle creation as four different attributions: the card, the card's keyword, the system, and the dying minion (the new Void Soul's `CREATOR` is `JAIL_733`, not the spell). The same windows also contain enchantments created for *other* cards (for example `GBL_002e` created by `EDR_890`, `GBL_009e` by `UNG_024`), which block position would have credited to the spell.
- **Infers**: `DEATH_BY_DAMAGE` (derivable). **Cannot**: that "return this to hand at end of turn" is implemented by the enchantment; that is visible only at the later `MAIN_END` step window.

### 9.9 End-of-turn trigger with a random target: Petal Peddler (`EDR_889`)

Text: "At the end of your turn, give another random friendly Dragon +1/+1."

```
root TRIGGER, STEP = MAIN_END   owner=EDR_889 (kw 32)
  CREATE enchantment EDR_889e ; target Dragon: ATK 5 -> 6, HEALTH 8 -> 9
```

- **Gets**: occurrence, owner, step (`MAIN_END` ⇒ end of turn), the +1/+1 via enchantment lifecycle, the chosen target. One window had one other Dragon (determined), another had two and the first was chosen.
- **Cannot**: randomness, uniformity, whether "another" excludes the source (derivable from the candidate set in the before-state, not provable).

### 9.10 Legality of an unsupported spell: Hold Them Off! (`JAIL_913`)

Text: "Prepare. Give a minion +5/+5 and Lifesteal." 199 option messages with a target list:

| Target | Accepted | Rejected (reason) |
|---|---:|---|
| Enemy minion | 519 | 15 `REQ_ENEMY_TARGET_NOT_IMMUNE`, 15 `REQ_CAN_BE_TARGETED_BY_SPELLS`, 1 `REQ_NONSTEALTH_ENEMY_TARGET` |
| Friendly minion | 191 | 2 `REQ_TARGET_NOT_UNTOUCHABLE`, 1 `REQ_CAN_BE_TARGETED_BY_SPELLS` |
| Hero (either side) | 0 | 420 `REQ_MINION_TARGET` |
| Location | 0 | 242 `REQ_MINION_TARGET` |

This resolves the target topology (any minion, no hero, no Location, subject to immunity/stealth/untargetability) from 710 accepted and 696 rejected **server-validated** target entries, which no effect observation could. It does not prove the effect.

### 9.11 Coverage of the requested categories

| Category | Example | Verdict |
|---|---|---|
| Direct damage / heal | §9.1, §9.3, §9.4 | damage direct; heal conversion needs modifier context |
| Summon / transform | §9.6 | direct; pools not |
| Triggered effect | §9.5, §9.8, §9.9 | direct for occurrence and owner; condition not |
| Generated / random | §9.7, §7.3 | outcome direct; pool not |
| Buff / enchantment | §9.3, §9.4, §9.5 | direct entity; cause via chain |

---

## 10. Unsupported-card detection

**Recommendation: one method, a static, fingerprinted ManaEngine support inventory keyed by card id.** The inventory is exported from the engine's *effective* definition table (after the contract-review and dependency checks in `_load_definitions`) and carries, per id, a state and a reason: `SUPPORTED`, `VERIFIED_VANILLA`, `UNSUPPORTED_DECLARED`, `UNSUPPORTED_NO_DECLARATION`, `UNSUPPORTED_CONTRACT_UNREVIEWED`, `UNSUPPORTED_DEPENDENCY`, `NOT_IN_ENGINE_CATALOG`, plus the inventory id and sha256 so every observation says which inventory it used. It is a generated artifact in the existing style (explicit evidence, not "whichever ignored native binary happens to exist locally").

Why this one:

| Candidate | Verdict |
|---|---|
| **Support inventory from engine definitions** | **Chosen.** Authoritative for ManaEngine (the primary backend), cheap, deterministic, available offline, covers non-collectible ids (hero powers, tokens, enchantments) the engine knows. |
| `SimulationAttempt` `UNSIMULATABLE` reasons / `FailureCode` | Not available: there is **no importer from an observed `GameState` or Power.log position into engine state** (PARTIAL_SIMULATOR_ARCHITECTURE §3, §14), so no attempt can be made on a real root. Later (Phase 4K.7) it becomes a secondary, non-gating annotation: it can attach the precise `FailureCode` (for example `UNSUPPORTED_CARD_BEHAVIOR`) to a window. `ENGINE_DEFECT` is never an evidence subject. |
| Registry `registration_status` / route proposal | Wrong axis: it describes the RosettaStone reference registrations. For example Medivh's Triumph is `DIRECT_SOURCE_BLOCK` there yet has no ManaEngine declaration. Use the registry for *complexity and dependency inputs* (§11), not for support. |
| Text heuristics | Rejected: equal text proves nothing (AGENTS.md). |

**Declaration proxy for the first implementation.** Until the inventory exports exist, read `experiments/manaengine/data/card_abilities.json` and label the basis `DECLARATION_PROXY`. It can only over-state support (a declared card may still be downgraded by contract review or by an unsupported dependency), so the unsupported set it yields is a lower bound. It must be impossible to mistake it for the authoritative basis: the basis is a mandatory field of every record, and aggregates built on a proxy say so.

**Scope of what gets an observation** (measured partition of the 1,450 `PLAY` windows [M]):

| Played id class | Windows | Distinct ids | Treatment |
|---|---:|---:|---|
| Standard root, no ManaEngine declaration | 974 | 251 | Evidence subject |
| Hero power (non-collectible) | 229 | 19 | Evidence subject; own lane (the Mage hero power is the only supported one) |
| Non-collectible spell / Location / minion / weapon (tokens, generated) | 62 / 36 / 29 / 13 | 28 / 2 / 18 / 2 | Evidence subject when unsupported; `NOT_IN_ENGINE_CATALOG` if unknown to the engine |
| ManaEngine-declared | 94 | 28 | `CONTROL_SAMPLE`: first few observations per card only |
| Collectible but not a Standard root (generated outcome) | 12 | 9 | Evidence subject; scope `COLLECTIBLE_NOT_STANDARD_ROOT`; these are *reachable outcomes* worth recording |

Beyond the played card, any **unit owner or created/transformed outcome** that is unsupported becomes a `related_card_ids` entry, and becomes its own observation only if its unit has semantic effects (a quest watcher with an empty trigger is counted, not stored: 78 % of foreign triggers under `PLAY` are empty).

Storage is not the constraint (a window record is small and raw text is never kept); **reviewer attention** is. So everything unsupported is stored cheaply; only the aggregator's priority decides what reaches the review queue (§11).

---

## 11. Prioritisation algorithm

### 11.1 What the logs say about demand [M]

| Measure (25 Ranked Standard games) | Value |
|---|---|
| SELF decision points with a card-effect action (hand play, hero power, Location) | 1,017 |
| …with at least one **unsupported** legal card-effect action | 1,006 (98.9 %) |
| …where **every** card-effect action is unsupported | 491 (48.3 %) |
| Unsupported share of 5,230 legal card-effect actions | 86.6 % (spells 2,465 of 3,143; minions 689 of 713; Locations 828 of 828; hero powers 505 of 505; weapons 41 of 41) |
| Same measure on 2,461 imported decision rows in 34 games (`processed_real`) | 100 % have ≥1 unsupported SELF hand card; 86.1 % of hand slots are unsupported |
| Distinct unsupported collectible ids played | 260; seen in 1 game: 166; ≥2 games: 94; ≥3: 45; ≥5: 23 |
| SELF-played unsupported ids | 90 (42 singletons). Top 5 = 36 %, top 10 = 57 %, top 20 = 76 % of SELF unsupported plays |
| Opponent-played unsupported ids | 223 (168 singletons). Top 10 = 22 %, top 20 = 33 %, top 40 = 48 % |

These are a *proxy* (declared support only) and a **single user's decks**: the SELF concentration is a property of what this user plays. The point for design is the shape: a short head for SELF, a long tail for opponents, and hero powers as a block of 19 ids with 229 plays.

### 11.2 Algorithm (advisory inputs to step 3 of the capability-package process)

The unit that is implemented is a **package**, not a card (AGENTS.md); the algorithm therefore ranks cards, then rolls up to the candidate capability groupings (the classifier's candidate signals first, reviewed groupings once they exist).

For each unsupported subject `c`, over the primary-scope corpus (all games, optionally recency-weighted; every input is recorded):

```
g(c)   = distinct games with a clean observation of c                       (independence)
dS(c)  = SELF decision points where c was a server-validated legal action / all SELF decision points
dO(c)  = opponent PLAY windows of c / all opponent PLAY windows
D(c)   = (dS + 0.25 * dO) * min(1, g / 2)                                  (singleton damping)
R(c)   = evidence readiness of its primary effect claims:
           0.25 no clean observation, 0.50 T0, 0.75 T1, 1.00 T2 or T3 ; 0 and flagged if any claim is CONTRADICTED
K(c)   = complexity weight from the registry route / reviewed capability:
           AUTO 1, COMPOSABLE 2, MISSING_PRIMITIVE 4, CUSTOM or UNKNOWN 8
         + 1 per unsupported static dependency (cap 4) + 4 if a dynamic pool is unresolved
card score  s(c) = D(c) * R(c) / K(c)
package score S(P) = sum_{c in P} D(c) * R(c)  /  (K_shared(P) + sum_{outliers} K(c))
```

Hard gates, applied before ranking:

1. Any `CONTRADICTED` claim or `PATCH_DRIFT_SUSPECTED` goes to review first, whatever its score.
2. Unresolved dynamic pools and unreviewed static edges put the card in a "needs pool/dependency package" lane; they do not disappear, and the pool is never narrowed to implemented outcomes.
3. Hero powers are their own lane (non-collectible, not registry roots, ubiquitous).
4. Evidence must be fresh: a changed support inventory, client build or pinned metadata invalidates `R` and re-queues.
5. `ENGINE_DEFECT` never enters this ranking.

The weights (0.25, the readiness values, the complexity table) are an initial transparent heuristic. They are **recorded with each queue row so the ranking can be audited and tuned**, and nothing here replaces the process's own grouping and package-cost estimation. A dated meta-frequency dataset, if one is attached later, replaces `dO`; the registry reports none for 2026-10-01.

### 11.3 Baseline from the local corpus (illustrative, one user's decks)

SELF decisions affected (of 1,017), with registry route and dependency data:

| Card | Decisions (games) | Plays (games) | Registry route / registration | Notes |
|---|---:|---:|---|---|
| `CATA_301` Ruby Sanctum (Location) | 550 (19) | 62 (19) | UNKNOWN / none | persistent "next healing" enchantment; confounds other cards (§9.4) |
| `EDR_449p` hero power (Imbue) | 359 (21) | n/a | not a root | hero-power lane |
| `JAIL_913` Hold Them Off! | 300 (19) | 25 (16) | UNKNOWN / none | legality already resolved (§9.10) |
| `CATA_308` Medivh's Triumph | 288 (18) | 25 (14) | COMPOSABLE / Rosetta-registered | amount variants need modifier context |
| `END_025` Eternal Firebolt | 241 (16) | 61 (14) | UNKNOWN / none | nested lifesteal + return-to-hand |
| `CORE_EX1_197` Shadow Word: Ruin | 210 (18) | 27 (14) | COMPOSABLE / Rosetta-registered | conditional mass destroy |
| `TLC_816` Gravedawn Sunbloom | 190 (15) | 24 (n/a) | COMPOSABLE / Rosetta-registered | draw |
| `TIME_432` Intertwined Fate | 168 (18) | 44 (17) | UNKNOWN / none | 2 unresolved dynamic pools |
| `CORE_BAR_311` Devouring Plague | 132 (17) | 26 (17) | CUSTOM / Rosetta-registered | random split damage, 1 pool |
| `EDR_476` Moonwell | 125 (18) | 27 (16) | COMPOSABLE / effect-composition | damage 4 ×62, 0 ×6, 8 ×43 |

The takeaway is not this list but what it shows: the head is dominated by cards a *package* would cover together (heal/damage conversions, Locations, hero powers), and the cheapest high-demand wins (hero powers, simple fixed effects) are invisible to a "complete Standard alphabetically" order.

---

## 12. Relationship to neural fallback

```
decision (live root or, later, a search node)
   |
   +-- attempt_action(root, a)                                   [implemented, Phase 4K.1]
   |      COMPLETED     -> exact/inferred afterstate -> Value (evidence debt kept)
   |      UNSIMULATABLE -> [future] Q_fallback(state, a)          (only fallback-eligible reasons)
   |      ILLEGAL | ENGINE_DEFECT | BUDGET_LIMIT -> never fallback
   |
   +-- (offline, after the match)  evidence extractor              [this design]
          every unit whose owner is unsupported -> observation -> card aggregate -> review queue
          -> reviewed contract -> capability package -> declarations -> engine support inventory changes
          -> that card leaves the unsupported set; its decisions leave the fallback burden
```

How they coexist:

- **Different axes, no shared state.** Evidence has no runtime influence and no online updates. A decision's route (exact, inferred, fallback) is decided by the engine's typed result; evidence only explains *which cards cause fallback and how often* (`dS`).
- **The headline metric is the neural-only share.** Today, under the declared-support proxy, 98.9 % of SELF decisions have at least one unsimulatable legal action and 48.3 % have only such actions. The same measurement, recomputed against each new support inventory, shows the system retiring fallback decisions package by package. Supported cards then become `CONTROL_SAMPLE` drift sentinels.
- **Evidence never creates a transition.** A fallback consumes a valid pre-action state and an action descriptor; evidence bundles do not feed it fabricated afterstates, and an unsupported card is never replaced by an observed effect in the simulator.
- **Possible, explicitly unauthorised future use:** public effect deltas as auxiliary supervision for the fallback network. That would be a separate dataset with its own authorisation and a leakage review; evidence bundles are not Value or Q labels and nothing here starts it.
- **Hidden-information consistency.** The same public-state projection feeds the model and the evidence's `public_states`; offline-only facts never cross.
- **Triage classes need an engine expectation.** For an unsupported card only `NOVEL_OBSERVATION` and `PATCH_DRIFT_SUSPECTED` are reachable. `KNOWN_EXPECTED`, `KNOWN_INFERRED_CONFIRMED` and `ENGINE_CONTRADICTION` become available for supported cards once a replay comparator exists (after an observed-state importer, Phase 4K.7).

---

## 13. Regression-fixture path

Evidence → fixture is a reviewed, staged path, not generation of engine code:

| Stage | Artifact | Who/what | Automated? |
|---|---|---|---|
| E1 | Observations (facts, inferences, confounders) | extractor | yes |
| E2 | Card aggregate (typed claims, tiers, outcome sets, never-claimed list) | aggregator | yes |
| E3 | **Card dossier**: pinned card text, claim table, the 3 cleanest canonical windows, confounded windows, outcomes with unseen-mass estimates, legality requirement codes seen, open questions (unexplained amounts, hidden conditions, candidate-set questions), related unsupported cards | generator | yes |
| E4 | Reviewed contract (capability-package proposal: semantic contract, risks, custom outliers) | human/agent | no |
| E5 | **Fixture spec**: `{card_id, contract_ref, claims, cases:[{preconditions as predicates over public state, action, expected effects, expected public delta, provenance observation ids}], negative cases (predicate false ⇒ no effect), random cases (outcome ∈ approved manifest, never equality)}` | generated from *approved* claims; expected values reviewed | partly |
| E6 | Scenario materialisation | today a hand-authored deck-order scenario guided by the spec's minimal preconditions; after an observed-state importer, seeded from `public_states.before` | partly |
| E7 | Replay comparator: engine `attempt_action` result vs observed `after` on public fields only; random effects compared by membership | future (needs Phase 4K.7) | future |

Constraints this must respect, from the current code: ManaEngine sessions are built from two decks and game setup (the native tests use filler decks with `shuffle=False` to control draw order), only Mage-mirror sessions are admitted, and there is no importer from an arbitrary `GameState`. So before 4K.7 a fixture spec is an *independent expected-behaviour document with minimal preconditions*; the implementer builds the scenario by hand. The spec removes log reading and transcription, not scenario design.

Status vocabulary: a fixture derived from logs carries `DIRECT_REPLAY_OBSERVED`; it can only become `DIRECT_REPLAY_VERIFIED` after an engine replay of the same before-state reproduces the after-state. Neither is `REVIEWED_INFERRED`, a rules verification, or training admission. Because these expectations come from the client rather than from a declaration generator, they are **independent** of the code under test (AGENTS.md: family scenarios need independent expectations), provided expected values are reviewed and never edited to match the engine.

Effort accounting follows the package process (record authoring, review, debug and build effort and correction cycles per package, with and without a dossier). No automation percentage is promised.

---

## 14. Risks

| Risk | Evidence | Mitigation |
|---|---|---|
| **Tiny, biased corpus** | 25 Ranked Standard games; one user's decks; 166 of 260 unsupported ids seen in one game | Ordinal tiers, games as the independence unit, singleton damping, recency weighting optional; never rank by raw counts. Collect continuously via the existing collector. |
| **Wrong SELF** | A first-`Choices` rule picked the wrong player in 15 of 25 games and silently inverted every SELF/opponent statistic, including the hidden-information counts | Use the project's rules (hand identity; LIVE-0A found the `SendChoices` owner agreed with it in 13 of 13 games, which my `Choices` variant did not), cross-check, and **skip the game** on disagreement (`UNTRUSTED_SELF`). Test with both orders of player ids. |
| **Privacy leak** | `repr(PlayerReference)` and `DebugPrintGame` carried a BattleTag/account id into tool output during this audit | Never `repr()` hslog player objects; never print exception text; canary test (§8 H7). |
| **Missed state in SubSpell** | 29 % of creations and 28 % of reveals are inside `SubSpell` | Walker descends into it; a synthetic-log test asserts a creation inside a SubSpell is extracted. |
| **Attribution errors** | Stale `LAST_AFFECTED_BY`; `CREATOR` absent on 9–11 % of created cards; 296 stat changes outside blocks; 49 unexplained | Precedence rules, same-unit-only `LAST_AFFECTED_BY`, explicit `UNATTRIBUTED`, confounders, and a conservative aggregator that excludes them. |
| **Confounded observations learned as rules** | Healing spell logged as 8 damage; a "1-Cost" pool of 2–7-cost outcomes | Confounder detection, `CONTRADICTION_WITH_METADATA_PREDICATE`, review before any contract. |
| **Hidden condition inputs** | Opponent gated battlecries (Broodmother, Weaver) | Outcome-only counts, `OFFLINE_ONLY_HIDDEN` inferences, no controlled negatives for opponent plays. |
| **Patch drift and mode** | All 40 logs report `BuildNumber=253216`; the pinned snapshot is the collectible slice of hsdata "patch 36.6.3.253932" (Fire-pool audit). The two numbers are different identities and their relationship (same scale or not, older or newer) is not established here [I]; non-Standard games share the log format | Record the log's build and `rules_scope` per observation; compare observed outcomes with the pinned snapshot rather than assume equality; a build different from the build of the pinned inputs ⇒ `PATCH_DRIFT_SUSPECTED` candidate, not rejection; never mix `OTHER_MODE_SECONDARY` into primary aggregates. |
| **Enum drift** | Unnamed tag and keyword ids in `hearthstone` 9.21.1; 3,371 `TRIGGER` blocks carry keyword 4297 | Store numeric ids, count unknown tags per window, treat them as confounders when they change in a window. |
| **Support inventory stale or proxy-only** | Native module not built here; declarations over-state support | Mandatory `basis` and `inventory_sha256` in every record; stale inventory invalidates aggregates. |
| **Conflation with training** | Evidence resembles labelled states | `model_input_allowed: false`; one-way import test; evidence never writes registry or weights. |
| **Review overload** | 260 unsupported ids in 25 games | Priority queue with gates; storage cheap, attention scarce. |
| **Legality channel overreach** | State-specific, SELF-only, one reason per target | Aggregate requirement codes seen, never "legal set"; keep state predicates; cause of flips (§9.1) stays open. |
| **Over-claiming from repetition** | 61 plays of one card in 14 games | Games as unit; "never claimed" list in every claim. |
| **Parsing cost and brittleness** | Prototype walked 25 games (178,700 events) in seconds | Single pass per game; incremental use of the live `GameReducer` is possible later; do not run extraction inside the live tail loop. |

---

## 15. Exact next bounded implementation task

**Model choice: Claude Sonnet 5.5 Medium.** The work is Python-only, deterministic parsing and aggregation over a tree the audit has already characterised; every rule is specified here and every pitfall is enumerable as a test. The hard parts (attribution precedence, SubSpell, SELF detection, privacy) are correctness-by-test, not research. It touches no ML, engine, live or registry code, so it does not collide with ML-1B. If attribution takes more than two correction cycles, re-run just that module at Extra effort rather than switching models. GPT-6.1 Sol Medium would also be capable; the deciding factor is that the code this task extends (the shared powerlog ingestion helpers, the live reducer, the visibility allowlist and their privacy tests) and the LIVE-0A audit were all produced with Sonnet 5.5 [S: `Co-Authored-By` trailers on `cecf923`, `7186fe2`, `7ffe310`, `71ef2ea`], so the conventions to match are already in that model's working set, whereas the heavy native/C++ work, where the other model has been used, is not part of this task.

Copy-ready task:

````text
# ManaMind EVIDENCE-0B — Unsupported Card Evidence Extractor

MODEL: Claude Sonnet 5.5 — Medium
MODE: BOUNDED IMPLEMENTATION (Python only)
Repository: MaksimOrekhov/manamind
Base: latest origin/main (re-check; the audit was written at 18e328a1365aa1c201924736376386f841c67b0e)
Branch: feat/evidence0b-unsupported-card-extractor

Another agent works on ML-1B (policy dataset). Do NOT touch ML, policy, live runtime, ManaEngine, the registry,
card declarations, or the overlay.

READ FIRST
reports/mechanic_discovery/EVIDENCE0A_REAL_CARD_MECHANIC_DISCOVERY.md (this task implements its sections 4-8, 10)
reports/mechanic_discovery/EVIDENCE_BUNDLE_SCHEMA_PROPOSAL.json
docs/PARTIAL_SIMULATOR_ARCHITECTURE.md, docs/LIVE_BRIDGE.md, docs/REAL_MATCH_DATA.md
src/manamind/integrations/powerlog/, src/manamind/live/ (reducer.py, visibility.py, session.py, trust.py)
tests/power_log_fixtures.py, tests/live_fixtures.py (synthetic Power.log builders)
experiments/manaengine/data/card_abilities.json (support declarations)

GOAL
Turn finished Power.log games (collector slices, live recordings or raw logs) into versioned, local, sanitized
evidence observations about UNSUPPORTED cards, and aggregate them per card and typed claim. Offline only.
No automatic rule, manifest, registry or model changes. No Q fallback. No fixtures generation (that is later).

DELIVERABLES
1. src/manamind/evidence/ (pure Python; imports only stdlib, hslog/hearthstone, manamind.cards, manamind.domain,
   manamind.integrations.powerlog, manamind.live.visibility/reducer helpers):
   - tree.py: pre-order walk of a parsed game that DESCENDS INTO Block AND SubSpell; flattens to units
     (owner, type, trigger keyword raw value, parent, depth, direct packets); SubSpell is transparent.
   - entities.py: time-ordered entity table (card_id, tags, controller, zone, created_in unit); FULL_ENTITY+SHOW_ENTITY
     merged for CARDTYPE/CREATOR/ATTACHED; unknown numeric tag ids preserved as strings, never dropped.
   - facts.py: typed fact extraction (damage packet from META DAMAGE + DAMAGE/ARMOR/DIVINE_SHIELD deltas, healing,
     zone move, creation, transform, reveal, enchant attach/remove, stat/keyword delta, death, choice offer/pick,
     TARGET_LEGALITY from playable Options entries incl. server error code).
   - attribution.py: precedence CREATOR_TAG > LAST_AFFECTED_BY set in the SAME unit > UNIT_OWNER > UNATTRIBUTED;
     foreign-unit effects are NESTED_ONLY and never in the subject's profile; causal_link DIRECT/STRUCTURAL/none.
   - confounders.py: foreign enchantment active on the same effect, foreign unit with effects, stale
     LAST_AFFECTED_BY, aura recalculation outside blocks, unknown tag ids in window, hidden condition input.
   - visibility.py: per-fact PUBLIC_TO_SELF / SELF_PRIVATE / OFFLINE_ONLY_HIDDEN using the live allowlist
     semantics (default deny); public before/after states ONLY via to_visible_state(...,
     opponent_identity_policy="none", hand_order="zone_position").
   - support.py: load a support inventory JSON {inventory_id, cards:{id:{state,reason}}} (sha256 recorded);
     if absent, derive from card_abilities.json and mark basis DECLARATION_PROXY (never silently authoritative).
   - extract.py: game -> observations (subjects: unsupported played cards, hero powers, Location activations,
     attackers, trigger/deathrattle/turn-phase owners WITH semantic effects; CONTROL_SAMPLE for supported cards,
     max 3 per card). Empty watcher triggers are counted, not stored.
   - aggregate.py: observations -> card aggregates with typed claims and tiers T0..T3 exactly as the report
     defines (games are the unit of independence; contradiction => CONTRADICTED; fixed never_claimed list;
     unseen-mass estimate for outcome sets; N1 never emitted as "cannot").
   - queue.py: priority inputs and a deterministic review_queue.json (formula in report 11.2; inputs recorded;
     ties by card_id).
   - schema.py: dataclasses + validators mirroring EVIDENCE_BUNDLE_SCHEMA_PROPOSAL.json (schema versions
     manamind.evidence.observation/1 and manamind.evidence.card_aggregate/1).
2. scripts/extract_evidence.py --input <Power.log | slice.log | directory> --output <NEW dir under
   data/processed_evidence/<extractor_version>/> [--support-inventory FILE] [--catalog FILE]. Refuse to
   overwrite an existing output. Print only aggregate counts and exception CLASS names.
3. A short docs/EVIDENCE_PIPELINE.md (operating guide: lanes, privacy rules, schema versions, how to rerun).
4. Tests under tests/ (use the synthetic log builders; no real logs in the repo):
   - SubSpell creation is extracted (a FULL_ENTITY inside SUB_SPELL_START is not lost).
   - PLAY with an own POWER child, a foreign effectful TRIGGER and an empty watcher: effects attributed to the right
     units; foreign effects NESTED_ONLY; empty watcher counted only.
   - CREATOR beats block owner; LAST_AFFECTED_BY ignored when not set in the same unit; stale value flagged.
   - Foreign enchantment rewriting a heal into damage => FOREIGN_ENCHANTMENT_ACTIVE, observation excluded from clean counts.
   - Conditional effect: controlled positive/negative for SELF evaluated from the before-state; opponent => outcome-only.
   - Hidden-info: opponent HAND/DECK/SECRET identity, OVERRIDE_HISTORY reveal, SHOW+HIDE transient => OFFLINE_ONLY_HIDDEN and
     absent from public_states.
   - SELF detection: project rules, cross-check; disagreement => game skipped (UNTRUSTED_SELF). Test both player-id orders.
   - Unknown numeric tag/keyword ids preserved; client build, game type and format recorded; non-Standard mode =>
     OTHER_MODE_SECONDARY and never mixed into primary aggregates.
   - Privacy canary: plant a sentinel BattleTag/PlayerName/account id in the synthetic log; assert absent from every output
     file, stdout and every error string; assert no repr() of hslog player objects is used.
   - Determinism: same input => identical observation ids and bytes; different extractor_version => different directory.
   - Aggregator: 61 plays in 1 game count as 1 clean game; n-of-1 never exceeds T0; contradiction => CONTRADICTED;
     a never-targeted-friendly value is only a descriptive count.
   - Import boundary: a static test that manamind.encoding / models / training / inference / live do not import manamind.evidence.
5. Smoke on the local logs (NOT committed): run on the 25 Ranked Standard games, compare aggregate counts with the report
   (PLAY roots 1,450; root TRIGGER 7,192; enchantment creations 1,171 all with CREATOR+ATTACHED; foreign-trigger and
   attribution shares within +-2 points), and report aggregate numbers only.

CONSTRAINTS
- Python only; add no dependency. Keep modules small. Follow AGENTS.md (hidden-information boundary, no player names,
  preserve raw logs, new output paths only). Do not print or commit names, BattleTags, account ids or raw lines.
- Do NOT change src/manamind/live, encoding, models, training, inference, integrations/manaengine, configs, registry files,
  card declarations or any generated artifact. Do NOT add an evidence call to the live tail loop or the collector.
- The support inventory export from the native engine is OUT OF SCOPE; only consume it.
- No automatic rule/fixture/engine generation. No claim of rules verification anywhere in the output.

VALIDATION
ruff clean; full pytest (new tests included); git diff --check; python scripts/check_generated_artifacts.py unchanged;
report exact base SHA; confirm no files outside src/manamind/evidence, scripts/extract_evidence.py, docs/EVIDENCE_PIPELINE.md,
tests/ changed.

COMMIT / PUSH
feat(evidence): extract unsupported-card mechanic evidence from Power.log
Push feat/evidence0b-unsupported-card-extractor. Do NOT merge.

FINAL VERDICT (exactly one): EVIDENCE0B_COMPLETE | EVIDENCE0B_PARTIAL | EVIDENCE0B_BLOCKED
````

---

## Validation (EVIDENCE-0A)

- Base: `origin/main` = `18e328a1365aa1c201924736376386f841c67b0e`, unchanged at the end of the task.
- Changes: this report and `EVIDENCE_BUNDLE_SCHEMA_PROPOSAL.json` only, under `reports/mechanic_discovery/`. No production, ML, policy, live, ManaEngine, registry or overlay file touched.
- Local data was read read-only; nothing was written under `D:\Games\Hearthstone\Logs`, `data/raw` or `data/processed_real`.
- Schema JSON parses and its two examples validate against it with a minimal in-scratch validator; all `$ref`s resolve.
- `git diff --check` on the staged change: PASS (no whitespace errors). Re-fetched `origin/main` at the end: still `18e328a1365aa1c201924736376386f841c67b0e`.
- Verdict: `EVIDENCE0A_READY`.
