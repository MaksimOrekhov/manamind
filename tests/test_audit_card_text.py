import json
import subprocess
import sys
from pathlib import Path

SUMMARY = Path("reports/card_text_audit_1/summary.json")


def run_audit(output: Path) -> dict:
    subprocess.run([sys.executable, "-I", "scripts/audit_card_text.py", "--output", str(output)], check=True, capture_output=True)
    return json.loads(output.read_text(encoding="utf-8"))


def test_audit_reproduces_committed_summary_without_local_real_data(tmp_path):
    fresh = run_audit(tmp_path / "summary.json")
    committed = json.loads(SUMMARY.read_text(encoding="utf-8"))
    committed.pop("real_data_card_id_coverage", None)  # needs ignored local data/processed_real
    assert fresh == committed


def test_audit_pins_the_facts_the_report_relies_on(tmp_path):
    summary = run_audit(tmp_path / "summary.json")
    assert summary["source"]["declared_hash_matches_snapshot_file"] is True
    assert summary["identity"]["unique_ids"] == summary["identity"]["cards"] == summary["identity"]["records_identical_to_snapshot"]
    assert [card["id"] for card in summary["coverage"]["without_text_cards"]] == ["Core_CS2_200", "TIME_053", "TLC_248"]
    assert summary["unbalanced_tags"] == []
    assert summary["variants"]["cards"] == 16


def test_audit_refuses_to_overwrite_an_existing_output(tmp_path):
    target = tmp_path / "summary.json"
    target.write_text("{}", encoding="utf-8")
    result = subprocess.run([sys.executable, "-I", "scripts/audit_card_text.py", "--output", str(target)], capture_output=True)
    assert result.returncode != 0
    assert target.read_text(encoding="utf-8") == "{}"
