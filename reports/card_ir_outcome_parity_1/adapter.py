"""Experimental IR front end over the unchanged Outcome resolver, not a second simulator.

Report-local by design: production package isolation is unchanged. The pure
engine translator supplies a bounded instruction list; no native engine or
synthetic GameState hydration is used. Own rules text is never parsed here.
"""
from __future__ import annotations

from manamind.card_ir.engine_translate import EngineSpec, TranslationRefused, translate
from manamind.card_ir.strict_v02 import validate_strict_v02
from manamind.outcome.forecast import _Run, describe_action
from manamind.outcome.grammar import Clause, Selector
from manamind.outcome.model import Forecast, Status, UnknownKind
from manamind.outcome.world import ObservedContext, Unsupported

_TARGETS = {
    "EXPLICIT_CHARACTER": Selector("CHOSEN", "CHARACTER", "ANY"),
    "EXPLICIT_ENEMY_CHARACTER": Selector("CHOSEN", "CHARACTER", "ENEMY"),
    "EXPLICIT_FRIENDLY_CHARACTER": Selector("CHOSEN", "CHARACTER", "FRIENDLY"),
    "EXPLICIT_MINION": Selector("CHOSEN", "MINION", "ANY"),
    "ENEMY_MINIONS": Selector("ALL", "MINION", "ENEMY"),
    "ENEMY_CHARACTERS": Selector("ALL", "CHARACTER", "ENEMY"),
    "ALL_MINIONS": Selector("ALL", "MINION", "ANY"),
    "ALL_CHARACTERS": Selector("ALL", "CHARACTER", "ANY"),
    "ALL_FRIENDLY_CHARACTERS": Selector("ALL", "CHARACTER", "FRIENDLY"),
    "SELF": Selector("ALL", "MINION", "FRIENDLY"),
}


class IRRun(_Run):
    """Only the source of own instructions differs; damage/heal/settle/reactions are inherited."""

    def __init__(self, state, action, texts, context, spec: EngineSpec):
        super().__init__(state, action, texts, context, describe_action(state, action))
        self.spec = spec

    def _run_text(self, card_id, text, *, damage_source):
        # text is intentionally unused. Both kind and number come from IR steps;
        # '$' is synthesized from the translator's required IR mark, not reparsed.
        self.damaging_source = damage_source
        paid = False
        for step in self.spec.steps:
            if step.requires_previous_discard and not paid:
                continue
            if step.kind == "DISCARD_RANDOM_SPELL":
                paid = self._discard(step)
                continue
            self.lifesteal_spell = step.lifesteal  # override the printed metadata flag with the IR instruction
            cause = f"IR {step.source}"
            selector = _TARGETS[step.target]
            if step.kind == "DAMAGE":
                clause = Clause("DAMAGE", text=cause + " $", selector=selector, amount=step.amount)
            elif step.kind == "HEAL":
                clause = Clause("HEAL", text=cause + " #", selector=selector, amount=step.amount)
            elif step.kind == "BUFF_FRIENDLY_MINIONS":
                clause = Clause("BUFF", text=cause, selector=selector, attack=step.amount, health=step.amount)
            else:
                raise Unsupported("IR_STEP_UNSUPPORTED")
            self._clause(clause, card_id)
        if self.spec.overload:
            # The existing World does not track this debt in its change ledger.
            # Do not implement a parallel resource resolver or silently lose it.
            self.world.unknown(UnknownKind.KEYWORD_UNDEFINED, "IR Overload debt is outside the Outcome ledger",
                               alters=False, tag="IR_RESOURCE_OVERLOAD_UNMODELLED")
        if self.chosen is not None and not self.chosen_used:
            raise Unsupported("IR_TARGET_NOT_USED")

    def _discard(self, step):
        removed = {ref.position for ref in self.world.hand_removed}
        candidates, unknown_pool = [], False
        for index, card in enumerate(self.state.self_hand):
            if index in removed or card.card_type != "SPELL":
                continue
            entry = self.texts.get(card.card_id)
            if entry is None or entry.spell_school is None:
                unknown_pool = True
            elif entry.spell_school == step.discard_school:
                candidates.append((index, card.card_id))
        if unknown_pool or len(candidates) > 1:
            self.world.unknown(UnknownKind.RANDOM_OUTCOME if not unknown_pool else UnknownKind.MODIFIER_UNOBSERVED,
                               "IR discard recipient cannot be determined from the pre-action hand",
                               tag="IR_DISCARD_RANDOM" if not unknown_pool else "IR_DISCARD_POOL_UNOBSERVED")
            return False
        if not candidates:
            return False
        index, card_id = candidates[0]
        self._leave_hand(index, card_id)  # existing hand-removal primitive; no new zone-transition arithmetic
        self.world.event("DISCARD", self.world.hand_removed[-1], 1, f"IR {step.source}: single eligible spell")
        self.classes.add("DISCARD")
        self.world.unknown(UnknownKind.POSSIBLE_REACTION, "Discard reactions are not resolved by this adapter",
                           tag="IR_DISCARD_REACTIONS")
        return True


def forecast_ir(state, action, texts, context, doc, metadata):
    """Public experimental gate. Strict acceptance is necessary, never semantic gold."""
    label = describe_action(state, action)
    if action.get("type") != "PLAY_CARD" or action.get("card_type") != "SPELL":
        return Forecast(dict(action), label, Status.UNSUPPORTED, unsupported_reason="IR_ACTION_UNSUPPORTED")
    if doc.get("card_id") != action.get("card_id"):
        return Forecast(dict(action), label, Status.UNSUPPORTED, unsupported_reason="IR_CARD_MISMATCH")
    report = validate_strict_v02(doc, metadata)
    if not report.complete or report.status != "FULL":
        return Forecast(dict(action), label, Status.UNSUPPORTED, unsupported_reason="IR_VALIDATION_OR_DEPENDENCY")
    try:
        spec = translate(doc)
        return IRRun(state, action, texts, context or ObservedContext(), spec).run()
    except TranslationRefused as error:
        return Forecast(dict(action), label, Status.UNSUPPORTED, unsupported_reason="IR_TRANSLATION_" + error.code)
    except Unsupported as error:
        return Forecast(dict(action), label, Status.UNSUPPORTED, unsupported_reason=error.reason)
