"""ACTION-OUTCOME-1: structured forecasts of the immediate consequences of legal actions.

Reading a forecast safely: ``forecast.exact_state()`` is the only way to get a full predicted position and
it raises ``NotExactError`` unless the status is ``EXACT``. Everything else is a ledger: ``changes`` (exact
ones, bounded ones, with their role), ``unknowns`` and ``tier``. A ``PARTIAL`` forecast offers
``partial_state()``, which is not a ``GameState`` and cannot be passed to the encoder or a value model.
"""

from manamind.outcome.compare import Summary, compare, render_comparison, summarise
from manamind.outcome.forecast import describe_action, forecast_action, forecast_alternatives
from manamind.outcome.model import (
    Change, Event, Forecast, NotExactError, PartialState, Ref, Status, Tier, Unknown, UnknownKind,
)
from manamind.outcome.texts import CardText, TextSource
from manamind.outcome.world import ObservedContext

__all__ = [
    "CardText", "Change", "Event", "Forecast", "NotExactError", "ObservedContext", "PartialState", "Ref", "Status",
    "Summary", "TextSource", "Tier", "Unknown", "UnknownKind", "compare", "describe_action", "forecast_action",
    "forecast_alternatives", "render_comparison", "summarise",
]
