"""Explicit review corrections; raw inputs are never changed. No validator repairs here."""
from __future__ import annotations

import copy

from author_first_pass import ROOT, decision, dep, write
from measure import read


def main():
    output = ROOT / "final"
    output.mkdir(exist_ok=False)
    docs = {c: read(ROOT / "raw" / f"{c}.json") for c in read(ROOT / "protocol.json")["order"]}
    corrections = []

    def record(card_id, category, why):
        corrections.append(dict(card_id=card_id, category=category, reason=why))

    d = docs["CORE_RLK_063"]
    d["abilities"][0]["effect"]["seq"][2]["what"] = dict(card="RLK_063t", resolved="NAME_IN_SET", dep="frostwyrm")
    d["dependencies"].append(dep("frostwyrm", "RLK_063t matches name, 5/5, original creator prefix; there are three gameplay records named Frostwyrm, so UNIQUE_NAME was false. CORE reprint linkage remains a DATA dependency.", "DATA", "TOKEN_IDENTITY"))
    record("CORE_RLK_063", "AUTHOR_ERROR", "Incorrect UNIQUE_NAME resolution; structural checker found three names. Use NAME_IN_SET plus explicit token dependency, preserving the PARTIAL thaw contract.")

    d = docs["CORE_SCH_713"]
    d["dependencies"].append(dep("deck_cost", "HAND-only application leaves the cost of spells in DECK unresolved when an additional effect reads deck costs.", "CONDITIONAL"))
    d["decisions"].append(decision("deck", "Are deck spell costs also modified?", ["HAND only", "HAND and DECK"], "UNRESOLVED", "UNKNOWN", "During the taxed turn an effect reads a spell's cost while it is still in the opponent's deck.", "deck_cost"))
    d["status"] = "FULL_DEP"
    record("CORE_SCH_713", "AUTHOR_ERROR", "Raw FULL omitted the unconfirmed deck-cost scope of HAND-only encoding. Strict checks accepted it. Record the bounded conditional scenario, downgrade to FULL_DEP.")

    d = docs["EDR_895"]
    d["dependencies"].extend([
        dep("boundary", "User observations give three own turns but do not explicitly locate Full Moon at start rather than end of the third turn; starts_after fixes a boundary that needs evidence."),
        dep("cost_interactions", "Ordering with other cost modifiers and repeated lunar cycles is not confirmed by the user's observations.", "CONDITIONAL")])
    d["decisions"].extend([
        decision("boundary", "At which boundary of own turn three does Full Moon rise?", ["Start", "End"], "UNRESOLVED", "UNKNOWN", "Read a card's cost during own turn three before its end.", "boundary"),
        decision("interactions", "How do later cost modifiers and a replayed Aviana interact?", ["Independent dynamic effects", "Other stacking or reset procedure"], "UNRESOLVED", "UNKNOWN", "After Full Moon reduce one card's cost or replay Aviana, and compare the resulting cost and activation time.", "cost_interactions")])
    record("EDR_895", "AUTHOR_ERROR", "Raw omitted uncertainty in the start/end boundary and modifier/replay behavior. Observed three own turns does not by itself prove starts_after's exact boundary. Status remains PARTIAL.")

    d = docs["JAIL_118"]
    d["dependencies"].append(dep("class_membership", "IR predicate says belongs to a class; matching multi-class Paladin membership rather than only scalar cardClass needs a reviewed metadata adapter. No executor exists here.", "CONDITIONAL"))
    d["decisions"].append(decision("multiclass", "How does the future adapter test class membership?", ["Membership in classes as well as cardClass", "Only scalar cardClass"], "UNRESOLVED", "UNKNOWN", "A multi-class minion including Paladin should be excluded if membership semantics are implemented.", "class_membership"))
    d["status"] = "FULL_DEP"
    record("JAIL_118", "EVIDENCE_CLARIFICATION", "The written predicate already means class membership, so the set subtraction is expressible; record the unresolved future multi-class adapter explicitly. No proven gameplay error in raw.")

    d = docs["CATA_585"]
    d["notes"] = "The encoded $8 is the initial play fragment only; it does not describe a replay after the user-observed reduction. No full Torch procedure or Spell Damage behavior is asserted. The persistence/return fragment remains unexpressed and CORE."
    record("CATA_585", "EVIDENCE_CLARIFICATION", "Explicitly bound the fixed $8 fragment to the initial play so it cannot be read as a procedure for later Torch instances.")

    for card_id, doc in docs.items():
        write(output / f"{card_id}.json", doc)
    write(ROOT / "final_bindings.json", copy.deepcopy(read(ROOT / "raw_bindings.json")))
    write(ROOT / "corrections.json", corrections)


if __name__ == "__main__":
    main()
