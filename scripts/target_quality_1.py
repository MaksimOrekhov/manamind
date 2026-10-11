"""Read-only frozen Policy v2 target diagnostics on pinned DATA-CHECKPOINT-1."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from refresh_real_policy_dataset import canonical_content_identity, dataset_identity  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.research.target_quality import (  # noqa: E402
    case_id, disagreement, sibling_key, summarize, target_key,
)
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402
from manamind.training.real_policy import audit_dataset, encode_example, load_examples  # noqa: E402

DATA = "b964e121d6ddb0c11be4014b1549d1a5c861cf57002bfd8975edd53b3be233c1"
CONTENT = "78c21cbd0a2c0c69cdaee77bd07525b086294dba781674a6c47a9a65d354e9c9"
CHECKPOINT = "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"
CATALOG = "c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_cards(state):
    for side in ("self_player", "opponent"):
        player = state[side]
        for item in (*player["board"], *player["locations"]):
            yield item["card"]["card_id"]
        if player["weapon"]:
            yield player["weapon"]["card_id"]
        for card in player["active_effects"]:
            yield card["card_id"]


def representation_gaps(state, records):
    # Coverage indicators; no causal attribution or assurance from an absent flag.
    result = []
    if any(c not in records for c in public_cards(state)):
        result.append("public_card_text_missing")
    if state["opponent"]["secret_count"]:
        result.append("opponent_secret_or_quest")
    if state["self_player"]["secret_count"]:
        result.append("self_secret_or_quest_identity_omitted")
    if state["opponent"]["hero_divine_shield"] is None:
        result.append("opponent_hero_shield_unknown")
    if state["self_player"]["healing_bonus"] is None:
        result.append("healing_bonus_unknown")
    return result


def public_summary(state):
    """Only details needed to review targets; no full-hand/dataset duplication."""
    result = {}
    for side in ("self_player", "opponent"):
        player = state[side]
        result[side] = {k: player[k] for k in ("hero_health", "hero_max_health", "armor",
                       "hero_attack", "hero_divine_shield", "secret_count", "spell_damage", "healing_bonus")}
        result[side]["board"] = [{**{k: v for k, v in m.items() if k != "card"},
            "card_id": m["card"]["card_id"], "mechanics": m["card"]["mechanics"]} for m in player["board"]]
        result[side]["locations"] = [{k: v for k, v in m.items() if k != "card"} |
            {"card_id": m["card"]["card_id"]} for m in player["locations"]]
        result[side]["weapon"] = player["weapon"]
    return result


def match_bootstrap(rows, orders):
    grouped = defaultdict(list)
    for row in rows:
        a = row["legal_actions"]
        grouped[row["game_id"]].append((
            int(orders[row["decision_id"]][0] == row["chosen_action_index"]),
            int(disagreement(a[orders[row["decision_id"]][0]], a[row["chosen_action_index"]]) == "target_only")))
    values = [(len(v), sum(x[0] for x in v), sum(x[1] for x in v)) for _, v in sorted(grouped.items())]
    rng = random.Random(20261011)
    exact, targets = [], []
    for _ in range(2000):
        sample = [rng.choice(values) for _ in values]
        n = sum(v[0] for v in sample)
        exact.append(sum(v[1] for v in sample) / n)
        targets.append(sum(v[2] for v in sample) / n)
    return {"seed": 20261011, "resamples": 2000, "unit": "whole_game_id",
            "exact_top1_95_percentile": [sorted(exact)[i] for i in (49, 1949)],
            "target_only_rate_95_percentile": [sorted(targets)[i] for i in (49, 1949)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Refusing to overwrite results")
    catalog = ROOT / "data/cards/standard_current_enUS.json"
    frozen = args.data_root / "processed_policy_ml2a/seed42_v2/policy.pt"
    corpus = args.data_root / "processed_data_checkpoint_1_20261010/canonical"
    if sha(catalog) != CATALOG or sha(frozen) != CHECKPOINT:
        raise ValueError("Pinned catalog/checkpoint mismatch")
    rows = load_examples(corpus)
    if dataset_identity(rows) != DATA or canonical_content_identity(corpus) != CONTENT:
        raise ValueError("Pinned corpus mismatch")
    audit = audit_dataset(corpus, CardCatalog.from_json(catalog))
    if (audit["labeled_matches"], audit["decisions_labeled"]) != (53, 2010):
        raise ValueError("Corpus count mismatch")
    inventory = json.loads((args.data_root / "processed_data_checkpoint_1_20261010/raw_inventory.json").read_text(encoding="utf-8"))
    development = {item["game_id"] for item in inventory if item["mtime"].startswith("2026-10-10")}
    if len(development & {r["game_id"] for r in rows}) != 16:
        raise ValueError("Development group mismatch")
    records = {r["id"]: r for r in json.loads(catalog.read_text(encoding="utf-8"))["cards"]}
    torch.manual_seed(0)
    torch.set_num_threads(1)
    model, encoder, payload = load_policy_checkpoint(frozen, device="cpu")
    if getattr(model, "representation_version", None) != 2:
        raise ValueError("Expected Policy v2")
    orders, cases, gaps, source_inventory = {}, [], Counter(), defaultdict(Counter)
    attack_review, attack_screen = [], Counter()
    groups, by_type, by_predicted, by_attack_source = (defaultdict(list) for _ in range(4))
    collisions, ties, identity_mismatch = 0, 0, 0
    attacks, chosen_sources = Counter(), Counter()
    training_parts = payload["experiment"]["split"]["game_ids"]
    with torch.inference_mode():
        for row in rows:
            inputs = encode_example(row, encoder, representation=2)
            logits = model(*inputs)
            if logits.shape != (len(row["legal_actions"]),) or not torch.isfinite(logits).all():
                raise ValueError("Invalid logits")
            order = torch.argsort(logits, descending=True, stable=True).tolist()
            orders[row["decision_id"]] = order
            actions = row["legal_actions"]
            predicted, chosen = actions[order[0]], actions[row["chosen_action_index"]]
            classification = disagreement(predicted, chosen)
            if chosen["type"] == "ATTACK":
                chosen_sources[chosen["source_kind"]] += 1
                by_attack_source[chosen["source_kind"]].append(row)
            if predicted["type"] == "ATTACK":
                attacks[(predicted["source_kind"], classification)] += 1
                siblings = [a for a in actions if sibling_key(a) == sibling_key(predicted)]
                attack_screen["policy_attack"] += 1
                attack_screen["multi_target"] += len({target_key(a) for a in siblings}) > 1
                enemy = row["state"]["opponent"]
                faces = [a for a in siblings if a.get("target_kind") == "HERO" and a.get("target_side") == "OPPONENT"]
                lethal = [a for a in faces if type(a.get("source_attack")) is int
                          and a["source_attack"] >= enemy["hero_health"] + enemy["armor"] > 0]
                hp = predicted.get("source_health")
                if predicted["source_kind"] == "HERO" and type(hp) is int:
                    hp += row["state"]["self_player"]["armor"]
                bad = (predicted.get("target_kind") == "MINION" and type(hp) is int
                       and predicted["source_attack"] < predicted["target_health"]
                       and predicted["target_attack"] >= hp)
                favorable = [a for a in siblings if a.get("target_kind") == "MINION" and type(hp) is int
                             and a["source_attack"] >= a["target_health"] and a["target_attack"] < hp]
                flags = []
                if lethal and predicted not in lethal:
                    flags.append("single_attack_face_lethal_threshold_missed")
                if bad and favorable:
                    flags.append("source_dies_target_survives_with_kill_survive_alternative")
                attack_screen.update(flags)
                if flags:
                    attack_review.append({"case_id": case_id(row), "flags": flags,
                        "prediction": predicted, "alternatives": lethal + favorable,
                        "player": chosen, "public_state": public_summary(row["state"]),
                        "scope": "ARITHMETIC_ONLY_NOT_COMBAT_RESOLUTION_OR_TARGET_DOMINANCE"})
            group = "development" if row["game_id"] in development else "older"
            groups[group].append(row)
            by_type[chosen["type"]].append(row)
            by_predicted[predicted["type"]].append(row)
            if len(order) > 1 and logits[order[0]] == logits[order[1]]:
                ties += 1
            # Exact action-dependent representation (features, card IDs, links).
            if classification == "target_only":
                p, c = order[0], row["chosen_action_index"]
                collisions += all(torch.equal(t[p], t[c]) for t in inputs[3:])
            if (classification == "different_source" and predicted["type"] == chosen["type"]
                    and predicted.get("source_card_id") == chosen.get("source_card_id")):
                identity_mismatch += 1
            target_groups = defaultdict(list)
            for i, a in enumerate(actions):
                target_groups[sibling_key(a)].append(i)
            for indices in target_groups.values():
                if len({target_key(actions[i]) for i in indices}) > 1:
                    a = actions[indices[0]]
                    cid = a.get("source_card_id") or a.get("card_id")
                    source_inventory[(a["type"], cid)]["decision_source_slot_groups"] += 1
                    source_inventory[(a["type"], cid)]["variants"] += len(indices)
            if classification == "target_only":
                missing = representation_gaps(row["state"], records)
                gaps.update(missing)
                cases.append({"case_id": case_id(row), "group": group,
                              "match_alias": hashlib.sha256(("TARGET-QUALITY-1:" + row["game_id"]).encode()).hexdigest()[:12],
                              "turn": row["state"]["turn_number"], "public_state": public_summary(row["state"]),
                              "prediction": predicted, "player": chosen,
                              "top3": [actions[i] for i in order[:3]],
                              "player_rank": order.index(row["chosen_action_index"]) + 1,
                              "player_target_rank_given_source_slot": [i for i in order if sibling_key(actions[i]) == sibling_key(chosen)].index(row["chosen_action_index"]) + 1,
                              "gaps": missing})
    result = {"schema": "manamind.target_quality/1", "inputs": {"base_commit": "0fe53dceee83898641c390f430f15c89e3d26766", "dataset": DATA, "content": CONTENT,
              "checkpoint": CHECKPOINT, "catalog": CATALOG}, "all": summarize(rows, orders),
              "by_player_type": {k: summarize(v, orders) for k, v in sorted(by_type.items())},
              "by_policy_type": {k: summarize(v, orders) for k, v in sorted(by_predicted.items())},
              "by_group": {k: {"matches": len({r["game_id"] for r in v}), **summarize(v, orders)} for k, v in sorted(groups.items())},
              "checkpoint_overlap": {k: len(set(ids) & {r["game_id"] for r in rows}) for k, ids in training_parts.items()},
              "match_bootstrap": {k: match_bootstrap(v, orders) for k, v in sorted(groups.items())} | {"all": match_bootstrap(rows, orders)},
              "attack_player_source_kind": dict(sorted(chosen_sources.items())),
              "by_attack_player_source_kind": {k: summarize(v, orders) for k, v in sorted(by_attack_source.items())},
              "attack_arithmetic_screen": dict(sorted(attack_screen.items())),
              "attack_arithmetic_cases": sorted(attack_review, key=lambda c: c["case_id"]),
              "attack_policy_source_kind_and_disagreement": [{"source_kind": k[0], "disagreement": k[1], "decisions": n} for k, n in sorted(attacks.items())],
              "exact_input_collisions_target_only": collisions, "top_logit_ties": ties,
              "same_card_id_different_source": identity_mismatch,
              "target_only_gaps": dict(sorted(gaps.items())),
              "multi_target_sources": [{"type": k[0], "card_id": k[1], "name": records.get(k[1], {}).get("name"),
                    "text": records.get(k[1], {}).get("text"), **dict(v)} for k, v in sorted(source_inventory.items())],
              "target_only_cases": sorted(cases, key=lambda c: c["case_id"])}
    if sha(frozen) != CHECKPOINT or sha(catalog) != CATALOG or canonical_content_identity(corpus) != CONTENT:
        raise ValueError("Inputs changed during diagnostics")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"decisions": len(rows), "exact": result["all"]["top1"]["exact"], "target_only": len(cases)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
