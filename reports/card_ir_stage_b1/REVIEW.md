# B1 — пакет независимого ревью 12 карт

Первичные JSON и исправления доступны отдельно, но для ревью они не нужны. Все 12 карточек ожидают
независимой gold-проверки. Русские пояснения — саморевью автора; строки рендера автоматически получены из IR.
PARTIAL и FULL_DEP не означают готовность исполнения; даже FULL не доказывает семантическую правильность.

## 1. Aviana, Elune's Chosen — `EDR_895`

Оригинальный текст:

> [x]<b>Battlecry:</b> Start a three turn lunar cycle. When the Full Moon rises, your cards cost (1) this game.

Автоматический обратный рендер IR:

- NOT EXPRESSED: Battlecry: Start a three turn lunar cycle. When the Full Moon rises, your cards cost (1) this game.

Эффект не закодирован. Неизвестны часы лунного цикла и момент полной луны; постоянную стоимость 1 нельзя заменить эффектом на один ход.

**Риск изменения результата:** Разная сторона отсчёта ходов меняет момент получения скидки для всех карт.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** Whose turn advances the lunar cycle and when does Full Moon rise? → **UNRESOLVED** (UNKNOWN). Альтернативы: every player turn / controller turns only. Различающий случай: Play just before the opponent turn: cost reduction could start on different turns.

Неизвестные зависимости:

- `lunar_cycle` — UNKNOWN_RULE/CORE: v0.1 lacks a lunar phase scheduler, full-moon event and THIS_GAME duration. Do not substitute three arbitrary TURN_END triggers. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 1, перечислений 2, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 2. Nascent Bolt — `TIME_216`

Оригинальный текст:

> Deal $5 damage to a minion. If it survives, draw 2 cards.

Автоматический обратный рендер IR:

- Cast: choose a chosen minion as <target>; deal $5 damage to them<target>
- NOT EXPRESSED: If it survives, draw 2 cards.

Выбирается существо любой стороны, ему наносится $5 урона. Условный добор двух карт оставлен невыраженным: нет проверенного условия выживания в нужной фазе.

**Риск изменения результата:** Безусловный добор или проверка не той сущности дают лишние карты. Послеуронные реакции могут менять выживание.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** Which entity must survive? → **the damaged target** (TEXT). Альтернативы: the damaged target / the spell source. Различающий случай: Target survives while source spell leaves resolution.
- **OUTCOME** When is survival assessed? → **UNRESOLVED** (UNKNOWN). Альтернативы: before death phase / after resulting reactions and death phase. Различающий случай: Lethal damage followed by a healing reaction changes whether two cards are drawn.

Неизвестные зависимости:

- `survival` — UNKNOWN_RULE/CORE: No survival predicate at the post-damage timing boundary. The conditional draw is omitted rather than made unconditional. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 0, перечислений 1, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 3. Ultraxion — `CATA_497`

Оригинальный текст:

> [x]<b>Battlecry:</b> <b>Herald</b> {0}. Reduce Deathwing's Cost by ({1}).  <i>(<b>Herald</b> to improve!)</i>

Автоматический обратный рендер IR:

- NOT EXPRESSED: Battlecry: Herald {0}. Reduce Deathwing's Cost by ({1}). (Herald to improve!)

Эффект оставлен невыраженным. {0} и {1} являются параметрами клиента; это не числа 0 и 1. Правило Herald и ссылка на Deathwing неизвестны.

**Риск изменения результата:** Буквальное чтение заполнителей меняет величину Herald и скидки; неверный Deathwing меняет получателя скидки.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** What numeric Herald and discount values are active? → **UNRESOLVED** (UNKNOWN). Альтернативы: runtime-dependent values / literal zero and one. Различающий случай: Second Herald activation may change both values; literal parsing loses the improvement.

Неизвестные зависимости:

- `herald_runtime` — UNKNOWN_RULE/CORE: Herald has no v0.1 rule; {0}/{1} are runtime placeholders, not constants 0 and 1; Deathwing name relation unresolved. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint
- `deathwing_name` — NAME_REFERENCE/DATA: Resolve the Deathwing identity/identities affected by the cost reduction. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint
- `herald_rule` — KEYWORD_RULE/CORE: Herald progression and runtime client parameters. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 0, перечислений 1, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 4. Spellweaver's Brilliance — `CATA_452`

Оригинальный текст:

> [x]Summon a 6/6 Dragon. Costs (1) less for each damage you dealt with spells this turn.

Автоматический обратный рендер IR:

- Cast: summon 1 x Azure Warden [CATA_452t] (resolved by description_match)
- NOT EXPRESSED: Costs (1) less for each damage you dealt with spells this turn.

Призывается один Azure Warden 6/6 по предположительной связи токена. Скидка за суммарный урон заклинаниями за ход не закодирована.

**Риск изменения результата:** Число сыгранных заклинаний не равно нанесённому ими урону. Приписанная по префиксу связь токена требует подтверждения.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** What is counted for the discount? → **damage actually dealt by spells** (TEXT). Альтернативы: damage actually dealt by spells / number of spells cast. Различающий случай: One spell deals six damage: discount six rather than one.
- **OUTCOME** Is the 6/6 Dragon Azure Warden? → **UNRESOLVED** (UNKNOWN). Альтернативы: CATA_452t / another 6/6 Dragon. Различающий случай: Different Dragon identity changes generated card and future interactions.

Неизвестные зависимости:

- `dragon_identity` — TOKEN_IDENTITY/DATA: CATA_452t is a 6/6 Dragon matching description and ID prefix; no authoritative parent-token relation. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint
- `spell_damage_sum` — UNKNOWN_RULE/CORE: v0.1 history counters count casts/cards, not total damage dealt by spells; a damage sum counter is missing. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 0, перечислений 1, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 5. V'ama, Looming Death — `JAIL_118`

Оригинальный текст:

> <b>Battlecry:</b> Destroy all non-Paladin minions.

Автоматический обратный рендер IR:

- NOT EXPRESSED: Battlecry: Destroy all non-Paladin minions.

Уничтожение всех существ не-паладинов не закодировано: существующий фильтр класса выражает принадлежность, но не её отрицание.

**Риск изменения результата:** Эффект касается обеих сторон. Список всех остальных классов небезопасен для многоклассовых и будущих карт.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** Does all include friendly minions? → **both sides** (TEXT). Альтернативы: both sides / enemies only. Различающий случай: A friendly non-Paladin minion must be included.
- **OUTCOME** Does a mixed-class Paladin minion count as Paladin? → **UNRESOLVED** (UNKNOWN). Альтернативы: has Paladin among its classes / exactly Paladin class only. Различающий случай: Paladin/Druid minion survives in only one reading.

Неизвестные зависимости:

- `class_negation` — UNKNOWN_RULE/CORE: No negation predicate: card_class PALADIN would invert non-Paladin; enumerating other classes is unsafe for multiclass and unknown classes. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 1, перечислений 0, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 6. Aldrachi Warblades — `CORE_BT_921`

Оригинальный текст:

> <b>Lifesteal</b>

Автоматический обратный рендер IR:

- Keyword Lifesteal

Оружие обладает Lifesteal. Тело карты остаётся в метаданных: базовая прочность указана как health=2, поле durability=0 не подставляется вместо неё.

**Риск изменения результата:** FULL описывает представленность текста, а не проверку правил лечения, готовность исполнителя или текущую прочность экземпляра.

Решения интерпретации (особенно OUTCOME):

- **NONE** Where is base durability stored? → **health=2 in this metadata record** (METADATA). Альтернативы: health=2 in this metadata record / durability=0. Различающий случай: не нужен

Неизвестные зависимости:

- Нет явно объявленных зависимостей; общие правила IR всё равно требуют реализации и проверки.

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `FULL`; независимое ревью **PENDING**.

Словарь: новых структур 0, перечислений 0, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 7. Imp Gang Stooge — `JAIL_399`

Оригинальный текст:

> [x]<b>Taunt</b>. <b>Deathrattle:</b> Put two 8/8 Demons with <b>Taunt</b> and <b>Lifesteal</b> on the bottom of your deck.

Автоматический обратный рендер IR:

- Keyword Taunt
- NOT EXPRESSED: Deathrattle: Put two 8/8 Demons with Taunt and Lifesteal on the bottom of your deck.

Собственный Taunt закодирован. Deathrattle с двумя демонами 8/8 с Taunt и Lifesteal на дне своей колоды не закодирован.

**Риск изменения результата:** SHUFFLE дал бы случайные позиции вместо дна колоды. Не установлено, имеют ли два демона одну идентичность токена.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** Where do the Demons enter? → **bottom of own deck** (TEXT). Альтернативы: bottom of own deck / random shuffled positions. Различающий случай: The next top-deck draw must not become a newly inserted Demon unless deck was empty.
- **OUTCOME** Do both generated Demons share an identity? → **UNRESOLVED** (UNKNOWN). Альтернативы: two copies of one token / two distinct Demon tokens. Различающий случай: Identity-sensitive effects distinguish these alternatives.

Неизвестные зависимости:

- `bottom_insert` — UNKNOWN_RULE/CORE: SHUFFLE_INTO_DECK has no insertion-position or multiplicity parameter; random shuffling is not bottom insertion. Token identities also unresolved. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint
- `demons_identity` — TOKEN_IDENTITY/DATA: Identify the two generated 8/8 Demon records from client relations. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 1, перечислений 1, параметров 2 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 8. Cult Neophyte — `CORE_SCH_713`

Оригинальный текст:

> <b>Battlecry:</b> Your opponent's spells cost (1) more next turn.

Автоматический обратный рендер IR:

- NOT EXPRESSED: Battlecry: Your opponent's spells cost (1) more next turn.

Эффект не закодирован: отсутствует точное окно следующего хода противника для повышения стоимости его заклинаний на 1.

**Риск изменения результата:** THIS_TURN или неопределённый turns=1 могут повысить стоимость на неправильном ходу. Динамическое применение к новым заклинаниям не подтверждено.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** Whose spells cost more? → **opponent spells** (TEXT). Альтернативы: opponent spells / own spells. Различающий случай: Opponent has a one-cost spell next turn.
- **OUTCOME** Is the modifier applied dynamically to all opponent spells during the window? → **UNRESOLVED** (UNKNOWN). Альтернативы: dynamic rule including new spells / only spell cards present when played. Различающий случай: Opponent draws or generates a spell during the affected turn.

Неизвестные зависимости:

- `next_opponent_turn` — UNKNOWN_RULE/CORE: No NEXT_OPPONENT_TURN duration/window. Negative reduce could express +1, but THIS_TURN or turns=1 would not specify the next opponent turn. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 0, перечислений 1, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 9. Waggle Pick — `CORE_DAL_720`

Оригинальный текст:

> [x]<b>Deathrattle:</b> Return a random friendly minion to your hand. It costs (2) less.

Автоматический обратный рендер IR:

- Deathrattle: you get random 1 friendly minion as <returned>; then cost of them<returned> reduced by 2

Предварительное IR: случайное дружественное существо из PLAY перемещается в свою руку; стоимость именно этого результата уменьшается на 2. Правила сброса состояния при возврате не установлены, поэтому итог PARTIAL.

**Риск изменения результата:** Ошибка первичного авторства: статус FULL предполагал, что обычное перемещение корректно реализует возврат. На повреждённом существе с зачарованиями это способно изменить результат. Ни один проверяющий слой не предупредил.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** Which card gets the discount? → **the returned minion** (TEXT). Альтернативы: the returned minion / the weapon. Различающий случай: The chosen minion is now in hand and costs two less.
- **OUTCOME** Does generic from_zone movement implement return-to-hand reset semantics? → **UNRESOLVED** (UNKNOWN). Альтернативы: move preserving current state / return with zone-transition reset before applying the two-cost discount. Различающий случай: Return a damaged enchanted minion: its resulting hand state and replayed stats distinguish the readings.

Неизвестные зависимости:

- `return_transition` — UNKNOWN_RULE/CORE: ADD_TO_HAND(from_zone) declares movement but v0.1 has no return-to-hand reset contract. Do not infer that enchantments/damage reset correctly. The encoded sequence is provisional, not a certified bounce. Источник нужен: Independent universal return-to-hand rule plus IR transition contract

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Одна авторская коррекция: FULL → PARTIAL; добавлена CORE-зависимость возврата и решение переведено в UNRESOLVED. Автопроверки проблему не обнаружили.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 1, перечислений 0, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 10. Magma Hound — `FIR_953`

Оригинальный текст:

> [x]<b>Rush</b>. After this attacks a minion and survives, deal this minion's Attack damage split among all enemies.

Автоматический обратный рендер IR:

- Keyword Rush
- NOT EXPRESSED: After this attacks a minion and survives, deal this minion's Attack damage split among all enemies.

Rush закодирован. Триггер после атаки этого существа с выживанием и распределение урона по врагам оставлены невыраженными.

**Риск изменения результата:** HERO_ATTACK не подходит для атаки существа. Нельзя без подтверждения заменить split случайными пакетами по 1; текущая или последняя известная атака тоже требуют проверки.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** How are Attack points split among enemy characters? → **UNRESOLVED** (UNKNOWN). Альтернативы: random one-point packets / another distribution rule. Различающий случай: Two enemy characters with one Health: allocation changes the survivor.
- **OUTCOME** Whose attack can trigger this? → **this minion attacks another minion and survives** (TEXT). Альтернативы: this minion attacks another minion and survives / any hero attack. Различающий случай: Another friendly attacker acts while this minion stays idle.

Неизвестные зависимости:

- `attack_survival_split` — UNKNOWN_RULE/CORE: No after-source-minion-attack-and-survives event; text says split but does not explicitly say randomly. Keep attack timing and distribution unresolved. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 0, перечислений 2, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 11. Torch — `CATA_585`

Оригинальный текст:

> [x]Deal $8 damage to a damaged minion. Return this to hand with any excess damage.

Автоматический обратный рендер IR:

- Cast: choose a chosen minion damaged as <target>; deal $8 damage to them<target>
- NOT EXPRESSED: Return this to hand with any excess damage.

Выбирается повреждённое существо любой стороны, в IR записан текстовый $8 урона. Возврат самого заклинания с избыточным уроном не выражен. Метка $ конфликтует с ImmuneToSpellpower в метаданных.

**Риск изменения результата:** Нельзя считать величину избыточного урона, пока не решены порядок расчёта и конфликт Spell Damage. Возвращается заклинание, не цель.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** What returns to hand? → **this spell** (TEXT). Альтернативы: this spell / the damaged minion. Различающий случай: Target dies; the spell rather than that minion returns.
- **OUTCOME** Does Spell Damage modify this amount? → **UNRESOLVED** (UNKNOWN). Альтернативы: text $ mark applies / ImmuneToSpellpower prevents it. Различающий случай: Cast with +1 Spell Damage and inspect actual damage and returned card amount.

Неизвестные зависимости:

- `excess_return` — UNKNOWN_RULE/CORE: No return-source operation with preserved excess-damage parameter; excess damage timing/calculation unresolved. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint
- `spellpower_conflict` — UNKNOWN_RULE/CORE: Text carries $8 but metadata says ImmuneToSpellpower. Preserve raw mark pending independent rule review; do not claim spell-damage scaling. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 2, перечислений 0, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.

## 12. Frostwyrm's Fury — `CORE_RLK_063`

Оригинальный текст:

> Deal $5 damage. <b>Freeze</b> all enemy minions. Summon a 5/5 Frostwyrm.

Автоматический обратный рендер IR:

- Cast: choose a chosen character as <target>; deal $5 damage to them<target>
- Cast: summon 1 x Frostwyrm [RLK_063t] (resolved by name_in_set)
- NOT EXPRESSED: Freeze all enemy minions.

Выбранному персонажу любой стороны наносится $5 урона; отдельно описан призыв одного Frostwyrm 5/5. Средний шаг заморозки всех вражеских существ отсутствует.

**Риск изменения результата:** Порядок должен быть урон → заморозка → призыв. Два фрагмента play с пропуском не являются полной исполнимой последовательностью. Связь токена CORE с RLK_063t предположительна.

Решения интерпретации (особенно OUTCOME):

- **OUTCOME** When is Freeze applied? → **after damage and before summon** (TEXT). Альтернативы: after damage and before summon / after summon. Различающий случай: A reaction to the summon observes the already frozen board.
- **OUTCOME** Which type may the damage target? → **any character** (TEXT). Альтернативы: any character / minions only. Различающий случай: Opponent hero is a legal damage target in the first reading.

Неизвестные зависимости:

- `freeze` — UNKNOWN_RULE/CORE: FREEZE operation is absent. The missing middle step must happen between damage and summon; these fragments are not an executable whole. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint
- `frostwyrm_identity` — TOKEN_IDENTITY/DATA: RLK_063t matches name/stats and original ID prefix; CORE parent relation needs confirmation. Источник нужен: Independent rules review or client relationship data; not inferred from a clean lint

**Проверки:** структурных ошибок 0, старых предупреждений 0, новых 0.

**Исправления:** Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.

**Итог:** `PARTIAL`; независимое ревью **PENDING**.

Словарь: новых структур 1, перечислений 0, параметров 0 **предложено, не добавлено**. Фактически добавлено 0.

- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.
- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.
