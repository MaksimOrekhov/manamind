"""Small experiment helpers. No control access or production integration."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

import torch

from manamind.domain.serialization import game_state_from_dict
from manamind.models.policy_inputs import encode_policy_inputs
from manamind.training.policy_checkpoint import identity
from manamind.training.policy_metrics import summarize
from manamind.training.real_policy import validate_example
from manamind.training.tactical_certificates import set_loss


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def real_parts(directory, split):
    """Read only the listed train/validation matches, never real test bodies."""
    groups = {}
    for part in ("train", "validation"):
        rows = []
        for game in split["game_ids"][part]:
            batch = read_rows(Path(directory)/f"{game}.jsonl")
            if any(r["game_id"] != game for r in batch):
                raise ValueError("Wrong whole match")
            for row in batch:
                validate_example(row)
            rows.extend(batch)
        rows.sort(key=lambda r: r["decision_id"])
        if set(r["decision_id"] for r in rows) != set(split["decision_ids"][part]):
            raise ValueError("Real split decision identity mismatch")
        groups[part] = rows
    return groups


def labels(row):
    if "chosen_action_index" in row:
        return [row["chosen_action_index"]]
    wanted = {identity(a) for a in row["correct_actions"]}
    return [i for i, a in enumerate(row["legal_actions"]) if identity(a) in wanted]


def encode_rows(rows, encoder, device):
    return [(encode_policy_inputs(game_state_from_dict(r["state"]), r["legal_actions"], encoder,
                                  representation=2, device=device), labels(r)) for r in rows]


def source_key(a):
    if a["type"] == "PLAY_CARD":
        return (a["type"], a.get("hand_index"), a.get("card_id"))
    return (a["type"], a.get("source_kind"), a.get("source_is_hero"),
            a.get("source_board_position"), a.get("source_card_id"))


def target_key(a):
    return (a.get("target_kind"), a.get("target_side"), a.get("target_board_position"), a.get("target_card_id"))


def metrics(records):
    result = summarize(records)
    if not records:
        return result
    targeted = [r for r in records if r["gold_targeted"]]
    sourced = [r for r in records if r["gold_sourced"]]
    result.update(type_agreement=sum(r["type_correct"] for r in records)/len(records),
                  source_agreement=sum(r["source_correct"] for r in sourced)/len(sourced) if sourced else None,
                  source_decisions=len(sourced),
                  target_agreement=sum(r["target_correct"] for r in targeted)/len(targeted) if targeted else None,
                  target_decisions=len(targeted),
                  predicted_END=sum(r["predicted_type"] == "END_TURN" for r in records),
                  gold_END=sum(r["gold_type"] == "END_TURN" for r in records),
                  false_END=sum(r["predicted_type"] == "END_TURN" and not r["allows_END"] for r in records),
                  correct=sum(r["rank"] == 1 for r in records))
    return result


def evaluate(policy, rows, encoded):
    policy.eval()
    records, ambiguous = [], []
    with torch.inference_mode():
        for row, (inputs, gold) in zip(rows, encoded, strict=True):
            scores = policy(*inputs)
            if not torch.isfinite(scores).all():
                raise ValueError("Nonfinite logits")
            order = torch.argsort(scores, descending=True, stable=True).tolist()
            chosen = order[0]
            prediction = row["legal_actions"][chosen]
            base = {"id": row.get("scenario_id", row.get("decision_id")), "chosen_index": chosen,
                    "prediction": prediction, "scores": scores.cpu().tolist(),
                    "category": row.get("category"), "class": row["state"]["self_player"]["player_class"],
                    "certainty": row.get("certificate", {}).get("certainty", "IMITATION")}
            if not gold:
                ambiguous.append(base)
                continue
            wanted = [row["legal_actions"][i] for i in gold]
            rank = min(order.index(i)+1 for i in gold)
            records.append({**base, "rank": rank, "menu_size": len(order), "loss": set_loss(scores, gold).item(),
                            "gold_type": wanted[0]["type"], "predicted_type": prediction["type"],
                            "allows_END": any(a["type"] == "END_TURN" for a in wanted),
                            "gold_targeted": any("target_kind" in a for a in wanted),
                            "gold_sourced": any(a["type"] != "END_TURN" for a in wanted),
                            "type_correct": any(a["type"] == prediction["type"] for a in wanted),
                            "source_correct": any(source_key(a) == source_key(prediction) for a in wanted),
                            "target_correct": any(target_key(a) == target_key(prediction) for a in wanted)})
    by_class, by_category = defaultdict(list), defaultdict(list)
    for r in records:
        by_class[r["class"]].append(r)
        by_category[str(r["category"])].append(r)
    return {"overall": metrics(records), "by_class": {k: metrics(v) for k, v in by_class.items()},
            "by_category": {k: metrics(v) for k, v in by_category.items()},
            "records": records, "ambiguous": ambiguous}


class Stream:
    """Seeded reshuffling without loss of the real training pool."""
    def __init__(self, count, seed):
        if count < 1:
            raise ValueError("Empty sample pool")
        self.count, self.rng, self.pending = count, random.Random(seed), []

    def take(self, count):
        result = []
        while len(result) < count:
            if not self.pending:
                self.pending = list(range(self.count))
                self.rng.shuffle(self.pending)
            result.append(self.pending.pop())
        return result


def compact(result):
    return {k: v for k, v in result.items() if k not in {"records", "ambiguous"}}
