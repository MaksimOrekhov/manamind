# Отдельный LIVE holdout-сбор

`--holdout` включает holdout-режим в том же `run_manamind.py --ui`: второй процесс
Collector не запускается. Перед первым сбором остановите обычный ManaMind runtime,
завершите текущую игру и закройте Hearthstone. Запустите ManaMind из корня репозитория:

```powershell
.\.venv\Scripts\python.exe scripts/run_manamind.py --ui --holdout `
  --logs-root "D:\Games\Hearthstone\Logs"
```

Затем откройте Hearthstone и играйте. Закройте панель `Ctrl+C` в консоли; итог покажет
число новых завершённых матчей, число Policy-матчей/решений и пересечение с историей.
Повторный запуск той же команды продолжит этот holdout. Обычный запуск без `--holdout`
по-прежнему пишет в обычные каталоги.

Подготовка происходит до запуска Collector. Она читает обычные
`data/raw/collected/collector_state.json` и raw-логи, сканирует уже существующие
`Power*.log`, все локальные Policy datasets/usage registries и match-level splits
двух frozen checkpoint. Их game_id записываются в новый holdout state как
`SKIPPED_ALREADY_IMPORTED`; встроенный Collector применяет свой обычный механизм
дедупликации и будет сохранять только последующие игры. В частности, raw ID, которых
не было в обычном state (ранее их было 18: 61 raw против 43 учтённых), также попадут
в блок-лист.

Обычный state и raw-файлы только читаются. В новой папке
`data/raw/holdout_checkpoint_2/` создаётся байтовая резервная копия state; SHA-256
сверяется до и после подготовки. Holdout state и manifest ведутся отдельно.
При изменённом state/raw, отсутствующей истории/checkpoint, повреждённой копии,
неоднозначном raw или пересечении Policy examples запуск прекращается до обычного
сбора. Не удаляйте и не переименовывайте эту папку при возобновлении: она содержит
состояние дедупликации и исходную границу holdout.

Holdout raw, Policy examples, Value examples, mechanic observations, LIVE recordings
и journal хранятся под `data/raw/holdout_checkpoint_2/`. Этот путь игнорируется Git.
Команда не обучает и не выбирает checkpoint. Сохраняйте holdout нетронутым до
согласования независимого сравнения; LIVE-рекомендации могут влиять на выбор игрока,
поэтому метрика совпадения остаётся метрикой имитации.
