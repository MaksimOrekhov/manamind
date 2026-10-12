"""Strategic Scorer (STRATEGIC-SCORER-1): an experimental, Policy-independent ranking of a legal menu.

A one-step look-ahead over the reviewed immediate-outcome forecaster with a hand-written position value. It is a
research candidate: no claim of playing strength is attached to it. ``manamind.live`` and the apps must not import
this package (a test enforces it); only the launcher script wires the optional ``--strategy-shadow`` journal.
"""

from manamind.strategy.scorer import SCORER_VERSION, ActionScore, MenuScore, Uncertainty, score_menu
from manamind.strategy.value import PARAMS, PARAMS_VERSION, Params, position_value

__all__ = ["PARAMS", "PARAMS_VERSION", "SCORER_VERSION", "ActionScore", "MenuScore", "Params", "Uncertainty",
           "position_value", "score_menu"]
