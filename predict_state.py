"""Load a trained checkpoint and estimate P(SELF wins) for a GameState JSON."""

import argparse
import json
from pathlib import Path

from manamind.cards import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.encoding import StateEncoder
from manamind.inference import predict_game_states
from manamind.training.checkpoint import load_checkpoint
from manamind.training.trainer import select_device

ROOT = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path, help="Path to a JSON GameState")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "checkpoints" / "value_v1_s4.pt")
    parser.add_argument("--cards", type=Path, default=None,
                        help="Optional additional catalog for previously unseen card IDs")
    args = parser.parse_args()

    device = select_device()
    model, vocabulary, checkpoint = load_checkpoint(args.checkpoint, device=device)
    catalog = CardCatalog.from_dict(checkpoint["catalog"])
    if args.cards:
        catalog = catalog.merged(CardCatalog.from_json(args.cards))
    encoder = StateEncoder(catalog, vocabulary=vocabulary)
    with args.state.open("r", encoding="utf-8-sig") as file:
        state = game_state_from_dict(json.load(file))
    result = predict_game_states([state], encoder, model)[0]

    print(f"Checkpoint epoch: {checkpoint['epoch']}")
    print(f"Device: {device}")
    print(f"P(SELF wins): {result.win_probability:.3f}")
    print(f"Model version: {result.model_version}")
    if result.unknown_cards:
        print("Unknown card IDs: " + ", ".join(result.unknown_cards))
    print("This checkpoint was trained on synthetic data; treat this as a pipeline demo.")


if __name__ == "__main__":
    main()
