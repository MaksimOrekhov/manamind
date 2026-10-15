"""ML-PREPARE-ABLATION-1: the prepare_card column is the only input that the ablation changes."""
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
from test_ml_prepare_train import tiny_experiment, write_corpus  # noqa: E402
from test_policy_prepare_data import PLAY_AND_PREPARE, prepare_rows, v1_row  # noqa: E402
from test_real_policy_dataset import CATALOG  # noqa: E402

from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.live.snapshot import state_hash  # noqa: E402
from manamind.models.policy_v2 import ACTION_V2_FEATURE_NAMES  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402
from manamind.training.real_policy import encode_example  # noqa: E402

COLUMN = ACTION_V2_FEATURE_NAMES.index("prepare_card")


@pytest.mark.parametrize("representation", [2, 3])
def test_mask_changes_only_the_prepare_card_column(representation):
    encoder = StateEncoder(CATALOG)
    row, = prepare_rows(roots=PLAY_AND_PREPARE)
    before = copy.deepcopy(row)
    plain = encode_example(row, encoder, representation=representation, allow_prepare=True)
    masked = encode_example(row, encoder, representation=representation, allow_prepare=True, mask_prepare_feature=True)
    assert row == before                                    # menu, order and labels are not touched
    assert len(plain) == len(masked)
    for index, (a, b) in enumerate(zip(plain, masked)):
        assert a.shape == b.shape and a.dtype == b.dtype
        if index != 3:                                      # state, entity tensors, card ids, links
            assert torch.equal(a, b)
    difference = plain[3] != masked[3]
    assert difference.any(dim=0).nonzero().flatten().tolist() == [COLUMN]
    assert plain[3][:, COLUMN].sum() > 0 and masked[3][:, COLUMN].sum() == 0
    assert all(torch.isfinite(t).all() for t in masked if t.is_floating_point())


def test_mask_leaves_menus_without_prepare_bit_identical_and_does_not_touch_the_original_tensor():
    encoder = StateEncoder(CATALOG)
    row = v1_row()
    plain = encode_example(row, encoder, representation=2)
    masked = encode_example(row, encoder, representation=2, mask_prepare_feature=True)
    assert all(torch.equal(a, b) for a, b in zip(plain, masked))
    rows = prepare_rows()
    first = encode_example(rows[0], encoder, representation=2, allow_prepare=True)
    encode_example(rows[0], encoder, representation=2, allow_prepare=True, mask_prepare_feature=True)
    again = encode_example(rows[0], encoder, representation=2, allow_prepare=True)
    assert all(torch.equal(a, b) for a, b in zip(first, again))


def test_other_cues_for_the_action_type_remain_so_the_ablation_is_partial():
    encoder = StateEncoder(CATALOG)
    row, = prepare_rows(roots=PLAY_AND_PREPARE)
    features = encode_example(row, encoder, representation=2, allow_prepare=True, mask_prepare_feature=True)[3]
    kinds = [a["type"] for a in row["legal_actions"]]
    prepare, play = kinds.index("PREPARE_CARD"), kinds.index("PLAY_CARD")
    assert not torch.equal(features[prepare], features[play])      # still distinguishable by other columns


def test_ablation_needs_v2_or_v3_and_the_prepare_path(tmp_path):
    encoder = StateEncoder(CATALOG)
    with pytest.raises(ValueError):
        encode_example(v1_row(), encoder, representation=1, mask_prepare_feature=True)
    with pytest.raises(ValueError, match="Prepare-aware"):
        trainer.run(tmp_path, tmp_path / "s.json", tmp_path / "c.json", tmp_path / "out", {}, ablate_prepare_feature=True)


def test_ablated_run_records_the_flag_keeps_data_identity_and_stays_semantic_2(tmp_path):
    root = tmp_path / "corpus"
    plan = write_corpus(root)
    spec_path = tiny_experiment(tmp_path, root)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["groups"]["prepare_v2"] = {"architecture": "v2", "data": "all", "allow_prepare": True}
    spec["groups"]["ablated_v2"] = {"architecture": "v2", "data": "all", "allow_prepare": True,
                                    "ablate_prepare_feature": True}
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out"
    experiment.train("prepare_v2", 42, out, root, spec_path)
    experiment.train("ablated_v2", 42, out, root, spec_path)
    _, _, normal = load_policy_checkpoint(out / "prepare_v2_seed42/policy.pt", allow_prepare=True)
    _, _, ablated = load_policy_checkpoint(out / "ablated_v2_seed42/policy.pt", allow_prepare=True)
    assert ablated["experiment"]["ablate_prepare_feature"] is True and "ablate_prepare_feature" not in normal["experiment"]
    assert ablated["semantic_action_schema_version"] == 2
    for key in ("dataset_sha256", "split_sha256", "config_sha256"):
        assert ablated["experiment"][key] == normal["experiment"][key]
    assert ablated["model_config"] == normal["model_config"]
    assert ablated["experiment"]["split"]["reserved_game_ids"] == plan["parts"]["fresh_holdout"]
    provenance = json.loads((out / "ablated_v2_seed42/provenance.json").read_text(encoding="utf-8"))
    assert provenance["ablate_prepare_feature"] is True and provenance["fresh_holdout_opened"] is False
    with pytest.raises(FileExistsError):
        experiment.train("ablated_v2", 42, out, root, spec_path)


# -- analysis helpers ---------------------------------------------------------------------------------------------------

import ml_prepare_ablation_analyze as ablation  # noqa: E402


def test_unknown_card_probe_changes_only_the_card_embedding_indices():
    encoder = StateEncoder(CATALOG)
    row, = prepare_rows(roots=PLAY_AND_PREPARE)
    prepared = next(a["card_id"] for a in row["legal_actions"] if a["type"] == "PREPARE_CARD")
    token = "JAIL_913"
    assert encoder.vocabulary.card_id(token) != 1
    row = json.loads(json.dumps(row).replace(f'"{prepared}"', f'"{token}"'))   # a real vocabulary card in hand and menu
    row["provenance"]["state_hash"] = state_hash(row["state"])
    plain = encode_example(row, encoder, representation=2, allow_prepare=True)
    probed = encode_example(row, ablation.unknown_card_encoder(StateEncoder(CATALOG), token), representation=2,
                            allow_prepare=True)
    assert all(a.shape == b.shape for a, b in zip(plain, probed))
    assert StateEncoder(CATALOG).vocabulary.card_id(token) != 1            # a fresh encoder is unaffected
    changed = [i for i, (a, b) in enumerate(zip(plain, probed)) if not torch.equal(a, b)]
    assert changed and set(changed) <= {1, 4}   # entity and action card ids only: stats, features and links identical
    assert all(torch.equal(plain[i], probed[i]) for i in (0, 2, 3, 5))


def report_for_verdict(difference, ci, parts=(-0.3, -0.3), other=(0.0, 0.02), seeds_neg=(3, 3)):
    seeds = [42, 43, 44]
    differences = {"pooled/prepare_in_menu": {"cross_entropy": {"difference": difference, "ci95": list(ci)}},
                   "pooled/no_prepare_in_menu": {"cross_entropy": {"difference": other[0], "ci95": [-0.01, other[1]]}},
                   "validation/prepare_in_menu": {"cross_entropy": {"difference": parts[0], "ci95": list(ci)}},
                   "test/prepare_in_menu": {"cross_entropy": {"difference": parts[1], "ci95": list(ci)}}}
    per_seed = {f"{p}/prepare_in_menu/seed{s}": {"cross_entropy": -0.1 if i < seeds_neg[0] else 0.1}
                for p in ("validation", "test") for i, s in enumerate(seeds)}
    return {"seeds": seeds, "paired": {"prepare_v2_minus_ablated_v2": {"differences": differences, "per_seed": per_seed}}}


def test_verdict_rules_and_the_documented_tie_break():
    useful = ablation.verdict(report_for_verdict(-0.30, (-0.45, -0.15)))
    assert useful["verdict"] == "FEATURE_USEFUL"
    tie = ablation.verdict(report_for_verdict(-0.01, (-0.02, -0.002), parts=(-0.006, -0.013)))
    assert tie["registered_conditions_met"] == {"FEATURE_USEFUL": True, "FEATURE_WEAK_OR_REDUNDANT": True}
    assert tie["verdict"] == "FEATURE_WEAK_OR_REDUNDANT" and tie["rule_overlap_resolved_in_favour_of"]
    assert tie["verdict_if_first_matching_rule_in_registration_order_were_used"] == "FEATURE_USEFUL"
    wide = ablation.verdict(report_for_verdict(-0.20, (-0.50, 0.10)))
    assert wide["verdict"] == "INCONCLUSIVE"
    assert ablation.verdict(report_for_verdict(0.05, (0.01, 0.09)))["verdict"] == "FEATURE_WEAK_OR_REDUNDANT"
    assert useful["strength_claim"] is False


def test_scoring_checks_the_digest_and_applies_the_training_mask_by_default(tmp_path):
    from test_ml_prepare_train import metadata, v2_policy
    from manamind.training.policy_checkpoint import save_policy_checkpoint
    encoder = StateEncoder(CATALOG)
    policy = v2_policy(encoder)
    meta = metadata()
    meta["ablate_prepare_feature"] = True
    path = tmp_path / "policy.pt"
    save_policy_checkpoint(path, policy, encoder, meta, allow_prepare=True)
    row, = prepare_rows(roots=PLAY_AND_PREPARE)
    sha = ablation.base.sha256_file(path)
    as_trained, _ = ablation.score(path, [row], sha)
    forced_off, _ = ablation.score(path, [row], sha, mask=False)
    forced_on, _ = ablation.score(path, [row], sha, mask=True)
    assert as_trained == forced_on and as_trained != forced_off   # the flag in the checkpoint decides the mask
    with torch.no_grad():
        expected = policy.eval()(*encode_example(row, encoder, representation=2, allow_prepare=True,
                                                 mask_prepare_feature=True)).tolist()
    assert as_trained[row["decision_id"]] == pytest.approx(expected)
    with pytest.raises(ValueError, match="SHA-256"):
        ablation.score(path, [row], "0" * 64)
