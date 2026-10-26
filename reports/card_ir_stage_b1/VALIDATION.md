# Проверки B1

Проверено 2026-10-26 в существующей рабочей копии, Python из `.venv`.

| Проверка | Результат |
|---|---|
| Card IR A + B1 + новые регрессии | **46 passed** |
| Полный `pytest -q -p no:cacheprovider --basetemp=.pytest-tmp-card-ir-b1-full` | **1287 passed, 1 skipped**, 88,21 с по выводу pytest |
| Ruff: все tracked Python-файлы + новые B1 Python-файлы | **320 файлов, All checks passed** |
| `scripts/check_generated_artifacts.py` | **2 pinned outputs reproduced** |
| `git diff --exit-code -- data/cards` | **0**, артефакты не изменились |
| Воспроизведение протокола, метрик, ревью | **байт в байт**, регрессионные тесты |
| Хеши raw, frozen checker, исходных файлов протокола и 53 деклараций A | **совпадают**, регрессионные тесты |
| Старые protocol/results/mutants/engine_mapping A | **воспроизводятся**, существующие тесты A |
| Новые 12: валидатор / старый lint / новый lint | **0 / 0 / 0** ошибок/предупреждений, raw и final |
| Граница изменений | только `reports/card_ir_stage_b1/`, `src/manamind/card_ir/semantic_lint.py`, два новых тестовых файла |

`ruff check .` отдельно был запущен и завершился с **73 ошибками вне задачи**: 72 в старых untracked временных
фикстурах (`.tmp_algo1b_pytest`, `.tmp_algo_first1_pytest`, `.tmp_live_mvp_full`, `.tmp_ml_pilot_1_pytest`) и
один unused import `Forecast` в существовавшем до задачи untracked `src/manamind/outcome/decision_review.py`.
Были также предупреждения доступа к старым временным каталогам. Пользовательские файлы не исправлялись и не
удалялись. Успех Ruff выше относится к всему отслеживаемому коду плюс новым Python-файлам этой задачи,
а не к рекурсивному обходу пользовательского временного мусора.

Для воспроизведения точного состава Ruff без чтения временных каталогов:

```python
import subprocess
import sys

paths = subprocess.check_output(["git", "ls-files", "--", "*.py"], text=True).splitlines()
subprocess.run([sys.executable, "-m", "ruff", "check", *paths], check=True)
```

После итогового коммита все B1-файлы тоже входят в `git ls-files`.

Пакет Card IR не интегрирован в LIVE, Policy или ML; тест изоляции сохранён и проходит. ManaEngine,
snapshot-файлы, схема/vocabulary v0.1, checkpoint, игровые датасеты и старые отчёты не менялись.
`fresh_holdout`, Power.log и реальные матчи для эксперимента не открывались; не было загрузки новых источников,
обучения, self-play или создания исполнителя. Полный pytest запускал существующие тесты проекта,
а не отдельный исследовательский training/evaluation pilot.

Независимое смысловое ревью **не проведено**. Ноль предупреждений и успешные тесты не подтверждают
правильность правил карты. Gold-проверки ожидают **все 12**, включая `FULL` Aldrachi Warblades.
