# ML-2A — Policy v2 representation

Ветка: `codex/ml2a-policy-v2`, без merge. Точная основа:
`1750e9403ef44c27f0e9d52fe361804ceb49ecc5` — принятая LIVE-0C с исправленным
privacy verdict. Она содержит main `9dc969d5e70025107d8b3099f8dcff9be85cb038`;
два коммита LIVE-0C пока являются зависимостью этой ветки, не изменением main.
LIVE-0D и коллектор не изменялись.

Итог: **v2 обучается, воспроизводится и работает через LIVE inference**.
Результаты качества смешанные; автоматическая замена принятого v1 не обоснована.

## Найденные ограничения v1 и доступные данные

V1 уже обучает embeddings карт руки и карты действия, сохраняет порядок руки
и числовые позиции. Однако стол сводится к суммам; теряются идентичности и
сочетания характеристик отдельных сущностей, большинство статусов существ,
категории/mechanics и маски пропусков. Идентичность цели не получает embedding;
источник не связан с полным текущим описанием сущности. Location попадает в
card_other; card_durability не используется. Отсутствующее значение часто
совпадает с нулём. Эти ограничения не доказывают причину ошибок ML-1C.

В исходном датасете есть всё необходимое для выбранного ограниченного v2:
видимая рука, 1 956 появлений существ и 659 Location в состояниях, текущие
характеристики/позиции, source/target identity/kind/side, точные legal варианты.
Например, сохранены taunt, shield, rush, lifesteal, reborn и dormant. Новая
схема сбора не требуется. Полных текстов эффектов, всех исторических счётчиков
и выбора Discover нет; v2 их не восстанавливает и не выдумывает.

## Дизайн и изменённые файлы

Общий EntityEncoder даёт card embeddings, базовые и текущие характеристики,
категории, mechanics, статусы и маски. V2 добавляет роль/сторону сущности,
public hero armor/status и player class. Рука сохраняет позиции; существа и
Location используют общие позиции стола. Переменные зоны не обрезаются.

Каждое действие связывается со своим источником, целью и соседями места вставки.
Добавлены target embedding, source/target kind, durability, маски и простые
числовые отношения attack/health. Это признаки, а не симуляция последствий.
Action query выбирает контекст из всех видимых tokens через attention; небольшой
scorer использует этот контекст, global state и source/target interaction.
103 713 параметров против 124 577 у v1; hidden size 64, embedding size 32.
158 global и 163 entity columns при сохранённом vocabulary/catalog.

- `src/manamind/models/policy_v2.py`: представление и PolicyNetworkV2.
- `src/manamind/models/policy_inputs.py`: общий явный dispatch v1/v2.
- `src/manamind/training/{real_policy,policy_metrics,policy_checkpoint}.py`:
  версия кодирования, сопоставимые метрики, строгий checkpoint.
- `scripts/train_real_policy.py`, `configs/real_policy_ml2a.json`:
  bounded v2 run с обязательным frozen v1 reference.
- `src/manamind/live/recommendation.py`, `scripts/run_manamind.py`,
  `scripts/replay_live_recommendations.py`: checkpoint pin и inference dispatch.
- `tests/test_policy_v2.py`, `tests/test_live_recommendation.py`:
  новые representation tests и действующие LIVE safety tests для обеих моделей.
- `docs/POLICY_REPRESENTATION.md`, `docs/REAL_MATCH_DATA.md`,
  `docs/LIVE_BRIDGE.md`, этот отчёт: контракты и результаты.

## Данные, split и конфигурация

Тот же admitted ML-1B corpus: **21 матч, 736 решений**. Frozen split:
train 17/591, validation 2/85, test 2/60 (матчи/решения). Ни один game_id
не пересекает части. Проверено полное равенство split и decision membership
с checkpoint ML-1C до обучения, а не только совпадение seed.

| Identity | SHA-256 |
|---|---|
| Dataset | `2b20c3b0fd48c34031dfbb8cf516cda9679ce53fee21843e0fc8613609f0b598` |
| Frozen split | `4e96ec57ecdf26ac95d754c23b2ea88d354a27cb9f363ee91cecd8e44d85229b` |
| V2 config | `fa5a5d33b7bf5be1d482d5f48d052824883241547054d79de9e9b9ab43e80080` |
| Catalog | `3dfae0cb5fe312af22c2a16e01eba1286c073f89ea020808fbbf1778067870d9` |
| Vocabulary | `5d54256a24edce79df217ee13852eb6f0f4132213ad3abc09fd75c2fa36301a1` |

Одна заранее выбранная конфигурация, без поиска гиперпараметров: seed/split seed
42, deterministic CPU, один Torch thread, AdamW lr 0.001, weight decay 0.001,
batch 32, gradient clip 1, максимум 60 эпох, patience 8, min_delta 0.0001.
Сохранили расписание v1 для понятного сравнения; smaller hidden size и dropout
0.1 ограничивают ёмкость на маленьком корпусе. Это сравнение двух конфигураций,
не изолированный causal ablation представления. Выбор — только validation CE:
**эпоха 8**, остановка на 16. Test открыт для метрик после сохранения/загрузки
выбранных весов. Test уже использован ML-1C; это regression comparison, не новый
нетронутый holdout. По его результатам модель/config не менялись.

## Результаты

V1 — точный принятый ML-1C checkpoint, а не новая модель для сравнения.

| Часть / модель | CE ↓ | Top-1 | Top-3 | MRR |
|---|---:|---:|---:|---:|
| Train v1 | 1.178686 | 0.631134 | 0.767591 | 0.745578 |
| Train v2 | 1.377507 | 0.609137 | 0.716418 | 0.717591 |
| Validation v1 | 1.882948 | 0.470588 | 0.575342 | 0.592275 |
| Validation v2 | 1.681451 | 0.517647 | 0.643836 | 0.635237 |
| Test v1 | 1.789960 | 0.466667 | 0.571429 | 0.593777 |
| Test v2 | 1.822485 | 0.450000 | 0.714286 | 0.615841 |
| Test uniform expected | 2.154141 | 0.163269 | 0.364080 | 0.351712 |

Top-3 считается только для меню ≥3: 469/73/56 решений. Остальные метрики —
по всем решениям. Test top-1: v1 28/60, v2 27/60; top-3: 32/56 → 40/56.
Для nontrivial menus v2 top-1 25/58. Два test матча: 18/41 и 9/19 correct,
CE 1.932163 и 1.585812. Решения одного матча зависимы; 60 решений не равны
60 независимым матчам. Этот результат не устанавливает playing strength.

## Ошибки и ограничения

- Overfitting сохраняется: v2 train CE 1.691922 → 1.377507 → 1.168448 на
  эпохах 1/8/16, validation 1.990571 → 1.681451 → 1.818699. Сохранены веса 8,
  не финальные веса. Dropout и меньше параметров не устранили эту проблему.
- Targeted test decisions: exact top-1 2/14 → 3/14, top-3 3/14 → 10/14;
  правильный source/action root 6/14 → 8/14. У v2 пять targeted ошибок после
  правильного root, ещё шесть — неверный root. Untargeted top-1 26/46 → 24/46.
  Различия source/target лучше представлены, но надёжный выбор цели не достигнут.
- Placement test: exact 7/14 → 8/14, correct roots 9/14 → 10/14. Эти подмножества
  пересекаются с targeted; их нельзя складывать. Encoding collisions выбранных
  действий отсутствуют у обеих моделей, на всех 736 решениях.
- UNK occurrence ratio исходного аудита 26.44%; vocabulary не расширялся.
  Test chosen UNK non-END_TURN: v2 5/8 correct против v1 4/8; остальные
  22/52 против 24/52. Малые смешанные группы не показывают, что UNK доминирует
  в ошибках. Сохраняется общий UNK embedding без обучения эффектов новых карт.
- Корпус концентрирован: SELF 18 Priest, 3 Warrior; validation/test только Priest.
  Не реконструировались приватные decks. Смена представления одновременно с
  regularization не позволяет приписать улучшение top-3 одному attention/признаку.
  Нужны новые независимые матчи; причинный вклад нехватки данных и признаков
  здесь не измерен. Human action optimality также не измеряется.

## Checkpoint, воспроизводимость и LIVE

Stable ignored local path, доступный из основного worktree:
`E:/ManaMind/data/processed_policy_ml2a/seed42_v2/policy.pt`.
SHA-256: `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`.

Формат `manamind.real_policy/2` владеет architecture/config/dropout, весами,
точным catalog/vocabulary, ordered state/entity/action names, roles/links,
normalization, representation 2, source schemas 16/4/1/1, split/data/seed/config,
source hashes и runtime provenance. Loader отвергает неправильные версии,
порядок/размеры признаков, mapping, split identity, shapes и nonfinite weights.
Автоматической миграции нет. Dataset/state/action schemas не менялись.

Повтор v2 из приватного snapshot: history, metrics, веса и logits всех 736
примеров совпали bitwise; файл checkpoint совпал побайтно с тем же SHA-256.
Runtime: Python 3.12.10, Torch 2.14.0+cu130 (CPU run), NumPy 2.5.3. Другие
версии/платформы проверяют контракт, но bitwise training portability не заявлена.
Source hashes checkpoint совпадают с итоговым training/model кодом.

Исходная configs/real_policy_ml1c.json повторно дала эпоху 6/stop 14, те же
метрики, bitwise веса и logits всех 736 примеров, что accepted v1. Новый файл
v1 имеет другую provenance, поэтому другой file digest; original файл сохранён
с `5a5e3435c0dcda5ce69bcd0a48dc8521fb3696e2a7794e268b894efbf7e3e95e`.

Offline replay завершённой реальной LIVE записи с v2: 47 READY/SELF,
29 superseded, 15 scored, 3 AMBIGUOUS_SELECTION; eligibility совпала с v1 smoke.
State replay 47/47 **IDENTICAL**, repeated top-3 rankings/logits identical.
Scoring median 2.83 ms, p90 4.14 ms, p99 8.05 ms (один локальный запуск).
Эта запись не входит в обученный corpus: matching admitted parity count 0;
TRAIN/LIVE используют одну функцию inputs, её parity проверена fixtures.
Живой ranked запуск v2 не выполнялся. LIVE принимает v2 только при явном
--checkpoint плюс --checkpoint-sha256; по умолчанию остаётся принятый v1.
Сохранены trust/SELF/complete-menu/staleness/catalog и privacy gates.

## Проверки и следующий шаг

Полный pytest: **481 passed, 1 skipped**. Ruff, generic identity guard, typed
failure inventory, 36 pinned generated outputs/ownership и git diff --check:
PASS. Тесты проверяют current/base values, masks, UNK, shared board slots,
target/source/neighbors, действие END_TURN, action-order equivariance, context
sensitivity, finite gradients, checkpoint round-trip/rejections, frozen reference,
детерминированное обучение и test-after-selection. Действующие LIVE canary,
полнота меню, lifecycle/invalidation/replay tests выполняются для v1 и v2.
Новые fixtures проверяют plumbing; качество измерено только на real data.
Private datasets/checkpoints/raw recordings остаются ignored/untracked; в diff
только код, config, tests и документы. Raw slice.log не переписывался.

Рекомендованная следующая задача: **ML-2B — расширение независимого real-policy
evaluation corpus**. Существующим reviewed pipeline собрать более разнообразные
матчи и SELF классы, заморозить новые whole-game validation/test до tuning;
сравнить frozen v1/v2 и отдельно targeted/placement/UNK группы. После увеличения
корпуса провести bounded ablation representation vs regularization. Не начинать
дальнейшее tuning на потреблённых двух test матчах и не продвигать v2 по одному
улучшению top-3. Новая collector/LIVE-0D архитектура для этого не требуется.
