"""Heuristic text and tag features used to size Card IR work. They are screens, not rules.

``families`` groups cards by official tags and obvious verbs. ``special_cases`` marks records whose behaviour cannot be
recovered from the text string alone. A record without a special-case flag is not proven simple: the screens only
detect what is visible in the record.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .snapshot import plain_text

_TRIGGER = re.compile(r"\b(whenever|after you|after a|after this|after your|at the (?:start|end) of|when you|when this|each time)\b", re.I)
_VERBS = {
    "summon": r"\bsummon", "draw": r"\bdraw\b", "damage": r"\bdeal\b[^.]*\bdamage|\bdamage\b", "heal": r"\brestore\b|\bheal",
    "buff": r"\+\d+|\bgain\b[^.]*\b(attack|health)|\bgive\b[^.]*\+", "destroy": r"\bdestroy", "copy": r"\bcopy|\bcopies",
    "transform": r"\btransform", "freeze": r"\bfreeze|\bfrozen", "armor": r"\barmor\b", "mana": r"mana crystal|\bmana\b",
    "cost_change": r"\bcosts?\b[^.]*\b(less|more)\b|\breduce|\bcost (?:of|\()", "bounce": r"return[^.]*\bto (?:its owner's|your) hand",
    "add_or_get_card": r"\b(?:add|get)\b[^.]*\bto your hand|\bget a\b", "discover": r"\bdiscover\b", "random": r"\brandom",
    "shuffle": r"\bshuffle", "equip": r"\bequip", "silence": r"\bsilence", "counter_progress": r"\b\d+\s*(?:left|more)\b|\bprogress\b",
}
_VERB_RE = {name: re.compile(pattern, re.I) for name, pattern in _VERBS.items()}

_HIDDEN_INFO = re.compile(r"\b(?:your|the opponent's|your opponent's|enemy) (?:deck|hand)\b|\bin your deck\b|\bopponent's hand\b", re.I)
_HISTORY = re.compile(r"\bthis (?:game|turn)\b|\blast turn\b|\bhas died\b|\bwere? played\b|\bhave played\b|\bspent\b|\bdied\b", re.I)
_RUNTIME_VALUE = re.compile(r"\{\d+\}")
# Mechanics whose rule is a counter or state hidden behind a keyword and not stated numerically in the text.
_STATEFUL_TAGS = frozenset({
    "QUEST", "SIDE_QUEST", "INFUSE", "SPELLBURST", "FRENZY", "DORMANT", "TITAN", "COLOSSAL", "TRADEABLE", "OUTCAST",
    "FORGETFUL", "START_OF_GAME", "SECRET", "COMBO", "TRIGGER_VISUAL", "DISCOVER", "ADAPT", "CHOOSE_ONE",
})


def families(record: Mapping[str, Any]) -> frozenset[str]:
    """Official mechanic tags (as ``tag:NAME``), card type, and verb families visible in the text."""
    found: set[str] = set()
    for key in ("mechanics", "referencedTags"):
        value = record.get(key)
        if isinstance(value, list):
            found.update(f"tag:{tag}" for tag in value if isinstance(tag, str))
    if isinstance(record.get("type"), str):
        found.add(f"type:{record['type']}")
    text = plain_text(record.get("text"))
    if text:
        if _TRIGGER.search(text):
            found.add("verb:trigger_sentence")
        for name, regex in _VERB_RE.items():
            if regex.search(text):
                found.add(f"verb:{name}")
    return frozenset(found)


def special_cases(record: Mapping[str, Any]) -> frozenset[str]:
    """Reasons the text alone does not define the behaviour (non-exclusive)."""
    raw = record.get("text") if isinstance(record.get("text"), str) else ""
    text = plain_text(raw)
    cases: set[str] = set()
    if "@" in raw:
        cases.add("multi_state_text")
    if _RUNTIME_VALUE.search(raw):
        cases.add("runtime_value_in_text")
    if _VERB_RE["random"].search(text) or _VERB_RE["discover"].search(text):
        cases.add("pool_not_in_text")
    if _HIDDEN_INFO.search(text):
        cases.add("hidden_information")
    if _HISTORY.search(text):
        cases.add("game_history_counter")
    mechanics = record.get("mechanics")
    if isinstance(mechanics, list) and _STATEFUL_TAGS & set(mechanics):
        cases.add("stateful_keyword")
    if record.get("countAsCopyOfDbfId") is not None:
        cases.add("copy_alias_of_another_card")
    return frozenset(cases)
