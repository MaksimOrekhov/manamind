"""Card IR v0.1: an executor-independent, data-only description of card effects (CARD-IR-PILOT-1 research prototype).

Nothing in the model, encoder, LIVE path or ManaEngine imports this package; it reads only the pinned card metadata.
A declaration that validates is well-formed and honest about its gaps. It is not proof that the reading of the card is
correct, and no executor exists for it.
"""

from manamind.card_ir.validate import Report, extract_elements, normalise_text, validate_declaration
from manamind.card_ir.vocabulary import ELEMENTS, RULES, Element, Rule

__all__ = ["ELEMENTS", "RULES", "Element", "Report", "Rule", "extract_elements", "normalise_text",
           "validate_declaration"]
