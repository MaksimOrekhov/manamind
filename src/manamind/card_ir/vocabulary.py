"""The closed vocabulary of Card IR v0.1 and the universal rules an executor would have to implement.

An *element* is one thing an executor must implement distinctly: an operation, a control construct, an ability kind,
a selector mode, a predicate kind, a value kind, a condition, an event, a timing, a duration, a keyword rule, a rule
parameter, a card source, a counter, a resource. Literal numbers and card IDs are data, not elements.

Tiers: ``GENERIC`` is defined without reference to any card or set; ``MECHANIC`` is a reusable keyword or set mechanic
rule (defined once, then used by every card that has the keyword); ``CARD`` would be logic for one card. v0.1 has no
``CARD`` element: a card that needs one is reported as PARTIAL or UNSUPPORTED instead.

``signature`` is a regular expression over normalised lower-case card text used only to screen how many other cards
mention the same thing (a heuristic for reuse potential, never a parser).

Rule ``basis`` says where the semantics come from: ``PROJECT_REVIEWED`` (reviewed in a ManaMind report, still not replay
proof), ``LOG_OBSERVED`` (seen in project Power.log analyses), ``COMMUNITY_RULES`` (independent rules research cited in
project reports), ``UNVERIFIED`` (common game knowledge with no source in the project) and ``UNKNOWN`` (open question).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    meaning: str
    basis: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class Element:
    element_id: str
    tier: str
    meaning: str
    rules: tuple[str, ...] = ()
    signature: str | None = None
    # A mechanic whose rule is not described by card text and has no reviewed source in the project: a declaration
    # that uses it must carry a KEYWORD_RULE dependency.
    needs_source: bool = False

    @property
    def category(self) -> str:
        return self.element_id.split(":", 1)[0]


BASES = ("PROJECT_REVIEWED", "LOG_OBSERVED", "COMMUNITY_RULES", "UNVERIFIED", "UNKNOWN")

_RULES = (
    Rule("R_STEP_BOUNDARY", "A sequence step finishes, with the reactions it causes, before the next step is evaluated; "
         "deaths are not processed between steps", "PROJECT_REVIEWED",
         "reports/manaengine_damage_group_20261005/DAMAGE_GROUP_RULES_REVIEW.md requirements 2 and 13"),
    Rule("R_DEATH_PHASE", "A destroyed or 0-Health minion stays in play mortally wounded until the outer phase boundary, "
         "then dead minions leave in order and their Deathrattles queue", "PROJECT_REVIEWED",
         "MORTALITY_POLICY.md; ManaEngine event pass"),
    Rule("R_AREA_SNAPSHOT", "An ALL selector fixes its members when the step starts (mortally wounded included, new "
         "entities excluded)", "PROJECT_REVIEWED", "DAMAGE_GROUP_RULES_REVIEW.md requirements 1, 8 and 12"),
    Rule("R_RANDOM_LIVE", "A RANDOM pick considers only live candidates (not mortally wounded, not pending destroy), "
         "is re-evaluated for every pick, and an empty candidate set does nothing", "COMMUNITY_RULES",
         "Advanced rulebook as cited in MORTALITY_POLICY.md"),
    Rule("R_DAMAGE", "A damage packet: Divine Shield and Immune prevent it, a hero loses Armor first, damage events are "
         "dispatched after the step's mutations", "PROJECT_REVIEWED", "DAMAGE_GROUP_RULES_REVIEW.md requirement 9"),
    Rule("R_SPELL_DAMAGE", "A '$' amount adds the controller's Spell Damage once per step (CURRENT_AT_STEP)",
         "PROJECT_REVIEWED", "DAMAGE_GROUP_RULES_REVIEW.md requirement 11"),
    Rule("R_HEALING", "A '#' amount adds the controller's healing bonus per packet and is capped at missing Health",
         "PROJECT_REVIEWED", "docs/proposals/20261008_engine_primitive1_healing_v1.md"),
    Rule("R_AMOUNT_ORDER", "Order of additive bonuses (Spell Damage, healing bonus), multipliers (doubling) and "
         "replacements (healing becomes damage)", "UNKNOWN",
         "manamind.outcome.world ObservedContext: order with doubling unverified"),
    Rule("R_LAST_KNOWN", "A value read from an entity that has left play is its last known value", "UNVERIFIED"),
    Rule("R_SUMMON_POSITION", "Battlecry summons enter to the right of the source, Deathrattle summons at its slot, other "
         "summons at the right end", "UNVERIFIED"),
    Rule("R_BOARD_LIMIT", "At most 7 minions per side; extra summons fail and later steps see only those summoned",
         "UNVERIFIED"),
    Rule("R_HAND_LIMIT", "At most 10 cards in hand; an extra card is destroyed", "UNVERIFIED"),
    Rule("R_DRAW", "A draw takes the top deck card; an empty deck causes fatigue; a full hand destroys the card",
         "UNVERIFIED"),
    Rule("R_TRIGGER_TIMING", "WHENEVER fires on the event, AFTER once the event has resolved, AT at a turn phase, WHEN "
         "(Secrets) before the event resolves", "COMMUNITY_RULES", "DAMAGE_GROUP_RULES_REVIEW.md S3"),
    Rule("R_TRIGGER_ORDER", "Simultaneous triggers resolve in the order their sources entered play; nested consequences "
         "finish before siblings", "PROJECT_REVIEWED", "DAMAGE_GROUP_RULES_REVIEW.md requirements 10 and 13"),
    Rule("R_DEATHRATTLE", "A Deathrattle resolves after its owner leaves play, from its last position; Silence removes "
         "it; Reborn returns the minion after its Deathrattles", "PROJECT_REVIEWED",
         "reports/manaengine_reborn_integration_20261005/REBORN_RULES_EVIDENCE.md (partly)"),
    Rule("R_ENCHANTMENT", "Stat and keyword changes are enchantments on the entity; enchantments on a card in hand stay "
         "when it is played; Silence removes them", "UNVERIFIED"),
    Rule("R_AURA", "Continuous effects are recomputed between steps; recomputation inside one step is unreviewed",
         "UNKNOWN", "FUTURE-ARCHITECTURE-RESEARCH-1 v1 1.2: Sleet Storm + Time-Twisted Seer"),
    Rule("R_COST", "Current cost = base cost with modifiers, floored at 0; the order of set-to-N and reductions",
         "UNKNOWN"),
    Rule("R_PLAY_TARGET", "A CHOSEN target is fixed when the card is played; a spell needs a legal target, a Battlecry "
         "without one resolves without it", "UNVERIFIED", "legal targets are listed in Power.log option menus"),
    Rule("R_HIDDEN_ZONE", "Effects on a hidden zone happen but are not observable to SELF; the IR never fills in the "
         "hidden identities", "PROJECT_REVIEWED", "AGENTS.md information contract"),
    Rule("R_COPY", "A copy duplicates the card and (how much of) its current state", "UNKNOWN",
         "ManaEngine INSTANCE_COPY_V1 admits only unmodified instances"),
    Rule("R_TRANSFORM", "Transform replaces the entity with a new instance of the target card without enchantments",
         "UNVERIFIED"),
    Rule("R_SILENCE", "Silence removes card-text abilities, enchantments and keywords", "UNVERIFIED"),
    Rule("R_POOL", "A pool's membership comes from an external reviewed manifest; outcomes are never pruned or rerolled",
         "PROJECT_REVIEWED", "experiments/manaengine/README.md (pool manifests)"),
    Rule("R_DISCOVER", "Offer distinct options from the pool, the controller picks one", "UNKNOWN",
         "option count and pool rules are not in HearthstoneJSON"),
    Rule("R_PLAYER_EFFECT", "A player-level effect has a duration and a use counter and applies to the next matching "
         "card or effect", "UNKNOWN", "what one 'use' is (card, effect, packet) is not stated in text"),
    Rule("R_COUNTERS", "Per-player history counters: cards played, spells cast, per turn, per game, last turn",
         "PROJECT_REVIEWED", "ManaEngine keeps bespoke counters (spells_cast_this_turn, minion types last turn)"),
    Rule("R_PAYMENT", "PAY runs its effect only if the whole cost can be paid, then pays it; otherwise nothing happens",
         "UNVERIFIED"),
    Rule("R_CHOICE", "CHOOSE asks the controller to pick among candidates during resolution", "UNKNOWN",
         "whether it is a play-time target or a sub-choice"),
    Rule("R_LOOP_BOUND", "A conditional repeat terminates; the game's own bound is not documented", "UNKNOWN"),
    Rule("R_DECK_POSITION", "Shuffling inserts at a random deck position; 'bottom' inserts last", "UNVERIFIED"),
    Rule("R_CAST", "CAST resolves a spell without paying for it or playing it from hand", "UNKNOWN",
         "whether cast-triggers and counters fire"),
    Rule("R_NAME_REFERENCE", "A card named in text is matched by a resolved list of card IDs, not by display name",
         "UNKNOWN", "HearthstoneJSON has no card-to-card relation field"),
    Rule("R_COLOSSAL", "Colossal +N summons N appendage minions next to the minion when it is played", "PROJECT_REVIEWED",
         "reports/manaengine_vulcanos_20261005/COLOSSAL_RULES_REVIEW.md"),
    Rule("R_KINDRED", "Kindred holds if the controller played, on their previous turn, a card sharing a minion type or "
         "spell school with this card", "UNVERIFIED",
         "ManaEngine kindred_qualified checks minion types of the previous turn only"),
    Rule("R_QUEST", "A Quest is put into the Secret zone, tracks progress and gives its reward card on completion",
         "UNVERIFIED", "OBSERVATION-AUDIT-1: QUEST, QUEST_PROGRESS(_TOTAL) tags"),
    Rule("R_SECRET", "A Secret waits in the Secret zone and triggers once on the opponent's turn", "PROJECT_REVIEWED",
         "ManaEngine secret windows"),
    Rule("R_DARK_GIFT", "A Dark Gift is one enchantment from the Dark Gift pool applied to the discovered minion",
         "PROJECT_REVIEWED", "reports/manaengine_dark_gift_integration_20261004"),
    Rule("R_PREPARE", "Prepare is a keyword whose rule is read from the game message, not from text order",
         "PROJECT_REVIEWED", "PREPARE-ROOTS-1"),
)
RULES: dict[str, Rule] = {rule.rule_id: rule for rule in _RULES}


def _e(element_id: str, tier: str, meaning: str, rules: tuple[str, ...] = (), signature: str | None = None,
       needs_source: bool = False) -> Element:
    return Element(element_id, tier, meaning, rules, signature, needs_source)


G, M = "GENERIC", "MECHANIC"
_ELEMENTS = (
    # ability kinds
    _e("ability:play", G, "effect when the card is played, cast or activated", ("R_PLAY_TARGET",)),
    _e("ability:trigger", G, "reaction to an event while the card is in its active zone",
       ("R_TRIGGER_TIMING", "R_TRIGGER_ORDER"), r"\b(whenever|after|at the (start|end) of)\b"),
    _e("ability:deathrattle", G, "effect when this minion dies", ("R_DEATHRATTLE", "R_DEATH_PHASE"), r"deathrattle"),
    _e("ability:aura", G, "continuous modifier while the card is in its active zone", ("R_AURA",),
       r"\b(costs \(\d+\) if|while|has \w|your \w+ (cost|have))"),
    _e("ability:quest", M, "quest: progress towards a goal, then a reward card", ("R_QUEST",), r"\bquest:", True),
    _e("ability:enchantment_template", G, "the card is an enchantment applied by another effect (e.g. a Dark Gift)",
       ("R_ENCHANTMENT",)),
    # play labels
    _e("label:SPELL", G, "the effect of a cast spell"),
    _e("label:BATTLECRY", G, "effect when the minion is played from hand", (), r"battlecry"),
    _e("label:LOCATION", G, "effect when the location is activated"),
    _e("label:KINDRED", M, "on-play bonus that requires Kindred", ("R_KINDRED",), r"kindred", True),
    _e("label:SECRET", M, "trigger of a Secret", ("R_SECRET",), r"\bsecret:"),
    # control
    _e("control:seq", G, "ordered steps", ("R_STEP_BOUNDARY",)),
    _e("control:if", G, "conditional step, evaluated when reached", (), r"\bif\b"),
    _e("control:repeat", G, "repeat a step a computed number of times (count evaluated once)", (),
       r"\b(repeat|randomly split|twice|for each)\b"),
    _e("control:repeat_while", G, "repeat while a condition holds, with a bound", ("R_LOOP_BOUND",),
       r"\brepeat\b.*\b(excess|until|while)\b"),
    _e("control:set", G, "assign a resolution-local variable"),
    _e("control:pay", G, "pay a cost, and only if it was paid in full run the effect", ("R_PAYMENT",),
       r"\b(spend \d+|discard [^.]* to)\b"),
    # operations
    _e("op:DEAL_DAMAGE", G, "deal damage to each selected character", ("R_DAMAGE",), r"\bdeal\b[^.]*\bdamage\b"),
    _e("op:RESTORE_HEALTH", G, "restore Health to each selected character", ("R_HEALING",), r"\brestore\b"),
    _e("op:ENCHANT", G, "attach an enchantment: stat change, keywords, attached abilities, duration",
       ("R_ENCHANTMENT",), r"\bgive\b|\bgain \+|\bhas \+"),
    _e("op:SILENCE", G, "silence each selected minion", ("R_SILENCE",), r"\bsilence\b"),
    _e("op:DESTROY", G, "destroy each selected entity", ("R_DEATH_PHASE",), r"\bdestroy\b"),
    _e("op:TRANSFORM", G, "replace each selected entity with a new card", ("R_TRANSFORM",), r"\btransform"),
    _e("op:SUMMON", G, "put minions into play", ("R_SUMMON_POSITION", "R_BOARD_LIMIT"), r"\bsummon"),
    _e("op:DRAW", G, "draw cards, optionally the first matching card", ("R_DRAW",), r"\bdraws?\b"),
    _e("op:ADD_TO_HAND", G, "put cards into a hand ('get', 'add')", ("R_HAND_LIMIT",), r"\b(get|add)\b"),
    _e("op:DISCOVER", G, "offer options from a pool and add the picked card to hand", ("R_DISCOVER", "R_HAND_LIMIT"),
       r"\bdiscover\b"),
    _e("op:CHOOSE", G, "the controller picks entities among candidates", ("R_CHOICE",), r"\bchoose an?\b(?! one)"),
    _e("op:MODIFY_COST", G, "change the cost of cards", ("R_COST",), r"\b(reduce its cost|costs? \(\d+\) (less|more))"),
    _e("op:ADD_PLAYER_EFFECT", G, "attach a player-level effect with duration and uses", ("R_PLAYER_EFFECT",),
       r"\b(your|the) next\b"),
    _e("op:SHUFFLE_INTO_DECK", G, "shuffle cards into a deck", ("R_DECK_POSITION", "R_HIDDEN_ZONE"), r"\bshuffle\b"),
    _e("op:CAST", G, "cast spells without paying for them", ("R_CAST",), r"\bcast (a|an|two|three|\d+) random\b"),
    # card sources
    _e("card_source:card", G, "a fixed card ID"),
    _e("card_source:copy_of", G, "a copy of an entity", ("R_COPY",), r"\bcop(y|ies) of\b"),
    _e("card_source:random_from", G, "a random card from a pool", ("R_POOL",), r"\brandom\b"),
    _e("card_source:from_zone", G, "move an existing card from a zone (e.g. summon from the deck)", ("R_HIDDEN_ZONE",),
       r"\bfrom your deck\b"),
    _e("card_source:all_from", G, "every member of a pool, minus bound cards ('the rest')", ("R_POOL",),
       r"\bthe rest\b"),
    # selectors
    _e("selector:SELF", G, "this entity"),
    _e("selector:ENEMY_HERO", G, "the opponent's hero"),
    _e("selector:ENEMY_WEAPON", G, "the opponent's weapon"),
    _e("selector:ref", G, "entities bound earlier in the resolution ('it', 'them')"),
    _e("pick:ALL", G, "every matching entity", ("R_AREA_SNAPSHOT",), r"\ball\b"),
    _e("pick:RANDOM", G, "random matching entities", ("R_RANDOM_LIVE",), r"\brandom"),
    _e("pick:CHOSEN", G, "a target chosen by the controller", ("R_PLAY_TARGET",)),
    _e("zone:PLAY", G, "the battlefield (minions, heroes, weapons, locations)"),
    _e("zone:HAND", G, "a hand", ("R_HIDDEN_ZONE",), r"\bhand\b"),
    _e("zone:DECK", G, "a deck", ("R_HIDDEN_ZONE",), r"\bdeck\b"),
    _e("selector:exclude", G, "exclude entities from a selection ('other')", (), r"\bother\b"),
    # predicates
    _e("pred:keyword", G, "has a keyword"),
    _e("pred:card_type", G, "is a minion, spell, weapon, ..."),
    _e("pred:card_set", G, "belongs to a card set"),
    _e("pred:race", G, "has a minion type"),
    _e("pred:spell_school", G, "has a spell school"),
    _e("pred:cost", G, "cost comparison", (), r"\d+-cost|costs? \(\d+\) or (less|more)"),
    _e("pred:damaged", G, "is (un)damaged", (), r"\b(un)?damaged\b"),
    _e("pred:named", G, "is one of the cards a name in the text refers to", ("R_NAME_REFERENCE",)),
    _e("pred:has_mechanic", G, "carries a mechanic (e.g. Battlecry, Deathrattle)"),
    _e("pred:card_class", G, "belongs to a class"),
    # values
    _e("value:literal", G, "a number from the text"),
    _e("value:spell_damage_literal", G, "a '$' number", ("R_SPELL_DAMAGE", "R_AMOUNT_ORDER"), r"\$\d"),
    _e("value:healing_literal", G, "a '#' number", ("R_HEALING", "R_AMOUNT_ORDER"), r"#\d"),
    _e("value:stat", G, "a stat of an entity (current or last known)", ("R_LAST_KNOWN",)),
    _e("value:counter", G, "a history counter", ("R_COUNTERS",),
       r"\b(you've|you have) (played|cast)\b|\bthis game\b|\bfor each\b"),
    _e("value:var", G, "a resolution-local variable"),
    _e("value:arith", G, "add, sub, max, neg over values"),
    _e("value:unknown", G, "an explicit hole: the text does not determine this value"),
    # conditions
    _e("cond:cmp", G, "compare two values"),
    _e("cond:exists", G, "some matching entity exists", (), r"\b(if you control|if you're (holding|wielding))\b"),
    _e("cond:is", G, "a selected entity satisfies predicates ('while damaged')", (), r"\bwhile\b"),
    _e("cond:mechanic", M, "a mechanic condition such as Kindred", ("R_KINDRED",), r"kindred", True),
    _e("cond:unknown", G, "an explicit hole: the text does not determine this condition"),
    # events and timings
    _e("event:HERO_ATTACK", G, "a hero attacks", (), r"\byour hero attacks\b"),
    _e("event:CARD_DRAWN", G, "a player draws a card", ("R_DRAW",), r"\bwhenever you draw\b"),
    _e("event:TURN_END", G, "a player's turn ends", (), r"\bend of (your|each|the) turn\b|\bturn ends\b"),
    _e("event:DAMAGE_TAKEN", G, "an entity takes damage", (), r"\btakes damage\b"),
    _e("event:DAMAGE_DEALT", G, "damage is dealt by a matching source", (), r"\bdeal damage with\b"),
    _e("event:ATTACK_DECLARED", G, "a character is attacked", (), r"\bis attacked\b"),
    _e("timing:AFTER", G, "after the event resolved", ("R_TRIGGER_TIMING",), r"\bafter\b"),
    _e("timing:WHENEVER", G, "when the event happens", ("R_TRIGGER_TIMING",), r"\bwhenever\b"),
    _e("timing:AT", G, "at a turn phase", ("R_TRIGGER_TIMING",), r"\bat the (start|end)\b"),
    _e("timing:WHEN", G, "before the event resolves (Secrets)", ("R_TRIGGER_TIMING",), r"\bwhen\b"),
    _e("trigger_limit:FIRST_EACH_TURN", G, "only the first matching event each turn", (), r"\bthe first time\b"),
    # durations
    _e("duration:THIS_TURN", G, "until the end of this turn", (), r"\bthis turn\b"),
    _e("duration:N_TURNS", G, "for a number of the controller's turns", (), r"\blasts \d+ turns\b"),
    _e("duration:UNTIL_USED", G, "until its uses are spent"),
    # modifiers
    _e("modifier:cost", G, "set or change cost", ("R_COST",)),
    _e("modifier:rule", G, "change a player rule parameter (multiplier, replacement, bonus)", ("R_AMOUNT_ORDER",)),
    _e("modifier:spell_damage", G, "Spell Damage +N", ("R_SPELL_DAMAGE",), r"spell damage \+\d"),
    _e("rule:SPELL_DAMAGE_MULTIPLIER", G, "multiplies spell damage amounts", (), r"double the damage"),
    _e("rule:SPELL_HEALING_MULTIPLIER", G, "multiplies spell healing amounts", (), r"(double|damage) and healing"),
    _e("rule:HEALING_DOES_DAMAGE", G, "healing is dealt as damage instead", (), r"healing[^.]* deals damage"),
    # counters, resources
    _e("counter:CARD_PLAYED", G, "cards played", (), r"\bplayed\b"),
    _e("counter:SPELL_CAST", G, "spells cast", (), r"\bcast\b"),
    _e("scope:THIS_TURN", G, "counted this turn"),
    _e("scope:THIS_GAME", G, "counted this game"),
    _e("resource:ARMOR", G, "Armor as a cost", (), r"\bspend \d+ armor\b"),
    _e("resource:CORPSE", M, "Corpses as a cost (Death Knight)", (), r"\bcorpses?\b", True),
    _e("pay:discard", G, "a discard as a cost", (), r"\bdiscard\b"),
    # keyword rules (defined once, then data)
    _e("keyword:TAUNT", M, "Taunt", (), r"\btaunt\b"),
    _e("keyword:RUSH", M, "Rush", (), r"\brush\b"),
    _e("keyword:LIFESTEAL", M, "Lifesteal", ("R_HEALING",), r"\blifesteal\b"),
    _e("keyword:REBORN", M, "Reborn", ("R_DEATHRATTLE",), r"\breborn\b"),
    _e("keyword:OVERLOAD", M, "Overload: (N)", (), r"\boverload\b"),
    _e("keyword:TRADEABLE", M, "Tradeable", (), r"\btradeable\b", True),
    _e("keyword:FABLED", M, "Fabled (deck-building bundle; no rule text in HearthstoneJSON)", (), r"\bfabled\b", True),
    _e("keyword:PREPARE", M, "Prepare (a 1-Mana hand action seen in logs; its effect is not in card text)",
       ("R_PREPARE",), r"\bprepare\b", True),
    _e("keyword:COLOSSAL", M, "Colossal +N", ("R_COLOSSAL",), r"\bcolossal\b"),
    _e("keyword:SECRET", M, "Secret", ("R_SECRET",), r"\bsecret\b"),
    _e("keyword:QUEST", M, "Quest", ("R_QUEST",), r"\bquest\b", True),
    _e("keyword:DARK_GIFT", M, "Dark Gift", ("R_DARK_GIFT",), r"\bdark gift\b"),
)
ELEMENTS: dict[str, Element] = {element.element_id: element for element in _ELEMENTS}

KEYWORDS = frozenset(element_id.split(":", 1)[1] for element_id in ELEMENTS if element_id.startswith("keyword:"))
assert all(rule in RULES for element in _ELEMENTS for rule in element.rules)
assert all(rule.basis in BASES for rule in _RULES)
