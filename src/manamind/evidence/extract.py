"""One completed game section -> observations, with every skip reason a stable code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version

from hearthstone.enums import BlockType
from hslog.packets import Block, Options

from manamind.integrations.powerlog.lines import inspect_segment
from manamind.integrations.powerlog.visible_state import infer_local_player_id
from manamind.live.reducer import GameReducer, PacketExporter, ReducerError, preorder, quiet_parser
from manamind.live.visibility import option_controllers

from . import EXTRACTOR_VERSION
from .entities import Redactor
from .observation import GameContext, build_observations
from .sanitize import safe_code
from .walker import Walker

BUILD_RE = re.compile(r"GameState\.DebugPrintGame\(\) - BuildNumber=(\d+)\s*$")
FIRST_ACTIONS = frozenset({BlockType.PLAY, BlockType.ATTACK})


def _version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


VERSIONS = {"hslog": _version("hslog"), "hearthstone": _version("hearthstone")}


@dataclass
class GameResult:
    summary: dict
    observations: list[dict] = field(default_factory=list)


def resolve_self(tree) -> tuple[int | None, str | None]:
    """SELF by the project's hand-identity rule, cross-checked with the server's own options.

    Disagreement or a missing cross-check means the game is skipped: a wrong SELF would invert
    every visibility decision.
    """
    exporter = PacketExporter(tree)  # the options message may come after the opponent's first play
    rule_a: int | None = None
    rule_b: int | None = None
    seen_action = False
    for packet in tree.packets:
        if rule_a is None and not seen_action and isinstance(packet, Block) and packet.type in FIRST_ACTIONS:
            seen_action = True
            try:
                rule_a = infer_local_player_id(exporter.game)
            except ValueError:
                rule_a = None
        if rule_b is not None and seen_action:
            break
        with quiet_parser():
            for item in preorder([packet]):
                exporter.export_packet(item)
        if isinstance(packet, Options) and rule_b is None:
            try:
                controllers = option_controllers(exporter.game, packet)
            except ReducerError:
                controllers = set()
            if len(controllers) == 1:
                rule_b = next(iter(controllers))
    if rule_a is None or rule_b is None:
        return None, "SELF_UNVERIFIED"
    if rule_a != rule_b:
        return None, "SELF_DISAGREE"
    return rule_a, None


def _skip(summary: dict, reason: str) -> GameResult:
    summary.update(status="SKIPPED", reason=reason)
    return GameResult(summary)


def extract_game(lines: list[str], *, source_kind: str, inventory, scope, catalog, catalog_sha256: str,
                 include_secondary: bool, control_counts: dict[str, int], max_control_samples: int,
                 extractor_version: str = EXTRACTOR_VERSION) -> GameResult:
    info = inspect_segment(lines)
    summary: dict = {
        "game_key16": info.start_key[:16] if info.start_key else None, "status": None, "reason": None,
        "game_type": None, "format_type": None, "client_build": None, "windows": 0, "observations": 0,
    }
    try:
        if info.start_key is None:
            return _skip(summary, "NO_GAME_KEY")
        if len(info.game_types) != 1 or len(info.formats) != 1:
            return _skip(summary, "MODE_AMBIGUOUS")
        game_type, format_type = next(iter(info.game_types)), next(iter(info.formats))
        summary.update(game_type=safe_code(game_type), format_type=safe_code(format_type))
        primary = game_type == "GT_RANKED" and format_type == "FT_STANDARD"
        if not primary and not include_secondary:
            return _skip(summary, "UNSUPPORTED_MODE")
        if info.mid_game_start:
            return _skip(summary, "MID_GAME_START")
        if info.complete_index is None:
            return _skip(summary, "INCOMPLETE")
        section = lines[:info.complete_index + 1]
        if any("BLOCK_START BlockType=GAME_RESET" in line for line in section):
            return _skip(summary, "GAME_RESET")
        for line in section:
            build = BUILD_RE.search(line)
            if build:
                summary["client_build"] = int(build.group(1))
                break
        reducer = GameReducer()
        for line in section:
            reducer.read_line(line)
        tree = reducer.tree
        if tree is None:
            return _skip(summary, "PARSE_ERROR")
        self_id, reason = resolve_self(tree)
        if self_id is None:
            return _skip(summary, reason or "SELF_UNVERIFIED")

        walk = Walker(tree, self_id, catalog).walk()
        ctx = GameContext(
            game_key16=info.start_key[:16], client_build=summary["client_build"], game_type=game_type,
            format_type=format_type, rules_scope="STANDARD_PRIMARY" if primary else "OTHER_MODE_SECONDARY",
            source_kind=source_kind, catalog_sha256=catalog_sha256, extractor_version=extractor_version,
            parser_versions=VERSIONS, redactor=Redactor(self_id, inventory), inventory=inventory, scope=scope,
            max_control_samples=max_control_samples, control_counts=control_counts,
        )
        observations: list[dict] = []
        root_types: dict[str, int] = {}
        for window in walk.windows:
            root_types[window.root_type] = root_types.get(window.root_type, 0) + 1
            observations.extend(build_observations(window, ctx))
        summary.update(
            status="PROCESSED", reason=None, windows=len(walk.windows), observations=len(observations),
            root_blocks_by_type=dict(sorted(root_types.items())), walker_stats=walk.stats,
            parser_unknown_tag_lines=reducer.skipped_unknown_tags, counters=dict(sorted(ctx.counters.items())),
        )
        return GameResult(summary, observations)
    except ReducerError as error:
        return _skip(summary, f"PARSE_{error.reason}")
    except Exception as error:  # noqa: BLE001 - only the class name may leave: messages can carry names
        name = type(error).__name__
        return _skip(summary, f"EXCEPTION_{name if name.isidentifier() else 'UNKNOWN'}")
