"""Pinned train/validation attack census and offline local-fact audit; no model loading."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.outcome import TextSource  # noqa: E402
from manamind.training.combat_reality import extract_attack, legacy_reasons  # noqa: E402
from manamind.training.numeric_combat import combat_features  # noqa: E402
from manamind.training.tactical_learning import real_parts  # noqa: E402

CORPUS = ROOT / "data/processed_policy_real/real_policy_retrain_1"
METADATA = ROOT / "data/processed_numeric_combat_ablation_1/dataset/metadata.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
REVIEWED = ROOT / "data/outcome/reviewed_texts.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def count_result(counter, result):
    counter["attacks"] += 1
    levels = {v["knownness"] for v in result["properties"].values()}
    if "OBSERVED" in levels: counter["with_observed_relations"] += 1
    if "CONDITIONAL" in levels or "VERIFIED_LOCAL" in levels: counter["with_exchange_values"] += 1
    if "VERIFIED_LOCAL" in levels: counter["with_verified_local_exchange"] += 1
    for level in ("OBSERVED", "CONDITIONAL", "VERIFIED_LOCAL", "UNKNOWN"):
        counter[level + "_properties"] += sum(v["knownness"] == level for v in result["properties"].values())


def successor_comparison(row, following, result):
    """Observed endpoints, never targets fed to the extractor; ambiguous identity is refused."""
    a = row["legal_actions"][row["chosen_action_index"]]
    checks, skipped = [], Counter()
    for label, side, key in (("source", "self_player", "source_card_id"),
                              ("target", "opponent", "target_card_id")):
        old = [m for m in row["state"][side]["board"] if m["card"]["card_id"] == a.get(key)]
        new = [m for m in following["state"][side]["board"] if m["card"]["card_id"] == a.get(key)]
        if len(old) != 1 or len(new) > 1:
            skipped["AMBIGUOUS_IDENTITY"] += 1
            continue
        if old[0]["reborn"]:
            skipped["REBORN_IDENTITY"] += 1
            continue
        props = result["properties"]
        death = props.get(label + "_body_dies", {})
        if death.get("value") is not None:
            # Absence/presence is an endpoint proxy, not proof of the DEATH event itself.
            checks.append({"property": label + "_body_dies", "proxy": "body_absent_next_decision",
                           "expected": death["value"], "observed": not new,
                           "knownness": death["knownness"]})
        if not new:
            skipped["BODY_ABSENT_NO_HEALTH_OR_SHIELD"] += 1
            continue
        if death.get("value") is False:
            health = props.get(label + "_health_after_packet", {})
            if health.get("value") is not None:
                checks.append({"property": label + "_health_after_packet", "proxy": "endpoint_health",
                               "expected": health["value"], "observed": new[0]["current_health"],
                               "knownness": health["knownness"]})
        shield = props.get(label + "_shield_removed", {})
        if shield.get("value") is not None and type(new[0].get("divine_shield")) is bool:
            checks.append({"property": label + "_shield_removed", "proxy": "endpoint_shield",
                           "expected": old[0]["divine_shield"] and not shield["value"],
                           "observed": new[0]["divine_shield"], "knownness": shield["knownness"]})
    return checks, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data/processed_combat_reality_1")
    args = parser.parse_args()
    if args.out.exists(): raise ValueError("Fresh output directory required")
    manifest = json.loads((CORPUS / "retrain_manifest.json").read_text(encoding="utf-8"))
    split = manifest["split"]
    inputs = [CORPUS / "retrain_manifest.json", METADATA, CATALOG, REVIEWED,
              ROOT / "src/manamind/training/combat_reality.py",
              ROOT / "src/manamind/training/numeric_combat.py",
              Path(__file__).resolve(),
              *[CORPUS / f"{g}.jsonl" for part in ("train", "validation") for g in split["game_ids"][part]]]
    hashes_before = {str(p): sha(p) for p in inputs}
    groups = real_parts(CORPUS, split)  # The test match files are not read.
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    # Existing Outcome text source, including reviewed tokens and printed Reborn stats.
    # This supplements offline diagnostics only, never the model catalog or vocabulary.
    texts = TextSource.from_files(CATALOG, REVIEWED)
    totals, classes, games, old_reasons, new_reasons, statuses = {}, {}, [], {}, {}, {}
    properties, observations, private, audit, contexts = {}, {}, [], [], {}
    strata_seen = set()
    for part, rows in groups.items():
        total, by_class, by_game = Counter(), defaultdict(Counter), defaultdict(Counter)
        old, old_mm, new, status, property_counts = Counter(), Counter(), Counter(), Counter(), Counter()
        context_counts = Counter()
        ordered = sorted(rows, key=lambda r: (r["game_id"], int(r["decision_id"].rsplit(":", 1)[1])))
        following = {r["decision_id"]: n for r, n in zip(ordered, ordered[1:])
                     if r["game_id"] == n["game_id"]
                     and int(n["decision_id"].rsplit(":", 1)[1]) == int(r["decision_id"].rsplit(":", 1)[1]) + 1
                     and r["state"]["turn_number"] == n["state"]["turn_number"]
                     and r["state"]["active_player"] == n["state"]["active_player"] == "SELF"}
        obs, obs_skip, obs_by_prop = Counter(), Counter(), defaultdict(Counter)
        for row in rows:
            state = game_state_from_dict(row["state"])
            cls, gid = row["state"]["self_player"]["player_class"], row["game_id"]
            targets = (total, by_class[cls], by_game[gid])
            attacks = [(i, a) for i, a in enumerate(row["legal_actions"]) if a["type"] == "ATTACK"]
            row_mm = row_verified = False
            legacy = combat_features(row, metadata)
            for c in targets:
                c["decisions"] += 1
                c["decisions_with_attacks"] += bool(attacks)
                c["decisions_without_attacks"] += not attacks
                c["legacy_covered_actions"] += int(legacy[:, 1].sum())
            for index, action in attacks:
                result = extract_attack(row, action, texts, state)
                reasons = legacy_reasons(row, action, metadata)
                mm = action.get("source_kind") == action.get("target_kind") == "MINION"
                row_mm |= mm
                row_verified |= any(v["knownness"] == "VERIFIED_LOCAL" for v in result["properties"].values())
                context_counts["source_hero"] += action.get("source_kind") == "HERO"
                context_counts["target_hero"] += action.get("target_kind") == "HERO"
                if mm:
                    context_counts["legacy_has_direct_blocker"] += any(r.startswith("DIRECT:") for r in reasons)
                    context_counts["legacy_has_other_board_blocker"] += any(r.startswith("OTHER_BOARD:") for r in reasons)
                    context_counts["legacy_only_other_board_blockers"] += bool(reasons) and all(r.startswith("OTHER_BOARD:") for r in reasons)
                for c in targets:
                    count_result(c, result)
                    c["minion_to_minion"] += mm
                old.update(reasons)
                if mm: old_mm.update(reasons)
                new.update(result["blockers"])
                status[result["outcome_status"]] += 1
                for name, value in result["properties"].items():
                    property_counts[name + ":" + value["knownness"]] += 1
                record = {"decision_id": row["decision_id"], "action_index": index, "result": result,
                          "legacy_reasons": reasons}
                if index == row["chosen_action_index"]:
                    obs["chosen_attacks"] += 1
                    obs["chosen_minion_to_minion"] += mm
                    if row["decision_id"] in following:
                        obs["adjacent_same_turn"] += 1
                        obs["adjacent_minion_to_minion"] += mm
                        checks, skipped = successor_comparison(row, following[row["decision_id"]], result) if mm else ([], Counter())
                        record["successor_checks"] = checks
                        obs["attacks_with_endpoint_checks"] += bool(checks)
                        obs_skip.update(skipped)
                        for check in checks:
                            verdict = "agreed" if check["expected"] == check["observed"] else "disagreed"
                            obs[check["knownness"] + ":" + verdict] += 1
                            obs_by_prop[check["property"]][check["knownness"] + ":" + verdict] += 1
                private.append(record)
                # A small audit sample chosen by pre-action features, not Policy scores or labels.
                if mm:
                    s = next(m for m in row["state"]["self_player"]["board"] if m["board_position"] == action["source_board_position"])
                    t = next(m for m in row["state"]["opponent"]["board"] if m["board_position"] == action["target_board_position"])
                    flags = {"poisonous": s["poisonous"] or t["poisonous"],
                             "shield": s["divine_shield"] or t["divine_shield"], "immune": s["immune"] or t["immune"],
                             "reborn": s["reborn"] or t["reborn"], "weapon": bool(row["state"]["self_player"]["weapon"] or row["state"]["opponent"]["weapon"]),
                             "secret": bool(row["state"]["opponent"]["secret_count"]),
                             "location": bool(row["state"]["opponent"]["locations"] or row["state"]["self_player"]["locations"]),
                             "deathrattle": "DEATHRATTLE" in set(s["card"]["mechanics"] + t["card"]["mechanics"]),
                             "aura": any("AURA" in m["card"]["mechanics"] for side in ("self_player", "opponent") for m in row["state"][side]["board"]),
                             "verified": any(v["knownness"] == "VERIFIED_LOCAL" for v in result["properties"].values())}
                    context_counts.update(k for k, v in flags.items() if v)
                    wanted = [k for k, v in flags.items() if v and k not in strata_seen]
                    if not strata_seen: wanted.append("ordinary_first")
                    if wanted:
                        strata_seen.update(wanted)
                        audit.append({"strata": wanted, "source": s, "target": t,
                                      "visible_board_texts": [{"id": m["card"]["card_id"], "text": texts.get(m["card"]["card_id"]).text if texts.get(m["card"]["card_id"]) else None}
                                                             for side in ("self_player", "opponent") for m in row["state"][side]["board"]],
                                      "record": record})
            for c in targets:
                c["decisions_with_minion_to_minion"] += row_mm
                c["decisions_with_verified_local_exchange"] += row_verified
        totals[part] = dict(total)
        classes[part] = {key: dict(value) for key, value in sorted(by_class.items())}
        for number, gid in enumerate(sorted(by_game), 1):
            cls = next(r["state"]["self_player"]["player_class"] for r in rows if r["game_id"] == gid)
            games.append({"match": part + f"_{number:02d}", "class": cls, **dict(by_game[gid])})
        old_reasons[part] = {"all_attacks": dict(old.most_common()), "minion_to_minion": dict(old_mm.most_common())}
        new_reasons[part], statuses[part], properties[part] = dict(new.most_common()), dict(status), dict(property_counts)
        observations[part] = {"totals": dict(obs), "skipped_endpoints": dict(obs_skip),
                              "by_property": {key: dict(value) for key, value in obs_by_prop.items()}}
        contexts[part] = dict(context_counts)
    hashes_after = {str(p): sha(p) for p in inputs}
    if hashes_before != hashes_after: raise ValueError("Inputs mutated")
    args.out.mkdir(parents=True)
    summary = {"schema": "combat_reality_audit/1", "totals": totals, "classes": classes, "matches": games,
               "legacy_reasons_nonexclusive": old_reasons, "new_blockers_nonexclusive": new_reasons,
               "outcome_status": statuses, "properties": properties, "observations": observations,
               "audit_strata": sorted(strata_seen), "input_files_unchanged": True, "model_loads": 0, "fits": 0,
               "corpus_manifest_sha256": sha(CORPUS / "retrain_manifest.json"), "metadata_sha256": sha(METADATA),
               "catalog_sha256": sha(CATALOG), "input_seal_sha256": hashlib.sha256(json.dumps(hashes_before, sort_keys=True).encode()).hexdigest()}
    summary["reviewed_texts_sha256"] = sha(REVIEWED)
    summary["visible_context_counts"] = contexts
    write(args.out / "summary.json", summary)
    write(args.out / "private_records.json", private)
    write(args.out / "private_manual_sample.json", audit)
    write(args.out / "private_input_hashes.json", hashes_before)
    print(json.dumps({"totals": totals, "observations": observations, "audit_strata": sorted(strata_seen)}, indent=2))


if __name__ == "__main__":
    main()
