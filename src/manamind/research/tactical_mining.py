"""TACTICAL-DECISION-1: detectors that flag real decisions where frozen Policy v2 *may* be wrong (offline).

A detector never says the player's move is right. It says: given only player-visible facts at the decision
(plus the experimental SELF-only overlay), the Policy Top-1 has a property that independent card-text or
arithmetic rules call questionable. Every hit carries a tier:

* ``PROVEN_LOCAL`` - the direct, visible consequence is adverse or null under written rules; the text names the
  residual caveats;
* ``PROBABLE_STRATEGIC`` - rules favour another move but its value depends on things not modelled (reward value,
  tempo, expiry of a one-turn effect, trade intent);
* ``UNCERTAIN`` - the verdict needs information or a simulation that is not available.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from manamind.research.decision_overlay import ACTIVE, DecisionOverlay
from manamind.research.tactical_context import (
    ENEMY_DAMAGE, GAIN, GAIN_LETHAL, HARM, HERO_POWER_HEALS, LETHAL, NEUTRAL, HealAssessment,
)

PROVEN_LOCAL, PROBABLE_STRATEGIC, UNCERTAIN = "PROVEN_LOCAL", "PROBABLE_STRATEGIC", "UNCERTAIN"
QUEST_SCHOOL = {"TLC_817t": "HOLY", "TLC_817t2": "SHADOW"}  # order of the two quests in the pinned TLC_817 text
RUIN, MEDIVH, ATIESH = "CORE_EX1_197", "TIME_890", "TIME_890t"
_SPELL_TRIGGER = re.compile(r"spell|cast|you play|play a card")
_MARKUP = re.compile(r"<[^>]+>|\[x\]")
_HEAL_TEXT = re.compile(r"restore|heal")
_BLOCKING_FLAGS = ("divine_shield", "poisonous", "reborn", "lifesteal", "windfury", "immune", "dormant", "frozen")


def name_of(records: Mapping[str, Mapping], card_id: str | None) -> str:
    record = records.get(card_id or "")
    return f"{record['name']}[{card_id}]" if record else f"[{card_id}]"


def _board_entity(state: Mapping, side: str, position: int, card_id: str | None) -> Mapping | None:
    player = state["self_player" if side == "SELF" else "opponent"]
    found = [e for e in player["board"] if e["board_position"] == position and e["card"]["card_id"] == card_id]
    return found[0] if len(found) == 1 else None


def brief(records: Mapping[str, Mapping], state: Mapping, action: Mapping) -> str:
    kind = action["type"]
    if kind == "END_TURN":
        return "END_TURN"
    source = name_of(records, action.get("source_card_id") or action.get("card_id"))
    text = f"{kind} {source}"
    if kind == "PLAY_CARD" and action.get("card_cost") is not None:
        text += f" cost{action['card_cost']}"
    if action.get("target_kind"):
        side = "OPP" if action.get("target_side") == "OPPONENT" else "SELF"
        if action["target_kind"] == "HERO":
            player = state["opponent" if side == "OPP" else "self_player"]
            text += f" -> {side} hero hp{player['hero_health']}"
            if player.get("armor"):
                text += f"+{player['armor']}armor"
        else:
            entity = _board_entity(state, action["target_side"], action["target_board_position"],
                                   action.get("target_card_id"))
            stats = f"{entity['current_attack']}/{entity['current_health']}" if entity else "?"
            text += f" -> {side} {name_of(records, action.get('target_card_id'))} {stats}"
    if kind == "ATTACK":
        text = f"ATTACK {source} {action.get('source_attack')}/{action.get('source_health')}" + text[len(f'ATTACK {source}'):]
    return text


def board_digest(records: Mapping[str, Mapping], state: Mapping) -> dict:
    def minions(player):
        return [f"{name_of(records, e['card']['card_id'])} {e['current_attack']}/{e['current_health']}"
                + ("T" if e["taunt"] else "") for e in player["board"]]
    me, foe = state["self_player"], state["opponent"]
    return {"turn": state["turn_number"], "mana": me["available_mana"], "self_hero": [me["hero_health"], me["armor"]],
            "opponent_hero": [foe["hero_health"], foe["armor"]], "self_board": minions(me),
            "opponent_board": minions(foe), "opponent_secrets_or_quests": foe["secret_count"],
            "hand": [f"{name_of(records, c['card_id'])} c{c['current_cost']}" for c in state["self_hand"]]}


def _public_texts(state: Mapping, texts: Mapping[str, str]) -> tuple[list[str], list[str]]:
    unknown, trigger = set(), set()
    for side in ("self_player", "opponent"):
        player = state[side]
        cards = [e["card"] for e in player["board"]] + [loc["card"] for loc in player["locations"]]
        if player["weapon"]:
            cards.append(player["weapon"])
        for card in cards:
            text = texts.get(card["card_id"])
            if text is None or text == "":
                unknown.add(card["card_id"])
            elif _SPELL_TRIGGER.search(text):
                trigger.add(card["card_id"])
    return sorted(unknown), sorted(trigger)


def heal_capable(records: Mapping[str, Mapping], action: Mapping) -> bool:
    """Any action whose pinned text mentions healing (including conditional ones the evaluator does not model)."""
    source = action.get("source_card_id")
    return source in HERO_POWER_HEALS or bool(_HEAL_TEXT.search(((records.get(source) or {}).get("text") or "").lower()))


def _quest_hint(overlay: DecisionOverlay, state: Mapping, action: Mapping) -> int | None:
    """1 when the client marks the hand card as advancing a Quest, 0 when not, None when unalignable."""
    index = action.get("hand_index")
    hand = tuple(card["card_id"] for card in state["self_hand"])
    if index is None or not 0 <= index < len(hand) or hand != overlay.hand_card_ids:
        return None
    return 1 if overlay.hand_contributors[index] == 1 else 0


def quest_completions(state: Mapping, actions: Sequence[Mapping], overlay: DecisionOverlay,
                      records: Mapping[str, Mapping]) -> list[int]:
    """Legal spells whose school matches a Quest one cast short of completion and that the client marks."""
    found = []
    near = {QUEST_SCHOOL[q.card_id] for q in overlay.quests if q.card_id in QUEST_SCHOOL and q.total
            and q.progress == q.total - 1}
    if not near:
        return found
    for index, action in enumerate(actions):
        if action["type"] != "PLAY_CARD" or action.get("card_type") != "SPELL":
            continue
        school = (records.get(action.get("source_card_id")) or {}).get("spellSchool")
        if school in near and _quest_hint(overlay, state, action) == 1:
            found.append(index)
    return found


def bad_trade(state: Mapping, action: Mapping) -> str | None:
    """Plain minion-vs-minion arithmetic: the attacker dies and the target survives; None if not applicable."""
    if action["type"] != "ATTACK" or action.get("source_kind") != "MINION" or action.get("target_kind") != "MINION":
        return None
    source = _board_entity(state, "SELF", action["source_board_position"], action.get("source_card_id"))
    target = _board_entity(state, action["target_side"], action["target_board_position"], action.get("target_card_id"))
    if source is None or target is None:
        return None
    if any(e.get(flag) for e in (source, target) for flag in _BLOCKING_FLAGS):
        return None
    if any(m in e["card"].get("mechanics", []) for e in (source, target)
           for m in ("DEATHRATTLE", "AURA", "TRIGGER_VISUAL", "BATTLECRY_PLUS")):
        return None
    dies = target["current_attack"] >= source["current_health"]
    kills = source["current_attack"] >= target["current_health"]
    return "DIES_WITHOUT_KILL" if dies and not kills else None


def good_trade(state: Mapping, action: Mapping) -> bool:
    if action["type"] != "ATTACK" or action.get("source_kind") != "MINION" or action.get("target_kind") != "MINION":
        return False
    source = _board_entity(state, "SELF", action["source_board_position"], action.get("source_card_id"))
    target = _board_entity(state, action["target_side"], action["target_board_position"], action.get("target_card_id"))
    if source is None or target is None or any(e.get(f) for e in (source, target) for f in _BLOCKING_FLAGS):
        return False
    return source["current_attack"] >= target["current_health"] and target["current_attack"] < source["current_health"]


def detect(state: Mapping, actions: Sequence[Mapping], order: list[int], chosen: int, overlay: DecisionOverlay,
           assessments: Mapping[int, HealAssessment], records: Mapping[str, Mapping],
           texts: Mapping[str, str]) -> list[dict]:
    """Zero or more hits for one decision; each is {class, tier, reason, missing, facts}."""
    hits: list[dict] = []
    top = order[0]
    top_action = actions[top]
    top_assessment = assessments.get(top)

    lethal = [i for i, a in assessments.items() if a.outcome == LETHAL]
    if lethal and top not in lethal:
        secret = any("OPPONENT_SECRET_PRESENT" in assessments[i].caveats for i in lethal)
        hits.append({"class": "HEAL_LETHAL_MISSED", "tier": UNCERTAIN if secret else PROVEN_LOCAL,
                     "reason": "Active heal-to-damage conversion deals at least the enemy hero's health plus armor; "
                               "Top-1 does not use it" + ("; a hidden Secret/Quest could still prevent it" if secret else ""),
                     "missing": "hidden opponent Secrets (a visible count only); hero immunity is not in the state"
                                if secret else "hero immunity/prevention effects are not part of the state",
                     "facts": {"alternatives": list(lethal)}})

    if top_assessment and top_assessment.value in (HARM, NEUTRAL) and top not in lethal:
        better = [i for i, a in assessments.items() if a.sibling_key == top_assessment.sibling_key
                  and _rank(a.value) < _rank(top_assessment.value)]
        if better:
            progress = top_assessment.quest_progress
            hits.append({"class": "HEAL_TARGET_DOMINATED", "tier": PROVEN_LOCAL,
                         "reason": f"Top-1 target outcome is {top_assessment.outcome}; the same {top_action['type']} "
                                   "has a target with a strictly better direct outcome (same cost, same triggers)",
                         "missing": "target-specific triggers not in card text (e.g. when-healed effects) and "
                                    "hidden opponent reactions; Quest progress is identical for all targets"
                                    + ("" if progress is not None else "; Quest hint unalignable"),
                         "facts": {"top1_outcome": top_assessment.outcome, "alternatives": better}})

    if overlay.healing_does_damage == ACTIVE:
        burn = [i for i, a in assessments.items() if a.outcome in (ENEMY_DAMAGE, LETHAL)]
        if (burn and top not in burn and top not in lethal and not (top_assessment and top_assessment.value == HARM)
                and not heal_capable(records, top_action)):
            hits.append({"class": "SANCTUM_FOLLOWUP_MISSED", "tier": PROBABLE_STRATEGIC,
                         "reason": "The one-turn 'next Healing effect deals damage instead' state is active and a "
                                   "supported healing action on an enemy is legal; Top-1 is another action, so the "
                                   "effect would expire unused",
                         "missing": "value of the alternative (tempo, board, lethal elsewhere); whether Purifying "
                                    "Breath style conditional heals are better; expiry is only verified at turn end",
                         "facts": {"alternatives": burn}})

    if top_action.get("source_card_id") == RUIN and top_action["type"] == "PLAY_CARD":
        minions = [e for side in ("self_player", "opponent") for e in state[side]["board"]]
        if not any(e["current_attack"] >= 5 for e in minions):
            hint = _quest_hint(overlay, state, top_action)
            unknown, trigger = _public_texts(state, texts)
            school = (records.get(RUIN) or {}).get("spellSchool")
            completes = hint == 1 and any(QUEST_SCHOOL.get(q.card_id) == school and q.total and q.progress == q.total - 1
                                          for q in overlay.quests)
            quest_effect = "COMPLETES_QUEST" if completes else "ADVANCES_QUEST" if hint == 1 else None
            if hint == 0 and not trigger and not unknown:
                tier, why = PROVEN_LOCAL, "no minion has 5+ Attack, the Quest hint says no progress, no visible spell trigger"
            else:
                tier = UNCERTAIN
                why = ("no minion has 5+ Attack, but "
                       + ("casting it completes a Quest, so Top-1 is not evidence of an error " if completes else
                          "the Quest hint is 1 (it advances a Quest) " if hint == 1 else
                          "the Quest hint is unalignable " if hint is None else "")
                       + ("visible text may react to a spell " if trigger else "")
                       + ("some visible card text is missing from the pinned catalog" if unknown else "")).strip()
            hits.append({"class": "AOE_RUIN_NO_TARGET", "tier": tier, "reason": why,
                         "missing": "effects of tokens absent from the pinned catalog; opponent reactions",
                         "facts": {"quest_hint": hint, "quest_effect": quest_effect, "unknown_text_cards": unknown[:4],
                                   "trigger_cards": trigger[:4]}})

    completions = quest_completions(state, actions, overlay, records)
    if completions and top not in completions:
        hits.append({"class": "QUEST_COMPLETION_MISSED", "tier": PROBABLE_STRATEGIC,
                     "reason": "A legal spell completes a Quest (matching school, client hint 1, progress total-1); "
                               "Top-1 does not",
                     "missing": "the reward cards (Life's Breath / Death's Touch) are not in the pinned catalog, so "
                                "their value against this board is unknown; a hidden Counterspell could negate it",
                     "facts": {"alternatives": completions}})

    flaw = bad_trade(state, top_action)
    if flaw and any(good_trade(state, a) for a in actions):
        hits.append({"class": "ATTACK_BAD_TRADE", "tier": PROBABLE_STRATEGIC,
                     "reason": "Top-1 attacks so the attacker dies and the target survives (plain arithmetic, no "
                               "keywords involved) while another attack kills a target and survives",
                     "missing": "intent such as removing Taunt or enabling lethal; deathrattle/aura text of tokens "
                                "outside the catalog; follow-up attacks",
                     "facts": {}})

    hand_ids = {card["card_id"] for card in state["self_hand"]}
    if top_action.get("source_card_id") == ATIESH and MEDIVH in hand_ids:
        medivh = [a for a in actions if a.get("source_card_id") == MEDIVH]
        atiesh_cost = next((c["current_cost"] for c in state["self_hand"] if c["card_id"] == ATIESH), None)
        if medivh and atiesh_cost:
            hits.append({"class": "FABLED_ORDER", "tier": UNCERTAIN,
                         "reason": "Top-1 plays Atiesh at full cost while Medivh is legal; controlling Medivh makes "
                                   "Atiesh cost 0 (observed from COST tags), but Medivh's battlecry destroys other minions",
                         "missing": "a two-step outcome (needs a simulation): board loss from Medivh vs mana saved",
                         "facts": {"atiesh_cost": atiesh_cost}})
    return hits


def _rank(value: str) -> int:
    return {GAIN_LETHAL: 0, GAIN: 1, NEUTRAL: 2, HARM: 3}.get(value, 9)
