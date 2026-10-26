"""Size the Card IR problem on real-match cards with the new metadata (read-only, aggregates and public card names).

Screens in ``manamind.card_metadata.text_features`` are heuristics over text and tags; they measure what is visible in
a record, not what the game does. The candidate list is a deterministic stratified proposal, not a locked protocol.

    python -I reports/card_metadata_2/card_ir_readiness.py --data-root E:/ManaMind/data \
        --output reports/card_metadata_2/card_ir_readiness.json --candidates reports/card_metadata_2/card_ir_pilot_candidates.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from manamind.card_metadata import CardMetadata  # noqa: E402
from manamind.card_metadata.coverage import TextStatus, share, text_status  # noqa: E402
from manamind.card_metadata.text_features import families, special_cases  # noqa: E402
from manamind.outcome.grammar import parse_text  # noqa: E402

from corpus_loader import collect, load_json, weighted  # noqa: E402

OLD_COLLECTIBLE = ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
STANDARD_CATALOG = ROOT / "data/cards/standard_current_enUS.json"
PILOT_TYPES = {"MINION", "SPELL", "WEAPON", "LOCATION"}
PER_STRATUM = 12


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.candidates):
        if path.exists():
            raise SystemExit(f"{path} exists; refusing to overwrite")

    matches, _, _ = collect(args.data_root)
    ids_all = sorted(matches)
    freq = weighted(matches, ids_all)
    total = sum(freq.values())
    new = CardMetadata.load()
    standard = {c["id"] for c in load_json(STANDARD_CATALOG)["cards"]}
    collectible = {c["id"] for c in load_json(OLD_COLLECTIBLE)}
    known_before = standard | collectible

    def record(card_id):
        return new.get(card_id)

    status = {i: text_status(record(i), parse_text) for i in freq}
    unknown_before = {i for i in freq if i not in known_before}
    out: dict = {"appearances": total, "unique_ids": len(freq), "previously_unknown_unique_ids": len(unknown_before),
                 "previously_unknown_appearances": sum(freq[i] for i in unknown_before),
                 "previously_unknown_share": share(sum(freq[i] for i in unknown_before), total)}

    # 1. frequent cards: text availability before and after
    ranked = [i for i, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))]
    topk = {}
    for k in (25, 50, 100, 195, 327, 459, len(ranked)):
        ids = ranked[:k]
        apps = sum(freq[i] for i in ids)
        topk[str(k)] = {
            "share_of_all_appearances": share(apps, total),
            "text_record_before": share(sum(freq[i] for i in ids if i in known_before), apps),
            "text_record_after": share(sum(freq[i] for i in ids if record(i) is not None), apps),
            "grammar_complete_after": share(sum(freq[i] for i in ids if status[i] in (TextStatus.TEXT_PARSED, TextStatus.EMPTY_TEXT_VANILLA)), apps),
        }
    out["frequent_cards"] = topk

    # 2. families among previously unknown IDs
    def family_table(ids):
        unique, weighted_counts = Counter(), Counter()
        for i in ids:
            for fam in families(record(i)):
                unique[fam] += 1
                weighted_counts[fam] += freq[i]
        return [{"family": f, "unique_ids": unique[f], "appearances": weighted_counts[f],
                 "share_of_group_appearances": share(weighted_counts[f], sum(freq[i] for i in ids))}
                for f, _ in sorted(weighted_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:30]]

    out["previously_unknown_families"] = family_table(sorted(unknown_before))
    by_status: Counter = Counter()
    for i in unknown_before:
        by_status[status[i].value] += freq[i]
    out["previously_unknown_by_text_status"] = {"appearances": dict(sorted(by_status.items())),
                                                "shares": {k: share(v, sum(by_status.values())) for k, v in sorted(by_status.items())}}
    kind_unique, kind_apps = Counter(), Counter()
    for i in unknown_before:
        key = (record(i).get("type"), bool(record(i).get("collectible")))
        kind_unique[key] += 1
        kind_apps[key] += freq[i]
    out["previously_unknown_by_type_and_collectibility"] = [
        {"type": t, "collectible": c, "unique_ids": kind_unique[(t, c)], "appearances": n}
        for (t, c), n in sorted(kind_apps.items(), key=lambda kv: (-kv[1], str(kv[0])))]

    # 3. special cases (text alone is not enough)
    cases = {i: special_cases(record(i)) for i in freq}
    case_counts, case_unique = Counter(), Counter()
    for i, found in cases.items():
        for case in found:
            case_counts[case] += freq[i]
            case_unique[case] += 1
    any_case = sum(freq[i] for i, found in cases.items() if found)
    out["special_cases"] = {
        "appearances_by_case": {k: case_counts[k] for k in sorted(case_counts)},
        "share_by_case": {k: share(case_counts[k], total) for k in sorted(case_counts)},
        "unique_ids_by_case": {k: case_unique[k] for k in sorted(case_unique)},
        "appearances_with_any_case": any_case, "share_with_any_case": share(any_case, total),
        "unique_ids_with_any_case": sum(1 for found in cases.values() if found),
        "no_screened_case_but_text_unparsed": share(sum(
            freq[i] for i, found in cases.items()
            if not found and status[i] in (TextStatus.TEXT_UNPARSED_OPAQUE, TextStatus.TEXT_UNPARSED_TRIGGER)), total),
        "share_with_any_case_among_zone": {},
    }
    for zone in ("hand", "self_board", "opp_board"):
        zone_freq: Counter = Counter()
        for g in ids_all:
            for (z, card_id), n in matches[g]["zones"].items():
                if z == zone:
                    zone_freq[card_id] += n
        zone_total = sum(zone_freq.values())
        out["special_cases"]["share_with_any_case_among_zone"][zone] = share(
            sum(n for i, n in zone_freq.items() if cases[i]), zone_total)

    # 4. pilot candidates: deterministic strata, top by appearances inside each
    def stratum(card_id):
        rec = record(card_id)
        if rec.get("type") not in PILOT_TYPES:
            return None
        st = status[card_id]
        if st is TextStatus.EMPTY_TEXT_VANILLA:
            return None
        if st is TextStatus.TEXT_PARSED:
            return "S5_control_grammar_parses"
        if card_id in known_before:
            return "S3_known_before_trigger_text" if st is TextStatus.TEXT_UNPARSED_TRIGGER else "S4_known_before_one_shot_text"
        return "S1_new_collectible" if rec.get("collectible") else "S2_new_to_source_noncollectible_token"
    strata: dict[str, list[str]] = {}
    for card_id in ranked:
        name = stratum(card_id)
        if name:
            strata.setdefault(name, []).append(card_id)
    candidates = []
    for name in sorted(strata):
        for card_id in strata[name][:PER_STRATUM]:
            rec = record(card_id)
            candidates.append({
                "stratum": name, "id": card_id, "name": rec.get("name"), "set": rec.get("set"), "type": rec.get("type"),
                "cost": rec.get("cost"), "appearances": freq[card_id], "text_status": status[card_id].value,
                "tags": sorted(f for f in families(rec) if f.startswith("tag:")), "special_cases": sorted(cases[card_id]),
            })
    out["pilot_candidates"] = {
        "per_stratum": PER_STRATUM, "strata_sizes": {k: len(v) for k, v in sorted(strata.items())},
        "candidates": len(candidates), "appearance_share": share(sum(c["appearances"] for c in candidates), total),
        "candidates_with_special_case": sum(1 for c in candidates if c["special_cases"]),
        "distinct_verb_families": len({f for c in candidates for f in families(record(c["id"])) if f.startswith("verb:")}),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    args.candidates.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: out[k] for k in ("frequent_cards", "special_cases", "pilot_candidates")}, indent=1, sort_keys=True))
    print(json.dumps(out["previously_unknown_families"][:15], indent=0))
    print(out["previously_unknown_by_text_status"])
    print(out["previously_unknown_by_type_and_collectibility"])


if __name__ == "__main__":
    main()
