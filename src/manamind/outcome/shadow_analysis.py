"""Offline analysis of outcome-shadow journals (ACTION-OUTCOME-2): coverage, invariants and checks against what happened.

Two independent parts, both read-only:

``coverage_summary``  works on the shadow journal alone: how much of the menu is forecastable, what keeps it
                      PARTIAL / UNSUPPORTED, how much of a PARTIAL forecast is still an exact local effect, latency.
``verify_recordings`` joins shadow rows to the LIVE recordings of *completed* games. The recording is re-labelled by
                      the offline importer (which reads the player's choice from the log), the forecast is recomputed
                      from the decision's own state and facts - never from later events - and compared with the
                      recorded digest; only then is the forecast of the action the player took scored against the
                      next observation. Alternatives have no observed result and are only counted.

Agreement between the player's choice and the Policy rank is reported as imitation, never as evidence about either
being a good move.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from manamind.cards.catalog import CardCatalog
from manamind.domain.game_state import GameState
from manamind.domain.serialization import game_state_from_dict
from manamind.integrations.powerlog.observed_facts import ObservedFacts
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match
from manamind.outcome.compare import summarise
from manamind.outcome.forecast import forecast_action
from manamind.outcome.model import Forecast, Status
from manamind.outcome.observation import context_from_observed
from manamind.outcome.shadow import (
    ERROR, NOT_COMPUTED, SHADOW_SCHEMA, action_digest, context_to_dict, forecast_digest,
)
from manamind.outcome.texts import TextSource
from manamind.outcome.verify import (
    LoggedDecision, build_gain_associations, score_pair, successor_pairs, summarise_results,
)

REACTION_KINDS = ("CONFIRMED_REACTION", "CONSISTENT_UNCONFIRMED", "DECLARED_GAP")
OBSERVATION_LIMIT_KINDS = ("OBSERVATION_GAP", "COMPARISON_LIMIT")


# ----- reading -----------------------------------------------------------------------------------------------


@dataclass
class ShadowDecision:
    """All shadow rows of one decision. ``row`` is the OUTCOME_SHADOW row (None when only errors were written)."""

    decision_id: str
    row: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    invalidations: list[str] = field(default_factory=list)


def read_shadow_rows(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], int]:
    """All parseable rows, in file order; the second value counts lines that were not valid JSON objects."""
    rows, bad = [], 0
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(row, dict) and "event" in row and "decision_id" in row:
                rows.append(row)
            else:
                bad += 1
    return rows, bad


def group_decisions(rows: Iterable[dict[str, Any]]) -> dict[str, ShadowDecision]:
    decisions: dict[str, ShadowDecision] = {}
    for row in rows:
        decision = decisions.setdefault(row["decision_id"], ShadowDecision(row["decision_id"]))
        event = row["event"]
        if event == "OUTCOME_SHADOW":
            decision.row = row
        elif event == "OUTCOME_SHADOW_ERROR":
            decision.errors.append(row.get("reason", "UNKNOWN"))
        elif event == "OUTCOME_SHADOW_INVALIDATION":
            decision.invalidations.append(row.get("reason", "UNKNOWN"))
    return decisions


# ----- invariants ----------------------------------------------------------------------------------------------


def invariant_violations(row: dict[str, Any]) -> list[str]:
    """Properties every record must have; a non-empty result is a bug in the shadow, not a forecast error."""
    problems: list[str] = []
    if row.get("schema") != SHADOW_SCHEMA:
        problems.append("SCHEMA")
    actions = row.get("actions", [])
    if row.get("menu_size") != len(actions):
        problems.append("MENU_SIZE")
    if sorted(a["rank"] for a in actions) != list(range(1, len(actions) + 1)):
        problems.append("RANK_SET")
    if len({a["index"] for a in actions}) != len(actions):
        problems.append("DUPLICATE_INDEX")
    for action in actions:
        status = action["status"]
        if status in (NOT_COMPUTED, ERROR):
            continue
        unknowns = action.get("unknowns", [])
        if status == Status.EXACT.value and (unknowns or action.get("tier") != "EXACT" or action.get("bounds")):
            problems.append("EXACT_WITH_OPEN_UNKNOWNS")
        if status == Status.PARTIAL.value and (not unknowns and not action.get("bounds")
                                               or action.get("tier") in ("EXACT", "UNSUPPORTED")):
            problems.append("PARTIAL_WITHOUT_OPEN_UNKNOWNS")
        if status == Status.UNSUPPORTED.value and (action.get("tier") != "UNSUPPORTED" or action.get("effects")
                                                    or not action.get("reason")):
            problems.append("UNSUPPORTED_WITH_EFFECTS")
        if not action.get("digest"):
            problems.append("NO_DIGEST")
    if row.get("computed", 0) + row.get("not_computed", 0) + row.get("errors", 0) != len(actions):
        problems.append("COUNTERS")
    return problems


# ----- coverage (shadow journal only) --------------------------------------------------------------------------


def _percentiles(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {"n": len(values), "median": round(float(np.percentile(values, 50)), 3),
            "p95": round(float(np.percentile(values, 95)), 3), "max": round(float(max(values)), 3)}


def action_type_of(action_row: dict[str, Any]) -> str:
    return action_row["label"].split(" ", 1)[0]


def coverage_summary(decisions: dict[str, ShadowDecision]) -> dict[str, Any]:
    rows = [d.row for d in decisions.values() if d.row is not None]
    actions = [(row, a) for row in rows for a in row["actions"]]
    computed = [(row, a) for row, a in actions if a["status"] not in (NOT_COMPUTED, ERROR)]
    not_end = [(row, a) for row, a in computed if action_type_of(a) != "END_TURN"]

    def has_effect(a: dict[str, Any]) -> bool:
        return bool(a.get("effects"))

    def group(items: list[tuple[dict, dict]]) -> dict[str, Any]:
        statuses = Counter(a["status"] for _, a in items)
        partial = [a for _, a in items if a["status"] == Status.PARTIAL.value]
        return {
            "actions": len(items),
            "status": dict(statuses),
            "tier": dict(Counter(a["tier"] for _, a in items)),
            "with_exact_effect": sum(has_effect(a) for _, a in items),
            "own_effect_known": sum(bool(a["own"]) for _, a in items),
            "partial_with_exact_effect": sum(has_effect(a) for a in partial),
            "partial_own_effect_known": sum(bool(a["own"]) for a in partial),
        }

    by_type: dict[str, list] = defaultdict(list)
    for row, a in computed:
        by_type[action_type_of(a)].append((row, a))
    blockers = Counter()
    for _, a in computed:
        if a["status"] == Status.PARTIAL.value:
            blockers.update(set(a.get("unknowns", [])))
    unsupported = Counter(a.get("reason", "?") for _, a in computed if a["status"] == Status.UNSUPPORTED.value)
    decisions_useful = sum(
        any(action_type_of(a) != "END_TURN" and a["status"] not in (NOT_COMPUTED, ERROR) and a["own"]
            and has_effect(a) for a in row["actions"]) for row in rows)
    menu_sizes = [row["menu_size"] for row in rows]
    return {
        "decisions": len(decisions),
        "decisions_with_record": len(rows),
        "decisions_with_error_only": sum(d.row is None and bool(d.errors) for d in decisions.values()),
        "error_reasons": dict(Counter(r for d in decisions.values() for r in d.errors)),
        "incomplete_decisions": sum(not row["complete"] for row in rows),
        "menu_actions": len(actions),
        "not_computed": sum(a["status"] == NOT_COMPUTED for _, a in actions),
        "action_errors": sum(a["status"] == ERROR for _, a in actions),
        "all_computed_actions": group(computed),
        "excluding_end_turn": group(not_end),
        "by_action_type": {kind: group(items) for kind, items in sorted(by_type.items())},
        "partial_blockers": dict(blockers.most_common()),
        "unsupported_reasons": dict(unsupported.most_common()),
        "decisions_with_a_useful_known_effect": decisions_useful,
        "coverage_context": dict(Counter(row.get("coverage", "?") for row in rows)),
        "context_failed": sum(bool(row.get("context_failed")) for row in rows),
        "invalidation_reasons": dict(Counter(
            d.invalidations[0].split(":", 1)[0] for d in decisions.values() if d.invalidations)),
        "never_invalidated": sum(d.row is not None and not d.invalidations for d in decisions.values()),
        "menu_size": _percentiles([float(n) for n in menu_sizes]),
        "decision_forecast_ms": _percentiles([row["elapsed_ms"] for row in rows]),
        "action_forecast_us": _percentiles([float(a["us"]) for _, a in computed if "us" in a]),
        "invariant_violations": dict(Counter(p for row in rows for p in invariant_violations(row))),
    }


# ----- verification against recordings -------------------------------------------------------------------------


@dataclass
class LabeledGame:
    decisions: dict[int, LoggedDecision]
    facts: dict[int, ObservedFacts | None]
    example_hashes: dict[int, str]
    pairs: list[tuple[LoggedDecision, LoggedDecision]]
    failure: str | None = None


def _options_id(decision_id: str) -> int:
    return int(decision_id.rsplit(":", 1)[1])


def label_recording(directory: Path, catalog: CardCatalog) -> tuple[dict[str, LabeledGame], str | None]:
    """The offline importer over one recording's ``slice.log``: {game_key: labeled game}, or a stable failure."""
    text = (Path(directory) / "slice.log").read_text(encoding="utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    facts: dict[str, ObservedFacts | None] = {}
    try:
        examples, summary = extract_match(lines, catalog, observer=lambda decision, f: facts.__setitem__(decision, f))
    except PolicyImportError as error:
        return {}, error.reason
    decisions: dict[int, LoggedDecision] = {}
    hashes: dict[int, str] = {}
    for row in examples:
        number = _options_id(row["decision_id"])
        decisions[number] = LoggedDecision(
            game_id=row["game_id"], number=number, decision_id=row["decision_id"],
            state=game_state_from_dict(row["state"]), action=row["legal_actions"][row["chosen_action_index"]],
            legal_actions=tuple(row["legal_actions"]))
        hashes[number] = row["provenance"]["state_hash"]
    ordered = sorted(decisions.values(), key=lambda item: item.number)
    pairs = list(successor_pairs({summary["game_id"]: ordered}))
    return {summary["game_id"]: LabeledGame(
        decisions, {_options_id(k): v for k, v in facts.items()}, hashes, pairs)}, None


def find_recordings(root: Path) -> dict[str, list[Path]]:
    """{first 16 hex of game_key: recording directories}, found under ``<root>/<session>/<key16>/slice.log``."""
    found: dict[str, list[Path]] = defaultdict(list)
    for slice_log in sorted(Path(root).glob("*/*/slice.log")):
        found[slice_log.parent.name].append(slice_log.parent)
    return found


def verify_recordings(decisions: dict[str, ShadowDecision], recordings: dict[str, list[Path]],
                      catalog: CardCatalog, texts: TextSource) -> dict[str, Any]:
    rows = [d.row for d in decisions.values() if d.row is not None]
    labeled: dict[Path, tuple[dict[str, LabeledGame], str | None]] = {}
    unmatched = Counter()
    matched: list[tuple[dict, LabeledGame, LoggedDecision]] = []
    for row in rows:
        game_key, number = row["match_id"], row["options_id"]
        candidates = recordings.get(game_key[:16], [])
        if not candidates:
            unmatched["NO_RECORDING"] += 1
            continue
        hit = None
        reason = "GAME_NOT_ANALYZABLE"
        for directory in candidates:
            if directory not in labeled:
                labeled[directory] = label_recording(directory, catalog)
            games, failure = labeled[directory]
            game = games.get(game_key)
            if game is None:
                reason = f"IMPORT_{failure}" if failure else reason
                continue
            logged = game.decisions.get(number)
            if logged is None:
                reason = "DECISION_NOT_LABELED"
            elif game.example_hashes[number] != row["state_hash"]:
                reason = "STATE_HASH_MISMATCH"
            else:
                hit = (game, logged)
                break
        if hit is None:
            unmatched[reason] += 1
        else:
            matched.append((row, hit[0], hit[1]))

    digests = {"digest_match": 0, "digest_mismatch": 0}
    checks: Counter = Counter()
    chosen_status: Counter = Counter()
    chosen_by_rank: Counter = Counter()
    chosen_unscorable: Counter = Counter()
    pair_results = []
    all_pairs = [pair for game in {id(g): g for _, g, _ in matched}.values() for pair in game.pairs]
    associations = build_gain_associations(all_pairs, texts) if all_pairs else {}
    alternatives = Counter()
    gifts: Counter = Counter()
    for row, game, logged in matched:
        state = logged.state
        context = context_from_observed(game.facts.get(logged.number), state)
        checks["context_reproduced" if context_to_dict(context) == row["context"] else "context_mismatch"] += 1
        by_digest = {a["action"]: a for a in row["actions"]}
        legal = {action_digest(a): a for a in logged.legal_actions}
        checks["menu_identical" if set(legal) == set(by_digest) else "menu_mismatch"] += 1
        reproduced = True
        forecasts = {}
        for digest_key, record in by_digest.items():
            if record["status"] in (NOT_COMPUTED, ERROR) or digest_key not in legal:
                continue
            forecasts[digest_key] = forecast_action(state, legal[digest_key], texts, context)
            same = forecast_digest(forecasts[digest_key]) == record["digest"]
            digests["digest_match" if same else "digest_mismatch"] += 1
            if digest_key == action_digest(logged.action):
                reproduced = same
        _count_gifts(gifts, state, row, forecasts, action_digest(logged.action))
        chosen = by_digest.get(action_digest(logged.action))
        if chosen is None:
            chosen_unscorable["CHOSEN_NOT_IN_RECORDED_MENU"] += 1
            continue
        chosen_status[chosen["status"]] += 1
        chosen_by_rank[chosen["rank"]] += 1
        alternatives["alternatives_no_observed_outcome"] += len(row["actions"]) - 1
        if chosen["status"] in (NOT_COMPUTED, ERROR):
            chosen_unscorable["CHOSEN_NOT_FORECAST"] += 1
        elif not reproduced:
            chosen_unscorable["CHOSEN_FORECAST_NOT_REPRODUCED"] += 1
        else:
            following = next((nxt for cur, nxt in game.pairs if cur is logged), None)
            if following is None:
                chosen_unscorable["NO_OBSERVATION_AFTER_ACTION"] += 1
            else:
                result = score_pair(logged, following, texts, context, associations)
                pair_results.append(result)
    summary = summarise_results(pair_results) if pair_results else {}
    discrepancy = _discrepancy_buckets(pair_results)
    top1 = chosen_by_rank.get(1, 0)
    total_rank = sum(chosen_by_rank.values())
    return {
        "shadow_decisions": len(rows),
        "joined_to_recording": len(matched),
        "not_joined": dict(unmatched),
        "reproduction": {**checks, **{f"action_{k}": v for k, v in digests.items()}},
        "chosen_action": {
            "status": dict(chosen_status),
            "policy_rank": {str(rank): count for rank, count in sorted(chosen_by_rank.items())},
            "imitation_top1": top1,
            "imitation_top3": sum(c for r, c in chosen_by_rank.items() if r <= 3),
            "decisions": total_rank,
            "note": "agreement with the Policy ranks is imitation of the player, not evidence that either was best",
            "unscorable": dict(chosen_unscorable),
        },
        "alternatives": dict(alternatives),
        "opponent_only_improvement": dict(gifts),
        "scored_pairs": len(pair_results),
        "scored": summary,
        "discrepancies": discrepancy,
        "exact_forecasts_contradicted": sum(
            1 for r in pair_results if r.status is Status.EXACT and r.contradicted),
    }


def _is_gift(state: GameState, forecast: Forecast) -> bool:
    """Exact direct effects only improve OPPONENT-controlled entities and the action's own effect is fully understood."""
    return (forecast.own_effect_known and forecast.status is not Status.UNSUPPORTED
            and summarise(state, forecast).note.startswith("direct effects only improve OPPONENT"))


def _count_gifts(counter: Counter, state: GameState, row: dict[str, Any], forecasts: dict[str, Forecast],
                 taken: str) -> None:
    """Descriptive counts for the 'gift' pattern; a gift is a bookkeeping fact about direct effects, not a verdict."""
    gift_digests = {key for key, forecast in forecasts.items() if _is_gift(state, forecast)}
    counter["decisions"] += 1
    if not gift_digests:
        return
    top = min(row["actions"], key=lambda a: a["rank"])["action"]
    counter["decisions_offering_one"] += 1
    counter["taken_by_player"] += taken in gift_digests
    if top in gift_digests:
        counter["policy_top1_is_one"] += 1
        counter["policy_top1_gift_taken_by_player"] += top == taken
        counter["policy_top1_gift_with_non_gift_in_top3"] += any(
            a["action"] not in gift_digests and a["rank"] <= 3 and a["status"] not in (NOT_COMPUTED, ERROR)
            for a in row["actions"])


def _discrepancy_buckets(results: list) -> dict[str, Any]:
    """Paths where the observation disagrees with the forecast, by what is known about the reason."""
    contradicted, missed = Counter(), Counter()
    for result in results:
        for path in result.contradicted:
            contradicted[result.explanations.get(path, ("UNEXPLAINED",))[0]] += 1
        for path in result.missed:
            missed[result.explanations.get(path, ("UNEXPLAINED",))[0]] += 1

    def bucket(counter: Counter) -> dict[str, int]:
        return {
            "unknown_reaction_or_declared_gap": sum(counter[k] for k in REACTION_KINDS),
            "observation_or_comparison_limit": sum(counter[k] for k in OBSERVATION_LIMIT_KINDS),
            "unexplained": counter["UNEXPLAINED"],
        }

    return {"contradicted_claims": bucket(contradicted), "missed_changes": bucket(missed),
            "contradicted_by_explanation": dict(contradicted), "missed_by_explanation": dict(missed)}
