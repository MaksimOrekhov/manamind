"""CARD-IR-EXECUTION-PILOT-1, source-only checks (no native ManaEngine needed).

Native execution of every scenario is checked in experiments/manaengine/tests/test_card_ir_execution_pilot.py.
"""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from manamind.card_ir.engine_translate import TranslationRefused, translate
from manamind.card_ir.strict_v02 import validate_strict_v02
from manamind.card_metadata import CardMetadata

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "reports/card_ir_execution_pilot_1"


def _load(name):
    sys.path.insert(0, str(HERE))
    try:
        spec = importlib.util.spec_from_file_location(f"execution_pilot_{name}", HERE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(HERE))


SC = _load("scenarios")
RESULTS = json.loads((HERE / "RESULTS.json").read_text(encoding="utf-8"))
LEGACY = json.loads((ROOT / "experiments/manaengine/data/card_abilities.json").read_text(encoding="utf-8"))["cards"]


def declared():
    return {card: json.loads((HERE / "declarations" / f"{card}.json").read_text(encoding="utf-8")) for card in SC.CARDS}


@pytest.fixture(scope="module")
def meta():
    return CardMetadata.load()


def test_declarations_are_the_historical_ones_with_only_the_version_changed():
    manifest = json.loads((HERE / "declarations_manifest.json").read_text(encoding="utf-8"))["cards"]
    assert set(manifest) == set(SC.CARDS)
    for card, doc in declared().items():
        source = ROOT / manifest[card]["source"]
        raw = source.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == manifest[card]["source_sha256"]
        original = json.loads(raw)
        assert original["ir"] == "card-ir/0.1" and doc["ir"] == "card-ir/0.2"
        assert {k: v for k, v in doc.items() if k != "ir"} == {k: v for k, v in original.items() if k != "ir"}


def test_every_pilot_declaration_is_strictly_accepted_as_full(meta):
    for card, doc in declared().items():
        report = validate_strict_v02(doc, meta)
        assert report.accepted and report.status == "FULL", (card, report.errors, report.warnings)


def test_composition_cards_translate_to_exactly_the_legacy_engine_steps():
    docs = declared()
    for card in (SC.FLASH, SC.OVERHEAT):
        assert LEGACY[card]["ability"] == "EFFECT_COMPOSITION"
        assert translate(docs[card]).declaration()["effects"] == LEGACY[card]["effects"]


def test_named_handler_cards_become_generic_steps():
    docs = declared()
    bolt, drain = translate(docs[SC.BOLT]), translate(docs[SC.DRAIN])
    assert bolt.declaration() == {"ability": "EFFECT_COMPOSITION", "overload": 1,
                                  "effects": [{"kind": "DAMAGE", "target": "EXPLICIT_CHARACTER", "amount": 3}]}
    assert drain.declaration() == {"ability": "EFFECT_COMPOSITION", "overload": 0, "effects": [
        {"kind": "DAMAGE", "target": "EXPLICIT_MINION", "amount": 3, "lifesteal": True}]}
    assert (LEGACY[SC.BOLT]["ability"], LEGACY[SC.DRAIN]["ability"]) == ("TARGET_DAMAGE", "LIFESTEAL_DAMAGE")


def test_translation_never_reads_the_card_id():
    for doc in declared().values():
        renamed = copy.deepcopy(doc)
        renamed["card_id"] = "SOME_OTHER_CARD"
        assert translate(renamed).steps == translate(doc).steps


def _mutated(mutation_id):
    mutation = SC.MUTATIONS[mutation_id]
    doc = copy.deepcopy(declared()[mutation.card])
    mutation.change(doc)
    return mutation, doc


@pytest.mark.parametrize("scenario", [s for s in SC.MUTATION_SCENARIOS], ids=lambda s: s.id)
def test_each_mutation_is_refused_with_its_code_or_changes_the_steps(scenario):
    mutation, doc = _mutated(scenario.ir)
    if scenario.expected_outcome == "REFUSED:ENGINE_CATALOG_REJECTED":
        # Translates, but drops a printed mechanic; ManaEngine's native catalog guard refuses it (native test).
        assert translate(doc).declaration() != translate(declared()[mutation.card]).declaration()
    elif scenario.expected_outcome.startswith("REFUSED:"):
        with pytest.raises(TranslationRefused) as caught:
            translate(doc)
        assert caught.value.code == scenario.expected_outcome.split(":", 1)[1]
    else:
        original = translate(declared()[mutation.card])
        changed = translate(doc)
        assert changed.declaration() != original.declaration() or scenario.expected_targets is not None


def test_target_side_mutations_change_the_explicit_selector():
    _, side = _mutated("M-side")
    _, friendly = _mutated("M-friendly")
    _, character = _mutated("M-any-character")
    assert translate(side).steps[0].target == "EXPLICIT_ENEMY_CHARACTER"
    assert translate(friendly).steps[0].target == "EXPLICIT_FRIENDLY_CHARACTER"
    assert translate(character).steps[0].target == "EXPLICIT_CHARACTER"


def test_former_validator_gap_is_closed_by_numeric_roles_without_changing_history(meta):
    """Outcome parity adds role checks; immutable execution-pilot results retain the original verdicts."""
    _, doc = _mutated("M-stats")
    report = validate_strict_v02(doc, meta)
    assert not report.accepted and any("NUMERIC_STAT_ROLE" in w for w in report.warnings)
    # The implicit 'a random' count is independent of the four +1/+1 stat literals.
    doc = copy.deepcopy(declared()[SC.OVERHEAT])
    doc["abilities"][0]["effect"]["seq"][1]["pay"]["discard"]["n"] = 2
    report = validate_strict_v02(doc, meta)
    assert not report.accepted and any("NUMERIC_DISCARD_ROLE" in w for w in report.warnings)
    with pytest.raises(TranslationRefused) as caught:
        translate(doc)
    assert caught.value.code == "UNSUPPORTED_PAYMENT"


def test_results_are_complete_and_all_criteria_hold():
    summary = RESULTS["summary"]
    assert all(c["passed"] for c in summary["criteria"].values())
    assert summary["scenarios"]["passed"] == summary["scenarios"]["total"] == len(SC.SCENARIOS)
    assert summary["mutations"]["passed"] == summary["mutations"]["total"] == len(SC.MUTATION_SCENARIOS)
    assert summary["b0_legacy_compatibility"]["different"] == []
    assert summary["criteria"]["C5_ir_controls_execution"]["identical_to_legacy_B1"] == []
    assert all(row["passed"] for row in RESULTS["rows"])
    assert [row["id"] for row in RESULTS["rows"]] == [s.id for s in (*SC.SCENARIOS, *SC.MUTATION_SCENARIOS)]
    assert all(level["L5_training_admission"] is False for level in summary["evidence_levels"].values())


def test_results_translations_reproduce_from_source():
    for card, doc in declared().items():
        spec = translate(doc)
        assert RESULTS["translations"][card] == {"steps": spec.declaration(), "keywords": list(spec.keywords),
                                                 "assumptions": list(spec.assumptions)}


def test_real_evidence_skipped_the_protected_holdout_and_keeps_no_game_keys():
    real = RESULTS["real_evidence"]
    assert real["holdout_games_skipped_unopened"] > 0
    text = json.dumps(real)
    assert "game_key" not in text and "BattleTag" not in text


def test_translator_and_bridge_have_no_card_specific_code():
    pilot = _load("pilot")
    check = pilot.static_card_check()
    assert check["passed"], check["findings"]
