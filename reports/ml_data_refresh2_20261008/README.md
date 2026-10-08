# ML-DATA-REFRESH-2 — Final Policy dataset rebuild after OBSERVATION-EXTRACTION-1

Status: `COMPLETE`

This is a data preparation and verification run only. No model was trained, no gameplay engine or encoder schema was changed, and no raw log, existing dataset, historical result, or checkpoint was modified.

## Source and corpus identity

- Base: `cc8400b52f00f10b926c8395663d624b0b6d66ab` (`origin/main` at start).
- Rebuild source revision: `2b5ff7309d8dc7352a8caf1720933394b59e3209`.
- Raw input: 36 Power.log files / 148,951,694 bytes; corpus fingerprint `e18c173827ed54ea073b6462411ccf671be6e19a592c5d58c57b93f159de28d3`.
- Admitted: 32 matches / 1,227 labeled decisions. Four matches were rejected as `GAME_RESET`.
- New dataset identity: `f89984cac9278dca68e02f519098467d2821a0b7d5323331f275b7ce6dfe7e37`.
- Canonical content identity: `6f6b9292372cf94994c39a5dc01a7c8d3439d754efefed02565adcda48a2d2cb`.
- Importer source fingerprint: `e776cfb884e63d5d0a116ef54cb329fc213f18511ff86400a6afed4e88483013`.
- Catalog file SHA-256: `c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34`; catalog identity: `3dfae0cb5fe312af22c2a16e01eba1286c073f89ea020808fbbf1778067870d9`.
- Schema versions: state encoding 16, Policy action 4, semantic action 1, real-policy dataset 1.

The existing v1 and v2 checkpoints loaded successfully without modification. Their SHA-256 values remain `5a5e3435c0dcda5ce69bcd0a48dc8521fb3696e2a7794e268b894efbf7e3e95e` and `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`, respectively.

## Comparison and extraction results

The new corpus was compared to the strict 32-match / 1,227-decision ML-DATA-REFRESH-1 canonical dataset (`60351703209b5cda69caa84364994e7763c43b6baba3d8a6d65181e3c7e96cb9`). All 1,227 decision IDs matched. Chosen-action indices, chosen-action semantics, legal menus, and outcomes were unchanged for all rows. There were no additions or losses and no differences in state fields outside the reviewed hero fields.

| State field | Decisions changed |
|---|---:|
| SELF `hero_max_health` | 1,227 |
| Opponent `hero_max_health` | 1,227 |
| SELF `hero_frozen` | 19 |
| Opponent `hero_frozen` | 0 |
| SELF `hero_power_ready` | 137 |
| Opponent `hero_power_ready` | 0 |

Maximum Health was known for both sides at every decision: SELF was 30 in 1,227/1,227; the opponent was 30 in 771 and 40 in 456. Frozen remained unknown when the log did not state it: SELF True 4, False 15, unknown 1,208; opponent unknown 1,227. Hero Power readiness: SELF True 693, False 390, unknown 144; opponent True 386, False 568, unknown 273.

Independent aggregate results: 1,227 decisions changed only through at least one permitted hero field; unexpected state changes: 0, with no unexpected paths. Missing Frozen/readiness values were not imputed. The importer source fingerprint includes the merged observation-extraction sources.

## Strict validation and reproducibility

The canonical output passed `load_examples()`, `validate_example()` for every row, and `audit_dataset()`. The audit reports 32 unique/labeled matches, 1,227 labeled decisions, 335 safely skipped decisions (`AMBIGUOUS_SELECTION` 254, `OPTIONS_SUPERSEDED` 79, `CHOICE_UNRESOLVED` 2), and privacy checks `PASS`. Four raw matches were rejected as `GAME_RESET`.

Two independent rebuilds produced identical canonical content identity `6f6b9292372cf94994c39a5dc01a7c8d3439d754efefed02565adcda48a2d2cb` and dataset identity `f89984cac9278dca68e02f519098467d2821a0b7d5323331f275b7ce6dfe7e37`.

## Quality and prior experiment use

- Outcomes: 18 wins, 14 losses, 0 draws. SELF class by match: Priest 29, Warrior 3.
- Chosen actions: PLAY_CARD 599, END_TURN 315, ATTACK 137, HERO_POWER 124, ACTIVATE_LOCATION 52.
- Targeted chosen decisions: 299/1,227. Legal-menu sizes: 1–69 (mean 11.63); full histogram and turn 1–46 histogram are in ignored local metadata.
- Unknown public card identity ratio: 26.31%. Deck identity is not reconstructed from partial visible hands.

Historical usage and extraction comparison were kept separate. ML-EVAL-0 usage was matched against its original 32-match / 1,227-decision corpus, identity `bc5d9c8667bcd5dbf2a6f26297a843c22d8cfdfe73b3a6dafafc825821f54b18`; the mapping was reliable. The ML-1C/ML-2A checkpoint split remains tied to its historical 21-match / 736-decision corpus, identity `2b20c3b0fd48c34031dfbb8cf516cda9679ce53fee21843e0fc8613609f0b598`. All 32 currently admitted matches are already used by a prior policy split or ML-EVAL-0. Four `NOT_KNOWN_USED` registry entries are rejected `GAME_RESET` matches and are not trainable examples; the registry also preserves one previously used identity absent from this raw corpus.

`NO_FRESH_HOLDOUT`: no admitted unused matches are available, and the proposed clean three-way split has 0 matches / 0 decisions. The data is strictly loadable, but is not ready for a new training/evaluation experiment. Additional complete matches with identities disjoint from every registered training, validation, test, and evaluation cohort are required. No evaluation result was rerun or reclassified.

## Model compatibility

This rebuild changes input values, not tensor layout or model provenance. State encoding remains version 16 with the existing 106 global feature names. `hero_frozen` and `hero_power_ready` retain their existing encoded features, so known values change encoded values. `hero_max_health` remains outside the current encoder. Tests confirm the global tensor shape is unchanged, the two existing feature values respond to their observations, and changing maximum Health alone does not alter encoded features. Both installed checkpoints passed the strict checkpoint loader; their files and split metadata were not written.

Checkpoint compatibility does not establish model accuracy or new training readiness. No benchmark or training run was performed.

## Tests and checks

- Refresh/dataset regression tests: **42 passed** (includes the new usage separation, field-level comparison, strict validation, determinism, and encoder compatibility checks).
- Full pytest with pinned RosettaStone `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`: **641 passed, 1 skipped**.
- Ruff `check src tests scripts`: pass. Generic card branch guard: pass. Native failure-site audit: 0 problems. Generated-artifact check: 36 pinned outputs reproduced.
- Hosted Source workflow [37830018799](https://github.com/MaksimOrekhov/manamind/actions/runs/37830018799), on tooling commit `2b5ff7309d8dc7352a8caf1720933394b59e3209`: Windows and Ubuntu jobs completed successfully. The ManaEngine workflow did not trigger because this branch changes no paths in its filter; no ManaEngine source was touched.

## Local output and reproduction

The generated JSONL, audit manifests, metadata, and experiment usage registry remain in ignored `E:\ManaMind\data\processed_policy_real\refresh_obs1_final`; the two independent determinism outputs are its ignored sibling directories. They contain private match identities and must remain local. Raw inputs stayed read-only.

Rebuild from the repository checkout using a new output path:

```powershell
$env:PYTHONPATH = 'src'
$env:PYTHONUTF8 = '1'
python scripts/refresh_real_policy_dataset.py `
  --raw-dir E:\ManaMind\data\raw\collected `
  --output-dir E:\ManaMind\data\processed_policy_real\<new-name> `
  --cards data\cards\standard_current_enUS.json `
  --previous E:\ManaMind\data\processed_policy_real\collected `
  --comparison-baseline E:\ManaMind\data\processed_policy_real\refresh_20261008_reviewfix `
  --historical-dataset E:\ManaMind\data\processed_policy_ml2a\seed42_v2\dataset `
  --v1-checkpoint E:\ManaMind\data\processed_policy_ml1c\baseline_seed42_v1\policy.pt `
  --v2-checkpoint E:\ManaMind\data\processed_policy_ml2a\seed42_v2\policy.pt `
  --eval-report reports\ml_eval0_real_policy_20261008\metrics.json `
  --seed 20261008 --verify-determinism
```
