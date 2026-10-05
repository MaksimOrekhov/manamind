"""Read-only compatibility audit for imported real match examples."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import fields
from pathlib import Path
from typing import Any

import torch

from manamind.cards.catalog import CardCatalog
from manamind.domain import game_state_from_dict
from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity, LocationEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.encoding.batch import collate_encoded_states
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.value_network import ValueNetwork
from manamind.training.real_dataset import (
    EXPECTED_SOURCE,
    match_fingerprint,
    split_matches,
)
from manamind.training.synthetic import LabeledState


_TOP_FIELDS = {field.name for field in fields(GameState)}
_PLAYER_FIELDS = {field.name for field in fields(PlayerObservation)}
_CARD_FIELDS = {field.name for field in fields(CardFeatures)}
_BOARD_FIELDS = {field.name for field in fields(BoardEntity)}
_LOCATION_FIELDS = {field.name for field in fields(LocationEntity)}
_CANONICAL_TARGETS = {0.0, 0.5, 1.0}


def _validate_visible_state_shape(state: dict[str, Any]) -> None:
    """Reject extra raw fields so unmodeled/hidden data cannot be smuggled in."""
    extra = set(state) - _TOP_FIELDS
    if extra:
        raise ValueError("state has fields outside the player-visible GameState schema")
    for player_name in ("self_player", "opponent"):
        player = state.get(player_name)
        if not isinstance(player, dict):
            continue
        if set(player) - _PLAYER_FIELDS:
            raise ValueError("player observation has fields outside its visible schema")
        for name, value in player.items():
            if name in {"known_secrets", "active_effects"}:
                _validate_card_list(value)
            elif name in {"weapon", "hero_power"}:
                _validate_card(value)
            elif name == "board":
                _validate_entity_list(value, _BOARD_FIELDS)
            elif name == "locations":
                _validate_entity_list(value, _LOCATION_FIELDS)
    for name in ("self_hand", "opponent_known_cards", "pending_choice_options"):
        if name in state:
            _validate_card_list(state[name])


def _validate_card(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - _CARD_FIELDS:
        raise ValueError("card has fields outside the visible card schema")


def _validate_card_list(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError("visible card collection must be a list")
    for card in value:
        _validate_card(card)


def _validate_entity_list(value: Any, allowed: set[str]) -> None:
    if not isinstance(value, list):
        raise ValueError("visible entity collection must be a list")
    for entity in value:
        if not isinstance(entity, dict) or set(entity) - allowed:
            raise ValueError("entity has fields outside its visible schema")
        _validate_card(entity.get("card"))


def _visible_card_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"card_id", "shatter_original_card_id"} and isinstance(item, str) and item:
                found.add(item)
            else:
                found.update(_visible_card_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_visible_card_ids(item))
    return found


def _load_input(
    input_dir: Path,
) -> tuple[list[LabeledState], dict[str, int], list[str], int, set[str]]:
    files = sorted(input_dir.glob("*.jsonl")) if input_dir.is_dir() else []
    examples: list[LabeledState] = []
    failures: list[str] = []
    card_ids: set[str] = set()
    duplicate_sample_ids = 0
    seen_sample_ids: set[str] = set()

    if not input_dir.is_dir():
        return [], {}, ["input_dir_missing"], 0, card_ids
    if not files:
        return [], {}, ["no_jsonl_files"], 0, card_ids

    for file_index, path in enumerate(files):
        try:
            stream = path.open("r", encoding="utf-8-sig")
        except OSError:
            failures.append(f"file_{file_index + 1}_unreadable")
            continue
        with stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict) or row.get("schema_version") != 1:
                        raise ValueError("invalid_schema")
                    target = float(row["target"])
                    if target not in _CANONICAL_TARGETS or not math.isfinite(target):
                        raise ValueError("invalid_target")
                    if str(row.get("perspective", "SELF")) != "SELF":
                        raise ValueError("invalid_perspective")
                    if str(row.get("source", "unknown")) != EXPECTED_SOURCE:
                        raise ValueError("invalid_source")
                    game_id = str(row.get("game_id", "")).strip()
                    sample_id = str(row.get("sample_id", "")).strip()
                    if not game_id or game_id == "None":
                        raise ValueError("missing_game_id")
                    if not sample_id or sample_id == "None":
                        raise ValueError("missing_sample_id")
                    if sample_id in seen_sample_ids:
                        duplicate_sample_ids += 1
                    seen_sample_ids.add(sample_id)
                    raw_state = row["state"]
                    if not isinstance(raw_state, dict):
                        raise ValueError("invalid_state")
                    _validate_visible_state_shape(raw_state)
                    state = game_state_from_dict(raw_state)
                    card_ids.update(_visible_card_ids(raw_state))
                    examples.append(LabeledState(
                        state=state,
                        target=target,
                        game_id=game_id,
                        sample_id=sample_id,
                        perspective="SELF",
                        source=EXPECTED_SOURCE,
                    ))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OverflowError):
                    # Deliberately retain no row content or user-provided values in diagnostics.
                    failures.append(f"file_{file_index + 1}_line_{line_number}_invalid")

    return examples, {"duplicate_sample_ids": duplicate_sample_ids}, failures, len(files), card_ids


def audit_real_dataset(
    input_dir: str | Path,
    cards_path: str | Path,
    batch_size: int = 16,
) -> dict[str, Any]:
    """Audit every row, encoder compatibility and one finite model forward pass."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    catalog = CardCatalog.from_json(cards_path)
    examples, integrity, failures, file_count, card_ids = _load_input(Path(input_dir))
    duplicate_sample_ids = integrity["duplicate_sample_ids"]
    match_groups: dict[str, list[LabeledState]] = {}
    for example in examples:
        match_groups.setdefault(example.game_id, []).append(example)

    inconsistent_matches = sum(
        len({example.target for example in rows}) != 1
        for rows in match_groups.values()
    )
    if duplicate_sample_ids:
        failures.append("duplicate_sample_ids")
    if inconsistent_matches:
        failures.append("inconsistent_match_targets")

    fingerprints: set[str] = set()
    duplicate_trajectories = 0
    unique_matches: dict[str, list[LabeledState]] = {}
    for game_id, rows in match_groups.items():
        fingerprint = match_fingerprint(rows)
        if fingerprint in fingerprints:
            duplicate_trajectories += 1
            continue
        fingerprints.add(fingerprint)
        unique_matches[game_id] = rows

    outcome_matches = {0.0: 0, 0.5: 0, 1.0: 0}
    for rows in unique_matches.values():
        if len({item.target for item in rows}) == 1:
            outcome_matches[rows[0].target] += 1
    target_counts = Counter(
        item.target for rows in unique_matches.values() for item in rows
    )
    match_sizes = [len(rows) for rows in unique_matches.values()]
    split_ready = False
    split_reason = "invalid_data" if failures else None
    if not failures:
        try:
            split_matches(unique_matches, seed=42)
            split_ready = True
        except ValueError:
            split_reason = "insufficient_matches_or_outcome_groups"

    encoder: StateEncoder | None = None
    encoded_count = 0
    encode_failures = 0
    first_batch = []
    if not failures:
        encoder = StateEncoder(catalog)
        for example in examples:
            try:
                encoded = encoder.encode(example.state)
                encoded_count += 1
                if len(first_batch) < batch_size:
                    first_batch.append(encoded)
            except (TypeError, ValueError, KeyError, IndexError, OverflowError):
                encode_failures += 1
    else:
        encode_failures = 0

    forward_success = False
    output_shape: list[int] | None = None
    if encoder is not None and first_batch and encode_failures == 0:
        try:
            model = ValueNetwork(encoder.vocabulary)
            model.eval()
            batch = collate_encoded_states(first_batch)
            with torch.inference_mode():
                logits = model(batch)
                probabilities = torch.sigmoid(logits)
            forward_success = bool(torch.isfinite(logits).all() and torch.isfinite(probabilities).all())
            output_shape = list(logits.shape)
            forward_success = forward_success and output_shape == [len(first_batch)]
        except (RuntimeError, TypeError, ValueError, IndexError):
            forward_success = False

    known_ids = card_ids & {card.card_id for card in catalog}
    unknown_ids = card_ids - known_ids
    examples_per_match = {
        "min": min(match_sizes) if match_sizes else None,
        "max": max(match_sizes) if match_sizes else None,
        "mean": (sum(match_sizes) / len(match_sizes)) if match_sizes else None,
    }
    can_train = split_ready and not failures and encode_failures == 0 and forward_success
    training_readiness = (
        "INVALID_DATA" if failures else
        "ENCODER_INCOMPATIBLE" if encode_failures or not forward_success else
        "READY" if can_train else "INSUFFICIENT_MATCHES"
    )

    return {
        "files": file_count,
        "unique_matches": len(unique_matches),
        "examples": len(examples),
        "unique_examples": sum(len(rows) for rows in unique_matches.values()),
        "wins": outcome_matches[1.0],
        "losses": outcome_matches[0.0],
        "draws": outcome_matches[0.5],
        "examples_per_match": examples_per_match,
        "target_distribution": {
            "win": target_counts[1.0],
            "loss": target_counts[0.0],
            "draw": target_counts[0.5],
        },
        "duplicate_sample_ids": duplicate_sample_ids,
        "duplicate_match_trajectories": duplicate_trajectories,
        "inconsistent_match_targets": inconsistent_matches,
        "sample_integrity": "INVALID" if failures else "OK",
        "failure_count": len(failures),
        "failure_codes": sorted(set(failures)),
        "card_identity": {
            "distinct_card_ids_seen": len(card_ids),
            "known_catalog_ids": len(known_ids),
            "unknown_catalog_ids": len(unknown_ids),
            "unknown_catalog_ratio": (len(unknown_ids) / len(card_ids)) if card_ids else 0.0,
            "unknown_ids_use_shared_unk_index": True,
        },
        "encoding": {
            "attempted": encoder is not None,
            "states_encoded": encoded_count,
            "failures": encode_failures,
        },
        "batch_forward": {
            "success": forward_success,
            "batch_size": len(first_batch),
            "output_shape": output_shape,
            "finite_output": forward_success,
        },
        "visibility": {
            "perspective_self": not failures,
            "source_power_log_ranked_standard": not failures,
            "hidden_opponent_identities_in_encoded_state": 0,
            "basis": "strict GameState visible-schema allowlist; opponent hand identities are absent except explicitly known cards",
        },
        "split_readiness": {
            "can_create_train_validation_test": split_ready,
            "reason_if_not": split_reason,
        },
        "training_readiness": training_readiness,
        "pipeline_ready": not failures and encode_failures == 0 and forward_success,
        "dataset_size_assessment": (
            "SPLITS_POSSIBLE_BUT_STATISTICAL_SUFFICIENCY_NOT_ESTABLISHED"
            if split_ready else "INSUFFICIENT_MATCHES_FOR_SPLITS"
        ),
        "model_quality_established": False,
    }
