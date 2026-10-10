"""One locked real-data comparison: frozen v2, retrained v2, and text Hybrid."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from manamind.cards.catalog import CardCatalog
from manamind.encoding.state_encoder import StateEncoder
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract
from manamind.research.card_text_features import CardTextAdapter
from manamind.research.hybrid_policy import HybridPolicyV2
from manamind.training.policy_checkpoint import (
    compatibility, identity, load_policy_checkpoint, save_policy_checkpoint,
)
from manamind.training.real_policy import audit_dataset, encode_example, load_examples
from refresh_real_policy_dataset import canonical_content_identity, dataset_identity

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed_data_checkpoint_1_20261010/canonical"
INVENTORY = ROOT / "data/processed_data_checkpoint_1_20261010/raw_inventory.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
FROZEN = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
PUBLIC = ROOT / "reports/ml_pilot_1"
OUTPUT = ROOT / "data/processed_ml_pilot_1_20261010"
CONFIG = ROOT / "configs/ml_pilot_1.json"
EXPECTED_DATA = "b964e121d6ddb0c11be4014b1549d1a5c861cf57002bfd8975edd53b3be233c1"
EXPECTED_CONTENT = "78c21cbd0a2c0c69cdaee77bd07525b086294dba781674a6c47a9a65d354e9c9"
EXPECTED_FROZEN = "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"
EXPECTED_CATALOG = "c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def load_inputs() -> tuple[list[dict], dict, dict]:
    if not DATA.is_dir() or not INVENTORY.is_file():
        raise FileNotFoundError("The canonical DATA-CHECKPOINT-1 corpus is missing")
    rows = sorted(load_examples(DATA), key=lambda row: row["decision_id"])
    metadata = json.loads((DATA / "refresh_metadata.json").read_text(encoding="utf-8"))
    if (dataset_identity(rows) != EXPECTED_DATA
            or metadata["dataset_identity_sha256"] != EXPECTED_DATA
            or canonical_content_identity(DATA) != EXPECTED_CONTENT
            or metadata["canonical_content_identity_sha256"] != EXPECTED_CONTENT):
        raise ValueError("Canonical corpus identity mismatch")
    if sha(CATALOG) != EXPECTED_CATALOG or sha(FROZEN) != EXPECTED_FROZEN:
        raise ValueError("Pinned catalog or frozen checkpoint identity mismatch")
    audit = audit_dataset(DATA, CardCatalog.from_json(CATALOG))
    if audit["decisions_labeled"] != 2010 or audit["labeled_matches"] != 53:
        raise ValueError("Canonical corpus audit mismatch")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if (config["seed"] != 42 or config["split_seed"] != 42 or config["device"] != "cpu"
            or config["torch_threads"] != 1 or config["max_epochs"] != 30):
        raise ValueError("Pilot configuration differs from the preregistered budget")
    return rows, metadata, config


def make_split(rows: list[dict], config: dict) -> dict:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    recent = {item["game_id"] for item in inventory if item["mtime"].startswith("2026-10-10")}
    games = {row["game_id"] for row in rows}
    test = games & recent
    old = games - recent
    if len(test) != 16 or len(old) != 37:
        raise ValueError("Expected exactly 37 old and 16 new usable matches")
    outcomes = {row["game_id"]: row["final_result"] for row in rows}
    validation: set[str] = set()
    for outcome in (0.0, 1.0):
        group = sorted((game for game in old if outcomes[game] == outcome),
                       key=lambda game: hashlib.sha256(f"{config['split_seed']}:{game}".encode()).hexdigest())
        validation.update(group[: max(1, round(len(group) * .2))])
    train = old - validation
    groups = {"train": train, "validation": validation, "test": test}
    trajectories: dict[str, str] = {}
    for game in sorted(games):
        trajectory = [{"state": row["state"], "legal_actions": row["legal_actions"],
                       "chosen_action_index": row["chosen_action_index"]}
                      for row in rows if row["game_id"] == game]
        digest = identity(trajectory)
        if digest in trajectories:
            raise ValueError("Normalized trajectory appears in multiple matches")
        trajectories[digest] = game
    if any(groups[a] & groups[b] for a, b in (("train", "validation"), ("train", "test"),
                                             ("validation", "test"))):
        raise ValueError("Match leakage across partitions")
    return {"algorithm": "outcome_stratified_sha256_80_20_old_development/1",
            "seed": config["split_seed"], "dataset_sha256": EXPECTED_DATA,
            "canonical_content_sha256": EXPECTED_CONTENT,
            "game_ids": {name: sorted(ids) for name, ids in groups.items()},
            "trajectory_sha256": {name: sorted(digest for digest, game in trajectories.items() if game in ids)
                                  for name, ids in groups.items()},
            "counts": {name: {"matches": len(ids), "decisions": sum(row["game_id"] in ids for row in rows),
                              "wins": sum(outcomes[game] == 1.0 for game in ids),
                              "losses": sum(outcomes[game] == 0.0 for game in ids)}
                       for name, ids in groups.items()}}


def partitions(rows: list[dict], split: dict) -> dict[str, list[dict]]:
    return {name: [row for row in rows if row["game_id"] in set(ids)]
            for name, ids in split["game_ids"].items()}


def rank_rows(model, rows: list[dict], encoder, text_vectors=None) -> tuple[list[dict], dict]:
    model.eval()
    result, errors = [], Counter()
    with torch.inference_mode():
        for row in rows:
            try:
                inputs = encode_example(row, encoder, representation=2)
                if text_vectors is not None:
                    inputs += text_vectors.inputs(row)
                logits = model(*inputs)
                if logits.shape != (len(row["legal_actions"]),) or not torch.isfinite(logits).all():
                    raise ValueError("Invalid logits")
                order = torch.argsort(logits, descending=True, stable=True).tolist()
                chosen = row["chosen_action_index"]
                action = row["legal_actions"][chosen]
                result.append({"game_id": row["game_id"], "decision_id": row["decision_id"],
                               "rank": order.index(chosen) + 1, "top1": order[0], "top3": order[:3],
                               "menu_size": len(order), "kind": action["type"],
                               "source_card_id": source_card(action),
                               "latency_inputs": len(inputs)})
            except (ValueError, RuntimeError, IndexError, KeyError) as error:
                errors[type(error).__name__] += 1
    return result, dict(errors)


def source_card(action: dict) -> str | None:
    if action["type"] == "END_TURN":
        return None
    return action.get("source_card_id") or action.get("card_id") or action.get("choice_card_id")


class TextVectors:
    def __init__(self, adapter: CardTextAdapter):
        self.adapter = adapter
        self.width = len(adapter.terms)
        self.cache: dict[str | None, tuple[torch.Tensor, float]] = {}

    def inputs(self, row: dict) -> tuple[torch.Tensor, torch.Tensor]:
        vectors, masks = [], []
        for action in row["legal_actions"]:
            card_id = source_card(action)
            if card_id not in self.cache:
                vector, usable = self.adapter.features(card_id)
                self.cache[card_id] = torch.from_numpy(vector), float(usable)
            vector, mask = self.cache[card_id]
            vectors.append(vector)
            masks.append(mask)
        return torch.stack(vectors), torch.tensor(masks, dtype=torch.float32)


def score(records: list[dict]) -> dict:
    if not records:
        return {"n": 0}
    top3 = [item for item in records if item["menu_size"] >= 3]
    return {"n": len(records), "top1": sum(item["rank"] == 1 for item in records) / len(records),
            "top3": sum(item["rank"] <= 3 for item in top3) / len(top3) if top3 else None,
            "top3_n": len(top3), "mrr": sum(1 / item["rank"] for item in records) / len(records)}


def preflight() -> None:
    rows, _, config = load_inputs()
    split = make_split(rows, config)
    test = partitions(rows, split)["test"]
    torch.set_num_threads(1)
    frozen, encoder, payload = load_policy_checkpoint(FROZEN)
    historical = payload["experiment"]["split"]["game_ids"]
    if any(set(ids) & set(split["game_ids"]["test"]) for ids in historical.values()):
        raise ValueError("Frozen checkpoint used a development-test match")
    if payload["catalog_sha256"] != identity(CardCatalog.from_json(CATALOG).to_dict()):
        raise ValueError("Frozen and pilot card catalogs differ")
    baseline, errors = rank_rows(frozen, test, encoder)
    metrics = score(baseline)
    if (len(baseline) != 669 or errors or sum(item["rank"] == 1 for item in baseline) != 330
            or sum(item["rank"] <= 3 and item["menu_size"] >= 3 for item in baseline) != 351
            or metrics["top3_n"] != 563):
        raise ValueError("Frozen baseline does not reproduce DATA-CHECKPOINT-1")
    PUBLIC.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_new(PUBLIC / "split_manifest.json", split)
    write_new(OUTPUT / "preflight.json", {"split_sha256": identity(split), "config_sha256": sha(CONFIG),
                                          "frozen_checkpoint_sha256": sha(FROZEN), "baseline": metrics,
                                          "baseline_top1_hits": 330, "baseline_top3_hits": 351,
                                          "baseline_errors": errors})
    print(json.dumps({"preflight": "PASS", "split": split["counts"], "baseline": metrics}))


def validation_loss(model, rows: list[dict], encoder, text_vectors=None) -> float:
    model.eval()
    losses = []
    with torch.inference_mode():
        for row in rows:
            inputs = encode_example(row, encoder, representation=2)
            if text_vectors is not None:
                inputs += text_vectors.inputs(row)
            logits = model(*inputs)
            losses.append(torch.nn.functional.cross_entropy(
                logits[None], torch.tensor([row["chosen_action_index"]])).item())
    return sum(losses) / len(losses)


def train_model(model, train: list[dict], validation: list[dict], encoder, config: dict,
                text_vectors=None) -> tuple[int, list[dict]]:
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"],
                                  weight_decay=config["weight_decay"])
    rng = random.Random(config["seed"])
    best, best_epoch, best_state, stale, history = float("inf"), 0, None, 0, []
    for epoch in range(1, config["max_epochs"] + 1):
        model.train()
        order = list(range(len(train)))
        rng.shuffle(order)
        train_loss = 0.0
        for start in range(0, len(order), config["batch_size"]):
            batch = order[start:start + config["batch_size"]]
            losses = []
            for index in batch:
                row = train[index]
                inputs = encode_example(row, encoder, representation=2)
                if text_vectors is not None:
                    inputs += text_vectors.inputs(row)
                logits = model(*inputs)
                losses.append(torch.nn.functional.cross_entropy(
                    logits[None], torch.tensor([row["chosen_action_index"]])))
            loss = torch.stack(losses).mean()
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config["gradient_clip"], error_if_nonfinite=True)
            optimizer.step()
            train_loss += loss.item() * len(batch)
        val_loss = validation_loss(model, validation, encoder, text_vectors)
        history.append({"epoch": epoch, "train_cross_entropy": train_loss / len(train),
                        "validation_cross_entropy": val_loss})
        if val_loss < best - config["min_delta"]:
            best, best_epoch, best_state, stale = val_loss, epoch, copy.deepcopy(model.state_dict()), 0
        else:
            stale += 1
        print(json.dumps({"epoch": epoch, "kind": "hybrid" if text_vectors else "v2",
                          "validation_ce": val_loss, "best_epoch": best_epoch}), flush=True)
        if stale >= config["patience"]:
            break
    if best_state is None:
        raise ValueError("No checkpoint selected by validation")
    model.load_state_dict(best_state)
    return best_epoch, history


def new_base(encoder, config):
    contract = feature_contract(encoder)
    return PolicyNetworkV2(card_count=encoder.vocabulary.card_count,
                           state_feature_count=len(contract["state_feature_names"]),
                           entity_feature_count=len(contract["entity_feature_names"]),
                           hidden_size=config["hidden_size"], dropout=config["dropout"])


def save_hybrid(path: Path, model, encoder, adapter, split, config, selected_epoch):
    # Store the full sparse text table so inference cannot silently use changed catalog text.
    table = {}
    for card_id in sorted(adapter.cards):
        vector, usable = adapter.features(card_id)
        if usable:
            table[card_id] = [[int(i), float(vector[i])] for i in np.flatnonzero(vector)]
    payload = {"schema": "manamind.experimental_hybrid_policy/1",
               "base_compatibility": compatibility(encoder, 2),
               "card_catalog": encoder.catalog.to_dict(), "card_vocabulary": encoder.vocabulary.to_dict(),
               "catalog_sha256": identity(encoder.catalog.to_dict()),
               "vocabulary_sha256": identity(encoder.vocabulary.to_dict()),
               "text_catalog_file_sha256": adapter.catalog_sha256,
               "text_config_sha256": adapter.config_sha256, "text_terms": adapter.terms,
               "text_table": table, "text_width": len(adapter.terms),
               "config": config, "config_sha256": identity(config),
               "split": split, "split_sha256": identity(split),
               "selected_epoch": selected_epoch, "model_state_dict": model.state_dict()}
    with path.open("xb") as stream:
        torch.save(payload, stream)


def load_hybrid(path: Path, encoder, adapter, split, config):
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if (payload.get("schema") != "manamind.experimental_hybrid_policy/1"
            or payload.get("base_compatibility") != compatibility(encoder, 2)
            or payload.get("catalog_sha256") != identity(encoder.catalog.to_dict())
            or payload.get("vocabulary_sha256") != identity(encoder.vocabulary.to_dict())
            or payload.get("text_catalog_file_sha256") != adapter.catalog_sha256
            or payload.get("text_config_sha256") != adapter.config_sha256
            or payload.get("text_terms") != adapter.terms
            or payload.get("text_width") != len(adapter.terms)
            or payload.get("split_sha256") != identity(split) or payload.get("split") != split
            or payload.get("config_sha256") != identity(config) or payload.get("config") != config):
        raise ValueError("Incompatible hybrid checkpoint")
    expected_table = {}
    for card_id in sorted(adapter.cards):
        vector, usable = adapter.features(card_id)
        if usable:
            expected_table[card_id] = [[int(i), float(vector[i])] for i in np.flatnonzero(vector)]
    if payload.get("text_table") != expected_table:
        raise ValueError("Hybrid text feature table differs from the pinned catalog")
    model = HybridPolicyV2(new_base(encoder, config), len(adapter.terms))
    model.load_state_dict(payload["model_state_dict"], strict=True)
    if not all(torch.isfinite(t).all() for t in model.state_dict().values()):
        raise ValueError("Nonfinite hybrid weights")
    model.eval()
    return model


def record_stats(records: list[dict], seed: int, replicates: int) -> dict:
    grouped = defaultdict(list)
    for record in records:
        grouped[record["game_id"]].append(record)
    games = sorted(grouped)
    rng = np.random.default_rng(seed)
    samples = [score([record for game in rng.choice(games, len(games), replace=True)
                      for record in grouped[game]]) for _ in range(replicates)]
    return {"point": score(records), "ci95": {
        name: np.quantile([item[name] for item in samples], [.025, .975]).tolist()
        for name in ("top1", "top3", "mrr")}}


def paired_stats(first: list[dict], second: list[dict], seed: int, replicates: int) -> dict:
    by_first = {r["decision_id"]: r for r in first}
    by_second = {r["decision_id"]: r for r in second}
    if set(by_first) != set(by_second):
        raise ValueError("Paired models did not score the same decisions")
    games = sorted({r["game_id"] for r in first})
    by_game = {game: [r["decision_id"] for r in first if r["game_id"] == game] for game in games}
    rng = np.random.default_rng(seed)

    def differences(ids):
        a, b = [by_first[i] for i in ids], [by_second[i] for i in ids]
        x, y = score(a), score(b)
        return {name: y[name] - x[name] for name in ("top1", "top3", "mrr")}

    bootstrap = [differences([item for game in rng.choice(games, len(games), replace=True)
                              for item in by_game[game]]) for _ in range(replicates)]
    return {"second_minus_first": differences([r["decision_id"] for r in first]),
            "ci95": {name: np.quantile([item[name] for item in bootstrap], [.025, .975]).tolist()
                     for name in ("top1", "top3", "mrr")},
            "changed_top1": sum(by_first[key]["top1"] != by_second[key]["top1"] for key in by_first),
            "first_wrong_second_right": sum(by_first[key]["rank"] != 1 and by_second[key]["rank"] == 1
                                            for key in by_first),
            "first_right_second_wrong": sum(by_first[key]["rank"] == 1 and by_second[key]["rank"] != 1
                                            for key in by_first)}


def action_brief(action: dict) -> dict:
    return {key: action[key] for key in ("type", "card_id", "source_card_id", "source_kind",
                                         "target_card_id", "target_kind", "target_side",
                                         "target_board_position", "hand_index", "play_position") if key in action}


def case_diagnostics(rows, records_by_model) -> dict:
    frozen = {r["decision_id"]: r for r in records_by_model["frozen"]}
    found = {}
    for row in rows:
        baseline = frozen[row["decision_id"]]
        action = row["legal_actions"][baseline["top1"]]
        card = source_card(action)
        state = row["state"]
        categories = []
        if card in {"HERO_09bp", "HERO_09dbp", "CORE_AT_055", "CORE_CFM_604"} and "target_kind" in action:
            player = state["self_player" if action["target_side"] == "SELF" else "opponent"]
            if action["target_kind"] == "HERO":
                current, maximum = player["hero_health"], player.get("hero_max_health")
            else:
                entity = next((item for item in player["board"]
                               if item["board_position"] == action.get("target_board_position")), None)
                current = entity["current_health"] if entity else None
                maximum = entity.get("max_health") if entity else None
            if current is not None and maximum is not None and current == maximum:
                categories.append("full_health_heal")
        if card in {"EX1_197", "CORE_EX1_197"} and all(
                item["current_attack"] < 5 for side in ("self_player", "opponent")
                for item in state[side]["board"]):
            categories.append("ruin_no_attack_5")
        if card == "TIME_890t" and any(item["card_id"] == "TIME_890" for item in state["self_hand"]):
            categories.append("atiesh_with_medivh_in_hand")
        if card == "TIME_890" and len(state["opponent"]["board"]) >= 4:
            categories.append("medivh_against_board")
        if action["type"] == "PLAY_CARD" and len(state["self_hand"]) >= 9:
            categories.append("near_full_hand_play")
        for category in categories:
            if category in found:
                continue
            found[category] = {"observation_sha256": identity({"state": state,
                                                                  "legal_actions": row["legal_actions"]}),
                               "self_hand_size": len(state["self_hand"]),
                               "top3": {name: [action_brief(row["legal_actions"][index])
                                               for index in next(r for r in records if r["decision_id"] == row["decision_id"])["top3"]]
                                        for name, records in records_by_model.items()}}
    found["coin_without_followup"] = {"status": "exact observation not recovered"}
    return found


def latency(model, rows, encoder, text_vectors=None):
    chosen = rows[: min(100, len(rows))]
    samples = []
    model.eval()
    with torch.inference_mode():
        for row in chosen:
            start = time.perf_counter()
            inputs = encode_example(row, encoder, representation=2)
            if text_vectors is not None:
                inputs += text_vectors.inputs(row)
            logits = model(*inputs)
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite benchmark logits")
            samples.append((time.perf_counter() - start) * 1000)
    return {"n": len(samples), "mean_ms": float(np.mean(samples)),
            "p50_ms": float(np.quantile(samples, .5)), "p95_ms": float(np.quantile(samples, .95)),
            "scope": "CPU single thread, full row encoding plus forward, warm text cache"}


def train_and_evaluate() -> None:
    rows, _, config = load_inputs()
    split = make_split(rows, config)
    if json.loads((PUBLIC / "split_manifest.json").read_text(encoding="utf-8")) != split:
        raise ValueError("Split manifest changed after preflight")
    pre = json.loads((OUTPUT / "preflight.json").read_text(encoding="utf-8"))
    if pre["split_sha256"] != identity(split) or pre["config_sha256"] != sha(CONFIG):
        raise ValueError("Configuration or split changed after baseline reproduction")
    if (OUTPUT / "retrained_v2.pt").exists() or (OUTPUT / "hybrid.pt").exists():
        raise FileExistsError("A pilot checkpoint already exists; never overwrite it")
    parts = partitions(rows, split)
    torch.set_num_threads(config["torch_threads"])
    torch.use_deterministic_algorithms(True)
    catalog = CardCatalog.from_json(CATALOG)
    encoder = StateEncoder(catalog)
    adapter = CardTextAdapter(CATALOG)
    text_vectors = TextVectors(adapter)

    def seed_all():
        random.seed(config["seed"])
        np.random.seed(config["seed"])
        torch.manual_seed(config["seed"])

    seed_all()
    retrained = new_base(encoder, config)
    epoch_b, history_b = train_model(retrained, parts["train"], parts["validation"], encoder, config)
    meta = {"dataset_sha256": EXPECTED_DATA, "split": split, "split_sha256": identity(split),
            "config": config, "config_sha256": identity(config), "selected_epoch": epoch_b,
            "experiment": "ML-PILOT-1 retrained v2; development test is not independent"}
    save_policy_checkpoint(OUTPUT / "retrained_v2.pt", retrained, encoder, meta)
    restored_b, encoder_b, _ = load_policy_checkpoint(OUTPUT / "retrained_v2.pt")
    if encoder_b.vocabulary.to_dict() != encoder.vocabulary.to_dict():
        raise ValueError("Retrained vocabulary roundtrip failed")

    seed_all()
    hybrid = HybridPolicyV2(new_base(encoder, config), text_vectors.width)
    epoch_c, history_c = train_model(hybrid, parts["train"], parts["validation"],
                                     encoder, config, text_vectors)
    save_hybrid(OUTPUT / "hybrid.pt", hybrid, encoder, adapter, split, config, epoch_c)
    restored_c = load_hybrid(OUTPUT / "hybrid.pt", encoder, adapter, split, config)
    probe = next(row for row in parts["validation"] if text_vectors.inputs(row)[1].any())
    encoded = encode_example(probe, encoder, representation=2)
    text, mask = text_vectors.inputs(probe)
    with torch.inference_mode():
        actual = restored_c(*encoded, text, mask)
        removed = restored_c(*encoded, torch.zeros_like(text), mask)
    text_effect = float((actual - removed).abs().max())
    if text_effect <= 1e-8:
        raise ValueError("The hybrid text features do not affect logits")
    write_new(OUTPUT / "training.json", {"retrained": {"selected_epoch": epoch_b, "history": history_b},
                                           "hybrid": {"selected_epoch": epoch_c, "history": history_c,
                                                      "text_effect_max_logit_delta": text_effect}})

    # This is the only development-test scoring after both checkpoints are selected.
    frozen, frozen_encoder, _ = load_policy_checkpoint(FROZEN)
    models = {"frozen": (frozen, frozen_encoder, None),
              "retrained": (restored_b, encoder_b, None),
              "hybrid": (restored_c, encoder, text_vectors)}
    records, errors, timings = {}, {}, {}
    for name, (model, model_encoder, vectors) in models.items():
        records[name], errors[name] = rank_rows(model, parts["test"], model_encoder, vectors)
        timings[name] = latency(model, parts["test"], model_encoder, vectors)
        if len(records[name]) != 669 or errors[name]:
            raise ValueError(f"{name} did not score every development-test row")
    if score(records["frozen"]) != pre["baseline"]:
        raise ValueError("Frozen baseline changed after training")
    base_seed, n_boot = config["bootstrap_seed"], config["bootstrap_replicates"]
    kinds = ("PLAY_CARD", "ATTACK", "HERO_POWER", "END_TURN", "ACTIVATE_LOCATION")
    metrics = {name: {"all": record_stats(values, base_seed, n_boot),
                      "by_kind": {kind: score([record for record in values if record["kind"] == kind])
                                  for kind in kinds}, "latency": timings[name]}
               for name, values in records.items()}
    pairs = {f"{a}_to_{b}": paired_stats(records[a], records[b], base_seed, n_boot)
             for a, b in (("frozen", "retrained"), ("retrained", "hybrid"), ("frozen", "hybrid"))}
    observed = {source_card(action) for row in parts["train"] for action in row["legal_actions"]}
    observed.update(card["card_id"] for row in parts["train"] for card in row["state"]["self_hand"])
    seen = {}
    for name, values in records.items():
        chosen_card = [record for record in values if record["source_card_id"] is not None]
        seen[name] = {group: score([record for record in chosen_card
                                    if (record["source_card_id"] in observed) == known])
                      for group, known in (("seen", True), ("unseen", False))}
    coverage = Counter()
    for row in parts["test"]:
        _, mask = text_vectors.inputs(row)
        coverage["legal_total"] += len(mask)
        coverage["legal_usable"] += int(mask.sum())
        chosen = row["chosen_action_index"]
        coverage["chosen_total"] += 1
        coverage["chosen_usable"] += int(mask[chosen])
    result = {"data_identity_sha256": EXPECTED_DATA, "split_sha256": identity(split),
              "config_sha256": sha(CONFIG), "checkpoints": {"frozen": sha(FROZEN),
                  "retrained": sha(OUTPUT / "retrained_v2.pt"), "hybrid": sha(OUTPUT / "hybrid.pt")},
              "selected_epochs": {"retrained": epoch_b, "hybrid": epoch_c},
              "text_effect_max_logit_delta": text_effect, "metrics": metrics, "paired": pairs,
              "seen_source_cards": seen, "text_coverage": dict(coverage), "errors": errors,
              "cases": case_diagnostics(parts["test"], records),
              "interpretation": "development test, imitation only; no gameplay-strength claim"}
    write_new(OUTPUT / "results.json", result)
    print(json.dumps({"result": "COMPLETE", "checkpoints": result["checkpoints"],
                      "top1": {name: item["all"]["point"]["top1"] for name, item in metrics.items()},
                      "paired_top1": {name: item["second_minus_first"]["top1"] for name, item in pairs.items()}},
                     sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("preflight", "run"))
    args = parser.parse_args()
    try:
        if args.phase == "preflight":
            preflight()
        else:
            train_and_evaluate()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(json.dumps({"result": "FAILED", "phase": args.phase,
                          "reason": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
