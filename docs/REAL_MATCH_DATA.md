# Collecting a real ranked Standard match

This is the local data-intake guide, not a development priority or permission to train. Product/data contracts are in [README](../README.md); current card-support priorities and simulator admission are in [the package process](CAPABILITY_PACKAGE_PROCESS.md) and [Standard registry](STANDARD_REGISTRY.md). Synthetic and weak-simulator labels do not demonstrate Hearthstone strength.

## Implemented intake and limitations

`scripts/audit_power_log.py` checks a **single-match** local `Power.log` for three conditions: the parser identifies Ranked, identifies Standard, and sees a complete win/loss/draw result. `scripts/import_power_log.py` then converts that match into local JSONL examples: visible states immediately before top-level card-play and attack actions, from the local player's perspective, labeled with the match result. The importer never writes player names or raw replay data.

For weapons, the importer derives current durability as `max(0, HEALTH - DAMAGE)`; a missing `DAMAGE` tag means zero damage. If `HEALTH` is absent, an explicit `DURABILITY` tag remains a compatibility fallback. Catalog durability is base metadata and is not used as the current value. Datasets imported before DATA-0B may therefore contain `current_durability=None` for weapons. Rebuild corrected data from raw logs into a fresh output directory; do not mix old and corrected trajectories because the serialized match fingerprint can change.

Hearthstone's game log is enabled through `log.config`. Hearthstone Deck Tracker normally manages this file for its own log reading; its upstream guide describes the manual setup if needed: [Setting up the log.config](https://github.com/HearthSim/Hearthstone-Deck-Tracker/wiki/Setting-up-the-log.config). The game's protocol and `Power.log` format are documented by HearthSim: [Game State Protocol](https://hearthsim.info/docs/gamestate-protocol/).

## Capture one match

1. Close Hearthstone.
2. Start it again, play one complete **Ranked Standard** match, then close the game.
3. Copy the match's `Power.log` from `<Hearthstone installation>\Logs` into ManaMind's ignored `data/raw/` folder. Hearthstone may place it in a newest `Hearthstone_<date_time>` subfolder and may name it `Power_old.log` after rotating logs. Copy the file and rename only the copy to `Power.log`.
4. From the ManaMind project root, first check it:

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\audit_power_log.py .\data\raw\Power.log
   ```

The audit prints only the format, ranked classification, completion state, result labels, and turn count. It does not print BattleTags or player names. Keep raw logs under `data/raw/`; Git ignores that directory. Do not send the log to a website or commit it.

The single-match tools reject files with more than one match (the automatic collector below isolates matches first) because it cannot safely associate each match with its mode metadata yet. Starting Hearthstone fresh and copying the log after just one match keeps this intake check unambiguous. If the report says the match is incomplete or the mode is missing, preserve the report and tell me; do not convert that match.

## After the audit

If the audit says `eligible_for_capture: true`, convert the log with:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_power_log.py .\data\raw\Power.log
```

The converter writes one randomly named file to `data/processed_real/`, which Git also ignores. It compares normalized state sequences and skips a match that was already imported. One match is only a pipeline check: its many snapshots all share the same final result and must stay together when splitting train/validation/test data. Collect multiple matches with both wins and losses before training or measuring model quality.

## Process a folder of captured matches

When several copied logs are ready, put all `.log` files in `data/raw/` and run this once from the project root:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_power_logs.py
```

The batch command audits each file, imports eligible new matches, skips duplicate matches, and prints a compact JSON summary. You do not need to run the single-file audit and importer for every log. Keep collecting unique completed Ranked Standard matches; when a batch is ready, run the command and review the summary before preparing training data.

## Automatic local collection

`scripts/collect_power_logs.py` watches a Hearthstone `Logs` folder and imports each finished Ranked Standard match once, without copying `Power.log` by hand. It only collects data: it never trains, touches checkpoints, ManaEngine rules or the registry.

```powershell
# one pass over the current logs, then exit
.\.venv\Scripts\python.exe .\scripts\collect_power_logs.py --logs-root "<Hearthstone>\Logs" --once

# continuous mode: leave it running while you play; stop with Ctrl+C
.\.venv\Scripts\python.exe .\scripts\collect_power_logs.py --logs-root "<Hearthstone>\Logs" --poll-seconds 5
```

`--logs-root` may also come from the `MANAMIND_HEARTHSTONE_LOGS` environment variable; there is no hard-coded path or log-location discovery. Options: `--raw-output` (default `data/raw/collected/`), `--processed-output` (default `data/processed_real/`), `--cards`, `--max-sessions` (default 3). Raw per-match slices, the state file and `collector_last_summary.json` stay under the git-ignored `data/raw/`; examples go to the git-ignored `data/processed_real/`. Console output shows only status, result, turn count and counts, never names or log lines. Log lines in the raw slices are original log data, so keep them local.

**How a match is isolated.** `hslog`'s `game_meta` is a single dict for the whole parse (last value wins; a game without mode lines inherits the previous game's), so a multi-game log cannot be passed to the single-match tools. In real logs the `GameType` / `FormatType` lines are printed inside the section that begins at each `GameState.DebugPrintPower() - CREATE_GAME` line. The collector cuts the stream at those lines and parses each section with its own parser. It admits a game only if its own section has exactly one consistent `GameType` and `FormatType` and a top-level `GameEntity STATE=COMPLETE` (EOF is never completion). The section up to that line is then run through the unchanged `audit_log` and `import_power_log`, so the importer's contracts hold. Checked on local real logs: collector output has the same trajectory fingerprint as a direct import of the whole single-match file.

**Statuses.** `IMPORTED`, `SKIPPED_ALREADY_IMPORTED`, `SKIPPED_NOT_RANKED`, `SKIPPED_NOT_STANDARD`, `SKIPPED_METADATA_AMBIGUOUS` (missing, conflicting or parser-disagreeing mode lines), `SKIPPED_MID_GAME_START` (section already past turn 0 at `CREATE_GAME`, e.g. a reconnect re-dump) are final. `SKIPPED_INCOMPLETE` (match still running) and `PARSE_FAILED` are retried on later polls; a failure never stops the collector.

**Duplicates and restarts.** A match is identified by a hash of its `CREATE_GAME` header (it contains a per-game seed), recorded in `data/raw/collected/collector_state.json`. If that file is lost, the importer's trajectory fingerprint still rejects the same match. Re-running over the same logs, `Power_old.log` rotations and new `Hearthstone_<timestamp>` folders therefore do not create duplicates. Each poll scans `Power*.log` in the root plus the newest `--max-sessions` session folders, and re-reads a file only when its size or modification time changed.

**Limits.** Matches are admitted only from the local client's own log, as before; the single-match local-player inference still applies. Reconnect re-dumps and matches whose mode lines are absent are skipped, not recovered. Only top-level `GameState` lines are used (`PowerTaskList` duplicates are ignored by `hslog`). Deleting `collector_state.json` is safe. Training data from this path is still subject to the "collect varied wins and losses first" guidance below.

## Prepare a small pilot split

To validate imported rows, remove identical match trajectories, and make train/validation/test files without splitting a match across sets, run:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_real_dataset.py
```

The default output is `data/processed_real/pilot_splits/`, which Git ignores. The script writes `train.jsonl`, `validation.jsonl`, `test.jsonl`, and `report.json`. It balances match outcomes across the three parts when the sample allows it. With only ten matches, these splits are for checking the pipeline; validation and test metrics will be very uncertain and are not evidence of playing strength. This preparation step does not train or overwrite a model checkpoint.

## Value training readiness and fixed snapshots

Before preparing a training snapshot, audit the collected examples and current
model path:

```powershell
python scripts/audit_real_training_readiness.py --input-dir <processed-real-dir> --cards data/cards/standard_current_enUS.json
```

The audit deserializes every row, checks SELF perspective, source and labels,
sample and match integrity, encodes all states, and runs a finite ValueNetwork
batch forward pass. Unknown visible card IDs use the encoder's shared UNK
identity and are reported only as aggregate counts. A successful forward pass
means **pipeline compatible**; it does not mean the data is statistically
large enough or that the model is good.

The collector may still be writing into `data/processed_real/`. Do not train
from that live directory. Prepare a new output directory as a fixed snapshot,
inspect its `report.json`, and keep the snapshot unchanged through training:

```powershell
python scripts/prepare_real_dataset.py --input-dir <processed-real-dir> --output-dir <snapshot-dir> --seed 42
python scripts/train_real_value.py --dataset-dir <snapshot-dir> --checkpoint <new-candidate-checkpoint> --cards data/cards/standard_current_enUS.json --epochs 20 --batch-size 128 --seed 42
```

The training wrapper requires a prepared snapshot with train, validation and
test files, rejects missing IDs, invalid labels, wrong source or perspective,
duplicate sample IDs and cross-split match leakage, and delegates to the
existing training pipeline. Always choose a new candidate checkpoint path. It
refuses to overwrite an existing checkpoint unless `--overwrite-checkpoint`
is explicitly provided; it never promotes a model. The optional `--smoke` flag
runs one epoch and suppresses model-quality metrics. It is only a plumbing
check.

## Future simulator evidence loop (not implemented)

The current Power.log importer captures completed match observations and
outcomes. It does **not** automatically replay a match in ManaEngine, compare
the two engines, update evidence, or learn from a discrepancy. Logs can later
provide gameplay observations and rules-evidence leads, subject to the privacy
and visibility boundary above.

A future replay/evidence bundle should retain enough provenance to reproduce a
comparison: `game_id`; client/build identity; timestamp and turn; the visible
state and involved card/entity IDs; the relevant raw log slice and parsed event
sequence; simulator support status; expected and observed transitions; active
`EvidenceConstraints` or the precise failure reason; and the evidence source
and review status. Keep raw logs in ignored `data/raw/`; never add hidden
opponent cards, deck order or future RNG outcomes to model inputs.

Candidate triage labels are `KNOWN_EXPECTED`, `KNOWN_INFERRED_CONFIRMED`,
`NOVEL_OBSERVATION`, `ENGINE_CONTRADICTION` and `PATCH_DRIFT_SUSPECTED`.
Repeated observations can increase confidence in an inference, but do not by
themselves prove complete dynamic-pool membership or establish a canonical
rules contract. No future discrepancy loop should edit production rules,
manifests, registry statuses, or model weights automatically; those changes
require review and the applicable evidence/regeneration workflow.


## Real supervised policy actions (ML-1B)

Policy imports are separate from the existing Value schema and live in the
already-ignored `data/processed_policy_real/`. Each match has a JSONL of exact
SELF labels and an `.audit.json` manifest of skipped decisions. Raw logs are
opened read-only; neither CLI copies them. Use a new output directory for a
new import run. Existing match IDs/files are rejected rather than overwritten.

```powershell
python scripts/import_policy_power_log.py <one-game.log> --output-dir data/processed_policy_real/run1
python scripts/import_policy_power_log.py <Power.log> --segmented --output-dir data/processed_policy_real/run1
python scripts/audit_real_policy_dataset.py data/processed_policy_real/run1
```

`--cards FILE` selects a local catalog. Every segmented section must independently
prove completed Ranked Standard, SELF and a final win/loss/draw. Reconnect
headers, GAME_RESET, spectator input and ambiguous mode/result are rejected.

Records contain schema/action versions, deterministic header-based `game_id`,
`decision_id`, the LIVE-sanitized `state`, the complete supported `legal_actions`,
`chosen_action_index`, numeric `final_result` (SELF win 1, loss 0, draw .5),
`source=power_log_ranked_standard` and non-model provenance (options/selection
line numbers and before-state hash). The supervised action label is the chosen
index; the outcome is never substituted for it or passed to the policy encoder.

At the completed options-message boundary, the offline reader closes the message
before reading the next line; the actual client task-list gate must be settled.
State and SELF resolution use LIVE-0B. Any intervening GameState message before
SendOption supersedes the candidate. Selection is exact by option ID, entity
target handle and insertion position. Handles stay in memory and never enter
model-facing actions/state. All legal targets are expanded. Minion/Location
plays expand the one-based insertion slots of the public shared seven-slot board.
END_TURN with error=INVALID is legal only in SELF's turn, including a menu with
no other action. The supported kinds are PLAY_CARD, ATTACK, HERO_POWER,
ACTIVATE_LOCATION and END_TURN. A duplicate source/menu mapping or repeated
SendOption is ambiguous; sub-options and unsupported/unresolvable targets skip
the entire decision, preserving a complete admitted action set. No localized
name matching or nearest-action fallback is used. Discover/mulligan are excluded.
Duplicate source variants are ambiguous even when another variant is invalid;
an unaffordable normal play must not relabel Trade/Forge as PLAY_CARD. Known
alternate hand powers and unestablished minion powers are excluded. Every chosen
non-END_TURN action also requires a subsequent public block with the same actor
handle before the next options message (ATTACK for attacks, PLAY otherwise).
This corroborates the label without passing future events to the model.

`manamind.training.real_policy` validates inputs, creates deterministic
outcome-stratified partitions by whole game_id, and supports held-out cross
entropy, top-1, top-3 (menus >=3), and mean reciprocal rank. It refuses evaluation
on training game IDs. At least three labeled games are required for three splits;
rare outcomes may remain unrepresented in a small held-out partition.

The existing scorer was extracted to `manamind.models.policy`; RosettaStone
imports are preserved. Policy action checkpoint schema 4 appends `play_position`
without changing the architecture or Value StateEncoder schema. Version 3
weights migrate with a zero-initialized new column. The inherited scorer remains
coarse: it embeds the action-bearing card, not each target's identity, and does
not consume every retained descriptor such as card durability. This is a model
capacity limitation, not permission to change exact labels.

Only an explicitly requested plumbing smoke should use:

```powershell
python scripts/smoke_real_policy.py data/processed_policy_real/run1 --checkpoint checkpoints/real_policy_smoke_new.pt
```

It performs one CPU update on at most 32 train decisions, evaluates separate
whole test matches, saves/reloads a new checkpoint, and makes no strength claim.
Checkpoint schema is separate from RosettaStone self-play checkpoints. Use a
new checkpoint path; overwrite is refused. Local validation and coverage limits
are recorded in `reports/ml/ML1B_REAL_POLICY_DATASET.md`.

## First real PolicyNetwork baseline (ML-1C)

The bounded behavior-cloning runner is separate from the one-update smoke:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python scripts/train_real_policy.py <admitted-policy-directory> `
  --config configs/real_policy_ml1c.json `
  --output data/processed_policy_ml1c/<new-run-name>
```

Use a new ignored output directory. The runner audits ML-1B examples, copies an
immutable dataset snapshot, freezes whole-match membership/config/source hashes,
and trains the existing PolicyNetwork on chosen_action_index. Published ML-1B
smoke-test matches remain in train for this baseline split. Validation CE alone
selects the epoch; the selected checkpoint is saved/reloaded before final test
metrics. The test set is consumed once reported and cannot be reused as an
untouched holdout for subsequent tuning. No simulator or online training is used.

Local outputs include frozen_experiment.json, the private snapshot, history,
aggregate metrics/diagnostics and policy.pt. Existing outputs are never overwritten.
The strict `manamind.training.policy_checkpoint.load_policy_checkpoint` loader
requires the baseline format, state/action/dataset/descriptor schemas, ordered
feature names and normalization, verifies catalog/vocabulary and split/config
identities, and rejects incompatible weights or split leakage. It reconstructs
the saved encoder; external metadata cannot reorder vocabulary indices. This
format is distinct from smoke, self-play and Value checkpoints; no automatic
migration is performed. Unknown IDs retain the existing shared UNK behavior.

See [the baseline report](../reports/ml/ML1C_REAL_POLICY_BASELINE.md) for the exact
frozen experiment and limits. Policy logits describe behavior selection, not
win probability. This small-corpus baseline does not establish playing strength
or authorize live integration, search or gameplay automation.
