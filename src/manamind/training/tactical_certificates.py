"""Offline, bounded certificates for declared fixtures; never a gameplay ranker.

Single-action claims use the existing Action Outcome. The only sequence proof
is <=4 one-use attackers against <=2 zero-Attack, vanilla Taunts and one hero.
It returns winning first indices, not a successor GameState or a general engine.
"""
from __future__ import annotations

from functools import lru_cache

import torch

from manamind.domain.serialization import game_state_from_dict
from manamind.outcome import TextSource, forecast_action
from manamind.outcome.diagnostics import direct_vector, dominates
from manamind.outcome.model import Status
from manamind.outcome.world import ObservedContext


def set_loss(scores, labels):
    """Existing MODEL-FIRST-2 set-marginal CE, including equivalent gold actions."""
    if not labels or len(set(labels)) != len(labels):
        raise ValueError("Nonempty unique gold indices required")
    if any(type(i) is not int or not 0 <= i < scores.numel() for i in labels):
        raise ValueError("Gold outside menu")
    return torch.logsumexp(scores, 0) - torch.logsumexp(scores[labels], 0)


def sequence_firsts(state, actions):
    """Independent integer proof: no retaliation, triggers, Windfury or repeats."""
    own = [m for m in state.self_player.board if m.can_attack]
    enemy = list(state.opponent.board)
    if len(own) > 4 or len(enemy) > 2:
        raise ValueError("Sequence certificate bound")
    if any(m.current_attack <= 0 or m.current_health <= 0 or m.frozen or m.dormant for m in own):
        raise ValueError("Sequence source must be observed ready and alive")
    if any(m.current_attack or not m.taunt or m.divine_shield or m.reborn or m.immune
           or m.poisonous or m.lifesteal or m.dormant or m.stealth for m in enemy):
        raise ValueError("Sequence certificate requires zero-Attack plain Taunts")
    if any(m.windfury or m.reborn or m.lifesteal or m.poisonous for m in own):
        raise ValueError("Sequence source mechanic outside certificate")
    if state.opponent.hero_divine_shield is None:
        raise ValueError("Hero shield unknown")
    sources = {(m.board_position, "MINION"): m.current_attack for m in own}
    if any(a.get("source_kind") == "HERO" for a in actions):
        if (state.self_player.hero_attack <= 0 or state.self_player.weapon is None
                or state.self_player.hero_frozen is not False
                or not state.self_player.weapon.effective_durability
                or state.self_player.weapon.effective_durability < 0):
            raise ValueError("Hero attack not observed")
        sources[(-1, "HERO")] = state.self_player.hero_attack
    keys = tuple(sources)
    if len(keys) > 4:
        raise ValueError("Sequence certificate bound includes the hero")
    attacks = tuple(sources.values())
    health = tuple(m.current_health for m in enemy)
    positions = tuple(m.board_position for m in enemy)

    @lru_cache(None)
    def wins(mask, targets, hp, shield):
        if hp <= 0:
            return True
        for i, attack in enumerate(attacks):
            if not mask & (1 << i):
                continue
            next_mask = mask ^ (1 << i)
            if any(h > 0 for h in targets):
                for j, h in enumerate(targets):
                    if h > 0:
                        new = list(targets)
                        new[j] = max(0, h - attack)
                        if wins(next_mask, tuple(new), hp, shield):
                            return True
            elif wins(next_mask, targets, hp if shield else hp-attack, False):
                return True
        return False

    answer = []
    hp = state.opponent.hero_health + state.opponent.armor
    shield = state.opponent.hero_divine_shield
    for index, action in enumerate(actions):
        if action["type"] != "ATTACK":
            continue
        key = (action["source_board_position"], action["source_kind"])
        i = keys.index(key)
        mask = ((1 << len(keys))-1) ^ (1 << i)
        targets = list(health)
        if action["target_kind"] == "HERO":
            if any(targets):
                raise ValueError("Face bypasses Taunt")
            won = wins(mask, tuple(targets), hp if shield else hp-attacks[i], False)
        else:
            j = positions.index(action["target_board_position"])
            targets[j] = max(0, targets[j]-attacks[i])
            won = wins(mask, tuple(targets), hp, shield)
        if won:
            answer.append(index)
    return answer


def certify(row):
    """Return a certificate over visible facts and explicitly declared fixture text."""
    state = game_state_from_dict(row["state"])
    goal = row["certificate"]["goal"]
    if goal == "AMBIGUOUS":
        if row["correct_actions"]:
            raise ValueError("Ambiguous fixture cannot own a gold")
        return {"gold": [], "scope": "ABSTAIN", "consequences": []}
    context = ObservedContext(**{**row["certificate"]["observed"],
                                "hand_keywords": tuple(frozenset(x) for x in
                                                       row["certificate"]["observed"]["hand_keywords"])})
    texts = TextSource.from_records(row["certificate"]["texts"], source="declared_fixture")
    forecasts = [forecast_action(state, a, texts, context) for a in row["legal_actions"]]
    if any(f.status is not Status.EXACT for f in forecasts):
        raise ValueError("Certificate has unobserved effects or reactions")
    effects = [f.exact_state() for f in forecasts]
    if goal == "WIN_BY_ATTACKS":
        gold = sequence_firsts(state, row["legal_actions"])
        scope = "WINNING_ATTACK_PREFIX_IN_BOUNDED_DOMAIN"
    elif goal == "WIN_NOW":
        gold = [i for i, s in enumerate(effects) if s.opponent.hero_health == 0 and s.self_player.hero_health > 0]
        scope = "IMMEDIATE_VICTORY"
    elif goal == "REMOVE_AND_SURVIVE":
        gold = []
        for i, (a, s) in enumerate(zip(row["legal_actions"], effects)):
            if a["type"] != "ATTACK" or a["target_kind"] != "MINION":
                continue
            # Outcome compacts positions after a death; fixture card handles are unique.
            target_gone = not any(m.card.card_id == a["target_card_id"] for m in s.opponent.board)
            source_survives = any(m.card.card_id == a["source_card_id"] for m in s.self_player.board)
            if target_gone and source_survives:
                gold.append(i)
        scope = "KILL_AND_SURVIVE_PROPERTY_NOT_GLOBAL_OPTIMALITY"
    elif goal == "LOCAL_PARETO":
        vectors = [direct_vector(state, f) for f in forecasts]
        gold = [i for i, v in enumerate(vectors) if not any(dominates(w, v) for w in vectors)]
        scope = "NONDOMINATED_EXACT_EFFECTS_COSTS_AND_FUTURE_EXCLUDED"
    else:
        raise ValueError("Unsupported certificate goal")
    if not gold:
        raise ValueError("No certified action")
    return {"gold": gold, "scope": scope,
            "consequences": [{"action": f.label, "changes": [c.describe() for c in f.changes]}
                             for f in forecasts]}
