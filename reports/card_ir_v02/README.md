# CARD-IR-V02-IMPLEMENTATION

**Реализован `card-ir/0.2`: 15 новых элементов языка, 13 новых и 3 уточнённых универсальных правила, механизм
признания предварительных правил и строгая приёмка v0.2 поверх Validation-2.** Карточных обработчиков нет: ни один
элемент не ссылается на ID, имя или набор карты. Из 6 запрошенных карт **5 выражены полностью с явными
зависимостями (FULL_DEP)**; Magma Hound выражен структурно целиком, но остаётся PARTIAL, потому что «split» без
«randomly» не подтверждён; Torch остаётся честным PARTIAL (S2 отложен, [S2_DESIGN.md](S2_DESIGN.md)).

Это реализация языка, проверок и документации. Исполнителя нет; ни один результат здесь не является подтверждением
исхода настоящей партии. Повторная компиляция 12 карт B1 и следующие 18 карт — отдельные задачи.

## База и границы

* Рабочая копия `E:\ManaMind`, ветка `claude/card-ir-v02` от `codex/card-ir-validation-2` @
  `74bb5ab6196a5db13199a033f99b76e74590f1cb` (после `git fetch origin`; локальная и удалённая ветки совпадали).
  CI базы: «Source and generated artifact checks» — **success** (run 40319373419). Worktree и merge не использовались.
* Прочитаны: IR_SPEC v0.1, README B1, CARD_AUDIT и IR_V02_PROPOSAL (Opus), README Validation-2,
  `docs/CARD_IR_VALIDATION.md`, весь `src/manamind/card_ir/`.
* Выводы независимой проверки правил Sonnet получены **из текста задачи** (отдельного отчёта в репозитории нет) и
  записаны в источники правил `vocabulary_v02.py` как «independent Sonnet rules check (CARD-IR-V02 task, 2026-10-26)».
* Данные пользователя по Aviana и Torch — игровой опыт, не документация Blizzard. В декларациях они помечены новым
  основанием решения `USER_OBSERVED`.
* Не менялись: ManaEngine, LIVE, Policy, обучение, self-play, checkpoint-ы, каталоги и снимки, holdout, декларации и
  результаты A/B1/аудита/Validation-2, модули v0.1. Сети и Power.log не использовались.

## Что реализовано

| Файл | Роль |
|---|---|
| `src/manamind/card_ir/vocabulary_v02.py` | словарь v0.2: элементы и правила v0.1 + дельта; основание `DEFINITION`; `PROVISIONAL_RULES` |
| `validate_v02.py` | структурный валидатор v0.2 (наследует walker v0.1, переопределяет изменившиеся узлы) |
| `lint_v02.py` | текстовые проверки новых конструкций; список заменённых предупреждений v0.1 |
| `strict_v02.py` | `validate_strict_v02` и диспетчер `validate_strict_any` по полю `ir` |
| `render_v02.py` | обычный и аудит-рендер новых узлов; `audit_render.render_audit` выбирает его для `card-ir/0.2` |
| `strict.py`, `strict_lint.py`, `audit_render.py` | обратно совместимые правки (раздел 1 [CHANGELOG](CHANGELOG.md)); вывод для v0.1 побайтно прежний |
| `scripts/validate_card_ir.py` | выбирает версию по `ir`; exit-коды прежние |
| `reports/card_ir_v02/examples/` | 7 примеров v0.2 и квитанция пропуска Torch |
| `conformance.py`, `measure.py`, `results.json` | 98 conformance-случаев и воспроизводимые измерения |
| `tests/test_card_ir_v02.py` | 110 тестов |

Нормативная дельта языка — [CHANGELOG.md](CHANGELOG.md); тесты — [CONFORMANCE.md](CONFORMANCE.md).

### Архитектура версий

Модули v0.1 закреплены хешами Validation-2 и не менялись. v0.2 — отдельные модули, которые **наследуют** walker
v0.1 и подменяют только изменившиеся узлы (≈ 940 строк в пяти модулях `*_v02.py`). Каждая декларация проверяется ровно одной версией:
v0.1 отвергает `card-ir/0.2`, v0.2 отвергает `card-ir/0.1`. Конструкции, у которых меняется смысл, в v0.2 обязаны
быть явными (кардинальность эффекта игрока, зоны стоимости, направление стоимости, роли атаки), поэтому замена строки
версии у старой декларации не превращает её молча в декларацию другого смысла.

### Универсальные операции, параметры и правила

* **Операция:** `FREEZE`.
* **Параметры и значения существующих элементов:** длительности `THIS_GAME` и `{"next_turn": игрок}`;
  `starts_after {player, turn_starts}`, `zones`, `uses: "ALL_MATCHING"` у `ADD_PLAYER_EFFECT`; роли `attacker`/
  `defender` у `ATTACK_DECLARED`; предикат `alive`; счётчик `DAMAGE_DEALT` с `measure: AMOUNT` и `source`;
  арифметика `mul`; направление стоимости `increase`; `position` и `count` у `SHUFFLE_INTO_DECK`; перемещение
  PLAY→HAND как элемент `move:PLAY_TO_HAND`.
* **Правила:** уточнены `R_COST` (порядок модификаторов), `R_PLAYER_EFFECT`, `R_DECK_POSITION`; новые
  `R_SURVIVE`, `R_RETURN_TO_HAND`, `R_RANDOM_SPLIT`, `R_FREEZE` (подтверждённые части), `R_TURN_WINDOW`,
  `R_DELAYED_START`, `R_PLAYER_AURA`, `R_ATTACK_ROLES` (определения конструкций), и **предварительные**
  `R_RETURN_FULL_HAND`, `R_SPLIT_UNQUALIFIED`, `R_FREEZE_THAW`, `R_ATTACK_REDIRECT`, `R_DAMAGE_EVENT_AMOUNT`.
* **Механизм признания:** декларация, которой нужно предварительное правило, обязана содержать
  `UNKNOWN_RULE`-зависимость с полем `rule`; автор выбирает CONDITIONAL или CORE, и статус честно понижается.

## Какие ограничения v0.1 устранены

| Ограничение v0.1 | В v0.2 |
|---|---|
| Нет FREEZE (пробел из IR_SPEC §10) | `op:FREEZE`, порядок в `seq` проверяется (`ORDER_V02`) |
| Длительности только `THIS_TURN`, `UNTIL_USED`, `{turns}` | + `THIS_GAME`, `{next_turn}` |
| Эффект игрока = «следующая подходящая карта» | явная кардинальность: `N` или `ALL_MATCHING`; явные зоны; отложенный старт |
| `ATTACK_DECLARED.subject` без определённой роли | `attacker`/`defender`, `subject` запрещён |
| Выживание только через `cmp HEALTH > 0` (не видит pending destroy) | `alive` по `R_SURVIVE` |
| Нет суммы урона и умножения: «(1) less for each damage» не проходит сверку чисел | `DAMAGE_DEALT/AMOUNT` + `mul` |
| «costs (N) more» как `reduce: -N`, перепутанный знак не ловится | `increase`, отрицательные литералы запрещены, `COST_SIGN` |
| `SHUFFLE` не выражает верх/низ и количество | `position`, `count`, `DECK_POSITION_V02`, `DECK_COUNT` |
| Перемещение PLAY→HAND без правила | `R_RETURN_TO_HAND` + признаваемое `R_RETURN_FULL_HAND` |
| Условие у `trigger` не проверяется вовсе (найдено в этой задаче) | проверяется |
| Роли событий не закреплены за типом события | закреплены; роль — фильтр (`pick ALL`) |
| Рендер скрывает условие триггера и пишет «for the next card» без `uses` | показывает условие, кардинальность, зоны, старт, окно, позицию, признания правил |

## Игровые правила: подтверждено и условно

| Утверждение | Статус в v0.2 |
|---|---|
| Выживание проверяется после реакций шага, до фазы смерти | подтверждено (Sonnet) → `R_SURVIVE`, без зависимости |
| Порядок модификаторов стоимости | подтверждено (Sonnet) → `R_COST` |
| Возврат существа в руку сбрасывает его состояние | подтверждено с оговорками → `R_RETURN_TO_HAND`; полная рука — предварительное `R_RETURN_FULL_HAND` |
| «randomly split» | подтверждено → `R_RANDOM_SPLIT` |
| «split» без «randomly» | **не приравнивается** → предварительное `R_SPLIT_UNQUALIFIED` |
| Наложение Freeze | `R_FREEZE`; **снятие** подтверждено не полностью → предварительное `R_FREEZE_THAW` |
| Общий отсчёт ходов | **не выводится** из Aviana: `R_DELAYED_START` — только определение конструкции; чьи ходы и какое N — решение карты |
| Перенаправленная атака, сумма урона при щите/броне/overkill | предварительные `R_ATTACK_REDIRECT`, `R_DAMAGE_EVENT_AMOUNT` |
| Aviana: три своих хода, рука и колода по (1), до конца партии | `USER_OBSERVED` в решениях примера |
| Aviana: новые карты, повторный розыгрыш, другие модификаторы | CONDITIONAL-зависимости примера |
| Torch: 8→5→3, ноль/щит — без возврата, значение сохраняется | `USER_OBSERVED`, записано в [S2_DESIGN.md](S2_DESIGN.md); **не** закодировано (нужен S2) |
| Torch: Spell Damage, Immune, полная рука | UNKNOWN |

Поправка к аудиту Opus: по наблюдению пользователя Divine Shield даёт Torch **нулевой** избыток, поэтому формула
`max(0, 8 − Health)` из CARD_AUDIT 3.11 неверна; нужен фактически нанесённый урон (S2_DESIGN §1).

## Примеры v0.2

Все 7 приняты строгим режимом v0.2 без ошибок и предупреждений и отвергнуты всеми инструментами v0.1
([results.json](results.json) → `examples`, там же обычный и аудит-рендер).

| Карта | Статус | Что показывает | Зависимости |
|---|---|---|---|
| Aviana `EDR_895` | FULL_DEP | `ADD_PLAYER_EFFECT {cost set 1, ALL_MATCHING, zones HAND+DECK, starts_after SELF 3, THIS_GAME}` | новые карты, повторный розыгрыш, другие модификаторы (CONDITIONAL) |
| Cult Neophyte `CORE_SCH_713` | FULL_DEP | `increase 1`, `applies_to SPELL`, `ALL_MATCHING`, `next_turn OPPONENT` | стоимость в колоде (CONDITIONAL) |
| Imp Gang Stooge `JAIL_399` | FULL_DEP | `SHUFFLE_INTO_DECK count 2, position BOTTOM`, токен `JAIL_399t1` | идентичность токена (DATA) |
| Frostwyrm's Fury `CORE_RLK_063` | FULL_DEP | одна `seq`: урон → `FREEZE` всех вражеских существ → призыв | токен (DATA), снятие Freeze (CONDITIONAL, `R_FREEZE_THAW`) |
| Magma Hound `FIR_953` | **PARTIAL** | `ATTACK_DECLARED {attacker SELF, defender minion}`, `AFTER`, `alive`, повтор по Attack | split без «randomly» (**CORE**, `R_SPLIT_UNQUALIFIED`), перенаправление (CONDITIONAL) |
| Spellweaver's Brilliance `CATA_452` | FULL_DEP | аура в руке: `reduce mul(1, DAMAGE_DEALT AMOUNT SELF THIS_TURN source SPELL)` | токен (DATA), сумма урона (CONDITIONAL, `R_DAMAGE_EVENT_AMOUNT`) |
| Torch `CATA_585` | **PARTIAL** | урон выражен; возврат — связанный пропуск | параметр экземпляра (CORE, S2), Spell Damage (CORE) |

## Сколько карт B1 потенциально выразимы

Реализованное отделено от прогноза. «Проверено» — декларация v0.2 реально принята строгим режимом (пример или
conformance-фикстура на реальном тексте). «Прогноз» — не перекодировано в этой задаче.

| # | Карта | B1 | Opus: v0.2 | v0.2 сейчас | Основание |
|---|---|---|---|---|---|
| 1 | Aviana | PARTIAL | FULL_DEP | FULL_DEP | проверено (пример) |
| 2 | Nascent Bolt | PARTIAL | FULL | FULL | проверено (фикстура, `alive`) |
| 3 | Ultraxion | PARTIAL | PARTIAL | PARTIAL | прогноз: Herald, `{1}`, данные Deathwing — v0.2 не решает |
| 4 | Spellweaver's Brilliance | PARTIAL | FULL_DEP | FULL_DEP | проверено (пример) |
| 5 | V'ama | PARTIAL | FULL_DEP | FULL_DEP | прогноз: уже выразима в v0.1 через `exclude` (проверено Opus в v0.1) |
| 6 | Aldrachi Warblades | FULL | FULL | FULL | прогноз: те же конструкции v0.1 |
| 7 | Imp Gang Stooge | PARTIAL | FULL_DEP | FULL_DEP | проверено (пример) |
| 8 | Cult Neophyte | PARTIAL | FULL / FULL_DEP | FULL_DEP | проверено (пример) |
| 9 | Waggle Pick | PARTIAL | FULL | **FULL_DEP** | проверено (фикстура): полная рука — предварительное правило |
| 10 | Magma Hound | PARTIAL | FULL_DEP | **PARTIAL** | проверено (пример): split без «randomly» не подтверждён |
| 11 | Torch | PARTIAL | PARTIAL без S2 | PARTIAL | проверено (пример) |
| 12 | Frostwyrm's Fury | PARTIAL | FULL_DEP | FULL_DEP | проверено (пример) |

**Потенциально FULL/FULL_DEP: 9/12** (B1: 1/12; прогноз Opus: 10/12). Из них 7 подтверждены принятой декларацией
v0.2, 2 (V'ama, Warblades) — прогноз. Расхождение с Opus — два места, где v0.2 осторожнее по проверке Sonnet:
Magma Hound (split) и Waggle Pick (полная рука). Если `R_SPLIT_UNQUALIFIED` подтвердится, Magma Hound станет
FULL_DEP без изменения языка.

Оговорка: примеры и фикстуры написаны автором языка с полным знанием CARD_AUDIT. Это демонстрация **выразимости**, а
не оценка того, как часто независимый автор напишет правильную декларацию.

## Что язык всё ещё не решает

* **Параметры экземпляра (S2)** и «фактически нанесённый урон» — Torch, «Improves», счётчики `{0}`
  ([S2_DESIGN.md](S2_DESIGN.md)).
* **Herald**, клиентские плейсхолдеры, семейства карт по имени (Deathwing) — Ultraxion.
* Spell Damage у карт с `ImmuneToSpellpower` (E10 отложен), мультикласс в отрицании (V'ama, CONDITIONAL).
* Старые UNKNOWN-правила v0.1 (`R_AMOUNT_ORDER`, `R_AURA`, `R_COPY`, `R_DISCOVER`, `R_CAST`, …) не требуют признания;
  механизм признания покрывает только новые правила v0.2.
* Событие начала хода, отрицание условий, ссылки на способности других карт, проверка метаданных токенов против
  текста (C9), несколько `play`-способностей у заклинания (C11).
* Lint-проверки — шаблоны английского; язык не доказывает эквивалентность текста и IR. Известные слепые участки —
  в [CONFORMANCE.md](CONFORMANCE.md).
* Найдена лазейка v0.1: условие у `trigger` вообще не проверяется. В v0.2 закрыта, в замороженном v0.1 — нет.

## Как проверять декларации v0.2

```powershell
.\.venv\Scripts\python.exe scripts/validate_card_ir.py <declaration>.json [--bindings <receipt>.json] [--audit-output <new>.txt]
```

```python
from manamind.card_ir.strict_v02 import validate_strict_any   # выбирает v0.1 или v0.2 по полю "ir"
from manamind.card_ir.audit_render import render_audit

report = validate_strict_any(declaration, metadata, bindings=receipt_or_none)
report.accepted   # нет ошибок и предупреждений; честный PARTIAL допустим
report.complete   # accepted и FULL/FULL_DEP; не gold и не готовность к исполнению
lines = render_audit(declaration, metadata, receipt_or_none, report)
```

Порядок для автора: прочитать аудит-рендер целиком (он показывает зоны, старт, окно, кардинальность, роли, признания
и происхождение каждого правила); для каждого предварительного правила выбрать CONDITIONAL или CORE и записать
различающий случай в решении.

## Воспроизведение и проверки

```powershell
.\.venv\Scripts\python.exe -I reports/card_ir_v02/measure.py --output <новый-результат>.json
.\.venv\Scripts\python.exe -m pytest tests/test_card_ir.py tests/test_card_ir_pilot_1.py tests/test_card_ir_stage_b1.py tests/test_card_ir_semantic_lint.py tests/test_card_ir_strict.py tests/test_card_ir_v02.py -q
```

Проверено 2026-10-26 в `E:\ManaMind`, Python из `.venv`:

| Проверка | Результат |
|---|---|
| Все тесты Card IR (A, B1, semantic lint, Validation-2, v0.2) | **219 passed** |
| Новые тесты v0.2 | **110 passed** (98 conformance-случаев + 12 тестов свойств) |
| Полный pytest | **1460 passed, 1 skipped**, 118,7 с (`--basetemp` внутри рабочей копии) |
| Ruff: 328 отслеживаемых Python-файлов + 8 новых | **All checks passed** |
| `scripts/check_generated_artifacts.py` | **2 pinned outputs reproduced**, diff `data/cards` пуст |
| Хеши 116 исторических входов Validation-2 (включая модули v0.1) | совпадают (существующий тест) |
| Протоколы/метрики A, B1, диагностика Opus, результаты Validation-2 | воспроизводятся байт в байт (существующие тесты) |
| `results.json` этой задачи | воспроизводится байт в байт (новый тест) |
| 65 исторических деклараций | 65/65 приняты строгим v0.1 с миграционными квитанциями; диспетчер даёт идентичный результат; v0.2 отвергает их по версии |
| Изоляция Card IR от LIVE/Policy/ManaEngine | существующий тест импорта проходит: пакет импортирует только `card_ir` и `card_metadata`, никто вне пакета не импортирует `card_ir` |

Полный pytest запускался в рабочей копии, где есть чужие неотслеживаемые файлы (в том числе
`tests/test_decision_review.py`); они не изменялись и в коммит не входят.
