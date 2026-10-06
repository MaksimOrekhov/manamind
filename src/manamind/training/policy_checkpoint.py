"""Strict, simulator-independent checkpoint contract for the real policy baseline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch

from manamind.cards.catalog import CardCatalog
from manamind.cards.vocabulary import CardVocabulary
from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION, StateEncoder
from manamind.models.policy import (
    ACTION_FEATURE_NAMES, CARD_EMBEDDING_DIM, MAX_HAND_SIZE, POLICY_ACTION_SCHEMA_VERSION,
    POLICY_STATE_FEATURE_NAMES, PolicyNetwork,
)

FORMAT = "manamind.real_policy_baseline/1"
NORMALIZATION = "signed_log1p_clip_10000"


def identity(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def compatibility() -> dict:
    return {"schema": FORMAT, "state_encoding_schema_version": STATE_ENCODING_SCHEMA_VERSION,
            "policy_action_schema_version": POLICY_ACTION_SCHEMA_VERSION,
            "real_policy_dataset_schema_version": 1, "semantic_action_schema_version": 1,
            "state_feature_names": list(POLICY_STATE_FEATURE_NAMES),
            "action_feature_names": list(ACTION_FEATURE_NAMES), "normalization": NORMALIZATION}


def save_policy_checkpoint(path: Path, policy, encoder, metadata: dict) -> None:
    catalog, vocabulary = encoder.catalog.to_dict(), encoder.vocabulary.to_dict()
    payload = {**compatibility(), "card_catalog": catalog, "card_vocabulary": vocabulary,
               "catalog_sha256": identity(catalog), "vocabulary_sha256": identity(vocabulary),
               "model_config": {"architecture": "PolicyNetwork", "hidden_size": policy.scorer[0].out_features,
                                "card_count": encoder.vocabulary.card_count,
                                "state_feature_count": len(POLICY_STATE_FEATURE_NAMES),
                                "card_embedding_dim": CARD_EMBEDDING_DIM, "max_hand_size": MAX_HAND_SIZE},
               "policy_state_dict": policy.state_dict(), "experiment": metadata}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        torch.save(payload, stream)


def load_policy_checkpoint(path: Path, device="cpu") -> tuple:
    payload = torch.load(path, map_location=device, weights_only=True)
    for key, expected in compatibility().items():
        if payload.get(key) != expected:
            raise ValueError(f"Incompatible real policy checkpoint: {key}")
    for name, key in (("catalog", "card_catalog"), ("vocabulary", "card_vocabulary")):
        if identity(payload.get(key)) != payload.get(f"{name}_sha256"):
            raise ValueError(f"Checkpoint {name} identity mismatch")
    catalog = CardCatalog.from_dict(payload["card_catalog"])
    vocabulary = CardVocabulary.from_dict(payload["card_vocabulary"])
    if (catalog.to_dict() != payload["card_catalog"]
            or CardVocabulary(catalog).to_dict() != vocabulary.to_dict()):
        raise ValueError("Checkpoint catalog/vocabulary mapping is incompatible")
    config = payload.get("model_config", {})
    expected = {"architecture": "PolicyNetwork", "card_count": vocabulary.card_count,
                "state_feature_count": len(POLICY_STATE_FEATURE_NAMES),
                "card_embedding_dim": CARD_EMBEDDING_DIM, "max_hand_size": MAX_HAND_SIZE}
    if (set(config) != {*expected, "hidden_size"}
            or any(config.get(k) != v for k, v in expected.items())
            or type(config.get("hidden_size")) is not int or config["hidden_size"] <= 0):
        raise ValueError("Incompatible policy model config")
    experiment = payload.get("experiment", {})
    split = experiment.get("split", {})
    parts = split.get("game_ids", {})
    if (set(parts) != {"train", "validation", "test"}
            or any(not isinstance(v, list) or not v or len(v) != len(set(v)) for v in parts.values())
            or set(parts["train"]) & set(parts["validation"])
            or set(parts["train"]) & set(parts["test"])
            or set(parts["validation"]) & set(parts["test"])
            or identity(split) != experiment.get("split_sha256")
            or split.get("dataset_sha256") != experiment.get("dataset_sha256")
            or not isinstance(experiment.get("config"), dict)
            or identity(experiment["config"]) != experiment.get("config_sha256")):
        raise ValueError("Invalid policy training/split identity")
    policy = PolicyNetwork(card_count=vocabulary.card_count, hidden_size=config["hidden_size"]).to(device)
    try:
        policy.load_state_dict(payload["policy_state_dict"], strict=True)
    except (KeyError, RuntimeError) as error:
        raise ValueError("Incompatible policy weight shapes") from error
    if not all(torch.isfinite(t).all() for t in policy.state_dict().values()):
        raise ValueError("Nonfinite policy weights")
    policy.eval()
    return policy, StateEncoder(catalog, vocabulary), payload
