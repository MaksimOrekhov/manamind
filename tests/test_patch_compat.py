"""PATCH-COMPAT-1: Power.log written by a client newer than the installed ``hearthstone`` enums.

The Oct 2026 client prints tag names (``CRAFTABLE_OUTPUT_POWER``, ``THO_DEFEATED_ALLY``) that hslog 1.20.0 + hearthstone
9.21.1 cannot resolve. They arrive as ``tag=NAME value=`` rows, ``TAG_CHANGE`` lines and as the ``TriggerKeyword=`` of a
``BLOCK_START``. All logs here are synthetic; ``BRAND_NEW_*`` names stand for any tag the enums do not know yet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hearthstone.enums import BlockType, GameTag
from hslog import LogParser
from hslog.exceptions import NoSuchEnum, ParsingError
from hslog.packets import Block, SubSpell

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import collect_power_logs as cpl  # noqa: E402
from audit_power_log import audit_log  # noqa: E402
from power_log_fixtures import SECRET_NAME, build_game, to_text  # noqa: E402
from test_collect_power_logs import Env  # noqa: E402
from test_real_policy_dataset import CATALOG, fixture  # noqa: E402

from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.integrations.powerlog.tolerant_parse import UnknownTags, read_line, read_lines  # noqa: E402

NEW_TAG = "BRAND_NEW_TAG"
NEW_KEYWORD = "BRAND_NEW_KEYWORD"
POWER = " GameState.DebugPrintPower() - "


def _prefix(line: str) -> str:
    return line.split(" - ", 1)[0] + " - "


def with_new_format(lines: list[str], *, keyword: str | None = NEW_KEYWORD) -> list[str]:
    """The same log with unknown tag rows, an unknown TAG_CHANGE and an unknown BLOCK_START keyword added."""
    out: list[str] = []
    rows_done = changes_done = keyword_done = False
    for line in lines:
        text = line.split(" - ", 1)[1] if POWER in line else ""
        if keyword is not None and not keyword_done and text.startswith("BLOCK_START BlockType=PLAY"):
            line += f" TriggerKeyword={keyword}"  # first PLAY block only
            keyword_done = True
        out.append(line)
        if not rows_done and text.strip() == "tag=ZONE value=HAND":
            out.append(_prefix(line) + f"    tag={NEW_TAG} value=1")  # row inside a FULL_ENTITY packet
            rows_done = True
        if not changes_done and text.startswith("TAG_CHANGE Entity=GameEntity tag=TURN"):
            out.append(_prefix(line) + f"TAG_CHANGE Entity=2 tag={NEW_TAG} value=3")
            changes_done = True
    assert rows_done and changes_done, "fixture changed: no place to add the new-format lines"
    return out


def parse(lines: list[str]) -> tuple[LogParser, UnknownTags]:
    parser = LogParser()
    unknown = read_lines(parser, (line + "\n" for line in lines))
    return parser, unknown


def blocks(packets) -> list[Block]:
    found: list[Block] = []
    for packet in packets:
        if isinstance(packet, (Block, SubSpell)):
            if isinstance(packet, Block):
                found.append(packet)
            found.extend(blocks(packet.packets))
    return found


def shape(packets) -> list:
    """Packet types with block nesting: equal shapes mean the tree was not desynchronised."""
    return [(type(p).__name__, shape(p.packets)) if isinstance(p, (Block, SubSpell)) else type(p).__name__
            for p in packets]


# -- the reader -----------------------------------------------------------------------------------------------------

def test_strict_hslog_rejects_the_new_names_which_is_the_reported_failure():
    lines = with_new_format(build_game(seed=1))
    parser = LogParser()
    with pytest.raises(NoSuchEnum) as info:
        for line in lines:
            parser.read_line(line + "\n")
    assert info.value.enum is GameTag and info.value.value == NEW_TAG


def test_unknown_tag_rows_and_keyword_are_tolerated_without_changing_the_tree():
    clean = build_game(seed=2)
    noisy_parser, unknown = parse(with_new_format(clean))
    clean_parser, none = parse(clean)

    assert none.as_dict() == {}
    assert unknown.as_dict() == {"tag_lines_skipped": {NEW_TAG: 2}, "trigger_keywords_kept": {NEW_KEYWORD: 1}}
    assert shape(noisy_parser.games[0].packets) == shape(clean_parser.games[0].packets)

    kept = [b for b in blocks(noisy_parser.games[0].packets) if b.trigger_keyword == NEW_KEYWORD]
    assert len(kept) == 1 and kept[0].type == BlockType.PLAY and kept[0].ended
    assert all(b.trigger_keyword is None for b in blocks(clean_parser.games[0].packets))


def test_known_keywords_stay_enum_members():
    lines = with_new_format(build_game(seed=3), keyword="DEATHRATTLE")
    parser, unknown = parse(lines)
    assert unknown.trigger_keywords == {}
    assert [b.trigger_keyword for b in blocks(parser.games[0].packets)].count(GameTag.DEATHRATTLE) == 1


def test_nested_block_keeps_its_children_and_parent_after_an_unknown_keyword():
    outer = "BLOCK_START BlockType=POWER Entity=6 EffectCardId= EffectIndex=0 Target=0 SubOption=-1"
    inner = f"BLOCK_START BlockType=TRIGGER Entity=7 EffectCardId= EffectIndex=0 Target=0 SubOption=-1 TriggerKeyword={NEW_KEYWORD}"
    game = build_game(seed=4)
    at = next(i for i, line in enumerate(game) if "BLOCK_END" in line)
    prefix = _prefix(game[at])
    body = [prefix + outer, prefix + "    TAG_CHANGE Entity=2 tag=RESOURCES_USED value=1",
            prefix + "    " + inner, prefix + "        TAG_CHANGE Entity=2 tag=RESOURCES_USED value=2",
            prefix + "    BLOCK_END", prefix + "    TAG_CHANGE Entity=2 tag=RESOURCES_USED value=3", prefix + "BLOCK_END"]
    parser, unknown = parse(game[:at] + body + game[at:])
    assert unknown.trigger_keywords == {NEW_KEYWORD: 1}
    top = next(b for b in blocks(parser.games[0].packets) if b.entity == 6 and b.type == BlockType.POWER)
    child = next(p for p in top.packets if isinstance(p, Block))
    assert child.trigger_keyword == NEW_KEYWORD and len(child.packets) == 1
    assert len(top.packets) == 3  # TAG_CHANGE, nested block, TAG_CHANGE: the parent was not closed early


@pytest.mark.parametrize("line", [
    # an unknown name anywhere else, or an unknown *value*, is still a rejected record
    "BLOCK_START BlockType=NOT_A_BLOCK_TYPE Entity=6 EffectCardId= EffectIndex=0 Target=0 SubOption=-1",
    "TAG_CHANGE Entity=2 tag=ZONE value=NOT_A_ZONE",
    f"HIDE_ENTITY - Entity=6 tag={NEW_TAG} value=DECK",
])
def test_everything_else_still_fails_closed(line):
    game = build_game(seed=5)
    at = next(i for i, text in enumerate(game) if "BLOCK_END" in text)
    parser = LogParser()
    with pytest.raises(Exception) as info:
        for text in game[:at] + [_prefix(game[at]) + line]:
            read_line(parser, text + "\n", UnknownTags())
    assert isinstance(info.value, ParsingError)


# -- the paths that failed -------------------------------------------------------------------------------------------

def test_audit_log_accepts_a_completed_match_with_new_tags(tmp_path: Path):
    path = tmp_path / "match.log"
    path.write_text(to_text(with_new_format(build_game(seed=6))), encoding="utf-8")
    result = audit_log(path)
    assert result["eligible_for_capture"] is True
    assert result["unknown_tags"] == {"tag_lines_skipped": {NEW_TAG: 2}, "trigger_keywords_kept": {NEW_KEYWORD: 1}}

    plain = tmp_path / "plain.log"
    plain.write_text(to_text(build_game(seed=6)), encoding="utf-8")
    assert "unknown_tags" not in audit_log(plain)  # old logs: result unchanged


def test_collector_imports_a_new_format_match_and_reports_no_failure(tmp_path: Path):
    env = Env(tmp_path)
    env.write("Power.log", to_text(with_new_format(build_game(seed=7))))
    collector = env.collector()
    collector.scan_once()

    assert collector.stats.matches_imported == 1 and collector.stats.parse_failures == 0
    assert not [m for m in env.messages if "POWERLOG_RECORD_REJECTED" in m or "warning" in m]
    assert len(env.outputs()) == 1 and len(list(env.raw.glob("*.log"))) == 1
    assert SECRET_NAME not in "\n".join(env.messages)
    assert cpl.PARSE_FAILED not in collector.stats.skipped


def test_collector_still_rejects_a_genuinely_malformed_record(tmp_path: Path):
    env = Env(tmp_path)
    lines = with_new_format(build_game(seed=8))
    at = next(i for i, line in enumerate(lines) if " - BLOCK_START " in line)
    lines[at] = f"{_prefix(lines[at])}BLOCK_START BlockType=NOT_A_BLOCK_TYPE Entity=6 EffectCardId= EffectIndex=0 Target=0 SubOption=-1"
    env.write("Power.log", to_text(lines))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.matches_imported == 0 and collector.stats.parse_failures == 1
    assert any("code=POWERLOG_RECORD_REJECTED" in m for m in env.messages)


def test_policy_import_labels_the_same_action_with_and_without_the_new_format():
    clean = fixture(6, 50, seed=11).lines
    clean_rows, clean_summary = extract_match(clean, CATALOG)
    noisy_rows, noisy_summary = extract_match(with_new_format(clean), CATALOG)

    assert noisy_summary["decisions_labeled"] == clean_summary["decisions_labeled"] == 1
    for noisy, plain in zip(noisy_rows, clean_rows):
        assert noisy["legal_actions"] == plain["legal_actions"]
        assert noisy["chosen_action_index"] == plain["chosen_action_index"]
        assert noisy["state"] == plain["state"]
        assert noisy["final_result"] == plain["final_result"]
    action = noisy_rows[0]["legal_actions"][noisy_rows[0]["chosen_action_index"]]
    assert action["type"] == "PLAY_CARD" and action["card_id"] == "CS2_029"


def test_audit_summary_is_json_serialisable_and_has_no_log_text(tmp_path: Path):
    path = tmp_path / "match.log"
    path.write_text(to_text(with_new_format(build_game(seed=9))), encoding="utf-8")
    text = json.dumps(audit_log(path))
    assert SECRET_NAME not in text and "Opponent#0001" not in text


def test_live_session_keeps_block_structure_and_state_across_an_unknown_keyword():
    from live_fixtures import LiveLog
    from test_live_session import drive, make, snapshots

    clean = LiveLog().create_game().mulligan().self_decision(1)
    noisy = LiveLog().create_game().mulligan()
    noisy.batch([
        f"BLOCK_START BlockType=TRIGGER Entity=1 EffectCardId= EffectIndex=0 Target=0 SubOption=-1 TriggerKeyword={NEW_KEYWORD}",
        f"    TAG_CHANGE Entity=2 tag={NEW_TAG} value=1",
        "BLOCK_END",
    ])
    noisy.self_decision(1)

    clean_session, noisy_session = make(), make()
    clean_snapshots = snapshots(drive(clean_session, clean.lines))
    noisy_snapshots = snapshots(drive(noisy_session, noisy.lines))
    assert len(clean_snapshots) == len(noisy_snapshots) == 1
    assert noisy_snapshots[0].state_hash == clean_snapshots[0].state_hash
    reducer = noisy_session.game.reducer
    assert reducer.unknown_tags.as_dict() == {"tag_lines_skipped": {NEW_TAG: 1}, "trigger_keywords_kept": {NEW_KEYWORD: 1}}
    assert reducer.skipped_unknown_tags == 1
    assert noisy_session.game.reducer.parser.games[0].packets  # tree intact: nothing after BLOCK_END was orphaned


def test_evidence_extractor_records_an_unknown_trigger_keyword_by_name():
    from evidence_fixtures import blk, flat, meta, play_game, tag
    from test_evidence_extractor import obs_for, run

    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(
        meta("DAMAGE", 1, 50), tag(50, "DAMAGE", 1))), blk("TRIGGER", 41, tag(50, "ATK", 5), keyword=NEW_KEYWORD))
    result = run(play_game(body, entity=6))
    spell = obs_for(result, "TEST_SPELL", "PLAYED_CARD")
    assert any(u["trigger_keyword"] == NEW_KEYWORD for u in spell["window"]["units"])
