# Первый capability package: сравнение кандидатов

Дата анализа: 2026-10-02. Пул закреплён на **2026-10-01**, профиль `standard_full_20261001_v1`. Источник — текущий canonical registry и исходники RosettaStone. Полные fingerprints карточек, исходные тексты и статусы сохранены в [JSON](capability_package_candidates_20261002.json).

Это shortlist после просмотра текстов unsupported draw/summon/buff/holding families, а не исчерпывающая классификация всех capabilities. «Reviewed candidate» здесь означает проверку соответствия закреплённого текста предложенному контракту и доступным исходным примитивам. Это **не** VERIFIED_SCOPED и не доказательство правил на runtime. Unsupported = `NO_DETECTED_RULE_REGISTRATION`; зарегистрированные control cases тоже не считаются автоматически корректными.

## Сводное сравнение

| Критерий | 1. minion_set_enchant_v1 | 2. held_card_gate_fixed_battlecry_v1 | 3. fixed_token_summon_v1 |
|---|---|---|---|
| Контракт | Постоянный фиксированный buff/keywords выбранного набора своих миньонов; target/board/hand, простой порог Attack | Battlecry: наличие подходящей карты в текущей SELF hand разрешает фиксированные эффекты | Неусловный немедленный summon фиксированных токенов на Battlecry/Deathrattle |
| Новые reviewed candidates | 3 | 5 | 5 |
| Unsupported среди новых | 3/3 | 5/5 | 5/5 |
| Declaration-only reuse после shared работы | Все 3; 4 существующих controls без переноса ownership | Потенциально все 5, но условный target legality и multi-race пока препятствия | Потенциально все 5, после разрешения всех токенов/keywords/позиций |
| Зависимости | 2 уже существующих фиксированных enchantments; новые карты не генерируются | Фиксированное self enchantment; hand predicate не является outcome pool | 6 описаний token outcomes; точные ID и число уникальных зависимостей UNKNOWN |
| Новые random/Discover pools | Не нужны в выбранном контракте | Не нужны в выбранном контракте | Не нужны в выбранном контракте |
| Shared стоимость | S–M: schema/validator + selection renderer + manifest/evidence | M–L: hand predicate + gated renderer + conditional targeting/parity; возможная доработка multi-race | M–L: точные token metadata/rules + dependency validation + summon-side renderer |
| Главный correctness risk | Выбор получателей до buff; silence/copy; hand→board; Elusive targeting | Current cost, источник уже ушёл из hand, dual-type Dragons, условный target | Отсутствующие token identities, Deathrattle position, полный board/Locations, Reborn |
| Training Profile v1 | Druid и Priest без новых широких outcome pools; DK позже отдельного session gate | Нейтральные Dragon-карты + Priest/Paladin; шире перенос между колодами, дороже legality | Druid/Paladin + нейтральные token minions; хороший дальнейший пакет, metadata блокирует оценку closure |

S/M/L — относительная стоимость **этого shortlist**, не сроки. Ни недель, ни общего срока окончания Standard здесь не оцениваем. Число shared work items и сценариев ниже — предварительная оценка объёма; actual authoring/review/debug/build time будет измерено в первом package.

## 1. minion_set_enchant_v1 — рекомендация

### Reviewed candidates и параметры

| ID / карта | Семантика | Сейчас |
|---|---|---|
| RLK_048 — Anti-Magic Shell | SPELL: всем своим board minions +1/+1 и Elusive | Unsupported |
| TLC_233 — Hatchery Helper | BATTLECRY: другим своим minions с текущим Attack ≤2 дать +1/+1 и Taunt | Unsupported |
| TIME_447 — Power Word: Barrier | SPELL: выбранному character Divine Shield; затем своим hand minions +2 Health | Unsupported |

TIME_447 использует общий minion-enchant контракт для второй части и отдельный существующий generic SetGameTagTask для первой. Это явная композиция двух параметризуемых действий, а не исключение по ID. Герои/вражеские персонажи разрешены текстом первой части; это нужно проверить в target/action сценариях, а не заменить minion-only targeting.

Controls: CAP_801 (target stats/keywords), CORE_CS2_009 (target enchantment), CORE_ULD_191 (friendly target Health), CORE_CFM_753 (hand minions). Они уже зарегистрированы; новые declarations/ownership для этих IDs не создаются. Их использование как controls не повышает статус правил. Остальные зарегистрированные cards этой широкой семьи не мигрируются ради PoC.

### Existing primitives и shared изменения

- `IncludeTask::GetEntities`: MINIONS и MINIONS_NOSOURCE выбирают именно своих board minions, MINIONS_HAND исключает spells/weapons. FRIENDS включает hero — для массового buff его использовать нельзя.
- `FilterStackTask` + `SelfCondition::IsAttack(..., LEQ)` используют текущий Attack; `AddEnchantmentTask`, `Enchant`, `Effects::AttackHealthN/HealthN`, `SetGameTagTask` уже существуют.
- Переиспользуемые фиксированные зависимости: `ICC_210e` (+1/+1, явный `Effects::AttackHealthN(1)` в generated C++) и `ULD_191e` (+2 Health, metadata и зарегистрированный Uldum CardDef). Проверить их независимыми expectations; сохранить по одному существующему владельцу. Не зависеть от эвристического парсинга текста как доказательства правил.
- Нужен один versioned selection/enchantment contract, строгий finite schema и renderer; allowlisted selectors/flags, отдельная output ownership/manifest metadata и family evidence. Никаких Python/C++ `card_id == X` для эффекта.
- Предварительно новые engine primitives и ABI изменения не нужны. Если family test выявит реальную ошибку существующего общего примитива, зафиксировать blocker и пересмотреть proposal, а не добавлять скрытый card-specific fix.

### Dependencies, outliers, риск и стоимость

Ни токены, ни random/Discover outcomes в этих трёх эффектах не создаются. Две фиксированные enchantment definitions — реальные зависимости с отдельными fingerprints/ownership/evidence, даже если они уже доступны. Пустые heuristic graph edges у unsupported roots не доказывают закрытый граф.

Outliers/deferred: RLK_958 (Undead targeting — native single-race representation требует отдельной проверки dual-type/ALL); CORE_BOT_576 (Combo activation); CORE_UNG_952/TLC_477 (добавленные Deathrattle и outcome); CATA_138 (размер buff зависит от board). Это кандидаты следующих reusable contracts, а не разрешение реализовать их по ID. Если потребуется ID-branch, эта реализация CUSTOM-first. Среди трёх выбранных новых cards ожидаемых CUSTOM веток нет; доказать это предстоит реализацией.

Стоимость S–M: **3 shared work areas** (schema/validation, renderer, traceable manifest/evidence), **3 declarations**, **2 dependency contracts** для независимой проверки, **12 групп native scenarios** и **4 группы bridge/import parity checks** из proposal. Один согласованный цикл generation→core build→bridge→family checks; количество исправлений и повторных builds пока UNKNOWN. Относительный риск умеренный. Основной риск — корректно зафиксировать selection timing и переносить enchantments/flags, не испортить stats/base metadata и silence.

Полезность: общий block для Druid board development и Priest handbuff/protection; третья card — DK, где отдельно остаётся hero/session gap. Это малая стоимость closure **эффектов**, а не закрытие целой колоды. Для будущего профиля Druid/Priest следует искать колоды без широких generation pools; текущих актуальных decklists/frequency inputs в registry нет, поэтому число колод, которые пакет закроет, **UNKNOWN**.

## 2. held_card_gate_fixed_battlecry_v1

### Reviewed candidates

| ID / карта | Hand predicate → действие | Сейчас |
|---|---|---|
| CATA_111 — Darkscale Broodmother | Dragon minion → refresh 2 Mana | Unsupported |
| TIME_062 — Chronicle Keeper | Dragon minion → self Taunt + Divine Shield | Unsupported |
| CORE_RLK_814 — Crystalsmith Cultist | Shadow spell → self +1/+1 | Unsupported |
| FIR_961 — Ashleaf Pixie | spell с текущей Cost ≥5 → self Divine Shield + Lifesteal | Unsupported |
| EDR_472 — Weaver of the Cycle | spell с текущей Cost ≥5 → targeted 3 damage | Unsupported |

Контракт: на разрешении Battlecry один раз проверить SELF hand после ухода разыгрываемого источника из неё, затем выполнить фиксированные effects при true. Нет истории «пока держал карту», Discover, Dark Gift predicate или скрытой hand противника.

Primitives: `ConditionTask` записывает flag, `FlagTask` переносит source/target в дочерние tasks; `SelfCondition::IsHoldingRace`, `Has5MoreCostSpellInHand` (использует `GetCost`, не base cost), `IsShadowSpell`, `RefreshManaTask` (ограничивает refresh общим Mana), `DamageTask`, `AddEnchantmentTask`, `SetGameTagTask`. Исторический BRM_033 демонстрирует ConditionTask→FlagTask→self enchantment; это non-Standard implementation control, не новый legal root. EDR_457 — возможный registered Dragon-gate control с weapon dependency; его не включаем в unlock count.

Shared changes: parameterized hand predicate по type/race/school/current cost с finite поля/комбинациями; один gated task sequence renderer; expose amount для RefreshManaTask и универсальное self enchantment; traceable contract/manifest. Минимум второго independent parameter variation для single-consumer school/refresh операции. Наивный перенос `Has5MoreCostSpellInHand()` как pseudo-generic с зашитой пятёркой не подходит.

Blockers: native `IsHoldingRace` сравнивает один `GetRace()`, loader читает одно `race`. Проверить dual-type/ALL и соответствие snapshot; исправление может затронуть headers/loader/targeting и требует отдельного measured design. Для EDR_472 доступность target должна совпадать с тем же hand predicate: недостаточно добавить ConditionTask, если bridge продолжит предлагать неправильные targets при false. `Card::Initialize` имеет Dragon-specific availability, но просмотренный код не даёт готового общего cost/school hand gate для targeting. Требуется отдельный contract/action audit; не считать эту card declaration-only до закрытия blocker.

Dependencies: фиксированное +1/+1 enchantment и существующие deck/hand entities. Hand predicate — **не** random outcome pool, но все карты выбранной колоды по-прежнему должны иметь корректные rules. Новых широких pools не ожидается.

Outliers: FIR_901/FIR_922/FIR_956 — Dark Gift/другие эффекты; TIME_213 — history while holding + draw; CORE_KAR_062 — gated Discover с большим Dragon pool. Не расширять пакет до них. При ID-dependent реализации CUSTOM-first; Dark Gift/history лучше рассматривать как отдельные reusable contracts.

Ожидаемый reuse: **5 declarations** после общего решения, условно на прохождение race/target legality blockers; до этого 5 — не гарантированный unlock. Стоимость M–L: 3 основных shared contracts/areas (predicate, gated effects, conditional target availability), 5 declarations, race audit/возможная native доработка, минимум 12 parameter/negative scenario groups и bridge action parity для true/false states. Correctness risk выше первого кандидата. Для Training Profile v1 полезно для нейтральных Dragon-карт, Priest и Paladin; количество закрываемых современных колод UNKNOWN без самих списков и graph audit. Хороший следующий пакет после проверенного stats/flags composition.

## 3. fixed_token_summon_v1

### Reviewed candidates

| ID / карта | Summon contract | Сейчас |
|---|---|---|
| TIME_017 — Tankgineer | DEATHRATTLE: один 7/7 Tank с Divine Shield | Unsupported |
| TIME_059 — Living Paradox | BATTLECRY: два 2/1 Living Paradoxes с Elusive | Unsupported |
| TLC_237 — Skyscreamer Eggs | DEATHRATTLE: четыре 2/1 Hatchlings | Unsupported |
| TLC_443 — Reluctant Wrangler | Reborn source; DEATHRATTLE: один 2/2 Undead Beast с Taunt | Unsupported |
| TLC_468 — Blob of Tar | DEATHRATTLE: 2/2 Poisonous Blob, затем 2/2 Taunt Blob | Unsupported |

Контракт: фиксированные reviewed token refs/count/sequence, controller источника, position согласно activation, последовательное ограничение вместимости shared board. Без случайного пула, scaled stats, delayed summon или forced attack.

Primitives: `SummonTask(cardID, amount, SummonSide)`, `SummonSide::DEATHRATTLE` использует last board position, `Generic::Summon`, существующие Deathrattle/Reborn/death processing. Native SummonTask останавливает действие при полном FieldZone. Нельзя просто переиспользовать current generic SUMMON default side для Deathrattle и считать positioning решённым. CORE_RLK_062 — registered Deathrattle summon control, без переноса его ownership.

Shared changes: finite summon-side/activation mapping в renderer; strict reviewed token schema + metadata snapshot/ownership для исходов; проверка токенов и transitive closure. Engine primitive для обычного summon уже есть, но interactions/Locations нужны в family scenarios.

Dependencies: тексты описывают **6 token outcome slots**, но точные token IDs и число уникальных узлов ещё не разрешены. В `Resources/cards.json` нет entries с префиксами этих пяти roots; pinned source snapshot/catalog содержат collectible roots, не полный non-collectible архив. Это не доказывает отсутствие токенов под другими IDs. Перед implementation нужна точная parent→token привязка из versioned metadata/rules source; нельзя выдумывать ID по имени, брать collectible Living Paradox с Battlecry вместо token или подменять token vanilla stats при неизвестном тексте.

Outliers: TLC_234 — Eternal Seedling с собственными правилами; TLC_622 — damage-trigger token; DINO_410 — цепочка Eggs; DINO_130 — summon плюс board buff; TIME_700 — duration Aura. Для них фиксированный summon лишь часть эффекта, поэтому сейчас не включать в пакет. Одноразовые ветки по их IDs были бы CUSTOM-first; reusable follow-up предпочтительнее.

Ожидаемый reuse: **5 declarations**, условно на точные token identities/rules. Стоимость M–L: 3 shared areas (reviewed token metadata/ownership, dependency validation, activation/position renderer), 5 declarations, 6 outcome descriptions, минимум 12 board/death/keyword scenario groups + native/bridge identity checks. Риск умеренный по summon, высокий по ещё неразрешённой metadata/closure; точная стоимость импорта UNKNOWN. Полезность для Druid token boards, Paladin и нейтральных sticky minions; DK остаётся зависимым от class session gate. Широких random pools нет, но известные токены могут иметь дополнительные правила — до их аудита это нельзя считать дешёвым полным closure.

## Выбор

Рекомендую **minion_set_enchant_v1**: минимальный набор новых shared механизмов, три новых consumers через один контракт, две уже доступные фиксированные зависимости, zero expected new random/Discover pools, нет нового action type и проблемы conditional target availability. Полезность для Druid/Priest сочетает переносимость с небольшой стоимостью closure. Размер пакета следует семантике, а не прежней норме batch size.

PoC должен доказать, что вторая и третья декларации не требуют изменения generator/native code, и измерить actual authoring/review/debug/build effort. Добавление трёх definitions без этого результата не будет успехом PoC.

Полноценные современные колоды здесь **не выбраны**. Registry не содержит current meta frequency/decklists и complete reviewed closures; пять исторических lists использовать как implementation queue нельзя. Поэтому deck unlock count и расписание Training Profile v1 пока UNKNOWN. После PoC потребуется актуальный dated набор deck candidates и расчёт всех deck roots, heroes/powers, outcomes, actions и session/match gates. В текущем профиле training eligibility остаётся 0.

Implementation не начат. См. [CAPABILITY PACKAGE PROPOSAL](../docs/proposals/20261002_minion_set_enchant_v1.md).
