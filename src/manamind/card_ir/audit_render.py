"""Expanded, opt-in human review of v0.1; the historical render remains byte-stable."""
from __future__ import annotations

import json
from collections.abc import Mapping

from manamind.card_ir.render import _Renderer
from manamind.card_ir.vocabulary import RULES


class _AuditRenderer(_Renderer):
    def value(self, node):
        result = super().value(node)
        if isinstance(node, Mapping) and "stat" in node:
            result += f" [read={node.get('at', 'CURRENT')}]"
        return result

    def selector(self, node, *, one=False):
        result = super().selector(node, one=one)
        if isinstance(node, Mapping) and "pick" in node:
            zone = node.get("zone", "PLAY")
            zones = zone if isinstance(zone, list) else [zone]
            result += f" [zones={','.join(zones)}; mode={node['pick']}]"
        return result

    def event(self, node):
        if "unknown" in node:
            return f"UNKNOWN event <{node['unknown']}> (participants/timing contract unresolved)"
        kind = node["type"]
        parts = [kind]
        if kind == "HERO_ATTACK":
            parts.append(f"attacker=hero of {node.get('player', 'UNSPECIFIED PLAYER')}")
        if "player" in node:
            parts.append(f"player={node['player']}")
        for role in ("subject", "defender"):
            if role in node:
                label = "subject (role UNDEFINED in v0.1)" if kind == "ATTACK_DECLARED" and role == "subject" else role
                parts.append(f"{label}={self.selector(node[role], one=True)}")
        if "source" in node:
            parts.append("source filters:" + self.where(node["source"]))
        return "; ".join(parts)

    def ability(self, node):
        if node.get("kind") != "trigger":
            return super().ability(node)
        parts = [f"Trigger [{node.get('label', 'no keyword')}, timing={node['timing']}, active zone={node.get('active_in', 'PLAY (default; weapon EQUIPPED)')}]",
                 self.event(node["event"])]
        if "condition" in node:
            parts.append("ONLY IF " + self.condition(node["condition"]))
        parts.append(f"limit={node.get('limit', 'none declared')}")
        parts.append("effect: " + self.effect(node["effect"]))
        return "; ".join(parts)

    def duration(self, node):
        if isinstance(node, Mapping):
            return f"{node['turns']} turns [clock/start/end ownership not explicit in v0.1]"
        return super().duration(node)

    def op(self, node):
        if node["op"] == "ADD_PLAYER_EFFECT":
            what = (self.modifier(node["modifier"]) if "modifier" in node else
                    "; ".join(self.ability(a) for a in node["abilities"]))
            filters = self.where(node.get("applies_to", [])) or " none declared"
            uses = str(node["uses"]) if "uses" in node else "UNSPECIFIED (v0.1 cardinality not resolved)"
            result = (f"player effect on {node['player']}: {what}; applies-to filters:{filters}; "
                      f"duration={self.duration(node['duration'])}; uses={uses}; use-unit={node.get('use_unit', 'unspecified')}")
        else:
            result = super().op(node)
        if "enchantment_id" in node:
            result += f" [enchantment={node['enchantment_id']}]"
        return result


def _render_audit(doc, meta=None, bindings=None, strict_report=None):
    """Never hide reminders, unknowns or conditions. Invalid fragments remain visible."""
    renderer = _AuditRenderer(meta)
    lines = [f"Declared status: {doc.get('status', '?')} — representation label, not semantic approval"]
    for kind in ("keywords", "abilities"):
        for i, node in enumerate(doc.get(kind, [])):
            try:
                if kind == "abilities":
                    text = renderer.ability(node)
                else:
                    text = f"Keyword {node['keyword']}"
                    if "amount" in node:
                        text += f" amount={node['amount']}"
                    if "parts" in node:
                        text += " parts: " + ", ".join(renderer.source(p) for p in node["parts"])
            except (TypeError, ValueError, KeyError, AttributeError, IndexError):
                text = "UNRENDERABLE: " + json.dumps(node, ensure_ascii=False)
            lines.append(f"{kind}[{i}] TEXT: {node.get('span', '<no span>')} => {text}")
    for kind, label in (("reminders", "REMINDER (not executed)"), ("unexpressed", "UNEXPRESSED (not executed)")):
        for i, item in enumerate(doc.get(kind, [])):
            lines.append(f"{kind}[{i}] {label}: {item.get('span')}; reason: {item.get('why')}")
    if bindings:
        for item in bindings.get("gaps", []):
            lines.append(f"Gap binding {item['gap']} => dependencies: {', '.join(item['dependencies'])}")
    for dep in doc.get("dependencies", []):
        lines.append(f"Dependency <{dep['id']}> {dep['kind']}/{dep['scope']}: {dep['detail']}; source needed: {dep['source_needed']}")
    for decision in doc.get("decisions", []):
        lines.append(f"Decision {decision['id']} [{decision['risk']}/{decision['basis']}]: {decision['question']} => "
                     f"{decision['chosen']}; alternatives: {' / '.join(decision['alternatives'])}; "
                     f"dependency={decision.get('dep', 'none')}; distinguishing case: {decision.get('discriminating_case', 'none')}")
    if doc.get("notes"):
        lines.append("Author notes (not executed): " + str(doc["notes"]))
    if strict_report:
        lines.append(f"Strict acceptance={strict_report.accepted}; complete={strict_report.complete}; computed status={strict_report.status}")
        lines.extend("ERROR: " + e for e in strict_report.errors)
        lines.extend("REVIEW WARNING: " + w for w in strict_report.warnings)
    # Show rule provenance, rather than implying that a clean declaration proved the rules.
    if meta is not None:
        from manamind.card_ir.validate import validate_declaration
        try:
            needed = validate_declaration(doc, meta).rules
            lines += [f"Rule {r} [{RULES[r].basis}]: {RULES[r].meaning}" for r in sorted(needed)]
        except (TypeError, ValueError, KeyError, AttributeError, IndexError):
            lines.append("Rule requirements unavailable: invalid declaration")
    return lines


def render_audit(doc, meta=None, bindings=None, strict_report=None):
    """Render valid semantics or an explicit failure; malformed data never vanishes."""
    try:
        return _render_audit(doc, meta, bindings, strict_report)
    except (TypeError, ValueError, KeyError, AttributeError, IndexError, RecursionError):
        lines = ["UNRENDERABLE DECLARATION: invalid shape; no semantic interpretation asserted",
                 json.dumps(doc, ensure_ascii=False)]
        if strict_report:
            lines.extend("ERROR: " + e for e in strict_report.errors)
        return lines
