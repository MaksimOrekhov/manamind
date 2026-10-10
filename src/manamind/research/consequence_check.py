"""CONSEQUENCE-PILOT-1: conservative direct-effect checks for two verified mechanics (offline only).

This is not an effect system. Only two exact card-text templates are understood:
targeted "Restore #N Health." and "Destroy all minions with N or more Attack.".
Everything else is UNSUPPORTED. A check answers whether the action's *direct*
effect changes the visible state; side effects (spell/heal triggers, quests,
secrets, in-hand cost changes) are reported separately and never inspected
beyond a keyword screen over visible card text. Unknown data stays unknown.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from manamind.domain.card import CardFeatures
from manamind.domain.game_state import GameState, PlayerObservation

DIRECT_EFFECT_PRESENT = "DIRECT_EFFECT_PRESENT"
NO_DIRECT_EFFECT = "NO_DIRECT_EFFECT"
UNKNOWN = "UNKNOWN"
UNSUPPORTED = "UNSUPPORTED"

# Side-effect screen outcome: no visible card text could react, a visible text could react, or the screen
# itself is blind (unidentified Secret/Quest, card text missing from the pinned catalog).
SIDE_NONE_VISIBLE = "NONE_VISIBLE"
SIDE_POSSIBLE = "POSSIBLE"
SIDE_UNKNOWN = "UNKNOWN"

RESTORE_TARGET = "RESTORE_TARGET"
DESTROY_MINIONS_MIN_ATTACK = "DESTROY_MINIONS_MIN_ATTACK"

_RESTORE_TEXT = re.compile(r"Restore #(\d+) Health\.")
_DESTROY_TEXT = re.compile(r"Destroy all minions with (\d+) or more Attack\.")
_MARKUP = re.compile(r"<[^>]+>")
# Fixed before any Policy ranking was inspected. Over-matching only costs coverage, never safety.
_HEAL_MODIFIER = re.compile(r"heal|restor")
_HEAL_SIDE = re.compile(r"heal|restor|health")
_SPELL_TRIGGER = re.compile(r"spell|cast")
_PLAY_TRIGGER = re.compile(r"you play|play a card")
_HERO_POWER_TRIGGER = re.compile(r"hero power|inspire")


@dataclass(frozen=True, slots=True)
class VerifiedEffect:
    """One verified direct effect of an action source; ``value`` is the restore amount or Attack threshold."""

    card_id: str
    mechanic: str
    value: int
    provenance: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    status: str
    reason: str
    side_effects: str | None = None
    side_reasons: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)


def catalog_effects(records: list[dict]) -> dict[str, VerifiedEffect]:
    """Effects whose complete pinned card text is exactly one supported template, nothing else."""
    effects: dict[str, VerifiedEffect] = {}
    for record in records:
        text, card_id = record.get("text"), record.get("id")
        if not isinstance(text, str) or not isinstance(card_id, str):
            continue
        if (match := _RESTORE_TEXT.fullmatch(text)) and record.get("type") == "SPELL":
            effects[card_id] = VerifiedEffect(card_id, RESTORE_TARGET, int(match[1]), "pinned_catalog_text")
        elif (match := _DESTROY_TEXT.fullmatch(text)) and record.get("type") == "SPELL":
            effects[card_id] = VerifiedEffect(card_id, DESTROY_MINIONS_MIN_ATTACK, int(match[1]),
                                              "pinned_catalog_text")
    return effects


def catalog_texts(records: list[dict]) -> dict[str, str]:
    """Lower-case rules text per pinned card ID; a pinned card without text maps to an empty string."""
    texts = {}
    for record in records:
        if isinstance(record.get("id"), str):
            text = record.get("text")
            texts[record["id"]] = _MARKUP.sub("", text).lower() if isinstance(text, str) else ""
    return texts


def _source_id(action: Mapping) -> str | None:
    if action.get("type") in ("PLAY_CARD", "HERO_POWER"):
        return action.get("source_card_id") or action.get("card_id")
    return None


def _public_cards(state: GameState) -> list[tuple[str, CardFeatures]]:
    cards = []
    for side, player in (("SELF", state.self_player), ("OPPONENT", state.opponent)):
        cards += [(side, entity.card) for entity in player.board]
        cards += [(side, location.card) for location in player.locations]
        if player.weapon is not None:
            cards.append((side, player.weapon))
    return cards


def _screen(cards, texts: Mapping[str, str], pattern: re.Pattern) -> tuple[list[str], list[str]]:
    unknown, matched = [], []
    for card in cards:
        text = texts.get(card.card_id)
        if text is None:
            unknown.append(card.card_id)
        elif pattern.search(text):
            matched.append(card.card_id)
    return sorted(set(unknown)), sorted(set(matched))


def _side_effects(state: GameState, action: Mapping, texts: Mapping[str, str],
                  pattern: re.Pattern) -> tuple[str, tuple[str, ...], dict]:
    hand = [card for index, card in enumerate(state.self_hand) if index != action.get("hand_index")]
    unknown, matched = _screen([card for _, card in _public_cards(state)] + hand, texts, pattern)
    secrets = bool(state.self_player.secret_count or state.opponent.secret_count)
    reasons = [reason for reason, present in (("SECRET_OR_QUEST_UNIDENTIFIED", secrets),
                                              ("CARD_TEXT_NOT_IN_PINNED_CATALOG", bool(unknown)),
                                              ("VISIBLE_TEXT_MAY_REACT", bool(matched))) if present]
    status = SIDE_UNKNOWN if secrets or unknown else SIDE_POSSIBLE if matched else SIDE_NONE_VISIBLE
    return status, tuple(reasons), {"side_unknown_cards": unknown, "side_matching_cards": matched}


def _trigger_pattern(action: Mapping, base: re.Pattern | None) -> re.Pattern:
    parts = [] if base is None else [base.pattern]
    if action.get("type") == "HERO_POWER":
        parts.append(_HERO_POWER_TRIGGER.pattern)
    else:
        parts += [_SPELL_TRIGGER.pattern, _PLAY_TRIGGER.pattern]
    return re.compile("|".join(parts))


def _target_health(state: GameState, action: Mapping) -> tuple[str | None, int | None, int | None]:
    side = action.get("target_side")
    player: PlayerObservation | None = {"SELF": state.self_player, "OPPONENT": state.opponent}.get(side)
    if player is None:
        return "TARGET_SIDE_UNKNOWN", None, None
    if action.get("target_kind") == "HERO":
        if player.hero_max_health is None:
            return "HERO_MAX_HEALTH_UNKNOWN", None, None
        return None, player.hero_health, player.hero_max_health
    if action.get("target_kind") != "MINION":
        return "TARGET_KIND_UNSUPPORTED", None, None
    matches = [entity for entity in player.board if entity.board_position == action.get("target_board_position")]
    if len(matches) != 1 or matches[0].card.card_id != action.get("target_card_id"):
        return "TARGET_NOT_RESOLVED", None, None
    entity = matches[0]
    if entity.max_health < 1 or not 0 <= entity.current_health <= entity.max_health:
        return "TARGET_HEALTH_INVALID", None, None
    return None, entity.current_health, entity.max_health


def _check_restore(state, action, effect, texts) -> CheckResult:
    if "target_kind" not in action:
        return CheckResult(UNSUPPORTED, "UNTARGETED_RESTORE")
    problem, current, maximum = _target_health(state, action)
    if problem:
        return CheckResult(UNKNOWN, problem)
    missing = maximum - current
    bonus = state.self_player.healing_bonus
    amount = effect.value + (bonus or 0)
    details = {"mechanic": RESTORE_TARGET, "missing_health": missing, "base_restore": effect.value,
               "healing_bonus": bonus, "restore_upper_bound_known": bonus is not None,
               "direct_restore_min": min(missing, amount), "effect_provenance": effect.provenance}
    side, side_reasons, side_details = _side_effects(state, action, texts, _trigger_pattern(action, _HEAL_SIDE))
    details.update(side_details)
    unknown, modifiers = _screen([card for _, card in _public_cards(state)], texts, _HEAL_MODIFIER)
    details.update({"modifier_unknown_cards": unknown, "modifier_matching_cards": modifiers})
    if unknown:
        return CheckResult(UNKNOWN, "VISIBLE_ENTITY_TEXT_UNKNOWN", side, side_reasons, details)
    if modifiers:
        # e.g. "Your next Healing effect this turn deals damage instead" turns a zero heal into damage.
        return CheckResult(UNKNOWN, "VISIBLE_HEALING_MODIFIER", side, side_reasons, details)
    if missing == 0:
        return CheckResult(NO_DIRECT_EFFECT, "TARGET_AT_FULL_HEALTH", side, side_reasons, details)
    return CheckResult(DIRECT_EFFECT_PRESENT, "TARGET_DAMAGED", side, side_reasons, details)


def _check_destroy(state, action, effect, texts) -> CheckResult:
    threshold = effect.value
    minions = [(side, entity) for side, player in (("SELF", state.self_player), ("OPPONENT", state.opponent))
               for entity in player.board]
    qualifying = [(side, entity) for side, entity in minions if entity.current_attack >= threshold]
    affected = [(side, entity) for side, entity in qualifying if not (entity.dormant or entity.immune)]
    details = {"mechanic": DESTROY_MINIONS_MIN_ATTACK, "attack_threshold": threshold,
               "minion_attacks": {side: sorted(entity.current_attack for s, entity in minions if s == side)
                                  for side in ("SELF", "OPPONENT")},
               "qualifying": {side: sum(s == side for s, _ in qualifying) for side in ("SELF", "OPPONENT")},
               "effect_provenance": effect.provenance}
    side, side_reasons, side_details = _side_effects(state, action, texts, _trigger_pattern(action, None))
    details.update(side_details)
    # A visible "whenever you cast a spell" text could change Attack before the destroy resolves.
    unknown, modifiers = _screen([card for _, card in _public_cards(state)], texts, _SPELL_TRIGGER)
    details.update({"modifier_unknown_cards": unknown, "modifier_matching_cards": modifiers})
    if unknown:
        return CheckResult(UNKNOWN, "VISIBLE_ENTITY_TEXT_UNKNOWN", side, side_reasons, details)
    if modifiers:
        return CheckResult(UNKNOWN, "VISIBLE_SPELL_TRIGGER", side, side_reasons, details)
    if len(affected) != len(qualifying):
        return CheckResult(UNKNOWN, "QUALIFYING_MINION_DORMANT_OR_IMMUNE", side, side_reasons, details)
    if not qualifying:
        return CheckResult(NO_DIRECT_EFFECT, "NO_MINION_MEETS_ATTACK_THRESHOLD", side, side_reasons, details)
    return CheckResult(DIRECT_EFFECT_PRESENT, "MINIONS_MEET_ATTACK_THRESHOLD", side, side_reasons, details)


def check_direct_effect(state: GameState, action: Mapping, effects: Mapping[str, VerifiedEffect],
                        texts: Mapping[str, str]) -> CheckResult:
    """Classify one legal action's direct effect in one player-visible state."""
    source = _source_id(action)
    effect = effects.get(source) if source else None
    if effect is None:
        return CheckResult(UNSUPPORTED, "MECHANIC_NOT_SUPPORTED")
    if effect.mechanic == RESTORE_TARGET:
        return _check_restore(state, action, effect, texts)
    if effect.mechanic == DESTROY_MINIONS_MIN_ATTACK:
        return _check_destroy(state, action, effect, texts)
    return CheckResult(UNSUPPORTED, "MECHANIC_NOT_SUPPORTED")


def is_demotable(result: CheckResult) -> bool:
    """Only a verified zero direct effect with no visible or hidden possible side effect may be demoted."""
    return result.status == NO_DIRECT_EFFECT and result.side_effects == SIDE_NONE_VISIBLE


def constrained_order(order: list[int], demote: set[int]) -> list[int]:
    """Stable diagnostic rerank: demotable actions move after all others; no action is removed."""
    return [index for index in order if index not in demote] + [index for index in order if index in demote]
