"""Controlled IR-dependence probes; synthetic and NEVER part of real-match totals."""
from __future__ import annotations

import copy
from pathlib import Path

from adapter import IRRun, forecast_ir
from data_access import CARDS, REPO, read, write_new
from manamind.card_ir.engine_translate import TranslationRefused, translate
from manamind.card_metadata import CardMetadata
from manamind.outcome import scenario as sc
from manamind.outcome.model import Status
from manamind.outcome.texts import TextSource
from manamind.outcome.world import ObservedContext, Unsupported


def resources():
    meta = CardMetadata.load()
    docs = {c: read(REPO / "reports/card_ir_execution_pilot_1/declarations" / f"{c}.json") for c in CARDS}
    texts = TextSource.from_records([dict(meta.get(c)) for c in CARDS] + [
        dict(id="VANILLA", text="", type="MINION", attack=2, health=20, mechanics=[]),
        dict(id="NATURE_TEST", text="", type="SPELL", spellSchool="NATURE", mechanics=[]),
    ])
    return meta, docs, texts


def position(card, *, target_health=9, target_max=20, self_health=20, nature=0):
    mine = sc.minion("VANILLA", 2, 3, 1, max_health=3)
    target = sc.minion("VANILLA", 2, target_health, 1, max_health=target_max)
    hand = (sc.hand_card(card, "SPELL", 1),) + tuple(sc.hand_card("NATURE_TEST", "SPELL", 1) for _ in range(nature))
    state = sc.position(self_side=sc.side(hero_health=self_health, board=(mine,)), opponent=sc.side(board=(target,)), hand=hand)
    action = sc.play(card, 0, "SPELL", 1, None if card == "FIR_906" else sc.target_minion("OPPONENT", 1, "VANILLA"))
    return state, action


def complete_context(**kwargs):
    return ObservedContext(**(dict(spell_damage=0, spell_damage_doubled=False, healing_bonus=0,
                                  spell_healing_doubled=False, healing_does_damage=False,
                                  self_hero_divine_shield=False, opponent_hero_divine_shield=False) | kwargs))


def numeric_view(forecast):
    return dict(status=forecast.status.value, changes=[dict(side=c.ref.side, zone=c.ref.zone, field=c.field,
                before=c.before, after=c.after, at_least=c.at_least, at_most=c.at_most) for c in forecast.changes],
                events=[dict(kind=e.kind, amount=e.amount) for e in forecast.events], reason=forecast.unsupported_reason)


def build():
    meta, docs, texts = resources()
    rows = []
    changes = [
        ("damage_3_to_5", "CORE_EX1_238", lambda d: d["abilities"][0]["effect"]["amount"].update(n=5)),
        ("enemy_target_only", "CORE_EX1_238", lambda d: d["abilities"][0]["target"]["choose"].update(side="ENEMY")),
        ("remove_lifesteal", "CORE_ICC_055", lambda d: d.update(keywords=[])),
        ("heal_to_damage", "CORE_AT_055", lambda d: (d["abilities"][0]["effect"].update(op="DEAL_DAMAGE"), d["abilities"][0]["effect"]["amount"].update(mark="$"))),
        ("reverse_sequence", "FIR_906", lambda d: d["abilities"][0]["effect"]["seq"].reverse()),
    ]
    for name, card, change in changes:
        state, action = position(card, nature=1)
        if name == "enemy_target_only":
            action = dict(action, **sc.target_minion("SELF", 1, "VANILLA"))
        ctx = complete_context()
        original = forecast_ir(state, action, texts, ctx, docs[card], meta)
        doc = copy.deepcopy(docs[card])
        change(doc)
        gated = forecast_ir(state, action, texts, ctx, doc, meta)
        # This path is ONLY a technical probe of the compiler/driver. Real-data
        # execution always uses forecast_ir's strict gate on immutable declarations.
        try:
            changed = IRRun(state, action, texts, ctx, translate(doc)).run()
            compiled = dict(view=numeric_view(changed), changed=numeric_view(original) != numeric_view(changed))
        except (TranslationRefused, Unsupported) as error:
            compiled = dict(refused=getattr(error, "code", getattr(error, "reason", "?")), changed=True)
        rows.append(dict(id=name, synthetic=True, public_gate_reason=gated.unsupported_reason,
                         public_gate_refused=gated.status is Status.UNSUPPORTED,
                         original=numeric_view(original), compiled_probe=compiled))
    return dict(real_events=0, cases=rows, all_public_gates_refuse=all(r["public_gate_refused"] for r in rows),
                all_compiled_probes_change_or_refuse=all(r["compiled_probe"]["changed"] for r in rows))


if __name__ == "__main__":
    value = build()
    write_new(Path(__file__).parent / "mutations.json", value)
    print([(r["id"], r["public_gate_reason"], r["compiled_probe"].get("refused", "changed")) for r in value["cases"]])
