"""Save and restore a value network together with its exact vocabulary."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from manamind.cards.catalog import CardCatalog
from manamind.cards.vocabulary import CardVocabulary
from manamind.encoding.entity_encoder import (
    NORMALIZATION_CONFIG,
    NUMERIC_FEATURES,
    PRESENCE_FEATURES,
    STATE_FLAG_NAMES,
)
from manamind.encoding.state_encoder import (
    GLOBAL_FEATURE_NAMES,
    STATE_ENCODING_SCHEMA_VERSION,
)
from manamind.models.value_network import ValueNetwork, ValueNetworkConfig


def save_checkpoint(
    path: str | Path,
    model: ValueNetwork,
    vocabulary: CardVocabulary,
    epoch: int,
    validation_metrics: dict[str, float],
    catalog: CardCatalog,
) -> None:
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "format_version": 2,
            "model_version": "value_v1",
            "state_encoding_schema_version": STATE_ENCODING_SCHEMA_VERSION,
            "global_feature_names": list(GLOBAL_FEATURE_NAMES),
            "numeric_feature_names": list(NUMERIC_FEATURES),
            "presence_feature_names": list(PRESENCE_FEATURES),
            "state_flag_names": list(STATE_FLAG_NAMES),
            "normalization": NORMALIZATION_CONFIG,
            "model_config": asdict(model.config),
            "vocabulary": vocabulary.to_dict(),
            "catalog": catalog.to_dict(),
            "model_state_dict": model.state_dict(),
            "epoch": epoch,
            "validation_metrics": validation_metrics,
        },
        checkpoint_path,
    )


def load_checkpoint(
    path: str | Path,
    device: torch.device | str = "cpu",
) -> tuple[ValueNetwork, CardVocabulary, dict[str, Any]]:
    payload = torch.load(path, map_location=device, weights_only=True)
    if payload.get("format_version") != 2:
        raise ValueError(
            "Unsupported checkpoint format; this model uses an older feature schema. "
            "Retrain with the current code to create a compatible checkpoint."
        )
    expected = {
        "state_encoding_schema_version": STATE_ENCODING_SCHEMA_VERSION,
        "global_feature_names": list(GLOBAL_FEATURE_NAMES),
        "numeric_feature_names": list(NUMERIC_FEATURES),
        "presence_feature_names": list(PRESENCE_FEATURES),
        "state_flag_names": list(STATE_FLAG_NAMES),
        "normalization": NORMALIZATION_CONFIG,
    }
    for name, value in expected.items():
        if payload.get(name) != value:
            raise ValueError(f"Checkpoint {name} does not match current encoder; retraining is required")

    vocabulary = CardVocabulary.from_dict(payload["vocabulary"])
    config = ValueNetworkConfig(**payload["model_config"])
    model = ValueNetwork(vocabulary, config)
    model.load_state_dict(payload["model_state_dict"])
    model.to(device)
    model.eval()
    return model, vocabulary, payload
