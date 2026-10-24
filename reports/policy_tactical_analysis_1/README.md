# POLICY-TACTICAL-ANALYSIS-1

Статус: **PROTOCOL_LOCKED**. Идентификатор выборки: `159318a76daf28b82b240cee9326613e59a0fe0b6a8f7ee326b0552570317229`.

## Гипотеза и baseline до inference

Recovering the 91 strictly joinable decisions may change the apparent imitation pattern; test whether Policy v3's relative result against Frozen v2 and same-data Retrained v2 survives equal-match weighting and leave-one-match/class-out checks.

Baseline — Frozen v2. Прежние метрики на 204 решениях уже исследованы и не являются независимым holdout.

| Модель | CE | Top-1 | Top-3 | MRR |
|---|---:|---:|---:|---:|
| frozen_v2 | 1.8251 | 0.387 | 0.483 | 0.552 |
| retrained_v2 | 1.9051 | 0.407 | 0.556 | 0.569 |
| policy_v3 | 1.7914 | 0.426 | 0.556 | 0.579 |

Размер зафиксированной выборки: 12 матчей, 295 решений; из них восстановлено 91.

После фиксации EVAL-2 изменились только файлы join-check: scripts/live_join_coverage_1.py, scripts/new_matches_eval_2.py. Данные и checkpoint проверяются по старым pin; новые версии join-кода закреплены в этом протоколе.

Методы и границы описаны в `protocol.json`. Обучение и fine-tuning не выполняются; fresh_holdout закрыт, LIVE Policy не меняется.
