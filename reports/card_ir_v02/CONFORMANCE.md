# Card IR v0.2 — conformance-тесты языка

**Что это:** проверка, что строгая приёмка v0.2 принимает правильные декларации с нужным статусом и рендером и
отвергает неправильные по ожидаемой причине. **Чем это не является:** подтверждением исхода настоящей партии
Hearthstone, оценкой доли ложного принятия на новых картах или независимой gold-разметкой. Случаи и проверки написаны
одним автором (Claude Opus, исполнитель v0.2); проверки, добавленные вместе со случаем, ловят этот случай по
построению. Независимую оценку даст отдельное переавторство карт другим автором.

Источник: [conformance.py](conformance.py) (построение случаев), [measure.py](measure.py) →
[results.json](results.json) (результат каждого случая), `tests/test_card_ir_v02.py` (один тест на случай).

## Итог

| Набор | Результат |
|---|---|
| Conformance-случаи | **98/98** ожидаемых исходов: good 21, bad 39, edge 27, interaction 11 |
| — на реальном тексте закреплённых карт (REAL) | 69 (в т. ч. мутации 7 примеров и фикстуры Nascent Bolt, Waggle Pick) |
| — синтетические тексты `CARD_IR_V02_FIXTURE_*` (SYNTHETIC) | 29; только во фикстурной обёртке метаданных, не в каталоге |
| 7 примеров | приняты с заявленным статусом: FULL_DEP 5, PARTIAL 2 |
| 65 исторических деклараций A/B1 | 65/65 приняты строгим v0.1 с миграционными квитанциями; диспетчер по версии даёт **тот же** результат 65/65; валидатор v0.2 отвергает 65/65 по версии (молчаливой переинтерпретации нет) |
| 9 диагностик Opus, переименованных в `card-ir/0.2` | 9/9 отвергнуты |
| Операторы мутаций пилота A на 7 примерах | **42/44** обнаружены (см. ниже) |
| Прежние тесты Card IR (A, B1, semantic lint, Validation-2) | без изменений, 109/109; результаты Validation-2 воспроизводятся байт в байт |

Каждый новый элемент и каждое новое правило используется хотя бы одной принятой декларацией (тест). Каждое
предварительное правило имеет случай отказа без признания (тест).

## Случаи по элементам

REAL — реальный текст закреплённой карты (сам пример или его мутация). Код — подстрока, которая обязана
появиться среди ошибок или предупреждений.

### `op:FREEZE`

| Случай | Вид | Текст | Ожидание |
|---|---|---|---|
| freeze a chosen enemy minion | good | SYNTHETIC | accept FULL_DEP; рендер «freeze them<t>», правило снятия помечено PROVISIONAL |
| freeze without acknowledging the thaw rule | bad | SYNTHETIC | `R_FREEZE_THAW` |
| thaw acknowledgement with DATA scope | edge | SYNTHETIC | `rule acknowledgement` |
| freeze text encoded as silence | bad | SYNTHETIC | `FREEZE_TEXT` |
| freeze cards in hand | bad | SYNTHETIC | `FREEZE targets characters` |
| freeze the enemy hero (short selector) | edge | SYNTHETIC | accept FULL_DEP |
| Frostwyrm's Fury: summon before freeze | interaction | REAL | `ORDER_V02` |
| Frostwyrm's Fury: freeze hidden in a reminder | interaction | REAL | `REMINDER` (защита Validation-2 сохраняется) |

### Длительности `THIS_GAME`, `NEXT_TURN`

| Случай | Вид | Текст | Ожидание |
|---|---|---|---|
| spells cheaper for the rest of the game | good | SYNTHETIC | accept FULL; рендер «for the rest of the game» |
| this game read as this turn | bad | SYNTHETIC | `WINDOW_GAME` |
| THIS_GAME without textual evidence | bad | SYNTHETIC | `WINDOW_GAME` |
| THIS_GAME with integer uses | edge | SYNTHETIC | `integer uses with THIS_GAME` |
| Cult Neophyte: this turn instead of next turn | bad | REAL | `WINDOW_NEXT_V02` |
| Cult Neophyte: your next turn instead of the opponent's | bad | REAL | `WINDOW_NEXT_V02` |
| explicit 'your next turn' | good | SYNTHETIC | accept FULL; рендер «during your next turn» |
| next_turn without textual evidence | edge | SYNTHETIC | `WINDOW_NEXT_V02` |
| next_turn names a player | edge | SYNTHETIC | `next_turn` (перечисление) |

### Эффект игрока: `starts_after`, `zones`, `uses: ALL_MATCHING`

| Случай | Вид | Текст | Ожидание |
|---|---|---|---|
| Aviana: two instead of three turns | bad | REAL | `DELAY_COUNT` |
| Aviana: effect starts at once | bad | REAL | `DELAY_COUNT` |
| Aviana: lasts three turns instead of starting after three | interaction | REAL | `WINDOW_GAME` (и `DELAY_COUNT` не помогает: `turns 3` совпадает с числом) |
| Aviana: counts the opponent's turns | bad | REAL | `DELAY_OWNER` |
| zero turn starts | edge | REAL | `positive integer` |
| Aviana: cost player effect without zones | bad | REAL | `zones` |
| zones on a non-cost player effect | bad | SYNTHETIC | `zones belong` |
| repeated zone | edge | REAL | `without repeats` |
| Aviana: hand only (a different, valid reading) | edge | REAL | **accept** FULL_DEP — язык не выбирает зону за автора; это решение карты |
| your next spell: one use | good | SYNTHETIC | accept FULL; рендер «the next 1 matching card(s)» |
| your next spell read as all spells | bad | SYNTHETIC | `USES_SCOPE` |
| Cult Neophyte: one spell instead of all | bad | REAL | `USES_SCOPE` |
| modifier player effect without uses | bad | REAL | `states its cardinality` |
| ALL_MATCHING until used | edge | SYNTHETIC | `use_unit belongs` |
| integer uses without a unit | edge | SYNTHETIC | `use_unit` |
| a v0.1 declaration relabelled as v0.2 (Preparation-like CORE_BT_416) | interaction | REAL | `zones` — смена строки версии не проходит |

### Роли атаки

| Случай | Вид | Текст | Ожидание |
|---|---|---|---|
| Magma Hound: hero attack instead of this minion | bad | REAL | `EVENT_SUBJECT` |
| Magma Hound: v0.1 'subject' role | bad | REAL | `unknown keys ['subject']` |
| Magma Hound: an enemy minion attacks | bad | REAL | `ATTACK_ROLE` |
| Magma Hound: attacks the hero instead of a minion | bad | REAL | `EVENT_DEFENDER` |
| Magma Hound: redirect rule not acknowledged | edge | REAL | `R_ATTACK_REDIRECT` |
| Magma Hound: a random defender | edge | REAL | `use pick ALL` |
| attack event without roles | edge | REAL | `needs an attacker or defender` |
| a friendly minion is attacked (defender only) | good | SYNTHETIC | accept FULL_DEP |
| Magma Hound audit shows both roles and the survival guard | good | REAL | accept PARTIAL; рендер «attacker this attacks defender a minion», «ONLY IF this is alive» |

### Выживание `alive`

| Случай | Вид | Текст | Ожидание |
|---|---|---|---|
| Nascent Bolt: draw only if the target survives | good | REAL | accept **FULL** |
| Nascent Bolt: unconditional draw | bad | REAL | `CONDITION_ENTITY` |
| Nascent Bolt: draw if it dies | bad | REAL | `CONDITION_ENTITY` |
| Nascent Bolt: survival of the wrong entity | bad | REAL | `CONDITION_ENTITY` |
| alive must be boolean | edge | REAL | `alive must be a boolean` |
| alive inside a selector | edge | SYNTHETIC | `alive is only allowed` |
| if it dies (alive false) | good | SYNTHETIC | accept FULL |
| trigger condition is validated (v0.1 loophole closed) | interaction | REAL | `unknown predicate` |
| Magma Hound: survival guard dropped | interaction | REAL | `CONDITION_ENTITY` |

### Счётчик урона и `mul`, направление стоимости

| Случай | Вид | Текст | Ожидание |
|---|---|---|---|
| Spellweaver's: spells cast instead of damage | bad | REAL | `DAMAGE_COUNTER` |
| Spellweaver's: damage from any source | bad | REAL | `DAMAGE_COUNTER` |
| Spellweaver's: counted this game | bad | REAL | `DAMAGE_COUNTER` |
| Spellweaver's: damage the opponent dealt | bad | REAL | `DAMAGE_COUNTER` |
| Spellweaver's: COUNT instead of AMOUNT | edge | REAL | `measure` |
| Spellweaver's: amount rule not acknowledged | edge | REAL | `R_DAMAGE_EVENT_AMOUNT` |
| Spellweaver's audit render shows the counter | good | REAL | accept FULL_DEP |
| Spellweaver's: reduce by the counter without mul | bad | REAL | `text number 1` (сверка чисел v0.1) |
| mul without a literal | edge | REAL | `mul takes` |
| mul with a wrong literal | bad | REAL | `text number 1` |
| Cult Neophyte: negative reduce | bad | REAL | `must not be negative` |
| Cult Neophyte: less instead of more | bad | REAL | `COST_SIGN` |
| returned minion costs more (random pick) | good | SYNTHETIC | accept FULL_DEP |

### Колода: позиция и количество

| Случай | Вид | Текст | Ожидание |
|---|---|---|---|
| Imp Gang Stooge: shuffle instead of bottom | bad | REAL | `DECK_POSITION_V02` |
| Imp Gang Stooge: top instead of bottom | bad | REAL | `DECK_POSITION_V02` |
| Imp Gang Stooge: one Demon instead of two | bad | REAL | `DECK_COUNT` |
| Imp Gang Stooge: unknown position | edge | REAL | `'MIDDLE' not in` |
| negative deck count | edge | REAL | `must not be negative` |
| shuffle with the default position | good | SYNTHETIC | accept FULL |
| shuffle with an explicit RANDOM position | edge | SYNTHETIC | accept FULL |
| shuffle text read as bottom | bad | SYNTHETIC | `DECK_POSITION_V02` |
| put on top | good | SYNTHETIC | accept FULL |

### PLAY → HAND, split, признание правил, квитанции, версии

| Случай | Вид | Текст | Ожидание |
|---|---|---|---|
| Waggle Pick: return with the full-hand rule acknowledged | good | REAL | accept FULL_DEP |
| Waggle Pick: full-hand rule not acknowledged | bad | REAL | `R_RETURN_FULL_HAND` |
| Waggle Pick: two minions | bad | REAL | `RETURN_SOURCE` (strict lint Validation-2 сохранён) |
| PLAY->HAND move of a non-minion | edge | REAL | `minions only` |
| full-hand acknowledgement without a move | edge | REAL | `does not need` |
| randomly split (confirmed rule, no acknowledgement) | good | SYNTHETIC | accept FULL |
| randomly split with an unnecessary unqualified-split acknowledgement | edge | SYNTHETIC | `does not need` |
| split read as damage to all enemies | bad | SYNTHETIC | `SPLIT_ENCODING` |
| Magma Hound: unqualified split not acknowledged | bad | REAL | `R_SPLIT_UNQUALIFIED` |
| acknowledging a non-provisional rule | bad | REAL | `not a provisional v0.2 rule` |
| acknowledging one rule twice | edge | REAL | `already acknowledged` |
| acknowledgement with a non-rule kind | edge | REAL | `rule acknowledgement` |
| Torch: no gap receipt | interaction | REAL | `GAP_BINDINGS` |
| Torch: CORE gap dependency removed | interaction | REAL | `GAP_DEPENDENCY` |
| Torch: return hidden in a reminder | interaction | REAL | `REMINDER` |
| Torch: static return as a plain ADD_TO_HAND | interaction | REAL | `RETURN_MOVE` |
| Torch: unconditional return of this card | interaction | REAL | `malformed declaration` — **поймано только защитой fail-closed** (см. ниже) |
| unknown version | edge | REAL | `VERSION` |

## Мутации пилота A на примерах v0.2

Неизменённые операторы `reports/card_ir_pilot_1/mutants.py`, первая применимая точка каждого оператора, 7 примеров:
**42/44** мутаций отвергнуты. Не обнаружены:

* `CORE_RLK_063`, `SIDE` у цели урона (`ANY → ENEMY`): слово «enemy» есть в соседнем предложении той же способности
  («Freeze all enemy minions»), поэтому якорь стороны v0.1 удовлетворён. Это тот же известный слепой участок, что
  `TIME_609` в A: якоря проверяют способность, а не отдельную клаузу.
* `FIR_953`, `SIDE` у защищающегося (`ANY → ENEMY`): эквивалентная мутация — свой Hound не может атаковать своё
  существо, поэтому «a minion» и «an enemy minion» дают один исход.

Третья мутация (`PICK` у защищающегося `ALL → RANDOM`) была не обнаружена в первом прогоне; после этого добавлен
структурный инвариант «роль события — фильтр (`pick ALL`)» и случай «Magma Hound: a random defender».

## Известные слепые участки

* **Безусловный возврат Torch** (`ADD_TO_HAND from_zone SELF` без условия избытка) отвергается только потому, что
  strict lint v0.1 аварийно читает `from_zone` как объект, а строгий режим превращает исключение в отказ. Ни одна
  смысловая проверка не видит пропущенного «with any excess». Отказ честный (fail closed), но не является обнаружением.
* Выбор зон (`Aviana: hand only`) и чьи ходы считаются (`starts_after.player` при совпадении с игроком эффекта)
  язык не проверяет по тексту: это решения карты, видимые в рендере и журнале решений.
* `ALL_MATCHING` против целых `uses` проверяется только словом «next»; карта, ограничивающая число использований
  другой формулировкой, пройдёт с неверной кардинальностью.
* Lint-проверки v0.2 читают тот же английский, что автор: это согласованность, а не независимая семантика.
