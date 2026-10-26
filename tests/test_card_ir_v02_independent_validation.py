import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from manamind.card_ir.audit_render import render_audit
from manamind.card_ir.strict_v02 import validate_strict_any
from manamind.card_ir.validate_v02 import validate_declaration_v02
from manamind.card_metadata import CardMetadata

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "reports/card_ir_v02_independent_validation"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load(name):
    sys.path.insert(0, str(HERE))
    try:
        spec = importlib.util.spec_from_file_location(f"independent_{name}", HERE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(HERE))


@pytest.fixture(scope="module")
def meta():
    return CardMetadata.load()


def test_raw_is_frozen_and_order_is_the_original_first_twelve():
    protocol = read(HERE / "protocol.json")
    b1 = read(ROOT / "reports/card_ir_stage_b1/protocol.json")
    assert protocol["order"] == [c["id"] for c in b1["sample"][:12]]
    assert hashlib.sha256((ROOT / "reports/card_ir_stage_b1/protocol.json").read_bytes()).hexdigest() == protocol["protocol_sha256"]
    for name, digest in read(HERE / "raw_manifest.json").items():
        assert hashlib.sha256((HERE / "raw" / name).read_bytes()).hexdigest() == digest
    assert len(list((HERE / "raw").glob("*.json"))) == len(list((HERE / "final").glob("*.json"))) == 12


def test_final_declarations_pass_and_do_not_gain_coverage_from_checker_changes(meta):
    bindings = read(HERE / "final_bindings.json")
    before = read(HERE / "final_baseline/measurement.json")
    complete = 0
    for card_id in read(HERE / "protocol.json")["order"]:
        doc = read(HERE / "final" / f"{card_id}.json")
        result = validate_strict_any(doc, meta, bindings.get(card_id))
        assert result.accepted, (card_id, result.errors, result.warnings)
        assert result.status == before["cards"][card_id]["strict"]["status"]
        assert result.complete == before["cards"][card_id]["strict"]["complete"]
        complete += result.complete
    assert complete == 6


def test_adversarial_inputs_and_current_measurements_reproduce():
    assert load("build_negative_cases").build() == read(HERE / "negative_cases.json")
    assert load("measure_negatives").build() == read(HERE / "negatives_after.json")


@pytest.mark.parametrize("index", range(38))
def test_frozen_independent_adversarial_verdict(meta, index):
    case = read(HERE / "negative_cases.json")[index]
    expected = read(HERE / "negatives_after.json")["cases"][index]
    result = validate_strict_any(case["declaration"], meta, case["bindings"])
    assert (result.accepted, result.complete, result.status) == (
        expected["strict"]["accepted"], expected["strict"]["complete"], expected["strict"]["status"])
    assert result.errors == expected["strict"]["errors"]
    assert result.warnings == expected["strict"]["warnings"]


def test_recorded_fixes_catch_semantics_and_json_instead_of_accidental_exceptions(meta):
    before = {c["id"]: c for c in read(HERE / "negatives_before.json")["cases"]}
    after = {c["id"]: c for c in read(HERE / "negatives_after.json")["cases"]}
    changed = {key for key in before if before[key]["strict"]["accepted"] != after[key]["strict"]["accepted"]}
    assert changed == {"fury_damage_enemy", "fury_damage_minions_only", "fury_freeze_heroes", "fury_nested_order",
                       "bolt_wrong_damage_entity", "bolt_float_mark", "bolt_empty_dependencies"}
    for key in changed:
        assert before[key]["strict"]["accepted"] and not after[key]["strict"]["accepted"]
        assert not any("malformed declaration" in m for m in after[key]["strict"]["errors"])
    # The structurally valid Torch counterexample still passes: do not call this solved.
    assert after["torch_structured_unconditional"]["strict"]["complete"]
    # Correct unqualified target on either side remains acceptable.
    doc = read(HERE / "final/CORE_RLK_063.json")
    assert validate_strict_any(doc, meta).accepted
    assert "chosen character" in "\n".join(render_audit(doc, meta))


@pytest.mark.parametrize("section", ["abilities", "dependencies", "decisions", "keywords", "reminders", "unexpressed"])
@pytest.mark.parametrize("value", [{}, "", None, False, 0])
def test_document_collections_cannot_pass_by_empty_iteration(meta, section, value):
    doc = read(HERE / "final/CORE_BT_921.json")
    doc[section] = value
    report = validate_strict_any(doc, meta)
    assert not report.accepted
    assert any(f"doc.{section}: must be an array" == e for e in report.errors)


def test_renamed_target_handle_is_resolved_at_the_damage_operation(meta):
    doc = read(HERE / "final/CORE_RLK_063.json")
    doc["abilities"][0]["target"]["bind"] = "another_handle"
    doc["abilities"][0]["effect"]["seq"][0]["to"] = {"ref": "another_handle"}
    assert validate_strict_any(doc, meta).accepted
    doc["abilities"][0]["target"]["choose"]["side"] = "ENEMY"
    report = validate_strict_any(doc, meta)
    assert validate_declaration_v02(doc, meta).ok
    assert any("CLAUSE_TARGET: DEAL_DAMAGE" in w for w in report.warnings)


def test_all_version_tags_still_reject_unknowns_without_guessing(meta):
    doc = read(HERE / "final/CORE_BT_921.json")
    for value in (None, "card-ir/9", [], {}, True):
        candidate = copy.deepcopy(doc)
        candidate["ir"] = value
        assert not validate_strict_any(candidate, meta).accepted
