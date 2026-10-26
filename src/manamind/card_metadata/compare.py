"""Deterministic comparison of two pinned snapshots.

A difference between snapshots is not a balance change by itself. Every changed record is therefore assigned to
exactly one cause group, and the groups are reported separately: source scope (the old collectible-only file lacked
the record), expansion set, non-gameplay metadata, and changed gameplay fields outside the expansion.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable, Mapping

from .snapshot import CardMetadata, plain_text, quality_flags, strip_text_artifacts

# Fields that define behaviour or availability. Changes only outside this set (art, flavor, earning text) are
# metadata noise for rules and effects.
GAMEPLAY_FIELDS = (
    "type", "cardClass", "classes", "cost", "attack", "health", "durability", "armor", "race", "races", "spellSchool",
    "mechanics", "referencedTags", "spellDamage", "overload", "runeCost", "multiClassGroup", "text", "rarity", "set",
    "collectible", "elite", "countAsCopyOfDbfId", "heroPowerDbfId", "questReward", "puzzleType",
)
PLAYABLE_TYPES = frozenset({"MINION", "SPELL", "WEAPON", "LOCATION", "HERO", "HERO_POWER"})
# Game modes whose records exist in client data but never appear in a Ranked Standard match.
OTHER_MODE_SETS = frozenset({"LETTUCE", "BATTLEGROUNDS", "TB", "HERO_SKINS"})
OTHER_MODE_TYPES = frozenset({
    "LETTUCE_ABILITY", "BATTLEGROUND_TRINKET", "BATTLEGROUND_SPELL", "BATTLEGROUND_ANOMALY", "BATTLEGROUND_QUEST_REWARD",
    "BATTLEGROUND_HERO_BUDDY", "PET", "GAME_MODE_BUTTON", "MOVE_MINION_HOVER_TARGET",
})
EXPANSION_SET = "BE"

_DIGITS = re.compile(r"\d+")


def _normalise_text(text: Any) -> str:
    return plain_text(text).lower()


def classify_text_change(old: Any, new: Any) -> str:
    """Why two text strings differ: injected text artifact, markup/whitespace only, numbers only, or wording."""
    if (old or "") == (new or ""):
        return "identical"
    if strip_text_artifacts(old) == strip_text_artifacts(new):
        return "text_artifact_only"
    a, b = _normalise_text(old), _normalise_text(new)
    if a == b:
        return "markup_or_whitespace_only"
    if not a or not b:
        return "text_added_or_removed"
    if _DIGITS.sub("#", a) == _DIGITS.sub("#", b):
        return "numbers_only"
    return "wording"


def _is_playable_standard_like(record: Mapping[str, Any]) -> bool:
    """A record a Hearthstone (not Battlegrounds/Mercenaries/Tavern Brawl/skin) match can plausibly contain."""
    if record.get("type") not in PLAYABLE_TYPES:
        return False
    return record.get("set") not in OTHER_MODE_SETS


def _by_id(store: CardMetadata) -> dict[str, Mapping[str, Any]]:
    ambiguous = store.ambiguous_ids()
    return {record["id"]: record for record in store.records() if record["id"] not in ambiguous}


def _top(counter: Counter, n: int = 12) -> dict[str, int]:
    return dict(counter.most_common(n))


def compare_snapshots(
    old: CardMetadata,
    new: CardMetadata,
    old_collectible_ids: Iterable[str],
    *,
    example_limit: int = 12,
) -> dict[str, Any]:
    """Compare ``old`` with ``new``. ``old_collectible_ids`` is the ID set of the old collectible-only source file."""
    old_collectible = set(old_collectible_ids)
    a, b = _by_id(old), _by_id(new)
    only_new = sorted(set(b) - set(a))
    only_old = sorted(set(a) - set(b))
    common = sorted(set(a) & set(b))
    result: dict[str, Any] = {
        "old_snapshot": old.snapshot_id, "new_snapshot": new.snapshot_id,
        "old_collectible_source_ids": len(old_collectible),
        "ids": {"old_full": len(a), "new_full": len(b), "common": len(common), "added": len(only_new),
                "removed": len(only_old), "ambiguous_old": len(old.ambiguous_ids()), "ambiguous_new": len(new.ambiguous_ids())},
    }

    # --- ids visible to the old model-side source vs to the full old build vs genuinely new
    pre_existing_noncollectible = [i for i in common if i not in old_collectible and not a[i].get("collectible")]
    result["scope_effect"] = {
        "ids_in_old_collectible_file": len(old_collectible),
        "ids_in_old_full_build_only": len(a) - len(old_collectible & set(a)),
        "new_full_ids_not_in_old_collectible_file": len(set(b) - old_collectible),
        "of_which_already_in_old_full_build": len(set(b) - old_collectible) - len(only_new),
        "of_which_new_in_new_build": len(only_new),
        "old_noncollectible_ids_still_present": len(pre_existing_noncollectible),
    }

    def describe_set(ids: list[str], records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        playable = [i for i in ids if _is_playable_standard_like(records[i])]
        return {
            "count": len(ids),
            "collectible": sum(1 for i in ids if records[i].get("collectible")),
            "non_collectible": sum(1 for i in ids if not records[i].get("collectible")),
            "by_set": _top(Counter(records[i].get("set") for i in ids), 15),
            "by_type": _top(Counter(records[i].get("type") for i in ids), 15),
            "in_other_game_modes": sum(1 for i in ids if records[i].get("set") in OTHER_MODE_SETS
                                       or records[i].get("type") in OTHER_MODE_TYPES),
            "enchantments": sum(1 for i in ids if records[i].get("type") == "ENCHANTMENT"),
            "playable_standard_like": len(playable),
            "playable_standard_like_collectible": sum(1 for i in playable if records[i].get("collectible")),
            "playable_standard_like_tokens": sum(1 for i in playable if not records[i].get("collectible")),
            "playable_standard_like_by_type": _top(Counter(records[i].get("type") for i in playable), 10),
            "playable_standard_like_by_set": _top(Counter(records[i].get("set") for i in playable), 15),
        }

    added = describe_set(only_new, b)
    added["expansion_set_ids"] = sum(1 for i in only_new if b[i].get("set") == EXPANSION_SET)
    added["expansion_set_collectible"] = sum(1 for i in only_new if b[i].get("set") == EXPANSION_SET and b[i].get("collectible"))
    added["expansion_set_non_collectible"] = added["expansion_set_ids"] - added["expansion_set_collectible"]
    added["expansion_set_tokens_playable"] = sum(
        1 for i in only_new if b[i].get("set") == EXPANSION_SET and not b[i].get("collectible") and b[i].get("type") in PLAYABLE_TYPES)
    added["expansion_set_by_type"] = _top(Counter(b[i].get("type") for i in only_new if b[i].get("set") == EXPANSION_SET), 10)
    added["examples_playable_noncollectible"] = [
        i for i in only_new if _is_playable_standard_like(b[i]) and not b[i].get("collectible")][:example_limit]
    result["added"] = added
    result["new_set_totals"] = {
        "expansion_set": EXPANSION_SET,
        "old_full": sum(1 for r in a.values() if r.get("set") == EXPANSION_SET),
        "new_full": sum(1 for r in b.values() if r.get("set") == EXPANSION_SET),
        "old_collectible": sum(1 for r in a.values() if r.get("set") == EXPANSION_SET and r.get("collectible")),
        "new_collectible": sum(1 for r in b.values() if r.get("set") == EXPANSION_SET and r.get("collectible")),
        "new_collectible_by_rarity": _top(Counter(r.get("rarity") for r in b.values()
                                                  if r.get("set") == EXPANSION_SET and r.get("collectible"))),
    }
    result["removed"] = {"count": len(only_old), "ids": only_old[:50],
                         "in_old_collectible_file": sum(1 for i in only_old if i in old_collectible)}

    # --- changed records among IDs present in both
    field_changes: Counter = Counter()
    gameplay_changes: Counter = Counter()
    groups: Counter = Counter()
    group_examples: dict[str, list[str]] = {}
    text_kinds: Counter = Counter()
    collectible_flips: list[str] = []
    identity: dict[str, list] = {"dbf_id_changed": [], "name_changed": [], "type_changed": [], "class_changed": []}
    changed_ids = []
    substantive_collectible: list[dict[str, Any]] = []
    noncollectible_playable_changed: list[str] = []
    for card_id in common:
        x, y = a[card_id], b[card_id]
        keys = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
        if not keys:
            continue
        changed_ids.append(card_id)
        for key in keys:
            field_changes[key] += 1
        gameplay = [k for k in keys if k in GAMEPLAY_FIELDS]
        for key in gameplay:
            gameplay_changes[key] += 1
        if "text" in keys:
            text_kinds[classify_text_change(x.get("text"), y.get("text"))] += 1
        if x.get("collectible") != y.get("collectible"):
            collectible_flips.append(card_id)
        if x.get("dbfId") != y.get("dbfId"):
            identity["dbf_id_changed"].append(card_id)
        if x.get("name") != y.get("name"):
            identity["name_changed"].append(card_id)
        if x.get("type") != y.get("type"):
            identity["type_changed"].append(card_id)
        if x.get("cardClass") != y.get("cardClass"):
            identity["class_changed"].append(card_id)
        substantive = [k for k in gameplay if k != "text"]
        if "text" in keys and classify_text_change(x.get("text"), y.get("text")) in ("wording", "numbers_only", "text_added_or_removed"):
            substantive.append("text")
        if y.get("set") == EXPANSION_SET or x.get("set") == EXPANSION_SET:
            group = "expansion_set_record"
        elif not gameplay:
            group = "non_gameplay_metadata_only"
        elif not substantive and "text" in gameplay and classify_text_change(x.get("text"), y.get("text")) == "text_artifact_only":
            group = "text_artifact_only"
        elif not substantive:
            group = "text_markup_or_whitespace_only"
        elif not (x.get("collectible") or y.get("collectible")):
            group = "gameplay_field_change_noncollectible"
        elif x.get("collectible") and card_id not in old_collectible:
            group = "gameplay_field_change_collectible_missing_from_old_source"
        else:
            group = "gameplay_field_change_collectible_other_sets"
        if substantive and (x.get("collectible") or y.get("collectible")):
            substantive_collectible.append({
                "id": card_id, "set": y.get("set"), "name": y.get("name"), "group": group,
                "changes": {k: [plain_text(x.get(k)), plain_text(y.get(k))] if k == "text" else [x.get(k), y.get(k)]
                            for k in substantive},
            })
        if substantive and not (x.get("collectible") or y.get("collectible")) and _is_playable_standard_like(y):
            noncollectible_playable_changed.append(card_id)
        groups[group] += 1
        group_examples.setdefault(group, [])
        if len(group_examples[group]) < example_limit:
            group_examples[group].append(card_id)
    result["changed"] = {
        "records_with_any_difference": len(changed_ids),
        "records_unchanged": len(common) - len(changed_ids),
        "field_change_counts": dict(field_changes.most_common()),
        "gameplay_field_change_counts": dict(gameplay_changes.most_common()),
        "text_change_kinds": dict(text_kinds.most_common()),
        "cause_groups": dict(groups.most_common()),
        "cause_group_examples": group_examples,
        "collectible_flag_flips": len(collectible_flips),
        "collectible_flip_examples": collectible_flips[:example_limit],
        "identity_changes": {k: len(v) for k, v in identity.items()},
        "identity_change_examples": {k: v[:example_limit] for k, v in identity.items()},
        "collectible_substantive_changes": substantive_collectible,
        "noncollectible_playable_standard_like_substantive_changes": len(noncollectible_playable_changed),
        "noncollectible_playable_standard_like_examples": noncollectible_playable_changed[:example_limit],
        "collectible_changed_gameplay_by_set": _top(Counter(
            b[i].get("set") for i in changed_ids if b[i].get("collectible") and any(
                k in GAMEPLAY_FIELDS and k != "text" for k in [k for k in set(a[i]) | set(b[i]) if a[i].get(k) != b[i].get(k)])
        ), 20),
    }

    # --- incomplete or suspicious records among the records that matter for play
    def suspicious(records: Mapping[str, Mapping[str, Any]], only: set[str] | None) -> dict[str, Any]:
        counter: Counter = Counter()
        examples: dict[str, list[str]] = {}
        playable = 0
        for card_id, record in records.items():
            if only is not None and card_id not in only:
                continue
            if not _is_playable_standard_like(record):
                continue
            playable += 1
            for flag in quality_flags(record):
                counter[flag] += 1
                examples.setdefault(flag, [])
                if len(examples[flag]) < example_limit:
                    examples[flag].append(card_id)
        return {"playable_standard_like_records": playable, "flag_counts": dict(counter.most_common()), "flag_examples": examples}

    result["quality_new_added_ids"] = suspicious(b, set(only_new))
    result["quality_new_all"] = suspicious(b, None)
    result["quality_old_all"] = suspicious(a, None)
    name_counts = Counter(r.get("name") for r in b.values() if r.get("collectible") and r.get("set") == EXPANSION_SET)
    result["duplicate_collectible_names_in_expansion"] = {n: c for n, c in name_counts.items() if c > 1}
    return result
