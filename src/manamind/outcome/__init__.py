"""ACTION-OUTCOME-1: structured forecasts of the immediate consequences of legal actions."""

from manamind.outcome.compare import Summary, compare, render_comparison, summarise
from manamind.outcome.forecast import describe_action, forecast_action, forecast_alternatives
from manamind.outcome.model import Change, Event, Forecast, Ref, Status, Unknown, UnknownKind
from manamind.outcome.texts import CardText, TextSource
from manamind.outcome.world import ObservedContext

__all__ = [
    "CardText", "Change", "Event", "Forecast", "ObservedContext", "Ref", "Status", "Summary", "TextSource",
    "Unknown", "UnknownKind", "compare", "describe_action", "forecast_action", "forecast_alternatives",
    "render_comparison", "summarise",
]
