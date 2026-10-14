"""Read Power.log through hslog without failing on tag names the installed package predates.

``hslog`` resolves every tag *name* through the ``hearthstone`` package's ``GameTag`` enum and raises
``NoSuchEnum`` for a name it does not know. The game client adds tags with its patches (Oct 2026:
``CRAFTABLE_OUTPUT_POWER``, ``THO_DEFEATED_ALLY``, ...) while the enum only follows in a later package release, so one
such name used to reject the whole match. The name can appear in two positions, and each needs its own handling:

* a **tag line** - the ``tag=NAME value=...`` rows of an entity packet and ``TAG_CHANGE`` lines. hslog parses the line
  before it changes any state, and a tag with no name in the enum has no feature in any ManaMind schema, so the line
  is skipped and counted. Skipping cannot desynchronise the packet tree.
* the ``TriggerKeyword=NAME`` of a **BLOCK_START**. The line must not be skipped: its ``BLOCK_END`` would then close
  the parent block and every later packet would be attributed to the wrong block. The block is created with a numeric
  stand-in keyword and the original name is restored on the packet, so the tree is complete and the name stays visible
  to the evidence extractor (``Block.trigger_keyword`` is only read there, as a code).

Everything else hslog rejects - an unknown name in any other position, an unknown value of a known tag, a malformed
record - still raises. Names are counted (tag names are game vocabulary, not log text) so callers can report them.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from hearthstone.enums import GameTag
from hslog import LogParser
from hslog.exceptions import NoSuchEnum, ParsingError
from hslog.packets import Block

_TAG_ROW = re.compile(r"\) -\s+tag=(\w+) value=\S+\s*$")
_TAG_CHANGE = re.compile(r"\bTAG_CHANGE Entity=.* tag=(\w+) value=\S+(?: DEF CHANGE)?\s*$")
_BLOCK_KEYWORD = re.compile(r"^(?P<head>.*\bBLOCK_START .* TriggerKeyword=)(?P<name>\w+)$")
_STAND_IN_KEYWORD = 0  # parsed as a plain integer by hslog; replaced by the real name right away


@dataclass
class UnknownTags:
    """Tag names this hearthstone package does not know, by how they were handled."""

    tag_lines: Counter = field(default_factory=Counter)         # name -> tag lines skipped
    trigger_keywords: Counter = field(default_factory=Counter)  # name -> BLOCK_START lines kept with the name

    @property
    def skipped_tag_lines(self) -> int:
        return sum(self.tag_lines.values())

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {key: dict(sorted(counter.items())) for key, counter in
                (("tag_lines_skipped", self.tag_lines), ("trigger_keywords_kept", self.trigger_keywords)) if counter}


def _is_unknown_tag_line(error: NoSuchEnum, line: str) -> bool:
    """A tag row or TAG_CHANGE whose tag *name* is the one hslog rejected (not HIDE_ENTITY, not a block header)."""
    text = line.rstrip("\r\n")
    matches = (_TAG_ROW.search(text), _TAG_CHANGE.search(text))
    return any(match is not None and match.group(1) == str(error.value) for match in matches)


def _read_block_with_unknown_keyword(parser: LogParser, head: str, name: str) -> None:
    parser.read_line(f"{head}{_STAND_IN_KEYWORD}\n")
    block = parser._parsing_state.current_block
    if not isinstance(block, Block) or block.ended or block.trigger_keyword != _STAND_IN_KEYWORD:
        raise ParsingError("BLOCK_START keyword could not be restored")
    block.trigger_keyword = name


def read_line(parser: LogParser, line: str, unknown: UnknownTags) -> None:
    """``parser.read_line`` that tolerates unknown tag names as described in the module docstring."""
    try:
        parser.read_line(line)
    except NoSuchEnum as error:
        if error.enum is not GameTag:
            raise
        name = str(error.value)
        keyword = _BLOCK_KEYWORD.match(line.rstrip("\r\n"))
        if keyword is not None and keyword.group("name") == name:
            _read_block_with_unknown_keyword(parser, keyword.group("head"), name)
            unknown.trigger_keywords[name] += 1
        elif _is_unknown_tag_line(error, line):
            unknown.tag_lines[name] += 1
        else:
            raise


def read_lines(parser: LogParser, lines: Iterable[str]) -> UnknownTags:
    """Feed ``lines`` to ``parser``; return the unknown tag names met on the way."""
    unknown = UnknownTags()
    for line in lines:
        read_line(parser, line, unknown)
    return unknown
