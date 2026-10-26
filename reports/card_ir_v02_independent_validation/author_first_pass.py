"""Recorded first authoring batch. Refuses to overwrite the frozen raw declarations.

Read before authoring: language implementation, normative spec/delta, B1 protocol,
the 12 pinned records and their directly related token records. No prior declarations,
conformance solutions or Opus results were read. This is human-visible in-session
model authorship, not an independent compiler API call or a semantic gold set.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from manamind.card_ir.validate import normalise_text
from manamind.card_metadata import CardMetadata, strip_text_artifacts

ROOT = Path(__file__).resolve().parent


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def dep(id_, detail, scope="CORE", kind="UNKNOWN_RULE", rule=None):
    result = dict(id=id_, kind=kind, scope=scope, detail=detail,
                  source_needed="Independent rule evidence or a discriminating observed game; pinned metadata for IDs")
    if rule:
        result["rule"] = rule
    return result


def decision(id_, question, alternatives, chosen, basis, case, dep_id=None):
    result = dict(id=id_, question=question, alternatives=alternatives, chosen=chosen,
                  basis=basis, risk="OUTCOME", discriminating_case=case)
    if dep_id:
        result["dep"] = dep_id
    return result


def query(pick="ALL", type_="MINION", side="ANY", **kwargs):
    return dict(pick=pick, type=type_, side=side, **kwargs)


def play(span, effect, label="SPELL", **kwargs):
    return dict(kind="play", label=label, span=span, effect=effect, **kwargs)


def main():
    meta = CardMetadata.load()
    protocol_path = ROOT.parent / "card_ir_stage_b1/protocol.json"
    sample = json.loads(protocol_path.read_text(encoding="utf-8"))["sample"][:12]
    docs = {}
    for card in sample:
        text = strip_text_artifacts(meta.get(card["id"])["text"])
        docs[card["id"]] = dict(ir="card-ir/0.2", card_id=card["id"], snapshot=meta.snapshot_id,
                                role="sample", text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                                abilities=[], dependencies=[], decisions=[], status="FULL")

    d = docs["EDR_895"]
    d["abilities"] = [play(normalise_text(d["text"]), dict(
        op="ADD_PLAYER_EFFECT", player="SELF", duration="THIS_GAME", uses="ALL_MATCHING",
        zones=["HAND", "DECK"], starts_after=dict(player="SELF", turn_starts=3),
        modifier=dict(cost=dict(set=1))), "BATTLECRY")]
    d["dependencies"] = [dep("future_cards", "ALL_MATCHING includes later arrivals and removes the modifier on leaving zones; user observations establish existing HAND/DECK and permanence only. Dynamic vs one-time population not confirmed.")]
    d["decisions"] = [
        decision("clock", "Whose three turns and how long?", ["Three own starts, rest of game", "Three global turns, temporary"],
                 "Three own starts, rest of game", "USER_OBSERVED", "Three intervening enemy turns must not activate the effect."),
        decision("population", "Do cards arriving after Full Moon inherit cost 1?", ["Dynamic ALL_MATCHING", "Only cards present at activation"],
                 "UNRESOLVED", "UNKNOWN", "Create a new card after Full Moon; compare its cost with 1.", "future_cards")]
    d["notes"] = "Provisional dynamic encoding only; not a confirmed rule. User confirms hand/deck at Full Moon, three own turns, permanence. New cards and cost-modifier interactions remain open."

    d = docs["TIME_216"]
    d["abilities"] = [play(normalise_text(d["text"]), {"seq": [
        dict(op="DEAL_DAMAGE", to=dict(ref="victim"), amount=dict(n=5, mark="$")),
        {"if": {"is": dict(entity=dict(ref="victim"), where=[dict(alive=True)])},
         "then": dict(op="DRAW", player="SELF", count=2)}]},
        target=dict(bind="victim", choose=query("CHOSEN")))]
    d["decisions"] = [decision("survival", "Which entity must survive and when?", ["Chosen victim after damage and reactions", "Source or pre-damage victim"],
                               "Chosen victim after damage and reactions", "TEXT", "Lethal damage to the target must not draw; a surviving target draws two.")]

    d = docs["CATA_497"]
    d["unexpressed"] = [dict(span=normalise_text(d["text"]), why="Herald operation and dynamic {0}/{1} state are absent; the identity of Deathwing and improvement rules cannot be inferred safely from this text.")]
    d["dependencies"] = [dep("herald_state", "Herald procedure, improvement counters, dynamic values and referenced Deathwing identity require external evidence; no invented values.")]
    d["decisions"] = [decision("herald", "Can placeholders be assigned literal values?", ["Read current client state", "Guess base values"],
                               "UNRESOLVED", "UNKNOWN", "Different prior Herald counts can change both operations.", "herald_state")]

    d = docs["CATA_452"]
    d["abilities"] = [play("Summon a 6/6 Dragon.", dict(op="SUMMON", what=dict(card="CATA_452t", resolved="DESCRIPTION_MATCH", dep="dragon"))),
                      dict(kind="aura", span="Costs (1) less for each damage you dealt with spells this turn.", active_in="HAND",
                           modifier=dict(cost=dict(reduce={"mul": [1, {"counter": dict(event="DAMAGE_DEALT", measure="AMOUNT", player="SELF", scope="THIS_TURN", source=[dict(card_type="SPELL")])}]})))]
    d["dependencies"] = [dep("dragon", "CATA_452t Azure Warden is a matching 6/6 Dragon with creator prefix; HSJSON does not contain a formal parent-token edge.", "DATA", "TOKEN_IDENTITY"),
                         dep("damage_amount", "The whole DAMAGE_DEALT amount contract is provisional, including prevention, overkill and qualifying spell sources; normal discount computation depends on it.", rule="R_DAMAGE_EVENT_AMOUNT")]
    d["decisions"] = [decision("counter", "How is discount counted?", ["Damage amount of own spells this turn", "Number of spells cast"],
                               "Damage amount of own spells this turn", "TEXT", "One spell dealing five damage discounts five, not one.", "damage_amount")]

    d = docs["JAIL_118"]
    d["abilities"] = [play(normalise_text(d["text"]), dict(op="DESTROY", to=query(exclude=[query(where=[dict(card_class="PALADIN")])])), "BATTLECRY")]
    d["decisions"] = [decision("class", "Does non-Paladin exclude both sides?", ["All sides minus Paladin membership", "Enemy side only"],
                               "All sides minus Paladin membership", "TEXT", "A friendly non-Paladin minion dies; a dual-class Paladin minion survives.")]

    d = docs["CORE_BT_921"]
    d["keywords"] = [dict(keyword="LIFESTEAL", span="Lifesteal")]
    d["notes"] = "Effect representation only. Pinned record has durability=0 and health=2; do not silently repair metadata or claim weapon execution readiness."

    d = docs["JAIL_399"]
    d["keywords"] = [dict(keyword="TAUNT", span="Taunt.")]
    d["abilities"] = [dict(kind="deathrattle", span="Deathrattle: Put two 8/8 Demons with Taunt and Lifesteal on the bottom of your deck.",
                           effect=dict(op="SHUFFLE_INTO_DECK", player="SELF", position="BOTTOM", count=2,
                                       what=dict(card="JAIL_399t1", resolved="DESCRIPTION_MATCH", dep="demon")))]
    d["dependencies"] = [dep("demon", "Grandmother Imp is an 8/8 Demon with Taunt and Lifesteal, creator prefix JAIL_399; formal creator linkage remains data dependency.", "DATA", "TOKEN_IDENTITY")]
    d["decisions"] = [decision("position", "Where are the two copies inserted?", ["Bottom of own deck", "Random positions"],
                               "Bottom of own deck", "TEXT", "Existing deck cards must be drawn before either new Demon.")]

    d = docs["CORE_SCH_713"]
    d["abilities"] = [play(normalise_text(d["text"]), dict(op="ADD_PLAYER_EFFECT", player="OPPONENT", duration=dict(next_turn="OPPONENT"),
        uses="ALL_MATCHING", zones=["HAND"], applies_to=[dict(card_type="SPELL")], modifier=dict(cost=dict(increase=1))), "BATTLECRY")]
    d["decisions"] = [decision("window", "Who is taxed and for which turn?", ["Every enemy spell during next enemy turn", "Only next spell or current turn"],
                               "Every enemy spell during next enemy turn", "TEXT", "Two enemy spells next turn are both taxed; no tax remains the following turn.")]

    d = docs["CORE_DAL_720"]
    d["abilities"] = [dict(kind="deathrattle", span=normalise_text(d["text"]), effect={"seq": [
        dict(op="ADD_TO_HAND", player="SELF", what=dict(from_zone=query("RANDOM", side="FRIENDLY", zone="PLAY", n=1)), **{"as": "returned"}),
        dict(op="MODIFY_COST", to=dict(ref="returned"), reduce=2)]})]
    d["dependencies"] = [dep("full_hand", "Return reset is represented by R_RETURN_TO_HAND; destruction/no-op followup with a full hand is unverified and conditional on hand capacity.", "CONDITIONAL", rule="R_RETURN_FULL_HAND")]
    d["decisions"] = [decision("capacity", "What happens when hand is full?", ["Destroy moved minion, followup no-op", "Other return failure behavior"],
                               "UNRESOLVED", "UNKNOWN", "Weapon dies with ten cards in hand and one friendly deathrattle minion.", "full_hand")]

    d = docs["FIR_953"]
    d["keywords"] = [dict(keyword="RUSH", span="Rush.")]
    d["abilities"] = [dict(kind="trigger", span="After this attacks a minion and survives, deal this minion's Attack damage split among all enemies.",
        event=dict(type="ATTACK_DECLARED", attacker="SELF", defender=query(type_="MINION")), timing="AFTER",
        condition={"is": dict(entity="SELF", where=[dict(alive=True)])},
        effect=dict(repeat=dict(stat="ATTACK", of="SELF", at="CURRENT"), do=dict(op="DEAL_DAMAGE", amount=1, to=query("RANDOM", "CHARACTER", "ENEMY"))))]
    d["dependencies"] = [dep("split", "Unqualified split is not confirmed to mean random packets; it changes the primary effect on every successful trigger.", rule="R_SPLIT_UNQUALIFIED"),
                         dep("redirect", "Which defender an attack filter sees after redirection remains unknown, conditional on redirection.", "CONDITIONAL", rule="R_ATTACK_REDIRECT")]
    d["decisions"] = [decision("distribution", "Does unqualified split mean random 1-damage packets?", ["Random live targets per packet", "Other split procedure"],
                               "UNRESOLVED", "UNKNOWN", "Two enemy characters: allocation differs between equal and random splitting.", "split"),
                      decision("attack", "When and which combat?", ["After source attacks a minion and survives", "Any character's attack"],
                               "After source attacks a minion and survives", "TEXT", "Attacking the enemy hero must not trigger; source death must not trigger.")]

    d = docs["CATA_585"]
    d["abilities"] = [play("Deal $8 damage to a damaged minion.", dict(op="DEAL_DAMAGE", to=dict(ref="victim"), amount=dict(n=8, mark="$")),
                           target=dict(bind="victim", choose=query("CHOSEN", where=[dict(damaged=True)])))]
    d["unexpressed"] = [dict(span="Return this to hand with any excess damage.", why="IR has no persistent per-card damage parameter or spell-return contract; local variables cannot preserve 8 -> 5 -> 3 over repeated plays, and return requires positive actual excess with no return through Divine Shield.")]
    d["dependencies"] = [dep("persistent_damage", "Need per-instance damage state and conditional return of the spell itself, not a fresh fixed card."),
                         dep("spell_damage", "Pinned $8 spelling and ImmuneToSpellpower tag conflict as an executable convention; Spell Damage, Immune and full-hand cases are unconfirmed.", "CONDITIONAL")]
    d["decisions"] = [decision("observed", "What does excess carry?", ["Remaining instance damage 8 -> 5 -> 3; positive excess only", "Fresh 8 damage or unconditional return"],
                               "Remaining instance damage 8 -> 5 -> 3; positive excess only", "USER_OBSERVED", "8 damage against 3 HP returns 5; next 5 against 2 HP returns 3; zero excess and Divine Shield return nothing.", "persistent_damage"),
                      decision("spellpower", "Does Spell Damage affect Torch?", ["Adds damage", "Ignored by ImmuneToSpellpower"],
                               "UNRESOLVED", "UNKNOWN", "Cast with +1 Spell Damage and inspect damage and returned parameter.", "spell_damage")]

    d = docs["CORE_RLK_063"]
    d["abilities"] = [play(normalise_text(d["text"]), {"seq": [
        dict(op="DEAL_DAMAGE", to=dict(ref="victim"), amount=dict(n=5, mark="$")),
        dict(op="FREEZE", to=query(side="ENEMY")),
        dict(op="SUMMON", what=dict(card="RLK_063t", resolved="UNIQUE_NAME"))]},
        target=dict(bind="victim", choose=query("CHOSEN", "CHARACTER")))]
    d["dependencies"] = [dep("thaw", "Thaw timing changes whether affected minions can attack on their ordinary next turn; provisional contract is not a confirmed freeze lifecycle.", rule="R_FREEZE_THAW")]
    d["decisions"] = [decision("thaw", "When does Frozen expire?", ["Controller-turn removal conditional on attack availability", "Other thaw timing"],
                               "UNRESOLVED", "UNKNOWN", "Freeze an exhausted enemy minion and inspect its next attack opportunity.", "thaw"),
                      decision("damage_target", "Does unqualified damage restrict side?", ["Chosen character on either side", "Enemy characters only"],
                               "Chosen character on either side", "TEXT", "Friendly hero or minion is an allowed selected damage target; only the freeze is enemy-wide.")]

    # These statuses express declared evidence gaps, not independently verified game correctness.
    bindings = {}
    raw_dir = ROOT / "raw"
    raw_dir.mkdir(exist_ok=True)
    for card in sample:
        d = docs[card["id"]]
        d["status"] = ("PARTIAL" if d.get("unexpressed") or any(x["scope"] == "CORE" for x in d["dependencies"])
                       else "FULL_DEP" if d["dependencies"] else "FULL")
        if d.get("unexpressed"):
            core = [x["id"] for x in d["dependencies"] if x["scope"] == "CORE"]
            bindings[d["card_id"]] = {k: d[k] for k in ("card_id", "snapshot", "text_sha256")}
            bindings[d["card_id"]]["gaps"] = [dict(gap=f"/unexpressed/{i}", **g, dependencies=core)
                                                 for i, g in enumerate(d["unexpressed"])]
        write(raw_dir / f"{d['card_id']}.json", d)
    write(ROOT / "raw_bindings.json", bindings)
    write(ROOT / "protocol.json", dict(
        id="CARD-IR-V02-INDEPENDENT-VALIDATION", base_sha="ec67dcbba91869bb01417476b3fcd7badab58466",
        author="OpenAI Codex, GPT-6 family; exact serving revision, sampling seed and temperature unavailable",
        hypothesis="Strict v0.2 catches syntax and selected text contradictions, but cannot establish semantics or dependency severity independently of its author.",
        baseline="Unmodified ec67dcb; Opus claimed potential 9/12, not a target or gold standard",
        order=[c["id"] for c in sample], snapshot=meta.snapshot_id,
        protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        independence="First 12 declarations generated once before validation results or prior declarations/conformance solutions were read; raw plus receipts committed before comparison.",
        limits="12 cards only; no execution, training, holdout, new snapshot, S2 or Herald implementation; no semantic gold accuracy claim",
        scope_policy="Unknown rule needed for ordinary primary effect is CORE; explicitly bounded additional edge scenario may be CONDITIONAL. This conservative author policy is not enforced by v0.2.",
        first_pass="Both base structure and strict checks reported; complete means accepted AND FULL/FULL_DEP; potential expressibility reported separately"))
    write(ROOT / "raw_manifest.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(raw_dir.glob("*.json"))})


if __name__ == "__main__":
    main()
