# LIVE-0C — first read-only live policy recommendation

Base: `9dc969d5e70025107d8b3099f8dcff9be85cb038` (`origin/main`, ML-1C included).
Branch: `work/live0c-first-recommendation`; implementation head:
`f4fdf1a5e7fb273cc66c09a2af88c6ad0eb507af`. No merge was performed.
Post-validation verdict: **LIVE0C_FIRST_LIVE_RECOMMENDATION_PASS**.

## Real live smoke — 2026-10-06

The unified runner completed one Ranked Standard match in session
`Hearthstone_2026_10_06_22_20_23` (game key prefix `219302142511e674`). Its trace has 47 trusted
READY/SELF decisions. The normal LIVE replay reproduced all 47 snapshots: `IDENTICAL`. Policy
replay reproduced the recorded state hashes and identical rankings on repeat. Of the 47 snapshots,
29 were superseded before the end of their read batch; 18 were current, 15 were scored, and three
were safely skipped as `AMBIGUOUS_SELECTION`. This coverage is expected for a 50 ms poller reading
Power.log updates that can advance before the UI settles; superseded decisions were not scored.

The lifecycle recording contains 48 `SYNCING`, 47 `READY`, and one `GAME_OVER` status. Every READY
was later invalidated by a state transition; the final GAME_OVER leaves no current snapshot. The
runner prints its initial `WAITING_FOR_GAME` before entering the poll loop. Its catch-up path
suppresses historical snapshots, and this recording contains only the new match. Snapshots are
SELF decisions only; no opponent-turn recommendation is eligible.

For all 15 scored decisions, the full menu contained 180 action variants. All ranked top-three
entries mapped back to that exact menu. The scored menus included 85 target variants, 23 placement
variants, and 15 `END_TURN` options, with each action variant preserved separately. Offline action
extraction labeled 32 of 48 decisions and skipped the rest by the existing policy-import rules.
Fifteen scored decisions matched an actual subsequent action by exact state hash and options ID:
top-1 agreement was **9/15** and top-3 agreement was **9/15**, with **0 unmatched** among those
exact matches. These are descriptive results from one match, not evidence of playing strength.

The completed match appears once under the existing ignored raw collection path, and the collector
state marks it `IMPORTED`. Its processed value dataset contains 73 rows; a fresh import of this
exact raw match produced the same dataset fingerprint. Repeating the importer against that dataset
returned `duplicate` and created no second output.

Privacy follows the contract in `docs/LIVE_BRIDGE.md`: sanitized snapshots, status events, metadata,
and replay-rendered recommendation output contain no player names, BattleTags or account IDs. All
47 states have an empty `opponent_known_cards` field; no hidden opponent identity enters model inputs
or recommendations. The raw `slice.log` is intentionally unredacted replay evidence, may contain
Power.log names, and remains local, git-ignored and untracked. It must not be shared unsanitized.
No raw log excerpt is included here. The original console transcript was not retained; stdout
privacy was checked against the runner's safe rendering path and reconstructed recommendation
output rather than by byte-for-byte comparison with that console session.

The observed smoke statistics do not establish general Hearthstone playing strength.

The unified runner follows Power.log with the reviewed LIVE bridge, records its raw slice and
read trace for replay, ranks only a current trusted READY/SELF/Ranked Standard/main-action
snapshot, and polls the existing completed-match collector independently. The exact ML-1C
checkpoint at ignored `data/processed_policy_ml1c/baseline_seed42_v1/policy.pt` has SHA-256
`5a5e3435c0dcda5ce69bcd0a48dc8521fb3696e2a7794e268b894efbf7e3e95e`.
The runner checks this hash, then uses `load_policy_checkpoint` for schema, catalog, vocabulary,
model and split compatibility. It also requires the runtime LIVE catalog to match the checkpoint
catalog exactly. It never trains or reloads weights during a session.

The action adapter uses the reviewed ML-1B `map_actions` on the **entire** legal packet, the
checkpoint-owned encoder and the existing PolicyNetwork. Each target and placement stays a
separate row; unknown card IDs use the saved UNK index. Mapping, privacy, menu and finite-output
failures suppress the whole recommendation. Outputs show a top-three policy ranking score,
explicitly described as behavior cloning rather than win probability. No names, private log
lines, BattleTags, raw handles or hidden opponent identities enter model inputs or console output.
The current READY snapshot is cleared on a new GameState line/SendOption/options message,
new queued task list, game change, reset, trust loss, source discontinuity and game over.
The runner invalidates a displayed ranking when the current snapshot changes.

## Offline acceptance

The accepted LIVE-0B recording with 43 snapshots replayed with identical recorded state hashes.
At read-batch boundaries, 28 snapshots had already been superseded; 15 remained current. Thirteen
were scored and two were safely skipped as `AMBIGUOUS_SELECTION`. All 13 scored decisions matched
admitted ML-1B state hashes, complete semantic action menus and model-facing tensors. Reloaded
checkpoint ranking was identical on repeat replay. These counts are for one recorded match and
measure integration, not policy quality. The end-to-end score-call latency on those 13 decisions
was median **1.51 ms**, p90 **1.91 ms**, p99 **6.49 ms** on this CPU/runtime; it includes the first
catalog-identity check but excludes log
delivery and UI delay.

Fixture tests confirm target and placement variants, END_TURN and UNK scoring, deterministic
ranking, refusal of tampered/incompatible checkpoints, hidden-information canaries, opponent and
all non-READY status suppression, and invalidation after SendOption, new options, task advance,
disconnect/source replacement, file discontinuity, reset and GAME_OVER. Unified-runner tests
confirm historical completed games do not emit recommendations at startup, a new game records a
LIVE slice, and collector failure warns without changing policy trust. With the actual collector,
a completed Ranked Standard fixture is retained in `data/raw/collected/` and imported once;
restart creates no second raw match. Recommendation unavailability leaves collection active.
Private logs, recordings, datasets and checkpoint remain ignored and untracked.

Validation: relevant LIVE/ML/collector tests, full pytest, Ruff, generator identity guard,
native typed-failure inventory, generated-artifact determinism and `git diff --check` passed
locally. Hosted source CI is checked separately on the pushed branch.

## Unified runner command used for the smoke

The completed smoke used this PowerShell command. It used the stable main-worktree data root for
collected matches and the isolated LIVE-0C branch code with its exact ignored checkpoint:

```powershell
& "E:\ManaMind\.venv\Scripts\python.exe" "C:\Users\Максим\.codex\worktrees\live0c-first-recommendation\ManaMind\scripts\run_manamind.py" --logs-root "D:\Games\Hearthstone\Logs" --data-root "E:\ManaMind\data"
```

The user played normally and stopped the runner after GAME_OVER. It performs no gameplay input
automation. The completed recording replays with `scripts/live_replay.py` and
`scripts/replay_live_recommendations.py`.

ML-1C remains a weak baseline: 21 matches, class/deck concentration, validation overfitting,
poor targeted-action accuracy and uncalibrated logits. LIVE-0C does not establish playing strength.
Graphical overlay integration remains separate follow-up work.

Final verdict: **LIVE0C_FIRST_LIVE_RECOMMENDATION_PASS**.
