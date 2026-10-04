# Dynamic generation prerequisites — Vulcanos / Winterspring Whelp

## Решение

**DYNAMIC_POOL_ARCHITECTURE_REVIEW_REQUIRED**

Typed TakesDamage, конечные pool manifests и модификация стоимости экземпляра выглядят ограниченными reusable задачами. Однако полный Fire closure уже непосредственно требует временной замены Hero Power и Dark Gift. Вложенные пулы дополнительно достигают копирования, Reborn, истории, ресурсов и генерации из прошлого. Поэтому нельзя разрешить реализацию полного Vulcanos как небольшой изолированный пакет без архитектурного решения.

Это audit/planning, не implementation authorization. Production engine, declarations, GameState/encoder schema, canonical registry и evidence не изменены. Vulcanos, Whelp, training/search не запускались. Прежний Colossal audit сохранён.

## 1. Зафиксированная база и источники

- Ветка: `codex/manaengine-first-deck`.
- ManaMind HEAD: `1686256493293459b6fa6f863832f887416025f7`.
- RosettaStone gitlink: `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`.
- Profile: `standard_full_20261001_v1`, дата пула **2026-10-01**, дата аудита **2026-10-04**. Не смешивать эти даты.
- Pinned collectible snapshot SHA-256: `d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930`.
- Публичный full-definition ответ HearthstoneJSON SHA-256: `e8ea569a7ca1790c2258ed57c60798d808ffb057acb7bb73663c00ea174dae65`.
- Все 105 исходных root objects в дополнительном full-definition срезе совпадают с pinned metadata. Дополнительные noncollectible определения относятся к отдельно сохранённому текущему full-feed; это не доказательство их исторической версии на 1 октября.
- В отчёте сохранены 252 полных определения. Prefix matches служат поисковыми кандидатами, а не доказанными dependency edges.
- RosettaStone source references и canonical heuristic pool signals используются как implementation/reference clues. Они не устанавливают Hearthstone rules truth и не повышают ManaEngine support.

### Артефакты

| Файл | Содержание |
|---|---|
| [VULCANOS_FIRE_POOL_REVIEW.json](VULCANOS_FIRE_POOL_REVIEW.json) | Все 33 Fire кандидата: ID, name, classes, cost, school, collectible, set, declarations, независимый canonical status, provenance и hash |
| [WHELP_ONE_COST_POOL_PROVISIONAL.json](WHELP_ONE_COST_POOL_PROVISIONAL.json) | Все 77 сырых кандидатов, ledger Quest/Neutral и обе рабочие версии |
| [POOL_MEMBERSHIP_TABLES.md](POOL_MEMBERSHIP_TABLES.md) | Читаемые отсортированные таблицы обоих пулов |
| [POOL_OVERLAP_AND_UNION.json](POOL_OVERLAP_AND_UNION.json) | Пересечения, объединения и варианты membership |
| [DYNAMIC_GENERATION_CAPABILITY_MATRIX.json](DYNAMIC_GENERATION_CAPABILITY_MATRIX.json) | Полная ручная структурная классификация 105 контрактов, все требуемые измерения |
| [DYNAMIC_GENERATION_CAPABILITY_MATRIX.md](DYNAMIC_GENERATION_CAPABILITY_MATRIX.md) | Краткая таблица матрицы |
| [DYNAMIC_GENERATION_FAMILY_PLAN.md](DYNAMIC_GENERATION_FAMILY_PLAN.md) / [JSON](DYNAMIC_GENERATION_FAMILY_PLAN.json) | Размер, изменения, зависимости, риск, сложность и модель для каждого family bucket |
| [DYNAMIC_GENERATION_DEPENDENCY_GRAPH.json](DYNAMIC_GENERATION_DEPENDENCY_GRAPH.json) | Типизированные nodes/edges, candidate envelopes, unresolved frontiers, циклы |
| [DARK_GIFT_OPTION_REVIEW.json](DARK_GIFT_OPTION_REVIEW.json) | Официальные launch options, текущие metadata identities и ограничения доказательств |
| [build_dynamic_generation_audit.py](build_dynamic_generation_audit.py) | Воспроизводимая сборка planning outputs, пишет только в этот каталог |

В `DYNAMIC_GENERATION_CARD_REVIEW.json` сохранён ручной анализ текста каждой карты. Это не исполняемые declarations. Builder проверяет membership, SHA pinned snapshot и совпадение root metadata. Полная доказанная recursive closure здесь не заявляется.

## 2. Непосредственный путь Vulcanos

`CATA_488`: 7 mana, 4/8 Elemental, Colossal +2; end of own turn — 3 damage всем другим minions. `CATA_488t` и `CATA_488t2`: 1/5 Elementals, TakesDamage → random Fire spell → instance cost −3. Актуальные характеристики согласуются с [Blizzard 36.2.2](https://hearthstone.blizzard.com/en-us/news/24293284/36-2-2-patch-notes).

При двух здоровых appendages первый end-turn делает каждую 1/2 и создаёт две damage reactions. При достаточном месте в руке каждая реакция даёт отдельный generated instance. Следующий такой end-turn может убить обе части: ограничение только nonlethal не обеспечивает full Vulcanos correctness.

Colossal остаётся отдельным контрактом: appendage placement, capacity, порядок активации, play **и** summon entrypoints. Нельзя ограничить его hand-play: официальное описание охватывает и summon. [Blizzard: Voyage to the Sunken City](https://news.blizzard.com/en-gb/article/23784370/voyage-to-the-sunken-city-is-now-live).

## 3. Fire manifest: точный результат metadata, незавершённая runtime review

Предикат кандидатов: pinned Standard collectible canonical roots ∩ SPELL ∩ FIRE, **любой класс**. Нет зависимости от класса владельца appendage или наличия поддержки в ManaEngine.

**33 кандидата**, sorted-LF SHA-256:

```text
480f5971bdf90a339f08142a9f2e47c7650be1ddd6973241960885b20b3e0e87
```

Hash: уникальные ID, ordinal sort, UTF-8 без BOM, LF после каждого ID, включая последний.

| Вопрос | Решение / статус |
|---|---|
| Standard membership | Использовать pinned profile, не live catalog; будущие event releases не добавлять автоматически |
| Classes | ANY; dual-class `END_025` учитывается один раз, Mage/Priest membership сохранён |
| Neutral | Fire Neutral кандидатов в snapshot нет; не требуется предполагать исключение ради этого числа |
| Core aliases | Один exact canonical root ID; не добавлять legacy оригинал как второй билет RNG |
| Collectible | Только collectible для этого обычного random spell предиката; generated noncollectibles появляются отдельными зависимостями |
| Format bans | Пустой pinned ban ledger; ban на deckbuilding не переносить автоматически на generation |
| Event cards | Не исключать весь EVENT set; membership устанавливает profile + отдельное generation eligibility review |
| Rune exclusions | Ни один из 33 не требует суммарно 3 руны |
| Quest | Fire Quest hits отсутствуют |
| Non-generatable exceptions | Полного patch-specific exception/tag inventory и client outcome trace нет |

Blizzard исключает из Discover/random generation карты с **любой комбинацией трёх рун**, не только три одинаковые. [26.0.4 patch notes](https://hearthstone.blizzard.com/en-us/news/23935323/26-0-4-patch-notes).

**Статус:** `METADATA_AND_CARD_TEXT_REVIEWED_RUNTIME_ELIGIBILITY_NOT_PROVEN`, `runtime_admitted=false`. Число 33 установлено точно для указанного metadata predicate; оно пока не сертифицировано как полный Hearthstone runtime pool. Для финального runtime manifest остаётся rules exclusion review. Ограничение доказательств сохранено явно вместо выдуманного результата.

Сейчас declarations есть у **7/33**. Это source presence, не семь closure-verified исходов: Blazing Invocation открывает вложенный Discover; Molten Gold требует token/held-progress closure; Secret declarations имеют собственные границы.

## 4. Whelp: самостоятельный предикат и варианты

`CATA_484`: Battlecry — **Discover** a 1-Cost spell from any class. Проверяется **base cost**, не стоимость существующего экземпляра после discount.

| Срез | Количество | Статус |
|---|---:|---|
| Все pinned collectible SPELL cost=1 | 77 | Raw metadata candidates |
| Quest candidates | 12 | Рабочее исключение; сохранены для проверки |
| Nonquest, включая Neutral | 65 | Neutral eligibility ещё не установлена |
| Nonquest class spells | 63 | Рабочая provisional версия |

Рабочий hash 63 IDs: `d6e369266beea0f3c0bbc30532a3efcf06a5493011030511d732bbbec9e90cb3`.

Quest exclusion опирается на опубликованное developer statement, доступное в [зеркале HearthPwn](https://www.hearthpwn.com/news/2274-journey-to-ungoro-is-hearthstones-next-expansion?page=18); новый первичный replay не получен. Не переносить это исключение автоматически на Sidequest.

Два Neutral кандидата вынесены отдельно:

- `TIME_EVENT_999 Sands of Time`: Rewind и spell Discover.
- `TLC_EVENT_400 Storm the Gates`: Sidequest, составной Zombeast.

Трактовка «any class» для этих Neutral spells остаётся open rule gate. В отчёте сохранены обе версии, исключение не используется для заявления closure. Нет кандидатов с суммарно тремя рунами. Рабочие 63 содержат только **3 существующие declarations**.

Пересечение Fire с raw/working Whelp одинаково: **5** IDs — `CATA_585`, `CORE_GIL_836`, `CORE_SW_108`, `FIR_914`, `FIR_954`.

- Raw union: **105**.
- Union Fire + nonquest including Neutral: **93**.
- Union Fire + working class Whelp: **91**.

Whelp требует выбор трёх разных offer identities и typed pending continuation; random single-card sampling не заменяет Discover. Совместно переиспользуются manifest identity, generated-instance creation и admission, а не вся семантика выбора.

## 5. TakesDamage: предлагаемый ограниченный контракт

### Rules established / reviewed baseline

Положительный непредотвращённый damage packet создаёт damage occurrence в момент применения. Divine Shield absorption и Immune не создают TakesDamage occurrence; нулевой packet также не создаёт. Eligibility источника проверяется по состоянию эффекта на момент события, включая Silence. Контракт потребителя SELF-minion: получатель generated card — controller повреждённого minion, не damage dealer.

**Не вводить survival condition.** Blizzard прямо описывает damage-trigger effects на functionally dead minions; это первичное свидетельство против проверки «только если пережил damage». Оно не устанавливает все фазы конкретного appendage после удаления. [32.0 patch notes](https://hearthstone.blizzard.com/en-us/news/24187196/).

Spell / combat / effect / hero power используют общий `deal_damage`. Один успешный packet — одна occurrence; repeated instructions — несколько occurrences. Area damage фиксирует список целей группы, не превращается в повторный произвольный обход изменяющейся board. Порядок одновременных consumers нужен отдельный, с reviewed activation/timestamp policy.

### Что пока не установлено достаточно точно

- Damage-group boundary для реакций относительно других end-turn sources и death checks.
- Детали lethal/self-dying appendage resolution и дополнительных packets по functionally dead entity.
- Snapshot effect против live source после silence/removal/transform между enqueue и resolve.
- Lifetime и controller policy после control change.
- Точный interleaving nested reactions и area damage; combat должен учитывать обе стороны packet group.

Не делать вид, что наличие FIFO в текущем движке устанавливает Hearthstone ordering. До этих review допустим только явно bounded **nonlethal, unchanged-source** контракт, fail closed при выходе из него. Это допустимый scoped test contract, но не `DECK_READY`.

### Typed integration proposal

```text
deal_damage (единственный health/protection/attribution pipeline)
→ при успешном packet: typed DamageOccurrence
→ captured eligible SELF reaction descriptors
→ reviewed damage-group checkpoint
→ FIFO eligible damage reactions
→ existing batch death phase
```

Минимальные payload поля: damage kind/attribution, source handle, damaged handle, damaged controller, packet amount, health delta, sequence/group token, captured effect descriptor/pool identity. Entity IDs — internal handles, не новые policy features.

`packet amount`, armor absorption и health delta различать. Для minion consumer armor не участвует; future hero TakesDamage не считать проверенным через этот scoped contract.

Сейчас `TriggerKind` не имеет TakesDamage, а `resolve_end_turn_reactions` выполняет список EOT sources внутри одного handler. Простое добавление в общий deque отложит child reactions до завершения всего этого handler. Предлагается небольшой typed checkpoint/continuation внутри damage instruction group, **не** новый universal event bus и **не** рекурсивный глобальный `stabilize()` после каждого packet.

Какой именно checkpoint соответствует rules, требуется принять до кодирования. Сохраняются Spellweaver counters, Raincaller instruction boundary, Shield/Immune, batch deaths и activation ordering. Никаких appendage-ID callbacks или второго health mutation path.

Для bounded v1 preflight должен отказывать до mutation/RNG, если вся группа может попасть в unreviewed lethal/source-lifetime state. Альтернатива — invalid transactional branch. Нельзя молча пропустить reaction после уничтожения source.

План независимых scenarios: positive/zero/prevented damage; два appendages; обе стороны/controllers; Silence; multi-packet vs single area group; effect/spell/combat/hero-power attribution; ordering с другим EOT source; lethal/removed/transformed fail-closed cases. Ожидания должны быть review-derived, не сняты с реализации.

## 6. Generated instance operation

Концептуальное API, пока не production code:

```text
GenerateRandomCardToHand(owner, ReviewedPoolRef, GeneratedInstanceModifiers)
GeneratedInstanceModifiers v1 = { additive_cost_delta }
```

1. Проверить pinned manifest identity и reviewed admission contract.
2. Выбрать один ID существующим deterministic bounded RNG из **всего** manifest; uniform per canonical identity для обычной генерации — контракт для проверки, не перенос weighted Discover.
3. Unsupported выбранный outcome делает branch invalid; никаких rerolls/support filtering. При pool-wide training admission все outcome closures обязательны.
4. Создать новый instance с отдельной identity/provenance, применить `cost_delta -= 3`, затем общий hand-entry pipeline.
5. Не изменять catalog metadata; не повышать rules status из результата этого helper.

| Состояние | Политика |
|---|---|
| Base cost 1 или 2 | Stored delta остаётся −3; effective cost clamp до 0. Не обрезать stored modifier, иначе последующие modifiers меняют результат |
| Несколько одинаковых исходов | Отдельные entity IDs и modifiers; изменение одного экземпляра не меняет другой |
| Clone | Копировать engine RNG, queued typed payloads, pending state и modifiers; immutable manifest можно разделять |
| Full hand | Видимое переполнение нельзя превращать в замену карты. Точный generate/burn/cancel/RNG-consumption порядок пока не доказан; fail closed / review before admission |
| Shatter | Сначала modifier, затем reviewed hand arrival; текущий Shatter guard отвергает pre-split cost delta. Не обходить и не распространять discount на fragments без правила |
| INSTANCE_COPY | Session clone и gameplay copy — разные операции. Текущий INSTANCE_COPY_V1 по-прежнему отвергает cost_delta и hand buffs; helper не расширяет его |
| Hidden information | SELF видит результат в своей руке, opponent получает только разрешённые агрегаты/явные reveals; manifests доступны правилам, будущий RNG outcome не policy input |

Future Whelp должен использовать тот же commit selected-instance pipeline после typed Choice. Options не выкидываются из offer из-за отсутствия поддержки; выбранный неподдерживаемый результат invalidates branch. Любой unknown behavior блокирует evidence admission.

## 7. Finite manifest architecture

Минимальный versioned data object:

```text
pool_id / schema_version / contract_version
format_profile_id / as_of_date
typed predicate kind + bounded parameters (school/base_cost/class policy)
canonical sorted unique IDs / count / sorted-LF hash
metadata snapshot hash / root-membership hash
rules-review status + references + explicit exclusion ledger
predicate-contract fingerprint / option-rule fingerprint
per-outcome closure evidence identity (отдельно от membership)
```

Для source review `candidate_manifest` и admitted `runtime_manifest` различать. Наличие JSON не разрешает runtime correctness. Сейчас outputs — candidate manifests, `runtime_admitted=false`.

Build/audit tool заново вычисляет candidates по pinned источнику и сравнивает membership, predicate/exclusion identity. Runtime использует конечный reviewed manifest, не пересканирует произвольный текущий catalog. Изменение predicate или semantics инвалидирует evidence даже при неизменных ID.

Для class-dependent Discover понадобятся manifest variants по controller class, с dual-class membership. Hidden deck/hand/history selectors — **runtime-derived candidate sets по внутреннему состоянию**, а не притворно статический Standard manifest. Один общий typed interface допустим, один giant universal DSL не нужен.

Unknown predicate/options/fields/versions fail closed. Arbitrary expressions и LLM-generated executable predicates не исполняются. Support status хранится отдельно и не определяет pool membership.

## 8. Recursive graph и реальные blockers

Граф: **1628 nodes, 3031 edges**, два cyclic components. **275 unresolved pool frontiers** — главным образом унаследованные canonical heuristic signals; это не 275 доказанных разных механик.

Широкий candidate envelope достигает **1115 Standard cards**. Это **не** точный обязательный список и не оценка 1115 карт работы: all-minion source-cost envelope консервативен, часть ветвей условна, pool exclusions не завершены, большие frontier nodes не получили полного manual rules review. Число показывает риск разрастания; certified dependency closure отсутствует.

| Witness path | Вывод |
|---|---|
| Fire → `CORE_GIL_836` → Mage/Neutral Battlecry envelope (142) → `CATA_484` → working 1-cost spells → `CORE_GIL_836` | Candidate cycle; class/eligibility predicate review обязательна |
| Whelp → `JAIL_125` → Frost spells → `JAIL_125` | Второй candidate cycle; фиксированная точка closure, не рекурсивное развертывание без visited set |
| Fire → `CORE_WON_337` → random 4-cost minion envelope (130) | Root armor/damage helper не закрывает 130 candidate minion rules |
| Fire → `FIR_900` / `FIR_920` / `FIR_939` → minion Discover + Dark Gift | Прямой choice/enchantment/lifecycle blocker, не дальняя теоретическая ветвь |
| Fire → `TLC_632` → `TLC_632t`, `TLC_632t2` | Временная Hero Power, два использования и восстановление; нет такого authoritative state сейчас |
| Fire → `FIR_941` → actual deck minion → 8/8 copy + Shield | Недопустимо подменять узким INSTANCE_COPY_V1 |
| Fire → `TLC_221` → `TLC_249` | Sizzling Cinder — collectible 2/1 с random-split Deathrattle, не vanilla token |
| Whelp → `TLC_235` → same-cost replacement minions | Destroy snapshot, cost semantics, death/replacement ordering и большой pool |
| Whelp → `TIME_039` / `EDR_522` | Copy из opponent hidden zones; internal eligibility и observable reveals раздельны |
| Battlecry frontier → `CATA_EVENT_000` | Colossal «from the past»: non-Standard/Wild scope unresolved |
| Battlecry frontier → `EDR_519`, `JAIL_122`, `FIR_959` | Hero Power progression / persistent spell reactions / repeated random casts требуют отдельных review |
| Whelp → Smoldering Strength / Shield of Light | Reachable hand-buffed Bookkeeper остаётся fail-closed по принятому copy contract |

Все непосредственные fixed dependency identities матрицы найдены в сохранённом metadata срезе. Это identity resolution, не rules verification. Например: Shreds — `TIME_025t`; Found Gear — `JAIL_386t`; Ant options — `EDR_813a/b`, token `EDR_813at`; Imp-formant — `CAP_400t2t`. CastsWhenDrawn/SummonedWhenDrawn не закрываются обычным fixed summon.

Закрываемые простые компоненты: fixed damage без generation; First Flame → Second Flame с текущим узким контрактом. Общие подграфы: Mage/Neutral Discover, cost modifiers, draw/filter, fixed-token identity. Runtime deck selectors конечны в конкретном состоянии, но требуют полного state/history/provenance semantics, не только catalog predicates.

### Dark Gift — отдельная причина остановки

Официальное launch описание устанавливает десять Gift типов и три разных сочетания minion/Gift. Среди них on-play 2/2 copy, двойной Battlecry и Reborn с full health/enchantments. [Blizzard: Into the Emerald Dream](https://hearthstone.blizzard.com/en-us/news/24179067).

Patch 32.2 уточняет keyword eligibility и особое сохранение Dark Gift enchantments **для Wallow the Wretched при его Sweet Dreams переносе**. Это не общее разрешение сохранять buffs при backward zone movement. [Blizzard 32.2](https://hearthstone.blizzard.com/en-us/news/24198086).

Launch ten сопоставлены с metadata IDs в отдельном artifact. Дополнительные `EDR_100t4` и `EDR_100t10` присутствуют в full feed, но prefix presence не доказывает current runtime option membership. Они сохранены как unclassified, без произвольного включения/исключения. Поэтому даже option manifest требует review.

## 9. Capability grouping и ordered roadmap

Матрица содержит **51 family bucket для 105 raw candidates**. Это классификация, **не** 51 утверждённый package. Mixed facets разделять на маленькие reusable contracts; не делать dispatcher по card ID. Quest bucket не попадает в рабочую generation queue; Neutral buckets ждут predicate review. Размеры всех families и модели доступны в отдельной таблице.

Ниже условная очередь **после architecture/rules review**, а не разрешение реализации сейчас. F/W — число потенциально затрагиваемых outcome rules в Fire/working Whelp; existing declarations входят в число, это не verified gain. Пересечения не суммировать.

| Порядок / package contract | F/W | Fixed / transitive outcomes | Новая shared работа | Rules risk / complexity | Модель |
|---|---:|---|---|---|---|
| 0. Predicate/exclusion + phase review | 33/63 candidate universe | Closure count unknown | 0 executable primitives; принять manifests и boundaries | HIGH; решает право продолжать | Sol High |
| 1. `takes_damage_self_reaction_v1` | 0/0 spell rules; два appendages | 0 generated rules closed | 1 typed reaction + reviewed checkpoint | MEDIUM scoped / HIGH full lethal ordering | Sol Medium после review; High для ordering |
| 2. `finite_pool_generated_instance_v1` | 0/0 outcome rules | Manifest refs Fire/Whelp; closures пока 0 | Manifest loader/identity + one generated-instance operation | MEDIUM; full-hand/RNG + arrival guard | Sol Medium |
| 3. Direct damage + fixed follow-up verification | 4/4 combined candidate union 7 | `SW_108t`, static | Existing selectors/pipeline; выделить self-hero damage под отдельный universal target contract | LOW–MEDIUM bounded | Luna на existing-only subset; Sol Medium на target extension |
| 4. Damage outcome follow-up contracts | 2/4, union 5 | Один consumer имеет random 1-cost minion frontier (65), отдельно defer | Killed/survived result + owner draw/heal; separate narrow proposals | MEDIUM; random consumer HIGH closure | Sol Medium; Luna declarations после contract |
| 5. School-based hand discard composition | 2/0 | Actual hand instances; новых catalog outcomes нет | Reviewed discard selector + conditional follow-up | MEDIUM; draw/discard ordering | Sol Medium |
| 6. Smoldering held-age contract | 3/1, union 3 | `FIR_914e`; held instance age | Typed hand-age progression/expiry | MEDIUM; placeholders initial values/cap/phase unresolved | Sol Medium после rules review |
| 7. State-scaled/repeated damage | 3/0 | No generated catalog outcomes | Board snapshot expression, held-cost predicate, deck-size cost, repeat groups как отдельные bounded contracts | MEDIUM; не смешивать snapshots/order | Sol Medium |
| 8. Random distinct enemies | 1/0 | Runtime targets, не card pool | Distinct target sampling + damage group | MEDIUM; replacement/retarget semantics | Sol Medium |
| 9. Tribal multi-zone enchant / typed draw | 2/0 across two families | Actual deck / own Elementals | 2 узких contracts; zones и dual-race draw review | MEDIUM; Bookkeeper buff boundary сохраняется | Sol Medium |
| 10. Damage-scaled fixed summon | 1/0 | `TLC_249` + его split-damage DR | Damage result count / fixed summon composition + reusable random split | MEDIUM; amount vs damage dealt | Sol Medium |
| 11. Narrow typed Discover / random summon families | 2 Fire direct incl. existing Blazing, plus Whelp families separately | 142 Battlecry / 130 4-cost candidates; actual counts после predicates | Reviewed manifests / continuation / summon entrypoint | HIGH closure dominates, не giant package | Sol Medium infrastructure; High frontier audit |
| 12. Temporary Hero Power lifecycle | 1/0 | `TLC_632t/t2` | Authoritative active power / use count / restoration | HIGH fundamental state; architecture review | Sol High |
| 13. Dark Gift composition | 3 Fire directly / ≥2 working Whelp plus resource variant | Ten launch options + eligible minion envelopes; current membership unknown | Typed enchants, conditional offers, copy, multiplicity, Reborn | HIGH fundamental lifecycle/state; architecture review | Sol High |
| 14. Other Fire contracts/outliers | Остальные exact IDs в family plan | Deck copy, return/self-variant, resources, secret windows, random replacement | Отдельные честные proposals, CUSTOM при уникальности | MEDIUM–HIGH; никакого ID behavior в generic | Medium bounded / High architectural |
| 15. Colossal + Vulcanos consumer | Root 1 + appendages 2 | Требуются все admitted Fire outcomes и их closure | Colossal placement/capacity/play+summon; декларации consumer | HIGH until prerequisites closed | Sol High phase review, Medium bounded implementation |
| 16. Whelp consumer + remaining pool closure | Root 1 | Вся independently reviewed Whelp membership/closure | Battlecry Discover minion entrypoint + pending selection | HIGH frontier; consumer сам небольшой | Sol Medium; Luna declaration after contracts |

Пример P3: fixed-damage family — 3 Fire / 3 Whelp; First Flame family добавляет 1/1. Self-hero damage consumer нельзя притворно считать уже покрытым direct target pipeline. Каждая single-consumer reusable операция должна иметь независимую вторую declaration/control variation без generator changes. Torch/excess self-return, refreshable Skeleton Key и Zombeast предварительно отмечены как потенциальные CUSTOM/outliers, не как готовые generic branches.

Рекомендуемый reuse порядок — existing primitives/evidence прежде расширения; затем bounded shared composition; затем архитектурные зависимости. Но milestones 12–14 нельзя пропустить ради объявления Vulcanos/колоды готовыми.

Оценки времени здесь не выдумываются: это pre-implementation complexity ranking. Exact transitive verified gain неизвестен до independently reviewed closure; executable artifacts и новые evidence в этой задаче отсутствуют. Model routing — инженерная рекомендация: Luna для повторяемых declarations, Sol Medium для bounded contracts, Sol High для core/order/state; не измерение скорости или стоимости. [OpenAI deployment guidance](https://developers.openai.com/api/docs/guides/deployment-checklist).

## 10. Конкретные architecture decisions до кодирования

1. **Damage checkpoint.** Варианты: reviewed local damage-group continuation в существующих phases; либо расширение phase scheduler, если nested/lethal evidence этого требует. Предпочтение первому ограниченному варианту, но не выбираем порядок без rules review.
2. **Generation infrastructure отдельно от closure.** Можно разрешить scoped infrastructure с invalid unsupported branches; тогда статус остаётся experimental, не deck-ready. Полная pool closure требует отдельного утверждённого capability roadmap. Урезание pools не является вариантом для correctness.
3. **Hero Power / Dark Gift architecture.** Прямые Fire outcomes требуют решения об authoritative state, restoration, typed enchantment lifetime/copy/death. Текущие `PlayerState`/copy bounds их не покрывают. `GameState.hero_power` уже есть: не нужен schema bump только ради существующего поля, но remaining uses/restoration public Markov features требуют отдельной оценки.
4. **Runtime predicate proof.** Подтвердить exceptions Fire, Whelp Neutral/Quest policy и актуальный Dark Gift option pool; сохранить source/review evidence, не вручную поставить PASS.

Остановка обязательна при новых global event/death changes, choice continuation redesign, expanded copy/enchantment state, unsupported source snapshots, hidden/session resources, «from the past» unresolved scope, новых regressions при будущей реализации или попытке card-ID branch. Отдельно: nonlethal-only appendage контракт не может стать full Vulcanos admission.

## 11. Audit checks и границы результата

Builder проверяет 105 уникальных reviewed IDs, metadata identity, sorted pool hashes и direct fixed identity presence; outputs повторно воспроизводятся из сохранённых inputs. Graph closure честно `false`, оба runtime manifests не admitted. Ни одно rules/evidence значение не повышено.

Production tests/builds/CI не запускались: пользователь запросил analysis-only. Известный CI baseline на HEAD не переименовывается в результат этого audit. Неизменность production tracked files проверяется отдельно через git status/diff.

Audit elapsed: начало `2026-10-04 13:06:54 UTC`, контроль завершения `13:45:08 UTC`, **38 минут 14 секунд** непрерывного выполнения (включая tools, без ожидания пользовательского ответа). Это время анализа, не throughput реализации. Повторная сборка 10 производных outputs дала byte-identical результат. `git diff --stat` пуст; в `git status` только untracked материалы этого каталога, включая два сохранённых предыдущих audit-файла. HEAD не изменён, commit/push в этой analysis-only задаче не выполнялись.

**Итог:** reusable infrastructure разумна; утверждение «две реакции + 33 простые spell declarations закрывают Vulcanos» не подтверждается. Нужна архитектурная review перечисленных фаз и прямых lifecycle зависимостей до следующей реализации.
