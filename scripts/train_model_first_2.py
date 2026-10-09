"""Fine-tune a copy of the frozen Policy v2 checkpoint on local tactical labels."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch

from manamind.domain.serialization import game_state_from_dict
from manamind.models.policy_inputs import encode_policy_inputs
from manamind.models.policy_inputs import representation_of
from manamind.training.model_first_1_control import scenario_content_fingerprint, validate_no_control_overlap
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_policy_baseline import action_key, load_scenarios  # noqa: E402


def _labels(row):
    wanted = {action_key(a) for a in row["correct_actions"]}
    return [index for index, action in enumerate(row["legal_actions"]) if action_key(action) in wanted]


def _load_split(path: Path, expected: str):
    rows = load_scenarios(path)
    if any(row["split"] != expected or row["label_status"] != "LABELED" for row in rows):
        raise ValueError(f"{expected} file has a wrong split or an unlabeled scenario")
    if not rows:
        raise ValueError(f"{expected} split is empty")
    validate_no_control_overlap(rows)
    return rows


def _fingerprint(rows):
    return hashlib.sha256("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":"),
                                             ensure_ascii=True) for row in rows).encode()).hexdigest()


def _evaluate_loss(policy, rows, encoder, device):
    policy.eval()
    losses, top1, top3, reciprocal = [], [], [], []
    with torch.inference_mode():
        for row in rows:
            state = game_state_from_dict(row["state"])
            inputs = encode_policy_inputs(state, row["legal_actions"], encoder, representation=2, device=device)
            scores = policy(*inputs)
            labels = _labels(row)
            loss = torch.logsumexp(scores, dim=0) - torch.logsumexp(scores[labels], dim=0)
            losses.append(float(loss.item()))
            ranks = torch.argsort(scores, descending=True).tolist()
            label_set = set(labels)
            best_rank = min(ranks.index(index) + 1 for index in label_set)
            top1.append(best_rank == 1)
            top3.append(best_rank <= 3)
            reciprocal.append(1.0 / best_rank)
    return {"cross_entropy": float(np.mean(losses)), "top1": float(np.mean(top1)),
            "top3": float(np.mean(top3)), "mrr": float(np.mean(reciprocal)), "count": len(rows)}


def run(train_path: Path, validation_path: Path, baseline_path: Path, output: Path,
        *, seed: int = 42, max_epochs: int = 16, patience: int = 4, learning_rate: float = 0.0001,
        batch_size: int = 32, device: str = "cuda", expected_baseline_sha: str | None =
        "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"):
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA requested but unavailable")
    if max_epochs > 30 or max_epochs < 1 or patience < 1 or batch_size < 1:
        raise ValueError("Training budget outside configured bounds")
    train_rows, validation_rows = _load_split(train_path, "train"), _load_split(validation_path, "validation")
    if ({r["family_id"] for r in train_rows} & {r["family_id"] for r in validation_rows}
            or {r["template_id"] for r in train_rows} & {r["template_id"] for r in validation_rows}):
        raise ValueError("Family/template leakage between train and validation")
    train_fingerprints = {scenario_content_fingerprint(r) for r in train_rows}
    if train_fingerprints & {scenario_content_fingerprint(r) for r in validation_rows}:
        raise ValueError("Exact scenario overlap between train and validation")
    baseline_sha = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    if expected_baseline_sha is not None and baseline_sha != expected_baseline_sha:
        raise ValueError("Frozen source Policy v2 checkpoint SHA mismatch")
    policy, encoder, payload = load_policy_checkpoint(baseline_path, device=device)
    if representation_of(policy) != 2:
        raise ValueError("The source checkpoint is not Policy v2")
    initial_weights = copy.deepcopy(policy.state_dict())
    cfg = {"seed": seed, "max_epochs": max_epochs, "patience": patience,
           "learning_rate": learning_rate, "batch_size": batch_size, "device": device,
           "optimizer": "AdamW", "loss": "set_marginal_cross_entropy", "gradient_clip": 1.0}
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if device == "cuda":
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    torch.set_num_threads(1)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=learning_rate, weight_decay=0.001)
    encoded = []
    for row in train_rows:
        state = game_state_from_dict(row["state"])
        inputs = encode_policy_inputs(state, row["legal_actions"], encoder, representation=2, device=device)
        encoded.append((inputs, _labels(row)))
    initial_validation = _evaluate_loss(policy, validation_rows, encoder, device)
    rng = random.Random(seed)
    history, best_state, best_loss, best_epoch, stale = [], copy.deepcopy(policy.state_dict()), float("inf"), 0, 0
    started = time.perf_counter()
    for epoch in range(1, max_epochs + 1):
        policy.train()
        order = list(range(len(encoded)))
        rng.shuffle(order)
        loss_sum = 0.0
        for offset in range(0, len(order), batch_size):
            batch = order[offset:offset + batch_size]
            losses = []
            for index in batch:
                inputs, labels = encoded[index]
                scores = policy(*inputs)
                index_tensor = torch.tensor(labels, dtype=torch.long, device=device)
                losses.append(torch.logsumexp(scores, dim=0) - torch.logsumexp(scores[index_tensor], dim=0))
            loss = torch.stack(losses).mean()
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()
            loss_sum += float(loss.item()) * len(batch)
        validation = _evaluate_loss(policy, validation_rows, encoder, device)
        history.append({"epoch": epoch, "training_loss": loss_sum / len(encoded), "validation": validation})
        if validation["cross_entropy"] < best_loss - 1e-5:
            best_loss, best_epoch, best_state, stale = validation["cross_entropy"], epoch, copy.deepcopy(policy.state_dict()), 0
        else:
            stale += 1
        print(json.dumps({"epoch": epoch, "train_loss": round(loss_sum / len(encoded), 5),
                          "validation_loss": round(validation["cross_entropy"], 5), "best_epoch": best_epoch}), flush=True)
        if stale >= patience:
            break
    elapsed = time.perf_counter() - started
    if elapsed > 30 * 60:
        raise ValueError("Training exceeded the authorized 30-minute limit")
    policy.load_state_dict(best_state)
    if all(torch.equal(initial_weights[key], value) for key, value in policy.state_dict().items()):
        raise ValueError("Training produced no parameter change")
    split = {"algorithm": "MODEL_FIRST_2_preassigned_families_templates/1", "seed": seed,
             "dataset_sha256": hashlib.sha256((train_path.read_bytes() + validation_path.read_bytes())).hexdigest(),
             "game_ids": {"train": [r["scenario_id"] for r in train_rows],
                          "validation": [r["scenario_id"] for r in validation_rows],
                          "test": ["heldout-test-not-loaded-by-trainer"]}}
    experiment = {"base_sha": "3f49efd21e225ae76e6077ce362db3f3e45a1b68",
                  "source_checkpoint_sha256": baseline_sha,
                  "dataset_sha256": split["dataset_sha256"], "split": split,
                  "split_sha256": identity(split), "config": cfg, "config_sha256": identity(cfg),
                  "selection": "minimum validation set-marginal cross entropy; heldout test not read",
                  "selected_epoch": best_epoch, "epochs_run": len(history), "training_seconds": elapsed,
                  "runtime": {"python": sys.version, "torch": str(torch.__version__),
                              "numpy": np.__version__, "device_name": torch.cuda.get_device_name(0) if device == "cuda" else "CPU"},
                  "train_rows_sha256": _fingerprint(train_rows),
                  "validation_rows_sha256": _fingerprint(validation_rows), "strength_claim": False}
    output.mkdir(parents=True, exist_ok=False)
    save_policy_checkpoint(output / "policy.pt", policy, encoder, experiment)
    restored, restored_encoder, _ = load_policy_checkpoint(output / "policy.pt", device=device)
    for row in validation_rows[:4]:
        inputs = encode_policy_inputs(game_state_from_dict(row["state"]), row["legal_actions"], encoder,
                                      representation=2, device=device)
        other = encode_policy_inputs(game_state_from_dict(row["state"]), row["legal_actions"], restored_encoder,
                                     representation=2, device=device)
        with torch.inference_mode():
            if not torch.equal(policy(*inputs), restored(*other)):
                raise ValueError("Checkpoint logits changed on reload")
    report = {"config": cfg, "selected_epoch": best_epoch, "epochs_run": len(history),
              "training_seconds": elapsed, "initial_validation": initial_validation,
              "selected_validation": history[best_epoch - 1]["validation"], "history": history,
              "checkpoint_sha256": hashlib.sha256((output / "policy.pt").read_bytes()).hexdigest(),
              "source_checkpoint_sha256": baseline_sha, "train_count": len(train_rows),
              "validation_count": len(validation_rows), "strength_claim": False}
    (output / "training.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "history"}, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--epochs", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run(args.train, args.validation, args.baseline, args.output, max_epochs=args.epochs,
        seed=args.seed, device=args.device)


if __name__ == "__main__":
    main()
