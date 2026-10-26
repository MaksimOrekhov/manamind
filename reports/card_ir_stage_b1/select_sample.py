"""Freeze B1 without reading games or holdouts; refuse to overwrite any output."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from manamind.card_metadata import CardMetadata  # noqa: E402
from manamind.card_metadata.snapshot import plain_text, strip_text_artifacts  # noqa: E402

SEED = 20261027


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload(value):
    return (json.dumps(value, ensure_ascii=False, indent=2,
                       default=lambda x: dict(x) if isinstance(x, Mapping) else list(x)) + "\n").encode("utf-8")


def build():
    meta = CardMetadata.load()
    scope = json.loads((ROOT / "data/cards/standard_scope_20261001.json").read_text(encoding="utf-8"))
    old = ROOT / "reports/card_ir_pilot_1/declarations"
    # Exclude ALL 53 A declarations, including closure and engine representatives.
    excluded = {p.stem for p in old.glob("*.json")} | set(scope["excluded_card_ids"])
    frame = sorted((r for r in meta.records() if r.get("collectible") is True
                    and r.get("set") in set(scope["standard_sets"]) | {"BE"}
                    and r.get("type") in ("MINION", "SPELL", "WEAPON", "LOCATION", "HERO")
                    and r["id"] not in excluded and plain_text(r.get("text"))), key=lambda r: r["id"])
    # Class-balanced waves; multi-class records have their own explicit stratum.
    # This deliberately differs from A's frequency-curated portion: no game data needed.
    def stratum(record):
        return record.get("cardClass") or "MULTICLASS"

    classes = sorted({stratum(r) for r in frame})
    rng = random.Random(SEED)
    buckets = {c: [r for r in frame if stratum(r) == c] for c in classes}
    sample = []
    while len(sample) < 60:
        order = classes.copy()
        rng.shuffle(order)
        for c in order:
            bucket = buckets[c]
            sample.append(bucket.pop(rng.randrange(len(bucket))))
            if len(sample) == 60:
                break
    rows = []
    for i, r in enumerate(sample, 1):
        text = strip_text_artifacts(r["text"])
        rows.append({"order": i, "id": r["id"], "name": r["name"], "card_class": r.get("cardClass"),
                     "classes": r.get("classes"), "class_stratum": stratum(r),
                     "type": r["type"], "set": r["set"], "text": text,
                     "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                     "record_sha256": hashlib.sha256(payload(r)).hexdigest(),
                     "metadata": {k: r.get(k) for k in ("cost", "attack", "health", "durability", "race", "races",
                                                         "mechanics", "referencedTags", "spellSchool")}})
    paths = ["data/cards/standard_scope_20261001.json", "data/card_metadata/manifest.json",
             "reports/card_ir_pilot_1/protocol.json", "reports/card_ir_pilot_1/IR_SPEC.md",
             "reports/card_ir_pilot_1/README.md", "reports/card_ir_stage_b1/compiler_prompt.md",
             "src/manamind/card_ir/vocabulary.py", "src/manamind/card_ir/validate.py",
             "src/manamind/card_ir/lint.py", "src/manamind/card_ir/render.py"]
    return {
        "id": "CARD-IR-STAGE-B1", "locked_on": "2026-10-26", "status": "LOCKED_BEFORE_GENERATION",
        "hypothesis": "Existing v0.1 can describe unfamiliar cards with explicit gaps; general lexical checks improve mutation detection over A without many clean-A warnings. Semantic compiler accuracy needs independent gold.",
        "baseline": {"A_full_or_full_dep": "20/21", "A_last_third_any_new_element_share": 0.61,
                     "A_last_third_structural_share": 0.23,
                     "A_mutations": {"total": 294, "validator": 189, "lint_only": 68, "missed": 37},
                     "A_first_pass_compilation_accuracy": None},
        "inputs": {"snapshot": meta.snapshot_id, "snapshot_raw_sha256": meta.info.raw_sha256,
                   "files": {p: digest(ROOT / p) for p in paths},
                   "A_declarations": {p.name: digest(p) for p in sorted(old.glob("*.json"))}},
        "selection": {"seed": SEED, "frame": "A random frame: pinned Standard sets plus BE; collectible nonempty effect text; five gameplay card types; scope exclusions and all 53 A declarations removed",
                      "frame_size": len(frame), "frame_ids_sha256": hashlib.sha256(payload([r["id"] for r in frame])).hexdigest(),
                      "method": "Shuffle sorted class strata with random.Random(seed); pop randrange from sorted remaining IDs in each stratum. Repeat until 60. Missing cardClass gets MULTICLASS stratum (original classes retained). Order is draw order. No substitutions.",
                      "classes": classes, "frame_types": dict(sorted(Counter(r["type"] for r in frame).items())),
                      "sample_types": dict(sorted(Counter(r["type"] for r in sample).items())),
                      "bias": "Class-balanced rather than frequency or type-proportional; rare types and mechanics not guaranteed; no selection using checker capabilities."},
        "sample": rows, "batch_size": 12, "stop_after": 12,
        "process": {"author": "Codex in this chat, not independent automatic compilation or gold",
                    "context": "User task, repository rules/README/roadmap, A report/spec/protocol/source/tests, pinned metadata. No games, protected holdout, online rule sources or external compiler API.",
                    "model": "GPT-6 family per session developer identity; exact serving revision/temperature/top_p/seed unavailable; selection seed is NOT a generation seed",
                    "order": "Freeze protocol commit; implement general checks using A mutations before reading batch texts; freeze checks in a second commit; generate raw batch once; validate/lint/render; self-review with separately stored corrections; independent gold deferred",
                    "raw": "Write-once files; no simulated API calls, no invented raw errors, no retry hidden in first-pass metric",
                    "closure": "Metadata lookups only for explicitly named dependencies; no extra declarations or execution",
                    "schema": "Freeze v0.1; unsupported constructs stay PARTIAL with proposed extensions; no vocabulary additions in B1"},
        "metrics": {"automatic_acceptance": "raw structural errors=0 AND old lint=0 AND new lint=0, including PARTIAL separately; not semantic accuracy",
                    "correction": "raw/final JSON diff; number of changed cards, correction rounds and leaf operations; includes author self-review (no external human edits)",
                    "detection": "paired A and B final-declaration mutations via unchanged A operators; validator/old lint/new-only/missed; equivalent mutations possible",
                    "false_positive": "warning counts on unmutated A/B; author disposition only, not an independent false-positive estimate",
                    "effort": "record actual generation batches, per-card reviews, check passes, correction rounds and JSON leaf changes; no fabricated minutes"},
        "full_B_gates_from_A_section_10": {
            "new_structural_last_30": {"success": "<=25%", "stop": ">40% after first 30"},
            "any_new_last_30": {"success": "<=45%", "stop": "not declining relative to A"},
            "gold_false_acceptance": {"success": "<=1/60", "stop": ">=3 in first 30"},
            "automatic_acceptance": {"success": ">=60%", "stop": "<35%"},
            "B1_decision": "Do not apply final GO/NO-GO or false-acceptance gates before independent user gold; recommend continue next 18 / change process / stop, then STOP."},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = payload(build())
    with args.output.open("xb") as stream:
        stream.write(result)
    print("Locked 60 cards; only the first 12 authorized for compilation.")
