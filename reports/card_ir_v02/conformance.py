"""Conformance cases of the Card IR v0.2 language (not of real Hearthstone games).

Each case is a declaration plus what strict acceptance must do with it: ``accept`` (with the computed status and text
the audit render must show) or ``reject`` (with a code that must appear among the errors or warnings). Kinds:
``good`` (a correct use), ``bad`` (a plausible wrong use), ``edge`` (a boundary of the contract), ``interaction``
(the element together with another element or an older protection).

Real pinned cards are labelled REAL and reuse their real text; synthetic texts are labelled SYNTHETIC, carry
``CARD_IR_V02_FIXTURE_*`` IDs and exist only in a fixture metadata wrapper, never in a catalog. Authored by the
implementer of v0.2 (Claude Opus): these are contract tests, not an independent gold set.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class FixtureMetadata:
    def __init__(self, real):
        self.real, self.records = real, {}
        self.snapshot_id = real.snapshot_id

    def get(self, card_id):
        return self.records.get(card_id) or self.real.get(card_id)

    def __getattr__(self, key):
        return getattr(self.real, key)


def ack(rule, scope="CONDITIONAL", dep_id=None):
    return {"id": dep_id or rule.lower(), "kind": "UNKNOWN_RULE", "scope": scope, "rule": rule,
            "detail": f"Acknowledges the provisional rule {rule}.", "source_needed": "Power.log evidence for the rule"}


def build_cases(real):
    from manamind.card_ir.validate import implied_status
    from manamind.card_metadata.snapshot import strip_text_artifacts

    meta, cases = FixtureMetadata(real), []
    examples = {p.stem: read(p) for p in sorted((HERE / "examples").glob("*.json")) if p.stem != "gap_bindings"}
    receipts = read(HERE / "examples/gap_bindings.json")

    def finish(doc):
        doc["status"] = implied_status(doc)
        return doc

    def synthetic(text, abilities, deps=(), decisions=(), keywords=None):
        card_id = f"CARD_IR_V02_FIXTURE_{len(meta.records):03}"
        meta.records[card_id] = {"id": card_id, "name": card_id, "text": text, "type": "SPELL"}
        doc = {"ir": "card-ir/0.2", "card_id": card_id, "snapshot": real.snapshot_id, "role": "example",
               "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
        if keywords:
            doc["keywords"] = keywords
        doc.update({"abilities": abilities, "dependencies": list(deps), "decisions": list(decisions)})
        return finish(doc)

    def real_card(card_id, abilities, deps=(), decisions=(), keywords=None):
        text = strip_text_artifacts(real.get(card_id)["text"])
        doc = {"ir": "card-ir/0.2", "card_id": card_id, "snapshot": real.snapshot_id, "role": "example",
               "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
        if keywords:
            doc["keywords"] = keywords
        doc.update({"abilities": abilities, "dependencies": list(deps), "decisions": list(decisions)})
        return finish(doc)

    def example(card_id, change=None):
        doc = copy.deepcopy(examples[card_id])
        if change:
            change(doc)
        return doc

    def add(name, feature, kind, doc, expect, code=None, status=None, render=(), origin="SYNTHETIC", bindings=None):
        cases.append({"name": name, "feature": feature, "kind": kind, "origin": origin, "doc": doc,
                      "bindings": bindings, "expect": expect, "code": code, "status": status, "render": list(render)})

    def spell(span, effect, target=None):
        ability = {"kind": "play", "label": "SPELL", "span": span, "effect": effect}
        if target:
            ability["target"] = {"bind": "t", "choose": {"pick": "CHOSEN", **target}}
        return ability

    def player_effect(**fields):
        return {"op": "ADD_PLAYER_EFFECT", **fields}

    enemy_minions = {"pick": "ALL", "type": "MINION", "side": "ENEMY"}

    # --- every example is accepted with its declared status --------------------------------------------------------
    for card_id, doc in examples.items():
        add(f"example {card_id}", "examples", "good", copy.deepcopy(doc), "accept", status=doc["status"],
            origin="REAL", bindings=receipts.get(card_id))

    # --- FREEZE ---------------------------------------------------------------------------------------------------
    freeze_one = spell("Freeze an enemy minion.", {"op": "FREEZE", "to": {"ref": "t"}},
                       {"type": "MINION", "side": "ENEMY"})
    add("freeze a chosen enemy minion", "op:FREEZE", "good",
        synthetic("Freeze an enemy minion.", [freeze_one], [ack("R_FREEZE_THAW")]), "accept", status="FULL_DEP",
        render=["freeze them<t>", "R_FREEZE_THAW [UNKNOWN; PROVISIONAL"])
    add("freeze without acknowledging the thaw rule", "op:FREEZE", "bad",
        synthetic("Freeze an enemy minion.", [copy.deepcopy(freeze_one)]), "reject", code="R_FREEZE_THAW")
    add("thaw acknowledgement with DATA scope", "op:FREEZE", "edge",
        synthetic("Freeze an enemy minion.", [copy.deepcopy(freeze_one)], [{**ack("R_FREEZE_THAW"), "scope": "DATA"}]),
        "reject", code="rule acknowledgement")
    add("freeze text encoded as silence", "op:FREEZE", "bad",
        synthetic("Freeze all enemy minions.", [spell("Freeze all enemy minions.",
                                                      {"op": "SILENCE", "to": dict(enemy_minions)})]),
        "reject", code="FREEZE_TEXT")
    add("freeze cards in hand", "op:FREEZE", "bad",
        synthetic("Freeze all enemy minions.", [spell("Freeze all enemy minions.", {"op": "FREEZE", "to": {
            "pick": "ALL", "type": "CARD", "side": "ENEMY", "zone": "HAND"}})], [ack("R_FREEZE_THAW")]),
        "reject", code="FREEZE targets characters")
    add("freeze the enemy hero (short selector)", "op:FREEZE", "edge",
        synthetic("Freeze the enemy hero.", [spell("Freeze the enemy hero.", {"op": "FREEZE", "to": "ENEMY_HERO"})],
                  [ack("R_FREEZE_THAW")]), "accept", status="FULL_DEP", render=["freeze the enemy hero"])

    def summon_first(doc):
        steps = doc["abilities"][0]["effect"]["seq"]
        steps[1], steps[2] = steps[2], steps[1]
    add("Frostwyrm's Fury: summon before freeze", "op:FREEZE", "interaction", example("CORE_RLK_063", summon_first),
        "reject", code="ORDER_V02", origin="REAL")

    def freeze_in_reminder(doc):
        doc["abilities"][0]["effect"]["seq"].pop(1)
        doc["dependencies"].pop()
        doc["abilities"][0]["span"] = "Deal $5 damage."
        doc["abilities"].append({"kind": "play", "label": "SPELL", "span": "Summon a 5/5 Frostwyrm.",
                                 "effect": doc["abilities"][0]["effect"]["seq"].pop(1)})
        doc["abilities"][0]["effect"] = doc["abilities"][0]["effect"]["seq"][0]
        doc["reminders"] = [{"span": "Freeze all enemy minions.", "why": "reminder"}]
    add("Frostwyrm's Fury: freeze hidden in a reminder", "op:FREEZE", "interaction",
        example("CORE_RLK_063", freeze_in_reminder), "reject", code="REMINDER", origin="REAL")

    # --- durations: THIS_GAME and NEXT_TURN ------------------------------------------------------------------------
    game_text = "Your spells cost (1) less this game."
    game = player_effect(player="SELF", modifier={"cost": {"reduce": 1}}, applies_to=[{"card_type": "SPELL"}],
                         uses="ALL_MATCHING", zones=["HAND"], duration="THIS_GAME")
    add("spells cheaper for the rest of the game", "duration:THIS_GAME", "good",
        synthetic(game_text, [spell(game_text, copy.deepcopy(game))]), "accept", status="FULL",
        render=["for the rest of the game", "every matching card while active"])
    add("this game read as this turn", "duration:THIS_GAME", "bad",
        synthetic(game_text, [spell(game_text, {**game, "duration": "THIS_TURN"})]), "reject", code="WINDOW_GAME")
    add("THIS_GAME without textual evidence", "duration:THIS_GAME", "bad",
        synthetic("Your spells cost (1) less.", [spell("Your spells cost (1) less.", copy.deepcopy(game))]),
        "reject", code="WINDOW_GAME")
    add("THIS_GAME with integer uses", "duration:THIS_GAME", "edge",
        synthetic(game_text, [spell(game_text, {**game, "uses": 1, "use_unit": "CARD"})]), "reject",
        code="integer uses with THIS_GAME")

    add("Cult Neophyte: this turn instead of next turn", "duration:NEXT_TURN", "bad",
        example("CORE_SCH_713", lambda d: d["abilities"][0]["effect"].update(duration="THIS_TURN")), "reject",
        code="WINDOW_NEXT_V02", origin="REAL")
    add("Cult Neophyte: your next turn instead of the opponent's", "duration:NEXT_TURN", "bad",
        example("CORE_SCH_713", lambda d: d["abilities"][0]["effect"].update(duration={"next_turn": "SELF"})),
        "reject", code="WINDOW_NEXT_V02", origin="REAL")
    next_text = "Your spells cost (1) less on your next turn."
    add("explicit 'your next turn'", "duration:NEXT_TURN", "good",
        synthetic(next_text, [spell(next_text, {**game, "duration": {"next_turn": "SELF"}})]), "accept",
        status="FULL", render=["during your next turn (start to end)"])
    add("next_turn without textual evidence", "duration:NEXT_TURN", "edge",
        synthetic("Your spells cost (1) less.", [spell("Your spells cost (1) less.",
                                                      {**game, "duration": {"next_turn": "SELF"}})]),
        "reject", code="WINDOW_NEXT_V02")
    add("next_turn names a player", "duration:NEXT_TURN", "edge",
        synthetic(next_text, [spell(next_text, {**game, "duration": {"next_turn": "BOTH"}})]), "reject",
        code="next_turn")

    # --- delayed start ---------------------------------------------------------------------------------------------
    add("Aviana: two instead of three turns", "player_effect:starts_after", "bad",
        example("EDR_895", lambda d: d["abilities"][0]["effect"]["starts_after"].update(turn_starts=2)), "reject",
        code="DELAY_COUNT", origin="REAL")
    add("Aviana: effect starts at once", "player_effect:starts_after", "bad",
        example("EDR_895", lambda d: d["abilities"][0]["effect"].pop("starts_after")), "reject", code="DELAY_COUNT",
        origin="REAL")
    add("Aviana: lasts three turns instead of starting after three", "player_effect:starts_after", "interaction",
        example("EDR_895", lambda d: (d["abilities"][0]["effect"].pop("starts_after"),
                                      d["abilities"][0]["effect"].update(duration={"turns": 3}))),
        "reject", code="WINDOW_GAME", origin="REAL")
    add("Aviana: counts the opponent's turns", "player_effect:starts_after", "bad",
        example("EDR_895", lambda d: d["abilities"][0]["effect"]["starts_after"].update(player="OPPONENT")),
        "reject", code="DELAY_OWNER", origin="REAL")
    add("zero turn starts", "player_effect:starts_after", "edge",
        example("EDR_895", lambda d: d["abilities"][0]["effect"]["starts_after"].update(turn_starts=0)), "reject",
        code="positive integer", origin="REAL")

    # --- zones and cardinality -------------------------------------------------------------------------------------
    add("Aviana: cost player effect without zones", "player_effect:zones", "bad",
        example("EDR_895", lambda d: d["abilities"][0]["effect"].pop("zones")), "reject", code="zones",
        origin="REAL")
    add("zones on a non-cost player effect", "player_effect:zones", "bad",
        synthetic("Your healing deals damage instead this turn.", [spell(
            "Your healing deals damage instead this turn.",
            player_effect(player="SELF", modifier={"rule": "HEALING_DOES_DAMAGE"}, uses="ALL_MATCHING",
                          zones=["HAND"], duration="THIS_TURN"))]), "reject", code="zones belong")
    add("repeated zone", "player_effect:zones", "edge",
        example("EDR_895", lambda d: d["abilities"][0]["effect"].update(zones=["HAND", "HAND"])), "reject",
        code="without repeats", origin="REAL")
    add("Aviana: hand only (a different, valid reading)", "player_effect:zones", "edge",
        example("EDR_895", lambda d: d["abilities"][0]["effect"].update(zones=["HAND"])), "accept",
        status="FULL_DEP", render=["zones=HAND;"], origin="REAL")

    next_spell = "Your next spell costs (1) less."
    one_use = player_effect(player="SELF", modifier={"cost": {"reduce": 1}}, applies_to=[{"card_type": "SPELL"}],
                            uses=1, use_unit="CARD", zones=["HAND"], duration="UNTIL_USED")
    add("your next spell: one use", "player_effect:ALL_MATCHING", "good",
        synthetic(next_spell, [spell(next_spell, copy.deepcopy(one_use))]), "accept", status="FULL",
        render=["the next 1 matching card(s)"])
    add("your next spell read as all spells", "player_effect:ALL_MATCHING", "bad",
        synthetic(next_spell, [spell(next_spell, {**{k: v for k, v in one_use.items() if k != "use_unit"},
                                                  "uses": "ALL_MATCHING", "duration": "THIS_TURN"})]),
        "reject", code="USES_SCOPE")
    add("Cult Neophyte: one spell instead of all", "player_effect:ALL_MATCHING", "bad",
        example("CORE_SCH_713", lambda d: d["abilities"][0]["effect"].update(uses=1, use_unit="CARD")), "reject",
        code="USES_SCOPE", origin="REAL")
    add("modifier player effect without uses", "player_effect:ALL_MATCHING", "bad",
        example("CORE_SCH_713", lambda d: d["abilities"][0]["effect"].pop("uses")), "reject",
        code="states its cardinality", origin="REAL")
    add("ALL_MATCHING until used", "player_effect:ALL_MATCHING", "edge",
        synthetic(next_spell, [spell(next_spell, {**one_use, "uses": "ALL_MATCHING", "use_unit": "CARD"})]),
        "reject", code="use_unit belongs")
    add("integer uses without a unit", "player_effect:ALL_MATCHING", "edge",
        synthetic(next_spell, [spell(next_spell, {k: v for k, v in one_use.items() if k != "use_unit"})]),
        "reject", code="use_unit")

    def relabel(doc):
        doc["ir"] = "card-ir/0.2"
    preparation = read(ROOT / "reports/card_ir_pilot_1/declarations/CORE_BT_416.json")
    relabel(preparation)
    add("a v0.1 declaration relabelled as v0.2", "versioning", "interaction", preparation, "reject",
        code="zones", origin="REAL")

    # --- cost direction and multiplication -------------------------------------------------------------------------
    add("Cult Neophyte: negative reduce", "modifier:cost", "bad",
        example("CORE_SCH_713", lambda d: d["abilities"][0]["effect"].update(modifier={"cost": {"reduce": -1}})),
        "reject", code="must not be negative", origin="REAL")
    add("Cult Neophyte: less instead of more", "modifier:cost", "bad",
        example("CORE_SCH_713", lambda d: d["abilities"][0]["effect"].update(modifier={"cost": {"reduce": 1}})),
        "reject", code="COST_SIGN", origin="REAL")
    add("returned minion costs more (random pick)", "modifier:cost", "good",
        synthetic("Return a random friendly minion to your hand. It costs (2) more.", [spell(
            "Return a random friendly minion to your hand. It costs (2) more.", {"seq": [
                {"op": "ADD_TO_HAND", "player": "SELF", "as": "r", "what": {"from_zone": {
                    "pick": "RANDOM", "n": 1, "type": "MINION", "side": "FRIENDLY"}}},
                {"op": "MODIFY_COST", "to": {"ref": "r"}, "increase": 2}]})], [ack("R_RETURN_FULL_HAND")]),
        "accept", status="FULL_DEP", render=["increased by 2", "move PLAY->HAND"])

    def counter_change(**fields):
        def change(doc):
            doc["abilities"][1]["modifier"]["cost"]["reduce"]["mul"][1]["counter"].update(fields)
        return change
    add("Spellweaver's: spells cast instead of damage", "counter:DAMAGE_DEALT", "bad",
        example("CATA_452", lambda d: (d["abilities"][1]["modifier"]["cost"]["reduce"]["mul"].__setitem__(
            1, {"counter": {"event": "SPELL_CAST", "player": "SELF", "scope": "THIS_TURN"}}),
                                      d["dependencies"].pop())), "reject", code="DAMAGE_COUNTER", origin="REAL")
    add("Spellweaver's: damage from any source", "counter:DAMAGE_DEALT", "bad",
        example("CATA_452", lambda d: d["abilities"][1]["modifier"]["cost"]["reduce"]["mul"][1]["counter"].pop(
            "source")), "reject", code="DAMAGE_COUNTER", origin="REAL")
    add("Spellweaver's: counted this game", "counter:DAMAGE_DEALT", "bad",
        example("CATA_452", counter_change(scope="THIS_GAME")), "reject", code="DAMAGE_COUNTER", origin="REAL")
    add("Spellweaver's: damage the opponent dealt", "counter:DAMAGE_DEALT", "bad",
        example("CATA_452", counter_change(player="OPPONENT")), "reject", code="DAMAGE_COUNTER", origin="REAL")
    add("Spellweaver's: COUNT instead of AMOUNT", "counter:DAMAGE_DEALT", "edge",
        example("CATA_452", counter_change(measure="COUNT")), "reject", code="measure", origin="REAL")
    add("Spellweaver's: amount rule not acknowledged", "counter:DAMAGE_DEALT", "edge",
        example("CATA_452", lambda d: d["dependencies"].pop()), "reject", code="R_DAMAGE_EVENT_AMOUNT",
        origin="REAL")
    add("Spellweaver's: reduce by the counter without mul", "value:mul", "bad",
        example("CATA_452", lambda d: d["abilities"][1]["modifier"]["cost"].update(
            reduce=d["abilities"][1]["modifier"]["cost"]["reduce"]["mul"][1])), "reject", code="text number 1",
        origin="REAL")
    add("mul without a literal", "value:mul", "edge",
        example("CATA_452", lambda d: d["abilities"][1]["modifier"]["cost"]["reduce"]["mul"].__setitem__(
            0, {"var": "x"})), "reject", code="mul takes", origin="REAL")
    add("mul with a wrong literal", "value:mul", "bad",
        example("CATA_452", lambda d: d["abilities"][1]["modifier"]["cost"]["reduce"]["mul"].__setitem__(0, 2)),
        "reject", code="text number 1", origin="REAL")
    add("Spellweaver's audit render shows the counter", "counter:DAMAGE_DEALT", "good",
        example("CATA_452"), "accept", status="FULL_DEP", origin="REAL",
        render=["(1 x total damage actually dealt (AMOUNT) by you with card type SPELL this turn)"])

    # --- attack roles ---------------------------------------------------------------------------------------------
    def event(**fields):
        def change(doc):
            doc["abilities"][0]["event"] = {"type": "ATTACK_DECLARED", **fields}
        return change
    defender = {"pick": "ALL", "type": "MINION", "side": "ANY"}
    add("Magma Hound: hero attack instead of this minion", "event_role:attacker", "bad",
        example("FIR_953", lambda d: (d["abilities"][0].update(event={"type": "HERO_ATTACK", "player": "SELF"}),
                                      d["dependencies"].pop())), "reject", code="EVENT_SUBJECT", origin="REAL")
    add("Magma Hound: v0.1 'subject' role", "event_role:attacker", "bad",
        example("FIR_953", event(subject="SELF", defender=defender)), "reject", code="unknown keys ['subject']",
        origin="REAL")
    add("Magma Hound: an enemy minion attacks", "event_role:attacker", "bad",
        example("FIR_953", event(attacker={"pick": "ALL", "type": "MINION", "side": "ENEMY"}, defender=defender)),
        "reject", code="ATTACK_ROLE", origin="REAL")
    add("Magma Hound: attacks the hero instead of a minion", "event_role:defender", "bad",
        example("FIR_953", event(attacker="SELF", defender={"pick": "ALL", "type": "HERO", "side": "ANY"})),
        "reject", code="EVENT_DEFENDER", origin="REAL")
    add("Magma Hound: redirect rule not acknowledged", "event_role:defender", "edge",
        example("FIR_953", lambda d: d["dependencies"].pop()), "reject", code="R_ATTACK_REDIRECT", origin="REAL")
    add("Magma Hound: a random defender", "event_role:defender", "edge",
        example("FIR_953", event(attacker="SELF", defender={**defender, "pick": "RANDOM", "n": 1})), "reject",
        code="use pick ALL", origin="REAL")
    add("attack event without roles", "event_role:attacker", "edge",
        example("FIR_953", event()), "reject", code="needs an attacker or defender", origin="REAL")
    attacked = "Whenever a friendly minion is attacked, gain +1 Attack."
    add("a friendly minion is attacked (defender only)", "event_role:defender", "good",
        synthetic(attacked, [{"kind": "trigger", "span": attacked, "timing": "WHENEVER",
                              "event": {"type": "ATTACK_DECLARED", "defender": {
                                  "pick": "ALL", "type": "MINION", "side": "FRIENDLY"}},
                              "effect": {"op": "ENCHANT", "to": "SELF", "attack": 1}}], [ack("R_ATTACK_REDIRECT")]),
        "accept", status="FULL_DEP", render=["defender a friendly minion", "R_ATTACK_REDIRECT"])
    add("Magma Hound audit shows both roles and the survival guard", "event_role:attacker", "good",
        example("FIR_953"), "accept", status="PARTIAL", origin="REAL",
        render=["attacker this attacks defender a minion", "ONLY IF this is alive (survived)"])

    # --- survival -------------------------------------------------------------------------------------------------
    bolt_effect = {"seq": [{"op": "DEAL_DAMAGE", "to": {"ref": "t"}, "amount": {"n": 5, "mark": "$"}},
                           {"if": {"is": {"entity": {"ref": "t"}, "where": [{"alive": True}]}},
                            "then": {"op": "DRAW", "player": "SELF", "count": 2}}]}
    bolt_text = "Deal $5 damage to a minion. If it survives, draw 2 cards."

    def bolt(effect):
        return real_card("TIME_216", [spell(bolt_text, effect, {"type": "MINION", "side": "ANY"})])
    add("Nascent Bolt: draw only if the target survives", "pred:alive", "good", bolt(copy.deepcopy(bolt_effect)),
        "accept", status="FULL", origin="REAL", render=["them<t> is alive (survived)", "R_SURVIVE [COMMUNITY_RULES]"])
    unconditional = copy.deepcopy(bolt_effect)
    unconditional["seq"][1] = unconditional["seq"][1]["then"]
    add("Nascent Bolt: unconditional draw", "pred:alive", "bad", bolt(unconditional), "reject",
        code="CONDITION_ENTITY", origin="REAL")
    inverted = copy.deepcopy(bolt_effect)
    inverted["seq"][1]["if"]["is"]["where"][0]["alive"] = False
    add("Nascent Bolt: draw if it dies", "pred:alive", "bad", bolt(inverted), "reject", code="CONDITION_ENTITY",
        origin="REAL")
    wrong_entity = copy.deepcopy(bolt_effect)
    wrong_entity["seq"][1]["if"]["is"]["entity"] = "SELF"
    add("Nascent Bolt: survival of the wrong entity", "pred:alive", "bad", bolt(wrong_entity), "reject",
        code="CONDITION_ENTITY", origin="REAL")
    not_bool = copy.deepcopy(bolt_effect)
    not_bool["seq"][1]["if"]["is"]["where"][0]["alive"] = 1
    add("alive must be boolean", "pred:alive", "edge", bolt(not_bool), "reject", code="alive must be a boolean",
        origin="REAL")
    in_selector = "Deal $5 damage to a random minion."
    add("alive inside a selector", "pred:alive", "edge",
        synthetic(in_selector, [spell(in_selector, {"op": "DEAL_DAMAGE", "amount": {"n": 5, "mark": "$"}, "to": {
            "pick": "RANDOM", "n": 1, "type": "MINION", "side": "ANY", "where": [{"alive": True}]}})]),
        "reject", code="alive is only allowed")
    dies_text = "Deal $2 damage to a minion. If it dies, draw a card."
    add("if it dies (alive false)", "pred:alive", "good",
        synthetic(dies_text, [spell(dies_text, {"seq": [
            {"op": "DEAL_DAMAGE", "to": {"ref": "t"}, "amount": {"n": 2, "mark": "$"}},
            {"if": {"is": {"entity": {"ref": "t"}, "where": [{"alive": False}]}},
             "then": {"op": "DRAW", "player": "SELF", "count": 1}}]}, {"type": "MINION", "side": "ANY"})]),
        "accept", status="FULL", render=["not alive (did not survive)"])
    garbage = "After this attacks a minion and survives, deal this minion's Attack damage split among all enemies."
    add("trigger condition is validated (v0.1 loophole closed)", "pred:alive", "interaction",
        example("FIR_953", lambda d: d["abilities"][0].update(condition={"is": {"entity": "SELF", "where": [
            {"alive": True}, {"no_such_predicate": 1}]}})), "reject", code="unknown predicate", origin="REAL")
    add("Magma Hound: survival guard dropped", "pred:alive", "interaction",
        example("FIR_953", lambda d: d["abilities"][0].pop("condition")), "reject", code="CONDITION_ENTITY",
        origin="REAL")
    assert garbage == examples["FIR_953"]["abilities"][0]["span"]

    # --- deck position and count ----------------------------------------------------------------------------------
    add("Imp Gang Stooge: shuffle instead of bottom", "deck_position:BOTTOM", "bad",
        example("JAIL_399", lambda d: d["abilities"][0]["effect"].update(position="RANDOM")), "reject",
        code="DECK_POSITION_V02", origin="REAL")
    add("Imp Gang Stooge: top instead of bottom", "deck_position:TOP", "bad",
        example("JAIL_399", lambda d: d["abilities"][0]["effect"].update(position="TOP")), "reject",
        code="DECK_POSITION_V02", origin="REAL")
    add("Imp Gang Stooge: one Demon instead of two", "deck_position:BOTTOM", "bad",
        example("JAIL_399", lambda d: d["abilities"][0]["effect"].update(count=1)), "reject", code="DECK_COUNT",
        origin="REAL")
    add("Imp Gang Stooge: unknown position", "deck_position:BOTTOM", "edge",
        example("JAIL_399", lambda d: d["abilities"][0]["effect"].update(position="MIDDLE")), "reject",
        code="'MIDDLE' not in", origin="REAL")
    shuffle_text = "Shuffle a copy of this into your deck."
    shuffle = {"op": "SHUFFLE_INTO_DECK", "player": "SELF", "what": {"copy_of": "SELF"}}
    add("shuffle with the default position", "deck_position:RANDOM", "good",
        synthetic(shuffle_text, [spell(shuffle_text, copy.deepcopy(shuffle))]), "accept", status="FULL",
        render=["shuffle into your deck", "[position=RANDOM]"])
    add("shuffle with an explicit RANDOM position", "deck_position:RANDOM", "edge",
        synthetic(shuffle_text, [spell(shuffle_text, {**shuffle, "position": "RANDOM"})]), "accept", status="FULL")
    add("shuffle text read as bottom", "deck_position:RANDOM", "bad",
        synthetic(shuffle_text, [spell(shuffle_text, {**shuffle, "position": "BOTTOM"})]), "reject",
        code="DECK_POSITION_V02")
    top_text = "Put a copy of this on top of your deck."
    add("put on top", "deck_position:TOP", "good",
        synthetic(top_text, [spell(top_text, {**shuffle, "position": "TOP"})]), "accept", status="FULL",
        render=["put on top of your deck"])
    add("negative deck count", "deck_position:BOTTOM", "edge",
        example("JAIL_399", lambda d: d["abilities"][0]["effect"].update(count=-2)), "reject",
        code="must not be negative", origin="REAL")

    # --- PLAY -> HAND moves ---------------------------------------------------------------------------------------
    waggle_text = "Deathrattle: Return a random friendly minion to your hand. It costs (2) less."
    waggle_effect = {"seq": [{"op": "ADD_TO_HAND", "player": "SELF", "as": "returned", "what": {"from_zone": {
        "pick": "RANDOM", "n": 1, "type": "MINION", "side": "FRIENDLY", "zone": "PLAY"}}},
        {"op": "MODIFY_COST", "to": {"ref": "returned"}, "reduce": 2}]}

    def waggle(effect, deps):
        return real_card("CORE_DAL_720", [{"kind": "deathrattle", "span": waggle_text, "effect": effect}], deps)
    add("Waggle Pick: return with the full-hand rule acknowledged", "move:PLAY_TO_HAND", "good",
        waggle(copy.deepcopy(waggle_effect), [ack("R_RETURN_FULL_HAND")]), "accept", status="FULL_DEP",
        origin="REAL", render=["move PLAY->HAND", "R_RETURN_TO_HAND [COMMUNITY_RULES]"])
    add("Waggle Pick: full-hand rule not acknowledged", "move:PLAY_TO_HAND", "bad",
        waggle(copy.deepcopy(waggle_effect), []), "reject", code="R_RETURN_FULL_HAND", origin="REAL")
    two = copy.deepcopy(waggle_effect)
    two["seq"][0]["what"]["from_zone"]["n"] = 2
    add("Waggle Pick: two minions", "move:PLAY_TO_HAND", "bad", waggle(two, [ack("R_RETURN_FULL_HAND")]),
        "reject", code="RETURN_SOURCE", origin="REAL")
    not_minion = copy.deepcopy(waggle_effect)
    not_minion["seq"][0]["what"]["from_zone"]["type"] = "CHARACTER"
    add("PLAY->HAND move of a non-minion", "move:PLAY_TO_HAND", "edge",
        waggle(not_minion, [ack("R_RETURN_FULL_HAND")]), "reject", code="minions only", origin="REAL")
    add("full-hand acknowledgement without a move", "move:PLAY_TO_HAND", "edge",
        example("JAIL_399", lambda d: d["dependencies"].append(ack("R_RETURN_FULL_HAND"))), "reject",
        code="does not need", origin="REAL")

    # --- split damage ---------------------------------------------------------------------------------------------
    split_text = "Deal $3 damage randomly split among all enemies."
    split = {"repeat": {"n": 3, "mark": "$"}, "do": {"op": "DEAL_DAMAGE", "amount": 1, "to": {
        "pick": "RANDOM", "n": 1, "type": "CHARACTER", "side": "ENEMY"}}}
    add("randomly split (confirmed rule, no acknowledgement)", "reading:split", "good",
        synthetic(split_text, [spell(split_text, copy.deepcopy(split))]), "accept", status="FULL",
        render=["R_RANDOM_SPLIT [COMMUNITY_RULES]"])
    add("randomly split with an unnecessary unqualified-split acknowledgement", "reading:split", "edge",
        synthetic(split_text, [spell(split_text, copy.deepcopy(split))], [ack("R_SPLIT_UNQUALIFIED", "CORE")]),
        "reject", code="does not need")
    add("split read as damage to all enemies", "reading:split", "bad",
        synthetic(split_text, [spell(split_text, {"op": "DEAL_DAMAGE", "amount": {"n": 3, "mark": "$"},
                                                  "to": {"pick": "ALL", "type": "CHARACTER", "side": "ENEMY"}})]),
        "reject", code="SPLIT_ENCODING")
    add("Magma Hound: unqualified split not acknowledged", "reading:split", "bad",
        example("FIR_953", lambda d: (d["dependencies"].pop(0), d["decisions"][1].update(
            basis="COMMUNITY_RULES"), d["decisions"][1].pop("dep"))), "reject", code="R_SPLIT_UNQUALIFIED",
        origin="REAL")

    # --- the rule-acknowledgement mechanism ----------------------------------------------------------------------
    add("acknowledging a non-provisional rule", "rule_acknowledgement", "bad",
        example("JAIL_399", lambda d: d["dependencies"].append({**ack("R_COST"), "id": "cost"})), "reject",
        code="not a provisional v0.2 rule", origin="REAL")
    add("acknowledging one rule twice", "rule_acknowledgement", "edge",
        example("CORE_RLK_063", lambda d: d["dependencies"].append({**ack("R_FREEZE_THAW"), "id": "again"})),
        "reject", code="already acknowledged", origin="REAL")
    add("acknowledgement with a non-rule kind", "rule_acknowledgement", "edge",
        example("CORE_RLK_063", lambda d: d["dependencies"][1].update(kind="TOKEN_IDENTITY")), "reject",
        code="rule acknowledgement", origin="REAL")

    # --- protections of validation-2 still hold under v0.2 -------------------------------------------------------
    torch = examples["CATA_585"]
    add("Torch: no gap receipt", "gap_receipts", "interaction", copy.deepcopy(torch), "reject", code="GAP_BINDINGS",
        origin="REAL")
    add("Torch: CORE gap dependency removed", "gap_receipts", "interaction",
        example("CATA_585", lambda d: d["dependencies"].pop(0)), "reject", code="GAP_DEPENDENCY", origin="REAL",
        bindings=receipts["CATA_585"])
    add("Torch: return hidden in a reminder", "gap_receipts", "interaction",
        example("CATA_585", lambda d: (d.update(reminders=d.pop("unexpressed")), d["dependencies"].pop(0),
                                       d.update(status="PARTIAL"))), "reject", code="REMINDER", origin="REAL")
    add("Torch: static return as a plain ADD_TO_HAND", "gap_receipts", "interaction",
        example("CATA_585", lambda d: (d["abilities"].append({
            "kind": "play", "label": "SPELL", "span": d.pop("unexpressed")[0]["span"],
            "effect": {"op": "ADD_TO_HAND", "player": "SELF", "what": {"copy_of": "SELF"}}}),
            d["dependencies"].pop(0), d.update(status="PARTIAL"))), "reject", code="RETURN_MOVE", origin="REAL")
    # No semantic check sees the missing 'excess' condition here; strict_lint fails closed on the short-selector
    # source (a guard, not a semantic detection). Recorded as such in CONFORMANCE.md.
    add("Torch: unconditional return of this card (caught only by the fail-closed guard)", "gap_receipts",
        "interaction",
        example("CATA_585", lambda d: (d["abilities"].append({
            "kind": "play", "label": "SPELL", "span": d.pop("unexpressed")[0]["span"],
            "effect": {"op": "ADD_TO_HAND", "player": "SELF", "what": {"from_zone": "SELF"}}}),
            d["dependencies"].pop(0), d.update(status="PARTIAL"))), "reject", code="malformed declaration",
        origin="REAL")
    add("unknown version", "versioning", "edge", example("EDR_895", lambda d: d.update(ir="card-ir/0.3")),
        "reject", code="VERSION", origin="REAL")
    return meta, cases
