"""Coverage of card IDs found in recorded decision states, measured against a metadata source.

Levels are reported separately and never merged: an ID can be resolved, have complete metadata, have meaningful
text, parse under the ManaMind grammar and be declared in an engine, and each of those is a different claim.
Presence of text does not mean an effect is supported.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from .snapshot import EFFECT_TAGS, quality_flags, strip_text_artifacts

EFFECT_ZONES = ("hand", "self_board", "opp_board", "self_weapon", "opp_weapon", "self_location", "opp_location")
EXTRA_ZONES = ("self_hero_power", "opp_hero_power", "opp_revealed")
INCOMPLETE_FLAGS = frozenset({"MISSING_TYPE", "MISSING_NAME", "MISSING_CLASS", "MISSING_COST", "MISSING_STATS"})


class TextStatus(str, Enum):
    """Mutually exclusive state of one card ID about its text, from least to most usable.

    Completeness of the other fields is a separate property (``missing_fields``); an incomplete record can still have
    a parseable text, and hiding that would understate what is known.
    """

    MISSING_ID = "MISSING_ID"
    EMPTY_TEXT_WITH_EFFECT_TAG = "EMPTY_TEXT_WITH_EFFECT_TAG"
    EMPTY_TEXT_VANILLA = "EMPTY_TEXT_VANILLA"
    TEXT_PARSED = "TEXT_PARSED"
    TEXT_UNPARSED_TRIGGER = "TEXT_UNPARSED_TRIGGER"
    TEXT_UNPARSED_OPAQUE = "TEXT_UNPARSED_OPAQUE"


def entities(state: Mapping[str, Any]) -> list[tuple[str, str]]:
    """(zone, card_id) for every card entity in a decision state.

    Board and Location slots nest the card under ``card``; hand, weapon, Hero Power and revealed-card entries are
    cards themselves.
    """
    out: list[tuple[str, str | None]] = []
    for side, tag in (("self_player", "self"), ("opponent", "opp")):
        player = state[side]
        out += [(f"{tag}_board", (m.get("card") or {}).get("card_id")) for m in player.get("board") or []]
        out += [(f"{tag}_location", (m.get("card") or {}).get("card_id")) for m in player.get("locations") or []]
        if player.get("weapon"):
            out.append((f"{tag}_weapon", player["weapon"].get("card_id")))
        if player.get("hero_power"):
            out.append((f"{tag}_hero_power", player["hero_power"].get("card_id")))
    out += [("hand", h.get("card_id")) for h in state.get("self_hand") or []]
    out += [("opp_revealed", c if isinstance(c, str) else c.get("card_id")) for c in state.get("opponent_known_cards") or []]
    return [(zone, card_id) for zone, card_id in out if card_id]


def missing_fields(record: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Essential fields absent from a record (empty for a complete record; ``None`` record: not applicable)."""
    return () if record is None else tuple(sorted(set(quality_flags(record)) & INCOMPLETE_FLAGS))


def text_status(
    record: Mapping[str, Any] | None,
    parse: Callable[[str], Any],
    *,
    strip_artifacts: bool = True,
) -> TextStatus:
    """Classify a record. ``parse`` is the grammar's ``parse_text`` (kept out of this module to stay independent)."""
    if record is None:
        return TextStatus.MISSING_ID
    flags = set(quality_flags(record))
    raw = record.get("text") if isinstance(record.get("text"), str) else ""
    text = strip_text_artifacts(raw) if strip_artifacts else raw
    if not text.strip() or "EMPTY_TEXT" in flags:
        mechanics = record.get("mechanics") if isinstance(record.get("mechanics"), list) else []
        if EFFECT_TAGS & set(mechanics):
            return TextStatus.EMPTY_TEXT_WITH_EFFECT_TAG
        return TextStatus.EMPTY_TEXT_VANILLA
    parsed = parse(text)
    if parsed.trigger_sentences:
        return TextStatus.TEXT_UNPARSED_TRIGGER
    if any(clause.kind == "OPAQUE" for clause in parsed.clauses):
        return TextStatus.TEXT_UNPARSED_OPAQUE
    return TextStatus.TEXT_PARSED


def share(part: int, whole: int) -> float | None:
    return None if not whole else round(part / whole, 6)


def status_counts(
    appearances: Mapping[str, int],
    getter: Callable[[str], Mapping[str, Any] | None],
    parse: Callable[[str], Any],
    engine_ids: Iterable[str] = (),
    *,
    strip_artifacts: bool = True,
) -> dict[str, Any]:
    """Appearance-weighted and unique-ID counts of each status, plus the independent levels."""
    engine = set(engine_ids)
    weighted: dict[str, int] = {}
    unique: dict[str, int] = {}
    levels = {"resolved": 0, "complete": 0, "text_meaningful": 0, "parse_complete": 0, "engine_declared": 0}
    unique_levels = dict.fromkeys(levels, 0)
    cache: dict[str, tuple[TextStatus, tuple[str, ...]]] = {}
    incomplete: dict[str, int] = {}
    total = 0
    for card_id, count in appearances.items():
        if card_id not in cache:
            record = getter(card_id)
            cache[card_id] = (text_status(record, parse, strip_artifacts=strip_artifacts), missing_fields(record))
        status, missing = cache[card_id]
        for flag in missing:
            incomplete[flag] = incomplete.get(flag, 0) + count
        total += count
        weighted[status.value] = weighted.get(status.value, 0) + count
        unique[status.value] = unique.get(status.value, 0) + 1
        achieved = {
            "resolved": status is not TextStatus.MISSING_ID,
            "complete": status is not TextStatus.MISSING_ID and not missing,
            "text_meaningful": status in (TextStatus.EMPTY_TEXT_VANILLA, TextStatus.TEXT_PARSED,
                                          TextStatus.TEXT_UNPARSED_TRIGGER, TextStatus.TEXT_UNPARSED_OPAQUE),
            "parse_complete": status in (TextStatus.EMPTY_TEXT_VANILLA, TextStatus.TEXT_PARSED),
            "engine_declared": card_id in engine,
        }
        for level, ok in achieved.items():
            if ok:
                levels[level] += count
                unique_levels[level] += 1
    return {
        "appearances": total,
        "unique_ids": len(appearances),
        "status_appearances": dict(sorted(weighted.items())),
        "status_unique_ids": dict(sorted(unique.items())),
        "incomplete_field_appearances": dict(sorted(incomplete.items())),
        "level_appearances": levels,
        "level_unique_ids": unique_levels,
        "level_share": {level: share(count, total) for level, count in levels.items()},
    }
