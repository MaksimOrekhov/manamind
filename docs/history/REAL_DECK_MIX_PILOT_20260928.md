# Реальные колоды: self-play пилот от 2026-09-28

> Historical evidence only. Old queues, resume steps and permissions are inactive. Current rules: [AGENTS.md](../../AGENTS.md) and [capability-package process](../CAPABILITY_PACKAGE_PROCESS.md).

## Источники и составы

Тренировочная конфигурация находится в data/samples/mother_drake_combo_drake_selfplay.json.

1. **Mother Drake Warlock** — список Vicious Syndicate, опубликованный 23 сентября 2026 года: https://www.vicioussyndicate.com/decks/mother-drake-warlock/
2. **Combo Drake Warlock** — опубликованный код колоды из эпизода Walk to Work от 22 сентября 2026 года: https://podcasts.apple.com/ca/podcast/w2w-1643-legend-storytime-for-september/id1074167723?i=1000791092392

Для второй колоды её 30 карт автоматически сверены с опубликованным deck code через установленный декодер Hearthstone deckstrings. Обе колоды прошли validate_decks как Standard Warlock по 30 карт и завершили пробные симуляционные партии.

## Новый прогон

Новая policy обучена с нуля на зеркальных матчах этих двух списков: 48 игр, 6 циклов по 8 игр, seeds 71001–71048. Итог mirror игр — 24 победы за PLAYER1 и 24 за PLAYER2, без ничьих. Равный счёт ожидаем в self-play и сам по себе не измеряет качество модели.

Checkpoint: checkpoints/policy_real_deck_mix_48games_20260928.pt.

## Оценка на новых seed

| Сравнение | Результат | Примечание |
|---|---:|---|
| Новая модель против фиксированной эвристики | 71–9 (80 игр) | 88.75%; 95% Wilson interval: 80.0%–94.0% |
| Прежняя 48-игровая Mother Drake policy против той же эвристики и тех же двух колод | 76–4 (80 игр) | 95.0%; отдельный непересекающийся диапазон seed |
| Новая модель против прежней policy | 32–48 (80 игр) | Новая модель выиграла 40% матчей; 95% Wilson interval: 30.0%–51.0% |

Каждая оценка меняла сторону policy и порядок колод; в отчётах также есть контрольные матчи эвристики против самой себя. Новая модель проходит базовый тест, но эти результаты не показывают улучшения относительно прежней модели. Старый checkpoint остаётся более надёжным экспериментальным вариантом; новый следует сохранить для дальнейших исследований, а не считать заменой.

Отчёты:

- reports/policy_real_deck_mix_vs_baseline_20260928.json
- reports/policy_real_deck_mix_vs_mother_drake_pilot_20260928.json
- reports/policy_mother_drake_pilot_vs_real_deck_mix_baseline_20260928.json

## Границы вывода

Обе реальные колоды — близкие варианты Warlock с Mother Drake combo. Это расширяет обучение за пределы одной точной колоды, но пока не проверяет разные классы и не представляет всю текущую Standard-мету. Результаты получены только в RosettaStone и на двух колодах, чьи карты прошли текущий симуляторный gate; они ничего не доказывают про матчи против людей или ladder.
