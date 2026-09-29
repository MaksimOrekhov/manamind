"""Orchestrate synthetic data generation, training, and held-out evaluation."""

import json
import random
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from manamind.cards.catalog import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.encoding.state_encoder import StateEncoder
from manamind.inference.predictor import predict_win_probabilities
from manamind.models.value_network import ValueNetwork, ValueNetworkConfig
from manamind.training.metrics import binary_metrics
from manamind.training.split import split_dataset
from manamind.training.synthetic import (
    create_synthetic_catalog,
    generate_synthetic_dataset,
    load_labeled_dataset,
    save_synthetic_dataset,
)
from manamind.training.trainer import (
    TrainingConfig,
    _encode_examples,
    evaluate,
    select_device,
    train_value_network,
)


def _validate_game_disjoint_splits(train, validation, test) -> None:
    """Reject dataset files that leak one match across training and evaluation."""
    named_splits = {
        "train": train,
        "validation": validation,
        "test": test,
    }
    game_ids: dict[str, set[str]] = {}
    for name, examples in named_splits.items():
        ids = {example.game_id for example in examples}
        if any(not game_id.strip() or game_id == "None" for game_id in ids):
            raise ValueError(f"{name} split contains an example without game_id")
        game_ids[name] = ids

    split_names = tuple(named_splits)
    for index, left_name in enumerate(split_names):
        for right_name in split_names[index + 1:]:
            shared = game_ids[left_name] & game_ids[right_name]
            if shared:
                raise ValueError(
                    f"Dataset leakage: {len(shared)} game_id value(s) appear in "
                    f"both {left_name} and {right_name} splits"
                )


def load_training_config(path: str | Path) -> tuple[ValueNetworkConfig, TrainingConfig]:
    with Path(path).open("r", encoding="utf-8-sig") as file:
        raw_config: dict[str, Any] = yaml.safe_load(file)
    return (
        ValueNetworkConfig(**raw_config["model"]),
        TrainingConfig(**raw_config["training"]),
    )


def run_synthetic_training(
    project_root: str | Path,
    sample_count: int = 2048,
    config_path: str | Path | None = None,
    epochs: int | None = None,
    batch_size: int | None = None,
    seed: int | None = None,
    dataset_dir: str | Path | None = None,
    cards_path: str | Path | None = None,
    checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate fixed splits, train the network, and print test metrics."""
    root = Path(project_root)
    model_config, training_config = load_training_config(
        config_path or root / "configs" / "value_v1.yaml"
    )
    training_config = replace(
        training_config,
        epochs=epochs if epochs is not None else training_config.epochs,
        batch_size=batch_size if batch_size is not None else training_config.batch_size,
        seed=seed if seed is not None else training_config.seed,
    )

    if cards_path is not None:
        catalog_path = Path(cards_path)
    elif dataset_dir is not None and (root / "data" / "cards" / "standard_current_enUS.json").is_file():
        catalog_path = root / "data" / "cards" / "standard_current_enUS.json"
    else:
        catalog_path = root / "data" / "samples" / "sample_cards.json"
    base_catalog = CardCatalog.from_json(catalog_path)
    print(f"Card catalog: {catalog_path} ({len(base_catalog)} cards)")
    catalog = create_synthetic_catalog(base_catalog)
    if dataset_dir:
        dataset_path = Path(dataset_dir)
        train_examples = load_labeled_dataset(dataset_path / "train.jsonl")
        validation_examples = load_labeled_dataset(dataset_path / "validation.jsonl")
        test_examples = load_labeled_dataset(dataset_path / "test.jsonl")
        if any(
            example.source != "synthetic"
            for split in (train_examples, validation_examples, test_examples)
            for example in split
        ):
            catalog = base_catalog
        splits = type("LoadedSplits", (), {
            "train": train_examples, "validation": validation_examples, "test": test_examples
        })()
    else:
        examples = generate_synthetic_dataset(
            sample_count, card_catalog=catalog, seed=training_config.seed,
        )
        splits = split_dataset(examples, seed=training_config.seed)
        processed_path = root / "data" / "processed"
        save_synthetic_dataset(processed_path / "train.jsonl", splits.train)
        save_synthetic_dataset(processed_path / "validation.jsonl", splits.validation)
        save_synthetic_dataset(processed_path / "test.jsonl", splits.test)
    _validate_game_disjoint_splits(
        splits.train, splits.validation, splits.test,
    )
    print(
        f"Dataset: {len(splits.train)} train / {len(splits.validation)} validation / "
        f"{len(splits.test)} test examples"
    )

    random.seed(training_config.seed)
    np.random.seed(training_config.seed)
    torch.manual_seed(training_config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(training_config.seed)

    encoder = StateEncoder(catalog)
    model = ValueNetwork(encoder.vocabulary, model_config)
    device = select_device()
    print(f"Device: {device}")

    checkpoint_path = Path(checkpoint_path) if checkpoint_path else (
        root / "checkpoints" / "value_v1_s4.pt"
    )
    model, history = train_value_network(
        model=model,
        vocabulary=encoder.vocabulary,
        encoder=encoder,
        training_examples=splits.train,
        validation_examples=splits.validation,
        config=training_config,
        checkpoint_path=checkpoint_path,
        device=device,
    )

    test_encoded = _encode_examples(splits.test, encoder)
    test_metrics = evaluate(model, test_encoded, training_config.batch_size, device)
    test_targets = np.asarray([example.target for example in splits.test])
    constant_probability = float(np.mean([example.target for example in splits.train]))
    test_baseline = binary_metrics(
        test_targets,
        np.full(len(splits.test), constant_probability, dtype=np.float64),
    )
    global_baseline = _train_global_baseline(
        encoder, splits.train, splits.validation, splits.test, training_config, device
    )
    print(
        "Test: "
        f"loss {test_metrics['loss']:.4f} | accuracy {_format_metric(test_metrics['accuracy'])} | "
        f"roc_auc {_format_metric(test_metrics['roc_auc'])} | brier {test_metrics['brier']:.3f}"
    )
    print(
        f"Constant-prevalence baseline (P={constant_probability:.3f}): "
        f"accuracy {_format_metric(test_baseline['accuracy'])} | "
        f"roc_auc {_format_metric(test_baseline['roc_auc'])} | brier {test_baseline['brier']:.3f}"
    )
    print(
        "Global-features-only baseline: "
        f"loss {global_baseline['loss']:.4f} | "
        f"accuracy {_format_metric(global_baseline['accuracy'])} | "
        f"roc_auc {_format_metric(global_baseline['roc_auc'])} | "
        f"brier {global_baseline['brier']:.3f}"
    )

    with (root / "data" / "samples" / "example_state.json").open(
        "r", encoding="utf-8-sig"
    ) as file:
        sample_state = game_state_from_dict(json.load(file))
    probability = predict_win_probabilities([sample_state], encoder, model)[0]
    inference_source = "loaded dataset" if dataset_dir else "synthetic model"
    print(f"Example inference: P(SELF wins) = {probability:.3f} ({inference_source})")

    return {
        "model": model,
        "encoder": encoder,
        "history": history,
        "test_metrics": test_metrics,
        "baseline_metrics": test_baseline,
        "global_baseline_metrics": global_baseline,
        "checkpoint_path": checkpoint_path,
        "device": device,
    }


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _train_global_baseline(encoder, train, validation, test, config, device):
    """Train a small global-state-only model as a useful feature baseline."""
    model = torch.nn.Sequential(
        torch.nn.Linear(len(encoder.global_feature_names), 48),
        torch.nn.ReLU(),
        torch.nn.Linear(48, 1),
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    loss_function = torch.nn.BCEWithLogitsLoss()

    def tensors(examples):
        features = torch.as_tensor(
            np.stack([encoder.encode(item.state).global_features for item in examples]),
            dtype=torch.float32, device=device,
        )
        targets = torch.as_tensor([item.target for item in examples], dtype=torch.float32, device=device)
        return features, targets

    train_x, train_y = tensors(train)
    validation_x, validation_y = tensors(validation)
    test_x, test_y = tensors(test)
    best_state = None
    best_loss = float("inf")
    rng = torch.Generator().manual_seed(config.seed)
    for _ in range(config.epochs):
        model.train()
        order = torch.randperm(len(train), generator=rng)
        for start in range(0, len(train), config.batch_size):
            indices = order[start:start + config.batch_size].to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_function(model(train_x[indices]).squeeze(-1), train_y[indices])
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            validation_loss = float(loss_function(model(validation_x).squeeze(-1), validation_y))
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
    model.load_state_dict(best_state)
    model.eval()
    with torch.inference_mode():
        logits = model(test_x).squeeze(-1)
        probabilities = torch.sigmoid(logits)
        loss = float(loss_function(logits, test_y))
    metrics = binary_metrics(test_y.cpu().numpy(), probabilities.cpu().numpy())
    metrics["loss"] = loss
    return metrics
