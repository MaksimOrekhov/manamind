# NUMERIC-COMBAT-ABLATION-1 — NO-GO

Четыре явных признака обычного боя усилили влияние текущего Attack, но **не исправили выбор атакующего на исходных численных парах: B 0/8, A 0/8**. На вариантах с неизвестными ID B решает 4/8 пар (все Attack), A — 0/8. Это ограниченное подтверждение полезности признаков при одинаковом identity embedding, но не успех основного критерия. Health и устойчивость при известных ID/перестановках позиций остаются нерешёнными.

Ровно два новых fits, одинаковые данные и порядок, одна заранее зафиксированная конфигурация. Новый control ранжировался только после выбора и сохранения обоих checkpoints. После открытия ни представление, ни конфигурация, ни эпоха не менялись. Production Policy, StateEncoder, LIVE, оверлей, Action Outcome и ManaEngine не изменены.

## 1. Как числа доходят до v2 и что изменено

`encode_policy_v2` передаёт текущие Attack/Health дважды: как action descriptors и как числовые поля source/target entity tokens. Action links выбирают точные локальные tokens. Entity tokens также содержат текущие Divine Shield, Poisonous, Immune, готовность и другие flags. Hero Armor и известность щита героя представлены отдельно. Разности `source_attack_minus_target_health` и `target_attack_minus_source_health` уже есть, с presence masks.

Числа нормализуются `sign(x)*log1p(abs(x))/log1p(10000)`: например, порог ATK 16 против HP 17 даёт разность −0.07526, ATK 17 — 0. Нормализация сохраняет различие, но сама не вычисляет смысл «убивает / переживает ответ». Текущие значения отделены от base metadata. Raw entity IDs не являются input; card identity embeddings размерности 32 участвуют и в tokens, и непосредственно в action query. Позиции присутствуют в descriptors/entity position и выборе linked source/target; query, attention и source×target взаимодействия смешивают их с числами через Tanh.

Это представление позволяет научиться сравнению, но не гарантирует его. В TL2 изменение чисел меняло logits B максимум на 0.02447, не дав правильной смены источника ни в одной паре. Здесь отдельно проверено, усиливает ли явно выраженное отношение влияние чисел.

Числовые поля имеют presence masks; hero Divine Shield — known mask. У обычных minion Divine Shield/Poisonous/Immune в текущем domain контракте тип `bool`, отдельных known masks в v2 tokens нет. Это не позволяет считать отсутствующий upstream-факт доказанным отсутствием эффекта. Experimental extractor поэтому дополнительно проверяет исходные сериализованные relevant flags и доступность metadata; он не исправляет уже утраченные upstream сведения и не переопределяет production контракт.

Минимальное изменение B — **4 новые колонки в первый Linear action projection**, всего 256 дополнительных весов при hidden64:

| Колонка | Значение |
|---|---|
| ordinary_target_destroyed | Положительный ATK, цель без Immune/Divine Shield, Poisonous источника либо ATK ≥ current HP цели |
| target_destroyed_known | Условия обычного взаимодействия подтверждены доступной metadata и наблюдениями |
| ordinary_source_survives | Immune/Divine Shield источника, нулевой ответный ATK либо отсутствие Poisonous цели и HP источника > её ATK |
| source_survives_known | Аналогичная маска известности |

Это **условные локальные свойства обычного minion→minion боя**, не полная стратегическая ценность и не полная предсказанная позиция. Hero attacks, non-attack actions и неподдержанный/неизвестный контекст получают `[0,0,0,0]`. Консервативно отказываемся от расчёта при недоступном/непустом тексте или mechanics любого существа, Reborn/Lifesteal/Windfury/Dormant, секретах, active effects, Locations, evidence constraints или неизвестных relevant flags. Глобальные реакции не моделируются. Неизвестный flag проверяется в исходной сериализации до преобразования, чтобы `None` не стал `False`.

Adapter читает только видимое состояние и доступную card metadata. Не читает goal, correct_actions, Outcome after-states или последствия. Для искусственных vanilla IDs metadata явно объявлена. Известный text/type берутся из закреплённого каталога, внешняя metadata не переиндексирует vocabulary. Старый v2 получает ровно прежние inputs. Mask означает отсутствие подтверждённого локального свойства; сама Policy при этом не обязана воздерживаться от рекомендации.

Новые колонки инициализированы **нулями**, общие веса скопированы побитово; initial max logit difference на tactical validation **0.0**. Новый head не прибавляет к score вручную заданный bonus. Все параметры обучаются тем же AdamW и LR. Изолированный `NumericCombatPolicy` использует отдельную checkpoint schema; production loader отвергает её. Checkpoint bundle B содержит `policy.pt` и companion `base.pt`, проверяет digest, ordered features, metadata, vocabulary/catalog и finite weights. Существующие checkpoint-схемы не менялись.

## 2. Какие признаки реально доступны

На текущем закрытом контроле маски ненулевые в 56/64 ситуациях: все сертифицированные атаки, кроме hero/non-attack действий. В 8 случаях явно отключена доступность metadata для extractor: колонки нулевые, gold отсутствует. Это контролируемая проверка отказа от арифметического утверждения при недоступной metadata, а не оценка неизвестных сложных карт по полному движку.

В tactical train ненулевые combat inputs есть в **128/192**, validation — **24/32**. Однако в разрешённых реальных данных **0/1175 train и 0/281 validation** решений проходят строгий ordinary-context gate. Новые признаки на real полностью маскированы. Поэтому этот пилот проверяет обучение на контролируемых задачах; он **не подтвердил пригодность такой консервативной схемы для реального боя**. Real CE меняется из-за обновления общих весов на tactical, а не прямого применения новых boolean к реальным атакам.

Пример Health: цель ATK 8 / HP 17, источники Poisonous ATK 3 с HP 9 или 8. Первый получает `[1,1,1,1]`, второй `[1,1,0,1]`. После перестановки HP эти векторы меняются местами. Удар в distractor со щитом не уничтожает его: первая колонка 0. Пример Attack: цель ATK 8 / HP 17, источник HP 10. ATK 17 получает `[1,1,1,1]`, ATK 16 — `[0,1,1,1]`. Это передаёт именно текущие пороги, независимо от base stats и card ID. [Полные значения выбранных примеров и coverage](feature_audit.json).

После выбранной epoch3 L2-нормы новых колонок: kill **0.10011**, kill-known **0.03001**, survive **0.01899**, survive-known **0.03001**; max |weight| 0.01417. Колонки ненулевые и участвовали в обучении; survival-путь получил заметно меньший вес. Нормы являются диагностикой, не причинным доказательством стратегического предпочтения.

## 3. Данные и два обучения

Использованы неизменённые проверенные TL2 train192 и validation32 — SHA файлов совпадает с TL2. Недействительный TL1 не обучал ни A, ни B. Real split прежний, по целым матчам: 32/1175 train, 7/281 validation. Реальный независимый test не открывался.

Новый control64 зафиксирован до fits: **16 base stats-ситуаций (8 пар), 16 position, 16 unknown-ID, 8 lethal, 8 unlabelled metadata-unavailable**. В source-задачах 5/6/7 источников, три Taunt, два со щитом. Health пары используют Poisonous и порог ответного урона; Attack пары — порог удаления цели. Перестановка текущего значения между двумя существами должна сменить единственного правильного источника, сохранив остальные факты. Unknown-ID варианты меняют только card IDs и соответствующую явно объявленную metadata; структурные и текущие поля сохраняются. Position варианты зеркально переставляют оба поля.

Все **288** train/validation/control строк прошли text/base/type/mechanics, legal menu, encoding и independent arithmetic vs exact Outcome до optimizers. Нормализованных клонов раскрытых TL1/TL2/MF1/MF2C controls нет. Шаблоны используют общие правила боя и заведомо простую metadata; повторные варианты и члены пар зависимы. Это маленький структурированный контроль, не 64 независимые игровые позиции.

Исходный checkpoint обоих SHA `d2f18737be46bc1773997ec5106d1e30fdf2caaf645a3a7c8998956f092d6377`. Seed42, AdamW LR0.0001 WD0.001, clip1, batch32, 50 steps/epoch. **Оба** получают одинаковые 1280 real + 320 tactical предъявлений за эпоху, одинаковый порядок Streams и dropout seed. Одинаковые set loss, split, budget и selection. Это отличается от TL2 A real-only: **здешний A тоже получает tactical**, чтобы единственным основным различием были новые колонки.

По **7 эпох / 350 шагов**, A 31.55 с, B 30.15 с CUDA с validation. Выбранная epoch **3 у обоих**. Tactical validation A 16/32, B 15/32; real guard исключил epochs4–7. [Протокол](PROTOCOL.md) заранее требует min tactical CE при real CE≤initial+0.03 и Top1≥initial−0.03; общий patience4. A воспроизвёл веса TL2 B **побитово**, что отдельно подтверждает сопоставимость обучения. Saved reload logits совпали побитово; B не заменял существующие checkpoints.

## 4. Независимый контроль и пары

Успех пары = обе рекомендации соответствуют доказанному локальному свойству **и** выбран правильный другой источник после вмешательства.

| Модель | Все certified | Base pairs | Position pairs | Unknown-ID pairs | Lethal |
|---|---:|---:|---:|---:|---:|
| frozen v2 | 10/56 | 0/8 | 0/8 | 0/8 | 4/8 |
| initial retrained | 0/56 | 0/8 | 0/8 | 0/8 | 0/8 |
| TL2 A (real-only) | 0/56 | 0/8 | 0/8 | 0/8 | 0/8 |
| TL2 B | 10/56 | 0/8 | 0/8 | 0/8 | 4/8 |
| A (matched v2+tactical) | 10/56 | 0/8 | 0/8 | 0/8 | 4/8 |
| **B (+numeric)** | **19/56** | **0/8** | **0/8** | **4/8** | **4/8** |
| B с нулевыми numeric inputs | 10/56 | 0/8 | 0/8 | 0/8 | 4/8 |

Все четыре успешные unknown-ID пары — **Attack**, Health остаётся 0/4 даже без известных ID. В исходных/position парах B не даёт ни одной правильной смены. Совокупные Attack случаи B 12/24 против A 4/24; Health B 3/24 против A 2/24. Весь прирост +9 находится в unknown-ID вариантах. Нельзя объявлять его переносом на исходные ситуации с известными embeddings.

| Unknown-ID pair | A ranks двух gold | B ranks двух gold | Правильные источники → B |
|---|---|---|---|
| Attack0 | 3,3 | **1,1** | 1→2, B 1→2 |
| Attack1 | 6,3 | **1,1** | 2→3, B 2→3 |
| Attack2 | 4,5 | **1,1** | 3→4, B 3→4 |
| Attack3 | 2,5 | **1,1** | 4→5, B 4→5 |
| Health0 | 4,5 | 4,4 | 1→2, B 5→5 |
| Health1 | 14,9 | 8,6 | 2→3, B 6→6 |
| Health2 | 9,12 | 5,8 | 3→4, B 7→7 |
| Health3 | 3,2 | 3,1 | 4→5, B 3→5; первый неверен |

Итоговая source agreement B **33.93%** против A 19.64%, target **100%** против 89.29% на 56 sourced/targeted случаях. Относительно A/TL2 B исправлены 9 ошибок, новых 0. Относительно frozen исправлены 15, добавлены **6 source ошибок**, все не lethal. Новых доказанных lethal-регрессий против A/frozen/TL2 B нет, но всё ещё пропущены 4/8 single lethal. [Все списки и gates](comparison.json).

Position robustness не подтверждена; unknown-ID успех только одного подтипа не означает полной ID-инвариантности. Исходные metadata embeddings и порядок всё ещё существенно меняют argmax. В unlabelled unavailable-context случаях B inputs нулевые, сохранённые logits B и numeric-zero совпадают точно во всех 8 случаях; качество рекомендации там не сертифицировано.

## 5. Logits и измеримый вклад колонок

Attack0, исходные IDs: max изменение logit при перестановке ATK A **0.02056**, B **0.08794**. Однако правильные источники 1→2, оба продолжают выбирать 4→4. С теми же stats и всеми неизвестными IDs A остаётся 5→5, а B меняет 1→2; max изменение B 0.08799. Значит новые признаки усиливают численную чувствительность примерно вчетверо, но при известных IDs этого недостаточно для смены argmax.

Health0: max изменение A 0.00282, B 0.00434; правильные источники 1→2, оба выбирают 4→4. Это гораздо более слабый эффект. [Все парные изменения, ranges, ranks и источники](pair_logits.json).

Posthoc input ablation выбранного B: выключение четырёх колонок снижает 19/56→10/56 и unknown-ID pairs 4/8→0/8. Это не третий обученный кандидат и не основание менять selection. Оно показывает непосредственный вклад нового input для выбранных весов. Одновременно успех только при одинаковом unknown embedding поддерживает гипотезу конкуренции между identity и механическим сигналом, но не доказывает единственную причину провала: ограничены обучение, шаблоны, масштаб признаков и общий scorer.

## 6. Real validation и раскрытые регрессии

| 7 whole validation matches / 281 решение | frozen | initial | TL2 A | A = TL2 B | B |
|---|---:|---:|---:|---:|---:|
| CE ↓ | 1.52652 | 1.52825 | 1.55812 | 1.54945 | **1.55032** |
| Top-1 | 56.23% | 52.31% | 53.02% | 51.60% | **51.60%** |
| Top-3, 231 eligible menus | 70.13% | 73.16% | 71.86% | 71.43% | **71.43%** |
| Source agreement, 213 | 51.64% | 45.07% | 46.48% | 43.66% | **43.66%** |
| Target agreement, 67 | 40.30% | 23.88% | 23.88% | 26.87% | **26.87%** |
| Predicted END / human gold 68 | 63 | 72 | 76 | 79 | **79** |
| END при human gold без END | 4 | 12 | 14 | 17 | **17** |

B CE хуже A на **0.000869**, остальные перечисленные discrete метрики одинаковы. Заданные safety допуски пройдены, но B не превосходит frozen и real win rate не измерялся. Real context masks в этом пилоте всюду нулевые, что особо ограничивает вывод о практической полезности.

95% paired whole-game bootstrap (7 матчей, seed42, 10 000 samples): B−A CE `[+0.000295; +0.001429]`, Top1 `[0;0]`; B−initial CE `[−0.01081; +0.05905]`, Top1 `[−3.90; +3.00]` п.п. Это reused validation, не независимый test; допуск по точечной оценке не доказывает неухудшаемость на других матчах. [Интервалы](real_uncertainty.json).

После selection на старом раскрытом TL2 control A и B получили **27/52**, lethal одинаковый, все 52 discrete рекомендации по признаку correct/error совпали с TL2 B: **0 fixed / 0 new errors**. B CE снизилась 1.44041→1.42193. Против frozen на этом раскрытом наборе сохраняются 19 fixed / 6 new, уже наблюдавшиеся в TL2, без новых улучшений Top-1. Это историческая диагностика, не независимый критерий и не источник настройки. [Регрессии](disclosed_TL2_regressions.json).

## 7. Вердикт и следующий минимальный шаг

**NO-GO** по заранее зафиксированному критерию: требовалось ≥4/8 base pairs и преимущество ≥2 над A; получено 0/8 и ноль преимущества. Position gate также не пройден. Unknown-ID gate, real допуски, selection guards и lethal safety прошли. Положительный результат в unknown-ID Attack-парах следует сохранить как узкое доказательство, но нельзя заменить им основной критерий после открытия контроля.

Механические boolean сами по себе в общем action projection за этот бюджет не дают устойчивого выбора источника. Kill чувствительность усилилась и работает при устранении различия identity; survival-сигнал слаб и не решает Health. Консервативный scope покрывает ноль реальных атак в разрешённом corpus.

Следующий минимальный шаг — отдельная ограниченная абляция **независимого numeric combat score**, чтобы проверить конкуренцию с identity: сохранить общий v2 score и обучать небольшой отдельный numeric residual с заранее фиксированным бюджетом/масштабом и новым независимым контролем. Сначала отдельно задать условные численные отношения и unknown-context masks для реальных атак, без заявления полного результата боя, и измерить coverage до fits. Не нужен большой encoder, engine или self-play. Этот отчёт не разрешает новый fit автоматически; оба разрешённых обучения уже выполнены. LIVE не подключать.

## 8. Артефакты и воспроизведение

Публично [config](../../configs/numeric_combat_ablation_1.json), [manifest](manifest.json), [gate](data_gate_summary.json), [protocol](training_protocol.json), [A history](history_A.json), [B history](history_B.json), [hashes](artifact_hashes.json). Raw JSONL, полные сертификаты, real IDs/построчные predictions/logits и checkpoints остаются ignored в `data/processed_numeric_combat_ablation_1/`.

A `runs/A/policy.pt`: SHA `c1d99af8710ea0540dc2976b7c17ce25d0852f4321dd8361dd162523bda728b7`.
B `runs/B/policy.pt`: SHA `9975909f8b714aa42c946da9409dd2eca2415716be806da41a83ce9400e3f210`; companion `runs/B/base.pt` обязателен, его digest сохранён в outer checkpoint и [hashes](artifact_hashes.json). Исходные frozen, retrained и TL1/TL2 checkpoints сохранены без изменений.

```powershell
.venv\Scripts\python.exe scripts/prepare_numeric_combat_ablation.py --config configs/numeric_combat_ablation_1.json --output <new-dataset>
.venv\Scripts\python.exe scripts/train_numeric_combat_ablation.py --dataset <new-dataset> --output <new-runs>
.venv\Scripts\python.exe scripts/evaluate_numeric_combat_ablation.py --dataset <new-dataset> --runs <new-runs> --output <new-evaluation>
```

Требуются сохранённые private inputs; повторно эти fits здесь не запускались. `report_numeric_combat_ablation.py` строит отчёт из сохранённых predictions без inference/optimizers. Dataset FITS_STARTED и runs CONTROL_OPENED не позволяют повторять обучение/открытие на тех же путях. Ветка `codex/numeric-combat-ablation-1` зависит от TL2 `6abb978`, поверх ещё не слитого TL1. Diff этой задачи смотрится относительно `6abb978`. Публикуется для review без merge/rebase.

Проверка: **ruff PASS**, offline pinned regeneration — 2 outputs reproduced, чистый diff каталога. Focused numeric+TL2 tests — **45 passed**. Full pytest в копии versioned source с новыми файлами — **977 passed, 1 skipped, 4 deselected**; четыре старых optimizer/training-теста исключены ради лимита двух новых fits. Копия не содержит старой непубликуемой `vendor/RosettaStone`, которая мешает migration guard в рабочем каталоге; папка сохранена без использования/изменений. Проверены source/input seals, сохранность исходных SHA, строгий schema rejection/reload и отсутствие real IDs/states/logits в публичных JSON. [Результаты проверок](verification.json).
