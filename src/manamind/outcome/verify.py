"""Check forecasts against what the next observation of a logged game actually shows.

For two consecutive labeled decisions of one SELF turn, the state of the second is the
observation after the action chosen at the first. The forecast is computed from the first state
and its action alone; the second state is read only afterwards, to score the forecast.

Scoring is path based over the fields the forecaster models. A path is *confirmed* when the
forecast moved it and the observation agrees, *contradicted* when the forecast moved it and the
observation disagrees, and *missed* when the observation moved a path the forecast left alone.
Every path has a role (what the action does, or its cost / hand / exhaustion bookkeeping), so local
results stay measurable even when the whole forecast is only ``PARTIAL``.

Entities are matched between states without guessing: the forecaster's own bookkeeping says which
entity became which in the prediction, and the observed states are aligned by card ID with a
minimum-difference assignment, so duplicate card IDs do not create phantom contradictions.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from manamind.domain.game_state import GameState
from manamind.domain.serialization import game_state_from_dict
from manamind.outcome.forecast import forecast_action
from manamind.outcome.model import Forecast, Status, Tier
from manamind.outcome.texts import TextSource
from manamind.outcome.world import ObservedContext

_ENTITY_FIELDS = ("card_id", "current_attack", "current_health", "max_health", "taunt", "divine_shield",
                  "stealth", "frozen", "immune", "rush", "charge", "windfury", "lifesteal", "poisonous",
                  "reborn", "dormant", "can_attack")
_KEYWORD_FIELDS = ("taunt", "divine_shield", "stealth", "rush", "charge", "windfury", "lifesteal", "poisonous",
                   "reborn")


@dataclass(frozen=True, slots=True)
class LoggedDecision:
    game_id: str
    number: int
    decision_id: str
    state: GameState
    action: dict[str, Any]
    legal_actions: tuple[dict[str, Any], ...]


def load_corpus(directory: str | Path) -> dict[str, list[LoggedDecision]]:
    """Read canonical policy JSONL files; decisions of a game are ordered by their decision number."""
    games: dict[str, list[LoggedDecision]] = defaultdict(list)
    for path in sorted(Path(directory).glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            games[row["game_id"]].append(LoggedDecision(
                game_id=row["game_id"], number=int(row["decision_id"].rsplit(":", 1)[1]),
                decision_id=row["decision_id"], state=game_state_from_dict(row["state"]),
                action=row["legal_actions"][row["chosen_action_index"]],
                legal_actions=tuple(row["legal_actions"])))
    return {game: sorted(items, key=lambda item: item.number) for game, items in games.items()}


def successor_pairs(games: dict[str, list[LoggedDecision]]) -> Iterable[tuple[LoggedDecision, LoggedDecision]]:
    """Adjacent labeled decisions of one SELF turn; nothing unlabeled lies between them."""
    for items in games.values():
        for current, following in zip(items, items[1:]):
            same_turn = (current.state.turn_number == following.state.turn_number
                         and current.state.active_player == following.state.active_player == "SELF")
            if following.number == current.number + 1 and same_turn and current.action["type"] != "END_TURN":
                yield current, following


def observe(state: GameState) -> dict[str, Any]:
    """Scalar facts plus the ordered entity lists, in a form that can be compared field by field."""
    out: dict[str, Any] = {}
    for side, player in (("SELF", state.self_player), ("OPPONENT", state.opponent)):
        out[f"{side}.hero.health"] = player.hero_health
        out[f"{side}.hero.armor"] = player.armor
        out[f"{side}.hero.attack"] = player.hero_attack
        out[f"{side}.hero.power_ready"] = player.hero_power_ready
        out[f"{side}.hero.divine_shield"] = player.hero_divine_shield
        out[f"{side}.mana"] = player.available_mana
        out[f"{side}.hand_size"] = player.hand_size
        out[f"{side}.weapon"] = None if player.weapon is None else (player.weapon.card_id,
                                                                      player.weapon.effective_durability)
        out[f"{side}.board"] = [
            {name: (e.card.card_id if name == "card_id" else getattr(e, name)) for name in _ENTITY_FIELDS}
            for e in player.board]
        out[f"{side}.locations"] = [
            {"card_id": p.card.card_id, "current_health": p.current_health, "on_cooldown": p.on_cooldown}
            for p in player.locations]
    out["SELF.hand"] = [{"card_id": card.card_id} for card in state.self_hand]
    return out


def role_of(path: str) -> str:
    """BOOKKEEPING for cost, hand, exhaustion and Location durability paths, otherwise EFFECT."""
    if path.endswith((".mana", ".hand_size", ".hero.power_ready", ".can_attack")) or ".weapon" in path:
        return "BOOKKEEPING"
    if ".locations" in path or (".hand[" in path):
        return "BOOKKEEPING"
    return "EFFECT"


# ----- aligning entities -------------------------------------------------------------------------------


def _distance(a: dict[str, Any], b: dict[str, Any]) -> int:
    return sum(1 for key, value in a.items() if key != "card_id" and b.get(key) != value)


def align_observed(old: list[dict[str, Any]], seen: list[dict[str, Any]]) -> dict[int, int]:
    """Order-preserving matching of two observed entity lists by card ID.

    Maximises the number of matches, then minimises the field differences between matched entities, so that
    of two same-ID entities the one that looks like the original is the one considered the same.
    """
    n, m = len(old), len(seen)
    best = [[(0, 0)] * (m + 1) for _ in range(n + 1)]       # (matches, -cost)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            choice = max(best[i - 1][j], best[i][j - 1])
            if old[i - 1]["card_id"] == seen[j - 1]["card_id"]:
                matches, cost = best[i - 1][j - 1]
                choice = max(choice, (matches + 1, cost - _distance(old[i - 1], seen[j - 1])))
            best[i][j] = choice
    mapping: dict[int, int] = {}
    i, j = n, m
    while i > 0 and j > 0:
        if (old[i - 1]["card_id"] == seen[j - 1]["card_id"]
                and best[i][j] == (best[i - 1][j - 1][0] + 1,
                                   best[i - 1][j - 1][1] - _distance(old[i - 1], seen[j - 1]))):
            mapping[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif best[i][j] == best[i - 1][j]:
            i -= 1
        else:
            j -= 1
    return mapping


def _forecast_mapping(state: GameState, forecast: Forecast) -> dict[str, dict[int, int]]:
    """Pre-action list index -> index in the predicted state, as the forecaster itself tracked it."""
    maps: dict[str, dict[int, int]] = {}
    for side, player in (("SELF", state.self_player), ("OPPONENT", state.opponent)):
        for zone, label, items in (("BOARD", "board", player.board), ("LOCATION", "locations", player.locations)):
            maps[f"{side}.{label}"] = {
                index: forecast._after_index[(side, zone, item.board_position)]
                for index, item in enumerate(items) if (side, zone, item.board_position) in forecast._after_index}
    removed = {c.ref.position for c in forecast.changes if c.ref.zone == "HAND" and c.field == "present"}
    survivors = [index for index in range(len(state.self_hand)) if index not in removed]
    maps["SELF.hand"] = {old: new for new, old in enumerate(survivors)}
    return maps


# ----- scoring -------------------------------------------------------------------------------------------


@dataclass(slots=True)
class PairResult:
    decision_id: str
    action_label: str
    family: str
    status: Status
    tier: Tier
    confirmed: dict[str, Any] = field(default_factory=dict)
    contradicted: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    missed: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    explanations: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    unknown_kinds: tuple[str, ...] = ()
    unknown_tags: tuple[str, ...] = ()
    unknown_details: tuple[str, ...] = ()
    own_effect_known: bool = False
    alters_listed: bool = False
    unsupported_reason: str | None = None

    @property
    def verdict(self) -> str:
        if self.status is Status.UNSUPPORTED:
            return "UNSUPPORTED"
        if self.contradicted:
            return "CONTRADICTED"
        return "INCOMPLETE" if self.missed else "CONFIRMED"

    def claims(self, role: str | None = None) -> tuple[int, int]:
        """(confirmed, contradicted) claim counts, optionally for one role."""
        def keep(path: str) -> bool:
            return role is None or role_of(path) == role
        return (sum(keep(p) for p in self.confirmed), sum(keep(p) for p in self.contradicted))


def family_of(action: dict[str, Any]) -> str:
    kind = action["type"]
    return f"{kind}/{action['card_type']}" if kind == "PLAY_CARD" else kind


def _stale_paths(state: GameState, forecast: Forecast) -> set[str]:
    stale: set[str] = set()
    for change in forecast.changes:
        if change.exact:
            continue
        side = change.ref.side
        if change.ref.zone == "HERO":
            stale.add(f"{side}.hero.{'power_ready' if change.field == 'hero_power_ready' else change.field}")
        elif change.ref.zone == "PLAYER":
            stale.add(f"{side}.mana" if change.field == "available_mana" else f"{side}.{change.field}")
        elif change.ref.zone == "WEAPON":
            stale.add(f"{side}.weapon")
        elif change.ref.zone in ("BOARD", "LOCATION"):
            items = ((state.self_player if side == "SELF" else state.opponent).board if change.ref.zone == "BOARD"
                     else (state.self_player if side == "SELF" else state.opponent).locations)
            label = "board" if change.ref.zone == "BOARD" else "locations"
            for index, item in enumerate(items):
                if item.board_position == change.ref.position:
                    field_name = {"attack": "current_attack", "health": "current_health"}.get(change.field, change.field)
                    stale.add(f"{side}.{label}[{index}:{item.card.card_id}].{field_name}")
    return stale


def _hand_claims(old: list[dict[str, Any]], new: list[dict[str, Any]], seen: list[dict[str, Any]],
                 out: PairResult) -> None:
    """A hand is compared as a multiset: which of two identical copies left is not observable, nor does it matter."""
    before, predicted, observed = (Counter(r["card_id"] for r in rows) for rows in (old, new, seen))
    for card in sorted({*before, *predicted, *observed}):
        expected = predicted[card] - before[card]          # < 0: copies the forecast removes
        actual = observed[card] - before[card]
        label = f"SELF.hand[{card}]"
        if expected < 0:
            (out.confirmed.__setitem__(f"{label}.gone", -expected) if actual == expected
             else out.contradicted.__setitem__(f"{label}.gone", (-expected, max(0, -actual))))
        elif actual != 0:
            out.missed[f"SELF.hand.new[{card}].present" if actual > 0 else f"{label}.gone"] = (0, abs(actual))


def _list_claims(name: str, old: list[dict[str, Any]], new: list[dict[str, Any]], seen: list[dict[str, Any]],
                 to_new: dict[int, int], out: PairResult, skip: set[str]) -> None:
    if name == "SELF.hand":
        _hand_claims(old, new, seen, out)
        return
    to_seen = align_observed(old, seen)
    for index, row in enumerate(old):
        label = f"{name}[{index}:{row['card_id']}]"
        j, k = to_new.get(index), to_seen.get(index)
        if j is None:
            if f"{label}.gone" in skip:
                continue
            if k is None:
                out.confirmed[f"{label}.gone"] = True
            else:
                out.contradicted[f"{label}.gone"] = (True, False)
            continue
        if k is None:
            out.missed[f"{label}.gone"] = (False, True)
            continue
        for field_name, before in row.items():
            path = f"{label}.{field_name}"
            if path in skip:
                continue
            predicted, observed = new[j][field_name], seen[k][field_name]
            if observed is None and before is not None:
                continue                                   # no longer observed: neither right nor wrong
            if predicted != before:
                (out.confirmed.__setitem__(path, predicted) if predicted == observed
                 else out.contradicted.__setitem__(path, (predicted, observed)))
            elif observed != before:
                out.missed[path] = (before, observed)
    fresh_new = [j for j in range(len(new)) if j not in to_new.values()]
    fresh_seen = [k for k in range(len(seen)) if k not in to_seen.values()]
    for j in fresh_new:
        match = next((k for k in fresh_seen if seen[k]["card_id"] == new[j]["card_id"]), None)
        label = f"{name}.new[{new[j]['card_id']}]"
        if match is None:
            out.contradicted[f"{label}.present"] = (True, False)
            continue
        fresh_seen.remove(match)
        for field_name, predicted in new[j].items():
            path = f"{label}.{field_name}"
            (out.confirmed.__setitem__(path, predicted) if predicted == seen[match][field_name]
             else out.contradicted.__setitem__(path, (predicted, seen[match][field_name])))
    for k in fresh_seen:
        out.missed[f"{name}.new[{seen[k]['card_id']}].present"] = (False, True)


def score_pair(current: LoggedDecision, following: LoggedDecision, texts: TextSource,
               context: ObservedContext | None = None,
               gain_associations: "dict[str, GainAssociation] | None" = None) -> PairResult:
    forecast = forecast_action(current.state, current.action, texts, context)
    result = PairResult(current.decision_id, forecast.label, family_of(current.action), forecast.status, forecast.tier,
                        unsupported_reason=forecast.unsupported_reason)
    if forecast._candidate is None:
        return result
    before, predicted, actual = observe(current.state), observe(forecast._candidate), observe(following.state)
    stale = _stale_paths(current.state, forecast)
    maps = _forecast_mapping(current.state, forecast)
    for path in sorted(before):
        old, new, seen = before[path], predicted[path], actual[path]
        if isinstance(old, list):
            _list_claims(path, old, new, seen, maps[path], result, stale)
        elif path in stale or old is None or (seen is None and old is not None):
            continue
        elif new != old:
            (result.confirmed.__setitem__(path, new) if new == seen
             else result.contradicted.__setitem__(path, (new, seen)))
        elif seen != old:
            result.missed[path] = (old, seen)
    result.unknown_kinds = tuple(sorted({unknown.kind.value for unknown in forecast.unknowns}))
    result.unknown_tags = tuple(sorted({unknown.tag for unknown in forecast.unknowns}))
    result.unknown_details = tuple(unknown.detail for unknown in forecast.unknowns)
    result.own_effect_known = forecast.own_effect_known
    result.alters_listed = any(unknown.alters_listed for unknown in forecast.unknowns)
    if result.contradicted or result.missed:
        result.explanations = explain_pair(current, following, forecast, result, gain_associations or {})
    return result


# ----- explaining discrepancies -----------------------------------------------------------------------------
#
# Kinds, strongest first. A discrepancy is only given a cause when the data itself carries the signature of
# that cause; naming a card that *could* have reacted is CONSISTENT_UNCONFIRMED, never a confirmation.
#   CONFIRMED_REACTION   a reaction of another object whose signature is in the two states
#   OBSERVATION_GAP      the discrepancy is exactly a field the state does not carry (and the data shows it)
#   COMPARISON_LIMIT     the two states cannot tell which same-ID entity is which
#   DECLARED_GAP         the forecast listed this as not understood (unparsed / random / missing text)
#   CONSISTENT_UNCONFIRMED  a flagged reaction could produce it; nothing in the data shows it did
#   UNEXPLAINED          nothing above applies

EXPLANATION_KINDS = ("CONFIRMED_REACTION", "OBSERVATION_GAP", "COMPARISON_LIMIT", "DECLARED_GAP",
                     "CONSISTENT_UNCONFIRMED", "UNEXPLAINED")


@dataclass(frozen=True, slots=True)
class GainAssociation:
    """When a card newly appeared in SELF's hand, what SELF had just done, across the whole corpus."""

    appearances: int
    signatures: dict[tuple[str, str | None], int]
    always_with_own_secret_object: bool


def build_gain_associations(pairs: list[tuple[LoggedDecision, LoggedDecision]],
                            texts: TextSource) -> dict[str, GainAssociation]:
    seen: dict[str, Counter] = defaultdict(Counter)
    with_secret: dict[str, list[bool]] = defaultdict(list)
    for current, following in pairs:
        gained = Counter(c.card_id for c in following.state.self_hand) - Counter(
            c.card_id for c in current.state.self_hand)
        action = current.action
        entry = texts.get(action.get("card_id") or "")
        school = entry.spell_school if entry is not None and action.get("card_type") == "SPELL" else None
        for card_id, count in gained.items():
            seen[card_id][(action["type"], school)] += count
            with_secret[card_id].append(current.state.self_player.secret_count > 0)
    return {card: GainAssociation(sum(counter.values()), dict(counter), all(with_secret[card]))
            for card, counter in seen.items()}


def explain_pair(current: LoggedDecision, following: LoggedDecision, forecast: Forecast, result: PairResult,
                 associations: dict[str, GainAssociation]) -> dict[str, tuple[str, str, str]]:
    explanations: dict[str, tuple[str, str, str]] = {}
    before_hand = Counter(c.card_id for c in current.state.self_hand)
    gained = [card for card, count in (Counter(c.card_id for c in following.state.self_hand) - before_hand).items()]
    secret_drop = current.state.opponent.secret_count - following.state.opponent.secret_count
    tags = set(result.unknown_tags)
    countered = _spell_countered(current, secret_drop, result)
    for path in sorted({*result.contradicted, *result.missed}):
        values = result.contradicted.get(path)
        explanations[path] = _explain_path(path, current, following, gained, secret_drop, tags, associations, values,
                                           forecast, countered)
    return explanations


def _spell_countered(current: LoggedDecision, secret_drop: int, result: PairResult) -> bool:
    """A spell was cast, an opponent Secret was consumed, and nothing the spell claims actually happened.

    Every effect the forecast claimed is contradicted by the *unchanged* pre-action value. That is the signature
    of a counter, seen in the probe too (11 of 11 zero-damage area measurements coincide with a consumed Secret).
    """
    if secret_drop <= 0 or current.action["type"] != "PLAY_CARD" or current.action.get("card_type") != "SPELL":
        return False
    effects = {path: pair for path, pair in result.contradicted.items() if role_of(path) == "EFFECT"}
    if not effects or any(role_of(path) == "EFFECT" for path in result.confirmed):
        return False
    before = observe(current.state)
    return all(_unchanged(path, pair[1], before) for path, pair in effects.items())


def _unchanged(path: str, observed: Any, before: dict[str, Any]) -> bool:
    if path.endswith(".gone"):
        return observed is False
    if "[" not in path:
        return before.get(path) == observed
    side, rest = path.split(".", 1)
    name, label = rest.split("[", 1)
    index = int(label.split(":", 1)[0])
    field_name = label.split("].", 1)[1] if "]." in label else ""
    rows = before.get(f"{side}.{name}", [])
    return 0 <= index < len(rows) and rows[index].get(field_name) == observed


def _explain_path(path: str, current: LoggedDecision, following: LoggedDecision, gained: list[str],
                  secret_drop: int, tags: set[str], associations: dict[str, GainAssociation],
                  values: tuple[Any, Any] | None, forecast: Forecast, countered: bool = False) -> tuple[str, str, str]:
    # a card newly in SELF's hand
    if path == "SELF.hand_size" or path.startswith("SELF.hand.new["):
        for card in gained:
            known = associations.get(card)
            if known and known.appearances >= 5 and len(known.signatures) == 1 and known.always_with_own_secret_object:
                (kind, school), count = next(iter(known.signatures.items()))
                return ("OBSERVATION_GAP", "QUEST_REWARD_ASSOCIATION",
                        f"{card} entered SELF's hand {count} of {count} times, always after {kind} of school "
                        f"{school} and always with a SELF Secret/Quest object; progress itself is not observed")
        if "OWN_TEXT_UNPARSED" in tags or "OWN_TEXT_RANDOM" in tags or "OWN_TEXT_MISSING" in tags:
            return ("DECLARED_GAP", "OWN_TEXT", "the action's own text has a clause the forecaster does not model")
    if countered and role_of(path) == "EFFECT":
        return ("CONFIRMED_REACTION", "SECRET_CONSUMED_SPELL_HAD_NO_EFFECT",
                f"opponent secret_count dropped by {secret_drop} and none of the spell's effects happened")
    # the attack was cancelled: a Secret was consumed and the attacker is back in the hand
    if secret_drop > 0 and current.action["type"] == "ATTACK":
        card = current.action.get("source_card_id")
        returned = (Counter(c.card_id for c in following.state.self_hand)[card]
                    > Counter(c.card_id for c in current.state.self_hand)[card])
        if returned:
            return ("CONFIRMED_REACTION", "SECRET_RETURNED_ATTACKER",
                    f"opponent secret_count dropped by {secret_drop} and {card} is back in SELF's hand")
    # a returned Reborn minion
    if path.endswith((".gone", ".reborn", ".current_health", ".current_attack", ".max_health")) and ".board[" in path:
        reborn = _reborn_return(path, current, following)
        if reborn:
            return ("CONFIRMED_REACTION", "REBORN_RETURN", reborn)
    # hand-instance keywords
    if ".board.new[" in path and path.rsplit(".", 1)[-1] in _KEYWORD_FIELDS + ("can_attack",) \
            and "HAND_KEYWORDS_UNOBSERVED" in tags:
        return ("OBSERVATION_GAP", "HAND_INSTANCE_KEYWORDS",
                "the played minion has a keyword its printed card lacks; hand-instance enchantments are not observed")
    # same-ID entities that cannot be told apart
    if ".board[" in path and values is not None and _identity_ambiguous(path, values, current, following):
        return ("COMPARISON_LIMIT", "DUPLICATE_CARD_IDS",
                "several entities of this card ID are on the board and the prediction holds for another one of them")
    if tags & {"OWN_TEXT_UNPARSED", "OWN_TEXT_RANDOM", "OWN_TEXT_MISSING", "OWN_TEXT_KEYWORD"}:
        return ("DECLARED_GAP", "OWN_TEXT", "the action's own text has a clause the forecaster does not model, "
                                            "and the forecast says so")
    links = _links(path, current, secret_drop, forecast)
    if links:
        return ("CONSISTENT_UNCONFIRMED", "+".join(links),
                "a flagged object is specifically tied to this path; the data does not show that it caused it")
    open_classes = sorted(tags & {"BOARD_STATIC_TEXT", "BOARD_TEXT_MISSING", "OWN_SECRET_OR_QUEST", "OPPONENT_SECRET",
                                  "BOARD_TRIGGER", "DEATHRATTLE"})
    return ("UNEXPLAINED", "+".join(open_classes),
            "no object is specifically tied to this path and the data carries no signature; "
            "only generic open classes are listed")


def _links(path: str, current: LoggedDecision, secret_drop: int, forecast: Forecast) -> list[str]:
    """Specific ties between a discrepancy and a flagged unknown (a generic open class is not a tie)."""
    links: list[str] = []
    side = path.split(".", 1)[0]
    entity = _entity_row(path, current.state) if ".board[" in path else None
    for unknown in forecast.unknowns:
        ref = unknown.subject
        if entity is not None and ref is not None and ref.zone == "BOARD" and ref.side == side \
                and ref.position == entity.board_position and "unreadable" not in unknown.detail                 and unknown.tag in {"BOARD_TRIGGER", "BOARD_STATIC_TEXT", "BOARD_TEXT_MISSING", "DEATHRATTLE"}:
            links.append(f"{unknown.tag}@{ref.label()}")
    if any(u.tag == "DEATHRATTLE" for u in forecast.unknowns) and "DEATHRATTLE" not in "+".join(links):
        links.append("DEATHRATTLE")                     # a Deathrattle minion died in this action
    if secret_drop > 0:
        links.append("OPPONENT_SECRET_FIRED")           # observed: the opponent's Secret count dropped
    if any(u.tag == "BOARD_TRIGGER" and "unreadable" not in u.detail for u in forecast.unknowns):
        links.append("BOARD_TRIGGER")
    return links


def _entity_row(path: str, state: GameState):
    """The pre-action board entity a ``SIDE.board[i:CARD]`` path refers to, or None."""
    side = path.split(".", 1)[0]
    try:
        index = int(path.split("[", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return None
    board = (state.self_player if side == "SELF" else state.opponent).board
    return board[index] if 0 <= index < len(board) else None


def _reborn_return(path: str, current: LoggedDecision, following: LoggedDecision) -> str | None:
    entity = _entity_row(path, current.state)
    if entity is None or not entity.reborn:
        return None
    side = path.split(".", 1)[0]
    board = (following.state.self_player if side == "SELF" else following.state.opponent).board
    returned = [e for e in board if e.card.card_id == entity.card.card_id and not e.reborn and e.current_health == 1]
    if not returned:
        return None
    return (f"{entity.card.card_id} had Reborn before and is on the board afterwards without Reborn "
            f"with 1 Health")


def _identity_ambiguous(path: str, values: tuple[Any, Any], current: LoggedDecision,
                        following: LoggedDecision) -> bool:
    """True when the predicted value is present on another same-ID entity, so identity is the only mismatch."""
    entity = _entity_row(path, current.state)
    if entity is None:
        return False
    side = path.split(".", 1)[0]
    before = (current.state.self_player if side == "SELF" else current.state.opponent).board
    after = (following.state.self_player if side == "SELF" else following.state.opponent).board
    card = entity.card.card_id
    if sum(e.card.card_id == card for e in before) < 2:
        return False
    if path.endswith(".gone"):
        return sum(e.card.card_id == card for e in after) < sum(e.card.card_id == card for e in before)
    name = path.rsplit(".", 1)[-1]
    return any(getattr(e, name, object()) == values[0] for e in after if e.card.card_id == card)


# ----- aggregation --------------------------------------------------------------------------------------------


def summarise_results(results: list[PairResult]) -> dict[str, Any]:
    def counts(items: list[PairResult]) -> dict[str, int]:
        return dict(Counter(item.verdict for item in items))

    def claims(items: list[PairResult], role: str | None = None) -> dict[str, int]:
        pairs = [item.claims(role) for item in items]
        return {"confirmed": sum(p[0] for p in pairs), "contradicted": sum(p[1] for p in pairs)}

    by_status = {status.value: [r for r in results if r.status is status] for status in Status}
    by_tier = {tier.value: [r for r in results if r.tier is tier] for tier in Tier}
    by_family: dict[str, dict[str, Any]] = {}
    for family in sorted({r.family for r in results}):
        rows = [r for r in results if r.family == family]
        by_family[family] = {
            "n": len(rows),
            "status": dict(Counter(r.status.value for r in rows)),
            "tier": dict(Counter(r.tier.value for r in rows)),
            "verdict": counts(rows),
            "claims": claims(rows),
            "effect_claims": claims(rows, "EFFECT"),
            "bookkeeping_claims": claims(rows, "BOOKKEEPING"),
        }
    contradictions = Counter()
    for result in results:
        for path in result.contradicted:
            contradictions[result.explanations.get(path, ("UNEXPLAINED", "", ""))[0]] += 1
    missed = Counter()
    for result in results:
        for path in result.missed:
            missed[result.explanations.get(path, ("UNEXPLAINED", "", ""))[0]] += 1
    return {
        "pairs": len(results),
        "status": {name: len(rows) for name, rows in by_status.items()},
        "tiers": {name: {"n": len(rows), "verdict": counts(rows), "claims": claims(rows),
                         "effect_claims": claims(rows, "EFFECT"), "bookkeeping_claims": claims(rows, "BOOKKEEPING")}
                  for name, rows in by_tier.items()},
        "verdict_by_status": {name: counts(rows) for name, rows in by_status.items()},
        "claims": claims(results),
        "missed_paths": sum(len(r.missed) for r in results),
        "contradictions_by_explanation": dict(contradictions),
        "missed_by_explanation": dict(missed),
        "by_family": by_family,
        "unknown_kinds": dict(Counter(kind for r in results for kind in r.unknown_kinds)),
        "unsupported_reasons": dict(Counter(r.unsupported_reason for r in by_status["UNSUPPORTED"])),
    }
