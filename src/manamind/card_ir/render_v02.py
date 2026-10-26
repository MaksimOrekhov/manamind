"""Rendering of Card IR v0.2 declarations: the v0.1 renderers plus the v0.2 nodes.

``_V02`` handles only v0.2 nodes and falls back to the v0.1 renderer for everything else. It is mixed into both the
plain renderer (``render_v02``) and the audit renderer (``audit_render.render_audit`` dispatches on ``ir``). Defaults
that change meaning are always spelled out: the uses of a player effect, its zones, its start, its window, the deck
position, attack roles and PLAY->HAND moves.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from manamind.card_ir.audit_render import _AuditRenderer
from manamind.card_ir.render import _PLAYER, _Renderer

_OWNER = {"SELF": "your", "OPPONENT": "the opponent's"}


class _V02:
    def value(self, node: Any) -> str:
        if isinstance(node, Mapping) and "mul" in node:
            return f"({self.value(node['mul'][0])} x {self.value(node['mul'][1])})"
        if isinstance(node, Mapping) and isinstance(node.get("counter"), Mapping) and \
                node["counter"].get("event") == "DAMAGE_DEALT":
            counter = node["counter"]
            source = self.where(counter.get("source", [])) or " any source"
            scope = counter["scope"].lower().replace("_", " ")
            return (f"total damage actually dealt ({counter['measure']}) by {_PLAYER[counter['player']]} "
                    f"with{source} {scope}")
        return super().value(node)

    def where(self, preds: list) -> str:
        alive = [p for p in preds if isinstance(p, Mapping) and "alive" in p]
        rest = [p for p in preds if p not in alive]
        text = super().where(rest)
        words = ["alive (survived)" if p["alive"] else "not alive (did not survive)" for p in alive]
        return text + ((", " if text else " ") + ", ".join(words) if words else "")

    def event(self, node: Mapping[str, Any]) -> str:
        if node.get("type") != "ATTACK_DECLARED" or "subject" in node:
            return super().event(node)
        attacker = self.selector(node["attacker"], one=True) if "attacker" in node else "any character"
        defender = self.selector(node["defender"], one=True) if "defender" in node else "any character"
        return f"attacker {attacker} attacks defender {defender}"

    def duration(self, node: Any) -> str:
        if node == "THIS_GAME":
            return "for the rest of the game"
        if isinstance(node, Mapping) and "next_turn" in node:
            return f"during {_OWNER[node['next_turn']]} next turn (start to end)"
        return super().duration(node)

    def modifier(self, node: Any) -> str:
        if isinstance(node, Mapping) and isinstance(node.get("cost"), Mapping) and "increase" in node["cost"]:
            return f"cost increased by {self.value(node['cost']['increase'])}"
        return super().modifier(node)

    def op(self, node: Mapping[str, Any]) -> str:
        name = node["op"]
        bind = f" as <{node['as']}>" if "as" in node else ""
        if name == "FREEZE":
            return f"freeze {self.selector(node['to'])}{bind}"
        if name == "MODIFY_COST" and "increase" in node:
            return f"cost of {self.selector(node['to'])} increased by {self.value(node['increase'])}"
        if name == "SHUFFLE_INTO_DECK":
            count = f"{self.value(node['count'])} x " if "count" in node else ""
            position = node.get("position", "RANDOM")
            where = {"RANDOM": "shuffle into", "TOP": "put on top of", "BOTTOM": "put on the bottom of"}[position]
            return f"{where} {_PLAYER[node['player']]}r deck: {count}{self.source(node['what'])} [position={position}]"
        if name == "ADD_PLAYER_EFFECT":
            return self.player_effect(node)
        text = super().op(node)
        if name == "ADD_TO_HAND" and "pick" in node["what"].get("from_zone", {}):
            text += " [move PLAY->HAND: state reset R_RETURN_TO_HAND; full hand R_RETURN_FULL_HAND]"
        return text

    def player_effect(self, node: Mapping[str, Any]) -> str:
        what = (self.modifier(node["modifier"]) if "modifier" in node
                else "; ".join(f"'{self.ability(ability)}'" for ability in node["abilities"]))
        uses = node.get("uses")
        if uses == "ALL_MATCHING":
            cardinality = "every matching card while active, including later arrivals"
        elif uses is not None:
            cardinality = f"the next {uses} matching {node.get('use_unit', '?').lower()}(s)"
        else:
            cardinality = "attached abilities (no use limit)"
        filters = self.where(node.get("applies_to", [])) or " any card"
        zones = f"; zones={','.join(node['zones'])}" if "zones" in node else ""
        start = node.get("starts_after")
        when = (f"inactive until the start of {_OWNER[start['player']]} turn number {start['turn_starts']} after it "
                f"is created" if start else "active immediately")
        return (f"{_PLAYER[node['player']]} get a player effect: {what}; applies to{filters}: {cardinality}{zones}; "
                f"{when}; {self.duration(node['duration'])}")


class RendererV02(_V02, _Renderer):
    def ability(self, node):
        text = super().ability(node)
        if node["kind"] == "trigger" and "condition" in node:
            # The v0.1 plain render omits trigger conditions; v0.2 never hides them.
            effect = self.effect(node["effect"])
            return f"{text[:-len(effect) - 2]}, only if {self.condition(node['condition'])}: {effect}"
        return text


class AuditRendererV02(_V02, _AuditRenderer):
    def op(self, node):
        result = super().op(node)
        if "enchantment_id" in node and "[enchantment=" not in result:
            result += f" [enchantment={node['enchantment_id']}]"
        return result


def render_v02(doc: Mapping[str, Any], meta: Any = None) -> list[str]:
    """One line per keyword, ability and unexpressed span (the v0.1 layout)."""
    renderer = RendererV02(meta)
    lines = []
    for keyword in doc.get("keywords", []):
        amount = f" {keyword['amount']}" if "amount" in keyword else ""
        parts = " with " + ", ".join(renderer.source(part) for part in keyword["parts"]) if keyword.get("parts") else ""
        lines.append(f"Keyword {keyword['keyword'].title()}{amount}{parts}")
    lines += [renderer.ability(ability) for ability in doc.get("abilities", [])]
    lines += [f"NOT EXPRESSED: {item['span']}" for item in doc.get("unexpressed", [])]
    return lines
