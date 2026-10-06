"""Supervised ranking metrics and aggregate diagnostics; no gameplay evaluation."""
from __future__ import annotations

import math
from collections import Counter, defaultdict

import torch

from manamind.training.real_policy import encode_example


def uniform_metrics(rows) -> dict:
    n = len(rows)
    sizes = [len(r["legal_actions"]) for r in rows]
    eligible = [k for k in sizes if k >= 3]
    return {"decisions": n, "cross_entropy": sum(math.log(k) for k in sizes) / n,
            "top1_accuracy": sum(1 / k for k in sizes) / n,
            "top3_accuracy": sum(3 / k for k in eligible) / len(eligible) if eligible else None,
            "top3_decisions": len(eligible),
            "mean_reciprocal_rank": sum(sum(1 / j for j in range(1, k+1)) / k for k in sizes) / n}


def summarize(records) -> dict:
    if not records:
        return {"decisions": 0}
    n = len(records)
    eligible = [r for r in records if r["menu_size"] >= 3]
    return {"decisions": n, "cross_entropy": sum(r["loss"] for r in records) / n,
            "top1_accuracy": sum(r["rank"] == 1 for r in records) / n,
            "top3_accuracy": sum(r["rank"] <= 3 for r in eligible) / len(eligible) if eligible else None,
            "top3_decisions": len(eligible),
            "mean_reciprocal_rank": sum(1 / r["rank"] for r in records) / n}


def action_root(action) -> tuple:
    # Diagnostic source/action agreement while leaving exact target/placement labels intact.
    return (action["type"], action.get("hand_index"), action.get("card_id"),
            action.get("source_card_id"), action.get("source_board_position"), action.get("source_is_hero"))


def evaluate(policy, rows, encoder) -> tuple:
    records = []
    policy.eval()
    with torch.no_grad():
        for row in rows:
            inputs = encode_example(row, encoder)
            logits = policy(*inputs)
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite policy evaluation logits")
            chosen = row["chosen_action_index"]
            order = torch.argsort(logits, descending=True, stable=True).tolist()
            action = row["legal_actions"][chosen]
            prediction = row["legal_actions"][order[0]]
            features, card_ids = inputs[1], inputs[3]
            collision = (features == features[chosen]).all(dim=1) & (card_ids == card_ids[chosen])
            unknown_hand = bool(inputs[2].eq(1).any())
            chosen_unknown = bool(card_ids[chosen] == 1) and action["type"] != "END_TURN"
            record = {"game_id": row["game_id"], "menu_size": len(order), "rank": order.index(chosen)+1,
                      "loss": torch.nn.functional.cross_entropy(logits[None], torch.tensor([chosen])).item(),
                      "kind": action["type"], "class": row["state"]["self_player"]["player_class"],
                      "unknown_hand": unknown_hand, "chosen_unknown": chosen_unknown,
                      "targeted": "target_kind" in action, "placement": action["play_position"] > 0,
                      "root_correct": action_root(action) == action_root(prediction),
                      "chosen_encoding_collision_size": int(collision.sum())}
            records.append(record)
    return summarize(records), records


def diagnostics(records) -> dict:
    groups = {}
    for field in ("kind", "class", "unknown_hand", "chosen_unknown", "targeted", "placement", "game_id"):
        bucket = defaultdict(list)
        for record in records:
            bucket[str(record[field])].append(record)
        groups[field] = {key: summarize(value) for key, value in sorted(bucket.items())}
    actionable = [r for r in records if r["menu_size"] > 1]
    groups["nontrivial"] = summarize(actionable)
    groups["root_accuracy"] = sum(r["root_correct"] for r in records) / len(records)
    groups["targeted_root_correct"] = sum(r["root_correct"] for r in records if r["targeted"])
    groups["placement_root_correct"] = sum(r["root_correct"] for r in records if r["placement"])
    groups["chosen_encoding_collisions"] = dict(Counter(r["chosen_encoding_collision_size"] for r in records))
    groups["collision_errors"] = sum(r["rank"] > 1 and r["chosen_encoding_collision_size"] > 1 for r in records)
    groups["errors"] = sum(r["rank"] > 1 for r in records)
    groups["singleton_decisions"] = sum(r["menu_size"] == 1 for r in records)
    return groups


def concentration(rows) -> dict:
    by_game = defaultdict(list)
    for row in rows:
        by_game[row["game_id"]].append(row)
    # Visible-hand identity overlap is not a full deck reconstruction.
    hands = {g: {c["card_id"] for r in rs for c in r["state"]["self_hand"]} for g, rs in by_game.items()}
    overlaps = []
    games = sorted(hands)
    for i, a in enumerate(games):
        for b in games[i+1:]:
            union = hands[a] | hands[b]
            overlaps.append(len(hands[a] & hands[b]) / len(union) if union else 0.0)
    return {"matches": len(games), "decisions": len(rows),
            "self_class_matches": dict(Counter(rs[0]["state"]["self_player"]["player_class"]
                                               for rs in by_game.values())),
            "opponent_class_matches": dict(Counter(rs[0]["state"]["opponent"]["player_class"]
                                                   for rs in by_game.values())),
            "mean_pairwise_visible_hand_jaccard": sum(overlaps) / len(overlaps) if overlaps else None,
            "chosen_kind": dict(Counter(r["legal_actions"][r["chosen_action_index"]]["type"] for r in rows))}
