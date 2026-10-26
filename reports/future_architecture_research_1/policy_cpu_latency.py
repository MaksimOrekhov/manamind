"""Read-only CPU latency of frozen Policy v2 / v3 per decision (encode + forward). No training, no writes."""
import sys, time, statistics, glob, os
from pathlib import Path
sys.path.insert(0, "src")
import torch
torch.set_num_threads(1)
from manamind.training.policy_checkpoint import load_policy_checkpoint
from manamind.models.policy_inputs import representation_of
from manamind.training.real_policy import load_examples, encode_example

cands = [d for d in ["data/processed_policy_real", "data/processed_new_matches_eval_2"] if os.path.isdir(d)]
rows = None
for d in cands:
    for sub in [d] + sorted(glob.glob(d + "/*")):
        try:
            r = load_examples(Path(sub))
            if r: rows = r; src = sub; break
        except Exception as e:
            continue
    if rows: break
print("examples from", src, len(rows))
rows = rows[:200]
for name, path in [("v2", "data/processed_policy_ml2a/seed42_v2/policy.pt"),
                   ("v3", "data/processed_policy_v3/experiment_1/final/architecturev3_seed42/policy.pt")]:
    if not os.path.exists(path): print(name, "missing"); continue
    policy, encoder, ckpt = load_policy_checkpoint(Path(path), device="cpu"); policy.eval()
    rep = representation_of(policy)
    enc_t, fwd_t, n_actions = [], [], []
    with torch.inference_mode():
        for row in rows:
            t0 = time.perf_counter()
            inputs = encode_example(row, encoder, representation=rep)
            t1 = time.perf_counter()
            x = inputs
            try:
                out = policy(*x)
            except TypeError:
                out = policy(*inputs)
            t2 = time.perf_counter()
            enc_t.append((t1-t0)*1e3); fwd_t.append((t2-t1)*1e3)
    print(f"{name}: encode median {statistics.median(enc_t):.2f} ms, forward median {statistics.median(fwd_t):.2f} ms, p95 fwd {sorted(fwd_t)[int(.95*len(fwd_t))]:.2f} ms (1 thread, n={len(rows)})")
