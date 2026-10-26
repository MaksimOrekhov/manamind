"""Conservative clause/control-flow checks for frozen Card IR v0.1 (no game execution)."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from manamind.card_ir.validate import normalise_text

VERBS = {
    "DRAW": r"\bdraw\b", "DEAL_DAMAGE": r"\bdeal\b(?! damage with)",
    "RESTORE_HEALTH": r"\brestore\b", "DESTROY": r"\bdestroy\b", "SILENCE": r"\bsilence\b",
    "SUMMON": r"\bsummon\b", "SHUFFLE_INTO_DECK": r"\b(?:shuffle|put)\b",
    "TRANSFORM": r"\btransform\b", "CAST": r"(?<!you've )(?<!you have )(?<!you )\bcast\b",
    "ENCHANT": r"\b(?:give|gain)\b",
}
CLASSES = frozenset("DEATHKNIGHT DEMONHUNTER DRUID HUNTER MAGE PALADIN PRIEST ROGUE SHAMAN WARLOCK WARRIOR NEUTRAL".split())
RACES = frozenset("BEAST DEMON DRAGON ELEMENTAL MECH MURLOC NAGA PIRATE QUILBOAR TOTEM UNDEAD".split())


def _core_decision(doc):
    cores = {d["id"] for d in doc["dependencies"] if d["scope"] == "CORE" and d["kind"] == "UNKNOWN_RULE"}
    return any(d.get("dep") in cores and d.get("risk") == "OUTCOME" for d in doc["decisions"])


def _nodes(node):
    if isinstance(node, Mapping):
        yield node
        for key, child in node.items():
            if key != "span":
                yield from _nodes(child)
    elif isinstance(node, list):
        for child in node:
            yield from _nodes(child)


@dataclass
class Action:
    node: Mapping
    guards: tuple


def _actions(effect, guards=()):
    if not isinstance(effect, Mapping):
        return
    if "op" in effect:
        yield Action(effect, guards)
    elif "seq" in effect:
        for step in effect["seq"]:
            yield from _actions(step, guards)
    elif "if" in effect:
        yield from _actions(effect["then"], (*guards, (effect["if"], True)))
        if "else" in effect:
            yield from _actions(effect["else"], (*guards, (effect["if"], False)))
    elif "repeat_while" in effect:
        yield from _actions(effect["do"], (*guards, (effect["repeat_while"], True)))
    elif "repeat" in effect:
        yield from _actions(effect["do"], guards)
    elif "pay" in effect:
        yield from _actions(effect["then"], guards)


def _alive(cond, entity, positive):
    node = cond.get("is") if isinstance(cond, Mapping) else None
    if isinstance(node, Mapping) and node.get("entity") == entity:
        # card-ir/0.2 survival predicate (R_SURVIVE); the v0.1 validator rejects it before this lint runs.
        return any(isinstance(p, Mapping) and p.get("alive") is positive for p in node.get("where", []))
    cmp = cond.get("cmp", []) if isinstance(cond, Mapping) else []
    if len(cmp) != 3:
        return False
    left, op, right = cmp
    if not isinstance(left, Mapping) or left.get("stat") != "HEALTH" or left.get("of") != entity:
        return False
    if positive:
        return (op, right) in ((">", 0), (">=", 1))
    return (op, right) in (("<=", 0), ("<", 1), ("=", 0))


def _condition_check(phrase, action, entity, warnings, path):
    # Guards come from the actual operation's control-flow ancestors, never a
    # condition in an unrelated sibling, event or decorative decision record.
    unless = bool(re.search(r"\bunless\b", phrase))
    if re.search(r"\bthis(?: minion)?\b", phrase):
        entity = "SELF"
    survives = bool(re.search(r"\bsurviv\w*\b", phrase))
    dies = bool(re.search(r"\b(?:dies|die|died)\b", phrase))
    if survives or dies:
        wanted_alive = survives != unless
        if not any(_alive(c, entity, wanted_alive == truth) for c, truth in action.guards):
            warnings.append(f"{path}: CONDITION_ENTITY: survival/death guard missing or on the wrong entity/branch")
    elif re.search(r"\b(?:is |isn't |is not )?(?:un)?damaged\b", phrase):
        wanted = not bool(re.search(r"\b(?:undamaged|isn't|is not)\b", phrase))
        wanted = wanted != unless
        def matches(cond, truth):
            node = cond.get("is", {})
            return node.get("entity") == entity and any(
                isinstance(p.get("damaged"), bool) and p["damaged"] == (wanted == truth)
                for p in node.get("where", []))
        if not any(matches(c, t) for c, t in action.guards):
            warnings.append(f"{path}: CONDITION_ENTITY: damaged guard missing or inverted")
    elif not action.guards:
        warnings.append(f"{path}: CONDITION_SCOPE: conditional text has an unconditional operation")


def _clauses(span, actions, start=0):
    """Pair repeated verbs by occurrence, only when there is an exact cardinality match."""
    result = []
    for op, pattern in VERBS.items():
        matches = [m for m in re.finditer(pattern, span) if m.start() >= start]
        candidates = [a for a in actions if a.node["op"] == op]
        if len(matches) == len(candidates):
            result.extend((m.start(), m.end(), a) for m, a in zip(matches, candidates))
    return sorted(result, key=lambda item: item[0])


def _selector_constraints(span, target, path, warnings):
    if not isinstance(target, Mapping) or "pick" not in target:
        return
    exclusions = target.get("exclude", [])
    if re.search(r"\bother\b|\bexcept (?:this|itself|the source)\b", span):
        if "SELF" not in exclusions:
            warnings.append(f"{path}: EXCLUSION_SOURCE: source exclusion is missing")
    terms = re.findall(r"\bnon[ -]([a-z]+)\b|\bexcept (?:for )?([a-z]+)\b", span)
    for pair in terms:
        term = next(t for t in pair if t).upper()
        if term in ("THIS", "ITSELF", "THE"):
            continue
        if term.endswith("S") and term[:-1] in CLASSES | RACES:
            term = term[:-1]
        key = "card_class" if term in CLASSES else "race" if term in RACES else None
        value = "MECHANICAL" if term == "MECH" else term
        def matches(pred):
            # A class exclusion is not a race with the same arbitrary string.
            return (key is not None and str(pred.get(key, "")).upper() == value)
        if any(matches(p) for p in target.get("where", [])) or not any(
                isinstance(e, Mapping) and any(matches(p) for p in e.get("where", []))
                and e.get("pick") == "ALL" and e.get("type") == target.get("type")
                and e.get("side") in (target.get("side"), "ANY")
                and e.get("zone", "PLAY") == target.get("zone", "PLAY") for e in exclusions):
            warnings.append(f"{path}: EXCLUSION_PREDICATE: exclusion for {term} is missing/inverted or in another zone")
    if re.search(r"\ball\b[^.;]*\bminions\b", span) and not re.search(
            r"\b(?:enemy|enemies|friendly|your|opponent)\b", span):
        if target.get("side") != "ANY":
            warnings.append(f"{path}: AREA_SIDE: unqualified all minions includes both sides")


def lint_strict(doc):
    warnings = []
    for index, ability in enumerate(doc.get("abilities", [])):
        path = f"abilities[{index}]"
        span = normalise_text(ability.get("span", "")).lower()
        guards = tuple((ability[k], True) for k in ("condition", "while") if k in ability)
        actions = list(_actions(ability.get("effect", {}), guards))
        start = span.find(",") + 1 if ability.get("kind") == "trigger" else 0
        paired = _clauses(span, actions, start)
        target = ability.get("target", {})
        entity = {"ref": target["bind"]} if target else "SELF"

        # Prefix conditions restrict the following clause, not earlier steps. A
        # full stop resets scope; commas inside 'If X, Y and Z' do not reset it.
        for position, end, action in paired:
            sentence_start = max(span.rfind(".", 0, position), span.rfind(";", 0, position)) + 1
            prefix = span[sentence_start:position]
            sentence_end = re.search(r"[.;]", span[end:])
            tail_end = end + sentence_end.start() if sentence_end else len(span)
            tail = span[end:tail_end]
            cue = re.search(r"\b(?:if|unless|while)\b", prefix)
            postfix = re.search(r"\b(?:if|unless|while)\b", tail)
            phrase = prefix[cue.start():] if cue else tail[postfix.start():] if postfix else ""
            if phrase:
                _condition_check(phrase, action, entity, warnings, path)

        if ability.get("kind") == "aura" and re.search(r"\b(?:while|if|unless)\b", span) and "while" not in ability:
            warnings.append(f"{path}: CONDITION_SCOPE: conditional aura text needs a while condition")
        elif ability.get("kind") == "aura" and re.search(r"\bwhile\b", span):
            _condition_check(span, Action(ability["modifier"], guards), "SELF", warnings, path)

        event = ability.get("event", {})
        if ability.get("kind") == "trigger":
            prefix = span.split(",", 1)[0]
            if "unknown" not in event and re.search(r"\b(?:surviv\w*|while|unless|if)\b", prefix):
                for action in actions:
                    _condition_check(prefix, action, "SELF", warnings, path)
            for word, timing in (("after", "AFTER"), ("whenever", "WHENEVER"), ("when", "WHEN")):
                if re.match(rf"(?:secret: )?{word}\b", span) and ability.get("timing") != timing:
                    warnings.append(f"{path}: EVENT_TIMING: {word} requires {timing}")
            if re.search(r"\b(?:start|beginning) of\b", prefix) and event.get("type") == "TURN_END":
                warnings.append(f"{path}: TURN_PHASE: start of turn is not TURN_END")
            if re.search(r"\bend of\b", prefix) and event.get("type") not in ("TURN_END", None):
                warnings.append(f"{path}: TURN_PHASE: end of turn needs TURN_END or an explicit unknown event")
            source_attack = re.search(r"\b(?:this|it|this minion) attacks\b", prefix)
            if source_attack and event.get("type") == "HERO_ATTACK":
                warnings.append(f"{path}: EVENT_SUBJECT: source minion attack is not HERO_ATTACK")
            if re.search(r"\byour hero attacks\b", prefix) and event.get("type") != "HERO_ATTACK":
                warnings.append(f"{path}: EVENT_SUBJECT: hero attack needs the explicit HERO_ATTACK contract")
            if re.search(r"\byour hero attacks\b", prefix) and event.get("type") == "HERO_ATTACK" and event.get("player") != "SELF":
                warnings.append(f"{path}: EVENT_OWNER: your hero requires player SELF")
            if re.search(r"\bfriendly minion is attacked\b", prefix):
                defender = event.get("defender", {})
                if event.get("type") != "ATTACK_DECLARED" or not isinstance(defender, Mapping) or (
                        defender.get("type"), defender.get("side")) != ("MINION", "FRIENDLY"):
                    warnings.append(f"{path}: EVENT_DEFENDER: friendly attacked minion must be the defender")
            if re.search(r"\battacks (?:a|an|another) minion\b", prefix) and event.get("type") == "ATTACK_DECLARED":
                defender = event.get("defender", {})
                if not isinstance(defender, Mapping) or defender.get("type") != "MINION":
                    warnings.append(f"{path}: EVENT_DEFENDER: attack must be against a minion")
            if event.get("type") == "ATTACK_DECLARED" and "subject" in event:
                # v0.1 never defines this role. An explicit CORE decision is an
                # honest PARTIAL; do not silently promote subject to attacker.
                if not _core_decision(doc):
                    warnings.append(f"{path}: EVENT_ROLE: ATTACK_DECLARED.subject has undefined semantics in v0.1")

        for position, end, action in paired:
            # Operand checks use the clause attached to the particular verb.
            stop = re.search(r"[.;]", span[end:])
            clause = span[position:end + stop.start()] if stop else span[position:]
            _selector_constraints(clause, action.node.get("to"), path, warnings)
            if action.node["op"] == "SHUFFLE_INTO_DECK":
                if re.search(r"\b(?:top|bottom)\b[^.;]*\bdeck\b", clause):
                    warnings.append(f"{path}: DECK_POSITION: v0.1 shuffle cannot express top/bottom insertion")
                elif not re.search(r"\bshuffle\b", clause):
                    warnings.append(f"{path}: DECK_POSITION: shuffle lacks textual random insertion evidence")
        for node in _nodes(ability):
            if node.get("op") == "ADD_TO_HAND":
                source = node.get("what", {}).get("from_zone", {})
                if source.get("zone", "PLAY") == "PLAY" and source and not _core_decision(doc):
                    warnings.append(f"{path}: RETURN_CONTRACT: PLAY-to-HAND reset semantics need an explicit CORE decision in v0.1")
                if re.search(r"\breturn (?:a|an|one) (?:random )?(?:friendly )?minion to your hand\b", span):
                    if (source.get("type"), source.get("zone", "PLAY"), source.get("n", 1), node.get("player")) != (
                            "MINION", "PLAY", 1, "SELF"):
                        warnings.append(f"{path}: RETURN_SOURCE: one battlefield minion must move into your hand")
            if node.get("op") in ("ENCHANT", "ADD_PLAYER_EFFECT"):
                if re.search(r"\bnext turn\b", span):
                    warnings.append(f"{path}: WINDOW_NEXT: v0.1 duration cannot encode the next player's turn")
                elif re.search(r"\bthis turn\b", span) and node.get("duration") != "THIS_TURN":
                    warnings.append(f"{path}: WINDOW_THIS: this-turn modifier needs THIS_TURN duration")
                elif node.get("duration") == "THIS_TURN" and not re.search(r"\bthis turn\b|\bend of (?:the |your )?turn\b", span):
                    warnings.append(f"{path}: WINDOW_EVIDENCE: THIS_TURN lacks a matching textual window")
    return warnings
