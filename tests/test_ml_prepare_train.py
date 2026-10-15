"""ML-PREPARE-TRAIN-1: the opt-in Prepare training path, the semantic-schema-2 checkpoint marker and the experiment split.

Synthetic matches only. Tiny trainings (a few epochs, hidden size 16) check plumbing, not model quality.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import ml_prepare_train as experiment  # noqa: E402
import train_policy_v3 as trainer  # noqa: E402
from test_policy_prepare_data import prepare_rows, v1_row  # noqa: E402
from test_real_policy_dataset import CATALOG  # noqa: E402

from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.models.policy import PolicyNetwork  # noqa: E402
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract  # noqa: E402
from manamind.models.policy_v3 import PolicyNetworkV3  # noqa: E402
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint  # noqa: E402
from manamind.training.policy_metrics import evaluate  # noqa: E402
from manamind.training.real_policy import encode_example  # noqa: E402


def metadata(reserved=None):
    config = {"seed": 42}
    split = {"dataset_sha256": "a" * 64, "game_ids": {"train": ["a" * 64], "validation": ["b" * 64],
                                                      "test": ["c" * 64]}}
    if reserved is not None:
        split["reserved_game_ids"] = reserved
    return {"dataset_sha256": "a" * 64, "split": split, "split_sha256": identity(split),
            "config": config, "config_sha256": identity(config)}


def v3_policy(encoder):
    contract = feature_contract(encoder)
    return PolicyNetworkV3(card_count=encoder.vocabulary.card_count,
                           state_feature_count=len(contract["state_feature_names"]),
                           entity_feature_count=len(contract["entity_feature_names"]), hidden_size=16, dropout=0.1)


def v2_policy(encoder):
    contract = feature_contract(encoder)
    return PolicyNetworkV2(card_count=encoder.vocabulary.card_count,
                           state_feature_count=len(contract["state_feature_names"]),
                           entity_feature_count=len(contract["entity_feature_names"]), hidden_size=16, dropout=0.1)


# -- checkpoint marker -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("make", [v2_policy, v3_policy])
def test_prepare_checkpoint_needs_the_explicit_flag_and_keeps_logits(tmp_path, make):
    encoder = StateEncoder(CATALOG)
    policy = make(encoder)
    row, = prepare_rows()
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, policy, encoder, metadata(["d" * 64]), allow_prepare=True)
    for loader in (lambda: load_policy_checkpoint(path), lambda: load_policy_checkpoint(path, allow_prepare=False)):
        with pytest.raises(ValueError, match="semantic_action_schema_version"):
            loader()
    restored, restored_encoder, payload = load_policy_checkpoint(path, allow_prepare=True)
    assert payload["semantic_action_schema_version"] == 2
    representation = 2 if make is v2_policy else 3
    with torch.no_grad():
        probe = encode_example(row, encoder, representation=representation, allow_prepare=True)
        assert torch.equal(policy.eval()(*probe), restored(*encode_example(
            row, restored_encoder, representation=representation, allow_prepare=True)))


def test_default_checkpoints_stay_semantic_1_and_load_with_or_without_the_flag(tmp_path):
    encoder = StateEncoder(CATALOG)
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, v2_policy(encoder), encoder, metadata())
    assert load_policy_checkpoint(path)[2]["semantic_action_schema_version"] == 1
    assert load_policy_checkpoint(path, allow_prepare=True)[2]["semantic_action_schema_version"] == 1


def test_changing_the_semantic_version_of_either_kind_of_checkpoint_is_refused(tmp_path):
    encoder = StateEncoder(CATALOG)
    plain, prepared = tmp_path / "plain.pt", tmp_path / "prepared.pt"
    save_policy_checkpoint(plain, v2_policy(encoder), encoder, metadata())
    save_policy_checkpoint(prepared, v2_policy(encoder), encoder, metadata(), allow_prepare=True)
    for path, value in ((plain, 2), (prepared, 1), (prepared, 3), (plain, 0)):
        payload = torch.load(path, weights_only=True)
        payload["semantic_action_schema_version"] = value
        tampered = tmp_path / f"tampered_{path.stem}_{value}.pt"
        torch.save(payload, tampered)
        with pytest.raises(ValueError):
            load_policy_checkpoint(tampered, allow_prepare=True)


def test_prepare_checkpoint_is_for_v2_v3_only_and_reserved_ids_stay_out_of_every_part(tmp_path):
    encoder = StateEncoder(CATALOG)
    with pytest.raises(ValueError):
        save_policy_checkpoint(tmp_path / "v1.pt", PolicyNetwork(card_count=encoder.vocabulary.card_count), encoder,
                               metadata(), allow_prepare=True)
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, v2_policy(encoder), encoder, metadata(["a" * 64]), allow_prepare=True)
    with pytest.raises(ValueError, match="split identity"):  # a reserved match that is also in train
        load_policy_checkpoint(path, allow_prepare=True)


# -- experiment data ---------------------------------------------------------------------------------------------------

def write_corpus(root: Path) -> dict:
    """train [P, V], validation [P, V], test_seen [V, P], fresh_holdout [P] with Prepare (P) and plain (V) matches."""
    layout = {"train": [("p", 1), ("v", 3)], "validation": [("p", 2), ("v", 5)], "test_seen": [("v", 4), ("p", 6)],
              "fresh_holdout": [("p", 7)]}
    parts = {}
    (root / "dataset").mkdir(parents=True)
    for name, matches in layout.items():
        parts[name] = []
        for kind, seed in matches:
            row = prepare_rows(seed=seed)[0] if kind == "p" else v1_row(seed=seed)
            lines = [row]
            if kind == "p":  # like every real match: a Prepare decision next to an ordinary schema 1 one
                plain = copy.deepcopy(v1_row(seed=3))
                plain["game_id"], plain["decision_id"] = row["game_id"], row["game_id"] + ":99"
                plain["provenance"] = {**plain["provenance"], "options_line": 1, "selection_line": 2}
                lines.append(plain)
            (root / "dataset" / f"{row['game_id']}.jsonl").write_text(
                "\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")
            parts[name].append(row["game_id"])
    plan = {"algorithm": "policy_prepare_data_1_split/1", "seed": 7, "parts": {k: sorted(v) for k, v in parts.items()}}
    plan["split_sha256"] = identity({"algorithm": plan["algorithm"], "seed": plan["seed"], "parts": plan["parts"]})
    (root / "split_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return plan


@pytest.fixture()
def corpus(tmp_path):
    root = tmp_path / "corpus"
    return root, write_corpus(root)


def test_fresh_holdout_is_never_opened_and_parts_are_disjoint(corpus, monkeypatch):
    root, plan = corpus
    opened = []
    original = experiment.read_match
    monkeypatch.setattr(experiment, "read_match", lambda c, g: opened.append(g) or original(c, g))
    parts, _ = experiment.load_parts(root)
    assert set(opened) == {g for name in ("train", "validation", "test_seen") for g in plan["parts"][name]}
    assert not set(opened) & set(plan["parts"]["fresh_holdout"])
    split = experiment.build_split(parts, plan)
    assert split["reserved_game_ids"] == plan["parts"]["fresh_holdout"]
    all_ids = [g for ids in split["game_ids"].values() for g in ids]
    assert len(all_ids) == len(set(all_ids)) == 6
    assert split["game_ids"]["test"] == plan["parts"]["test_seen"]


def test_plan_must_match_files_hash_and_be_disjoint(corpus):
    root, plan = corpus
    experiment.load_plan(root)
    broken = copy.deepcopy(plan)
    broken["parts"]["train"].append(plan["parts"]["validation"][0])
    (root / "split_plan.json").write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError):
        experiment.load_plan(root)
    (root / "split_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (root / "dataset" / f"{'f' * 64}.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="cover"):
        experiment.load_plan(root)


def test_control_keeps_exactly_the_schema_1_rows(corpus):
    parts, _ = experiment.load_parts(corpus[0])
    control = experiment.schema1_only(parts)
    assert all(r["action_schema_version"] == 1 for rows in control.values() for r in rows)
    for name in parts:
        assert [r for r in parts[name] if r["action_schema_version"] == 1] == control[name]
    assert any(r["action_schema_version"] == 2 for rows in parts.values() for r in rows)


# -- training paths ----------------------------------------------------------------------------------------------------

def tiny_experiment(tmp_path, root):
    base = {"base": {"architecture": "v2", "seed": 0, "hidden_size": 16, "dropout": 0.1, "heads": 4,
                     "entity_layers": 1, "menu_layers": 1, "learning_rate": 0.001, "weight_decay": 0.001,
                     "batch_size": 4, "max_epochs": 2, "patience": 8, "min_delta": 0.0001, "gradient_clip": 1.0,
                     "torch_threads": 1, "device": "cpu"}}
    (tmp_path / "base.json").write_text(json.dumps(base), encoding="utf-8")
    spec = {"base_config": str(tmp_path / "base.json"),
            "groups": {"prepare_v3": {"architecture": "v3", "data": "all", "allow_prepare": True},
                       "control_v2": {"architecture": "v2", "data": "schema1_only", "allow_prepare": False}}}
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_prepare_and_control_runs_write_distinct_checkpoints_and_never_touch_the_holdout(tmp_path, corpus):
    root, plan = corpus
    spec = tiny_experiment(tmp_path, root)
    out = tmp_path / "out"
    first = experiment.train("prepare_v3", 42, out, root, spec)
    control = experiment.train("control_v2", 42, out, root, spec)
    with pytest.raises((FileExistsError, OSError)):  # an existing result directory is never overwritten
        experiment.train("prepare_v3", 42, out, root, spec)
    policy, encoder, payload = load_policy_checkpoint(out / "prepare_v3_seed42/policy.pt", allow_prepare=True)
    assert payload["semantic_action_schema_version"] == 2 and payload["experiment"]["allow_prepare"] is True
    assert payload["experiment"]["split"]["reserved_game_ids"] == plan["parts"]["fresh_holdout"]
    assert payload["experiment"]["split"]["plan_sha256"] == plan["split_sha256"]
    plain, _, plain_payload = load_policy_checkpoint(out / "control_v2_seed42/policy.pt")
    assert plain_payload["semantic_action_schema_version"] == 1
    assert "allow_prepare" not in plain_payload["experiment"]  # default runs keep their old metadata shape
    assert first["checkpoint_sha256"] != control["checkpoint_sha256"]
    provenance = json.loads((out / "prepare_v3_seed42/provenance.json").read_text(encoding="utf-8"))
    assert provenance["fresh_holdout_opened"] is False
    assert not set(provenance["match_file_sha256"]) & set(plan["parts"]["fresh_holdout"])
    assert provenance["prepare_in_menu"] == {"train": 1, "validation": 1, "test": 1}
    assert json.loads((out / "control_v2_seed42/provenance.json").read_text(encoding="utf-8"))["prepare_in_menu"] == {
        "train": 0, "validation": 0, "test": 0}
    # the Prepare model scores Prepare menus; the control scores them too only when asked to (analysis path)
    parts, _ = experiment.load_parts(root)
    metrics, _ = evaluate(policy, parts["test"], encoder, allow_prepare=True)
    assert metrics["decisions"] == len(parts["test"])
    with pytest.raises(ValueError):
        evaluate(plain, parts["test"], encoder)


def test_default_training_still_refuses_prepare_rows_and_accepts_version_1(tmp_path, corpus):
    root, _ = corpus
    parts, plan = experiment.load_parts(root)
    config = experiment.group_config(Path(tiny_experiment(tmp_path, root)).parent / "base.json", "v2", 42)
    with pytest.raises(ValueError):  # no allow_prepare: a schema 2 row is refused before any training happens
        trainer.run(root / "dataset", root / "split_plan.json", ROOT / "data/cards/standard_current_enUS.json",
                    tmp_path / "default_refused", config, prepared=(parts, experiment.build_split(parts, plan)))
    plain = experiment.schema1_only(parts)
    trainer.run(root / "dataset", root / "split_plan.json", ROOT / "data/cards/standard_current_enUS.json",
                tmp_path / "default_ok", config, prepared=(plain, experiment.build_split(plain, plan)))
    assert load_policy_checkpoint(tmp_path / "default_ok/policy.pt")[2]["semantic_action_schema_version"] == 1


def test_registered_experiment_names_the_four_groups_and_hides_the_holdout():
    spec = json.loads((ROOT / "configs/ml_prepare_train_1/experiment.json").read_text(encoding="utf-8"))
    assert set(spec["groups"]) == {"prepare_v2", "prepare_v3", "control_v2", "control_v3"}
    assert spec["parts_never_opened"] == ["fresh_holdout"]
    assert {g["allow_prepare"] for n, g in spec["groups"].items() if n.startswith("control")} == {False}
    assert spec["seeds_all"][:1] == spec["seeds_first"]
