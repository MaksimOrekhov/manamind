"""Conservative, experimental tactical rules for player-visible legal actions.

This module is deliberately not a simulator or a general move ranker. It only
reports narrow arithmetic observations and abstains when the menu or mechanics
fall outside those observations.
"""
from __future__ import annotations

from dataclasses import dataclass

from manamind.domain.card import CardFeatures
from manamind.domain.game_state import GameState


@dataclass(frozen=True, slots=True)
class Advice:
    action: dict | None
    status: str
    rule_type: str
    applicability: str
    explanation: str
    limitations: tuple[str, ...] = ()


_UNSAFE_COMBAT_FLAGS = (
    "divine_shield", "stealth", "immune", "frozen", "lifesteal", "poisonous",
    "reborn", "dormant", "windfury",
)


def _abstain(reason: str, *, rule: str = "NONE") -> Advice:
    return Advice(None, "ABSTAIN", rule, "NONE", reason)


def _has_unsafe_combat_flags(entity) -> bool:
    return any(getattr(entity, name, False) for name in _UNSAFE_COMBAT_FLAGS)


def _vanilla_board(state: GameState, known_card_ids: set[str]) -> bool:
    entities = (*state.self_player.board, *state.opponent.board)
    return (state.opponent.secret_count == 0 and all(
        entity.card.card_id in known_card_ids
        and entity.card.card_type == "MINION"
        and not entity.card.mechanics
        and not _has_unsafe_combat_flags(entity)
        for entity in entities
    ))


def _attack_sources(state: GameState, actions: list[dict]) -> dict[int, object] | None:
    ready = {minion.board_position: minion for minion in state.self_player.board if minion.can_attack}
    menu_sources = {a.get("source_board_position") for a in actions if a.get("type") == "ATTACK"}
    if not ready or menu_sources != set(ready):
        return None
    for action in actions:
        if action.get("type") != "ATTACK":
            continue
        source = ready.get(action.get("source_board_position"))
        if (source is None or action.get("source_attack") != source.current_attack
                or action.get("source_health") != source.current_health):
            return None
    return ready


def _lethal(state: GameState, actions: list[dict], known_card_ids: set[str]) -> Advice | None:
    if any(a.get("type") not in {"ATTACK", "END_TURN"} for a in actions):
        return None
    if not _vanilla_board(state, known_card_ids):
        return None
    sources = _attack_sources(state, actions)
    if sources is None:
        return None
    face_by_source: dict[int, dict] = {}
    for action in actions:
        if (action.get("type") == "ATTACK" and action.get("target_kind") == "HERO"
                and action.get("target_side") == "OPPONENT"):
            source_pos = action.get("source_board_position")
            if source_pos in face_by_source:
                return None
            face_by_source[source_pos] = action
    if set(face_by_source) != set(sources):
        return None
    required = state.opponent.hero_health + state.opponent.armor
    total = sum(source.current_attack for source in sources.values())
    if required <= 0 or total < required:
        return None
    chosen = min(face_by_source.values(), key=lambda action: (
        action.get("source_board_position", 0), action.get("target_side", ""),
    ))
    return Advice(
        chosen, "RECOMMEND", "ATTACK_ONLY_LETHAL", "PARTIAL",
        f"Арифметически подтверждено: доступные обычные атаки по герою суммарно наносят {total}, "
        f"у героя противника {required} здоровья с бронёй. Начните с указанной атаки.",
        ("Проверяется только последовательность обычных атак; это не сравнение с розыгрышем карт/силой героя.",),
    )


def _trade_candidates(state: GameState, actions: list[dict], known_card_ids: set[str]) -> tuple[list[dict], list[dict]]:
    if not _vanilla_board(state, known_card_ids):
        return [], []
    own = {m.board_position: m for m in state.self_player.board}
    enemy = {m.board_position: m for m in state.opponent.board}
    favorable, unfavorable = [], []
    for action in actions:
        if (action.get("type") != "ATTACK" or action.get("target_kind") != "MINION"
                or action.get("target_side") != "OPPONENT"):
            continue
        source = own.get(action.get("source_board_position"))
        target = enemy.get(action.get("target_board_position"))
        if source is None or target is None or source.current_attack <= 0 or target.current_attack < 0:
            continue
        if (action.get("source_attack") != source.current_attack
                or action.get("source_health") != source.current_health
                or action.get("target_attack") != target.current_attack
                or action.get("target_health") != target.current_health
                or action.get("target_taunt") != target.taunt):
            continue
        target_dies = source.current_attack >= target.current_health
        source_dies = target.current_attack >= source.current_health
        if target_dies and not source_dies:
            favorable.append(action)
        elif source_dies and not target_dies:
            unfavorable.append(action)
    return favorable, unfavorable


def _simple_minion_plays(
    state: GameState, actions: list[dict], known_card_ids: set[str], metadata: dict[str, CardFeatures],
) -> list[tuple[tuple[float, int, int, int], dict]]:
    """Rank only plain, catalog-known minion plays by visible body/mana/board descriptors."""
    if state.self_player.available_mana < 0 or len(state.self_player.board) + len(state.self_player.locations) >= 7:
        return []
    if state.self_player.active_effects or state.opponent.active_effects:
        return []
    own_board_count = len(state.self_player.board) + len(state.self_player.locations)
    opponent_board_count = len(state.opponent.board) + len(state.opponent.locations)
    candidates = []
    for action in actions:
        if action.get("type") != "PLAY_CARD" or action.get("card_type") != "MINION":
            continue
        hand_index = action.get("hand_index")
        if type(hand_index) is not int or not 0 <= hand_index < len(state.self_hand):
            continue
        observed = state.self_hand[hand_index]
        card_id = action.get("card_id")
        base = metadata.get(card_id)
        if (base is None or card_id not in known_card_ids or observed.card_id != card_id
                or base.card_type != "MINION" or observed.mechanics or base.mechanics
                or base.attack is None or base.health is None
                or action.get("card_attack") != base.attack or action.get("card_health") != base.health):
            continue
        cost = observed.current_cost if observed.current_cost is not None else observed.cost
        if (type(cost) is not int or cost < 0 or cost > state.self_player.available_mana
                or action.get("card_cost") != cost):
            continue
        if (action.get("play_position") not in range(1, 8)
                or action.get("play_position") > 7 - own_board_count):
            continue
        # This lexicographic score is only an uncalibrated descriptor ordering.
        # It weighs visible stats against current cost, then considers mana use and board context.
        stat_efficiency = (base.attack + base.health) / max(cost, 1)
        stat_total = base.attack + base.health
        spends_more_available_mana = min(cost, state.self_player.available_mana)
        board_context = int(own_board_count == 0) - opponent_board_count
        candidates.append(((stat_efficiency, stat_total, spends_more_available_mana, board_context), action))
    return candidates


def advise(
    state: GameState,
    legal_actions: list[dict],
    *,
    known_card_ids: set[str] | None = None,
    metadata: dict[str, CardFeatures] | None = None,
) -> Advice:
    """Return a narrowly justified recommendation or an explicit abstention."""
    if not legal_actions or any(not isinstance(action, dict) for action in legal_actions):
        return _abstain("Пустое или некорректное меню действий.")
    if state.active_player != "SELF" or state.pending_choice_owner is not None:
        return _abstain("Сейчас не обычный ход SELF или ожидается выбор.")
    if state.evidence_constraints:
        return _abstain("Состояние содержит неразрешённые ограничения достоверности.")
    if known_card_ids is None:
        return _abstain("Не передан список карт с проверенными метаданными.")

    lethal = _lethal(state, legal_actions, known_card_ids)
    if lethal is not None:
        return lethal

    favorable, unfavorable = _trade_candidates(state, legal_actions, known_card_ids)
    simple_plays = _simple_minion_plays(state, legal_actions, known_card_ids, metadata or {})
    if favorable and simple_plays:
        return _abstain("Есть и подходящий размен, и приблизительно оценённый розыгрыш существа; сравнить их ценность нельзя.",
                        rule="CROSS_ACTION_UNRANKED")
    unsupported_menu = any(a.get("type") not in {"ATTACK", "END_TURN"} for a in legal_actions)
    if len(favorable) == 1:
        return Advice(
            favorable[0], "RECOMMEND", "ARITHMETIC_FAVORABLE_TRADE", "PARTIAL",
            "По видимым текущим характеристикам эта обычная атака убивает цель, а атакующий выживает.",
            (("Другие действия меню не оцениваются; это не глобальный выбор хода.",) if unsupported_menu
             else ("Арифметика не учитывает ценность существ, будущие ответы и эффекты за пределами видимых признаков.",)),
        )
    if len(favorable) > 1:
        return _abstain("Найдено несколько арифметически успешных разменов без данных, чтобы сравнить их ценность.",
                        rule="ARITHMETIC_FAVORABLE_TRADE")
    if unfavorable:
        warning = (f"Обнаружено {len(unfavorable)} обычных атак, где атакующий погибает, а цель выживает. "
                   "Это предупреждение не определяет лучший ход и не оценивает возможный урон цели.")
    else:
        warning = ""
    if simple_plays:
        top_rank = max(rank for rank, _ in simple_plays)
        best_actions = [action for rank, action in simple_plays if rank == top_rank]
        if len(best_actions) != 1:
            return _abstain("Несколько существ получили одинаковую приблизительную оценку.",
                            rule="SIMPLE_MINION_PLAY_ESTIMATE")
        chosen = best_actions[0]
        other_kinds = sorted({a.get("type") for a in legal_actions if a.get("type") != "PLAY_CARD"})
        limits = ["Оценка приблизительная и не калибрована: сортирует только известные существа без механик "
                  "по отношению атаки+здоровья к текущей цене, затрачиваемой мане и заполненности стола."]
        if other_kinds:
            limits.append(f"Действия типов {', '.join(other_kinds)} и прочие розыгрыши не оцениваются; глобальное превосходство не установлено.")
        play_actions = [action for action in legal_actions if action.get("type") == "PLAY_CARD"]
        if len(play_actions) > len(simple_plays):
            limits.append("Некоторые розыгрыши карт (включая заклинания и неизвестные механики) не входят в сравнение.")
        if warning:
            limits.append(warning)
        return Advice(chosen, "RECOMMEND", "SIMPLE_MINION_PLAY_ESTIMATE", "APPROXIMATE_PARTIAL",
                      "Из поддерживаемых существ это наивысшая оценка по видимой стоимости, базовым характеристикам "
                      "и размеру стола.", tuple(limits))
    if warning:
        return Advice(None, "ABSTAIN", "ARITHMETIC_BAD_TRADE_WARNING", "PARTIAL", warning)
    return _abstain("В меню нет ситуации, для которой доступны узкие арифметические правила.")
