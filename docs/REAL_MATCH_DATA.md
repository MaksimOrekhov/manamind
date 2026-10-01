# Collecting a real ranked Standard match

This is the local data-intake guide, not a development priority or permission to train. Product/data contracts are in [README](../README.md); current card-support priorities and simulator admission are in [the package process](CAPABILITY_PACKAGE_PROCESS.md) and [Standard registry](STANDARD_REGISTRY.md). Synthetic and weak-simulator labels do not demonstrate Hearthstone strength.

## Implemented intake and limitations

`scripts/audit_power_log.py` checks a **single-match** local `Power.log` for three conditions: the parser identifies Ranked, identifies Standard, and sees a complete win/loss/draw result. `scripts/import_power_log.py` then converts that match into local JSONL examples: visible states immediately before top-level card-play and attack actions, from the local player's perspective, labeled with the match result. The importer never writes player names or raw replay data.

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

The parser currently rejects files with more than one match because it cannot safely associate each match with its mode metadata yet. Starting Hearthstone fresh and copying the log after just one match keeps this intake check unambiguous. If the report says the match is incomplete or the mode is missing, preserve the report and tell me; do not convert that match.

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

## Prepare a small pilot split

To validate imported rows, remove identical match trajectories, and make train/validation/test files without splitting a match across sets, run:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_real_dataset.py
```

The default output is `data/processed_real/pilot_splits/`, which Git ignores. The script writes `train.jsonl`, `validation.jsonl`, `test.jsonl`, and `report.json`. It balances match outcomes across the three parts when the sample allows it. With only ten matches, these splits are for checking the pipeline; validation and test metrics will be very uncertain and are not evidence of playing strength. This preparation step does not train or overwrite a model checkpoint.
