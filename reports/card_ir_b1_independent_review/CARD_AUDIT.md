# CARD-IR-B1-INDEPENDENT-REVIEW — аудит 12 деклараций B1

**Автор:** Claude Opus 5.5, модельное ревью. Это **не** человеческая gold-разметка.
**Порядок работы:** независимый разбор зафиксирован коммитом `5424a9e` (и запушен) до чтения решений Codex; этот
документ написан после чтения `IR_SPEC.md`, `src/manamind/card_ir/`, `reports/card_ir_stage_b1/{README.md, REVIEW.md,
review_notes.json, raw/, final/, results.json}` и Stage A-деклараций. Сравнение опирается на
[INDEPENDENT_INTERPRETATION.md](INDEPENDENT_INTERPRETATION.md) (правила G1–G11, данные D1–D4) и на воспроизводимую
диагностику [diagnostics.py](diagnostics.py) → [diagnostics.json](diagnostics.json).

## 0. Как читать

Категории расхождений (из задания): **AUTHOR_ERROR**, **IR_LIMITATION**, **RULE_UNCERTAINTY**, **DATA_DEPENDENCY**,
**OVERCONSERVATIVE**, **UNRESOLVED**. У каждой карты выделена **первопричина** PARTIAL. IR_LIMITATION дополнительно
уточняется: *структура* (нужен новый вид узла/операция), *параметр* (нужно значение перечисления, поле или роль у уже
существующего элемента), *слой правил* (правило игры известно, но в IR нет универсального правила `R_*`).

Уровни: **CONFIRMED** — проверено кодом валидатора, запуском диагностики, текстом карты или метаданными;
**SUPPORTED** — wiki/аналогия; **HYPOTHESIS**; **UNKNOWN**.

Важная асимметрия источников: протокол B1 запрещал Codex онлайн-источники правил. Я пользовался wiki. Поэтому часть
UNRESOLVED-решений Codex — следствие протокола, а не ошибки или неумения; ниже это отмечено отдельно.

## 1. Сводка

| # | Карта | B1 | Первопричина PARTIAL | Вторичные причины | Ошибка автора | Лучшее в v0.1 (мой CF) | v0.2 | Уверенность |
|---|---|---|---|---|---|---|---|---|
| 1 | Aviana, Elune's Chosen | PARTIAL | IR_LIMITATION, параметр: нет постоянной длительности, отложенного старта и «на все карты» у эффекта игрока | RULE_UNCERTAINTY: объём «your cards» | нет (в журнале нет вопроса об объёме) | PARTIAL | FULL_DEP | SUPPORTED |
| 2 | Nascent Bolt | PARTIAL | **OVERCONSERVATIVE**: `if HEALTH(target) > 0` уже есть в v0.1 | граница pending destroy (CONDITIONAL) | нет | **FULL_DEP** (проверено) | FULL | CONFIRMED / SUPPORTED |
| 3 | Ultraxion | PARTIAL | RULE_UNCERTAINTY + DATA_DEPENDENCY | IR_LIMITATION: Herald, параметры клиента `{0}/{1}` | нет | PARTIAL | PARTIAL | SUPPORTED |
| 4 | Spellweaver's Brilliance | PARTIAL | IR_LIMITATION, параметр: счётчик суммы урона + умножение «(1) … for each» | DATA: токен (SUPPORTED) | нет (мелкая несогласованность журнала) | PARTIAL | FULL_DEP | CONFIRMED |
| 5 | V'ama, Looming Death | PARTIAL | **OVERCONSERVATIVE**: отрицание выражается через `exclude` | RULE_UNCERTAINTY: мультикласс (CONDITIONAL) | нет | **FULL_DEP** (проверено) | FULL_DEP | CONFIRMED |
| 6 | Aldrachi Warblades | FULL | — | DATA: прочность в `health` (учтено) | нет | FULL | FULL | CONFIRMED |
| 7 | Imp Gang Stooge | PARTIAL | IR_LIMITATION, параметр: нет позиции вставки в колоду | OVERCONSERVATIVE: токен `JAIL_399t1` не найден | нет | PARTIAL | FULL_DEP | CONFIRMED |
| 8 | Cult Neophyte | PARTIAL | IR_LIMITATION, параметр: нет окна «следующий ход оппонента»; эффект игрока = «следующая карта» | RULE: динамичность (SUPPORTED по Loatheb) | нет | PARTIAL | FULL / FULL_DEP | SUPPORTED |
| 9 | Waggle Pick | PARTIAL | IR_LIMITATION, слой правил: нет `R_*` возврата в руку (правило игры известно) | — | **да, в raw**: FULL (исправлено самим Codex) | PARTIAL | FULL | SUPPORTED |
| 10 | Magma Hound | PARTIAL | IR_LIMITATION, параметр: роль атакующего у события атаки не определена | OVERCONSERVATIVE: split | нет | PARTIAL (структура выражена) | FULL_DEP | SUPPORTED |
| 11 | Torch | PARTIAL | IR_LIMITATION, структура: возврат себя с изменённым числом (параметр экземпляра) | RULE_UNCERTAINTY: Spell Damage при `ImmuneToSpellpower`, Divine Shield, полная рука | нет (Codex прав про Spell Damage, ошибался я) | PARTIAL | FULL_DEP только со структурным S2, иначе PARTIAL | SUPPORTED / UNKNOWN |
| 12 | Frostwyrm's Fury | PARTIAL | IR_LIMITATION, структура: нет FREEZE | DATA: токен `RLK_063t` (SUPPORTED) | нет | PARTIAL | FULL_DEP | CONFIRMED |

Счёт по первопричинам 11 PARTIAL: **IR_LIMITATION — 8** (структура 2: Frostwyrm, Torch; параметр 5: Aviana,
Spellweaver's, Imp, Neophyte, Magma Hound; слой правил 1: Waggle Pick), **OVERCONSERVATIVE — 2** (V'ama, Nascent Bolt),
**RULE_UNCERTAINTY + DATA_DEPENDENCY — 1** (Ultraxion). Категория UNRESOLVED как первопричина не понадобилась; внутри
карт открытыми остаются отдельные вопросы (раздел 4).

## 2. Поправки к моему независимому разбору после сравнения

Первичный документ не редактировался; поправки фиксируются здесь.

1. **Torch и Spell Damage — моя ошибка.** В первом проходе я записал «урон 8 без Spell Damage (CONFIRMED)», выведя это
   из метки `ImmuneToSpellpower`. Это перебор. В рамке B1 тот же тег стоит у 11 карт с `$`, из них 8 — split/random
   (где Spell Damage увеличивает **число** ударов, а не урон удара), а у остальных трёх — Torch, Eldritch Tentacles
   («Repeat this with 1 less damage») и Explosive Runes (`diagnostics.json → reuse.immune_to_spellpower_with_dollar`).
   Wiki «Spell Damage» утверждает, что Spell Damage усиливает почти все заклинания, включая урон Secret-ов. Поэтому
   тег правдоподобнее означает «Spell Damage учитывает процедура самой карты», а не «Spell Damage не действует»
   (**HYPOTHESIS**). Для Torch ответ **UNKNOWN**; решение Codex `UNRESOLVED` было правильным.
2. **Magma Hound.** Я не заметил в первом проходе, что «after this attacks» в v0.1 частично выражается существующим
   `ATTACK_DECLARED` + `AFTER`; пробел оказался определением роли, а не отсутствием события (раздел 3.10).
3. Остальные выводы первого прохода сравнение не изменило. Codex поднял два вопроса, которых у меня не было как
   отдельных пунктов: «реакция на призыв видит уже замороженный стол» (Frostwyrm) и «лечащая реакция после
   смертельного урона» (Nascent Bolt). Оба согласуются с G3/G9 и не меняют оценку.

## 3. Разбор по картам

### 3.1 EDR_895 — Aviana, Elune's Chosen

**Codex.** Весь текст `unexpressed`; зависимость `lunar_cycle` (UNKNOWN_RULE/CORE); решение «чьи ходы двигают цикл»
— UNRESOLVED. Предложено: `control:SCHEDULE`, `duration:THIS_GAME`, `keyword:LUNAR_CYCLE`.

**Сравнение.**
* «Чьи ходы» — отвечается wiki: отсчёт в начале **своих** трёх следующих ходов (**SUPPORTED**). У Codex это
  RULE_UNCERTAINTY из-за протокола без источников, не ошибка.
* Объём «your cards» (рука / колода / будущие карты) в журнале решений Codex **отсутствует**. На статус не влияет
  (всё равно PARTIAL), но при появлении v0.2 этот вопрос станет решающим. Замечание к журналу, не ошибка.
* Почему v0.1 действительно не хватает (**CONFIRMED** по `validate.py`/`vocabulary.py`): длительности только
  `THIS_TURN`, `UNTIL_USED`, `{turns}`; события начала хода нет; отложенного старта нет; а `ADD_PLAYER_EFFECT` по
  `R_PLAYER_EFFECT` и рендеру означает «для **следующей** подходящей карты», то есть постоянной ауры на все карты в
  v0.1 нет.

**Пример, где наивная подстановка v0.1 ошиблась бы:** `ADD_PLAYER_EFFECT {turns: 3, modifier: cost set 1}` сделал бы
карты по 1 мане **сразу** и на три хода, а затем вернул бы цены. Карта делает наоборот: ничего три хода, затем цена 1
до конца игры.

**Предложения.** `keyword:LUNAR_CYCLE` — по сути карточный элемент: «лунный цикл» встречается только здесь. Отклоняю.
`control:SCHEDULE` слишком общий и неопределённый; достаточно параметра отложенного старта у существующего
`ADD_PLAYER_EFFECT` и длительности `THIS_GAME` (см. IR_V02_PROPOSAL, E4–E6).

**Итог:** первопричина IR_LIMITATION (параметр), вторичная RULE_UNCERTAINTY (объём). v0.2 → FULL_DEP. **SUPPORTED.**

### 3.2 TIME_216 — Nascent Bolt

**Codex.** Урон `$5` по выбранному существу любой стороны выражен; «If it survives, draw 2 cards.» — `unexpressed`;
зависимость `survival` CORE; решение «когда проверять выживание» UNRESOLVED.

**Сравнение.** v0.1 уже выражает эту часть (**CONFIRMED** запуском валидатора и обоих линтеров,
`diagnostics.json → counterfactual.TIME_216`):

```json
{"seq": [{"op": "DEAL_DAMAGE", "to": {"ref": "target"}, "amount": {"n": 5, "mark": "$"}},
         {"if": {"cmp": [{"stat": "HEALTH", "of": {"ref": "target"}}, ">", 0]},
          "then": {"op": "DRAW", "player": "SELF", "count": 2}}]}
```

`R_STEP_BOUNDARY` в v0.1 уже говорит, что шаг завершается вместе с реакциями, а смерти между шагами не
обрабатываются. Это ровно правило Slam из wiki (G3): сначала урон и триггеры, потом проверка; смертельно раненая цель
не «выжила». Единственное расхождение — цель, помеченная на уничтожение (pending destroy) реакцией при Health > 0; в
v0.1 его видно только как CONDITIONAL-зависимость. Итог: FULL_DEP уже в v0.1.

**Первопричина:** OVERCONSERVATIVE (**CONFIRMED** по коду; эквивалентность правилу — **SUPPORTED**).
**Опасность обратной ошибки:** декларация с безусловным добором проходит все проверки как FULL
(`wrong_but_accepted.TIME_216/unconditional_draw`). Пример: цель — вражеское 3/3; карта не даёт карт, декларация даёт 2.

### 3.3 CATA_497 — Ultraxion

**Codex.** Весь текст `unexpressed`; зависимости `herald_runtime` (CORE), `deathwing_name` (NAME_REFERENCE/DATA),
`herald_rule` (KEYWORD_RULE/CORE); решение о плейсхолдерах UNRESOLVED.

**Сравнение.** Согласен полностью. Wiki добавляет факты, которых у Codex не было (протокол без источников): выбор
Soldier зависит от класса игрока, класса карты и класса оппонента; скидка действует на **пять** карт «с персонажем
Deathwing», а в HearthstoneJSON нет поля, по которому этот список выводится. Формула `{1}`, зона скидки и поведение при
полном столе остаются **UNKNOWN** и после wiki.

**Пример, почему плейсхолдер нельзя читать буквально:** `{1}` в тексте клиента — не число 1; после нескольких Herald
скидка больше (wiki: «Herald to improve!»), а буквальное чтение даёт всегда 1.

**Итог:** RULE_UNCERTAINTY + DATA_DEPENDENCY (первопричина), IR_LIMITATION вторична. PARTIAL верен и в v0.2 останется
PARTIAL. **SUPPORTED.**

### 3.4 CATA_452 — Spellweaver's Brilliance

**Codex.** `SUMMON CATA_452t` (DESCRIPTION_MATCH, зависимость TOKEN_IDENTITY/DATA); скидка `unexpressed`, зависимость
CORE «нет счётчика суммы урона»; решения: считать урон (TEXT), токен — UNRESOLVED.

**Сравнение.** Согласен с пробелом и добавляю второй, которого Codex не назвал: даже при наличии счётчика валидатор
не примет `reduce: {counter}`, потому что литерал «(1)» в «Costs (1) less for each…» должен совпасть с числом в IR, а
умножения в v0.1 нет (**CONFIRMED**: `probes.CATA_452/one_less_for_each_counter` → «text number 1 has no matching IR
number»). Значит, нужны два параметра: агрегирующий счётчик урона и `mul`. В рамке «(N) less/more for each»
встречается у 17 карт, так что `mul` не карточный.

Замечание к журналу: IR использует `CATA_452t`, а решение «Is the 6/6 Dragon Azure Warden?» помечено UNRESOLVED с
риском OUTCOME. Декларация одновременно выбирает и не выбирает ID. Игрового эффекта нет; это несогласованность
документации. Токен **SUPPORTED** (префикс, 6/6 Dragon, единственный кандидат).

**Пример ошибки подстановки:** счётчик `SPELL_CAST` вместо урона. Fireball на 6 урона: по карте цена 10 − 6 = 4, по
подстановке 10 − 1 = 9.

**Итог:** IR_LIMITATION (параметр) + DATA. v0.2 → FULL_DEP. **CONFIRMED.**

### 3.5 JAIL_118 — V'ama, Looming Death

**Codex.** Весь текст `unexpressed`; зависимость `class_negation` CORE: «нет предиката отрицания»; решения: обе
стороны (TEXT), мультикласс UNRESOLVED. Предложено `cond:NOT`.

**Сравнение.** Отрицание в v0.1 уже есть как разность множеств через `exclude` (**CONFIRMED** валидатором и линтерами,
`counterfactual.JAIL_118`, статус FULL_DEP):

```json
{"op": "DESTROY", "to": {"pick": "ALL", "type": "MINION", "side": "ANY",
  "exclude": [{"pick": "ALL", "type": "MINION", "side": "ANY", "where": [{"card_class": "PALADIN"}]}]}}
```

Рендер: «destroy all minions except all minions card class PALADIN». Сама V'ama — Paladin и не уничтожается.
Вопрос мультикласса (считать ли существо с Paladin среди классов) остаётся честной CONDITIONAL-зависимостью; Codex
прав, что перечислять остальные классы небезопасно.

**Первопричина:** OVERCONSERVATIVE. `cond:NOT` для этой карты не нужен.
**Опасность:** «destroy all minions» без `exclude` проходит все проверки как FULL (`JAIL_118/destroy_all`). Пример: на
столе Silver Hand Recruit и сама V'ama — по карте оба выживают, по декларации погибают.

### 3.6 CORE_BT_921 — Aldrachi Warblades

**Codex.** `keywords: [LIFESTEAL]`, FULL; решение: базовая прочность — `health=2`, а не `durability=0` (METADATA).

**Сравнение.** Совпадает (D1; wiki: прочность 2). Пилот A уже фиксировал, что у 248 из 251 коллекционного оружия
`durability = 0`. FULL корректен в смысле IR: текст полностью представлен. Это не утверждение о реализации правила
Lifesteal (взаимодействие с бонусом лечения — вопрос `R_HEALING`, не карты). **CONFIRMED.**

### 3.7 JAIL_399 — Imp Gang Stooge

**Codex.** Taunt выражен; Deathrattle `unexpressed`; зависимости `bottom_insert` CORE и `demons_identity`
TOKEN_IDENTITY/DATA; решения: дно колоды (TEXT), один или два токена — UNRESOLVED. Предложено `op:INSERT_INTO_DECK` с
`count`, `position` и `deck_position:BOTTOM`.

**Сравнение.**
* Пробел позиции реальный (**CONFIRMED**: у `SHUFFLE_INTO_DECK` только `player`, `what`; `R_DECK_POSITION` упоминает
  «bottom», но операция не принимает параметр). Но это пробел **параметра**, а не повод для новой операции.
* Токен найден у меня однозначно: `JAIL_399t1` Grandmother Imp — единственная запись с префиксом, 8/8 Demon, Taunt +
  Lifesteal, стоимость 8 (**SUPPORTED**). Для Spellweaver's и Frostwyrm Codex такие токены нашёл, здесь — нет.
  Непоследовательная политика замыкания: OVERCONSERVATIVE (вторично).

**Пример ошибки подстановки:** `SHUFFLE_INTO_DECK` ×2 проходит все проверки как FULL_DEP (`JAIL_399/shuffle_not_bottom`).
Следующий добор из непустой колоды по карте никогда не даст Grandmother Imp, по подстановке может.

**Итог:** IR_LIMITATION (параметр) + DATA. v0.2 → FULL_DEP. **CONFIRMED.**

### 3.8 CORE_SCH_713 — Cult Neophyte

**Codex.** Весь текст `unexpressed`; зависимость `next_opponent_turn` CORE; решения: заклинания оппонента (TEXT),
динамическое применение — UNRESOLVED. Предложено `duration:NEXT_OPPONENT_TURN`.

**Сравнение.** Согласен. Есть и вторая, не названная Codex причина: `ADD_PLAYER_EFFECT` в v0.1 означает «следующая
подходящая карта» (рендер прямо пишет «for the next card»), поэтому даже правильное окно не дало бы «все заклинания
оппонента в его ход». Динамическое применение отвечается аналогией с Loatheb (зачарование на игроке, действует на
заклинания в руке в его ход, снимается в конце хода; **SUPPORTED**).

**Пример ошибки подстановки:** `duration: THIS_TURN` проходит все проверки как FULL (`CORE_SCH_713/this_turn`). У
оппонента 1-мана заклинание на его следующем ходу: по карте оно стоит 2, по подстановке 1 (эффект истёк в конце
моего хода).

**Итог:** IR_LIMITATION (параметр + семантика неограниченного эффекта игрока). v0.2 → FULL (FULL_DEP, если записать
редкий случай Battlecry на ходу оппонента). **SUPPORTED.**

### 3.9 CORE_DAL_720 — Waggle Pick

**Codex.** raw: `ADD_TO_HAND(from_zone RANDOM FRIENDLY MINION)` → `MODIFY_COST(ref) reduce 2`, статус **FULL**. final:
та же структура, зависимость `return_transition` CORE, решение «сбрасывает ли перенос состояние» UNRESOLVED, статус
PARTIAL. Предложено `op:RETURN_TO_HAND`.

**Сравнение.** Структура верна в обеих версиях. Правило игры известно (wiki, G5): возврат в руку даёт исходную карту
без урона и зачарований, а при полной руке существо **уничтожается** с Deathrattle и death-триггерами. В v0.1 его нет:
`R_HAND_LIMIT` говорит «лишняя карта уничтожается», не уточняя, что для существа это смерть.

* **raw FULL — AUTHOR_ERROR (завышенный статус), CONFIRMED** самим Codex. Мой различающий пример (дополнительно к
  примеру Codex со сброшенными зачарованиями): рука полна, случайно выбрано существо с Deathrattle. По игре оно умирает
  и Deathrattle срабатывает; исполнитель, следующий букве `R_HAND_LIMIT`, сожжёт карту без Deathrattle.
* final PARTIAL верен для v0.1. Но первопричина — отсутствующее **универсальное правило** перехода PLAY→HAND, а не
  неизвестность правила игры и не отсутствие операции. `op:RETURN_TO_HAND` не нужен: достаточно правила
  `R_RETURN_TO_HAND` для существующего перемещения.

**Итог:** IR_LIMITATION (слой правил). v0.2 → FULL. **SUPPORTED.**

### 3.10 FIR_953 — Magma Hound

**Codex.** Rush выражен; триггер `unexpressed`; зависимость `attack_survival_split` CORE; решения: распределение
UNRESOLVED («text says split but does not explicitly say randomly»), субъект атаки — сам Hound (TEXT). Предложены
`event:SOURCE_ATTACK`, `pred:SURVIVES`.

**Сравнение.**
* **Split — OVERCONSERVATIVE (вторично).** Все «split among» в Hearthstone — серия случайных ударов по 1, смертельно
  раненые исключаются (wiki «Damage», «Arcane Missiles»; **SUPPORTED**). В A уже есть FULL_DEP-декларация
  `CORE_BT_201` («Deal this minion's Attack damage randomly split among all enemies») с тем же `repeat + RANDOM`, а
  `IR_SPEC.md` прямо задаёт эту кодировку.
* **Событие — настоящий, но узкий пробел.** В v0.1 есть `ATTACK_DECLARED` с полями `subject`/`defender` и тайминг
  `AFTER` («после разрешения события»). Мой CF (`counterfactual.FIR_953`) выражает весь триггер:
  `ATTACK_DECLARED{subject: SELF, defender: enemy minion} + AFTER + condition HEALTH(SELF) > 0 + repeat ATTACK(SELF)`.
  Валидатор и линтеры его принимают. Но роль `subject` у этого события в v0.1 не определена, и я честно записал её
  как CORE-зависимость, поэтому статус PARTIAL.
* **Пробел рендера (CONFIRMED):** рендер этого CF — «After a enemy minion is attacked: repeat this's attack times …».
  В нём нет ни условия выживания, ни роли атакующего. Ревьюер, проверяющий по рендеру (как рекомендовал пилот A),
  этих мест не увидит.

**Пример ошибки подстановки:** событие `HERO_ATTACK` проходит все проверки как FULL (`FIR_953/hero_attack`). Герой
атакует оружием, Hound стоит — срабатывает только подстановка.

**Итог:** IR_LIMITATION (параметр: роль атакующего), вторично OVERCONSERVATIVE. `event:SOURCE_ATTACK` заменяю
определением ролей у существующего события. v0.2 → FULL_DEP (перенаправленная атака — CONDITIONAL). **SUPPORTED.**

### 3.11 CATA_585 — Torch

**Codex.** Урон `$8` по выбранному повреждённому существу любой стороны выражен; возврат `unexpressed`; зависимости
`excess_return` CORE и `spellpower_conflict` CORE; решения: возвращается само заклинание (TEXT), Spell Damage —
UNRESOLVED. Предложены `op:RETURN_TO_HAND`, `value:EXCESS_DAMAGE`.

**Сравнение.**
* **Spell Damage — Codex прав, я ошибался** (раздел 2). При этом v0.1 не позволяет записать «$ без усиления»:
  валидатор отвергает урон без метки, если в тексте `$8` (**CONFIRMED**, `probes.CATA_585/ImmuneToSpellpower_without_mark`).
  Контракт меток в v0.1 конфликтует с картами, у которых Spell Damage обрабатывает сама процедура.
* **Excess** в простом случае вычисляется арифметикой v0.1 (`set h = HEALTH(target)` до удара, `max(0, 8 − h)` после),
  как в A у BE_555. Для Divine Shield wiki описывает аналоги (Piercing Shot, Rolling Fireball, Explosive Runes): щит
  поглощает урон, равный Health. Это даёт ту же формулу. Поэтому `value:EXCESS_DAMAGE` для Torch не нужен. Он может
  понадобиться картам, где excess считается от урона с Spell Damage (например Sindragosa's Triumph `$8`), — отложено.
* **Настоящий пробел — структурный.** Нужно вернуть **эту же** карту в руку с изменённым числом урона. В v0.1 нет
  способа изменить число в тексте экземпляра карты: у `ENCHANT` только атака, здоровье, ключевые слова, способности и
  Spell Damage. Это параметр экземпляра (instance parameter), тот же механизм нужен плейсхолдерам `{0}/{1}` (36 карт
  рамки). `op:RETURN_TO_HAND` при этом не нужен: перемещение уже есть, нужен `R_RETURN_TO_HAND` и параметр.
* Граничные правила (**UNKNOWN**): полная рука; Immune-цель; Divine Shield именно у Torch.

**Пример ошибки подстановки:** возврат, спрятанный в `reminders`, проходит все проверки как FULL
(`CATA_585/reminder_loophole`). Цель — повреждённое существо с 2 Health: по карте в руку вернётся Torch(6), по
декларации карта потеряна.

**Итог:** IR_LIMITATION (структура) + RULE_UNCERTAINTY. Без параметра экземпляра — PARTIAL и в v0.2; с ним — FULL_DEP
(Spell Damage, Divine Shield, полная рука — CONDITIONAL). **SUPPORTED/UNKNOWN.**

### 3.12 CORE_RLK_063 — Frostwyrm's Fury

**Codex.** Две отдельные `play`-способности: урон `$5` по любому персонажу и `SUMMON RLK_063t` (NAME_IN_SET, DATA);
Freeze `unexpressed`; зависимость `freeze` CORE; решения: порядок урон → заморозка → призыв (TEXT), цель — любой
персонаж (TEXT). Предложен `op:FREEZE`.

**Сравнение.** Согласен. FREEZE отсутствовал в v0.1 и был в списке пробелов пилота A (`IR_SPEC.md` §10, 4 декларации
ManaEngine). Токен `RLK_063t` (5/5, **Undead + Dragon**) — **SUPPORTED**. Замечание к представлению: две `play`-способности
вместо одной `seq`. Спецификация v0.1 не задаёт порядок между способностями. Codex сам пометил, что фрагменты не
являются исполнимым целым, поэтому это не ошибка, но в v0.2 должна быть одна последовательность.

**Пример ошибки подстановки:** «Freeze all enemy minions.» в `reminders` проходит все проверки как FULL_DEP
(`CORE_RLK_063/reminder_loophole`). Вражеские существа атакуют в следующем ходу, хотя карта их заморозила.

**Итог:** IR_LIMITATION (структура: FREEZE) + DATA. v0.2 → FULL_DEP. **CONFIRMED.**

## 4. Проверка статусов

### 4.1 FULL / FULL_DEP / PARTIAL / UNSUPPORTED

* **FULL (1):** Aldrachi Warblades — верно.
* **Ложных FULL в итоговых декларациях нет.** В первичных — один: Waggle Pick (исправлен автором; автоматические
  проверки его пропустили).
* **FULL_DEP (0):** при лучшем авторстве v0.1 их было бы два (V'ama, Nascent Bolt).
* **UNSUPPORTED (0):** верно, ни одна карта не требует карточной логики.
* **PARTIAL (11)**, причины по картам (первопричина):

| Причина PARTIAL | Карт | Какие |
|---|---:|---|
| Действительно отсутствует универсальная операция / структура | 2 | Frostwyrm's Fury (FREEZE), Torch (параметр экземпляра) |
| Недостаёт параметра, значения или роли у существующего элемента | 5 | Aviana, Spellweaver's, Imp Gang Stooge, Cult Neophyte, Magma Hound |
| Нет универсального правила в слое `R_*` (правило игры известно) | 1 | Waggle Pick |
| Неизвестное правило игры + внешние данные | 1 | Ultraxion |
| Неверное или излишне осторожное решение автора | 2 | V'ama, Nascent Bolt |

### 4.2 Решения UNRESOLVED (10) — что из них отвечается источниками

| Карта | Вопрос Codex | Мой ответ | Уровень |
|---|---|---|---|
| Aviana | чьи ходы двигают цикл | только свои | SUPPORTED (wiki notes) |
| Nascent Bolt | когда проверять выживание | после реакций, до Death Phase; pending destroy = не выжил | SUPPORTED (Slam notes) |
| Ultraxion | значения плейсхолдеров | клиентские, формула неизвестна | UNKNOWN (частично) |
| Spellweaver's | токен | `CATA_452t` | SUPPORTED |
| V'ama | мультикласс | — | UNKNOWN (HYPOTHESIS: «Paladin среди классов») |
| Imp Gang Stooge | один или два токена | две копии `JAIL_399t1` | SUPPORTED |
| Cult Neophyte | динамическое применение | да, включая новые заклинания | SUPPORTED (Loatheb) |
| Waggle Pick | сброс состояния при возврате | сброс; полная рука → смерть | SUPPORTED (wiki) |
| Magma Hound | распределение split | случайные удары по 1, живые цели | SUPPORTED (wiki) |
| Torch | Spell Damage | — | UNKNOWN |

7 из 10 отвечаются проверяемыми, хоть и не официальными источниками; 3 остаются открытыми. Значит, заметная доля
«неизвестных правил» B1 — следствие запрета источников в протоколе, а не реальной неизвестности.

### 4.3 Структурная валидность ≠ игровая корректность

Валидатор вычисляет статус только из наличия `unexpressed` и зависимостей (`implied_status`). Поэтому:

* ни одна из 12 итоговых деклараций не содержит игровой ошибки — но лишь потому, что Codex почти ничего спорного не
  закодировал (в 7 из 12 деклараций `abilities: []`);
* правдоподобная **неверная** декларация обычно проходит всё. Из 9 намеренно неверных деклараций
  (`diagnostics.json → wrong_but_accepted`) **8 приняты без единого предупреждения**, из них 6 — как FULL и 2 как
  FULL_DEP. Поймана только одна (сторона ENEMY без слова «enemy» — старый линтер).

| Ошибка | Принята? | Статус | Игровой пример |
|---|---|---|---|
| Nascent Bolt: безусловный добор | да | FULL | вражеское 3/3 умирает, добор 2 вместо 0 |
| V'ama: «destroy all minions» | да | FULL | Silver Hand Recruit и сама V'ama гибнут |
| V'ama: только враги | **нет** (old lint) | — | контроль |
| Imp: shuffle вместо дна колоды | да | FULL_DEP | следующий добор может быть 8/8 |
| Neophyte: `THIS_TURN` | да | FULL | заклинание оппонента в его ход дешевле на 1 |
| Magma Hound: `HERO_ATTACK` | да | FULL | срабатывает от атаки героя оружием |
| Torch: возврат в `reminders` | да | FULL | Torch(6) не возвращается |
| Frostwyrm: Freeze в `reminders` | да | FULL_DEP | враги не заморожены |
| Aviana: весь текст в `reminders` | да | FULL | пустая декларация, рендер пуст |

Последние три случая — общий лаз: спаны `reminders` не проверяются по содержанию, не рендерятся и не понижают статус.
Это детерминированно исправимо (IR_V02_PROPOSAL, §6). Остальные пять — смысловые ошибки на уровне условия, окна
времени, позиции в колоде, субъекта события и отрицания. Часть из них ловится новыми лексическими якорями, но в общем
случае нужна независимая семантика.

## 5. Итоговые числа аудита

* **Подтверждённые ошибки Codex (AUTHOR_ERROR): 1** — завышенный FULL у первичного Waggle Pick, исправлен самим автором.
  В итоговых декларациях игровых ошибок **0**. Замечания к документации (не ошибки): несогласованность токена у
  Spellweaver's, разная политика замыкания токенов (Imp против Spellweaver's/Frostwyrm), отсутствие вопроса об объёме
  у Aviana, две `play`-способности вместо `seq` у Frostwyrm.
* **OVERCONSERVATIVE: 2 как первопричина** (V'ama, Nascent Bolt) **+ 2 вторичных** (split у Magma Hound, токен у Imp).
* **IR_LIMITATION: 8 карт как первопричина**; различных пробелов — 1 структурная операция (FREEZE), 1 структурный
  механизм (параметр экземпляра), 9 параметров/значений/ролей у существующих элементов (+1 необязательный предикат
  `alive`) и 1 универсальное правило возврата в руку (полный список — IR_V02_PROPOSAL, §3).
* **RULE_UNCERTAINTY:** 1 как первопричина (Ultraxion); как CONDITIONAL внутри карт — объём «your cards» у Aviana,
  мультикласс у V'ama, Spell Damage / Divine Shield / полная рука у Torch, pending destroy у Nascent Bolt.
* **DATA_DEPENDENCY:** Ultraxion (семейство Deathwing, таблица Soldier) и 3 токена (Spellweaver's, Imp, Frostwyrm);
  особенность прочности оружия у 2 карт (учтена).
* Моя поправка к собственному первому проходу: 1 (Spell Damage у Torch).
