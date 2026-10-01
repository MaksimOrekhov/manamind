# Матрица покрытия актуальных колод Standard

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

Срез каталога: **2026-09-27**. Колоды взяты из сохранённых конфигураций и списков высокого ранга.
Всего: **5 колод**, **150 слотов**, **74 уникальных карт**.
Правила зарегистрированы для **67** карт; **7** текстовых карт требуют реализации.
Standard ban gate: **PASS** (снимок от 2026-09-29; нарушений: 0).

## Колоды

| Архетип | Класс | Источник | Слоты | Уникальные ID покрыты правилами | Ожидают поддержки |
|---|---|---|---:|---:|---:|
| Dragon Warrior | WARRIOR | [Hearthstone Meta Stats — Azeroth’s Most Wanted Legend list](https://metastats.net/hearthstone/decksbyrank/legend/patch/) (n=816, 55.92%) | 30 | 16/17 | 1 |
| Attack Druid | DRUID | [Hearthstone Meta Stats — Azeroth’s Most Wanted Legend list](https://metastats.net/hearthstone/decksbyrank/legend/patch/) (n=2902, 53.42%) | 30 | 17/20 | 3 |
| Quest Priest | PRIEST | [Hearthstone Meta Stats — Azeroth’s Most Wanted Legend list](https://metastats.net/hearthstone/decksbyrank/legend/patch/) (n=88, 54.38%) | 30 | 14/17 | 3 |
| Mother Drake Warlock | WARLOCK | [Vicious Syndicate](https://www.vicioussyndicate.com/decks/mother-drake-warlock/) | 30 | 19/19 | 0 |
| Combo Drake Warlock | WARLOCK | [Walk to Work podcast / Apple Podcasts](https://podcasts.apple.com/ca/podcast/w2w-1643-legend-storytime-for-september/id1074167723?i=1000791092392) | 30 | 19/19 | 0 |

## Покрытие механик

| Механика из каталога | Колоды | Неподдержанные карты |
|---|---|---:|
| AURA | Attack Druid, Combo Drake Warlock, Mother Drake Warlock | 0 |
| BATTLECRY | Attack Druid, Combo Drake Warlock, Dragon Warrior, Mother Drake Warlock, Quest Priest | 3 |
| CHARGE | Dragon Warrior | 0 |
| CHOOSE_ONE | Attack Druid, Quest Priest | 0 |
| COLOSSAL | Attack Druid | 1 |
| DEATHRATTLE | Combo Drake Warlock, Mother Drake Warlock, Quest Priest | 1 |
| DISCOVER | Attack Druid, Dragon Warrior, Mother Drake Warlock, Quest Priest | 0 |
| ELUSIVE | Dragon Warrior | 0 |
| ImmuneToSpellpower | Dragon Warrior, Quest Priest | 0 |
| LIFESTEAL | Combo Drake Warlock, Mother Drake Warlock, Quest Priest | 0 |
| QUEST | Quest Priest | 1 |
| START_OF_GAME_KEYWORD | Attack Druid, Combo Drake Warlock, Dragon Warrior, Mother Drake Warlock | 0 |
| TAUNT | Combo Drake Warlock, Dragon Warrior, Mother Drake Warlock, Quest Priest | 1 |
| TRADEABLE | Dragon Warrior | 0 |
| TRIGGER_VISUAL | Attack Druid, Combo Drake Warlock, Mother Drake Warlock | 1 |

## Очередь групп реализации

1. **Готовый Warlock-пул:** обе опубликованные колоды прошли прежний аудит правил и smoke-партии; оставить как опорную группу.
2. **Warrior — драконы, оружие и урон:** Battlecry/Discover с условием на дракона, временные и случайные эффекты, массовый урон, оружие, end-of-turn токены.
3. **Druid — атаки героя и развитие стола:** временная мана, эффекты от атак героя, выбор/Discover и перенос карт колоды, усиление по потраченной мане, большие призывы.
4. **Priest — исцеление и контроль:** Quest-награды, Holy/Shadow, Reborn/воскрешение, выбор целей, массовое уничтожение, лечение и добор.

Группы следует проверять отдельными игровыми сценариями и затем проходить всем пулом. Обучение и итоговая оценка допустимы только после того, как каждая колода создаёт полноценные завершённые партии без неподдержанных окон выбора.

## Ограничения допуска

- Список MetaStats является срезом пользовательских высокоранговых списков на 2026-09-27, а не полным официальным tier-листом.
- Две Warlock-колоды включены из ранее декодированных и проверенных конфигураций.
- Список банов хранится отдельно от RosettaStone; перед обновлением пула обновить датированный снимок и повторить этот gate.
- Наличие `CardDef` в исходниках — только инвентарный признак. Оно не заменяет проверку фактического эффекта.

Подробные строки по каждой карте: `reports/standard_meta_coverage_20260928.json`.
