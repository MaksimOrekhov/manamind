"""ML-POLICY-V3-1: bounded CPU behavior-cloning run on a pre-frozen whole-match split.

Unlike ``train_real_policy.py`` this run needs neither the historical v2 dataset nor a v1 reference: the split comes
from ``ml_policy_v3_freeze.py``. Architecture is ``v2`` (PolicyNetworkV2, fresh random weights) or ``v3``
(PolicyNetworkV3). Selection uses validation cross-entropy only; test metrics are computed only with
``--evaluate-test`` (final candidates), after the weights are chosen and saved. Writes only to a NEW directory.

  python scripts/train_policy_v3.py data/processed_policy_v3/dataset --split data/processed_policy_v3/frozen_split.json \
      --config configs/policy_v3_1/v3_seed42.json --output data/processed_policy_v3/experiment_1/v3_seed42
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract  # noqa: E402
from manamind.models.policy_v3 import PolicyNetworkV3  # noqa: E402
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint  # noqa: E402
from manamind.training.policy_metrics import concentration, diagnostics, evaluate, summarize, uniform_metrics  # noqa: E402
from manamind.training.real_policy import encode_example, load_examples  # noqa: E402

COMMON = {"architecture", "seed", "hidden_size", "dropout", "learning_rate", "weight_decay", "batch_size",
          "max_epochs", "patience", "min_delta", "gradient_clip", "torch_threads", "device"}
V3_ONLY = {"heads", "entity_layers", "menu_layers"}


def validate_config(config: dict) -> None:
    expected = COMMON | (V3_ONLY if config.get("architecture") == "v3" else set())
    if config.get("architecture") not in ("v2", "v3") or set(config) != expected:
        raise ValueError("Unexpected policy config keys")
    if config["device"] != "cpu" or config["torch_threads"] != 1:
        raise ValueError("Bounded deterministic CPU config required")
    for key, maximum in (("seed", 2**31), ("max_epochs", 200), ("patience", 200), ("batch_size", 128),
                         ("hidden_size", 256)):
        if type(config[key]) is not int or not 0 <= config[key] <= maximum or (key != "seed" and config[key] < 1):
            raise ValueError(f"Invalid {key}")
    for key in ("learning_rate", "gradient_clip", "weight_decay", "min_delta", "dropout"):
        if type(config[key]) not in (int, float) or not np.isfinite(config[key]) or config[key] < 0:
            raise ValueError(f"Invalid {key}")
    if config["dropout"] >= 1 or config["learning_rate"] == 0 or config["gradient_clip"] == 0:
        raise ValueError("Invalid dropout/learning rate/gradient clip")


def build_policy(config, encoder):
    contract = feature_contract(encoder)
    shape = dict(card_count=encoder.vocabulary.card_count, state_feature_count=len(contract["state_feature_names"]),
                 entity_feature_count=len(contract["entity_feature_names"]),
                 hidden_size=config["hidden_size"], dropout=config["dropout"])
    if config["architecture"] == "v2":
        return PolicyNetworkV2(**shape)
    return PolicyNetworkV3(**shape, heads=config["heads"], entity_layers=config["entity_layers"],
                           menu_layers=config["menu_layers"])


def quick_metrics(policy, encoded, rows):
    """Validation/train metrics on cached inputs (same formulas as ``policy_metrics.evaluate``)."""
    policy.eval()
    records = []
    with torch.no_grad():
        for (inputs, chosen), _ in zip(encoded, rows):
            logits = policy(*inputs)
            order = torch.argsort(logits, descending=True, stable=True).tolist()
            records.append({"menu_size": len(order), "rank": order.index(chosen) + 1,
                            "loss": torch.nn.functional.cross_entropy(logits[None], torch.tensor([chosen])).item()})
    return summarize(records)


def load_split(dataset: Path, split_path: Path):
    split = json.loads(Path(split_path).read_text(encoding="utf-8"))
    rows = sorted(load_examples(dataset), key=lambda r: r["decision_id"])
    if identity(rows) != split["dataset_sha256"]:
        raise ValueError("Dataset differs from the frozen split")
    parts = {name: [r for r in rows if r["game_id"] in set(ids)] for name, ids in split["game_ids"].items()}
    if sum(len(p) for p in parts.values()) != len(rows):
        raise ValueError("Split does not cover the dataset exactly")
    return rows, parts, split


def run(dataset: Path, split_path: Path, cards: Path, output: Path, config: dict, *, evaluate_test=False,
        train_games: list[str] | None = None, validation_games: list[str] | None = None,
        test_games: list[str] | None = None, label=None, allow_prepare=False, prepared=None) -> dict:
    """``train_games``/``validation_games``/``test_games`` override the frozen split (cross-validation folds only).

    ``allow_prepare`` accepts action schema 2 rows (PREPARE_CARD) and writes a semantic-schema-2 checkpoint; it is off by
    default, so every existing command behaves exactly as before. ``prepared=(parts, split)`` supplies already
    validated partitions (the Prepare experiment's own split plan) instead of reading ``dataset``/``split_path``;
    ``split`` then needs ``dataset_sha256`` and ``game_ids`` with train/validation/test.
    """
    validate_config(config)
    rows, parts, split = (None, *prepared) if prepared is not None else load_split(dataset, split_path)
    if train_games is not None:
        if prepared is not None:
            raise ValueError("Cross-validation folds do not combine with a prepared split")
        by = {r["game_id"]: [] for r in rows}
        for r in rows:
            by[r["game_id"]].append(r)
        parts = {"train": [r for g in train_games for r in by[g]],
                 "validation": [r for g in validation_games for r in by[g]],
                 "test": [r for g in (test_games or []) for r in by[g]]}
        split = {**split, "algorithm": "grouped_cross_validation_fold", "game_ids": {
            "train": sorted(train_games), "validation": sorted(validation_games), "test": sorted(test_games or [])}}
        evaluate_test = bool(test_games)
    catalog = CardCatalog.from_json(cards)
    output.mkdir(parents=True, exist_ok=False)
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.set_num_threads(config["torch_threads"])
    torch.use_deterministic_algorithms(True)
    encoder = StateEncoder(catalog)
    policy = build_policy(config, encoder)
    parameters = sum(p.numel() for p in policy.parameters())
    optimizer = torch.optim.AdamW(policy.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    representation = 2 if config["architecture"] == "v2" else 3
    train = [(encode_example(r, encoder, representation=representation, allow_prepare=allow_prepare),
              r["chosen_action_index"]) for r in parts["train"]]
    valid = [(encode_example(r, encoder, representation=representation, allow_prepare=allow_prepare),
              r["chosen_action_index"]) for r in parts["validation"]]
    rng = random.Random(config["seed"])
    started = time.time()
    initial_validation = quick_metrics(policy, valid, parts["validation"])
    history, best, best_epoch, best_weights, stale = [], float("inf"), 0, None, 0
    for epoch in range(1, config["max_epochs"] + 1):
        policy.train()
        order = list(range(len(train)))
        rng.shuffle(order)
        loss_sum = 0.0
        for start in range(0, len(order), config["batch_size"]):
            indices = order[start:start + config["batch_size"]]
            loss = torch.stack([torch.nn.functional.cross_entropy(policy(*train[i][0])[None],
                                                                  torch.tensor([train[i][1]])) for i in indices]).mean()
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), config["gradient_clip"], error_if_nonfinite=True)
            optimizer.step()
            loss_sum += loss.item() * len(indices)
        validation = quick_metrics(policy, valid, parts["validation"])
        train_metrics = quick_metrics(policy, train, parts["train"])
        history.append({"epoch": epoch, "optimization_loss": loss_sum / len(train), "train": train_metrics,
                        "validation": validation})
        if validation["cross_entropy"] < best - config["min_delta"]:
            best, best_epoch, best_weights, stale = validation["cross_entropy"], epoch, copy.deepcopy(policy.state_dict()), 0
        else:
            stale += 1
        print(json.dumps({"label": label, "epoch": epoch, "train_ce": round(train_metrics["cross_entropy"], 4),
                          "val_ce": round(validation["cross_entropy"], 4), "best_epoch": best_epoch}), flush=True)
        if stale >= config["patience"]:
            break
    seconds = time.time() - started
    policy.load_state_dict(best_weights)
    dataset_sha = split["dataset_sha256"]
    source_paths = [ROOT / p for p in (
        "scripts/train_policy_v3.py", "scripts/ml_policy_v3_freeze.py", "src/manamind/models/policy_v2.py",
        "src/manamind/models/policy_v3.py", "src/manamind/models/policy_inputs.py",
        "src/manamind/training/policy_checkpoint.py", "src/manamind/training/policy_metrics.py",
        "src/manamind/training/real_policy.py")]
    split_keys = ("algorithm", "seed", "game_ids", "dataset_sha256") + (
        ("reserved_game_ids", "plan_sha256", "part_names") if allow_prepare else ())
    metadata = {"dataset_sha256": dataset_sha, "split": {k: v for k, v in split.items() if k in split_keys},
                "config": config, "config_sha256": identity(config), "selected_epoch": best_epoch,
                "epochs_run": len(history), "parameters": parameters, "training_seconds": round(seconds, 1),
                "base_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
                "runtime": {"python": sys.version, "torch": str(torch.__version__), "numpy": np.__version__},
                "selection": "minimum_validation_cross_entropy_with_min_delta", "strength_claim": False,
                "frozen_split_sha256": identity(split) if train_games is None else None,
                "initialization": "fresh_random_no_transfer"}
    if allow_prepare:  # only the experimental path hashes the runner; default runs write the same metadata as before
        metadata["source_sha256"]["scripts/ml_prepare_train.py"] = hashlib.sha256(
            (ROOT / "scripts/ml_prepare_train.py").read_bytes()).hexdigest()
    metadata["split_sha256"] = identity(metadata["split"])
    checkpoint = output / "policy.pt"
    if train_games is None:
        save_policy_checkpoint(checkpoint, policy, encoder, metadata, allow_prepare=allow_prepare)
        restored, saved_encoder, _ = load_policy_checkpoint(checkpoint, allow_prepare=allow_prepare)
        if not all(torch.equal(t, restored.state_dict()[k]) for k, t in policy.state_dict().items()):
            raise ValueError("Checkpoint weight round-trip mismatch")
        probe = encode_example(parts["validation"][0], encoder, representation=representation, allow_prepare=allow_prepare)
        policy.eval()
        with torch.no_grad():
            if not torch.equal(policy(*probe), restored(*probe)):
                raise ValueError("Checkpoint logit round-trip mismatch")
    else:  # cross-validation fold: nothing to publish, no frozen test part to satisfy the checkpoint contract
        restored, saved_encoder = policy, encoder
    result = {"label": label, "architecture": config["architecture"], "selected_epoch": best_epoch,
              "epochs_run": len(history), "parameters": parameters, "training_seconds": round(seconds, 1),
              "best_validation_cross_entropy": best, "initial_validation": initial_validation,
              "final_epoch": history[-1], "best_epoch_record": history[best_epoch - 1],
              "dataset_sha256": dataset_sha, "split_sha256": metadata["split_sha256"],
              "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest() if checkpoint.exists() else None,
              "strength_claim": False}
    names = ["train", "validation"] + (["test"] if evaluate_test else [])
    details = {}
    for name in names:
        learned, records = evaluate(restored, parts[name], saved_encoder, allow_prepare=allow_prepare)
        result[name] = {"learned": learned, "uniform_random_expected": uniform_metrics(parts[name])}
        details[name] = {"diagnostics": diagnostics(records), "concentration": concentration(parts[name])}
    if train_games is not None and parts["test"]:  # per-decision logits of the held-out fold for pooled comparisons
        restored.eval()
        with torch.no_grad():
            held = {r["decision_id"]: restored(*encode_example(r, saved_encoder, representation=representation,
                                                               allow_prepare=allow_prepare)).tolist()
                    for r in parts["test"]}
        with (output / "heldout_logits.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(held, stream)
    for name, payload in (("history.json", {"initial_validation": initial_validation, "epochs": history}),
                          ("metrics.json", result), ("diagnostics.json", details), ("config.json", config)):
        with (output / name).open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--evaluate-test", action="store_true", help="Final candidates only")
    args = parser.parse_args()
    result = run(args.dataset, args.split, args.cards, args.output, json.loads(args.config.read_text(encoding="utf-8-sig")),
                 evaluate_test=args.evaluate_test, label=args.output.name)
    print(json.dumps({k: result[k] for k in ("label", "selected_epoch", "epochs_run", "parameters",
                                             "training_seconds", "best_validation_cross_entropy")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
