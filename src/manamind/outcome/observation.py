"""Turn separately observed SELF facts into an ``ObservedContext`` (the side channel the forecaster reads).

``context_from_observed`` is the production path (OBSERVATION-EXT-1a): ``ObservedFacts`` are read from the live
entity table at the decision point (``manamind.integrations.powerlog.observed_facts``, attached to the LIVE
``Snapshot``). ``context_from_facts`` is the older ACTION-OUTCOME-1B path over the offline probe's JSON rows; it is
kept so that report can be reproduced. Nothing here touches ``GameState``, the encoder or any checkpoint. A fact that
disagrees with the state it is paired with (a hand whose card IDs differ, for instance) is dropped instead of being
trusted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manamind.domain.game_state import GameState
from manamind.integrations.powerlog.observed_facts import (
    SPELL_DAMAGE_NONE_SEEN, SPELL_DAMAGE_PRESENT, ObservedFacts,
)
from manamind.outcome.world import ObservedContext


def load_facts(path: str | Path) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            facts[row["decision_id"]] = row
    return facts


FACT_GROUPS = ("sanctum", "healing", "hero_shield", "hand_keywords", "spell_damage")


def context_from_facts(fact: dict[str, Any], state: GameState,
                       groups: frozenset[str] | set[str] = frozenset(FACT_GROUPS)) -> ObservedContext:
    """``groups`` selects which fact groups are used, so each can be measured on its own (an ablation)."""
    full = _context_from_facts(fact, state)
    unset = ObservedContext()
    pick = {
        "sanctum": ("healing_does_damage",),
        "healing": ("healing_bonus", "spell_healing_doubled"),
        "hero_shield": ("self_hero_divine_shield", "opponent_hero_divine_shield"),
        "hand_keywords": ("hand_keywords",),
        "spell_damage": ("spell_damage", "spell_damage_doubled"),
    }
    values = {name: (getattr(full, name) if group in groups else getattr(unset, name))
              for group, names in pick.items() for name in names}
    return ObservedContext(**values)


def context_from_observed(facts: ObservedFacts | None, state: GameState,
                          groups: frozenset[str] | set[str] = frozenset(FACT_GROUPS)) -> ObservedContext:
    """The forecaster's context from live-read facts; ``None`` (facts unreadable) is an all-unknown context.

    Spell Damage: only "no Spell Damage source seen over a fully observed history" is usable as the number 0. A source
    that was seen (size and order with doubling unverified, no log has one for SELF) leaves the damage a lower bound.
    Healing doubling is the union of the spell-only and the all-healing flags; it is unknown unless one is true or both
    are false.
    """
    if facts is None:
        return ObservedContext()
    values: dict = {}
    if "sanctum" in groups:
        values["healing_does_damage"] = facts.healing_does_damage
    if "healing" in groups:
        flags = (facts.spell_healing_doubled, facts.all_healing_doubled)
        values["healing_bonus"] = facts.healing_bonus
        values["spell_healing_doubled"] = (True if True in flags else False if flags == (False, False) else None)
    if "hero_shield" in groups:
        values["self_hero_divine_shield"] = facts.self_hero_divine_shield
        values["opponent_hero_divine_shield"] = facts.opponent_hero_divine_shield
    if "hand_keywords" in groups:
        values["hand_keywords"] = _hand_keywords(facts, state)
    if "spell_damage" in groups:
        values["spell_damage_doubled"] = facts.spell_damage_doubled
        if facts.spell_damage_status == SPELL_DAMAGE_NONE_SEEN:
            values["spell_damage"] = 0
        elif facts.spell_damage_status == SPELL_DAMAGE_PRESENT:
            values["spell_damage_unverified"] = True
    return ObservedContext(**values)


def _hand_keywords(facts: ObservedFacts, state: GameState) -> tuple[frozenset[str] | None, ...] | None:
    """Per hand position (so identical copies stay separate); a position whose card differs is dropped."""
    if len(facts.hand) != len(state.self_hand):
        return None
    return tuple(frozenset(fact.keywords) if fact.keywords is not None and fact.card_id == card.card_id else None
                 for fact, card in zip(facts.hand, state.self_hand, strict=True))


def _context_from_facts(fact: dict[str, Any], state: GameState) -> ObservedContext:
    sanctum = {"ACTIVE": True, "INACTIVE": False}.get(fact.get("sanctum"))
    spell_power, healing = fact.get("spell_power", {}), fact.get("healing", {})
    hand = fact.get("hand", [])
    keywords: tuple[frozenset[str] | None, ...] | None = None
    if len(hand) == len(state.self_hand):
        keywords = tuple(frozenset(row["keywords"]) if row["card_id"] == card.card_id else None
                         for row, card in zip(hand, state.self_hand, strict=True))
    return ObservedContext(
        healing_does_damage=sanctum,
        spell_damage=(spell_power.get("current_sum", 0) + spell_power.get("player_current", 0)
                      if spell_power else None),
        spell_damage_doubled=spell_power.get("doubled") if spell_power else None,
        healing_bonus=healing.get("bonus") if healing else None,
        spell_healing_doubled=(bool(healing.get("spell_double") or healing.get("all_double")) if healing else None),
        self_hero_divine_shield=fact.get("hero_divine_shield"),
        opponent_hero_divine_shield=fact.get("opponent_hero_divine_shield"),
        hand_keywords=keywords)
