# REAL-DATA-READINESS-1

## Результат

Конвейер готов собирать новые завершённые Ranked Standard матчи в непрерывном режиме. На локальных сохранённых Power.log live-сбор не запускался: текущую папку Hearthstone `Logs` нужно указать явно. Проведены проверки кода, тестов и существующего корпуса без записи в старые наборы.

В `collect_power_logs.py` добавлен `--state-file`. Он позволяет собирать независимый holdout в отдельных папках, сохраняя общий реестр идентичности матчей с обычным collector. Это не даёт обычному collector повторно обработать те же Power.log сессии при смене выходных директорий.

## Хранение и проверки

- Raw slices коллектора: `data/raw/collected/`; состояние и краткая сводка: `collector_state.json` и `collector_last_summary.json` там же. Все эти данные игнорируются Git.
- Policy observations обычного коллектора: `data/processed_policy_real/collected/`; Value observations: `data/processed_real/`.
- Результат `refresh_real_policy_dataset.py`: новая отдельная папка под `data/processed_policy_real/`. Refresh отказывается перезаписывать уже существующий `--output-dir` и не удаляет исходные raw logs.
- Importer записывает `game_id`, `decision_id`, источник Power.log и безопасную provenance без player names. Deduplication идёт по идентичности игры; повторная обработка существующего Policy output не создаёт вторую запись.

На имеющемся корпусе `refresh_obs1_final` проверка `audit_real_policy_dataset.py` прошла: 32 матча, 1 227 размеченных из 1 562 решений, 18 побед и 14 поражений, privacy checks PASS. Это проверка структуры/качества данных, а не независимая оценка Policy.

Тесты коллектора подтверждают разбиение многоматчевого лога, фильтрацию Ranked Standard, сохранение только после `STATE=COMPLETE`, retry незавершённой игры после роста файла или перезапуска, поведение при потере state и дедупликацию при ротации логов. Новая проверка подтверждает общий state между разными выходными папками. Известное ограничение: за один проход сканируется корень логов и только последние `--max-sessions` папок `Hearthstone_*` (по умолчанию 3); при накоплении большого числа сессий запускайте collector непрерывно или увеличьте это значение.

## Четыре `NOT_KNOWN_USED` матча

Все четыре исходных лога найдены в локальном `data/raw/collected/`, каждый содержит одну завершённую Ranked Standard игру. В `refresh_metadata.json` для каждого уже записано `status=REJECTED`, `reason=GAME_RESET`; Policy observations для них отсутствуют. Следовательно, причина не в потере raw-файлов: текущий Policy importer намеренно отклоняет эти логи. Их можно повторно проверить или использовать для диагностики отказа, но безопасно восстановить Policy labels существующим importer-ом нельзя; обходить `GAME_RESET` и вручную выдумывать решения нельзя.

| Локальный raw-файл | Начало `game_id` | Итог importer-а |
|---|---|---|
| `game14.log` | `1033453487d16ffe` | `REJECTED: GAME_RESET` |
| `game06.log` | `1d3b81b67b85c53b` | `REJECTED: GAME_RESET` |
| `game08.log` | `953e29b7d6a6aac0` | `REJECTED: GAME_RESET` |
| `game19.log` | `ac2c1dab52463e8d` | `REJECTED: GAME_RESET` |

## Holdout для следующих матчей

Назначайте holdout до refresh или любого обучения: запустите существующий collector с отдельными raw/processed output и общим `state-file`. Отдельная папка Policy observations становится фиксированным holdout corpus; обычный refresh читает только `data/raw/collected/` и поэтому не включает эти матчи. Не передавайте в refresh родительскую папку `data/raw/` и не объединяйте holdout-output с обычным корпусом. Refresh создаёт отдельный выход и не перезаписывает эти папки.

Запустите из корня репозитория. Подставьте фактическую папку Hearthstone `Logs`; collector не ищет её автоматически.

```powershell
$py = ".\.venv\Scripts\python.exe"
$logs = "<Hearthstone>\Logs"

& $py .\scripts\collect_power_logs.py `
  --logs-root $logs --poll-seconds 5 --max-sessions 20 `
  --raw-output .\data\raw\policy_holdout_1 `
  --state-file .\data\raw\collected\collector_state.json `
  --processed-output .\data\processed_real\policy_holdout_1 `
  --policy-output .\data\processed_policy_real\policy_holdout_1 `
  --evidence-output .\data\processed_evidence\policy_holdout_1
```

Остановите collector после 20–30 матчей, у которых в выводе есть положительное `Policy examples: N`. Незавершённые, не Ranked Standard или отклонённые Policy importer-ом игры в это число не входят. Затем проверьте отдельный корпус:

```powershell
& $py .\scripts\audit_real_policy_dataset.py `
  .\data\processed_policy_real\policy_holdout_1 `
  --cards .\data\cards\standard_current_enUS.json
```

Сравните `game_id` из `*.audit.json` holdout-папки со всеми ID текущего `experiment_usage_registry.json`; пересечение должно быть пустым. Реестр usage — производный аудит экспериментов, а не долговременный holdout ledger. Защита от повторного использования здесь обеспечивается отдельными raw/Policy путями и общим collector state. При следующих обычных сборах используйте тот же state-файл и обычные выходы. Переключайте collectors последовательно: никогда не запускайте два процесса одновременно с одним `--state-file`, поскольку конкурирующая запись полного snapshot может потерять новые ключи.

Обычный refresh создавайте в новой папке и направляйте только на обычные raw logs:

```powershell
& $py .\scripts\refresh_real_policy_dataset.py `
  --raw-dir .\data\raw\collected `
  --output-dir .\data\processed_policy_real\refresh_real_data_1
```

Эта команда не перезаписывает holdout. Не считайте исторические test splits независимыми новыми матчами; holdout оценивайте отдельно и один раз после фиксации Policy/checkpoint.

## Проверки этой ветки

- `tests/test_collect_power_logs.py`, `tests/test_policy_refresh.py`, `tests/test_real_policy_dataset.py`: 69 passed.
- Follow-up интеграционные проверки collector: 28 passed, включая последовательный переход `regular → holdout → regular` и запуск CLI без `--state-file`.
- Полный pytest после интеграции: 624 passed, 1 skipped.
- Существующий Policy corpus audit: PASS, 32 матча / 1 227 размеченных решений.
- Ruff: PASS; `scripts/check_generated_artifacts.py`: PASS, два pinned outputs воспроизведены; native source guard: PASS.
- Запрещено одновременно запускать два collector процесса с одним `--state-file`; переключайте их последовательно.
- GitHub Actions Ubuntu/Windows будут проверены после push integration-ветки.
- Обучение и изменения старых datasets/checkpoints не выполнялись.
