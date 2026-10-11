"""Score the immediate-outcome forecaster against the logged next observation (ACTION-OUTCOME-1B).

For every pair of adjacent labeled decisions of one SELF turn, the forecast is computed from the first
state and the action the player chose; the second state is used only to score it. Training, model
checkpoints and Power.log parsing are not involved: the input is the canonical policy dataset that
DATA-CHECKPOINT-1 re-extracted from the raw logs.

  python scripts/verify_action_outcomes.py --corpus <canonical dir> --out reports/observation_ext_1a/real_log_verification.json
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

from manamind.outcome import ObservedContext, Status, TextSource, Tier, forecast_action  # noqa: E402
from manamind.integrations.powerlog.observed_facts import ObservedFacts  # noqa: E402
from manamind.outcome.observation import context_from_facts, context_from_observed, load_facts  # noqa: E402
from manamind.outcome.verify import (  # noqa: E402
    PairResult, build_gain_associations, load_corpus, role_of, score_pair, successor_pairs, summarise_results,
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
                "CONDITION_UNOBSERVED", "REBORN_BASE_UNKNOWN"}
_RULES = {"BOARD_STATIC_TEXT", "BOARD_TRIGGER", "DEATHRATTLE", "OWN_TEXT_UNPARSED", "OWN_TEXT_KEYWORD",
          "OWN_TEXT_RANDOM"}
RESOLUTION_SCENARIOS = {
    "observation_gaps_closed": _OBSERVATION,
    "observation_gaps_closed_and_board_rules_understood": _OBSERVATION | {
        "BOARD_STATIC_TEXT", "BOARD_TRIGGER", "DEATHRATTLE"},
    "everything_except_opponent_secrets": _OBSERVATION | _RULES,
}


def blockers(result_forecast) -> set[str]:
    return {unknown.tag or f"UNTAGGED:{unknown.kind.value}" for unknown in result_forecast.unknowns}


def blocker_analysis(pairs, texts: TextSource, context: ObservedContext, make=None) -> dict:
    """What keeps forecasts from being EXACT, and how many would be if one blocker class were resolved."""
    sets = []
    for current, _ in pairs:
        used = make(current) if make is not None else context
        forecast = forecast_action(current.state, current.action, texts, used)
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
                if forecast.status is Status.UNSUPPORTED or forecast._candidate is None:
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


ABLATION = (
    ("nothing", ()),
    ("sanctum", ("sanctum",)),
    ("sanctum+healing", ("sanctum", "healing")),
    ("sanctum+healing+hero_shield", ("sanctum", "healing", "hero_shield")),
    ("sanctum+healing+hero_shield+hand_keywords", ("sanctum", "healing", "hero_shield", "hand_keywords")),
    ("all five groups", ("sanctum", "healing", "hero_shield", "hand_keywords", "spell_damage")),
    ("hand_keywords only", ("hand_keywords",)),
    ("spell_damage only", ("spell_damage",)),
    ("hero_shield only", ("hero_shield",)),
    ("healing only", ("healing",)),
)


def ablation(pairs, texts: TextSource, make_for_groups, associations=None) -> list[dict]:
    """How many forecasts reach each tier when only some observed-fact groups are available.

    With ``associations`` the pairs are also scored against the next observation, so each row shows which group adds
    confirmed effect claims and which adds contradicted ones.
    """
    rows = []
    for name, groups in ABLATION:
        make = make_for_groups(frozenset(groups))
        if associations is None:
            tiers = Counter(forecast_action(current.state, current.action, texts, make(current)).tier.value
                            for current, _ in pairs)
            rows.append({"facts": name, "tiers": dict(tiers)})
            continue
        results = [score_pair(current, following, texts, make(current), associations) for current, following in pairs]
        section = summarise_results(results)["tiers"]
        rows.append({"facts": name, "tiers": {tier: data["n"] for tier, data in section.items()},
                     "effect_claims": {tier: data["effect_claims"] for tier, data in section.items()
                                       if tier in ("EXACT", "OWN_EFFECT_KNOWN")}})
    return rows


def effect_delta(before: list[PairResult], after: list[PairResult]) -> dict:
    """What the extra facts changed in the claims about EFFECT paths, judged against the next logged observation.

    ``changed_value_confirmed``: the claim existed before and after with different values and the new one was
    confirmed, i.e. the fact corrected a number, it did not only remove a warning.
    """
    counts: Counter = Counter()
    for old, new in zip(before, after, strict=True):
        for path, value in new.confirmed.items():
            if role_of(path) != "EFFECT":
                continue
            if path in old.confirmed:
                counts["changed_value_confirmed" if old.confirmed[path] != value else "unchanged_confirmed"] += 1
            elif path in old.contradicted:
                counts["fixed_contradiction"] += 1
            else:
                counts["newly_confirmed"] += 1
        for path in new.contradicted:
            if role_of(path) != "EFFECT" or path in old.contradicted:
                continue
            counts["regressed_confirmed_to_contradicted" if path in old.confirmed else "newly_contradicted_claim"] += 1
        for path in old.contradicted:
            if role_of(path) == "EFFECT" and path not in new.contradicted and path not in new.confirmed:
                counts["contradiction_removed_without_claim"] += 1
        for path in old.confirmed:
            if role_of(path) == "EFFECT" and path not in new.confirmed and path not in new.contradicted:
                counts["confirmed_claim_withdrawn"] += 1
    return dict(sorted(counts.items()))


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
    parser.add_argument("--out", default=str(ROOT / "reports" / "observation_ext_1a" / "real_log_verification.json"))
    parser.add_argument("--examples", type=int, default=12)
    parser.add_argument("--facts", default="data/processed_observation_probe_1b/facts.jsonl",
                        help="per-decision SELF facts from observation_probe_1b.py; adds the observed_facts_1b run")
    parser.add_argument("--discrepancies-for", nargs="*", default=["observed_ext_1a"],
                        help="runs whose full discrepancy list is stored (the file stays reviewable)")
    parser.add_argument("--observed-facts", default="data/processed_observation_ext_1a/observed_facts.jsonl",
                        help="facts re-extracted by extract_observed_facts.py; adds the observed_ext_1a run")
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
    associations = build_gain_associations(pairs, texts)

    def locate(path: str) -> Path:
        found = Path(path)
        return found if found.exists() else next((p / path for p in ROOT.parents if (p / path).exists()), found)

    # name -> function(decision) -> ObservedContext; the facts are read from the decision's own entry only
    makers: dict[str, object] = {name: (lambda current, c=context: c) for name, context in CONTEXTS.items()}
    group_makers = {}
    legacy_path = locate(args.facts)
    if legacy_path.exists():
        legacy = load_facts(legacy_path)
        makers["observed_facts_1b"] = lambda current: (
            context_from_facts(legacy[current.decision_id], current.state)
            if current.decision_id in legacy else ObservedContext())
        group_makers["observed_facts_1b"] = lambda groups: (lambda current: (
            context_from_facts(legacy[current.decision_id], current.state, groups)
            if current.decision_id in legacy else ObservedContext()))
    ext_path = locate(args.observed_facts)
    if ext_path.exists():
        extracted = {}
        for line in ext_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            extracted[row["decision_id"]] = ObservedFacts.from_dict(row["facts"]) if row["facts"] else None
        report["observed_ext_1a_input"] = {
            "rows": len(extracted), "sha256": hashlib.sha256(ext_path.read_bytes()).hexdigest()}
        makers["observed_ext_1a"] = lambda current: context_from_observed(
            extracted.get(current.decision_id), current.state)
        group_makers["observed_ext_1a"] = lambda groups: (lambda current: context_from_observed(
            extracted.get(current.decision_id), current.state, groups))
    all_results: dict[str, list[PairResult]] = {}
    for name, make in makers.items():
        results = [score_pair(current, following, texts, make(current), associations) for current, following in pairs]
        all_results[name] = results
        section = summarise_results(results)
        section["blockers"] = blocker_analysis(pairs, texts, ObservedContext(), make)
        section["jail_913"] = card_section(results, "JAIL_913")
        if name in args.discrepancies_for:
            section["gain_associations"] = {
                card: {"appearances": a.appearances,
                       "signatures": {f"{k[0]}/{k[1]}": v for k, v in a.signatures.items()},
                       "always_with_own_secret_object": a.always_with_own_secret_object}
                for card, a in associations.items() if a.appearances >= 5}
            # every discrepancy of the two reliable tiers, with its explanation: the list is the audit trail
            section["discrepancies"] = [
                {"decision": r.decision_id, "action": r.action_label, "tier": r.tier.value, "path": path,
                 "kind": kind, "values": list(pair) if pair else None,
                 "explanation": list(r.explanations.get(path, ("UNEXPLAINED", "", ""))),
                 "open_unknowns": list(r.unknown_tags)}
                for r in results if r.tier in (Tier.EXACT, Tier.OWN_EFFECT_KNOWN)
                for kind, bucket in (("contradicted", r.contradicted), ("missed", r.missed))
                for path, pair in bucket.items()]
        else:
            section["gain_associations"] = section["discrepancies"] = "omitted: stored for " + ", ".join(
                args.discrepancies_for)
        section["exact_violations"] = [
            {"decision": r.decision_id, "action": r.action_label,
             "contradicted": {k: list(v) for k, v in r.contradicted.items()}}
            for r in results if r.tier is Tier.EXACT and r.verdict != "CONFIRMED"]
        report["runs"][name] = section
    for after_name in ("observed_facts_1b", "observed_ext_1a"):
        if after_name in all_results:
            report.setdefault("effect_delta", {})[after_name] = {
                f"vs_{before_name}": effect_delta(all_results[before_name], all_results[after_name])
                for before_name in ("observed_only", "assumed_defaults")}
    for name, make_for_groups in group_makers.items():
        report.setdefault("fact_group_ablation", {})[name] = ablation(
            pairs, texts, make_for_groups, associations if name == "observed_ext_1a" else None)
    report["menu_scan"] = menu_scan(games, texts)
    report["timing"] = timing(games, pairs, texts)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    for name, section in report["runs"].items():
        print(f"[{name}] pairs={section['pairs']} status={section['status']} tiers=" +
              json.dumps({k: (v['n'], v['effect_claims']) for k, v in section['tiers'].items()}))
    print("timing:", json.dumps(report["timing"]))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
