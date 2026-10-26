"""Structural validation of Card IR v0.2 declarations (delta: reports/card_ir_v02/CHANGELOG.md).

The v0.1 validator is frozen (pinned by hash), so v0.2 subclasses its walker and overrides only the nodes whose
contract changed. Each declaration is checked by exactly one version: v0.1 tools reject ``card-ir/0.2`` and this
module rejects ``card-ir/0.1``. Nothing is reinterpreted silently; upgrading a v0.1 declaration is re-authoring.

New checks on top of v0.1:

* new nodes and parameters (FREEZE, THIS_GAME, NEXT_TURN, delayed start, cost zones, uses ALL_MATCHING, attack roles,
  ``alive``, damage-amount counter, ``mul``, cost ``increase``, deck position/count, PLAY->HAND moves) with their
  structural invariants;
* constructs that changed meaning must be explicit (a cost player effect states ``uses`` and ``zones``; a negative
  ``reduce`` is rejected in favour of ``increase``; ``subject`` is rejected on ATTACK_DECLARED);
* every provisional rule (``vocabulary_v02.PROVISIONAL_RULES``) the declaration needs is acknowledged by an
  ``UNKNOWN_RULE`` dependency whose ``rule`` names it, and no dependency acknowledges a rule the declaration does not
  need.

As in v0.1, passing says nothing about whether the reading of the card is right.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any, Mapping

from manamind.card_ir.validate import (_OPS, DECISION_BASES, DEP_KINDS, DEP_SCOPES, EVENTS, IRError, KEYWORDS,
                                       PLAYERS, RISKS, ROLES, STATUSES, ZONES, Report, _check_coverage, _check_numbers,
                                       _Walker, implied_status)
from manamind.card_ir.vocabulary_v02 import ELEMENTS_V02, PROVISIONAL_RULES, RULES_V02
from manamind.card_metadata.snapshot import strip_text_artifacts

IR_VERSION_V02 = "card-ir/0.2"
ROLES_V02 = (*ROLES, "example")
# USER_OBSERVED: the user's own game experience, recorded in the declaration; not official documentation.
DECISION_BASES_V02 = (*DECISION_BASES, "USER_OBSERVED")
UNSOURCED = ("UNVERIFIED", "ASSUMPTION", "UNKNOWN")
DURATIONS_V02 = ("THIS_TURN", "UNTIL_USED", "THIS_GAME")
DECK_POSITIONS = ("RANDOM", "TOP", "BOTTOM")
ALL_MATCHING = "ALL_MATCHING"
CHARACTER_TYPES = ("CHARACTER", "MINION", "HERO")
# event type -> (required roles, optional roles); ATTACK_DECLARED also needs at least one of attacker/defender
EVENT_ROLES = {
    "HERO_ATTACK": ((), ("player",)),
    "CARD_DRAWN": ((), ("player",)),
    "TURN_END": ((), ("player",)),
    "DAMAGE_TAKEN": (("subject",), ()),
    "DAMAGE_DEALT": ((), ("player", "source")),
    "ATTACK_DECLARED": ((), ("attacker", "defender")),
}
assert set(EVENT_ROLES) == set(EVENTS)

_OPS_V02 = {**_OPS,
            "MODIFY_COST": (("to",), ("reduce", "set", "increase", "enchantment_id")),
            "ADD_PLAYER_EFFECT": (("player", "duration"), ("modifier", "abilities", "uses", "use_unit", "applies_to",
                                                           "enchantment_id", "zones", "starts_after")),
            "SHUFFLE_INTO_DECK": (("player", "what"), ("count", "position")),
            "FREEZE": (("to",), ())}
_SPLIT = re.compile(r"\bsplit\b")
_RANDOM_SPLIT = re.compile(r"\brandomly split\b")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _has_cost(modifier: Any) -> bool:
    if isinstance(modifier, list):
        return any(_has_cost(item) for item in modifier)
    return isinstance(modifier, Mapping) and "cost" in modifier


class _WalkerV02(_Walker):
    """The v0.1 walker with the v0.2 vocabulary and the changed nodes overridden."""

    def __init__(self, doc: Mapping[str, Any], meta: Any, report: Report) -> None:
        super().__init__(doc, meta, report)
        self.alive_paths: dict[str, bool] = {}  # '<cond path>.is.where' -> entity may carry 'alive'

    def use(self, element_id: str, path: str) -> None:
        element = ELEMENTS_V02.get(element_id)
        if element is None:
            self.err(path, f"element {element_id!r} is not in the vocabulary")
            return
        self.report.elements[element_id] += 1
        self.report.rules.update(element.rules)

    def non_negative(self, value: Any, path: str) -> None:
        if _is_int(value) and value < 0:
            self.err(path, "must not be negative (state the direction: reduce or increase)")

    # values, conditions, predicates --------------------------------------------------------------------------------
    def value(self, node: Any, path: str, bound: set[str]) -> None:
        if isinstance(node, Mapping) and "mark" in node and not _is_int(node.get("n")):
            self.err(path + ".n", "a marked amount must be an integer, not a boolean or float")
            return
        if isinstance(node, Mapping) and len(node) == 1 and "mul" in node:
            items = node["mul"]
            if not isinstance(items, list) or len(items) != 2 or not any(_is_int(item) for item in items):
                self.err(path, "mul takes exactly two values, at least one an integer literal from the text")
                return
            self.use("value:mul", path)
            for index, item in enumerate(items):
                self.value(item, f"{path}.mul[{index}]", bound)
            return
        super().value(node, path, bound)

    def counter(self, node: Any, path: str, bound: set[str]) -> None:
        if not (isinstance(node, Mapping) and node.get("event") == "DAMAGE_DEALT"):
            super().counter(node, path, bound)
            return
        if not self.keys(node, path, ("event", "player", "scope", "measure"), ("source",)):
            return
        self.use("counter:DAMAGE_DEALT", path)
        self.enum(node["measure"], ("AMOUNT",), path + ".measure")
        if self.enum(node["scope"], ("THIS_TURN", "THIS_GAME"), path + ".scope"):
            self.use(f"scope:{node['scope']}", path)
        self.enum(node["player"], PLAYERS, path + ".player")
        self.predicates(node.get("source", []), path + ".source", bound)

    def condition(self, node: Any, path: str, bound: set[str]) -> None:
        if isinstance(node, Mapping) and len(node) == 1 and isinstance(node.get("is"), Mapping):
            entity = node["is"].get("entity")
            self.alive_paths[path + ".is.where"] = entity == "SELF" or (
                isinstance(entity, Mapping) and set(entity) == {"ref"})
        super().condition(node, path, bound)

    def predicate(self, node: Any, path: str, bound: set[str]) -> None:
        if isinstance(node, Mapping) and "alive" in node:
            if not self.keys(node, path, ("alive",)):
                return
            if not isinstance(node["alive"], bool):
                self.err(path, "alive must be a boolean")
            elif not self.alive_paths.get(path.rsplit("[", 1)[0]):
                self.err(path, "alive is only allowed in an 'is' condition over SELF or a bound reference")
            else:
                self.use("pred:alive", path)
            return
        super().predicate(node, path, bound)

    # events, durations, modifiers ------------------------------------------------------------------------------------
    def event(self, node: Any, path: str, bound: set[str]) -> None:
        if not isinstance(node, Mapping) or "unknown" in node or node.get("type") not in EVENT_ROLES:
            super().event(node, path, bound)
            return
        required, optional = EVENT_ROLES[node["type"]]
        if not self.keys(node, path, ("type", *required), optional):
            return
        self.use(f"event:{node['type']}", path)
        if "player" in node:
            self.enum(node["player"], PLAYERS, path + ".player")
        for role in ("subject", "attacker", "defender"):
            if role in node:
                self.selector(node[role], f"{path}.{role}", bound)
                if isinstance(node[role], Mapping) and node[role].get("pick", "ALL") != "ALL":
                    self.err(f"{path}.{role}", "an event role is a filter on participants: use pick ALL")
                if role != "subject":
                    self.use(f"event_role:{role}", path)
        if "source" in node:
            self.predicates(node["source"], path + ".source", bound)
        if node["type"] == "ATTACK_DECLARED" and not {"attacker", "defender"} & set(node):
            self.err(path, "ATTACK_DECLARED needs an attacker or defender role")

    def duration(self, node: Any, path: str) -> None:
        if isinstance(node, Mapping) and "next_turn" in node:
            if self.keys(node, path, ("next_turn",)) and self.enum(node["next_turn"], PLAYERS, path + ".next_turn"):
                self.use("duration:NEXT_TURN", path)
        elif isinstance(node, Mapping):
            super().duration(node, path)
        elif self.enum(node, DURATIONS_V02, path):
            self.use(f"duration:{node}", path)

    def modifier(self, node: Any, path: str, bound: set[str]) -> None:
        if isinstance(node, Mapping) and "cost" in node:
            cost = node["cost"]
            if self.keys(node, path, ("cost",)) and isinstance(cost, Mapping) and len(cost) == 1 and \
                    next(iter(cost)) in ("set", "reduce", "increase"):
                self.use("modifier:cost", path)
                amount = next(iter(cost.values()))
                self.non_negative(amount, path + ".cost")
                self.value(amount, path + ".cost", bound)
            else:
                self.err(path, "cost modifier takes exactly one of set/reduce/increase")
            return
        super().modifier(node, path, bound)

    # operations -----------------------------------------------------------------------------------------------------
    def op(self, node: Mapping[str, Any], path: str, bound: set[str]) -> set[str]:
        name = node["op"]
        if name not in _OPS_V02:
            self.err(path, f"unknown operation {name!r}")
            return bound
        required, optional = _OPS_V02[name]
        if not self.keys(node, path, ("op", *required), (*optional, "as")):
            return bound
        self.use(f"op:{name}", path)
        for key, value in node.items():
            sub = f"{path}.{key}"
            if key in ("to", "from"):
                self.selector(value, sub, bound, chosen_ok=(name == "CHOOSE"))
            elif key in ("amount", "count", "attack", "health", "reduce", "set", "increase", "spell_damage"):
                if key in ("reduce", "increase", "count"):
                    self.non_negative(value, sub)
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
            elif key == "options" and not _is_int(value):
                self.err(sub, "must be an integer")
            elif key == "uses":
                self.uses(value, sub)
            elif key == "use_unit":
                self.enum(value, ("CARD", "EFFECT"), sub)
            elif key == "position":
                if self.enum(value, DECK_POSITIONS, sub):
                    self.use(f"deck_position:{value}", sub)
            elif key == "zones":
                self.zones(value, sub)
            elif key == "starts_after":
                self.starts_after(value, sub)
        if name == "ENCHANT" and not set(node) & {"attack", "health", "keywords", "abilities", "spell_damage"}:
            self.err(path, "ENCHANT changes nothing")
        if name == "MODIFY_COST" and len(set(node) & {"reduce", "set", "increase"}) != 1:
            self.err(path, "MODIFY_COST takes exactly one of reduce/set/increase")
        if name == "ADD_PLAYER_EFFECT":
            self.player_effect(node, path)
        if name == "FREEZE":
            target = node["to"]
            if isinstance(target, Mapping) and "pick" in target and target.get("type") not in CHARACTER_TYPES:
                self.err(path + ".to", f"FREEZE targets characters, not {target.get('type')!r}")
            if target == "ENEMY_WEAPON":
                self.err(path + ".to", "FREEZE targets characters, not a weapon")
        if name == "ADD_TO_HAND":
            source = node["what"].get("from_zone") if isinstance(node["what"], Mapping) else None
            if isinstance(source, Mapping) and "pick" in source:
                zones = source.get("zone", "PLAY")
                if "PLAY" in (zones if isinstance(zones, list) else [zones]):
                    if source.get("type") != "MINION":
                        self.err(path + ".what", "a PLAY->HAND move is defined for minions only")
                    self.use("move:PLAY_TO_HAND", path)
        if "as" not in node:
            return bound
        self.bound_names.append((node["as"], path))
        return bound | {node["as"]}

    def uses(self, value: Any, path: str) -> None:
        if value == ALL_MATCHING:
            self.use("player_effect:ALL_MATCHING", path)
        elif not _is_int(value) or value < 1:
            self.err(path, f"uses must be a positive integer or {ALL_MATCHING!r}")

    def zones(self, value: Any, path: str) -> None:
        if not isinstance(value, list) or not value or len(set(map(str, value))) != len(value):
            self.err(path, "zones must be a non-empty list without repeats")
            return
        self.use("player_effect:zones", path)
        for zone in value:
            if self.enum(zone, ZONES, path):
                self.use(f"zone:{zone}", path)

    def starts_after(self, value: Any, path: str) -> None:
        if not self.keys(value, path, ("player", "turn_starts")):
            return
        self.use("player_effect:starts_after", path)
        self.enum(value["player"], PLAYERS, path + ".player")
        if not _is_int(value["turn_starts"]) or value["turn_starts"] < 1:
            self.err(path + ".turn_starts", "must be a positive integer")
        else:
            self.numbers.append(("", value["turn_starts"]))

    def player_effect(self, node: Mapping[str, Any], path: str) -> None:
        if len(set(node) & {"modifier", "abilities"}) != 1:
            self.err(path, "ADD_PLAYER_EFFECT takes a modifier or abilities")
        uses, duration = node.get("uses"), node.get("duration")
        if "modifier" in node and "uses" not in node:
            self.err(path, f"a modifier player effect states its cardinality: uses N or {ALL_MATCHING!r}")
        if uses == ALL_MATCHING:
            if "use_unit" in node:
                self.err(path, "use_unit belongs to integer uses")
            if duration == "UNTIL_USED":
                self.err(path, "ALL_MATCHING is never used up; UNTIL_USED needs integer uses")
        elif _is_int(uses):
            if "use_unit" not in node:
                self.err(path, "integer uses need a use_unit (CARD or EFFECT)")
            if duration == "THIS_GAME":
                self.err(path, "integer uses with THIS_GAME is UNTIL_USED")
        elif duration == "UNTIL_USED":
            self.err(path, "UNTIL_USED needs integer uses")
        has_cost = _has_cost(node.get("modifier"))
        if has_cost and "zones" not in node:
            self.err(path, "a cost player effect states the zones whose cards it modifies")
        if "zones" in node and not has_cost:
            self.err(path, "zones belong to a cost player effect")

    # abilities -------------------------------------------------------------------------------------------------------
    def ability(self, node: Any, path: str, *, nested: bool = False) -> None:
        super().ability(node, path, nested=nested)
        if isinstance(node, Mapping) and node.get("kind") == "trigger" and "condition" in node:
            # The v0.1 walker accepts a trigger condition without checking it (frozen loophole); v0.2 checks it.
            self.condition(node["condition"], path + ".condition", set())
        if nested or not isinstance(node, Mapping) or not isinstance(node.get("span"), str):
            return
        span = node["span"].lower()
        if _RANDOM_SPLIT.search(span):
            self.report.rules.add("R_RANDOM_SPLIT")
        elif _SPLIT.search(span):
            self.report.rules.update(("R_RANDOM_SPLIT", "R_SPLIT_UNQUALIFIED"))


def _check_decisions_v02(doc: Mapping[str, Any], walker: _WalkerV02, report: Report) -> None:
    """v0.1 decision rules with the v0.2 bases (USER_OBSERVED counts as a source)."""
    for index, decision in enumerate(doc["decisions"]):
        path = f"decisions[{index}]"
        if not walker.keys(decision, path, ("id", "question", "alternatives", "chosen", "basis", "risk"),
                           ("discriminating_case", "dep")):
            continue
        walker.enum(decision["basis"], DECISION_BASES_V02, path + ".basis")
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
        if decision["risk"] == "OUTCOME" and decision["basis"] in UNSOURCED and "dep" not in decision:
            report.errors.append(f"{path}: an outcome-changing reading without a source needs a dependency")
        if "dep" in decision:
            walker.dep(decision["dep"], path)
        if decision["risk"] != "NONE" and not decision.get("discriminating_case"):
            report.errors.append(f"{path}: a risky reading needs a discriminating case")


def validate_declaration_v02(doc: Mapping[str, Any], meta: Any) -> Report:
    """Validate one ``card-ir/0.2`` declaration against the pinned metadata ``meta`` (a ``CardMetadata``)."""
    report = Report(str(doc.get("card_id")) if isinstance(doc, Mapping) else "?")
    if not isinstance(doc, Mapping):
        report.errors.append("doc: expected an object")
        return report
    for key in ("abilities", "dependencies", "decisions", "keywords", "reminders", "unexpressed"):
        if key in doc and not isinstance(doc[key], list):
            report.errors.append(f"doc.{key}: must be an array")
    if report.errors:
        return report
    walker = _WalkerV02(doc if isinstance(doc, Mapping) else {}, meta, report)
    if not walker.keys(doc, "doc", ("ir", "card_id", "snapshot", "role", "text", "text_sha256", "abilities",
                                    "dependencies", "decisions", "status"),
                       ("keywords", "reminders", "unexpressed", "notes")):
        return report
    if doc["ir"] != IR_VERSION_V02:
        report.errors.append(f"doc: ir must be {IR_VERSION_V02} (v0.1 declarations are validated by v0.1 tools)")
        return report
    walker.enum(doc["role"], ROLES_V02, "doc.role")
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

    acknowledged: dict[str, str] = {}  # rule -> dependency id
    for index, dep in enumerate(doc["dependencies"]):
        path = f"dependencies[{index}]"
        if not walker.keys(dep, path, ("id", "kind", "scope", "detail", "source_needed"), ("card_level", "rule")):
            continue
        walker.enum(dep["kind"], DEP_KINDS, path + ".kind")
        walker.enum(dep["scope"], DEP_SCOPES, path + ".scope")
        if "rule" in dep:
            if dep["rule"] not in PROVISIONAL_RULES:
                report.errors.append(f"{path}: rule {dep['rule']!r} is not a provisional v0.2 rule")
            elif dep["kind"] != "UNKNOWN_RULE" or dep["scope"] not in ("CONDITIONAL", "CORE"):
                report.errors.append(f"{path}: a rule acknowledgement is an UNKNOWN_RULE with scope CONDITIONAL/CORE")
            elif dep["rule"] in acknowledged:
                report.errors.append(f"{path}: rule {dep['rule']!r} is already acknowledged")
            else:
                acknowledged[dep["rule"]] = dep["id"]
    _check_decisions_v02(doc, walker, report)

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

    for name, path in walker.bound_names:
        if name not in walker.used_names:
            report.errors.append(f"{path}: {name!r} is bound but never used")
    needed = report.rules & PROVISIONAL_RULES
    for rule in sorted(needed - set(acknowledged)):
        report.errors.append(f"dependencies: provisional rule {rule} needs an UNKNOWN_RULE dependency with "
                             f"rule {rule!r}")
    for rule, dep_id in sorted(acknowledged.items()):
        if rule in needed:
            walker.used_deps.add(dep_id)
        else:
            report.errors.append(f"dependencies: {dep_id!r} acknowledges {rule}, which the declaration does not need")
    for dep_id, dep in walker.deps.items():
        if dep_id not in walker.used_deps and not dep.get("card_level"):
            report.errors.append(f"dependencies: {dep_id!r} is declared but never referenced (mark card_level)")
    sourced = sorted(e for e in report.elements if ELEMENTS_V02[e].needs_source)
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
    report.rules &= set(RULES_V02)
    return report


def extract_elements_v02(doc: Mapping[str, Any], meta: Any) -> Counter:
    """Elements of a valid v0.2 declaration; raises ``IRError`` for an invalid one."""
    report = validate_declaration_v02(doc, meta)
    if report.errors:
        raise IRError(f"{doc.get('card_id')}: {report.errors[:3]}")
    return report.elements
