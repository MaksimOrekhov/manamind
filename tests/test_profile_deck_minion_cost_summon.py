"""Finite contract tests for the shared profile deck-minion selector."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_profile_deck_minion_cost_summon import record_hash, validate, generate  # noqa: E402
from card_rules.profile_deck_minion_cost_summon import (  # noqa: E402
    render_tasks,
    validate_activation,
    validate_selection,
)


@pytest.fixture
def inputs():
    declaration = json.loads((ROOT / "integrations/rosettastone/card_rules/profile_deck_minion_cost_summon.v1.json").read_text(encoding="utf-8"))
    catalog = {c["id"]: c for c in json.loads((ROOT / "data/cards/standard_current_enUS.json").read_text(encoding="utf-8"))["cards"]}
    resources = {c["id"]: c for c in json.loads((ROOT / "vendor/RosettaStone/Resources/cards.json").read_text(encoding="utf-8"))}
    profile = json.loads((ROOT / "configs/training_profiles/meta_training_20261002_v1.json").read_text(encoding="utf-8"))
    return declaration, catalog, resources, profile


def test_two_consumers_share_deterministic_renderer(inputs):
    declaration, catalog, resources, profile = inputs
    rows = validate(declaration, catalog, resources, profile)
    assert [row["card_id"] for row in rows] == ["JAIL_327", "JAIL_516"]
    assert generate(rows) == generate(list(reversed(rows)))
    assert "SelfCondition::IsCost(2, RelaSign::LEQ)" in generate(rows)[1]
    assert "RandomTask>(EntityType::STACK, 1)" in generate(rows)[1]
    assert "RandomTask>(EntityType::STACK, 2)" in generate(rows)[1]
    assert 'AddEnchantmentTask>("ULD_178a4", EntityType::STACK)' in generate(rows)[1]


def test_selector_contract_is_semantic_and_parameterized(inputs):
    declaration, catalog, resources, profile = inputs
    rows = validate(declaration, catalog, resources, profile)
    control = deepcopy(rows[1])
    control["card_id"] = "INDEPENDENT_CONTROL"
    control["selection"] = {"max_cost": 3, "count": 1}
    control["grant_rush"] = False
    tasks = render_tasks(control, "ULD_178a4")
    assert "SelfCondition::IsCost(3, RelaSign::LEQ)" in tasks[1]
    assert "RandomTask>(EntityType::STACK, 1)" in tasks[2]
    assert not any("AddEnchantmentTask" in task for task in tasks)


@pytest.mark.parametrize("selection", [
    {"max_cost": True, "count": 1},
    {"max_cost": 11, "count": 1},
    {"max_cost": 2, "count": 0},
    {"max_cost": 2, "count": 8},
    {"max_cost": 2, "count": 1, "unreviewed": True},
])
def test_invalid_selection_fails_closed(selection):
    with pytest.raises(ValueError):
        validate_selection(selection)


@pytest.mark.parametrize("activation", [
    {"type": "BATTLECRY", "trigger_limit": 3},
    {"type": "TURN_END"},
    {"type": "TURN_END", "trigger_limit": True},
    {"type": "AFTER_ATTACK"},
])
def test_invalid_activation_fails_closed(activation):
    with pytest.raises(ValueError):
        validate_activation(activation)


def test_dependencies_and_profile_membership_are_fingerprinted(inputs):
    declaration, catalog, resources, profile = inputs
    assert record_hash(catalog["JAIL_327"]) == declaration["cards"][0]["metadata_sha256"]
    assert "JAIL_327" in {slot.get("card_id") for deck in profile["decks"] for slot in deck["slots"]}
    assert "JAIL_516" in {slot.get("card_id") for deck in profile["decks"] for slot in deck["slots"]}
    assert resources["ULD_178a4"]["type"] == "SPELL"
