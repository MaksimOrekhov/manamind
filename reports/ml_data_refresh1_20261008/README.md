# ML-DATA-REFRESH-1 — Canonical real-policy dataset rebuild

Result: `COMPLETE`

The Policy corpus was rebuilt from the current local Power.log collection using the existing segmented ML-1B importer. This is a data refresh only: no model training, evaluation, encoder/schema changes, or changes to live/ManaEngine behavior were made.

## Provenance and reproducibility

- Exact base: `3c0cb5db76a306fc3c7bb86ed32d3e99af17e377` (`origin/main` at task start).
- Branch: `codex/ml-data-refresh-1`; workflow source revision: `f90e8a39ab7bb590fe8270e6cf8f46a948dc4fc9`.
- Raw inputs: 36 `.log` files, 148,951,694 bytes. Four reset/incomplete matches were rejected as `GAME_RESET`; 32 matches were admitted.
- Two independent imports produced the same canonical content identity: `730303e1f9d89af7609e48ceab57ac3b2265ca8672e282cf957541f9c3f367dd`.
- Admitted dataset: 32 matches / 1,227 decisions; dataset identity `60351703209b5cda69caa84364994e7763c43b6baba3d8a6d65181e3c7e96cb9`.
- Input corpus fingerprint: `e18c173827ed54ea073b6462411ccf671be6e19a592c5d58c57b93f159de28d3`. Catalog identity: `3dfae0cb5fe312af22c2a16e01eba1286c073f89ea020808fbbf1778067870d9`. Catalog file SHA-256: `c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34`. Importer/dependency source fingerprint: `d5776d49fd8d227d5267648d8b3bb8cde7053020e9021f3b283b2c958c918d51` (individual tracked source hashes are in local metadata).
- Existing contracts retained: real-policy dataset schema 1, state encoding 16, policy action 4, semantic action 1. The checkpoint loader successfully validated the existing v1 and v2 checkpoint provenance; their exact SHA-256 values are stored in the ignored local usage registry.
- Comparison with the previous 32-match / 1,227-decision corpus found no decision, action label, legal-menu, outcome, or non-schema state differences. All 1,227 serialized states now explicitly include the current `healing_bonus: null` field; this is a serialization compatibility repair through the canonical importer, not a change in observation meaning.

The corpus and per-match registries remain under `data/processed_policy_real/refresh_20261008` and are Git-ignored. The two determinism outputs are also ignored. No raw log excerpt, player identity, or per-match identifier is included in this report.

## Experiment-use registry and split safety

The local registry records the frozen v1/v2 match-level split provenance (17 train / 2 validation / 2 test matches; 591 / 85 / 60 decisions) and the 12-match / 515-decision ML-EVAL-0 inference cohort. The ML-1C/ML-2A historical corpus identity remains `2b20c3b0fd48c34031dfbb8cf516cda9679ce53fee21843e0fc8613609f0b598` (21 matches / 736 decisions). The prior ML-EVAL-0 corpus identity remains `bc5d9c8667bcd5dbf2a6f26297a843c22d8cfdfe73b3a6dafafc825821f54b18` (32 matches / 1,227 decisions).

All 32 currently admitted matches are already assigned to prior training, validation, test, or ML-EVAL-0 inference use. The four rejected reset matches contribute no admitted decisions. Therefore the refresh proposes no clean three-way split (0 eligible matches / 0 decisions). No fresh holdout was created, and no historical split or test result was changed or reused as a new evaluation.

## Data quality observations

- Outcomes: 18 wins, 14 losses, 0 draws. SELF class is concentrated: 29 Priest matches and 3 Warrior matches.
- Decisions per match: minimum 11, median 34, maximum 95. Action labels: `PLAY_CARD` 599, `END_TURN` 315, `ATTACK` 137, `HERO_POWER` 124, `ACTIVATE_LOCATION` 52. Targeted decisions: 299/1,227 (24.4%).
- 335 decisions were skipped by existing admission rules: 254 `AMBIGUOUS_SELECTION`, 79 `OPTIONS_SUPERSEDED`, and 2 `CHOICE_UNRESOLVED`.
- 299/1,227 admitted decisions are targeted; legal-menu sizes range from 1 to 69 actions.
- The unknown public-card identity ratio is 26.31% under the existing audit definition.
- `healing_bonus` is unknown in 2,454 serialized player observations; turn number is unknown for all 1,227 decisions. No deck identity is inferred from partial visible-hand snapshots.

The refreshed corpus is technically loadable for plumbing checks, but it is not ready for a defensible new training/evaluation cycle: its admitted matches are all previously used and there is no clean holdout. These are observable data limitations, not evidence of model quality or playing strength. No model was trained and no new predictive metrics are claimed.

## Validation

- New refresh tests plus existing real-policy dataset tests: **36 passed**.
- Ruff across the repository: **passed**.
- `git diff --check`: **passed**.
- Full pytest: **490 passed, 1 skipped, 26 errors and 3 failed**. All 29 failures stem from the isolated worktree lacking the initialized `vendor/RosettaStone/Resources/cards.json` pinned submodule needed by those existing tests. The pinned submodule revision is present in the main checkout; the worktree was left unmodified rather than linking/copying that unrelated private checkout into it.
- Rebuilt corpus and determinism directories were verified Git-ignored; no private data is staged or committed.
- Hosted Source and generated artifact checks passed on Ubuntu and Windows for the implementation/report revision (GitHub Actions run [37822180693](https://github.com/MaksimOrekhov/manamind/actions/runs/37822180693)); both platform jobs reported success.

## Reproduction command

Run from the task checkout. Choose a new output name each time; the importer refuses to overwrite an existing dataset.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
$out = 'E:\ManaMind\data\processed_policy_real\refresh_REPRODUCE_WITH_NEW_NAME'
E:\ManaMind\.venv\Scripts\python.exe scripts\refresh_real_policy_dataset.py `
  --raw-dir E:\ManaMind\data\raw\collected `
  --output-dir $out `
  --cards data\cards\standard_current_enUS.json `
  --previous E:\ManaMind\data\processed_policy_real\collected `
  --historical-dataset E:\ManaMind\data\processed_policy_ml2a\seed42_v2\dataset `
  --v1-checkpoint E:\ManaMind\data\processed_policy_ml1c\baseline_seed42_v1\policy.pt `
  --v2-checkpoint E:\ManaMind\data\processed_policy_ml2a\seed42_v2\policy.pt `
  --eval-report reports\ml_eval0_real_policy_20261008\metrics.json `
  --seed 20261008 --verify-determinism
```

## Recommended next task

Collect a new cohort of complete, admitted matches with identities disjoint from every registered v1/v2 and ML-EVAL-0 cohort, spanning more SELF classes, outcomes, matchups/decks, and publicly visible card variety. Freeze whole-game train/validation/test partitions before any training or tuning, and keep prior held-out matches out of model selection.

ML-DATA-REFRESH-1 = COMPLETE
