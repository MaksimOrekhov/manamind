"""ML-POLICY-V3-1: readable frozen-test decisions where two cached models disagree on the top-1 action.

Selection is mechanical (largest cross-entropy gap per category), not hand-picked. No player names; card names come from
the public pinned catalog. Output is descriptive: the human action is a label for imitation, not a verdict on quality.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ml_policy_v3_compare import cached_logits, decision_record  # noqa: E402
from manamind.training.real_policy import load_examples  # noqa: E402


def names_from(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    records = payload.get("cards", []) if isinstance(payload, dict) else payload
    return {r["id"]: r["name"] for r in records if r.get("id") and r.get("name")}


def describe(action, names) -> str:
    def n(card_id):
        return names.get(card_id, card_id or "?")
    kind = action["type"]
    if kind == "END_TURN":
        return "END_TURN"
    if kind == "PLAY_CARD":
        text = f"PLAY {n(action['card_id'])} (cost {action.get('card_cost')})"
        if action.get("target_kind"):
            text += f" -> {action['target_side']} {n(action.get('target_card_id')) if action['target_kind'] != 'HERO' else 'HERO'}"
        return text + (f" @slot{action['play_position']}" if action["play_position"] else "")
    if kind == "HERO_POWER":
        text = f"HERO POWER {n(action.get('source_card_id'))}"
    elif kind == "ATTACK":
        source = "HERO" if action.get("source_is_hero") else n(action.get("source_card_id"))
        text = f"ATTACK {source}"
    else:
        text = f"{kind} {n(action.get('source_card_id') or action.get('card_id'))}"
    if action.get("target_kind"):
        text += f" -> {action['target_side']} {'HERO' if action['target_kind'] == 'HERO' else n(action.get('target_card_id'))}"
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--a", required=True, help="reference model as name=checkpoint (e.g. frozen_v2=...)")
    parser.add_argument("--b", required=True, help="model under study as name=checkpoint (e.g. v3_s42=...)")
    parser.add_argument("--per-category", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    split = json.loads(args.split.read_text(encoding="utf-8"))
    names = names_from(ROOT / "data/cards/standard_current_enUS.json")
    games = set(split["game_ids"]["test"])
    all_rows = sorted(load_examples(args.dataset), key=lambda r: r["decision_id"])
    rows = [r for r in all_rows if r["game_id"] in games]
    (name_a, path_a), (name_b, path_b) = (item.split("=", 1) for item in (args.a, args.b))
    cache = {name: cached_logits(args.cache_dir, Path(path), all_rows, split["dataset_sha256"])
             for name, path in ((name_a, path_a), (name_b, path_b))}
    args.a, args.b = name_a, name_b
    categories = {"b_matches_human_a_does_not": [], "a_matches_human_b_does_not": [], "neither_matches_human": []}
    for row in rows:
        if len(row["legal_actions"]) < 4:
            continue
        ra = decision_record(row, cache[args.a][row["decision_id"]])
        rb = decision_record(row, cache[args.b][row["decision_id"]])
        if ra["pred_index"] == rb["pred_index"]:
            continue
        key = ("b_matches_human_a_does_not" if rb["rank"] == 1 and ra["rank"] != 1 else
               "a_matches_human_b_does_not" if ra["rank"] == 1 and rb["rank"] != 1 else
               "neither_matches_human" if ra["rank"] != 1 and rb["rank"] != 1 else None)
        if key:
            categories[key].append((abs(ra["loss"] - rb["loss"]), row, ra, rb))
    result = {}
    for key, items in categories.items():
        items.sort(key=lambda t: (-t[0], t[1]["decision_id"]))
        result[key] = {"count": len(items), "examples": []}
        for _, row, ra, rb in items[:args.per_category]:
            state, actions = row["state"], row["legal_actions"]
            me = state["self_player"]
            result[key]["examples"].append({
                "decision_id": row["decision_id"][:12] + row["decision_id"][64:],
                "self_class": me["player_class"], "opponent_class": state["opponent"]["player_class"],
                "mana": me["available_mana"], "hand": [names.get(c["card_id"], c["card_id"]) for c in state["self_hand"]],
                "own_board": [f"{names.get(m['card']['card_id'], m['card']['card_id'])} {m['current_attack']}/{m['current_health']}"
                              for m in me["board"]],
                "enemy_board": [f"{names.get(m['card']['card_id'], m['card']['card_id'])} {m['current_attack']}/{m['current_health']}"
                                for m in state["opponent"]["board"]],
                "menu_size": len(actions), "human": describe(actions[row["chosen_action_index"]], names),
                f"{args.a}_top1": describe(actions[ra["pred_index"]], names), f"{args.a}_rank_of_human": ra["rank"],
                f"{args.b}_top1": describe(actions[rb["pred_index"]], names), f"{args.b}_rank_of_human": rb["rank"],
                "ce_gap": float(np.round(ra["loss"] - rb["loss"], 3))})
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1, ensure_ascii=False)
        stream.write("\n")
    for key, body in result.items():
        print(f"== {key}: {body['count']} decisions")
        for e in body["examples"]:
            print(f"  [{e['self_class']} vs {e['opponent_class']}, mana {e['mana']}] human: {e['human']} | "
                  f"{args.a}: {e[args.a + '_top1']} (rank {e[args.a + '_rank_of_human']}) | "
                  f"{args.b}: {e[args.b + '_top1']} (rank {e[args.b + '_rank_of_human']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
