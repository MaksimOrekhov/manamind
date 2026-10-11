"""Turn separately observed SELF facts into an ``ObservedContext`` (the side channel the forecaster reads).

The facts come from replaying a raw Power.log up to a decision point (``scripts/observation_probe_1b.py``);
nothing here touches ``GameState``, the encoder or any checkpoint. Only facts the player could see are used:
SELF's player tags, SELF's hero, SELF's minions and SELF's own hand. A fact that disagrees with the state it is
paired with (a hand whose card IDs differ, for instance) is dropped instead of being trusted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manamind.domain.game_state import GameState
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
