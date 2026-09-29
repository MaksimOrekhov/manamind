## Контекст

В процессе разработки выяснилось, что одним из главных bottleneck проекта стала не сама нейросеть, а актуальность Hearthstone simulator.

RosettaStone предоставляет полезную основу:

- game loop;
- players;
- entities;
- zones;
- combat;
- mana;
- triggers;
- auras;
- targeting;
- death processing;
- базовые mechanics;
- Python bindings.

Однако его набор реализованных карт сильно отстаёт от современного Hearthstone.

Сейчас добавление актуальных карт вручную по одной оказывается очень дорогим процессом:

```text
card
↓
исследование похожих реализаций
↓
C++ implementation
↓
tests
↓
build
↓
debug
↓
следующая card
```

При большом количестве отсутствующих карт такой подход масштабируется плохо.

Поэтому хотелось бы рассмотреть изменение стратегии.

Это НЕ жёсткое требование реализовать именно описанную ниже архитектуру.

У тебя есть доступ к текущему коду, уже выполненной работе и внутренней архитектуре RosettaStone, поэтому сначала оцени предложенный подход и при необходимости измени, упрости или замени его более подходящим решением.

Главная цель:

> значительно сократить количество ручной работы, необходимой для добавления современных карт.

---

# 1. Временно не делать массовый перенос карт по одной

Предлагается пока не продолжать механически реализовывать десятки или сотни следующих карт тем же способом.

Сначала стоит проанализировать:

- какие типы карточных эффектов повторяются;
- какие RosettaStone primitives уже существуют;
- какие современные карты можно выразить через существующие primitives;
- какие новые primitives дали бы максимальное увеличение coverage;
- можно ли сделать часть карточного контента data-driven;
- можно ли автоматически генерировать часть implementation/tests.

Если после анализа окажется, что ручной путь всё-таки рациональнее для определённых категорий карт — это нормально.

Но хотелось бы сначала проверить возможность существенно более масштабируемого подхода.

---

# 2. Основная гипотеза

Вместо модели:

```text
1 card
→
1 custom C++ implementation
```

попробовать приблизиться к:

```text
card
↓
normalized effect description
↓
reusable mechanics / tasks
↓
generic runtime or code generator
```

То есть масштабировать разработку скорее по количеству уникальных mechanics/effects, чем по количеству карт.

Условно:

```text
O(number of cards)
```

хотелось бы приблизить к:

```text
O(number of mechanics)
```

насколько это вообще возможно в архитектуре RosettaStone.

---

# 3. Сначала провести аудит существующих возможностей RosettaStone

Перед проектированием новой системы желательно автоматически или полуавтоматически собрать список уже существующих building blocks.

Например:

```text
Tasks
Triggers
Auras
Conditions
Target selectors
Enchantments
Card helpers
GameTags
Reusable utilities
```

Нужна карта возможностей примерно такого вида:

```text
DAMAGE
    available:
        DamageTask
        ...
        
HEAL
    available:
        HealTask
        HealFullTask

DRAW
    available:
        DrawTask

SUMMON
    available:
        SummonTask

DESTROY
    available:
        ...

BUFF
    available:
        ...

TRANSFORM
    ...

DISCOVER
    ...

ADD_CARD
    ...

COPY
    ...

SILENCE
    ...

FREEZE
    ...
```

Названия здесь условные.

Используй реальные abstractions RosettaStone.

Цель такого аудита — понять, сколько современных карт уже можно представить без добавления новой низкоуровневой логики.

---

# 4. Проанализировать уже вручную добавленные нами современные карты

Очень полезно использовать уже проделанную работу как dataset для проектирования automation.

Посмотри:

- какие карты уже добавлялись;
- какие фрагменты реализации повторяются;
- какие тестовые сценарии повторяются;
- какие новые mechanics пришлось добавить;
- какие implementations отличаются только параметрами;
- какие cards могли бы быть описаны декларативно.

Например может оказаться, что множество карт фактически различаются только:

```text
trigger
target
amount
condition
```

при одинаковой основной операции.

Это хорошие кандидаты на автоматизацию.

---

# 5. Рассмотреть промежуточное представление Card Effect IR

Один из возможных вариантов — ввести внутреннее декларативное представление эффекта карты.

Например условный Card IR:

```json
{
  "trigger": "BATTLECRY",
  "conditions": [],
  "effects": [
    {
      "type": "DAMAGE",
      "target": "ALL_ENEMY_MINIONS",
      "amount": 3
    }
  ]
}
```

Это только пример.

Не нужно копировать именно эту schema.

Нужно сначала посмотреть, какие concepts действительно существуют в RosettaStone.

Возможные категории:

```text
Trigger

Effect

TargetSelector

Condition

ValueExpression

Sequence

RandomChoice

Repeat

Aura

Enchantment
```

Например карта:

```text
Battlecry:
Deal 2 damage to all enemy minions.
Draw a card.
```

могла бы концептуально стать:

```text
trigger = BATTLECRY

effects:
    Damage(
        target = ALL_ENEMY_MINIONS,
        amount = 2
    )

    Draw(
        player = SELF,
        amount = 1
    )
```

---

# 6. Не обязательно генерировать C++

Стоит рассмотреть как минимум два варианта.

### Вариант A — code generation

```text
Card IR
↓
generator
↓
RosettaStone C++ card definition
```

Преимущества:

- минимальные изменения существующего runtime;
- generated code ведёт себя как обычные RosettaStone cards;
- проще интегрировать с существующими tests/build.

### Вариант B — data-driven runtime

```text
Card IR
↓
generic effect interpreter
↓
RosettaStone Tasks / game operations
```

В таком случае одна generic implementation могла бы исполнять множество cards без отдельного C++ definition.

Это потенциально более масштабируемо, но может требовать более серьёзного изменения архитектуры.

Не нужно заранее выбирать вариант.

Проанализируй текущий RosettaStone и предложи наиболее безопасный путь.

Возможен и hybrid:

```text
простые карты
→ data-driven

сложные карты
→ generated / custom C++
```

---

# 7. Классификация карт по сложности

Предлагается автоматически классифицировать карты примерно по уровням.

Названия категорий могут быть другими.

## Tier A — полностью декларативные

Простые эффекты:

```text
Deal X damage
Heal X
Draw X
Gain X Armor
Summon X
Destroy target
Buff +X/+Y
Freeze
Silence
Taunt
Rush
Divine Shield
Lifesteal
etc.
```

Для таких карт хотелось бы минимизировать ручной код.

---

## Tier B — композиция известных эффектов

Например:

```text
Deal 3 damage.
If the target dies, draw a card.
```

или:

```text
Summon two minions, then give them +1/+1.
```

Если primitives уже существуют, карта должна по возможности собираться из них.

---

## Tier C — отсутствующая reusable mechanic

Например новая mechanic дополнения используется в 15–30 картах.

В таком случае лучше один раз реализовать:

```text
new mechanic / task / condition / selector
```

после чего автоматически или почти автоматически поддержать все карты, использующие её.

Приоритизация таких mechanics может дать огромный выигрыш.

---

## Tier D — уникальная карта

Очень специфичные legendary effects, которые трудно выразить общим DSL.

Их нормально продолжать писать вручную.

Цель не в том, чтобы сделать 100% карт декларативными.

Даже автоматизация 60–80% карточного пула уже будет очень полезна.

---

# 8. Автоматическая классификация актуального пула

Было бы полезно взять не весь Hearthstone сразу, а репрезентативную выборку современных карт.

Например:

```text
50–100 cards
```

или другой размер, который сочтёшь разумным.

Для каждой карты определить:

```text
AUTO
COMPOSABLE
MISSING_PRIMITIVE
CUSTOM
UNKNOWN
```

И получить статистику вроде:

```text
100 modern cards

42 — expressible directly
28 — expressible through composition
18 — require missing reusable primitive
9  — unique custom behavior
3  — unclear
```

Это пока пример.

Реальные цифры намного важнее.

На основе результата уже решить, насколько data-driven подход оправдан.

---

# 9. HearthstoneJSON как источник metadata

Для актуальных cards желательно по возможности автоматически использовать HearthstoneJSON.

Например:

```text
id
dbfId
name
type
cost
attack
health
mechanics
cardClass
race
text
referencedTags
```

Но важно различать:

```text
metadata
```

и:

```text
executable behavior
```

Не стоит предполагать, что HearthstoneJSON полностью описывает логику карты.

Он скорее источник card metadata и input для классификации/parser.

---

# 10. Возможность использования Codex/LLM для Card → IR

Ещё один вариант ускорения — использовать самого Codex как offline parser.

Например pipeline:

```text
HearthstoneJSON entry
+
card text
+
known RosettaStone primitives
↓
Codex
↓
strict Card IR JSON
↓
schema validation
↓
codegen/runtime
```

Важно, чтобы LLM по возможности не генерировала напрямую произвольный C++ для каждой карты.

Желательно, чтобы она формировала ограниченное структурированное representation.

Например:

```json
{
  "trigger": "...",
  "target": "...",
  "effects": [...]
}
```

после чего deterministic code решает, как это исполнять.

Это должно уменьшить число hallucination bugs и сделать систему более проверяемой.

Но если после анализа окажется, что direct code generation надёжнее — можно выбрать другой вариант.

---

# 11. Schema validation

Если появляется Card IR, желательно сделать строгий validator.

Например:

```text
unknown effect
unknown target
invalid target/effect combination
missing amount
unsupported trigger
```

должны приводить не к молчаливой неправильной реализации, а к:

```text
UNSUPPORTED
```

или понятной diagnostic error.

Для simulator correctness лучше отказаться от auto-generation карты, чем создать неправильную механику.

---

# 12. Capability registry

Хорошей частью системы может стать machine-readable registry того, что simulator уже умеет.

Условно:

```json
{
  "effects": [
    "DAMAGE",
    "HEAL",
    "DRAW",
    "SUMMON",
    "DESTROY"
  ],
  "targets": [
    "SELF_HERO",
    "ENEMY_HERO",
    "FRIENDLY_MINION",
    "ENEMY_MINION",
    "ALL_ENEMY_MINIONS"
  ],
  "triggers": [
    "BATTLECRY",
    "DEATHRATTLE",
    "START_OF_TURN",
    "END_OF_TURN"
  ]
}
```

Реальная структура может быть совершенно другой.

Это позволит автоматически отвечать:

```text
может ли текущий engine выразить эту карту?
```

---

# 13. Missing primitives report

Очень полезно автоматически получать статистику:

```text
unsupported cards grouped by missing primitive
```

Например:

```text
DISCOVER_FROM_DECK
    affects 18 cards

REPLAY_SPELL
    affects 12 cards

COPY_DEATHRATTLE
    affects 9 cards

SWAP_COST
    affects 3 cards
```

Тогда можно выбирать следующий implementation не по принципу:

```text
какую следующую карту добавить?
```

а:

```text
какая новая primitive разблокирует больше всего карт?
```

Это может значительно ускорить coverage.

---

# 14. Автоматическая генерация tests

Если простые cards описываются через IR, стоит рассмотреть генерацию базовых tests.

Например:

```text
DAMAGE 3 → enemy minion
```

может автоматически создать scenario:

```text
enemy minion health = 5
play card
expect health = 2
```

Для:

```text
DRAW 2
```

можно проверить:

```text
handSize + 2
deckSize - 2
```

Для:

```text
SUMMON
```

проверить появление entity на board.

Не все tests можно генерировать автоматически.

Но даже базовые smoke tests для простых effects могут сильно сэкономить время.

---

# 15. Differential / reference testing

Если есть возможность использовать уже реализованную аналогичную карту как reference, это тоже можно автоматизировать.

Например новая карта отличается только:

```text
damage = 4
```

от уже существующей:

```text
damage = 3
```

Можно использовать одинаковый test template.

Если такой подход плохо вписывается в RosettaStone, его не обязательно реализовывать.

---

# 16. Не стремиться сразу поддерживать все карты Hearthstone

Для AI проекта намного важнее поддержать карты, которые реально встречаются в матчах.

Можно создать отдельный concept:

```text
Target Card Pool
```

Он может строиться из:

- наших decklists;
- популярных meta decks;
- generated tokens;
- discover pools;
- relevant neutral cards.

Например:

```text
Top N meta decks
↓
unique card IDs
↓
dependencies / tokens
↓
target support set
```

После этого измерять:

```text
meta coverage
```

а не coverage всех существовавших Hearthstone cards.

---

# 17. Coverage report

Было бы полезно иметь command/report примерно такого типа:

```text
Current target pool:

421 unique cards

Fully supported:
356

Partially supported:
18

Unsupported:
47

Coverage:
84.6%
```

И дополнительно:

```text
Top missing primitives:
...
```

Можно также считать coverage по deck:

```text
Priest deck     30/30
Warlock deck    29/30
Paladin deck    27/30
...
```

Так будет понятно, какие matchup уже можно безопасно использовать для self-play.

---

# 18. Dependencies / generated cards

При анализе одной карты важно учитывать карты, которые она создаёт:

```text
tokens
generated spells
transforms
hero powers
weapons
locations
```

Поэтому target card pool желательно расширять транзитивными dependencies, насколько это можно определить.

Например:

```text
Card A
→ summons Token B
→ Token B deathrattle summons C
```

Все три могут понадобиться simulator.

---

# 19. Correctness важнее coverage

Очень важно не получить ситуацию:

```text
95% cards technically load
```

но множество из них работают неправильно.

Для training simulator correctness критичен.

Неправильный simulator будет обучать нейросеть неправильной игре.

Поэтому желательно различать:

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNVERIFIED
UNSUPPORTED
```

Если mechanic непонятна — лучше оставить карту unsupported.

---

# 20. Ручные карты всё равно оставить

Даже если появится declarative system, custom implementation должна остаться нормальным вариантом.

Например:

```text
90% cards → IR
10% cards → custom C++
```

Это абсолютно приемлемый результат.

Не нужно пытаться построить универсальный язык, который способен выразить любую карту Hearthstone.

Это может привести к чрезмерной сложности.

---

# 21. Не overengineer Card IR

Card IR тоже может превратиться в отдельный огромный язык программирования.

Хотелось бы этого избежать.

Начать можно с effects, которые реально часто встречаются в выбранном современном card pool.

Например:

```text
Damage
Heal
Draw
Summon
Buff
Destroy
GainArmor
AddCard
Freeze
Silence
Transform
Discover
```

и постепенно расширять.

---

# 22. Возможная архитектура

Один из вариантов:

```text
HearthstoneJSON
       ↓
CardImporter
       ↓
CardClassifier
       ↓

┌──────────────┬───────────────────┐
│              │                   │
AUTO         PARTIAL             CUSTOM
│              │                   │
↓              ↓                   ↓
Card IR    Missing Primitive     existing
│              report             manual path
↓
Validator
↓
Effect Runtime / Code Generator
↓
RosettaStone
```

Но это не требуемая архитектура.

Если после анализа текущего проекта можно сделать проще или надёжнее — предложи другой вариант.

---

# 23. Желательный первый этап

Я бы не стал сразу переписывать RosettaStone.

Сначала хотелось бы получить investigation / prototype.

Например:

### Step 1

Проанализировать existing RosettaStone mechanics/tasks.

### Step 2

Проанализировать уже вручную добавленные нами modern cards.

### Step 3

Взять репрезентативную выборку современных cards.

### Step 4

Попробовать представить их через proposed Card IR / classification.

### Step 5

Получить количественный отчёт:

```text
automatic
composable
missing primitive
custom
```

### Step 6

Определить, какая архитектура даст лучший ROI.

### Step 7

Только потом реализовывать полноценный generator/runtime.

---

# 24. Первый useful deliverable

Хотелось бы получить что-то вроде:

```text
CARD SUPPORT ANALYSIS

Sample:
100 modern cards

Existing engine supports directly:
X

Can be composed from existing primitives:
Y

Require N new reusable primitives:
Z

Truly custom:
K


Most valuable missing primitive:
1. ...
2. ...
3. ...
```

И отдельно рекомендации:

```text
Recommended implementation strategy:
...
```

На основании реального кода, а не только этого ТЗ.

---

# 25. Очень важная свобода принятия решений

У тебя сейчас значительно больше контекста о фактической кодовой базе, чем у автора этого ТЗ.

Поэтому если при анализе обнаружится:

- RosettaStone уже содержит похожий mechanism;
- Card IR плохо подходит его архитектуре;
- проще расширить существующую CardDef систему;
- лучше генерировать текущий C++ формат;
- лучше использовать Python preprocessing;
- можно использовать compile-time generation;
- существует уже подходящий parser/helper;
- другой подход даст меньше технического долга;

не нужно слепо следовать предложенной архитектуре.

Используй этот документ как направление исследования.

Главная задача:

> найти наиболее масштабируемый и надёжный способ поддерживать современные карты с минимальным количеством ручной работы.

---

# 26. Приоритеты

При выборе решения ориентироваться примерно на такой порядок:

```text
simulation correctness

↓

ability to test automatically

↓

large reduction of manual card work

↓

maintainability after future Hearthstone patches

↓

compatibility with RosettaStone

↓

implementation simplicity

↓

performance
```

Performance пока не является главным bottleneck.

---

# 27. Будущие обновления Hearthstone

Желательно проектировать систему с мыслью, что каждые несколько месяцев будут появляться:

```text
new expansion
new cards
new keywords
balance changes
```

В идеале workflow после нового expansion должен быть примерно:

```text
update HearthstoneJSON
↓
scan new cards
↓
automatic classification
↓
most simple cards imported
↓
missing primitives report
↓
implement several new reusable mechanics
↓
re-run importer
↓
manual work only for outliers
```

Если удастся приблизиться к такому workflow, проблема поддержки cards станет значительно более управляемой.

---

# 28. Что пока не является целью

Не нужно на этом этапе:

- реализовать все существующие Hearthstone cards;
- создавать идеальный generic DSL;
- гарантировать auto-support любой будущей mechanic;
- полностью отказаться от custom C++;
- строить NLP model для понимания card text;
- интегрировать этот pipeline с нейросетью;
- менять working ML code без необходимости.

Это отдельный infrastructure improvement вокруг simulator.

---

# 29. Отчёт перед серьёзным refactor

Так как предлагаемый подход потенциально может затронуть архитектуру RosettaStone integration, перед большим refactor желательно сначала дать краткий отчёт:

```text
1. Что сейчас является главным bottleneck.

2. Какие repeating patterns найдены.

3. Какие existing abstractions RosettaStone можно переиспользовать.

4. Насколько реалистичен Card IR / generator.

5. Какие есть альтернативы.

6. Какая стратегия рекомендуется.

7. Какие риски.

8. Какой ожидаемый выигрыш по объёму ручной работы.
```

Если вывод будет:

> предложенный Card IR неоправдан, но есть более простое решение X

— используй X.

---

# 30. Главная мысль

Сейчас нас интересует не скорость реализации следующей карты.

Нас интересует:

> **как сделать так, чтобы следующие сотни карт не пришлось реализовывать тем же способом.**

Любое решение, которое заметно уменьшает стоимость добавления целого класса похожих карт, потенциально важнее реализации нескольких отдельных cards.

Используй этот принцип при выборе следующего шага.
