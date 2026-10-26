import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from manamind.card_ir.audit_render import render_audit
from manamind.card_ir.lint_v02 import SUPERSEDED_V01
from manamind.card_ir.strict import validate_strict
from manamind.card_ir.strict_v02 import validate_strict_any, validate_strict_v02
from manamind.card_ir.validate import validate_declaration
from manamind.card_ir.validate_v02 import validate_declaration_v02
from manamind.card_ir.vocabulary import ELEMENTS, RULES
from manamind.card_ir.vocabulary_v02 import ELEMENTS_V02, PROVISIONAL_RULES, RULES_V02
from manamind.card_metadata import CardMetadata

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "reports/card_ir_v02"
HISTORY = [*sorted((ROOT / "reports/card_ir_pilot_1/declarations").glob("*.json")),
           *sorted((ROOT / "reports/card_ir_stage_b1/final").glob("*.json"))]
CASES = 98


def load(name):
    spec = importlib.util.spec_from_file_location(f"card_ir_v02_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def meta():
    return CardMetadata.load()


@pytest.fixture(scope="module")
def cases(meta):
    return load("conformance").build_cases(meta)


@pytest.fixture(scope="module")
def examples():
    return {p.stem: read(p) for p in sorted((HERE / "examples").glob("*.json")) if p.stem != "gap_bindings"}


@pytest.fixture(scope="module")
def receipts():
    return read(HERE / "examples/gap_bindings.json")


@pytest.mark.parametrize("index", range(CASES))
def test_conformance_case(cases, index):
    fixture_meta, rows = cases
    assert len(rows) == CASES
    case = rows[index]
    report = validate_strict_any(case["doc"], fixture_meta, case["bindings"])
    messages = report.errors + report.warnings
    if case["expect"] == "accept":
        assert report.accepted, (case["name"], messages)
        assert report.status == case["status"], case["name"]
        audit = "\n".join(render_audit(case["doc"], fixture_meta, case["bindings"], report))
        for text in case["render"]:
            assert text in audit, (case["name"], text)
    else:
        assert not report.accepted, case["name"]
        assert any(case["code"] in m for m in messages), (case["name"], case["code"], messages)


def test_every_new_feature_has_good_bad_and_edge_or_interaction_cases(cases):
    _, rows = cases
    features = {}
    for row in rows:
        features.setdefault(row["feature"], set()).add(row["kind"])
    for feature in ("op:FREEZE", "duration:THIS_GAME", "duration:NEXT_TURN", "player_effect:zones",
                    "player_effect:ALL_MATCHING", "event_role:attacker", "event_role:defender", "pred:alive",
                    "counter:DAMAGE_DEALT", "value:mul", "modifier:cost", "deck_position:RANDOM",
                    "move:PLAY_TO_HAND", "reading:split", "player_effect:starts_after"):
        kinds = features[feature]
        assert "bad" in kinds or "edge" in kinds, feature
        assert kinds & {"good", "edge"} and kinds - {"good"}, feature


def test_examples_are_accepted_with_their_status_and_rejected_by_every_v01_tool(meta, examples, receipts):
    expected = {"EDR_895": "FULL_DEP", "CORE_SCH_713": "FULL_DEP", "JAIL_399": "FULL_DEP", "CORE_RLK_063": "FULL_DEP",
                "FIR_953": "PARTIAL", "CATA_452": "FULL_DEP", "CATA_585": "PARTIAL"}
    assert {k: d["status"] for k, d in examples.items()} == expected
    for card_id, doc in examples.items():
        report = validate_strict_v02(doc, meta, receipts.get(card_id))
        assert report.accepted and report.status == expected[card_id], (card_id, report.errors, report.warnings)
        assert validate_declaration(doc, meta).errors, card_id
        assert not validate_strict(doc, meta, receipts.get(card_id)).accepted, card_id
        # Without the version tag the v0.2 constructs are still rejected by v0.1 (no silent acceptance).
        downgraded = dict(doc, ir="card-ir/0.1")
        assert any("not in" in e or "unknown" in e for e in validate_declaration(downgraded, meta).errors), card_id


def test_historical_declarations_keep_v01_verdicts_and_are_never_read_as_v02(meta):
    links = read(ROOT / "reports/card_ir_validation_2/historical_gap_bindings.json")
    assert len(HISTORY) == 65
    for path in HISTORY:
        doc = read(path)
        v01 = validate_strict(doc, meta, links.get(doc["card_id"]))
        routed = validate_strict_any(doc, meta, links.get(doc["card_id"]))
        assert v01.accepted, path.name
        assert (routed.errors, routed.warnings, routed.status) == (v01.errors, v01.warnings, v01.status)
        assert validate_declaration_v02(doc, meta).errors == [
            "doc: ir must be card-ir/0.2 (v0.1 declarations are validated by v0.1 tools)"]


def test_v01_tables_are_untouched_and_v02_changes_are_explicit():
    assert set(ELEMENTS) < set(ELEMENTS_V02)
    assert set(RULES) < set(RULES_V02)
    assert sorted(r for r in RULES if RULES[r] != RULES_V02[r]) == ["R_COST", "R_DECK_POSITION", "R_PLAYER_EFFECT"]
    assert RULES["R_COST"].basis == "UNKNOWN" and "next matching" in RULES["R_PLAYER_EFFECT"].meaning
    assert PROVISIONAL_RULES <= set(RULES_V02) - set(RULES)


def test_every_new_element_and_rule_is_exercised_by_an_accepted_example_or_case(meta, cases, examples, receipts):
    fixture_meta, rows = cases
    used_elements, used_rules = set(), set()
    docs = [(d, receipts.get(k), meta) for k, d in examples.items()]
    docs += [(r["doc"], r["bindings"], fixture_meta) for r in rows if r["expect"] == "accept"]
    for doc, receipt, source in docs:
        assert validate_strict_v02(doc, source, receipt).accepted
        report = validate_declaration_v02(doc, source)
        used_elements |= set(report.elements)
        used_rules |= report.rules
    assert set(ELEMENTS_V02) - set(ELEMENTS) <= used_elements
    assert set(RULES_V02) - set(RULES) <= used_rules


def test_each_provisional_rule_is_refused_without_its_acknowledgement(cases):
    _, rows = cases
    refused = {rule for row in rows if row["expect"] == "reject" for rule in PROVISIONAL_RULES if row["code"] == rule}
    assert refused == PROVISIONAL_RULES


def test_audit_render_shows_every_v02_field(meta, examples, receipts):
    markers = {"zones": "zones=", "starts_after": "inactive until", "position": "[position=", "attacker": "attacker ",
               "defender": "defender ", "alive": "alive (survived)", "mul": " x ", "rule": "acknowledges provisional",
               "next_turn": "next turn (start to end)", "measure": "damage actually dealt"}
    values = {"THIS_GAME": "rest of the game", "ALL_MATCHING": "every matching card", "FREEZE": "freeze ",
              "increase": "increased by"}
    for card_id, doc in examples.items():
        audit = "\n".join(render_audit(doc, meta, receipts.get(card_id), validate_strict_v02(doc, meta,
                                                                                              receipts.get(card_id))))
        text = json.dumps(doc)
        for key, marker in markers.items():
            if f'"{key}":' in text:
                assert marker in audit, (card_id, key)
        for value, marker in values.items():
            if f'"{value}"' in text:
                assert marker in audit, (card_id, value)
        assert "IR version: card-ir/0.2" in audit
        assert "UNRENDERABLE" not in audit


def test_superseded_v01_warnings_are_documented_codes_of_the_strict_lint():
    source = (ROOT / "src/manamind/card_ir/strict_lint.py").read_text(encoding="utf-8")
    for code in SUPERSEDED_V01:
        assert f"{code}:" in source


def test_relabelled_review_diagnostics_stay_rejected(meta):
    wrong = read(ROOT / "reports/card_ir_b1_independent_review/diagnostics.json")["wrong_but_accepted"]
    for name, row in wrong.items():
        assert not validate_strict_v02(dict(row["declaration"], ir="card-ir/0.2"), meta).accepted, name


def test_v02_strict_rejects_malformed_input_instead_of_crashing(meta, examples):
    doc = copy.deepcopy(examples["EDR_895"])
    doc["abilities"][0]["effect"]["zones"] = "HAND"
    assert not validate_strict_v02(doc, meta).accepted
    assert not validate_strict_v02(["not", "an", "object"], meta).accepted
    assert not validate_strict_any(dict(doc, ir="card-ir/9"), meta).accepted


def test_measurements_reproduce_byte_for_byte():
    module = load("measure")
    result = module.build()
    assert module.payload(result) == (HERE / "results.json").read_bytes()
    assert result["conformance"]["passed"] == result["conformance"]["total"] == CASES
    assert result["history"]["v01_accepted"] == result["history"]["dispatch_identical"] == 65
    assert result["diagnostics_relabelled"]["rejected"] == 9


def test_cli_validates_v02_by_version(tmp_path):
    script = ROOT / "scripts/validate_card_ir.py"
    good = subprocess.run([sys.executable, str(script), str(HERE / "examples/JAIL_399.json")], cwd=ROOT,
                          capture_output=True)
    assert good.returncode == 0, good.stdout.decode(errors="replace")
    assert json.loads(good.stdout)["status"] == "FULL_DEP"
    bad = read(HERE / "examples/JAIL_399.json")
    bad["abilities"][0]["effect"]["position"] = "RANDOM"
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(bad), encoding="utf-8")
    run = subprocess.run([sys.executable, str(script), str(candidate)], cwd=ROOT, capture_output=True)
    assert run.returncode == 1
    torch = subprocess.run([sys.executable, str(script), str(HERE / "examples/CATA_585.json"), "--bindings",
                            str(HERE / "examples/gap_bindings.json")], cwd=ROOT, capture_output=True)
    assert torch.returncode == 0 and json.loads(torch.stdout)["complete"] is False
