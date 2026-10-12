"""Hand-written position value for the Strategic Scorer (STRATEGIC-SCORER-1).

The value is measured from SELF's point of view in *stat points*: one point is roughly one Attack or one Health on a
minion, and a fair card of printed cost ``c`` is worth about ``2c + 1`` points (the classic "vanilla" curve). The value
only reads the player-visible ``GameState``: the SELF hand, public board entities, both heroes and the opponent's hand
*size*. It never reads opponent hand identities, deck order, future draws or any Policy output.

Every term is named so that a score can be explained, and the terms fall into four kinds (see ``Breakdown``):

* ``static``    - what is on the board and in the SELF hand now (minions, heroes, weapons, cards);
* ``risk``      - a rough look at the opponent's *visible* attackers against SELF's next turn and back, an estimate;
* ``potential`` - what SELF can still do this turn with the remaining Mana and ready attackers, an estimate;
* ``terminal``  - a hero at 0 effective Health.

``PARAMS`` was written from public game knowledge before the scorer was run on any recorded decision; it is versioned
and must not be tuned on the evaluation sets. Changing it is a new version, not a fix.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.outcome.grammar import parse_text
from manamind.outcome.texts import TextSource

# v1 (frozen at ee55494, evaluated in reports/strategic_scorer_1/results_params_v1.json).
# v2: structural fixes found by that evaluation, coefficients unchanged - Location charges are a stored resource like
# a card in hand (an activation is no longer free value), and a card whose cost is not observed is assumed plan-neutral.
# v3: a minion whose text the scorer cannot read is a fair card of its cost (stats above the curve usually pay for a
# drawback such as Dormant, below it for an upside), instead of max(body, fair card).
PARAMS_VERSION = "strategic-scorer-1/params-v3"


@dataclass(frozen=True, slots=True)
class Params:
    attack: float = 1.0               # per point of current Attack on a minion
    health: float = 1.0               # per point of current Health on a minion
    taunt: float = 1.0
    divine_shield: float = 1.0        # times max(1, Attack): a Shield absorbs one whole hit
    poisonous: float = 2.0
    lifesteal: float = 0.5            # times Attack
    windfury: float = 0.5             # times Attack
    reborn: float = 0.5               # times (Attack + 1): the 1-Health copy
    stealth: float = 1.0
    frozen: float = 0.5               # times Attack, lost next attack
    dormant: float = 0.5              # multiplier
    hero: float = 0.5                 # per point of effective Health (Health + Armor) above the danger zones
    hero_danger_high: int = 15        # below this every point counts double ...
    hero_danger_low: int = 8          # ... and below this 3.5 times
    win: float = 100.0                # opponent hero at 0
    card_base: float = 1.0            # fair card value = card_base + card_per_mana * printed cost
    card_per_mana: float = 2.0
    hand_fraction: float = 0.5        # a card in hand is worth this share of what playing it is expected to give
    opponent_card: float = 2.5        # each card in the opponent's hand (identity never read)
    hero_power: float = 1.5           # expected gain of an unread Hero Power use
    location_activation: float = 2.0  # expected gain of an unread Location activation
    weapon: float = 0.5               # times Attack * Durability
    threat: float = 0.5               # share of SELF's Health value the visible enemy attackers could take next turn
    lethal_risk: float = 20.0         # visible enemy attackers alone reach SELF's effective Health
    pressure: float = 0.25            # share of the opponent's Health value SELF's board threatens next turn


PARAMS = Params()


def health_value(effective: int, p: Params = PARAMS) -> float:
    """Value of a hero's effective Health; low Health is worth more per point (concave in danger)."""
    x = max(0, effective)
    # marginal value per point: 1 above ``hero_danger_high``, 2 down to ``hero_danger_low``, 3.5 below it
    return p.hero * (x + min(x, p.hero_danger_high) * 1.0 + min(x, p.hero_danger_low) * 1.5)


def effective_health(player: PlayerObservation) -> int:
    return player.hero_health + player.armor


def minion_value(entity: BoardEntity, p: Params = PARAMS) -> float:
    attack, health = max(0, entity.current_attack), entity.current_health
    if health <= 0:
        return 0.0
    value = p.attack * attack + p.health * health
    if entity.taunt:
        value += p.taunt
    if entity.divine_shield:
        value += p.divine_shield * max(1, attack)
    if entity.poisonous and attack > 0:
        value += p.poisonous
    if entity.lifesteal:
        value += p.lifesteal * attack
    if entity.windfury:
        value += p.windfury * attack
    if entity.reborn:
        value += p.reborn * (attack + 1)
    if entity.stealth:
        value += p.stealth
    if entity.frozen:
        value -= p.frozen * attack
    if entity.dormant:
        value *= p.dormant
    return value


def card_prior(cost: int | None, p: Params = PARAMS) -> float:
    """Expected value of a fair card of this printed cost; unknown cost is treated as an average 3-drop."""
    return p.card_base + p.card_per_mana * (3 if cost is None else max(0, cost))


_BODY_KEYWORDS = {"TAUNT": "taunt", "DIVINE_SHIELD": "divine_shield", "POISONOUS": "poisonous",
                  "LIFESTEAL": "lifesteal", "WINDFURY": "windfury", "REBORN": "reborn", "STEALTH": "stealth",
                  "RUSH": "rush", "CHARGE": "charge"}


@lru_cache(maxsize=4096)
def _text_is_body_only(text: str) -> bool:
    """True when a minion's rules text adds nothing beyond keywords the body already shows."""
    parsed = parse_text(text)
    return not parsed.trigger_sentences and all(c.kind == "KEYWORDS" for c in parsed.clauses)


def body_value(card: CardFeatures, p: Params = PARAMS) -> float | None:
    """Value of the minion a hand card would put on the board, from its observed numbers and keywords."""
    attack = card.effective_attack
    health = card.current_health if card.current_health is not None else card.health
    if attack is None or health is None:
        return None
    flags = {flag: True for name, flag in _BODY_KEYWORDS.items() if name in card.mechanics}
    flags.pop("rush", None)
    flags.pop("charge", None)
    entity = BoardEntity(card=card, current_attack=attack, current_health=health, max_health=health,
                         board_position=1, **flags)
    return minion_value(entity, p)


def expected_play_value(card: CardFeatures, texts: TextSource, p: Params = PARAMS) -> float:
    """What playing this card is expected to give, before any forecast: its body, or a fair card of its cost.

    A minion whose text adds nothing beyond keywords is its body. Any other card (a minion with more text, a spell,
    a Location, a weapon) is assumed to be a fair card of its printed cost - an estimate, never a fact. For a minion
    this deliberately ignores how far its stats are from the curve: the text usually pays for that difference.
    """
    prior = card_prior(card.cost if card.cost is not None else card.effective_cost, p)
    if card.card_type == "MINION":
        body = body_value(card, p)
        entry = texts.get(card.card_id)
        if body is not None and entry is not None and _text_is_body_only(entry.text):
            return body
    return prior


def hand_value(card: CardFeatures, texts: TextSource, p: Params = PARAMS) -> float:
    return p.hand_fraction * expected_play_value(card, texts, p)


def weapon_value(weapon: CardFeatures | None, p: Params = PARAMS) -> float:
    if weapon is None:
        return 0.0
    attack = weapon.effective_attack or 0
    durability = weapon.effective_durability or 0
    return p.weapon * max(0, attack) * max(0, durability)


def location_value(place, p: Params = PARAMS) -> float:
    """A Location stores activations the way a hand stores cards: each charge is worth the hand share of one use."""
    return p.hand_fraction * p.location_activation * max(0, place.current_health)


# ----- next-turn risk ---------------------------------------------------------------------------------------------

def _attackers(player: PlayerObservation) -> list[int]:
    """Attack values the side's visible minions (and weapon) could swing with on its next turn."""
    hits: list[int] = []
    for entity in player.board:
        if entity.dormant or entity.current_attack <= 0:
            continue
        hits.append(entity.current_attack)
        if entity.windfury:
            hits.append(entity.current_attack)
    if player.weapon is not None and (player.weapon.effective_attack or 0) > 0 \
            and (player.weapon.effective_durability or 0) > 0:
        hits.append(player.weapon.effective_attack)
    return hits


def face_damage_through_taunts(hits: list[int], defender: PlayerObservation) -> int:
    """Rough damage that reaches the defending hero: attackers must first clear the visible Taunts.

    Each Taunt is broken by the smallest single attacker that can do it alone, otherwise by the largest attackers
    until its Health (plus one extra hit for a Divine Shield) is spent. An estimate of an opponent's line, not a rule.
    """
    remaining = sorted(hits)
    for taunt in sorted((e for e in defender.board if e.taunt and not e.dormant and not e.stealth),
                        key=lambda e: e.current_health):
        if not remaining:
            break
        if taunt.divine_shield:
            remaining.pop(0)
            if not remaining:
                break
        need = taunt.current_health
        single = [hit for hit in remaining if hit >= need]
        if single:
            remaining.remove(single[0])
            continue
        while remaining and need > 0:
            need -= remaining.pop()
    return sum(remaining)


@dataclass(frozen=True, slots=True)
class Breakdown:
    """Named terms of one position value; ``total`` is their sum."""

    terms: tuple[tuple[str, float], ...]

    @property
    def total(self) -> float:
        return sum(value for _, value in self.terms)

    def get(self, name: str) -> float:
        return sum(value for key, value in self.terms if key == name)

    def kind(self, kind: str) -> float:
        return sum(value for key, value in self.terms if TERM_KIND[key] == kind)


TERM_KIND = {
    "board_self": "static", "board_opponent": "static", "hero_self": "static", "hero_opponent": "static",
    "weapon_self": "static", "weapon_opponent": "static", "hand_self": "static", "hand_opponent": "static",
    "locations_self": "static", "locations_opponent": "static",
    "win": "terminal", "loss": "terminal",
    "threat": "risk", "lethal_risk": "risk", "pressure": "risk",
    "mana_potential": "potential", "attack_potential": "potential",
}


def position_value(state: GameState, texts: TextSource, *, turn_open: bool, p: Params = PARAMS) -> Breakdown:
    """Value of a position with SELF to move (``turn_open``) or after SELF ends the turn."""
    me, opponent = state.self_player, state.opponent
    mine, theirs = effective_health(me), effective_health(opponent)
    terms: list[tuple[str, float]] = [
        ("board_self", sum(minion_value(e, p) for e in me.board)),
        ("board_opponent", -sum(minion_value(e, p) for e in opponent.board)),
        ("hero_self", health_value(mine, p)),
        ("hero_opponent", -health_value(theirs, p)),
        ("weapon_self", weapon_value(me.weapon, p)),
        ("weapon_opponent", -weapon_value(opponent.weapon, p)),
        ("hand_self", sum(hand_value(card, texts, p) for card in state.self_hand)),
        ("hand_opponent", -p.opponent_card * opponent.hand_size),
        ("locations_self", sum(location_value(place, p) for place in me.locations)),
        ("locations_opponent", -sum(location_value(place, p) for place in opponent.locations)),
        ("win", p.win if theirs <= 0 else 0.0),
        ("loss", -p.win if mine <= 0 else 0.0),
    ]
    if theirs > 0 and mine > 0:
        incoming = face_damage_through_taunts(_attackers(opponent), me)
        outgoing = face_damage_through_taunts(_attackers(me), opponent)
        terms += [
            ("threat", -p.threat * (health_value(mine, p) - health_value(mine - incoming, p))),
            ("lethal_risk", -p.lethal_risk if incoming >= mine else 0.0),
            ("pressure", p.pressure * (health_value(theirs, p) - health_value(theirs - outgoing, p))),
        ]
    if turn_open and theirs > 0 and mine > 0:
        terms += [("mana_potential", mana_potential(state, texts, p)),
                  ("attack_potential", attack_potential(state, p))]
    return Breakdown(tuple(terms))


# ----- what is left of the turn -----------------------------------------------------------------------------------

def mana_potential(state: GameState, texts: TextSource, p: Params = PARAMS) -> float:
    """Best surplus SELF can still expect this turn from the cards it can afford (0/1 knapsack over Mana).

    Playing a card is expected to turn its hand value into its play value, so each affordable card offers
    ``(1 - hand_fraction) * expected play value``. A ready Hero Power offers ``hero_power``, a ready Location
    ``(1 - hand_fraction) * location_activation``. Minions need a free board slot. Cards whose cost is not observed
    are left out (their affordability is unknown). Estimates only: no card text is executed here.
    """
    me = state.self_player
    mana = me.available_mana
    room = 7 - len(me.board) - len(me.locations)
    items: list[tuple[int, float, bool]] = []
    for card in state.self_hand:
        cost = card.effective_cost
        if cost is None or cost > mana:
            continue
        needs_slot = card.card_type in ("MINION", "LOCATION")
        if needs_slot and room <= 0:
            continue
        items.append((max(0, cost), (1.0 - p.hand_fraction) * expected_play_value(card, texts, p), needs_slot))
    for place in me.locations:
        if place.current_health > 0 and not place.on_cooldown and place.can_activate is not False:
            items.append((0, (1.0 - p.hand_fraction) * p.location_activation, False))
    power = me.hero_power
    if me.hero_power_ready is True and power is not None:
        cost = power.effective_cost
        if cost is not None and cost <= mana:
            items.append((max(0, cost), p.hero_power, False))
    # knapsack over Mana; the board-slot limit is applied greedily by keeping the best ``room`` minions
    best = [0.0] * (mana + 1)
    chosen: list[list[int]] = [[] for _ in range(mana + 1)]
    for number, (cost, gain, _) in enumerate(items):
        for budget in range(mana, cost - 1, -1):
            candidate = best[budget - cost] + gain
            if candidate > best[budget] + 1e-12:
                best[budget] = candidate
                chosen[budget] = chosen[budget - cost] + [number]
    picked = chosen[mana]
    slotted = sorted((items[i][1] for i in picked if items[i][2]), reverse=True)
    free = sum(items[i][1] for i in picked if not items[i][2])
    return free + sum(slotted[:max(0, room)])


def _strike(attacker: BoardEntity, defender: BoardEntity, p: Params) -> float:
    """Value change of one minion-vs-minion attack by plain combat arithmetic (an estimate for the plan term)."""
    def hit(target: BoardEntity, amount: int, poisonous: bool) -> BoardEntity:
        if amount <= 0:
            return target
        if target.divine_shield:
            return replace(target, divine_shield=False)
        health = 0 if poisonous else target.current_health - amount
        return replace(target, current_health=health)

    struck = hit(defender, attacker.current_attack, attacker.poisonous)
    back = hit(attacker, defender.current_attack, defender.poisonous)
    return ((minion_value(defender, p) - minion_value(struck, p))
            - (minion_value(attacker, p) - minion_value(back, p)))


def attack_potential(state: GameState, p: Params = PARAMS) -> float:
    """Sum over SELF's ready minions of their best single attack now (never below 0: an attack is optional).

    Rush minions are not given the enemy hero (whether they entered play this turn is not in the state); the hero's
    own attack is left out because the state does not say whether it is still available. Attackers are judged
    independently, so two of them may count the same target: an optimistic estimate.
    """
    opponent = state.opponent
    theirs = effective_health(opponent)
    taunts = [e for e in opponent.board if e.taunt and not e.stealth and not e.dormant]
    targets = taunts or [e for e in opponent.board if not e.stealth and not e.dormant and not e.immune]
    face_open = not taunts and opponent.hero_health > 0
    total = 0.0
    for entity in state.self_player.board:
        if not entity.can_attack or entity.frozen or entity.dormant or entity.current_attack <= 0:
            continue
        best = 0.0
        if face_open and not (entity.rush and not entity.charge):
            # no ``win`` here: a lethal that is only possible must never offset one that an action confirms
            best = max(best, health_value(theirs, p) - health_value(theirs - entity.current_attack, p))
        for target in targets:
            best = max(best, _strike(entity, target, p))
        total += best
    return total


__all__ = [
    "PARAMS", "PARAMS_VERSION", "Breakdown", "Params", "TERM_KIND", "attack_potential", "body_value", "card_prior",
    "effective_health", "expected_play_value", "face_damage_through_taunts", "hand_value", "health_value",
    "location_value",
    "mana_potential", "minion_value", "position_value", "weapon_value",
]
