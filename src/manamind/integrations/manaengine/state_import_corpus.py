"""ENGINE-STATE-IMPORT-0: read existing sanitized corpora, sample deterministically, aggregate sanitized metrics.

Reads only already-sanitized artifacts (policy decision records, live snapshots, Value examples). It never parses
Power.log and never opens raw log slices. Aggregates contain no game IDs, handles or per-game trajectories.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from manamind.integrations.manaengine.state_import_capability import CapabilityIndex
from manamind.integrations.manaengine.state_import_readiness import (
    ANALYZER_VERSION, BLOCKER_SPECS, RESOLUTIONS, PositionDiagnostic, analyze_position,
)

SOURCE_KINDS = ("POLICY_DECISION", "LIVE_SNAPSHOT", "VALUE_EXAMPLE")
MIN_GAMES_FOR_CARD_LISTING = 2
UNIVERSAL_PERCENT = 99.5  # blockers at or above this share of positions do not discriminate between positions
SUBSYSTEMS = ("GAME_TURN", "HERO", "HERO_POWER", "WEAPON", "BOARD", "LOCATION", "SECRET", "HAND", "DECK", "EFFECTS", "PENDING_CHOICE", "INTEGRITY")
_RESOLUTION_ORDER = ("OBSERVATION_EXTRACTION", "IMPORT_CONTRACT", "ENGINE_PRIMITIVE", "CARD_DECLARATION", "RULES_EVIDENCE", "DEFER")


@dataclass(frozen=True, slots=True)
class CorpusPosition:
    """One sanitized position. ``game_id`` is an opaque local grouping key and is never written to reports."""

    game_id: str
    position_id: str
    source_kind: str
    ordinal: int
    state: dict
    action: dict | None = None
    envelope: dict | None = None
    source_profile: str = "LIVE_SANITIZED"

    @property
    def is_self_decision(self) -> bool:
        return str(self.state.get("active_player", "")).upper() == "SELF" and (
            self.envelope is None or self.envelope.get("phase", "SELF_DECISION") == "SELF_DECISION")


@dataclass(frozen=True, slots=True)
class AnalyzedPosition:
    position: CorpusPosition
    diagnostic: PositionDiagnostic
    detail: dict


def _jsonl(path: Path) -> Iterator[tuple[int, dict | None]]:
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                yield number, None
                continue
            yield number, record if isinstance(record, dict) else None


def read_policy_positions(directory: Path) -> tuple[list[CorpusPosition], dict]:
    """ML-1B policy records (`*.jsonl`, not `.audit.json`): LIVE-sanitized SELF states with the chosen legal action."""
    positions: list[CorpusPosition] = []
    unreadable = 0
    files = sorted(Path(directory).glob("*.jsonl"))
    for path in files:
        for number, record in _jsonl(path):
            try:
                if not isinstance(record["state"], dict):
                    raise TypeError("state must be a mapping")
                action = record["legal_actions"][int(record["chosen_action_index"])]
                trusted = record.get("source") == "power_log_ranked_standard"
                envelope = {"status": "READY" if trusted else "UNTRUSTED_SOURCE", "game_type": "GT_RANKED", "format": "FT_STANDARD",
                            "phase": "SELF_DECISION", "opponent_identity_policy": "none"}
                positions.append(CorpusPosition(str(record["game_id"]), str(record["decision_id"]), "POLICY_DECISION", number,
                                                record["state"], action, envelope))
            except (TypeError, KeyError, IndexError, ValueError):
                unreadable += 1
    return positions, {"files": len(files), "unreadable_records": unreadable}


def read_live_positions(root: Path) -> tuple[list[CorpusPosition], dict]:
    """LIVE-0 `snapshots.jsonl` files under `<session>/<game>/`; the chosen action is not recorded there."""
    positions: list[CorpusPosition] = []
    unreadable = 0
    files = sorted(Path(root).glob("*/*/snapshots.jsonl"))
    for path in files:
        meta = {}
        meta_path = path.with_name("meta.json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}
        for number, record in _jsonl(path):
            if record is None or not isinstance(record.get("state"), dict):
                unreadable += 1
                continue
            envelope = {key: record.get(key) for key in ("status", "game_type", "format", "phase")}
            envelope["opponent_identity_policy"] = meta.get("opponent_identity_policy")
            positions.append(CorpusPosition(str(record.get("game_key", path.parent.name)), f"{record.get('game_key', path.parent.name)}:{record.get('seq', number)}",
                                            "LIVE_SNAPSHOT", number, record["state"], None, envelope))
    return positions, {"files": len(files), "unreadable_records": unreadable}


def read_value_positions(directory: Path) -> tuple[list[CorpusPosition], dict]:
    """Value-training examples: offline importer states (entity-order SELF hand, revealed-opponent policy)."""
    positions: list[CorpusPosition] = []
    unreadable = 0
    files = sorted(Path(directory).glob("*.jsonl"))
    for path in files:
        for number, record in _jsonl(path):
            if record is None or not isinstance(record.get("state"), dict) or "game_id" not in record:
                unreadable += 1
                continue
            positions.append(CorpusPosition(str(record["game_id"]), str(record.get("sample_id", f"{record['game_id']}:{number}")),
                                            "VALUE_EXAMPLE", number, record["state"], None, None, "OFFLINE_PARITY"))
    return positions, {"files": len(files), "unreadable_records": unreadable}


def _hash_rank(seed: int, position_id: str) -> str:
    return hashlib.sha256(f"{seed}:{position_id}".encode()).hexdigest()


def _strata(position: CorpusPosition) -> dict[str, str]:
    state = position.state
    own, other = state.get("self_player"), state.get("opponent")
    own, other = (own if isinstance(own, dict) else {}), (other if isinstance(other, dict) else {})
    turn = state.get("turn_number")
    turn = turn if isinstance(turn, int) and not isinstance(turn, bool) else 0
    board = len(own.get("board") or ()) + len(own.get("locations") or ())
    power = (own.get("hero_power") or {}).get("card_id", "NONE") if isinstance(own.get("hero_power"), dict) or own.get("hero_power") is None else "NONE"
    return {
        "opponent_class": str(other.get("player_class", "UNKNOWN")),
        "self_hero_power": str(power),
        "turn_bucket": "T1-3" if turn <= 3 else "T4-6" if turn <= 6 else "T7-9" if turn <= 9 else "T10+",
        "board_bucket": "B0" if board == 0 else "B1-2" if board <= 2 else "B3-4" if board <= 4 else "B5+",
        "chosen_action": str((position.action or {}).get("type", "NONE")),
    }


def select_sample(positions: Iterable[CorpusPosition], size: int, seed: int, per_game_cap: int = 3) -> list[CorpusPosition]:
    """Greedy balanced sample: each pick favors under-represented stratum values and games; ties break by a seeded hash.

    Depends only on position content and the seed (not on file system order), caps picks per game, and so spreads over
    games, turns, board sizes, opponent classes, Hero Power identities and chosen action types where the corpus has them.
    """
    candidates = sorted((p for p in positions if p.is_self_decision), key=lambda p: _hash_rank(seed, p.position_id))
    picked: dict[str, Counter] = defaultdict(Counter)
    per_game: Counter = Counter()
    chosen: list[CorpusPosition] = []
    pool = list(candidates)
    while pool and len(chosen) < size:
        best_index, best_gain = None, -1.0
        for index, candidate in enumerate(pool):
            if per_game[candidate.game_id] >= per_game_cap:
                continue
            gain = sum(1.0 / (1 + picked[key][value]) for key, value in _strata(candidate).items()) + 2.0 / (1 + per_game[candidate.game_id])
            if gain > best_gain:
                best_index, best_gain = index, gain
        if best_index is None:
            break
        pick = pool.pop(best_index)
        for key, value in _strata(pick).items():
            picked[key][value] += 1
        per_game[pick.game_id] += 1
        chosen.append(pick)
    return sorted(chosen, key=lambda p: p.position_id)


def analyze_corpus(positions: Iterable[CorpusPosition], capability: CapabilityIndex) -> list[AnalyzedPosition]:
    result = []
    for position in positions:
        diagnostic = analyze_position(position.state, capability, action=position.action, snapshot=position.envelope, source_profile=position.source_profile)
        result.append(AnalyzedPosition(position, diagnostic, diagnostic.to_dict()))
    return result


def _pct(count: int, total: int) -> float:
    return round(100.0 * count / total, 2) if total else 0.0


def _is_source_gap(row: dict) -> bool:
    if row["category"] in ("UNKNOWN", "INCONSISTENT") and row["nature"] != "INHERENTLY_HIDDEN":
        return True
    return row["category"] == "NOT_REPRESENTED" and row["axis"] in ("SOURCE", "BOTH")


def _rank(counter: dict[str, set], limit: int) -> list[dict]:
    rows = sorted(counter.items(), key=lambda item: (-len(item[1]), item[0]))
    return [{"key": key, "count": len(members)} for key, members in rows[:limit]]


def aggregate(analyzed: list[AnalyzedPosition]) -> dict:
    """Sanitized aggregate metrics. Counts are distinct positions or distinct games; overlapping groups are not additive."""
    total = len(analyzed)
    games = {a.position.game_id for a in analyzed}
    by_code_positions: dict[str, set] = defaultdict(set)
    by_code_games: dict[str, set] = defaultdict(set)
    by_category_positions: dict[str, set] = defaultdict(set)
    by_category_games: dict[str, set] = defaultdict(set)
    by_family: dict[str, set] = defaultdict(set)
    by_axis: dict[str, set] = defaultdict(set)
    by_resolution: dict[str, set] = defaultdict(set)
    resolution_codes: dict[str, set] = defaultdict(set)
    effects: dict[str, Counter] = defaultdict(Counter)
    subsystem_insufficient: dict[str, set] = defaultdict(set)
    cards: dict[str, dict[str, set]] = defaultdict(lambda: {"positions": set(), "games": set(), "codes": set(), "reasons": set()})
    hero_power_status: dict[str, Counter] = {"SELF": Counter(), "OPPONENT": Counter()}
    hero_power_ids: dict[str, Counter] = {"SELF": Counter(), "OPPONENT": Counter()}
    flags: dict[str, set] = defaultdict(set)
    nonhidden_by_position: dict[int, set] = {}
    resolution_by_position: dict[int, dict[str, set]] = {}
    co_occurrence: dict[str, Counter] = defaultdict(Counter)
    valid = 0
    for index, item in enumerate(analyzed):
        pid, gid, detail = index, item.position.game_id, item.detail
        valid += detail["structurally_valid"]
        rows = detail["blockers"]
        codes = {row["code"] for row in rows}
        nonhidden = {row["code"] for row in rows if row["nature"] != "INHERENTLY_HIDDEN"}
        nonhidden_by_position[pid] = nonhidden
        resolution_by_position[pid] = defaultdict(set)
        for row in rows:
            code = row["code"]
            if row["nature"] != "INHERENTLY_HIDDEN":
                resolution_by_position[pid][row["resolution"]].add(code)
            by_code_positions[code].add(pid)
            by_code_games[code].add(gid)
            by_category_positions[row["category"]].add(pid)
            by_category_games[row["category"]].add(gid)
            by_family[row["family"]].add(pid)
            axis_key = "SOURCE_HIDDEN_BY_DESIGN" if row["nature"] == "INHERENTLY_HIDDEN" else row["axis"]
            by_axis[axis_key].add(pid)
            by_resolution[row["resolution"]].add(pid)
            resolution_codes[row["resolution"]].add(row["code"])
            if _is_source_gap(row):
                subsystem_insufficient[row["subsystem"]].add(pid)
            # Opponent-origin identities are never listed, even when the capture revealed them.
            if row["category"] == "UNSUPPORTED_CARD" and row.get("card_id") and row.get("entity", [None, None])[:2] != ["HAND", "OPPONENT"]:
                entry = cards[row["card_id"]]
                entry["positions"].add(pid)
                entry["games"].add(gid)
                entry["codes"].add(code)
                entry["reasons"].add(row.get("detail") or "")
            if row["category"] == "UNSUPPORTED_CARD":
                flags["unsupported_card"].add(pid)
            if row["category"] == "UNSUPPORTED_MECHANIC":
                flags["unsupported_mechanic"].add(pid)
            if row["category"] == "RULE_UNRESOLVED":
                flags["rule_unresolved"].add(pid)
            if row["category"] == "NOT_REPRESENTED" and row["axis"] in ("NATIVE", "BOTH"):
                flags["missing_native_state"].add(pid)
            if row["category"] == "NOT_REPRESENTED" and row["axis"] in ("SOURCE", "BOTH"):
                flags["missing_in_game_state_contract"].add(pid)
            if row["category"] == "INCONSISTENT":
                flags["inconsistent"].add(pid)
            if row["nature"] == "INHERENTLY_HIDDEN":
                flags["hidden_information"].add(pid)
            if row["category"] == "UNKNOWN" and row["nature"] == "OBSERVABLE":
                flags["observable_but_unknown"].add(pid)
        per_code: dict[str, set] = defaultdict(set)
        for row in rows:
            per_code[row["code"]].add(row["chosen_action_effect"])
        for code, seen in per_code.items():
            for label in ("BLOCKS", "UNDETERMINED", "NOT_INVOLVED", "NOT_ASSESSED"):
                if label in seen:
                    effects[code][label] += 1
                    break
        for code in codes:
            for other in codes - {code}:
                co_occurrence[code][other] += 1
        for seat in ("SELF", "OPPONENT"):
            status = detail["hero_power"][seat]["status"]
            hero_power_status[seat][status] += 1
            hp_rows = [row for row in rows if row["subsystem"] == "HERO_POWER" and row.get("seat") == seat and row.get("card_id")]
            if hp_rows:
                hero_power_ids[seat][hp_rows[0]["card_id"]] += 1
            elif detail["hero_power"][seat]["status"] == "PROVEN_SUPPORTED_BASE":
                hero_power_ids[seat]["<reviewed base power>"] += 1
        if detail["hero_power"]["SELF"]["status"] != "PROVEN_SUPPORTED_BASE" or detail["hero_power"]["OPPONENT"]["status"] != "PROVEN_SUPPORTED_BASE":
            flags["hero_power_not_proven_supported_either_seat"].add(pid)
        if detail["hero_power"]["SELF"]["status"] != "PROVEN_SUPPORTED_BASE":
            flags["hero_power_not_proven_supported_self"].add(pid)
        if "HERO_POWER_ID_UNKNOWN" in codes:
            flags["hero_power_identity_missing"].add(pid)
        if detail["chosen_action"] is not None:
            outcome = {row["chosen_action_effect"] for row in rows}
            flags["chosen_action_directly_blocked" if "BLOCKS" in outcome else
                  "chosen_action_undetermined" if "UNDETERMINED" in outcome else "chosen_action_no_direct_blocker"].add(pid)
            if any(row["chosen_action_effect"] == "BLOCKS" and row["applies_to"] != "WHOLE" for row in rows):
                flags["chosen_action_blocked_by_action_specific_blocker"].add(pid)
            elif "BLOCKS" in outcome:
                flags["chosen_action_blocked_only_by_whole_position_blockers"].add(pid)
        if not nonhidden:
            flags["no_non_hidden_blocker"].add(pid)
        if detail["axes"]["source_completeness"] == "COMPLETE_VISIBLE_FIELDS":
            flags["source_complete_visible_fields"].add(pid)

    design_input = {i for i in range(total) if analyzed[i].detail["structurally_valid"]} - flags["inconsistent"]

    def share(name: str) -> dict:
        return {"positions": len(flags[name]), "percent": _pct(len(flags[name]), total)}

    funnel = []
    remaining = set(range(total))
    stages = (
        ("structurally_valid", lambda i: analyzed[i].detail["structurally_valid"]),
        ("no_inconsistent_blocker", lambda i: i not in flags["inconsistent"]),
        ("visible_fields_sufficient_and_represented", lambda i: i not in flags["observable_but_unknown"] and i not in flags["missing_in_game_state_contract"]),
        ("no_missing_native_state", lambda i: i not in flags["missing_native_state"]),
        ("no_unsupported_mechanic", lambda i: i not in flags["unsupported_mechanic"]),
        ("no_unsupported_card", lambda i: i not in flags["unsupported_card"]),
        ("no_unresolved_rule", lambda i: i not in flags["rule_unresolved"]),
        ("no_hidden_information_gap", lambda i: i not in flags["hidden_information"]),
    )
    for name, predicate in stages:
        alone = sum(1 for i in range(total) if predicate(i))
        remaining = {i for i in remaining if predicate(i)}
        funnel.append({"gate": name, "positions_passing_this_gate_alone": alone, "percent_alone": _pct(alone, total),
                       "positions_passing_all_gates_so_far": len(remaining), "percent_so_far": _pct(len(remaining), total)})

    cumulative = []
    cleared_resolutions: set[str] = set()
    for resolution in _RESOLUTION_ORDER:
        cleared_resolutions.add(resolution)
        cleared = [i for i in range(total) if all(res in cleared_resolutions for res in resolution_by_position[i] if resolution_by_position[i][res])]
        cleared_set = set(cleared)
        residual: Counter = Counter()
        for i in range(total):
            if i in cleared_set:
                continue
            for res, members in resolution_by_position[i].items():
                if res not in cleared_resolutions:
                    residual.update(members)
        cumulative.append({"after_resolving": sorted(cleared_resolutions, key=_RESOLUTION_ORDER.index), "positions_with_no_remaining_non_hidden_blocker": len(cleared),
                           "percent": _pct(len(cleared), total), "top_remaining_codes_by_position_count": [
                               {"code": code, "positions": count} for code, count in sorted(residual.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]})

    ranking = []
    for code, members in by_code_positions.items():
        spec = BLOCKER_SPECS[code]
        counts = effects[code]
        sole = sum(1 for pid in members if nonhidden_by_position[pid] == {code})
        ranking.append({
            "code": code, "category": spec.category.value, "subsystem": spec.subsystem, "axis": spec.axis, "nature": spec.nature,
            "family": spec.family, "recommended_resolution": spec.resolution,
            "distinct_positions": len(members), "distinct_games": len(by_code_games[code]),
            "percent_positions": _pct(len(members), total),
            "next_action_effect_positions": {name: counts[name] for name in sorted(counts)},
            "positions_where_it_is_the_only_non_hidden_blocker": sole,
            "most_frequent_co_blockers": [{"code": other, "positions": count} for other, count in
                                          sorted(co_occurrence[code].items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
        })
    ranking.sort(key=lambda row: (-row["distinct_positions"], -row["distinct_games"], row["code"]))
    by_games = sorted(ranking, key=lambda row: (-row["distinct_games"], -row["distinct_positions"], row["code"]))

    card_rows = []
    for card_id, entry in cards.items():
        if len(entry["games"]) >= MIN_GAMES_FOR_CARD_LISTING:
            card_rows.append({"card_id": card_id, "distinct_positions": len(entry["positions"]), "distinct_games": len(entry["games"]),
                              "blocker_codes": sorted(entry["codes"]), "reasons": sorted(r for r in entry["reasons"] if r)})
    card_rows.sort(key=lambda row: (-row["distinct_positions"], row["card_id"]))
    unlisted = sum(1 for entry in cards.values() if len(entry["games"]) < MIN_GAMES_FOR_CARD_LISTING)

    return {
        "unique_games": len(games),
        "decision_positions": total,
        "structurally_valid": {"positions": valid, "percent": _pct(valid, total)},
        "visible_fields_sufficient_by_subsystem": {
            name: {"positions": total - len(subsystem_insufficient[name]), "percent": _pct(total - len(subsystem_insufficient[name]), total)}
            for name in SUBSYSTEMS},
        "blocked_by": {
            "unsupported_card": share("unsupported_card"), "unsupported_mechanic": share("unsupported_mechanic"),
            "rule_unresolved": share("rule_unresolved"), "missing_native_state": share("missing_native_state"),
            "missing_in_game_state_contract": share("missing_in_game_state_contract"), "inconsistent_source": share("inconsistent"),
            "observable_but_unknown_field": share("observable_but_unknown"), "hidden_information": share("hidden_information"),
        },
        "hero_power": {
            "not_proven_supported_either_seat": share("hero_power_not_proven_supported_either_seat"),
            "not_proven_supported_self": share("hero_power_not_proven_supported_self"),
            "identity_missing_either_seat": share("hero_power_identity_missing"),
            "status_by_seat": {seat: dict(sorted(counter.items())) for seat, counter in hero_power_status.items()},
            "identities_by_seat": {seat: dict(sorted(counter.items())) for seat, counter in hero_power_ids.items()},
        },
        "ready_for_import_design": {
            "native_hydration_possible_today": {"positions": 0, "percent": 0.0},
            "valid_design_input_structurally_valid_and_consistent": {"positions": len(design_input), "percent": _pct(len(design_input), total)},
            "no_non_hidden_blocker": share("no_non_hidden_blocker"),
            "source_complete_visible_fields": share("source_complete_visible_fields"),
        },
        "next_action_assessment": {
            "chosen_action_directly_blocked": share("chosen_action_directly_blocked"),
            "chosen_action_blocked_by_action_specific_blocker": share("chosen_action_blocked_by_action_specific_blocker"),
            "chosen_action_blocked_only_by_whole_position_blockers": share("chosen_action_blocked_only_by_whole_position_blockers"),
            "chosen_action_undetermined_only": share("chosen_action_undetermined"),
            "chosen_action_no_direct_blocker_but_hydration_still_blocked": share("chosen_action_no_direct_blocker"),
        },
        "gate_funnel": funnel,
        "cumulative_resolution_effect": cumulative,
        "categories": {
            name: {"distinct_positions": len(by_category_positions[name]), "distinct_games": len(by_category_games[name]),
                   "percent_positions": _pct(len(by_category_positions[name]), total)}
            for name in sorted(by_category_positions)},
        "families": {name: len(members) for name, members in sorted(by_family.items())},
        "limitation_axis_positions": {
            name: {"positions": len(members), "percent": _pct(len(members), total)} for name, members in sorted(by_axis.items())},
        "resolution_demand": {
            name: {"positions": len(by_resolution[name]), "percent": _pct(len(by_resolution[name]), total), "distinct_blocker_codes": len(resolution_codes[name])}
            for name in sorted(by_resolution)},
        "top10_blockers_by_distinct_positions": [_brief(row) for row in ranking[:10]],
        "top10_blockers_by_distinct_games": [_brief(row) for row in by_games[:10]],
        "top10_blockers_below_universal_by_distinct_positions": [_brief(row) for row in ranking if row["percent_positions"] < UNIVERSAL_PERCENT][:10],
        "universal_blocker_count": sum(1 for row in ranking if row["percent_positions"] >= UNIVERSAL_PERCENT),
        "unsupported_cards": {"listed_min_games": MIN_GAMES_FOR_CARD_LISTING, "listed": card_rows[:40], "unlisted_distinct_card_ids": unlisted},
        "ranking": ranking,
    }


def _brief(row: dict) -> dict:
    return {key: row[key] for key in ("code", "category", "distinct_positions", "distinct_games", "percent_positions", "recommended_resolution")}


def describe_sample(sample: list[CorpusPosition]) -> dict:
    """Composition of a sample along the sampling strata (counts only)."""
    strata = [_strata(p) for p in sample]
    summary = {key: dict(sorted(Counter(row[key] for row in strata).items())) for key in ("opponent_class", "self_hero_power", "turn_bucket", "board_bucket", "chosen_action")}
    turns = [int(p.state["turn_number"]) if isinstance(p.state.get("turn_number"), int) else 0 for p in sample]
    summary.update({"positions": len(sample), "distinct_games": len({p.game_id for p in sample}),
                    "max_positions_from_one_game": max(Counter(p.game_id for p in sample).values()) if sample else 0,
                    "turn_range": [min(turns), max(turns)] if turns else None})
    return summary


def dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


__all__ = ["ANALYZER_VERSION", "RESOLUTIONS", "SOURCE_KINDS", "AnalyzedPosition", "CorpusPosition", "aggregate", "analyze_corpus", "describe_sample",
           "dumps", "read_live_positions", "read_policy_positions", "read_value_positions", "select_sample"]
