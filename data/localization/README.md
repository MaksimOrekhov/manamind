# Display-only card names

`card_names_253932.json`: закреплённые названия ruRU/enUS, извлечённые из полного
HearthstoneJSON build **253932**, включая обычные карты, токены, силы героев,
локации и другие определения клиента. Только `id → name` обеих локалей; эффекты,
тексты и числовые параметры не интерпретируются.

Это официальные строки локализации клиента, опубликованные
[HearthstoneJSON](https://hearthstonejson.com/) по build/locale. Нет машинного перевода.
Полные URL и SHA-256 исходных байтов находятся в `sources` внутри snapshot.
English Standard model catalog и его источники не менялись.

36 022 идентификатора. RU использует `ruRU → enUS → card_id`; EN использует
`enUS → card_id`. Будущие или отсутствующие ID безопасно сохраняют fallback.
Runtime загружает только локальный JSON, без сетевых запросов.

Воспроизведение отдельно от игры:

```powershell
Invoke-WebRequest https://api.hearthstonejson.com/v1/253932/ruRU/cards.json -OutFile $env:TEMP\cards-253932-ru.json
Invoke-WebRequest https://api.hearthstonejson.com/v1/253932/enUS/cards.json -OutFile $env:TEMP\cards-253932-en.json
python scripts/build_card_names.py --ru $env:TEMP\cards-253932-ru.json `
  --en $env:TEMP\cards-253932-en.json --output $env:TEMP\card_names_reproduced.json
```

Builder проверяет закреплённые source hashes, сортирует идентификаторы и пишет UTF-8/LF.
Полные исходные cards.json нужны только для этой проверки; хранить их дубликаты в repo не нужно.
Обновление snapshot — отдельное явное действие, не загрузка `latest` при старте.
