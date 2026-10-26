import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "reports/card_ir_pilot_1"
sys.path.insert(0, str(PILOT))

from ir_format import dumps  # noqa: E402


def run(script, out):
    return subprocess.run([sys.executable, "-I", str(PILOT / script), "--output", str(out)], cwd=ROOT,
                          capture_output=True)


def test_the_locked_protocol_is_reproduced_byte_for_byte(tmp_path):
    out = tmp_path / "protocol.json"
    assert run("select_sample.py", out).returncode == 0
    assert out.read_bytes() == (PILOT / "protocol.json").read_bytes()
    assert run("select_sample.py", out).returncode != 0


def test_the_protocol_sample_has_the_locked_shape():
    protocol = json.loads((PILOT / "protocol.json").read_text(encoding="utf-8"))
    sample = protocol["sample"]
    assert len(sample) == 21 and len({row["id"] for row in sample}) == 21
    assert sorted(protocol["authoring_order"]["ids"]) == sorted(row["id"] for row in sample)
    assert len(protocol["engine_validation"]["cards"]) == 26


@pytest.mark.parametrize("script, committed", [
    ("measure.py", "results.json"), ("mutants.py", "mutants.json"), ("engine_mapping.py", "engine_mapping.json"),
])
def test_committed_measurements_are_reproduced_byte_for_byte(tmp_path, script, committed):
    out = tmp_path / committed
    result = run(script, out)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert out.read_bytes() == (PILOT / committed).read_bytes()


def test_every_locked_card_has_a_declaration_and_every_created_token_is_declared():
    protocol = json.loads((PILOT / "protocol.json").read_text(encoding="utf-8"))
    docs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (PILOT / "declarations").glob("*.json")}
    for row in protocol["sample"]:
        assert docs[row["id"]]["role"] == "sample"
    for row in protocol["engine_validation"]["cards"]:
        assert docs[row["id"]]["role"] == "engine_validation"
    created = set()

    def collect(node):
        if isinstance(node, dict):
            for key in ("what", "into", "reward"):
                if isinstance(node.get(key), dict) and "card" in node[key]:
                    created.add(node[key]["card"])
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    for row in protocol["sample"]:
        collect(docs[row["id"]]["abilities"])
    # The Coin is deliberately not declared: 70 functionally identical records, identity unresolved (dep_coin).
    assert created - {"GAME_005"} <= set(docs)


def test_declarations_are_stored_in_the_canonical_layout():
    for path in (PILOT / "declarations").glob("*.json"):
        assert path.read_bytes() == dumps(json.loads(path.read_text(encoding="utf-8"))).encode("utf-8"), path.name
