# NEW-MATCHES-EVAL-2

Статус: **COMPLETE**. Идентичность выборки: `9522fcec5b3768d351703517ed6f557e4c352c8e537883df6a8a91819939a906`.

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

- `additional`: ["control_v2_seed42"]
- `baseline`: "frozen_v2"
- `class_rule`: "At least 5 games per class for descriptive comparisons; fewer marked insufficient. No class-specific model choice. Archetypes remain UNKNOWN without verified deck metadata."
- `hypothesis`: "Fixed existing candidates may improve imitation over Frozen v2 across newly collected classes."
- `live_policy_changed`: false
- `main_comparison`: "All seven fixed seed42 models, identical ordinary full ordered legal menus."
- `metrics`: ["cross_entropy", "top1", "top3", "mrr", "uniform_random", "top1_pairwise_agreement"]
- `pairing`: "Unique raw key; same full state/hash/options ID; identical snapshots except seq; shadow seq belongs to group; no conflicting journals; complete ordered menus; block-corroborated player choice."
- `prepare_rule`: "Only Prepare v2/v3 on exactly joined compatible menus; zero examples does not block ordinary comparison."
- `primary_candidates`: ["retrained_v2", "policy_v3", "control_v3_seed42", "prepare_v2_seed42", "prepare_v3_seed42"]
- `review_rule`: "Up to 20 unique decisions, round-robin over EVAL-1 fixed disagreement categories sorted by score/ID; check every legal action with existing forecaster. CONFIRMED_ERROR only if a strict EXACT living-self lethal exists and model top1 is EXACT nonlethal; heuristic gaps alone are DISAGREEMENT_ONLY. PARTIAL/unsupported coverage is INSUFFICIENT_COVERAGE. No multistep lethal claim."
- `top3_rule`: "Menus with at least three actions only; ties use original menu order."
- `training_or_finetuning`: false
- `uncertainty`: {"draws": 5000, "method": "paired whole-match bootstrap", "primary_family_correction": "Bonferroni simultaneous 99% intervals for five candidates; marginal 95% also reported", "seed": 20261018}
- `verdict_rule`: "Fewer than 10 strict ordinary matches: INSUFFICIENT_DATA. Otherwise candidate improvement requires simultaneous CE CI <0 and Top1 CI >0, same signs on match-balanced means, and no sign reversal when leaving one class out. Regression requires simultaneous CE CI >0 and Top1 CI <0. Else NO_CLEAR_WINNER. No automatic live promotion."

## Checkpoint SHA-256

- `control_v2_seed42`: `4671710a50b3f13fbde2bbbee39f5c51b1abfc2f3e2c53a16b92f55c4d46aaf0`
- `control_v3_seed42`: `314232188cc042e837de81ae7865c5d3d1fc0896dc8978ce681fcf25dcc26d7a`
- `frozen_v2`: `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`
- `policy_v3`: `d874d196d9c2f1e12c6d697ad2de57883a29352976dbb1ee9dbd6ba63af84f82`
- `prepare_v2_seed42`: `a9dd7c1eee8c9f4bbe23b3447e4aa02b5f06019f421ad27e7240ab2ae3a89c9e`
- `prepare_v3_seed42`: `3541ac74840491491a5ae07a9d1be9ea068d61aaf158ad6016d8b3fab7680d12`
- `retrained_v2`: `9358f932fc7846d6a436e2a1e6c7ff6cffda1f2929fac5521710f973e14a05e3`

## A. Имитация

Вердикт: **NO_CLEAR_WINNER**.

| Модель | CE ↓ | Top-1 ↑ | Top-3 ↑ | MRR ↑ |
|---|---:|---:|---:|---:|
| frozen_v2 | 1.8251 | 0.387 | 0.483 | 0.552 |
| retrained_v2 | 1.9051 | 0.407 | 0.556 | 0.569 |
| policy_v3 | 1.7914 | 0.426 | 0.556 | 0.579 |
| prepare_v2_seed42 | 1.8706 | 0.402 | 0.53 | 0.565 |
| prepare_v3_seed42 | 2.3434 | 0.402 | 0.536 | 0.565 |
| control_v2_seed42 | 1.8393 | 0.402 | 0.55 | 0.567 |
| control_v3_seed42 | 1.9921 | 0.402 | 0.55 | 0.566 |

Парные 95% и одновременные 99% интервалы, uniform baseline, совпадение Top-1, метрики по матчам, классам, типам действий, фазам и размеру меню: `results.json`. Robustness содержит равный вес матчей и исключение по одному классу/матчу. Top-3 имеет отдельный знаменатель: меню от трёх действий. Действие игрока не считается эталоном стратегии.

Prepare: NO_EXAMPLES; выборов PREPARE_CARD: 0.

## B. Реальные рекомендации

**STRATEGIC_QUALITY_NOT_ESTABLISHED**. Эвристика Strategic Scorer не является доказательством правильности хода. Outcome Shadow проверяет доступную механику одного действия; поиск цепочки летала не выполнялся.

```json
{
  "reviewed_decisions": 20,
  "classification_counts": {
    "INSUFFICIENT_COVERAGE": 19,
    "DISAGREEMENT_ONLY": 1
  },
  "confirmed_errors_by_model": {},
  "scope": "Selected disagreements, not an error-frequency estimate. Exact one-action only; no multistep search."
}
```

Полные выбранные ситуации, состояния, меню, Top-3 семи моделей, ход игрока, оценки scorer, исходные и пересчитанные прогнозы сохранены только в ignored `data/processed_new_matches_eval_2/cases.private.json`. Это целевой разбор расхождений, не оценка частоты ошибок.

## C. Следующий приоритет

1. Повысить проверяемость последствий: аудит отсутствующих текстов/метаданных и видимых SELF-фактов, затем узкая поддержка реально встречавшихся эффектов в существующем Outcome Shadow. Без смены закреплённого каталога, ManaEngine или второго движка правил.
2. Повысить репрезентативность строгой оценки: выяснить причины отсутствующих LIVE-состояний, сохранять полный join без ослабления; собрать новые игры по недопредставленным классам и экспертные оценки без показанных подсказок. Эту выборку больше не считать untouched holdout.
3. После отдельного согласования проверить небольшой Policy-эксперимент на новой независимой контрольной выборке. Сейчас не расширять архитектуру и не подгонять веса Strategic Scorer: общего преимущества не доказано, а его крупные отрывы часто зависят от непрочитанных эффектов.

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
    "CONFLICTING_OUTCOME_ROWS": 91,
    "LIVE_SNAPSHOT_NOT_MATCHED": 694,
    "NO_PREDICTION_ROW": 5
  },
  "importer": {
    "AMBIGUOUS_SELECTION": 11,
    "CHOICE_UNRESOLVED": 1,
    "GAME_RESET_STALE_STATE": 1,
    "OPTIONS_SUPERSEDED": 113,
    "TARGET_UNRESOLVED": 6,
    "UNSUPPORTED_DECISION_KIND": 22
  }
}
```

## Воспроизведение

`.venv/Scripts/python.exe scripts/new_matches_eval_2.py --preflight`, отдельный commit протокола, затем `--evaluate`. Повторная запись существующих private outputs запрещена. Все данные закреплены SHA-256; новые поступления не меняют выборку.

## Что означают результаты

На момент фиксации обнаружено 35 новых keyed raw-кандидатов: 33 удалось независимо подтвердить как завершённые Ranked Standard, два отклонены как `SELF_AMBIGUOUS`. Таким образом, игр больше 25 уже отдельно от прежних 13; проблема не в смешении старой и новой выборки, а в узком строгом LIVE-покрытии. 994 импортированных решения = 204 строгих + 790 диагностических. Эти 790 не участвовали в inference или выборе победителя. Из 33 игр 21 не имеет ни одного строгого решения. Все 694 отсутствующих сопоставления и 91 конфликтующий Outcome исключены, не восстановлены предположительно.

Протокол зафиксирован коммитом `022e762` до inference. Начальный технический draft инвентаризации также сохранён локально; до окончательной фиксации добавлены фактический census LIVE/ожидающих файлов и явный запрет дублированных индексов меню. В ходе инвентаризации продолжали поступать новые файлы; после финального lock состав не менялся. Защищённые игры не открывались.

Policy v3 имеет лучшие описательные показатели среди сетей: CE 1.7914, Top-1 42.65%, Top-3 55.63%, MRR 0.5792. Frozen: CE 1.8251, Top-1 38.73%. Uniform: CE 1.6766, Top-1 29.97%, Top-3 44.00%, MRR 0.4863. Все сети лучше uniform по совпадению Top-1, но хуже по CE: уверенные расхождения остаются существенной проблемой. Это не измерение стратегической силы и не отдельный тест калибровки.

| Кандидат − Frozen | ΔCE | Парный 95% CI | ΔTop-1, п.п. | Парный 95% CI, п.п. |
|---|---:|---|---:|---|
| Retrained v2 | +0.0800 | [-0.0631; +0.1938] | +1.96 | [-1.44; +6.56] |
| Policy v3 | -0.0337 | [-0.1627; +0.0963] | +3.92 | [-1.96; +8.75] |
| Control v3 | +0.1670 | [+0.0235; +0.3012] | +1.47 | [-3.36; +5.22] |
| Prepare v2 | +0.0455 | [-0.0599; +0.1254] | +1.47 | [-3.91; +8.02] |
| Prepare v3 | +0.5182 | [+0.2473; +0.8224] | +1.47 | [-2.82; +6.11] |

Для основного решения использованы более широкие одновременные 99% интервалы по пяти кандидатам, как задано до inference. У Prepare v3 CE ухудшается даже по этому критерию: [+0.1882; +0.9428]. Это отдельный сигнал регрессии CE на обычных меню; общий вердикт не `REGRESSION`, поскольку заранее требовалось также убедительное ухудшение Top-1. Control v3 не повторяет прежнее преимущество: его CE теперь выше Frozen, а одновременный интервал включает ноль. Прошлый пилот не использовался для выбора модели.

## Устойчивость по классам и длине партий

| Класс | Игр / решений | Frozen CE / Top-1 | Policy v3 CE / Top-1 | Control v3 CE / Top-1 |
|---|---:|---:|---:|---:|
| Demon Hunter | 2 / 31 | 1.784 / 45.2% | 1.424 / 54.8% | 1.649 / 41.9% |
| Hunter | 3 / 58 | 1.806 / 43.1% | 1.721 / 46.6% | 1.901 / 46.6% |
| Warlock | 4 / 64 | 1.744 / 39.1% | 1.914 / 39.1% | 2.190 / 42.2% |
| Warrior | 3 / 51 | 1.974 / 29.4% | 1.941 / 35.3% | 2.056 / 29.4% |

Каждый срез меньше заранее заданных пяти матчей; таблица описательная. Преимущество Policy v3 по CE зависит от класса: без Demon Hunter разница становится +0.0247, хотя преимущество Top-1 остаётся +2.89 п.п. В Warlock CE Policy v3 уже хуже Frozen. Поэтому перенос на разные классы не подтверждён. Paladin и Rogue представлены новыми raw-играми, но не строгим набором; их нейросетевые метрики не вычислялись.

Самая длинная включённая партия даёт 39/204 решений (19.1%). При равном весе матчей Top-1: Frozen 35.69%, Policy v3 38.68%; ΔCE Policy v3 −0.1324. Исключение любого одного матча сохраняет описательные знаки преимущества Policy v3, но исключение класса меняет вывод по CE. Оценки по каждому матчу, действие×предсказание для каждого класса и частота расхождения сетей опубликованы в `results.json`; победитель для отдельного класса не выбирался.

## Полезность рекомендаций и ограничения scorer

Двадцать полных локальных разборов дополнены индивидуальными пояснениями в ignored `case_annotations.private.json`. Из них 19 — `INSUFFICIENT_COVERAGE`, один — `DISAGREEMENT_ONLY`; `CONFIRMED_ERROR` и `LIKELY_PROBLEM` не присвоены. Покрытие пересчитанных 120 действий: 3 EXACT, 114 PARTIAL, 3 UNSUPPORTED. Строго подтверждённых пропущенных одношаговых леталов не найдено; многошаговые леталы не проверялись. Это не доказывает отсутствие тактических ошибок.

В разборе встречаются обе стороны проблемы END_TURN: пас при доступных атаках и предложение продолжать атаку, когда игрок и scorer предпочитают остановиться. Доступное действие само по себе не доказывает полезности. Для Hero Power против розыгрыша/атаки не хватает текстов и точных последствий; даже совпадение всех семи сетей не подтверждает лучший ход. Различные атакующие нередко означают различный порядок действий или проверку секрета, поэтому несовпадение с игроком не классифицировалось как плохой размен.

Strategic Scorer имеет полные строки для всех 204 меню, но это полнота вычисления эвристики. Frozen совпадает с его лучшим действием/ничьей в 96/204 случаях (47.1%), Policy v3 — 95/204 (46.6%), Retrained v2 — 92/204 (45.1%), Control v3 — 102/204 (50.0%). Только в пяти меню отрыв первых двух оценок достигает трёх баллов. В выбранных расхождениях крупный отрыв может прямо зависеть от `UNREAD_EFFECT_ESTIMATE`; он не является доказательством ошибки сети. Параметры scorer не менялись.

Outcome Shadow тоже записал полные строки для 204 меню, но для хода игрока только 8 EXACT, 184 PARTIAL и 12 UNSUPPORTED. По всем 1721 действиям: 28 EXACT, 1593 PARTIAL, 100 UNSUPPORTED. `BOARD_TEXT_MISSING` встречается в 1482 прогнозах, `OWN_TEXT_MISSING` — в 525, `OWN_TEXT_UNPARSED` — в 301; признаки могут пересекаться. Среди unsupported: 52 `MINION_BODY_UNOBSERVED`, 44 `PLAY_WEAPON_NOT_MODELLED`. Механических флагов `SELF_HARM`/`SIDE_MISDIRECTION` в строгих журналах нет; при таком покрытии это не свидетельство безопасности ходов.

Главное установленное ограничение — способность независимо проверить рекомендацию, затем репрезентативность строго сопоставленных данных. Слабость сети, объём обучения и качество стратегической эвристики здесь нельзя разделить причинно. Ошибки построения legal menu не подтверждены: принятые меню сверены полностью, несовпадения исключены. Каталог, LIVE Policy, Model Shadow и обучение не менялись. Эти результаты не дают основания автоматически заменять Frozen v2.


## Проверки

- 24 целевых теста: успешно (EVAL-1, EVAL-2 и LIVE-join).
- Полный pytest в исходной рабочей папке: 1154 passed, 1 skipped, 1 failed. Единственное падение — существующая untracked-папка `vendor/RosettaStone`, которую задание запрещает трогать.
- Полный pytest в чистом `git archive 022e762` без посторонних файлов: **1148 passed, 2 skipped**. Исходники оценки и тесты с момента этого коммита не менялись; последующие изменения — отчёт.
- Ruff на отслеживаемом Python-коде и новых файлах: PASS; Ruff в чистой копии: PASS. Общий Ruff рабочей папки видит существующий untracked `src/manamind/outcome/decision_review.py` с неиспользуемым `Forecast`; файл не менялся.
- Offline regeneration pinned Standard: PASS, оба файла побайтно совпадают с committed outputs после нормализации CRLF. Нативный source guard CI: 310 baseline sites, 128 native rows, 0 problems.
- На Windows оба полных запуска печатают существующие native diagnostics `0xc0000008` в `_lower_thread_priority`; чистый набор при этом заканчивается с exit 0. Model Shadow не изменялся.
- Повторно проверены хеши источников, metadata, весов и состав выборки после inference; аудит публикации не нашёл состояний, меню, ID матчей/решений или индивидуальных логитов.

Текущая LIVE Policy, Collector, Overlay, ManaEngine, параметры scorer и checkpoint не менялись. Обучение эксперимента не запускалось. Старые отчёты и датасеты сохранены.
