"""Re-measure card-metadata coverage on the permitted real-match corpus (baseline: FUTURE-ARCHITECTURE-RESEARCH-1).

Read-only. Run from the repository root; ``--data-root`` points at the ignored ``data/`` directory (it lives only in the
main checkout). Protected ``fresh_holdout`` matches are excluded by ID from file names *before* any game file is opened.
Only aggregates are written: no game IDs, player names or log lines. Writes a new JSON file (never overwrites).

    python -I reports/card_metadata_2/measure_coverage.py --data-root E:/ManaMind/data --output reports/card_metadata_2/coverage.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from manamind.card_metadata import CardMetadata, quality_flags  # noqa: E402
from manamind.card_metadata.compare import classify_text_change  # noqa: E402
from manamind.card_metadata.coverage import (  # noqa: E402
    EFFECT_ZONES, TextStatus, missing_fields, share, status_counts, text_status,
)
from manamind.outcome.grammar import parse_text  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_loader import by_zone, client_builds, collect, load_json, weighted  # noqa: E402

OLD_COLLECTIBLE = ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
STANDARD_CATALOG = ROOT / "data/cards/standard_current_enUS.json"
ABILITIES = ROOT / "experiments/manaengine/data/card_abilities.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; refusing to overwrite")

    matches, held, protected_present = collect(args.data_root)
    ids_all = sorted(matches)
    groups = {"ALL": ids_all, "OLDER": [g for g in ids_all if matches[g]["group"] == "OLDER"],
              "NEWER": [g for g in ids_all if matches[g]["group"] == "NEWER"]}

    old_full, new_full = CardMetadata.load("hsjson_253216_enUS"), CardMetadata.load()
    standard = {c["id"]: c for c in load_json(STANDARD_CATALOG)["cards"]}
    collectible = {c["id"]: c for c in load_json(OLD_COLLECTIBLE)}
    abilities = load_json(ABILITIES)["cards"]
    engine_ids = {k for k, v in abilities.items() if v.get("support_state") in ("SUPPORTED", "VERIFIED_VANILLA")}
    sources = {
        "A_old_pinned_collectible": lambda i: standard.get(i) or collectible.get(i),
        "B_old_full_build_253216": old_full.get,
        "C_new_full_build_255130": new_full.get,
    }

    out: dict = {"corpus": {
        "matches": len(ids_all), "protected_fresh_holdout_excluded_by_id": len(held), "protected_files_present_not_opened": protected_present,
        "decisions": sum(len(m["decisions"]) for m in matches.values()),
        "older_matches": len(groups["OLDER"]), "newer_matches": len(groups["NEWER"]),
        "effect_zone_appearances": sum(weighted(matches, ids_all).values()),
        "unique_effect_zone_ids": len(weighted(matches, ids_all)),
        "client_builds_by_group": {
            name: {"+".join(k): v for k, v in sorted(client_builds(args.data_root, groups[name]).items())}
            for name in ("OLDER", "NEWER")},
    }}

    # ---- 1/3/7: overall and per-group resolution by source
    table = {}
    for name, getter in sources.items():
        table[name] = {grp: status_counts(weighted(matches, ids), getter, parse_text, engine_ids) for grp, ids in groups.items()}
    # build-matched view: each match against the data of the client build it was (almost entirely) played on
    matched = {}
    for grp, getter_name in (("OLDER", "B_old_full_build_253216"), ("NEWER", "C_new_full_build_255130")):
        matched[grp] = table[getter_name][grp]
    out["by_source_and_group"] = table
    out["build_matched"] = matched

    # ---- 2: by zone, baseline source vs new source (ALL matches)
    zone_table = {}
    for name in ("A_old_pinned_collectible", "C_new_full_build_255130"):
        zone_table[name] = {}
        for zone in (*EFFECT_ZONES, "self_hero_power", "opp_hero_power", "opp_revealed"):
            freq = by_zone(matches, ids_all, zone)
            zone_table[name][zone] = status_counts(freq, sources[name], parse_text, engine_ids) if freq else {"appearances": 0}
    out["by_zone"] = zone_table

    # ---- 4: by class (SELF zones by SELF class, OPP zones by OPP class)
    classes = {}
    for name in ("A_old_pinned_collectible", "C_new_full_build_255130"):
        per: dict = {}
        for g in ids_all:
            m = matches[g]
            for (zone, card_id), n in m["zones"].items():
                if zone not in EFFECT_ZONES:
                    continue
                key = (f"OPP {m['opp_class']}" if zone.startswith("opp") else f"SELF {m['self_class']}")
                per.setdefault(key, Counter())[card_id] += n
        classes[name] = {k: status_counts(v, sources[name], parse_text, engine_ids) for k, v in sorted(per.items())}
    out["by_class"] = classes

    # ---- decision level (all entities in the effect zones satisfy a level)
    decisions = []
    for g in ids_all:
        decisions += matches[g]["decisions"]
    decision_level = {}
    for name in ("A_old_pinned_collectible", "C_new_full_build_255130"):
        cache = {}

        def st(card_id, name=name):
            if card_id not in cache:
                cache[card_id] = text_status(sources[name](card_id), parse_text)
            return cache[card_id]
        decision_level[name] = {
            "decisions": len(decisions),
            "all_resolved": sum(all(st(c) is not TextStatus.MISSING_ID for c in d) for d in decisions),
            "all_complete_metadata": sum(all(st(c) is not TextStatus.MISSING_ID and not missing_fields(sources[name](c)) for c in d)
                                         for d in decisions),
            "all_parse_complete": sum(all(st(c) in (TextStatus.TEXT_PARSED, TextStatus.EMPTY_TEXT_VANILLA) for c in d) for d in decisions),
            "all_engine_declared": sum(all(c in engine_ids for c in d) for d in decisions),
        }
    out["decision_level"] = decision_level

    # ---- 5/6: what the old source missed and why; what remains with the new source
    freq_all = weighted(matches, ids_all)
    total = sum(freq_all.values())
    reasons: Counter = Counter()
    for card_id, n in freq_all.items():
        if sources["A_old_pinned_collectible"](card_id) is not None:
            continue
        in_b, in_c = old_full.get(card_id) is not None, new_full.get(card_id) is not None
        record = new_full.get(card_id) or {}
        scope = "in_old_full_build_but_not_in_collectible_file" if in_b else ("only_in_new_build" if in_c else "in_no_snapshot")
        reasons[(scope, "collectible" if record.get("collectible") else "non_collectible", record.get("type"), record.get("set") if scope == "only_in_new_build" else "-")] += n
    out["old_gap_reasons"] = [{"scope": k[0], "collectibility": k[1], "type": k[2], "set_if_new": k[3], "appearances": v,
                               "share_of_all": share(v, total)} for k, v in reasons.most_common()]
    out["unresolved_in_new"] = {
        "unique_ids": sum(1 for c in freq_all if new_full.get(c) is None),
        "appearances": sum(n for c, n in freq_all.items() if new_full.get(c) is None),
        "ambiguous_ids_in_corpus": sum(1 for c in freq_all if c in new_full.ambiguous_ids()),
    }
    remaining = defaultdict(list)
    for card_id, n in freq_all.most_common():
        status = text_status(new_full.get(card_id), parse_text)
        record = new_full.get(card_id)
        for kind in (["METADATA_INCOMPLETE"] if missing_fields(record) else []) + (
                ["EMPTY_TEXT_WITH_EFFECT_TAG"] if status is TextStatus.EMPTY_TEXT_WITH_EFFECT_TAG else []):
            remaining[kind].append({"id": card_id, "name": record.get("name"), "type": record.get("type"),
                                            "set": record.get("set"), "appearances": n,
                                            "flags": list(quality_flags(record)), "text_status": status.value,
                                            "mechanics": record.get("mechanics")})
    out["remaining_data_problems_new"] = dict(remaining)

    # ---- text artifacts: how many appearances carry them and what they do to the grammar
    flagged = {c for c in freq_all if new_full.get(c) is not None and
               {"LAYOUT_MARKER_IN_TEXT", "DEBUG_MARKER_IN_TEXT"} & set(quality_flags(new_full.get(c)))}
    raw_counts = status_counts(freq_all, new_full.get, parse_text, engine_ids, strip_artifacts=False)
    clean_counts = status_counts(freq_all, new_full.get, parse_text, engine_ids, strip_artifacts=True)
    out["text_artifacts"] = {
        "unique_ids_with_artifact": len(flagged), "appearances_with_artifact": sum(freq_all[c] for c in flagged),
        "share_of_appearances": share(sum(freq_all[c] for c in flagged), total),
        "parse_complete_share_with_artifacts_left_in": raw_counts["level_share"]["parse_complete"],
        "parse_complete_share_after_stripping": clean_counts["level_share"]["parse_complete"],
    }

    # ---- temporal drift: older matches were played on 253216; does the new text still describe them?
    drift = Counter()
    drift_examples = []
    older_freq = weighted(matches, groups["OLDER"])
    for card_id, n in older_freq.items():
        x, y = old_full.get(card_id), new_full.get(card_id)
        if x is None:
            drift["not_in_client_build_253216_snapshot"] += n
        elif x == y:
            drift["identical"] += n
        else:
            changed = [k for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)]
            if changed == ["text"] and classify_text_change(x.get("text"), y.get("text")) in ("text_artifact_only", "markup_or_whitespace_only"):
                drift["differs_only_by_text_artifact_or_markup"] += n
            else:
                drift["substantive_difference"] += n
                if len(drift_examples) < 20:
                    drift_examples.append({"id": card_id, "fields": changed, "appearances": n})
    older_total = sum(older_freq.values())
    out["temporal_drift_older_matches"] = {"appearances": older_total, **{k: v for k, v in drift.items()},
                                           "shares": {k: share(v, older_total) for k, v in drift.items()},
                                           "substantive_examples": drift_examples}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out["corpus"], indent=1, sort_keys=True))
    for name, groups_out in table.items():
        for grp in ("ALL", "OLDER", "NEWER"):
            print(name, grp, groups_out[grp]["level_share"])


if __name__ == "__main__":
    main()
