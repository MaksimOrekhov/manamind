"""Follow Hearthstone's Power.log and print one sanitized snapshot per SELF decision point.

Read-only on the Logs folder. No recommendations, no model, no network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.live.recorder import Recorder
from manamind.live.render import render
from manamind.live.runner import LiveRunner
from manamind.live.session import LiveSession
from manamind.live.snapshot import Snapshot
from manamind.live.trust import DEVELOPER_GAME_TYPES, ModePolicy, StatusEvent

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    env_root = os.environ.get("MANAMIND_HEARTHSTONE_LOGS")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--logs-root", type=Path, default=Path(env_root) if env_root else None,
                        help="Hearthstone Logs folder (or set MANAMIND_HEARTHSTONE_LOGS)")
    parser.add_argument("--poll-ms", type=int, default=50)
    parser.add_argument("--json", action="store_true", help="print one JSON object per line")
    parser.add_argument("--allow-mode", action="append", default=[], choices=sorted(DEVELOPER_GAME_TYPES),
                        help="developer option: also follow this game type (default: Ranked Standard only)")
    parser.add_argument("--record", nargs="?", const=Path("data/raw/live"), default=None, type=Path,
                        help="record slice/trace/snapshots under this folder (default data/raw/live)")
    parser.add_argument("--cards", type=Path, default=ROOT / "data" / "cards" / "standard_current_enUS.json")
    return parser


def emit(event, as_json: bool) -> None:
    if isinstance(event, Snapshot):
        print(event.to_json() if as_json else render(event), flush=True)
    elif isinstance(event, StatusEvent):
        if as_json:
            print(json.dumps(event.to_dict(), sort_keys=True), flush=True)
        else:
            reason = f" ({event.reason})" if event.reason else ""
            print(f"status: {event.status.value}{reason}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.logs_root is None:
        parser.error("--logs-root is required (or set MANAMIND_HEARTHSTONE_LOGS)")
    if args.poll_ms < 10:
        parser.error("--poll-ms must be at least 10")

    policy = ModePolicy(frozenset(args.allow_mode))
    session = LiveSession(CardCatalog.from_json(args.cards), policy)
    recorder = Recorder(args.record, catalog_path=args.cards, mode_policy=policy) if args.record else None
    runner = LiveRunner(args.logs_root, session, recorder)
    if not args.json:
        print("ManaMind live state (read-only). Ctrl+C to stop.", flush=True)
    emit(StatusEvent(session.status, session.reason), args.json)
    try:
        while True:
            for event in runner.step():
                emit(event, args.json)
            time.sleep(args.poll_ms / 1000)
    except KeyboardInterrupt:
        return 0
    except Exception as error:  # privacy: class name only, never the message
        print(f"live state stopped: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
