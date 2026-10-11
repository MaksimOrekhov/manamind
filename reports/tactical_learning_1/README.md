# TACTICAL-LEARNING-1

**INCONCLUSIVE.** Выполнены ровно два обучения A/B, но финальный аудит обнаружил нарушение контракта тактических фикстур: генератор объявлял пустой текст для части известных card ID с непустыми способностями. В искусственно объявленном мире B проходит численные пороги (семь дополнительных основных ответов, без новых ошибок против A/initial), однако эти числа нельзя принять как результат механически корректного Hearthstone-контроля. Новых обучений после открытого контроля нет.

**Ошибка данных и её масштаб.** Отбор `not card.mechanics` ошибочно трактовался как vanilla. Из 25 использованных известных board ID 23 имеют текст в pinned каталоге; среди них `TIME_060` (двойной получаемый урон), `CORE_SCH_605` (урон соседним целям), `END_022` (условный Spell Damage). Непустой известный текст был заменён пустым в 93/128 train, 26/32 validation и 53/60 control записей. При подстановке настоящих текстов неизменённый Action Outcome отклоняет сертификат в 90/128 train, 26/32 validation и 45/60 control; восемь других затронутых control уже имели AMBIGUOUS и не проверялись на gold. Это conservative fail-closed отказ, не подсчёт всех реально изменившихся исходов. Полный [text integrity audit](text_integrity_audit.json) сохраняет ID, настоящий текст и основания отказов.

Декларирование synthetic vanilla alias допустимо для контролируемой фикстуры, но известный реальный ID нельзя считать эквивалентным при удалении его способности. Поэтому строгий gate валидности данных провален. Численные результаты, исходные JSONL, веса, manifest и истории сохранены без изменения. Не выделялся post-hoc «хороший» поднабор для нового GO. Генератор исправлен для будущего **отдельно разрешённого** эксперимента: настоящий пустой текст и пустые mechanics из pinned snapshot, совпадающие базовые cost/Attack/Health, без изменения vocabulary/catalog модели. Проверенный пул известной vanilla — `TIME_053`, `TLC_248`; дополнительные тела могут иметь явно заданные synthetic alias. Trainer отклоняет `dataset/INVALIDATED.json` до загрузки checkpoint и создания output. На старом наборе добавлен такой marker. Старое построение сохранено в коммите `f6ef82a` этой ветки; новый набор не генерировался и новые обучения не выполнялись.

**Доказательства улучшения реакции на Attack/Health нет:** все модели провалили четыре парных вмешательства даже в исходно объявленных фикстурах. B лучше совпадает с некоторыми synthetic lethal-метками и меньше зависит от ID в одном отложенном семействе; из-за дефекта текстов это не доказательство переноса механики реальных карт. У B есть две ошибки относительно frozen production в этих фикстурах, уже присутствовавшие у исходной retrained Policy и A.

## Протокол и данные

[Протокол до обучения](PROTOCOL.md), [конфигурация](../../configs/tactical_learning_1.json), [manifest](tactical_manifest.json), [зафиксированные входы/исходники](training_protocol.json). Старт ветки — `2a66108931bf0ab717eb54b6df870860b4986578`; соседние незавершённые ветки не объединялись. Архитектура PolicyNetworkV2, StateEncoder, vocabulary, Action Outcome, ManaEngine, production и LIVE не менялись.

Ровно два новых обучения, общий ранний останов на пятой эпохе. По 250 шагов оптимизации, одинаковые начальные веса/seed 42/правила выбора. A — 8000 real presentations; B — 6400 real + 1600 tactical, ровно 20%. Каждому доступны все 1175 real train решений; B видит все 128 tactical train за эпоху. Выбрана эпоха 1 у обоих по real validation CE с guard tactical validation. B на эпохе 5 достиг 23/32 tactical validation, но эта эпоха не была выбрана: CE 1.53381 хуже 1.52869 на эпохе 1. Дополнительных обучений после контроля нет.

Время A 84.98 с, B 25.63 с включает validation и конкуренцию с проверками исходников; это не сравнение скорости обучения. До входа в эпохи выполнялись загрузка и кодирование. Оба значительно укладываются в бюджет около 10 минут.

128 train / 32 validation / 60 control, 68 / 26 / 32 различных состояний после удаления ID, позиций, базовой метаинформации и номера хода. Повторные механические схемы и зависимые варианты уменьшают эффективный размер контроля; 60 нельзя считать 60 независимыми испытаниями. Основной gate считает только 32 сертификата среди 48 базовых ситуаций. Дополнительно 12 эквивалентных вариантов, 8 эвристических и 8 неоднозначных. Общие механики нужны для переноса, но сочетания семейств train/validation/control различаются. Проверены пересечения нормализованных состояний между split и со старыми MF1/2C; это проверка конкретных структур, не универсальное доказательство отсутствия любых смысловых аналогов.

Метки создавались независимо от Policy: арифметическая рецептура сверялась с неизменённым Action Outcome и ограниченным integer certificate winning-prefix. Он перебирает только до четырёх однократных атак против до двух обычных Taunt с нулевой Attack и героя с известными Shield/Armor; не возвращает GameState и не является универсальным симулятором. Факты были явно объявлены в synthetic мире, но их согласованность с текстами известных ID не проверялась — существенный дефект подготовки. В неоднозначных случаях Shield оставлен неизвестным и gold отсутствует.

Kill-and-survive — доказанное свойство, не глобально лучший ход. LOCAL_PARETO сравнивает шесть прямых эффектов без стоимости карт/маны, расхода готовности и будущих взаимодействий; END при чистом вреде — локальный сертификат. Недоминируемые действия могут иметь разные, несопоставимые последствия. Set-marginal CE суммирует вероятность всех допустимых действий, не выбирает произвольное одно.

Контрольные состояния создавались и сертифицировались до обучения; их **предсказания** впервые вычислены после сохранения A/B. `TRAINING_COMPLETE.json` и exclusive `CONTROL_OPENED.json` фиксируют порядок и препятствуют повторному runner. Результаты ниже получены из сохранённых logits без повторной оценки. Старые тесты использовались до обучения только для проверки пересечений; исторические предсказания — после выбора checkpoint.

## Реальное imitation agreement

Один сохранённый split: train 32 матча / 1175 решений (26 Priest, 5 Warrior, 1 DK); validation 7 / 281 (6 Priest, 1 Warrior). Тела старого real test из 16 матчей не читались. Эти метрики показывают совпадение с игроком, не оптимальность действий.

| Модель | Split | CE | Top-1 | Top-3 | Тип | Источник | Цель | END / N | False END† |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| frozen | train | 1.50124 | 55.66% | 67.65% | 76.94% | 52.13% | 40.14% | 274/1175 (23.32%) | 23 |
| frozen | validation | 1.52652 | 56.23% | 70.13% | 77.22% | 51.64% | 40.30% | 63/281 (22.42%) | 4 |
| initial | train | 1.20502 | 63.06% | 77.34% | 78.81% | 57.08% | 51.90% | 297/1175 (25.28%) | 29 |
| initial | validation | 1.52825 | 52.31% | 73.16% | 74.02% | 45.07% | 23.88% | 72/281 (25.62%) | 12 |
| A | train | 1.17308 | 64.26% | 77.03% | 80.77% | 56.96% | 52.25% | 324/1175 (27.57%) | 44 |
| A | validation | 1.53930 | 53.74% | 71.86% | 76.51% | 46.48% | 25.37% | 76/281 (27.05%) | 14 |
| B | train | 1.18363 | 64.77% | 76.82% | 81.02% | 57.77% | 57.79% | 320/1175 (27.23%) | 40 |
| B | validation | 1.52869 | 53.38% | 72.29% | 75.80% | 46.01% | 26.87% | 75/281 (26.69%) | 13 |

Top-3 считается для меню ≥3: train 949, validation 231. Источник: только non-END gold, 869/213; цель: только targeted gold, 289/67. Источник учитывает карту/hand slot либо attack handle, цель — side/kind/position/card. †False END здесь означает несовпадение с действием игрока, не доказанную игровую ошибку. Игрок END: 306/1175 и 68/281.

| Модель | Класс validation | N | CE | Top-1 | Top-3 |
|---|---|---:|---:|---:|---:|
| frozen | PRIEST | 248 | 1.51457 | 58.06% | 71.15% |
| frozen | WARRIOR | 33 | 1.61629 | 42.42% | 60.87% |
| initial | PRIEST | 248 | 1.52579 | 52.42% | 74.04% |
| initial | WARRIOR | 33 | 1.54670 | 51.52% | 65.22% |
| A | PRIEST | 248 | 1.52965 | 54.03% | 72.60% |
| A | WARRIOR | 33 | 1.61180 | 51.52% | 65.22% |
| B | PRIEST | 248 | 1.52442 | 53.63% | 73.56% |
| B | WARRIOR | 33 | 1.56078 | 51.52% | 60.87% |

Warrior validation — всего один матч, 33 решения: B/A/initial 17/33, frozen 14/33. B CE 1.56078 против A 1.61180 и initial 1.54670; отсутствие потери top-1 на одном матче не доказывает обобщение на Warrior. Все классы train и дополнительные диагностические метрики сохранены в comparison.json.

Парный bootstrap по семи целым validation матчам, seed 42, 4000 выборок: B−A CE 95% [-0.02984, 0.00862], top-1 [-0.98, 0.00] п.п. B−initial CE [-0.01369, 0.01355], top-1 [-0.66, 3.67] п.п. Интервалы отражают малый имеющийся корпус и не являются новой независимой проверкой игры.

## Числа контроля в исходно объявленном synthetic мире

Сертификаты ниже действуют **только при ошибочно объявленных пустых текстах**. Таблица сохраняет фактически выполненный эксперимент; её нельзя использовать как сертификат корректности реальных Hearthstone-действий.

| Модель | Базовые сертификаты /32 | Все /44 | Lethal miss /28 | Источник /40 | Цель /40 | Ошибочный END‡ | Эвристика /8 |
|---|---:|---:|---:|---:|---:|---:|---:|
| frozen | 19 | 25 | 8 | 27 | 29 | 9 | 4 |
| initial | 16 | 23 | 11 | 24 | 30 | 9 | 2 |
| A | 14 | 19 | 15 | 20 | 25 | 14 | 2 |
| B | 21 | 32 | 3 | 33 | 37 | 2 | 2 |

‡END вопреки сертифицированной выигрышной последовательности либо положительному прямому эффекту; это число не включает эвристические и неоднозначные позиции. Неоптимальность любого другого действия определяется лишь в пределах конкретного сертификата. В восьми неоднозначных позициях нет accuracy; выбор модели не становится утверждением об оптимальности.

| Категория (включая варианты) | N | frozen | initial | A | B |
|---|---:|---:|---:|---:|---:|
| hero_shield_finish | 14 | 7 | 6 | 3 | 12 |
| two_taunts | 14 | 13 | 11 | 10 | 13 |
| stats_target | 8 | 3 | 4 | 4 | 4 |
| two_self_damage | 4 | 0 | 0 | 0 | 0 |
| spell_side | 4 | 2 | 2 | 2 | 3 |

B против A: 13 исправлений / 0 новых / 12 общих ошибок на 44 сертификатах; на 32 базовых — 7 / 0 / 11. B против initial: 9 / 0 / 12 на 44, из них 5 исправлений на основных. B против frozen: 6 исправлений и **2 новых ошибки** (`hero_shield_finish_6`, `stats_target_6`), унаследованные от initial. Gate до обучения относился к A/initial, не к отсутствию любых ошибок против дополнительного frozen baseline.

| Парная проверка | frozen | initial | A | B |
|---|---:|---:|---:|---:|
| position: обе стороны верны | 6/6 | 5/6 | 4/6 | 6/6 |
| position: один семантический выбор | 6/6 | 6/6 | 5/6 | 6/6 |
| id: обе стороны верны | 0/6 | 2/6 | 0/6 | 5/6 |
| id: один семантический выбор | 1/6 | 5/6 | 4/6 | 5/6 |
| stats: обе стороны верны | 0/4 | 0/4 | 0/4 | 0/4 |
| stats: один семантический выбор | 4/4 | 4/4 | 4/4 | 4/4 |

Для position/ID одинаковый семантический выбор полезен; для stats требуется **сменить** источник, поэтому постоянство 4/4 означает провал. Две пары Health и две Attack меняют только соответствующее текущее значение; gold источник меняется у всех. Ни одна модель не сменяет источник. B position 6/6 против A 4/6 и initial 5/6; ID обе стороны 5/6 против 0/6 и 2/6. Это шесть пар в одном семействе: известный minion ID заменяется UNK при тех же базовых и текущих характеристиках. Механика эквивалентна, но представление известности ID меняется. Результат не доказывает независимость от всех ID и позиций.

## Исторические регрессии

| Модель | MF1 /11 | MF2C старый gold /400 | MF2C CE | MF2C Top-3 |
|---|---:|---:|---:|---:|
| frozen | 10 | 36 | 2.06149 | 94.00% |
| initial | 9 | 210 | 1.93450 | 83.25% |
| A | 10 | 193 | 1.90742 | 89.50% |
| B | 10 | 209 | 1.93987 | 80.00% |

MF1: A/B вернули t04, t11 остался ошибочным; у A и B одинаковые ошибки. MF2C B против A: 44 совпадения исправлены, 28 новых несовпадений; итог +16. B против initial: 209 вместо 210, CE немного хуже, Top-3 80% вместо 83.25%. Это **старый смешанный gold**, включающий эвристические размены и 36 неподтверждённых END из no_proven_gain, с unknown Hero Shield. Новые несовпадения не равны 28 доказанным игровым ошибкам. Никакой checkpoint не выбирался по этим числам.

## Конкретные синтетические случаи

S# / E# — SELF / OPPONENT board position. В as-run фикстурах тексты существ были объявлены пустыми и реакции отсутствующими; для известных ID это предположение часто неверно (см. аудит выше). Перечисленные Shield/Poison/Armor — заданные synthetic условия. Указан полный legal menu. Строки последствий описывают именно этот объявленный мир; метка `PROVEN_PROPERTY` — первоначальная классификация, не подтверждение пригодности после text audit.

### tl1_control_hero_shield_finish_0_0

SELF hero 20 HP, attack 10; board: #1 1/8 can_attack. OPP hero 6 HP + 4 Armor, Shield=True; board: пусто.

Меню: 0: S#1 → OPP Hero; 1: Hero → OPP Hero; 2: END.

Сертификат: `PROVEN_PROPERTY` / `WIN_BY_ATTACKS`; допустимые индексы: [0].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 2: END | нет | Нет изменений в заданной модели |
| initial | 2: END | нет | Нет изменений в заданной модели |
| A | 2: END | нет | Нет изменений в заданной модели |
| B | 0: S#1 → OPP Hero | да | OPPONENT hero.divine_shield: True -> False (attack damage); SELF board#1 TIME_053.can_attack: True -> False (the attack is spent) |

Атака minion 1 сначала снимает Shield; атака героя затем снимает Armor+HP и побеждает. Обратный порядок тратит сильный удар на Shield и оставляет лишь 1 damage, END упускает имеющуюся победу. Сценарий 6 показывает сохранившийся END-пропуск, которого frozen не делал.

### tl1_control_two_taunts_2_0

SELF hero 20 HP, attack 0; board: #1 1/8 can_attack; #2 1/8 can_attack; #3 1/8 can_attack; #4 8/8 can_attack. OPP hero 7 HP + 1 Armor, Shield=False; board: #1 0/1 taunt; #2 0/1 taunt.

Меню: 0: S#2 → E#1; 1: S#2 → E#2; 2: S#3 → E#2; 3: END; 4: S#1 → E#2; 5: S#4 → E#2; 6: S#3 → E#1; 7: S#1 → E#1; 8: S#4 → E#1.

Сертификат: `PROVEN_PROPERTY` / `WIN_BY_ATTACKS`; допустимые индексы: [0, 1, 2, 4, 6, 7].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 0: S#2 → E#1 | да | OPPONENT board#1 EDR_781.health: 1 -> 0 (-1) (attack damage); OPPONENT board#1 EDR_781 leaves play (death); SELF board#2 JAIL_204.can_attack: True -> False (the attack is spent) |
| initial | 5: S#4 → E#2 | нет | OPPONENT board#2 EDR_979.health: 1 -> -7 (-8) (attack damage); OPPONENT board#2 EDR_979 leaves play (death); SELF board#4 DINO_138.can_attack: True -> False (the attack is spent) |
| A | 3: END | нет | Нет изменений в заданной модели |
| B | 0: S#2 → E#1 | да | OPPONENT board#1 EDR_781.health: 1 -> 0 (-1) (attack damage); OPPONENT board#1 EDR_781 leaves play (death); SELF board#2 JAIL_204.can_attack: True -> False (the attack is spent) |

Любые два из трёх minion с Attack 1 удаляют два Taunt, третий слабый удар может идти в лицо; сильный атакующий добивает героя через Armor. Сильный первый удар в Taunt лишает выигрышной последовательности. Несколько правильных первых source/target не сводятся к одному gold.

### tl1_control_spell_side_0_0

SELF hero 20 HP, attack 0; board: #1 3/6 . OPP hero 30 HP + 0 Armor, Shield=False; board: #1 3/6 taunt.

Меню: 0: CORE_CS2_029 → SELF Hero; 1: CORE_CS2_029 → OPP Hero; 2: CORE_CS2_029 → E#1; 3: END; 4: CORE_CS2_029 → S#1.

Сертификат: `PROVEN_PROPERTY` / `LOCAL_PARETO`; допустимые индексы: [1, 2].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 1: CORE_CS2_029 → OPP Hero | да | OPPONENT hero.health: 30 -> 24 (-6) ('Deal $6 damage'); SELF player.available_mana: 4 -> 0 (-4) (pays 4 Mana); SELF player.hand_size: 1 -> 0 (-1) (card leaves hand); SELF hand#0 CORE_CS2_029 leaves the hand (card leaves hand) |
| initial | 3: END | нет | Нет изменений в заданной модели |
| A | 3: END | нет | Нет изменений в заданной модели |
| B | 1: CORE_CS2_029 → OPP Hero | да | OPPONENT hero.health: 30 -> 24 (-6) ('Deal $6 damage'); SELF player.available_mana: 4 -> 0 (-4) (pays 4 Mana); SELF player.hand_size: 1 -> 0 (-1) (card leaves hand); SELF hand#0 CORE_CS2_029 leaves the hand (card leaves hand) |

Fireball по OPP hero либо OPP minion имеет положительный прямой эффект без SELF damage. SELF hero/minion ухудшают SELF при одинаковой стоимости и отсутствии реакций; они доминируются альтернативами. B исправляет END-пропуск локально полезного действия. Это не утверждение о глобально лучшей цели.

### tl1_control_stats_target_0_0

SELF hero 20 HP, attack 0; board: #1 2/8 poisonous,can_attack; #2 2/5 poisonous,can_attack. OPP hero 30 HP + 0 Armor, Shield=False; board: #1 5/12 divine_shield; #2 5/12 taunt.

Меню: 0: S#1 → E#2; 1: END; 2: S#2 → E#2.

Сертификат: `PROVEN_PROPERTY` / `REMOVE_AND_SURVIVE`; допустимые индексы: [0].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 1: END | нет | Нет изменений в заданной модели |
| initial | 2: S#2 → E#2 | нет | OPPONENT board#2 DINO_404.health: 12 -> 10 (-2) (attack damage); OPPONENT board#2 DINO_404 leaves play (death); SELF board#2 CATA_529.health: 5 -> 0 (-5) (counter-attack damage); SELF board#2 CATA_529.can_attack: True -> False (the attack is spent); SELF board#2 CATA_529 leaves play (death) |
| A | 2: S#2 → E#2 | нет | OPPONENT board#2 DINO_404.health: 12 -> 10 (-2) (attack damage); OPPONENT board#2 DINO_404 leaves play (death); SELF board#2 CATA_529.health: 5 -> 0 (-5) (counter-attack damage); SELF board#2 CATA_529.can_attack: True -> False (the attack is spent); SELF board#2 CATA_529 leaves play (death) |
| B | 2: S#2 → E#2 | нет | OPPONENT board#2 DINO_404.health: 12 -> 10 (-2) (attack damage); OPPONENT board#2 DINO_404 leaves play (death); SELF board#2 CATA_529.health: 5 -> 0 (-5) (counter-attack damage); SELF board#2 CATA_529.can_attack: True -> False (the attack is spent); SELF board#2 CATA_529 leaves play (death) |

Парная сторона `tl1_control_stats_target_0_0`: SELF #1 2/8 poisonous,can_attack; #2 2/5 poisonous,can_attack; gold [0]; frozen: END; initial: S#2 → E#2; A: S#2 → E#2; B: S#2 → E#2.

Парная сторона `tl1_control_stats_target_0_0_health_swap`: SELF #1 2/5 poisonous,can_attack; #2 2/8 poisonous,can_attack; gold [1]; frozen: END; initial: S#2 → E#2; A: S#2 → E#2; B: S#2 → E#2.

После изменения Health атакующий должен пережить retaliation; после изменения Attack он должен достигнуть HP цели. Все модели сохраняют source ID и проваливают одну сторону пары. Правильная цель без правильного source недостаточна. Случай 6 также демонстрирует регрессию B относительно frozen, уже имевшуюся у initial.

### tl1_control_stats_target_4_0

SELF hero 20 HP, attack 0; board: #1 14/5 can_attack; #2 13/5 can_attack. OPP hero 30 HP + 0 Armor, Shield=False; board: #1 2/14 divine_shield; #2 2/14 taunt.

Меню: 0: S#1 → E#2; 1: S#2 → E#2; 2: END.

Сертификат: `PROVEN_PROPERTY` / `REMOVE_AND_SURVIVE`; допустимые индексы: [0].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 1: S#2 → E#2 | нет | OPPONENT board#2 TLC_248.health: 14 -> 1 (-13) (attack damage); SELF board#2 END_022.health: 5 -> 3 (-2) (counter-attack damage); SELF board#2 END_022.can_attack: True -> False (the attack is spent) |
| initial | 1: S#2 → E#2 | нет | OPPONENT board#2 TLC_248.health: 14 -> 1 (-13) (attack damage); SELF board#2 END_022.health: 5 -> 3 (-2) (counter-attack damage); SELF board#2 END_022.can_attack: True -> False (the attack is spent) |
| A | 1: S#2 → E#2 | нет | OPPONENT board#2 TLC_248.health: 14 -> 1 (-13) (attack damage); SELF board#2 END_022.health: 5 -> 3 (-2) (counter-attack damage); SELF board#2 END_022.can_attack: True -> False (the attack is spent) |
| B | 1: S#2 → E#2 | нет | OPPONENT board#2 TLC_248.health: 14 -> 1 (-13) (attack damage); SELF board#2 END_022.health: 5 -> 3 (-2) (counter-attack damage); SELF board#2 END_022.can_attack: True -> False (the attack is spent) |

Парная сторона `tl1_control_stats_target_4_0`: SELF #1 14/5 can_attack; #2 13/5 can_attack; gold [0]; frozen: S#2 → E#2; initial: S#2 → E#2; A: S#2 → E#2; B: S#2 → E#2.

Парная сторона `tl1_control_stats_target_4_0_health_swap`: SELF #1 13/5 can_attack; #2 14/5 can_attack; gold [2]; frozen: S#2 → E#2; initial: S#2 → E#2; A: S#2 → E#2; B: S#2 → E#2.

После изменения Health атакующий должен пережить retaliation; после изменения Attack он должен достигнуть HP цели. Все модели сохраняют source ID и проваливают одну сторону пары. Правильная цель без правильного source недостаточна. Случай 6 также демонстрирует регрессию B относительно frozen, уже имевшуюся у initial.

### tl1_control_two_self_damage_0_0

SELF hero 20 HP, attack 0; board: #1 5/1 ; #2 4/1 . OPP hero 30 HP + 0 Armor, Shield=False; board: пусто.

Меню: 0: END; 1: TL_DAMAGE_ALL.

Сертификат: `PROVEN_PROPERTY` / `LOCAL_PARETO`; допустимые индексы: [0].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 1: TL_DAMAGE_ALL | нет | SELF player.available_mana: 4 -> 3 (-1) (pays 1 Mana); SELF player.hand_size: 1 -> 0 (-1) (card leaves hand); SELF board#1 DINO_435.health: 1 -> 0 (-1) ('Deal $1 damage to all minions'); SELF board#1 DINO_435 leaves play (death); SELF board#2 CATA_615.health: 1 -> 0 (-1) ('Deal $1 damage to all minions'); SELF board#2 CATA_615 leaves play (death); SELF hand#0 TL_DAMAGE_ALL leaves the hand (card leaves hand) |
| initial | 1: TL_DAMAGE_ALL | нет | SELF player.available_mana: 4 -> 3 (-1) (pays 1 Mana); SELF player.hand_size: 1 -> 0 (-1) (card leaves hand); SELF board#1 DINO_435.health: 1 -> 0 (-1) ('Deal $1 damage to all minions'); SELF board#1 DINO_435 leaves play (death); SELF board#2 CATA_615.health: 1 -> 0 (-1) ('Deal $1 damage to all minions'); SELF board#2 CATA_615 leaves play (death); SELF hand#0 TL_DAMAGE_ALL leaves the hand (card leaves hand) |
| A | 1: TL_DAMAGE_ALL | нет | SELF player.available_mana: 4 -> 3 (-1) (pays 1 Mana); SELF player.hand_size: 1 -> 0 (-1) (card leaves hand); SELF board#1 DINO_435.health: 1 -> 0 (-1) ('Deal $1 damage to all minions'); SELF board#1 DINO_435 leaves play (death); SELF board#2 CATA_615.health: 1 -> 0 (-1) ('Deal $1 damage to all minions'); SELF board#2 CATA_615 leaves play (death); SELF hand#0 TL_DAMAGE_ALL leaves the hand (card leaves hand) |
| B | 1: TL_DAMAGE_ALL | нет | SELF player.available_mana: 4 -> 3 (-1) (pays 1 Mana); SELF player.hand_size: 1 -> 0 (-1) (card leaves hand); SELF board#1 DINO_435.health: 1 -> 0 (-1) ('Deal $1 damage to all minions'); SELF board#1 DINO_435 leaves play (death); SELF board#2 CATA_615.health: 1 -> 0 (-1) ('Deal $1 damage to all minions'); SELF board#2 CATA_615 leaves play (death); SELF hand#0 TL_DAMAGE_ALL leaves the hand (card leaves hand) |

Неизвестная Policy карта с явно заданным текстом `Deal 1 damage to all minions` за 1 mana уничтожает два SELF minion с 1 HP; врагов нет, Deathrattle/реакции отсутствуют. END сохраняет их. Все четыре модели рекомендуют вредный cast. B не переносит учебный вариант с одним SELF minion на два. Текст используется только teacher, архитектура Policy текст не получает.

### tl1_control_hero_shield_finish_6_0

SELF hero 20 HP, attack 8; board: #1 1/8 can_attack. OPP hero 7 HP + 1 Armor, Shield=True; board: пусто.

Меню: 0: Hero → OPP Hero; 1: END; 2: S#1 → OPP Hero.

Сертификат: `PROVEN_PROPERTY` / `WIN_BY_ATTACKS`; допустимые индексы: [2].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 2: S#1 → OPP Hero | да | OPPONENT hero.divine_shield: True -> False (attack damage); SELF board#1 EDR_781.can_attack: True -> False (the attack is spent) |
| initial | 1: END | нет | Нет изменений в заданной модели |
| A | 1: END | нет | Нет изменений в заданной модели |
| B | 1: END | нет | Нет изменений в заданной модели |

Атака minion 1 сначала снимает Shield; атака героя затем снимает Armor+HP и побеждает. Обратный порядок тратит сильный удар на Shield и оставляет лишь 1 damage, END упускает имеющуюся победу. Сценарий 6 показывает сохранившийся END-пропуск, которого frozen не делал.

### tl1_control_stats_target_6_0

SELF hero 20 HP, attack 0; board: #1 14/8 can_attack; #2 15/8 can_attack. OPP hero 30 HP + 0 Armor, Shield=False; board: #1 5/15 divine_shield; #2 5/15 taunt.

Меню: 0: END; 1: S#2 → E#2; 2: S#1 → E#2.

Сертификат: `PROVEN_PROPERTY` / `REMOVE_AND_SURVIVE`; допустимые индексы: [1].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 1: S#2 → E#2 | да | OPPONENT board#2 EDR_781.health: 15 -> 0 (-15) (attack damage); OPPONENT board#2 EDR_781 leaves play (death); SELF board#2 EDR_469.health: 8 -> 3 (-5) (counter-attack damage); SELF board#2 EDR_469.can_attack: True -> False (the attack is spent) |
| initial | 2: S#1 → E#2 | нет | OPPONENT board#2 EDR_781.health: 15 -> 1 (-14) (attack damage); SELF board#1 TLC_429.health: 8 -> 3 (-5) (counter-attack damage); SELF board#1 TLC_429.can_attack: True -> False (the attack is spent) |
| A | 2: S#1 → E#2 | нет | OPPONENT board#2 EDR_781.health: 15 -> 1 (-14) (attack damage); SELF board#1 TLC_429.health: 8 -> 3 (-5) (counter-attack damage); SELF board#1 TLC_429.can_attack: True -> False (the attack is spent) |
| B | 2: S#1 → E#2 | нет | OPPONENT board#2 EDR_781.health: 15 -> 1 (-14) (attack damage); SELF board#1 TLC_429.health: 8 -> 3 (-5) (counter-attack damage); SELF board#1 TLC_429.can_attack: True -> False (the attack is spent) |

Парная сторона `tl1_control_stats_target_6_0`: SELF #1 14/8 can_attack; #2 15/8 can_attack; gold [1]; frozen: S#2 → E#2; initial: S#1 → E#2; A: S#1 → E#2; B: S#1 → E#2.

Парная сторона `tl1_control_stats_target_6_0_health_swap`: SELF #1 15/8 can_attack; #2 14/8 can_attack; gold [0]; frozen: S#2 → E#2; initial: S#1 → E#2; A: S#1 → E#2; B: S#1 → E#2.

После изменения Health атакующий должен пережить retaliation; после изменения Attack он должен достигнуть HP цели. Все модели сохраняют source ID и проваливают одну сторону пары. Правильная цель без правильного source недостаточна. Случай 6 также демонстрирует регрессию B относительно frozen, уже имевшуюся у initial.

### tl1_control_ambiguous_face_0_0

SELF hero 20 HP, attack 0; board: #1 4/10 lifesteal,can_attack. OPP hero 30 HP + 0 Armor, Shield=None; board: #1 5/3 .

Меню: 0: S#1 → OPP Hero; 1: END; 2: S#1 → E#1.

Сертификат: `AMBIGUOUS` / `AMBIGUOUS`; допустимые индексы: [].

| Модель | Рекомендация | Сертификат | Немедленные последствия |
|---|---|---|---|
| frozen | 2: S#1 → E#1 | нет gold | Не сертифицировано: Hero Shield неизвестен |
| initial | 2: S#1 → E#1 | нет gold | Не сертифицировано: Hero Shield неизвестен |
| A | 2: S#1 → E#1 | нет gold | Не сертифицировано: Hero Shield неизвестен |
| B | 2: S#1 → E#1 | нет gold | Не сертифицировано: Hero Shield неизвестен |

Shield неизвестен: нельзя сертифицировать damage/победу в лицо. Убийство minion либо face attack могут иметь разные будущие последствия. Все рекомендации — наблюдения ранжирования, не ошибка относительно оптимального хода; accuracy отсутствует.

## Пороги, сохранность и проверка

Семь численных gate прошли, но результат отклонён из-за нарушенной валидности данных. В [comparison.json](comparison.json) сохранены исходный `as_run_numeric_verdict: GO` и окончательный `verdict: INCONCLUSIVE`; все 60 as-run исходов — [scenario_audit.csv](scenario_audit.csv), истории — [training_history.json](training_history.json). Для использования Attack/Health четыре пары дали отрицательный ответ; дополнительный тактический сигнал в корректном карточном мире остаётся непроверенным. Новый эксперимент потребует исправленных train/validation и нового, заранее отложенного контроля, в отдельной разрешённой задаче.

| Артефакт | SHA-256 |
|---|---|
| frozen | `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d` |
| initial | `d2f18737be46bc1773997ec5106d1e30fdf2caaf645a3a7c8998956f092d6377` |
| A | `54f837cac6cb1f5abdca829312ddf9439052732bcc417d74246c7dbe8cf0df79` |
| B | `bf39816c90c3dcb282f50b71e7745da1d0a291452f1c77509bf8d1ac018c6820` |
| control | `12f51f92670233538f8c63b81e21b39f04db0f1756bf58073fea0d710b6b1fb2` |
| train | `a2af5129216fadb36398eb625b65f30cd157beb1c325442c1b6d11a558f9d05e` |
| validation | `27c0317ff23cd0934976139e5199461ebd6111a59db5acb920de66852aa4108d` |

Локальные checkpoints: `data/processed_tactical_learning_1/runs/A/policy.pt`, `runs/B/policy.pt`. A обучался только на реальных действиях; B содержит невалидированный tactical сигнал. Оба экспериментальные, не для LIVE. Новые JSONL и подготовительные smoke-папки, checkpoints, per-decision реальные predictions и control-open marker остаются в ignored `data/processed_tactical_learning_1/`. Checkpoint сохраняет собственные config/weights, исходный vocabulary/catalog/feature contract, split identity и ссылку SHA на tactical manifest. Два strict roundtrip сохранили CPU logits побитово. Frozen/initial SHA неизменны.

Воспроизведение в новом выходном каталоге с локальными исходными данными: `prepare_tactical_learning.py --config configs/tactical_learning_1.json --output NEW_DATA`, затем `train_tactical_learning.py --dataset NEW_DATA --output NEW_RUNS`, после завершения `evaluate_tactical_learning.py --dataset NEW_DATA --runs NEW_RUNS --output NEW_EVAL`. Публикация кода не является разрешением автоматически повторить обучение; в этой задаче выполнены только два запуска. Старый MF2C путь зафиксирован в manifest; отсутствующие локальные private inputs не подменяются новыми.

Проверки: ruff всего src/scripts/tests — PASS; offline regeneration — два pinned artifacts побайтно воспроизведены с нормализацией LF, Standard состав не менялся. Общий pytest: 928 passed, 1 skipped, 3 deselected, **1 предсуществующий failure** migration guard из-за локального untracked каталога старого vendor. Его не удаляли и не подключали. Три deselected теста запускают дополнительное обучение, поэтому исключены при явном лимите двух запусков. Финальный новый regression suite — 29 passed, включая различение empty mechanics и настоящего текста и отказ trainer на invalidated dataset.

После завершения эксперимента усилена граница integer certificate: герой входит в лимит четырёх источников, противоречивые frozen/dormant/zero-Attack источники и ненаблюдаемая готовность героя отклоняются. Для всех 220 зафиксированных train/validation/control записей множества сертификатов остались идентичны. Веса, прогнозы и метки не менялись; новых оптимизаций нет. Manifest/protocol сохраняют SHA исходников **на момент подготовки и обучения**, а окончательная проверка кода/неизменности сертификатов записана в `post_experiment_validation.json`.

Новые регрессии проверяют независимые сертификаты и старый encoder, несколько gold и градиент set-loss, запрет unknown Shield, отсутствие gold у ambiguity, инвариантность сертификата по позициям, смену gold после Attack/Health, охват real pool, запрет чтения real test и повторного открытия контроля. Они не запускают optimizer. Public report содержит агрегаты реальных решений и только синтетические состояния; private Power.log, реальные game IDs/имена/hidden data и checkpoints не публикуются.
