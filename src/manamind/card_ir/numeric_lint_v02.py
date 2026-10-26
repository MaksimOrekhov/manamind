"""Bound numeric literals to their semantic roles in narrow v0.2 text templates.

The frozen v0.1 bag-of-numbers check remains unchanged. This does NOT require
every IR number to occur in text: defaults, arithmetic and token metadata are
legitimate. Only an unambiguous stat grant or explicit/singular discard count
is checked against its matching operation, never against another role's number.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from manamind.card_ir.semantic_lint import NUMBER, WORDS, nodes
from manamind.card_ir.strict_lint import _actions
from manamind.card_ir.validate import normalise_text

_STATS = re.compile(r"\b(?:give|gain|grant)\b[^.;]*?([+-]\d+)/([+-]\d+)")
_DISCARD = re.compile(rf"\bdiscard\s+(a|an|{NUMBER})\s+(?:random\s+)?(?:\w+\s+)?(?:spells?|cards?|minions?)\b")


def _literal(value):
    return isinstance(value, int) and not isinstance(value, bool)


def lint_numeric_roles(doc: Mapping) -> list[str]:
    warnings = []
    for i, ability in enumerate(doc.get("abilities", [])):
        span = normalise_text(ability.get("span", "")).lower()
        stats = list(_STATS.finditer(span))
        grants = [a.node for a in _actions(ability.get("effect", {}))
                  if a.node["op"] == "ENCHANT" and {"attack", "health"} & a.node.keys()]
        # Pair by occurrence only when cardinality is exact; no guessing across
        # unmatched templates, generated token stats or arbitrary expressions.
        if len(stats) == len(grants):
            for index, (phrase, node) in enumerate(zip(stats, grants)):
                for field, text in zip(("attack", "health"), phrase.groups()):
                    value = node.get(field, 0)
                    if _literal(value) and value != int(text):
                        warnings.append(f"abilities[{i}]: NUMERIC_STAT_ROLE: grant {index} {field}="
                                        f"{value} differs from its own text {text}")
        phrases = list(_DISCARD.finditer(span))
        selectors = [n["discard"] for n in nodes(ability.get("effect", {})) if "discard" in n]
        if len(phrases) == len(selectors):
            for index, (phrase, selector) in enumerate(zip(phrases, selectors)):
                if not isinstance(selector, Mapping) or selector.get("pick") != "RANDOM":
                    continue
                word = phrase[1]
                expected = 1 if word in ("a", "an") else int(word) if word.isdigit() else WORDS[word]
                actual = selector.get("n", 1)
                if _literal(actual) and actual != expected:
                    warnings.append(f"abilities[{i}]: NUMERIC_DISCARD_ROLE: discard {index} count="
                                    f"{actual} differs from its own text count {expected}")
    return warnings
