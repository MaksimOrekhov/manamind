"""One frozen CPU behavior-cloning run; test opens only after checkpoint selection."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import shutil
import subprocess
from pathlib import Path

import numpy as np
import torch

from manamind.cards.catalog import CardCatalog
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.policy import PolicyNetwork
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint
from manamind.training.policy_metrics import concentration, diagnostics, evaluate, uniform_metrics
from manamind.training.real_policy import audit_dataset, encode_example, load_examples, split_matches

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def freeze_split(rows, seed, previous_seed):
    """Old published smoke-test matches are forced into train, before any fitting."""
    rows = sorted(rows, key=lambda r: r["decision_id"])
    old_test = {r["game_id"] for r in split_matches(rows, previous_seed)["test"]}
    parts = split_matches(rows, seed)
    games = {k: {r["game_id"] for r in rs} for k, rs in parts.items()}
    outcomes = {r["game_id"]: r["final_result"] for r in rows}
    for name in ("validation", "test"):
        for game in sorted(games[name] & old_test):
            candidates = [g for g in games["train"] if g not in old_test and outcomes[g] == outcomes[game]]
            if not candidates:
                raise ValueError("Cannot isolate previous smoke test preserving outcome balance")
            replacement = min(candidates, key=lambda g: hashlib.sha256(f"{seed}:{g}".encode()).hexdigest())
            games[name].remove(game)
            games[name].add(replacement)
            games["train"].remove(replacement)
            games["train"].add(game)
    if not old_test <= games["train"]:
        raise ValueError("Published smoke-test matches must stay in train")
    return {k: [r for r in rows if r["game_id"] in ids] for k, ids in games.items()}, sorted(old_test)


def validate_config(config):
    expected = {"seed", "split_seed", "hidden_size", "learning_rate", "weight_decay", "batch_size",
                "max_epochs", "patience", "min_delta", "gradient_clip", "torch_threads", "device",
                "previous_smoke_split_seed"}
    if config.get("representation") == 2:
        expected.update({"representation", "dropout"})
        if type(config.get("dropout")) not in (int, float) or not 0 <= config["dropout"] < 1:
            raise ValueError("Invalid dropout")
    if set(config) != expected or config["device"] != "cpu" or config["torch_threads"] != 1:
        raise ValueError("Baseline requires explicit bounded deterministic CPU config")
    for key in ("seed", "split_seed", "previous_smoke_split_seed"):
        if type(config[key]) is not int or config[key] < 0:
            raise ValueError(f"Invalid {key}")
    for key, maximum in (("max_epochs", 200), ("patience", 200), ("batch_size", 128), ("hidden_size", 128)):
        if type(config[key]) is not int or not 1 <= config[key] <= maximum:
            raise ValueError(f"Invalid bounded {key}")
    for key in ("learning_rate", "gradient_clip", "weight_decay", "min_delta"):
        if type(config[key]) not in (int, float) or not np.isfinite(config[key]) or config[key] < 0:
            raise ValueError(f"Invalid {key}")
    if config["learning_rate"] == 0 or config["gradient_clip"] == 0:
        raise ValueError("Learning rate and gradient clip must be positive")


def run(directory: Path, cards: Path, output: Path, config: dict, *, baseline_checkpoint: Path | None = None) -> dict:
    validate_config(config)
    catalog = CardCatalog.from_json(cards)
    audit = audit_dataset(directory, catalog)
    rows = sorted(load_examples(directory), key=lambda r: r["decision_id"])
    parts, old_test = freeze_split(rows, config["split_seed"], config["previous_smoke_split_seed"])
    dataset_sha = identity(rows)
    split = {"algorithm": "ML1B_outcome_hash_split_with_published_smoke_test_forced_to_train/1",
             "seed": config["split_seed"], "previous_smoke_split_seed": config["previous_smoke_split_seed"],
             "published_smoke_test_game_ids": old_test, "dataset_sha256": dataset_sha,
             "game_ids": {k: sorted({r["game_id"] for r in rs}) for k, rs in parts.items()},
             "decision_ids": {k: [r["decision_id"] for r in rs] for k, rs in parts.items()}}
    representation = config.get("representation", 1)
    reference = None
    if representation == 2:
        if baseline_checkpoint is None:
            raise ValueError("Policy v2 requires an explicit frozen v1 checkpoint")
        reference, reference_encoder, reference_payload = load_policy_checkpoint(baseline_checkpoint)
        if not isinstance(reference, PolicyNetwork):
            raise ValueError("Comparison reference must be policy v1")
        experiment = reference_payload["experiment"]
        if (experiment["dataset_sha256"] != dataset_sha or experiment["split"] != split
                or identity(catalog.to_dict()) != reference_payload["catalog_sha256"]):
            raise ValueError("V1/v2 data, catalog or frozen split identity mismatch")
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "dataset"
    snapshot.mkdir()
    for path in sorted(directory.iterdir()):
        if path.suffix == ".jsonl" or path.name.endswith(".audit.json"):
            shutil.copyfile(path, snapshot / path.name)
    if identity(sorted(load_examples(snapshot), key=lambda r: r["decision_id"])) != dataset_sha:
        raise ValueError("Dataset changed during snapshot creation")
    if audit_dataset(snapshot, catalog) != audit:
        raise ValueError("Audit changed during snapshot creation")
    source_paths = [ROOT / p for p in (
        "scripts/train_real_policy.py", "src/manamind/training/real_policy.py",
        "src/manamind/training/policy_checkpoint.py", "src/manamind/training/policy_metrics.py",
        "src/manamind/models/policy.py", "src/manamind/encoding/state_encoder.py",
        "src/manamind/integrations/powerlog/policy_import.py")]
    if representation == 2:
        source_paths.extend(ROOT / p for p in ("src/manamind/models/policy_v2.py",
                                              "src/manamind/models/policy_inputs.py"))
    metadata = {"dataset_sha256": dataset_sha, "split": split, "split_sha256": identity(split),
                "config": config, "config_sha256": identity(config),
                "base_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in source_paths},
                "runtime": {"python": __import__("sys").version, "torch": str(torch.__version__),
                            "numpy": np.__version__},
                "selection": "minimum_validation_cross_entropy_with_min_delta", "strength_claim": False}
    if reference is not None:
        metadata["v1_reference_sha256"] = hashlib.sha256(Path(baseline_checkpoint).read_bytes()).hexdigest()
    write_json(output / "frozen_experiment.json", metadata)
    write_json(output / "audit.json", audit)
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.set_num_threads(config["torch_threads"])
    torch.use_deterministic_algorithms(True)
    encoder = StateEncoder(catalog)
    if representation == 2:
        contract = feature_contract(encoder)
        policy = PolicyNetworkV2(card_count=encoder.vocabulary.card_count,
                                 state_feature_count=len(contract["state_feature_names"]),
                                 entity_feature_count=len(contract["entity_feature_names"]),
                                 hidden_size=config["hidden_size"], dropout=config["dropout"])
    else:
        policy = PolicyNetwork(card_count=encoder.vocabulary.card_count, hidden_size=config["hidden_size"])
    optimizer = torch.optim.AdamW(policy.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    train = [(encode_example(r, encoder, representation=representation), r["chosen_action_index"])
             for r in parts["train"]]
    rng = random.Random(config["seed"])
    initial_validation, _ = evaluate(policy, parts["validation"], encoder)
    history, best, best_epoch, best_weights, stale = [], float("inf"), 0, None, 0
    for epoch in range(1, config["max_epochs"] + 1):
        policy.train()
        order = list(range(len(train)))
        rng.shuffle(order)
        loss_sum = 0.0
        for start in range(0, len(order), config["batch_size"]):
            indices = order[start:start+config["batch_size"]]
            losses = [torch.nn.functional.cross_entropy(policy(*train[i][0])[None],
                       torch.tensor([train[i][1]])) for i in indices]
            loss = torch.stack(losses).mean()
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), config["gradient_clip"], error_if_nonfinite=True)
            optimizer.step()
            loss_sum += loss.item() * len(indices)
        validation, _ = evaluate(policy, parts["validation"], encoder)
        train_metrics, _ = evaluate(policy, parts["train"], encoder)
        history.append({"epoch": epoch, "optimization_loss": loss_sum / len(train),
                        "train": train_metrics, "validation": validation})
        improved = validation["cross_entropy"] < best - config["min_delta"]
        if improved:
            best, best_epoch, best_weights, stale = validation["cross_entropy"], epoch, copy.deepcopy(policy.state_dict()), 0
        else:
            stale += 1
        print(json.dumps({"epoch": epoch, "train_ce": train_metrics["cross_entropy"],
                          "validation_ce": validation["cross_entropy"], "best_epoch": best_epoch}), flush=True)
        if stale >= config["patience"]:
            break
    policy.load_state_dict(best_weights)
    metadata["selected_epoch"] = best_epoch
    metadata["epochs_run"] = len(history)
    write_json(output / "history.json", {"initial_validation": initial_validation, "epochs": history})
    checkpoint = output / "policy.pt"
    save_policy_checkpoint(checkpoint, policy, encoder, metadata)
    restored, saved_encoder, _ = load_policy_checkpoint(checkpoint)
    if not all(torch.equal(t, restored.state_dict()[k]) for k, t in policy.state_dict().items()):
        raise ValueError("Checkpoint weight round-trip mismatch")
    # Test labels are first used for metrics here, after all training choices and saving.
    results, details = {}, {}
    for name, rs in parts.items():
        learned, records = evaluate(restored, rs, saved_encoder)
        results[name] = {"learned": learned, "uniform_random_expected": uniform_metrics(rs)}
        details[name] = {"diagnostics": diagnostics(records), "concentration": concentration(rs)}
        if reference is not None:
            metrics, reference_records = evaluate(reference, rs, reference_encoder)
            results[name]["frozen_v1"] = metrics
            details[name]["v1_diagnostics"] = diagnostics(reference_records)
    result = {"selected_epoch": best_epoch, "epochs_run": len(history), "metrics": results,
              "dataset_sha256": dataset_sha, "split_sha256": identity(split),
              "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(), "strength_claim": False}
    write_json(output / "metrics.json", result)
    write_json(output / "diagnostics.json", details)
    # Exact logit round-trip, independent of ranking ties.
    probe = encode_example(parts["validation"][0], encoder, representation=representation)
    with torch.no_grad():
        if not torch.equal(policy(*probe), restored(*probe)):
            raise ValueError("Checkpoint logit round-trip mismatch")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/real_policy_ml1c.json")
    parser.add_argument("--baseline-checkpoint", type=Path, help="V2 requires the frozen ML-1C v1 reference")
    args = parser.parse_args()
    try:
        result = run(args.directory, args.cards, args.output, json.loads(args.config.read_text(encoding="utf-8-sig")),
                     baseline_checkpoint=args.baseline_checkpoint)
    except Exception as error:
        print(json.dumps({"result": "FAILED", "reason": type(error).__name__}), flush=True)
        return 1
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
