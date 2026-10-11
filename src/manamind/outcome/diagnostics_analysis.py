"""Offline census of the mechanical diagnostics over finished, labelled games (CONSEQUENCE-DIAGNOSTICS-1).

The Policy ranks come from shadow rows that were recorded live (or replayed); the forecasts and flags are recomputed
with the *current* texts, grammar and diagnostics from each decision's own state and facts. The player's action
comes from the finished log and is used only to count how often a flagged action was actually taken; agreement
with the player is never a measure of whether a flag is right, and these games are a diagnostic sample, not an
independent validation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from manamind.cards.catalog import CardCatalog
from manamind.outcome.diagnostics import FLAGS, diagnose_menu
from manamind.outcome.forecast import describe_action, forecast_action
from manamind.outcome.observation import context_from_observed
from manamind.outcome.shadow import action_digest
from manamind.outcome.shadow_analysis import label_recording
from manamind.outcome.texts import TextSource


def _bucket(rank: int) -> str:
    return "top1" if rank == 1 else "top3" if rank <= 3 else "rest"


# Sensitivity levels: which abstention reasons to switch off. Only the first (nothing ignored) is what LIVE uses.
RELAXATIONS: dict[str, frozenset[str]] = {
    "strict (production)": frozenset(),
    "ignore OWN_SECRET_OR_QUEST": frozenset({"OWN_SECRET_OR_QUEST"}),
    "ignore OWN_SECRET_OR_QUEST, BOARD_TRIGGER": frozenset({"OWN_SECRET_OR_QUEST", "BOARD_TRIGGER"}),
    "ignore all text/trigger abstentions": frozenset({"OWN_SECRET_OR_QUEST", "BOARD_TRIGGER", "BOARD_STATIC_TEXT",
                                                      "BOARD_TEXT_MISSING", "OWN_TEXT_MISSING", "AURA_ON_BOARD"}),
    "ignore everything incl. Deathrattle": frozenset({"OWN_SECRET_OR_QUEST", "BOARD_TRIGGER", "BOARD_STATIC_TEXT",
                                                      "BOARD_TEXT_MISSING", "OWN_TEXT_MISSING", "DEATHRATTLE_POSSIBLE",
                                                      "AURA_ON_SUMMON", "AURA_ON_BOARD"}),
}


def info_of(items) -> dict[int, tuple]:
    return {i: (a, r, d) for i, a, _, r, d in items}


def census(shadow_rows: Iterable[dict[str, Any]], recordings: dict[str, list[Path]], catalog: CardCatalog,
           texts: TextSource, examples: int = 40) -> dict[str, Any]:
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in shadow_rows:
        if row.get("event") == "OUTCOME_SHADOW":
            by_game[row["match_id"]].append(row)
    stat: Counter = Counter()
    decisions: dict[str, set] = defaultdict(set)         # "<flag> <bucket>" -> {(game, options_id)}
    reasons: Counter = Counter()
    sens: dict[str, set] = defaultdict(set)
    seen_examples: set = set()
    chosen_flagged: list[dict[str, Any]] = []
    shown: list[dict[str, Any]] = []
    for game_key, rows in by_game.items():
        game = None
        for directory in recordings.get(game_key[:16], []):
            labelled, _ = label_recording(directory, catalog)
            game = labelled.get(game_key)
            if game is not None:
                break
        if game is None:
            stat["games_not_labelled"] += 1
            continue
        stat["games"] += 1
        for row in rows:
            number = row["options_id"]
            logged = game.decisions.get(number)
            if logged is None or game.example_hashes[number] != row["state_hash"]:
                continue
            state = logged.state
            context = context_from_observed(game.facts.get(number), state)
            rank = {a["action"]: a["rank"] for a in row["actions"]}
            chosen = action_digest(logged.action)
            items = []
            for index, action in enumerate(logged.legal_actions):
                digest = action_digest(action)
                if digest in rank:
                    items.append((index, action, forecast_action(state, action, texts, context), rank[digest], digest))
            stat["decisions"] += 1
            diagnosis = diagnose_menu(state, [(i, a, f) for i, a, f, _, _ in items], texts=texts)
            for level, ignore in RELAXATIONS.items():
                relaxed = diagnose_menu(state, [(i, a, f) for i, a, f, _, _ in items], texts=texts, ignore=ignore)
                for flag in relaxed.flags:
                    _, ranking, digest = next(v for k, v in info_of(items).items() if k == flag.index)
                    if ranking <= 3:
                        sens[f"{level} | {flag.flag} top3 decisions"].add((game_key, number))
                        if ranking == 1:
                            sens[f"{level} | {flag.flag} top1 decisions"].add((game_key, number))
                    if digest == chosen:
                        sens[f"{level} | {flag.flag} chosen by player"].add((game_key, number))
            info = {i: (a, r, d) for i, a, _, r, d in items}
            for flag in diagnosis.flags:
                action, ranking, digest = info[flag.index]
                bucket = _bucket(ranking)
                stat[f"{flag.flag} actions {bucket}"] += 1
                decisions[f"{flag.flag} {bucket}"].add((game_key, number))
                if ranking <= 3:
                    decisions[f"{flag.flag} top3_or_better"].add((game_key, number))
                if digest == chosen:
                    stat[f"{flag.flag} CHOSEN_BY_PLAYER"] += 1
                    chosen_flagged.append({"game": game_key[:8], "decision": number, "flag": flag.flag,
                                           "action": describe_action(state, action), "rank": ranking})
                if flag.against is not None and info[flag.against][2] == chosen:
                    decisions[f"{flag.flag} took_dominator"].add((game_key, number))
                key = (game_key, number, describe_action(state, action).split(" (position")[0])
                if ranking <= 3 and len(shown) < examples and key not in seen_examples:
                    seen_examples.add(key)
                    against = None if flag.against is None else describe_action(state, info[flag.against][0])
                    shown.append({"game": game_key[:8], "decision": number, "flag": flag.flag, "rank": ranking,
                                  "action": describe_action(state, action), "against": against})
            for index, flag, reason in diagnosis.blocked_at:
                bucket = _bucket(info[index][1])
                reasons[f"{flag} {reason} {bucket}"] += 1
                if bucket != "rest":
                    decisions[f"{flag} blocked {reason}"].add((game_key, number))
            for index, flag in diagnosis.insufficient_at:
                reasons[f"{flag} INSUFFICIENT_FORECAST {_bucket(info[index][1])}"] += 1
    out: dict[str, Any] = {"games": stat["games"], "games_not_labelled": stat["games_not_labelled"],
                           "decisions": stat["decisions"]}
    for flag in FLAGS:
        out[flag] = {
            "actions": {b: stat[f"{flag} actions {b}"] for b in ("top1", "top3", "rest")},
            "distinct_decisions": {b: len(decisions[f"{flag} {b}"]) for b in ("top1", "top3", "rest")},
            "distinct_decisions_with_flag_in_top3": len(decisions[f"{flag} top3_or_better"]),
            "chosen_by_player": stat[f"{flag} CHOSEN_BY_PLAYER"],
            "decisions_where_player_took_the_dominating_alternative": len(decisions[f"{flag} took_dominator"]),
        }
    out["sensitivity"] = {f"{level} | {flag}": {
        "top3_decisions": len(sens[f"{level} | {flag} top3 decisions"]),
        "top1_decisions": len(sens[f"{level} | {flag} top1 decisions"]),
        "chosen_by_player": len(sens[f"{level} | {flag} chosen by player"])}
        for level in RELAXATIONS for flag in FLAGS}
    out["abstention_reasons_by_rank"] = dict(sorted(reasons.items()))
    out["distinct_decisions_blocked_in_top3"] = {k: len(v) for k, v in sorted(decisions.items()) if " blocked " in k}
    out["chosen_flagged"] = chosen_flagged
    out["examples_top3"] = shown
    return out
