"""Independent adversarial corpus, frozen and measured BEFORE checker changes.

These hand-selected errors have specified witnesses, not a population accuracy rate.
Controls are the author's accepted final declarations, not independently verified gold.
"""
from __future__ import annotations

import copy

from author_first_pass import ROOT, write
from measure import read
from manamind.card_ir.validate import implied_status, normalise_text


def build():
    docs = {c: read(ROOT / "final" / f"{c}.json") for c in read(ROOT / "protocol.json")["order"]}
    bindings = read(ROOT / "final_bindings.json")
    rows = []

    def add(id_, card, category, witness, change, kind="semantic_error", binding=True):
        doc = copy.deepcopy(docs[card])
        change(doc)
        doc["status"] = implied_status(doc)
        rows.append(dict(id=id_, card_id=card, category=category, kind=kind,
                         witness=witness, declaration=doc, bindings=bindings.get(card) if binding else None))

    def effect(d):
        return d["abilities"][0]["effect"]

    add("fury_damage_enemy", "CORE_RLK_063", "target_side", "Choose own hero/minion for the unqualified damage. The adjacent enemy freeze must not restrict that choice.",
        lambda d: d["abilities"][0]["target"]["choose"].update(side="ENEMY"))
    add("fury_damage_minions_only", "CORE_RLK_063", "target_type", "The unqualified damage can target a hero; minions-only removes that legal action.",
        lambda d: d["abilities"][0]["target"]["choose"].update(type="MINION"))
    add("fury_freeze_heroes", "CORE_RLK_063", "target_type", "Enemy minions should freeze; the enemy hero should not be the area selection.",
        lambda d: effect(d)["seq"][1]["to"].update(type="HERO"))
    add("fury_nested_order", "CORE_RLK_063", "order", "A summon reaction reading Frozen enemies runs before freeze in the wrong nested sequence.",
        lambda d: effect(d).update(seq=[effect(d)["seq"][0], {"seq": [effect(d)["seq"][2], effect(d)["seq"][1]]}]))
    add("fury_missing_damage", "CORE_RLK_063", "omission", "No damage is dealt although the card has a damage clause; unused victim binding is also visible to structure.",
        lambda d: effect(d)["seq"].pop(0))
    add("bolt_draw_opponent", "TIME_216", "owner", "The target survives; the author draws two, not the opponent.",
        lambda d: effect(d)["seq"][1]["then"].update(player="OPPONENT"))
    add("bolt_unconditional_draw", "TIME_216", "condition", "Target dies to five damage; wrong declaration still draws two.",
        lambda d: effect(d)["seq"].__setitem__(1, effect(d)["seq"][1]["then"]))
    add("bolt_inverted_survival", "TIME_216", "condition", "Dead rather than surviving target draws two.",
        lambda d: effect(d)["seq"][1]["if"]["is"]["where"][0].update(alive=False))
    add("bolt_health_not_alive", "TIME_216", "condition", "After a reaction marks a positive-Health target for destruction, HEALTH>0 is true but R_SURVIVE is false.",
        lambda d: effect(d)["seq"][1].update(**{"if": {"cmp": [dict(stat="HEALTH", of=dict(ref="victim")), ">", 0]}}))
    add("bolt_guard_before_damage", "TIME_216", "order", "Living 3-Health target draws before lethal five damage, whereas the card should draw zero.",
        lambda d: effect(d)["seq"].reverse())
    add("bolt_wrong_damage_entity", "TIME_216", "binding", "Damage hits SELF instead of the chosen target, whose survival is still tested.",
        lambda d: effect(d)["seq"][0].update(to="SELF"))
    add("neophyte_minion_tax", "CORE_SCH_713", "target_type", "Enemy minions are taxed instead of enemy spells.",
        lambda d: effect(d)["applies_to"][0].update(card_type="MINION"))
    add("neophyte_deck_only", "CORE_SCH_713", "zone", "A spell already in enemy hand is unaffected by a DECK-only modifier when played.",
        lambda d: effect(d).update(zones=["DECK"]))
    add("neophyte_wrong_window", "CORE_SCH_713", "window", "Tax expires before the enemy's next turn.",
        lambda d: effect(d).update(duration="THIS_TURN"))
    add("aviana_enemy_owner", "EDR_895", "owner", "Enemy instead of own cards become cheap after enemy instead of own turn starts; both owner fields agree internally.",
        lambda d: (effect(d).update(player="OPPONENT"), effect(d)["starts_after"].update(player="OPPONENT")))
    add("aviana_hand_only", "EDR_895", "zone", "User explicitly observed deck cards also cost one; this encoding leaves deck costs unchanged.",
        lambda d: effect(d).update(zones=["HAND"]))
    add("aviana_two_turns", "EDR_895", "window", "Cost one activates after two own starts instead of three.",
        lambda d: effect(d)["starts_after"].update(turn_starts=2))
    add("aviana_no_cost_set", "EDR_895", "state_change", "Cost reduced by one instead of set to one: a nine-mana card costs eight.",
        lambda d: effect(d)["modifier"].update(cost=dict(reduce=1)))

    def downgrade(d):
        for dependency in d["dependencies"]:
            if dependency["scope"] == "CORE":
                dependency["scope"] = "CONDITIONAL"

    add("hound_core_downgrade", "FIR_953", "dependency_scope", "Unconfirmed split procedure affects the primary effect every trigger, yet merely changing the author's scope grants FULL_DEP.", downgrade, "evidence_error")
    add("fury_core_downgrade", "CORE_RLK_063", "dependency_scope", "Thaw timing affects ordinary next-turn attacks, yet changing CORE to CONDITIONAL grants FULL_DEP.", downgrade, "evidence_error")
    add("aviana_core_downgrade", "EDR_895", "dependency_scope", "Unresolved activation boundary and future-card procedure remain, but scope alone upgrades the label to FULL_DEP.", downgrade, "evidence_error")
    add("hound_health_packets", "FIR_953", "state_read", "A 5-Attack, 8-Health Hound deals eight packets rather than five.",
        lambda d: effect(d)["repeat"].update(stat="HEALTH"))
    add("hound_no_survival", "FIR_953", "condition", "Hound dies attacking a minion; a trigger without the survival condition would still deal damage.",
        lambda d: d["abilities"][0].pop("condition"))
    add("hound_defender_hero", "FIR_953", "event_role", "Hound attacking a hero triggers the effect instead of attacking a minion.",
        lambda d: d["abilities"][0]["event"]["defender"].update(type="HERO"))
    add("hound_defender_enemy_equivalent", "FIR_953", "event_role", "In ordinary legal combat own Hound cannot attack a friendly minion; ANY -> ENEMY is equivalent, excluded from errors.",
        lambda d: d["abilities"][0]["event"]["defender"].update(side="ENEMY"), "equivalent_control")
    add("imp_wrong_owner", "JAIL_399", "owner", "The two Demons go to opponent's deck instead of own.",
        lambda d: effect(d).update(player="OPPONENT"))
    add("imp_wrong_position", "JAIL_399", "window", "A Demon can be drawn before cards that were already in the deck.",
        lambda d: effect(d).update(position="RANDOM"))
    add("imp_wrong_token", "JAIL_399", "token", "AT_120 Frost Giant has 8/8 stats but is not a Demon with Taunt and Lifesteal.",
        lambda d: effect(d)["what"].update(card="AT_120"))
    add("brilliance_wrong_token", "CATA_452", "token", "AT_041 Knight of the Wild is 6/6 but not a Dragon.",
        lambda d: effect(d)["what"].update(card="AT_041"))
    add("vama_all_minions", "JAIL_118", "omission", "A Paladin minion including V'ama is destroyed because the exclusion disappeared.",
        lambda d: effect(d)["to"].pop("exclude"))
    add("waggle_wrong_discount_target", "CORE_DAL_720", "binding", "The weapon SELF rather than the returned minion receives the cost reduction; returned reference is unused.",
        lambda d: effect(d)["seq"][1].update(to="SELF"))

    def torch_return(d):
        a = d["abilities"][0]
        a["span"] = normalise_text(d["text"])
        a["effect"] = dict(seq=[a["effect"], dict(op="ADD_TO_HAND", player="SELF", what=dict(from_zone=dict(ref="victim")))])
        d.pop("unexpressed")
        d["dependencies"] = [x for x in d["dependencies"] if x["id"] != "persistent_damage"]
        d["decisions"] = [x for x in d["decisions"] if x.get("dep") != "persistent_damage"]

    add("torch_structured_unconditional", "CATA_585", "condition_and_state", "Zero excess or Divine Shield must return nothing. This structurally valid encoding unconditionally returns the victim and stores no damage; FULL_DEP is false. Multiple independent semantic faults, not an isolated full Torch control.",
        torch_return, binding=False)

    def hide_reminder(d):
        d["reminders"] = d.pop("unexpressed")

    add("torch_reminder", "CATA_585", "service_field", "Executable return clause disguised as a UI reminder must be rejected.", hide_reminder)

    def hide_notes(d):
        torch_return(d)
        d["abilities"][0]["effect"]["seq"].pop()
        d["notes"] = "Runtime must return this spell when excess > 0, storing the excess damage."

    add("torch_notes_only", "CATA_585", "service_field", "Entire return and persistence procedure is only a non-executable note under the full span.", hide_notes, binding=False)

    add("bolt_float_mark", "TIME_216", "json_type", "The literal schema requires integers; JSON 5.0 is not an integer.",
        lambda d: effect(d)["seq"][0]["amount"].update(n=5.0), "schema_error")
    add("bolt_bool_mark", "TIME_216", "json_type", "A boolean must not be accepted as a marked damage number.",
        lambda d: effect(d)["seq"][0]["amount"].update(n=True), "schema_error")
    add("bolt_untyped_ref", "TIME_216", "binding_type", "A scalar assigned to victim overwrites its entity binding; subsequent ref victim is no longer an entity.",
        lambda d: effect(d)["seq"].insert(0, {"set": {"victim": 5}}), "schema_error")
    add("bolt_empty_dependencies", "TIME_216", "json_type", "dependencies must be an array; the empty object must not pass by vacuous iteration.",
        lambda d: d.update(dependencies={}), "schema_error")
    return rows


if __name__ == "__main__":
    write(ROOT / "negative_cases.json", build())
