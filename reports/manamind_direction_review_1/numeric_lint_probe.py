"""Read-only probe of the CARD-IR-OUTCOME-PARITY-1 numeric role lint (lint function only, not full strict v0.2).

Shows one false rejection (correct "instead" declaration whose IR branch order differs from text order),
one false acceptance (semantically swapped branches) and one silent pass (stat-phrase cardinality mismatch).
Condition dicts are placeholders: the lint does not read them. Run: PYTHONPATH=src python <this file>
"""
from manamind.card_ir.numeric_lint_v02 import lint_numeric_roles

SEL = {"pick": "CHOSEN", "type": "MINION", "side": "ANY"}
TEXT = "Give a minion +1/+1. If you're holding a Dragon, give it +3/+3 instead."


def enchant(attack, health=None):
    node = {"op": "ENCHANT", "to": SEL, "attack": attack, "enchantment_id": "X"}
    if health is not None:
        node["health"] = health
    return node


def doc(span, effect):
    return {"card_id": "PROBE", "abilities": [{"span": span, "effect": effect}]}


cases = {
    "correct IR, then-branch first (expected: no warning)":
        doc(TEXT, {"if": {"holding": "DRAGON"}, "then": enchant(3, 3), "else": enchant(1, 1)}),
    "WRONG IR, branches swapped (expected: warning)":
        doc(TEXT, {"if": {"holding": "DRAGON"}, "then": enchant(1, 1), "else": enchant(3, 3)}),
    "WRONG 5/5 with mixed '+2 Attack' text (expected: warning)":
        doc("Give a minion +2 Attack and your minions +1/+1.", {"seq": [enchant(2), enchant(5, 5)]}),
}
for name, case in cases.items():
    print(f"{name}: {lint_numeric_roles(case) or 'no warning'}")
