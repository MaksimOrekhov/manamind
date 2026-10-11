"""Mechanical diagnostics over the forecasts of one menu (CONSEQUENCE-DIAGNOSTICS-1): flags with evidence, or no conclusion.

Two flags, both about *direct, exact* consequences only:

``SIDE_MISDIRECTION``  the action aims a source at the opponent's side while another legal use of the very same source
                       (same card, same hand slot / board slot) aimed at SELF's side has strictly better exact direct
                       consequences in every compared dimension.
``SELF_HARM``          a non-attack action whose exact direct consequences are no better than nothing in every compared
                       dimension and worse in at least one, with no visible way for it to pay off.

A flag is never a verdict on a move: it says "these exact effects are mechanically dominated", not "this play is a
mistake". Whenever a forecast is unsupported, not fully understood, only bounded, or something visible could turn the
effect into a gain (a Deathrattle, a board trigger, an aura, a Quest, a board text the grammar cannot read), the
function returns no conclusion and counts the reason. Nothing here depends on a card ID.

The compared dimensions come from the forecast's exact-changes-only after-state: damage to the opponent hero (Health and
Armor), Attack plus Health on the opponent's board, Attack plus Health on SELF's board, SELF hero Health plus Armor, and
the number of keywords (Divine Shield, Taunt, ...) on each board. Mana, cards and weapon durability are costs, not
effects, and are deliberately not compared.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from manamind.outcome.compare import side_metrics
from manamind.domain.game_state import GameState
from manamind.outcome.grammar import board_profile
from manamind.outcome.model import Forecast, Status
from manamind.outcome.texts import TextSource

SIDE_MISDIRECTION = "SIDE_MISDIRECTION"
SELF_HARM = "SELF_HARM"
FLAGS = (SIDE_MISDIRECTION, SELF_HARM)

# Visible things that can turn a harmful-looking effect into a gain; either flag abstains on them.
_REACTION_TAGS = {
    "DEATHRATTLE": "DEATHRATTLE_POSSIBLE",
    "BOARD_TRIGGER": "BOARD_TRIGGER",
    "AURA_ON_SUMMON": "AURA_ON_SUMMON",
    "OWN_SECRET_OR_QUEST": "OWN_SECRET_OR_QUEST",
}
# SELF_HARM additionally needs the board's texts to be readable and rule-free: a harm claim is only as good as the
# text of the objects around it.
_HARM_ONLY_TAGS = {
    "BOARD_STATIC_TEXT": "BOARD_STATIC_TEXT",
    "BOARD_TEXT_MISSING": "BOARD_TEXT_MISSING",
    "OWN_TEXT_MISSING": "OWN_TEXT_MISSING",
}
# Reactions that the forecaster attaches to the *source* being played rather than to its target. When the compared
# alternative carries exactly the same ones (same tag, same object) they cannot separate the two uses, so SIDE_MISDIRECTION
# does not abstain on them; anything target-specific (a Deathrattle of the minion hit, an aura on summon) always blocks.
_SYMMETRIC_TAGS = frozenset({"OWN_SECRET_OR_QUEST", "BOARD_TRIGGER"})
_SKIP_TYPES = ("ATTACK", "END_TURN")


@dataclass(frozen=True, slots=True)
class Flag:
    index: int           # menu index of the flagged action
    flag: str
    against: int | None  # menu index of the dominating alternative (SIDE_MISDIRECTION)


@dataclass(slots=True)
class MenuDiagnosis:
    flags: list[Flag] = field(default_factory=list)
    blocked: Counter = field(default_factory=Counter)        # (flag, reason): would have flagged, evidence incomplete
    insufficient: Counter = field(default_factory=Counter)   # flag: candidates whose forecast cannot support a claim
    blocked_at: list = field(default_factory=list)           # (menu index, flag, reason), for per-rank accounting
    insufficient_at: list = field(default_factory=list)      # (menu index, flag)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.flags:
            out["flags"] = [[f.index, f.flag, f.against] for f in self.flags]
        if self.blocked:
            out["blocked"] = {f"{flag}:{reason}": count for (flag, reason), count in sorted(self.blocked.items())}
        if self.insufficient:
            out["insufficient"] = dict(sorted(self.insufficient.items()))
        return out


def direct_vector(state: GameState, forecast: Forecast) -> tuple[int, ...] | None:
    """Exact direct consequences, higher = better for SELF; ``None`` when there is no after-state."""
    after = forecast._candidate
    if after is None:
        return None
    ob, oa = side_metrics(state.opponent), side_metrics(after.opponent)
    sb, sa = side_metrics(state.self_player), side_metrics(after.self_player)

    def stats(metrics: dict[str, int]) -> int:
        return metrics["board_attack"] + metrics["board_health"]

    return (
        (ob["hero_health"] + ob["armor"]) - (oa["hero_health"] + oa["armor"]),
        stats(ob) - stats(oa),
        stats(sa) - stats(sb),
        (sa["hero_health"] + sa["armor"]) - (sb["hero_health"] + sb["armor"]),
        ob["keywords"] - oa["keywords"],
        sa["keywords"] - sb["keywords"],
    )


def dominates(better: tuple[int, ...], worse: tuple[int, ...]) -> bool:
    return all(a >= b for a, b in zip(better, worse)) and any(a > b for a, b in zip(better, worse))


def _usable(forecast: Forecast) -> str | None:
    """Why this forecast cannot support a claim (``None`` = it can)."""
    if forecast.status is Status.UNSUPPORTED or forecast._candidate is None:
        return "UNSUPPORTED"
    if not forecast.own_effect_known:
        return "OWN_EFFECT_UNKNOWN"
    if forecast.bounded_changes:
        return "BOUNDED_VALUES"
    return None


def _blockers(forecast: Forecast, flag: str, ignore: frozenset[str]) -> list[str]:
    tags = {u.tag for u in forecast.unknowns}
    reasons = [name for tag, name in _REACTION_TAGS.items() if tag in tags]
    if flag == SELF_HARM:
        reasons += [name for tag, name in _HARM_ONLY_TAGS.items() if tag in tags]
    return sorted(set(reasons) - ignore)


def _symmetric_signature(forecast: Forecast) -> frozenset:
    return frozenset((u.tag, u.subject.label() if u.subject is not None else None)
                     for u in forecast.unknowns if u.tag in _SYMMETRIC_TAGS)


def _group(action: dict[str, Any]) -> tuple:
    return (action.get("type"), action.get("card_id") or action.get("source_card_id"), action.get("hand_index"),
            action.get("source_board_position"))


def _aura_on_board(state: GameState, texts: TextSource | None) -> bool:
    """A friendly minion whose rules reach other minions (an aura, a Spell Damage source, an adjacency buff)."""
    for entity in state.self_player.board:
        mechanics = set(entity.card.mechanics)
        entry = texts.get(entity.card.card_id) if texts is not None else None
        if entry is not None:
            mechanics |= set(entry.mechanics)
        if mechanics & {"AURA", "ADJACENT_BUFF", "SPELLPOWER"}:
            return True
    return False


def _delayed_damage_trigger(state: GameState, texts: TextSource | None) -> bool:
    """A friendly minion with a trigger that deals damage later (an end-of-turn ping, a 'fire' on attack).

    Such a trigger can finish what a harmless-looking hit started, so an action that only leaves the opponent's
    minion slightly changed (more Attack, a little less Health) is not called harm while one is on the board.
    """
    if texts is None:
        return False
    for entity in state.self_player.board:
        entry = texts.get(entity.card.card_id)
        if entry is not None and any("damage" in sentence.lower() for sentence in board_profile(entry.text)[0]):
            return True
    return False


def diagnose_menu(state: GameState, items: Sequence[tuple[int, dict[str, Any], Forecast]], *,
                  texts: TextSource | None = None, ignore: frozenset[str] = frozenset()) -> MenuDiagnosis:
    """``items`` are ``(menu index, action, forecast)`` for every action of one decision (any order).

    ``ignore`` names abstention reasons to disregard. It exists for sensitivity analysis only (how many flags each
    abstention rule costs); LIVE and the shadow journal always use the default, which ignores nothing.
    """
    result = MenuDiagnosis()
    vectors = {index: direct_vector(state, forecast) for index, _, forecast in items}
    by_group: dict[tuple, list[int]] = {}
    for index, action, _ in items:
        if action.get("type") not in _SKIP_TYPES:
            by_group.setdefault(_group(action), []).append(index)
    auras = _aura_on_board(state, texts) and "AURA_ON_BOARD" not in ignore
    pingers = _delayed_damage_trigger(state, texts) and "DELAYED_DAMAGE_TRIGGER" not in ignore
    actions = {index: action for index, action, _ in items}
    forecasts = {index: forecast for index, _, forecast in items}

    for index, action, forecast in items:
        if action.get("type") in _SKIP_TYPES:
            continue
        # ---- SELF_HARM -------------------------------------------------------------------------------------
        why = _usable(forecast)
        vector = vectors[index]
        if why is not None or vector is None:
            result.insufficient[SELF_HARM] += 1
            result.insufficient_at.append((index, SELF_HARM))
        elif all(v <= 0 for v in vector) and any(v < 0 for v in vector):
            blockers = _blockers(forecast, SELF_HARM, ignore) + (["AURA_ON_BOARD"] if auras else [])
            if pingers and (vector[0] < 0 or vector[1] < 0):          # the opponent comes out ahead: a ping could finish it
                blockers.append("DELAYED_DAMAGE_TRIGGER")
            if blockers:
                for reason in blockers:
                    result.blocked[(SELF_HARM, reason)] += 1
                    result.blocked_at.append((index, SELF_HARM, reason))
            else:
                result.flags.append(Flag(index, SELF_HARM, None))
        # ---- SIDE_MISDIRECTION -----------------------------------------------------------------------------
        if action.get("target_side") != "OPPONENT":
            continue
        alternatives = [j for j in by_group[_group(action)]
                        if j != index and actions[j].get("target_side") == "SELF"]
        if not alternatives:
            continue
        if why is not None or vector is None:
            result.insufficient[SIDE_MISDIRECTION] += 1
            result.insufficient_at.append((index, SIDE_MISDIRECTION))
            continue
        usable_alternatives = [j for j in alternatives if _usable(forecasts[j]) is None and vectors[j] is not None]
        if not usable_alternatives:
            result.insufficient[SIDE_MISDIRECTION] += 1
            result.insufficient_at.append((index, SIDE_MISDIRECTION))
            continue
        dominating = [j for j in usable_alternatives if dominates(vectors[j], vector)]
        if not dominating:
            continue                       # a comparison was possible and found no dominance: not an abstention
        dominator = forecasts[dominating[0]]
        same = _symmetric_signature(forecast) == _symmetric_signature(dominator)
        mine = _blockers(forecast, SIDE_MISDIRECTION, ignore)
        theirs = _blockers(dominator, SIDE_MISDIRECTION, ignore)
        if same:
            mine = [r for r in mine if r not in {_REACTION_TAGS[t] for t in _SYMMETRIC_TAGS}]
            theirs = [r for r in theirs if r not in {_REACTION_TAGS[t] for t in _SYMMETRIC_TAGS}]
        blockers = mine + [f"ALTERNATIVE_{r}" for r in theirs]
        if blockers:
            for reason in sorted(set(blockers)):
                result.blocked[(SIDE_MISDIRECTION, reason)] += 1
                result.blocked_at.append((index, SIDE_MISDIRECTION, reason))
        else:
            result.flags.append(Flag(index, SIDE_MISDIRECTION, min(dominating)))
    return result
