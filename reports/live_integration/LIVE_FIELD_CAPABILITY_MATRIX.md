# LIVE-0A — Field capability matrix

Companion to [LIVE_REALTIME_BRIDGE_AUDIT.md](LIVE_REALTIME_BRIDGE_AUDIT.md). Read the audit first; this file only holds the per-field comparison.

## How to read this table

**Capability grades**

| Grade | Meaning |
|---|---|
| `DIRECT` | The source states the value (a tag, a line or an API member) with no inference. |
| `DERIVABLE` | Fully determined by direct values through a known formula or reduction. |
| `UNRELIABLE` | Obtainable, but only through heuristics, card-specific special cases, or with known leakage/false-positive risk. |
| `NOT AVAILABLE` | The source does not carry it. |

**Evidence level** (last letter of each Power.log cell): **[M]** measured on the local logs described in the audit (§0), aggregate-only; **[S]** read from upstream source (file:line in the audit); **[I]** inference, not verified locally.

**"Safe to expose"** is a separate decision from capability. A field can be `DIRECT` internally and still be excluded from the live DTO. Columns:

- `EXPOSE` — goes into the sanitized live snapshot.
- `COUNT` — only a count crosses the sanitization boundary.
- `HANDLE` — only an action handle (entity id) in a side channel; never a model input.
- `EXCLUDE` — never crosses the boundary.

**"ManaMind today"** reports what `scripts/import_power_log.py` already projects into `GameState` at base `55f95a9`.

"HDT" means the in-process object model of Hearthstone Deck Tracker v1.58.7 (`Core.Game`, `Entity`, `Player`, `GameEvents`) as read from source. HDT builds that model from the same Power.log, plus memory reads (`HearthMirror`) for a few facts.

## GAME

| Field | Power.log | HDT | Safe to expose | ManaMind today | Notes |
|---|---|---|---|---|---|
| Session id (client launch) | DERIVABLE — newest `Logs/Hearthstone_<ts>/` folder name [M] | NOT AVAILABLE as a plugin API value | EXPOSE | not imported | Folder is created per client launch. |
| Game id | DERIVABLE — `start_key` = sha256 of the `CREATE_GAME` header up to the first `Player` line (the collector's rule); contains a per-game seed [M: stable while the file grows] | DIRECT but useless for correlation: `GameStats.GameId = Guid.NewGuid()` (`Stats/GameStats.cs:77`) | EXPOSE | importer uses random `uuid4` | Use the collector's `start_key` so live and post-match capture share one key. |
| Mode / format | DIRECT — `GameState.DebugPrintGame() - GameType=…` / `FormatType=…` lines inside the `CREATE_GAME` section [M: present in 14/14 games] | DIRECT via memory read (`GameV2.cs:427-434`, `HearthMirror.Reflection.Client.GetGameType/GetFormat`) | EXPOSE | collector requires exactly one consistent pair | No memory reading needed. |
| Client build | DIRECT — `BuildNumber=` in `DebugPrintGame` [M] | DIRECT (`GameInfo.BuildNumberRegex`) | EXPOSE | not imported | Record for patch-drift diagnosis. |
| Turn number | DIRECT — `GameEntity` tag `TURN` [M] | DIRECT (`Game.GetTurnNumber()`) | EXPOSE | imported | `TURN` counts both players' turns. |
| Active player | DIRECT — `CURRENT_PLAYER` on a player entity [M] | DIRECT (`Entity.IsCurrentPlayer`) | EXPOSE | imported | |
| Game start | DIRECT — `CREATE_GAME` [M] | DIRECT (`GameEvents.OnGameStart`) | EXPOSE | collector segments on it | |
| Game end / result | DIRECT — `GameEntity STATE=COMPLETE`, player `PLAYSTATE` WON/LOST/TIED [M] | DIRECT (`OnGameEnd/Won/Lost/Tied`) | EXPOSE | importer label | EOF is never completion (collector rule). |
| Mid-game start / reconnect re-dump | DERIVABLE — a `CREATE_GAME` whose header already has `TURN>0` (collector `SKIPPED_MID_GAME_START`) [S]; **not observed in the local logs** [I] | DIRECT-ish — `LoadingScreen.log` `MulliganManager.HandleGameStart … IsPastBeginPhase()=True` → `HandleGameReconnect` [S]; LoadingScreen.log reported length 0 in the running session [M] | EXPOSE as status | skipped | See audit §10. |
| Spectator mode | DERIVABLE — `Begin Spectating …` / `Start Spectator Game` marker lines (hslog `SPECTATOR_MODE_*`) [S] | DIRECT (memory: `IsSpectating`) | EXPOSE as status | not handled | Unsupported in V1: hands of the spectated player may be visible. |

## SELF (the local player)

| Field | Power.log | HDT | Safe to expose | ManaMind today | Notes |
|---|---|---|---|---|---|
| Which player is SELF | DERIVABLE — owner of the entities in the client-sent `SendChoices` (mulligan), or the player whose hand entities carry card ids [M: both rules agreed in 13/13 games] | DIRECT via memory (`MatchInfo.LocalPlayer.Id`, `GameV2.cs:419`) | EXPOSE (as `SELF`) | heuristic (hand with ids) | Cross-check both rules; disagreement → `UNTRUSTED`. |
| Hero health | DERIVABLE — `HEALTH − DAMAGE` on the hero entity (`HERO_ENTITY` of the player) [M] | DIRECT (`Entity.Health`) | EXPOSE | imported | |
| Armor, hero attack | DIRECT — `ARMOR`, `ATK` [M] | DIRECT | EXPOSE | imported | |
| Hero power | DIRECT — `CARDTYPE=HERO_POWER` entity in `PLAY`; used = `EXHAUSTED` [M] | DIRECT (`Player.Board`) | EXPOSE | imported (`hero_power_ready`) | |
| Weapon | DIRECT entity; durability in **`HEALTH` − `DAMAGE`** [M: 19/19 weapon entities carry `HEALTH`, 0/19 carry `DURABILITY`] | DIRECT | EXPOSE | **importer reads the `DURABILITY` tag, so `current_durability` is always `None` on real logs** | Importer defect candidate (audit §17). |
| Mana crystals / available | DERIVABLE — player tags `RESOURCES`, `RESOURCES_USED`, `TEMP_RESOURCES`, `OVERLOAD_LOCKED` [M] | DIRECT (same tags) | EXPOSE | imported | |
| Overload (locked now / owed next) | DIRECT — `OVERLOAD_LOCKED`, `OVERLOAD_OWED` [M] | DIRECT | EXPOSE | imported | |
| Hand identities | DIRECT — `card_id` on `HAND` entities [M: SELF hand always carried ids] | DIRECT (`Player.Hand`) | EXPOSE | imported | Identity = `card_id` only. |
| Hand order | DIRECT — `ZONE_POSITION` [M] | DIRECT | EXPOSE | imported (ordered) | |
| Hand size | DIRECT (entity count) | DIRECT | EXPOSE | imported | |
| Cost in hand | DIRECT — `COST` tag [M] | DIRECT (`Entity.Cost`) | EXPOSE | imported (`current_cost`) | |
| Board (minions, locations) | DIRECT — `PLAY` zone, `CARDTYPE` MINION/LOCATION, `ZONE_POSITION` [M] | DIRECT | EXPOSE | imported (shared board order) | |
| Minion stats | DERIVABLE — `ATK`, `HEALTH`, `DAMAGE` [M] | DIRECT | EXPOSE | imported | Effective values, not base. |
| Keyword/state tags | DIRECT — `TAUNT`, `DIVINE_SHIELD`, `STEALTH`, `FROZEN`, `SILENCED`, `IMMUNE`, `RUSH`, `CHARGE`, `WINDFURY`, `LIFESTEAL`, `POISONOUS`, `REBORN`, `DORMANT` [M/S] | DIRECT | EXPOSE | imported | |
| Enchantments / buffs | DIRECT as separate entities (`CARDTYPE=ENCHANTMENT`, `ATTACHED`, `CREATOR`) [S: HDT `Entity.IsEnchantment/IsAttachedTo`]; stat effects already folded into `ATK/HEALTH` | DIRECT | EXPOSE only if a consumer needs them | not imported | Effective stats are the model input; list is optional. |
| Attacks remaining / can attack | DERIVABLE — `NUM_ATTACKS_THIS_TURN`, `WINDFURY`, `EXHAUSTED`, `FROZEN`, `CANT_ATTACK`, `ATK` [M]; **or DIRECT from the options message** (`error=NONE` on the attacker) [M] | DERIVABLE | EXPOSE | approximated (`can_attack` formula) | The options message is the server's own answer and removes the approximation. |
| Deck size | DIRECT (count of `DECK` entities) [M] | DIRECT (`Player.DeckCount`) | COUNT | imported | |
| Deck contents / order | NOT AVAILABLE for the hidden part. Known cards shuffled in appear with ids [M: SELF DECK with `card_id`, up to 5 per snapshot]; initial deck entities have no `ZONE_POSITION` [M] | HDT knows the *decklist* (deck manager / memory) — **not** present in Power.log | EXCLUDE | not imported | A SELF decklist would have to come from the user. |
| Own secrets | DIRECT — `SECRET` zone with `card_id` [I: only one opponent-side secret was seen locally] | DIRECT (`Player.Secrets`) | EXPOSE (SELF only) | `secret_count` default 0, not filled | Verify in prototype. |
| Fatigue | DIRECT — player tag `FATIGUE` [M] | DIRECT | EXPOSE | imported | |
| Spell damage, spells cast this turn, discounts | DERIVABLE only with card-specific rules [I] | partial | EXPOSE when derivable | not filled | `GameState` has fields; the importer leaves them unset. |

## OPPONENT

| Field | Power.log | HDT | Safe to expose | ManaMind today | Notes |
|---|---|---|---|---|---|
| Hero health / armor / attack | DIRECT / DERIVABLE as SELF [M] | DIRECT | EXPOSE | imported | Public. |
| Hero power, weapon | DIRECT entities in `PLAY` [M] | DIRECT | EXPOSE | imported | Same weapon-durability caveat. |
| Mana | DERIVABLE — public player tags `RESOURCES`, `RESOURCES_USED` [M] | DIRECT | EXPOSE | imported | |
| Hand **size** | DIRECT — count of `HAND` entities [M: hidden entities carry only `ZONE`, `CONTROLLER`, `ENTITY_ID`, `ZONE_POSITION`, sometimes `DISPLAYED_CREATOR`/`EVIL_GLOW`/`SHATTERED`] | DIRECT (`Player.HandCount`) | COUNT | imported | |
| Hand **identities** | UNRELIABLE — the log shows an id for ≤2 opponent hand entities per snapshot that hslog does not mark `revealed` [M: 13/62 snapshots in one game]; HDT has special-case suppression of identities the log carries but the UI does not show (`PowerHandler.cs:~400`, `TagChangeActions.cs:~987`) [S] | UNRELIABLE (internal `Info.Hidden`, `GuessedCardState`, predicted cards) | EXCLUDE in V1 (see audit §5) | imported when `revealed` | V1 live DTO sets opponent known cards to empty until a per-case review exists. |
| Board, stats, keywords | DIRECT / DERIVABLE [M] | DIRECT | EXPOSE | imported | Public. |
| Enchantments on opponent minions | DIRECT as entities [S] | DIRECT | EXPOSE if needed | not imported | |
| Secrets (count) | DERIVABLE — entities in `SECRET` zone [I] | DIRECT (`Player.Secrets`) | COUNT | not filled | Identity hidden until it triggers. |
| Secrets (identity) | NOT AVAILABLE until trigger/reveal [I] | HDT *guesses* possible secrets (`Hearthstone/Secrets/`) — inference | EXCLUDE | rejected by `GameState` validation | Never consume HDT guesses. |
| Deck size | DIRECT (count) [M] | DIRECT | COUNT | imported | |
| Deck identities | NOT AVAILABLE for hidden cards; **publicly shuffled-in cards appear with ids and full tags** (up to 10 per snapshot) [M] | HDT predicts deck contents (`OpponentCardList`, `GetPredictedCardsInDeck`) — inference | EXCLUDE | not imported | Order is hidden; ids are opaque. |
| Set-aside / removed-from-game entities | present with ids in places [M: ≤1 opponent `SETASIDE` entity per snapshot] | DIRECT (`Player.SetAside`) | EXCLUDE | not imported | Not a player-visible zone. |

## PUBLIC HISTORY

| Field | Power.log | HDT | Safe to expose | ManaMind today | Notes |
|---|---|---|---|---|---|
| Cards played (both sides) | DERIVABLE — `BLOCK_START BlockType=PLAY` with entity/card id [M: PLAY blocks present] | DIRECT (`GameEvents.OnPlayerPlay/OnOpponentPlay`) | EXPOSE (V2) | used to cut importer snapshots | |
| Revealed generated cards | UNRELIABLE — `SHOW_ENTITY` inside `META_DATA Meta=OVERRIDE_HISTORY` blocks is not UI-visible [M: 33 such blocks in 14 games; reveals of SELF DECK ×20, SELF SETASIDE ×7, OPP PLAY ×10, OPP SETASIDE ×6] | UNRELIABLE (HDT hides these: `HideShowEntities`, `PowerHandler.cs:623-629`) | EXCLUDE until reviewed | not handled | Central hidden-information finding. |
| Known secrets / reveals | DIRECT only when the secret triggers or is revealed [I] | DIRECT after reveal | EXPOSE after reveal (V2) | not handled | |
| Graveyard / deaths | DERIVABLE — `GRAVEYARD` zone entities with ids [M: weapons and others end there] | DIRECT (`Player.Graveyard`) | EXPOSE (V2) | not imported | Public for minions that died; verify per type. |
| Entity ids | DIRECT [M] | DIRECT | HANDLE | not in `GameState` | Action handles only. Measured: no significant correlation between entity id and draw order (ρ = 0.41, −0.05, −0.15 on n = 18/14/11). |
| Choices made (SELF) | DIRECT — client-sent `SendChoices`, `SendOption` [M] | DIRECT (internal choice handling; no plugin event) | EXPOSE (V2) | not imported | |

## CHOICES AND LEGAL ACTIONS

| Field | Power.log | HDT | Safe to expose | ManaMind today | Notes |
|---|---|---|---|---|---|
| Legal actions for SELF | **DIRECT — `GameState.DebugPrintOptions`: each playable card/attacker/hero power with a server-validated `error=NONE`, plus `target` sub-lines with per-target errors** [M: 74 and 42 option messages in the two complete local games, equal to the number of `SendOption` actions] | not exposed as a plugin event (`GameEvents` has no options/choice hook) | HANDLE (+ card ids) | not imported | Replaces a legal-move generator for the live root. Board *position* of a played minion is not enumerated. |
| Decision-point marker | DERIVABLE — options message with ≥1 `error=NONE` option, then visual settle (audit §9) [M] | n/a | EXPOSE (as `decision`) | cut at PLAY/ATTACK blocks instead | |
| Discover / Choose One options visible to SELF | DIRECT — `DebugPrintEntityChoices` entities with ids for SELF's own choice [M]; the opponent's appear with blank ids [M] | partial (`Player.OfferedEntities` set by `HandlePlayerEntityChoices`, `GameEventHandler.cs:1539`) | EXPOSE (SELF only) | not imported (`pending_choice_*` empty) | |
| Pending choice | DERIVABLE — offered without matching `EntitiesChosen` [M: `ChoiceCardMgr` WAIT/BEGIN lines tie it to a task list] | DERIVABLE | EXPOSE | not imported | |
| Targeting state (cursor, drag) | NOT AVAILABLE | NOT AVAILABLE (HDT hover events are about its own overlay) | — | — | Only the *legal* targets exist in the log. |
| Mulligan | DIRECT — `EntityChoices` with `ChoiceType=MULLIGAN`; SELF's offered ids visible [M] | DIRECT (`OnPlayerMulligan`) | EXPOSE (SELF) | not imported | |

## Timing facts used by the matrix (all from the audit's measurements)

- A hidden opponent hand entity carries four tag names (`ZONE`, `CONTROLLER`, `ENTITY_ID`, `ZONE_POSITION`), sometimes with `DISPLAYED_CREATOR`, `EVIL_GLOW` or `SHATTERED`. Visible entities carry full tag sets.
- `GameState` lines lead `PowerTaskList` lines (the UI order) by a median of 0.3-1.0 s. When the server's options message arrives, the client's own task-list queue has exactly one list left to finish in 71-81 % of cases and none in 19-29 % (never more than one in the local logs).
- Therefore every field above must be read from the state *after* the visual stream has settled (audit section 9), not from the first state in which it appears.
