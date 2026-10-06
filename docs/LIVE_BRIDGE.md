# Live bridge: FIRST_LIVE_STATE

While Hearthstone runs, `scripts/live_state.py` follows the growing `Power.log` and prints one
**sanitized, settled** snapshot at every decision point of the local player (SELF). The LIVE-0C
runner also ranks the complete legal SELF menu with the fixed ML-1C behavior-cloning policy. It
prints read-only experimental recommendations and uses the existing collector to retain completed
matches. There is no ManaEngine import, search, overlay transport, HDT, OCR or memory reading.

Design and evidence: [LIVE_REALTIME_BRIDGE_AUDIT.md](../reports/live_integration/LIVE_REALTIME_BRIDGE_AUDIT.md).
This page is the operating guide.

## Start

For the unified LIVE-0C workflow, from the repository root with the accepted ignored checkpoint
at `data/processed_policy_ml1c/baseline_seed42_v1/policy.pt`:

```powershell
python scripts/run_manamind.py --logs-root "D:\Games\Hearthstone\Logs"
```

The runner follows Power.log, records replayable LIVE slices under `data/raw/live/`, and invokes
the existing completed-match collector every five seconds. New raw matches are retained under
`data/raw/collected/` and imported using the collector's existing rules. Those paths are ignored
local data. `--data-root` selects another local data root; `--checkpoint` selects the exact reviewed
ML-1C file, whose SHA-256 is checked before the strict schema loader runs. The LIVE catalog must
match the checkpoint-owned catalog. Checkpoint or catalog failure
disables ranking while collection continues. Collection failures are shown and retried; they do not
relax LIVE trust gates. Stop with Ctrl+C. No automatic retraining or model reload occurs.

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
- Unknown `GameTag` names (new patch, older `hearthstone` package) are counted and skipped because
  they cannot be tags the bridge reads. Any other unknown enum is `PARSE_ERROR`.

## When a snapshot is emitted

`GameState` packets run ahead of the screen (median 0.3-1 s). A decision is emitted only when

1. a SELF `DebugPrintOptions` message is complete and has at least one option with `error=NONE`, or an `END_TURN` option while it is SELF's turn (real logs always give `END_TURN` `error=INVALID`);
2. nothing newer was read after it (any later `GameState` line, including `SendOption`, supersedes it
   and it is dropped, which also covers the player acting before the screen caught up);
3. every task list the client queued (`PowerTaskList.DebugDump ID=n`) has finished
   (`PowerProcessor.EndCurrentTaskList m_currentTaskList=n`);
4. SELF, the mode and all invariants check out.

So there is exactly one snapshot per settled SELF decision, none in the opponent's turn, and none
for a message the player already answered. On the 15 local games checked (aggregate only), about
12 % of legal options messages were answered before the screen settled and are therefore not shown.

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

- Only `MAIN_ACTION` decisions. Mulligan and Discover/choice states are not emitted yet.
- No opponent hand identities (a deliberate difference from the offline importer, which exposes
  `revealed` opponent hand cards). Own secret identities are not exposed, only the count.
- `GameState` fields the importer never fills stay unset (`spell_damage`, discounts, histories,
  `hero_frozen`, ...). Neither the live nor the importer path claims them.
- The offline importer samples the state before every top-level `PLAY`/`ATTACK` block, i.e. after the
  tag changes that follow `SendOption`; the live snapshot is the state at the options message. They
  agree exactly only where nothing sits in between (tests use `parity_view` for the identical-policy
  comparison).
- Reconnect (`CREATE_GAME` with `TURN>0`) and `GAME_RESET` handling is implemented fail-closed and
  covered by synthetic logs only; no real example was available. Do not test it in a ranked game.
- Card names are not shown (the compact catalog has no names); output is `card_id` only.
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
7. Report only the game date and the number of snapshots checked, not their contents.
