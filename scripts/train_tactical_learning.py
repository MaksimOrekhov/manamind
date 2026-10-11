"""Exactly two matched candidates; sealed control is never read by this script."""
from __future__ import annotations

import argparse
import copy
import json
import os
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import torch  # noqa: E402

from manamind.training.policy_checkpoint import identity, load_policy_checkpoint, save_policy_checkpoint
from manamind.training.tactical_learning import Stream, compact, encode_rows, evaluate, read_rows, real_parts
from manamind.training.tactical_certificates import set_loss

from prepare_tactical_learning import INITIAL, INITIAL_SHA, ROOT, sha, write


def run(dataset, output):
    if (dataset/"INVALIDATED.json").exists():
        raise ValueError("Tactical dataset explicitly invalidated; no training permitted")
    manifest = json.loads((dataset/"manifest.json").read_text())
    cfg = manifest["config"]
    if (sha(INITIAL) != INITIAL_SHA or identity(cfg) != manifest["config_sha256"]
            or cfg["seed"] != 42 or cfg["max_epochs"] > 12 or cfg["seconds_per_candidate"] > 600
            or not torch.cuda.is_available()):
        raise ValueError("Frozen protocol/runtime mismatch")
    for part in ("train", "validation"):
        if sha(dataset/f"{part}.jsonl") != manifest["files"][part]:
            raise ValueError("Tactical split changed")
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    policies, optimizers = {}, {}
    for name in ("A", "B"):
        policies[name], encoder, payload = load_policy_checkpoint(INITIAL, device=cfg["device"])
        optimizers[name] = torch.optim.AdamW(policies[name].parameters(), lr=cfg["learning_rate"],
                                           weight_decay=cfg["weight_decay"])
    if any(not torch.equal(policies["A"].state_dict()[k], v) for k, v in policies["B"].state_dict().items()):
        raise ValueError("Initial weights differ")
    original = {k: v.cpu().clone() for k, v in policies["A"].state_dict().items()}
    split = payload["experiment"]["split"]
    real = real_parts(ROOT/"data/processed_policy_real/real_policy_retrain_1", split)
    tactical = {p: read_rows(dataset/f"{p}.jsonl") for p in ("train", "validation")}
    enc_real = {p: encode_rows(rs, encoder, cfg["device"]) for p, rs in real.items()}
    enc_tactic = {p: encode_rows(rs, encoder, cfg["device"]) for p, rs in tactical.items()}
    initial_validation = compact(evaluate(policies["A"], real["validation"], enc_real["validation"]))
    initial_tactical = compact(evaluate(policies["A"], tactical["validation"], enc_tactic["validation"]))
    streams = {n: Stream(len(real["train"]), cfg["seed"]) for n in policies}
    tactic_stream = Stream(len(tactical["train"]), cfg["seed"])
    histories = {n: [] for n in policies}
    best, guarded, stale, seconds = {}, {}, {n: 0 for n in policies}, {n: 0.0 for n in policies}
    frozen = {"dataset_manifest_sha256": sha(dataset/"manifest.json"), "initial_sha256": INITIAL_SHA,
              "config": cfg, "config_sha256": identity(cfg), "real_split_sha256": identity(split),
              "real_input_sha256": {part: identity(real[part]) for part in real},
              "source_sha256": {p: sha(ROOT/p) for p in ["scripts/train_tactical_learning.py",
                  "src/manamind/training/tactical_learning.py", "src/manamind/training/tactical_certificates.py"]},
              "initial_validation": initial_validation, "initial_tactical_validation": initial_tactical,
              "runtime": {"torch": str(torch.__version__), "gpu": torch.cuda.get_device_name(0)}}
    write(output/"protocol.json", frozen)
    for epoch in range(1, cfg["max_epochs"]+1):
        for name, policy in policies.items():
            started = time.perf_counter()
            policy.train()
            loss_sum, seen_real, seen_tactical = 0.0, set(), set()
            for step in range(cfg["steps_per_epoch"]):
                torch.manual_seed(cfg["seed"]+epoch*1000+step)
                k = cfg["tactical_counts_cycle"][step % len(cfg["tactical_counts_cycle"])] if name == "B" else 0
                real_indices = streams[name].take(cfg["batch_size"]-k)
                tactic_indices = tactic_stream.take(k)
                batch = [enc_real["train"][i] for i in real_indices]+[enc_tactic["train"][i] for i in tactic_indices]
                seen_real.update(real_indices)
                seen_tactical.update(tactic_indices)
                loss = torch.stack([set_loss(policy(*inputs), gold) for inputs, gold in batch]).mean()
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite loss")
                optimizers[name].zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(policy.parameters(), cfg["gradient_clip"], error_if_nonfinite=True)
                optimizers[name].step()
                loss_sum += loss.item()
            rv = compact(evaluate(policy, real["validation"], enc_real["validation"]))
            tv = compact(evaluate(policy, tactical["validation"], enc_tactic["validation"]))
            seconds[name] += time.perf_counter()-started
            row = {"epoch": epoch, "steps": cfg["steps_per_epoch"], "train_loss": loss_sum/cfg["steps_per_epoch"],
                   "real_validation": rv, "tactical_validation": tv, "seconds_total": seconds[name],
                   "real_examples_seen": len(seen_real), "tactical_examples_seen": len(seen_tactical),
                   "real_presentations": 1600 if name == "A" else 1280,
                   "tactical_presentations": 0 if name == "A" else 320}
            histories[name].append(row)
            ce = rv["overall"]["cross_entropy"]
            snapshot = (ce, epoch, copy.deepcopy(policy.state_dict()))
            if name not in best or ce < best[name][0]-1e-5:
                best[name], stale[name] = snapshot, 0
            else:
                stale[name] += 1
            guard_ok = tv["overall"]["correct"] >= initial_tactical["overall"]["correct"]-cfg["tactical_validation_maximum_correct_loss"]
            if guard_ok and (name not in guarded or ce < guarded[name][0]-1e-5):
                guarded[name] = snapshot
            print(json.dumps({"candidate": name, "epoch": epoch, "real_CE": round(ce, 5),
                              "tactical_correct": tv["overall"]["correct"], "seconds": round(seconds[name], 1)}), flush=True)
        if any(v >= cfg["patience"] for v in stale.values()) or any(v >= cfg["seconds_per_candidate"] for v in seconds.values()):
            break
    completed = {}
    for name, policy in policies.items():
        _, epoch, state = guarded.get(name, best[name])
        policy.load_state_dict(state)
        policy.cpu().eval()
        if all(torch.equal(original[k], v) for k, v in policy.state_dict().items()):
            raise ValueError("No parameter update")
        metadata = {**payload["experiment"], "config": cfg, "config_sha256": identity(cfg),
                    "source_checkpoint_sha256": INITIAL_SHA, "candidate": name, "selected_epoch": epoch,
                    "epochs_run": len(histories[name]), "optimizer_steps": len(histories[name])*cfg["steps_per_epoch"],
                    "tactical_manifest_sha256": sha(dataset/"manifest.json"), "training_seconds": seconds[name],
                    "selection_guard_passed": name in guarded, "strength_claim": False}
        destination = output/name
        save_policy_checkpoint(destination/"policy.pt", policy, encoder, metadata)
        restored, restored_encoder, _ = load_policy_checkpoint(destination/"policy.pt")
        probe = encode_rows(real["validation"][:3], encoder, "cpu")
        other = encode_rows(real["validation"][:3], restored_encoder, "cpu")
        with torch.inference_mode():
            if any(not torch.equal(policy(*a[0]), restored(*b[0])) for a, b in zip(probe, other, strict=True)):
                raise ValueError("Checkpoint reload changed logits")
        completed[name] = {"checkpoint_sha256": sha(destination/"policy.pt"), "selected_epoch": epoch,
                           "epochs_run": len(histories[name]), "optimizer_steps": metadata["optimizer_steps"],
                           "selection_guard_passed": name in guarded, "seconds": seconds[name]}
        write(destination/"history.json", histories[name])
    if sha(INITIAL) != INITIAL_SHA:
        raise ValueError("Initial checkpoint was modified")
    write(output/"TRAINING_COMPLETE.json", {"candidates": completed, "dataset_manifest_sha256": sha(dataset/"manifest.json")})
    return completed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.output), indent=2))
