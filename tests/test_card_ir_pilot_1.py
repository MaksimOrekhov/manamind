import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "reports/card_ir_pilot_1"


def test_the_locked_protocol_is_reproduced_byte_for_byte(tmp_path):
    out = tmp_path / "protocol.json"
    subprocess.run([sys.executable, "-I", str(PILOT / "select_sample.py"), "--output", str(out)], check=True,
                   cwd=ROOT, capture_output=True)
    assert out.read_bytes() == (PILOT / "protocol.json").read_bytes()
    refuse = subprocess.run([sys.executable, "-I", str(PILOT / "select_sample.py"), "--output", str(out)],
                            cwd=ROOT, capture_output=True)
    assert refuse.returncode != 0


def test_the_protocol_sample_has_the_locked_shape():
    protocol = json.loads((PILOT / "protocol.json").read_text(encoding="utf-8"))
    sample = protocol["sample"]
    assert len(sample) == 21 and len({row["id"] for row in sample}) == 21
    assert sorted(protocol["authoring_order"]["ids"]) == sorted(row["id"] for row in sample)
    assert len(protocol["engine_validation"]["cards"]) == 26
