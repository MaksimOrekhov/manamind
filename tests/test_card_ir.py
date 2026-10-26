import copy
import json
import re
from pathlib import Path

import pytest

from manamind.card_ir import ELEMENTS, RULES, normalise_text, validate_declaration
from manamind.card_ir.lint import lint_declaration
from manamind.card_ir.render import render
from manamind.card_metadata import CardMetadata

ROOT = Path(__file__).resolve().parents[1]
DECLARATIONS = ROOT / "reports/card_ir_pilot_1/declarations"


@pytest.fixture(scope="module")
def meta():
    return CardMetadata.load()


@pytest.fixture(scope="module")
def docs():
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(DECLARATIONS.glob("*.json"))}


def errors(doc, meta):
    return validate_declaration(doc, meta).errors


def test_every_declaration_validates_and_lints_clean(docs, meta):
    assert len(docs) == 53
    for card_id, doc in docs.items():
        assert doc["card_id"] == card_id
        assert errors(doc, meta) == [], card_id
        assert lint_declaration(doc) == [], card_id


def test_every_vocabulary_element_and_rule_is_used_by_some_declaration(docs, meta):
    used, rules = set(), set()
    for doc in docs.values():
        report = validate_declaration(doc, meta)
        used |= set(report.elements)
        rules |= report.rules
    assert used == set(ELEMENTS)
    assert rules == set(RULES)


def test_normalised_text_keeps_spell_damage_and_healing_marks():
    assert normalise_text("[x]Restore #5 Health\nand deal <b>$3</b> damage.") == "Restore #5 Health and deal $3 damage."


def mutated(docs, card_id, change):
    doc = copy.deepcopy(docs[card_id])
    change(doc)
    return doc


@pytest.mark.parametrize("card_id, change, expected", [
    ("CORE_EX1_238", lambda d: d["abilities"][0]["effect"].update(amount=3), "same mark"),
    ("TIME_609", lambda d: d["abilities"][0]["effect"]["seq"][0].update(amount={"n": 2, "mark": "$"}), "carries a mark"),
    ("CORE_AT_055", lambda d: d["abilities"][0]["effect"].update(amount={"n": 4, "mark": "#"}), "#5 has no matching"),
    ("BE_207", lambda d: d["abilities"].clear(), "is not covered"),
    ("TIME_890t2", lambda d: d["dependencies"].pop(), "is not declared"),
    ("CORE_REV_990", lambda d: d["abilities"][0]["effect"]["seq"][1].update(to={"ref": "x"}), "not bound before use"),
    ("BE_561", lambda d: d["abilities"][0]["effect"]["seq"][1]["then"].update(to="SELF"), "bound but never used"),
    ("CATA_999", lambda d: d["abilities"][0]["effect"].update(op="DEAL_DAMAGE_TWICE"), "unknown operation"),
    ("CATA_200", lambda d: d["abilities"][0]["effect"]["seq"][1]["into"].update(resolved="UNIQUE_NAME"), "does not occur"),
    ("CORE_DRG_107", lambda d: d["abilities"][0]["effect"]["what"].update(resolved="UNIQUE_NAME"), "4 gameplay records"),
    ("TLC_602", lambda d: d.update(status="FULL_DEP"), "differs from implied PARTIAL"),
    ("CORE_EX1_002", lambda d: d["dependencies"].clear(), "KEYWORD_RULE"),
    ("CAP_107t", lambda d: d.update(text=d["text"].replace("1 damage", "2 damage")), "differs from the snapshot"),
    ("BE_552", lambda d: d["decisions"][0].update(chosen="yes", basis="UNKNOWN"), "use UNRESOLVED"),
    ("BE_561", lambda d: d["decisions"][0].pop("dep"), "needs a dependency"),
])
def test_the_validator_rejects_plausible_authoring_errors(docs, meta, card_id, change, expected):
    found = errors(mutated(docs, card_id, change), meta)
    assert any(expected in error for error in found), found


def test_lint_catches_a_flipped_side_that_the_validator_accepts(docs, meta):
    def flip(doc):
        doc["abilities"][0]["effect"]["to"]["side"] = "FRIENDLY"

    mutant = mutated(docs, "CAP_107t", flip)
    assert errors(mutant, meta) == []
    assert lint_declaration(mutant)


def test_known_blind_spot_a_side_flip_in_one_of_two_identical_steps_passes_every_check(docs, meta):
    """Sylvanas's first wave hitting her own side passes the validator and the lint: the second wave still carries
    'enemy'. Such errors need a human gold check of the rendered IR or a contradicting log (mutation report)."""
    def flip(doc):
        doc["abilities"][0]["effect"]["seq"][0]["to"]["side"] = "FRIENDLY"

    mutant = mutated(docs, "TIME_609", flip)
    assert errors(mutant, meta) == []
    assert lint_declaration(mutant) == []


def test_render_covers_every_declaration_and_names_the_gaps(docs, meta):
    for doc in docs.values():
        lines = render(doc, meta)
        assert len(lines) >= len(doc["abilities"]) + len(doc.get("keywords", []))
    assert any(line.startswith("NOT EXPRESSED") for line in render(docs["JAIL_732"], meta))
    assert any("<UNKNOWN" in line for line in render(docs["TLC_602"], meta))


def test_nothing_outside_the_package_imports_card_ir_and_it_imports_only_card_metadata():
    pattern = re.compile(r"^\s*(?:from|import)\s+(manamind\.[\w.]+)", re.MULTILINE)
    for path in (ROOT / "src/manamind").rglob("*.py"):
        imports = set(pattern.findall(path.read_text(encoding="utf-8")))
        if "card_ir" in path.parts:
            assert all(name.startswith(("manamind.card_ir", "manamind.card_metadata")) for name in imports), path
        else:
            assert not any(name.startswith("manamind.card_ir") for name in imports), path
