"""Convert one finished Ranked Standard Power.log into local training examples.

The converter records the local player's view immediately before each top-level
PLAY or ATTACK action. It never writes player names or raw replay data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import uuid
import warnings
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hearthstone.enums import (
    BlockType,
    FormatType,
    GameTag,
    GameType,
    PlayState,
    State,
)
from hslog import LogParser
from hslog.packets import Block

from manamind.cards.catalog import CardCatalog
from manamind.integrations.powerlog.exporter import CompatibleEntityTreeExporter
from manamind.integrations.powerlog import visible_state as _visible
from manamind.training.synthetic import LabeledState


# Names kept importable from this script (tests and tools use them).
_infer_local_player_id = _visible.infer_local_player_id
_find_player = _visible.find_player
_to_visible_state = _visible.to_visible_state
_player_observation = _visible._player_observation
_board_entity = _visible._board_entity
_location_entity = _visible._location_entity
_card_features = _visible._card_features
_visible_hand_cards = _visible._visible_hand_cards
_mana_values = _visible._mana_values
_current_health = _visible._current_health
_current_weapon_durability = _visible._current_weapon_durability
_integer = _visible._integer
_optional_int = _visible._optional_int
_enum_tag_name = _visible._enum_tag_name

ACTION_BLOCKS = {BlockType.PLAY, BlockType.ATTACK}


def import_power_log(
    log_path: str | Path,
    output_path: str | Path,
    catalog_path: str | Path,
) -> dict[str, Any]:
    """Convert an eligible one-game log and return a privacy-safe summary."""
    log_path = Path(log_path)
    output_path = Path(output_path)
    parser = LogParser()
    with log_path.open("r", encoding="utf-8", errors="replace") as file:
        parser.read(file)

    if len(parser.games) != 1:
        raise ValueError("expected a log containing exactly one match")
    if parser.game_meta.get("GameType") != GameType.GT_RANKED:
        raise ValueError("log is not identified as Ranked")
    if parser.game_meta.get("FormatType") != FormatType.FT_STANDARD:
        raise ValueError("log is not identified as Standard")

    catalog = CardCatalog.from_json(catalog_path)
    exporter = CompatibleEntityTreeExporter(parser.games[0])
    game_id = uuid.uuid4().hex
    examples: list[LabeledState] = []
    self_player_id: int | None = None
    previous_state: str | None = None

    for packet in parser.games[0].packets:
        if isinstance(packet, Block) and packet.type in ACTION_BLOCKS and exporter.game:
            if self_player_id is None:
                self_player_id = _infer_local_player_id(exporter.game)
            state = _to_visible_state(exporter.game, self_player_id, catalog)
            if state is not None:
                signature = json.dumps(asdict(state), sort_keys=True, separators=(",", ":"))
                if signature != previous_state:
                    examples.append(LabeledState(
                        state=state,
                        target=0.0,  # Replaced with the final result below.
                        game_id=game_id,
                        sample_id=f"{game_id}-{len(examples):05d}",
                        perspective="SELF",
                        source="power_log_ranked_standard",
                    ))
                    previous_state = signature
        exporter.export_packet(packet)

    exporter.flush()
    game = exporter.game
    if game is None or game.tags.get(GameTag.STATE) != State.COMPLETE:
        raise ValueError("game result is incomplete")
    if self_player_id is None:
        raise ValueError("could not identify the local player perspective")

    local_player = _find_player(game, self_player_id)
    if local_player is None:
        raise ValueError("could not find the local player in the finished game")
    result = local_player.tags.get(GameTag.PLAYSTATE)
    target_by_result = {
        PlayState.WON: 1.0,
        PlayState.LOST: 0.0,
        PlayState.TIED: 0.5,
    }
    if result not in target_by_result:
        raise ValueError("game has no final win/loss/draw label")
    if not examples:
        raise ValueError("no decision-point snapshots were found")

    target = target_by_result[result]
    examples = [
        LabeledState(
            state=example.state,
            target=target,
            game_id=example.game_id,
            sample_id=example.sample_id,
            perspective=example.perspective,
            source=example.source,
        )
        for example in examples
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_path}")
    fingerprint = _examples_fingerprint(examples)
    for existing_path in output_path.parent.glob("*.jsonl"):
        if _file_fingerprint(existing_path) == fingerprint:
            return {
                "examples_written": 0,
                "duplicate": True,
                "duplicate_of": existing_path.name,
                "reason": "this match was already imported",
            }
    _save_labeled_examples(output_path, examples)

    return {
        "examples_written": len(examples),
        "perspective": "SELF",
        "target": target,
        "result": result.name,
        "turns": game.tags.get(GameTag.TURN),
        "output": str(output_path),
    }


def _save_labeled_examples(path: Path, examples: list[LabeledState]) -> None:
    """Write the project's existing JSONL schema without leaking log metadata."""
    with path.open("x", encoding="utf-8") as file:
        for example in examples:
            row = {
                "schema_version": 1,
                "game_id": example.game_id,
                "sample_id": example.sample_id,
                "perspective": example.perspective,
                "source": example.source,
                "state": asdict(example.state),
                "target": example.target,
            }
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _examples_fingerprint(examples: list[LabeledState]) -> str:
    rows = [
        {
            "state": asdict(example.state),
            "target": example.target,
            "perspective": example.perspective,
        }
        for example in examples
    ]
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_fingerprint(path: Path) -> str | None:
    try:
        rows = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                example = json.loads(line)
                rows.append({
                    "state": example["state"],
                    "target": example["target"],
                    "perspective": example.get("perspective", "SELF"),
                })
        payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def main() -> int:
    argument_parser = argparse.ArgumentParser(
        description="Convert one finished Ranked Standard Power.log to local JSONL examples."
    )
    argument_parser.add_argument("log_file", type=Path)
    argument_parser.add_argument(
        "--output", type=Path,
        help="Output JSONL path (defaults to data/processed_real/<random-id>.jsonl)",
    )
    argument_parser.add_argument(
        "--cards", type=Path,
        default=Path("data/cards/standard_current_enUS.json"),
    )
    args = argument_parser.parse_args()

    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    output_path = args.output or (
        Path("data/processed_real") / f"{uuid.uuid4().hex}.jsonl"
    )
    try:
        result = import_power_log(args.log_file, output_path, args.cards)
    except Exception as error:
        print(json.dumps({
            "examples_written": 0,
            "reason": f"import failed ({type(error).__name__})",
        }, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
