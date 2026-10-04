"""Source contract tests: no native build or declaration-derived rules oracle."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_minion_set_enchant import validate, generate  # noqa: E402
from card_rules.minion_set_enchant import render_tasks, validate_effects  # noqa: E402
from scripts.check_generic_card_branches import inventory  # noqa: E402


@pytest.fixture
def inputs():
    declaration = json.loads((ROOT / "integrations/rosettastone/card_rules/minion_set_enchant.v1.json").read_text(encoding="utf-8"))
    catalog = {c["id"]: c for c in json.loads((ROOT / "data/cards/standard_current_enUS.json").read_text(encoding="utf-8"))["cards"]}
    resources = {c["id"]: c for c in json.loads((ROOT / "vendor/RosettaStone/Resources/cards.json").read_text(encoding="utf-8"))}
    return declaration, catalog, resources


def test_all_three_consumers_deterministic_and_no_behavior_ids(inputs):
    declaration, catalog, resources = inputs
    rows = validate(declaration, catalog, resources)
    assert len(rows) == 3
    assert generate(rows) == generate(list(reversed(rows)))
    assert not [r for r in inventory(ROOT) if r["path"] == "scripts/card_rules/minion_set_enchant.py"]
    # Independent second parameterization, not a new root implementation.
    effect = {"op": "MINION_SET_ENCHANT", "selector": "TARGET_MINION",
              "enchantment_ref": "ULD_191e", "keywords": ["TAUNT"]}
    validate_effects("SPELL", [effect], declaration["dependencies"])
    assert render_tasks([effect]) == [
        "std::make_shared<IncludeTask>(EntityType::TARGET)",
        'std::make_shared<AddEnchantmentTask>("ULD_191e", EntityType::STACK)',
        "std::make_shared<SetGameTagTask>(EntityType::STACK, GameTag::TAUNT, 1)",
    ]
    variation = deepcopy(rows[0]); variation["card_id"] = "INDEPENDENT_VARIATION"
    variation["effects"] = [effect]
    assert '"INDEPENDENT_VARIATION"' in generate([variation])[1]
    assert len(render_tasks(rows[0]["effects"])) == 4


@pytest.mark.parametrize("change", [
    lambda d: d.update(extra=True),
    lambda d: d.update(contract_version=2),
    lambda d: d.update(contract_version=True),
    lambda d: d.update(implementation_kind="GENERIC"),
    lambda d: d["cards"].append(deepcopy(d["cards"][0])),
    lambda d: d["cards"][0].update(metadata_sha256="0" * 64),
    lambda d: d["cards"][0]["effects"][0].update(op="EXECUTE_PYTHON"),
    lambda d: d["cards"][0]["effects"][0].update(selector="ALL_CHARACTERS"),
    lambda d: d["cards"][0]["effects"][0].update(enchantment_ref="MISSING_001"),
    lambda d: d["cards"][0]["effects"][0].update(keywords=["REBORN"]),
    lambda d: d["cards"][0]["effects"][0].update(callback="anything"),
    lambda d: d["cards"][0]["effects"].insert(0, deepcopy(d["cards"][0]["effects"][0])),
    lambda d: d["cards"][0].update(effects=["bad"]),
    lambda d: d["cards"][1]["effects"][0].update(max_current_attack=True),
    lambda d: d["cards"][1]["effects"][0].update(max_current_attack=-1),
    lambda d: d["cards"][1]["effects"][0].update(max_current_attack=1001),
    lambda d: d["cards"][1]["effects"][0].update(selector="OWN_HAND_MINIONS"),
    lambda d: d["cards"][2]["effects"][0].update(extra=1),
    lambda d: d["cards"][2]["effects"][1].update(selector="TARGET_MINION"),
    lambda d: d["dependencies"]["ULD_191e"].update(owner_sha256="0" * 64),
    lambda d: d["dependencies"]["ULD_191e"].update(metadata_sha256="0" * 64),
    lambda d: d["dependencies"]["ULD_191e"].update(source_owner="README.md"),
])
def test_schema_fails_closed(inputs, change):
    declaration, catalog, resources = inputs
    change(declaration)
    with pytest.raises(ValueError):
        validate(declaration, catalog, resources)


def test_new_visible_flags_preserve_unknown_and_checkpoint_schema():
    from manamind.domain.serialization import game_state_from_dict
    from manamind.cards.catalog import CardCatalog
    from manamind.encoding.state_encoder import StateEncoder, STATE_ENCODING_SCHEMA_VERSION
    from manamind.encoding.entity_encoder import STATE_FLAG_NAMES
    from manamind.domain.card import CardFeatures
    data = {"turn_number": 1, "active_player": "SELF", "self_player": {"hero_health": 30,
            "board": [{"card_id": "TEST", "attack": 2, "health": 3}]}, "opponent": {"hero_health": 30}}
    encoder = StateEncoder(CardCatalog([CardFeatures(card_id="TEST")]))
    unknown = encoder.encode(game_state_from_dict(data))
    index = STATE_FLAG_NAMES.index("cant_be_targeted_by_spells_known")
    assert unknown.self_board.state_flags[0, index] == 0
    assert game_state_from_dict(data).self_player.hero_divine_shield is None
    data["self_player"]["board"][0]["cant_be_targeted_by_spells"] = False
    data["self_player"]["hero_divine_shield"] = False
    known = encoder.encode(game_state_from_dict(data))
    assert known.self_board.state_flags[0, index] == 1
    assert known.global_features[encoder.global_feature_names.index("self_hero_divine_shield")] < 0
    data["self_player"]["hero_divine_shield"] = True
    assert encoder.encode(game_state_from_dict(data)).global_features[encoder.global_feature_names.index("self_hero_divine_shield")] > 0
    assert STATE_ENCODING_SCHEMA_VERSION == 11
