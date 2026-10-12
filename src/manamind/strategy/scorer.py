"""Strategic Scorer (STRATEGIC-SCORER-1): rank a legal menu by the position each action leads to.

For every legal action, independently and from the same pre-action position, the reviewed immediate-outcome
forecaster (``manamind.outcome``) computes what the action does. The scorer values the position after it with the
hand-written ``position_value`` and ranks actions by ``V(after) - V(before)``. It is a one-step look-ahead with a
heuristic evaluation; there is no search, no opponent model and no second rules engine.

The score of an action is split into parts that must not be confused:

* ``confirmed``         - value change of what the forecaster computed exactly (board, heroes, hand, weapons);
* ``risk``              - change of a rough look at the visible attackers of both sides for the next turns;
* ``plan``              - change of what SELF can still do this turn (Mana and ready attackers), an estimate;
* ``unknown_estimate``  - for an action whose own text the forecaster cannot read, the value a fair card of that
                          cost would add beyond what was computed. An estimate that unsupported effects are not
                          worthless; it is never presented as a mechanical consequence.

``uncertainty`` says how much the score could move because of what is not known (unread own text, possible
reactions, hidden Secrets, unobserved modifiers). Nothing here reads a Policy score, a human choice or hidden
information; the input is the visible ``GameState``, the full legal menu and card texts.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from manamind.domain.game_state import GameState
from manamind.outcome.forecast import describe_action, forecast_action
from manamind.outcome.model import Change, Forecast, Status
from manamind.outcome.texts import TextSource
from manamind.outcome.world import ObservedContext
from manamind.strategy.value import (
    PARAMS, PARAMS_VERSION, Breakdown, Params, expected_play_value, hand_value, health_value, minion_value,
    position_value,
)

SCORER_VERSION = "strategic-scorer-1"
DEFAULT_BUDGET_MS = 400.0
NOT_COMPUTED = "NOT_COMPUTED"
ERROR = "ERROR"

# Unknown tags that mean the action's *own* effect is not (fully) read: an estimate stands in for it.
OWN_EFFECT_TAGS = frozenset({"OWN_TEXT_UNPARSED", "OWN_TEXT_MISSING", "OWN_TEXT_RANDOM", "OWN_TEXT_KEYWORD",
                             "CONDITION_UNOBSERVED"})
# Other objects that may react: the computed effect may be changed or extended.
REACTION_TAGS = frozenset({"BOARD_TRIGGER", "BOARD_STATIC_TEXT", "BOARD_TEXT_MISSING", "DEATHRATTLE",
                           "AURA_ON_SUMMON", "OWN_SECRET_OR_QUEST"})
SECRET_TAGS = frozenset({"OPPONENT_SECRET"})
# Everything else is an unobserved modifier: the computed number is a bound.


@dataclass(frozen=True, slots=True)
class Uncertainty:
    level: str                      # LOW | MEDIUM | HIGH
    magnitude: float                # rough size of what could still move, in stat points
    tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "magnitude": round(self.magnitude, 3), "tags": list(self.tags)}


@dataclass(frozen=True, slots=True)
class ActionScore:
    index: int
    action: dict[str, Any]
    label: str
    status: str                     # forecast status, or NOT_COMPUTED / ERROR
    score: float
    confirmed: float
    risk: float
    plan: float
    unknown_estimate: float
    uncertainty: Uncertainty
    factors: tuple[tuple[str, float, str], ...]   # (code, value, detail), largest first
    group: str                      # actions with the same group and score are interchangeable for this scorer

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "label": self.label, "status": self.status, "score": round(self.score, 3),
                "confirmed": round(self.confirmed, 3), "risk": round(self.risk, 3), "plan": round(self.plan, 3),
                "unknown_estimate": round(self.unknown_estimate, 3), "uncertainty": self.uncertainty.to_dict(),
                "factors": [[code, round(value, 2), detail] for code, value, detail in self.factors]}


@dataclass(frozen=True, slots=True)
class MenuScore:
    actions: tuple[ActionScore, ...]          # menu order
    ranking: tuple[int, ...]                  # menu indices, best first (ties: lower menu index first)
    groups: tuple[tuple[int, ...], ...]       # ranking collapsed to interchangeable groups, best first
    elapsed_ms: float
    computed: int

    def top(self, count: int = 3) -> list[ActionScore]:
        """The best member (lowest menu index) of each of the first ``count`` groups."""
        by_index = {a.index: a for a in self.actions}
        return [by_index[group[0]] for group in self.groups[:count]]

    def group_of(self, index: int) -> int:
        for position, group in enumerate(self.groups):
            if index in group:
                return position
        raise KeyError(index)


# ----- helpers ----------------------------------------------------------------------------------------------------

def _group_key(action: dict[str, Any]) -> str:
    """Hand slot and insertion slot do not enter the value: copies and placements share a group if they tie."""
    reduced = {k: v for k, v in action.items() if k not in ("hand_index", "play_position")}
    return json.dumps(reduced, sort_keys=True, separators=(",", ":"))


def _tag(unknown) -> str:
    return unknown.tag or unknown.kind.value


def _bound_correction(state: GameState, change: Change, p: Params) -> float:
    """Value of the guaranteed part of a bounded Health / Armor change.

    Damage with an unobserved Spell Damage bonus leaves Health "at most N"; healing with an unobserved doubling
    leaves it "at least N". The PARTIAL lower-bound position keeps the pre-action value in such a field; the bound
    itself is known, so its value is added here and nothing beyond it.
    """
    if change.field not in ("health", "armor"):
        return 0.0
    bound = change.at_most if change.at_most is not None else change.at_least
    if bound is None:
        return 0.0
    ref = change.ref
    player = state.self_player if ref.side == "SELF" else state.opponent
    sign = 1.0 if ref.side == "SELF" else -1.0
    if ref.zone == "HERO":
        before = player.hero_health + player.armor
        after = (max(0, bound) + player.armor) if change.field == "health" else (player.hero_health + max(0, bound))
        return sign * (health_value(after, p) - health_value(before, p))
    if (change.field == "health" and ref.zone == "BOARD" and ref.position is not None
            and 1 <= ref.position <= len(player.board)):
        entity = player.board[ref.position - 1]
        if entity.card.card_id != ref.card_id:
            return 0.0
        moved = replace(entity, current_health=max(0, min(entity.max_health, bound)))
        return sign * (minion_value(moved, p) - minion_value(entity, p))
    return 0.0


def _expected_effect(state: GameState, action: dict[str, Any], texts: TextSource, p: Params) -> float | None:
    """What the action is expected to give if its own text is fair, before any forecast."""
    kind = action.get("type")
    if kind == "PLAY_CARD":
        index = action.get("hand_index")
        if index is not None and 0 <= index < len(state.self_hand):
            return expected_play_value(state.self_hand[index], texts, p)
        return None
    if kind == "HERO_POWER":
        return p.hero_power
    if kind == "ACTIVATE_LOCATION":
        return p.location_activation
    return None


def _fallback_state(state: GameState, action: dict[str, Any]) -> GameState | None:
    """Bookkeeping-only position for an action the forecaster could not handle: cost paid, card gone, nothing else."""
    kind = action.get("type")
    me = state.self_player
    cost = action.get("card_cost")
    if kind == "PLAY_CARD":
        index = action.get("hand_index")
        if index is None or not 0 <= index < len(state.self_hand):
            return None
        card = state.self_hand[index]
        cost = card.effective_cost if cost is None else cost
        if cost is None or cost > me.available_mana:
            return None
        hand = tuple(c for i, c in enumerate(state.self_hand) if i != index)
        player = replace(me, available_mana=me.available_mana - cost, hand_size=max(len(hand), me.hand_size - 1))
        return replace(state, self_player=player, self_hand=hand,
                       self_hand_known_count=max(0, (state.self_hand_known_count or 0) - 1))
    if kind == "HERO_POWER":
        if cost is None or cost > me.available_mana:
            return None
        return replace(state, self_player=replace(me, available_mana=me.available_mana - cost, hero_power_ready=False))
    return None


_TERM_LABELS = {
    "board_self": "SELF_BOARD", "board_opponent": "ENEMY_BOARD", "hero_self": "SELF_HEALTH",
    "hero_opponent": "ENEMY_HEALTH", "weapon_self": "SELF_WEAPON", "weapon_opponent": "ENEMY_WEAPON",
    "hand_self": "SELF_HAND", "hand_opponent": "ENEMY_HAND", "win": "LETHAL", "loss": "SELF_DEATH",
    "threat": "INCOMING_THREAT", "lethal_risk": "LETHAL_RISK", "pressure": "PRESSURE",
    "mana_potential": "MANA_PLAN", "attack_potential": "ATTACK_PLAN",
}


def _factors(before: Breakdown, after: Breakdown, forecast: Forecast | None, residual: float,
             bound: float) -> tuple[tuple[str, float, str], ...]:
    found: list[tuple[str, float, str]] = []
    names = [name for name, _ in after.terms] + [n for n, _ in before.terms if n not in dict(after.terms)]
    for name in dict.fromkeys(names):
        delta = after.get(name) - before.get(name)
        if abs(delta) >= 0.25:
            found.append((_TERM_LABELS[name], delta, ""))
    if forecast is not None:
        for change in forecast.changes:
            if change.field == "present" and change.ref.zone == "BOARD" and change.after is False:
                found.append(("DIES", 0.0, change.ref.label()))
    if residual:
        found.append(("UNREAD_EFFECT_ESTIMATE", residual, "fair-card estimate for text the forecaster cannot read"))
    if bound:
        found.append(("BOUNDED_EFFECT", bound, "guaranteed part of an effect whose size is only bounded"))
    found.sort(key=lambda item: (-abs(item[1]), item[0], item[2]))
    return tuple(found[:8])


# ----- scoring ----------------------------------------------------------------------------------------------------

def score_action(state: GameState, index: int, action: dict[str, Any], forecast: Forecast | None,
                 before: Breakdown, texts: TextSource, *, status_override: str | None = None,
                 p: Params = PARAMS) -> ActionScore:
    """Score one action from its forecast (``None`` when it was not computed or failed)."""
    label = _label(state, action)
    kind = action.get("type")
    turn_open = kind != "END_TURN"
    tags: list[str] = []
    bound = 0.0
    own_unknown = False
    after_state: GameState | None = None
    status = status_override or (forecast.status.value if forecast is not None else ERROR)
    if forecast is not None and forecast.status is Status.EXACT:
        after_state = forecast.exact_state()
    elif forecast is not None and forecast.status is Status.PARTIAL:
        partial = forecast.partial_state()
        after_state = partial.diagnostic_state() if partial is not None else None
        bound = sum(_bound_correction(state, change, p) for change in forecast.bounded_changes)
    if forecast is not None:
        tags = sorted({_tag(u) for u in forecast.unknowns})
        own_unknown = any(tag in OWN_EFFECT_TAGS for tag in tags)
    if after_state is None:
        # Not forecast (UNSUPPORTED / failed / out of budget): only bookkeeping is applied, the effect is estimated.
        after_state = _fallback_state(state, action) if kind != "END_TURN" else state
        own_unknown = after_state is not None and kind in ("PLAY_CARD", "HERO_POWER")
        if after_state is None:
            after_state = state
        tags = sorted(set(tags) | {f"NOT_FORECAST:{status}"})
    after = position_value(after_state, texts, turn_open=turn_open, p=p)
    confirmed = (after.kind("static") + after.kind("terminal")) - (before.kind("static") + before.kind("terminal"))
    confirmed += bound
    risk = after.kind("risk") - before.kind("risk")
    plan = after.kind("potential") - before.kind("potential")
    residual = 0.0
    if own_unknown:
        expected = _expected_effect(state, action, texts, p)
        if expected is not None:
            hand_change = after.get("hand_self") - before.get("hand_self")
            modelled = confirmed - hand_change
            residual = max(0.0, expected - modelled)
    magnitude = residual
    reactions = sum(1 for tag in tags if tag in REACTION_TAGS)
    modifiers = sum(1 for tag in tags if tag not in REACTION_TAGS | SECRET_TAGS | OWN_EFFECT_TAGS
                    and not tag.startswith("NOT_FORECAST"))
    magnitude += 1.0 * reactions + 0.5 * modifiers + (3.0 if any(t in SECRET_TAGS for t in tags) else 0.0)
    if status in (Status.UNSUPPORTED.value, ERROR, NOT_COMPUTED) or residual >= 3.0 or magnitude > 5.0:
        level = "HIGH"
    elif status == Status.EXACT.value or magnitude <= 1.0:
        level = "LOW"
    else:
        level = "MEDIUM"
    score = confirmed + risk + plan + residual
    return ActionScore(
        index=index, action=dict(action), label=label, status=status, score=score, confirmed=confirmed, risk=risk,
        plan=plan, unknown_estimate=residual, uncertainty=Uncertainty(level, magnitude, tuple(tags)),
        factors=_factors(before, after, forecast, residual, bound), group=_group_key(action))


def score_menu(state: GameState, actions: Sequence[dict[str, Any]], texts: TextSource,
               context: ObservedContext | None = None, *, budget_ms: float = DEFAULT_BUDGET_MS,
               clock: Callable[[], int] = time.perf_counter_ns, p: Params = PARAMS) -> MenuScore:
    """Score every legal action of one decision, in menu order, independently from the same position.

    Deterministic in (state, actions, texts, context) except ``elapsed_ms`` and, when the wall-clock budget runs
    out, which actions are left NOT_COMPUTED (they are then scored from bookkeeping only and marked HIGH).
    """
    started = clock()
    context = context or ObservedContext()
    before = position_value(state, texts, turn_open=True, p=p)
    scored: list[ActionScore] = []
    computed = 0
    for index, action in enumerate(actions):
        if (clock() - started) / 1e6 > budget_ms:
            scored.append(score_action(state, index, action, None, before, texts, status_override=NOT_COMPUTED, p=p))
            continue
        try:
            forecast = forecast_action(state, action, texts, context)
        except Exception:                       # one action must not cost the menu; the reason is in the status
            scored.append(score_action(state, index, action, None, before, texts, status_override=ERROR, p=p))
            continue
        computed += 1
        scored.append(score_action(state, index, action, forecast, before, texts, p=p))
    ranking = tuple(a.index for a in sorted(scored, key=lambda a: (-round(a.score, 6), a.index)))
    by_index = {a.index: a for a in scored}
    groups: list[list[int]] = []
    for index in ranking:
        item = by_index[index]
        for group in groups:
            head = by_index[group[0]]
            if head.group == item.group and round(head.score, 6) == round(item.score, 6):
                group.append(index)
                break
        else:
            groups.append([index])
    return MenuScore(actions=tuple(scored), ranking=ranking, groups=tuple(tuple(g) for g in groups),
                     elapsed_ms=round((clock() - started) / 1e6, 3), computed=computed)


def _label(state: GameState, action: dict[str, Any]) -> str:
    try:
        return describe_action(state, action)
    except Exception:
        return str(action.get("type", "?"))


__all__ = [
    "DEFAULT_BUDGET_MS", "PARAMS_VERSION", "SCORER_VERSION", "ActionScore", "MenuScore", "Uncertainty",
    "hand_value", "score_action", "score_menu",
]
