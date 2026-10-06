"""One bounded supervised CPU update and checkpoint; no playing-strength claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from manamind.cards.catalog import CardCatalog
from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION, StateEncoder
from manamind.models.policy import (
    ACTION_FEATURE_NAMES, POLICY_ACTION_SCHEMA_VERSION, POLICY_STATE_FEATURE_NAMES, PolicyNetwork,
)
from manamind.training.real_policy import encode_example, evaluate_held_out, load_examples, split_matches


def smoke(directory: Path, cards: Path, checkpoint: Path, seed=1, max_decisions=8) -> dict:
    if checkpoint.exists():
        raise FileExistsError("Checkpoint already exists")
    if not 1 <= max_decisions <= 32:
        raise ValueError("Smoke is bounded to 1..32 decisions")
    torch.manual_seed(seed)
    catalog = CardCatalog.from_json(cards)
    encoder = StateEncoder(catalog)
    partitions = split_matches(load_examples(directory), seed)
    training_games = {row["game_id"] for row in partitions["train"]}
    policy = PolicyNetwork(card_count=encoder.vocabulary.card_count)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=0.0003)
    train = partitions["train"][:max_decisions]
    losses = [torch.nn.functional.cross_entropy(
        policy(*encode_example(row, encoder))[None], torch.tensor([row["chosen_action_index"]]))
        for row in train]
    loss = torch.stack(losses).mean()
    if not torch.isfinite(loss):
        raise ValueError("Nonfinite smoke loss")
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    metrics = evaluate_held_out(policy, partitions["test"], encoder, training_games)
    payload = {
        "schema": "manamind.real_policy_smoke/1", "policy_action_schema_version": POLICY_ACTION_SCHEMA_VERSION,
        "state_encoding_schema_version": STATE_ENCODING_SCHEMA_VERSION,
        "action_feature_names": list(ACTION_FEATURE_NAMES), "state_feature_names": list(POLICY_STATE_FEATURE_NAMES),
        "card_vocabulary": encoder.vocabulary.to_dict(), "card_catalog": catalog.to_dict(),
        "policy_state_dict": policy.state_dict(), "optimizer_state_dict": optimizer.state_dict(),
        "hidden_size": 128, "seed": seed, "max_decisions": max_decisions,
        "normalization": "signed_log1p_clip_10000", "training_game_ids": sorted(training_games),
    }
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint.open("xb") as stream:
        torch.save(payload, stream)
    reloaded = torch.load(checkpoint, map_location="cpu", weights_only=False)
    restored = PolicyNetwork(card_count=encoder.vocabulary.card_count)
    restored.load_state_dict(reloaded["policy_state_dict"])
    if not all(torch.equal(value, restored.state_dict()[key]) for key, value in policy.state_dict().items()):
        raise ValueError("Checkpoint did not reproduce smoke weights")
    return {"backward_and_checkpoint": "PASS", "updates": 1, "training_decisions": len(train),
            "training_loss": loss.item(), "held_out_test": metrics,
            "split_matches": {k: len({r["game_id"] for r in rows}) for k, rows in partitions.items()},
            "strength_claim": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--cards", type=Path, default=Path("data/cards/standard_current_enUS.json"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-decisions", type=int, default=8)
    args = parser.parse_args()
    try:
        result = smoke(args.directory, args.cards, args.checkpoint, args.seed, args.max_decisions)
    except Exception as error:
        print(json.dumps({"result": "FAILED", "reason": type(error).__name__}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
