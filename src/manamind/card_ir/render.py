"""Deterministic rendering of a Card IR declaration back into plain English, for human review.

The rendering is mechanical and verbose on purpose: it shows what the declaration says, including the defaults a
reader of the card text fills in silently (who may be targeted, whether a pick is random, what a reference points to).
It is a reading aid, not a check that the reading is right: an ordering error that reads the same in English survives.
"""

from __future__ import annotations

from typing import Any, Mapping

_PLAYER = {"SELF": "you", "OPPONENT": "the opponent"}
_SHORT = {"SELF": "this", "ENEMY_HERO": "the enemy hero", "ENEMY_WEAPON": "the enemy weapon"}
_PLAY_LABEL = {"SPELL": "Cast", "BATTLECRY": "Battlecry", "LOCATION": "Activate", "KINDRED": "Kindred (on play)"}
_ACTIVE = {"HAND": "In hand", "PLAY": "In play", "EQUIPPED": "While equipped"}


def _name(meta: Any, card_id: str) -> str:
    record = meta.get(card_id) if meta is not None else None
    return f"{record.get('name')} [{card_id}]" if record else f"[{card_id}]"


class _Renderer:
    def __init__(self, meta: Any) -> None:
        self.meta = meta

    def value(self, node: Any) -> str:
        if isinstance(node, int):
            return str(node)
        if "mark" in node:
            return f"{node['mark']}{node['n']}"
        if "stat" in node:
            when = " (last known)" if node.get("at") == "LAST_KNOWN" else ""
            return f"{self.selector(node['of'])}'s {node['stat'].lower()}{when}"
        if "counter" in node:
            counter = node["counter"]
            what = "spells cast" if counter["event"] == "SPELL_CAST" else "cards played"
            distinct = "distinct " if counter.get("distinct") else ""
            scope = counter["scope"].lower().replace("_", " ")
            return f"number of {distinct}{what}{self.where(counter.get('where', []))} by {_PLAYER[counter['player']]} {scope}"
        if "var" in node:
            return node["var"]
        if "max" in node:
            return f"max({self.value(node['max'][0])}, {self.value(node['max'][1])})"
        if "sub" in node:
            return f"({self.value(node['sub'][0])} - {self.value(node['sub'][1])})"
        if "add" in node:
            return f"({self.value(node['add'][0])} + {self.value(node['add'][1])})"
        return f"<UNKNOWN: {node['unknown']}>"

    def where(self, preds: list) -> str:
        parts = []
        for pred in preds:
            kind = next(iter(pred))
            if kind == "keyword":
                parts.append(f"with {pred['keyword'].title()}")
            elif kind == "cost":
                parts.append(f"costing {pred['cost']['cmp']} {pred['cost']['n']}")
            elif kind == "damaged":
                parts.append("damaged" if pred["damaged"] else "undamaged")
            elif kind == "named":
                names = pred["named"] if isinstance(pred["named"], list) else [pred["named"]]
                parts.append(f"named {' or '.join(names)} {pred['ids']}")
            else:
                parts.append(f"{kind.replace('_', ' ')} {pred[kind]}")
        return (" " + ", ".join(parts)) if parts else ""

    def selector(self, node: Any, *, one: bool = False) -> str:
        """``one``: read an ALL selector as 'a ...' (existence, event subjects)."""
        if isinstance(node, str):
            return _SHORT[node]
        if "ref" in node:
            return f"them<{node['ref']}>"
        if one and node["pick"] == "ALL":
            node = {**node, "pick": "ONE"}
        pick = {"ALL": "all", "RANDOM": "random", "CHOSEN": "a chosen", "ONE": "a"}[node["pick"]]
        count = f" {self.value(node['n'])}" if "n" in node and node["pick"] == "RANDOM" else ""
        side = {"FRIENDLY": " friendly", "ENEMY": " enemy", "ANY": ""}[node["side"]]
        zones = node.get("zone", "PLAY")
        zones = zones if isinstance(zones, list) else [zones]
        zone = "" if zones == ["PLAY"] else " in " + " and ".join(z.lower() for z in zones)
        exclude = " except " + ", ".join(self.selector(item) for item in node["exclude"]) if "exclude" in node else ""
        noun = node["type"].lower() + ("s" if node["pick"] == "ALL" else "")
        return f"{pick}{count}{side} {noun}{self.where(node.get('where', []))}{zone}{exclude}"

    def source(self, node: Mapping[str, Any]) -> str:
        if "card" in node:
            how = "" if node["resolved"] == "UNIQUE_NAME" else f" (resolved by {node['resolved'].lower()})"
            return _name(self.meta, node["card"]) + how
        if "copy_of" in node:
            return f"a copy of {self.selector(node['copy_of'])}"
        if "random_from" in node:
            return f"a random {self.pool(node['random_from'])}"
        if "all_from" in node:
            rest = " except " + ", ".join(self.selector(item) for item in node.get("exclude", [])) if node.get("exclude") else ""
            return f"every {self.pool(node['all_from'])}{rest}"
        return f"{self.selector(node['from_zone'])}"

    def pool(self, node: Mapping[str, Any]) -> str:
        return f"{node['type'].lower()}{self.where(node['where'])} from pool <{node['dep']}>"

    def modifier(self, node: Any) -> str:
        if isinstance(node, list):
            return " and ".join(self.modifier(item) for item in node)
        if "cost" in node:
            how, amount = next(iter(node["cost"].items()))
            return f"cost set to {self.value(amount)}" if how == "set" else f"cost reduced by {self.value(amount)}"
        if "rule" in node:
            factor = f" x{node['factor']}" if "factor" in node else ""
            return f"rule {node['rule']}{factor}"
        return f"Spell Damage +{self.value(node['spell_damage'])}"

    def condition(self, node: Mapping[str, Any]) -> str:
        kind = next(iter(node))
        if kind == "cmp":
            left, op, right = node["cmp"]
            return f"{self.value(left)} {op} {self.value(right)}"
        if kind == "exists":
            return f"there is {self.selector(node['exists'], one=True)}"
        if kind == "is":
            return f"{self.selector(node['is']['entity'])} is{self.where(node['is']['where'])}"
        return f"{node['mechanic'].title()} holds"

    def event(self, node: Mapping[str, Any]) -> str:
        if "unknown" in node:
            return f"<UNKNOWN event: {node['unknown']}>"
        kind, player = node["type"], _PLAYER.get(node.get("player", ""), "")
        if kind == "HERO_ATTACK":
            return f"{'your' if player == 'you' else 'a'} hero attacks"
        if kind == "CARD_DRAWN":
            return f"{player} draw a card"
        if kind == "TURN_END":
            return "the end of your turn" if player == "you" else "the end of the turn"
        if kind == "DAMAGE_TAKEN":
            return f"{self.selector(node['subject'])} takes damage"
        if kind == "DAMAGE_DEALT":
            return f"{player} deal damage with{self.where(node.get('source', []))}"
        return f"{self.selector(node['defender'], one=True)} is attacked"

    def effect(self, node: Mapping[str, Any]) -> str:
        if "seq" in node:
            return "; then ".join(self.effect(step) for step in node["seq"])
        if "if" in node:
            other = f"; otherwise {self.effect(node['else'])}" if "else" in node else ""
            return f"if {self.condition(node['if'])}: {self.effect(node['then'])}{other}"
        if "repeat" in node:
            return f"repeat {self.value(node['repeat'])} times: [{self.effect(node['do'])}]"
        if "repeat_while" in node:
            bound = self.value(node["max"]) if isinstance(node["max"], Mapping) else node["max"]
            return f"while {self.condition(node['repeat_while'])} (at most {bound}): [{self.effect(node['do'])}]"
        if "set" in node:
            ((name, value),) = node["set"].items()
            return f"let {name} = {self.value(value)}"
        if "pay" in node:
            cost = node["pay"]
            what = (f"{self.value(cost['amount'])} {cost['resource'].title()}" if "resource" in cost
                    else f"a discard of {self.selector(cost['discard'])}")
            return f"if you can pay {what}, pay it and {self.effect(node['then'])}"
        return self.op(node)

    def op(self, node: Mapping[str, Any]) -> str:
        name, bind = node["op"], f" as <{node['as']}>" if "as" in node else ""
        count = f"{self.value(node['count'])} x " if "count" in node else ""
        if name == "DEAL_DAMAGE":
            return f"deal {self.value(node['amount'])} damage to {self.selector(node['to'])}"
        if name == "RESTORE_HEALTH":
            return f"restore {self.value(node['amount'])} Health to {self.selector(node['to'])}"
        if name == "ENCHANT":
            parts = []
            if "attack" in node or "health" in node:
                parts.append(f"+{self.value(node.get('attack', 0))}/+{self.value(node.get('health', 0))}")
            parts += [keyword.title() for keyword in node.get("keywords", [])]
            if "spell_damage" in node:
                parts.append(f"Spell Damage +{self.value(node['spell_damage'])}")
            parts += [f"'{self.ability(ability)}'" for ability in node.get("abilities", [])]
            duration = f" ({self.duration(node['duration'])})" if "duration" in node else ""
            return f"give {self.selector(node['to'])} {', '.join(parts)}{duration}{bind}"
        if name in ("SILENCE", "DESTROY"):
            return f"{name.lower()} {self.selector(node['to'])}"
        if name == "TRANSFORM":
            return f"transform {self.selector(node['to'])} into {self.source(node['into'])}"
        if name == "SUMMON":
            return f"summon {count}{self.source(node['what'])}{bind}"
        if name == "DRAW":
            return f"{_PLAYER[node['player']]} draw {count}card{self.where(node.get('where', []))}"
        if name == "ADD_TO_HAND":
            return f"{_PLAYER[node['player']]} get {count}{self.source(node['what'])}{bind}"
        if name == "DISCOVER":
            return f"discover ({node.get('options', '?')} options) a {self.pool(node['pool'])}{bind}"
        if name == "CHOOSE":
            return f"you choose {self.selector(node['from'])}{bind}"
        if name == "MODIFY_COST":
            how = f"set to {self.value(node['set'])}" if "set" in node else f"reduced by {self.value(node['reduce'])}"
            return f"cost of {self.selector(node['to'])} {how}"
        if name == "ADD_PLAYER_EFFECT":
            what = (self.modifier(node["modifier"]) if "modifier" in node
                    else "; ".join(f"'{self.ability(ability)}'" for ability in node["abilities"]))
            applies = f" for the next card{self.where(node['applies_to'])}" if "applies_to" in node else ""
            uses = f", {node['uses']} use ({node.get('use_unit', '?').lower()})" if "uses" in node else ""
            return f"{_PLAYER[node['player']]} get a player effect: {what}{applies}, {self.duration(node['duration'])}{uses}"
        if name == "SHUFFLE_INTO_DECK":
            return f"shuffle {self.source(node['what'])} into {_PLAYER[node['player']]}r deck"
        return f"cast {count}{self.source(node['what'])}"

    def duration(self, node: Any) -> str:
        if isinstance(node, Mapping):
            return f"for {node['turns']} turns"
        return {"THIS_TURN": "this turn", "UNTIL_USED": "until used"}[node]

    def ability(self, node: Mapping[str, Any]) -> str:
        kind = node["kind"]
        if kind == "play":
            target = f"choose {self.selector(node['target']['choose'])} as <{node['target']['bind']}>; " if "target" in node else ""
            condition = f"if {self.condition(node['condition'])}: " if "condition" in node else ""
            return f"{_PLAY_LABEL[node['label']]}: {target}{condition}{self.effect(node['effect'])}"
        if kind == "trigger":
            timing = {"AFTER": "After", "WHENEVER": "Whenever", "AT": "At", "WHEN": "When"}[node["timing"]]
            label = "Secret: " if node.get("label") == "SECRET" else ""
            limit = " (first time each turn only)" if node.get("limit") else ""
            return f"{label}{timing} {self.event(node['event'])}{limit}: {self.effect(node['effect'])}"
        if kind == "deathrattle":
            return f"Deathrattle: {self.effect(node['effect'])}"
        if kind == "aura":
            condition = f" while {self.condition(node['while'])}" if "while" in node else ""
            return f"{_ACTIVE[node['active_in']]}: {self.modifier(node['modifier'])}{condition}"
        if kind == "quest":
            return (f"Quest: progress on {self.event(node['progress']['event'])}, goal {node['progress']['goal']}; "
                    f"reward {self.source(node['reward'])}")
        stats = [f"+{node[key]} {key.title()}" for key in ("attack", "health") if key in node]
        return f"{node['context'].replace('_', ' ').title()} option: {', '.join(stats + [k.title() for k in node.get('keywords', [])])}"


def render(doc: Mapping[str, Any], meta: Any = None) -> list[str]:
    """One line per keyword, ability and unexpressed span."""
    renderer = _Renderer(meta)
    lines = []
    for keyword in doc.get("keywords", []):
        amount = f" {keyword['amount']}" if "amount" in keyword else ""
        parts = " with " + ", ".join(renderer.source(part) for part in keyword["parts"]) if keyword.get("parts") else ""
        lines.append(f"Keyword {keyword['keyword'].title()}{amount}{parts}")
    lines += [renderer.ability(ability) for ability in doc.get("abilities", [])]
    lines += [f"NOT EXPRESSED: {item['span']}" for item in doc.get("unexpressed", [])]
    return lines
