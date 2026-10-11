"""Score the immediate-outcome forecaster against the logged next observation (ACTION-OUTCOME-1).

For every pair of adjacent labeled decisions of one SELF turn, the forecast is computed from the first
state and the action the player chose; the second state is used only to score it. Training, model
checkpoints and Power.log parsing are not involved: the input is the canonical policy dataset that
DATA-CHECKPOINT-1 re-extracted from the raw logs.

  python scripts/verify_action_outcomes.py --corpus <canonical dir> --out reports/action_outcome_1/real_log_verification.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.outcome import ObservedContext, Status, TextSource, forecast_action  # noqa: E402
from manamind.outcome.verify import (  # noqa: E402
    PairResult, load_corpus, score_pair, successor_pairs, summarise_results,
)

CONTEXTS = {
    "observed_only": ObservedContext(),
    "assumed_defaults": ObservedContext.assuming_common_defaults(),
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


# What a richer observation export and a text supplement could remove, versus what needs new rules knowledge.
_OBSERVATION = {"HAND_KEYWORDS_UNOBSERVED", "HEALING_BONUS_UNOBSERVED", "HERO_SHIELD_UNOBSERVED",
                "SANCTUM_UNOBSERVED", "COST_UNOBSERVED", "ATTACKS_USED_UNOBSERVED", "WEAPON_UNOBSERVED",
                "OWN_SECRET_OR_QUEST", "BOARD_TEXT_MISSING", "OWN_TEXT_MISSING", "SPELL_DAMAGE_UNOBSERVED",
                "CONDITION_UNOBSERVED"}
_RULES = {"BOARD_STATIC_TEXT", "BOARD_TRIGGER", "DEATHRATTLE_OR_REBORN", "OWN_TEXT_UNPARSED", "OWN_TEXT_KEYWORD",
          "OWN_TEXT_RANDOM"}
RESOLUTION_SCENARIOS = {
    "observation_gaps_closed": _OBSERVATION,
    "observation_gaps_closed_and_board_rules_understood": _OBSERVATION | {
        "BOARD_STATIC_TEXT", "BOARD_TRIGGER", "DEATHRATTLE_OR_REBORN"},
    "everything_except_opponent_secrets": _OBSERVATION | _RULES,
}


def blockers(result_forecast) -> set[str]:
    return {unknown.tag or f"UNTAGGED:{unknown.kind.value}" for unknown in result_forecast.unknowns}


def blocker_analysis(pairs, texts: TextSource, context: ObservedContext) -> dict:
    """What keeps forecasts from being EXACT, and how many would be if one blocker class were resolved."""
    sets = []
    for current, _ in pairs:
        forecast = forecast_action(current.state, current.action, texts, context)
        if forecast.status is not Status.UNSUPPORTED:
            sets.append(blockers(forecast))
    present = Counter(tag for blocker_set in sets for tag in blocker_set)
    alone = Counter(next(iter(blocker_set)) for blocker_set in sets if len(blocker_set) == 1)
    scenarios = {name: sum(not (blocker_set - resolved) for blocker_set in sets)
                 for name, resolved in RESOLUTION_SCENARIOS.items()}
    return {
        "exact_if_resolved": scenarios,
        "forecasts": len(sets),
        "exact_now": sum(not blocker_set for blocker_set in sets),
        "forecasts_blocked_by": dict(present.most_common()),
        "would_become_exact_if_only_this_class_were_resolved": dict(alone.most_common()),
        "untagged_unknowns": sum(tag.startswith("UNTAGGED") for blocker_set in sets for tag in blocker_set),
    }


def menu_scan(games, texts: TextSource) -> dict:
    """Forecast every legal action of every SELF decision: how many are supported, and how many are gifts.

    A 'gift' is an action whose exact direct changes improve only OPPONENT-controlled entities (see
    ``compare.summarise``). That is a statement about direct effects, not a verdict on the action.
    """
    from manamind.outcome import summarise

    totals, gifts, gifts_known, chosen_gifts, decisions_with_gift = Counter(), 0, 0, 0, 0
    by_type: Counter = Counter()
    gift_cards: Counter = Counter()
    for items in games.values():
        for decision in items:
            if decision.state.active_player != "SELF":
                continue
            has_gift = False
            for index, action in enumerate(decision.legal_actions):
                forecast = forecast_action(decision.state, action, texts)
                totals[forecast.status.value] += 1
                by_type[(action["type"], forecast.status.value)] += 1
                if forecast.after_state is None:
                    continue
                if summarise(decision.state, forecast).note.startswith("direct effects only improve OPPONENT"):
                    gifts += 1
                    gifts_known += forecast.own_effect_known
                    gift_cards[action.get("card_id")] += 1
                    has_gift = True
                    chosen_gifts += action == decision.action
            decisions_with_gift += has_gift
    total = sum(totals.values())
    return {
        "legal_actions": total, "by_status": dict(totals),
        "by_type_and_status": {f"{kind}/{status}": count for (kind, status), count in sorted(by_type.items())},
        "opponent_only_improvement_actions": gifts,
        "of_which_own_effect_known": gifts_known, "by_card": dict(gift_cards.most_common()),
        "decisions_offering_one": decisions_with_gift,
        "chosen_by_the_player": chosen_gifts,
    }


def timing(games, pairs, texts: TextSource) -> dict:
    chosen = [(current.state, current.action) for current, _ in pairs]
    samples = []
    for _ in range(3):                                   # three passes; the last two are warm
        samples = []
        for state, action in chosen:
            start = time.perf_counter_ns()
            forecast_action(state, action, texts)
            samples.append((time.perf_counter_ns() - start) / 1e6)
    menus = []
    sizes = []
    for items in games.values():
        for decision in items:
            if decision.state.active_player != "SELF":
                continue
            start = time.perf_counter_ns()
            for action in decision.legal_actions:
                forecast_action(decision.state, action, texts)
            menus.append((time.perf_counter_ns() - start) / 1e6)
            sizes.append(len(decision.legal_actions))
    return {
        "single_action_ms": {"n": len(samples), "mean": round(statistics.fmean(samples), 4),
                             "p50": round(percentile(samples, 0.5), 4), "p95": round(percentile(samples, 0.95), 4),
                             "max": round(max(samples), 4)},
        "whole_menu_ms": {"n": len(menus), "mean": round(statistics.fmean(menus), 3),
                          "p50": round(percentile(menus, 0.5), 3), "p95": round(percentile(menus, 0.95), 3),
                          "max": round(max(menus), 3)},
        "menu_size": {"mean": round(statistics.fmean(sizes), 1), "p95": percentile([float(s) for s in sizes], 0.95),
                      "max": max(sizes)},
    }


def card_section(results: list[PairResult], card_id: str) -> dict:
    rows = [r for r in results if f" {card_id}" in r.action_label and r.family == "PLAY_CARD/SPELL"]
    paths = Counter(path.split(".")[-1] for r in rows for path in r.confirmed)
    by_target = Counter(("OPPONENT" if "-> OPPONENT" in r.action_label else "SELF" if "-> SELF" in r.action_label
                         else "none") for r in rows)
    return {
        "card_id": card_id, "casts": len(rows), "by_target_side": dict(by_target),
        "status": dict(Counter(r.status.value for r in rows)),
        "verdict": dict(Counter(r.verdict for r in rows)),
        "confirmed_path_fields": dict(paths.most_common()),
        "contradicted": [{"decision": r.decision_id, "paths": {k: list(v) for k, v in r.contradicted.items()}}
                         for r in rows if r.contradicted][:10],
        "missed": [{"decision": r.decision_id, "paths": {k: list(v) for k, v in r.missed.items()}}
                   for r in rows if r.missed][:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", default="data/processed_data_checkpoint_1_20261010/canonical")
    parser.add_argument("--catalog", default=str(ROOT / "data" / "cards" / "standard_current_enUS.json"))
    parser.add_argument("--reviewed", default=str(ROOT / "data" / "outcome" / "reviewed_texts.json"))
    parser.add_argument("--supplement", nargs="*", default=[], help="lowest-priority card JSON files (tokens)")
    parser.add_argument("--out", default=str(ROOT / "reports" / "action_outcome_1" / "real_log_verification.json"))
    parser.add_argument("--examples", type=int, default=12)
    args = parser.parse_args()

    corpus = Path(args.corpus)
    if not corpus.exists():
        corpus = next((p / args.corpus for p in ROOT.parents if (p / args.corpus).exists()), corpus)
    games = load_corpus(corpus)
    texts = TextSource.from_files(args.catalog, args.reviewed, *args.supplement)
    pairs = list(successor_pairs(games))
    decisions = sorted(d.decision_id for items in games.values() for d in items)

    report: dict = {
        "corpus": {"games": len(games), "labeled_decisions": len(decisions),
                   "adjacent_pairs_scored": len(pairs),
                   "decision_ids_sha256": hashlib.sha256("\n".join(decisions).encode()).hexdigest()},
        "text_sources": texts.fingerprints,
        "runs": {},
    }
    for name, context in CONTEXTS.items():
        results = [score_pair(current, following, texts, context) for current, following in pairs]
        own_known = [r for r in results if r.own_effect_known]
        exact = [r for r in results if r.status is Status.EXACT]
        section = summarise_results(results)
        section["tiers"] = {
            "EXACT": {"n": len(exact), "verdict": dict(Counter(r.verdict for r in exact)),
                      "confirmed_paths": sum(len(r.confirmed) for r in exact),
                      "contradicted_paths": sum(len(r.contradicted) for r in exact)},
            "OWN_EFFECT_KNOWN (reactions of other objects still open)": {
                "n": len(own_known), "verdict": dict(Counter(r.verdict for r in own_known)),
                "confirmed_paths": sum(len(r.confirmed) for r in own_known),
                "contradicted_paths": sum(len(r.contradicted) for r in own_known)},
        }
        section["blockers"] = blocker_analysis(pairs, texts, context)
        section["jail_913"] = card_section(results, "JAIL_913")
        section["contradiction_examples"] = [
            {"decision": r.decision_id, "action": r.action_label, "status": r.status.value,
             "own_effect_known": r.own_effect_known, "contradicted": {k: list(v) for k, v in r.contradicted.items()},
             "open_unknowns": list(r.unknown_details[:4])}
            for r in results if r.verdict == "CONTRADICTED"][: args.examples]
        section["exact_violations"] = [
            {"decision": r.decision_id, "action": r.action_label,
             "contradicted": {k: list(v) for k, v in r.contradicted.items()}}
            for r in exact if r.verdict != "CONFIRMED"]
        report["runs"][name] = section
    report["menu_scan"] = menu_scan(games, texts)
    report["timing"] = timing(games, pairs, texts)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    for name, section in report["runs"].items():
        print(f"[{name}] pairs={section['pairs']} status={section['status']} tiers=" +
              json.dumps({k: v['verdict'] for k, v in section['tiers'].items()}))
    print("timing:", json.dumps(report["timing"]))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
