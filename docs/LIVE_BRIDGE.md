# Live bridge: FIRST_LIVE_STATE

While Hearthstone runs, `scripts/live_state.py` follows the growing `Power.log` and prints one
**sanitized, settled** snapshot at every decision point of the local player (SELF). The unified
runner ranks the complete legal SELF menu with a pinned behavior-cloning policy, uses the existing
collector to retain completed matches, and can show a small Windows Tkinter always-on-top panel.
The panel is read-only; there is no ManaEngine import, search, HDT, OCR or memory reading.

Design and evidence: [LIVE_REALTIME_BRIDGE_AUDIT.md](../reports/live_integration/LIVE_REALTIME_BRIDGE_AUDIT.md).
This page is the operating guide.

## Start

For the Windows MVP, install dependencies once and run the unified workflow from the repository
root. The default selects frozen Policy v2 and checks its pinned SHA-256 before loading:

```powershell
python -m pip install -e ".[dev,replays]"
python scripts/run_manamind.py --ui --logs-root "D:\Games\Hearthstone\Logs"
```

Close the panel or press Ctrl+C in the console to stop. `--ui` uses Python's standard Tkinter; no
second server, process, Electron or Tauri installation is needed. The runner follows Power.log,
records replayable LIVE slices under `data/raw/live/`, and invokes
the existing completed-match collector every five seconds. New raw matches are retained under
`data/raw/collected/` and imported using the collector's existing rules. Those paths are ignored
local data. `--data-root` selects another local data root; `--checkpoint` and `--checkpoint-sha256`
select the pinned Policy v2 by default and are checked before the strict schema loader runs. The LIVE catalog must
match the checkpoint-owned catalog. Checkpoint or catalog failure
disables ranking while collection continues. Collection failures are shown and retried; they do not
relax LIVE trust gates. Stop with Ctrl+C. No automatic retraining or model reload occurs.
Displayed top-three rankings are appended to `data/raw/live/prediction_journal.jsonl` with match and
decision identity, state/checkpoint hashes and invalidation events. The journal never stores player
names or hidden opponent cards. Actual player action linkage stays `UNKNOWN` unless decision identity
can be proven.

The optional Vue/WebView2 overlay adds one button under Top-3: «Рекомендация кажется
сомнительной». It is available only for the displayed READY decision and sends just the
overlay session/revision to the local Python bridge. The runtime rechecks the exact active
snapshot under a lock; a changed turn, stale frame or replacement app session cannot flag an
old recommendation. Repeated calls for the same active decision are idempotent.

An accepted flag is appended to the separate, ignored
`data/raw/live/decision_feedback.jsonl`. It joins to the prediction journal and replay by match,
decision and state hash, and carries the checkpoint SHA, Top-3 and full legal menu with per-action
digests. It does not copy the game state, store hidden cards, or infer a preference from the click.
After a match, run `python scripts/review_live_feedback.py` to verify and restore context from the
local replay, then record an expert preference, explanation or unverified mechanical-error claim.
Only an explicit post-game assessment can record those; a mechanical claim remains pending
independent verification. The reviewer does not train or change Policy.

### Outcome shadow (`--outcome-shadow`, optional, off by default)

ACTION-OUTCOME-2. Next to the Policy ranking the runtime can forecast the immediate consequences of **every** legal
action of a displayed decision with `manamind.outcome` and write them to
`data/raw/live/prediction_journal.outcome_shadow.jsonl`. It is a read-only consumer of what the Policy path already
trusted (the same `Snapshot`, its `observed` SELF facts, and the same legal menu in Policy rank order): the displayed
Top-3, the overlay, the `RECOMMENDATION` journal rows, state hashes and the checkpoint are unchanged, the forecast runs
only after the recommendation was displayed and journaled, and a failure ends in a stable code in the shadow journal,
never in the Policy path. Forecasts are never shown and never rank anything. `manamind.live`, the overlay and `apps`
do not import `manamind.outcome` (a test enforces it); only `scripts/run_manamind.py` wires the two.

| Row | Content |
|---|---|
| `OUTCOME_SHADOW` | `match_id`, `seq`, `options_id`, `state_hash`, `decision_id`; observed-fact context and history coverage; per action: menu index, Policy rank, label, action digest, `status` (`EXACT` / `PARTIAL` / `UNSUPPORTED` / `NOT_COMPUTED` / `ERROR`), `tier`, exact local effects, bounded values, stable unknown tags, forecast digest, microseconds |
| `OUTCOME_SHADOW_ERROR` | the shadow of that decision could not be produced: stable reason code only |
| `OUTCOME_SHADOW_INVALIDATION` | the decision stopped being current (same reasons as `INVALIDATION`); its forecasts are history, not advice |

CONSEQUENCE-DIAGNOSTICS-1 adds journal-only diagnostics to the same row: an action may carry
`flags: {"SIDE_MISDIRECTION": <menu index of the dominating alternative>, "SELF_HARM": null}`, and the row a `diag` block with
`blocked` (a flag would have fired but for a stated reason) and `insufficient` (candidates whose forecast cannot support a claim)
counters. They describe exact direct effects only, are never shown, never rank anything and abstain on any visible way the effect
could pay off. Rows also record `forecaster_rev`; the analyzer compares forecast digests only between rows and code of the same
revision. Report: [reports/consequence_diagnostics_1/README.md](../reports/consequence_diagnostics_1/README.md).

The pre-action state is not copied: it is in the LIVE recording, and the digests let `scripts/outcome_shadow_report.py`
prove that it recomputed the same forecast from that recording. A decision is capped at `--outcome-shadow-budget-ms`
(default 250 ms; actions left over are `NOT_COMPUTED`, never invented), a file at 64 MiB (it is renamed with a UTC stamp
and a new file starts; nothing is deleted).

```bash
python scripts/run_manamind.py --ui --outcome-shadow
python scripts/outcome_shadow_report.py --shadow data/raw/live/prediction_journal.outcome_shadow*.jsonl --recordings-root data/raw/live --out reports/<new dir>/shadow_report.json
python scripts/outcome_shadow_replay.py <recording dir> ... --out-dir <new dir> --report-json <new file>
```

Report: [reports/action_outcome_2/README.md](../reports/action_outcome_2/README.md).

### Strategy shadow (`--strategy-shadow`, optional, off by default)

STRATEGIC-SCORER-1. An experimental, Policy-independent ranking of the same displayed menu: `manamind.strategy`
forecasts every legal action with `manamind.outcome`, values the resulting visible position with a hand-written,
versioned evaluation (`strategic-scorer-1/params-v1`) and writes its own Top-3 with score parts (`confirmed`, `risk`,
`plan`, `unknown_estimate`), factors and an uncertainty level to `data/raw/live/prediction_journal.strategy_shadow.jsonl`
(`STRATEGY_SHADOW`, `STRATEGY_SHADOW_ERROR`, `STRATEGY_SHADOW_INVALIDATION`; same rotation as the outcome shadow). It
takes the menu in menu order and never reads Policy scores; it runs after the Policy recommendation was displayed and
journaled; the displayed Top-3, overlay and `RECOMMENDATION` rows are unchanged; failures end in a stable code in its
own file. `manamind.live`, the overlay and `apps` do not import `manamind.strategy` (a test enforces it). It is not
shown to the player and no claim of playing strength is attached. Report:
[reports/strategic_scorer_1/README.md](../reports/strategic_scorer_1/README.md).

```bash
python scripts/run_manamind.py --ui --strategy-shadow
```

The command below is the standalone state inspector, without policy ranking or collection:

```bash
python scripts/live_state.py --logs-root "D:\Games\Hearthstone\Logs"
```

The folder can also come from `MANAMIND_HEARTHSTONE_LOGS`; nothing is hard-coded. Options:

| Option | Meaning |
|---|---|
| `--poll-ms N` | poll interval, default 50 |
| `--json` | one JSON object per line (snapshots and status changes) instead of readable text |
| `--allow-mode GT_VS_AI` | developer option: also follow solo games against the AI. Without it only Ranked Standard is followed. |
| `--record [DIR]` | record each game under `DIR` (default `data/raw/live`, git-ignored) |
| `--cards FILE` | card catalog, default `data/cards/standard_current_enUS.json` |
| `--ui` | show the Windows always-on-top panel; without it retain the console runner |
| `--overlay` | optional Vue / WebView2 desktop overlay; structured LIVE DTO, official RU/EN names; mutually exclusive with `--ui` |
| `--outcome-shadow`, `--outcome-shadow-budget-ms N` | `run_manamind.py` only: optional read-only consequence forecast of the whole menu, journal only (see Outcome shadow); default off, budget 250 |
| `--strategy-shadow`, `--strategy-shadow-budget-ms N` | `run_manamind.py` only: optional independent Strategic Scorer ranking of the whole menu, journal only (see Strategy shadow); default off, budget 250 |

The tool only ever opens `Power.log` for reading (for the length of one poll), never writes,
renames or deletes anything under `Logs`, and never touches `log.config`. Hearthstone must have
its `[Power]` logger enabled (HDT normally manages that file); without a `Power.log` the status is
`DISCONNECTED (NO_POWER_LOG)`.

Starting mid-game is supported: the tail finds the last `CREATE_GAME` line, rebuilds the game
silently and prints the decision that is current right now.

## Statuses

Every status carries a stable reason code. **A decision snapshot is only ever produced while the
session can reach `READY`**.

| Status | Meaning | Typical reasons |
|---|---|---|
| `DISCONNECTED` | no readable log | `NO_LOGS_ROOT`, `NO_POWER_LOG`, `UNREADABLE` |
| `WAITING_FOR_GAME` | nothing to follow | `UNSUPPORTED_MODE`, `MODE_AMBIGUOUS`, `SPECTATOR` |
| `SYNCING` | game found, no settled decision yet | `AWAITING_DECISION`, `RECONNECT` (a `CREATE_GAME` that already has `TURN>0`), `GAME_RESET` |
| `READY` | the current settled decision is trusted | none |
| `UNTRUSTED` | fail-closed, nothing is emitted for this game | `FILE_DISCONTINUITY`, `ENTITY_UNKNOWN`, `PARSE_ERROR`, `INVARIANT`, `SELF_AMBIGUOUS`, `SETTLE_TIMEOUT` |
| `GAME_OVER` | `GameEntity STATE=COMPLETE` was seen | none |

Notes:

- `UNTRUSTED` for a deterministic data problem lasts until the next `CREATE_GAME`.
  `SETTLE_TIMEOUT` (UI not caught up after 15 s) rebuilds the game and returns to `SYNCING`; a shrunk
  or replaced file re-reads the game from its `CREATE_GAME`.
- There is no `STALE`: log silence is normal while the opponent thinks.
- A LIVE-0C recommendation is bound to the current READY snapshot. SendOption, any newer
  GameState line, task-list advancement, reset, trust loss, source change and game completion
  invalidate it. The runner prints an invalidation when a displayed ranking becomes stale.
  After task-list advancement alone, the unchanged legal menu can be revalidated once all
  queued lists finish. It gets a new snapshot/ranking; a superseding GameState packet or
  SendOption clears the retained menu and prevents this revalidation.
- Unknown `GameTag` names (new patch, older `hearthstone` package) are counted and skipped because
  they cannot be tags the bridge reads. Any other unknown enum is `PARSE_ERROR`.

## When a snapshot is emitted

`GameState` packets run ahead of the screen (median 0.3-1 s). A decision is emitted only when

1. a SELF `DebugPrintOptions` message is complete and has at least one option with `error=NONE`, or an `END_TURN` option while it is SELF's turn (real logs always give `END_TURN` `error=INVALID`);
2. no newer `GameState` data was read after it (any later `GameState` line, including `SendOption`, supersedes it
   and it is dropped, which also covers the player acting before the screen caught up);
3. every task list the client queued (`PowerTaskList.DebugDump ID=n`) has finished
   (`PowerProcessor.EndCurrentTaskList m_currentTaskList=n`);
4. SELF, the mode and all invariants check out.

Read batches are evaluated after all their lines have been processed, avoiding transient READY
states between task-list markers. A settled SELF menu is emitted once; if later UI task lists
invalidate it, it can produce another snapshot after those lists finish, while its GameState/menu
binding is still current. There are no snapshots in the opponent's turn or for a message already
answered by SendOption. This does not weaken the `q_ended >= q_created` check or preserve an old
rating while tasks run. See [the real timing diagnosis](../reports/live_mvp_timing/README.md).

## Snapshot (`manamind.live.snapshot/1`)

`seq` (per `game_key`), `status`, `reason`, `game_key` (the collector's `start_key`, same function),
`session`, `source.line_in_game`, `client_build`, `game_type`, `format`, `phase`, `turn`,
`active_player`, `state`, `decision`, `state_hash`.

- `state` is the existing player-visible `GameState` (same field names as `manamind.domain`). It
  contains **no entity ids**.
- `decision` = `{kind: "MAIN_ACTION", options_id, legal: [...]}`. Each legal action has
  `option_index`, `kind` (`END_TURN`, `PLAY_CARD`, `ATTACK`, `HERO_POWER`, `USE_LOCATION`, `POWER`),
  `source` and `targets` as `{handle, card_id}`, and `sub_options` for choose-one. `handle` is the
  entity id and is an action handle for a later recommendation mapper, never a model input. A
  `card_id` appears only for SELF entities and public (in-play) entities. Legal actions are not
  ranked.
- `state_hash` = SHA-256 of the canonical (sorted keys, compact) JSON of `state`. Identity is
  `card_id`; localized names are never parsed.

The hand is in on-screen (zone position) order. SELF health/armor/mana/overload/hero power/weapon/
board and the opponent's health/armor/weapon/board are filled; `weapon.current_durability` uses the
same `HEALTH - DAMAGE` rule as the importer.

The in-memory `Snapshot` also carries `observed` (OBSERVATION-EXT-1a): SELF facts that `GameState`
does not hold (hand-instance keywords, both heroes' Divine Shield, Ruby Sanctum, healing and Spell
Damage modifiers), read from the same entity table at the same moment. It is **not** part of `to_dict()`,
the JSON, `state` or `state_hash`, and it is excluded from snapshot equality. An unset tag counts as 0
only when the section was followed from turn 0 without a `GAME_RESET`; a reconnect dump keeps logged
values only and a rewind makes every fact unknown. Reader contract and checks:
[reports/observation_ext_1a](../reports/observation_ext_1a/README.md). No recommendation or overlay code
reads it.

## Privacy boundary

Allowlist by (controller, zone, card type), default deny, applied after the reducer.

- SELF: hand identities, hero, hero power, weapon, board; deck and secrets as counts only.
- Opponent: hero, weapon, board, **hand size, deck size, secret count**.
- **No opponent identity from HAND, DECK, SETASIDE or SECRET**, even if the raw log carries a card id
  (including `META_DATA Meta=OVERRIDE_HISTORY` reveals, `SHOW_ENTITY` + `HIDE_ENTITY`, start-of-game
  reveals). `opponent_known_cards` is always empty. Relaxing this needs a per-case review.
- Player names, BattleTags, `GameAccountId` and raw log lines never appear in stdout, snapshots, status
  events, errors or the sanitized recording files. Errors print the exception class only.
- The recorded `slice.log` is raw and does contain names. It lives only in the git-ignored
  `data/raw/live/`; never share it.
- Entity ids never appear inside `state`.

## Recording and replay

```bash
python scripts/live_state.py --logs-root "D:\Games\Hearthstone\Logs" --record
python scripts/live_replay.py data/raw/live/<session>/<game_key16>
```

Per game the recorder writes `slice.log` (raw lines from `CREATE_GAME`), `tail_trace.jsonl` (monotonic
ms, number of lines and byte range per read batch), `snapshots.jsonl`, `status.jsonl` and `meta.json`
(versions, client build, catalog hash, policy flags). The replay re-feeds the slice with the original
batch boundaries and verifies that the `state_hash` sequence is identical (`--show` prints the
snapshots). A bug report is slice + trace + meta; scrub player names from the slice before sharing it.

For the reviewed policy ranking path, `scripts/replay_live_recommendations.py <recording-dir>`
replays the same batches, scores only the decision still current at each batch end, and checks
recorded state hashes plus repeat-ranking determinism. Optional `--admitted-dataset <dir>` checks
model-input parity against matching admitted ML-1B decisions. Its latency percentiles measure
scoring overhead, not Power.log delivery or UI delay.

## Current limitations

The Windows unified runner defaults to the frozen Policy v2 path and SHA-256 above. Other
checkpoints can be selected only by supplying both `--checkpoint` and `--checkpoint-sha256`.
Existing direct `PolicyRecommender` callers without a digest retain the reviewed ML-1C fallback.
Both versions use the same trust/privacy/menu and invalidation gates; the runtime catalog must match
the saved catalog. See
[the representation contract](POLICY_REPRESENTATION.md).

- Only `MAIN_ACTION` decisions. Mulligan and Discover/choice states are not emitted yet.
- No opponent hand identities (a deliberate difference from the offline importer, which exposes
  `revealed` opponent hand cards). Own secret identities are not exposed, only the count.
- `GameState` fields the importer never fills stay unset (`spell_damage`, discounts, histories,
  `hero_freeze_turns_remaining`, ...). Neither the live nor the importer path claims them. Hero maximum Health
  (`HEALTH` tag), hero Frozen (explicit `FROZEN` tag only) and Hero Power readiness (explicit `EXHAUSTED` tag; for SELF
  decisions also the options message: a validated Hero Power option or `REQ_NOT_EXHAUSTED_HERO_POWER`) are extracted;
  each stays None when the log does not state it. Recordings made before OBSERVATION-EXTRACTION-1 do not replay to their
  recorded `state_hash` values, because the replayed states now carry these fields.
- The offline importer samples the state before every top-level `PLAY`/`ATTACK` block, i.e. after the
  tag changes that follow `SendOption`; the live snapshot is the state at the options message. They
  agree exactly only where nothing sits in between (tests use `parity_view` for the identical-policy
  comparison).
- Reconnect (`CREATE_GAME` with `TURN>0`) and `GAME_RESET` handling is implemented fail-closed and
  covered by synthetic logs only; no real example was available. Do not test it in a ranked game.
- The compact runtime catalog has no names. The Windows panel looks up names in the local Standard
  metadata JSON and falls back to `card_id`, action type and hand/board position when unknown; the
  inference catalog and checkpoint vocabulary are unchanged.
  The optional Vue overlay uses a separate pinned RU/EN display-name snapshot (all client entities),
  with RU → EN → ID fallback. See [setup and position contract](../apps/overlay-ui/README.md).
  It receives typed `PresentationEvent` callbacks, never console text. Board coordinates share minion/Location
  slots; both sides run left to right on the player's screen. Missing or inconsistent coordinates are omitted.
  Its Windows host has been checked separately; actual Hearthstone/DPI/fullscreen verification remains pending.
- The reducer keeps hearthstone's entity code off the card database (see `PacketExporter`); without
  the optional `hearthstone_data` package python-hearthstone would otherwise download card data from
  the web on certain reveals.
- Windows file identity is used to detect a replaced `Power.log`; a file rewritten in place to a
  longer length cannot be told apart from growth.

## Manual verification (Ranked Standard, user check)

1. `python scripts/live_state.py --logs-root "D:\Games\Hearthstone\Logs" --record` before or during a game.
2. Expect `status: WAITING_FOR_GAME`, then `SYNCING` at the start of the game, then `READY` with the first snapshot
   at your first turn (or the current decision if you attach mid-game).
3. At five or more random decisions compare the printed snapshot with the screen:
   your hand (ids in on-screen order), both boards (attack/health/exhaustion), your mana and overload,
   both heroes' health/armor, the opponent's hand size.
4. Confirm no opponent hand/deck identity is printed anywhere and no name appears.
5. After the game run `scripts/live_replay.py` on the recorded directory: expect `IDENTICAL`.
6. Optional, never in ranked: attach mid-game; briefly drop the network in a casual or solo-AI game
   (`--allow-mode GT_VS_AI`) to see the reconnect path.
7. The panel path is technically tested, but remains **TECHNICALLY READY** until the user confirms
   it on a real Windows Hearthstone client. Report only the game date and number of snapshots checked,
   not their contents.
