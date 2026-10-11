"""Agreement diagnostics and paired confidence intervals on whole real matches."""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from manamind.training.policy_metrics import summarize


def source_key(action):
    if action["type"] == "END_TURN":
        return None
    if action["type"] == "PLAY_CARD":
        return ("HAND", action.get("hand_index"), action.get("card_id"))
    return (action.get("source_kind"), action.get("source_is_hero"),
            action.get("source_board_position"), action.get("source_card_id"))


def target_key(action):
    if not action.get("target_kind"):
        return None
    return (action["target_side"], action["target_kind"], action.get("target_board_position"),
            action.get("target_card_id"))


def agreement(rows, records):
    if len(rows) != len(records) or not rows:
        raise ValueError("Aligned nonempty decisions are required")
    chosen = [row["legal_actions"][row["chosen_action_index"]] for row in rows]
    predicted = [row["legal_actions"][record["prediction_index"]] for row, record in zip(rows, records)]
    source = [i for i, action in enumerate(chosen) if source_key(action) is not None]
    targeted = [i for i, action in enumerate(chosen) if target_key(action) is not None]
    same_root = [i for i in targeted if chosen[i]["type"] == predicted[i]["type"]
                 and source_key(chosen[i]) == source_key(predicted[i])]

    def rate(indices, predicate):
        return {"matches": len({rows[i]["game_id"] for i in indices}), "decisions": len(indices),
                "correct": sum(predicate(i) for i in indices),
                "accuracy": sum(predicate(i) for i in indices) / len(indices) if indices else None}

    all_indices = list(range(len(rows)))
    side_present = [i for i in targeted if target_key(predicted[i]) is not None]
    false_end = [i for i in all_indices if predicted[i]["type"] == "END_TURN" and chosen[i]["type"] != "END_TURN"]
    return {"action_type": rate(all_indices, lambda i: chosen[i]["type"] == predicted[i]["type"]),
            "source": rate(source, lambda i: source_key(chosen[i]) == source_key(predicted[i])),
            "target": rate(targeted, lambda i: target_key(chosen[i]) == target_key(predicted[i])),
            "target_given_correct_type_source": rate(same_root, lambda i: target_key(chosen[i]) == target_key(predicted[i])),
            "target_side": rate(side_present, lambda i: chosen[i]["target_side"] == predicted[i]["target_side"]),
            "missing_target_predictions": len(targeted) - len(side_present),
            "predicted_type": dict(sorted(Counter(action["type"] for action in predicted).items())),
            "observed_type": dict(sorted(Counter(action["type"] for action in chosen).items())),
            "false_end_turn": {"matches": len({rows[i]["game_id"] for i in false_end}),
                               "decisions": len(false_end), "denominator": len(rows),
                               "nontrivial_denominator": sum(len(row["legal_actions"]) > 1 for row in rows)},
            "confusion": dict(sorted(Counter(f"{gold['type']}->{pred['type']}"
                                              for gold, pred in zip(chosen, predicted)).items()))}


def grouped_metrics(rows, records):
    if len(rows) != len(records):
        raise ValueError("Rows and predictions are not aligned")
    groups = defaultdict(list)
    for row, record in zip(rows, records):
        chosen = row["legal_actions"][row["chosen_action_index"]]
        keys = [("kind", chosen["type"]), ("class", row["state"]["self_player"]["player_class"]),
                ("unknown_hand", str(record["unknown_hand"])),
                ("chosen_unknown", str(record["chosen_unknown"])),
                ("nontrivial", str(len(row["legal_actions"]) > 1))]
        for key in keys:
            groups[key].append((row, record))
    return {field: {key: {**summarize([record for _, record in selected]),
                          "matches": len({row["game_id"] for row, _ in selected}),
                          "agreement": agreement([row for row, _ in selected], [record for _, record in selected])}
                    for (name, key), selected in sorted(groups.items()) if name == field}
            for field in ("kind", "class", "unknown_hand", "chosen_unknown", "nontrivial")}


def paired_bootstrap(rows, old_records, new_records, *, seed=20261011, draws=2000):
    if len(rows) != len(old_records) or len(rows) != len(new_records) or not rows:
        raise ValueError("Paired nonempty records are required")
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["game_id"]].append(index)
    games = sorted(groups)
    totals = np.array([[len(groups[game]),
                        sum(new_records[i]["loss"] - old_records[i]["loss"] for i in groups[game]),
                        sum((new_records[i]["rank"] == 1) - (old_records[i]["rank"] == 1) for i in groups[game])]
                       for game in games], dtype=float)
    rng = np.random.default_rng(seed)
    resampled = totals[rng.integers(0, len(games), size=(draws, len(games)))].sum(axis=1)
    estimates = resampled[:, 1:] / resampled[:, :1]
    return {"method": "paired whole-game bootstrap; decision-weighted delta new-minus-frozen",
            "matches": len(games), "decisions": len(rows), "seed": seed, "draws": draws,
            "cross_entropy_delta": float(totals[:, 1].sum() / totals[:, 0].sum()),
            "cross_entropy_delta_ci95": np.quantile(estimates[:, 0], [0.025, 0.975]).tolist(),
            "top1_delta": float(totals[:, 2].sum() / totals[:, 0].sum()),
            "top1_delta_ci95": np.quantile(estimates[:, 1], [0.025, 0.975]).tolist(),
            "game_macro_top1_delta": float(np.mean(totals[:, 2] / totals[:, 0])),
            "improved_games": int((totals[:, 2] > 0).sum()),
            "worsened_games": int((totals[:, 2] < 0).sum()), "tied_games": int((totals[:, 2] == 0).sum())}
