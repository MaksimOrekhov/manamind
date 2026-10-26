"""CARD-IR-EXECUTION-PILOT-1: positions, scenarios and IR mutations (data only, no execution).

Every expectation below was written by hand from the printed card text and the cited Card IR rule before the scenario
was first run; none was copied from an engine result. Positions are reached only through the supported prototype
path: unshuffled decks, ordinary legal actions, fixed seed. Hero entity IDs are not used; targets are named by side and
card ID and resolved against the legal action list.

Deck order is draw order. The first seat starts with its first four cards and 1 Mana; the second seat with its first
four cards plus The Coin, and it draws on each of its turns.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

BOLT, FLASH, DRAIN, OVERHEAT = "CORE_EX1_238", "CORE_AT_055", "CORE_ICC_055", "FIR_906"
CARDS = (BOLT, FLASH, DRAIN, OVERHEAT)
FILLER = "CORE_EX1_145"  # Preparation: never played here, no school
SHOT = "CORE_DS1_185"  # Arcane Shot: deal $2 damage
COIN = "GAME_005"
RAZORJAW = "CS3_038"  # 3/1 Rush
SENJIN = "CORE_CS2_179"  # 3/5 Taunt
LEECH = "CORE_GIL_558"  # 2/1 Lifesteal
THALNOS = "CORE_EX1_012"  # 1/1 Spell Damage +1
CLERIC = "CATA_216"  # 4/5, Battlecry: your healing effects restore 2 more Health this game
SPARKS = "CORE_BOT_451"  # Nature spell, never played here
INNERVATE = "CORE_EX1_169"  # Nature spell with no ManaEngine declaration

END = ("end",)


def play(card: str, target: Any = None) -> tuple:
    return ("play", card, target)


def attack(card: str, target: Any) -> tuple:
    return ("attack", card, target)


@dataclass(frozen=True)
class Setup:
    """Decks (front cards; the rest is FILLER) and the actions that reach the tested position."""

    deck1: tuple[str, ...]
    deck2: tuple[str, ...]
    script: tuple[tuple, ...]
    note: str


SETUPS = {
    "bolt_turn1": Setup((BOLT,), (), (), "first seat, turn 1, 1 Mana, empty boards, both heroes 30"),
    "razorjaw": Setup((BOLT, DRAIN), (RAZORJAW,),
                      (END, play(COIN), play(RAZORJAW), END),
                      "first seat turn 2 (2 Mana); enemy Razorjaw 3/1 on board"),
    "senjin": Setup((BOLT, DRAIN, FLASH), (SHOT, SHOT, SENJIN),
                    (END, play(SHOT, "OPP_HERO"), END, END, play(SHOT, "OPP_HERO"), END, END,
                     play(COIN), play(SENJIN), END),
                    "first seat turn 4 (4 Mana), own hero 26 (two Arcane Shots), enemy Sen'jin 3/5"),
    "hero22": Setup((FLASH, DRAIN), (SHOT, SHOT, SHOT, SHOT),
                    (END, play(COIN), play(SHOT, "OPP_HERO"), play(SHOT, "OPP_HERO"), END,
                     END, play(SHOT, "OPP_HERO"), play(SHOT, "OPP_HERO"), END),
                    "first seat turn 3 (3 Mana), own hero 22 (four Arcane Shots), no minions"),
    "cleric": Setup((FLASH, CLERIC), (SHOT, SHOT, SHOT, SHOT),
                    (END, play(COIN), play(SHOT, "OPP_HERO"), play(SHOT, "OPP_HERO"), END,
                     END, play(SHOT, "OPP_HERO"), play(SHOT, "OPP_HERO"), END,
                     END, END, play(CLERIC), END, END),
                    "first seat turn 5 (5 Mana), own hero 22, own Cleansing Cleric played (healing bonus 2)"),
    "thalnos": Setup((BOLT, THALNOS, DRAIN), (RAZORJAW,),
                     (END, play(COIN), play(RAZORJAW), END, play(THALNOS), END, attack(RAZORJAW, "OPP_HERO"), END),
                     "first seat turn 3 (3 Mana), own Thalnos (Spell Damage +1), own hero 27 (Razorjaw hit), "
                     "enemy Razorjaw 3/1"),
    "drain_no_minion": Setup((DRAIN,), (), (END, END), "first seat turn 2 (2 Mana), no minions anywhere"),
    "overheat": Setup((OVERHEAT, LEECH, RAZORJAW), (),
                      (play(LEECH), END, END, play(RAZORJAW), END, END),
                      "first seat turn 3 (3 Mana), own Swamp Leech 2/1 and Razorjaw 3/1, no Nature spell in hand"),
    "overheat_nature": Setup((OVERHEAT, LEECH, RAZORJAW, BOLT), (),
                             (play(LEECH), END, END, play(RAZORJAW), END, END),
                             "as overheat, plus Lightning Bolt (Nature) in hand"),
    "overheat_two_nature": Setup((OVERHEAT, LEECH, RAZORJAW, BOLT, SPARKS), (),
                                 (play(LEECH), END, END, play(RAZORJAW), END, END),
                                 "as overheat, plus Lightning Bolt and Sparks (both Nature) in hand"),
    "overheat_empty_board": Setup((OVERHEAT, BOLT), (), (END, END, END, END),
                                  "first seat turn 3 (3 Mana), no minions, Lightning Bolt in hand"),
    "unsupported_in_hand": Setup((OVERHEAT, LEECH, RAZORJAW, INNERVATE), (), (),
                                 "first seat turn 1 holding Innervate, a Nature spell ManaEngine does not support"),
}


def mutate(card: str, change: Callable[[dict], None]) -> Callable[[dict], dict]:
    def apply(declarations: dict) -> dict:
        doc = copy.deepcopy(declarations[card])
        change(doc)
        return doc
    return apply


def _effect(doc):
    return doc["abilities"][0]["effect"]


def _set(path: tuple, value: Any) -> Callable[[dict], None]:
    def change(doc: dict) -> None:
        node = doc
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return change


def _del(path: tuple) -> Callable[[dict], None]:
    def change(doc: dict) -> None:
        node = doc
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return change


def _steps(*changes: Callable[[dict], None]) -> Callable[[dict], None]:
    def change(doc: dict) -> None:
        for one in changes:
            one(doc)
    return change


def _insert_before_pay(step: dict) -> Callable[[dict], None]:
    return lambda doc: _effect(doc)["seq"].insert(1, step)


EFFECT = ("abilities", 0, "effect")
TARGET = ("abilities", 0, "target")


@dataclass(frozen=True)
class Scenario:
    id: str
    card: str
    mechanic: str
    category: str  # normal | edge | unsupported | order | legality | compat | wrong_ir | mutation
    setup: str
    action: tuple[tuple, ...]
    expected_outcome: str  # COMPLETED | NO_LEGAL_ACTION | UNSIMULATABLE:<code> | REFUSED:<code>
    basis: str
    rules: tuple[str, ...] = ()
    expected_changes: dict[str, Any] | None = None  # observable path -> value after the action
    expected_any: tuple[dict[str, Any], ...] = ()  # alternative expected changes (random outcome)
    mode: str = "full"  # full: no other observable field may change; fields: only the listed ones are checked
    expected_targets: tuple[str, ...] | None = None  # legal targets of the card before the action
    expected_trace: tuple[str, ...] | None = None  # ordered native trace events of the action
    ir: str = "declared"  # declared, or the id of a mutation in MUTATIONS
    expected_validator: str | None = None  # for mutations: ACCEPTED or REJECTED by strict v0.2
    compare_legacy: bool = False  # also run ManaEngine's legacy declaration (B0 compatibility)
    evidence: str = "TEST_CONTRACT"  # TEST_CONTRACT | REAL_LOG_CONSISTENT (see real_evidence.json)
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def bolt_play(mana_before: int, mana_after: int, hand_before: list, hand_after: list) -> dict[str, Any]:
    return {"SELF.available_mana": mana_after, "SELF.pending_overload": 1, "SELF.hand": hand_after,
            "SELF.hand_size": len(hand_after)}


F = FILLER
SCENARIOS: tuple[Scenario, ...] = (
    # ---------------- Lightning Bolt: DEAL_DAMAGE $3 to a chosen character, Overload (1) ----------------
    Scenario("LB-1", BOLT, "DEAL_DAMAGE", "normal", "bolt_turn1", (play(BOLT, "OPP_HERO"),), "COMPLETED",
             "Text 'Deal $3 damage': no Spell Damage on board, so 3. Overload (1) owes 1 Mana; cost 1.",
             ("R_DAMAGE", "R_SPELL_DAMAGE", "R_PLAY_TARGET"),
             {"OPP.hero_health": 27, "SELF.available_mana": 0, "SELF.pending_overload": 1,
              "SELF.hand": [F, F, F], "SELF.hand_size": 3}, compare_legacy=True, evidence="REAL_LOG_CONSISTENT"),
    Scenario("LB-2", BOLT, "DEAL_DAMAGE", "legality", "bolt_turn1", (), "COMPLETED",
             "'a character' with no minions in play: exactly both heroes are legal targets.", ("R_PLAY_TARGET",),
             expected_targets=("OPP_HERO", "SELF_HERO")),
    Scenario("LB-3", BOLT, "DEAL_DAMAGE", "edge", "bolt_turn1", (play(BOLT, "SELF_HERO"),), "COMPLETED",
             "Any character includes the caster's own hero.", ("R_DAMAGE", "R_PLAY_TARGET"),
             {"SELF.hero_health": 27, "SELF.available_mana": 0, "SELF.pending_overload": 1,
              "SELF.hand": [F, F, F], "SELF.hand_size": 3}, compare_legacy=True),
    Scenario("LB-4", BOLT, "DEAL_DAMAGE", "edge", "razorjaw", (play(BOLT, ("OPP_MINION", RAZORJAW)),), "COMPLETED",
             "3 damage to a 3/1 kills it (overkill is irrelevant); it leaves the board at the death phase.",
             ("R_DAMAGE", "R_DEATH_PHASE"),
             {"OPP.board": [], "SELF.available_mana": 1, "SELF.pending_overload": 1,
              "SELF.hand": [DRAIN, F, F, F], "SELF.hand_size": 4}, compare_legacy=True),
    Scenario("LB-5", BOLT, "DEAL_DAMAGE", "normal", "senjin", (play(BOLT, ("OPP_MINION", SENJIN)),), "COMPLETED",
             "3 damage to a 3/5 leaves it 3/2 (max Health 5).", ("R_DAMAGE",),
             {"OPP.board": [f"{SENJIN} 3/2/5"], "SELF.available_mana": 3, "SELF.pending_overload": 1,
              "SELF.hand": [DRAIN, FLASH, F, F, F, F], "SELF.hand_size": 6}, compare_legacy=True,
             evidence="REAL_LOG_CONSISTENT"),
    Scenario("LB-6", BOLT, "DEAL_DAMAGE", "edge", "thalnos", (play(BOLT, "OPP_HERO"),), "COMPLETED",
             "'$' amount plus the controller's Spell Damage once per step: 3 + 1 (Thalnos) = 4.",
             ("R_SPELL_DAMAGE",),
             {"OPP.hero_health": 26, "SELF.available_mana": 2, "SELF.pending_overload": 1,
              "SELF.hand": [DRAIN, F, F, F], "SELF.hand_size": 4}, compare_legacy=True),
    Scenario("LB-7", BOLT, "OVERLOAD", "order", "bolt_turn1", (play(BOLT, "OPP_HERO"), END, END), "COMPLETED",
             "Overload (1) paid at play locks 1 of the next turn's 2 Mana: max 2, available 1, owed becomes locked.",
             (),
             {"OPP.hero_health": 27, "SELF.max_mana": 2, "SELF.available_mana": 1, "SELF.overloaded_mana": 1,
              "SELF.pending_overload": 0}, mode="fields", compare_legacy=True),
    # ---------------- Flash Heal: RESTORE_HEALTH #5 to a chosen character ----------------
    Scenario("FH-1", FLASH, "RESTORE_HEALTH", "normal", "hero22", (play(FLASH, "SELF_HERO"),), "COMPLETED",
             "Restore 5 to a hero missing 8: 22 -> 27. Cost 1.", ("R_HEALING",),
             {"SELF.hero_health": 27, "SELF.available_mana": 2, "SELF.hand": [DRAIN, F, F, F, F],
              "SELF.hand_size": 5}, compare_legacy=True, evidence="REAL_LOG_CONSISTENT"),
    Scenario("FH-2", FLASH, "RESTORE_HEALTH", "edge", "senjin", (play(FLASH, "SELF_HERO"),), "COMPLETED",
             "Healing is capped at missing Health: 26 + 5 caps at 30.", ("R_HEALING",),
             {"SELF.hero_health": 30, "SELF.available_mana": 3, "SELF.hand": [BOLT, DRAIN, F, F, F, F],
              "SELF.hand_size": 6}, compare_legacy=True),
    Scenario("FH-3", FLASH, "RESTORE_HEALTH", "edge", "senjin", (play(FLASH, ("OPP_MINION", SENJIN)),), "COMPLETED",
             "Any character includes an undamaged enemy minion; it restores nothing.", ("R_HEALING", "R_PLAY_TARGET"),
             {"SELF.available_mana": 3, "SELF.hand": [BOLT, DRAIN, F, F, F, F], "SELF.hand_size": 6},
             compare_legacy=True),
    Scenario("FH-4", FLASH, "RESTORE_HEALTH", "edge", "cleric", (play(FLASH, "SELF_HERO"),), "COMPLETED",
             "'#' amount plus the controller's healing bonus per packet: 5 + 2 = 7, 22 -> 29.", ("R_HEALING",),
             {"SELF.hero_health": 29, "SELF.available_mana": 4, "SELF.hand": [F, F, F, F, F, F],
              "SELF.hand_size": 6}, compare_legacy=True),
    Scenario("FH-5", FLASH, "RESTORE_HEALTH", "unsupported", "cleric", (play(FLASH, "OPP_HERO"),),
             "UNSIMULATABLE:HEALING_BONUS_SCOPE_UNREVIEWED",
             "Whether the caster's healing bonus applies to a character it does not control is unreviewed in "
             "ManaEngine; the attempt must stop instead of guessing.", ("R_HEALING", "R_AMOUNT_ORDER"),
             compare_legacy=True),
    # ---------------- Drain Soul: Lifesteal, DEAL_DAMAGE $3 to a chosen minion ----------------
    Scenario("DS-1", DRAIN, "DEAL_DAMAGE+LIFESTEAL", "normal", "senjin", (play(DRAIN, ("OPP_MINION", SENJIN)),),
             "COMPLETED", "3 damage to a 3/5 -> 3/2; Lifesteal heals the caster's hero by the damage dealt: 26 -> 29.",
             ("R_DAMAGE", "R_HEALING"),
             {"OPP.board": [f"{SENJIN} 3/2/5"], "SELF.hero_health": 29, "SELF.available_mana": 2,
              "SELF.hand": [BOLT, FLASH, F, F, F, F], "SELF.hand_size": 6}, compare_legacy=True,
             evidence="REAL_LOG_CONSISTENT"),
    Scenario("DS-2", DRAIN, "DEAL_DAMAGE+LIFESTEAL", "legality", "senjin", (), "COMPLETED",
             "'to a minion' (any side): heroes are not legal targets.", ("R_PLAY_TARGET",),
             expected_targets=(f"OPP_MINION:{SENJIN}",)),
    Scenario("DS-3", DRAIN, "DEAL_DAMAGE+LIFESTEAL", "legality", "drain_no_minion", (), "COMPLETED",
             "A spell needs a legal target: with no minions in play it cannot be cast.", ("R_PLAY_TARGET",),
             expected_targets=()),
    Scenario("DS-4", DRAIN, "DEAL_DAMAGE+LIFESTEAL", "edge", "thalnos", (play(DRAIN, ("OPP_MINION", RAZORJAW)),),
             "COMPLETED",
             "Spell Damage makes it 4; 4 damage to a 3/1 counts in full for Lifesteal (overkill included): "
             "27 + 4 caps at 30. Real logs show 3 damage into a 2-Health minion healing 3.",
             ("R_SPELL_DAMAGE", "R_HEALING", "R_DEATH_PHASE"),
             {"OPP.board": [], "SELF.hero_health": 30, "SELF.available_mana": 1,
              "SELF.hand": [BOLT, F, F, F], "SELF.hand_size": 4}, compare_legacy=True,
             evidence="REAL_LOG_CONSISTENT"),
    # ---------------- Overheat: seq ENCHANT ALL friendly +1/+1; pay discard random Nature spell -> +1/+1 ----------------
    Scenario("OH-1", OVERHEAT, "ENCHANT", "normal", "overheat", (play(OVERHEAT),), "COMPLETED",
             "No Nature spell in hand: only the first +1/+1; nothing is discarded. Cost 3.",
             ("R_ENCHANTMENT", "R_PAYMENT", "R_STEP_BOUNDARY"),
             {"SELF.board": [f"{LEECH} 3/2/2", f"{RAZORJAW} 4/2/2"], "SELF.available_mana": 0,
              "SELF.hand": [F, F, F], "SELF.hand_size": 3},
             expected_trace=("FRIENDLY_MINIONS_BUFF", "RANDOM_SPELL_DISCARD_EMPTY"), compare_legacy=True),
    Scenario("OH-2", OVERHEAT, "ENCHANT+PAY", "order", "overheat_nature", (play(OVERHEAT),), "COMPLETED",
             "Buff, then discard the only Nature spell, then the paid +1/+1 on the same minions: +2/+2 in total.",
             ("R_ENCHANTMENT", "R_PAYMENT", "R_STEP_BOUNDARY"),
             {"SELF.board": [f"{LEECH} 4/3/3", f"{RAZORJAW} 5/3/3"], "SELF.available_mana": 0,
              "SELF.hand": [F, F], "SELF.hand_size": 2},
             expected_trace=("FRIENDLY_MINIONS_BUFF", "RANDOM_SPELL_DISCARDED", "FRIENDLY_MINIONS_BUFF"),
             compare_legacy=True),
    Scenario("OH-3", OVERHEAT, "ENCHANT+PAY", "edge", "overheat_two_nature", (play(OVERHEAT),), "COMPLETED",
             "Two Nature spells: exactly one of them is discarded at random; +2/+2 either way.",
             ("R_PAYMENT", "R_RANDOM_LIVE"),
             expected_any=(
                 {"SELF.board": [f"{LEECH} 4/3/3", f"{RAZORJAW} 5/3/3"], "SELF.available_mana": 0,
                  "SELF.hand": [SPARKS, F], "SELF.hand_size": 2},
                 {"SELF.board": [f"{LEECH} 4/3/3", f"{RAZORJAW} 5/3/3"], "SELF.available_mana": 0,
                  "SELF.hand": [BOLT, F], "SELF.hand_size": 2},
             ), compare_legacy=True),
    Scenario("OH-4", OVERHEAT, "ENCHANT+PAY", "edge", "overheat_empty_board", (play(OVERHEAT),), "COMPLETED",
             "No minions: the payment can still be made, so the Nature spell is discarded and nobody is buffed.",
             ("R_PAYMENT",),
             {"SELF.available_mana": 0, "SELF.hand": [F, F, F, F], "SELF.hand_size": 4}, compare_legacy=True,
             notes="R_PAYMENT is UNVERIFIED: whether Hearthstone discards with an empty board is not evidenced."),
    Scenario("OH-5", OVERHEAT, "ENCHANT+PAY", "unsupported", "unsupported_in_hand", (END,),
             "UNSIMULATABLE:UNSUPPORTED_CARD_ENTERED_HAND",
             "A hand holding a card without a ManaEngine declaration is refused as a whole position; it is not "
             "simulated with that card ignored (it would also be a discard candidate).", (), compare_legacy=True,
             notes="Expected code corrected after the first run: UNSUPPORTED_CARD_IN_ACTIVE_HAND was predicted; the "
                   "engine already refuses when the card enters the hand at the opening draw."),
)


# Mutations of the declared IR. Each `expect` was written before the first run; `validator` is the expected strict v0.2
# verdict. A mutation that translates is executed through the bridge on the scenario's position.
@dataclass(frozen=True)
class Mutation:
    id: str
    card: str
    klass: str
    description: str
    change: Callable[[dict], None]


MUTATIONS = {m.id: m for m in (
    Mutation("M-amount", BOLT, "amount", "damage n 3 -> 5", _set((*EFFECT, "amount", "n"), 5)),
    Mutation("M-side", BOLT, "owner/side", "target side ANY -> ENEMY", _set((*TARGET, "choose", "side"), "ENEMY")),
    Mutation("M-area", BOLT, "target", "chosen target -> ALL enemy characters (binding removed)",
             _steps(_del(TARGET), _set((*EFFECT, "to"), {"pick": "ALL", "type": "CHARACTER", "side": "ENEMY"}))),
    Mutation("M-unused-target", BOLT, "target", "effect -> ALL enemy characters, chosen target kept",
             _set((*EFFECT, "to"), {"pick": "ALL", "type": "CHARACTER", "side": "ENEMY"})),
    Mutation("M-op-heal", BOLT, "target", "DEAL_DAMAGE $3 -> RESTORE_HEALTH #3",
             _steps(_set((*EFFECT, "op"), "RESTORE_HEALTH"), _set((*EFFECT, "amount", "mark"), "#"))),
    Mutation("M-no-overload", BOLT, "removed keyword", "Overload keyword removed", _del(("keywords",))),
    Mutation("M-overload-2", BOLT, "amount", "Overload amount 1 -> 2", _set(("keywords", 0, "amount"), 2)),
    Mutation("M-mark", BOLT, "amount mark", "damage mark '$' -> '#'", _set((*EFFECT, "amount", "mark"), "#")),
    Mutation("M-unknown-op", BOLT, "unknown operation", "op -> EXPLODE", _set((*EFFECT, "op"), "EXPLODE")),
    Mutation("M-destroy", BOLT, "unknown operation", "op -> DESTROY (IR op without an engine step here)",
             _steps(_set((*EFFECT, "op"), "DESTROY"), _del((*EFFECT, "amount")))),
    Mutation("M-field", BOLT, "unknown field", "effect gains a 'condition' field",
             _set((*EFFECT, "condition"), {"cmp": ">", "left": 1, "right": 0})),
    Mutation("M-heal-2", FLASH, "amount", "heal n 5 -> 2", _set((*EFFECT, "amount", "n"), 2)),
    Mutation("M-friendly", FLASH, "owner/side", "target side ANY -> FRIENDLY",
             _set((*TARGET, "choose", "side"), "FRIENDLY")),
    Mutation("M-no-lifesteal", DRAIN, "removed keyword", "Lifesteal keyword removed", _del(("keywords",))),
    Mutation("M-any-character", DRAIN, "target", "target type MINION -> CHARACTER",
             _set((*TARGET, "choose", "type"), "CHARACTER")),
    Mutation("M-no-pay", OVERHEAT, "removed operation", "the paid second buff (pay/then) removed",
             lambda doc: _effect(doc)["seq"].pop(1)),
    Mutation("M-swap", OVERHEAT, "step order", "seq steps swapped (paid buff first)",
             lambda doc: _effect(doc)["seq"].reverse()),
    Mutation("M-enemy-buff", OVERHEAT, "owner/side", "first buff side FRIENDLY -> ENEMY",
             _set((*EFFECT, "seq", 0, "to", "side"), "ENEMY")),
    Mutation("M-stats", OVERHEAT, "amount", "first buff +1/+1 -> +2/+1", _set((*EFFECT, "seq", 0, "attack"), 2)),
    Mutation("M-stats-2", OVERHEAT, "amount", "both buffs +1/+1 -> +2/+2",
             _steps(*(_set((*EFFECT, "seq", 0, key), 2) for key in ("attack", "health")),
                    *(_set((*EFFECT, "seq", 1, "then", key), 2) for key in ("attack", "health")))),
    # Post-hoc probe, added after the first run showed M-stats passing the strict validator.
    Mutation("M-stats-9", OVERHEAT, "amount", "first buff +1/+1 -> +9/+9 (second buff unchanged)",
             _steps(_set((*EFFECT, "seq", 0, "attack"), 9), _set((*EFFECT, "seq", 0, "health"), 9))),
    Mutation("M-heal-between", OVERHEAT, "step order", "a heal-all-friendly step inserted before the payment",
             _insert_before_pay({"op": "RESTORE_HEALTH", "to": {"pick": "ALL", "type": "CHARACTER", "side": "FRIENDLY"},
                                 "amount": {"n": 1, "mark": "#"}})),
    Mutation("M-damage-between", OVERHEAT, "step order", "an enemy-minion damage step inserted before the payment",
             _insert_before_pay({"op": "DEAL_DAMAGE", "to": {"pick": "ALL", "type": "MINION", "side": "ENEMY"},
                                 "amount": {"n": 1, "mark": "$"}})),
    Mutation("M-partial", FLASH, "status", "status FULL -> PARTIAL", _set(("status",), "PARTIAL")),
    Mutation("M-version", FLASH, "version", "ir card-ir/0.2 -> card-ir/0.1", _set(("ir",), "card-ir/0.1")),
)}

LB_HAND = {"SELF.available_mana": 0, "SELF.hand": [F, F, F], "SELF.hand_size": 3}
MUTATION_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("MUT-amount", BOLT, "DEAL_DAMAGE", "mutation", "bolt_turn1", (play(BOLT, "OPP_HERO"),), "COMPLETED",
             "Executed damage follows the IR amount: 5, not the card's 3.", ir="M-amount", expected_validator="REJECTED",
             expected_changes={"OPP.hero_health": 25, "SELF.pending_overload": 1, **LB_HAND}),
    Scenario("MUT-side", BOLT, "DEAL_DAMAGE", "mutation", "bolt_turn1", (play(BOLT, "SELF_HERO"),), "NO_LEGAL_ACTION",
             "An ENEMY-side target removes the caster's hero from the legal targets.", ir="M-side",
             expected_validator="ACCEPTED", expected_targets=("OPP_HERO",)),
    Scenario("MUT-area", BOLT, "DEAL_DAMAGE", "mutation", "senjin", (play(BOLT),), "COMPLETED",
             "An ALL enemy characters area hits the enemy hero and Sen'jin, with no target chosen.", ir="M-area",
             expected_validator="REJECTED",
             expected_changes={"OPP.hero_health": 27, "OPP.board": [f"{SENJIN} 3/2/5"], "SELF.available_mana": 3,
                               "SELF.pending_overload": 1, "SELF.hand": [DRAIN, FLASH, F, F, F, F],
                               "SELF.hand_size": 6}),
    Scenario("MUT-unused-target", BOLT, "DEAL_DAMAGE", "mutation", "bolt_turn1", (play(BOLT, "OPP_HERO"),),
             "REFUSED:UNUSED_TARGET", "A chosen target that no step uses is refused.", ir="M-unused-target",
             expected_validator="REJECTED"),
    Scenario("MUT-op-heal", BOLT, "RESTORE_HEALTH", "mutation", "senjin", (play(BOLT, "SELF_HERO"),), "COMPLETED",
             "The operation decides the effect: the same card now restores 3 (26 -> 29) and still Overloads.",
             ir="M-op-heal", expected_validator="REJECTED",
             expected_changes={"SELF.hero_health": 29, "SELF.available_mana": 3, "SELF.pending_overload": 1,
                               "SELF.hand": [DRAIN, FLASH, F, F, F, F], "SELF.hand_size": 6}),
    Scenario("MUT-no-overload", BOLT, "DEAL_DAMAGE", "mutation", "bolt_turn1", (play(BOLT, "OPP_HERO"),),
             "REFUSED:ENGINE_CATALOG_REJECTED",
             "The card's printed Overload mechanic is no longer represented; ManaEngine's catalog guard refuses it.",
             ir="M-no-overload", expected_validator="REJECTED"),
    Scenario("MUT-overload-2", BOLT, "OVERLOAD", "mutation", "bolt_turn1", (play(BOLT, "OPP_HERO"),), "COMPLETED",
             "Owed Overload follows the IR amount.", ir="M-overload-2", expected_validator="REJECTED",
             expected_changes={"OPP.hero_health": 27, "SELF.pending_overload": 2, **LB_HAND}),
    Scenario("MUT-mark", BOLT, "DEAL_DAMAGE", "mutation", "bolt_turn1", (play(BOLT, "OPP_HERO"),),
             "REFUSED:UNSUPPORTED_AMOUNT", "A damage amount with a healing mark has no faithful engine step.",
             ir="M-mark", expected_validator="REJECTED"),
    Scenario("MUT-unknown-op", BOLT, "DEAL_DAMAGE", "mutation", "bolt_turn1", (play(BOLT, "OPP_HERO"),),
             "REFUSED:UNSUPPORTED_OP", "An unknown operation stops translation.", ir="M-unknown-op",
             expected_validator="REJECTED"),
    Scenario("MUT-destroy", BOLT, "DEAL_DAMAGE", "mutation", "bolt_turn1", (play(BOLT, "OPP_HERO"),),
             "REFUSED:UNSUPPORTED_OP", "A real IR operation without an engine step in this pilot stops translation.",
             ir="M-destroy", expected_validator="REJECTED"),
    Scenario("MUT-field", BOLT, "DEAL_DAMAGE", "mutation", "bolt_turn1", (play(BOLT, "OPP_HERO"),),
             "REFUSED:UNKNOWN_FIELD", "A field the translator does not consume is never ignored.", ir="M-field",
             expected_validator="REJECTED"),
    Scenario("MUT-heal-2", FLASH, "RESTORE_HEALTH", "mutation", "hero22", (play(FLASH, "SELF_HERO"),), "COMPLETED",
             "Restored Health follows the IR amount: 22 -> 24.", ir="M-heal-2", expected_validator="REJECTED",
             expected_changes={"SELF.hero_health": 24, "SELF.available_mana": 2, "SELF.hand": [DRAIN, F, F, F, F],
                               "SELF.hand_size": 5}),
    Scenario("MUT-friendly", FLASH, "RESTORE_HEALTH", "mutation", "hero22", (play(FLASH, "OPP_HERO"),),
             "NO_LEGAL_ACTION", "A FRIENDLY target excludes the enemy hero.", ir="M-friendly",
             expected_validator="ACCEPTED", expected_targets=("SELF_HERO",)),
    Scenario("MUT-no-lifesteal", DRAIN, "DEAL_DAMAGE", "mutation", "senjin", (play(DRAIN, ("OPP_MINION", SENJIN)),),
             "REFUSED:ENGINE_CATALOG_REJECTED",
             "The printed Lifesteal mechanic is no longer represented; ManaEngine's catalog guard refuses it.",
             ir="M-no-lifesteal", expected_validator="REJECTED"),
    Scenario("MUT-any-character", DRAIN, "DEAL_DAMAGE+LIFESTEAL", "mutation", "senjin", (play(DRAIN, "OPP_HERO"),),
             "COMPLETED", "A CHARACTER target admits heroes: 3 to the enemy hero, Lifesteal 26 -> 29.",
             ir="M-any-character", expected_validator="ACCEPTED",
             expected_targets=("OPP_HERO", f"OPP_MINION:{SENJIN}", "SELF_HERO"),
             expected_changes={"OPP.hero_health": 27, "SELF.hero_health": 29, "SELF.available_mana": 2,
                               "SELF.hand": [BOLT, FLASH, F, F, F, F], "SELF.hand_size": 6}),
    Scenario("MUT-no-pay", OVERHEAT, "ENCHANT", "mutation", "overheat_nature", (play(OVERHEAT),), "COMPLETED",
             "Without the paid step only +1/+1 happens and the Nature spell stays in hand.", ir="M-no-pay",
             expected_validator="REJECTED",
             expected_changes={"SELF.board": [f"{LEECH} 3/2/2", f"{RAZORJAW} 4/2/2"], "SELF.available_mana": 0,
                               "SELF.hand": [BOLT, F, F], "SELF.hand_size": 3}),
    Scenario("MUT-swap", OVERHEAT, "ENCHANT+PAY", "mutation", "overheat_nature", (play(OVERHEAT),),
             "REFUSED:UNBOUND_REF", "Swapped order refers to 'buffed' before it is bound.", ir="M-swap",
             expected_validator="REJECTED"),
    Scenario("MUT-enemy-buff", OVERHEAT, "ENCHANT", "mutation", "overheat_nature", (play(OVERHEAT),),
             "REFUSED:UNSUPPORTED_SELECTOR", "The engine has no enemy-wide buff; the owner change is refused.",
             ir="M-enemy-buff", expected_validator="REJECTED"),
    Scenario("MUT-stats", OVERHEAT, "ENCHANT", "mutation", "overheat_nature", (play(OVERHEAT),),
             "REFUSED:UNSUPPORTED_STATS", "+2/+1 has no engine buff (it adds equal Attack and Health).", ir="M-stats",
             expected_validator="REJECTED"),
    Scenario("MUT-stats-2", OVERHEAT, "ENCHANT", "mutation", "overheat_nature", (play(OVERHEAT),), "COMPLETED",
             "Both buffs +2/+2: +4/+4 in total, Nature spell discarded.", ir="M-stats-2", expected_validator="REJECTED",
             expected_changes={"SELF.board": [f"{LEECH} 6/5/5", f"{RAZORJAW} 7/5/5"], "SELF.available_mana": 0,
                               "SELF.hand": [F, F], "SELF.hand_size": 2}),
    Scenario("MUT-stats-9", OVERHEAT, "ENCHANT", "mutation", "overheat_nature", (play(OVERHEAT),), "COMPLETED",
             "+9/+9 then the paid +1/+1: Leech 2/1 -> 12/11, Razorjaw 3/1 -> 13/11; Bolt discarded. Executed exactly "
             "as written.", ir="M-stats-9",
             expected_validator="ACCEPTED",
             expected_changes={"SELF.board": [f"{LEECH} 12/11/11", f"{RAZORJAW} 13/11/11"], "SELF.available_mana": 0,
                               "SELF.hand": [F, F], "SELF.hand_size": 2},
             notes="Post-hoc probe (added after the first run showed M-stats accepted). Its validator prediction "
                   "(ACCEPTED) was wrong: the slack in number matching is one number, so changing two is caught."),
    Scenario("MUT-heal-between", OVERHEAT, "ENCHANT+PAY", "mutation", "overheat_nature", (play(OVERHEAT),),
             "REFUSED:REF_NOT_EQUIVALENT", "A non-neutral step between binding and reuse blocks re-selection.",
             ir="M-heal-between", expected_validator="REJECTED"),
    Scenario("MUT-damage-between", OVERHEAT, "ENCHANT+PAY", "mutation", "overheat_nature", (play(OVERHEAT),),
             "REFUSED:AREA_AFTER_DAMAGE", "A buff area after damage may differ on mortally wounded minions.",
             ir="M-damage-between", expected_validator="REJECTED"),
    Scenario("MUT-partial", FLASH, "RESTORE_HEALTH", "mutation", "hero22", (play(FLASH, "SELF_HERO"),),
             "REFUSED:STATUS_NOT_FULL", "Only FULL declarations are executed.", ir="M-partial",
             expected_validator="REJECTED"),
    Scenario("MUT-version", FLASH, "RESTORE_HEALTH", "mutation", "hero22", (play(FLASH, "SELF_HERO"),),
             "REFUSED:VERSION", "Only card-ir/0.2 is translated.", ir="M-version", expected_validator="REJECTED"),
)
