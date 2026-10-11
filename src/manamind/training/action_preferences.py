"""Offline preference preparation/validation. No optimizer or gameplay consumer."""
from __future__ import annotations

from itertools import combinations
from datetime import datetime

from manamind.training.policy_checkpoint import identity

RESULTS = ("A", "B", "EQUIVALENT", "INSUFFICIENT")
CONFIDENCE = ("low", "medium", "high")
ASPECTS = ("strategic", "source_survival", "target_destruction")
BASES = ("expert", "verified_mechanics", "insufficient")


def target_key(a):
    return (a.get("target_side"), a.get("target_kind"), a.get("target_board_position"), a.get("target_card_id"))


def candidates(row, facts, scores):
    """Identify interesting comparisons, not correct answers; never read chosen_action_index."""
    actions = row["legal_actions"]
    found = {}

    def add(i, j, tag):
        key = tuple(sorted((i, j)))
        found.setdefault(key, set()).add(tag)

    attacks = [i for i, a in enumerate(actions) if a["type"] == "ATTACK"]
    for i, j in combinations(attacks, 2):
        a, b = actions[i], actions[j]
        pa, pb = facts[i]["properties"], facts[j]["properties"]
        if (a.get("source_kind") == b.get("source_kind") == "MINION" and
                a.get("target_kind") == b.get("target_kind") == "MINION" and target_key(a) == target_key(b)
                and a.get("source_board_position") != b.get("source_board_position")):
            add(i, j, "same_target_attackers")
            kills = [p.get("target_body_dies", {}).get("value") for p in (pa, pb)]
            deaths = [p.get("source_body_dies", {}).get("value") for p in (pa, pb)]
            if kills == [True, True] and set(deaths) == {True, False}:
                add(i, j, "kill_survive_contrast")
                bad = i if deaths[0] else j
                good = j if deaths[0] else i
                if a.get("source_card_id") != b.get("source_card_id") and scores[bad] > scores[good]:
                    add(i, j, "identity_suspicion")  # A flag for review, not causal ID attribution.
        if (a.get("source_kind"), a.get("source_board_position"), a.get("source_card_id")) == (
                b.get("source_kind"), b.get("source_board_position"), b.get("source_card_id")):
            if {a.get("target_kind"), b.get("target_kind")} == {"HERO", "MINION"}:
                add(i, j, "face_or_trade")
    spells = [i for i, a in enumerate(actions) if a["type"] == "PLAY_CARD" and a.get("card_type") == "SPELL" and a.get("target_kind")]
    for i, j in combinations(spells, 2):
        a, b = actions[i], actions[j]
        if a.get("hand_index") == b.get("hand_index") and target_key(a) != target_key(b) and a["play_position"] == b["play_position"]:
            add(i, j, "spell_target")
    ends = [i for i, a in enumerate(actions) if a["type"] == "END_TURN"]
    for i in attacks:
        for j in ends: add(i, j, "attack_or_end")
    return [{"indices": list(key), "tags": sorted(tags)} for key, tags in sorted(found.items())]


def mechanical_scopes(pair):
    """Proven comparisons in narrow scopes; no claim of the globally best move."""
    a, b = pair["alternatives"]
    aa, bb = a["action"], b["action"]
    if aa.get("type") != "ATTACK" or bb.get("type") != "ATTACK" or target_key(aa) != target_key(bb):
        return {}
    scopes = {}
    for aspect, key, positive in (("source_survival", "source_body_dies", False),
                                  ("target_destruction", "target_body_dies", True)):
        values = [x["combat"]["properties"].get(key, {}) for x in (a, b)]
        if not all(v.get("knownness") == "VERIFIED_LOCAL" and type(v.get("value")) is bool for v in values):
            continue
        va, vb = (v["value"] for v in values)
        relation = "EQUIVALENT" if va == vb else "A" if va == positive else "B"
        scopes[aspect] = {"relation": relation, "property": key,
                          "scope": "original bodies in the local exchange; not full-state or strategic optimality"}
    return scopes


def validate_annotations(pack, payload):
    """Validate manual labels and preserve provenance. Insufficient never becomes a negative."""
    if payload.get("schema") != "manamind.preference_annotations/1" or payload.get("pack_sha256") != identity(pack):
        raise ValueError("Wrong annotation schema or stale pack digest")
    if not isinstance(payload.get("reviewer"), str) or not payload["reviewer"].strip():
        raise ValueError("Reviewer required")
    pairs = {p["pair_id"]: p for p in pack["pairs"]}
    seen, accepted, abstentions, equivalent = set(), [], [], []
    annotations = payload.get("annotations")
    if not isinstance(annotations, list): raise ValueError("Annotation list required")
    for entry in annotations:
        pid = entry.get("pair_id")
        if pid not in pairs or pid in seen: raise ValueError("Unknown or duplicate pair")
        seen.add(pid)
        pair = pairs[pid]
        if entry.get("pair_sha256") != identity(pair): raise ValueError("Pair changed")
        initial = entry.get("initial")
        if not isinstance(initial, dict): raise ValueError("Initial blind annotation required")
        revisions = entry.get("revisions", [])
        if not isinstance(revisions, list): raise ValueError("Revision list required")
        for label in [initial, *revisions]:
            if (label.get("result") not in RESULTS or label.get("confidence") not in CONFIDENCE
                    or label.get("basis") not in BASES or label.get("aspect") not in ASPECTS
                    or not isinstance(label.get("explanation"), str) or not label["explanation"].strip()
                    or not isinstance(label.get("timestamp"), str) or not label["timestamp"]):
                raise ValueError("Incomplete label")
            try:
                when = datetime.fromisoformat(label["timestamp"].replace("Z", "+00:00"))
                if when.tzinfo is None: raise ValueError("Timezone required")
            except ValueError as exc:
                raise ValueError("Invalid label timestamp") from exc
            if label["basis"] == "verified_mechanics":
                scope = mechanical_scopes(pair).get(label["aspect"])
                if scope is None or scope["relation"] != label["result"]:
                    raise ValueError("Unproved mechanical preference or wrong scope")
            if label["result"] == "INSUFFICIENT" and label["basis"] != "insufficient":
                raise ValueError("Abstention needs insufficient basis")
            if label["basis"] == "insufficient" and label["result"] != "INSUFFICIENT":
                raise ValueError("Insufficient basis cannot justify preference")
        if entry.get("revealed", False) and not entry.get("reveal_timestamp"):
            raise ValueError("Reveal provenance required")
        if type(entry.get("revealed", False)) is not bool: raise ValueError("Reveal must be boolean")
        times = [datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00")) for x in [initial, *revisions]]
        if times != sorted(times): raise ValueError("Revisions out of order")
        if entry.get("revealed", False):
            reveal = datetime.fromisoformat(entry["reveal_timestamp"].replace("Z", "+00:00"))
            if reveal.tzinfo is None or times[0] > reveal: raise ValueError("Initial label was not before reveal")
        # Keep the initial assessment as the default future target; revisions are audit only.
        result = {"pair_id": pid, "pair_sha256": identity(pair), "game_group": pair["game_group"],
                  "game_group_sha256": pair["game_group_sha256"],
                  "source_part": pair["source_part"], "reviewer": payload["reviewer"],
                  "label": initial, "revisions": revisions, "revealed": entry.get("revealed", False),
                  "reveal_timestamp": entry.get("reveal_timestamp"), "independent_review": payload.get("independent_review", False)}
        if initial["result"] == "INSUFFICIENT": abstentions.append(result)
        elif initial["result"] == "EQUIVALENT": equivalent.append(result)
        else: accepted.append(result)
    return {"strict_preferences": accepted, "aspect_equivalences": equivalent, "abstentions": abstentions,
            "unlabelled": len(pairs) - len(seen), "ready_for_training": False,
            "reason": "Manual agreement/quality review and a match-level future split remain required"}
