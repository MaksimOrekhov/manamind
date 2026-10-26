"""Text consistency checks for the Card IR v0.2 constructs (no game execution).

Like the v0.1 lints these read the same English as the author: they catch contradictions between an ability's span and
its IR in narrow, unambiguous templates, both directions where the template allows it. A clean result is not proof.
Each warning starts with a code; ``SUPERSEDED_V01`` lists the v0.1 strict-lint codes that v0.2 replaces (the v0.1
warning said 'v0.1 cannot express this'; v0.2 can, so the replacement checks that it is expressed correctly).
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from manamind.card_ir.semantic_lint import NUMBER, VERBS, WORDS, nodes
from manamind.card_ir.strict_lint import _actions
from manamind.card_ir.validate import normalise_text

SUPERSEDED_V01 = {
    "WINDOW_NEXT": "WINDOW_NEXT_V02 (next turn <-> next_turn duration and owner)",
    "DECK_POSITION": "DECK_POSITION_V02 (top/bottom/shuffle <-> position)",
    "RETURN_CONTRACT": "validator: move:PLAY_TO_HAND needs R_RETURN_TO_HAND and an acknowledged R_RETURN_FULL_HAND",
    "EVENT_ROLE": "validator: ATTACK_DECLARED takes attacker/defender roles; subject is rejected",
}
_TURNS = re.compile(rf"\b({NUMBER})[ -]turns?\b")
ORDER_VERBS = {**VERBS, "FREEZE": r"\bfreeze\b"}


def _linear_steps(effect):
    """Flatten only unconditional sequences; never guess order across guards or loops."""
    if not isinstance(effect, Mapping):
        return None
    if "op" in effect:
        return [effect]
    if "seq" not in effect:
        return None
    steps = []
    for child in effect["seq"]:
        part = _linear_steps(child)
        if part is None:
            return None
        steps.extend(part)
    return steps


def _clause_targets(ability, span):
    """Associate a unique verb with its own sentence and resolve the play-target handle.

    Deliberately narrow English templates. A neighbouring enemy word must not
    justify an enemy-only *damage* target. No card IDs or names are consulted.
    """
    actions = list(_actions(ability.get("effect", {})))
    for op in ("DEAL_DAMAGE", "FREEZE"):
        matches = list(re.finditer(ORDER_VERBS[op], span))
        candidates = [a.node for a in actions if a.node["op"] == op]
        if len(matches) != 1 or len(candidates) != 1:
            continue
        start = matches[0].start()
        stop = re.search(r"[.;]", span[start:])
        clause = span[start:start + stop.start()] if stop else span[start:]
        expected = None
        if op == "DEAL_DAMAGE":
            phrase = re.fullmatch(r"deal\s+[$#]?\d+\s+damage(?:\s+to\s+(?:a|an)\s+(?:damaged\s+)?(minion|hero|character))?", clause)
            if phrase:
                expected = ("CHOSEN", (phrase[1] or "character").upper(), "ANY", "PLAY")
        elif re.fullmatch(r"freeze all enemy minions", clause):
            expected = ("ALL", "MINION", "ENEMY", "PLAY")
        if expected is None:
            continue
        target = candidates[0].get("to")
        binding = ability.get("target", {})
        if isinstance(target, Mapping) and target == {"ref": binding.get("bind")}:
            target = binding.get("choose")
        # CHOSEN constrains a play target; automatic damage without one is outside
        # this template. FREEZE's explicit area clause always constrains its selector.
        if op == "DEAL_DAMAGE" and not binding:
            continue
        actual = ((target.get("pick"), target.get("type"), target.get("side"), target.get("zone", "PLAY"))
                  if isinstance(target, Mapping) else None)
        if actual != expected:
            yield f"CLAUSE_TARGET: {op} clause {clause!r} requires {expected}, got {actual}"


def _integer(text):
    return int(text) if text.isdigit() else WORDS[text]


def superseded(warning: str) -> bool:
    return any(f": {code}:" in warning for code in SUPERSEDED_V01)


def _repeat_split(tree):
    """A repeat whose step is 1 damage to a RANDOM pick: the R_RANDOM_SPLIT encoding."""
    for node in tree:
        step = node.get("do") if "repeat" in node else None
        if isinstance(step, Mapping) and step.get("op") == "DEAL_DAMAGE" and step.get("amount") == 1 and \
                isinstance(step.get("to"), Mapping) and step["to"].get("pick") == "RANDOM":
            return True
    return False


def lint_v02(doc: Mapping) -> list[str]:
    warnings = []
    for index, ability in enumerate(doc.get("abilities", [])):
        path = f"abilities[{index}]"
        span = normalise_text(ability.get("span", "")).lower()
        tree = list(nodes(ability))
        ops = [n for n in tree if "op" in n]

        def warn(code, message):
            warnings.append(f"{path}: {code}: {message}")

        warnings.extend(f"{path}: {message}" for message in _clause_targets(ability, span))

        # FREEZE: the verb and the operation in both directions.
        has_freeze = any(n["op"] == "FREEZE" for n in ops)
        if re.search(r"\bfreeze\b", span) and not has_freeze:
            warn("FREEZE_TEXT", "'freeze' in the text needs a FREEZE operation")
        if has_freeze and not re.search(r"\bfreeze\b", span):
            warn("FREEZE_TEXT", "FREEZE needs 'freeze' in the text")
        # Straight-line order with FREEZE (the v0.1 semantic lint skips sequences containing an op it does not know).
        effect = ability.get("effect", {})
        steps = _linear_steps(effect) or []
        if has_freeze and steps and all(isinstance(s, Mapping) and s.get("op") in ORDER_VERBS for s in steps):
            positions = [[m.start() for m in re.finditer(ORDER_VERBS[s["op"]], span)] for s in steps]
            if all(len(p) == 1 for p in positions) and [p[0] for p in positions] != sorted(p[0] for p in positions):
                warn("ORDER_V02", "straight-line operations differ from textual verb order")

        windowed = [n for n in ops if n["op"] in ("ENCHANT", "ADD_PLAYER_EFFECT")]
        for node in windowed:
            duration = node.get("duration")
            next_turn = duration.get("next_turn") if isinstance(duration, Mapping) else None
            if re.search(r"\bnext turn\b", span):
                owner = ("SELF" if re.search(r"\byour next turn\b", span) else
                         "OPPONENT" if re.search(r"\bopponent'?s next turn\b", span) else
                         node.get("player") if node["op"] == "ADD_PLAYER_EFFECT" else None)
                if next_turn is None:
                    warn("WINDOW_NEXT_V02", "next-turn text needs a next_turn duration")
                elif owner is not None and next_turn != owner:
                    warn("WINDOW_NEXT_V02", f"next turn belongs to {owner}, not {next_turn}")
            elif next_turn is not None:
                warn("WINDOW_NEXT_V02", "a next_turn duration needs 'next turn' in the text")
            game = re.search(r"\bthis game\b|\brest of the game\b", span)
            counted = any(isinstance(n.get("counter"), Mapping) and n["counter"].get("scope") == "THIS_GAME" for n in tree)
            if duration == "THIS_GAME" and not game:
                warn("WINDOW_GAME", "THIS_GAME needs 'this game' or 'rest of the game' in the text")
            if game and not counted and duration != "THIS_GAME":
                warn("WINDOW_GAME", "'this game' modifier needs THIS_GAME duration")

        # Delayed start / N turns: the number of turns in the text.
        phrases = [_integer(m.group(1)) for m in _TURNS.finditer(span)]
        for node in (n for n in ops if n["op"] == "ADD_PLAYER_EFFECT"):
            start = node.get("starts_after")
            duration = node.get("duration")
            counts = {start.get("turn_starts")} if isinstance(start, Mapping) else set()
            counts |= {duration.get("turns")} if isinstance(duration, Mapping) and "turns" in duration else set()
            if isinstance(start, Mapping) and start.get("turn_starts") not in phrases:
                warn("DELAY_COUNT", f"starts_after {start.get('turn_starts')} turns does not match the text {phrases}")
            if isinstance(start, Mapping) and start.get("player") != node.get("player") and \
                    not re.search(r"\b(?:opponent|enemy)\b", span):
                warn("DELAY_OWNER", "counting another player's turns needs 'opponent' in the text")
            if phrases and not counts & set(phrases):
                warn("DELAY_COUNT", f"'{phrases[0]} turn' in the text needs starts_after or a turns duration")
            # 'your next spell' limits uses; 'next turn' is a window, not a use limit.
            limited = re.search(r"\bnext\b(?! turn)", span)
            if node.get("uses") == "ALL_MATCHING" and limited:
                warn("USES_SCOPE", "'next' in the text limits uses; ALL_MATCHING applies to every matching card")
            if isinstance(node.get("uses"), int) and not limited:
                warn("USES_SCOPE", "integer uses need 'next' in the text")

        # Deck insertion position and count.
        shuffles = [n for n in ops if n["op"] == "SHUFFLE_INTO_DECK"]
        for node in shuffles:
            position = node.get("position", "RANDOM")
            wanted = ("BOTTOM" if re.search(r"\bbottom of\b[^.;]*\bdeck\b", span) else
                      "TOP" if re.search(r"\btop of\b[^.;]*\bdeck\b", span) else
                      "RANDOM" if re.search(r"\bshuffle\b", span) else None)
            if wanted is None:
                warn("DECK_POSITION_V02", "deck insertion lacks 'shuffle', 'top of' or 'bottom of' in the text")
            elif position != wanted:
                warn("DECK_POSITION_V02", f"text inserts {wanted}, IR inserts {position}")
        count_words = list(re.finditer(rf"\b(?:put|shuffle)\s+({NUMBER}|a|an)\b", span))
        if len(count_words) == len(shuffles) == 1:
            word = count_words[0].group(1)
            expected = 1 if word in ("a", "an") else _integer(word)
            if shuffles[0].get("count", 1) != expected:
                warn("DECK_COUNT", f"'{count_words[0].group()}' requires count={expected}")

        # Attack roles: the source minion as attacker; the attacked character as defender.
        event = ability.get("event", {}) if ability.get("kind") == "trigger" else {}
        prefix = span.split(",", 1)[0]
        if isinstance(event, Mapping) and event.get("type") == "ATTACK_DECLARED":
            source_attacks = re.search(r"\b(?:this|it|this minion) attacks\b", prefix)
            if source_attacks and event.get("attacker") != "SELF":
                warn("ATTACK_ROLE", "'this attacks' needs attacker SELF")
            if event.get("attacker") == "SELF" and not source_attacks:
                warn("ATTACK_ROLE", "attacker SELF needs 'this attacks' in the text")
            if re.search(r"\bis attacked\b", prefix) and "defender" not in event:
                warn("ATTACK_ROLE", "'is attacked' needs a defender role")

        # Split damage: the encoding and the reading.
        if re.search(r"\bsplit\b", span) and not _repeat_split(tree):
            warn("SPLIT_ENCODING", "split damage is a repeat of 1 damage to a RANDOM pick")

        # Cost direction and multiplication.
        increases = any("increase" in n or (isinstance(n.get("cost"), Mapping) and "increase" in n["cost"]) for n in tree)
        if re.search(r"\bcosts? \(\d+\) more\b", span) and not increases:
            warn("COST_SIGN", "'costs (N) more' needs increase")
        if increases and not re.search(r"\(\d+\) more\b", span):
            warn("COST_SIGN", "increase needs '(N) more' in the text")
        has_mul = any("mul" in n for n in tree)
        if re.search(r"\(\d+\) (?:less|more) for each\b", span) and not has_mul:
            warn("MULTIPLY", "'(N) less/more for each' needs mul")
        if has_mul and not re.search(r"\bfor (?:each|every)\b", span):
            warn("MULTIPLY", "mul needs 'for each' in the text")

        # Damage-amount counters: present when the text counts damage dealt; owner, source filter and scope.
        damage_counted = any(isinstance(n.get("counter"), Mapping) and n["counter"].get("event") == "DAMAGE_DEALT"
                             for n in tree)
        if re.search(r"\bdamage (?:you(?:'ve)?|your \w+) dealt\b", span) and not damage_counted:
            warn("DAMAGE_COUNTER", "'damage you dealt' needs a DAMAGE_DEALT counter")
        for node in tree:
            counter = node.get("counter")
            if not (isinstance(counter, Mapping) and counter.get("event") == "DAMAGE_DEALT"):
                continue
            spells = any(p.get("card_type") == "SPELL" for p in counter.get("source", []) if isinstance(p, Mapping))
            if bool(re.search(r"\bwith spells\b", span)) != spells:
                warn("DAMAGE_COUNTER", "'with spells' <-> source card_type SPELL")
            if re.search(r"\byou(?:'ve)? dealt\b", span) and counter.get("player") != "SELF":
                warn("DAMAGE_COUNTER", "'you dealt' needs player SELF")
            scope = "THIS_TURN" if re.search(r"\bthis turn\b", span) else "THIS_GAME" if re.search(r"\bthis game\b", span) else None
            if scope and counter.get("scope") != scope:
                warn("DAMAGE_COUNTER", f"text counts {scope}")

        # 'Return X to hand' moves X; a copy or a fixed card is a different card.
        if re.search(r"\breturn\b", span):
            for node in (n for n in ops if n["op"] == "ADD_TO_HAND"):
                if not (isinstance(node.get("what"), Mapping) and "from_zone" in node["what"]):
                    warn("RETURN_MOVE", "'return' moves an existing card: ADD_TO_HAND needs from_zone")

        # Survival predicate needs survival/death wording.
        if any(isinstance(n.get("alive"), bool) for n in tree) and not re.search(r"\bsurviv\w*|\b(?:dies|die|died)\b", span):
            warn("SURVIVE_TEXT", "alive needs 'survives' or 'dies' in the text")
    return warnings
