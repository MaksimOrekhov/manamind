"""Check whether a single local Hearthstone log contains a finished Ranked Standard game.

This is an intake check only. It does not export or create training examples.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

from hearthstone.enums import CardType, FormatType, GameTag, GameType, PlayState, State
from hslog import LogParser

from manamind.integrations.powerlog.exporter import CompatibleEntityTreeExporter  # noqa: F401


def audit_log(path: Path) -> dict[str, Any]:
    """Read a local log and return a privacy-safe eligibility summary."""
    parser = LogParser()
    with path.open("r", encoding="utf-8", errors="replace") as log_file:
        parser.read(log_file)

    if len(parser.games) != 1:
        return {
            "eligible_for_capture": False,
            "reason": "expected exactly one game in the log",
            "games_found": len(parser.games),
        }

    game = CompatibleEntityTreeExporter(parser.games[0]).export().game
    if game is None:
        return {
            "eligible_for_capture": False,
            "reason": "could not reconstruct game state",
        }

    metadata = parser.game_meta
    game_type = _enum_value(GameType, metadata.get("GameType"))
    format_type = _enum_value(FormatType, metadata.get("FormatType"))
    is_ranked = game_type == GameType.GT_RANKED
    is_standard = format_type == FormatType.FT_STANDARD
    is_complete = game.tags.get(GameTag.STATE) == State.COMPLETE

    players = [entity for entity in game.entities if entity.type == CardType.PLAYER]
    outcomes: list[str] = []
    for player in players:
        play_state = player.tags.get(GameTag.PLAYSTATE)
        if play_state == PlayState.WON:
            outcomes.append("WIN")
        elif play_state == PlayState.LOST:
            outcomes.append("LOSS")
        elif play_state == PlayState.TIED:
            outcomes.append("DRAW")
        else:
            outcomes.append("UNKNOWN")

    reasons = []
    if not is_ranked:
        reasons.append("not identified as Ranked")
    if not is_standard:
        reasons.append("not identified as Standard")
    if not is_complete or "UNKNOWN" in outcomes or len(outcomes) != 2:
        reasons.append("game result is incomplete")

    return {
        "eligible_for_capture": not reasons,
        "game_type": _enum_name(GameType, metadata.get("GameType")),
        "format": _enum_name(FormatType, metadata.get("FormatType")),
        "complete": is_complete,
        "outcomes": outcomes,
        "turns": game.tags.get(GameTag.TURN),
        "reason": "; ".join(reasons) if reasons else "ready for snapshot conversion",
    }


def _enum_value(enum_class, value):
    if value is None:
        return None
    if isinstance(value, enum_class):
        return value
    try:
        return enum_class(value)
    except (ValueError, TypeError):
        return None


def _enum_name(enum_class, value):
    parsed = _enum_value(enum_class, value)
    return parsed.name if parsed is not None else None


def main() -> int:
    argument_parser = argparse.ArgumentParser(
        description="Privacy-safe audit for one local Hearthstone Power.log match."
    )
    argument_parser.add_argument("log_file", type=Path, help="Path to a copied Power.log")
    args = argument_parser.parse_args()

    if not args.log_file.is_file():
        argument_parser.error(f"file does not exist: {args.log_file}")

    # Parser warnings can include raw game text or card/player identifiers.
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    try:
        result = audit_log(args.log_file)
    except Exception as error:  # Parser failures should not dump log contents.
        result = {
            "eligible_for_capture": False,
            "reason": f"could not parse log ({type(error).__name__})",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["eligible_for_capture"] else 1


if __name__ == "__main__":
    sys.exit(main())
