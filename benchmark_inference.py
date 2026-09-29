"""Measure value-model inference latency for a sample state and a batch."""

import argparse
import json
import statistics
import time
from pathlib import Path

from manamind.cards import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.encoding import StateEncoder
from manamind.inference import predict_win_probabilities
from manamind.training.checkpoint import load_checkpoint
from manamind.training.trainer import select_device

ROOT = Path(__file__).parent


def _sync(device) -> None:
    if device.type == "cuda":
        import torch
        torch.cuda.synchronize(device)


def _measure(states, encoder, model, device, repeats: int) -> list[float]:
    timings = []
    for _ in range(repeats):
        _sync(device)
        start = time.perf_counter()
        predict_win_probabilities(states, encoder, model)
        _sync(device)
        timings.append((time.perf_counter() - start) * 1000)
    return timings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=ROOT / "data" / "samples" / "example_state.json")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "checkpoints" / "value_v1_s4.pt")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args()
    if args.batch_size < 1 or args.repeats < 1:
        parser.error("--batch-size and --repeats must be positive")

    device = select_device()
    model, vocabulary, payload = load_checkpoint(args.checkpoint, device)
    catalog = CardCatalog.from_dict(payload["catalog"])
    encoder = StateEncoder(catalog, vocabulary)
    with args.state.open("r", encoding="utf-8-sig") as file:
        state = game_state_from_dict(json.load(file))

    single = [state]
    batch = [state] * args.batch_size
    predict_win_probabilities(single, encoder, model)  # warmup
    predict_win_probabilities(batch, encoder, model)
    for label, states in (("single", single), (f"batch-{len(batch)}", batch)):
        timings = _measure(states, encoder, model, device, args.repeats)
        print(f"{label}: median {statistics.median(timings):.3f} ms | mean {statistics.mean(timings):.3f} ms")


if __name__ == "__main__":
    main()
