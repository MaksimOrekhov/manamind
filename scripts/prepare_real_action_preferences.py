"""Prepare blind real-action comparisons and offline HTML, without training."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402
from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.models.policy_inputs import encode_policy_inputs  # noqa: E402
from manamind.outcome import TextSource, forecast_action  # noqa: E402
from manamind.training.action_preferences import candidates, mechanical_scopes  # noqa: E402
from manamind.training.combat_reality import extract_attack  # noqa: E402
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint  # noqa: E402
from manamind.training.tactical_learning import real_parts  # noqa: E402

CORPUS = ROOT / "data/processed_policy_real/real_policy_retrain_1"
CHECKPOINT = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
CHECKPOINT_SHA = "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"
CATEGORIES = ("kill_survive_contrast", "spell_target", "face_or_trade", "same_target_attackers", "attack_or_end", "identity_suspicion")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data/processed_real_action_preferences_1/final")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    if not 1 <= args.limit <= 50: raise ValueError("Limit must be 1..50")
    if args.out.exists(): raise ValueError("Fresh output directory required")
    manifest_path = CORPUS / "retrain_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = [manifest_path, CHECKPOINT, ROOT / "data/cards/standard_current_enUS.json", ROOT / "data/outcome/reviewed_texts.json",
               Path(__file__).resolve(), ROOT / "scripts/action_preferences.html",
               ROOT / "src/manamind/training/action_preferences.py", ROOT / "src/manamind/training/combat_reality.py",
               *[CORPUS / f"{g}.jsonl" for part in ("train", "validation") for g in manifest["split"]["game_ids"][part]]]
    seals = {str(p): sha(p) for p in sources}
    if sha(CHECKPOINT) != CHECKPOINT_SHA: raise ValueError("Frozen checkpoint changed")
    torch.set_num_threads(1)
    policy, encoder, _ = load_policy_checkpoint(CHECKPOINT, "cpu")
    policy.eval()
    texts = TextSource.from_files(sources[2], sources[3])
    groups = real_parts(CORPUS, manifest["split"])
    rows, all_candidates, diagnostics, facts = {}, [], {}, {}
    for part, batch in groups.items():
        for row in batch:
            did = row["decision_id"]
            rows[did] = (part, row)
            state = game_state_from_dict(row["state"])
            with torch.inference_mode():
                scores = policy(*encode_policy_inputs(state, row["legal_actions"], encoder, representation=2)).tolist()
            diagnostics[did] = {"scores": scores, "chosen_index": row["chosen_action_index"]}
            local = {i: extract_attack(row, a, texts, state) for i, a in enumerate(row["legal_actions"]) if a["type"] == "ATTACK"}
            facts[did] = local
            for candidate in candidates(row, local, scores):
                comparison = {"alternatives": [{"action": row["legal_actions"][i], "combat": local.get(i, {"properties": {}})}
                                               for i in candidate["indices"]]}
                candidate["mechanical_scopes"] = mechanical_scopes(comparison)
                all_candidates.append({"decision": did, "game": row["game_id"], "state_hash": row["provenance"]["state_hash"],
                                       "class": row["state"]["self_player"]["player_class"], **candidate})
    rng = random.Random(42)
    ordered = sorted(all_candidates, key=identity)
    rng.shuffle(ordered)
    queues = {tag: [c for c in ordered if tag in c["tags"]] for tag in CATEGORIES}
    selected, state_seen, game_counts = [], set(), Counter()

    def take(c):
        if c["state_hash"] in state_seen or game_counts[c["game"]] >= 2: return False
        selected.append(c)
        state_seen.add(c["state_hash"])
        game_counts[c["game"]] += 1
        return True

    # Reserve the scarce verified comparisons, respecting the same match/state caps.
    for c in ordered:
        if c["mechanical_scopes"] and len(selected) < min(args.limit, 5): take(c)
    # Rare classes get one real state before the mixed category round-robin.
    for cls in sorted({c["class"] for c in ordered}, key=lambda k: sum(c["class"] == k for c in ordered)):
        if len(selected) < args.limit:
            next((c for c in ordered if c["class"] == cls and take(c)), None)
    while len(selected) < args.limit:
        progress = False
        for tag in CATEGORIES:
            while queues[tag]:
                c = queues[tag].pop(0)
                if take(c):
                    progress = True
                    break
            if len(selected) == args.limit: break
        if not progress: break
    game_names = {g: f"M{i:02d}" for i, g in enumerate(sorted(game_counts), 1)}
    pairs, feedback, private_provenance = [], [], []
    for number, candidate in enumerate(selected, 1):
        part, row = rows[candidate["decision"]]
        indices = candidate["indices"].copy()
        rng.shuffle(indices)  # No systematic A=mechanically better or top Policy action.
        state = game_state_from_dict(row["state"])
        alternatives = []
        for index in indices:
            action = row["legal_actions"][index]
            alternatives.append({"menu_index": index, "action": action,
                                 "combat": facts[row["decision_id"]].get(index, {"properties": {}, "blockers": ["NOT_MINION_ATTACK"]}),
                                 "outcome": forecast_action(state, action, texts).to_dict()})
        pair = {"pair_id": f"P{number:03d}", "game_group": game_names[row["game_id"]], "source_part": part,
                "game_group_sha256": identity(row["game_id"]),
                "state": row["state"], "legal_actions": row["legal_actions"], "alternatives": alternatives}
        pair["mechanical_scopes"] = mechanical_scopes(pair)
        pairs.append(pair)
        scores = diagnostics[row["decision_id"]]["scores"]
        ranks = {i: rank for rank, i in enumerate(sorted(range(len(scores)), key=lambda i: (-scores[i], i)), 1)}
        feedback.append({"pair_id": pair["pair_id"], "pair_sha256": identity(pair),
                         "policy": [{"logit": scores[i], "rank_in_complete_menu": ranks[i]} for i in indices],
                         "player_action": row["legal_actions"][row["chosen_action_index"]],
                         "player_choice_in_pair": "A" if row["chosen_action_index"] == indices[0] else "B" if row["chosen_action_index"] == indices[1] else "OTHER",
                         "selection_tags": candidate["tags"], "warning": "Imitation logit and player selection are not ground truth or action values."})
        private_provenance.append({"pair_id": pair["pair_id"], "game_id": row["game_id"], "decision_id": row["decision_id"],
                                   "state_hash": candidate["state_hash"], "tags": candidate["tags"]})
    # Only visible identities for display; no hidden deck, opponent hand or future metadata.
    visible_ids = set()
    for pair in pairs:
        s = pair["state"]
        visible_ids.update(c["card_id"] for c in s["self_hand"])
        for side in ("self_player", "opponent"):
            p = s[side]
            visible_ids.update(m["card"]["card_id"] for m in [*p["board"], *p["locations"]])
            visible_ids.update(c["card_id"] for c in p["active_effects"])
            visible_ids.update(p[k]["card_id"] for k in ("weapon", "hero_power") if p[k])
    payload = json.loads(sources[2].read_text(encoding="utf-8"))
    catalog = {r["id"]: r for r in payload["cards"]}
    cards = {cid: {"name": catalog.get(cid, {}).get("name", cid), "text": texts.get(cid).text if texts.get(cid) else None}
             for cid in sorted(visible_ids)}
    pack = {"schema": "manamind.action_preference_pack/1", "seed": 42, "pairs": pairs, "cards": cards,
            "notice": "Viewed development train/validation; one pair per state, at most two states per match. No preference labels or fresh control."}
    digest = identity(pack)
    after = {str(p): sha(p) for p in sources}
    if seals != after: raise ValueError("Input mutated")
    args.out.mkdir(parents=True)
    write(args.out / "blind_pack.json", pack)
    write(args.out / "feedback.json", {"schema": "manamind.preference_feedback/1", "pack_sha256": digest,
                                      "checkpoint_sha256": CHECKPOINT_SHA, "pairs": feedback})
    write(args.out / "private_provenance.json", private_provenance)
    write(args.out / "input_hashes.json", seals)
    write(args.out / "blank_annotations.json", {"schema": "manamind.preference_annotations/1", "pack_sha256": digest,
                                               "reviewer": "", "independent_review": False, "annotations": []})
    template = (ROOT / "scripts/action_preferences.html").read_text(encoding="utf-8")
    encoded = json.dumps({"pack": pack, "digest": digest}, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    with (args.out / "review.html").open("x", encoding="utf-8", newline="\n") as f:
        f.write(template.replace("__PACK_JSON__", encoded))
    selected_tags = Counter(tag for c in selected for tag in c["tags"])
    summaries = {"candidate_pairs": len(all_candidates), "candidate_states": len({c["state_hash"] for c in all_candidates}),
                 "candidate_matches": len({c["game"] for c in all_candidates}), "candidate_categories": dict(Counter(t for c in all_candidates for t in c["tags"])),
                 "candidate_mechanical_pairs": sum(bool(c["mechanical_scopes"]) for c in all_candidates),
                 "candidate_mechanical_states": len({c["state_hash"] for c in all_candidates if c["mechanical_scopes"]}),
                 "candidate_mechanical_directional": sum(any(s["relation"] in ("A", "B") for s in c["mechanical_scopes"].values()) for c in all_candidates),
                 "selected_states": len(pairs), "selected_matches": len(game_counts), "selected_categories": dict(selected_tags),
                 "selected_classes": dict(Counter(c["class"] for c in selected)),
                 "selected_parts": dict(Counter(p["source_part"] for p in pairs)),
                 "mechanical_review_eligible": sum(bool(p["mechanical_scopes"]) for p in pairs),
                 "mechanical_directional_eligible": sum(any(s["relation"] in ("A", "B") for s in p["mechanical_scopes"].values()) for p in pairs),
                 "expert_or_insufficient_required": sum(not p["mechanical_scopes"] for p in pairs),
                 "actual_preference_labels": 0, "deck_identity": "UNKNOWN: canonical visible-state rows have no verified deck list",
                 "pair_action_types": dict(Counter('/'.join(sorted(a["action"]["type"] for a in p["alternatives"])) for p in pairs)),
                 "max_states_per_match": max(game_counts.values(), default=0), "unique_states": len(state_seen),
                 "match_multiplicities": dict(Counter(game_counts.values())), "pack_sha256": digest, "checkpoint_sha256": CHECKPOINT_SHA,
                 "manifest_sha256": sha(manifest_path), "input_files_unchanged": True, "fits": 0, "real_test_read": False}
    write(args.out / "summary.json", summaries)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
