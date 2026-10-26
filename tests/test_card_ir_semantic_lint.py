import copy
import json
from pathlib import Path

import pytest

from manamind.card_ir.semantic_lint import lint_semantics

ROOT = Path(__file__).resolve().parents[1]


def lint(span, effect):
    return lint_semantics({"abilities": [{"span": span, "effect": effect}]})


@pytest.mark.parametrize("word,count", [("two", 2), ("three", 3), ("five", 5), ("twelve", 12), ("a", 1)])
def test_counts_are_attached_to_operations(word, count):
    effect = {"op": "DRAW", "player": "SELF", "count": count}
    assert lint(f"Draw {word} cards.", effect) == []
    effect["count"] = count + 1
    assert any("count:" in x for x in lint(f"Draw {word} cards.", effect))


def test_other_and_implicit_all():
    target = {"pick": "ALL", "type": "MINION", "side": "ANY", "exclude": ["SELF"]}
    assert lint("Destroy all other minions.", {"op": "DESTROY", "to": target}) == []
    del target["exclude"]
    assert lint("Destroy all other minions.", {"op": "DESTROY", "to": target})
    target.update(side="FRIENDLY")
    assert lint("Give your minions +1/+1.", {"op": "ENCHANT", "to": target}) == []
    target.update(pick="RANDOM")
    assert lint("Give your minions +1/+1.", {"op": "ENCHANT", "to": target})


@pytest.mark.parametrize("keyword,word", [("RUSH", "Rush"), ("TAUNT", "Taunt"), ("DIVINE_SHIELD", "Divine Shield")])
def test_keyword_grants(keyword, word):
    op = {"op": "ENCHANT", "to": "SELF", "keywords": [keyword]}
    assert lint(f"Gain {word}.", op) == []
    op["keywords"] = ["LIFESTEAL"]
    assert lint(f"Gain {word}.", op)


def test_order_pronouns_and_each_enemy_selector():
    ops = [{"op": "SILENCE", "to": "SELF"}, {"op": "DESTROY", "to": "SELF"}]
    assert lint("Silence and destroy a minion.", {"seq": ops}) == []
    assert lint("Silence and destroy a minion.", {"seq": ops[::-1]})
    ops = [{"op": "SUMMON", "as": "made"}, {"op": "ENCHANT", "to": {"ref": "made"}}]
    assert lint("Summon a minion. Give it +1 Attack.", {"seq": ops}) == []
    ops[1]["to"] = "SELF"
    assert lint("Summon a minion. Give it +1 Attack.", {"seq": ops})
    target = {"pick": "ALL", "type": "CHARACTER", "side": "ENEMY"}
    ops = [{"op": "DEAL_DAMAGE", "to": target}, {"op": "DEAL_DAMAGE", "to": {**target, "side": "FRIENDLY"}}]
    assert lint("Deal 2 damage to all enemies. Repeat.", {"seq": ops})


def test_baseline_A_has_no_new_warnings():
    for path in (ROOT / "reports/card_ir_pilot_1/declarations").glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert lint_semantics(copy.deepcopy(doc)) == [], path.name
