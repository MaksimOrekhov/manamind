"""The evidence lane is one-way: model/live code never imports it, and it never reaches engine rules."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "manamind"
FORBIDDEN_CONSUMERS = ("encoding", "models", "training", "inference", "live")
FORBIDDEN_DEPENDENCIES = (
    "manamind.integrations.manaengine", "manamind.models", "manamind.encoding", "manamind.training",
    "manamind.inference",
)


def imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = ("." * node.level) + (node.module or "")
            modules.add(base)
            modules.update(f"{base}.{alias.name}" for alias in node.names)
    return modules


def test_model_and_live_code_never_import_the_evidence_package():
    offenders = []
    for package in FORBIDDEN_CONSUMERS:
        for path in sorted((SRC / package).rglob("*.py")):
            for module in imported_modules(path):
                if module.startswith("manamind.evidence") or module.lstrip(".").startswith("evidence"):
                    offenders.append(f"{path.relative_to(SRC)} -> {module}")
    assert not offenders, offenders


def test_evidence_package_does_not_import_models_engine_or_training():
    offenders = []
    for path in sorted((SRC / "evidence").glob("*.py")):
        for module in imported_modules(path):
            if module.startswith(FORBIDDEN_DEPENDENCIES):
                offenders.append(f"{path.name} -> {module}")
    assert not offenders, offenders


def test_only_the_pipeline_writes_files():
    for path in sorted((SRC / "evidence").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if path.name == "pipeline.py":
            continue
        for marker in ("write_text", "write_bytes", ".unlink(", 'open("w"', ".mkdir("):
            assert marker not in text, f"{path.name}: {marker}"
