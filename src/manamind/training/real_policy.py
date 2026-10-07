"""Validated real policy examples, whole-match partitions and held-out metrics."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import torch

from manamind.cards.catalog import CardCatalog
from manamind.domain.serialization import game_state_from_dict
from manamind.domain.policy_action import ACTION_FIELDS, ACTION_TYPES
from manamind.live.snapshot import canonical_json, state_to_dict
from manamind.models.policy_inputs import encode_policy_inputs, representation_of

ROW_FIELDS = {"schema_version", "action_schema_version", "game_id", "decision_id", "state",
              "legal_actions", "chosen_action_index", "final_result", "source", "provenance"}
SKIP_REASONS = frozenset({"AMBIGUOUS_SELECTION", "TARGET_UNRESOLVED", "CHOICE_UNRESOLVED",
                          "OPTIONS_SUPERSEDED", "PARSE_ERROR", "SELF_AMBIGUOUS",
                          "UNSUPPORTED_DECISION_KIND", "NO_SELECTION"})


def validate_example(row: dict) -> None:
    if set(row) != ROW_FIELDS or row["schema_version"] != 1 or row["action_schema_version"] != 1:
        raise ValueError("Invalid real policy schema")
    if (row["source"] != "power_log_ranked_standard" or type(row["final_result"]) not in (int, float)
            or row["final_result"] not in (0.0, 0.5, 1.0)):
        raise ValueError("Invalid real policy source/result")
    if (not isinstance(row["game_id"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["game_id"])
            or not re.fullmatch(re.escape(row["game_id"]) + r":\d+", row["decision_id"])):
        raise ValueError("Invalid decision identity")
    state = game_state_from_dict(row["state"])
    if state_to_dict(state) != row["state"]:
        raise ValueError("Unexpected fields or noncanonical visible state")
    if (state.active_player != "SELF" or state.opponent_known_cards or state.pending_choice_owner is not None
            or state.opponent.known_secrets or state.self_player.known_secrets):
        raise ValueError("Real policy privacy/decision boundary violated")
    def check_identity(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("card_id") and item is not None:
                    if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_]+", item):
                        raise ValueError("Invalid public card identity")
                else:
                    check_identity(item)
        elif isinstance(value, list):
            for item in value:
                check_identity(item)
    check_identity(row["state"])
    actions = row["legal_actions"]
    chosen = row["chosen_action_index"]
    if not isinstance(actions, list) or not actions or type(chosen) is not int or not 0 <= chosen < len(actions):
        raise ValueError("Chosen action must be exactly one legal action")
    for action in actions:
        if (not isinstance(action, dict) or not set(action) <= ACTION_FIELDS
                or action.get("type") not in ACTION_TYPES):
            raise ValueError("Unexpected or unsupported semantic action fields")
        if action.get("target_side") not in (None, "SELF", "OPPONENT"):
            raise ValueError("Invalid target side")
        check_identity(action)
        for key, value in action.items():
            if key in {"type", "card_type", "source_kind", "target_kind", "target_side"} or key.endswith("card_id"):
                continue
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError("Invalid semantic numeric/boolean field")
        for key in ("card_type", "source_kind", "target_kind"):
            if action.get(key) not in (None, "HERO", "HERO_POWER", "MINION", "LOCATION", "SPELL", "WEAPON"):
                raise ValueError("Invalid semantic entity kind")
        if (type(action.get("play_position")) is not int or not 0 <= action["play_position"] <= 7
                or ("hand_index" in action and (type(action["hand_index"]) is not int
                                               or not 0 <= action["hand_index"] < len(state.self_hand)))):
            raise ValueError("Invalid action position")
    if len({canonical_json(action) for action in actions}) != len(actions):
        raise ValueError("Ambiguous duplicate semantic actions")
    if set(row["provenance"]) != {"options_line", "selection_line", "state_hash"}:
        raise ValueError("Unexpected provenance fields")
    if not 0 < row["provenance"]["options_line"] < row["provenance"]["selection_line"]:
        raise ValueError("Invalid provenance line order")
    from manamind.live.snapshot import state_hash
    if row["provenance"]["state_hash"] != state_hash(row["state"]):
        raise ValueError("State hash does not match provenance")


def load_examples(directory: Path) -> list[dict]:
    if (Path(directory) / "INVALIDATED.json").exists():
        raise ValueError("Dataset explicitly invalidated; diagnostic use only")
    rows, seen, seen_matches = [], set(), set()
    for path in sorted(Path(directory).glob("*.jsonl")):
        matches = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            validate_example(row)
            if row["decision_id"] in seen:
                raise ValueError("Duplicate decision")
            seen.add(row["decision_id"])
            matches.add(row["game_id"])
            rows.append(row)
        if len(matches) > 1:
            raise ValueError("Each input JSONL must contain exactly one match")
        if seen_matches & matches:
            raise ValueError("Duplicate match across dataset files")
        seen_matches.update(matches)
    return rows


def split_matches(rows: list[dict], seed: int = 1) -> dict[str, list[dict]]:
    """Deterministic outcome-stratified game split; never split a match's decisions.

    Three unique games are the minimum. Small strata start in training; whole
    matches are moved if needed to keep all partitions nonempty. Rare outcomes
    may not appear in every split.
    """
    groups, outcomes = defaultdict(list), defaultdict(list)
    for row in rows:
        validate_example(row)
        groups[row["game_id"]].append(row)
    if len(groups) < 3:
        raise ValueError("At least three whole matches required for train/validation/test")
    for game, decisions in groups.items():
        results = {row["final_result"] for row in decisions}
        if len(results) != 1:
            raise ValueError("Inconsistent match outcome")
        outcomes[next(iter(results))].append(game)
    partitions = {"train": [], "validation": [], "test": []}
    # Each sufficiently large outcome stratum contributes held-out whole matches.
    for result in sorted(outcomes):
        ordered = sorted(outcomes[result], key=lambda g: hashlib.sha256(f"{seed}:{g}".encode()).hexdigest())
        held = max(1, len(ordered) // 10) if len(ordered) >= 3 else 0
        for index, game in enumerate(ordered):
            name = "test" if index < held else "validation" if index < held * 2 else "train"
            partitions[name].extend(groups[game])
    for name in ("validation", "test"):
        if not partitions[name]:
            game = min({r["game_id"] for r in partitions["train"]})
            partitions[name] = groups[game]
            partitions["train"] = [row for row in partitions["train"] if row["game_id"] != game]
    return partitions


def encode_example(row, encoder, device="cpu", *, representation=1) -> tuple:
    validate_example(row)
    state = game_state_from_dict(row["state"])
    actions = row["legal_actions"]
    return encode_policy_inputs(state, actions, encoder, representation=representation, device=device)


def evaluate_held_out(policy, rows, encoder, training_game_ids: set[str]) -> dict:
    """Supervised metrics only on held-out whole matches, with legal-action masking."""
    if not rows or training_game_ids & {row["game_id"] for row in rows}:
        raise ValueError("Evaluation must use held-out whole matches")
    loss, top1, top3, top3_count, reciprocal = 0.0, 0, 0, 0, 0.0
    device = next(policy.parameters()).device
    policy.eval()
    with torch.no_grad():
        for row in rows:
            logits = policy(*encode_example(row, encoder, device, representation=representation_of(policy)))
            chosen = row["chosen_action_index"]
            loss += torch.nn.functional.cross_entropy(logits[None], torch.tensor([chosen], device=device)).item()
            order = torch.argsort(logits, descending=True, stable=True).tolist()
            rank = order.index(chosen) + 1
            top1 += rank == 1
            reciprocal += 1 / rank
            if len(order) >= 3:
                top3_count += 1
                top3 += rank <= 3
    return {"decisions": len(rows), "cross_entropy": loss / len(rows), "top1_accuracy": top1 / len(rows),
            "top3_accuracy": top3 / top3_count if top3_count else None,
            "top3_decisions": top3_count, "mean_reciprocal_rank": reciprocal / len(rows)}


def audit_dataset(directory: Path, catalog: CardCatalog) -> dict:
    rows = load_examples(directory)
    summaries = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.audit.json"))]
    for summary in summaries:
        expected = {"schema_version", "game_id", "final_result", "decisions_total", "decisions_labeled",
                    "decisions_skipped", "skip_reasons", "skipped_decisions"}
        if set(summary) != expected or summary["schema_version"] != 1:
            raise ValueError("Invalid match manifest schema")
        if not re.fullmatch(r"[0-9a-f]{64}", summary["game_id"]):
            raise ValueError("Invalid match identity")
        if not set(summary["skip_reasons"]) <= SKIP_REASONS:
            raise ValueError("Unexpected skip reason")
        if any(type(summary[k]) is not int or summary[k] < 0
               for k in ("decisions_total", "decisions_labeled", "decisions_skipped")):
            raise ValueError("Invalid match counts")
        skip_rows = summary["skipped_decisions"]
        if (len(skip_rows) != summary["decisions_skipped"]
                or dict(Counter(s["reason"] for s in skip_rows)) != summary["skip_reasons"]
                or any(set(s) != {"decision_id", "reason"} or s["reason"] not in SKIP_REASONS
                       or not s["decision_id"].startswith(summary["game_id"] + ":") for s in skip_rows)):
            raise ValueError("Invalid skipped decision manifest")
    by_game = {item["game_id"]: item for item in summaries}
    if len(by_game) != len(summaries):
        raise ValueError("Duplicate match manifest")
    grouped = Counter(row["game_id"] for row in rows)
    for game, count in grouped.items():
        if game not in by_game or by_game[game]["decisions_labeled"] != count:
            raise ValueError("Missing/inconsistent match audit manifest")
        if any(row["final_result"] != by_game[game]["final_result"] for row in rows if row["game_id"] == game):
            raise ValueError("Inconsistent manifest outcome")
    if any(grouped[g] != item["decisions_labeled"] for g, item in by_game.items()):
        raise ValueError("Missing match decisions")
    counts = [len(row["legal_actions"]) for row in rows]
    chosen = [row["legal_actions"][row["chosen_action_index"]] for row in rows]
    known = {card.card_id for card in catalog}
    identities = []
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("card_id") and item:
                    identities.append(item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    for row in rows:
        visit(row["state"])
        visit(row["legal_actions"])
    skips = Counter()
    for item in summaries:
        if item["decisions_total"] != item["decisions_labeled"] + item["decisions_skipped"]:
            raise ValueError("Inconsistent decision counts")
        skips.update(item["skip_reasons"])
    return {
        "unique_matches": len(by_game), "labeled_matches": len(grouped),
        "decisions_total": sum(s["decisions_total"] for s in summaries),
        "decisions_labeled": len(rows), "decisions_skipped": sum(skips.values()),
        "chosen_action_distribution": {k: sum(a["type"] == k for a in chosen) for k in sorted(ACTION_TYPES)},
        "legal_action_count": {"min": min(counts, default=0), "max": max(counts, default=0),
                               "mean": sum(counts) / len(counts) if counts else 0},
        "targeted_action_count": sum("target_kind" in a for a in chosen),
        "unknown_card_id_ratio": sum(c not in known for c in identities) / len(identities) if identities else 0,
        "identity_occurrences": len(identities), "skip_reasons": dict(sorted(skips.items())),
        "privacy_checks": "PASS", "split_readiness": "READY" if len(grouped) >= 3 else "INSUFFICIENT_MATCHES",
        "outcomes_by_match": dict(Counter(str(s["final_result"]) for s in summaries)),
    }
