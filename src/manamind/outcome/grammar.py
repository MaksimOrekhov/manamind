"""A deliberately small grammar over card rules text.

Every sentence must match one reviewed template exactly; anything else becomes an ``OPAQUE``
clause that the forecaster reports as an unknown. No sentence is matched by a card ID, and no
fragment of a sentence is ignored: extra words make the whole sentence opaque.

Numbers carry the text markers ``$`` (damage, scaled by Spell Damage) and ``#`` (healing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

KEYWORD_FLAGS = {
    "taunt": "taunt", "divine shield": "divine_shield", "lifesteal": "lifesteal", "rush": "rush",
    "charge": "charge", "windfury": "windfury", "stealth": "stealth", "poisonous": "poisonous",
    "reborn": "reborn",
}
# Words that are keywords but whose rules the forecaster has not reviewed.
UNREVIEWED_KEYWORDS = frozenset({
    "rewind", "imbue", "kindred", "dark gift", "herald", "fabled", "shatter", "dormant", "elusive",
    "silence", "freeze", "overload", "tradeable", "echo", "twinspell", "magnetic", "colossal",
})

_SELECTORS = {
    "a minion": ("CHOSEN", "MINION", "ANY"),
    "an enemy minion": ("CHOSEN", "MINION", "ENEMY"),
    "a friendly minion": ("CHOSEN", "MINION", "FRIENDLY"),
    "a character": ("CHOSEN", "CHARACTER", "ANY"),
    "an enemy character": ("CHOSEN", "CHARACTER", "ENEMY"),
    "a friendly character": ("CHOSEN", "CHARACTER", "FRIENDLY"),
    "an enemy": ("CHOSEN", "CHARACTER", "ENEMY"),
    "all minions": ("ALL", "MINION", "ANY"),
    "all enemy minions": ("ALL", "MINION", "ENEMY"),
    "all friendly minions": ("ALL", "MINION", "FRIENDLY"),
    "your minions": ("ALL", "MINION", "FRIENDLY"),
    "all characters": ("ALL", "CHARACTER", "ANY"),
    "all enemy characters": ("ALL", "CHARACTER", "ENEMY"),
    "all friendly characters": ("ALL", "CHARACTER", "FRIENDLY"),
    "your hero": ("FIXED", "HERO", "FRIENDLY"),
    "the enemy hero": ("FIXED", "HERO", "ENEMY"),
}
_SEL = "|".join(re.escape(name) for name in sorted(_SELECTORS, key=len, reverse=True))
_KW = "|".join(re.escape(name) for name in sorted(KEYWORD_FLAGS, key=len, reverse=True))
_NUM = r"[\$#]?(?P<n>\d+)"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DAMAGE", re.compile(rf"deal {_NUM} damage(?: to (?P<sel>{_SEL}))?")),
    # One reviewed compound shape. "it" is the damaged target and nothing else; no free pronoun resolution exists,
    # so "give it +N attack" elsewhere (a weapon, a minion that survived damage) stays an unparsed sentence.
    ("DAMAGE_BUFF", re.compile(
        rf"deal {_NUM} damage to (?P<sel>a minion|an enemy minion|a friendly minion) and give it \+(?P<a>\d+) attack")),
    ("HEAL", re.compile(rf"restore {_NUM} health(?: to (?P<sel>{_SEL}))?")),
    ("BUFF", re.compile(
        rf"give (?P<sel>{_SEL}) \+(?P<a>\d+)/\+(?P<h>\d+)(?P<kw>(?:(?:, and|,| and) (?:{_KW}))*)")),
    ("BUFF", re.compile(rf"give (?P<sel>{_SEL}) \+(?P<a>\d+) attack(?P<kw>(?:(?:, and|,| and) (?:{_KW}))*)")),
    ("BUFF", re.compile(rf"give (?P<sel>{_SEL}) \+(?P<h>\d+) health(?P<kw>(?:(?:, and|,| and) (?:{_KW}))*)")),
    ("GRANT", re.compile(rf"give (?P<sel>{_SEL}) (?P<kw>(?:{_KW})(?:(?:, and|,| and) (?:{_KW}))*)")),
    ("FREEZE", re.compile(r"freeze (?P<sel>an enemy)")),
    ("DESTROY_DAMAGED", re.compile(r"destroy a damaged enemy minion")),
    ("DESTROY", re.compile(
        r"destroy (?P<sel>a minion|all minions|all enemy minions|all friendly minions)"
        r"(?: with (?P<cmp_n>\d+) or (?P<cmp>more|less) attack)?")),
    ("DESTROY_HIGHEST", re.compile(r"destroy the highest attack enemy minion")),
    ("ARMOR", re.compile(rf"gain {_NUM} armor")),
    ("HERO_ATTACK", re.compile(r"give your hero \+(?P<n>\d+) attack this turn")),
    ("MANA_TEMP", re.compile(r"gain (?P<n>\d+) mana crystals? this turn only")),
)
_COST_ONLY = re.compile(r"(?:kindred: )?(?:this )?costs \(\d+\)(?: less)?(?: if .+)?")
_TRIGGER_START = re.compile(
    r"(?:whenever|after|at the (?:start|end) of|deathrattle:|spellburst:|frenzy:|overkill:|"
    r"honorable kill:|inspire:)", re.I)
_CONDITIONAL = re.compile(r"if it (?P<cond>dies|survives), (?P<rest>.+)")
_FREEZE_FORM = re.compile(r"\b(?:freeze|freezes|freezing|frozen|froze)\b")
_PLAY_LABEL = re.compile(r"(?:battlecry|combo|outcast|choose one)", re.I)
# A sentence that starts like this continues the Battlecry/trigger paragraph before it. Line breaks cannot
# tell a continuation from a new rule (layout wraps after periods), but static rules read descriptively
# ('Has +6 Attack...', 'Your other minions...'), so only effect verbs and 'if/then' count as continuation.
_CONTINUATION = re.compile(
    r"(?:deal|summon|draw|give|restore|gain|destroy|add|get|discover|shuffle|equip|return|silence|freeze|take|swap|"
    r"transform|copy|set|trigger|replace|reduce|increase|change|choose|cast|play|put|reveal|remove|steal|control|"
    r"resurrect|spend|pay|lose|attack|repeat|if|then|otherwise|do it|it |they |that |each )", re.I)
_KEYWORD_LINES = frozenset({*KEYWORD_FLAGS, "prepare", *UNREVIEWED_KEYWORDS})


@dataclass(frozen=True, slots=True)
class Selector:
    mode: str        # CHOSEN | ALL | FIXED
    kinds: str       # MINION | CHARACTER | HERO
    allegiance: str  # ANY | ENEMY | FRIENDLY


@dataclass(frozen=True, slots=True)
class Clause:
    kind: str
    text: str = ""
    selector: Selector | None = None
    amount: int = 0
    attack: int = 0
    health: int = 0
    keywords: tuple[str, ...] = ()
    attack_filter: tuple[str, int] | None = None   # ("GE" | "LE", n)
    condition: str | None = None                   # IF_DIES | IF_SURVIVES
    inner: "Clause | None" = None
    category: str = ""                              # opaque clause category


@dataclass(frozen=True, slots=True)
class ParsedText:
    clauses: tuple[Clause, ...]
    trigger_sentences: tuple[str, ...]


def _is_keyword_list(line: str) -> bool:
    words = [part.strip() for part in re.split(r",| and ", line.lower().rstrip(".")) if part.strip()]
    return bool(words) and all(word in _KEYWORD_LINES for word in words)


def normalise(text: str) -> list[str]:
    """Strip markup and return the sentences of a card text.

    A line break ends a sentence only after a period/colon or a bare keyword line; elsewhere it is layout
    wrapping ('Deal 3 damage / to a minion'). Whether a later sentence belongs to the same Battlecry or
    trigger is decided by its content (see ``_CONTINUATION``), not by its line.
    """
    plain = re.sub(r"<[^>]+>", "", text).replace("\xa0", " ").strip().removeprefix("[x]")
    lines = [line.strip() for line in plain.split("\n") if line.strip()]
    joined = ""
    for index, line in enumerate(lines):
        joined += line
        if index + 1 < len(lines):
            ends = line.endswith((".", ":")) or _is_keyword_list(line)
            joined += ". " if ends and not line.endswith(".") else " "
    joined = re.sub(r"\s+", " ", joined).strip()
    sentences = re.split(r"(?<=\.)\s+", joined)
    return [sentence.strip().rstrip(".").strip() for sentence in sentences if sentence.strip(". ")]


def _selector(name: str | None, default: Selector) -> Selector:
    return default if name is None else Selector(*_SELECTORS[name])


def _keywords(tail: str | None) -> tuple[str, ...]:
    return tuple(KEYWORD_FLAGS[word] for word in re.findall(_KW, tail or ""))


def _effect(sentence: str) -> Clause | None:
    lowered = sentence.lower()
    for kind, pattern in _PATTERNS:
        match = pattern.fullmatch(lowered)
        if match is None:
            continue
        groups = match.groupdict()
        number = int(groups["n"]) if groups.get("n") else 0
        if kind in {"DAMAGE", "HEAL"}:
            chosen_any = Selector("CHOSEN", "CHARACTER", "ANY")
            return Clause(kind, sentence, _selector(groups.get("sel"), chosen_any), amount=number)
        if kind == "DAMAGE_BUFF":
            return Clause(kind, sentence, _selector(groups["sel"], None), amount=number, attack=int(groups["a"]))
        if kind == "BUFF":
            return Clause(kind, sentence, _selector(groups["sel"], None), attack=int(groups.get("a") or 0),
                          health=int(groups.get("h") or 0), keywords=_keywords(groups.get("kw")))
        if kind == "GRANT":
            return Clause(kind, sentence, _selector(groups["sel"], None), keywords=_keywords(groups["kw"]))
        if kind == "FREEZE":
            return Clause(kind, sentence, _selector(groups["sel"], None))
        if kind == "DESTROY_DAMAGED":
            return Clause(kind, sentence, Selector("CHOSEN", "MINION", "ENEMY"))
        if kind == "DESTROY":
            attack_filter = None
            if groups.get("cmp"):
                attack_filter = ("GE" if groups["cmp"] == "more" else "LE", int(groups["cmp_n"]))
            return Clause(kind, sentence, _selector(groups["sel"], None), attack_filter=attack_filter)
        if kind == "DESTROY_HIGHEST":
            return Clause(kind, sentence, Selector("ALL", "MINION", "ENEMY"))
        return Clause(kind, sentence, amount=number)
    return None


def _opaque(sentence: str) -> Clause:
    lowered = sentence.lower()
    if lowered in UNREVIEWED_KEYWORDS or lowered.split(":")[0] in UNREVIEWED_KEYWORDS:
        category = "KEYWORD_UNDEFINED"
    elif "random" in lowered:
        category = "RANDOM_OUTCOME"
    else:
        category = "UNPARSED_CLAUSE"
    return Clause("OPAQUE", sentence, category=category)


def _sentence(sentence: str) -> tuple[Clause, bool]:
    """Return the clause for one sentence and whether it is a trigger sentence."""
    lowered = sentence.lower()
    if lowered.startswith("battlecry:"):
        return _sentence(sentence.split(":", 1)[1].strip())
    if _TRIGGER_START.match(lowered):
        return Clause("TRIGGER", sentence), True
    if _COST_ONLY.fullmatch(lowered):
        return Clause("COST_ONLY", sentence), False
    if lowered == "prepare":
        return Clause("PREPARE", sentence), False
    words = [part.strip() for part in re.split(r",| and ", lowered) if part.strip()]
    if words and all(word in KEYWORD_FLAGS for word in words):
        return Clause("KEYWORDS", sentence, keywords=tuple(KEYWORD_FLAGS[word] for word in words)), False
    conditional = _CONDITIONAL.fullmatch(lowered)
    if conditional is not None:
        rest = sentence[sentence.index(",") + 1:].strip()
        inner = _effect(rest) or _opaque(rest)
        return Clause("COND", sentence, condition=f"IF_{conditional['cond'].upper()}", inner=inner), False
    return (_effect(sentence) or _opaque(sentence)), False


@lru_cache(maxsize=4096)
def parse_text(text: str) -> ParsedText:
    clauses: list[Clause] = []
    triggers: list[str] = []
    in_trigger = False
    for sentence in normalise(text):
        clause, is_trigger = _sentence(sentence)
        if is_trigger:
            triggers.append(sentence)
            in_trigger = True
        elif clause.kind in ("KEYWORDS", "COST_ONLY", "PREPARE") or _PLAY_LABEL.match(sentence):
            in_trigger = False
            clauses.append(clause)
        elif in_trigger and _CONTINUATION.match(sentence):
            triggers.append(sentence)               # a further sentence of the same trigger paragraph
        else:
            clauses.append(clause)
    return ParsedText(tuple(clauses), tuple(triggers))


def board_profile(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the text of a card already in play into (trigger sentences, static sentences).

    Play-time labels (Battlecry, Combo, Outcast) and bare keywords describe nothing that can still
    happen on the board; every other non-trigger sentence is a static rule the forecaster does not
    understand, so the caller must treat it as an unknown.
    """
    triggers: list[str] = []
    statics: list[str] = []
    scope = ""                                      # "play" or "trigger": the paragraph being read
    for sentence in normalise(text):
        lowered = sentence.lower()
        words = [part.strip() for part in re.split(r",| and ", lowered) if part.strip()]
        keyword_only = lowered == "prepare" or _COST_ONLY.fullmatch(lowered) or (
            words and all(word in KEYWORD_FLAGS for word in words)) or _is_keyword_list(sentence)
        if keyword_only:
            scope = ""
        elif _PLAY_LABEL.match(lowered):
            scope = "play"
        elif _TRIGGER_START.match(lowered):
            triggers.append(sentence)
            scope = "trigger"
        elif scope and _CONTINUATION.match(sentence):
            if scope == "trigger":
                triggers.append(sentence)
        else:
            statics.append(sentence)
    return tuple(triggers), tuple(statics)


_BODY_WORDS = re.compile(
    r"\b(minions?|characters?|attack|health|taunt|rush|charge|divine shield|windfury|stealth|lifesteal|poisonous|"
    r"reborn|immune|elusive|frozen|dormant|silence[ds]?|can't|cannot)\b|[+-]\d", re.IGNORECASE)


def affects_minion_body(sentence: str) -> bool:
    """Could this static sentence change the Attack, Health or keywords of a minion that enters play?

    Words about stats, keywords or minions say yes. A sentence about cost, Hero Powers, Corpses or other resources
    cannot change the body, and flagging it would only hide the real cases.
    """
    return bool(_BODY_WORDS.search(sentence))


def trigger_events(sentence: str) -> frozenset[str]:
    """Event classes that can fire one trigger sentence; ``ANY`` when the condition is unreadable."""
    lowered = sentence.lower()
    labelled = {"deathrattle:": "DEATH_SELF", "spellburst:": "SPELL_CAST", "frenzy:": "DAMAGE_SELF",
                "overkill:": "ATTACK_SELF", "honorable kill:": "ATTACK_SELF", "inspire:": "HERO_POWER_USED"}
    for label, event in labelled.items():
        if lowered.startswith(label):
            return frozenset({event})
    condition = lowered.split(",", 1)[0]
    found: set[str] = set()
    if "end of" in condition and "turn" in condition:
        found.add("TURN_END")
    if "start of" in condition and "turn" in condition:
        found.add("TURN_START")
    if "cast" in condition or "spell" in condition:
        found.add("SPELL_CAST")
    if "play" in condition:
        found |= {"MINION_PLAYED", "SUMMON"}
        if "minion" not in condition:
            found |= {"SPELL_CAST", "HERO_POWER_USED"}
    if "summon" in condition:
        found |= {"SUMMON", "MINION_PLAYED"}
    if "hero power" in condition:
        found.add("HERO_POWER_USED")
    if re.search(r"\bdie[s]?\b", condition):
        found.add("DEATH")
    if "attack" in condition:
        found |= {"ATTACK", "BUFF"}
    if "damage" in condition or "survives" in condition or "divine shield" in condition:
        found.add("DAMAGE")
    if "restore" in condition or "heal" in condition:
        found.add("HEAL")
    if "armor" in condition:
        found.add("ARMOR_GAIN")
    if "gain" in condition or "stats" in condition or "buff" in condition:
        found |= {"BUFF", "KEYWORD_GAIN", "ARMOR_GAIN"}
    if "mana" in condition:
        found.add("MANA_SPENT")
    if _FREEZE_FORM.search(condition):
        found.add("FREEZE")
    if re.search(r"\b(draw|draws|discard|shuffle)\b", condition) and not found:
        found.add("OTHER")                      # none of the supported actions draws or discards
    return frozenset(found) if found else frozenset({"ANY"})
