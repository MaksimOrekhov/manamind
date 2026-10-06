# LIVE-0C — first read-only live policy recommendation

Base: `9dc969d5e70025107d8b3099f8dcff9be85cb038` (`origin/main`, ML-1C included).
Branch: `work/live0c-first-recommendation`. No real game smoke or merge was performed.

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

## One-command live smoke, when explicitly authorized

Run this PowerShell command on the user's machine; it uses the stable main-worktree data root
for newly collected matches while executing the isolated LIVE-0C branch code and its exact
ignored checkpoint:

```powershell
& "E:\ManaMind\.venv\Scripts\python.exe" "C:\Users\Максим\.codex\worktrees\live0c-first-recommendation\ManaMind\scripts\run_manamind.py" --logs-root "D:\Games\Hearthstone\Logs" --data-root "E:\ManaMind\data"
```

Start before a Ranked Standard game, play normally, inspect only read-only console rankings,
then stop with Ctrl+C. Historical games should show no ranking; current SELF decisions should
rank or explicitly decline; after GAME_OVER no ranking remains. The collector retains a completed
match and the LIVE recording can be replayed with `scripts/live_replay.py` and
`scripts/replay_live_recommendations.py`. No gameplay input is automated.

ML-1C remains a weak baseline: 21 matches, class/deck concentration, validation overfitting,
poor targeted-action accuracy and uncalibrated logits. LIVE-0C does not establish playing strength.
The graphical overlay and a real interactive smoke remain separate follow-up work.
