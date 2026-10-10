# LIVE-MVP-1 — First Playable Prototype

## Статус

**TECHNICALLY READY — PLAYTEST NOT VERIFIED.** MVP запускает одну Windows Tkinter-панель поверх существующего `UnifiedRuntime`. До первой проверки пользователем с реальным клиентом Hearthstone утверждать, что панель корректно отображается во время игры, нельзя.

Основа: `origin/main` `74524b24454d9455e3f6efab7840bd8d3494539d`; ветка `codex/live-mvp-1`.

## Запуск

Один раз установить зависимости из корня репозитория, затем запускать приложение одной командой:

```powershell
python -m pip install -e ".[dev,replays]"
python scripts/run_manamind.py --ui
```

`--ui` создаёт always-on-top окно Tkinter и запускает в том же процессе один Power.log reader, один LIVE runner и существующий collector. По умолчанию читается `D:\Games\Hearthstone\Logs`; другой путь можно передать `--logs-root "<путь>"` или задать `MANAMIND_HEARTHSTONE_LOGS`. Закрытие панели останавливает runtime; также работает Ctrl+C в консоли. Панель рассчитана на оконный/borderless режим, не на эксклюзивный fullscreen.

Для проверки без игры статус должен перейти в `DISCONNECTED`/`WAITING_FOR_GAME`, а рекомендации остаются скрыты. На trusted SELF snapshot показываются ход и первые три legal action по logits Policy v2. Окно показывает ранг, не score и не вероятность победы. Неизвестное имя заменяется на card_id с типом/позицией действия. Имена берутся из текущего локального Standard JSON; inference catalog, encoder и checkpoint vocabulary не меняются.

## Checkpoint и LIVE границы

Файл `data/processed_policy_ml2a/seed42_v2/policy.pt` проверен локально: SHA-256 `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`. Существующий loader прочитал schema `manamind.real_policy/2`; на READY SELF fixture с полным меню из 4 legal вариантов вернул top-3. Затем тот же checkpoint был запущен через `UnifiedRuntime`: он получил один READY decision, показал top-3, записал журнал и вызвал тот же collector один раз. Схема, веса и checkpoint не менялись, обучение не запускалось.

Политика вызывается только существующим `PolicyRecommender`: READY, settled SELF, Ranked Standard, приватный player-visible state, полное menu и точные соответствия catalog/checkpoint. При `SYNCING`, `UNTRUSTED`, `DISCONNECTED`, чужом ходе, GAME_OVER или ошибке menu подсказка скрывается/недоступна с причиной. Новые строки Power.log проверяются после inference перед показом. Приложение не кликает и не отправляет игровых действий.

## Журнал и сбор

Существующий collector продолжает работу в том же `UnifiedRuntime`; отдельный collector не создаётся. Новые завершённые матчи остаются в существующих git-ignored raw/processed каталогах. Raw Power.log может содержать личные данные и остаётся локальным.

Панель записывает рекомендации и инвалидации в `data/raw/live/prediction_journal.jsonl` (путь покрыт правилом `data/raw/` в `.gitignore`). Запись рекомендации содержит `match_id` (game key), `decision_id` (game key/seq/options/state hash), `state_hash`, SHA checkpoint, top-3 action descriptors и время UTC. Запись инвалидации ссылается на ту же пару match/decision и содержит причину и время UTC. В сериализуемом действии есть только поля уже проверенного legal menu; имён игроков и скрытых карт противника нет.

Фактическое действие игрока в текущей версии **не сопоставляется автоматически**: статус остаётся `UNKNOWN`. UI не выводит его из соседних лог-событий, если тождество решения не доказано. Журнал не является обучающим корпусом, а сами рекомендации автоматически не импортируются в dataset. При завершении матча существующий collector сохраняет raw log; записи рекомендаций остаются в том же локальном журнале.

## Проверки

- Реальная локальная Policy v2: SHA проверен; loader/schema/catalog проверки прошли; scoring на synthetic READY fixture — 4 legal-варианта, top-3.
- LIVE integration: fixtures проверяют старт без игры, появление READY, немедленную инвалидацию, GAME_OVER, повторный запуск collector без дублей и privacy canaries.
- Новый panel/journal path: names/fallback/positions, скрытие устаревшей рекомендации и `UNKNOWN` для неподтверждённого действия.
- `tests/test_live_recommendation.py`: 46 passed; повторный live-only запуск test block — 46 passed.
- Полный локальный pytest: 624 passed, 1 skipped, 2 сбоя только из-за посторонних незатреканных `vendor/RosettaStone` и stale `src/manamind.egg-info/SOURCES.txt`; эти артефакты не менялись. Чистые CI runners не содержат их.
- Ruff (`src tests scripts`), source guard и генерация pinned artifacts прошли.
- Source CI на Ubuntu/Windows прошёл полностью на реализации `df43ecb` ([run](https://github.com/MaksimOrekhov/manamind/actions/runs/38042826035)); обе ОС выполнили Ruff, source guard, pinned artifact check и полный pytest успешно.

Это не тест реального Hearthstone UI: он требует проверки пользователем на его Windows машине и в партии. После запуска сообщите только дату партии и число просмотренных решений; не присылайте unsanitized raw log.

## Ограничения первой версии

- Только settled `MAIN_ACTION` в доверенном SELF ходе; mulligan/Discover и выборы не поддержаны.
- При отсутствии или несовпадении локального checkpoint/catalog Policy отключается, collection продолжает retry.
- Tkinter panel рассчитана на окно поверх игры в windowed/borderless; поведение при эксклюзивном fullscreen не обещается.
- Реальное использование в клиенте, задержка обновления поверх игрового окна, послеигровое завершение и повторный запуск ещё ждут пользовательского playtest.
