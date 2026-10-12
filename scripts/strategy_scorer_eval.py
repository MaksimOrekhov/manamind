"""STRATEGIC-SCORER-1 offline evaluation. Parameters were frozen (commit ee55494) before this script was first run.

Three separate questions, never merged into one number:

1. Controlled tactics: Top-1 / Top-3 / MRR of the scorer and of the frozen Policy v2 on the locked synthetic sets
   (MODEL-FIRST-1 control, MODEL-FIRST-2 and 2C test). Synthetic labels follow hand-written rules: plumbing evidence.
2. Does the position value point the right way? AUC of the static position value for the final result of real
   Ranked games, against simple baselines, with a bootstrap over whole games. Says nothing about action quality.
3. Real decisions: on the same full legal menus of every recorded LIVE game, the Policy v2 ranking against the scorer
   ranking - agreement, disagreements, action-type mix, uncertainty, latency - plus the decisions the player flagged.
   The human action is reported for description only; it is not a correct answer.

  python scripts/strategy_scorer_eval.py --out reports/strategic_scorer_1/results.json \
      --private-out data/raw/live/strategy_scorer_1/decisions.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from evaluate_policy_baseline import action_key  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match  # noqa: E402
from manamind.models.policy_inputs import encode_policy_inputs, representation_of  # noqa: E402
from manamind.outcome.live_shadow import load_texts  # noqa: E402
from manamind.outcome.observation import context_from_observed  # noqa: E402
from manamind.outcome.world import ObservedContext  # noqa: E402
from manamind.strategy import PARAMS_VERSION, SCORER_VERSION, score_menu  # noqa: E402
from manamind.strategy.value import effective_health, position_value  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402

POLICY = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
CARDS = ROOT / "data/cards/standard_current_enUS.json"
LIVE = ROOT / "data/raw/live"
CANONICAL = ROOT / "data/processed_data_checkpoint_1_20261010/canonical"
SYNTHETIC = {
    "model_first_1_control": ROOT / "data/evaluation/model_first_1/control_test.jsonl",
    "model_first_2_test": ROOT / "model-first-2/data/processed_synthetic/model_first_2/test.jsonl",
    "model_first_2c_test": ROOT / "model-first-2/data/processed_synthetic/model_first_2c/test.jsonl",
}
RECENT_SESSIONS = ("Hearthstone_2026_10_11", "Hearthstone_2026_10_12")
MAJOR_GAP = 3.0          # stat points (about 1.5 Mana) between the two Top-1 actions on the scorer's own scale


# ----- shared ---------------------------------------------------------------------------------------------------------

def policy_order(policy, encoder, state, actions) -> tuple[list[int], list[float]]:
    with torch.inference_mode():
        logits = policy(*encode_policy_inputs(state, actions, encoder, representation=representation_of(policy)))
    order = torch.argsort(logits, descending=True, stable=True).tolist()
    return order, [float(x) for x in logits]


def rank_metrics(ranking: list[int], correct: set[int]) -> dict:
    rank = next((position for position, index in enumerate(ranking, 1) if index in correct), None)
    return {"top1": rank == 1, "top3": rank is not None and rank <= 3, "rr": 0.0 if rank is None else 1.0 / rank}


def summarize(items: list[dict], menu_sizes: list[int]) -> dict:
    if not items:
        return {"n": 0}
    top3 = [m["top3"] for m, size in zip(items, menu_sizes) if size >= 3]
    return {"n": len(items), "top1": round(float(np.mean([m["top1"] for m in items])), 4),
            "top3": round(float(np.mean(top3)), 4) if top3 else None, "top3_n": len(top3),
            "mrr": round(float(np.mean([m["rr"] for m in items])), 4)}


def action_type(action: dict) -> str:
    kind = action.get("type", "?")
    if kind == "PLAY_CARD":
        return f"PLAY_{action.get('card_type', '?')}"
    if kind == "ATTACK":
        return "ATTACK_HERO" if action.get("target_kind") == "HERO" else "ATTACK_MINION"
    return kind


# ----- 1. controlled tactics ------------------------------------------------------------------------------------------

def synthetic(policy, encoder, texts) -> dict:
    out = {}
    for name, path in SYNTHETIC.items():
        if not path.exists():
            out[name] = {"missing": str(path.relative_to(ROOT))}
            continue
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        per = defaultdict(lambda: {"scorer": [], "policy": [], "sizes": [], "scorer_tied_top": 0})
        for row in rows:
            if row["label_status"] != "LABELED":
                continue
            state = game_state_from_dict(row["state"])
            actions = row["legal_actions"]
            keys = {action_key(a) for a in row["correct_actions"]}
            correct = {i for i, a in enumerate(actions) if action_key(a) in keys}
            result = score_menu(state, actions, texts, ObservedContext(), budget_ms=10_000)
            p_order, _ = policy_order(policy, encoder, state, actions)
            for bucket in (per[row["category"]], per["ALL"]):
                bucket["scorer"].append(rank_metrics(list(result.ranking), correct))
                bucket["policy"].append(rank_metrics(p_order, correct))
                bucket["sizes"].append(len(actions))
                top = result.actions[result.ranking[0]].score
                bucket["scorer_tied_top"] += sum(1 for a in result.actions if round(a.score, 6) == round(top, 6)) > 1
        out[name] = {category: {"scorer": summarize(v["scorer"], v["sizes"]),
                                "policy_v2": summarize(v["policy"], v["sizes"]),
                                "scorer_top_score_shared": v["scorer_tied_top"]}
                     for category, v in sorted(per.items())}
    return out


# ----- real data --------------------------------------------------------------------------------------------------------

def seen_by_policy() -> set[str]:
    frozen = json.loads((POLICY.parent / "frozen_experiment.json").read_text(encoding="utf-8"))
    ids = frozen["split"]["decision_ids"]
    return {decision.rsplit(":", 1)[0] for part in ids.values() for decision in part}


def recorded_games(catalog) -> tuple[list[dict], Counter]:
    """Every labeled decision of every complete recorded Ranked Standard game, with its observed SELF facts."""
    games, failures = [], Counter()
    for slice_log in sorted(LIVE.glob("Hearthstone_*/*/slice.log")):
        directory = slice_log.parent
        lines = slice_log.read_text(encoding="utf-8").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        facts = {}
        try:
            examples, summary = extract_match(lines, catalog, observer=lambda d, f: facts.__setitem__(d, f))
        except PolicyImportError as error:
            failures[error.reason] += 1
            continue
        except Exception as error:                       # noqa: BLE001 - counted, never printed
            failures[type(error).__name__] += 1
            continue
        if not examples:
            failures["NO_LABELED_DECISIONS"] += 1
            continue
        games.append({"directory": directory, "session": directory.parent.name, "game_id": summary["game_id"],
                      "examples": examples, "facts": facts})
    return games, failures


def auc(scores: list[float], labels: list[float]) -> float | None:
    pos = [s for s, y in zip(scores, labels) if y == 1.0]
    neg = [s for s, y in zip(scores, labels) if y == 0.0]
    if not pos or not neg:
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    values = np.concatenate([pos, neg])[order]
    ranks = np.empty(len(values))
    i = 0
    while i < len(values):                                # average ranks for ties
        j = i
        while j + 1 < len(values) and values[j + 1] == values[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2 + 1
        i = j + 1
    full = np.empty(len(values))
    full[order] = ranks
    return float((full[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def value_validation(positions: list[dict], seed: int = 20261012, rounds: int = 1000) -> dict:
    """AUC of each position feature for the final SELF result; CIs resample whole games."""
    features = sorted(positions[0]["features"])
    by_game = defaultdict(list)
    for row in positions:
        by_game[row["game"]].append(row)
    games = sorted(by_game)
    rng = np.random.default_rng(seed)
    out = {"games": len(games), "positions": len(positions),
           "wins": sum(by_game[g][0]["y"] == 1.0 for g in games), "losses": sum(by_game[g][0]["y"] == 0.0 for g in games)}
    phases = {"all": lambda r: True, "turn<=10": lambda r: r["turn"] <= 10, "turn>10": lambda r: r["turn"] > 10}
    for phase, keep in phases.items():
        rows = [r for r in positions if keep(r)]
        block = {"positions": len(rows)}
        for feature in features:
            point = auc([r["features"][feature] for r in rows], [r["y"] for r in rows])
            samples = []
            for _ in range(rounds):
                pick = rng.choice(games, size=len(games), replace=True)
                sample = [r for g in pick for r in by_game[g] if keep(r)]
                value = auc([r["features"][feature] for r in sample], [r["y"] for r in sample])
                if value is not None:
                    samples.append(value)
            block[feature] = {"auc": None if point is None else round(point, 4),
                              "ci95": [round(float(np.percentile(samples, 2.5)), 4),
                                       round(float(np.percentile(samples, 97.5)), 4)] if samples else None}
        out[phase] = block
    return out


def position_features(state, texts) -> dict[str, float]:
    me, them = state.self_player, state.opponent
    value = position_value(state, texts, turn_open=False)
    stats = lambda side: sum(max(0, e.current_attack) + max(0, e.current_health) for e in side.board)  # noqa: E731
    return {
        "baseline_health_difference": float(effective_health(me) - effective_health(them)),
        "baseline_board_stats_difference": float(stats(me) - stats(them)),
        "baseline_hand_size_difference": float(me.hand_size - them.hand_size),
        "scorer_hero_terms": value.get("hero_self") + value.get("hero_opponent"),
        "scorer_board_terms": value.get("board_self") + value.get("board_opponent"),
        "scorer_risk_terms": value.kind("risk"),
        "scorer_static_plus_risk": value.kind("static") + value.kind("risk") + value.kind("terminal"),
    }


def journal_top3() -> dict[tuple[str, int, str], list[dict]]:
    found = {}
    path = LIVE / "prediction_journal.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("event") != "RECOMMENDATION":
            continue
        game, _, options, state_hash = row["decision_id"].split(":")
        found.setdefault((game, int(options), state_hash), [item["action"] for item in row["top3"]])
    return found


def flagged() -> dict[tuple[str, int, str], dict]:
    found = {}
    path = LIVE / "decision_feedback.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        game, _, options, state_hash = row["decision_id"].split(":")
        found.setdefault((game, int(options), state_hash), row)
    return found


def describe(action: dict) -> str:
    kind = action.get("type")
    if kind == "END_TURN":
        return "END_TURN"
    text = f"{kind} {action.get('card_id') or action.get('source_card_id')}"
    if action.get("target_kind"):
        where = "hero" if action["target_kind"] == "HERO" else (
            f"{action.get('target_card_id')} {action.get('target_attack')}/{action.get('target_health')}")
        text += f" -> {action['target_side']} {where}"
    if action.get("play_position"):
        text += f" @pos{action['play_position']}"
    return text


def board_summary(state) -> dict:
    side = lambda p: [f"{e.card.card_id} {e.current_attack}/{e.current_health}" + (" T" if e.taunt else "")  # noqa: E731
                      + (" DS" if e.divine_shield else "") for e in p.board]
    me, them = state.self_player, state.opponent
    return {"turn": state.turn_number, "class": me.player_class, "opponent_class": them.player_class,
            "self_health": effective_health(me), "opponent_health": effective_health(them),
            "mana": me.available_mana, "self_board": side(me), "opponent_board": side(them),
            "hand": [f"{c.card_id}({c.effective_cost})" for c in state.self_hand], "opponent_hand_size": them.hand_size}


def compare_real(policy, encoder, texts, games, policy_seen) -> tuple[dict, list[dict], list[dict]]:
    journal = journal_top3()
    flags = flagged()
    decisions, positions = [], []
    for game in games:
        examples = game["examples"]
        result = examples[0]["final_result"]
        for row in examples:
            state = game_state_from_dict(row["state"])
            actions = row["legal_actions"]
            options = int(row["decision_id"].rsplit(":", 1)[1])
            positions.append({"game": game["game_id"], "y": result, "turn": state.turn_number,
                              "features": position_features(state, texts)})
            try:
                context = context_from_observed(game["facts"].get(row["decision_id"]), state)
            except Exception:                                    # noqa: BLE001 - unknown facts are always safe
                context = ObservedContext()
            started = time.perf_counter()
            scored = score_menu(state, actions, texts, context, budget_ms=10_000)
            elapsed = (time.perf_counter() - started) * 1000
            p_order, p_logits = policy_order(policy, encoder, state, actions)
            chosen = row["chosen_action_index"]
            key = (game["game_id"], options, row["provenance"]["state_hash"])
            groups = scored.groups
            group_of = {index: g for g, members in enumerate(groups) for index in members}
            s_top, p_top = groups[0][0], p_order[0]
            gap = scored.actions[s_top].score - scored.actions[p_top].score
            s_a, p_a = scored.actions[s_top], scored.actions[p_top]
            confirmed_gap = (s_a.confirmed + s_a.risk) - (p_a.confirmed + p_a.risk)
            certain = all(a.uncertainty.level != "HIGH" and a.unknown_estimate == 0 for a in (s_a, p_a))
            decisions.append({
                "game": game["game_id"], "session": game["session"], "options_id": options,
                "state_hash": row["provenance"]["state_hash"], "policy_seen_game": game["game_id"] in policy_seen,
                "recent": game["session"].startswith(RECENT_SESSIONS), "flagged": key in flags,
                "journal_top3_match": (None if key not in journal else
                                       [actions[i] for i in p_order[:3]] == journal[key]),
                "menu_size": len(actions), "groups": len(groups), "final_result": result,
                "class": state.self_player.player_class, "turn": state.turn_number,
                "scorer_top1": s_top, "policy_top1": p_top, "player": chosen,
                "scorer_top1_type": action_type(actions[s_top]), "policy_top1_type": action_type(actions[p_top]),
                "player_type": action_type(actions[chosen]),
                "top1_same_group": group_of[p_top] == 0,
                "policy_top1_in_scorer_top3_groups": group_of[p_top] < 3,
                "scorer_top1_in_policy_top3": bool(set(groups[0]) & set(p_order[:3])),
                "player_scorer_group_rank": group_of[chosen] + 1,
                "player_policy_rank": p_order.index(chosen) + 1,
                "policy_top1_scorer_group_rank": group_of[p_top] + 1,
                "scorer_top1_policy_rank": min(p_order.index(i) for i in groups[0]) + 1,
                "gap_points": round(gap, 3), "confirmed_gap_points": round(confirmed_gap, 3),
                "confident_disagreement": bool(gap >= MAJOR_GAP and confirmed_gap >= MAJOR_GAP and certain),
                "spearman": _spearman([a.score for a in scored.actions], p_logits) if len(actions) >= 3 else None,
                "scorer_top1_uncertainty": s_a.uncertainty.level,
                "status_counts": dict(Counter(a.status for a in scored.actions)),
                "levels": dict(Counter(a.uncertainty.level for a in scored.actions)),
                "estimate_share_top1": _share(s_a), "elapsed_ms": round(elapsed, 3),
                "detail": {"position": board_summary(state),
                           "scorer_top3": [{**scored.actions[g[0]].to_dict(), "members": len(g),
                                            "action": describe(actions[g[0]])} for g in groups[:3]],
                           "policy_top3": [{"action": describe(actions[i]), "logit": round(p_logits[i], 3),
                                            "scorer": scored.actions[i].to_dict(),
                                            "scorer_group_rank": group_of[i] + 1} for i in p_order[:3]],
                           "player": {"action": describe(actions[chosen]), "scorer_group_rank": group_of[chosen] + 1,
                                      "policy_rank": p_order.index(chosen) + 1,
                                      "scorer": scored.actions[chosen].to_dict()}},
            })
    return {"decisions": len(decisions)}, decisions, positions


def _spearman(a: list[float], b: list[float]) -> float | None:
    ra, rb = _ranks(a), _ranks(b)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _ranks(values: list[float]) -> np.ndarray:
    values = np.asarray(values)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values))
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2
        i = j + 1
    return ranks


def _share(action) -> float:
    total = abs(action.confirmed) + abs(action.risk) + abs(action.plan) + abs(action.unknown_estimate)
    return 0.0 if total == 0 else round(action.unknown_estimate / total, 3)


def aggregate(decisions: list[dict]) -> dict:
    def block(rows):
        if not rows:
            return {"decisions": 0}
        mean = lambda key: round(float(np.mean([r[key] for r in rows])), 4)  # noqa: E731
        spear = [r["spearman"] for r in rows if r["spearman"] is not None]
        multi = [r for r in rows if r["groups"] >= 2]
        return {
            "decisions": len(rows), "games": len({r["game"] for r in rows}),
            "menu_size_median": float(np.median([r["menu_size"] for r in rows])),
            "top1_agreement_same_group": mean("top1_same_group"),
            "top1_agreement_multi_group_menus": (round(float(np.mean([r["top1_same_group"] for r in multi])), 4)
                                                  if multi else None),
            "policy_top1_in_scorer_top3": mean("policy_top1_in_scorer_top3_groups"),
            "scorer_top1_in_policy_top3": mean("scorer_top1_in_policy_top3"),
            "spearman_median": round(float(np.median(spear)), 4) if spear else None,
            "major_disagreements_gap_ge_3": sum(r["gap_points"] >= MAJOR_GAP for r in rows),
            "confident_disagreements": sum(r["confident_disagreement"] for r in rows),
            "descriptive_player_agreement": {
                "player_is_scorer_top1": mean_eq(rows, "player_scorer_group_rank", 1),
                "player_is_policy_top1": mean_eq(rows, "player_policy_rank", 1),
                "player_in_scorer_top3": round(float(np.mean([r["player_scorer_group_rank"] <= 3 for r in rows])), 4),
                "player_in_policy_top3": round(float(np.mean([r["player_policy_rank"] <= 3 for r in rows])), 4),
                "note": "descriptive only: the player's action is not a correct answer"},
            "top1_action_types": {"scorer": dict(Counter(r["scorer_top1_type"] for r in rows).most_common()),
                                  "policy_v2": dict(Counter(r["policy_top1_type"] for r in rows).most_common()),
                                  "player": dict(Counter(r["player_type"] for r in rows).most_common())},
            "scorer_top1_uncertainty": dict(Counter(r["scorer_top1_uncertainty"] for r in rows)),
            "action_status": dict(sum((Counter(r["status_counts"]) for r in rows), Counter())),
            "action_uncertainty": dict(sum((Counter(r["levels"]) for r in rows), Counter())),
            "latency_ms": {"median": round(float(np.median([r["elapsed_ms"] for r in rows])), 2),
                           "p95": round(float(np.percentile([r["elapsed_ms"] for r in rows], 95)), 2),
                           "max": round(float(max(r["elapsed_ms"] for r in rows)), 2)},
            "journal_top3_reproduced": dict(Counter(str(r["journal_top3_match"]) for r in rows)),
        }

    out = {"all": block(decisions),
           "policy_unseen_games": block([r for r in decisions if not r["policy_seen_game"]]),
           "policy_seen_games": block([r for r in decisions if r["policy_seen_game"]]),
           "recent_sessions_oct_11_12": block([r for r in decisions if r["recent"]]),
           "flagged_by_player": block([r for r in decisions if r["flagged"]]),
           "not_flagged_recent": block([r for r in decisions if r["recent"] and not r["flagged"]])}
    out["by_class"] = {cls: block([r for r in decisions if r["class"] == cls])
                       for cls in sorted({r["class"] for r in decisions})}
    return out


def mean_eq(rows, key, value):
    return round(float(np.mean([r[key] == value for r in rows])), 4)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--private-out", type=Path, required=True)
    parser.add_argument("--skip-synthetic", action="store_true")
    args = parser.parse_args(argv)
    for path in (args.out, args.private_out):
        if path.exists():
            raise SystemExit(f"refusing to overwrite {path}")
    torch.set_num_threads(1)
    texts = load_texts(ROOT)
    catalog = CardCatalog.from_json(CARDS)
    policy, encoder, _ = load_policy_checkpoint(POLICY, device="cpu")
    policy.eval()
    report = {"scorer": SCORER_VERSION, "params": PARAMS_VERSION, "major_gap_points": MAJOR_GAP}
    if not args.skip_synthetic:
        report["synthetic"] = synthetic(policy, encoder, texts)
    games, failures = recorded_games(catalog)
    seen = seen_by_policy()
    _, decisions, positions = compare_real(policy, encoder, texts, games, seen)
    report["recordings"] = {"games_used": len(games), "not_importable": dict(failures),
                            "games_seen_by_policy_training": sum(g["game_id"] in seen for g in games)}
    report["real_comparison"] = aggregate(decisions)
    canonical_positions = []
    known_games = {g["game_id"] for g in games}
    for path in sorted(CANONICAL.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["game_id"] in known_games:
                continue
            state = game_state_from_dict(row["state"])
            canonical_positions.append({"game": row["game_id"], "y": row["final_result"], "turn": state.turn_number,
                                        "features": position_features(state, texts)})
    report["value_validation"] = value_validation(positions + canonical_positions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    args.private_out.parent.mkdir(parents=True, exist_ok=True)
    with args.private_out.open("w", encoding="utf-8") as file:
        for row in decisions:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({k: report[k] for k in ("recordings",)}, indent=1))
    print(json.dumps(report["real_comparison"]["all"], indent=1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
