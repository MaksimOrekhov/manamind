# MODEL-FIRST-2 — First Tactical Learning

## Итог

**MODEL-FIRST-2: POSITIVE** в узком смысле критерия эксперимента: после двух идентичных обучений Policy v2 улучшилась на 300 synthetic test позициях из трёх полностью отложенных семейств; повтор дал побитово одинаковые веса. Это доказательство переноса описанного локального правила обычного боя на новые комбинации, а не доказательство игровой силы или готовности для live.

Гипотеза до обучения: fine-tuning существующей Policy v2 на арифметически размеченных разменах и гарантированном летале улучшит ранжирование на новых board sizes, stat ranges, семействах шаблонов и card ID. Исходный checkpoint и фиксированный MODEL-FIRST-1 контроль остались вне обучения. Validation использовался для выбора эпохи; Synthetic Test открывался после сохранения выбранного checkpoint.

Процедурное отклонение: до обучения был сделан baseline-only preflight существующим MODEL-FIRST-1 runner на frozen control. Runner вычислил показатели в памяти, затем завершился ошибкой создания отчёта в закрытом `.codex` каталоге. Результат не был выведен или сохранён и не использовался для выбора данных, параметров, эпохи либо checkpoint. Сравнение обоих checkpoints, приведённое ниже, выполнено после выбора модели. Это раннее открытие control отмечено явно; выводы основаны на сохранённой пост-селекционной оценке.

## Данные и gold labels

Генератор `scripts/generate_model_first_2.py` создал 1 800 корректных по схеме GameState сценариев:

| Split | Сценариев | Семейств | Шаблонов | Назначение |
|---|---:|---:|---:|---|
| Train | 1 200 | 6 | 6 | 1–2 атакующих, обычные размены, Taunt и face lethal |
| Validation | 300 | 3 | 3 | новые семейства, ранний останов/выбор эпохи |
| Synthetic Test | 300 | 3 | 3 | 1–3 атакующих, до четырёх целей, новые диапазоны характеристик и неизвестные ID |

Split и шаблоны назначены до обучения. Между split нет пересечений family/template ID или одинаковых точных state + semantic legal menu; MODEL-FIRST-1 boundary проверяется для train и validation. Все 300 тестовых сценариев используют незнакомые `MF2_HELDOUT_*` card ID, которых нет в обучающем vocabulary. Существующий unknown-ID путь encoder не изменялся. Семейства теста — `heldout_wide_board_trade`, `heldout_three_attacker_lethal`, `heldout_unknown_id_trade`.

SHA-256 исходных данных для воспроизведения: `train.jsonl` `3813d61fc51c6bea37b56d2eeea6dbded15ac25f702ea4183435fc09372b6e2e`; `validation.jsonl` `1ad331d5c979a5003171aafe7d833f412e44eb68f5e009b580fca8e52e3f19e0`; `test.jsonl` `cdb7eb4035211b4311d99c12ccf3257ec8eab4ac3dc315771d06153f5366830`; `provenance.jsonl` `ff8e6ba38aa9fbb0b3e47947dd3d5f8dcf3c92349eee2ddaaddb671e884d5605`; `manifest.json` `ab4d3baf104aaaf0431606029f1b0aab6a420ac6878b758046ae409d9f222570`.

Независимые gold labels получены прямой целочисленной арифметикой боя: атака в лицо размечается, когда сумма доступных атак гарантирует летал; атака по существу — когда цель погибает, а атакующий выживает. Для Taunt меню содержит только видимые легальные Taunt-цели; такие примеры размечены лишь при доказуемом выгодном размене. Примеры без доказуемого локального результата отвергаются генератором, а не получают угаданную метку. Предсказания Policy и эвристики не используются. Это локальная тактическая разметка, не оценка полной стратегической оптимальности.

У каждой записи есть отдельный provenance с seed, split, family/template ID, генератором и fingerprint. Датасет и provenance хранятся в игнорируемом `data/processed_synthetic/model_first_2/`; в Git они не добавлены.

## Обучение

Использован существующий checkpoint Policy v2, без изменений архитектуры, encoder, vocabulary или исходных весов:

- Исходный SHA-256: `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`.
- Runs: два идентичных повтора, seed `42`, RTX 5080 (`torch 2.14.0+cu130`), AdamW, learning rate `0.0001`, batch `32`, максимум `16` эпох, patience `4`. Второй запуск проверял воспроизводимость; конфигурация по Synthetic Test не подбиралась.
- Loss: set-marginal cross-entropy, суммирующая вероятности всех gold-действий и поддерживающая несколько верных действий.
- Run 1: `47.54 s`; Run 2: `46.04 s`. В обоих выбрана эпоха `16` по минимальному validation loss `0.03212` (исходный validation loss `0.43505`); Train/Validation истории совпали.
- Валидационный top-1 был `100%` до обучения и `99.33%` на выбранной эпохе. Поэтому обучение не показало прироста на validation top-1; Test не использовался для настройки.
- Checkpoint: игнорируемый `data/processed_policy_ml2b/model_first_2_seed42/policy.pt`, SHA-256 `32b4314288c64473c54aafb3b731db910bd5c03b06c9615d9545b11511a19bd0`.
- Повторный checkpoint: игнорируемый `data/processed_policy_ml2b/model_first_2_seed42_repeat/policy.pt`, SHA-256 `1b5945cbb96025b3dc79d03a333bda86a809e8ee01cfcac7a7f014812b77f1f4`. Метаданные содержат время запуска, поэтому файлы имеют разные SHA; все тензоры `policy_state_dict` при повторе побитово совпали.
- Checkpoint загружен штатным `load_policy_checkpoint`; сохранённые logits совпали после round-trip.

| Run | Время | Эпоха | Validation loss / Top-1 | SHA-256 checkpoint | Веса совпали с Run 1 |
|---|---:|---:|---:|---|---|
| 1 (выбранный) | 47.54 s | 16 | 0.03212 / 99.33% | `32b4314288c64473c54aafb3b731db910bd5c03b06c9615d9545b11511a19bd0` | reference |
| 2 (точный повтор) | 46.04 s | 16 | 0.03212 / 99.33% | `1b5945cbb96025b3dc79d03a333bda86a809e8ee01cfcac7a7f014812b77f1f4` | да |

Повторно обучать не требуется для проверки артефактов. Выходной каталог не перезаписывается; для нового локального запуска укажите новый `--output`.

## Evaluation

Все четыре ranker сравнивались на одних и тех же сценариях. Top-1, Top-3 и MRR считают ближайшее из нескольких допустимых gold-действий. У эвристики отдельно указана применимость. Random — ожидаемые метрики при равномерной перестановке legal menu. Время измерено существующим runner на CPU, один повтор, поэтому сравнение latency ориентировочное.

| Split / контроль | Labeled | Baseline v2 Top-1 | Fine-tuned v2 Top-1 | Эвристика Top-1 | Random Top-1 | Fine-tuned Top-3 / MRR |
|---|---:|---:|---:|---:|---:|---:|
| Train | 1 200 | 98.92% | 99.00% | 100% (1 200 применимых) | 48.17% | 100% / 0.9950 |
| Validation | 300 | 100% | 99.33% | 100% (300 применимых) | 55.91% | 100% / 0.9967 |
| Held-out Synthetic Test | 300 | 0% | **97.67%** | **100% (300 применимых)** | 48.88% | **100% / 0.9883** |
| Frozen MODEL-FIRST-1 | 11 из 13; 2 ambiguous исключены | 90.91% | 100% | 100% (11 применимых) | 35.45% | 100% / 1.0000 |

На Synthetic Test по категориям: lethal — fine-tuned `100/100`, baseline `0/100`; target selection — fine-tuned `193/200` (96.5%), baseline `0/200`. Все 300 test-сценариев одновременно являются проверкой новых card ID, так как все используют идентификаторы `MF2_HELDOUT_*`; их метрики совпадают с общей строкой Synthetic Test.

В примере `mf2_test_heldout_wide_board_trade_0000` baseline поставил `END_TURN` выше выгодных атак и получил rank 2 для ближайшего gold-действия; обученная Policy поставила выгодную атаку на первое место. В `mf2_test_heldout_wide_board_trade_0005` fine-tuned модель поставила на первое место размен, в котором атакующий погибает, а правильное выживающее действие осталось на rank 2. Всего таких ошибок target selection — 7; все gold-действия остаются в Top-3. На frozen контроле не обнаружено ухудшения: fine-tuned `11/11` против baseline `10/11`; выбор по этим контрольным данным не выполнялся.

CPU inference на Synthetic Test (state decode + encoding + forward): baseline `1.45 ms` mean, fine-tuned `1.43 ms`; только forward `0.224` и `0.225 ms` соответственно. Это малая синтетическая выборка с одним повтором.

## Выводы и ограничения

1. Сеть усвоила и перенесла локальное правило выгодного размена/летала: test top-1 вырос с `0%` до `97.67%` на трёх отложенных семействах.
2. Новые card ID обрабатываются через прежний unknown-ID путь: на этих 300 случаях fine-tuned top-1 `97.67%`.
3. Исходная Policy v2 на этом конкретном сдвиге распределения не ранжировала gold-действие первым. Fine-tuned Policy почти достигла ограниченную эвристику, но отстала от неё на 2.33 процентного пункта.
4. Validation top-1 уменьшился на 0.67 п.п.; frozen контроль мал (`11` labeled) и не заменяет независимую проверку реальных матчей. Дополнительная реальная регрессия не запускалась.
5. Один фиксированный seed и процедурные метки не устанавливают статистическую устойчивость, стратегическую оптимальность или пользу в настоящих партиях. Test покрывает только заданную арифметику боя.

Результат поддерживает продолжение контролируемых тактических экспериментов; переход к Text Policy остаётся отдельным сравнительным этапом и этим запуском не проверялся. Checkpoint экспериментальный, в live не продвигается. MODEL-FIRST-3 и merge не выполнялись.

## Воспроизведение

Из корня репозитория, с проектным `.venv`:

```powershell
python scripts/generate_model_first_2.py --output data/processed_synthetic/model_first_2
python scripts/check_model_first_1_training_boundary.py data/processed_synthetic/model_first_2/train.jsonl
python scripts/check_model_first_1_training_boundary.py data/processed_synthetic/model_first_2/validation.jsonl
python scripts/train_model_first_2.py `
  --train data/processed_synthetic/model_first_2/train.jsonl `
  --validation data/processed_synthetic/model_first_2/validation.jsonl `
  --baseline data/processed_policy_ml2a/seed42_v2/policy.pt `
  --output data/processed_policy_ml2b/model_first_2_seed42 `
  --device cuda --epochs 16
python scripts/evaluate_model_first_2.py `
  --baseline data/processed_policy_ml2a/seed42_v2/policy.pt `
  --trained data/processed_policy_ml2b/model_first_2_seed42/policy.pt `
  --repeats 1 --output reports/model_first_2/results.json
```

Последняя команда повторно оценивает frozen control вместе с выбранным checkpoint. Synthetic Test открывается только после checkpoint selection. Для нового полного обучения используйте новый output path; текущий отчёт зафиксирован в `results.json`.

## Тесты

- `python -m pytest tests/test_model_first_2.py -q` — 4 passed.
- `python -m ruff check scripts/generate_model_first_2.py scripts/train_model_first_2.py scripts/evaluate_model_first_2.py tests/test_model_first_2.py` — passed.
- В `tests/test_model_first_2.py` проверяются schema/legal menu, происхождение/разделение, семантический точный overlap при переименованных ID и переставленном меню, контрольные границы, gold-арифметика и короткий training/checkpoint round-trip.
- Новых workflow нет. CI pytest содержит только двухэпоховый CPU smoke-test на крошечном временном fixture для проверки training/checkpoint цикла; основной эксперимент на 1 200 сценариях автоматически не запускается.
