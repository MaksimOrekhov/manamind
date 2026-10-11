# ManaMind LIVE overlay

Vue 3 + TypeScript, внутри опционального Python-хоста pywebview 6.2.1 / WebView2.
Перенесены build-файлы и визуальная основа `work/ui-overlay-shell`; старые mock-данные,
EXACT/INFERRED, вероятности победы и контракт симулятора не используются.

## Запуск Windows

Нужны существующая Python 3.12+ venv с ManaMind и `hslog`, Node.js / pnpm,
установленный [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).
Rust, CMake и отдельная venv не нужны. Один раз в существующей venv:

```powershell
python -m pip install -e ".[overlay]"
```

Из корня репозитория:

```powershell
.\scripts\start_overlay.ps1
```

Скрипт собирает отсутствующий UI, затем запускает **один Python-процесс** с существующим
LIVE и collector. `-Build` пересобирает UI. Зависимости UI закреплены `pnpm-lock.yaml`.
При работе в worktree можно явно использовать исходные локальные ресурсы:

```powershell
.\scripts\start_overlay.ps1 -Python E:\ManaMind\.venv\Scripts\python.exe `
  -Checkpoint E:\ManaMind\data\processed_policy_ml2a\seed42_v2\policy.pt `
  -DataRoot E:\ManaMind\data -LogsRoot D:\Games\Hearthstone\Logs
```

Checkpoint сверяется с существующим frozen Policy v2 SHA-256; его нет в Git.
Без него окно показывает недоступность рекомендаций, collector продолжает работу.
Для уже собранного UI достаточно `python scripts/run_manamind.py --overlay`.
Консольный запуск и прежний Tkinter `--ui` сохранены; `--ui` и `--overlay` взаимоисключающие.

## Использование

- Перетаскивание за заголовок **ManaMind**; окно поверх остальных, без рамки.
- `−` сворачивает до заголовка, `＋` возвращает панель; `×` завершает приложение.
- RU/EN меняет инструкции и имена; slider регулирует непрозрачность всего окна (55–100%).
- Положение, размер, язык, прозрачность и сворачивание сохраняются в
  `<data-root>/raw/overlay_preferences.json`; игровые данные там не сохраняются.
- Размеры в логических пикселях; WebView2/WinForms обрабатывает DPI.
  После изменения разрешения сохранённое окно возвращается в границы доступного монитора.
- Слева направо на **экране игрока**, отдельно для каждой стороны и руки.
  Существа и локации считаются в общем ряду; подпись прямо напоминает об этом.
  Между N-й и N+1-й **картами на столе** учитывает локации.
- Если позиция отсутствует, порядок неполон или не совпала карта, координата скрывается
  и выводится предупреждение. Самостоятельно выбирать между неразличимыми копиями нельзя.
- В «Деталях» доступны поля действия и logit, явно обозначенный как оценка ранжирования,
  не вероятность победы. Основные блоки показывают действие, источник и цель.

## Архитектура и безопасность

`UnifiedRuntime → PresentationEvent → OverlayFeed → pywebview.api.get_frame() → Vue`.
LIVE остаётся единственным источником состояния и ранжирования. Callback использует
реальный `Recommendation` и соответствующий `Snapshot`, без разбора консольных строк.
DTO `manamind.overlay/1` содержит только выбранные публичные действия, RU/EN подписи,
номер хода, время, статус и ревизию. В нём нет полного состояния, игровой идентичности,
действий по entity handle, логов, игроковых имён или скрытых карт противника.

Vite JS/CSS встроены в локальный HTML. HTTP/WS сервер **не создаётся**; внешнего API
нет, CSP запрещает сетевые соединения. Только три внутренних метода моста:
`get_frame`, `set_preferences`, `close`; настройки не могут менять пути/Policy/игровые действия.
Локальный словарь имён не входит в модель и не меняет vocabulary / Standard catalog.

Каждый статус/новое решение/инвалидация очищает прежний Top-3. Результат привязан к тому же
снимку и меню. Нет очереди старых событий. После перезагрузки UI читает текущее состояние,
новый Python-процесс имеет новую session. Задержанный ответ после timeout отбрасывается.
При недоступности моста или остановке polling >2 с подсказка скрывается; для восстановления
после остановки polling нужен новый подтверждённый результат. Длительный collector scan
может вызвать такое безопасное скрытие. Закрытие ждёт завершения текущей записи collector.

## Проверки

```powershell
cd apps/overlay-ui
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm test
pnpm run build
```

Python-тесты: `python -m pytest tests/test_overlay_presentation.py tests/test_live_recommendation.py`.
Replay использует существующий replay/scorer и проверяет точное сохранение действий/logits:

```powershell
python scripts/replay_overlay.py E:\ManaMind\data\raw\live `
  --checkpoint E:\ManaMind\data\processed_policy_ml2a\seed42_v2\policy.pt `
  --output data\processed_overlay_smoke\replay.json
python scripts/smoke_overlay_window.py --output data\processed_overlay_smoke\window.json
```

Второй скрипт кратко открывает и закрывает только собственное окно; это отдельная
опциональная Windows-проверка, не headless CI и не проверка реальной игры.
Итоги и ручной checklist: [отчёт LIVE-OVERLAY-1](../../reports/live_overlay_1/README.md).
