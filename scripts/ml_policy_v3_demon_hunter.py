"""ML-POLICY-V3-1: HERO_POWER / END_TURN behaviour of cached Policy logits, per SELF class (default Demon Hunter).

Reads the logits cache written by ``ml_policy_v3_compare.py``; no training, no model changes. "Human choice" is the
recorded player action (description only, not a correct answer).
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ml_policy_v3_compare import decision_record  # noqa: E402
from manamind.training.policy_checkpoint import identity  # noqa: E402
from manamind.training.real_policy import load_examples  # noqa: E402

BUCKETS = (("1", 1, 1), ("2", 2, 2), ("3-4", 3, 4), ("5-6", 5, 6), ("7+", 7, 99))


def rate(count, total):
    return None if not total else count / total


def behaviour(records) -> dict:
    n = len(records)
    legal = [r for r in records if r["hero_power_legal"]]
    alternatives = [r for r in legal if any(k in ("PLAY_CARD", "ATTACK", "ACTIVATE_LOCATION") for k in r["kinds_in_menu"])]
    card_choice = [r for r in records if r["chosen_kind"] == "PLAY_CARD" and "card_above_hero_power" in r]
    acted = [r for r in records if r["chosen_kind"] != "END_TURN" and r["menu_size"] > 1]
    by_mana = {}
    for name, low, high in BUCKETS:
        part = [r for r in legal if low <= r["mana"] <= high]
        by_mana[name] = {"hero_power_legal_decisions": len(part),
                         "model_top1_hero_power": rate(sum(r["pred_kind"] == "HERO_POWER" for r in part), len(part)),
                         "human_hero_power": rate(sum(r["chosen_kind"] == "HERO_POWER" for r in part), len(part))}
    return {
        "decisions": n, "matches": len({r["game_id"] for r in records}),
        "top1_accuracy": rate(sum(r["rank"] == 1 for r in records), n),
        "hero_power_legal_decisions": len(legal),
        "model_top1_hero_power_share_all": rate(sum(r["pred_kind"] == "HERO_POWER" for r in records), n),
        "human_hero_power_share_all": rate(sum(r["chosen_kind"] == "HERO_POWER" for r in records), n),
        "model_top1_hero_power_share_when_legal": rate(sum(r["pred_kind"] == "HERO_POWER" for r in legal), len(legal)),
        "human_hero_power_share_when_legal": rate(sum(r["chosen_kind"] == "HERO_POWER" for r in legal), len(legal)),
        "hero_power_legal_with_card_or_attack_alternatives": len(alternatives),
        "model_top1_hero_power_with_alternatives": rate(sum(r["pred_kind"] == "HERO_POWER" for r in alternatives),
                                                        len(alternatives)),
        "human_hero_power_with_alternatives": rate(sum(r["chosen_kind"] == "HERO_POWER" for r in alternatives),
                                                   len(alternatives)),
        "hero_power_overuse_top1_hp_human_not": sum(r["pred_kind"] == "HERO_POWER" and r["chosen_kind"] != "HERO_POWER"
                                                    for r in records),
        "hero_power_underuse_human_hp_top1_not": sum(r["chosen_kind"] == "HERO_POWER" and r["pred_kind"] != "HERO_POWER"
                                                     for r in records),
        "human_played_card_and_hp_legal": len(card_choice),
        "best_card_ranked_above_hero_power": rate(sum(r["card_above_hero_power"] for r in card_choice), len(card_choice)),
        "by_available_mana": by_mana,
        "premature_end_turn_top1_end_turn_while_player_acted": sum(r["pred_kind"] == "END_TURN" for r in acted),
        "player_acted_decisions": len(acted),
        "late_end_turn_player_ended_top1_acted": sum(r["chosen_kind"] == "END_TURN" and r["pred_kind"] != "END_TURN"
                                                     for r in records),
        "player_ended_decisions": sum(r["chosen_kind"] == "END_TURN" for r in records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--klass", default="DEMONHUNTER")
    args = parser.parse_args()
    split = json.loads(args.split.read_text(encoding="utf-8"))
    rows = sorted(load_examples(args.dataset), key=lambda r: r["decision_id"])
    if identity(rows) != split["dataset_sha256"]:
        raise SystemExit("dataset differs from the frozen split")
    cache = pickle.loads(args.cache.read_bytes())
    part_of = {g: name for name, ids in split["game_ids"].items() for g in ids}
    selected = [r for r in rows if r["state"]["self_player"]["player_class"] == args.klass]
    sets = {"held_out_test": [r for r in selected if part_of[r["game_id"]] == "test"],
            "held_out_test_and_validation": [r for r in selected if part_of[r["game_id"]] in ("test", "validation")],
            "all_matches_of_class": selected}
    result = {"class": args.klass, "matches_by_part": {
        name: len({r["game_id"] for r in selected if part_of[r["game_id"]] == name}) for name in split["game_ids"]},
        "sets": {}}
    for set_name, set_rows in sets.items():
        result["sets"][set_name] = {model: behaviour([decision_record(r, logits[r["decision_id"]]) for r in set_rows])
                                    for model, logits in cache.items()}
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    for set_name, models in result["sets"].items():
        print("==", set_name)
        for model, b in models.items():
            print(f"  {model:<18} n={b['decisions']:>4} top1={b['top1_accuracy']:.3f} HPtop1={b['model_top1_hero_power_share_all']:.3f} "
                  f"HPhuman={b['human_hero_power_share_all']:.3f} HPover={b['hero_power_overuse_top1_hp_human_not']} "
                  f"HPunder={b['hero_power_underuse_human_hp_top1_not']} earlyEnd={b['premature_end_turn_top1_end_turn_while_player_acted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
