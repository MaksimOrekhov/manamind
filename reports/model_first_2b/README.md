# MODEL-FIRST-2B — Shortcut Challenge

## Итог

Исходная Policy v2 показала **0/300** на Synthetic Test MODEL-FIRST-2: во всех трёх тестовых семействах она ставила `END_TURN` на первое место. Прежняя fine-tuned Policy v2 показала **97,67%** на этом тесте, но challenge выявил слабое место: на контролируемой паре характеристик она выбирала безопасный размен в low arm и проигрывала все high arm, где безопасный атакующий менялся со слота 1 на слот 2.

После одной разрешённой корректирующей тренировки до шести эпох checkpoint набрал 95,33% на новом validation и при повторном запуске набрал 240/240 на challenge. На парных проверках он сохранил 100% в обоих вариантах характеристик, размера стола и перестановки существ. **Challenge и counterfactual test были просмотрены до корректирующей тренировки; повторные 100% не являются независимым post-training результатом.** Обучающие данные были отдельными; test не подавался в trainer и не влиял на выбор эпохи.

Это подтверждает, что checkpoint способен использовать боевые характеристики в заданных диагностических шаблонах после коррекции. Для следующего этапа разумно перейти к MODEL-FIRST-3 как отдельному сравнительному эксперименту, сохранив оба старых checkpoint и считая новый checkpoint экспериментальным. Результаты не дают независимой оценки обобщения после обучения и не являются основанием для live-развёртывания.

## Наборы и правила меток

Новый диагностический challenge содержит 240 сценариев и не входит в train или validation. Gold action вычисляется прямой арифметикой боя: атака должна убить цель (`source_attack >= target_health`), а ответный урон цели не должен убить атакующего (`target_attack < source_health`). Отдельный audit повторно вычисляет это правило по legal actions; если множество gold не совпадает с метками или содержит не ровно одно действие, запуск останавливается. Метки не читают предсказания Policy, эвристики или позиционного baseline. Все 240 сценариев однозначны; 240 действий убивают цель ценой смерти своего атакующего, и в challenge есть 477 целей, неубиваемых одним ударом в доступном меню.

Gold атакующий распределён по позициям 1–4: 60, 110, 50 и 20 сценариев; gold цель по позициям 1–4: 112, 80, 32 и 16. Следовательно, первый атакующий выбран правильным только в четверти сценариев, а первая цель — в 46,7%. Позиционный baseline всегда атакует существом №1 в цель №1, если такая атака есть; иначе он пытается атаковать героя, а при отсутствии такой legal action получает неверный выбор.

Синтетические новые ID используют `card.attack=None`, `card.health=None`, пустые mechanics и явные `BoardEntity.current_attack/current_health`. Реальная карта `BE_036` в новых синтетических наборах не используется. ID counterfactual сравнивает реальный `Core_CS2_200` (Boulderfist Ogre, настоящая база 6/7, без mechanics) с неизвестными ID при одинаковых характеристиках базы и экземпляра. Размеры стола, характеристики и позиции изменяются раздельно.

Независимая разметка здесь воспроизводится двумя способами: сценарий строится из целочисленных параметров боя, затем audit заново вычисляет допустимый gold из сериализованных legal actions и проверяет точное совпадение. Предсказатели не участвуют ни в одном шаге разметки. Это проверка заданного локального правила, не доказательство полной стратегической оптимальности.

## Сравнение на одинаковых применимых сценариях

Во всех строках heuristic применима ко всем сценариям (`NOT_APPLICABLE = 0`); позиционный baseline также получает legal action во всех указанных наборах. Top-1 считает предсказание правильным, если оно совпало хотя бы с одним gold action.

| Набор / arm | Сценариев | Исходная Policy v2 | Fine-tuned до коррекции | После коррекции | Эвристика | Positional baseline |
|---|---:|---:|---:|---:|---:|---:|
| MODEL-FIRST-2 Synthetic Test | 300 | 0% | 97,67% | 98,33% | 100% | 100% |
| MODEL-FIRST-2B challenge, до обучения | 240 | 0% | 98,33% | — | 100% | 11,25% |
| Тот же challenge, после коррекции† | 240 | 0% | 98,33% | 100% | 100% | 11,25% |
| ID: известный `Core_CS2_200` | 300 | 16,83% | 65,67% | 65,83% | 100% | 100% |
| ID: неизвестный ID, те же свойства | 300 | 16,83% | 65,67% | 65,83% | 100% | 100% |
| Характеристики: low, безопасен слот 1 | 48 | 0% | 100% | 100% | 100% | 100% |
| Характеристики: high, безопасен слот 2 | 48 | 0% | **0%** | 100% | 100% | **0%** |
| Стол: small | 48 | 0% | 95,83% | 100% | 100% | 16,67% |
| Стол: large | 48 | 0% | 95,83% | 100% | 100% | 16,67% |
| Перестановка: original | 48 | 0% | 100% | 100% | 100% | 10,42% |
| Перестановка: permuted | 48 | 0% | 97,92% | 100% | 100% | 10,42% |

† Этот post-correction результат повторно использует просмотренные позиции; он показывает поведение нового checkpoint на известных диагностических примерах, но не независимую проверку.

При перестановке board positions корректирующий checkpoint выбрал то же сочетание сущностей (attacker/target) в 48/48 парах; positional baseline — 0/48. В контролируемой ID-абляции обе ветви дали одинаковый top-1 для каждого предсказателя. Это показывает отсутствие эффекта самого ID в данном paired setup, а не отсутствие любого ID-эффекта в других состояниях.

### Что означает старый 0%

В исходном Synthetic Test причина наблюдаемого нулевого top-1 конкретна: исходная Policy v2 поставила `END_TURN` первым во всех 300 случаях (100/100 в каждом из трёх семейств). Позиционный baseline набрал 300/300, потому что на этих исходных данных первая пара атакующих/целей всегда была gold. В контролируемой ID-паре известный и неизвестный ID дали одинаковые метрики; значит, неизвестный ID сам по себе не объясняет старый ноль. Исходный тест одновременно менял семейства, размеры стола, значения полей карты и ID, поэтому результаты не позволяют приписать 0% одной из этих причин.

## Корректирующая тренировка

Поскольку до обучения был провален high-stat arm, выполнен ровно один корректирующий run на исправленных синтетических данных: 1 200 train, 300 новых validation, 12/3 отдельных templates, seed 42, AdamW, batch 32, learning rate `0.0001`, максимум шесть эпох, GPU. Validation выбирала эпоху по set-marginal cross-entropy; challenge не загружался trainer-ом и не участвовал в выборе.

- Baseline checkpoint оставлен без изменений: SHA-256 `044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d`.
- Предыдущий fine-tuned checkpoint оставлен без изменений: SHA-256 `32b4314288c64473c54aafb3b731db910bd5c03b06c9615d9545b11511a19bd0`.
- Новый экспериментальный checkpoint: SHA-256 `1307e9cd9f84ec5efbf5da0fac775d988b8bab6a4f43f7072860429315aca362`.
- Run занял 52,22 секунды; validation top-1 вырос с 0% до 95,33%, выбран epoch 6.
- На старых MODEL-FIRST-2 train/validation top-1 нового checkpoint равен 50%/66,67%, ниже прежнего checkpoint. На старом Synthetic Test — 98,33%. Не заменять старый checkpoint и не считать этот run общим улучшением без отдельного разбора этого сдвига.

Checkpoint и train JSONL остаются в локальных игнорируемых каталогах, старые checkpoint и frozen control не перезаписаны.

## Воспроизведение

Команды выполняются из корня worktree `codex/model-first-2` с установленной средой проекта и доступным исходным checkpoint `data/processed_policy_ml2a/seed42_v2/policy.pt`. В текущем managed worktree этот локальный ignored checkpoint лежит в соседнем основном checkout по `..\data\...`; в обычном checkout уберите `..\` из пути.

```powershell
# Исходные checkpoints до корректировки. Используйте новые output/results пути.
python scripts/model_first_2b_shortcut_challenge.py `
  --baseline ..\data\processed_policy_ml2a\seed42_v2\policy.pt `
  --trained data\processed_policy_ml2b\model_first_2_seed42\policy.pt `
  --output data\processed_synthetic\model_first_2b_reproduction_pre `
  --results reports\model_first_2b\reproduction_pre.json

# Новые corrective train и validation (генератор фиксирован, 1200/300).
python scripts/model_first_2b_shortcut_challenge.py `
  --generate-corrective-output data\processed_synthetic\model_first_2b_corrective_reproduction
python scripts/check_model_first_1_training_boundary.py data\processed_synthetic\model_first_2b_corrective_reproduction\train.jsonl
python scripts/check_model_first_1_training_boundary.py data\processed_synthetic\model_first_2b_corrective_reproduction\validation.jsonl
python scripts/train_model_first_2.py `
  --train data\processed_synthetic\model_first_2b_corrective_reproduction\train.jsonl `
  --validation data\processed_synthetic\model_first_2b_corrective_reproduction\validation.jsonl `
  --baseline ..\data\processed_policy_ml2a\seed42_v2\policy.pt `
  --output data\processed_policy_ml2b\model_first_2b_corrective_reproduction `
  --device cuda --epochs 6 --seed 42

# Однократная диагностическая переоценка после обучения. Это не независимый test.
python scripts/model_first_2b_shortcut_challenge.py `
  --baseline ..\data\processed_policy_ml2a\seed42_v2\policy.pt `
  --trained data\processed_policy_ml2b\model_first_2b_corrective_reproduction\policy.pt `
  --training-summary data\processed_policy_ml2b\model_first_2b_corrective_reproduction\training.json `
  --output data\processed_synthetic\model_first_2b_reproduction_post `
  --results reports\model_first_2b\reproduction_post.json
```

Локальные результаты этого запуска находятся в [results.json](results.json); там записаны SHA-256 challenge/counterfactual JSONL, checkpoint hashes и pre-correction metrics.

## Тесты и CI

- `python -m pytest tests/test_model_first_2b_shortcut_challenge.py -q` — 6 passed.
- `python -m ruff check scripts/model_first_2b_shortcut_challenge.py tests/test_model_first_2b_shortcut_challenge.py` — passed.
- Команды workflow `python -m ruff check src tests scripts`, `python reports/manaengine_unknown_state_architecture/phase_4k1b_failure_site_audit.py check` и `python scripts/check_generated_artifacts.py` — все прошли локально на Windows.
- Полный `python -m pytest -q --basetemp .pytest-model-first-2b-ci` — 606 passed, 1 skipped. Первый запуск без `--basetemp` столкнулся с sandbox permission error в системном temp-каталоге; повтор с temp-каталогом внутри worktree прошёл.
- GitHub source-checks workflow настроен на Ubuntu и Windows, но remote Actions для этих незапушенных изменений не запускались. Это не заявляется как зелёный GitHub CI.

Сценарий — только диагностика board combat scoring. Не менялись архитектура, Policy исходного checkpoint, ManaEngine, прежние checkpoint или frozen control. MODEL-FIRST-3 не запускался; merge не делался.
