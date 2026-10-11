"""TARGET-QUALITY-1 diagnostics; no action corrections or card interpretation."""
from __future__ import annotations

from collections import Counter

from manamind.training.policy_checkpoint import identity


def source_key(action: dict) -> tuple:
    """A concrete source in ONE snapshot, independent of target and insertion slot."""
    kind = action["type"]
    if kind == "END_TURN":
        return (kind,)
    card = action.get("source_card_id") or action.get("card_id")
    if kind == "PLAY_CARD":
        return (kind, action.get("source_kind"), card, action["hand_index"])
    if action.get("source_kind") in ("HERO", "HERO_POWER"):
        return (kind, action["source_kind"], card)
    return (kind, action.get("source_kind"), card, action["source_board_position"])


def target_key(action: dict) -> tuple:
    """Side + shared board position identifies the copy; card ID alone does not."""
    if "target_kind" not in action:
        return (None,)
    return (action["target_side"], action["target_kind"],
            action.get("target_board_position") if action["target_kind"] != "HERO" else None,
            action.get("target_card_id") if action["target_kind"] != "HERO" else None)


def sibling_key(action: dict) -> tuple:
    """Safe correction boundary: only target fields can differ (including slot stays)."""
    return tuple(sorted((k, v) for k, v in action.items() if not k.startswith("target_")))


def disagreement(predicted: dict, chosen: dict) -> str:
    if predicted == chosen:
        return "exact"
    if source_key(predicted) != source_key(chosen):
        return "different_source"
    different_target = target_key(predicted) != target_key(chosen)
    if different_target and sibling_key(predicted) == sibling_key(chosen):
        return "target_only"
    if different_target:
        return "target_and_other_fields"
    return "same_source_same_target_other_fields"


def case_id(row: dict) -> str:
    return identity({"state": row["state"], "legal_actions": row["legal_actions"]})[:16]


def summarize(rows: list[dict], orders: dict[str, list[int]]) -> dict:
    counts = Counter()
    conditional = Counter()
    for row in rows:
        actions = row["legal_actions"]
        chosen = actions[row["chosen_action_index"]]
        order = orders[row["decision_id"]]
        predicted = actions[order[0]]
        counts["decisions"] += 1
        counts["player_targeted"] += "target_kind" in chosen
        counts["policy_targeted"] += "target_kind" in predicted
        counts[disagreement(predicted, chosen)] += 1
        if source_key(predicted) == source_key(chosen):
            counts["same_source"] += 1
            counts["same_source_same_target"] += target_key(predicted) == target_key(chosen)
            available_targets = {target_key(a) for a in actions if sibling_key(a) == sibling_key(predicted)}
            if len(available_targets) > 1:
                counts["same_source_multi_target"] += 1
                counts["same_source_multi_target_match"] += target_key(predicted) == target_key(chosen)
        # Diagnostic teacher-forced source; NOT a deployable strategy / oracle correction.
        siblings = [i for i in order if sibling_key(actions[i]) == sibling_key(chosen)]
        if len({target_key(actions[i]) for i in siblings}) > 1:
            conditional["multi_target_source_decisions"] += 1
            conditional["target_match"] += target_key(actions[siblings[0]]) == target_key(chosen)
            conditional["exact_match"] += siblings[0] == row["chosen_action_index"]
            conditional["uniform_target_match_expected"] += 1 / len(siblings)
    return {"top1": dict(sorted(counts.items())), "given_player_source_and_slot": dict(sorted(conditional.items()))}
