"""Result types of the immediate-outcome forecaster.

A forecast is a typed ledger of changes plus an explicit list of what is not known. It is never
a complete game state: ``Status.EXACT`` means every modelled direct change was computed from
observed values and nothing in the visible state hints at an unmodelled interaction; any open
unknown downgrades the status to ``PARTIAL``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from manamind.domain.game_state import GameState

SIDES = ("SELF", "OPPONENT")


class Status(str, Enum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


class UnknownKind(str, Enum):
    UNPARSED_CLAUSE = "UNPARSED_CLAUSE"          # a text sentence outside the reviewed grammar
    TEXT_UNAVAILABLE = "TEXT_UNAVAILABLE"        # no rules text for a card whose behaviour matters
    MODIFIER_UNOBSERVED = "MODIFIER_UNOBSERVED"  # a value the arithmetic needs is not in the state
    POSSIBLE_REACTION = "POSSIBLE_REACTION"      # a visible trigger / deathrattle / aura may react
    HIDDEN_SECRET = "HIDDEN_SECRET"              # an opponent Secret may trigger
    RANDOM_OUTCOME = "RANDOM_OUTCOME"            # the text contains a random choice
    KEYWORD_UNDEFINED = "KEYWORD_UNDEFINED"      # a keyword whose rules are not reviewed


@dataclass(frozen=True, slots=True)
class Ref:
    """A position in the pre-action state: ``zone`` is HERO, BOARD, LOCATION, HAND or PLAYER."""

    side: str
    zone: str
    position: int | None
    card_id: str

    def label(self) -> str:
        place = {"HERO": "hero", "PLAYER": "player"}.get(self.zone)
        if place:
            return f"{self.side} {place}"
        slot = "" if self.position is None else f"#{self.position}"
        return f"{self.side} {self.zone.lower()}{slot} {self.card_id}"


@dataclass(frozen=True, slots=True)
class Change:
    """One field of one object: ``before`` -> ``after`` (``after`` None = touched, value unknown)."""

    ref: Ref
    field: str
    before: Any
    after: Any
    cause: str
    at_least: int | None = None
    at_most: int | None = None

    @property
    def exact(self) -> bool:
        return self.after is not None

    @property
    def delta(self) -> int | None:
        if isinstance(self.before, bool) or isinstance(self.after, bool):
            return None
        if isinstance(self.before, int) and isinstance(self.after, int):
            return self.after - self.before
        return None

    def describe(self) -> str:
        if self.field == "present":
            verb = ("enters play" if self.after else
                    "leaves the hand" if self.ref.zone == "HAND" else "leaves play")
            return f"{self.ref.label()} {verb} ({self.cause})"
        if not self.exact:
            bound = (f" (at least {self.at_least})" if self.at_least is not None else
                     f" (at most {self.at_most})" if self.at_most is not None else "")
            return f"{self.ref.label()}.{self.field}: {self.before} -> unknown{bound} ({self.cause})"
        step = "" if self.delta is None else f" ({self.delta:+d})"
        return f"{self.ref.label()}.{self.field}: {self.before} -> {self.after}{step} ({self.cause})"


@dataclass(frozen=True, slots=True)
class Event:
    """An ordered resolution step, kept so that sequencing effects stay explainable."""

    kind: str
    subject: Ref | None
    amount: int | None
    note: str


@dataclass(frozen=True, slots=True)
class Unknown:
    """Something the forecaster cannot determine, and whether it can touch computed values."""

    kind: UnknownKind
    detail: str
    subject: Ref | None = None
    alters_listed: bool = True
    adds_unlisted: bool = True
    tag: str = ""                 # stable blocker class, used to count what keeps forecasts from being EXACT


@dataclass(frozen=True, slots=True)
class Forecast:
    action: dict[str, Any]
    label: str
    status: Status
    changes: tuple[Change, ...] = ()
    events: tuple[Event, ...] = ()
    unknowns: tuple[Unknown, ...] = ()
    assumptions: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    unsupported_reason: str | None = None
    # Exact changes applied to a copy of the pre-action state. Meaningful as a position only when
    # ``status`` is EXACT; otherwise a lower bound that ignores every listed unknown.
    after_state: GameState | None = field(default=None, compare=False, repr=False)

    @property
    def own_effect_known(self) -> bool:
        """True when the action's own text is fully understood and every modifier it needs is observed.

        Only reactions of other objects (triggers, Secrets, auras, cards without text on the board) are
        then still open, so the listed direct changes are what the action itself does.
        """
        reaction_only = {UnknownKind.POSSIBLE_REACTION, UnknownKind.HIDDEN_SECRET}
        return self.status is not Status.UNSUPPORTED and all(
            u.kind in reaction_only or (u.kind is UnknownKind.TEXT_UNAVAILABLE and u.subject is not None
                                        and u.subject.zone in ("BOARD", "LOCATION"))
            for u in self.unknowns)

    @property
    def exact_changes(self) -> tuple[Change, ...]:
        return tuple(change for change in self.changes if change.exact)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "status": self.status.value,
            "unsupported_reason": self.unsupported_reason,
            "changes": [
                {"target": c.ref.label(), "field": c.field, "before": c.before, "after": c.after,
                 "delta": c.delta, "at_least": c.at_least, "at_most": c.at_most, "cause": c.cause}
                for c in self.changes
            ],
            "events": [{"kind": e.kind, "subject": e.subject.label() if e.subject else None,
                        "amount": e.amount, "note": e.note} for e in self.events],
            "unknowns": [
                {"kind": u.kind.value, "detail": u.detail,
                 "subject": u.subject.label() if u.subject else None,
                 "alters_listed": u.alters_listed, "adds_unlisted": u.adds_unlisted, "tag": u.tag}
                for u in self.unknowns
            ],
            "assumptions": list(self.assumptions),
            "rules": list(self.rules),
        }
