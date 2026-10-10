"""Partial, fail-closed tactical observations for visible legal actions.

This experiment is not a rules engine. It reports direct arithmetic facts and
simple card-body descriptors separately from concrete action recommendations.
"""
from __future__ import annotations

from dataclasses import dataclass

from manamind.domain.card import CardFeatures
from manamind.domain.game_state import GameState


@dataclass(frozen=True, slots=True)
class Advice:
    # Keep the original fields first for callers of the ALGO-FIRST-1 API.
    action: dict | None
    status: str
    rule_type: str
    applicability: str
    explanation: str
    limitations: tuple[str, ...] = ()
    facts: tuple[dict, ...] = ()
    estimates: tuple[dict, ...] = ()
    unassessed_alternatives: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    analysis_status: str = "NO_ANALYSIS"
    candidate_exclusions: tuple[tuple[str, int], ...] = ()


_NON_COLLISION_MECHANICS = frozenset({
    # These keywords affect targeting/availability or a prior card-play step,
    # but do not themselves alter one ordinary attack's damage arithmetic.
    "BATTLECRY", "CANT_ATTACK", "CHARGE", "COMBO", "DISCOVER", "ELUSIVE",
    "FORGE", "OVERLOAD", "RUSH", "SPELLPOWER", "START_OF_GAME_KEYWORD",
    "STEALTH", "TAUNT", "TRADEABLE", "WINDFURY",
})
_UNRESOLVED_MECHANICS = frozenset({
    "AURA", "DEATHRATTLE", "DIVINE_SHIELD", "ENRAGED", "IMMUNE", "INVISIBLEDEATHRATTLE",
    "LIFESTEAL", "POISONOUS", "REBORN", "TRIGGER_VISUAL",
})
_ACTION_TYPE_LABELS = {
    "PLAY_CARD": "PLAY_CARD effects",
    "HERO_POWER": "HERO_POWER effects",
    "ACTIVATE_LOCATION": "ACTIVATE_LOCATION effects",
    "END_TURN": "END_TURN value",
}


def _result(
    *,
    action: dict | None = None,
    rule: str = "NONE",
    explanation: str,
    facts: list[dict] | None = None,
    estimates: list[dict] | None = None,
    alternatives: list[str] | None = None,
    blockers: list[str] | None = None,
    limitations: list[str] | None = None,
    exclusions: dict[str, int] | None = None,
) -> Advice:
    facts = facts or []
    estimates = estimates or []
    status = "RECOMMEND" if action is not None else "ABSTAIN"
    analysis_status = "PARTIAL" if facts or estimates else "NO_ANALYSIS"
    return Advice(
        action=action,
        status=status,
        rule_type=rule,
        applicability="PARTIAL" if analysis_status == "PARTIAL" else "NONE",
        explanation=explanation,
        limitations=tuple(limitations or []),
        facts=tuple(facts),
        estimates=tuple(estimates),
        unassessed_alternatives=tuple(sorted(set(alternatives or []))),
        blockers=tuple(sorted(set(blockers or []))),
        analysis_status=analysis_status,
        candidate_exclusions=tuple(sorted((exclusions or {}).items())),
    )


def _board_index(state: GameState) -> tuple[dict[int, object], dict[int, object], list[str]]:
    own = {item.board_position: item for item in state.self_player.board}
    opponent = {item.board_position: item for item in state.opponent.board}
    errors = []
    if len(own) != len(state.self_player.board) or len(opponent) != len(state.opponent.board):
        errors.append("DUPLICATE_BOARD_POSITION")
    return own, opponent, errors


def _mechanic_review(entity, known_card_ids: set[str], metadata: dict[str, CardFeatures]) -> list[str]:
    """Return blockers to claiming a complete ordinary combat resolution."""
    blockers = []
    card_id = entity.card.card_id
    if card_id not in known_card_ids or card_id not in metadata:
        blockers.append("CARD_METADATA_MISSING")
    mechanics = set(entity.card.mechanics)
    if card_id in metadata:
        mechanics.update(metadata[card_id].mechanics)
    unresolved = mechanics & _UNRESOLVED_MECHANICS
    blockers.extend(f"MECHANIC_{name}" for name in sorted(unresolved))
    unknown = mechanics - _NON_COLLISION_MECHANICS - _UNRESOLVED_MECHANICS
    blockers.extend(f"UNKNOWN_MECHANIC_{name}" for name in sorted(unknown))
    if any((getattr(entity, name, False) for name in (
        "divine_shield", "immune", "lifesteal", "poisonous", "reborn", "dormant",
    ))):
        blockers.append("COMBAT_STATUS_FLAG")
    return blockers


def _attack_local_fact(action: dict, own: dict, opponent: dict) -> tuple[dict | None, list[str]]:
    if action.get("type") != "ATTACK":
        return None, []
    source_attack = action.get("source_attack")
    if type(source_attack) is not int or source_attack < 0:
        return None, ["ATTACK_SOURCE_STATS_MISSING"]
    source = None
    if action.get("source_kind") == "MINION" or action.get("source_board_position", -1) > 0:
        source = own.get(action.get("source_board_position"))
        if (source is None or action.get("source_attack") != source.current_attack
                or action.get("source_health") != source.current_health):
            return None, ["ATTACK_SOURCE_MENU_MISMATCH"]

    if action.get("target_kind") == "HERO" and action.get("target_side") == "OPPONENT":
        fact = {
            "type": "FACE_ATTACK_DAMAGE",
            "source_board_position": action.get("source_board_position"),
            "damage_if_unmodified": source_attack,
            "statement": "The legal ordinary attack exposes this much current attack damage toward the opposing hero.",
            "scope": "DAMAGE_POTENTIAL_ONLY",
        }
        return fact, []

    if action.get("target_kind") != "MINION" or action.get("target_side") != "OPPONENT":
        return None, []
    target = opponent.get(action.get("target_board_position"))
    if target is None:
        return None, ["ATTACK_TARGET_NOT_IN_VISIBLE_BOARD"]
    if (action.get("target_attack") != target.current_attack
            or action.get("target_health") != target.current_health):
        return None, ["ATTACK_TARGET_MENU_MISMATCH"]
    source_health = action.get("source_health")
    if type(source_health) is not int or source_health < 0:
        return None, ["ATTACK_SOURCE_HEALTH_MISSING"]
    target_damage = target.current_attack
    fact = {
        "type": "DIRECT_ATTACK_ARITHMETIC",
        "source_board_position": action.get("source_board_position"),
        "target_board_position": target.board_position,
        "source_damage": source_attack,
        "target_health_before_attack": target.current_health,
        "target_reaches_zero_from_direct_damage": source_attack >= target.current_health,
        "return_damage": target_damage,
        "source_health_before_attack": source_health,
        "source_reaches_zero_from_return_damage": target_damage >= source_health,
        "scope": "DIRECT_DAMAGE_ARITHMETIC_ONLY",
    }
    return fact, []


def _face_attack_group(state: GameState, actions: list[dict], own: dict) -> tuple[list[dict], int, list[str]]:
    ready = {position: minion for position, minion in own.items() if minion.can_attack}
    by_position = {}
    hero_actions = []
    for action in actions:
        if (action.get("type") == "ATTACK" and action.get("target_kind") == "HERO"
                and action.get("target_side") == "OPPONENT" and action.get("source_is_hero")):
            hero_actions.append(action)
        elif (action.get("type") == "ATTACK" and action.get("target_kind") == "HERO"
                and action.get("target_side") == "OPPONENT"
                and action.get("source_board_position") in ready):
            position = action["source_board_position"]
            by_position.setdefault(position, []).append(action)
    if set(by_position) != set(ready) or any(len(items) != 1 for items in by_position.values()):
        return [], 0, ["INCOMPLETE_OR_AMBIGUOUS_FACE_ATTACK_MENU"]
    total = 0
    for position, minion in ready.items():
        action = by_position[position][0]
        if (type(minion.current_attack) is not int or minion.current_attack <= 0
                or action.get("source_attack") != minion.current_attack
                or action.get("source_health") != minion.current_health):
            return [], 0, ["FACE_ATTACK_STATS_UNRESOLVED"]
        total += minion.current_attack
    if len(hero_actions) > 1:
        return [], 0, ["AMBIGUOUS_HERO_FACE_ATTACK_MENU"]
    if hero_actions:
        hero_attack = hero_actions[0].get("source_attack")
        if type(hero_attack) is not int or hero_attack <= 0:
            return [], 0, ["HERO_FACE_ATTACK_STATS_UNRESOLVED"]
        total += hero_attack
    ordered = [by_position[position][0] for position in sorted(by_position)] + hero_actions
    return ordered, total, []


def _candidate_estimates(
    state: GameState,
    actions: list[dict],
    known_card_ids: set[str],
    metadata: dict[str, CardFeatures],
) -> tuple[list[dict], dict[str, int], list[str]]:
    estimates = []
    exclusions: dict[str, int] = {}
    blockers = []

    def exclude(reason: str) -> None:
        exclusions[reason] = exclusions.get(reason, 0) + 1

    used_slots = len(state.self_player.board) + len(state.self_player.locations)
    for action in actions:
        if action.get("type") != "PLAY_CARD" or action.get("card_type") != "MINION":
            continue
        if "PLAY_CARD" in {item.get("type") for item in actions}:
            blockers.append("PLAY_CARD_EFFECTS_NOT_EVALUATED")
        if used_slots >= 7:
            exclude("NO_OPEN_SHARED_BOARD_SLOT")
            continue
        hand_index = action.get("hand_index")
        if type(hand_index) is not int or not 0 <= hand_index < len(state.self_hand):
            exclude("MENU_STRUCTURE_HAND_LINK")
            continue
        card_id = action.get("card_id")
        observed = state.self_hand[hand_index]
        base = metadata.get(card_id)
        if base is None or card_id not in known_card_ids or observed.card_id != card_id:
            exclude("CARD_METADATA_MISSING_OR_ID_MISMATCH")
            continue
        if base.card_type != "MINION" or base.attack is None or base.health is None:
            exclude("BASE_STATS_MISSING")
            continue
        cost = observed.current_cost if observed.current_cost is not None else observed.cost
        if (type(cost) is not int or cost < 0 or cost > state.self_player.available_mana
                or action.get("card_cost") != cost):
            exclude("CURRENT_COST_OR_MANA_UNRESOLVED")
            continue
        position = action.get("play_position")
        # The importer generates insertion slots 1..occupied_shared_slots+1.
        if type(position) is not int or not 1 <= position <= used_slots + 1 or position > 7:
            exclude("MENU_STRUCTURE_INVALID_PLAY_POSITION")
            continue
        mechanics = sorted(set(observed.mechanics) | set(base.mechanics))
        estimates.append({
            "type": "MINION_BODY_TO_COST",
            "candidate_id": f"{card_id}:hand:{hand_index}:position:{position}",
            "card_id": card_id,
            "hand_index": hand_index,
            "play_position": position,
            "cost_now": cost,
            "available_mana": state.self_player.available_mana,
            "base_attack": base.attack,
            "base_health": base.health,
            "base_stats_per_cost": round((base.attack + base.health) / max(cost, 1), 6),
            "self_board_entities_before_play": used_slots,
            "opponent_board_entities": len(state.opponent.board) + len(state.opponent.locations),
            "mechanics_seen": mechanics,
            "effect_value": "NOT_EVALUATED",
            "placement_value": "NOT_EVALUATED",
            "scope": "APPROXIMATE_CARD_BODY_DESCRIPTOR",
        })
        blockers.append("MINION_TEXT_OR_EFFECT_NOT_EVALUATED")
        if mechanics:
            blockers.append("MINION_HAS_DECLARED_MECHANICS")
    return estimates, exclusions, blockers


def _unassessed_actions(actions: list[dict], estimates: list[dict]) -> list[str]:
    kinds = {action.get("type") for action in actions}
    labels = [_ACTION_TYPE_LABELS[kind] for kind in kinds if kind in _ACTION_TYPE_LABELS]
    if any(action.get("type") == "PLAY_CARD" and action.get("card_type") != "MINION" for action in actions):
        labels.append("PLAY_CARD non-minion effects")
    if estimates:
        labels.append("Global value comparison between card candidates and attacks")
        labels.append("Minion placement effects and adjacency interactions")
    return sorted(set(labels))


def advise(
    state: GameState,
    legal_actions: list[dict],
    *,
    known_card_ids: set[str] | None = None,
    metadata: dict[str, CardFeatures] | None = None,
) -> Advice:
    """Report local facts and rough candidate descriptors; recommend only a proven win line."""
    if not legal_actions or any(not isinstance(action, dict) for action in legal_actions):
        return _result(explanation="Пустое или некорректное меню действий.", blockers=["LEGAL_MENU_INVALID"])
    if state.active_player != "SELF" or state.pending_choice_owner is not None:
        return _result(explanation="Сейчас не обычный ход SELF или ожидается выбор.", blockers=["STATE_NOT_DECISION_READY"])
    if known_card_ids is None:
        known_card_ids = set()
    metadata = metadata or {}
    own, opponent, board_errors = _board_index(state)

    facts = []
    blockers = list(board_errors)
    exclusions: dict[str, int] = {}
    for action in legal_actions:
        fact, fact_blockers = _attack_local_fact(action, own, opponent)
        if fact is not None:
            if fact["type"] == "DIRECT_ATTACK_ARITHMETIC":
                participating = [own.get(fact["source_board_position"]),
                                 opponent.get(fact["target_board_position"])]
                interaction_blockers = []
                for entity in participating:
                    if entity is not None:
                        interaction_blockers.extend(_mechanic_review(entity, known_card_ids, metadata))
                if state.self_player.active_effects or state.opponent.active_effects:
                    interaction_blockers.append("ACTIVE_EFFECT_INTERACTION_UNRESOLVED")
                if state.evidence_constraints:
                    interaction_blockers.append("STATE_EVIDENCE_CONSTRAINT")
                fact["resolution"] = "DIRECT_DAMAGE_ONLY" if not interaction_blockers else "FULL_RESOLUTION_UNRESOLVED"
                fact["resolution_blockers"] = sorted(set(interaction_blockers))
                blockers.extend(interaction_blockers)
            else:
                blockers.append("HERO_DAMAGE_REACTIONS_NOT_EVALUATED")
            facts.append(fact)
        blockers.extend(fact_blockers)

    lethal_action = None
    face_actions, face_damage, face_errors = _face_attack_group(state, legal_actions, own)
    blockers.extend(face_errors if face_errors and any(m.can_attack for m in own.values()) else [])
    if face_actions and state.opponent.hero_health > 0:
        required = state.opponent.hero_health + state.opponent.armor
        facts.append({
            "type": "ORDINARY_FACE_ATTACK_DAMAGE_POTENTIAL",
            "damage_if_all_visible_ordinary_attacks_resolve_unmodified": face_damage,
            "opponent_health_plus_armor": required,
            "arithmetic_condition_met": face_damage >= required,
            "scope": "POTENTIAL_ATTACK_ONLY_NOT_GLOBAL_MENU_RANKING",
        })
        lethal_blockers = []
        for minion in (*state.self_player.board, *state.opponent.board):
            lethal_blockers.extend(_mechanic_review(minion, known_card_ids, metadata))
        if state.opponent.secret_count:
            lethal_blockers.append("OPPONENT_SECRET_REACTION_UNRESOLVED")
        if any(action.get("source_is_hero") for action in face_actions):
            lethal_blockers.append("HERO_ATTACK_REACTION_UNRESOLVED")
        if state.opponent.hero_divine_shield is not False:
            lethal_blockers.append("OPPONENT_HERO_SHIELD_UNKNOWN_OR_PRESENT")
        if state.self_player.active_effects or state.opponent.active_effects:
            lethal_blockers.append("ACTIVE_EFFECT_INTERACTION_UNRESOLVED")
        if state.evidence_constraints:
            lethal_blockers.append("STATE_EVIDENCE_CONSTRAINT")
        potential = face_damage >= required
        if potential:
            facts.append({
                "type": "POTENTIAL_ATTACK_ONLY_LETHAL",
                "damage_if_all_ordinary_attacks_resolve_unmodified": face_damage,
                "opponent_health_plus_armor": required,
                "arithmetic_condition_met": True,
                "resolution": "PROVEN_ATTACK_LINE" if not lethal_blockers else "POTENTIAL_ONLY",
                "resolution_blockers": sorted(set(lethal_blockers)),
                "scope": "ATTACKS_ONLY_NOT_GLOBAL_MENU_RANKING",
            })
            if not lethal_blockers:
                # A guaranteed immediate win is sufficient to recommend the first
                # attack, regardless of other legal actions in the menu.
                lethal_action = face_actions[0]
                blockers = [item for item in blockers if item not in lethal_blockers]
            else:
                blockers.extend(lethal_blockers)

    estimates, exclusions, play_blockers = _candidate_estimates(
        state, legal_actions, known_card_ids, metadata,
    )
    blockers.extend(play_blockers)
    alternatives = _unassessed_actions(legal_actions, estimates)
    if state.evidence_constraints:
        blockers.append("STATE_EVIDENCE_CONSTRAINT")

    if lethal_action is not None:
        return _result(
            action=lethal_action,
            rule="ATTACK_ONLY_LETHAL",
            explanation="Найдена подтверждённая последовательность обычных атак, достаточная для победы по текущим видимым значениям.",
            facts=facts,
            estimates=estimates,
            alternatives=alternatives,
            blockers=blockers,
            limitations=["Рекомендация касается немедленного win line; полный ranking других действий не выполняется."],
            exclusions=exclusions,
        )
    if facts or estimates:
        why = "Есть локальные факты/приблизительные признаки, но оснований сравнить все legal actions для выбора лучшего хода нет."
        return _result(
            rule="PARTIAL_VISIBLE_STATE_ANALYSIS",
            explanation=why,
            facts=facts,
            estimates=estimates,
            alternatives=alternatives,
            blockers=blockers or ["NO_PROVEN_TERMINAL_LINE", "GLOBAL_ACTION_VALUES_UNASSESSED"],
            limitations=["Локальная арифметика и body-to-cost признаки не являются оценкой глобальной ценности хода."],
            exclusions=exclusions,
        )
    return _result(
        explanation="Не найдено поддерживаемого арифметического факта или кандидата карты; лучший ход не определяется.",
        alternatives=alternatives,
        blockers=blockers or ["NO_SUPPORTED_LOCAL_ANALYSIS", "GLOBAL_ACTION_VALUES_UNASSESSED"],
        exclusions=exclusions,
    )
