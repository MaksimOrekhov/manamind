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
from manamind.models.policy_inputs import representation_of
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract

FORMAT = "manamind.real_policy_baseline/1"
FORMAT_V2 = "manamind.real_policy/2"
NORMALIZATION = "signed_log1p_clip_10000"


def identity(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def compatibility(encoder=None, representation=1) -> dict:
    result = {"schema": FORMAT, "state_encoding_schema_version": STATE_ENCODING_SCHEMA_VERSION,
            "policy_action_schema_version": POLICY_ACTION_SCHEMA_VERSION,
            "real_policy_dataset_schema_version": 1, "semantic_action_schema_version": 1,
            "state_feature_names": list(POLICY_STATE_FEATURE_NAMES),
            "action_feature_names": list(ACTION_FEATURE_NAMES), "normalization": NORMALIZATION}
    if representation == 2:
        result.update(feature_contract(encoder))
        result["schema"] = FORMAT_V2
    elif representation != 1:
        raise ValueError("Unsupported policy representation")
    return result


def model_config(policy, encoder) -> dict:
    if representation_of(policy) == 2:
        return {"architecture": "PolicyNetworkV2", "hidden_size": policy.hidden_size,
                "dropout": policy.dropout, "card_count": encoder.vocabulary.card_count,
                "state_feature_count": policy.state_feature_count,
                "entity_feature_count": policy.entity_feature_count, "card_embedding_dim": CARD_EMBEDDING_DIM}
    return {"architecture": "PolicyNetwork", "hidden_size": policy.scorer[0].out_features,
            "card_count": encoder.vocabulary.card_count, "state_feature_count": len(POLICY_STATE_FEATURE_NAMES),
            "card_embedding_dim": CARD_EMBEDDING_DIM, "max_hand_size": MAX_HAND_SIZE}


def save_policy_checkpoint(path: Path, policy, encoder, metadata: dict) -> None:
    catalog, vocabulary = encoder.catalog.to_dict(), encoder.vocabulary.to_dict()
    payload = {**compatibility(encoder, representation_of(policy)), "card_catalog": catalog, "card_vocabulary": vocabulary,
               "catalog_sha256": identity(catalog), "vocabulary_sha256": identity(vocabulary),
               "model_config": model_config(policy, encoder),
               "policy_state_dict": policy.state_dict(), "experiment": metadata}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        torch.save(payload, stream)


def load_policy_checkpoint(path: Path, device="cpu") -> tuple:
    payload = torch.load(path, map_location=device, weights_only=True)
    if not isinstance(payload, dict) or payload.get("schema") not in (FORMAT, FORMAT_V2):
        raise ValueError("Incompatible real policy checkpoint: schema")
    representation = 2 if payload["schema"] == FORMAT_V2 else 1
    for name, key in (("catalog", "card_catalog"), ("vocabulary", "card_vocabulary")):
        if identity(payload.get(key)) != payload.get(f"{name}_sha256"):
            raise ValueError(f"Checkpoint {name} identity mismatch")
    catalog = CardCatalog.from_dict(payload["card_catalog"])
    vocabulary = CardVocabulary.from_dict(payload["card_vocabulary"])
    if (catalog.to_dict() != payload["card_catalog"]
            or CardVocabulary(catalog).to_dict() != vocabulary.to_dict()):
        raise ValueError("Checkpoint catalog/vocabulary mapping is incompatible")
    encoder = StateEncoder(catalog, vocabulary)
    for key, expected_value in compatibility(encoder, representation).items():
        if payload.get(key) != expected_value:
            raise ValueError(f"Incompatible real policy checkpoint: {key}")
    config = payload.get("model_config", {})
    expected = {"architecture": "PolicyNetwork", "card_count": vocabulary.card_count,
                "state_feature_count": len(POLICY_STATE_FEATURE_NAMES),
                "card_embedding_dim": CARD_EMBEDDING_DIM, "max_hand_size": MAX_HAND_SIZE}
    extra = {"hidden_size"}
    if representation == 2:
        contract = feature_contract(encoder)
        expected = {"architecture": "PolicyNetworkV2", "card_count": vocabulary.card_count,
                    "state_feature_count": len(contract["state_feature_names"]),
                    "entity_feature_count": len(contract["entity_feature_names"]),
                    "card_embedding_dim": CARD_EMBEDDING_DIM}
        extra.add("dropout")
        if type(config.get("dropout")) not in (float, int) or not 0 <= config["dropout"] < 1:
            raise ValueError("Incompatible policy dropout")
    if (set(config) != {*expected, *extra}
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
    policy = ((PolicyNetworkV2(**{k: v for k, v in config.items() if k not in {"architecture", "card_embedding_dim"}}))
              if representation == 2 else PolicyNetwork(card_count=vocabulary.card_count, hidden_size=config["hidden_size"]))
    policy = policy.to(device)
    try:
        policy.load_state_dict(payload["policy_state_dict"], strict=True)
    except (KeyError, RuntimeError) as error:
        raise ValueError("Incompatible policy weight shapes") from error
    if not all(torch.isfinite(t).all() for t in policy.state_dict().values()):
        raise ValueError("Nonfinite policy weights")
    policy.eval()
    return policy, encoder, payload
