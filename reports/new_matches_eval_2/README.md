# NEW-MATCHES-EVAL-2

Статус: **PROTOCOL_LOCKED**. Идентичность выборки: `9522fcec5b3768d351703517ed6f557e4c352c8e537883df6a8a91819939a906`.

Новых raw-кандидатов: 35; завершённых Ranked Standard после импорта: 33; строгая выборка: **12 матчей, 204 решений**. Диагностические решения вне основного набора: 790. Безопасно объединены повторные снимки для 33 решений.

Это новые матчи отдельно от 13 игр EVAL-1. Все источники прежней инвентаризации исключены по ID, девять fresh_holdout исключены до открытия игровых файлов. Старые результаты не пересчитывались. Число 25 не использовалось для выбора файлов или остановки.

## Классы и колоды

| Класс | Завершено игр | Строгих игр | Решений |
|---|---:|---:|---:|
| DEMONHUNTER | 2 | 2 | 31 |
| HUNTER | 16 | 3 | 58 |
| PALADIN | 1 | 0 | 0 |
| ROGUE | 1 | 0 | 0 |
| WARLOCK | 4 | 4 | 64 |
| WARRIOR | 9 | 3 | 51 |

Архетипы UNKNOWN: проверенного списка колод нет. Класс не доказывает архетип; разные колоды внутри класса не угадывались.

## Зафиксированный протокол

- `hypothesis`: "Fixed existing candidates may improve imitation over Frozen v2 across newly collected classes."
- `baseline`: "frozen_v2"
- `primary_candidates`: ["retrained_v2", "policy_v3", "control_v3_seed42", "prepare_v2_seed42", "prepare_v3_seed42"]
- `additional`: ["control_v2_seed42"]
- `main_comparison`: "All seven fixed seed42 models, identical ordinary full ordered legal menus."
- `metrics`: ["cross_entropy", "top1", "top3", "mrr", "uniform_random", "top1_pairwise_agreement"]
- `top3_rule`: "Menus with at least three actions only; ties use original menu order."
- `pairing`: "Unique raw key; same full state/hash/options ID; identical snapshots except seq; shadow seq belongs to group; no conflicting journals; complete ordered menus; block-corroborated player choice."
- `uncertainty`: {"method": "paired whole-match bootstrap", "draws": 5000, "seed": 20261018, "primary_family_correction": "Bonferroni simultaneous 99% intervals for five candidates; marginal 95% also reported"}
- `verdict_rule`: "Fewer than 10 strict ordinary matches: INSUFFICIENT_DATA. Otherwise candidate improvement requires simultaneous CE CI <0 and Top1 CI >0, same signs on match-balanced means, and no sign reversal when leaving one class out. Regression requires simultaneous CE CI >0 and Top1 CI <0. Else NO_CLEAR_WINNER. No automatic live promotion."
- `class_rule`: "At least 5 games per class for descriptive comparisons; fewer marked insufficient. No class-specific model choice. Archetypes remain UNKNOWN without verified deck metadata."
- `review_rule`: "Up to 20 unique decisions, round-robin over EVAL-1 fixed disagreement categories sorted by score/ID; check every legal action with existing forecaster. CONFIRMED_ERROR only if a strict EXACT living-self lethal exists and model top1 is EXACT nonlethal; heuristic gaps alone are DISAGREEMENT_ONLY. PARTIAL/unsupported coverage is INSUFFICIENT_COVERAGE. No multistep lethal claim."
- `prepare_rule`: "Only Prepare v2/v3 on exactly joined compatible menus; zero examples does not block ordinary comparison."
- `training_or_finetuning`: false
- `live_policy_changed`: false

## Checkpoint SHA-256

- `frozen_v2`: `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`
- `retrained_v2`: `9358f932fc7846d6a436e2a1e6c7ff6cffda1f2929fac5521710f973e14a05e3`
- `policy_v3`: `d874d196d9c2f1e12c6d697ad2de57883a29352976dbb1ee9dbd6ba63af84f82`
- `prepare_v2_seed42`: `a9dd7c1eee8c9f4bbe23b3447e4aa02b5f06019f421ad27e7240ab2ae3a89c9e`
- `prepare_v3_seed42`: `3541ac74840491491a5ae07a9d1be9ea068d61aaf158ad6016d8b3fab7680d12`
- `control_v2_seed42`: `4671710a50b3f13fbde2bbbee39f5c51b1abfc2f3e2c53a16b92f55c4d46aaf0`
- `control_v3_seed42`: `314232188cc042e837de81ae7865c5d3d1fc0896dc8978ce681fcf25dcc26d7a`

## Исключения

```json
{
  "matches": {
    "LEGACY_FILENAME_WITHOUT_MATCH_KEY": 18,
    "MATCH_ID_IN_PRIOR_SPLIT_OR_EVALUATION": 77,
    "NO_EXACT_LIVE_JOIN": 21,
    "PROTECTED_FRESH_HOLDOUT_ID_ONLY": 8,
    "SELF_AMBIGUOUS": 2,
    "SOURCE_ALREADY_IN_EVAL_1_INVENTORY": 1
  },
  "decisions": {
    "LIVE_SNAPSHOT_NOT_MATCHED": 694,
    "CONFLICTING_OUTCOME_ROWS": 91,
    "NO_PREDICTION_ROW": 5
  },
  "importer": {
    "OPTIONS_SUPERSEDED": 113,
    "UNSUPPORTED_DECISION_KIND": 22,
    "TARGET_UNRESOLVED": 6,
    "AMBIGUOUS_SELECTION": 11,
    "GAME_RESET_STALE_STATE": 1,
    "CHOICE_UNRESOLVED": 1
  }
}
```

## Воспроизведение

`.venv/Scripts/python.exe scripts/new_matches_eval_2.py --preflight`, отдельный commit протокола, затем `--evaluate`. Повторная запись существующих private outputs запрещена. Все данные закреплены SHA-256; новые поступления не меняют выборку.
