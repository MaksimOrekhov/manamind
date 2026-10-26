"""Lexical anchors: cheap, deterministic consistency warnings between an ability's text span and its IR.

A forward anchor says "this phrase in the span needs this IR feature somewhere in the ability"; a reverse anchor says
"this IR feature needs a supporting word in the span". They catch flipped sides, picks, zones and timings that pass the
structural validator. They read the same English as the author, so they are a consistency filter, not independent
evidence, and a clean lint never proves a reading right.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterator, Mapping

from manamind.card_ir.validate import normalise_text


def _pairs(node: Any, key: str = "") -> Iterator[tuple[str, Any]]:
    """Every (key, scalar value) pair of a subtree; scalars inside a list keep the list's key."""
    if isinstance(node, Mapping):
        for child_key, value in node.items():
            yield child_key, None
            yield from _pairs(value, child_key)
    elif isinstance(node, list):
        for item in node:
            yield from _pairs(item, key)
    else:
        yield key, node


def _features(ability: Mapping[str, Any]) -> set[str]:
    """'key:K' for every key, 'K=V' and 'value=V' for every scalar value."""
    found = set()
    for key, value in _pairs({k: v for k, v in ability.items() if k != "span"}):
        if value is None:
            found.add(f"key:{key}")
        else:
            found.update({f"{key}={value}", f"value={value}"})
    return found


def _has(*features: str) -> Callable[[set[str]], bool]:
    return lambda found: any(feature in found for feature in features)


# (name, regex on the lower-case span, requirement on the ability's features)
FORWARD: tuple[tuple[str, str, Callable[[set[str]], bool]], ...] = (
    ("random", r"\brandom", _has("pick=RANDOM", "key:random_from")),
    # "randomly split among all enemies" names the candidates of a random pick, not an ALL selector
    ("all", r"(?<!among )\ball\b", _has("pick=ALL")),
    ("enemy", r"\b(enemy|enemies|opponent'?s?)\b", _has("side=ENEMY", "value=ENEMY_HERO", "value=ENEMY_WEAPON",
                                                       "player=OPPONENT")),
    ("friendly", r"\bfriendly\b", _has("side=FRIENDLY")),
    ("in hand", r"\bin your hand\b", _has("zone=HAND")),
    ("deck zone", r"\b(from|in) your deck\b|\bhand and deck\b", _has("zone=DECK")),
    ("after", r"^after\b", _has("timing=AFTER")),
    ("whenever", r"\bwhenever\b", _has("timing=WHENEVER")),
    ("at turn phase", r"^at the (start|end)\b", _has("timing=AT")),
    ("when", r"^when\b", _has("timing=WHEN")),
    # "you deal damage with a spell" is an event, not an operation
    ("deal", r"\bdeal\b(?! damage with)", _has("op=DEAL_DAMAGE")),
    ("restore", r"\brestore\b", _has("op=RESTORE_HEALTH")),
    ("summon", r"\bsummon", _has("op=SUMMON")),
    ("destroy", r"\bdestroy\b", _has("op=DESTROY")),
    ("silence", r"\bsilence\b", _has("op=SILENCE")),
    ("discover", r"\bdiscover\b", _has("op=DISCOVER")),
    ("transform", r"\btransform", _has("op=TRANSFORM")),
    ("shuffle", r"\bshuffle\b", _has("op=SHUFFLE_INTO_DECK")),
    ("draw", r"(?<!you )\bdraw\b", _has("op=DRAW")),
    ("get/add", r"\b(get|add)\b", _has("op=ADD_TO_HAND")),
    ("cost reduced", r"\bcosts? \(\d+\) less\b|\breduce its cost\b", _has("key:reduce")),
    ("cost set", r"\bcosts \(0\)", _has("key:set")),
)
REVERSE: tuple[tuple[str, str, str], ...] = (
    ("side=ENEMY", "enemy side needs an enemy word", r"\b(enemy|enemies|opponent'?s?)\b"),
    ("side=FRIENDLY", "friendly side needs a friendly word", r"\b(friendly|your|you)\b"),
    ("zone=HAND", "hand zone needs 'hand' or 'discard'", r"\b(hand|discard)\b"),
    ("zone=DECK", "deck zone needs 'deck'", r"\bdeck\b"),
    ("timing=AFTER", "AFTER needs 'after'", r"\bafter\b"),
    ("timing=WHENEVER", "WHENEVER needs 'whenever' or 'the first time'", r"\b(whenever|the first time)\b"),
    ("timing=AT", "AT needs 'at the start/end' or 'end of turn'", r"\bat the (start|end)\b|\bend of turn\b"),
    ("timing=WHEN", "WHEN needs 'when'", r"\bwhen\b"),
)


def lint_declaration(doc: Mapping[str, Any]) -> list[str]:
    warnings = []
    for index, ability in enumerate(doc.get("abilities", [])):
        span = normalise_text(ability.get("span", "")).lower()
        found = _features(ability)
        for name, pattern, requirement in FORWARD:
            if re.search(pattern, span) and not requirement(found):
                warnings.append(f"abilities[{index}]: '{name}' in the text but not in the IR")
        for feature, message, pattern in REVERSE:
            if feature in found and not re.search(pattern, span):
                warnings.append(f"abilities[{index}]: {message}")
    return warnings
