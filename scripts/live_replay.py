"""Replay a recorded live game and verify that the state_hash sequence is reproduced."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.live.render import render
from manamind.live.replay import replay_game, verify_replay

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("directory", type=Path, help="data/raw/live/<session>/<game_key16>")
    parser.add_argument("--cards", type=Path, default=ROOT / "data" / "cards" / "standard_current_enUS.json")
    parser.add_argument("--show", action="store_true", help="print the replayed snapshots")
    args = parser.parse_args(argv)

    catalog = CardCatalog.from_json(args.cards)
    try:
        if args.show:
            for snapshot in replay_game(args.directory, catalog):
                print(render(snapshot))
        identical, recorded, replayed = verify_replay(args.directory, catalog)
    except Exception as error:  # privacy: class name only
        print(f"replay failed: {type(error).__name__}", file=sys.stderr)
        return 2
    print(f"recorded {len(recorded)} snapshots, replayed {len(replayed)}: "
          f"{'IDENTICAL' if identical else 'MISMATCH'}")
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
