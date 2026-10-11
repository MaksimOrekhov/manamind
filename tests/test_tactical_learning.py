"""Mechanical certificates and protocol boundaries; no optimizer/training runs."""
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import torch

from manamind.cards.catalog import CardCatalog
from manamind.domain.card import CardFeatures
from manamind.domain.serialization import game_state_from_dict
from manamind.encoding.state_encoder import StateEncoder
from manamind.training.tactical_certificates import certify, sequence_firsts, set_loss
from manamind.training.tactical_learning import Stream, encode_rows, labels, real_parts

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from prepare_tactical_learning import fixture, menu, semantic_fingerprint  # noqa: E402
import evaluate_tactical_learning as evaluator  # noqa: E402
import manamind.training.tactical_learning as learning  # noqa: E402


@pytest.fixture
def encoder():
    return StateEncoder(CardCatalog([CardFeatures(card_id=f"PLAIN_{i}", cost=2, attack=2,
        health=3, card_type="MINION", card_class="NEUTRAL") for i in range(8)] +
        [CardFeatures(card_id="CORE_CS2_029", cost=4, card_type="SPELL", card_class="MAGE")]))


@pytest.mark.parametrize("family", ["armor_finish", "shield_finish", "taunt_finish", "combined_finish",
    "two_taunts", "hero_shield_finish", "poison", "poison_taunt", "poison_shield", "stats_target",
    "immune", "self_damage", "two_self_damage", "spell_finish", "spell_side", "lifesteal", "shield_lifesteal"])
def test_recipe_independent_certificate_and_existing_encoder(encoder, family):
    row = fixture("control", family, 3, encoder)
    assert set(labels(row)) == set(certify(row)["gold"])
    inputs, gold = encode_rows([row], encoder, "cpu")[0]
    assert gold and all(torch.isfinite(x).all() for x in inputs)


def test_set_marginal_loss_keeps_all_equivalent_actions():
    scores = torch.tensor([2., 2., -3.], requires_grad=True)
    loss = set_loss(scores, [0, 1])
    assert loss < set_loss(scores, [0])
    loss.backward()
    assert scores.grad[0] == scores.grad[1] and scores.grad[2] > 0
    with pytest.raises(ValueError):
        set_loss(scores, [0, 0])


def test_unknown_shield_cannot_certify_lethal(encoder):
    row = fixture("control", "shield_finish", 0, encoder)
    row["state"]["opponent"]["hero_divine_shield"] = None
    with pytest.raises(ValueError):
        certify(row)


def test_sequence_bound_includes_hero_and_rejects_frozen_sources(encoder):
    row = fixture("control", "hero_shield_finish", 0, encoder)
    state = game_state_from_dict(row["state"])
    source = state.self_player.board[0]
    crowded = replace(state, self_player=replace(state.self_player,
        board=tuple(replace(source, board_position=i+1) for i in range(4))))
    with pytest.raises(ValueError, match="includes the hero"):
        sequence_firsts(crowded, menu(crowded))
    frozen = replace(state, self_player=replace(state.self_player, board=(replace(source, frozen=True),)))
    with pytest.raises(ValueError, match="ready and alive"):
        sequence_firsts(frozen, menu(frozen))


def test_unknown_control_has_no_gold(encoder):
    row = fixture("control", "ambiguous_face", 0, encoder)
    assert row["state"]["opponent"]["hero_divine_shield"] is None
    assert not labels(row) and not certify(row)["gold"]


def test_taunt_multiple_first_actions_and_position_invariance(encoder):
    row = fixture("control", "two_taunts", 1, encoder)
    assert len(labels(row)) == 6
    changed = copy.deepcopy(row)
    for side in ("self_player", "opponent"):
        b = changed["state"][side]["board"]
        for m in b:
            m["board_position"] = len(b)+1-m["board_position"]
        b.sort(key=lambda m: m["board_position"])
    changed["legal_actions"] = menu(game_state_from_dict(changed["state"]))
    assert len(certify(changed)["gold"]) == 6
    assert semantic_fingerprint(row) == semantic_fingerprint(changed)


@pytest.mark.parametrize("n,field", [(0, "current_health"), (4, "current_attack")])
def test_stats_intervention_changes_surviving_killer(encoder, n, field):
    row = fixture("control", "stats_target", n, encoder)
    first = row["legal_actions"][labels(row)[0]]["source_card_id"]
    changed = copy.deepcopy(row)
    board = changed["state"]["self_player"]["board"]
    board[0][field], board[1][field] = board[1][field], board[0][field]
    changed["legal_actions"] = menu(game_state_from_dict(changed["state"]))
    gold = certify(changed)["gold"]
    assert len(gold) == 1 and changed["legal_actions"][gold[0]]["source_card_id"] != first


def test_stream_covers_every_real_row_without_duplication_in_first_cycle():
    a, b = Stream(1175, 42), Stream(1175, 42)
    assert a.take(1175) == b.take(1175)
    assert len(set(Stream(1175, 42).take(1175))) == 1175


def test_train_reader_never_opens_test_bodies(tmp_path, monkeypatch):
    touched = []
    def reader(path):
        assert path.stem != "heldout"
        touched.append(path.stem)
        return [{"game_id": path.stem, "decision_id": path.stem+"_decision"}]
    monkeypatch.setattr(learning, "read_rows", reader)
    monkeypatch.setattr(learning, "validate_example", lambda row: None)
    split = {"game_ids": {"train": ["train"], "validation": ["val"], "test": ["heldout"]},
             "decision_ids": {"train": ["train_decision"], "validation": ["val_decision"]}}
    assert len(real_parts(tmp_path, split)) == 2
    assert touched == ["train", "val"]


def test_already_opened_control_blocks_before_reading_or_scoring(tmp_path, monkeypatch):
    dataset, runs = tmp_path/"dataset", tmp_path/"runs"
    dataset.mkdir()
    runs.mkdir()
    initial, frozen = tmp_path/"initial.pt", tmp_path/"frozen.pt"
    initial.write_bytes(b"initial")
    frozen.write_bytes(b"frozen")
    monkeypatch.setattr(evaluator, "INITIAL", initial)
    monkeypatch.setattr(evaluator, "FROZEN", frozen)
    monkeypatch.setattr(evaluator, "INITIAL_SHA", evaluator.sha(initial))
    monkeypatch.setattr(evaluator, "FROZEN_SHA", evaluator.sha(frozen))
    (dataset/"control.jsonl").write_text("must remain unopened")
    (dataset/"manifest.json").write_text(json.dumps({"files": {"control": evaluator.sha(dataset/"control.jsonl")}}))
    candidates = {}
    for name in ("A", "B"):
        (runs/name).mkdir()
        (runs/name/"policy.pt").write_bytes(name.encode())
        candidates[name] = {"checkpoint_sha256": evaluator.sha(runs/name/"policy.pt")}
    (runs/"TRAINING_COMPLETE.json").write_text(json.dumps({"candidates": candidates,
        "dataset_manifest_sha256": evaluator.sha(dataset/"manifest.json")}))
    (runs/"CONTROL_OPENED.json").write_text("already opened")
    def forbidden(path):
        pytest.fail("Previously opened control was read again")
    monkeypatch.setattr(evaluator, "read_rows", forbidden)
    with pytest.raises(FileExistsError):
        evaluator.run(dataset, runs, tmp_path/"evaluation")
    assert not (tmp_path/"evaluation").exists()
