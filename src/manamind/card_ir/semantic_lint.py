"""Opt-in B1 consistency checks. Warnings are review requests, never semantic proof.

The original lint/validator remain frozen for paired measurements and A reproducibility.
Only narrow unambiguous English templates are checked; other wording is deliberately
left to independent review. No card IDs, names, sets or metadata-specific branches.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Any

from manamind.card_ir.validate import normalise_text

WORDS = {word: n for n, word in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"))}
NUMBER = r"(?:\d+|" + "|".join(WORDS) + r")"
KEYWORD_WORDS = {"RUSH": "rush", "TAUNT": "taunt", "DIVINE_SHIELD": "divine shield",
                 "LIFESTEAL": "lifesteal", "REBORN": "reborn", "WINDFURY": "windfury"}
VERBS = {"DEAL_DAMAGE": r"\bdeal\b(?! damage with)", "RESTORE_HEALTH": r"\brestore\b",
         "SUMMON": r"\bsummon\b", "DRAW": r"\bdraw\b", "DESTROY": r"\bdestroy\b",
         "SILENCE": r"\bsilence\b", "MODIFY_COST": r"\breduce\b", "TRANSFORM": r"\btransform\b"}


def nodes(value: Any) -> Iterator[Mapping]:
    if isinstance(value, Mapping):
        yield value
        for key, child in value.items():
            if key not in ("span", "text", "decisions", "dependencies"):
                yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def _integer(text):
    return int(text) if text.isdigit() else WORDS[text]


def lint_semantics(doc: Mapping[str, Any]) -> list[str]:
    warnings = []
    for index, ability in enumerate(doc.get("abilities", [])):
        span = normalise_text(ability.get("span", "")).lower()
        tree = list(nodes(ability))
        ops = [n for n in tree if "op" in n]
        prefix = f"abilities[{index}]"

        # Associate number WORDS with operation counts, not an unrelated literal in the subtree.
        for verb, op in (("summon", "SUMMON"), ("draw", "DRAW"), ("cast", "CAST"), ("add", "ADD_TO_HAND")):
            matches = list(re.finditer(rf"\b{verb}\s+({NUMBER}|a|an)\b", span))
            candidates = [n for n in ops if n["op"] == op]
            if len(matches) == len(candidates) == 1:
                word = matches[0][1]
                expected = 1 if word in ("a", "an") else _integer(word)
                operation = candidates[0]
                source = operation.get("what", {}).get("from_zone", {})
                actual = operation.get("count", source.get("n", 1))
                if actual != expected:
                    warnings.append(f"{prefix}: count: '{verb} {word}' requires count={expected}")

        # Scope constraints apply to EACH affected selector, not merely somewhere in the ability.
        if re.search(r"\ball other minions\b", span):
            for op in ops:
                target = op.get("to")
                if isinstance(target, Mapping) and target.get("type") == "MINION" and "pick" in target:
                    if target.get("pick") != "ALL" or "SELF" not in target.get("exclude", []):
                        warnings.append(f"{prefix}: other: all other minions requires ALL excluding SELF")
        if re.search(r"\bgive your minions\b", span):
            for op in ops:
                target = op.get("to")
                if op["op"] == "ENCHANT" and isinstance(target, Mapping) and "pick" in target:
                    if (target.get("pick"), target.get("side"), target.get("type"), target.get("zone", "PLAY")) != (
                            "ALL", "FRIENDLY", "MINION", "PLAY"):
                        warnings.append(f"{prefix}: your minions: requires ALL FRIENDLY MINION in PLAY")

        # Unambiguous global enemy damage phrase, including repeated copies of its operation.
        if re.search(r"\bdamage to all enemies\b", span) and not re.search(r"\b(friendly|your minions)\b", span):
            for op in ops:
                if op["op"] == "DEAL_DAMAGE":
                    target = op.get("to")
                    if isinstance(target, Mapping) and "pick" in target and (
                            target.get("side"), target.get("type"), target.get("zone", "PLAY")) != (
                                "ENEMY", "CHARACTER", "PLAY"):
                        warnings.append(f"{prefix}: enemy scope: damage must address enemy characters in PLAY")

        # Grants/predicates must have their exact keyword in their own ability span, in both directions.
        used = {k for n in tree for k in n.get("keywords", []) if isinstance(k, str)}
        used.update(n["keyword"] for n in tree if isinstance(n.get("keyword"), str))
        for keyword, word in KEYWORD_WORDS.items():
            present = bool(re.search(rf"\b{word}\b", span))
            if keyword in used and not present:
                warnings.append(f"{prefix}: keyword: IR {keyword} absent from span")
            # A summoned token can carry the keyword in its metadata instead of an ENCHANT.
            grant = re.search(rf"\b(?:give|gain|grant)\b[^.;]*\b{word}\b", span)
            predicate = re.search(rf"\bminion with {word}\b", span)
            if present and (grant or predicate) and keyword not in used:
                warnings.append(f"{prefix}: keyword: '{word}' absent from IR")

        # Only straight-line sequences with uniquely named verbs: do not guess across branches/triggers.
        effect = ability.get("effect", {})
        steps = effect.get("seq", []) if isinstance(effect, Mapping) else []
        if steps and all(isinstance(s, Mapping) and s.get("op") in VERBS for s in steps):
            positions = []
            for step in steps:
                matches = list(re.finditer(VERBS[step["op"]], span))
                if len(matches) != 1:
                    break
                positions.append(matches[0].start())
            else:
                if len(set(positions)) == len(positions) and positions != sorted(positions):
                    warnings.append(f"{prefix}: order: straight-line operations differ from textual verb order")

        # For a simple two-step result -> 'it/them/that minion', verify its actual target.
        if len(steps) == 2 and isinstance(steps[0], Mapping) and steps[0].get("as"):
            follow = steps[1]
            if isinstance(follow, Mapping) and follow.get("op") in ("ENCHANT", "MODIFY_COST", "DESTROY", "TRANSFORM"):
                if re.search(r"\b(?:give|destroy|transform) (?:it|them|that minion)\b|\bits cost\b|\bit costs\b", span):
                    if follow.get("to") != {"ref": steps[0]["as"]}:
                        warnings.append(f"{prefix}: reference: follow-up pronoun must target the preceding result")
    return warnings
