"""TL2 data integrity and numeric interventions, without optimizer runs."""
import copy
import sys
from pathlib import Path

import pytest

from manamind.cards.catalog import CardCatalog
from manamind.domain.card import CardFeatures
from manamind.domain.serialization import game_state_from_dict
from manamind.encoding.state_encoder import StateEncoder
from manamind.training.tactical_learning_2_gate import arithmetic_gold, validate_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from prepare_tactical_learning_2 import fixture, menu  # noqa: E402
from train_tactical_learning_2 import preflight, selection_guard  # noqa: E402
from evaluate_tactical_learning_2 import pairs  # noqa: E402


@pytest.fixture
def context():
    cards = [CardFeatures(card_id=f"TL2_PLAIN_{i}", cost=2, attack=2, health=3,
                         card_type="MINION", card_class="NEUTRAL") for i in range(2)]
    cards.append(CardFeatures(card_id="CORE_CS2_029", cost=4, card_type="SPELL", card_class="MAGE"))
    raw = {c.card_id: {"id": c.card_id, "type": c.card_type, "cardClass": c.card_class,
           "cost": c.cost, "attack": c.attack, "health": c.health, "mechanics": [],
           "text": "Deal $6 damage." if c.card_type == "SPELL" else ""} for c in cards}
    return StateEncoder(CardCatalog(cards)), cards[:2], raw


@pytest.mark.parametrize("split", ["train", "validation", "control"])
@pytest.mark.parametrize("family", ["one_finish", "multi_finish", "health", "attack", "target", "harm", "ambiguous"])
def test_independent_arithmetic_and_outcome(context, split, family):
    encoder, pool, raw = context
    row = fixture(split, family, 1, encoder, pool, raw)
    result = validate_row(row, encoder, raw, menu)
    assert bool(result["gold"]) == (family != "ambiguous")


@pytest.mark.parametrize("family,field", [("health", "current_health"), ("attack", "current_attack")])
def test_one_numeric_intervention_changes_correct_source(context, family, field):
    encoder, pool, raw = context
    row = fixture("control", family, 0, encoder, pool, raw)
    changed = copy.deepcopy(row)
    board = changed["state"]["self_player"]["board"]
    ordered = sorted(board, key=lambda m: m[field], reverse=True)
    ordered[0][field], ordered[1][field] = ordered[1][field], ordered[0][field]
    changed["legal_actions"] = menu(game_state_from_dict(changed["state"]))
    changed["correct_actions"] = [changed["legal_actions"][i] for i in arithmetic_gold(changed)]
    before = validate_row(row, encoder, raw, menu)["gold"]
    after = validate_row(changed, encoder, raw, menu)["gold"]
    assert row["legal_actions"][before[0]]["source_card_id"] != changed["legal_actions"][after[0]]["source_card_id"]
    for a, b in zip(row["state"]["self_player"]["board"], board, strict=True):
        assert {k:v for k,v in a.items() if k != field} == {k:v for k,v in b.items() if k != field}


@pytest.mark.parametrize("mutation", ["text", "base", "effect", "gold", "menu", "synthetic"])
def test_gate_rejects_corrupted_data(context, mutation):
    encoder, pool, raw = context
    row = fixture("control", "target", 1, encoder, pool, raw)
    if mutation == "text":
        next(t for t in row["certificate"]["texts"] if t["id"] == "CORE_CS2_029")["text"] = ""
    elif mutation == "base":
        row["state"]["self_hand"][0]["cost"] = 1
    elif mutation == "effect":
        del row["certificate"]["observed"]["spell_damage_doubled"]
    elif mutation == "gold":
        row["correct_actions"] = [row["legal_actions"][-1]]
    elif mutation == "menu":
        row["legal_actions"].pop()
    else:
        synthetic = next(t for t in row["certificate"]["texts"] if t["id"] not in raw)
        synthetic["text"] = "Battlecry: Deal 1 damage."
    with pytest.raises(ValueError):
        validate_row(row, encoder, raw, menu)


def test_failed_gate_blocks_before_checkpoint_load(tmp_path, monkeypatch):
    import json
    import train_tactical_learning_2 as trainer
    (tmp_path/"manifest.json").write_text(json.dumps({"data_gate_passed": False}))
    (tmp_path/"data_gate.json").write_text(json.dumps({"all_passed": False}))
    monkeypatch.setattr(trainer, "load_policy_checkpoint", lambda *a, **k: pytest.fail("Loaded before gate"))
    with pytest.raises(ValueError, match="data gate failed"):
        preflight(tmp_path)


def test_epoch_selection_allows_bounded_real_ce_loss():
    cfg = {"real_selection_CE_tolerance": .03, "real_selection_top1_tolerance": .03}
    initial = {"cross_entropy": 1.5, "top1_accuracy": .5}
    assert selection_guard({"cross_entropy": 1.52, "top1_accuracy": .49}, initial, cfg)
    assert not selection_guard({"cross_entropy": 1.54, "top1_accuracy": .49}, initial, cfg)
    assert not selection_guard({"cross_entropy": 1.52, "top1_accuracy": .46}, initial, cfg)


def test_multiple_invariance_pairs_share_one_base_case(context):
    encoder, pool, raw = context
    base = fixture("control", "one_finish", 0, encoder, pool, raw)
    position, alias = copy.deepcopy(base), copy.deepcopy(base)
    position["scenario_id"] += "_position"
    alias["scenario_id"] += "_id"
    base["pairs"] = [{"kind": "position", "id": "p"}, {"kind": "id", "id": "i"}]
    position["pairs"] = base["pairs"][:1]
    alias["pairs"] = base["pairs"][1:]
    rows = [base, position, alias]
    records = [{"id": r["scenario_id"], "rank": 1, "prediction": r["correct_actions"][0]} for r in rows]
    result = pairs(rows, records)
    assert result["position"]["pairs"] == result["id"]["pairs"] == 1
    assert result["position"]["both_correct"] == result["id"]["both_correct"] == 1
