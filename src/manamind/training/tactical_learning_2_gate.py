"""Pre-training integrity gate and independent arithmetic for declared TL2 fixtures."""
from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
import json

from manamind.domain.serialization import game_state_from_dict
from manamind.outcome import TextSource, forecast_action
from manamind.outcome.model import Status
from manamind.outcome.world import ObservedContext
from manamind.training.policy_checkpoint import identity
from manamind.training.tactical_certificates import sequence_firsts
from manamind.live.snapshot import state_to_dict


def arithmetic_gold(row):
    """Compute from serialized numeric facts, never Action Outcome after-states."""
    state = game_state_from_dict(row["state"])
    goal = row["certificate"]["goal"]
    if goal == "AMBIGUOUS":
        return []
    if goal == "WIN_BY_ATTACKS":
        return sequence_firsts(state, row["legal_actions"])
    if goal == "PURE_SELF_HARM":
        # Declared AoE 2; only hostile body is Immune, own unshielded bodies die.
        if state.self_hand[0].card_id != "TL2_DAMAGE_ALL":
            raise ValueError("Wrong pure-harm spell")
        if not state.self_player.board or not state.opponent.board:
            raise ValueError("Harm template bound")
        if any(m.divine_shield or m.immune or m.current_health > 2 for m in state.self_player.board):
            raise ValueError("Own harm not guaranteed")
        if any(not m.immune for m in state.opponent.board):
            raise ValueError("Enemy gains not excluded")
        return [i for i,a in enumerate(row["legal_actions"]) if a["type"] == "END_TURN"]
    gold = []
    for i, a in enumerate(row["legal_actions"]):
        if a["type"] == "END_TURN":
            continue
        if goal == "WIN_NOW":
            if a.get("target_kind") == "HERO" and a.get("target_side") == "OPPONENT" and not state.opponent.hero_divine_shield:
                damage = a.get("source_attack", 6 if a["type"] == "PLAY_CARD" else 0)
                if damage >= state.opponent.hero_health+state.opponent.armor:
                    gold.append(i)
        elif goal == "REMOVE_AND_SURVIVE":
            if a["type"] != "ATTACK" or a["target_kind"] != "MINION":
                continue
            source = next(m for m in state.self_player.board if m.board_position == a["source_board_position"])
            target = next(m for m in state.opponent.board if m.board_position == a["target_board_position"])
            kills = not target.divine_shield and not target.immune and (source.poisonous or source.current_attack >= target.current_health)
            survives = source.divine_shield or source.immune or source.current_health > target.current_attack
            if kills and survives:
                gold.append(i)
        elif goal == "DEAL_ENEMY_DAMAGE":
            if a["type"] != "PLAY_CARD" or a.get("target_side") != "OPPONENT":
                continue
            shield = state.opponent.hero_divine_shield if a["target_kind"] == "HERO" else next(
                m.divine_shield for m in state.opponent.board if m.board_position == a["target_board_position"])
            if shield is False:
                gold.append(i)
        else:
            raise ValueError("Unsupported TL2 goal")
    if not gold:
        raise ValueError("No arithmetic certificate")
    return gold


def outcome_gold(row, legal_menu=None):
    """Independent second implementation for atomic properties; sequence bound separately audited."""
    if row["certificate"]["goal"] == "AMBIGUOUS":
        return [], []
    state = game_state_from_dict(row["state"])
    observed = row["certificate"]["observed"]
    context = ObservedContext(**{**observed, "hand_keywords": tuple(frozenset(x) for x in observed["hand_keywords"])})
    text = TextSource.from_records(row["certificate"]["texts"], source="verified_tl2_fixture")
    forecasts = [forecast_action(state,a,text,context) for a in row["legal_actions"]]
    if any(f.status is not Status.EXACT for f in forecasts):
        raise ValueError("Non-exact Outcome certificate")
    after = [f.exact_state() for f in forecasts]
    goal = row["certificate"]["goal"]
    gold = []
    for i,(a,s) in enumerate(zip(row["legal_actions"],after,strict=True)):
        if goal == "WIN_NOW" and s.opponent.hero_health == 0 and s.self_player.hero_health > 0:
            gold.append(i)
        elif goal == "REMOVE_AND_SURVIVE" and a["type"] == "ATTACK" and a["target_kind"] == "MINION":
            if not any(m.card.card_id == a["target_card_id"] for m in s.opponent.board) and any(
                    m.card.card_id == a["source_card_id"] for m in s.self_player.board):
                gold.append(i)
        elif goal == "DEAL_ENEMY_DAMAGE":
            before_hp = state.opponent.hero_health+state.opponent.armor+sum(m.current_health for m in state.opponent.board)
            after_hp = s.opponent.hero_health+s.opponent.armor+sum(m.current_health for m in s.opponent.board)
            own_before = state.self_player.hero_health+sum(m.current_health for m in state.self_player.board)
            own_after = s.self_player.hero_health+sum(m.current_health for m in s.self_player.board)
            if after_hp < before_hp and own_after == own_before:
                gold.append(i)
        elif goal == "PURE_SELF_HARM" and a["type"] == "END_TURN":
            gold.append(i)
    if goal == "PURE_SELF_HARM":
        cast = next(s for a,s in zip(row["legal_actions"],after,strict=True) if a["type"] == "PLAY_CARD")
        if cast.self_player.board or cast.opponent.board != state.opponent.board:
            raise ValueError("Outcome disagrees on pure harm")
    if goal == "WIN_BY_ATTACKS":
        if legal_menu is None:
            raise ValueError("Sequence validation requires complete menu")
        if state.self_hand:
            raise ValueError("Sequence audit only supports attack fixtures")
        @lru_cache(None)
        def wins(serialized, depth):
            current = game_state_from_dict(json.loads(serialized))
            if current.opponent.hero_health == 0:
                return True
            if not depth:
                return False
            for action in legal_menu(current):
                if action["type"] != "ATTACK":
                    continue
                forecast = forecast_action(current, action, text, context)
                if forecast.status is not Status.EXACT:
                    raise ValueError("Sequence successor not exact")
                if wins(json.dumps(state_to_dict(forecast.exact_state()),sort_keys=True), depth-1):
                    return True
            return False
        gold = [i for i,(a,s) in enumerate(zip(row["legal_actions"],after,strict=True)) if a["type"] == "ATTACK"
                and wins(json.dumps(state_to_dict(s),sort_keys=True),3)]
        # FIRST action atomic result independently matches packets and survival.
        for a,s in zip(row["legal_actions"],after,strict=True):
            if a["type"] != "ATTACK":
                continue
            if a["target_kind"] == "MINION":
                target = next(m for m in state.opponent.board if m.board_position == a["target_board_position"])
                remaining = max(0,target.current_health-a["source_attack"])
                survivors = [m.current_health for m in s.opponent.board if m.card.card_id == target.card.card_id]
                if survivors != ([remaining] if remaining else []):
                    raise ValueError("Sequence first packet disagreement")
    return gold, [[c.describe() for c in f.changes] for f in forecasts]


def validate_row(row, encoder, raw_catalog, legal_menu):
    state = game_state_from_dict(row["state"])
    observed = row["certificate"]["observed"]
    required = {"spell_damage", "spell_damage_doubled", "healing_does_damage",
                "spell_healing_doubled", "hand_keywords"}
    if set(observed) != required or any(observed[k] is not False for k in required-
                                      {"spell_damage", "hand_keywords"}):
        raise ValueError("Missing/unsupported observed effects; no default substitution")
    if observed["spell_damage"] != 0 or len(observed["hand_keywords"]) != len(state.self_hand):
        raise ValueError("Unsupported observed damage/keywords")
    if len({identity(a) for a in row["legal_actions"]}) != len(row["legal_actions"]):
        raise ValueError("Duplicate fixture actions")
    if {identity(a) for a in row["legal_actions"]} != {identity(a) for a in legal_menu(state)}:
        raise ValueError("Incomplete/illegal fixture menu")
    text_lookup = {t["id"]:t for t in row["certificate"]["texts"]}
    cards = [m.card for p in [state.self_player,state.opponent] for m in p.board]+list(state.self_hand)
    for card in cards:
        text = text_lookup.get(card.card_id)
        if text is None:
            raise ValueError("Missing explicit text")
        raw = raw_catalog.get(card.card_id)
        if raw is None:
            if not card.card_id.startswith("TL2_"):
                raise ValueError("Unreviewed non-synthetic identity")
            if card.card_id != "TL2_DAMAGE_ALL" and (text["text"] != "" or
                    text["type"] != "MINION" or text["mechanics"] or card.card_type != "MINION"):
                raise ValueError("Synthetic vanilla declaration inconsistent")
            if card.card_id == "TL2_DAMAGE_ALL" and (text["text"] != "Deal $2 damage to all minions." or
                    card.card_type != "SPELL" or card.current_cost != 1 or text["mechanics"]):
                raise ValueError("Synthetic spell declaration inconsistent")
            continue
        base = encoder.catalog.get(card.card_id)
        if asdict(card) != asdict(base):
            raise ValueError("Known base metadata replaced")
        if (text["text"] != raw.get("text", "") or text["type"] != raw["type"]
                or sorted(text.get("mechanics", [])) != sorted(raw.get("mechanics", []))):
            raise ValueError("Known text/type/mechanics replaced")
        if (base.attack,base.health,base.cost,base.card_type,base.card_class) != (
                raw.get("attack"),raw.get("health"),raw.get("cost"),raw["type"],raw["cardClass"]):
            raise ValueError("Pinned base stats mismatch")
    if row["certificate"]["observed"]["spell_damage"] != state.self_player.spell_damage:
        raise ValueError("Spell Damage observation inconsistent")
    if row["certificate"]["goal"] != "AMBIGUOUS" and state.opponent.hero_divine_shield is None:
        raise ValueError("Unknown shield cannot own certificate")
    first = arithmetic_gold(row)
    second, consequences = outcome_gold(row, legal_menu)
    stored = {identity(a) for a in row["correct_actions"]}
    if set(first) != set(second) or stored != {identity(row["legal_actions"][i]) for i in first}:
        raise ValueError("Independent gold disagreement")
    return {"gold":first,"scope":row["certificate"]["goal"],"consequences":consequences}
