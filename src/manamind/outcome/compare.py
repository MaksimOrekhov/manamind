"""Side-by-side comparison of alternative forecasts from one state.

The summary is objective bookkeeping of what the exact changes do to each side. It never says an
action is good or bad: whether helping an opponent minion is a mistake depends on the rest of the
position, which this layer does not judge.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from manamind.domain.game_state import GameState, PlayerObservation
from manamind.outcome.model import Change, Forecast, Status

_KEYWORD_FLAGS = ("taunt", "divine_shield", "lifesteal", "rush", "charge", "windfury", "stealth",
                  "poisonous", "reborn")
_IMPROVING_FIELDS = {"attack", "health", "max_health", "armor"}
_FLAG_FIELDS = set(_KEYWORD_FLAGS)


def side_metrics(player: PlayerObservation) -> dict[str, int]:
    return {
        "minions": len(player.board),
        "board_attack": sum(e.current_attack for e in player.board),
        "board_health": sum(e.current_health for e in player.board),
        "keywords": sum(bool(getattr(e, flag)) for e in player.board for flag in _KEYWORD_FLAGS),
        "locations": len(player.locations),
        "hero_health": player.hero_health,
        "armor": player.armor,
        "hand_size": player.hand_size,
        "mana": player.available_mana,
    }


def metric_deltas(before: GameState, after: GameState) -> dict[str, dict[str, int]]:
    result = {}
    for side, old, new in (("SELF", before.self_player, after.self_player),
                           ("OPPONENT", before.opponent, after.opponent)):
        old_m, new_m = side_metrics(old), side_metrics(new)
        result[side] = {name: new_m[name] - old_m[name] for name in old_m}
    return result


def _direction(change: Change) -> int:
    """+1 raises the owner's resources, -1 lowers them, 0 neutral/unknown."""
    if not change.exact:
        return 0
    if change.field == "present":
        return 1 if change.after else -1
    if change.field in _FLAG_FIELDS:
        return 1 if change.after and not change.before else (-1 if change.before and not change.after else 0)
    if change.field in _IMPROVING_FIELDS and change.delta:
        return 1 if change.delta > 0 else -1
    return 0


@dataclass(frozen=True, slots=True)
class Summary:
    label: str
    status: Status
    deltas: dict[str, dict[str, int]]
    improves: dict[str, list[str]] = field(default_factory=dict)
    harms: dict[str, list[str]] = field(default_factory=dict)
    note: str = ""


def summarise(state: GameState, forecast: Forecast) -> Summary:
    if forecast.after_state is None:
        return Summary(forecast.label, forecast.status, {}, note=f"unsupported: {forecast.unsupported_reason}")
    improves: dict[str, list[str]] = {"SELF": [], "OPPONENT": []}
    harms: dict[str, list[str]] = {"SELF": [], "OPPONENT": []}
    for change in forecast.exact_changes:
        if change.ref.zone not in ("BOARD", "HERO", "LOCATION") or change.field in ("body", "can_attack"):
            continue
        direction = _direction(change)
        if change.ref.zone == "BOARD" and change.field == "present" and change.after:
            continue                                 # a played minion is the actor's own card, not a gift
        if direction > 0:
            improves[change.ref.side].append(change.describe())
        elif direction < 0:
            harms[change.ref.side].append(change.describe())
    deltas = metric_deltas(state, forecast.after_state)
    note = ""
    if improves["OPPONENT"] and not improves["SELF"] and not harms["OPPONENT"]:
        note = ("direct effects only improve OPPONENT-controlled entities; SELF's direct change is the cost "
                "paid (strategic value, e.g. combos, is not assessed)")
    elif harms["SELF"] and not improves["SELF"] and not harms["OPPONENT"] and not improves["OPPONENT"]:
        note = "direct effects only reduce SELF resources"
    return Summary(forecast.label, forecast.status, deltas, improves, harms, note)


def compare(state: GameState, forecasts: Sequence[Forecast]) -> list[Summary]:
    return [summarise(state, forecast) for forecast in forecasts]


def render_comparison(state: GameState, forecasts: Sequence[Forecast], *, detail: bool = True,
                      events: bool = False) -> str:
    lines = []
    for index, forecast in enumerate(forecasts, start=1):
        summary = summarise(state, forecast)
        lines.append(f"[{index}] {forecast.label}  ->  {forecast.status.value}")
        if forecast.status is Status.UNSUPPORTED:
            lines.append(f"      unsupported: {forecast.unsupported_reason}")
            continue
        for change in forecast.changes:
            if change.ref.zone == "PLAYER" and change.field == "hand_size":
                continue
            lines.append(f"      {change.describe()}")
        for side in ("SELF", "OPPONENT"):
            moved = {k: v for k, v in summary.deltas[side].items() if v and k not in ("hand_size",)}
            if moved:
                lines.append(f"      net {side}: " + ", ".join(f"{k} {v:+d}" for k, v in moved.items()))
        if events:
            lines += [f"      . {event.note}" for event in forecast.events if event.kind != "MANA_SPENT"]
        if summary.note:
            lines.append(f"      note: {summary.note}")
        if detail:
            for unknown in forecast.unknowns:
                lines.append(f"      ? {unknown.kind.value}: {unknown.detail}")
            for assumption in forecast.assumptions:
                lines.append(f"      assumption: {assumption}")
    return "\n".join(lines)
