import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from manamind.card_ir import validate_declaration
from manamind.card_ir.lint import lint_declaration
from manamind.card_ir.semantic_lint import lint_semantics
from manamind.card_metadata import CardMetadata

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "reports/card_ir_stage_b1"


def load(name):
    spec = importlib.util.spec_from_file_location(f"b1_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_protocol_reproduces_and_excludes_all_A_declarations():
    selector = load("select_sample")
    assert selector.payload(selector.build()) == (HERE / "protocol.json").read_bytes()
    protocol = read(HERE / "protocol.json")
    ids = [r["id"] for r in protocol["sample"]]
    assert len(ids) == len(set(ids)) == 60
    assert not set(ids) & {p.stem for p in (ROOT / "reports/card_ir_pilot_1/declarations").glob("*.json")}
    # Multi-class original values are preserved, never silently treated as neutral.
    assert any(r["card_class"] is None and r["classes"] for r in protocol["sample"])


def test_locked_input_hashes_and_write_once_raw_provenance():
    protocol, authorship = read(HERE / "protocol.json"), read(HERE / "authorship.json")
    for path, sha in protocol["inputs"]["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path
    for name, sha in protocol["inputs"]["A_declarations"].items():
        assert hashlib.sha256((ROOT / "reports/card_ir_pilot_1/declarations" / name).read_bytes()).hexdigest() == sha
    for card_id, sha in authorship["raw_sha256"].items():
        assert hashlib.sha256((HERE / "raw" / f"{card_id}.json").read_bytes()).hexdigest() == sha
    assert hashlib.sha256((ROOT / "src/manamind/card_ir/semantic_lint.py").read_bytes()).hexdigest() == authorship["frozen_checker_sha256"]


def test_metrics_review_and_initial_checks_reproduce():
    measure = load("measure")
    results = measure.build()
    assert measure.payload(results) == (HERE / "results.json").read_bytes()
    assert measure.review(results).encode("utf-8") == (HERE / "REVIEW.md").read_bytes()
    assert {r["card_id"]: r["initial"] for r in results["cards"]} == read(HERE / "initial_checks.json")
    assert results["mutations_A"]["total"]["total"] == 294
    assert results["mutations_A"]["total"]["validator"] == 189
    assert results["mutations_A"]["total"]["old_lint"] == 68
    assert results["summary"]["independent_accuracy"] is None
    assert results["summary"]["false_acceptance_rate"] is None


def test_only_first_twelve_generated_and_every_final_passes():
    meta = CardMetadata.load()
    expected = {r["id"] for r in read(HERE / "protocol.json")["sample"][:12]}
    for folder in ("raw", "final"):
        assert {p.stem for p in (HERE / folder).glob("*.json")} == expected
        for path in (HERE / folder).glob("*.json"):
            doc = read(path)
            assert validate_declaration(doc, meta).errors == []
            assert lint_declaration(doc) == []
            assert lint_semantics(doc) == []
    raw, final = (read(HERE / folder / "CORE_DAL_720.json") for folder in ("raw", "final"))
    assert raw["status"] == "FULL" and final["status"] == "PARTIAL"
    assert any(d["id"] == "return_transition" and d["scope"] == "CORE" for d in final["dependencies"])


@pytest.mark.parametrize("script", ["select_sample.py", "measure.py"])
def test_tools_refuse_overwrite(tmp_path, script):
    out = tmp_path / "existing.json"
    out.write_bytes(b"preserve")
    result = subprocess.run([sys.executable, "-I", str(HERE / script), "--output", str(out)],
                            capture_output=True, cwd=ROOT)
    assert result.returncode != 0
    assert out.read_bytes() == b"preserve"
