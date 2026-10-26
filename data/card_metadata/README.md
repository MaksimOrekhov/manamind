# Полный слой метаданных карт (CARD-METADATA-2)

Полные снимки HearthstoneJSON `enUS`: коллекционные **и** неколлекционные записи (токены, создаваемые карты, Hero Powers,
Locations, оружие, зачарования, скины и записи других режимов). Слой только читает данные и предназначен для
исследовательских инструментов и будущих компонентов (Card IR, Text Policy, Turn Engine, Deck Builder).

**Он не подключён к модели.** Каталог `data/cards/standard_current_enUS.json`, `configs/standard_profile.json`, словари и
каталоги внутри checkpoint, LIVE и обучение его не читают и не импортируют. Запись в снимке означает только «клиентские
данные определяют такой ID». Это не доказывает легальность карты в формате и не означает поддержку эффекта движком.

| Файл | Что это |
|---|---|
| `manifest.json` | Список закреплённых снимков: сборка, патч, URL, дата загрузки, SHA-256 и размер исходных байтов, роль (`current` ровно у одного) |
| `hearthstonejson_255130_enUS.json.gz` | Текущий снимок: клиентская сборка 255130 (патч 37.0.0), 36 390 записей |
| `hearthstonejson_253216_enUS.json.gz` | Предыдущий снимок: сборка 253216 (патч 36.6.0), 36 022 записи. Его коллекционная часть байт в байт равна `data/cards/source_snapshots/cards_collectible_20261001_enUS.json` |

Файлы хранятся сжатыми (gzip с фиксированным заголовком); идентичность данных задаёт SHA-256 **распакованных** байтов из
манифеста. Загрузка проверяет её и размер, при расхождении выбрасывается `SnapshotIntegrityError`. Сети не требуется.

```python
from manamind.card_metadata import CardMetadata, Status

meta = CardMetadata.load()                      # текущий снимок; CardMetadata.load("hsjson_253216_enUS") — другой
found = meta.lookup("BE_009t1")                 # Status.FOUND | MISSING | AMBIGUOUS
card = meta.describe("BE_009t1")                # типизированное описание; None, если ID нет
card.card_type, card.cost, card.mechanics, card.is_token, card.flags, card.snapshot_id
```

* Отсутствующее значение остаётся `None`, ничего не подставляется. `flags` — независимые пометки качества записи
  (`MISSING_COST`, `EMPTY_TEXT_WITH_EFFECT_TAG`, `LAYOUT_MARKER_IN_TEXT`, …); запись они не исправляют.
* Дубликаты ID дают `AMBIGUOUS`; `get()` и `describe()` бросают `AmbiguousCardId` и не выбирают запись молча.
* В снимке сборки 254477 и новее есть артефакты текста: «лишний» `&` после `</b>`, запятой или точки (323 коллекционные
  карты) и отладочный хвост `~GAMEPLAY ASPROXY …` (10 записей). `plain_text()` и `strip_text_artifacts()` их убирают,
  сырые записи остаются как есть.

Добавить или проверить снимок (существующий файл никогда не перезаписывается):

```powershell
.\.venv\Scripts\python.exe -I scripts\fetch_card_metadata_snapshot.py --build 255130 --verify
```

Отчёт и воспроизводимые измерения: `reports/card_metadata_2/README.md`. Обновление снимка — отдельное явное действие,
а не загрузка `latest` при старте; смена `current` не меняет модель и её каталог.
