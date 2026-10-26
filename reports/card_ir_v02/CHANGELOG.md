# Card IR v0.2 — изменения относительно v0.1

Нормативная дельта к [IR_SPEC.md v0.1](../card_ir_pilot_1/IR_SPEC.md). Всё, что здесь не упомянуто, в v0.2 значит
то же, что в v0.1. Авторитетный код: `src/manamind/card_ir/vocabulary_v02.py`, `validate_v02.py`, `lint_v02.py`,
`strict_v02.py`, `render_v02.py`. Использование и приёмка — [docs/CARD_IR_VALIDATION.md](../../docs/CARD_IR_VALIDATION.md).

## 1. Версии

* Декларация v0.2 несёт `"ir": "card-ir/0.2"`. Каждую декларацию проверяет **ровно одна** версия:
  инструменты v0.1 отвергают `card-ir/0.2`, валидатор v0.2 отвергает `card-ir/0.1`. `validate_strict_any` и
  `scripts/validate_card_ir.py` выбирают версию по полю `ir`; неизвестная версия отвергается, а не угадывается.
* Модули v0.1 (`validate.py`, `vocabulary.py`, `render.py`, `lint.py`, `semantic_lint.py`, `__init__.py`) не изменены:
  они закреплены хешами в `reports/card_ir_validation_2/input_hashes.json`. v0.2 наследует walker v0.1 и
  переопределяет только изменившиеся узлы.
* Обновление декларации v0.1 до v0.2 — это **переавторство**, а не замена строки версии. Конструкции, у которых
  меняется смысл, в v0.2 обязаны быть явными; поэтому переименованная декларация v0.1 обычно не проходит
  (conformance-случай «a v0.1 declaration relabelled as v0.2»).
* Общие strict-модули изменены обратно совместимо: `strict.py` (структурные проверки вынесены в функции с тем же
  поведением), `strict_lint.py` (`_alive` распознаёт предикат `alive`, который валидатор v0.1 отвергает раньше),
  `audit_render.py` (ветка для `card-ir/0.2`). Результаты Validation-2 воспроизводятся байт в байт.

## 2. Документ декларации

| Поле | Изменение |
|---|---|
| `role` | добавлено `example` — пример выразимости, не участник выборки A/B |
| `decisions[].basis` | добавлено `USER_OBSERVED` — непосредственный игровой опыт пользователя. Считается источником (как `COMMUNITY_RULES`), не официальной документацией |
| `dependencies[].rule` | новое необязательное поле: признание **предварительного правила** (раздел 5) |

## 3. Новые и изменённые узлы

| Элемент | Форма | Семантика | Инварианты валидатора |
|---|---|---|---|
| `op:FREEZE` | `{"op": "FREEZE", "to": selector}` | `R_FREEZE`; снятие — `R_FREEZE_THAW` (предварительное) | `to` — персонажи (CHARACTER/MINION/HERO, не оружие, не карты в руке); нужна зависимость `rule: R_FREEZE_THAW` |
| `duration:THIS_GAME` | `"THIS_GAME"` | до конца игры, независимо от источника (`R_TURN_WINDOW`) | не сочетается с целыми `uses` (это `UNTIL_USED`) |
| `duration:NEXT_TURN` | `{"next_turn": "SELF"\|"OPPONENT"}` | первый ход указанного игрока, начавшийся после создания эффекта, от начала до конца (`R_TURN_WINDOW`) | игрок указан явно |
| `player_effect:starts_after` | `"starts_after": {"player", "turn_starts": N}` у `ADD_PLAYER_EFFECT` | эффект неактивен до N-го начала хода `player` после создания (`R_DELAYED_START`) | `N ≥ 1` целое; число попадает в сверку чисел текста |
| `player_effect:zones` | `"zones": [HAND, DECK, PLAY]` у `ADD_PLAYER_EFFECT` | зоны, карты которых меняет стоимостный эффект игрока | обязательно, если в модификаторе есть `cost`; запрещено без `cost`; непустой список без повторов |
| `player_effect:ALL_MATCHING` | `"uses": "ALL_MATCHING"` | все подходящие карты в зонах, пока эффект активен, включая пришедшие позже (`R_PLAYER_AURA`) | без `use_unit`; не с `UNTIL_USED` |
| `uses` у эффекта игрока с `modifier` | `N` или `"ALL_MATCHING"` | **обязательно** в v0.2 (в v0.1 отсутствие `uses` значило «следующая карта») | целое `uses` требует `use_unit`; `UNTIL_USED` требует целое `uses` |
| `event_role:attacker`, `event_role:defender` | у `ATTACK_DECLARED`: `attacker`, `defender` | атакующий и атакуемый (`R_ATTACK_ROLES`); `WHEN` — объявление, `AFTER` — после боя и реакций | `subject` у атаки запрещён; нужна хотя бы одна роль; роль — фильтр (`pick ALL`, `SELF`, `ref`); `defender` требует `rule: R_ATTACK_REDIRECT` |
| роли других событий | `DAMAGE_TAKEN` — `subject` (обязателен); `DAMAGE_DEALT` — `player`, `source`; остальные — `player` | как в v0.1, но ключи закреплены за типом события | лишние роли отвергаются |
| `pred:alive` | `{"alive": true\|false}` | `R_SURVIVE`: после шага и его реакций, до фазы смерти, в игре, Health > 0, не помечен на уничтожение | только в условии `is` над `SELF` или `ref`; булево |
| `counter:DAMAGE_DEALT` | `{"counter": {"event": "DAMAGE_DEALT", "measure": "AMOUNT", "player", "scope", "source"?}}` | сумма фактически нанесённого урона источниками, подходящими под `source` (`R_DAMAGE_EVENT_AMOUNT`, предварительное) | `measure` только `AMOUNT`; нужна зависимость `rule: R_DAMAGE_EVENT_AMOUNT` |
| `value:mul` | `{"mul": [a, b]}` | произведение | ровно два значения, хотя бы одно — целый литерал (он участвует в сверке чисел текста) |
| cost `increase` | `{"cost": {"increase": v}}`, `MODIFY_COST.increase` | «costs (N) more» | `reduce`/`increase`/`count` не могут быть отрицательными литералами (в v0.1 «more» писали как `reduce: -N`) |
| `deck_position:*`, `count` у `SHUFFLE_INTO_DECK` | `"position": "RANDOM"\|"TOP"\|"BOTTOM"`, `"count": N` | `R_DECK_POSITION`; по умолчанию `RANDOM` (смысл v0.1) | перечисление; `count ≥ 0` |
| `move:PLAY_TO_HAND` | `ADD_TO_HAND` с `from_zone` — запросом в зоне `PLAY` | `R_RETURN_TO_HAND`; полная рука — `R_RETURN_FULL_HAND` (предварительное) | только для существ; нужна зависимость `rule: R_RETURN_FULL_HAND` |
| условие триггера | `condition` у `trigger` | — | **проверяется** (валидатор v0.1 его не проверял вовсе — см. раздел 7) |
| чтение split | текст спана | «randomly split» → `R_RANDOM_SPLIT`; «split» без «randomly» → ещё `R_SPLIT_UNQUALIFIED` (предварительное) | правило выводится из текста спана способности; кодировка — `repeat` + урон 1 по `RANDOM` (lint) |

## 4. Правила

Основание `DEFINITION` (новое) означает: правило определяет смысл конструкции IR и **ничего не утверждает о картах**.
Соответствие текста конкретной карты этой конструкции — решение (`decisions`) в декларации карты.

| Правило | Основание | Предварительное | Смысл / источник |
|---|---|---|---|
| `R_COST` (изменено) | COMMUNITY_RULES (было UNKNOWN) | — | модификаторы в порядке применения; `set` заменяет текущее значение; минимум 0 — один раз после всех. Порядок подтверждён независимой проверкой Sonnet |
| `R_PLAYER_EFFECT` (изменено) | UNKNOWN | — | эффект на игроке, не зависит от источника; целые `uses` — следующие N карт/эффектов (смысл v0.1); что такое «одно использование» — по-прежнему UNKNOWN |
| `R_DECK_POSITION` (изменено) | UNVERIFIED | — | RANDOM / TOP / BOTTOM, `count` вставляет по одной; предел размера колоды не покрыт |
| `R_SURVIVE` | COMMUNITY_RULES | — | Sonnet: хорошо подтверждено |
| `R_RETURN_TO_HAND` | COMMUNITY_RULES | — | сброс урона, зачарований, Silence; Sonnet: подтверждено с оговорками, поэтому полная рука вынесена отдельно |
| `R_RETURN_FULL_HAND` | UNVERIFIED | **да** | при полной руке существо уничтожается (умирает) |
| `R_RANDOM_SPLIT` | COMMUNITY_RULES | — | Sonnet: подтверждено для «randomly split» |
| `R_SPLIT_UNQUALIFIED` | UNKNOWN | **да** | «split» без «randomly» = «randomly split»: Sonnet — автоматически не приравнивать |
| `R_FREEZE` | COMMUNITY_RULES | — | наложение Frozen; Frozen не атакует |
| `R_FREEZE_THAW` | UNKNOWN | **да** | момент снятия Frozen: Sonnet — подтверждено не полностью |
| `R_TURN_WINDOW` | DEFINITION | — | NEXT_TURN, THIS_GAME |
| `R_DELAYED_START` | DEFINITION | — | отсчёт начал ходов; **не выведено из Aviana** — Aviana лишь один случай его применения |
| `R_PLAYER_AURA` | DEFINITION | — | `ALL_MATCHING` динамичен; ведёт ли себя так конкретная карта — её решение |
| `R_ATTACK_ROLES` | DEFINITION | — | роли и тайминги атаки |
| `R_ATTACK_REDIRECT` | UNKNOWN | **да** | какую цель видит фильтр роли при перенаправлении |
| `R_DAMAGE_EVENT_AMOUNT` | UNVERIFIED | **да** | щит → 0, броня считается, overkill полностью; граничные источники не решены |

## 5. Признание предварительных правил

Если среди правил, которые валидатор выводит для декларации, есть правило из `PROVISIONAL_RULES`, декларация обязана
содержать зависимость `{"kind": "UNKNOWN_RULE", "scope": "CONDITIONAL"|"CORE", "rule": "<id>"}`. Масштаб выбирает
автор: CORE делает декларацию PARTIAL, CONDITIONAL — FULL_DEP. Обратная проверка: зависимость с `rule`, которого
декларации не нужно, — ошибка; повторное признание и признание непредварительного правила — ошибки. Такая
зависимость считается использованной; CORE-зависимость по-прежнему должна быть связана с решением, `unknown` или
квитанцией пропуска (строгий режим Validation-2).

Старые правила с основанием UNKNOWN из v0.1 (`R_AMOUNT_ORDER`, `R_AURA`, `R_COPY`, `R_DISCOVER`, …) этого признания
**не требуют**: иначе каждая карта с `$` получила бы зависимость. Это сознательное ограничение области v0.2.

## 6. Строгий режим

`validate_strict_v02` = валидатор v0.2 + все проверки Validation-2 (структура, квитанции пропусков и их миграционный
файл, якоря CORE, reminders, оба линтера v0.1, strict lint) + `lint_v02`. Отброшены только предупреждения strict lint,
которые говорили «v0.1 этого не выражает»; каждое заменено проверкой правильности выражения:

| Код v0.1 | Замена в v0.2 |
|---|---|
| `WINDOW_NEXT` | `WINDOW_NEXT_V02`: «next turn» ↔ `next_turn`, владелец («your/opponent's next turn», иначе игрок эффекта) |
| `DECK_POSITION` | `DECK_POSITION_V02`: «bottom of / top of … deck» / «shuffle» ↔ `position` |
| `RETURN_CONTRACT` | валидатор: `move:PLAY_TO_HAND` → `R_RETURN_TO_HAND` + признанное `R_RETURN_FULL_HAND` |
| `EVENT_ROLE` | валидатор: `subject` у `ATTACK_DECLARED` отвергается, роли `attacker`/`defender` определены |

Новые коды `lint_v02`: `FREEZE_TEXT` (в обе стороны), `ORDER_V02` (порядок прямой последовательности с FREEZE),
`WINDOW_GAME`, `DELAY_COUNT` (число ходов, включая слова «three»), `DELAY_OWNER`, `USES_SCOPE` («next» ↔ целые `uses`;
«next turn» не считается), `DECK_COUNT` («put two»), `ATTACK_ROLE`, `SPLIT_ENCODING`, `COST_SIGN`, `MULTIPLY`,
`DAMAGE_COUNTER` (наличие, `with spells`, владелец, период), `RETURN_MOVE` («return» — перемещение, не копия),
`SURVIVE_TEXT`.

## 7. Найденная лазейка v0.1 (не исправлена в v0.1)

Валидатор v0.1 принимает `condition` у способности `trigger`, **не проверяя его содержимое**: `{"garbage": 1}`
проходит. В v0.2 условие триггера проверяется. Замороженные v0.1-инструменты не менялись; строгий режим v0.1 эту
лазейку тоже не закрывает. Исправление для v0.1 — отдельное решение (оно изменит поведение замороженной приёмки).

## 8. Отклонено и отложено

| Предложение (IR_V02_PROPOSAL / B1) | Решение | Почему |
|---|---|---|
| `control:SCHEDULE`, `keyword:LUNAR_CYCLE` | отклонено | достаточно `starts_after`; лунный цикл — карточный элемент |
| `cond:NOT` | отклонено | отрицание множества уже есть (`exclude`) |
| `op:RETURN_TO_HAND`, `op:INSERT_INTO_DECK`, `event:SOURCE_ATTACK` | отклонено | правило + существующее перемещение; параметры `position`/`count`; роль `attacker` |
| `value:EXCESS_DAMAGE` | не нужно | для Torch excess считается арифметикой; но без S2 его некуда сохранить |
| R7 «отсчёт в начале N-го своего хода» как игровое правило | заменено | `R_DELAYED_START` — определение конструкции; чьи ходы и какое N — решение карты |
| R2 «split без randomly = randomly split» | ослаблено | предварительное `R_SPLIT_UNQUALIFIED` (Sonnet) |
| R1 одним правилом | разделено | сброс — `R_RETURN_TO_HAND`, полная рука — предварительное `R_RETURN_FULL_HAND` |
| R6 одним правилом | разделено | наложение — `R_FREEZE`, снятие — предварительное `R_FREEZE_THAW` |
| E10 `spell_damage: CARD_PROCEDURE` | отложено | нужен только Torch, который без S2 всё равно PARTIAL; Spell Damage Torch — UNKNOWN |
| E11 `keyword:HERALD` | отложено | Ultraxion остаётся PARTIAL по данным и правилам |
| S2 параметры экземпляра | отложено | [S2_DESIGN.md](S2_DESIGN.md) |
| C9 (метаданные токенов против текста), C11 (несколько `play`-способностей) | не сделано | не нужны для новых конструкций; остаются в списке ужесточений |
| событие начала хода, NOT для условий | не сделано | ни одна карта задачи не требует |
