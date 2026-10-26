import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from manamind.card_ir.audit_render import render_audit
from manamind.card_ir.strict import validate_strict
from manamind.card_metadata import CardMetadata

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "reports/card_ir_validation_2"


def load(name):
    spec = importlib.util.spec_from_file_location(f"validation2_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def meta():
    return CardMetadata.load()


@pytest.fixture(scope="module")
def data(meta):
    return load("cases").build_cases(meta)


@pytest.mark.parametrize("index", range(36))
def test_new_wrong_variants_and_matching_positive_controls(data, index):
    meta, pairs, _ = data
    case = pairs[index]
    good = validate_strict(case["good"], meta, case["good_bindings"])
    bad = validate_strict(case["bad"], meta, case["bad_bindings"])
    assert good.accepted, (case["name"], good.errors, good.warnings)
    assert not bad.accepted, case["name"]


def test_display_and_random_shuffle_lookalikes_are_allowed(data):
    meta, _, controls = data
    for doc in controls[:2]:
        assert validate_strict(doc, meta).accepted
    # Do not disguise a real, conservative false alert as an error in the card.
    explanation = validate_strict(controls[2], meta)
    assert any("REMINDER" in e for e in explanation.errors)


def test_all_nine_review_diagnostics_are_rejected(meta):
    diagnostics = json.loads((ROOT / "reports/card_ir_b1_independent_review/diagnostics.json").read_text(encoding="utf-8"))
    wrong = diagnostics["wrong_but_accepted"]
    assert len(wrong) == 9
    for name, row in wrong.items():
        assert not validate_strict(row["declaration"], meta).accepted, name


def test_gap_links_are_not_automatically_regenerated_after_deletion(meta):
    doc = json.loads((ROOT / "reports/card_ir_stage_b1/final/CATA_585.json").read_text(encoding="utf-8"))
    links = json.loads((HERE / "historical_gap_bindings.json").read_text(encoding="utf-8"))[doc["card_id"]]
    assert not validate_strict(doc, meta).accepted  # explicit migration receipt required
    assert validate_strict(doc, meta, links).accepted
    # Brevity is not lack of knowledge: a precise two-word reason is valid.
    concise, receipt = copy.deepcopy(doc), copy.deepcopy(links)
    concise["unexpressed"][0]["why"] = receipt["gaps"][0]["why"] = "Return unsupported"
    assert validate_strict(concise, meta, receipt).accepted
    concise["unexpressed"][0]["why"] = receipt["gaps"][0]["why"] = "unknown"
    assert any("GAP_REASON" in e for e in validate_strict(concise, meta, receipt).errors)
    doc["dependencies"].pop(0)
    found = validate_strict(doc, meta, links)
    assert any("GAP_DEPENDENCY" in e for e in found.errors)
    assert found.status == "PARTIAL"  # a second CORE dependency must not hide deletion


@pytest.mark.parametrize("mutation", ["wrong_card", "stale_span", "stale_why", "empty_refs", "duplicate", "missing", "wrong_path"])
def test_gap_receipts_are_bound_to_exact_text_and_each_gap(meta, mutation):
    doc = json.loads((ROOT / "reports/card_ir_stage_b1/final/TIME_216.json").read_text(encoding="utf-8"))
    receipt = json.loads((HERE / "historical_gap_bindings.json").read_text(encoding="utf-8"))[doc["card_id"]]
    if mutation == "wrong_card":
        receipt["card_id"] = "ANOTHER_CARD"
    elif mutation == "stale_span":
        receipt["gaps"][0]["span"] = "different words"
    elif mutation == "stale_why":
        receipt["gaps"][0]["why"] = "a different explanation"
    elif mutation == "empty_refs":
        receipt["gaps"][0]["dependencies"] = []
    elif mutation == "duplicate":
        receipt["gaps"].append(copy.deepcopy(receipt["gaps"][0]))
    elif mutation == "missing":
        receipt["gaps"] = []
    else:
        receipt["gaps"][0]["gap"] = "/abilities/0"
    assert not validate_strict(doc, meta, receipt).accepted


def test_core_card_level_flag_is_not_a_link(meta):
    doc = json.loads((ROOT / "reports/card_ir_stage_b1/final/CORE_BT_921.json").read_text(encoding="utf-8"))
    doc["dependencies"] = [{"id": "unanchored", "kind": "UNKNOWN_RULE", "scope": "CORE", "card_level": True,
                            "detail": "A missing behavior with no exact link", "source_needed": "Some independent evidence"}]
    doc["status"] = "PARTIAL"
    report = validate_strict(doc, meta)
    assert any("CORE_ORPHAN" in e for e in report.errors)


def test_unreviewed_return_cannot_claim_full_and_honest_partial_is_allowed(meta):
    raw, final = (json.loads((ROOT / "reports/card_ir_stage_b1" / folder / "CORE_DAL_720.json").read_text(encoding="utf-8"))
                  for folder in ("raw", "final"))
    report = validate_strict(raw, meta)
    assert any("RETURN_CONTRACT" in w for w in report.warnings)
    assert not report.complete
    assert validate_strict(final, meta).accepted


def test_next_card_is_not_next_turn_and_aura_while_is_not_inverted(meta):
    doc = json.loads((ROOT / "reports/card_ir_pilot_1/declarations/CORE_BT_416.json").read_text(encoding="utf-8"))
    assert validate_strict(doc, meta).accepted
    doc["abilities"][0]["effect"]["duration"] = "THIS_TURN"
    assert any("WINDOW_EVIDENCE" in w for w in validate_strict(doc, meta).warnings)
    doc = json.loads((ROOT / "reports/card_ir_pilot_1/declarations/END_022.json").read_text(encoding="utf-8"))
    doc["abilities"][0]["while"]["is"]["where"][0]["damaged"] = False
    assert any("CONDITION_ENTITY" in w for w in validate_strict(doc, meta).warnings)


def test_mech_word_uses_the_pinned_mechanical_race_name(data):
    fixture, pairs, _ = data
    doc = copy.deepcopy(next(c["good"] for c in pairs if c["name"] == "non-Demon"))
    doc["text"] = "Destroy all non-Mech minions."
    doc["text_sha256"] = hashlib.sha256(doc["text"].encode()).hexdigest()
    doc["abilities"][0]["span"] = doc["text"]
    doc["abilities"][0]["effect"]["to"]["exclude"][0]["where"] = [{"race": "MECHANICAL"}]
    separate = load("cases").FixtureMetadata(fixture.real)
    separate.records[doc["card_id"]] = {"id": doc["card_id"], "text": doc["text"], "type": "SPELL"}
    assert validate_strict(doc, separate).accepted


@pytest.mark.parametrize("value", [None, [], "text", {}, {"abilities": None}])
def test_malformed_input_fails_closed_and_renders_visibly(meta, value):
    report = validate_strict(value, meta)
    assert not report.accepted
    assert render_audit(value, meta, strict_report=report)


def test_boolean_is_not_a_count_and_damaged_is_not_a_string(data):
    meta, cases, _ = data
    doc = copy.deepcopy(cases[0]["good"])
    doc["abilities"][0]["effect"]["seq"][1]["then"]["count"] = True
    assert not validate_strict(doc, meta).accepted
    doc = copy.deepcopy(cases[4]["good"])
    doc["abilities"][0]["effect"]["seq"][1]["if"]["is"]["where"][0]["damaged"] = "false"
    assert not validate_strict(doc, meta).accepted


def test_audit_exposes_trigger_condition_roles_constraints_and_reminders(meta):
    diagnostics = json.loads((ROOT / "reports/card_ir_b1_independent_review/diagnostics.json").read_text(encoding="utf-8"))
    hound = diagnostics["counterfactual"]["FIR_953"]["declaration"]
    lines = "\n".join(render_audit(hound, meta))
    for expected in ("ONLY IF", "Health".lower(), "subject (role UNDEFINED", "defender=", "timing=AFTER", "zones=PLAY"):
        assert expected.lower() in lines.lower()
    for name, row in diagnostics["wrong_but_accepted"].items():
        if "reminder" in name:
            text = "\n".join(render_audit(row["declaration"], meta))
            for reminder in row["declaration"]["reminders"]:
                assert reminder["span"] in text
    vama = diagnostics["counterfactual"]["JAIL_118"]["declaration"]
    assert "except" in "\n".join(render_audit(vama, meta))


def test_nested_trigger_conditions_and_window_filters_are_visible(meta):
    doc = json.loads((ROOT / "reports/card_ir_pilot_1/declarations/BE_553t.json").read_text(encoding="utf-8"))
    child = doc["abilities"][0]["effect"]["abilities"][0]
    child["condition"] = {"cmp": [{"stat": "HEALTH", "of": "SELF"}, ">", 0]}
    assert "ONLY IF" in "\n".join(render_audit(doc, meta))
    doc = json.loads((ROOT / "reports/card_ir_pilot_1/declarations/CORE_EX1_145.json").read_text(encoding="utf-8"))
    text = "\n".join(render_audit(doc, meta))
    for expected in ("SELF", "THIS_TURN", "uses=1", "SPELL"):
        # THIS_TURN renders in plain English while exact use/role fields stay explicit.
        assert ("this turn" if expected == "THIS_TURN" else expected) in text


def test_strict_cli_and_write_once_audit(tmp_path):
    output = tmp_path / "audit.txt"
    cmd = [sys.executable, str(ROOT / "scripts/validate_card_ir.py"),
           str(ROOT / "reports/card_ir_stage_b1/final/TIME_216.json"),
           "--bindings", str(HERE / "historical_gap_bindings.json"), "--audit-output", str(output)]
    first = subprocess.run(cmd, cwd=ROOT, capture_output=True)
    assert first.returncode == 0, first.stderr.decode(errors="replace")
    original = output.read_bytes()
    assert "UNEXPRESSED" in original.decode("utf-8")
    assert json.loads(first.stdout)["complete"] is False
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode != 0
    assert output.read_bytes() == original


def test_measurements_and_historical_hashes_reproduce():
    module = load("measure")
    result = module.build()
    assert module.payload(result) == (HERE / "results.json").read_bytes()
    assert result["nine_summary"] == {"total": 9, "before": 1, "after": 9}
    assert result["new_summary"]["false_alerts"] == 0
    assert result["positive_summary"] == {"total": 39, "false_alerts": 1, "known_conservative_reminder_rejections": 1}
    for rows in result["historical_regressions"].values():
        assert all(not r["after_detected"] for r in rows)


def test_all_pinned_historical_inputs_remain_byte_identical():
    pinned = json.loads((HERE / "input_hashes.json").read_text(encoding="utf-8"))
    for path, sha in pinned["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path


def test_opus_diagnostics_reproduce_byte_for_byte(tmp_path):
    output = tmp_path / "diagnostics.json"
    original = ROOT / "reports/card_ir_b1_independent_review/diagnostics.json"
    result = subprocess.run([sys.executable, "-I", str(original.with_suffix(".py")), "--output", str(output)],
                            cwd=ROOT, capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert output.read_bytes() == original.read_bytes()


def test_strict_cli_returns_failure_for_semantic_diagnostic(tmp_path):
    diagnostic = json.loads((ROOT / "reports/card_ir_b1_independent_review/diagnostics.json").read_text(encoding="utf-8"))
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(diagnostic["wrong_but_accepted"]["TIME_216/unconditional_draw"]["declaration"]), encoding="utf-8")
    run = subprocess.run([sys.executable, str(ROOT / "scripts/validate_card_ir.py"), str(candidate)], cwd=ROOT, capture_output=True)
    assert run.returncode == 1
    assert json.loads(run.stdout)["accepted"] is False
