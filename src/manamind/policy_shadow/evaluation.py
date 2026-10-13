"""MODEL-SHADOW-EVAL-1: score the model-shadow rankings against the action the player really took (offline).

Inputs are plain data: model-shadow journal rows and, per match, the labeled decisions the Policy importer
(``manamind.integrations.powerlog.policy_import``) recovered from the completed Power.log. A shadow row is paired with a
label only when the match id, ``options_id``, ``state_hash`` and the complete ordered legal menu all agree; every other
row is skipped with a stable reason. Nothing is guessed, nothing is trained and no file is written here.

What this measures is *agreement with a human who was shown Policy v2's Top-3 while playing*. It is not playing strength,
the human choice is not declared optimal, and Policy v2 has an exposure advantage (its advice was on screen).
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from manamind.live.snapshot import canonical_json
from manamind.policy_shadow.shadow import action_sha

SCHEMA = "manamind.model_shadow_eval/1"
BOOTSTRAP_SEED = 20261013
BOOTSTRAP_RESAMPLES = 5000
HERO_POWER_MANA = (("<=1", 0, 1), ("2", 2, 2), ("3-4", 3, 4), ("5+", 5, 99))
REQUIRED_ROW_KEYS = ("match_id", "options_id", "state_hash", "menu_sha256", "menu_size", "actions", "models")


@dataclass
class MatchLabels:
    """What the Policy importer made of one completed log: its labeled examples and its own skipped decisions."""
    examples: list[dict] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)        # options_id (text) -> importer reason
    import_error: str | None = None                              # the whole match was refused (stable code)

    @classmethod
    def from_import(cls, examples: list[dict], summary: dict) -> MatchLabels:
        skipped = {row["decision_id"].rsplit(":", 1)[1]: row["reason"] for row in summary.get("skipped_decisions", [])}
        return cls(examples=list(examples), skipped=skipped)


# -- pairing -----------------------------------------------------------------------------------------------------


def menu_digest(actions: list[dict]) -> str:
    return hashlib.sha256(canonical_json(actions).encode("utf-8")).hexdigest()


def _valid_ranks(ranks, size: int) -> bool:
    return (isinstance(ranks, list) and len(ranks) == size
            and sorted(r for r in ranks if isinstance(r, int) and not isinstance(r, bool)) == list(range(1, size + 1)))


def _row_problem(row: dict, models: list[str]) -> str | None:
    if row.get("event") != "MODEL_SHADOW" or any(key not in row for key in REQUIRED_ROW_KEYS):
        return "SHADOW_ROW_MALFORMED"
    size = row["menu_size"]
    if (not isinstance(size, int) or size < 1 or not isinstance(row["actions"], list) or len(row["actions"]) != size
            or not isinstance(row["models"], list)):
        return "SHADOW_ROW_MALFORMED"
    entries = {entry.get("name"): entry for entry in row["models"] if isinstance(entry, dict)}
    for name in models:
        entry = entries.get(name)
        if entry is None:
            return f"MODEL_MISSING:{name}"
        if entry.get("status") != "OK":
            return f"MODEL_NOT_OK:{name}:{entry.get('status')}"
        if not _valid_ranks(entry.get("ranks"), size):
            return f"MODEL_INVALID_RANKS:{name}"
    return None


def _content(row: dict) -> tuple:
    return (row.get("menu_sha256"), json.dumps(sorted((e.get("name"), e.get("checkpoint_sha256"), tuple(e.get("ranks", ())))
                                                       for e in row.get("models", []) if isinstance(e, dict)), default=str))


def _label_problem(row: dict, labels: MatchLabels | None) -> tuple[str | None, dict | None]:
    if labels is None:
        return "NO_POWER_LOG", None
    if labels.import_error is not None:
        return f"IMPORT_FAILED:{labels.import_error}", None
    option = str(row["options_id"])
    found = [e for e in labels.examples if e["decision_id"].rsplit(":", 1)[1] == option]
    if len(found) > 1:
        return "AMBIGUOUS_LABEL", None
    if not found:
        reason = labels.skipped.get(option)
        return (f"IMPORTER_SKIPPED:{reason}" if reason else "NO_LABEL"), None
    example = found[0]
    if example.get("game_id") != row["match_id"]:
        return "MATCH_ID_MISMATCH", None
    if example["provenance"]["state_hash"] != row["state_hash"]:
        return "STATE_HASH_MISMATCH", None
    actions = example["legal_actions"]
    if len(actions) != row["menu_size"]:
        return "MENU_MISMATCH", None
    if menu_digest(actions) != row["menu_sha256"] or [action_sha(a) for a in actions] != [a.get("sha") for a in row["actions"]]:
        mine, theirs = sorted(action_sha(a) for a in actions), sorted(a.get("sha") for a in row["actions"])
        return ("MENU_ORDER_MISMATCH" if mine == theirs else "MENU_MISMATCH"), None
    chosen = example["chosen_action_index"]
    if not isinstance(chosen, int) or isinstance(chosen, bool) or not 0 <= chosen < len(actions):
        return "CHOSEN_ACTION_INVALID", None
    return None, example


def _checkpoint_mismatch(row: dict, expected: dict[str, str]) -> list[str]:
    entries = {e.get("name"): e for e in row.get("models", []) if isinstance(e, dict)}
    return [name for name, sha in expected.items() if name in entries and entries[name].get("checkpoint_sha256") != sha]


def match_decisions(shadow_rows: list[dict], labels: dict[str, MatchLabels], models: list[str],
                    training_games: dict[str, set[str]] | None = None,
                    checkpoints: dict[str, str] | None = None) -> dict:
    """Pair every shadow row with its confirmed label or give it exactly one skip reason.

    ``training_games`` maps a model name to the match ids its checkpoint trained or was selected on; a match any model
    saw is ``TRAINING_OVERLAP`` and never enters the independent metrics. ``checkpoints`` maps a model name to the SHA-256
    of the checkpoint file those training splits were read from: a match with any row whose journaled digest differs (or
    that mixes versions) is ``CHECKPOINT_MISMATCH``, because its training split would then say nothing about that model.
    """
    training_games = training_games or {}
    overlapping = {match for games in training_games.values() for match in games}
    rows = [r for r in shadow_rows if isinstance(r, dict) and r.get("event") == "MODEL_SHADOW"]
    unverified = {r.get("match_id") for r in rows if checkpoints and _checkpoint_mismatch(r, checkpoints)}
    groups: dict[tuple, list[int]] = defaultdict(list)
    for position, row in enumerate(rows):
        groups[(row.get("match_id"), str(row.get("options_id")), row.get("state_hash"))].append(position)
    skipped, matched, collapsed = [], [], []

    def skip(row: dict, reason: str) -> None:
        skipped.append({"match_id": row.get("match_id"), "decision_id": row.get("decision_id"), "reason": reason})

    for position, row in enumerate(rows):
        group = groups[(row.get("match_id"), str(row.get("options_id")), row.get("state_hash"))]
        if len(group) > 1:
            if len({_content(rows[p]) for p in group}) > 1:
                skip(row, "CONFLICTING_DUPLICATE_SHADOW_ROWS")
                continue
            if position != group[0]:                 # LIVE re-emitted the same decision (new seq): not a second decision
                collapsed.append({"match_id": row.get("match_id"), "decision_id": row.get("decision_id")})
                continue
        problem = _row_problem(row, models)
        if problem:
            skip(row, problem)
            continue
        if row["match_id"] in unverified:
            skip(row, "CHECKPOINT_MISMATCH")
            continue
        if row["match_id"] in overlapping:
            skip(row, "TRAINING_OVERLAP")
            continue
        problem, example = _label_problem(row, labels.get(row["match_id"]))
        if problem:
            skip(row, problem)
            continue
        entries = {e["name"]: e for e in row["models"]}
        ranks = {name: entries[name]["ranks"] for name in models}
        chosen = example["chosen_action_index"]
        matched.append({"row": row, "example": example, "actions": example["legal_actions"], "chosen": chosen,
                        "ranks": ranks, "rank": {name: ranks[name][chosen] for name in models},
                        "top1": {name: ranks[name].index(1) for name in models}})
    seen = {(r.get("match_id"), str(r.get("options_id"))) for r in rows}
    labeled_without_shadow = [
        {"match_id": match, "decision_id": e["decision_id"]}
        for match, lab in sorted(labels.items()) if lab.import_error is None for e in lab.examples
        if (match, e["decision_id"].rsplit(":", 1)[1]) not in seen]
    return {"matched": matched, "skipped": skipped, "collapsed_duplicates": collapsed, "labeled_without_shadow": labeled_without_shadow,
            "shadow_rows": len(rows)}


def explain_unshadowed(missing: list[dict], events: list[dict] | None) -> dict:
    """Why labeled decisions have no shadow row, joined by match id + options_id to journal events (never guessed).

    Counts are of decisions; ``events`` counts the journal events behind them (one decision can carry several, and a
    journal event may belong to a decision that was not labeled at all, so the two numbers are not comparable).
    """
    if events is None:
        return {"status": "EVENTS_NOT_PROVIDED", "decisions": len(missing)}
    wanted = {"RECOMMENDATION", "UNAVAILABLE", "DISCARDED", "MODEL_SHADOW_ERROR", "MODEL_SHADOW_DISCARDED"}
    index: dict[tuple, list[str]] = defaultdict(list)
    for event in events:
        parts = str(event.get("decision_id", "")).split(":")
        kind = event.get("event")
        if kind in wanted and len(parts) >= 3:
            index[(event.get("match_id"), parts[2])].append(f"{kind}:{event['reason']}" if event.get("reason") else kind)
    decisions, behind = Counter(), Counter()
    for item in missing:
        found = sorted(set(index.get((item["match_id"], item["decision_id"].rsplit(":", 1)[1]), [])))
        decisions["+".join(found) if found else "NO_JOURNAL_EVENT_FOR_DECISION"] += 1
        behind.update(index.get((item["match_id"], item["decision_id"].rsplit(":", 1)[1]), []))
    return {"status": "OK", "decisions": len(missing), "by_decision": dict(sorted(decisions.items())),
            "journal_events_behind_these_decisions": dict(sorted(behind.items()))}


# -- metrics -----------------------------------------------------------------------------------------------------


def _share(count: int, total: int) -> float | None:
    return round(count / total, 6) if total else None


def _harmonic(n: int) -> float:
    return sum(1 / k for k in range(1, n + 1))


def rank_metrics(ranks: list[int], sizes: list[int]) -> dict:
    """Top-1 and MRR over every decision; Top-3 only over menus of 3+ actions (in a smaller menu it is trivially 100%)."""
    n = len(ranks)
    if not n:
        return {"decisions": 0}
    arr = np.asarray(ranks)
    wide = np.asarray(sizes) >= 3
    top3_n = int(wide.sum())
    top3_hits = int((arr[wide] <= 3).sum())
    return {"decisions": n, "top1_hits": int((arr == 1).sum()), "top1": _share(int((arr == 1).sum()), n),
            "top3_decisions": top3_n, "top3_hits": top3_hits, "top3": _share(top3_hits, top3_n),
            "mrr": round(float((1 / arr).mean()), 4), "mean_rank": round(float(arr.mean()), 3),
            "median_rank": float(np.median(arr)),
            "chance": {"top1": round(float(np.mean([1 / s for s in sizes])), 4),
                       "top3": round(float(np.mean([3 / s for s in sizes if s >= 3])), 4) if top3_n else None,
                       "mrr": round(float(np.mean([_harmonic(s) / s for s in sizes])), 4)}}


def slice_metrics(items: list[dict], models: list[str]) -> dict:
    sizes = [m["row"]["menu_size"] for m in items]
    return {name: rank_metrics([m["rank"][name] for m in items], sizes) for name in models}


SLICES = (("all", lambda m: True), ("nontrivial_menu_2plus", lambda m: m["row"]["menu_size"] >= 2),
          ("large_menu_5plus", lambda m: m["row"]["menu_size"] >= 5))


def metric_tables(items: list[dict], models: list[str]) -> dict:
    return {label: {"decisions": len(sub), **{"models": slice_metrics(sub, models)}}
            for label, test in SLICES for sub in [[m for m in items if test(m)]]}


def _binomial_two_sided(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_comparison(items: list[dict], a: str, b: str, *, seed: int = BOOTSTRAP_SEED,
                      resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Model ``a`` minus model ``b`` on the same decisions. Decisions of one match are correlated: the CI is optimistic."""
    ra = np.array([m["rank"][a] for m in items], dtype=float)
    rb = np.array([m["rank"][b] for m in items], dtype=float)
    n = len(items)
    if n == 0:
        return {"decisions": 0, "verdict": "NO_DATA"}
    top1 = (ra == 1).astype(float) - (rb == 1).astype(float)
    mrr = 1 / ra - 1 / rb
    only_a, only_b = int((top1 > 0).sum()), int((top1 < 0).sum())
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, n, size=(resamples, n))
    boot = mrr[picks].mean(axis=1)
    low, high = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
    matches = [m["row"]["match_id"] for m in items]
    per_match, leave_out = {}, {}
    for match in sorted(set(matches)):
        inside = np.array([x == match for x in matches])
        per_match[match[:8]] = {"decisions": int(inside.sum()), "top1_diff": round(float(top1[inside].mean()), 4),
                                "mrr_diff": round(float(mrr[inside].mean()), 4)}
        rest = ~inside
        leave_out[match[:8]] = ({"top1_diff": round(float(top1[rest].mean()), 4), "mrr_diff": round(float(mrr[rest].mean()), 4)}
                                if rest.any() else None)
    p_top1 = _binomial_two_sided(min(only_a, only_b), only_a + only_b)
    significant = (low > 0 or high < 0) or p_top1 < 0.05
    signs = {math.copysign(1, v["mrr_diff"]) for v in per_match.values() if v["mrr_diff"] != 0 and v["decisions"] >= 5}
    if not significant:
        verdict = "INCONCLUSIVE"
    elif len(signs) == 1 and len(per_match) >= 2:
        verdict = "SUGGESTIVE_NOT_ESTABLISHED"
    else:
        verdict = "UNSTABLE_ACROSS_MATCHES"
    return {"decisions": n, "matches": len(per_match), "a": a, "b": b,
            "top1": {"both": int(((ra == 1) & (rb == 1)).sum()), f"only_{a}": only_a, f"only_{b}": only_b,
                     "neither": int(((ra != 1) & (rb != 1)).sum()), "mean_diff": round(float(top1.mean()), 4),
                     "exact_sign_test_p": round(p_top1, 4)},
            "mrr": {"mean_diff": round(float(mrr.mean()), 4), "bootstrap95": [round(low, 4), round(high, 4)],
                    "resamples": resamples, "seed": seed},
            "per_match": per_match, "leave_one_match_out": leave_out, "verdict": verdict}


# -- categories (what kind of action the player took vs what each model put first) -------------------------------


def action_text(action: dict, names: dict[str, str]) -> str:
    def name(card_id):
        return names.get(card_id, card_id) if card_id else "?"
    kind = action["type"]
    if kind == "END_TURN":
        return "END_TURN"
    target = ""
    if "target_kind" in action:
        who = "enemy" if action.get("target_side") == "OPPONENT" else "own"
        target = f" -> {who} {'hero' if action['target_kind'] == 'HERO' else name(action.get('target_card_id'))}"
    if kind == "ATTACK":
        source = "hero" if action.get("source_is_hero") else name(action.get("source_card_id"))
        return f"ATTACK {source}{target}"
    if kind == "HERO_POWER":
        return f"HERO_POWER {name(action.get('card_id'))}{target}"
    position = f" @{action['play_position']}" if action.get("play_position") else ""
    return f"{kind} {name(action.get('card_id') or action.get('source_card_id'))}{target}{position}"


def _root(action: dict) -> tuple:
    return (action["type"], action.get("hand_index"), action.get("card_id"), action.get("source_card_id"),
            action.get("source_board_position"), action.get("source_is_hero"))


def _target(action: dict) -> tuple | None:
    if "target_kind" not in action:
        return None
    return (action["target_kind"], action.get("target_side"), action.get("target_board_position"),
            action.get("target_card_id"))


def _target_class(action: dict) -> str:
    if action.get("target_kind") == "HERO" and action.get("target_side") == "OPPONENT":
        return "FACE"
    if action.get("target_kind") == "HERO":
        return "OWN_HERO"
    return "MINION" if action.get("target_kind") else "NONE"


def _tops(m: dict, name: str) -> dict:
    return m["actions"][m["top1"][name]]


def _chosen(m: dict) -> dict:
    return m["actions"][m["chosen"]]


def _kind_report(items: list[dict], models: list[str], chosen_kind: str) -> dict:
    """Decisions where the player took ``chosen_kind``: what each model put first."""
    mine = [m for m in items if _chosen(m)["type"] == chosen_kind]
    out = {"player_chose": len(mine), "models": {}}
    for name in models:
        counts = Counter()
        for m in mine:
            top, chosen = _tops(m, name), _chosen(m)
            if m["top1"][name] == m["chosen"]:
                counts["exact_action"] += 1
            elif top["type"] != chosen_kind:
                counts[f"top1_is_{top['type']}"] += 1
            elif _root(top) == _root(chosen):
                counts["same_source_other_target_or_position"] += 1
            else:
                counts["other_source_or_card"] += 1
        out["models"][name] = {"top1_exact": counts["exact_action"], "top1_exact_share": _share(counts["exact_action"], len(mine)),
                               "breakdown": dict(sorted(counts.items())),
                               "mean_rank_of_chosen": (round(float(np.mean([m["rank"][name] for m in mine])), 3) if mine else None)}
    return out


def _hero_power_report(items: list[dict], models: list[str]) -> dict:
    legal = [m for m in items if any(a["type"] == "HERO_POWER" for a in m["actions"])]

    def stats(sub: list[dict]) -> dict:
        taken = [m for m in sub if _chosen(m)["type"] == "HERO_POWER"]
        out = {"available": len(sub), "player_used": len(taken), "player_used_share": _share(len(taken), len(sub)), "models": {}}
        for name in models:
            top = [m for m in sub if _tops(m, name)["type"] == "HERO_POWER"]
            over = [m for m in top if _chosen(m)["type"] != "HERO_POWER"]
            under = [m for m in taken if _tops(m, name)["type"] != "HERO_POWER"]
            out["models"][name] = {"top1_hero_power": len(top), "top1_share": _share(len(top), len(sub)),
                                   "hits_top1_and_used": len(top) - len(over), "overestimated_top1_but_not_used": len(over),
                                   "underestimated_used_but_not_top1": len(under)}
        return out

    return {"overall": stats(legal),
            "by_available_mana": {label: stats([m for m in legal if low <= m["row"]["mana"] <= high])
                                  for label, low, high in HERO_POWER_MANA}}


def _end_turn_report(items: list[dict], models: list[str]) -> dict:
    multi = [m for m in items if m["row"]["menu_size"] > 1]
    ended = [m for m in multi if _chosen(m)["type"] == "END_TURN"]
    out = {"decisions_with_alternatives": len(multi), "player_ended_turn": len(ended), "models": {}}
    for name in models:
        early = [m for m in multi if _tops(m, name)["type"] == "END_TURN" and _chosen(m)["type"] != "END_TURN"]
        missed = [m for m in ended if _tops(m, name)["type"] != "END_TURN"]
        out["models"][name] = {"top1_end_turn": sum(_tops(m, name)["type"] == "END_TURN" for m in multi),
                               "model_ends_turn_player_continues": len(early),
                               "player_ends_turn_model_suggests_other": len(missed),
                               "both_end_turn": len(ended) - len(missed),
                               "mean_rank_of_end_turn_when_player_ended":
                                   (round(float(np.mean([m["rank"][name] for m in ended])), 3) if ended else None)}
    return out


def _target_report(items: list[dict], models: list[str]) -> dict:
    targeted = [m for m in items if "target_kind" in _chosen(m)]
    out = {"player_chose_targeted_action": len(targeted), "models": {}}
    for name in models:
        counts = Counter()
        confusion: dict[str, Counter] = defaultdict(Counter)
        for m in targeted:
            top, chosen = _tops(m, name), _chosen(m)
            if m["top1"][name] == m["chosen"]:
                counts["exact"] += 1
            elif _root(top) == _root(chosen):
                counts["right_source_wrong_target"] += 1
            else:
                counts["other_source_or_card"] += 1
            if chosen["type"] == "ATTACK" and top["type"] == "ATTACK":
                confusion[_target_class(chosen)][_target_class(top)] += 1
        out["models"][name] = {**dict(sorted(counts.items())),
                               "attack_target_class_player_vs_model_top1_when_both_attack":
                                   {k: dict(v) for k, v in sorted(confusion.items())}}
    return out


def _play_card_report(items: list[dict], models: list[str]) -> dict:
    out = _kind_report(items, models, "PLAY_CARD")
    for name in models:
        counts = Counter()
        for m in items:
            if _chosen(m)["type"] != "PLAY_CARD" or _tops(m, name)["type"] != "PLAY_CARD":
                continue
            same_card = _root(_tops(m, name)) == _root(_chosen(m))
            counts["same_card" if same_card else "different_card"] += 1
        out["models"][name]["when_both_play_a_card"] = dict(counts)
    return out


def _confusion(items: list[dict], models: list[str]) -> dict:
    return {name: {kind: dict(Counter(_tops(m, name)["type"] for m in items if _chosen(m)["type"] == kind))
                   for kind in sorted({_chosen(m)["type"] for m in items})} for name in models}


def state_summary(state: dict, names: dict[str, str]) -> str:
    def card(entity):
        c = entity.get("card", entity)
        return f"{names.get(c.get('card_id'), c.get('card_id'))} {c.get('current_attack', c.get('attack'))}/{c.get('current_health', c.get('health'))}"
    me, opp = state["self_player"], state["opponent"]
    hand = ", ".join(f"{names.get(c.get('card_id'), c.get('card_id'))}({c.get('current_cost', c.get('cost'))})"
                     for c in state.get("self_hand", []))
    return (f"turn {state.get('turn_number')}, mana {me['available_mana']}/{me['max_mana']}; "
            f"me {me['hero_health']}+{me['armor']} hp, board [{', '.join(card(e) for e in me['board'])}], hand [{hand}]; "
            f"opponent {opp['player_class']} {opp['hero_health']}+{opp['armor']} hp, board [{', '.join(card(e) for e in opp['board'])}], "
            f"hand {opp['hand_size']}")


def disagreements(items: list[dict], models: list[str], names: dict[str, str], examples: int) -> dict:
    """Decisions where the models' first choices differ in substance (another action kind, card or source)."""
    found = []
    for m in items:
        roots = {_root(_tops(m, n)) for n in models}
        if len(roots) < 2:
            continue
        agree_with_player = [n for n in models if m["top1"][n] == m["chosen"]]
        spread = max(m["rank"].values()) - min(m["rank"].values())
        found.append((len(roots), len(agree_with_player) == 1, spread, m))
    found.sort(key=lambda t: (-t[0], -t[1], -t[2], t[3]["row"]["decision_id"]))
    kinds = Counter(tuple(sorted({_tops(t[3], n)["type"] for n in models})) for t in found)
    listing = []
    for _, _, spread, m in found[:examples]:
        listing.append({
            "decision_id": m["row"]["decision_id"], "match": m["row"]["match_id"][:8], "turn": m["row"]["turn"],
            "state": state_summary(m["example"]["state"], names), "menu_size": m["row"]["menu_size"],
            "player_chose": action_text(_chosen(m), names),
            "models": {n: {"top1": action_text(_tops(m, n), names), "rank_of_player_choice": m["rank"][n]} for n in models}})
    return {"decisions_with_different_top1_substance": len(found),
            "of_which_all_models_differ": sum(t[0] == len(models) for t in found),
            "top1_type_combinations": {"+".join(k): v for k, v in sorted(kinds.items())}, "examples": listing}


# -- report ------------------------------------------------------------------------------------------------------


def evaluate(shadow_rows: list[dict], labels: dict[str, MatchLabels], models: list[str], *,
             training_games: dict[str, set[str]] | None = None, checkpoints: dict[str, str] | None = None,
             prediction_rows: list[dict] | None = None, names: dict[str, str] | None = None,
             examples: int = 6, self_class: str = "DEMONHUNTER") -> dict:
    names = names or {}
    paired = match_decisions(shadow_rows, labels, models, training_games, checkpoints)
    matched, skipped = paired["matched"], paired["skipped"]
    total, collapsed = paired["shadow_rows"], len(paired["collapsed_duplicates"])
    distinct = total - collapsed
    reasons = Counter(s["reason"] for s in skipped)
    by_match_total, by_match_ok = Counter(), Counter()
    for row in (r for r in shadow_rows if r.get("event") == "MODEL_SHADOW"):
        by_match_total[row.get("match_id")] += 1
    for m in matched:
        by_match_ok[m["row"]["match_id"]] += 1
    klass_items = [m for m in matched if m["row"]["self_class"] == self_class]
    journal_shas: dict[str, set] = defaultdict(set)
    for row in (r for r in shadow_rows if r.get("event") == "MODEL_SHADOW"):
        for entry in row.get("models", []):
            if isinstance(entry, dict):
                journal_shas[entry.get("name")].add(entry.get("checkpoint_sha256"))
    unverified_matches = {s["match_id"] for s in skipped if s["reason"] == "CHECKPOINT_MISMATCH"}
    overlap = {match: [n for n, games in sorted((training_games or {}).items()) if match in games]
               for match in sorted(by_match_total) if any(match in g for g in (training_games or {}).values())}
    nontrivial = [m for m in matched if m["row"]["menu_size"] >= 2]
    ordering = sorted(models, key=lambda n: -(float(np.mean([1 / m["rank"][n] for m in nontrivial])) if nontrivial else 0.0))
    report = {
        "schema": SCHEMA, "models": models,
        "claims": ["Agreement with the player's real action, not playing strength; the player is not assumed optimal.",
                   "The player saw Policy v2's Top-3 during play, which can favour policy_v2 (exposure, not independence).",
                   "Few matches of one player and one class: differences are descriptive, not an established ranking."],
        "coverage": {"shadow_rows": total, "duplicate_rows_collapsed": collapsed, "distinct_decisions": distinct,
                     "matched": len(matched), "matched_share_of_distinct": _share(len(matched), distinct),
                     "matched_share_of_rows": _share(len(matched), total), "skipped": len(skipped), "skip_reasons": dict(sorted(reasons.items())),
                     "labeled_decisions_without_shadow_row": len(paired["labeled_without_shadow"]),
                     "labeled_without_shadow_explained": explain_unshadowed(
                         paired["labeled_without_shadow"], None if prediction_rows is None else [*prediction_rows, *shadow_rows]),
                     "per_match": {mid[:8]: {"shadow_rows": by_match_total[mid], "matched": by_match_ok[mid]}
                                   for mid in sorted(by_match_total)},
                     "matches_in_journal": len(by_match_total), "matches_with_power_log": sum(
                         1 for mid in by_match_total if mid in labels and labels[mid].import_error is None)},
        "independence": {"training_overlap_matches": {m[:8]: v for m, v in overlap.items()},
                         "checked_models": sorted(training_games or {}),
                         "checkpoint_identity_verified": checkpoints is not None and not unverified_matches,
                         "checkpoint_identity": {n: {"expected_sha256": sha, "journal_sha256": sorted(journal_shas.get(n, ()))}
                                                 for n, sha in sorted((checkpoints or {}).items())},
                         "checkpoint_mismatch_matches": sorted(m[:8] for m in unverified_matches)},
        "metrics": metric_tables(matched, models),
        "ranking_by_mrr_nontrivial": ordering,
        "per_match": {mid[:8]: metric_tables([m for m in matched if m["row"]["match_id"] == mid], models)
                      for mid in sorted({m["row"]["match_id"] for m in matched})},
        "reliability": {f"{a}_vs_{b}": paired_comparison(nontrivial, a, b)
                        for i, a in enumerate(models) for b in models[i + 1:]},
        "self_class": self_class, "self_class_decisions": len(klass_items),
        "categories": {"hero_power": _hero_power_report(klass_items, models),
                       "attack": _kind_report(klass_items, models, "ATTACK"),
                       "play_card": _play_card_report(klass_items, models),
                       "end_turn": _end_turn_report(klass_items, models),
                       "targets": _target_report(klass_items, models),
                       "player_action_vs_model_top1_type": _confusion(klass_items, models)},
        "model_disagreements": disagreements(klass_items, models, names, examples),
        "matched_decisions": [{"decision_id": m["row"]["decision_id"], "chosen_index": m["chosen"],
                               "chosen_type": _chosen(m)["type"], "menu_size": m["row"]["menu_size"],
                               "rank_of_chosen": m["rank"], "top1_index": m["top1"]} for m in matched],
        "skipped_decisions": skipped,
    }
    return report


def _pct(value) -> str:
    return "  -  " if value is None else f"{100 * value:5.1f}"


def render(report: dict) -> str:
    models = report["models"]
    cov = report["coverage"]
    lines = [f"MODEL-SHADOW-EVAL-1: {cov['matches_in_journal']} матча(ей) в журнале, логи Power.log найдены для {cov['matches_with_power_log']}",
             f"строк Shadow {cov['shadow_rows']}, из них повторных эмиссий того же решения {cov['duplicate_rows_collapsed']} -> "
             f"различных решений {cov['distinct_decisions']}",
             f"сопоставлено {cov['matched']} ({_pct(cov['matched_share_of_distinct']).strip()}% различных, "
             f"{_pct(cov['matched_share_of_rows']).strip()}% всех строк); причины пропуска: {cov['skip_reasons'] or 'нет'}",
             f"размечено импортёром, но без строки Shadow: {cov['labeled_decisions_without_shadow_row']} "
             f"(по журналам: {cov['labeled_without_shadow_explained'].get('by_decision', cov['labeled_without_shadow_explained']['status'])})",
             f"личность чекпойнтов подтверждена: {report['independence']['checkpoint_identity_verified']}",
             f"пересечение с обучением: {report['independence']['training_overlap_matches'] or 'нет'}", ""]
    for label, table in report["metrics"].items():
        lines.append(f"[{label}] решений: {table['decisions']} (Top-3 только по меню из 3+ действий)")
        lines.append(f"  {'модель':<14}{'Top-1%':>8}{'Top-3%':>8}{'MRR':>7}{'ср.ранг':>9}{'случайно T1/T3/MRR':>24}")
        for name in models:
            m = table["models"][name]
            if not m["decisions"]:
                continue
            c = m["chance"]
            lines.append(f"  {name:<14}{_pct(m['top1']):>8}{_pct(m['top3']):>8}{m['mrr']:>7.3f}{m['mean_rank']:>9.2f}"
                         f"{100 * c['top1']:>9.1f}/{_pct(c['top3']).strip()}/{c['mrr']:.3f}  Top-3 n={m['top3_decisions']}")
    lines += ["", "по матчам (нетривиальные меню, Top-1% / MRR, n):"]
    for mid, tables in report["per_match"].items():
        sub = tables["nontrivial_menu_2plus"]
        lines.append(f"  {mid}  n={sub['decisions']:<3} " + "  ".join(
            f"{name}: {_pct(sub['models'][name].get('top1')).strip()}%/{sub['models'][name].get('mrr', float('nan')):.3f}"
            for name in models))
    lines += ["", f"порядок по MRR (нетривиальные меню): {' > '.join(report['ranking_by_mrr_nontrivial'])}", "надёжность (парные сравнения):"]
    for key, r in report["reliability"].items():
        if not r["decisions"]:
            continue
        t, mr = r["top1"], r["mrr"]
        a, b = r["a"], r["b"]
        lines.append(f"  {key}: n={r['decisions']} Top-1 только {a} {t[f'only_{a}']} / только {b} {t[f'only_{b}']}, p={t['exact_sign_test_p']}; "
                     f"MRR разность {mr['mean_diff']:+.3f} CI95 [{mr['bootstrap95'][0]:+.3f}, {mr['bootstrap95'][1]:+.3f}] -> {r['verdict']}")
        lines.append("      по матчам MRR: " + ", ".join(f"{k} {v['mrr_diff']:+.3f}(n={v['decisions']})" for k, v in r["per_match"].items()))
    cats = report["categories"]
    hp = cats["hero_power"]
    lines += ["", f"=== {report['self_class']}: решений {report['self_class_decisions']} ===",
              f"HERO_POWER: доступна {hp['overall']['available']}, игрок использовал {hp['overall']['player_used']}"]
    for label, stats in [("всего", hp["overall"]), *hp["by_available_mana"].items()]:
        if not stats["available"]:
            continue
        lines.append(f"  мана {label:<6} доступна {stats['available']:<3} использовал {stats['player_used']:<3} | " + "; ".join(
            f"{n}: top1={s['top1_hero_power']} переоц.={s['overestimated_top1_but_not_used']} недооц.={s['underestimated_used_but_not_top1']}"
            for n, s in stats["models"].items()))
    for title, key in (("ATTACK", "attack"), ("PLAY_CARD", "play_card")):
        rep = cats[key]
        lines.append(f"{title}: игрок выбрал {rep['player_chose']}")
        for n, s in rep["models"].items():
            lines.append(f"  {n:<14}точное совпадение {s['top1_exact']} ({_pct(s['top1_exact_share']).strip()}%) {s['breakdown']}")
    et = cats["end_turn"]
    lines.append(f"END_TURN: меню с альтернативами {et['decisions_with_alternatives']}, игрок закончил ход {et['player_ended_turn']}")
    for n, s in et["models"].items():
        lines.append(f"  {n:<14}модель: конец хода, игрок продолжил {s['model_ends_turn_player_continues']}; "
                     f"игрок: конец хода, модель другое {s['player_ends_turn_model_suggests_other']}; оба {s['both_end_turn']}")
    tg = cats["targets"]
    lines.append(f"цели: игрок выбрал действие с целью {tg['player_chose_targeted_action']} раз")
    for n, s in tg["models"].items():
        lines.append(f"  {n:<14}{ {k: v for k, v in s.items() if k != 'attack_target_class_player_vs_model_top1_when_both_attack'} } "
                     f"атака (игрок->модель): {s['attack_target_class_player_vs_model_top1_when_both_attack']}")
    dis = report["model_disagreements"]
    lines += ["", f"принципиальные расхождения моделей: {dis['decisions_with_different_top1_substance']} "
              f"(все три разные: {dis['of_which_all_models_differ']})"]
    for e in dis["examples"]:
        lines.append(f"- {e['match']} ход {e['turn']}: {e['state']}")
        lines.append(f"    игрок: {e['player_chose']}")
        for n, v in e["models"].items():
            lines.append(f"    {n}: {v['top1']} (ранг выбора игрока {v['rank_of_player_choice']})")
    lines += ["", *[f"! {c}" for c in report["claims"]]]
    return "\n".join(lines)
