"""Structural validation of Card IR v0.1 declarations and extraction of the vocabulary elements they use.

The checks are deterministic and target the errors that look plausible on simple cards:

* closed vocabulary: unknown keys, operations, enums and node shapes are rejected, and every node maps to an element
  of ``vocabulary.ELEMENTS`` (a shape whose element is not in the vocabulary is rejected too);
* binding: every ``ref``/``var`` is bound earlier in the same resolution; every ``dep`` names a declared dependency;
* text accountability: every ability, keyword, reminder and unexpressed span is an exact substring of the normalised
  card text, the spans together cover every word of it, and every number in a span is matched by a number in the IR
  under that span with the same ``$``/``#`` mark (a mark is never invented or dropped);
* honesty: random pools, ambiguous token IDs and name references need typed dependencies, holes (``unknown``) must point
  at a rule dependency, mechanics without a rule source need a KEYWORD_RULE dependency, and the declared status must
  equal the status implied by the gaps (no optimistic labels).

Passing them says nothing about whether the reading of the card is right.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from manamind.card_ir.vocabulary import BASES, ELEMENTS, KEYWORDS, RULES
from manamind.card_metadata.snapshot import strip_text_artifacts

IR_VERSION = "card-ir/0.1"
STATUSES = ("FULL", "FULL_DEP", "PARTIAL", "UNSUPPORTED")
ROLES = ("sample", "closure", "engine_validation")
DEP_KINDS = ("POOL_MEMBERSHIP", "TOKEN_IDENTITY", "NAME_REFERENCE", "KEYWORD_RULE", "UNKNOWN_RULE")
DEP_SCOPES = ("DATA", "CONDITIONAL", "CORE")
DECISION_BASES = ("TEXT", "METADATA", *BASES, "ASSUMPTION")
RISKS = ("OUTCOME", "EDGE", "NONE")
RESOLUTIONS = ("UNIQUE_NAME", "NAME_IN_SET", "DESCRIPTION_MATCH", "AMBIGUOUS")

PLAY_LABELS = ("SPELL", "BATTLECRY", "LOCATION", "KINDRED")
TIMINGS = ("AFTER", "WHENEVER", "AT", "WHEN")
EVENTS = ("HERO_ATTACK", "CARD_DRAWN", "TURN_END", "DAMAGE_TAKEN", "DAMAGE_DEALT", "ATTACK_DECLARED")
ZONES = ("PLAY", "HAND", "DECK")
ACTIVE_ZONES = ("PLAY", "HAND", "EQUIPPED")
PICKS = ("ALL", "RANDOM", "CHOSEN")
TYPES = ("CHARACTER", "MINION", "HERO", "CARD", "SPELL", "WEAPON", "LOCATION")
CARD_TYPES = ("MINION", "SPELL", "WEAPON", "LOCATION", "HERO")
SIDES = ("FRIENDLY", "ENEMY", "ANY")
SHORT_SELECTORS = ("SELF", "ENEMY_HERO", "ENEMY_WEAPON")
PLAYERS = ("SELF", "OPPONENT")
CMPS = ("=", ">", ">=", "<", "<=")
STATS = ("ATTACK", "HEALTH", "COST")
DURATIONS = ("THIS_TURN", "UNTIL_USED")
RULE_PARAMS = ("SPELL_DAMAGE_MULTIPLIER", "SPELL_HEALING_MULTIPLIER", "HEALING_DOES_DAMAGE")
COUNTERS = ("CARD_PLAYED", "SPELL_CAST")
COUNTER_SCOPES = ("THIS_TURN", "THIS_GAME")
RESOURCES = ("ARMOR", "CORPSE")
MECHANIC_CONDITIONS = ("KINDRED",)
TEMPLATE_CONTEXTS = ("DARK_GIFT",)
SIMPLE_PREDICATES = ("race", "spell_school", "has_mechanic", "card_class", "card_set")

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z0-9$#+'/\-]+")
_NUMBER = re.compile(r"([$#]?)(\d+)")
# Tokens and generated cards extend the creating card's ID ("BE_553t", "TIME_890t2"); their enchantments may carry the
# creating card's prefix ("BE_553e" for the Overdrive token BE_553t). CORE reprints reuse the original enchantments
# ("REV_990e" for CORE_REV_990).
_TOKEN_SUFFIX = re.compile(r"t\d*$")

# operation -> (required arguments, optional arguments); every operation also accepts "as" (bind its result)
_OPS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "DEAL_DAMAGE": (("to", "amount"), ()),
    "RESTORE_HEALTH": (("to", "amount"), ()),
    "ENCHANT": (("to",), ("attack", "health", "keywords", "abilities", "spell_damage", "duration", "enchantment_id")),
    "SILENCE": (("to",), ()),
    "DESTROY": (("to",), ()),
    "TRANSFORM": (("to", "into"), ()),
    "SUMMON": (("what",), ("count",)),
    "DRAW": (("player",), ("count", "where")),
    "ADD_TO_HAND": (("player", "what"), ("count",)),
    "DISCOVER": (("pool",), ("options",)),
    "CHOOSE": (("from",), ()),
    "MODIFY_COST": (("to",), ("reduce", "set", "enchantment_id")),
    "ADD_PLAYER_EFFECT": (("player", "duration"),
                          ("modifier", "abilities", "uses", "use_unit", "applies_to", "enchantment_id")),
    "SHUFFLE_INTO_DECK": (("player", "what"), ()),
    "CAST": (("what",), ("count",)),
}


class IRError(ValueError):
    pass


def normalise_text(text: str) -> str:
    """Card text without markup and layout: tags, a leading ``[x]`` and line breaks removed; ``$`` and ``#`` kept."""
    plain = _SPACE.sub(" ", _TAG.sub("", text).replace(" ", " ")).strip()
    return plain[3:].strip() if plain.startswith("[x]") else plain


@dataclass
class Report:
    card_id: str
    errors: list[str] = field(default_factory=list)
    elements: Counter = field(default_factory=Counter)
    rules: set[str] = field(default_factory=set)
    card_refs: set[str] = field(default_factory=set)
    computed_status: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


class _Walker:
    """Recursive checker for one declaration. Collects elements, rule needs, card refs and numbers per span."""

    def __init__(self, doc: Mapping[str, Any], meta: Any, report: Report) -> None:
        self.doc, self.meta, self.report = doc, meta, report
        self.text = normalise_text(doc.get("text", "")) if isinstance(doc.get("text"), str) else ""
        self.deps = {dep.get("id"): dep for dep in doc.get("dependencies", []) if isinstance(dep, Mapping)}
        self.used_deps: set[str] = set()
        self.bound_names: list[tuple[str, str]] = []  # (name, path) of every binding
        self.used_names: set[str] = set()
        self.numbers: list[tuple[str, int]] = []      # numbers available under the current span
        self.marked: list[tuple[str, int]] = []       # marked literals under the current span

    # helpers -------------------------------------------------------------------------------------------------------
    def err(self, path: str, message: str) -> None:
        self.report.errors.append(f"{path}: {message}")

    def use(self, element_id: str, path: str) -> None:
        element = ELEMENTS.get(element_id)
        if element is None:
            self.err(path, f"element {element_id!r} is not in the vocabulary")
            return
        self.report.elements[element_id] += 1
        self.report.rules.update(element.rules)

    def keys(self, node: Any, path: str, required: Iterable[str], optional: Iterable[str] = ()) -> bool:
        if not isinstance(node, Mapping):
            self.err(path, f"expected an object, got {node!r}")
            return False
        required, allowed = set(required), set(required) | set(optional)
        missing, extra = required - set(node), set(node) - allowed
        if missing:
            self.err(path, f"missing {sorted(missing)}")
        if extra:
            self.err(path, f"unknown keys {sorted(extra)}")
        return not missing and not extra

    def enum(self, value: Any, allowed: Iterable[str], path: str) -> bool:
        if value not in tuple(allowed):
            self.err(path, f"{value!r} not in {tuple(allowed)}")
            return False
        return True

    def dep(self, dep_id: Any, path: str, kinds: Iterable[str] = DEP_KINDS, scopes: Iterable[str] = DEP_SCOPES) -> None:
        dep = self.deps.get(dep_id)
        if dep is None:
            self.err(path, f"dependency {dep_id!r} is not declared")
            return
        self.used_deps.add(dep_id)
        if dep.get("kind") not in tuple(kinds):
            self.err(path, f"dependency {dep_id!r} must be one of {tuple(kinds)}")
        if dep.get("scope") not in tuple(scopes):
            self.err(path, f"dependency {dep_id!r} must have scope in {tuple(scopes)}")

    def card_id(self, value: Any, path: str) -> Mapping[str, Any] | None:
        record = self.meta.get(value) if isinstance(value, str) else None
        if record is None:
            self.err(path, f"card {value!r} is not in the snapshot")
            return None
        self.report.card_refs.add(value)
        return record

    def literal(self, value: Any, path: str) -> None:
        if isinstance(value, int) and not isinstance(value, bool):
            self.numbers.append(("", abs(value)))
        else:
            self.err(path, "must be an integer")

    # values, conditions, predicates --------------------------------------------------------------------------------
    def value(self, node: Any, path: str, bound: set[str]) -> None:
        if isinstance(node, int) and not isinstance(node, bool):
            self.use("value:literal", path)
            self.numbers.append(("", abs(node)))
            return
        if not isinstance(node, Mapping) or not node:
            self.err(path, f"bad value {node!r}")
            return
        if "mark" in node:
            if self.keys(node, path, ("n", "mark")) and self.enum(node["mark"], ("$", "#"), path + ".mark"):
                self.use("value:spell_damage_literal" if node["mark"] == "$" else "value:healing_literal", path)
                self.numbers.append((node["mark"], abs(node["n"])))
                self.marked.append((node["mark"], abs(node["n"])))
        elif "stat" in node:
            if self.keys(node, path, ("stat", "of"), ("at",)):
                self.enum(node["stat"], STATS, path + ".stat")
                self.enum(node.get("at", "CURRENT"), ("CURRENT", "LAST_KNOWN"), path + ".at")
                self.use("value:stat", path)
                self.selector(node["of"], path + ".of", bound)
        elif "counter" in node:
            if self.keys(node, path, ("counter",)):
                self.use("value:counter", path)
                self.counter(node["counter"], path + ".counter", bound)
        elif "var" in node:
            if self.keys(node, path, ("var",)):
                self.use("value:var", path)
                self.used_names.add(node["var"])
                if node["var"] not in bound:
                    self.err(path, f"variable {node['var']!r} is not set before use")
        elif len(node) == 1 and next(iter(node)) in ("add", "sub", "max"):
            op = next(iter(node))
            if not isinstance(node[op], list) or len(node[op]) != 2:
                self.err(path, "arithmetic takes exactly two values")
                return
            self.use("value:arith", path)
            for index, item in enumerate(node[op]):
                self.value(item, f"{path}.{op}[{index}]", bound)
        elif "unknown" in node:
            if self.keys(node, path, ("unknown",)):
                self.use("value:unknown", path)
                self.dep(node["unknown"], path, ("UNKNOWN_RULE",), ("CORE", "CONDITIONAL"))
        else:
            self.err(path, f"unknown value shape {sorted(node)}")

    def counter(self, node: Any, path: str, bound: set[str]) -> None:
        if not self.keys(node, path, ("event", "player", "scope"), ("where", "distinct")):
            return
        if self.enum(node["event"], COUNTERS, path + ".event"):
            self.use(f"counter:{node['event']}", path)
        if self.enum(node["scope"], COUNTER_SCOPES, path + ".scope"):
            self.use(f"scope:{node['scope']}", path)
        self.enum(node["player"], PLAYERS, path + ".player")
        self.predicates(node.get("where", []), path + ".where", bound)

    def condition(self, node: Any, path: str, bound: set[str]) -> None:
        if not isinstance(node, Mapping) or len(node) != 1:
            self.err(path, f"bad condition {node!r}")
            return
        (kind,) = node
        if kind == "cmp":
            items = node["cmp"]
            if not (isinstance(items, list) and len(items) == 3 and items[1] in CMPS):
                self.err(path, "cmp takes [value, operator, value]")
                return
            self.use("cond:cmp", path)
            self.value(items[0], path + ".cmp[0]", bound)
            self.value(items[2], path + ".cmp[2]", bound)
        elif kind == "exists":
            self.use("cond:exists", path)
            self.selector(node["exists"], path + ".exists", bound)
        elif kind == "is":
            if self.keys(node["is"], path + ".is", ("entity", "where")):
                self.use("cond:is", path)
                self.selector(node["is"]["entity"], path + ".is.entity", bound)
                self.predicates(node["is"]["where"], path + ".is.where", bound)
        elif kind == "mechanic":
            if self.enum(node["mechanic"], MECHANIC_CONDITIONS, path):
                self.use("cond:mechanic", path)
        else:
            self.err(path, f"unknown condition {kind!r}")

    def predicates(self, items: Any, path: str, bound: set[str]) -> None:
        if not isinstance(items, list):
            self.err(path, "predicates must be a list")
            return
        for index, pred in enumerate(items):
            self.predicate(pred, f"{path}[{index}]", bound)

    def predicate(self, node: Any, path: str, bound: set[str]) -> None:
        if not isinstance(node, Mapping) or not node:
            self.err(path, f"bad predicate {node!r}")
            return
        kind = next(iter(node))
        if kind == "keyword":
            if self.keys(node, path, ("keyword",)) and self.enum(node["keyword"], KEYWORDS, path):
                self.use("pred:keyword", path)
        elif kind in SIMPLE_PREDICATES:
            if self.keys(node, path, (kind,)):
                self.use(f"pred:{kind}", path)
        elif kind == "card_type":
            if self.keys(node, path, ("card_type",)) and self.enum(node["card_type"], CARD_TYPES, path):
                self.use("pred:card_type", path)
        elif kind == "cost":
            cost = node["cost"]
            if self.keys(node, path, ("cost",)) and isinstance(cost, Mapping) and cost.get("cmp") in CMPS:
                self.use("pred:cost", path)
                self.literal(cost.get("n"), path + ".cost.n")
            else:
                self.err(path, "cost takes {cmp, n}")
        elif kind == "damaged":
            if self.keys(node, path, ("damaged",)):
                self.use("pred:damaged", path)
        elif kind == "named":
            if self.keys(node, path, ("named", "ids", "dep")):
                self.use("pred:named", path)
                for card in node["ids"]:
                    self.card_id(card, path + ".ids")
                self.dep(node["dep"], path, ("NAME_REFERENCE",), ("DATA", "CONDITIONAL"))
                for name in node["named"] if isinstance(node["named"], list) else [node["named"]]:
                    if name not in self.text:
                        self.err(path, f"name {name!r} does not occur in the text")
        else:
            self.err(path, f"unknown predicate {kind!r}")

    # selectors, card sources, modifiers, events ----------------------------------------------------------------------
    def selector(self, node: Any, path: str, bound: set[str], *, chosen_ok: bool = False) -> None:
        if isinstance(node, str):
            if self.enum(node, SHORT_SELECTORS, path):
                self.use(f"selector:{node}", path)
            return
        if isinstance(node, Mapping) and "ref" in node:
            if self.keys(node, path, ("ref",)):
                self.use("selector:ref", path)
                self.used_names.add(node["ref"])
                if node["ref"] not in bound:
                    self.err(path, f"reference {node['ref']!r} is not bound before use")
            return
        if not self.keys(node, path, ("pick", "type", "side"), ("zone", "n", "where", "exclude")):
            return
        if self.enum(node["pick"], PICKS, path + ".pick"):
            self.use(f"pick:{node['pick']}", path)
            if node["pick"] == "CHOSEN" and not chosen_ok:
                self.err(path, "CHOSEN is only allowed in a play target or CHOOSE")
        self.enum(node["type"], TYPES, path + ".type")
        self.enum(node["side"], SIDES, path + ".side")
        zones = node.get("zone", "PLAY")
        for zone in zones if isinstance(zones, list) else [zones]:
            if self.enum(zone, ZONES, path + ".zone"):
                self.use(f"zone:{zone}", path)
        if "n" in node:
            self.value(node["n"], path + ".n", bound)
        self.predicates(node.get("where", []), path + ".where", bound)
        if "exclude" in node:
            self.use("selector:exclude", path)
            for index, item in enumerate(node["exclude"]):
                self.selector(item, f"{path}.exclude[{index}]", bound)

    def pool(self, node: Any, path: str, bound: set[str]) -> None:
        if self.keys(node, path, ("type", "where", "dep")):
            self.enum(node["type"], TYPES, path + ".type")
            self.predicates(node["where"], path + ".where", bound)
            self.dep(node["dep"], path, ("POOL_MEMBERSHIP",))

    def card_source(self, node: Any, path: str, bound: set[str]) -> None:
        kinds = {"card", "copy_of", "random_from", "all_from", "from_zone"}
        if not isinstance(node, Mapping) or len(set(node) & kinds) != 1:
            self.err(path, f"bad card source {node!r}")
            return
        if "card" in node:
            if not self.keys(node, path, ("card", "resolved"), ("dep",)):
                return
            self.use("card_source:card", path)
            record = self.card_id(node["card"], path + ".card")
            if self.enum(node["resolved"], RESOLUTIONS, path + ".resolved") and record is not None:
                if node["resolved"] == "UNIQUE_NAME":
                    self.check_unique_name(record, path)
                elif "dep" not in node:
                    self.err(path, f"{node['resolved']} token identity needs a TOKEN_IDENTITY dependency")
            if "dep" in node:
                self.dep(node["dep"], path, ("TOKEN_IDENTITY",), ("DATA", "CONDITIONAL"))
            for key in ("attack", "health", "cost"):
                if record is not None and isinstance(record.get(key), int):
                    self.numbers.append(("", record[key]))
        elif "copy_of" in node:
            if self.keys(node, path, ("copy_of",)):
                self.use("card_source:copy_of", path)
                self.selector(node["copy_of"], path + ".copy_of", bound)
        elif "random_from" in node:
            if self.keys(node, path, ("random_from",)):
                self.use("card_source:random_from", path)
                self.pool(node["random_from"], path + ".random_from", bound)
        elif "all_from" in node:
            if self.keys(node, path, ("all_from",), ("exclude",)):
                self.use("card_source:all_from", path)
                self.pool(node["all_from"], path + ".all_from", bound)
                for index, item in enumerate(node.get("exclude", [])):
                    self.selector(item, f"{path}.exclude[{index}]", bound)
        elif self.keys(node, path, ("from_zone",)):
            self.use("card_source:from_zone", path)
            self.selector(node["from_zone"], path + ".from_zone", bound)

    def check_unique_name(self, record: Mapping[str, Any], path: str) -> None:
        name = record.get("name") or ""
        if name.lower() not in self.text.lower():
            self.err(path, f"UNIQUE_NAME but {name!r} does not occur in the text")
            return
        same = [r["id"] for r in self.meta.records() if r.get("name") == name and r.get("type") in CARD_TYPES]
        if len(same) != 1:
            self.err(path, f"UNIQUE_NAME but {len(same)} gameplay records are named {name!r}")

    def enchantment(self, value: Any, path: str) -> None:
        """An enchantment ID must be an ENCHANTMENT record derived from this card's ID (prefix)."""
        record = self.card_id(value, path)
        if record is None:
            return
        if record.get("type") != "ENCHANTMENT":
            self.err(path, f"{value!r} is not an enchantment record")
        root = _TOKEN_SUFFIX.sub("", str(self.doc.get("card_id")))
        if not str(value).startswith((root, root.removeprefix("CORE_"))):
            self.err(path, f"{value!r} does not derive from {root!r}")

    def duration(self, node: Any, path: str) -> None:
        if isinstance(node, Mapping) and self.keys(node, path, ("turns",)):
            self.use("duration:N_TURNS", path)
            self.literal(node["turns"], path + ".turns")
        elif not isinstance(node, Mapping) and self.enum(node, DURATIONS, path):
            self.use(f"duration:{node}", path)

    def modifier(self, node: Any, path: str, bound: set[str]) -> None:
        if isinstance(node, list) and len(node) >= 2:
            for index, item in enumerate(node):
                self.modifier(item, f"{path}[{index}]", bound)
        elif isinstance(node, Mapping) and "cost" in node:
            cost = node["cost"]
            if self.keys(node, path, ("cost",)) and isinstance(cost, Mapping) and len(cost) == 1 and \
                    next(iter(cost)) in ("set", "reduce"):
                self.use("modifier:cost", path)
                self.value(next(iter(cost.values())), path + ".cost", bound)
            else:
                self.err(path, "cost modifier takes exactly one of set/reduce")
        elif isinstance(node, Mapping) and "rule" in node:
            if self.keys(node, path, ("rule",), ("factor",)) and self.enum(node["rule"], RULE_PARAMS, path):
                self.use("modifier:rule", path)
                self.use(f"rule:{node['rule']}", path)
        elif isinstance(node, Mapping) and "spell_damage" in node:
            if self.keys(node, path, ("spell_damage",)):
                self.use("modifier:spell_damage", path)
                self.value(node["spell_damage"], path + ".spell_damage", bound)
        else:
            self.err(path, f"unknown modifier {node!r}")

    def event(self, node: Any, path: str, bound: set[str]) -> None:
        if isinstance(node, Mapping) and "unknown" in node:
            if self.keys(node, path, ("unknown",)):
                self.use("cond:unknown", path)
                self.dep(node["unknown"], path, ("UNKNOWN_RULE",), ("CORE", "CONDITIONAL"))
            return
        if not self.keys(node, path, ("type",), ("player", "subject", "defender", "source")):
            return
        if self.enum(node["type"], EVENTS, path + ".type"):
            self.use(f"event:{node['type']}", path)
        if "player" in node:
            self.enum(node["player"], PLAYERS, path + ".player")
        for key in ("subject", "defender"):
            if key in node:
                self.selector(node[key], f"{path}.{key}", bound)
        if "source" in node:
            self.predicates(node["source"], path + ".source", bound)

    # effects ----------------------------------------------------------------------------------------------------------
    def effect(self, node: Any, path: str, bound: set[str]) -> set[str]:
        """Validate one effect node; return the names bound after it."""
        control = set(node) & {"seq", "if", "repeat", "repeat_while", "set", "pay", "op"} if isinstance(node, Mapping) else ()
        if len(control) != 1:
            self.err(path, f"an effect needs exactly one of seq/if/repeat/repeat_while/set/pay/op, got {node!r}")
            return bound
        (kind,) = control
        if kind == "seq":
            if not self.keys(node, path, ("seq",)) or not isinstance(node["seq"], list) or len(node["seq"]) < 2:
                self.err(path, "seq needs a list of at least two steps")
                return bound
            self.use("control:seq", path)
            for index, step in enumerate(node["seq"]):
                bound = self.effect(step, f"{path}.seq[{index}]", bound)
        elif kind == "if":
            if self.keys(node, path, ("if", "then"), ("else",)):
                self.use("control:if", path)
                self.condition(node["if"], path + ".if", bound)
                self.effect(node["then"], path + ".then", set(bound))
                if "else" in node:
                    self.effect(node["else"], path + ".else", set(bound))
        elif kind == "repeat":
            if self.keys(node, path, ("repeat", "do")):
                self.use("control:repeat", path)
                self.value(node["repeat"], path + ".repeat", bound)
                self.effect(node["do"], path + ".do", set(bound))
        elif kind == "repeat_while":
            if self.keys(node, path, ("repeat_while", "do", "max")):
                self.use("control:repeat_while", path)
                self.condition(node["repeat_while"], path + ".repeat_while", bound)
                if isinstance(node["max"], Mapping):
                    self.value(node["max"], path + ".max", bound)
                elif not isinstance(node["max"], int):
                    self.err(path, "max must be an integer bound or an unknown")
                self.effect(node["do"], path + ".do", set(bound))
        elif kind == "set":
            if not self.keys(node, path, ("set",)) or not isinstance(node["set"], Mapping) or len(node["set"]) != 1:
                self.err(path, "set assigns exactly one variable")
                return bound
            self.use("control:set", path)
            ((name, value),) = node["set"].items()
            self.value(value, f"{path}.set.{name}", bound)
            if name not in bound:
                self.bound_names.append((name, path))
            return bound | {name}
        elif kind == "pay":
            if self.keys(node, path, ("pay", "then")):
                self.use("control:pay", path)
                self.payment(node["pay"], path + ".pay", bound)
                self.effect(node["then"], path + ".then", set(bound))
        else:
            return self.op(node, path, bound)
        return bound

    def payment(self, cost: Any, path: str, bound: set[str]) -> None:
        if isinstance(cost, Mapping) and "resource" in cost:
            if self.keys(cost, path, ("resource", "amount")) and self.enum(cost["resource"], RESOURCES, path + ".resource"):
                self.use(f"resource:{cost['resource']}", path)
                self.value(cost["amount"], path + ".amount", bound)
        elif isinstance(cost, Mapping) and "discard" in cost:
            if self.keys(cost, path, ("discard",)):
                self.use("pay:discard", path)
                self.selector(cost["discard"], path + ".discard", bound)
        else:
            self.err(path, "pay takes {resource, amount} or {discard}")

    def op(self, node: Mapping[str, Any], path: str, bound: set[str]) -> set[str]:
        name = node["op"]
        if name not in _OPS:
            self.err(path, f"unknown operation {name!r}")
            return bound
        required, optional = _OPS[name]
        if not self.keys(node, path, ("op", *required), (*optional, "as")):
            return bound
        self.use(f"op:{name}", path)
        for key, value in node.items():
            sub = f"{path}.{key}"
            if key in ("to", "from"):
                self.selector(value, sub, bound, chosen_ok=(name == "CHOOSE"))
            elif key in ("amount", "count", "attack", "health", "reduce", "set", "spell_damage"):
                self.value(value, sub, bound)
            elif key == "player":
                self.enum(value, PLAYERS, sub)
            elif key in ("what", "into"):
                self.card_source(value, sub, bound)
            elif key == "pool":
                self.pool(value, sub, bound)
            elif key in ("where", "applies_to"):
                self.predicates(value, sub, bound)
            elif key == "keywords":
                for keyword in value:
                    if self.enum(keyword, KEYWORDS, sub):
                        self.use(f"keyword:{keyword}", sub)
            elif key == "abilities":
                for index, ability in enumerate(value):
                    self.ability(ability, f"{sub}[{index}]", nested=True)
            elif key == "duration":
                self.duration(value, sub)
            elif key == "modifier":
                self.modifier(value, sub, bound)
            elif key == "enchantment_id":
                self.enchantment(value, sub)
            elif key in ("options", "uses") and not isinstance(value, int):
                self.err(sub, "must be an integer")
            elif key == "use_unit":
                self.enum(value, ("CARD", "EFFECT"), sub)
        if name == "ENCHANT" and not set(node) & {"attack", "health", "keywords", "abilities", "spell_damage"}:
            self.err(path, "ENCHANT changes nothing")
        if name == "MODIFY_COST" and len(set(node) & {"reduce", "set"}) != 1:
            self.err(path, "MODIFY_COST takes exactly one of reduce/set")
        if name == "ADD_PLAYER_EFFECT" and len(set(node) & {"modifier", "abilities"}) != 1:
            self.err(path, "ADD_PLAYER_EFFECT takes a modifier or abilities")
        if "as" not in node:
            return bound
        self.bound_names.append((node["as"], path))
        return bound | {node["as"]}

    # abilities --------------------------------------------------------------------------------------------------------
    def ability(self, node: Any, path: str, *, nested: bool = False) -> None:
        kind = node.get("kind") if isinstance(node, Mapping) else None
        span = () if nested else ("span",)
        bound: set[str] = set()
        if kind == "play":
            if not self.keys(node, path, ("kind", "label", "effect", *span), ("target", "condition")):
                return
            if self.enum(node["label"], PLAY_LABELS, path + ".label"):
                self.use(f"label:{node['label']}", path)
            if "target" in node and self.keys(node["target"], path + ".target", ("bind", "choose")):
                choose = node["target"]["choose"]
                self.selector(choose, path + ".target.choose", bound, chosen_ok=True)
                if not (isinstance(choose, Mapping) and choose.get("pick") == "CHOSEN"):
                    self.err(path + ".target", "a play target must pick CHOSEN")
                bound = bound | {node["target"]["bind"]}
                self.bound_names.append((node["target"]["bind"], path + ".target"))
            if "condition" in node:
                self.condition(node["condition"], path + ".condition", bound)
        elif kind == "trigger":
            if not self.keys(node, path, ("kind", "event", "timing", "effect", *span),
                             ("label", "condition", "limit", "active_in")):
                return
            self.event(node["event"], path + ".event", bound)
            if self.enum(node["timing"], TIMINGS, path + ".timing"):
                self.use(f"timing:{node['timing']}", path)
            if "label" in node and self.enum(node["label"], ("SECRET",), path + ".label"):
                self.use("label:SECRET", path)
            if "limit" in node and self.enum(node["limit"], ("FIRST_EACH_TURN",), path + ".limit"):
                self.use("trigger_limit:FIRST_EACH_TURN", path)
            if "active_in" in node:
                self.enum(node["active_in"], ACTIVE_ZONES, path + ".active_in")
        elif kind == "deathrattle":
            if not self.keys(node, path, ("kind", "effect", *span)):
                return
        elif kind == "aura":
            if self.keys(node, path, ("kind", "active_in", "modifier", *span), ("while",)):
                self.use("ability:aura", path)
                self.enum(node["active_in"], ACTIVE_ZONES, path + ".active_in")
                if "while" in node:
                    self.condition(node["while"], path + ".while", bound)
                self.modifier(node["modifier"], path + ".modifier", bound)
            return
        elif kind == "quest":
            if self.keys(node, path, ("kind", "progress", "reward", *span)):
                self.use("ability:quest", path)
                if self.keys(node["progress"], path + ".progress", ("event", "goal")):
                    self.event(node["progress"]["event"], path + ".progress.event", bound)
                    self.literal(node["progress"]["goal"], path + ".progress.goal")
                self.card_source(node["reward"], path + ".reward", bound)
            return
        elif kind == "enchantment_template":
            if self.keys(node, path, ("kind", "context", *span), ("attack", "health", "keywords")):
                self.use("ability:enchantment_template", path)
                if self.enum(node["context"], TEMPLATE_CONTEXTS, path + ".context"):
                    self.use(f"keyword:{node['context']}", path)
                for key in ("attack", "health"):
                    if key in node:
                        self.value(node[key], f"{path}.{key}", bound)
                for keyword in node.get("keywords", []):
                    if self.enum(keyword, KEYWORDS, path + ".keywords"):
                        self.use(f"keyword:{keyword}", path)
            return
        else:
            self.err(path, f"unknown ability kind {kind!r}")
            return
        self.use(f"ability:{kind}", path)
        self.effect(node["effect"], path + ".effect", bound)


def _spans(doc: Mapping[str, Any]) -> list[tuple[str, Any]]:
    spans = [(f"abilities[{i}]", a.get("span")) for i, a in enumerate(doc.get("abilities", []))]
    for kind in ("keywords", "reminders", "unexpressed"):
        spans += [(f"{kind}[{i}]", item.get("span")) for i, item in enumerate(doc.get(kind, []))]
    return spans


def _check_coverage(doc: Mapping[str, Any], text: str, report: Report) -> dict[str, tuple[int, int]]:
    """Every span must occur in the text without overlapping another; every word must lie inside some span."""
    located: dict[str, tuple[int, int]] = {}
    for path, span in _spans(doc):
        if not isinstance(span, str) or not span:
            report.errors.append(f"{path}: missing span")
            continue
        start = text.find(span)
        while start >= 0 and any(start < end and start + len(span) > begin for begin, end in located.values()):
            start = text.find(span, start + 1)
        if start < 0:
            report.errors.append(f"{path}: span {span!r} is not in the text (or overlaps another span)")
            continue
        located[path] = (start, start + len(span))
    for match in _WORD.finditer(text):
        if not any(begin <= match.start() and match.end() <= end for begin, end in located.values()):
            report.errors.append(f"text: word {match.group()!r} at {match.start()} is not covered by any span")
    return located


def _check_numbers(path: str, span_text: str, numbers: list[tuple[str, int]], marked: list[tuple[str, int]],
                   report: Report) -> None:
    available = Counter(numbers)
    in_text = [(mark, int(n)) for mark, n in _NUMBER.findall(span_text)]
    for item in in_text:
        if available[item] > 0:
            available[item] -= 1
        else:
            report.errors.append(f"{path}: text number {item[0]}{item[1]} has no matching IR number with the same mark")
    text_marked = Counter(item for item in in_text if item[0])
    for item, count in Counter(marked).items():
        if count > text_marked[item]:
            report.errors.append(f"{path}: IR number {item[0]}{item[1]} carries a mark the text does not have")


def implied_status(doc: Mapping[str, Any]) -> str:
    """PARTIAL with an unexpressed span or a CORE gap; FULL_DEP with any other dependency; FULL otherwise."""
    if doc.get("unexpressed"):
        return "PARTIAL"
    scopes = {dep.get("scope") for dep in doc.get("dependencies", []) if isinstance(dep, Mapping)}
    if "CORE" in scopes:
        return "PARTIAL"
    return "FULL_DEP" if scopes else "FULL"


def _check_decisions(doc: Mapping[str, Any], walker: _Walker, report: Report) -> None:
    for index, decision in enumerate(doc["decisions"]):
        path = f"decisions[{index}]"
        if not walker.keys(decision, path, ("id", "question", "alternatives", "chosen", "basis", "risk"),
                           ("discriminating_case", "dep")):
            continue
        walker.enum(decision["basis"], DECISION_BASES, path + ".basis")
        walker.enum(decision["risk"], RISKS, path + ".risk")
        if not isinstance(decision["alternatives"], list) or len(decision["alternatives"]) < 2:
            report.errors.append(f"{path}: needs at least two alternatives")
        elif decision["chosen"] == "UNRESOLVED":
            if decision["basis"] != "UNKNOWN" or "dep" not in decision:
                report.errors.append(f"{path}: UNRESOLVED needs basis UNKNOWN and a dependency")
        elif decision["chosen"] not in decision["alternatives"]:
            report.errors.append(f"{path}: chosen is not one of the alternatives")
        elif decision["basis"] == "UNKNOWN":
            report.errors.append(f"{path}: basis UNKNOWN cannot choose a reading; use UNRESOLVED")
        unsourced = decision["basis"] in ("UNVERIFIED", "ASSUMPTION", "UNKNOWN")
        if decision["risk"] == "OUTCOME" and unsourced and "dep" not in decision:
            report.errors.append(f"{path}: an outcome-changing reading without a source needs a dependency")
        if "dep" in decision:
            walker.dep(decision["dep"], path)
        if decision["risk"] != "NONE" and not decision.get("discriminating_case"):
            report.errors.append(f"{path}: a risky reading needs a discriminating case")


def validate_declaration(doc: Mapping[str, Any], meta: Any) -> Report:
    """Validate one declaration against the pinned metadata ``meta`` (a ``CardMetadata``)."""
    report = Report(str(doc.get("card_id")))
    walker = _Walker(doc, meta, report)
    if not walker.keys(doc, "doc", ("ir", "card_id", "snapshot", "role", "text", "text_sha256", "abilities",
                                    "dependencies", "decisions", "status"),
                       ("keywords", "reminders", "unexpressed", "notes")):
        return report
    if doc["ir"] != IR_VERSION:
        report.errors.append(f"doc: ir must be {IR_VERSION}")
    walker.enum(doc["role"], ROLES, "doc.role")
    if doc["snapshot"] != meta.snapshot_id:
        report.errors.append(f"doc: snapshot {doc['snapshot']!r} is not the loaded {meta.snapshot_id!r}")
    record = meta.get(doc["card_id"])
    if record is None:
        report.errors.append("doc: card is not in the snapshot")
        return report
    if doc["text"] != strip_text_artifacts(record.get("text", "")):
        report.errors.append("doc: text differs from the snapshot's cleaned text")
    if doc["text_sha256"] != hashlib.sha256(doc["text"].encode("utf-8")).hexdigest():
        report.errors.append("doc: text_sha256 does not match text")

    for index, dep in enumerate(doc["dependencies"]):
        path = f"dependencies[{index}]"
        if walker.keys(dep, path, ("id", "kind", "scope", "detail", "source_needed"), ("card_level",)):
            walker.enum(dep["kind"], DEP_KINDS, path + ".kind")
            walker.enum(dep["scope"], DEP_SCOPES, path + ".scope")
    _check_decisions(doc, walker, report)

    located = _check_coverage(doc, walker.text, report)
    for index, keyword in enumerate(doc.get("keywords", [])):
        path = f"keywords[{index}]"
        if not walker.keys(keyword, path, ("keyword", "span"), ("amount", "parts")):
            continue
        if walker.enum(keyword["keyword"], KEYWORDS, path):
            walker.use(f"keyword:{keyword['keyword']}", path)
        walker.numbers, walker.marked = [], []
        if "amount" in keyword:
            walker.literal(keyword["amount"], path + ".amount")
        for part_index, part in enumerate(keyword.get("parts", [])):
            walker.card_source(part, f"{path}.parts[{part_index}]", set())
        if path in located:
            _check_numbers(path, walker.text[slice(*located[path])], walker.numbers, walker.marked, report)
    for index, ability in enumerate(doc["abilities"]):
        path = f"abilities[{index}]"
        walker.numbers, walker.marked = [], []
        walker.ability(ability, path)
        if path in located:
            _check_numbers(path, walker.text[slice(*located[path])], walker.numbers, walker.marked, report)
    for kind in ("reminders", "unexpressed"):
        for index, item in enumerate(doc.get(kind, [])):
            walker.keys(item, f"{kind}[{index}]", ("span", "why"))

    # A name that is bound but never read usually means 'it'/'them' was resolved to the wrong entity.
    for name, path in walker.bound_names:
        if name not in walker.used_names:
            report.errors.append(f"{path}: {name!r} is bound but never used")
    for dep_id, dep in walker.deps.items():
        if dep_id not in walker.used_deps and not dep.get("card_level"):
            report.errors.append(f"dependencies: {dep_id!r} is declared but never referenced (mark card_level)")
    sourced = sorted(e for e in report.elements if ELEMENTS[e].needs_source)
    if sourced and not any(dep.get("kind") == "KEYWORD_RULE" for dep in walker.deps.values()):
        report.errors.append(f"dependencies: {sourced} need a KEYWORD_RULE dependency (rule not in text)")

    report.computed_status = implied_status(doc)
    if doc["status"] not in STATUSES:
        report.errors.append(f"doc: status {doc['status']!r} not in {STATUSES}")
    elif doc["status"] == "UNSUPPORTED":
        if not doc.get("unexpressed"):
            report.errors.append("doc: UNSUPPORTED needs the unexpressed spans")
    elif doc["status"] != report.computed_status:
        report.errors.append(f"doc: status {doc['status']} differs from implied {report.computed_status}")
    report.rules &= set(RULES)
    return report


def extract_elements(doc: Mapping[str, Any], meta: Any) -> Counter:
    """Elements of a valid declaration; raises ``IRError`` for an invalid one."""
    report = validate_declaration(doc, meta)
    if report.errors:
        raise IRError(f"{doc.get('card_id')}: {report.errors[:3]}")
    return report.elements
