"""The closed vocabulary of Card IR v0.2: the v0.1 vocabulary plus the delta in reports/card_ir_v02/CHANGELOG.md.

``vocabulary.py`` (v0.1) is frozen and pinned by hash; v0.2 copies its tables and adds or replaces entries here. A v0.1
declaration keeps v0.1 meanings: it is validated only by v0.1 tools and never reinterpreted with these rules.

Two rule bases are new in v0.2:

* ``DEFINITION`` -- the rule defines what an IR construct means (for example which turn ``NEXT_TURN`` covers). It makes
  no claim about any card: whether a card's text maps to the construct is a decision in that card's declaration.
* ``PROVISIONAL`` rules (any basis, listed in ``PROVISIONAL_RULES``) are game rules that are not confirmed well enough to
  be an unconditional contract. A declaration that needs one must acknowledge it with an ``UNKNOWN_RULE`` dependency
  whose ``rule`` field names it, so the gap stays explicit in its status.
"""

from __future__ import annotations

from dataclasses import replace

from manamind.card_ir.vocabulary import BASES, ELEMENTS, RULES, Element, Rule

RULE_BASES_V02 = (*BASES, "DEFINITION")

# Recorded in reports/card_ir_v02/README.md: the independent rules check by Claude Sonnet (summarised in the
# CARD-IR-V02-IMPLEMENTATION task, 2026-10-26) plus the wiki pages cited in IR_V02_PROPOSAL.md. Not replay proof.
_SONNET = "independent Sonnet rules check (CARD-IR-V02 task, 2026-10-26)"
_PROPOSAL = "reports/card_ir_b1_independent_review/IR_V02_PROPOSAL.md"

_CHANGED_RULES = (
    Rule("R_COST", "Current cost = base cost, then every cost modifier in the order it was applied: a set-to-N "
         "replaces the running value, reductions and increases change the running value; the floor of 0 is applied "
         "once, after all modifiers", "COMMUNITY_RULES", f"{_SONNET}: order confirmed; {_PROPOSAL} R4"),
    Rule("R_PLAYER_EFFECT", "A player-level effect lives on the player, independent of its source, from its start to "
         "the end of its duration. With integer uses it applies to the next N matching cards (use_unit CARD) or "
         "effects (EFFECT); what one use is stays UNKNOWN", "UNKNOWN",
         "v0.1 meaning kept for integer uses; ALL_MATCHING is R_PLAYER_AURA"),
    Rule("R_DECK_POSITION", "RANDOM inserts each card at a random deck position; TOP makes it the next card drawn; "
         "BOTTOM puts it after every card already in the deck; count N inserts N cards one at a time",
         "UNVERIFIED", "deck size limit not covered"),
)
_NEW_RULES = (
    Rule("R_SURVIVE", "'alive: true' holds for an entity that, after the current step and the reactions it caused and "
         "before the death phase, is still in play with Health > 0 and not pending destruction", "COMMUNITY_RULES",
         f"{_SONNET}: survival after reactions confirmed; {_PROPOSAL} R3"),
    Rule("R_RETURN_TO_HAND", "Moving a minion from play to a hand gives the card without its damage, enchantments, "
         "Silence or other in-play state; a reference bound to it then denotes the card in hand", "COMMUNITY_RULES",
         f"{_SONNET}: confirmed with caveats (full hand is R_RETURN_FULL_HAND); {_PROPOSAL} R1"),
    Rule("R_RETURN_FULL_HAND", "With a full hand the moved minion is destroyed instead (it dies: Deathrattles and death "
         "triggers run) and later steps that refer to it do nothing", "UNVERIFIED", f"{_PROPOSAL} R1 (wiki only)"),
    Rule("R_RANDOM_SPLIT", "'Randomly split N damage' is N packets of 1 damage, each to a random live candidate chosen "
         "per packet (R_RANDOM_LIVE); a '$' mark on N adds packets", "COMMUNITY_RULES",
         f"{_SONNET}: confirmed for 'randomly split'; IR_SPEC.md section 7 encoding"),
    Rule("R_SPLIT_UNQUALIFIED", "'Split among' without 'randomly' resolves like R_RANDOM_SPLIT", "UNKNOWN",
         f"{_SONNET}: not to be equated automatically"),
    Rule("R_FREEZE", "FREEZE gives each selected character the Frozen state; a Frozen character cannot attack; "
         "freezing deals no damage", "COMMUNITY_RULES", f"{_PROPOSAL} R6 (wiki 'Freeze')"),
    Rule("R_FREEZE_THAW", "When Frozen is removed (commonly at the end of its controller's next turn; details depend on "
         "whether the character could still attack)", "UNKNOWN", f"{_SONNET}: removal details not fully confirmed"),
    Rule("R_TURN_WINDOW", "NEXT_TURN of player P covers the first turn of P that starts after the effect is created, "
         "from its start to its end; THIS_GAME lasts until the game ends, independent of the source", "DEFINITION"),
    Rule("R_DELAYED_START", "starts_after {player P, turn_starts N}: the effect is inactive (affects nothing) until the "
         "N-th start of a turn of P after its creation and becomes active at that turn start. How a card's text maps "
         "to P and N is the card's decision, not this rule", "DEFINITION",
         "not derived from any single card (Aviana is one user-observed instance)"),
    Rule("R_PLAYER_AURA", "uses ALL_MATCHING: while active, every card in the effect's zones that matches applies_to is "
         "modified, including cards that enter those zones later; a card that leaves the zones loses it",
         "DEFINITION", "whether a given card behaves this way is that card's decision"),
    Rule("R_ATTACK_ROLES", "ATTACK_DECLARED: attacker is the character that attacks, defender the character it attacks; "
         "WHEN fires on declaration before combat, AFTER once combat and its reactions resolved", "DEFINITION"),
    Rule("R_ATTACK_REDIRECT", "Which defender role filters see when the attack target changes after declaration",
         "UNKNOWN"),
    Rule("R_DAMAGE_EVENT_AMOUNT", "A DAMAGE_DEALT AMOUNT counter adds the damage actually dealt per packet: prevented "
         "damage (Divine Shield, Immune) counts 0, damage absorbed by Armor counts, overkill counts in full",
         "UNVERIFIED", f"{_PROPOSAL} E7 (wiki only); boundary sources (Secrets, created spells) not settled"),
)
PROVISIONAL_RULES = frozenset({"R_RETURN_FULL_HAND", "R_SPLIT_UNQUALIFIED", "R_FREEZE_THAW", "R_ATTACK_REDIRECT",
                               "R_DAMAGE_EVENT_AMOUNT"})

_changed = {rule.rule_id: rule for rule in _CHANGED_RULES}
RULES_V02: dict[str, Rule] = {rule.rule_id: _changed.get(rule.rule_id, rule) for rule in RULES.values()}
RULES_V02.update({rule.rule_id: rule for rule in _NEW_RULES})


def _e(element_id: str, meaning: str, rules: tuple[str, ...] = (), signature: str | None = None) -> Element:
    return Element(element_id, "GENERIC", meaning, rules, signature)


_CHANGED_ELEMENTS = {
    "event:ATTACK_DECLARED": "an attack between an attacker and a defender (roles in R_ATTACK_ROLES)",
    "op:ADD_PLAYER_EFFECT": "attach a player-level effect: duration, cardinality (uses), zones, delayed start",
    "op:SHUFFLE_INTO_DECK": "insert cards into a deck at a RANDOM (default), TOP or BOTTOM position",
}
_NEW_ELEMENTS = (
    _e("op:FREEZE", "freeze each selected character", ("R_FREEZE", "R_FREEZE_THAW"), r"\bfreeze\b"),
    _e("duration:THIS_GAME", "until the end of the game", ("R_TURN_WINDOW",), r"\bthis game\b|\brest of the game\b"),
    _e("duration:NEXT_TURN", "during the next turn of a named player", ("R_TURN_WINDOW",), r"\bnext turn\b"),
    _e("player_effect:starts_after", "the player effect becomes active only at a later turn start of a named player",
       ("R_DELAYED_START",), r"\b(two|three|four|five|\d+)[ -]turns?\b"),
    _e("player_effect:zones", "the zones whose cards a cost player effect modifies", ("R_COST",)),
    _e("player_effect:ALL_MATCHING", "the player effect applies to every matching card while active",
       ("R_PLAYER_AURA",), r"\byour (cards|spells|minions) cost\b|\bopponent's \w+ cost\b"),
    _e("event_role:attacker", "the attacking character of an ATTACK_DECLARED event", ("R_ATTACK_ROLES",),
       r"\b(this|it|this minion) attacks\b"),
    _e("event_role:defender", "the attacked character of an ATTACK_DECLARED event",
       ("R_ATTACK_ROLES", "R_ATTACK_REDIRECT"), r"\bis attacked\b|\battacks an? (minion|hero|character)\b"),
    _e("pred:alive", "an entity survived (R_SURVIVE) or did not", ("R_SURVIVE",), r"\bsurviv|\bdies\b"),
    _e("counter:DAMAGE_DEALT", "total damage actually dealt by matching sources", ("R_DAMAGE_EVENT_AMOUNT",),
       r"\bdamage (you('ve)?|your \w+) dealt\b|\bdamage dealt\b"),
    _e("value:mul", "product of two values, one a literal from the text", (), r"\bfor each\b"),
    _e("deck_position:RANDOM", "insert at a random position (shuffle)", ("R_DECK_POSITION",), r"\bshuffle\b"),
    _e("deck_position:TOP", "insert on top of the deck", ("R_DECK_POSITION",), r"\btop of\b[^.]*\bdeck\b"),
    _e("deck_position:BOTTOM", "insert at the bottom of the deck", ("R_DECK_POSITION",), r"\bbottom of\b[^.]*\bdeck\b"),
    _e("move:PLAY_TO_HAND", "a minion moves from play to a hand ('return')", ("R_RETURN_TO_HAND", "R_RETURN_FULL_HAND"),
       r"\breturn\b"),
)

ELEMENTS_V02: dict[str, Element] = {
    element.element_id: replace(element, meaning=_CHANGED_ELEMENTS.get(element.element_id, element.meaning))
    for element in ELEMENTS.values()}
ELEMENTS_V02.update({element.element_id: element for element in _NEW_ELEMENTS})

assert all(rule in RULES_V02 for element in ELEMENTS_V02.values() for rule in element.rules)
assert all(rule.basis in RULE_BASES_V02 for rule in RULES_V02.values())
assert PROVISIONAL_RULES <= set(RULES_V02)
