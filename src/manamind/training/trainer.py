"""A straightforward PyTorch training loop for the first value model."""

import copy
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

from manamind.cards.vocabulary import CardVocabulary
from manamind.encoding.batch import collate_encoded_states
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.value_network import ValueNetwork
from manamind.training.checkpoint import save_checkpoint
from manamind.training.metrics import binary_metrics
from manamind.training.synthetic import LabeledState


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    batch_size: int = 128
    learning_rate: float = 0.0003
    epochs: int = 20
    weight_decay: float = 0.0001
    seed: int = 42


def select_device() -> torch.device:
    """Prefer CUDA, then MPS, with CPU always available as a fallback."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _encode_examples(examples: list[LabeledState], encoder: StateEncoder):
    return [(encoder.encode(example.state), example.target) for example in examples]


def evaluate(
    model: ValueNetwork,
    examples: list[tuple],
    batch_size: int,
    device: torch.device,
) -> dict[str, float]:
    if not examples:
        raise ValueError("Cannot evaluate an empty dataset split")

    was_training = model.training
    model.eval()
    loss_function = nn.BCEWithLogitsLoss(reduction="sum")
    total_loss = 0.0
    all_targets: list[float] = []
    all_probabilities: list[float] = []

    with torch.inference_mode():
        for start in range(0, len(examples), batch_size):
            chunk = examples[start : start + batch_size]
            states = [item[0] for item in chunk]
            targets = torch.tensor(
                [item[1] for item in chunk], dtype=torch.float32, device=device
            )
            batch = collate_encoded_states(states, device=device)
            logits = model(batch)
            probabilities = torch.sigmoid(logits)
            total_loss += float(loss_function(logits, targets).item())
            all_targets.extend(targets.cpu().tolist())
            all_probabilities.extend(probabilities.cpu().tolist())

    model.train(was_training)
    metrics = binary_metrics(np.asarray(all_targets), np.asarray(all_probabilities))
    metrics["loss"] = total_loss / len(examples)
    return metrics


def train_value_network(
    model: ValueNetwork,
    vocabulary: CardVocabulary,
    encoder: StateEncoder,
    training_examples: list[LabeledState],
    validation_examples: list[LabeledState],
    config: TrainingConfig,
    checkpoint_path: str | Path,
    device: torch.device | None = None,
) -> tuple[ValueNetwork, list[dict[str, float]]]:
    if not training_examples or not validation_examples:
        raise ValueError("Training and validation splits must both contain examples")
    if config.epochs < 1 or config.batch_size < 1:
        raise ValueError("epochs and batch_size must be positive")

    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)

    selected_device = device or select_device()
    model.to(selected_device)
    train_encoded = _encode_examples(training_examples, encoder)
    validation_encoded = _encode_examples(validation_examples, encoder)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    loss_function = nn.BCEWithLogitsLoss()
    best_validation_loss = float("inf")
    best_state = copy.deepcopy(model.state_dict())
    history: list[dict[str, float]] = []

    for epoch in range(1, config.epochs + 1):
        model.train()
        order = torch.randperm(len(train_encoded)).tolist()
        total_loss = 0.0

        for start in range(0, len(order), config.batch_size):
            indices = order[start : start + config.batch_size]
            chunk = [train_encoded[index] for index in indices]
            batch = collate_encoded_states([item[0] for item in chunk], device=selected_device)
            targets = torch.tensor(
                [item[1] for item in chunk], dtype=torch.float32, device=selected_device
            )

            optimizer.zero_grad(set_to_none=True)
            logits = model(batch)
            loss = loss_function(logits, targets)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach().item()) * len(chunk)

        train_loss = total_loss / len(train_encoded)
        validation_metrics = evaluate(
            model, validation_encoded, config.batch_size, selected_device
        )
        epoch_metrics = {"epoch": float(epoch), "train_loss": train_loss, **validation_metrics}
        history.append(epoch_metrics)

        print(
            f"Epoch {epoch:02d}/{config.epochs} | "
            f"train loss {train_loss:.4f} | val loss {validation_metrics['loss']:.4f} | "
            f"accuracy {_format_metric(validation_metrics['accuracy'])} | "
            f"roc_auc {_format_metric(validation_metrics['roc_auc'])} | "
            f"brier {validation_metrics['brier']:.3f}"
        )

        if validation_metrics["loss"] < best_validation_loss:
            best_validation_loss = validation_metrics["loss"]
            best_state = copy.deepcopy(model.state_dict())
            save_checkpoint(
                checkpoint_path,
                model,
                vocabulary,
                epoch,
                validation_metrics,
                catalog=encoder.catalog,
            )
            print(f"  Best checkpoint saved: {checkpoint_path}")

    model.load_state_dict(best_state)
    return model, history


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"
