# Архитектура: Card IR → ManaEngine

```text
declarations/*.json (card-ir/0.2)
   │  validate_strict_v02 — L1, FULL, 0 ошибок и предупреждений          (manamind.card_ir, без изменений)
   ▼
engine_translate.translate()  — чистая функция, allowlist узлов IR       (src/manamind/card_ir/engine_translate.py, новый)
   │  EngineSpec: шаги EFFECT_COMPOSITION + Overload + явные допущения
   ▼
engine_bridge.build_catalog() — свежая строка CardDefinition из метаданных + шагов   (reports/…/engine_bridge.py, новый)
   │  строки остальных карт и пулы — как у ManaEngineSession; нативная проверка каталога
   ▼
native.CardCatalog → native.GameSession → ManaEngineSession  (обычная прототипная сессия)
   ▼
attempt_action() на клоне → SimulationAttempt (COMPLETED / UNSIMULATABLE / ILLEGAL / ENGINE_DEFECT)
```

## Что используется повторно (без изменений)

* **ManaEngine C++**: шаги `Damage`, `Heal`, `BuffFriendlyMinions`, `DiscardRandomSpell`, флаг `lifesteal`,
  `requires_previous_discard`, поле `overload`; легальность целей выводится из селекторов шагов; конвейеры урона и
  лечения (Spell Damage `CURRENT_AT_STEP`, бонус лечения, ограничение по максимуму), фаза смертей, Overload, failure
  funnel, отравление сессии, глубокий `clone`. Нативный код, данные и тесты не менялись; сборка — обычная.
* **Нативная проверка каталога** (`NF-130:*`): например, у декларации без Lifesteal/Overload механика карты становится
  «непредставленной», и каталог не собирается. Мост превращает это в отказ `ENGINE_CATALOG_REJECTED`.
* **Python-адаптер**: `_load_definitions` (метаданные строк), `_parse_effect_steps` (строгий разбор шагов),
  `attempt_action`, `ManaEngineSession` (сессия создаётся так же, как в `__init__`, отличается только каталог).
* **Card IR**: строгий валидатор v0.2, словарь правил (основания ожиданий в сценариях).

## Что добавлено

| Файл | Роль |
|---|---|
| `src/manamind/card_ir/engine_translate.py` | IR → шаги. Не импортирует ничего из `manamind`, не смотрит на `card_id`. Каждый узел и поле либо потребляется, либо даёт `TranslationRefused(code, path)` |
| `reports/…/engine_bridge.py` | гейт «валидатор + транслятор», сборка свежей строки и каталога, запуск сессии |
| `reports/…/scenarios.py`, `pilot.py` | позиции, ожидания, мутации; прогон и `RESULTS.json` |
| `reports/…/real_evidence.py` | сверка с реальными наблюдениями EVIDENCE-0B (L4) |

Мост лежит вне `src/` намеренно: правила пакетов (`tests/test_card_ir.py`, `tests/test_card_metadata.py`) запрещают
импорт `manamind.card_ir` и `manamind.card_metadata` из остального `src/`. Первая версия моста в
`src/manamind/integrations/manaengine/` нарушала это правило и была перенесена; ослаблять границу без решения
пользователя не стал.

## Как обеспечено «исполняется IR, а не карта»

* Строка карты строится с нуля: из строки каталога копируются только метаданные (`card_id, name, card_type,
  card_class, race, spell_school, collectible, cost, attack, health, durability, minion_types`) и печатные механики;
  `ability`, `effects`, `overload`, `damage` и прочие поля поведения из `card_abilities.json` не читаются.
* Транслятор не читает `card_id` (тест: переименование карты не меняет шаги). Статическая проверка AST: в трансляторе
  и мосте нет строк-идентификаторов карт и сравнений `card_id` с литералом.
* 25 мутаций: 11 исполняются и **каждая** даёт результат, отличный от прежней декларации ManaEngine (B1 = 0 совпадений);
  14 отвергаются с типизированной причиной.
* `rules_contract_reviewed` (авторская защита движка «проверенный текст = текст карты») выставляется только если
  текст IR совпадает с текстом карты в закреплённом снимке движка (`ENGINE_TEXT_MISMATCH` иначе).

## Таблица трансляции

| IR | Шаг ManaEngine | Условие |
|---|---|---|
| `DEAL_DAMAGE {n, mark "$"}` → `ref` цели CHOSEN | `DAMAGE` + `EXPLICIT_CHARACTER` / `EXPLICIT_ENEMY_CHARACTER` / `EXPLICIT_MINION` | (тип, сторона) цели: (CHARACTER, ANY / ENEMY), (MINION, ANY) |
| `DEAL_DAMAGE` → `ALL` в PLAY | `ENEMY_MINIONS`, `ENEMY_CHARACTERS`, `ALL_MINIONS`, `ALL_CHARACTERS` | без `where`/`exclude` |
| `RESTORE_HEALTH {n, mark "#"}` | `HEAL` + `EXPLICIT_CHARACTER` / `EXPLICIT_FRIENDLY_CHARACTER` / `ALL_FRIENDLY_CHARACTERS` | |
| `ENCHANT ALL FRIENDLY MINION +a/+h` | `BUFF_FRIENDLY_MINIONS a` | `a == h > 0`; не после урона в той же последовательности |
| `ENCHANT {ref: set}` | `BUFF_FRIENDLY_MINIONS` | set создан `as` на «все свои существа», между ними только «нейтральные к доске» шаги (сброс) |
| `pay discard RANDOM 1 SPELL FRIENDLY HAND where spell_school` + `then` | `DISCARD_RANDOM_SPELL school` + следующий шаг с `requires_previous_discard` | школа NATURE/FIRE; `then` ровно один шаг |
| `seq` | порядок шагов сохраняется | |
| `keyword OVERLOAD amount` | поле `overload` | 1..10 |
| `keyword LIFESTEAL` у заклинания | `lifesteal` на каждом `DAMAGE` | хотя бы один шаг урона |

Всё остальное (другие операции, `if`, `repeat`, `trigger`, `aura`, `deathrattle`, миньоны, FULL_DEP/PARTIAL,
`reminders`, `unexpressed`, лишние поля, неверная метка числа) — отказ.

## Явные допущения трансляции (записываются в `EngineSpec.assumptions`)

* `ENCHANTMENT_AS_BASE_STATS` — бафф в движке не является отдельным enchantment. Внутри движка это ненаблюдаемо (в нём
  нет Silence), но для импортированной реальной позиции это различие станет важным (`R_ENCHANTMENT` UNVERIFIED).
* `REF_RESELECT_EQUIVALENT:<set>` — «them» = «все свои существа сейчас», доказано только для промежуточного сброса
  (движок отвергает сбросы с триггерами).

## Чего нет

* **Импорт произвольной позиции.** Позиции строятся только обычными ходами прототипной сессии. Реальное наблюдаемое
  состояние в ManaEngine не загружается (ограничение ENGINE-STATE-IMPORT-0 остаётся в силе). Обходов фиктивным
  состоянием нет.
* Миньоны (Battlecry), триггеры, ауры, токены (FULL_DEP), правила игрока (например, «лечение наносит урон»).
* Изменения нативного ManaEngine, правил допуска к обучению, LIVE/Policy — не делались.
