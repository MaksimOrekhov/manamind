# LIVE-OVERLAY-1 — Windows-оверлей и понятные RU/EN инструкции

**Результат: TECHNICALLY READY FOR HEARTHSTONE PLAYTEST.** Реальный Windows/WebView2-хост
и полный UnifiedRuntime проверены автоматическим запуском собственного окна.
Подтверждения на экране живого Hearthstone в этой задаче нет: DPI нескольких мониторов,
перетаскивание рядом с игрой и фактическое соответствие координат остаются ручным checklist.
Это не подтверждение качества игровых рекомендаций frozen Policy v2.

Основное задание и высокоприоритетное дополнение реализованы вместе, в
`codex/live-overlay-1` от `main` **0fe53dceee83898641c390f430f15c89e3d26766**.
Ветка старого UI целиком не объединялась. Из `work/ui-overlay-shell` взяты сборочные
файлы, Vue entry point и палитра; прежние mock-контракты/вероятности/EXACT/INFERRED заменены.

## Что готово

- Vue 3 внутри Python pywebview 6.2.1 / Windows WebView2, без Rust/CMake и второго LIVE.
- Окно поверх остальных, без рамки; перенос за заголовок, сворачивание до 56 px,
  восстановление, размер, непрозрачность 55–100%, сохранение настроек.
- Возврат сохранённого окна в видимые границы при изменении разрешения; логические
  пиксели и DPI-механизм WinForms/WebView2. Эксклюзивный fullscreen не обещается.
- Top-1 крупнее, Top-2/3 компактнее; **действие → источник → цель**,
  размещение отдельной строкой. Ни один вариант не переставляется и не заменяется.
- RU/EN: официальные имена, стороны, текущие характеристики, места в руке/на столе.
  Entity/action IDs и числовая оценка только в раскрывающихся деталях; fallback ID допустим,
  когда имени нет. Logit явно подписан как рейтинг, не вероятность победы.
- Цель `PLAY_CARD` исправлена и в прежнем `panel.describe_action()`.
- Атаки героем, одинаковые карты, силы героев, локации, целевые розыгрыши и размещение.
- DISCONNECTED / WAITING_FOR_GAME / SYNCING / THINKING / UNTRUSTED / GAME_OVER /
  UNAVAILABLE; checkpoint error сохраняется видимым и при потере журнала.
- Закрытие завершает polling и текущую запись collector; отдельных серверных процессов нет.
  Прежние console и Tkinter `--ui` сохранены.

Не менялись модель, checkpoint, StateEncoder, vocabulary, закреплённый English Standard
каталог, rules/легальность и trust/privacy gates LIVE. Добавлены только presentation callbacks.
Нет обучения, новых матчей, расширения ManaEngine, L1/L2/L3, анализа текста консоли или
объяснений эффектов/разменов, которые Policy не вычисляет.

## Запуск

Полная инструкция: [apps/overlay-ui/README.md](../../apps/overlay-ui/README.md).
Один раз установить опциональный хост в **существующую** venv:

```powershell
python -m pip install -e ".[overlay]"
```

Запуск из корня этой ветки, с сохранёнными исходными локальными ресурсами:

```powershell
.\scripts\start_overlay.ps1 -Python E:\ManaMind\.venv\Scripts\python.exe `
  -Checkpoint E:\ManaMind\data\processed_policy_ml2a\seed42_v2\policy.pt `
  -DataRoot E:\ManaMind\data -LogsRoot D:\Games\Hearthstone\Logs
```

Node/pnpm нужны для первоначальной сборки; WebView2 Runtime — для окна.
При наличии build: `python scripts/run_manamind.py --overlay`. Ошибка или отсутствие
checkpoint отключает рекомендации, оставляя существующий collector активным.

## Состояние, транспорт и инвалидация

`UnifiedRuntime → PresentationEvent → OverlayFeed → внутренний JS/Python bridge → Vue`.
`Recommendation` и соответствующий `Snapshot` передаются структурированно. PolicyRecommender
сохраняет прежний score/menu/visibility contract и повторно читает LIVE после inference.

DTO `manamind.overlay/1` содержит выбранные actions, исходные logits, два варианта подписи,
статус, ход, время, session/revision и доступность Policy. Нет полного GameState,
game key/options ID/entity handles, имён игроков, сырых строк или скрытых зон противника.
Reason codes проходят allowlist. UI API не позволяет менять checkpoint/пути или играть.
Готовый JS/CSS встроен в HTML: не стартует даже статический HTTP-сервер, нет WS/внешнего API.
В runtime CSP запрещает сетевые соединения. Reload читает только актуальное состояние,
истории рекомендаций нет. Новая session обнуляет старую; меньшая revision отвергается.

Status, invalidation, новый расчёт, inference failure и GAME_OVER очищают Top-3 до нового
результата. Задержанный ответ после timeout не возвращает старую подсказку.
Если polling или bridge молчит >2 секунд, UI скрывает совет. Длительный синхронный collector
scan может вызвать безопасное скрытие до нового результата; журнал при этом не повреждается.

## Имена и позиции

Отдельный display snapshot [card_names_253932.json](../../data/localization/card_names_253932.json)
содержит **36 022 ID**: полные client definitions, включая токены, силы героев и локации.
Источник — [HearthstoneJSON](https://hearthstonejson.com/), строки официальной локализации
клиента, build **253932**, полный `cards.json` ruRU/enUS. Не перевод LLM и не второй
интерпретатор карт. RU → EN → ID; EN → ID. Source URL/hash сохранены внутри файла.

| Закреплённый вход | SHA-256 |
|---|---|
| ruRU/cards.json | `96ca61b1c658d3fd6311a4413a6384f4e91a9e348478ffd0e223816d741425a7` |
| enUS/cards.json | `e8ea569a7ca1790c2258ed57c60798d808ffb057acb7bb73663c00ea174dae65` |
| Готовый словарь | `bb8a9b4334e6f4c83a937a951884529f846e561f92bfb1f81d83940f85cda7fa` |

`scripts/build_card_names.py` воспроизводит байты из двух проверенных входов; hash двух
построений совпал. В Git сохранён только нужный словарь, полные 10/13 MB sources — не дублируются.
Актуальный Standard catalog и его source SHA-256 не изменились.

Контракт координат:

| Поле | Проверка / отображение |
|---|---|
| `hand_index` | LIVE `visible_state(hand_order="zone_position")`; mapper сверяет SELF `ZONE_POSITION − 1` с индексом/ID. UI требует полную руку и совпадение ID; показывает index+1 слева. |
| `board_position` | Публичный `ZONE_POSITION`; источник/цель сопоставляется по **side + kind + position**, не только card_id. |
| `source_board_position` / `target_board_position` | UI сверяет ID с ровно тем слотом стороны в том же snapshot. Общий ряд minions+Locations должен иметь уникальные непрерывные позиции. |
| `play_position` | One-based insertion slot; 1 — слева, count+1 — справа, иначе между position−1 и position. Учитывает локации. |
| Отсутствие/конфликт | Никакой придуманной «N-е слева»: координата не подтверждена, видимое предупреждение. |

Направление проверено по первичной реализации экранного оверлея HearthSim/HDT на commit
**3e4ba05d6880c054be6beb7f9dac4f190ad1c2ba**:
[сортировка обеих сторон по ZONE_POSITION](https://github.com/HearthSim/Hearthstone-Deck-Tracker/blob/3e4ba05d6880c054be6beb7f9dac4f190ad1c2ba/Hearthstone%20Deck%20Tracker/Windows/OverlayWindow.Update.cs#L167),
[горизонтальные панели обеих сторон](https://github.com/HearthSim/Hearthstone-Deck-Tracker/blob/3e4ba05d6880c054be6beb7f9dac4f190ad1c2ba/Hearthstone%20Deck%20Tracker/Windows/OverlayWindow.xaml#L304),
[возрастание X с индексом SELF hand](https://github.com/HearthSim/Hearthstone-Deck-Tracker/blob/3e4ba05d6880c054be6beb7f9dac4f190ad1c2ba/Hearthstone%20Deck%20Tracker/Windows/OverlayWindow.MouseOverDetection.cs#L386).
Противник не зеркалится. Это проверка кода и записей, а не проведённое в этой задаче
сравнение с кадром текущего Hearthstone; последнее явно остаётся ручной проверкой.

## Replay и конкретные примеры

Frozen v2 SHA-256 `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`.
Использованы **31 уже существующая LIVE-запись**, без новых матчей и копирования датасетов.
Проверены **1 870 рейтингов / 5 264 показанных варианта**; каждый DTO action/logit в том же
порядке точно равен результату scorer на том же состоянии. Отдельно проверено очищение feed.

| Тип | Показанные варианты (Top-3, не частота Top-1) |
|---|---:|
| PLAY_CARD | 2 587 |
| ATTACK | 788 |
| HERO_POWER | 764 |
| ACTIVATE_LOCATION | 353 |
| END_TURN | 772 |

1 556 вариантов с целью; 6 048 именованных источников/целей, **0 без ruRU имени**;
0 координат, отклонённых проверкой консистентности. Это покрытие записанных рекомендаций,
не обещание полной поддержки будущих карт или correctness всех позиций на живом экране.
Сводка и агрегатные SHA-256 входных файлов: [replay.json](replay.json).

Примеры **фактически показанных вариантов**, без утверждения об оптимальности:

- **АТАКОВАТЬ** → своё существо **Телепатка · 1/2 · 1-е слева** → существо противника
  **Пухокрылка-страж · 4/4 · 1-е слева**.
- **РАЗЫГРАТЬ** → **Ткач круговорота · 10-я карта слева** → противник
  **Хроми · 4/6 · 2-е слева**; размещение справа от своих карт.
- **АТАКОВАТЬ** → **твой герой · 1/30** → **Вероломный мучитель · 5/8 · 6-е слева** противника.
- **АКТИВИРОВАТЬ ЛОКАЦИЮ** → **Кровавые катакомбы · 3 прочности · 1-е слева** → своё
  существо **Главный канонир · 3/1 · 2-е слева**.

Контролируемые примеры дополнительно покрывают два одинаковых существа с разными текущими
статами, локацию между ними, 4-ю карту в руке, placement между 2-й/3-й картами, обе стороны,
герой/сила героя/локация как источник, герой/существо/локация как цель, неизвестный ID,
неполную руку и конфликтующие позиции. При неизвестной координате тест требует предупреждение.

**Ограничение исторических данных:** 17/31 записей воспроизвели сохранённую последовательность
`state_hash`; 14/31 не воспроизвели её. Документированный drift старых observation-полей может
объяснять это, но причины всех 14 здесь не расследованы. Они использованы только для проверки
нового отображения **заново построенных текущим LIVE** состояний; не включаются в утверждение
об идентичности исторического replay. Исходные записи и сохранённые hashes не менялись.
Существующий scorer также отказался оценивать неоднозначные/неподдержанные меню
(`AMBIGUOUS_SELECTION`, `CHOICE_UNRESOLVED`, `TARGET_UNRESOLVED`); UI не обходил эти отказы.

## Проверки и оставшиеся ограничения

| Проверка | Результат |
|---|---|
| Full pytest | 653 passed, 1 skipped |
| Ruff | PASS |
| Offline Standard regeneration | 2 pinned outputs reproduced; model catalog clean |
| Vue typecheck / tests / build | PASS; 11 тестов; production bundle ≈75 KB до gzip |
| Windows host | [window_smoke.json](window_smoke.json): Vue mounted, RU/EN, TopMost, FormBorderStyle=None, opacity=.65, 56→640 px, GAME_OVER hides advice, no HTTP server |
| UnifiedRuntime с frozen checkpoint / без файла | [runtime_smoke.json](runtime_smoke.json): оба окна закрылись, return code 0, **0 оставшихся LIVE threads** |

Windows smoke управляет только собственным тестовым окном. Он не проверяет Hearthstone,
мышь игры, перетаскивание или фактическую разницу 100%/150% DPI на разных мониторах.
Click-through в этой версии не реализован: рекомендуем компактный режим и размещение
в свободной области. Exclusive fullscreen может перекрывать обычное topmost окно;
приоритет — windowed/borderless. Новые карты вне snapshot используют EN/ID fallback.
Нет поддержки Discover/mulligan/неподдержанных LIVE powers за пределами существующего MAIN_ACTION.

Ручной checklist перед статусом PLAYTEST VERIFIED:

1. Открыть Hearthstone windowed/borderless и эту панель; проверить topmost, перенос,
   сворачивание/восстановление, прозрачность, закрытие и сохранение положения.
2. При 100%/150% DPI, изменении разрешения/монитора проверить доступность всех controls.
3. Сопоставить несколько рук, обе половины стола, две одинаковые копии, локацию в общем ряду
   и размещение между соседями. Проверить номер **слева на экране игрока** для source и target.
4. Проверить RU/EN, целевой `PLAY_CARD`, героя и силу героя; технические поля только в details.
5. После действия/нового решения/потери trust/завершения матча не должно оставаться прежнего
   Top-3; переподключение не должно восстанавливать старое событие.

## Git и локальные данные

Работа предназначена для ревью, **merge не выполнен**. Существующие datasets, checkpoint,
raw logs и результаты предыдущих задач сохранены. В Git нет node_modules, dist, временных
cards.json, сырых записей, venv или копий датасета; небольшой локальный dist нужен для запуска.
В worktree остаются нужные игнорируемые runtime/build-файлы; их нельзя считать disposable
перед архивированием. После будущего одобренного merge сначала проверить Git-сохранность
и отдельно сохранить необходимые ignored данные, затем удалить ветку/worktree безопасно.
