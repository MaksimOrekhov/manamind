"""New paired controls, authored for validation (not independent gold).

Real pinned-card mutations are labeled separately from fictional wording controls.
Synthetic metadata only binds fixture text to its declaration; it is never a catalog.
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


def bindings(doc):
    return {**{k: doc[k] for k in ("card_id", "snapshot", "text_sha256")}, "gaps": [
        {"gap": f"/unexpressed/{i}", "span": gap["span"], "why": gap["why"],
         "dependencies": [d["id"] for d in doc["dependencies"] if d["scope"] == "CORE"]}
        for i, gap in enumerate(doc.get("unexpressed", []))]}


def build_cases(real):
    meta, cases = FixtureMetadata(real), []

    def base(text, effect=None, target=False, kind="play"):
        card_id = f"VALIDATION_2_FIXTURE_{len(meta.records):03}"
        meta.records[card_id] = {"id": card_id, "name": card_id, "text": text, "type": "MINION"}
        doc = {"ir": "card-ir/0.1", "card_id": card_id, "snapshot": real.snapshot_id, "role": "sample",
               "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
               "abilities": [], "dependencies": [], "decisions": [], "status": "FULL"}
        if effect:
            ability = {"kind": kind, "label": "SPELL", "span": text, "effect": effect}
            if target:
                ability["target"] = {"bind": "t", "choose": {"pick": "CHOSEN", "type": "MINION", "side": "ANY"}}
            doc["abilities"] = [ability]
        return doc

    def partial(doc):
        doc = copy.deepcopy(doc)
        doc["abilities"] = []
        doc["unexpressed"] = [{"span": doc["text"], "why": "The precise timing or position is unavailable in the frozen language."}]
        doc["dependencies"] = [{"id": "missing_contract", "kind": "UNKNOWN_RULE", "scope": "CORE", "card_level": True,
                                "detail": "The text requires a timing or insertion-position contract missing in v0.1.",
                                "source_needed": "A separately designed language contract; not an assumed runtime behavior"}]
        doc["status"] = "PARTIAL"
        return doc

    def add(name, group, good, bad, origin="SYNTHETIC_CONTRACT", good_links=None, bad_links=None):
        cases.append({"name": name, "group": group, "origin": origin, "good": good, "bad": bad,
                      "good_bindings": good_links, "bad_bindings": bad_links})

    draw = {"op": "DRAW", "player": "SELF", "count": 1}
    damage = {"op": "DEAL_DAMAGE", "to": {"ref": "t"}, "amount": {"n": 2, "mark": "$"}}
    stat = {"stat": "HEALTH", "of": {"ref": "t"}}
    for phrase, cmp in (("If it survives", ">"), ("If that minion dies", "<="),
                        ("Unless it survives", "<="), ("Unless that minion dies", ">")):
        good = base(f"Deal $2 damage to a minion. {phrase}, draw a card.",
                    {"seq": [damage, {"if": {"cmp": [stat, cmp, 0]}, "then": draw}]}, target=True)
        bad = copy.deepcopy(good)
        bad["abilities"][0]["effect"]["seq"][1] = draw
        add(phrase, "condition", good, bad)
    for phrase, damaged in (("If it is damaged", True), ("Unless it is damaged", False)):
        good = base(f"Deal $2 damage to a minion. {phrase}, draw a card.",
                    {"seq": [damage, {"if": {"is": {"entity": {"ref": "t"}, "where": [{"damaged": damaged}]}}, "then": draw}]}, target=True)
        bad = copy.deepcopy(good)
        bad["abilities"][0]["effect"]["seq"][1]["if"]["is"]["where"][0]["damaged"] = not damaged
        add(phrase, "condition", good, bad)
    good = base("Deal $2 damage to a minion. If it survives, draw 1 card. Draw 1 card.",
                {"seq": [damage, {"if": {"cmp": [stat, ">", 0]}, "then": draw}, draw]}, target=True)
    bad = copy.deepcopy(good)
    bad["abilities"][0]["effect"]["seq"][1:] = [draw, {"if": {"cmp": [stat, ">", 0]}, "then": draw}]
    add("condition_in_wrong_sibling", "condition", good, bad)
    good = base("Deal $2 damage to a minion. If it survives, draw 1 card.",
                {"seq": [damage, {"if": {"cmp": [stat, ">", 0]}, "then": draw}]}, target=True)
    bad = copy.deepcopy(good)
    bad["abilities"][0]["effect"]["seq"][1]["if"]["cmp"][0]["of"] = "SELF"
    add("survival_wrong_entity", "condition", good, bad)
    bad = copy.deepcopy(good)
    bad["abilities"][0]["effect"]["seq"][1]["if"]["cmp"][1] = "<="
    add("survival_wrong_branch", "condition", good, bad)

    def area(exclusion=None):
        result = {"pick": "ALL", "type": "MINION", "side": "ANY"}
        if exclusion:
            result["exclude"] = [exclusion]
        return result

    for phrase, pred in (("non-Demon", {"race": "DEMON"}), ("non-Mage", {"card_class": "MAGE"})):
        good = base(f"Destroy all {phrase} minions.", {"op": "DESTROY", "to": area({**area(), "where": [pred]})})
        bad = copy.deepcopy(good)
        del bad["abilities"][0]["effect"]["to"]["exclude"]
        add(phrase, "exclusion", good, bad)
    good = base("Destroy all minions except Dragons.",
                {"op": "DESTROY", "to": area({**area(), "where": [{"race": "DRAGON"}]})})
    bad = copy.deepcopy(good)
    bad["abilities"][0]["effect"]["to"] = {**area(), "where": [{"race": "DRAGON"}]}
    add("except_inverted", "exclusion", good, bad)
    good = base("Destroy all non-Paladin minions. Destroy all non-Priest minions.", {"seq": [
        {"op": "DESTROY", "to": area({**area(), "where": [{"card_class": c}]})} for c in ("PALADIN", "PRIEST")]})
    bad = copy.deepcopy(good)
    bad["abilities"][0]["effect"]["seq"][0]["to"].pop("exclude")
    add("exclusion_in_wrong_sibling", "exclusion", good, bad)
    for field, value in (("type", "SPELL"), ("pick", "RANDOM"), ("zone", "DECK")):
        good = base("Destroy all non-Mage minions.",
                    {"op": "DESTROY", "to": area({**area(), "where": [{"card_class": "MAGE"}]})})
        bad = copy.deepcopy(good)
        bad["abilities"][0]["effect"]["to"]["exclude"][0][field] = value
        add(f"wrong_exclusion_{field}", "exclusion", good, bad)

    good = base("Give a minion +1/+1 this turn.",
                {"op": "ENCHANT", "to": {"ref": "t"}, "attack": 1, "health": 1, "duration": "THIS_TURN"}, target=True)
    bad = copy.deepcopy(good)
    bad["abilities"][0]["effect"]["duration"] = "UNTIL_USED"
    add("modifier_duration", "window", good, bad)
    bad = base("Give a minion +1/+1 next turn.",
               {"op": "ENCHANT", "to": {"ref": "t"}, "attack": 1, "health": 1, "duration": "THIS_TURN"}, target=True)
    good = partial(bad)
    add("next_turn_is_not_now", "window", good, bad, good_links=bindings(good))

    source = {"from_zone": {"pick": "RANDOM", "n": 1, "type": "CARD", "side": "FRIENDLY", "zone": "HAND"}}
    for place in ("top", "bottom"):
        bad = base(f"Put a card from your hand on the {place} of your deck.",
                   {"op": "SHUFFLE_INTO_DECK", "player": "SELF", "what": source})
        good = partial(bad)
        add(f"put_on_{place}", "deck_position", good, bad, good_links=bindings(good))

    good = base("Draw 1 card.", draw)
    bad = copy.deepcopy(good)
    bad["abilities"] = []
    bad["reminders"] = [{"span": good["text"], "why": "just explanatory text"}]
    add("action_hidden_as_reminder", "reminder", good, bad)
    good = base("Deal $2 damage to a minion. (If it survives, draw a card.)",
                {"seq": [damage, {"if": {"cmp": [stat, ">", 0]}, "then": draw}]}, target=True)
    bad = copy.deepcopy(good)
    bad["abilities"][0].update(span="Deal $2 damage to a minion.", effect=damage)
    bad["reminders"] = [{"span": "(If it survives, draw a card.)", "why": "parenthetical explanation"}]
    add("parenthesized_conditional_reminder", "reminder", good, bad)

    links = read(HERE / "historical_gap_bindings.json")
    for card_id in ("JAIL_321", "END_022", "TIME_890", "JAIL_872", "CAP_107t", "CATA_488"):
        good = read(ROOT / "reports/card_ir_pilot_1/declarations" / f"{card_id}.json")
        bad = copy.deepcopy(good)
        if card_id == "JAIL_321":
            bad["abilities"][0]["effect"] = bad["abilities"][0]["effect"]["then"]
            group = "condition"
        elif card_id in ("END_022", "TIME_890"):
            bad["abilities"][0].pop("while")
            group = "condition"
        elif card_id == "JAIL_872":
            bad["abilities"][0]["event"]["type"] = "ATTACK_DECLARED"
            group = "event"
        elif card_id == "CAP_107t":
            bad["abilities"][0]["timing"] = "AFTER"
            group = "window"
        else:
            bad["abilities"][0]["effect"]["to"].pop("exclude")
            group = "exclusion"
        add(f"pinned_{card_id}", group, good, bad, "PINNED_REAL_CARD")
    for card_id in ("JAIL_399", "CATA_585", "CORE_RLK_063"):
        good = read(ROOT / "reports/card_ir_stage_b1/final" / f"{card_id}.json")
        bad = copy.deepcopy(good)
        bad["dependencies"].pop(0)
        add(f"delete_gap_dep_{card_id}", "gap_dependency", good, bad, "PINNED_REAL_CARD",
            good_links=links[card_id], bad_links=links[card_id])
    for text in ("After this attacks a minion, draw 1 card.",
                 "After this minion attacks a minion and survives, draw 1 card.",
                 "At the start of your turn, draw 1 card."):
        good = base(text)
        good["abilities"] = [{"kind": "trigger", "span": text, "event": {"unknown": "event_contract"},
                              "timing": "AT" if text.startswith("At") else "AFTER", "effect": draw}]
        good["dependencies"] = [{"id": "event_contract", "kind": "UNKNOWN_RULE", "scope": "CORE",
                                  "detail": "Attacker roles or turn-start event contract are unavailable in frozen v0.1.",
                                  "source_needed": "An explicit language/event contract; no game behavior assumed"}]
        good["status"] = "PARTIAL"
        bad = copy.deepcopy(good)
        bad["abilities"][0]["event"] = {"type": "TURN_END" if text.startswith("At") else "HERO_ATTACK", "player": "SELF"}
        if "survives" in text:
            bad["abilities"][0]["condition"] = {"cmp": [{"stat": "HEALTH", "of": "SELF"}, ">", 0]}
        bad["dependencies"] = []
        bad["status"] = "FULL"
        add(f"event_paraphrase_{len(cases)}", "event", good, bad)
    good = base("When a friendly minion is attacked, draw 1 card.")
    good["abilities"] = [{"kind": "trigger", "span": good["text"], "timing": "WHEN",
                          "event": {"type": "ATTACK_DECLARED", "defender": {"pick": "ALL", "type": "MINION", "side": "FRIENDLY"}},
                          "effect": draw}]
    bad = copy.deepcopy(good)
    bad["abilities"][0]["event"]["defender"]["type"] = "HERO"
    add("passive_attack_defender", "event", good, bad)
    good = base("Whenever your hero attacks, draw 1 card.")
    good["abilities"] = [{"kind": "trigger", "span": good["text"], "timing": "WHENEVER",
                          "event": {"type": "HERO_ATTACK", "player": "SELF"}, "effect": draw}]
    bad = copy.deepcopy(good)
    bad["abilities"][0]["event"]["player"] = "OPPONENT"
    add("hero_attack_owner", "event", good, bad)
    # Correct look-alikes not used as a training set or false-error examples.
    controls = [base("Shuffle a card from your hand into your deck.",
                     {"op": "SHUFFLE_INTO_DECK", "player": "SELF", "what": source})]
    display = base("Draw 1 card. (1/3)", draw)
    display["abilities"][0]["span"] = "Draw 1 card."
    display["reminders"] = [{"span": "(1/3)", "why": "UI progress display only"}]
    controls.append(display)
    # A known conservative rejection: the frozen language has Rush, but no
    # verified explanation registry. Count this as a false alert, not a success.
    reminder = base("Rush. (Can attack minions immediately.)")
    reminder["keywords"] = [{"keyword": "RUSH", "span": "Rush."}]
    reminder["reminders"] = [{"span": "(Can attack minions immediately.)", "why": "Explanation of the already declared Rush keyword"}]
    controls.append(reminder)
    return meta, cases, controls
