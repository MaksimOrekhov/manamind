# NEW-MATCHES-EVAL-1 — протокол и результаты

## Зафиксированный протокол

Цель — проверить, насколько существующие checkpoints повторяют решения игрока на новых завершённых матчах. Обучение и изменение LIVE Policy не выполняются. Позиции включаются только при совпадении полного match ID, options ID, state hash, записанного LIVE snapshot, полного упорядоченного меню из Strategy и Outcome Shadow и фактического выбранного действия из Power.log. Frozen v2 top-3 дополнительно проверяется на принадлежность этому меню.

Найдены **13 пригодных матчей** и **239 решений**. Это ниже ожидаемых примерно 25 матчей; оценка будет техническим пилотом и не позволит уверенно выбрать победителя.

Приватный идентификатор входного набора: `3f94258a274858e58996062ee15cde3afe61589554cfe39cc447c169c812f0b1`. Split-plan SHA-256: `408cb21b8e29cd1caa9dfd585c0b6d2dc7917c6a8021aa49910a4ddd5cf0218a`. Код протокола зафиксирован коммитом `a8632301ed79268ac116e34e67173217b0b4e2c5`; SHA-256 скрипта: `359ec940486f706d90f71fbf9793de53ee360bdf46ca45e409b8a7a3389d216b`.

Девять ID из `fresh_holdout` использованы только для исключения пересечений. Их игровые данные не открывались, inference не запускался.

### Checkpoints

- `frozen_v2` — `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d` (architecture from checkpoint).
- `retrained_v2` — `9358f932fc7846d6a436e2a1e6c7ff6cffda1f2929fac5521710f973e14a05e3` (v2).
- `policy_v3` — `d874d196d9c2f1e12c6d697ad2de57883a29352976dbb1ee9dbd6ba63af84f82` (v3).
- `prepare_v2_seed42` — `a9dd7c1eee8c9f4bbe23b3447e4aa02b5f06019f421ad27e7240ab2ae3a89c9e` (v2).
- `prepare_v3_seed42` — `3541ac74840491491a5ae07a9d1be9ea068d61aaf158ad6016d8b3fab7680d12` (v3).
- `control_v2_seed42` — `4671710a50b3f13fbde2bbbee39f5c51b1abfc2f3e2c53a16b92f55c4d46aaf0` (v2).
- `control_v3_seed42` — `314232188cc042e837de81ae7865c5d3d1fc0896dc8978ce681fcf25dcc26d7a` (v3).

Основные сравнения: все кандидаты на одинаковых меню без Prepare; Prepare v2/v3 отдельно на меню с Prepare. Старые и контрольные модели на Prepare-меню не запускаются. Дополнительно включены control v2/v3 seed 42, чтобы сравнить Prepare и контрольные checkpoints на обычных меню.

Метрики: cross-entropy, Top-1, Top-3 (только меню 3+ действий), MRR и uniform random baseline. Неопределённость считается парным bootstrap по целым матчам, 5 000 повторов, seed 20261018. Модели и подмножества после просмотра результатов не выбираются.

## Инвентаризация до inference

- Файлов в `data/raw/collected`: 104; по ID именованы 86; legacy-файлы без ключа: 18 (UNVERIFIED).
- Категории инвентаризации: {"NEW_ELIGIBLE": 13, "PREVIOUSLY_USED": 73, "UNVERIFIED": 19}. Причины исключений: {"LEGACY_FILENAME_WITHOUT_MATCH_KEY": 18, "MATCH_ID_IN_PRIOR_SPLIT_OR_EVALUATION": 64, "NO_DECISION_WITH_EXACT_LIVE_MENU_JOIN": 1, "PRE_EXISTING_LIVE_OBSERVATION": 1, "PROTECTED_FRESH_HOLDOUT_ID_ONLY": 8}.
- Записей LIVE: 66; совпадающие и не собранные Power.log записи отдельно классифицированы по ID.
- По прежним split, registry или checkpoint использований исключено: 73.
- Защищённые raw-префиксы `fresh_holdout`, пропущенные без чтения: 8.
- Новые кандидаты после проверки пересечений: 14; импортировано завершённо: 14.
- Пригодные после точной LIVE-сверки: 13 матчей; 239 решений.
- Prepare-меню в повторном импорте: 15; точное совпадение полного LIVE-меню: 0; точных выбранных действий `PREPARE_CARD`: 0.
- LIVE запуск не включал `--prepare-actions`; несовпавшие Prepare-меню исключены: `{"DUPLICATE_LIVE_SNAPSHOT": 1, "LIVE_SNAPSHOT_NOT_MATCHED": 9, "NO_PREDICTION_ROW": 5}`.
- Оценённых Prepare-меню после точной сверки: 0; выбранных `PREPARE_CARD`: 0.
- Не сопоставленные LIVE-решения исключены по диагностике: `{"DUPLICATE_LIVE_SNAPSHOT": 157, "LIVE_SNAPSHOT_NOT_MATCHED": 103, "NO_PREDICTION_ROW": 14}`.
- Решения, пропущенные Power.log импортёром: `{"AMBIGUOUS_SELECTION": 2, "CHOICE_UNRESOLVED": 3, "GAME_RESET_STALE_STATE": 41, "OPTIONS_SUPERSEDED": 46}`.

`results.json` пока содержит только зафиксированный протокол. Полные состояния, legal menu, оценки и приватные разборы хранятся в игнорируемом `data/processed_new_matches_eval_1/`.
