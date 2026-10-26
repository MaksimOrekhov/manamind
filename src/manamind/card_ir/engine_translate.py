"""Card IR v0.2 -> ManaEngine effect steps (CARD-IR-EXECUTION-PILOT-1, experimental).

A pure, card-independent translation of a small allowlisted subset of ``card-ir/0.2`` into the existing generic
``EFFECT_COMPOSITION`` step vocabulary of ManaEngine. Nothing here imports the native engine, and nothing reads a card
ID to decide behaviour: every step comes from an IR node, and every IR node or field that is not understood stops the
translation with a typed :class:`TranslationRefused`. A refused card is never approximated.

The translation relies on a few explicit equivalences between IR semantics and the engine's step semantics. Each one
used by a card is recorded in :attr:`EngineSpec.assumptions`, so a reader can see what the executed result rests on.
Validation (``validate_strict_v02``) is a separate gate that callers apply first; see
``compile_declaration`` in ``reports/card_ir_execution_pilot_1/engine_bridge.py``.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

IR_VERSION = "card-ir/0.2"

# (op, target type, target side) of a CHOSEN target -> explicit engine selector. Native legality is derived from the
# selector, so a side or type the engine cannot express exactly is refused instead of widened or narrowed.
_CHOSEN = {
    ("DEAL_DAMAGE", "CHARACTER", "ANY"): "EXPLICIT_CHARACTER",
    ("DEAL_DAMAGE", "CHARACTER", "ENEMY"): "EXPLICIT_ENEMY_CHARACTER",
    ("DEAL_DAMAGE", "MINION", "ANY"): "EXPLICIT_MINION",
    ("RESTORE_HEALTH", "CHARACTER", "ANY"): "EXPLICIT_CHARACTER",
    ("RESTORE_HEALTH", "CHARACTER", "FRIENDLY"): "EXPLICIT_FRIENDLY_CHARACTER",
}
# (op, type, side) of an ALL selector in PLAY -> area selector (R_AREA_SNAPSHOT: members fixed when the step starts).
_AREA = {
    ("DEAL_DAMAGE", "MINION", "ENEMY"): "ENEMY_MINIONS",
    ("DEAL_DAMAGE", "CHARACTER", "ENEMY"): "ENEMY_CHARACTERS",
    ("DEAL_DAMAGE", "MINION", "ANY"): "ALL_MINIONS",
    ("DEAL_DAMAGE", "CHARACTER", "ANY"): "ALL_CHARACTERS",
    ("RESTORE_HEALTH", "CHARACTER", "FRIENDLY"): "ALL_FRIENDLY_CHARACTERS",
    ("ENCHANT", "MINION", "FRIENDLY"): "SELF",
}
_ENGINE_KIND = {"DEAL_DAMAGE": "DAMAGE", "RESTORE_HEALTH": "HEAL", "ENCHANT": "BUFF_FRIENDLY_MINIONS"}
# The engine adds Spell Damage to every spell Damage step and the healing bonus to every Heal step, so the IR amount
# must carry exactly that modifier mark; an unmarked amount cannot be executed faithfully.
_MARK = {"DEAL_DAMAGE": "$", "RESTORE_HEALTH": "#"}
_DISCARD_SCHOOLS = {"NATURE", "FIRE"}
# Steps after which a set bound by `as` is still exactly "every friendly minion": they never add, remove or kill one.
_BOARD_NEUTRAL = {"DISCARD_RANDOM_SPELL"}
_MAX_AMOUNT = 1000


class TranslationRefused(ValueError):
    """The declaration (or a part of it) has no faithful translation; nothing may be executed for it."""

    def __init__(self, code: str, path: str, detail: str = "") -> None:
        super().__init__(f"{code} at {path}" + (f": {detail}" if detail else ""))
        self.code = code
        self.path = path
        self.detail = detail


@dataclass(frozen=True)
class EngineStep:
    """One native ``EffectStep`` plus the IR path that produced it."""

    kind: str
    target: str
    amount: int
    source: str
    lifesteal: bool = False
    discard_school: str = "NONE"
    requires_previous_discard: bool = False

    def declaration(self) -> dict[str, Any]:
        """The step in ``card_abilities.json`` form (optional fields only when set), for comparison and parsing."""
        row: dict[str, Any] = {"kind": self.kind, "target": self.target, "amount": self.amount}
        if self.lifesteal:
            row["lifesteal"] = True
        if self.discard_school != "NONE":
            row["discard_school"] = self.discard_school
        if self.requires_previous_discard:
            row["requires_previous_discard"] = True
        return row


@dataclass(frozen=True)
class EngineSpec:
    card_id: str
    text: str
    text_sha256: str
    steps: tuple[EngineStep, ...]
    overload: int = 0
    keywords: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    ability: str = "EFFECT_COMPOSITION"

    def declaration(self) -> dict[str, Any]:
        return {"ability": self.ability, "effects": [step.declaration() for step in self.steps], "overload": self.overload}


@dataclass
class _Context:
    bound_target: tuple[str, str] | None = None  # (type, side) of the ability's CHOSEN target
    bound_target_name: str | None = None
    target_used: bool = False
    sets: dict[str, tuple[str, int]] = field(default_factory=dict)  # `as` name -> (area selector, index of its step)
    steps: list[EngineStep] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def _keys(node: Any, path: str, required: set[str], optional: set[str] = frozenset()) -> Mapping[str, Any]:
    if not isinstance(node, Mapping):
        raise TranslationRefused("SHAPE", path, "expected an object")
    missing = required - set(node)
    unknown = set(node) - required - set(optional)
    if missing:
        raise TranslationRefused("SHAPE", path, f"missing {sorted(missing)}")
    if unknown:
        raise TranslationRefused("UNKNOWN_FIELD", path, f"untranslated fields {sorted(unknown)}")
    return node


def _amount(node: Any, op: str, path: str) -> int:
    value = _keys(node, path, {"n", "mark"})
    n = value["n"]
    if isinstance(n, bool) or not isinstance(n, int) or not 0 < n <= _MAX_AMOUNT:
        raise TranslationRefused("UNSUPPORTED_AMOUNT", path, "only a positive integer literal is executable")
    if value["mark"] != _MARK[op]:
        raise TranslationRefused("UNSUPPORTED_AMOUNT", path, f"{op} needs mark {_MARK[op]!r}")
    return n


def _selector(node: Any, op: str, ctx: _Context, path: str) -> tuple[str, str | None]:
    """Return (engine selector, name of the reused set or None)."""
    if isinstance(node, Mapping) and set(node) == {"ref"}:
        name = node["ref"]
        if ctx.bound_target is not None and name == ctx.bound_target_name:
            selector = _CHOSEN.get((op, *ctx.bound_target))
            if selector is None:
                raise TranslationRefused("UNSUPPORTED_SELECTOR", path, f"no explicit selector for {op} on {ctx.bound_target}")
            ctx.target_used = True
            return selector, None
        if name in ctx.sets:
            return _reuse_set(name, op, ctx, path), name
        raise TranslationRefused("UNBOUND_REF", path, f"{name!r} is not bound before this step")
    sel = _keys(node, path, {"pick", "type", "side"}, {"zone"})
    if sel["pick"] != "ALL" or sel.get("zone", "PLAY") != "PLAY":
        raise TranslationRefused("UNSUPPORTED_SELECTOR", path, "only an ALL selection in PLAY maps onto an engine area")
    selector = _AREA.get((op, sel["type"], sel["side"]))
    if selector is None:
        raise TranslationRefused("UNSUPPORTED_SELECTOR", path, f"no engine area for {op} on {sel['type']}/{sel['side']}")
    return selector, None


def _reuse_set(name: str, op: str, ctx: _Context, path: str) -> str:
    """A bound set equals a fresh selection only while nothing in between can change its membership."""
    selector, index = ctx.sets[name]
    between = ctx.steps[index + 1:]
    if op != "ENCHANT" or selector != "SELF" or any(step.kind not in _BOARD_NEUTRAL for step in between):
        raise TranslationRefused("REF_NOT_EQUIVALENT", path,
                                 f"{name!r} cannot be re-selected: a step in between may change the set")
    ctx.assumptions.append(f"REF_RESELECT_EQUIVALENT:{name}")
    return selector


def _op(node: Mapping[str, Any], ctx: _Context, path: str) -> list[EngineStep]:
    op = node.get("op")
    if op in ("DEAL_DAMAGE", "RESTORE_HEALTH"):
        _keys(node, path, {"op", "to", "amount"})
        amount = _amount(node["amount"], op, f"{path}/amount")
        selector, _ = _selector(node["to"], op, ctx, f"{path}/to")
        return [EngineStep(_ENGINE_KIND[op], selector, amount, path)]
    if op == "ENCHANT":
        _keys(node, path, {"op", "to", "attack", "health"}, {"enchantment_id", "as"})
        attack, health = node["attack"], node["health"]
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (attack, health)) or attack != health or attack <= 0:
            raise TranslationRefused("UNSUPPORTED_STATS", path, "the engine buff adds the same positive Attack and Health")
        if any(step.kind == "DAMAGE" for step in ctx.steps):
            # BUFF_FRIENDLY_MINIONS skips mortally wounded minions; R_AREA_SNAPSHOT includes them.
            raise TranslationRefused("AREA_AFTER_DAMAGE", path, "a buff area after damage may differ on mortally wounded minions")
        selector, _ = _selector(node["to"], op, ctx, f"{path}/to")
        if "enchantment_id" in node:
            ctx.assumptions.append("ENCHANTMENT_AS_BASE_STATS")
        step = EngineStep(_ENGINE_KIND[op], selector, attack, path)
        if "as" in node:
            if not isinstance(node["as"], str) or node["as"] in ctx.sets or node["as"] == ctx.bound_target_name:
                raise TranslationRefused("SHAPE", f"{path}/as", "set names must be unique strings")
            ctx.sets[node["as"]] = (selector, len(ctx.steps))
        return [step]
    raise TranslationRefused("UNSUPPORTED_OP", path, f"operation {op!r} has no engine step in this pilot")


def _pay(node: Mapping[str, Any], ctx: _Context, path: str) -> list[EngineStep]:
    _keys(node, path, {"pay", "then"})
    cost = _keys(node["pay"], f"{path}/pay", {"discard"})
    sel = _keys(cost["discard"], f"{path}/pay/discard", {"pick", "n", "type", "side", "zone", "where"})
    where = sel["where"]
    if (sel["pick"], sel["n"], sel["type"], sel["side"], sel["zone"]) != ("RANDOM", 1, "SPELL", "FRIENDLY", "HAND") or \
            not isinstance(where, list) or len(where) != 1 or not isinstance(where[0], Mapping) or \
            set(where[0]) != {"spell_school"} or where[0]["spell_school"] not in _DISCARD_SCHOOLS:
        raise TranslationRefused("UNSUPPORTED_PAYMENT", f"{path}/pay",
                                 "only 'discard one random friendly spell of a supported school' is executable")
    discard = EngineStep("DISCARD_RANDOM_SPELL", "SELF", 0, f"{path}/pay", discard_school=where[0]["spell_school"])
    ctx.steps.append(discard)
    then = _effect(node["then"], ctx, f"{path}/then")
    ctx.steps.pop()
    if len(then) != 1:
        # The engine conditions only the single step that directly follows a discard (R_PAYMENT).
        raise TranslationRefused("UNSUPPORTED_PAYMENT", f"{path}/then", "a paid effect must be exactly one step")
    paid = then[0]
    return [discard, EngineStep(paid.kind, paid.target, paid.amount, paid.source, paid.lifesteal, paid.discard_school, True)]


def _effect(node: Any, ctx: _Context, path: str) -> list[EngineStep]:
    if not isinstance(node, Mapping):
        raise TranslationRefused("SHAPE", path, "expected an effect object")
    if "seq" in node:
        _keys(node, path, {"seq"})
        if not isinstance(node["seq"], list) or not node["seq"]:
            raise TranslationRefused("EMPTY_EFFECT", path, "seq needs steps")
        out: list[EngineStep] = []
        base = len(ctx.steps)
        for i, child in enumerate(node["seq"]):
            produced = _effect(child, ctx, f"{path}/seq/{i}")
            ctx.steps.extend(produced)
            out.extend(produced)
        del ctx.steps[base:]
        return out
    if "pay" in node:
        return _pay(node, ctx, path)
    if "op" in node:
        return _op(node, ctx, path)
    raise TranslationRefused("UNSUPPORTED_CONTROL", path, f"no executable control in {sorted(node)}")


def translate(doc: Mapping[str, Any]) -> EngineSpec:
    """Translate one already-validated declaration. Raises :class:`TranslationRefused` for anything untranslatable."""
    doc = _keys(doc, "doc", {"ir", "card_id", "snapshot", "role", "text", "text_sha256", "abilities", "dependencies",
                             "decisions", "status"}, {"keywords", "reminders", "unexpressed", "notes"})
    if doc["ir"] != IR_VERSION:
        raise TranslationRefused("VERSION", "doc/ir", f"only {IR_VERSION} is translated")
    if doc["status"] != "FULL":
        raise TranslationRefused("STATUS_NOT_FULL", "doc/status", "FULL_DEP/PARTIAL need dependency handling")
    for section in ("dependencies", "reminders", "unexpressed"):
        if doc.get(section):
            raise TranslationRefused("UNTRANSLATED_SECTION", f"doc/{section}", "must be empty for execution")
    abilities = doc["abilities"]
    if not isinstance(abilities, list) or len(abilities) != 1:
        raise TranslationRefused("ABILITY_COUNT", "doc/abilities", "exactly one ability is executable in this pilot")
    ability = _keys(abilities[0], "doc/abilities/0", {"kind", "label", "span", "effect"}, {"target"})
    if (ability["kind"], ability["label"]) != ("play", "SPELL"):
        raise TranslationRefused("ABILITY_KIND", "doc/abilities/0", "only a played spell is executable")
    ctx = _Context()
    if "target" in ability:
        target = _keys(ability["target"], "doc/abilities/0/target", {"bind", "choose"})
        choose = _keys(target["choose"], "doc/abilities/0/target/choose", {"pick", "type", "side"})
        if choose["pick"] != "CHOSEN" or not isinstance(target["bind"], str):
            raise TranslationRefused("UNSUPPORTED_SELECTOR", "doc/abilities/0/target", "a play target must be CHOSEN")
        ctx.bound_target = (choose["type"], choose["side"])
        ctx.bound_target_name = target["bind"]
    steps = _effect(ability["effect"], ctx, "doc/abilities/0/effect")
    if ctx.bound_target is not None and not ctx.target_used:
        raise TranslationRefused("UNUSED_TARGET", "doc/abilities/0/target", "a chosen target no step uses")
    overload, keywords = 0, []
    for i, raw in enumerate(doc.get("keywords", [])):
        path = f"doc/keywords/{i}"
        name = raw.get("keyword") if isinstance(raw, Mapping) else None
        if name == "OVERLOAD":
            item = _keys(raw, path, {"keyword", "span", "amount"})
            if isinstance(item["amount"], bool) or not isinstance(item["amount"], int) or not 0 < item["amount"] <= 10:
                raise TranslationRefused("UNSUPPORTED_KEYWORD", path, "Overload needs an amount within 1..10")
            overload = item["amount"]
        elif name == "LIFESTEAL":
            _keys(raw, path, {"keyword", "span"})
            damage = [n for n, step in enumerate(steps) if step.kind == "DAMAGE"]
            if not damage:
                raise TranslationRefused("UNSUPPORTED_KEYWORD", path, "Lifesteal on a spell needs a damage step")
            # A spell's Lifesteal heals its controller's hero for the damage each of its packets deals.
            steps = [EngineStep(s.kind, s.target, s.amount, s.source, True, s.discard_school, s.requires_previous_discard)
                     if n in damage else s for n, s in enumerate(steps)]
        else:
            raise TranslationRefused("UNSUPPORTED_KEYWORD", path, f"keyword {name!r} is not executable in this pilot")
        if name in keywords:
            raise TranslationRefused("SHAPE", path, "duplicate keyword")
        keywords.append(name)
    if not steps:
        raise TranslationRefused("EMPTY_EFFECT", "doc/abilities/0/effect", "nothing to execute")
    return EngineSpec(str(doc["card_id"]), str(doc["text"]), str(doc["text_sha256"]), tuple(steps), overload,
                      tuple(keywords), tuple(dict.fromkeys(ctx.assumptions)))
