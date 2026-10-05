# ML-1A — Real Match Value Training Readiness

## Revisions and scope

- Base: `origin/main` at `55f95a97ff5cddbc97669d2e61a05c77f8c8ffe6`.
- Branch: `work/ml1a-real-value-readiness`.
- This change adds a read-only audit CLI and a wrapper around the existing value training pipeline. It does not change the ValueNetwork architecture, encoder schema, collector, card registry, or gameplay simulator.

## Existing components confirmed

- `GameState` and `StateEncoder`, including unknown-card encoding through `CardVocabulary.UNKNOWN_CARD`.
- `ValueNetwork`, `collate_encoded_states`, the training loop, checkpoint save/load, binary metrics and baseline comparison.
- `scripts/import_power_log.py` writes SELF-perspective `power_log_ranked_standard` examples with `game_id`, unique `sample_id` and final outcome target.
- `scripts/prepare_real_dataset.py` validates those fields, deduplicates complete match trajectories and assigns whole `game_id` groups to train/validation/test. It does not split individual states across partitions.

## Read-only local data audit

The source directory `data/processed_real/` was inspected read-only. No raw logs or examples were copied into the branch or committed. Counts changed between checks, so the latest audit and the fixed one-epoch smoke snapshot are reported separately.

- Latest read-only audit: **33 files**, **2,312** imported rows, **32** unique matches after identifying one duplicate trajectory, **2,273** unique examples.
- Latest match outcomes: **18 wins, 14 losses, 0 draws**.
- Latest examples per unique match: **26–156**, mean **71.03**.
- Latest distinct visible card IDs: **358**; current catalog IDs: **257**; unknown IDs: **101 (28.21%)**.
- All **2,312** rows in the latest read-only check deserialized and encoded. Encoder failures: **0**.
- Latest unknown IDs successfully used the shared UNK embedding. Forward smoke: **PASS**, batch size **2**, logits shape `[2]`, finite logits and probabilities. The earlier first audit also passed with batch size **8**.
- The model-visible state passes a strict `GameState` schema allowlist. Opponent hand identities are absent except cards explicitly represented as known/revealed; no hidden opponent identity fields are included in the encoded state.
- Split readiness: **PASS**. The existing splitter produced disjoint train/validation/test sets by whole match: 18 / 7 / 6 unique matches.

## One-epoch smoke

Because the available matches could produce valid train and validation splits, the optional one-epoch smoke ran using a temporary prepared snapshot made from the earlier read-only observation: 32 files, 31 unique matches, 2,247 deduplicated examples, split into 18 / 7 / 6 matches (1,402 / 410 / 435 examples). It completed the existing optimizer, backward pass, validation, test, and checkpoint path. The temporary snapshot and checkpoint were deleted after verification and were not committed. Metrics from this smoke are not evidence of model quality and are intentionally not reported here. A later read-only audit saw one additional collected match, confirming why training must use a fixed snapshot.

## Readiness and limits

- **PIPELINE READY:** yes. Real rows deserialize, encode, batch, run inference, and complete a one-epoch training/checkpoint smoke.
- **DATASET LARGE ENOUGH:** not established. Thirty-one unique matches are a small pilot and too few to support reliable generalization or model-quality claims.
- **MODEL GOOD:** unknown. No playing-strength claim is supported.
- Metrics already include loss, accuracy, ROC-AUC when defined, Brier score, and existing constant-prevalence/global-feature baselines.
- Principal limitation: the current examples do not retain reliable deck/archetype coverage metadata. Check collection diversity before interpreting future results.

## Validation

- Focused readiness, pipeline and Power.log tests: **39 passed**.
- Full Python suite with the pinned RosettaStone submodule (`f34da0d3fcb5ad312f7e2acf634d0536b044d29a`): **287 passed**.
- Ruff on changed Python files: **passed**.
- `scripts/check_generated_artifacts.py`: **36 pinned outputs reproduced**.
- `git diff --check`: **passed**.

### Practical collection target before ML-1B

For a first real-data Value baseline, target **at least 500 unique completed Ranked Standard matches**, including at least **150 wins and 150 losses**, so a whole-match 60/20/20 split can leave roughly 100 matches for each held-out partition. This is a practical starting heuristic, not a statistical guarantee. A larger and more varied sample (around 1,000+ matches) is preferable before relying on calibration or comparing model quality. Keep matches from multiple decks/opponents/ranks where available.

## Future commands

Run from the repository root, using a stable copy of the processed examples and a fresh snapshot directory:

```powershell
python scripts/prepare_real_dataset.py --input-dir <processed-real-dir> --output-dir <immutable-snapshot-dir> --seed 42
python scripts/audit_real_training_readiness.py --input-dir <processed-real-dir> --cards data/cards/standard_current_enUS.json
python scripts/train_real_value.py --dataset-dir <immutable-snapshot-dir> --checkpoint <new-candidate-checkpoint> --cards data/cards/standard_current_enUS.json --epochs 20 --batch-size 128 --seed 42
```

Do not train directly from the active collector directory, overwrite a prior checkpoint, or promote the candidate automatically.

## Next task — ML-1B: First Real Value Baseline Training

> When the local collection has grown, inspect the aggregate readiness report and select a fixed processed-data snapshot. Confirm that it contains enough distinct matches and a useful win/loss balance, then prepare disjoint whole-match train/validation/test splits. Run the existing ValueNetwork pipeline once on that snapshot, saving to a new candidate checkpoint path. Record provenance, split sizes, class balance and baseline metrics. Treat results as an initial experiment only; do not overwrite or promote any existing model and do not claim playing strength from a small pilot.
