# Card IR v0.1 — спецификация прототипа

Исследовательский прототип CARD-IR-PILOT-1. Авторитетный список элементов — `src/manamind/card_ir/vocabulary.py`,
проверка — `validate.py`, обратный рендер — `render.py`, лексические якоря — `lint.py`. Модель, LIVE, ManaEngine и
обучение этот пакет не импортируют (тест изоляции).

## 1. Принципы

1. **Только данные.** Декларация — JSON. В ней нет кода, ссылок на функции движка и карточных веток.
2. **Независимость от исполнителя.** Смысл каждого элемента задаётся этой спецификацией и списком *универсальных
   правил* (`R_*`), а не реализацией. Будущий Python- или C++-исполнитель обязан реализовать правила одинаково и пройти
   один и тот же набор conformance-сценариев.
3. **Пять слоёв разделены явно:**

   | Слой | Где живёт | Пример |
   |---|---|---|
   | Универсальные правила Hearthstone | `RULES` (`R_DEATH_PHASE`, `R_RANDOM_LIVE`, …) — один раз для всех карт | смерти обрабатываются на границе фазы |
   | Конкретный эффект карты | `abilities` декларации | `DEAL_DAMAGE 3$` по выбранной цели |
   | Условия и цели | селекторы, предикаты, условия внутри `abilities` | «случайный вражеский миньон с Taunt» |
   | Внешние зависимости и неизвестные правила | `dependencies` (типизированные), «дыры» `{"unknown": dep}` | членство пула Discover, «что значит Improve» |
   | Порядок применения | `seq` + универсальные правила шага | «Silence, затем destroy» |

4. **Неизвестное не выдумывается.** То, что текст не определяет, записывается как зависимость или как явная «дыра»
   `unknown`, а статус карты понижается автоматически.
5. **Словарь растёт по данным.** Элемент добавлялся, только когда его требовала карта выборки; неиспользуемые элементы
   удалены (тест: каждый элемент и каждое правило используется хотя бы одной декларацией).

## 2. Документ декларации

| Поле | Обязательно | Смысл |
|---|---|---|
| `ir` | да | `card-ir/0.1` |
| `card_id`, `snapshot` | да | ID и закреплённый снимок HearthstoneJSON (`hsjson_255130_enUS`) |
| `role` | да | `sample` / `closure` (токены и создаваемые карты выборки) / `engine_validation` |
| `text`, `text_sha256` | да | `strip_text_artifacts(text)`: разметка, `[x]`, `$`, `#` сохранены; хеш привязывает декларацию к тексту |
| `keywords` | нет | ключевые слова-правила: `{keyword, span, amount?, parts?}` |
| `abilities` | да | способности карты (раздел 3) |
| `reminders` | нет | фрагменты текста, которые не являются правилом (напоминания) |
| `unexpressed` | нет | фрагменты, которые IR не выражает, с причиной |
| `dependencies` | да | типизированные внешние зависимости (раздел 8) |
| `decisions` | да | журнал решений интерпретации (раздел 8) |
| `status` | да | `FULL` / `FULL_DEP` / `PARTIAL` / `UNSUPPORTED` (раздел 8) |

**Текстовая подотчётность.** Каждая способность и каждое ключевое слово несут `span` — точную подстроку нормализованного
текста. Спаны не пересекаются и вместе покрывают **каждое слово** текста. Каждое число в спане должно найтись среди чисел
IR под этим спаном (литералы, статы созданного токена) **с той же меткой `$`/`#`**; метку нельзя ни потерять, ни
добавить.

## 3. Способности

| `kind` | Поля | Семантика |
|---|---|---|
| `play` | `label` (`SPELL`, `BATTLECRY`, `LOCATION`, `KINDRED`), `target?`, `condition?`, `effect` | эффект розыгрыша, каста или активации. `target = {bind, choose}` — цель, выбранная при розыгрыше (`R_PLAY_TARGET`) |
| `trigger` | `event`, `timing`, `effect`, `label?` (`SECRET`), `condition?`, `limit?` (`FIRST_EACH_TURN`), `active_in?` | реакция на событие, пока карта в активной зоне (по умолчанию `PLAY`; оружие — `EQUIPPED`) |
| `deathrattle` | `effect` | эффект при смерти (`R_DEATHRATTLE`, `R_DEATH_PHASE`) |
| `aura` | `active_in` (`PLAY`/`HAND`/`EQUIPPED`), `modifier`, `while?` | непрерывный модификатор, пересчитывается между шагами (`R_AURA`) |
| `quest` | `progress {event, goal}`, `reward` | механика Quest (`R_QUEST`) |
| `enchantment_template` | `context` (`DARK_GIFT`), `attack?`, `health?`, `keywords?` | карта, которая является зачарованием для другой механики |

Внутри способностей, прикреплённых зачарованием (`ENCHANT.abilities`) или эффектом игрока, `SELF` означает **носителя**.

## 4. Эффекты и порядок

| Узел | Семантика |
|---|---|
| `{"seq": [...]}` | шаги по порядку; шаг завершается вместе с вызванными реакциями до начала следующего; смерти между шагами **не** обрабатываются (`R_STEP_BOUNDARY`) |
| `{"if": cond, "then": e, "else"?: e}` | условие вычисляется в момент достижения |
| `{"repeat": value, "do": e}` | число повторов вычисляется **один раз**; каждый повтор — отдельный шаг |
| `{"repeat_while": cond, "do": e, "max": int или unknown}` | условный цикл с обязательной границей (`R_LOOP_BOUND`) |
| `{"set": {"x": value}}` | локальная переменная резолюции, читается через `{"var": "x"}` |
| `{"pay": cost, "then": e}` | эффект выполняется, только если цена оплачена целиком (`R_PAYMENT`); цена — `{resource, amount}` (`ARMOR`, `CORPSE`) или `{discard: selector}` |
| `{"op": ..., ..., "as"?: name}` | операция; `as` связывает созданные или затронутые сущности («it», «them») |

**Связывание.** Каждое `ref`/`var` должно быть связано раньше в той же резолюции, и каждое связанное имя должно
использоваться (иначе «it» почти наверняка указывает не туда).

## 5. Операции (15)

| Операция | Аргументы | Правила исполнителя |
|---|---|---|
| `DEAL_DAMAGE` | `to`, `amount` | `R_DAMAGE` |
| `RESTORE_HEALTH` | `to`, `amount` | `R_HEALING` |
| `ENCHANT` | `to`, `attack?`, `health?`, `keywords?`, `abilities?`, `spell_damage?`, `duration?`, `enchantment_id?` | `R_ENCHANTMENT`; объединяет бафф, выдачу ключевого слова и прикреплённые триггеры |
| `SILENCE`, `DESTROY` | `to` | `R_SILENCE`, `R_DEATH_PHASE` |
| `TRANSFORM` | `to`, `into` | `R_TRANSFORM` |
| `SUMMON` | `what`, `count?` | `R_SUMMON_POSITION`, `R_BOARD_LIMIT` |
| `DRAW` | `player`, `count?`, `where?` | `R_DRAW` |
| `ADD_TO_HAND` | `player`, `what`, `count?` | `R_HAND_LIMIT` |
| `DISCOVER` | `pool`, `options?` | `R_DISCOVER` |
| `CHOOSE` | `from` (CHOSEN) | `R_CHOICE` |
| `MODIFY_COST` | `to`, `reduce` или `set`, `enchantment_id?` | `R_COST` |
| `ADD_PLAYER_EFFECT` | `player`, `duration`, `modifier` или `abilities`, `uses?`, `use_unit?`, `applies_to?`, `enchantment_id?` | `R_PLAYER_EFFECT`; «your next…», «lasts N turns» |
| `SHUFFLE_INTO_DECK` | `player`, `what` | `R_DECK_POSITION`, `R_HIDDEN_ZONE` |
| `CAST` | `what`, `count?` | `R_CAST` |

## 6. Селекторы, источники карт, пулы

- Короткие селекторы: `SELF`, `ENEMY_HERO`, `ENEMY_WEAPON`; связанные: `{"ref": name}`.
- Запрос: `{"pick": ALL|RANDOM|CHOSEN, "type", "side": FRIENDLY|ENEMY|ANY, "zone"?: PLAY|HAND|DECK|[...], "n"?, "where"?: [pred], "exclude"?: [...]}`.
  `ALL` фиксирует состав в начале шага, смертельно раненые включены (`R_AREA_SNAPSHOT`); `RANDOM` выбирает только среди
  живых и пересчитывается на каждый выбор (`R_RANDOM_LIVE`); `CHOSEN` допустим только в цели розыгрыша и в `CHOOSE`.
- Предикаты: `keyword`, `card_type`, `card_set`, `race`, `spell_school`, `cost {cmp, n}`, `damaged`, `has_mechanic`,
  `card_class`, `named {named, ids, dep}`.
- Источники карт: `{"card", "resolved", "dep"?}`, `{"copy_of"}`, `{"random_from": pool}`, `{"all_from": pool, "exclude"?}`,
  `{"from_zone": selector}`. `resolved` говорит, как ID найден по тексту: `UNIQUE_NAME` (единственная игровая запись с
  этим именем, проверяется), `NAME_IN_SET`, `DESCRIPTION_MATCH`, `AMBIGUOUS` — последние три требуют зависимости
  `TOKEN_IDENTITY`. В HearthstoneJSON нет связи «карта → её токены», поэтому это эвристика.
- **Пул:** `{"type", "where", "dep"}`. Членство пула — всегда внешний манифест из зависимости `POOL_MEMBERSHIP`;
  `where` — ограничения из текста, которым манифест обязан удовлетворять. Пул никогда не угадывается по тексту.

## 7. Значения, условия, события

- Значения: целое число; `{"n", "mark": "$"|"#"}` (`$` — Spell Damage, `#` — лечение; правило `R_SPELL_DAMAGE`,
  `R_HEALING`, порядок с множителями — `R_AMOUNT_ORDER`); `{"stat", "of", "at": CURRENT|LAST_KNOWN}`; `{"counter":
  {event, player, scope, where?, distinct?}}`; `{"var"}`; `{"add"|"sub"|"max": [a, b]}`; `{"unknown": dep}`.
  Для «randomly split» метка `$` стоит на **числе повторов**, а каждый удар — 1 без метки (подтверждается тегом
  `ImmuneToSpellpower` у всех таких карт рамки).
- Условия: `cmp`, `exists`, `is {entity, where}`, `mechanic` (`KINDRED`), `unknown`.
- События: `HERO_ATTACK`, `CARD_DRAWN`, `TURN_END`, `DAMAGE_TAKEN`, `DAMAGE_DEALT`, `ATTACK_DECLARED`; тайминги `AFTER`,
  `WHENEVER`, `AT`, `WHEN` (`R_TRIGGER_TIMING`). Событие тоже может быть дырой `{"unknown": dep}`.
- Длительности: `THIS_TURN`, `UNTIL_USED`, `{"turns": n}`. Модификаторы: `cost {set|reduce}`, `rule` (`SPELL_DAMAGE_MULTIPLIER`,
  `SPELL_HEALING_MULTIPLIER`, `HEALING_DOES_DAMAGE`), `spell_damage`.

## 8. Зависимости, решения, статус

**Зависимость** `{id, kind, scope, detail, source_needed, card_level?}`:

| `kind` | Что это |
|---|---|
| `POOL_MEMBERSHIP` | состав случайного пула или Discover |
| `TOKEN_IDENTITY` | какой ID создаёт карта, если текст не называет его однозначно |
| `NAME_REFERENCE` | «Medivh», «Atiesh»: каким ID соответствует имя в тексте |
| `KEYWORD_RULE` | правило механики, которого нет в тексте карты (Tradeable, Fabled, Kindred, Quest, Corpse, Prepare) |
| `UNKNOWN_RULE` | открытый вопрос правил |

`scope`: `DATA` (нужны данные, а не решение по правилу), `CONDITIONAL` (влияет только при определимом дополнительном
условии), `CORE` (влияет на обычную игру).

**Решение** `{id, question, alternatives, chosen, basis, risk, discriminating_case?, dep?}` фиксирует каждое место, где
автор выбирал прочтение. `basis`: `TEXT`, `METADATA`, `PROJECT_REVIEWED`, `LOG_OBSERVED`, `COMMUNITY_RULES`,
`UNVERIFIED`, `ASSUMPTION`, `UNKNOWN`; `risk`: `OUTCOME`, `EDGE`, `NONE`. Правила валидатора: прочтение, меняющее исход
(`OUTCOME`), без источника (`UNVERIFIED`/`ASSUMPTION`/`UNKNOWN`) обязано ссылаться на зависимость; `UNKNOWN` не выбирает
прочтение (`chosen = UNRESOLVED`); у рискованного прочтения есть различающий случай — наблюдение, на котором альтернативы
расходятся (мутанты по смыслу FUTURE-ARCHITECTURE-RESEARCH-1, 3.4).

**Статус вычисляется, а не назначается:** `PARTIAL`, если есть невыраженный фрагмент или зависимость `CORE`; иначе
`FULL_DEP`, если есть любая зависимость; иначе `FULL`. Объявленный статус обязан совпасть с вычисленным
(`UNSUPPORTED` — только с невыраженными фрагментами).

## 9. Универсальные правила

40 правил `R_*` в `vocabulary.py`, у каждого основание: `PROJECT_REVIEWED` 15, `UNVERIFIED` 13, `UNKNOWN` 10,
`COMMUNITY_RULES` 2. Валидатор выводит из элементов декларации, какие правила ей нужны: это и есть список требований к
будущему исполнителю для этой карты.

## 10. Чего в v0.1 нет (известные пробелы)

- **Ссылки на способность другой карты** («your Cannoneers FIRE!» у Hand Cannon): у способностей нет ID.
- Из переписи ManaEngine: `GAIN_ARMOR`, `FREEZE`, селекторы своего героя и оружия, условие «если цель умерла», события
  «разыгран спелл» и «сыгран миньон», `Choose One`, `Shatter`, `Counter`, «наибольшее Health», «бесконечный» урон,
  «до полного здоровья», «владелец цели», бонус лечения, условие на атаку (19 элементов для поддержанных деклараций,
  22 вместе с неподдержанными; раздел 5 отчёта).
- Значения, которые клиент подставляет в текст во время игры (`{0}`, многосостоянийный текст с `@`): IR может хранить
  их только как дыру `unknown`.
- Порядок внутри одного шага (пересчёт ауры посреди области урона) — вопрос универсальных правил (`R_AURA`), а не
  декларации.
