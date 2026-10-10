# TACTICAL-DECISION-1 — оценка последствий действий поверх Policy v2

**Вердикт: ограниченный GO для двух доказуемо-локальных правил (L1, L2) в режиме подсказки; NO-GO для «закреплённого эффекта» (L3) и для приоритета завершения Quest.** Эффект узкий: он относится к одной колоде с Ruby Sanctum и затрагивает 26 из 2010 решений (1,3%). Но в этих 26 решениях изменения подтверждаются правилами, не зависящими от выбора игрока, и ни разу не ухудшают совпадение с игроком.

Это диагностика на уже просмотренных матчах, а не независимый тест качества игры. Обучения нет, production `GameState`, `StateEncoder`, Policy, LIVE-MVP и checkpoints не менялись, ветка с `main` не объединялась.

## Короткий ответ

| Вопрос | Результат |
|---|---|
| Где Policy v2 заметно ошибается? | Целевой выбор лечебных эффектов. Из 43 решений, где Top-1 — поддержанное лечение, в **42 цель — противник**: в 6 действие лечит противника, в 34 ничего не делает, в 2 (эффект включён) наносит урон — это верно. Policy не видит, включён ли эффект Ruby Sanctum («следующее лечение наносит урон»), поэтому не отличает лечение от урона |
| Что показали новые наблюдаемые факты? | Состояние Sanctum определено во всех 2010 решениях без UNKNOWN. Три раза у игрока была летальная атака лечением (Flash Heal при эффекте = 5 урона в героя с 4 здоровья); Policy ставила её на ранги 3, 6 и 12, ни разу не Top-1. Во всех трёх игрок сыграл её, это было последнее решение матча, матч выигран |
| Сколько рекомендаций изменилось? | L1: 23 Top-1; L1+L2: 26; L1+L2+L3: 62 (из 2010) |
| Что подтверждено независимыми правилами? | Все 26 изменений L1/L2: текст закреплённого каталога, формальное состояние эффекта и арифметика здоровья. Исходы выбранных игроком действий подтверждают модель прямого эффекта: 43/43 проверяемых (19 урон при включённом эффекте, 21 лечение своего, 3 нулевых), и 91/91 в OBSERVATION-AUDIT-1 |
| Где регрессии? | L1, L2: нет изменений, где Policy совпадала с игроком, а новая рекомендация нет. L3: 2 таких случая, оба связаны с Purifying Breath, которую оценщик не моделирует; плюс 5 подмен на hero power с уроном 2, ни одна не совпала с игроком |
| Что остаётся неопределённым | Побочные эффекты применения без прямого эффекта (22 Top-1 после L1), ценность альтернатив при активном эффекте, условные лечения (Purifying Breath), награды Quest, Secret противника |

## Протокол

- Ветка `claude/tactical-decision-1` от `main` `0fe53dc`. Корпус DATA-CHECKPOINT-1 `canonical`: 53 матча, 2010 решений (identity `b964e121…3c1`, content `78c21cbd…9c9`), каталог `c767c303…cb34`, frozen Policy v2 SHA-256 `044b9b50…1e4d`. Скрипт сверяет все идентичности и штатный audit до начала работы.
- Группы как в ML-PILOT-1 и CONSEQUENCE-PILOT-1: **development** — 16 матчей 10 октября (669 решений; frozen v2 их не видел, но игрок видел подсказки); **older** — 37 матчей (1341), из которых 20 входили в train/validation/test frozen v2.
- Временный слой — модуль [decision_overlay.py](../../src/manamind/research/decision_overlay.py): пакет за пакетом воспроизводит raw Power.log теми же `PacketExporter` и маршрутизацией `GameState.*`, что LIVE reducer, и читает **три факта о SELF** только в момент пакета `Options`: состояние Sanctum (флаг игрока `HEALING_DOES_DAMAGE` вместе с энчантментом `CATA_301e`), собственные Quest (идентичность, прогресс, цель), подсказку `QUEST_CONTRIBUTOR` только у карт своей руки. Скрытые зоны противника не читаются. Будущие пакеты не используются ни как вход, ни для оценки (оценка идёт по следующему записанному состоянию корпуса или по исходу матча).
- **Переизмерение:** слой воспроизводит числа OBSERVATION-AUDIT-1 на тех же 93 raw-файлах: 62 матча, 2991 точка решения, ACTIVE 65 / INACTIVE 2926 / UNKNOWN 0, из размеченных 46 ACTIVE, 1353 решения с Quest. Скрипт падает, если числа не совпали. Рука из слоя совпала с рукой корпуса в 2010/2010 строк.
- Запуск: `python scripts/tactical_decision_1.py --data-root <data основного checkout>`. Два прогона дали побайтно одинаковый [results.json](results.json) (SHA-256 `5a98bf8e…4bbc`). Seed хеширования выбора кейсов и bootstrap — 20261011, 2000 пересэмплирований целых матчей. CPU, один поток, `torch.manual_seed(0)`.
- **Что не было заморожено заранее — прямо.** Класс ошибок и форму слоя L3 я выбрал после предварительного просмотра этого же корпуса (ранги Policy в состояниях ACTIVE, исходы Top-1 лечений). Правила L1 и L2 выведены из текста карт и арифметики и не подбирались по метрикам. После первого просмотра отобранных кейсов были исправлены два дефекта детекторов (ложное срабатывание «Sanctum не использован», когда Top-1 сам является условным лечением; для Shadow Word: Ruin добавлено «завершает Quest»). Метрики сравнения после этого не пересматривались.

## 1. Какие решения отобраны и как они классифицированы

Семь детекторов проходят все 2010 решений. Каждый использует только видимые факты и слой SELF, проверяет Top-1 Policy и **не считает ход игрока правильным**. Затем детерминированно (хеш + seed) отбираются кейсы по квотам. Полный список — в приложении; подробные записи (Top-3, ход игрока и его ранг у Policy, доступные сведения, отсутствующая информация) — в `results.json` → `cases`.

| Класс | Флагов из 2010 | dev / older | Ход игрока = альтернатива | Ход игрока = Top-1 Policy | Уровень |
|---|---:|---:|---:|---:|---|
| `HEAL_LETHAL_MISSED` — есть летальное лечение-урон, Top-1 его не использует | 3 | 1 / 2 | 3 | 0 | 2 PROVEN_LOCAL, 1 UNCERTAIN (Secret/Quest противника) |
| `HEAL_TARGET_DOMINATED` — у того же источника есть цель строго лучше | 23 | 6 / 17 | 11 | 0 | PROVEN_LOCAL |
| `SANCTUM_FOLLOWUP_MISSED` — эффект включён, но Top-1 не лечение по врагу | 34 | 9 / 25 | 29 | 0 | PROBABLE_STRATEGIC |
| `QUEST_COMPLETION_MISSED` — есть заклинание, завершающее Quest | 176 | 45 / 131 | 22 | 68 | PROBABLE_STRATEGIC |
| `ATTACK_BAD_TRADE` — атакующий гибнет, цель выживает, есть выгодный размен | 1 | 0 / 1 | — | 0 | PROBABLE_STRATEGIC |
| `AOE_RUIN_NO_TARGET` — Top-1 Ruin без существ с атакой ≥5 | 9 | 2 / 7 | — | 0 | UNCERTAIN (в 4 из 9 Ruin двигает или завершает Quest) |
| `FABLED_ORDER` — Atiesh первым при доступном Medivh | 11 | 3 / 8 | — | 1 | UNCERTAIN (нужна симуляция) |

Отобрано **38 кейсов** (11 development, 27 older): 11 PROVEN_LOCAL, 18 PROBABLE_STRATEGIC, 9 UNCERTAIN. Классы с малым числом флагов (3 летальных, 1 размен) отобраны целиком.

**Три уровня и чего не хватает**

- **Доказуемые локальные ошибки (11).** Видимый прямой эффект рекомендации вреден или нулевой по записанным правилам, а лучшая цель того же источника существует. Остаточные оговорки: триггеры, зависящие от цели и не описанные в тексте; Secret и неуязвимость героя противника (в состоянии нет признака неуязвимости героя).
- **Вероятные стратегические ошибки (18).** Правила предпочитают другой ход, но его ценность зависит от того, что не моделируется: темп и стол, «эффект Sanctum сгорит неиспользованным» (подтверждён только на конце хода противника, у SELF сгоревшего эффекта в корпусе нет), награды Quest (Life's Breath, Death's Touch нет в закреплённом каталоге).
- **Неопределённые (9).** Нужен двухшаговый расчёт (Medivh уничтожает остальных существ, Atiesh становится бесплатным) или неизвестен текст карты на столе (18,2% появлений карт без текста в каталоге).

**Конкретные примеры** (ID — первые 16 символов хеша наблюдения; ранг — позиция в ранжировании frozen v2)

| ID, группа | Контекст на момент решения | Top-3 Policy v2 | Ход игрока (ранг) | Вывод |
|---|---|---|---|---|
| `3e342f3d`, dev | Sanctum ACTIVE, у противника 4 здоровья, 1 мана | END_TURN; атака героя 1/30 в героя; Flash Heal→вражеский герой | Flash Heal→герой (3) | **Доказуемо:** 5 урона ≥ 4; игра закончена выигрышем. Policy ставит конец хода первым |
| `24519455`, older | то же, 18 здоровья у SELF, 2 маны | Lunarwing Messenger; hero power `EDR_449p`; END_TURN | Flash Heal→герой (6) | **Доказуемо**, матч выигран на этом ходу |
| `64f055c1`, older | то же, у противника 1 Secret/Quest, 7 маны | Eternal Firebolt по существу; Kaldorei Priestess; hero power | Flash Heal→герой (12) | Летально по видимым данным, но скрытый Secret мог помешать: UNCERTAIN; матч выигран |
| `83e9144a`, dev, известный эпизод | INACTIVE, у SELF 27/30, hero power готов | hero power→Violet Treasuregill (полное здоровье); →вражеский герой; →`CS2_101t` | hero power→свой герой (4) | **Доказуемо:** три Top-3 лечат врага ничем. L1 переносит свой раненый герой на ранг 1 (стал Top-1, совпал с игроком) |
| `57d93394`, older | INACTIVE, вражеский герой 28/30 | hero power→вражеский герой (+2 врагу); →свой герой (полный); END_TURN | END_TURN (3) | **Доказуемо:** Top-1 лечит противника. Ход игрока не совпал и с новым Top-1: L1 лишь убирает вред |
| `ed6e3856`, older | ACTIVE, у противника 17, 5 маны | Gravedawn Sunbloom; Devouring Plague; Shadow Word: Ruin | Flash Heal→герой (8) | **Вероятно:** эффект сгорает в конце хода, а Flash Heal стоит 1 |
| `719b8abb`, older | ACTIVE, 6 маны, у Policy hero power и Moonwell выше | hero power; Moonwell; Purifying Breath | Flash Heal→Mug'Zee (15) | **Вероятно**, но Moonwell и Breath сами лечащие: оценщик не может их сравнить |
| `4ace66af`, dev, известный эпизод ML-PILOT-1 | Ruin, существ с атакой ≥5 нет; Quest Shadow 3/4, у карты подсказка 1 | Ruin; hero power→герой врага; hero power→свой герой | Flash Heal→свой герой (17) | **Не ошибка.** Слой Quest показывает: Ruin — заклинание школы Shadow и завершает Quest 3/4 (если Secret противника, например Counterspell, его не отменит). ML-PILOT-1 считал этот случай ошибкой Policy; теперь он не подтверждён |
| `48017cc7`, dev | Atiesh и Medivh в руке, 10 маны | Atiesh; Medivh; Medivh | Medivh (20) | **Неопределённо:** нужен расчёт двух шагов |
| `f24ddd60`, older | Cleric 4/5 идёт на 5/5 | атака Cleric→Jailhouse Manastorm 5/5 | Hold Them Off! на Cleric (8) | **Вероятно:** Cleric гибнет без размена (4<5), но намерение игрока (Taunt, добивание) неизвестно |

## 2. Выбор класса

Критерии выбора заданы здесь, а не подогнаны: число решений ≥ 20, правило записано независимо от хода игрока, недостающие сведения закрываются проверенным слоем, последствия можно сверить с корпусом.

| Класс | Достаточно данных | Правило независимо от игрока | Слой закрывает недостающее | Итог |
|---|---|---|---|---|
| Лечение × Sanctum (цели, летал, закреплённый эффект) | 43 Top-1 лечения, 46 ACTIVE-решений, 3 летала | да (текст карты, арифметика) | да (Sanctum) | **выбран** |
| Завершение Quest | 176 флагов, но игрок завершает Quest лишь в 22 из них (12,5%), а в 68 его ход равен Top-1 Policy | нет: ценность награды неизвестна | частично | нет оснований для правила |
| AoE (Ruin) | 9 | нет | Quest показывает, что в 4 из 9 Ruin двигает Quest | мало данных, правило не нужно |
| Атака, плохой размен | 1 | да | — | мало данных |
| Порядок Medivh/Atiesh | 11 | нужна симуляция | нет | вне задачи |

Слой Quest **не изменил ни одного ранжирования** оценщика: все цели одного источника имеют одинаковый вклад в Quest, поэтому L1 их не различает. Он использован для классификации (Ruin и завершение Quest) и убрал одну из «известных ошибок».

## 3. Оценщик

Модуль [tactical_context.py](../../src/manamind/research/tactical_context.py). Это не система эффектов: поддержано **два вида источников лечения** — целевое заклинание, чей закреплённый текст начинается с `Restore #N Health.` (Flash Heal, Holy Embrace; без «to all»), и hero power Priest (+2, значение выведено по исходам в CONSEQUENCE-PILOT-1, в каталоге его нет). Остальное не оценивается и остаётся на своих местах.

Для каждого поддержанного действия считается прямой исход по состоянию (Sanctum ACTIVE: лечение ⇒ урон):

| Состояние | Цель — противник | Цель — SELF |
|---|---|---|
| INACTIVE | здоровье неполное: лечит врага (**вред**); полное: нет эффекта (нейтрально) | неполное: лечение (**выигрыш**); полное: нейтрально |
| ACTIVE | урон врагу (**выигрыш**); если герой с бронёй гарантированно умирает — **летал** | урон себе (**вред**) |

Герой с Divine Shield, неуязвимая/спящая цель, неизвестный максимум здоровья или состояние UNKNOWN дают UNRESOLVED: действие не трогается. `healing_bonus` неизвестен, но только увеличивает лечение/урон, поэтому для летала берётся нижняя граница.

Три вложенных слоя переранжирования (ни одно действие не удаляется):

- **L1 — доминирование цели.** Внутри одного источника (та же копия карты или тот же hero power) цели упорядочены ВЫИГРЫШ > НЕЙТРАЛЬНО > ВРЕД. Занятые слоты источника и все остальные действия остаются на местах. Меняется только цель. Обоснование: стоимость, триггеры применения и Quest-прогресс одинаковы для всех целей.
- **L2 — гарантированный летал** выходит на первое место.
- **L3 — закреплённый эффект (стратегическое допущение).** Пока эффект активен, урон по врагу идёт впереди всех нелечащих действий. Это допущение, а не доказательство.

## 4. Сравнение с неизменённой Policy v2

Одни и те же 2010 состояния и одни и те же меню. Метрики имитации — совпадение Top-1 с ходом игрока, **не сила игры**.

| Вариант | Top-1 изменён | Top-3 (набор) изменён | Top-1 = игрок, все 2010 | dev 669 | older 1341 | в 771 решении с поддержанным лечением | в 41 решении Sanctum ACTIVE |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 — frozen v2 | 0 | 0 | 1080 (53,7%) | 330 | 750 | 331 | 3 |
| V1 — L1 | 23 | 59 | 1091 (54,3%) | 335 | 756 | 342 | 3 |
| V2 — L1+L2 | 26 | 61 | 1094 (54,4%) | 336 | 758 | 345 | 6 |
| V3 — L1+L2+L3 | 62 | 97 | 1107 (55,1%) | 339 | 768 | 358 | 19 |

Прирост совпадения Top-1 на все решения, bootstrap по целым матчам (95%):

| Вариант | Все 2010 | Development (669) |
|---|---|---|
| V1 | +11 (+0,55 п.п.; 0,20…0,95) | +5 (0,0…1,64) |
| V2 | +14 (+0,70 п.п.; 0,30…1,14) | +6 (0,15…1,79) |
| V3 | +27 (+1,34 п.п.; 0,75…1,99) | +9 (0,30…2,84) |

Малые абсолютные числа. Интервалы не пересекают 0 в сумме, но 11–27 совпадений на 2010 решений не говорят о силе игры. Top-3 корпуса (1653 меню ≥3): 1103 → 1111 / 1113 / 1131.

### Что именно изменилось

**L1 — 23 изменения, development 6 / older 17, все PROVEN_LOCAL.** Новый Top-1: 19 раз hero power на свой герой, 3 раза заклинание на свой герой (Holy Embrace ×2, Flash Heal), 1 раз hero power на вражеского героя с полным здоровьем. Типы переходов: 16 «ничего врагу → лечение своего»; 3 «лечит врага → нейтральная цель»; 2 «лечит врага → лечение своего»; 1 «нейтральная своя → лечение своего»; 1 «лечит врага → ничего врагу». В 11 случаях новый Top-1 совпал с игроком, в 12 — нет (игрок сыграл другой источник, например Coin, Devouring Plague, Ruin или END_TURN); **0 случаев, когда старый Top-1 совпадал с игроком, а новый нет**.

После L1 Top-1 по врагу, лечащему врага, не остаётся ни одного (было 6). Остаётся 22 решения, где Top-1 — применение без прямого эффекта (20 hero power, 2 заклинания), потому что все цели нейтральны и строго лучшей нет; сравнить это с END_TURN нельзя, не зная побочных эффектов («если вы применили hero power»), поэтому оценщик здесь молчит (аналог NO_DIRECT_EFFECT из CONSEQUENCE-PILOT-1).

**L2 — 3 изменения** (1 dev, 2 older): везде новый Top-1 = Flash Heal в герой с 4 здоровья, во всех трёх это последнее решение выигранного матча. В одном из трёх у противника был скрытый Secret/Quest (в оценщике пометка `OPPONENT_SECRET_PRESENT`).

**L3 — 36 изменений** (dev 8 / older 28). Новый Top-1 всегда урон по врагу из лечебного источника. 15 раз совпал с игроком, 19 — нет, 2 — старый Top-1 совпадал с игроком, а новый нет (оба раза игрок сыграл Purifying Breath, и L3 заменил её на hero power с уроном 2 и на Flash Heal по другой цели). По источнику: 31 заклинание (15 совпало с игроком) и **5 hero power (0 совпадений)**. В 7 из 36 игрок сыграл условное лечение, которое оценщик не моделирует (Purifying Breath и подобные). В 39 из 41 решений Sanctum ACTIVE V3 меняет Top-1: V3 практически заменяет Policy скриптом «после Sanctum — лечение». Совпадение в ACTIVE выросло с 3/41 до 19/41; остальные 22 расходятся по выбору конкретной цели/источника, которые оценщик сам не ранжирует.

### Подтверждение независимыми правилами

| Утверждение | Основание, не зависящее от игрока | Статус |
|---|---|---|
| Эффект включён ⇒ лечение становится уроном | Текст `CATA_301`: «Your next Healing effect this turn deals damage instead»; на следующем записанном состоянии корпуса 19/19 проверяемых исходов `ENEMY_DAMAGE` дали ≥ предсказанного урона, 0 противоречий; OBSERVATION-AUDIT-1: 91/91 | подтверждено |
| Эффект выключен ⇒ обычное лечение | на следующем состоянии 21/21 `SELF_HEAL` и 3/3 `SELF_NO_EFFECT` подтверждены; 0 противоречий | подтверждено для своих целей |
| Лечение врага даёт врагу здоровье / ничего | Симметрично пред. строке по тексту `Restore #N Health.`; **игрок эти действия не выбирал**, прямых наблюдений нет | не проверено напрямую |
| Летал: 5 урона ≥ здоровье+броня | Арифметика; 3/3: решение последнее в матче, `final_result` = победа SELF | подтверждено исходом |
| Закреплённый эффект ценен | Не доказывается правилами: ценность альтернатив неизвестна | допущение |

Проверка последствий возможна только в «чистом окне» из одного решения (то же правило, что в CONSEQUENCE-PILOT-1), поэтому наблюдений мало: 43 подтверждено, 19 без чистого следующего состояния (в том числе 3 летальных: матч закончился), 4 ненаблюдаемых. Противоречий 0.

### Где возможны регрессии

1. **L3, условные лечения.** Purifying Breath («Deal $5 damage to a minion. If it dies, restore #5 Health to the enemy hero») при активном Sanctum превращается в урон по герою, если существо умирает: игрок так играл. L3 ставит Flash Heal выше, и это не доказанное улучшение. `27759b9e` и `2e6f9826` — два случая, где Top-1 Policy = ход игрока был потерян.
2. **L3, hero power.** Урон 2 за 2 маны выдвигается над розыгрышем существ и условными лечениями. 5 из 5 таких подмен не совпали с игроком.
3. **L1.** Единственный незамоделированный риск: триггеры «когда исцелён» и особые правила целей. Для Quest-прогресса, стоимости и «if you used your Hero Power» выбор цели безразличен.
4. **Moonwell** («Deal $4 damage to all enemy characters. Restore #4 Health to all friendly characters.») при активном Sanctum, возможно, наносит урон своим персонажам. В корпусе не проверялось; оценщик Moonwell не касается.
5. **Hero power `EDR_449p`** (Imbue) не оценивается: у него нет цели.

## 5. Рекомендация

| Компонент | Решение | Условие |
|---|---|---|
| L1 — доминирование цели | **GO (ограниченный, подсказка рядом с Policy)** | факт `healing_does_damage` для SELF вне encoder (OBSERVATION-EXT-1, оценка ~1 рабочий день); независимая проверка на свежих матчах; показывать как «цель хуже», а не подменять ранг Policy |
| L2 — гарантированный летал | **GO (ограниченный)** | то же; при `secret_count > 0` помечать «если нет Secret» |
| L3 — закреплённый эффект | **NO-GO** | допущение; 5 из 5 подмен hero power не совпали с игроком, 2 потерянных совпадения |
| Приоритет завершения Quest | **NO-GO** | награды неизвестны, игрок завершает Quest в 12,5% флагов |
| Обобщение на другие карты/колоды | **не показано** | всё покрытие: Ruby Sanctum, два шаблона заклинаний и один hero power в одной колоде |

Выбор между «правило-фильтр» и моделью — отдельное решение. Правила L1/L2 дёшевы и проверяемы, но это точечный патч поверх Policy, а не обобщение. Путь Model-first — дать модели эти поля в новой схеме encoder и обучить — требует отдельной задачи и явного разрешения.

Автоматически ничего не запускается. Очередной шаг (на выбор пользователя): OBSERVATION-EXT-1 только для `healing_does_damage` и подготовка независимой выборки, на которой L1/L2 проверяются до любого подключения к LIVE.

## Ограничения

- Корпус почти целиком одна колода Priest с Ruby Sanctum и двойным Quest. Dev-матчи игрок видел, older частично обучали frozen v2. Независимого набора нет: любое утверждение «лучше» относится к просмотренным состояниям.
- Всего 65 точек решения с Sanctum ACTIVE (46 размеченных, 41 с поддержанным лечением), 3 летальных, 43 Top-1 лечения.
- Совпадение с игроком — имитация. Рост этой метрики не доказывает рост силы игры, а падение не доказывает ошибку.
- Условные лечения (Purifying Breath), массовое (Moonwell), Lifesteal, `healing_bonus` и скрытые Secret не моделируются.

## Проверки

- `ruff check src tests scripts`: PASS.
- Новые тесты: [test_tactical_context.py](../../tests/test_tactical_context.py) (12), [test_decision_overlay.py](../../tests/test_decision_overlay.py) (5, включая проверку, что чтение происходит до применения следующих пакетов; мутация «читать после» тест ловит), [test_tactical_mining.py](../../tests/test_tactical_mining.py) (7). Ожидаемые исходы заданы в тестах до вызова кода.
- Полный pytest: **659 passed, 1 skipped**.
- Raw-логи, датасеты и checkpoints в Git не добавлены. `results.json` содержит только ID карт, счётчики и 16-символьные хеши наблюдений, без `game_id` и имён игроков.

## Воспроизведение

```powershell
$env:PYTHONPATH="src"; $env:PYTHONUTF8="1"
.venv\Scripts\python.exe scripts\tactical_decision_1.py --data-root <каталог data основного checkout> --output reports\tactical_decision_1\results.json
.venv\Scripts\python.exe -m pytest tests\test_tactical_context.py tests\test_decision_overlay.py tests\test_tactical_mining.py -q
```

## Приложение. Все 38 кейсов

Ранг — позиция хода игрока у frozen v2. «Top-1» — первый выбор Policy. Полные Top-3 и доступные сведения — в `results.json` → `cases`.

| # | ID | Группа | Класс | Уровень | Top-1 Policy v2 | Ход игрока (ранг) |
|---:|---|---|---|---|---|---|
| 1 | `24519455` | older | HEAL_LETHAL_MISSED | PROVEN_LOCAL | PLAY_CARD Lunarwing Messenger[EDR_449] cost2 | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP hero hp4 (6) |
| 2 | `3e342f3d` | dev | HEAL_LETHAL_MISSED | PROVEN_LOCAL | END_TURN | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP hero hp4 (3) |
| 3 | `64f055c1` | older | HEAL_LETHAL_MISSED | UNCERTAIN | PLAY_CARD Eternal Firebolt[END_025] cost3 -> OPP Blackwing Experiment[CATA_464] 3/1 | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP hero hp4 (12) |
| 4 | `83e9144a` ★ | dev | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP Violet Treasuregill[TLC_438] 1/2 | HERO_POWER [HERO_09dbp] -> SELF hero hp27 (4) |
| 5 | `88153277` | dev | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP hero hp26 | HERO_POWER [HERO_09dbp] -> SELF hero hp26 (2) |
| 6 | `ae9048d5` | older | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP hero hp30+10armor | HERO_POWER [HERO_09dbp] -> SELF hero hp16 (2) |
| 7 | `f6dbfc91` | older | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP Scaled Lancer[CATA_898] 4/6 | PLAY_CARD [DINO_COIN2] (6) |
| 8 | `0efabc49` | dev | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP Twilight Mender[TLC_814] 3/4 | HERO_POWER [HERO_09dbp] -> SELF hero hp28 (6) |
| 9 | `da78e1a6` | older | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP hero hp30+2armor | HERO_POWER [HERO_09dbp] -> SELF hero hp21 (2) |
| 10 | `3996d0f9` | older | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP hero hp30+10armor | PLAY_CARD [JAIL_EVENT_COIN] (5) |
| 11 | `cdb8b53c` | older | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP Ultragigasaur[TLC_248] 14/28 | PLAY_CARD Shadow Word: Ruin[CORE_EX1_197] cost4 (5) |
| 12 | `57d93394` | older | HEAL_TARGET_DOMINATED | PROVEN_LOCAL | HERO_POWER [HERO_09dbp] -> OPP hero hp28 | END_TURN (3) |
| 13 | `ea1ad42d` | older | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | PLAY_CARD Hold Them Off![JAIL_913] cost3 -> OPP Darkrider[EDR_456] 5/6 | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP Darkrider[EDR_456] 5/6 (5) |
| 14 | `719b8abb` | older | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | HERO_POWER [EDR_449p] | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP Mug'Zee[JAIL_800] 6/7 (15) |
| 15 | `d7baa865` | dev | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | ATTACK The Great Dracorex[DINO_401] 5/7 -> OPP Undercover Cultist[TLC_101] 5/1 | PLAY_CARD Holy Embrace[JAIL_941] cost2 -> OPP hero hp13 (8) |
| 16 | `c4213d38` | dev | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | PLAY_CARD Medivh the Hallowed[TIME_890] cost0 | PLAY_CARD Flash Heal[CORE_AT_055] cost0 -> OPP hero hp30+2armor (7) |
| 17 | `193f8fba` | older | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | END_TURN | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP Soothsayer[JAIL_912] 4/6 (2) |
| 18 | `1c7b4e3b` | older | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | HERO_POWER [EDR_449p] | PLAY_CARD Holy Embrace[JAIL_941] cost2 -> OPP hero hp12 (3) |
| 19 | `ed6e3856` | older | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | PLAY_CARD Gravedawn Sunbloom[TLC_816] cost4 | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP hero hp17 (8) |
| 20 | `7ddb11e8` | dev | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | END_TURN | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP hero hp17 (7) |
| 21 | `99891553` | older | SANCTUM_FOLLOWUP_MISSED | PROBABLE_STRATEGIC | PLAY_CARD Eternal Firebolt[END_025] cost3 -> OPP Calia Menethil[CORE_CATA_002] 4/5 | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> OPP hero hp20 (24) |
| 22 | `c7424d36` | older | QUEST_COMPLETION_MISSED | PROBABLE_STRATEGIC | PLAY_CARD Kaldorei Priestess[EDR_970] cost3 | PLAY_CARD Hold Them Off![JAIL_913] cost3 -> SELF Lunarwing Messenger[EDR_449] 3/2 (16) |
| 23 | `109dc07d` | older | QUEST_COMPLETION_MISSED | PROBABLE_STRATEGIC | PLAY_CARD Lunarwing Messenger[EDR_449] cost2 | PLAY_CARD Eternal Firebolt[END_025] cost3 -> OPP Ravenous Felhunter[EDR_891] 5/3 (2) |
| 24 | `27c463b1` | older | QUEST_COMPLETION_MISSED | PROBABLE_STRATEGIC | HERO_POWER [EDR_449p] | HERO_POWER [EDR_449p] (1) |
| 25 | `0583da96` | older | QUEST_COMPLETION_MISSED | PROBABLE_STRATEGIC | PLAY_CARD Memoriam Manifest[TIME_616] cost4 | PLAY_CARD Eternal Firebolt[END_025] cost3 -> OPP Kaldorei Priestess[EDR_970] 3/3 (8) |
| 26 | `203c6751` | older | QUEST_COMPLETION_MISSED | PROBABLE_STRATEGIC | PLAY_CARD Lingering Spirit[CAP_803] cost2 | PLAY_CARD Lingering Spirit[CAP_803] cost2 (1) |
| 27 | `2a273017` | dev | QUEST_COMPLETION_MISSED | PROBABLE_STRATEGIC | HERO_POWER [EDR_449p] | PLAY_CARD Hold Them Off![JAIL_913] cost0 -> SELF Cleansing Lightspawn[TIME_427] 0/2 (8) |
| 28 | `046f7d88` | older | QUEST_COMPLETION_MISSED | PROBABLE_STRATEGIC | HERO_POWER [EDR_449p] | PLAY_CARD Intertwined Fate[TIME_432] cost3 (2) |
| 29 | `0b9571c0` | older | QUEST_COMPLETION_MISSED | PROBABLE_STRATEGIC | HERO_POWER [EDR_449p] | PLAY_CARD Eternal Firebolt[END_025] cost3 -> OPP Vicious Voidscale[JAIL_733] 1/1 (2) |
| 30 | `f24ddd60` | older | ATTACK_BAD_TRADE | PROBABLE_STRATEGIC | ATTACK Cleansing Cleric[CATA_216] 4/5 -> OPP Jailhouse Manastorm[JAIL_122] 5/5 | PLAY_CARD Hold Them Off![JAIL_913] cost1 -> SELF Cleansing Cleric[CATA_216] 4/5 (8) |
| 31 | `109564b5` | dev | AOE_RUIN_NO_TARGET | UNCERTAIN | PLAY_CARD Shadow Word: Ruin[CORE_EX1_197] cost4 | HERO_POWER [HERO_09dbp] -> SELF hero hp24 (3) |
| 32 | `4a1358a2` | older | AOE_RUIN_NO_TARGET | UNCERTAIN | PLAY_CARD Shadow Word: Ruin[CORE_EX1_197] cost4 | END_TURN (2) |
| 33 | `4ace66af` ★ | dev | AOE_RUIN_NO_TARGET | UNCERTAIN | PLAY_CARD Shadow Word: Ruin[CORE_EX1_197] cost4 | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> SELF hero hp19 (17) |
| 34 | `fbf54b3a` | older | AOE_RUIN_NO_TARGET | UNCERTAIN | PLAY_CARD Shadow Word: Ruin[CORE_EX1_197] cost4 | PLAY_CARD Flash Heal[CORE_AT_055] cost1 -> SELF Sinful Steed[CAP_800] 2/1 (5) |
| 35 | `423099a7` | older | FABLED_ORDER | UNCERTAIN | PLAY_CARD [TIME_890t] cost1 | PLAY_CARD Intertwined Fate[TIME_432] cost1 (2) |
| 36 | `5c00eecb` | older | FABLED_ORDER | UNCERTAIN | PLAY_CARD [TIME_890t] cost1 | PLAY_CARD [TIME_890t] cost1 (1) |
| 37 | `48017cc7` | dev | FABLED_ORDER | UNCERTAIN | PLAY_CARD [TIME_890t] cost10 | PLAY_CARD Medivh the Hallowed[TIME_890] cost10 (20) |
| 38 | `065c438b` | older | FABLED_ORDER | UNCERTAIN | PLAY_CARD [TIME_890t] cost10 | PLAY_CARD Medivh the Hallowed[TIME_890] cost10 (4) |

★ — ситуация уже разбиралась в ML-PILOT-1 / CONSEQUENCE-PILOT-1.
