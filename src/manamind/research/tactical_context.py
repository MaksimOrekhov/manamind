"""TACTICAL-DECISION-1: context-aware consequence evaluator for healing effects (offline, experimental).

Frozen Policy v2 cannot see whether the player's "next Healing effect this turn deals damage instead" state
(Ruby Sanctum) is on, so it cannot tell a heal from a burn spell. This module reads that state from the
experimental ``DecisionOverlay`` and computes the *direct* consequence of each supported healing action:

* supported sources: a targeted spell whose pinned text starts with ``Restore #N Health.`` (Flash Heal,
  Holy Embrace) and the Priest hero power (restore 2, verified from outcomes by CONSEQUENCE-PILOT-1);
* every other action is left untouched and reported as unsupported - there is no general effect system here.

Three nested reranking layers keep the frozen Policy order wherever the evaluator has no claim:

* ``L1`` target dominance - inside one source (same card instance / same hero power) targets are ordered
  GAIN > NEUTRAL > HARM; the set of rank slots used by that source and every other action stay in place;
* ``L2`` guaranteed lethal - a converted heal that surely kills the enemy hero goes first;
* ``L3`` committed effect (strategic assumption) - while the one-turn conversion is active, converted damage
  on the enemy goes ahead of every non-healing action.

Nothing here reads future events, opponent hidden information or the production encoder.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from manamind.research.decision_overlay import ACTIVE, INACTIVE, DecisionOverlay

HERO_POWER_HEALS = {"HERO_09dbp": 2, "HERO_09bp": 2}  # restore amount observed in logs, not in the pinned catalog

GAIN_LETHAL, GAIN, NEUTRAL, HARM, UNRESOLVED = "GAIN_LETHAL", "GAIN", "NEUTRAL", "HARM", "UNRESOLVED"
_VALUE = {GAIN_LETHAL: 0, GAIN: 1, NEUTRAL: 2, HARM: 3}

ENEMY_DAMAGE, SELF_DAMAGE = "ENEMY_DAMAGE", "SELF_DAMAGE"
ENEMY_HEAL, ENEMY_NO_EFFECT = "ENEMY_HEAL", "ENEMY_NO_EFFECT"
SELF_HEAL, SELF_NO_EFFECT = "SELF_HEAL", "SELF_NO_EFFECT"
LETHAL = "LETHAL_ON_ENEMY_HERO"

_MARKUP = re.compile(r"<[^>]+>|\[x\]")
_RESTORE_FIRST = re.compile(r"^Restore #(\d+) Health\.(?P<rest>.*)$", re.S)


@dataclass(frozen=True, slots=True)
class HealSource:
    card_id: str
    amount: int
    kind: str  # SPELL | HERO_POWER
    provenance: str
    extra_effect: bool  # more card text than the plain restore (Holy Embrace adds a card)


@dataclass(frozen=True, slots=True)
class HealAssessment:
    outcome: str  # one of the constants above
    value: str  # GAIN_LETHAL | GAIN | NEUTRAL | HARM | UNRESOLVED
    amount: int  # guaranteed minimum magnitude; Healing bonuses (unknown) only increase it
    quest_progress: int | None  # 1 when the client hint says the cast advances a Quest, 0 when not, None unknown
    caveats: tuple[str, ...]
    sibling_key: tuple


def heal_sources(records: Sequence[Mapping]) -> dict[str, HealSource]:
    """Supported healing sources from the pinned catalog text, plus the observed-outcome hero powers."""
    sources: dict[str, HealSource] = {}
    for record in records:
        text, card_id = record.get("text"), record.get("id")
        if record.get("type") != "SPELL" or not isinstance(text, str) or not isinstance(card_id, str):
            continue
        match = _RESTORE_FIRST.match(" ".join(_MARKUP.sub("", text).replace(" ", " ").split()))
        if match and " to all " not in match["rest"]:
            sources[card_id] = HealSource(card_id, int(match[1]), "SPELL", "pinned_catalog_text",
                                          bool(match["rest"].strip()))
    for card_id, amount in HERO_POWER_HEALS.items():
        sources[card_id] = HealSource(card_id, amount, "HERO_POWER", "observed_outcomes_consequence_pilot_1", False)
    return sources


def sibling_key(action: Mapping) -> tuple:
    return (action.get("type"), action.get("source_card_id"), action.get("hand_index"))


def _resolve(state: Mapping, action: Mapping) -> tuple[Mapping | None, int | None, int | None, int, list[str]]:
    """Target (hero or minion) health facts: (entity, health, max_health, armor, caveats)."""
    player = state["self_player" if action.get("target_side") == "SELF" else "opponent"]
    if action.get("target_kind") == "HERO":
        return (player, player["hero_health"], player["hero_max_health"], player.get("armor") or 0,
                ["DIVINE_SHIELD"] if player.get("hero_divine_shield") else [])
    entities = [e for e in player["board"] if e["board_position"] == action.get("target_board_position")
                and e["card"]["card_id"] == action.get("target_card_id")]
    if len(entities) != 1:
        return None, None, None, 0, ["TARGET_NOT_RESOLVED"]
    entity = entities[0]
    caveats = [name.upper() for name in ("divine_shield", "immune", "dormant", "stealth") if entity.get(name)]
    return entity, entity["current_health"], entity["max_health"], 0, caveats


def quest_progress(overlay: DecisionOverlay, state: Mapping, action: Mapping, source: HealSource) -> int | None:
    if source.kind != "SPELL":
        return 0  # a hero power is not a spell; the only Quest in the corpus counts spells
    if not overlay.quests:
        return 0
    index = action.get("hand_index")
    hand = [card["card_id"] for card in state["self_hand"]]
    if (index is None or not 0 <= index < len(hand) or tuple(hand) != overlay.hand_card_ids
            or hand[index] != action.get("source_card_id")):
        return None
    tag = overlay.hand_contributors[index]
    return 1 if tag == 1 else 0  # absent/0 never advanced a Quest in the audited corpus


def assess_heal(state: Mapping, action: Mapping, overlay: DecisionOverlay,
                sources: Mapping[str, HealSource]) -> HealAssessment | None:
    """Direct consequence of one supported healing action; None when the action is not a supported heal."""
    if action.get("type") not in ("PLAY_CARD", "HERO_POWER") or "target_kind" not in action:
        return None
    source = sources.get(action.get("source_card_id"))
    if source is None or (action["type"] == "HERO_POWER") != (source.kind == "HERO_POWER"):
        return None
    key = sibling_key(action)
    progress = quest_progress(overlay, state, action, source)
    caveats = ["EXTRA_EFFECT_NOT_MODELED"] if source.extra_effect else []
    entity, health, maximum, armor, target_caveats = _resolve(state, action)
    caveats += target_caveats
    enemy = action.get("target_side") == "OPPONENT"
    if entity is None or health is None or overlay.healing_does_damage not in (ACTIVE, INACTIVE):
        return HealAssessment("UNRESOLVED", UNRESOLVED, source.amount, progress, tuple(caveats), key)
    if overlay.healing_does_damage == ACTIVE:
        if set(target_caveats) & {"IMMUNE", "DORMANT", "DIVINE_SHIELD", "STEALTH"}:
            return HealAssessment("UNRESOLVED", UNRESOLVED, source.amount, progress, tuple(caveats), key)
        if not enemy:
            return HealAssessment(SELF_DAMAGE, HARM, source.amount, progress, tuple(caveats), key)
        if action["target_kind"] == "HERO" and health + armor <= source.amount:
            if state["opponent"].get("secret_count"):
                caveats.append("OPPONENT_SECRET_PRESENT")
            return HealAssessment(LETHAL, GAIN_LETHAL, source.amount, progress, tuple(caveats), key)
        return HealAssessment(ENEMY_DAMAGE, GAIN, source.amount, progress, tuple(caveats), key)
    if maximum is None:
        return HealAssessment("UNRESOLVED", UNRESOLVED, source.amount, progress, tuple(caveats), key)
    missing = maximum - health
    if enemy:
        outcome, value = (ENEMY_HEAL, HARM) if missing > 0 else (ENEMY_NO_EFFECT, NEUTRAL)
    else:
        outcome, value = (SELF_HEAL, GAIN) if missing > 0 else (SELF_NO_EFFECT, NEUTRAL)
    return HealAssessment(outcome, value, min(missing, source.amount), progress, tuple(caveats), key)


def assess_menu(state: Mapping, actions: Sequence[Mapping], overlay: DecisionOverlay,
                sources: Mapping[str, HealSource]) -> dict[int, HealAssessment]:
    found = {}
    for index, action in enumerate(actions):
        assessment = assess_heal(state, action, overlay, sources)
        if assessment is not None:
            found[index] = assessment
    return found


def target_dominance(order: list[int], assessments: Mapping[int, HealAssessment]) -> list[int]:
    """L1: reorder targets inside each source; slots of the source and all other actions stay where they are."""
    groups: dict[tuple, list[int]] = {}
    for index in order:
        item = assessments.get(index)
        if item is not None and item.value != UNRESOLVED:
            groups.setdefault(item.sibling_key, []).append(index)
    result = list(order)
    for members in groups.values():
        slots = sorted(result.index(index) for index in members)
        ranked = sorted(members, key=lambda index: (_VALUE[assessments[index].value], members.index(index)))
        for slot, index in zip(slots, ranked):
            result[slot] = index
    return result


def lethal_first(order: list[int], assessments: Mapping[int, HealAssessment]) -> list[int]:
    lethal = [index for index in order if assessments.get(index) and assessments[index].value == GAIN_LETHAL]
    return lethal + [index for index in order if index not in lethal]


def committed_effect_first(order: list[int], assessments: Mapping[int, HealAssessment]) -> list[int]:
    """L3: converted damage on the enemy goes ahead of non-healing actions (kept in Policy order)."""
    chosen = [index for index in order if assessments.get(index) and assessments[index].value
              in (GAIN_LETHAL, GAIN) and assessments[index].outcome in (LETHAL, ENEMY_DAMAGE)]
    return chosen + [index for index in order if index not in chosen]


VARIANTS = ("V0_frozen_v2", "V1_target_dominance", "V2_plus_lethal", "V3_plus_committed_effect")


def rerank(order: list[int], assessments: Mapping[int, HealAssessment]) -> dict[str, list[int]]:
    v1 = target_dominance(order, assessments)
    v2 = lethal_first(v1, assessments)
    v3 = lethal_first(committed_effect_first(v1, assessments), assessments)
    return {VARIANTS[0]: list(order), VARIANTS[1]: v1, VARIANTS[2]: v2, VARIANTS[3]: v3}
