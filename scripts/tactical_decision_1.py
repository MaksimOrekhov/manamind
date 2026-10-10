"""TACTICAL-DECISION-1: context-aware decision pilot on the DATA-CHECKPOINT-1 corpus (offline, no training).

Reads the canonical corpus, the frozen Policy v2 checkpoint and the raw Power.log files without modifying any of
them. It (1) flags real decisions where Policy v2 may be wrong, (2) evaluates a small consequence evaluator that
uses the experimental SELF-only overlay (Ruby Sanctum state, Quests), and (3) compares reranked recommendations
with the unchanged Policy on identical states. Results go to one new anonymized JSON file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import torch

from manamind.cards.catalog import CardCatalog
from manamind.research.decision_overlay import ACTIVE, INACTIVE, collect_overlays
from manamind.research.tactical_context import (
    ENEMY_DAMAGE, ENEMY_HEAL, LETHAL, SELF_DAMAGE, VARIANTS, assess_menu, heal_sources, rerank,
)
from manamind.research.tactical_mining import board_digest, brief, detect
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint
from manamind.training.real_policy import audit_dataset, encode_example, load_examples

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_real_policy_dataset import canonical_content_identity, dataset_identity  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
EXPECTED_DATA = "b964e121d6ddb0c11be4014b1549d1a5c861cf57002bfd8975edd53b3be233c1"
EXPECTED_CONTENT = "78c21cbd0a2c0c69cdaee77bd07525b086294dba781674a6c47a9a65d354e9c9"
EXPECTED_FROZEN = "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"
EXPECTED_CATALOG = "c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34"
# Numbers OBSERVATION-AUDIT-1 reported for the same raw logs; the overlay reimplementation must reproduce them.
AUDIT_REPRODUCTION = {"replayed_matches": 62, "decision_points": 2991, "ACTIVE": 65, "INACTIVE": 2926,
                      "labeled_ACTIVE": 46, "labeled_with_quest": 1353}
KNOWN_EPISODES = {  # situations already reviewed in ML-PILOT-1 (identity of {"state", "legal_actions"})
    "83e9144a6f6061b12f62ff1ef94432c40cb92c8cecb8e79dfefd0ff13c43f277": "full_health_heal",
    "4ace66afa0531174116b60eb257f76d2d3d52f3222a9e577c4b622614fe368e4": "ruin_no_attack_5",
    "abacd59f61e3cd64670f2d48608c3b0d11befdae8d3ea37f5493a3b1e6ce70fd": "atiesh_with_medivh_in_hand",
    "be831feae52a9120d342147a578363343e9dd19f16bb0661606b4946c832c6de": "medivh_against_board",
}
CLASS_PRIORITY = ("HEAL_LETHAL_MISSED", "HEAL_TARGET_DOMINATED", "SANCTUM_FOLLOWUP_MISSED", "QUEST_COMPLETION_MISSED",
                  "ATTACK_BAD_TRADE", "AOE_RUIN_NO_TARGET", "FABLED_ORDER")
QUOTA = {"HEAL_LETHAL_MISSED": 4, "HEAL_TARGET_DOMINATED": 9, "SANCTUM_FOLLOWUP_MISSED": 9,
         "QUEST_COMPLETION_MISSED": 8, "ATTACK_BAD_TRADE": 6, "AOE_RUIN_NO_TARGET": 4, "FABLED_ORDER": 4}
BOOTSTRAP, SEED = 2000, 20261011
MARKUP = re.compile(r"<[^>]+>|\[x\]")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_of(row: dict) -> int:
    return int(row["decision_id"].rsplit(":", 1)[1])


def case_id(row: dict) -> str:
    return identity({"state": row["state"], "legal_actions": row["legal_actions"]})


def load_inputs(data_root: Path):
    frozen = data_root / "processed_policy_ml2a/seed42_v2/policy.pt"
    corpus = data_root / "processed_data_checkpoint_1_20261010/canonical"
    inventory = data_root / "processed_data_checkpoint_1_20261010/raw_inventory.json"
    if sha(CATALOG) != EXPECTED_CATALOG or sha(frozen) != EXPECTED_FROZEN:
        raise ValueError("Pinned catalog or frozen checkpoint identity mismatch")
    rows = load_examples(corpus)
    if dataset_identity(rows) != EXPECTED_DATA or canonical_content_identity(corpus) != EXPECTED_CONTENT:
        raise ValueError("Canonical corpus identity mismatch")
    audit = audit_dataset(corpus, CardCatalog.from_json(CATALOG))
    if audit["decisions_labeled"] != 2010 or audit["labeled_matches"] != 53:
        raise ValueError("Canonical corpus audit mismatch")
    recent = {item["game_id"] for item in json.loads(inventory.read_text(encoding="utf-8"))
              if item["mtime"].startswith("2026-10-10")}
    development = recent & {row["game_id"] for row in rows}
    if len(development) != 16:
        raise ValueError("Expected the 16 development-test matches of ML-PILOT-1")
    records = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    return sorted(rows, key=lambda row: (row["game_id"], index_of(row))), records, development, frozen


def rank_all(rows: list[dict], frozen: Path) -> dict[str, list[int]]:
    torch.manual_seed(0)
    torch.set_num_threads(1)
    model, encoder, _ = load_policy_checkpoint(frozen)
    model.eval()
    orders = {}
    with torch.inference_mode():
        for row in rows:
            logits = model(*encode_example(row, encoder, representation=2))
            if logits.shape != (len(row["legal_actions"]),) or not torch.isfinite(logits).all():
                raise ValueError("Invalid frozen logits")
            orders[row["decision_id"]] = torch.argsort(logits, descending=True, stable=True).tolist()
    return orders


def check_overlays(rows, overlays, info) -> dict:
    states = Counter(o.healing_does_damage for o in overlays.values())
    labeled = [overlays[row["decision_id"]] for row in rows if row["decision_id"] in overlays]
    misaligned = sum(
        tuple(card["card_id"] for card in row["state"]["self_hand"]) != overlays[row["decision_id"]].hand_card_ids
        for row in rows if row["decision_id"] in overlays)
    result = {"replayed_matches": info["replayed_matches"], "decision_points": len(overlays),
              "ACTIVE": states[ACTIVE], "INACTIVE": states[INACTIVE], "UNKNOWN": states["UNKNOWN"],
              "labeled_matched": len(labeled), "labeled_ACTIVE": sum(o.healing_does_damage == ACTIVE for o in labeled),
              "labeled_with_quest": sum(bool(o.quests) for o in labeled),
              "labeled_rows_with_hand_misaligned": misaligned, "rejected": info["rejected"]}
    expected = AUDIT_REPRODUCTION
    result["reproduces_observation_audit_1"] = all(result[key] == value for key, value in expected.items())
    if len(labeled) != len(rows) or not result["reproduces_observation_audit_1"]:
        raise ValueError(f"Overlay does not reproduce OBSERVATION-AUDIT-1 / does not cover the corpus: {result}")
    return result


def tier_counts(hits) -> dict:
    return dict(Counter(hit["tier"] for hit in hits))


def group_of(row: dict, development: set) -> str:
    return "development" if row["game_id"] in development else "older"


def select_cases(pools: dict[str, list[dict]]) -> list[dict]:
    taken, used = [], set()
    for name in CLASS_PRIORITY:
        pool = [item for item in pools[name] if item["decision_id"] not in used]
        pool.sort(key=lambda item: hashlib.sha256(f"{SEED}:{item['decision_id']}".encode()).hexdigest())
        for item in pool[:QUOTA[name]]:
            used.add(item["decision_id"])
            taken.append(item)
    return taken


def mine(rows, orders, overlays, sources, records_by_id, texts, development):
    pools: dict[str, list[dict]] = defaultdict(list)
    per_decision = {}
    for row in rows:
        did = row["decision_id"]
        actions, order = row["legal_actions"], orders[did]
        assessments = assess_menu(row["state"], actions, overlays[did], sources)
        hits = detect(row["state"], actions, order, row["chosen_action_index"], overlays[did], assessments,
                      records_by_id, texts)
        per_decision[did] = assessments
        for hit in hits:
            chosen = row["chosen_action_index"]
            alternatives = hit["facts"].get("alternatives")
            pools[hit["class"]].append({
                "decision_id": did, "group": group_of(row, development), "hit": hit,
                "player_took_alternative": None if alternatives is None else chosen in alternatives,
                "top1_is_player": order[0] == chosen, "player_rank": order.index(chosen) + 1,
                "all_classes": sorted(h["class"] for h in hits), "row": row, "order": order})
    return pools, per_decision


def case_record(item: dict, records_by_id: dict) -> dict:
    row, order, hit = item["row"], item["order"], item["hit"]
    state, actions = row["state"], row["legal_actions"]
    cid = case_id(row)
    return {
        "case_id": cid[:16], "known_episode": KNOWN_EPISODES.get(cid), "group": item["group"],
        "class": hit["class"], "tier": hit["tier"], "also_flagged_as": [c for c in item["all_classes"] if c != hit["class"]],
        "reason": hit["reason"], "missing_information": hit["missing"],
        "available_facts": board_digest(records_by_id, state),
        "policy_v2_top3": [brief(records_by_id, state, actions[i]) for i in order[:3]],
        "player_action": brief(records_by_id, state, actions[row["chosen_action_index"]]),
        "player_action_policy_rank": item["player_rank"], "menu_size": len(actions)}


def sanctum_context(overlay) -> dict:
    return {"healing_does_damage": overlay.healing_does_damage,
            "quests": [[q.card_id, q.progress, q.total] for q in overlay.quests]}


def next_clean(rows: list[dict], position: int) -> dict | None:
    row = rows[position]
    if position + 1 >= len(rows):
        return None
    following = rows[position + 1]
    if (following["game_id"] != row["game_id"] or index_of(following) != index_of(row) + 1
            or following["state"]["turn_number"] != row["state"]["turn_number"]):
        return None
    return following


def target_effective_health(state: dict, action: dict) -> tuple[int, int | None] | None:
    """(health + armor, max health) of the action target; None when it cannot be resolved uniquely."""
    player = state["self_player" if action["target_side"] == "SELF" else "opponent"]
    if action["target_kind"] == "HERO":
        return player["hero_health"] + (player["armor"] or 0), player["hero_max_health"]
    found = [e for e in player["board"] if e["board_position"] == action["target_board_position"]
             and e["card"]["card_id"] == action["target_card_id"]]
    return (found[0]["current_health"], found[0]["max_health"]) if len(found) == 1 else None


def verify_physics(rows, overlays, sources) -> dict:
    """Evaluator claims about the *chosen* supported heal vs the next recorded state (verification only)."""
    tally = Counter()
    contradictions = []
    for position, row in enumerate(rows):
        action = row["legal_actions"][row["chosen_action_index"]]
        assessment = assess_menu(row["state"], [action], overlays[row["decision_id"]], sources).get(0)
        if assessment is None or assessment.value == "UNRESOLVED":
            continue
        following = next_clean(rows, position)
        if following is None:
            tally[(assessment.outcome, "no_clean_next_state")] += 1
            continue
        before = target_effective_health(row["state"], action)
        after = target_effective_health(following["state"], action)
        if before is None:
            tally[(assessment.outcome, "target_unresolved")] += 1
            continue
        if after is None:
            # The target left the board: consistent with damage that covers its health, unobservable otherwise.
            verdict = "confirmed" if assessment.outcome in (ENEMY_DAMAGE, SELF_DAMAGE) and assessment.amount >= before[0] \
                else "unobservable"
        else:
            delta = after[0] - before[0]
            if assessment.outcome in (ENEMY_DAMAGE, SELF_DAMAGE, LETHAL):
                verdict = "confirmed" if delta <= -assessment.amount else "contradicted"
            elif assessment.outcome in (ENEMY_HEAL, "SELF_HEAL"):
                verdict = "confirmed" if assessment.amount <= delta <= (before[1] - before[0] if before[1] else 99) \
                    else "contradicted"
            else:
                verdict = "confirmed" if delta == 0 else "contradicted"
        tally[(assessment.outcome, verdict)] += 1
        if verdict == "contradicted":
            contradictions.append({"case_id": case_id(row)[:16], "outcome": assessment.outcome,
                                   "before": before, "after": after, "amount": assessment.amount})
    return {"by_outcome": [{"outcome": k[0], "verdict": k[1], "count": n} for k, n in sorted(tally.items())],
            "confirmed": sum(n for k, n in tally.items() if k[1] == "confirmed"),
            "contradicted": len(contradictions), "contradictions": contradictions}


def agreement(rows, ranking, subset=None) -> dict:
    chosen = [(row, ranking[row["decision_id"]]) for row in rows if subset is None or row["decision_id"] in subset]
    top1 = sum(order[0] == row["chosen_action_index"] for row, order in chosen)
    top3 = sum(row["chosen_action_index"] in order[:3] for row, order in chosen if len(order) >= 3)
    eligible = sum(len(order) >= 3 for _, order in chosen)
    return {"n": len(chosen), "top1": top1, "top3": top3, "top3_eligible": eligible}


def bootstrap_delta(rows, base, variant, subset, rng: random.Random) -> dict:
    by_game = defaultdict(lambda: [0, 0])
    for row in rows:
        if row["decision_id"] in subset:
            by_game[row["game_id"]][0] += variant[row["decision_id"]][0] == row["chosen_action_index"]
            by_game[row["game_id"]][1] += base[row["decision_id"]][0] == row["chosen_action_index"]
    games = list(by_game.values())
    total = sum(row["decision_id"] in subset for row in rows)
    deltas = []
    for _ in range(BOOTSTRAP):
        sample = [games[rng.randrange(len(games))] for _ in games]
        deltas.append((sum(a for a, _ in sample) - sum(b for _, b in sample)) / max(total, 1))
    deltas.sort()
    point = (sum(a for a, _ in games) - sum(b for _, b in games))
    return {"top1_matches_gained": point, "per_decision_delta": point / max(total, 1),
            "ci95_per_decision": [deltas[int(0.025 * BOOTSTRAP)], deltas[int(0.975 * BOOTSTRAP)]]}


def layer_of(variants: dict[str, list[int]]) -> str | None:
    base, v1, v2, v3 = (variants[name][0] for name in VARIANTS)
    if v3 == base:
        return None
    if v1 != base:
        return "L1_TARGET_DOMINANCE"
    if v2 != v1:
        return "L2_LETHAL"
    return "L3_COMMITTED_EFFECT"


def compare(rows, orders, overlays, per_decision, records_by_id, development, sources):
    variants = {}
    changes = []
    for row in rows:
        did = row["decision_id"]
        variants[did] = rerank(orders[did], per_decision[did]) if per_decision[did] else {
            name: list(orders[did]) for name in VARIANTS}
    supported = {did for did, found in per_decision.items() if found}
    active_supported = {did for did in supported if overlays[did].healing_does_damage == ACTIVE}
    rankings = {name: {did: variants[did][name] for did in variants} for name in VARIANTS}
    for row in rows:
        did = row["decision_id"]
        layer = layer_of(variants[did])
        if layer is None:
            continue
        actions, state = row["legal_actions"], row["state"]
        chosen = row["chosen_action_index"]
        old, new = variants[did][VARIANTS[0]], variants[did][VARIANTS[3]]
        found = per_decision[did]
        new_top_assessment = found.get(new[0])
        changes.append({
            "case_id": case_id(row)[:16], "group": group_of(row, development), "layer": layer,
            "first_variant_that_changes": next(name for name in VARIANTS[1:] if variants[did][name][0] != old[0]),
            "sanctum": overlays[did].healing_does_damage,
            "old_top1": brief(records_by_id, state, actions[old[0]]),
            "old_top1_outcome": found[old[0]].outcome if old[0] in found else "NOT_A_SUPPORTED_HEAL",
            "new_top1": brief(records_by_id, state, actions[new[0]]),
            "new_top1_outcome": new_top_assessment.outcome if new_top_assessment else "NOT_A_SUPPORTED_HEAL",
            "new_top1_caveats": list(new_top_assessment.caveats) if new_top_assessment else [],
            "player_action": brief(records_by_id, state, actions[chosen]),
            "player_rank_old": old.index(chosen) + 1, "player_rank_new": new.index(chosen) + 1,
            "old_matches_player": old[0] == chosen, "new_matches_player": new[0] == chosen,
            "same_source_as_player": actions[new[0]].get("source_card_id") == actions[chosen].get("source_card_id")
            and actions[new[0]]["type"] == actions[chosen]["type"],
            "new_top1_source_type": actions[new[0]]["type"],
            "player_action_unmodeled_heal_capable": (
                actions[chosen].get("source_card_id") not in sources
                and bool(re.search(r"restore|heal", (records_by_id.get(actions[chosen].get("source_card_id"), {})
                                                      .get("text") or "").lower()))),
            "known_episode": KNOWN_EPISODES.get(case_id(row)),
            "available_facts": board_digest(records_by_id, state)})
    metrics = {}
    for name in VARIANTS:
        metrics[name] = {
            "all": agreement(rows, rankings[name]),
            "development": agreement(rows, rankings[name], {r["decision_id"] for r in rows if r["game_id"] in development}),
            "older": agreement(rows, rankings[name], {r["decision_id"] for r in rows if r["game_id"] not in development}),
            "supported_heal_decisions": agreement(rows, rankings[name], supported),
            "sanctum_active_decisions": agreement(rows, rankings[name], active_supported),
            "top1_changed_vs_v0": sum(variants[d][name][0] != variants[d][VARIANTS[0]][0] for d in variants),
            "top3_set_changed_vs_v0": sum(set(variants[d][name][:3]) != set(variants[d][VARIANTS[0]][:3])
                                          for d in variants)}
    rng = random.Random(SEED)
    bootstrap = {name: bootstrap_delta(rows, rankings[VARIANTS[0]], rankings[name], {r["decision_id"] for r in rows}, rng)
                 for name in VARIANTS[1:]}
    dev_ids = {r["decision_id"] for r in rows if r["game_id"] in development}
    bootstrap_dev = {name: bootstrap_delta(rows, rankings[VARIANTS[0]], rankings[name], dev_ids, rng)
                     for name in VARIANTS[1:]}
    return changes, metrics, bootstrap, bootstrap_dev, supported, active_supported


def summarise_changes(changes: list[dict]) -> dict:
    by_layer = defaultdict(Counter)
    for item in changes:
        by_layer[item["layer"]][(item["group"], item["old_matches_player"], item["new_matches_player"])] += 1
    return {layer: {"total": sum(counts.values()),
                    "by_group": {g: sum(n for k, n in counts.items() if k[0] == g) for g in ("development", "older")},
                    "old_matched_player_new_does_not": sum(n for k, n in counts.items() if k[1] and not k[2]),
                    "new_matches_player_old_did_not": sum(n for k, n in counts.items() if not k[1] and k[2]),
                    "neither_matches_player": sum(n for k, n in counts.items() if not k[1] and not k[2])}
            for layer, counts in sorted(by_layer.items())}


def l3_breakdown(changes: list[dict]) -> dict:
    result = {}
    for kind in ("PLAY_CARD", "HERO_POWER"):
        subset = [c for c in changes if c["layer"] == "L3_COMMITTED_EFFECT" and c["new_top1_source_type"] == kind]
        result[kind] = {"changes": len(subset),
                        "new_matches_player": sum(c["new_matches_player"] for c in subset),
                        "old_matched_player_new_does_not": sum(c["old_matches_player"] and not c["new_matches_player"]
                                                               for c in subset),
                        "player_used_unmodeled_heal_capable_action": sum(c["player_action_unmodeled_heal_capable"]
                                                                        for c in subset),
                        "same_source_as_player": sum(c["same_source_as_player"] for c in subset)}
    return result


def lethal_verification(rows, overlays, per_decision, orders) -> dict:
    """The converted-heal lethal claim against what happened next: did the game end right after the player's move?"""
    last = {}
    for row in rows:
        last[row["game_id"]] = row["decision_id"]
    out = []
    for row in rows:
        found = per_decision[row["decision_id"]]
        lethal = [i for i, a in found.items() if a.outcome == LETHAL]
        if not lethal:
            continue
        out.append({"case_id": case_id(row)[:16], "policy_top1_is_lethal": orders[row["decision_id"]][0] in lethal,
                    "policy_rank_of_best_lethal": min(orders[row["decision_id"]].index(i) for i in lethal) + 1,
                    "player_played_lethal": row["chosen_action_index"] in lethal,
                    "was_last_decision_of_match": last[row["game_id"]] == row["decision_id"],
                    "match_result_for_self": row["final_result"],
                    "opponent_secret_or_quest_count": row["state"]["opponent"]["secret_count"]})
    return {"cases": out, "lethal_available": len(out), "policy_top1_lethal": sum(c["policy_top1_is_lethal"] for c in out),
            "player_played_lethal_and_match_ended_in_win": sum(
                c["player_played_lethal"] and c["was_last_decision_of_match"] and c["match_result_for_self"] == 1.0
                for c in out)}


def top1_outcomes(rows, per_decision, orders) -> dict:
    """Direct outcome of the Top-1 action when it is a supported healing action, before and after L1."""
    tally = {name: Counter() for name in (VARIANTS[0], VARIANTS[1])}
    for row in rows:
        found = per_decision[row["decision_id"]]
        if not found:
            continue
        ranked = rerank(orders[row["decision_id"]], found)
        for name in tally:
            top = ranked[name][0]
            if top in found:
                tally[name][f"{row['legal_actions'][top]['type']}|{found[top].outcome}"] += 1
    return {name: {"total": sum(counts.values()), "by_outcome": dict(sorted(counts.items()))}
            for name, counts in tally.items()}


def residual_noop(rows, per_decision, orders) -> dict:
    """After L1, Top-1 supported heals that still have no direct effect (side effects stay unmodelled)."""
    tally = Counter()
    for row in rows:
        found = per_decision[row["decision_id"]]
        if not found:
            continue
        top = rerank(orders[row["decision_id"]], found)[VARIANTS[1]][0]
        item = found.get(top)
        if item is not None and item.value == "NEUTRAL":
            tally[(row["legal_actions"][top]["type"], f"quest_progress={item.quest_progress}")] += 1
    return {f"{k[0]}|{k[1]}": n for k, n in sorted(tally.items())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data",
                        help="directory holding processed_data_checkpoint_1_20261010, processed_policy_ml2a and raw")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/tactical_decision_1/results.json")
    args = parser.parse_args()
    rows, records, development, frozen = load_inputs(args.data_root)
    records_by_id = {r["id"]: r for r in records}
    texts = {r["id"]: MARKUP.sub("", r.get("text") or "").lower() for r in records}
    overlays, info = collect_overlays(args.data_root / "raw")
    overlay_check = check_overlays(rows, overlays, info)
    orders = rank_all(rows, frozen)
    sources = heal_sources(records)
    pools, per_decision = mine(rows, orders, overlays, sources, records_by_id, texts, development)

    mining_table = []
    for name in CLASS_PRIORITY:
        pool = pools[name]
        mining_table.append({
            "class": name, "decisions_flagged": len(pool),
            "development": sum(item["group"] == "development" for item in pool),
            "older": sum(item["group"] == "older" for item in pool),
            "tiers": tier_counts([item["hit"] for item in pool]),
            "player_matched_policy_top1": sum(item["top1_is_player"] for item in pool),
            "player_took_alternative": (sum(bool(item["player_took_alternative"]) for item in pool)
                                        if pool and pool[0]["player_took_alternative"] is not None else None),
            "quest_effect_of_top1": (dict(Counter(str(item["hit"]["facts"].get("quest_effect")) for item in pool))
                                     if name == "AOE_RUIN_NO_TARGET" else None),
            "player_action_rank_median": sorted(item["player_rank"] for item in pool)[len(pool) // 2] if pool else None})
    cases = [case_record(item, records_by_id) for item in select_cases(pools)]
    for item, case in zip(select_cases(pools), cases):
        case["overlay"] = sanctum_context(overlays[item["decision_id"]])

    changes, metrics, bootstrap, bootstrap_dev, supported, active_supported = compare(
        rows, orders, overlays, per_decision, records_by_id, development, sources)
    physics = verify_physics(rows, overlays, sources)
    outcomes = Counter(a.outcome for found in per_decision.values() for a in found.values())
    result = {
        "inputs": {"catalog_sha256": EXPECTED_CATALOG, "frozen_policy_sha256": EXPECTED_FROZEN,
                   "dataset_identity": EXPECTED_DATA, "content_identity": EXPECTED_CONTENT,
                   "decisions": len(rows), "matches": len({r["game_id"] for r in rows}),
                   "development_matches": len(development), "bootstrap_resamples": BOOTSTRAP, "seed": SEED,
                   "supported_sources": {k: [v.amount, v.kind, v.provenance, v.extra_effect]
                                         for k, v in sorted(sources.items())}},
        "overlay_reproduction": overlay_check,
        "mining": {"classes": mining_table,
                   "selected_cases": len(cases),
                   "selected_by_tier": tier_counts([{"tier": c["tier"]} for c in cases]),
                   "selected_by_group": dict(Counter(c["group"] for c in cases)),
                   "selected_by_class": dict(Counter(c["class"] for c in cases))},
        "cases": cases,
        "evaluator": {"supported_heal_decisions": len(supported), "sanctum_active_decisions": len(active_supported),
                      "action_outcomes": dict(outcomes), "metrics": metrics,
                      "bootstrap_all": bootstrap, "bootstrap_development": bootstrap_dev,
                      "changes_summary": summarise_changes(changes), "l3_breakdown": l3_breakdown(changes),
                      "lethal_verification": lethal_verification(rows, overlays, per_decision, orders),
                      "top1_supported_heal_outcomes": top1_outcomes(rows, per_decision, orders),
                      "residual_noop_top1_after_l1": residual_noop(rows, per_decision, orders),
                      "changes": changes,
                      "physics_check": physics},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, default=str, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"overlay": overlay_check["reproduces_observation_audit_1"],
                      "mining": [(m["class"], m["decisions_flagged"]) for m in mining_table],
                      "changes": summarise_changes(changes), "agree": {k: v["all"] for k, v in metrics.items()},
                      "physics": {k: physics[k] for k in ("confirmed", "contradicted")}}, indent=1))


if __name__ == "__main__":
    main()
