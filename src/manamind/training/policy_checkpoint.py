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
from manamind.models.policy_v3 import PolicyNetworkV3

FORMAT = "manamind.real_policy_baseline/1"
FORMAT_V2 = "manamind.real_policy/2"
FORMAT_V3 = "manamind.real_policy/3"  # v2 input contract, PolicyNetworkV3 network
NORMALIZATION = "signed_log1p_clip_10000"
PREPARE_SEMANTIC_VERSION = 2  # semantic action schema 2 = PLAY_CARD plus PREPARE_CARD roots (experimental)


def identity(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def compatibility(encoder=None, representation=1, semantic_action_schema_version=1) -> dict:
    result = {"schema": FORMAT, "state_encoding_schema_version": STATE_ENCODING_SCHEMA_VERSION,
            "policy_action_schema_version": POLICY_ACTION_SCHEMA_VERSION,
            "real_policy_dataset_schema_version": 1,
            "semantic_action_schema_version": semantic_action_schema_version,
            "state_feature_names": list(POLICY_STATE_FEATURE_NAMES),
            "action_feature_names": list(ACTION_FEATURE_NAMES), "normalization": NORMALIZATION}
    if representation in (2, 3):
        result.update(feature_contract(encoder))
        result["schema"] = FORMAT_V2 if representation == 2 else FORMAT_V3
    elif representation != 1:
        raise ValueError("Unsupported policy representation")
    return result


def model_config(policy, encoder) -> dict:
    if representation_of(policy) == 3:
        return {"architecture": "PolicyNetworkV3", "hidden_size": policy.hidden_size, "dropout": policy.dropout,
                "heads": policy.heads, "entity_layers": policy.entity_layers, "menu_layers": policy.menu_layers,
                "card_count": encoder.vocabulary.card_count, "state_feature_count": policy.state_feature_count,
                "entity_feature_count": policy.entity_feature_count, "card_embedding_dim": CARD_EMBEDDING_DIM}
    if representation_of(policy) == 2:
        return {"architecture": "PolicyNetworkV2", "hidden_size": policy.hidden_size,
                "dropout": policy.dropout, "card_count": encoder.vocabulary.card_count,
                "state_feature_count": policy.state_feature_count,
                "entity_feature_count": policy.entity_feature_count, "card_embedding_dim": CARD_EMBEDDING_DIM}
    return {"architecture": "PolicyNetwork", "hidden_size": policy.scorer[0].out_features,
            "card_count": encoder.vocabulary.card_count, "state_feature_count": len(POLICY_STATE_FEATURE_NAMES),
            "card_embedding_dim": CARD_EMBEDDING_DIM, "max_hand_size": MAX_HAND_SIZE}


def save_policy_checkpoint(path: Path, policy, encoder, metadata: dict, *, allow_prepare: bool = False) -> None:
    """``allow_prepare`` marks a checkpoint trained with semantic action schema 2 (PREPARE_CARD roots).

    Such a checkpoint is refused by every loader that does not pass ``allow_prepare=True``, so an experimental
    Prepare-aware model can never reach LIVE or the shadow evaluation by accident.
    """
    representation = representation_of(policy)
    if allow_prepare and representation not in (2, 3):
        raise ValueError("Prepare-aware checkpoints need the v2/v3 representation")
    catalog, vocabulary = encoder.catalog.to_dict(), encoder.vocabulary.to_dict()
    payload = {**compatibility(encoder, representation, PREPARE_SEMANTIC_VERSION if allow_prepare else 1),
               "card_catalog": catalog, "card_vocabulary": vocabulary,
               "catalog_sha256": identity(catalog), "vocabulary_sha256": identity(vocabulary),
               "model_config": model_config(policy, encoder),
               "policy_state_dict": policy.state_dict(), "experiment": metadata}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        torch.save(payload, stream)


def load_policy_checkpoint(path: Path, device="cpu", *, allow_prepare: bool = False) -> tuple:
    """Load and strictly validate a checkpoint. A semantic action schema 2 (Prepare) checkpoint needs ``allow_prepare``."""
    payload = torch.load(path, map_location=device, weights_only=True)
    if not isinstance(payload, dict) or payload.get("schema") not in (FORMAT, FORMAT_V2, FORMAT_V3):
        raise ValueError("Incompatible real policy checkpoint: schema")
    representation = {FORMAT: 1, FORMAT_V2: 2, FORMAT_V3: 3}[payload["schema"]]
    for name, key in (("catalog", "card_catalog"), ("vocabulary", "card_vocabulary")):
        if identity(payload.get(key)) != payload.get(f"{name}_sha256"):
            raise ValueError(f"Checkpoint {name} identity mismatch")
    catalog = CardCatalog.from_dict(payload["card_catalog"])
    vocabulary = CardVocabulary.from_dict(payload["card_vocabulary"])
    if (catalog.to_dict() != payload["card_catalog"]
            or CardVocabulary(catalog).to_dict() != vocabulary.to_dict()):
        raise ValueError("Checkpoint catalog/vocabulary mapping is incompatible")
    encoder = StateEncoder(catalog, vocabulary)
    semantic = payload.get("semantic_action_schema_version")
    if semantic == PREPARE_SEMANTIC_VERSION:
        if not allow_prepare or representation not in (2, 3):
            raise ValueError("Incompatible real policy checkpoint: semantic_action_schema_version")
    else:
        semantic = 1  # anything but 1 or 2 fails the comparison below
    for key, expected_value in compatibility(encoder, representation, semantic).items():
        if payload.get(key) != expected_value:
            raise ValueError(f"Incompatible real policy checkpoint: {key}")
    config = payload.get("model_config", {})
    expected = {"architecture": "PolicyNetwork", "card_count": vocabulary.card_count,
                "state_feature_count": len(POLICY_STATE_FEATURE_NAMES),
                "card_embedding_dim": CARD_EMBEDDING_DIM, "max_hand_size": MAX_HAND_SIZE}
    extra = {"hidden_size"}
    if representation in (2, 3):
        contract = feature_contract(encoder)
        expected = {"architecture": "PolicyNetworkV2" if representation == 2 else "PolicyNetworkV3",
                    "card_count": vocabulary.card_count,
                    "state_feature_count": len(contract["state_feature_names"]),
                    "entity_feature_count": len(contract["entity_feature_names"]),
                    "card_embedding_dim": CARD_EMBEDDING_DIM}
        extra.add("dropout")
        if type(config.get("dropout")) not in (float, int) or not 0 <= config["dropout"] < 1:
            raise ValueError("Incompatible policy dropout")
        if representation == 3:
            extra.update({"heads", "entity_layers", "menu_layers"})
            if any(type(config.get(k)) is not int for k in ("heads", "entity_layers", "menu_layers")):
                raise ValueError("Incompatible policy v3 shape config")
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
    reserved = split.get("reserved_game_ids", [])  # matches deliberately kept out of training, validation and test
    if (not isinstance(reserved, list) or len(reserved) != len(set(reserved))
            or set(reserved) & {g for v in parts.values() for g in v}):
        raise ValueError("Invalid policy training/split identity")
    kwargs = {k: v for k, v in config.items() if k not in {"architecture", "card_embedding_dim"}}
    policy = (PolicyNetworkV2(**kwargs) if representation == 2 else PolicyNetworkV3(**kwargs) if representation == 3
              else PolicyNetwork(card_count=vocabulary.card_count, hidden_size=config["hidden_size"]))
    policy = policy.to(device)
    try:
        policy.load_state_dict(payload["policy_state_dict"], strict=True)
    except (KeyError, RuntimeError) as error:
        raise ValueError("Incompatible policy weight shapes") from error
    if not all(torch.isfinite(t).all() for t in policy.state_dict().values()):
        raise ValueError("Nonfinite policy weights")
    policy.eval()
    return policy, encoder, payload
