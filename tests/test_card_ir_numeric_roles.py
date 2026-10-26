import copy
import importlib.util
from pathlib import Path

import pytest

from manamind.card_ir.numeric_lint_v02 import lint_numeric_roles
from manamind.card_ir.strict_v02 import validate_strict_v02
from manamind.card_metadata import CardMetadata

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("parity_numeric_measure", ROOT / "reports/card_ir_outcome_parity_1/validation_measure.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


@pytest.fixture(scope="module")
def meta():
    return CardMetadata.load()


@pytest.mark.parametrize("name,kind,doc", measure.probes(), ids=lambda value: value if isinstance(value, str) else None)
def test_overheat_and_pilot_numeric_regressions(meta, name, kind, doc):
    result = validate_strict_v02(doc, meta)
    assert result.accepted == (kind == "control"), (name, result.errors, result.warnings)
    if kind == "wrong":
        assert any("NUMERIC_" in w for w in result.warnings)


def _ability(text, attack, health):
    return {"abilities": [{"span": text, "effect": {"op": "ENCHANT", "to": "SELF", "attack": attack, "health": health}}]}


def test_asymmetric_and_signed_stats_keep_their_own_roles():
    text = "Give a minion +2/+3."
    assert lint_numeric_roles(_ability(text, 2, 3)) == []
    wrong = lint_numeric_roles(_ability(text, 3, 2))
    assert len(wrong) == 2 and all("NUMERIC_STAT_ROLE" in w for w in wrong)
    assert lint_numeric_roles(_ability("Give a minion -2/+3.", -2, 3)) == []


def test_derived_values_and_extra_metadata_numbers_are_not_blanket_rejected():
    assert lint_numeric_roles(_ability("Give a minion +2/+3.", {"add": [1, 1]}, {"sub": [7, 4]})) == []
    doc = _ability("Summon a 6/6 Dragon.", 99, 101)
    doc["abilities"][0]["effect"] = {"op": "SUMMON", "count": 1, "what": {"card": "token", "cost": 8}}
    assert lint_numeric_roles(doc) == []


def test_unmatched_templates_are_not_guessed_and_no_card_id_is_used():
    doc = _ability("Your minion gets better.", 7, 9)
    assert lint_numeric_roles(doc) == []
    doc = _ability("Give a minion +2/+3.", 7, 9)
    before = lint_numeric_roles(doc)
    doc["card_id"] = "ARBITRARY_OTHER_ID"
    assert lint_numeric_roles(doc) == before


def test_random_discard_count_words_defaults_and_expressions():
    doc = {"abilities": [{"span": "Discard two random Nature spells to gain +1/+1.",
                          "effect": {"pay": {"discard": {"pick": "RANDOM", "n": 2}}, "then": {"op": "ENCHANT", "attack": 1, "health": 1}}}]}
    assert lint_numeric_roles(doc) == []
    doc["abilities"][0]["effect"]["pay"]["discard"]["n"] = 1
    assert any("NUMERIC_DISCARD_ROLE" in w for w in lint_numeric_roles(doc))
    expression = copy.deepcopy(doc)
    expression["abilities"][0]["effect"]["pay"]["discard"]["n"] = {"add": [1, 1]}
    assert lint_numeric_roles(expression) == []
