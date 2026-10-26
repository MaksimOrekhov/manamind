"""Reproduce B1 checks, paired mutations, corrections and review from saved LLM data.

No generation, games, holdouts, inference or engine imports. Outputs are write-once.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from manamind.card_ir import validate_declaration  # noqa: E402
from manamind.card_ir.lint import lint_declaration  # noqa: E402
from manamind.card_ir.render import render  # noqa: E402
from manamind.card_ir.semantic_lint import lint_semantics  # noqa: E402
from manamind.card_ir.validate import normalise_text  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def payload(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def checks(doc, meta):
    report = validate_declaration(doc, meta)
    return {"validator": report.errors, "old_lint": lint_declaration(doc),
            "new_lint": lint_semantics(doc), "render": render(doc, meta)}


def accepted(result):
    return not any(result[k] for k in ("validator", "old_lint", "new_lint"))


def changes(before, after, path=""):
    """One operation for an added/removed/replaced JSON value; recurse shared lists/objects."""
    result = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}/{key}"
            if key not in before:
                result.append({"path": child, "operation": "add", "after": after[key]})
            elif key not in after:
                result.append({"path": child, "operation": "remove", "before": before[key]})
            else:
                result.extend(changes(before[key], after[key], child))
    elif isinstance(before, list) and isinstance(after, list):
        for i in range(max(len(before), len(after))):
            child = f"{path}/{i}"
            if i >= len(before):
                result.append({"path": child, "operation": "add", "after": after[i]})
            elif i >= len(after):
                result.append({"path": child, "operation": "remove", "before": before[i]})
            else:
                result.extend(changes(before[i], after[i], child))
    elif before != after:
        result.append({"path": path, "operation": "replace", "before": before, "after": after})
    return result


def mutations(docs, meta):
    spec = importlib.util.spec_from_file_location("card_ir_A_mutants", ROOT / "reports/card_ir_pilot_1/mutants.py")
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    totals, by_operator, details = Counter(), {}, []
    for operator in old.ORDER:
        counts = Counter()
        for doc in docs:
            result = old.mutate(doc, operator)
            if result is None or result[0] == doc:
                continue
            mutant, site = result
            c = checks(mutant, meta)
            layer = ("validator" if c["validator"] else "old_lint" if c["old_lint"]
                     else "new_only" if c["new_lint"] else "missed")
            counts["total"] += 1
            counts[layer] += 1
            details.append({"card_id": doc["card_id"], "operator": operator, "site": site,
                            "layer": layer, "new_warnings": c["new_lint"]})
        by_operator[operator] = {k: counts[k] for k in ("total", "validator", "old_lint", "new_only", "missed")}
        totals.update(counts)
    total = {k: totals[k] for k in ("total", "validator", "old_lint", "new_only", "missed")}
    total["baseline_detected_share"] = round((totals["validator"] + totals["old_lint"]) / totals["total"], 6)
    total["enhanced_detected_share"] = round(1 - totals["missed"] / totals["total"], 6)
    return {"total": total, "by_operator": by_operator, "details": details,
            "caveat": "Same-author mutations, possibly equivalent; PARTIAL bodies supply few sites. Not independent semantic accuracy or a false-acceptance rate."}


def build():
    meta = CardMetadata.load()
    protocol, notes = read(HERE / "protocol.json"), read(HERE / "review_notes.json")
    rows, final_docs = [], []
    for row in protocol["sample"][:12]:
        card_id = row["id"]
        raw, final = (read(HERE / folder / f"{card_id}.json") for folder in ("raw", "final"))
        initial, latest = checks(raw, meta), checks(final, meta)
        delta = changes(raw, final)
        report = validate_declaration(final, meta)
        # Textual representation coverage: excludes reminders and explicit gaps; not a quality score.
        spans = [x["span"] for key in ("abilities", "keywords") for x in final.get(key, [])]
        words = lambda t: len(re.findall(r"[A-Za-z0-9]+", t))
        all_words = words(normalise_text(final["text"]))
        rows.append({"card_id": card_id, "name": row["name"], "raw_status": raw["status"],
                     "final_status": final["status"], "initial": initial, "final": latest,
                     "author_corrected": bool(delta), "correction_operations": delta,
                     "dependencies": len(final["dependencies"]),
                     "dependency_kinds": dict(sorted(Counter(d["kind"] for d in final["dependencies"]).items())),
                     "unresolved_decisions": sum(d["chosen"] == "UNRESOLVED" for d in final["decisions"]),
                     "decisions": len(final["decisions"]), "used_vocabulary": sorted(report.elements),
                     "represented_text_words": sum(words(s) for s in spans), "total_text_words": all_words,
                     "unexpressed_spans": final.get("unexpressed", []), **notes[card_id]})
        final_docs.append(final)
    old_docs = [read(p) for p in sorted((ROOT / "reports/card_ir_pilot_1/declarations").glob("*.json"))]
    proposals = {kind: sorted({x for r in rows for x in r[f"proposed_{kind}"]})
                 for kind in ("structural", "enum", "parameters")}
    summary = {
        "cards": 12, "first_pass_check_acceptance": sum(accepted(r["initial"]) for r in rows),
        "first_pass_complete_check_acceptance": sum(accepted(r["initial"]) and r["raw_status"] in ("FULL", "FULL_DEP") for r in rows),
        "final_complete_check_acceptance": sum(accepted(r["final"]) and r["final_status"] in ("FULL", "FULL_DEP") for r in rows),
        "author_corrected_cards": sum(r["author_corrected"] for r in rows),
        "correction_operations": sum(len(r["correction_operations"]) for r in rows),
        "final_statuses": dict(sorted(Counter(r["final_status"] for r in rows).items())),
        "dependencies": sum(r["dependencies"] for r in rows),
        "unresolved_decisions": sum(r["unresolved_decisions"] for r in rows),
        "decisions": sum(r["decisions"] for r in rows),
        "added_structural_elements": 0, "added_enum_elements": 0, "added_parameters": 0,
        "proposed_distinct": {k: len(v) for k, v in proposals.items()},
        "cards_proposing_structural": sum(bool(r["proposed_structural"]) for r in rows),
        "cards_proposing_any": sum(any(r[f"proposed_{k}"] for k in proposals) for r in rows),
        "warning_counts": {phase: {layer: sum(len(r[phase][layer]) for r in rows)
                                    for layer in ("validator", "old_lint", "new_lint")}
                           for phase in ("initial", "final")},
        "A_unmutated_new_warnings": sum(len(lint_semantics(d)) for d in old_docs),
        "independent_gold_review_required": 12, "independent_accuracy": None,
        "false_acceptance_rate": None, "final_GO_NO_GO": "DEFERRED_PENDING_INDEPENDENT_GOLD",
        "recommendation": "CHANGE_PROCESS_BEFORE_NEXT_18",
    }
    return {"id": "CARD-IR-STAGE-B1", "summary": summary, "proposals": proposals, "cards": rows,
            "mutations_A": mutations(old_docs, meta), "mutations_B": mutations(final_docs, meta)}


def review(result):
    lines = ["# B1 — пакет независимого ревью 12 карт", "",
             "Первичные JSON и исправления доступны отдельно, но для ревью они не нужны. Все 12 карточек ожидают",
             "независимой gold-проверки. Русские пояснения — саморевью автора; строки рендера автоматически получены из IR.",
             "PARTIAL и FULL_DEP не означают готовность исполнения; даже FULL не доказывает семантическую правильность.", ""]
    for i, row in enumerate(result["cards"], 1):
        doc = read(HERE / "final" / f"{row['card_id']}.json")
        lines.extend([f"## {i}. {row['name']} — `{row['card_id']}`", "", "Оригинальный текст:", "",
                      "> " + doc["text"].replace("\n", " "), "", "Автоматический обратный рендер IR:", ""])
        lines += [f"- {line}" for line in row["final"]["render"]]
        lines.extend(["", row["ru"], "", f"**Риск изменения результата:** {row['risk']}", "",
                      "Решения интерпретации (особенно OUTCOME):", ""])
        for d in doc["decisions"]:
            lines.append(f"- **{d['risk']}** {d['question']} → **{d['chosen']}** ({d['basis']}). Альтернативы: {' / '.join(d['alternatives'])}. Различающий случай: {d.get('discriminating_case', 'не нужен')}")
        lines.extend(["", "Неизвестные зависимости:", ""])
        lines += [f"- `{d['id']}` — {d['kind']}/{d['scope']}: {d['detail']} Источник нужен: {d['source_needed']}" for d in doc["dependencies"]] or ["- Нет явно объявленных зависимостей; общие правила IR всё равно требуют реализации и проверки."]
        correction = ("Одна авторская коррекция: FULL → PARTIAL; добавлена CORE-зависимость возврата и решение переведено в UNRESOLVED. Автопроверки проблему не обнаружили."
                      if row["author_corrected"] else "Изменений после первичной генерации нет. Это не независимое подтверждение отсутствия ошибок.")
        lines.extend(["", f"**Проверки:** структурных ошибок {len(row['final']['validator'])}, старых предупреждений {len(row['final']['old_lint'])}, новых {len(row['final']['new_lint'])}.",
                      "", "**Исправления:** " + correction, "", f"**Итог:** `{row['final_status']}`; независимое ревью **PENDING**.", "",
                      f"Словарь: новых структур {len(row['proposed_structural'])}, перечислений {len(row['proposed_enum'])}, параметров {len(row['proposed_parameters'])} **предложено, не добавлено**. Фактически добавлено 0.",
                      "", "- [ ] Проверить соответствие тексту, область, сторону, порядок и все OUTCOME-решения.",
                      "- [ ] Зафиксировать gold: принять / исправить / неизвестно, включая пропущенные фрагменты.", ""])
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-output", type=Path)
    args = parser.parse_args()
    for path in (args.output, args.review_output):
        if path is not None and path.exists():
            parser.error(f"{path} exists; refusing to overwrite")
    result = build()
    args.output.write_bytes(payload(result))
    if args.review_output:
        args.review_output.write_bytes(review(result).encode("utf-8"))
    print(json.dumps(result["summary"], ensure_ascii=True, indent=2))
    print("Mutations A", result["mutations_A"]["total"])
    print("Mutations B", result["mutations_B"]["total"])
