"""Check forecasts against what the next observation of a logged game actually shows.

For two consecutive labeled decisions of one SELF turn, the state of the second is the
observation after the action chosen at the first. The forecast is computed from the first state
and its action alone; the second state is read only afterwards, to score the forecast.

Scoring is path based over the fields the forecaster models. A path is *confirmed* when the
forecast moved it and the observation agrees, *contradicted* when the forecast moved it and the
observation disagrees, and *missed* when the observation moved a path the forecast left alone.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from manamind.domain.game_state import GameState
from manamind.domain.serialization import game_state_from_dict
from manamind.outcome.forecast import forecast_action
from manamind.outcome.model import Forecast, Status
from manamind.outcome.texts import TextSource
from manamind.outcome.world import ObservedContext

_ENTITY_FIELDS = ("card_id", "current_attack", "current_health", "max_health", "taunt", "divine_shield",
                  "stealth", "frozen", "immune", "rush", "charge", "windfury", "lifesteal", "poisonous",
                  "reborn", "dormant", "can_attack")


@dataclass(frozen=True, slots=True)
class LoggedDecision:
    game_id: str
    number: int
    decision_id: str
    state: GameState
    action: dict[str, Any]
    legal_actions: tuple[dict[str, Any], ...]


def load_corpus(directory: str | Path) -> dict[str, list[LoggedDecision]]:
    """Read canonical policy JSONL files; decisions of a game are ordered by their decision number."""
    games: dict[str, list[LoggedDecision]] = defaultdict(list)
    for path in sorted(Path(directory).glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            games[row["game_id"]].append(LoggedDecision(
                game_id=row["game_id"], number=int(row["decision_id"].rsplit(":", 1)[1]),
                decision_id=row["decision_id"], state=game_state_from_dict(row["state"]),
                action=row["legal_actions"][row["chosen_action_index"]],
                legal_actions=tuple(row["legal_actions"])))
    return {game: sorted(items, key=lambda item: item.number) for game, items in games.items()}


def successor_pairs(games: dict[str, list[LoggedDecision]]) -> Iterable[tuple[LoggedDecision, LoggedDecision]]:
    """Adjacent labeled decisions of one SELF turn; nothing unlabeled lies between them."""
    for items in games.values():
        for current, following in zip(items, items[1:]):
            same_turn = (current.state.turn_number == following.state.turn_number
                         and current.state.active_player == following.state.active_player == "SELF")
            if following.number == current.number + 1 and same_turn and current.action["type"] != "END_TURN":
                yield current, following


def observe(state: GameState) -> dict[str, Any]:
    """Scalar facts plus the two ordered entity lists, in a form that can be compared field by field."""
    out: dict[str, Any] = {}
    for side, player in (("SELF", state.self_player), ("OPPONENT", state.opponent)):
        out[f"{side}.hero.health"] = player.hero_health
        out[f"{side}.hero.armor"] = player.armor
        out[f"{side}.hero.attack"] = player.hero_attack
        out[f"{side}.hero.power_ready"] = player.hero_power_ready
        out[f"{side}.hero.divine_shield"] = player.hero_divine_shield
        out[f"{side}.mana"] = player.available_mana
        out[f"{side}.hand_size"] = player.hand_size
        out[f"{side}.weapon"] = None if player.weapon is None else (player.weapon.card_id,
                                                                      player.weapon.effective_durability)
        out[f"{side}.board"] = [
            {name: (e.card.card_id if name == "card_id" else getattr(e, name)) for name in _ENTITY_FIELDS}
            for e in player.board]
        out[f"{side}.locations"] = [
            {"card_id": p.card.card_id, "current_health": p.current_health, "on_cooldown": p.on_cooldown}
            for p in player.locations]
    out["SELF.hand"] = [{"card_id": card.card_id} for card in state.self_hand]
    return out


def _align(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[int, int]:
    """Order-preserving match of entities by card ID, so that one death does not shift every later index."""
    matcher = difflib.SequenceMatcher(None, [r["card_id"] for r in before], [r["card_id"] for r in after],
                                      autojunk=False)
    return {block.a + k: block.b + k for block in matcher.get_matching_blocks() for k in range(block.size)}


def _list_claims(name: str, old: list[dict[str, Any]], new: list[dict[str, Any]], seen: list[dict[str, Any]],
                 out: "PairResult", skip: set[str]) -> None:
    to_new, to_seen = _align(old, new), _align(old, seen)
    for index, row in enumerate(old):
        label = f"{name}[{index}:{row['card_id']}]"
        j, k = to_new.get(index), to_seen.get(index)
        if j is None:
            if f"{label}.gone" in skip:
                continue
            if k is None:
                out.confirmed[f"{label}.gone"] = True
            else:
                out.contradicted[f"{label}.gone"] = (True, False)
            continue
        if k is None:
            out.missed[f"{label}.gone"] = (False, True)
            continue
        for field_name, before in row.items():
            path = f"{label}.{field_name}"
            if path in skip:
                continue
            predicted, observed = new[j][field_name], seen[k][field_name]
            if observed is None and before is not None:
                continue                                   # no longer observed: neither right nor wrong
            if predicted != before:
                (out.confirmed.__setitem__(path, predicted) if predicted == observed
                 else out.contradicted.__setitem__(path, (predicted, observed)))
            elif observed != before:
                out.missed[path] = (before, observed)
    fresh_new = [j for j in range(len(new)) if j not in to_new.values()]
    fresh_seen = [k for k in range(len(seen)) if k not in to_seen.values()]
    for j in fresh_new:
        match = next((k for k in fresh_seen if seen[k]["card_id"] == new[j]["card_id"]), None)
        label = f"{name}.new[{new[j]['card_id']}]"
        if match is None:
            out.contradicted[f"{label}.present"] = (True, False)
            continue
        fresh_seen.remove(match)
        for field_name, predicted in new[j].items():
            path = f"{label}.{field_name}"
            (out.confirmed.__setitem__(path, predicted) if predicted == seen[match][field_name]
             else out.contradicted.__setitem__(path, (predicted, seen[match][field_name])))
    for k in fresh_seen:
        out.missed[f"{name}.new[{seen[k]['card_id']}].present"] = (False, True)


def _stale_paths(state: GameState, forecast: Forecast) -> set[str]:
    stale: set[str] = set()
    for change in forecast.changes:
        if change.exact:
            continue
        side = change.ref.side
        if change.ref.zone == "HERO":
            stale.add(f"{side}.hero.{'power_ready' if change.field == 'hero_power_ready' else change.field}")
        elif change.ref.zone == "PLAYER":
            stale.add(f"{side}.mana" if change.field == "available_mana" else f"{side}.{change.field}")
        elif change.ref.zone == "WEAPON":
            stale.add(f"{side}.weapon")
        elif change.ref.zone == "BOARD":
            board = state.self_player.board if side == "SELF" else state.opponent.board
            for index, entity in enumerate(board):
                if entity.board_position == change.ref.position:
                    field_name = {"attack": "current_attack", "health": "current_health"}.get(change.field, change.field)
                    stale.add(f"{side}.board[{index}:{entity.card.card_id}].{field_name}")
    return stale


@dataclass(slots=True)
class PairResult:
    decision_id: str
    action_label: str
    family: str
    status: Status
    confirmed: dict[str, Any] = field(default_factory=dict)
    contradicted: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    missed: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    unknown_kinds: tuple[str, ...] = ()
    unknown_details: tuple[str, ...] = ()
    own_effect_known: bool = False
    alters_listed: bool = False
    unsupported_reason: str | None = None

    @property
    def verdict(self) -> str:
        if self.status is Status.UNSUPPORTED:
            return "UNSUPPORTED"
        if self.contradicted:
            return "CONTRADICTED"
        return "INCOMPLETE" if self.missed else "CONFIRMED"


def family_of(action: dict[str, Any]) -> str:
    kind = action["type"]
    return f"{kind}/{action['card_type']}" if kind == "PLAY_CARD" else kind


def score_pair(current: LoggedDecision, following: LoggedDecision, texts: TextSource,
               context: ObservedContext | None = None) -> PairResult:
    forecast = forecast_action(current.state, current.action, texts, context)
    result = PairResult(current.decision_id, forecast.label, family_of(current.action), forecast.status,
                        unsupported_reason=forecast.unsupported_reason)
    if forecast.after_state is None:
        return result
    before, predicted, actual = observe(current.state), observe(forecast.after_state), observe(following.state)
    stale = _stale_paths(current.state, forecast)
    for path in sorted(before):
        old, new, seen = before[path], predicted[path], actual[path]
        if isinstance(old, list):
            _list_claims(path, old, new, seen, result, stale)
        elif path in stale or (seen is None and old is not None):
            continue
        elif new != old:
            (result.confirmed.__setitem__(path, new) if new == seen
             else result.contradicted.__setitem__(path, (new, seen)))
        elif seen != old:
            result.missed[path] = (old, seen)
    result.unknown_kinds = tuple(sorted({unknown.kind.value for unknown in forecast.unknowns}))
    result.unknown_details = tuple(unknown.detail for unknown in forecast.unknowns)
    result.own_effect_known = forecast.own_effect_known
    result.alters_listed = any(unknown.alters_listed for unknown in forecast.unknowns)
    return result


def summarise_results(results: list[PairResult]) -> dict[str, Any]:
    def counts(items: list[PairResult]) -> dict[str, int]:
        return dict(Counter(item.verdict for item in items))

    by_status = {status.value: [r for r in results if r.status is status] for status in Status}
    by_family: dict[str, dict[str, Any]] = {}
    for family in sorted({r.family for r in results}):
        rows = [r for r in results if r.family == family]
        by_family[family] = {
            "n": len(rows),
            "status": dict(Counter(r.status.value for r in rows)),
            "verdict": counts(rows),
            "confirmed_paths": sum(len(r.confirmed) for r in rows),
            "contradicted_paths": sum(len(r.contradicted) for r in rows),
        }
    unflagged = [r for r in by_status["PARTIAL"] if r.contradicted and not r.alters_listed]
    return {
        "pairs": len(results),
        "status": {name: len(rows) for name, rows in by_status.items()},
        "verdict_by_status": {name: counts(rows) for name, rows in by_status.items()},
        "confirmed_paths": sum(len(r.confirmed) for r in results),
        "contradicted_paths": sum(len(r.contradicted) for r in results),
        "missed_paths": sum(len(r.missed) for r in results),
        "partial_contradicted_without_altering_unknown": len(unflagged),
        "by_family": by_family,
        "unknown_kinds": dict(Counter(kind for r in results for kind in r.unknown_kinds)),
        "unsupported_reasons": dict(Counter(r.unsupported_reason for r in by_status["UNSUPPORTED"])),
    }
