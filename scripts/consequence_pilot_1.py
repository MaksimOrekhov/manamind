"""CONSEQUENCE-PILOT-1: direct-effect checks on real positions and a diagnostic frozen-v2 rerank.

Offline only. Reads the canonical DATA-CHECKPOINT-1 corpus and the frozen Policy v2 checkpoint without
modifying either, and writes one new anonymized results file. Nothing here trains a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import torch

from manamind.cards.catalog import CardCatalog
from manamind.domain.serialization import game_state_from_dict
from manamind.research.consequence_check import (
    DESTROY_MINIONS_MIN_ATTACK, DIRECT_EFFECT_PRESENT, NO_DIRECT_EFFECT, RESTORE_TARGET, UNKNOWN, UNSUPPORTED,
    VerifiedEffect, catalog_effects, catalog_texts, check_direct_effect, constrained_order, is_demotable,
)
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint
from manamind.training.real_policy import audit_dataset, encode_example, load_examples

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_real_policy_dataset import canonical_content_identity, dataset_identity  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORPUS = INVENTORY = FROZEN = Path()  # set by configure(); local data lives in git-ignored data/
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
EXPECTED_DATA = "b964e121d6ddb0c11be4014b1549d1a5c861cf57002bfd8975edd53b3be233c1"
EXPECTED_CONTENT = "78c21cbd0a2c0c69cdaee77bd07525b086294dba781674a6c47a9a65d354e9c9"
EXPECTED_FROZEN = "044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d"
EXPECTED_CATALOG = "c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34"
# Situations already reviewed in ML-PILOT-1 (observation identity of {"state", "legal_actions"}).
KNOWN_EPISODES = {
    "83e9144a6f6061b12f62ff1ef94432c40cb92c8cecb8e79dfefd0ff13c43f277": "full_health_heal",
    "4ace66afa0531174116b60eb257f76d2d3d52f3222a9e577c4b622614fe368e4": "ruin_no_attack_5",
    "abacd59f61e3cd64670f2d48608c3b0d11befdae8d3ea37f5493a3b1e6ce70fd": "atiesh_with_medivh_in_hand",
    "be831feae52a9120d342147a578363343e9dd19f16bb0661606b4946c832c6de": "medivh_against_board",
}
OBSERVED_HERO_POWER = "HERO_09dbp"  # not in the pinned catalog; its effect may only be verified from outcomes
FABLED = ("TIME_890", "TIME_890t", "TIME_890t2")
CASES_PER_CATEGORY = 4


def configure(data_root: Path) -> None:
    global CORPUS, INVENTORY, FROZEN
    CORPUS = data_root / "processed_data_checkpoint_1_20261010/canonical"
    INVENTORY = data_root / "processed_data_checkpoint_1_20261010/raw_inventory.json"
    FROZEN = data_root / "processed_policy_ml2a/seed42_v2/policy.pt"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def short(value: str) -> str:
    return value[:16]


def index_of(row: dict) -> int:
    return int(row["decision_id"].rsplit(":", 1)[1])


def brief(action: dict) -> dict:
    return {key: action[key] for key in ("type", "source_card_id", "target_side", "target_kind", "target_card_id",
                                         "target_board_position") if action.get(key) is not None}


def load_inputs() -> tuple[list[dict], list[dict], set[str]]:
    if sha(CATALOG) != EXPECTED_CATALOG or sha(FROZEN) != EXPECTED_FROZEN:
        raise ValueError("Pinned catalog or frozen checkpoint identity mismatch")
    rows = load_examples(CORPUS)
    if dataset_identity(rows) != EXPECTED_DATA or canonical_content_identity(CORPUS) != EXPECTED_CONTENT:
        raise ValueError("Canonical corpus identity mismatch")
    audit = audit_dataset(CORPUS, CardCatalog.from_json(CATALOG))
    if audit["decisions_labeled"] != 2010 or audit["labeled_matches"] != 53:
        raise ValueError("Canonical corpus audit mismatch")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    recent = {item["game_id"] for item in inventory if item["mtime"].startswith("2026-10-10")}
    development = recent & {row["game_id"] for row in rows}
    if len(development) != 16:
        raise ValueError("Expected the 16 development-test matches of ML-PILOT-1")
    records = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    return sorted(rows, key=lambda row: (row["game_id"], index_of(row))), records, development


def clean_next(rows: list[dict], position: int) -> dict | None:
    """The next decision only if no other decision (recorded or skipped) and no turn change happened between."""
    row = rows[position]
    if position + 1 >= len(rows):
        return None
    following = rows[position + 1]
    if (following["game_id"] != row["game_id"] or index_of(following) != index_of(row) + 1
            or following["state"]["turn_number"] != row["state"]["turn_number"]):
        return None
    return following


def target_health(state: dict, action: dict) -> tuple[int, int] | None:
    player = state["self_player" if action.get("target_side") == "SELF" else "opponent"]
    if action.get("target_kind") == "HERO":
        return player["hero_health"], player["hero_max_health"]
    matches = [entity for entity in player["board"] if entity["board_position"] == action.get("target_board_position")
               and entity["card"]["card_id"] == action.get("target_card_id")]
    if len(matches) != 1:
        # A target that left the board between decisions; a same-card neighbour shift is not resolved.
        return None
    return matches[0]["current_health"], matches[0]["max_health"]


def observed_restore_evidence(rows: list[dict], card_id: str) -> dict:
    """Health change of the chosen target across a clean one-decision window, per chosen use of ``card_id``."""
    deltas = []
    for position, row in enumerate(rows):
        action = row["legal_actions"][row["chosen_action_index"]]
        if action.get("source_card_id") != card_id or "target_kind" not in action:
            continue
        following = clean_next(rows, position)
        before = target_health(row["state"], action)
        after = target_health(following["state"], action) if following else None
        if before is None or after is None or after[1] != before[1]:
            continue
        deltas.append({"missing": before[1] - before[0], "delta": after[0] - before[0],
                       "target_side": action["target_side"]})
    uncapped = {item["delta"] for item in deltas if item["missing"] > item["delta"] >= 0}
    amount = next(iter(uncapped)) if len(uncapped) == 1 else None
    consistent = amount is not None and amount > 0 and all(
        item["delta"] == min(item["missing"], amount) for item in deltas)
    return {"card_id": card_id, "observations": len(deltas),
            "damaged_target_observations": sum(item["missing"] > 0 for item in deltas),
            "full_target_observations": sum(item["missing"] == 0 for item in deltas),
            "observed_deltas": sorted(Counter((item["missing"] > 0, item["delta"]) for item in deltas).items()),
            "inferred_restore": amount, "consistent": consistent}


def rank(rows: list[dict]) -> dict[str, list[int]]:
    torch.manual_seed(0)
    torch.set_num_threads(1)
    model, encoder, payload = load_policy_checkpoint(FROZEN)
    model.eval()
    orders = {}
    with torch.inference_mode():
        for row in rows:
            logits = model(*encode_example(row, encoder, representation=2))
            if logits.shape != (len(row["legal_actions"]),) or not torch.isfinite(logits).all():
                raise ValueError("Invalid frozen logits")
            orders[row["decision_id"]] = torch.argsort(logits, descending=True, stable=True).tolist()
    return orders, payload


def result_dict(result) -> dict:
    keep = ("mechanic", "missing_health", "base_restore", "direct_restore_min", "attack_threshold",
            "minion_attacks", "qualifying", "modifier_matching_cards", "modifier_unknown_cards",
            "side_matching_cards", "side_unknown_cards", "effect_provenance")
    return {"status": result.status, "reason": result.reason, "side_effects": result.side_effects,
            "side_reasons": list(result.side_reasons),
            **{key: result.details[key] for key in keep if key in result.details}}


def outcome(row: dict, following: dict | None, action: dict, result, texts: dict) -> dict | None:
    """Compare the analyzer's direct claim with the next clean state; None when unobservable."""
    if following is None or result.status == UNSUPPORTED or "mechanic" not in result.details:
        return None
    if result.details["mechanic"] == RESTORE_TARGET:
        before, after = target_health(row["state"], action), target_health(following["state"], action)
        if before is None or after is None:
            return {"observable": False, "note": "target left the board or could not be matched"}
        delta = after[0] - before[0]
        if result.status == NO_DIRECT_EFFECT:
            agrees = delta == 0
        elif result.status == DIRECT_EFFECT_PRESENT:
            agrees = delta >= result.details["direct_restore_min"]
        else:
            agrees = None
        return {"observable": True, "health_delta": delta, "agrees": agrees}
    threshold = result.details["attack_threshold"]
    counts = {}
    for side in ("self_player", "opponent"):
        qualifying = Counter(e["card"]["card_id"] for e in row["state"][side]["board"]
                             if e["current_attack"] >= threshold)
        others = Counter(e["card"]["card_id"] for e in row["state"][side]["board"]
                         if e["current_attack"] < threshold)
        after = Counter(e["card"]["card_id"] for e in following["state"][side]["board"])
        counts[side] = {"qualifying_remaining": sum(min(after[k], n) for k, n in qualifying.items()),
                        "others_remaining": sum(min(after[k], n) for k, n in others.items()),
                        "others_before": sum(others.values())}
    remaining = sum(item["qualifying_remaining"] for item in counts.values())
    others_kept = all(item["others_remaining"] == item["others_before"] for item in counts.values())
    # Same-ID minions after a destroy may be Deathrattle/Reborn returns, not survivors: no verdict then.
    confounded = any(e["reborn"] or "deathrattle" in texts.get(e["card"]["card_id"], "deathrattle")
                     for side in ("self_player", "opponent") for e in row["state"][side]["board"])
    if result.status == NO_DIRECT_EFFECT:
        agrees = others_kept
    elif result.status == DIRECT_EFFECT_PRESENT:
        agrees = True if remaining == 0 else None if confounded else False
    else:
        agrees = None
    return {"observable": True, "qualifying_remaining": remaining, "non_qualifying_kept": others_kept,
            "deathrattle_or_reborn_on_board": confounded, "agrees": agrees}


def fabled_diagnostics(rows: list[dict], records: list[dict], orders: dict) -> dict:
    pinned = {record["id"]: record for record in records}
    transitions = Counter()
    unexplained = 0
    medivh_on_board_with_atiesh_in_hand = 0
    for position, row in enumerate(rows):
        state = row["state"]
        hand = {card["card_id"] for card in state["self_hand"]}
        if "TIME_890t" in hand and any(e["card"]["card_id"] == "TIME_890" for e in state["self_player"]["board"]):
            medivh_on_board_with_atiesh_in_hand += 1
        if position + 1 >= len(rows) or rows[position + 1]["game_id"] != row["game_id"]:
            continue
        following = rows[position + 1]["state"]
        before = {card["card_id"]: card["current_cost"] for card in state["self_hand"] if card["card_id"] in FABLED}
        after = {card["card_id"]: card["current_cost"] for card in following["self_hand"]
                 if card["card_id"] in FABLED}
        for card_id in set(before) & set(after):
            if before[card_id] == after[card_id]:
                continue
            controlled_before = fabled_controlled(state)
            controlled_after = fabled_controlled(following)
            new = sorted(controlled_after - controlled_before)
            if not new:
                unexplained += 1
            transitions[(card_id, before[card_id], after[card_id], ",".join(new) or "none")] += 1
    atiesh_rows = []
    for row in rows:
        actions = row["legal_actions"]
        hand = {card["card_id"] for card in row["state"]["self_hand"]}
        atiesh = [i for i, a in enumerate(actions) if a.get("source_card_id") == "TIME_890t"]
        if atiesh and "TIME_890" in hand:
            order = orders[row["decision_id"]]
            state = row["state"]
            costs = {card["card_id"]: card["current_cost"] for card in state["self_hand"] if card["card_id"] in FABLED}
            medivh_legal = any(a.get("source_card_id") == "TIME_890" for a in actions)
            case_id = identity({"state": state, "legal_actions": actions})
            atiesh_rows.append({
                "case_id": short(case_id), "known_episode": KNOWN_EPISODES.get(case_id),
                "frozen_top3": [brief(actions[i]) for i in order[:3]],
                "player_action": brief(actions[row["chosen_action_index"]]),
                "available_mana": state["self_player"]["available_mana"], "fabled_costs_in_hand": costs,
                "frozen_top1_is_atiesh": order[0] in atiesh,
                "player_chose_atiesh": row["chosen_action_index"] in atiesh,
                "medivh_legal": medivh_legal,
                # Observed rule: controlling Medivh made Atiesh cost 0; Atiesh made Karazhan 0; Karazhan made Medivh 0.
                "medivh_first_then_free_atiesh": medivh_legal and costs.get("TIME_890t", 99) > 0,
                "atiesh_first_then_free_medivh_same_turn": "TIME_890t2" in (hand | fabled_controlled(state)),
                "board_minions": len(state["self_player"]["board"]) + len(state["opponent"]["board"])})
    return {
        "pinned_catalog": {card_id: ({"name": pinned[card_id]["name"], "cost": pinned[card_id].get("cost"),
                                      "text": pinned[card_id].get("text")} if card_id in pinned else None)
                           for card_id in FABLED},
        "observed_cost_transitions": [
            {"card_id": key[0], "cost_before": key[1], "cost_after": key[2], "newly_controlled": key[3], "count": n}
            for key, n in sorted(transitions.items(), key=str)],
        "transitions_without_new_controlled_fabled_card": unexplained,
        "states_medivh_on_self_board_and_atiesh_in_hand": medivh_on_board_with_atiesh_in_hand,
        "atiesh_legal_with_medivh_in_hand": {
            "decisions": len(atiesh_rows),
            "frozen_top1_atiesh": sum(item["frozen_top1_is_atiesh"] for item in atiesh_rows),
            "player_chose_atiesh": sum(item["player_chose_atiesh"] for item in atiesh_rows),
            "frozen_top1_atiesh_and_player_chose_atiesh": sum(
                item["frozen_top1_is_atiesh"] and item["player_chose_atiesh"] for item in atiesh_rows),
            "medivh_also_legal": sum(item["medivh_legal"] for item in atiesh_rows),
            "frozen_top1_atiesh_while_medivh_first_frees_atiesh_and_no_karazhan_route": sum(
                item["frozen_top1_is_atiesh"] and item["medivh_first_then_free_atiesh"]
                and not item["atiesh_first_then_free_medivh_same_turn"] for item in atiesh_rows),
            "of_those_with_minions_on_board": sum(
                item["frozen_top1_is_atiesh"] and item["medivh_first_then_free_atiesh"]
                and not item["atiesh_first_then_free_medivh_same_turn"] and item["board_minions"] > 0
                for item in atiesh_rows),
            "examples": [item for item in atiesh_rows if item["frozen_top1_is_atiesh"]
                         and item["medivh_first_then_free_atiesh"]
                         and not item["atiesh_first_then_free_medivh_same_turn"]]},
    }


def fabled_controlled(state: dict) -> set[str]:
    player = state["self_player"]
    controlled = {e["card"]["card_id"] for e in player["board"]} | {l["card"]["card_id"] for l in player["locations"]}
    if player["weapon"]:
        controlled.add(player["weapon"]["card_id"])
    return controlled & set(FABLED)


def category(row: dict, order: list[int], checks: list) -> list[str]:
    actions = row["legal_actions"]
    top = order[0]
    labels = []
    detail = checks[top].details
    if detail.get("mechanic") == RESTORE_TARGET and "missing_health" in detail:
        labels.append("heal_full_target" if detail["missing_health"] == 0 else "heal_damaged_target")
    ruins = [i for i, item in enumerate(checks) if item.details.get("mechanic") == DESTROY_MINIONS_MIN_ATTACK]
    if ruins:
        qualifying = sum(checks[ruins[0]].details["qualifying"].values())
        if top in ruins and not qualifying:
            labels.append("ruin_no_qualifying_minion")
        elif qualifying:
            labels.append("ruin_with_qualifying_minion")
    hand = {card["card_id"] for card in row["state"]["self_hand"]}
    if any(a.get("source_card_id") in ("TIME_890", "TIME_890t") for a in actions) and {"TIME_890", "TIME_890t"} <= hand:
        labels.append("medivh_atiesh")
    return labels


def helpfulness(row: dict, order: list[int], checks: list) -> str:
    top = checks[order[0]]
    if top.status == UNSUPPORTED:
        return "NOT_APPLICABLE_TOP1_UNSUPPORTED"
    if top.status == DIRECT_EFFECT_PRESENT:
        return "NOT_APPLICABLE_TOP1_HAS_DIRECT_EFFECT"
    if top.status == UNKNOWN:
        return f"NO_TOP1_UNKNOWN_{top.reason}"
    if is_demotable(top):
        return "YES_TOP1_DEMOTED"
    return f"NO_SIDE_EFFECTS_{top.side_effects}"


def run(output: Path) -> dict:
    rows, records, development = load_inputs()
    texts = catalog_texts(records)
    effects = catalog_effects(records)
    evidence = observed_restore_evidence(rows, OBSERVED_HERO_POWER)
    if evidence["consistent"] and evidence["damaged_target_observations"] >= 5:
        effects[OBSERVED_HERO_POWER] = VerifiedEffect(OBSERVED_HERO_POWER, RESTORE_TARGET,
                                                      evidence["inferred_restore"], "observed_outcomes")
    orders, payload = rank(rows)
    frozen_seen = set().union(*map(set, payload["experiment"]["split"]["game_ids"].values()))
    groups = {"development_test": development, "older": {row["game_id"] for row in rows} - development}

    status_counts = defaultdict(Counter)
    top1_counts = defaultdict(Counter)
    outcomes = defaultdict(Counter)
    disagreements = []
    rerank = {variant: {name: Counter() for name in groups} for variant in ("B_strict", "C_direct_only_diagnostic")}
    rerank_examples = []
    cases = defaultdict(list)
    restore_sides, catalog_gap, missing_ids = Counter(), Counter(), Counter()
    for position, row in enumerate(rows):
        state = game_state_from_dict(row["state"])
        checks = [check_direct_effect(state, action, effects, texts) for action in row["legal_actions"]]
        order = orders[row["decision_id"]]
        chosen = row["chosen_action_index"]
        group = "development_test" if row["game_id"] in development else "older"
        for result in checks:
            if result.status != UNSUPPORTED:
                mechanic = result.details.get("mechanic", "unresolved")
                status_counts[mechanic][(result.status, result.reason, result.side_effects)] += 1
        top = checks[order[0]]
        if top.status != UNSUPPORTED:
            top1_counts[top.details.get("mechanic", "unresolved")][(top.status, top.side_effects)] += 1
            if top.details.get("mechanic") == RESTORE_TARGET:
                restore_sides[(row["legal_actions"][order[0]].get("target_side"), top.status, top.reason)] += 1
        for card in [e.card for side in (state.self_player, state.opponent) for e in side.board] + [
                l.card for side in (state.self_player, state.opponent) for l in side.locations] + [
                side.weapon for side in (state.self_player, state.opponent) if side.weapon] + list(state.self_hand):
            catalog_gap[card.card_id in texts] += 1
            if card.card_id not in texts:
                missing_ids[card.card_id] += 1
        observed = outcome(row, clean_next(rows, position), row["legal_actions"][chosen], checks[chosen], texts)
        if observed is not None:
            mechanic = checks[chosen].details["mechanic"]
            key = (mechanic, checks[chosen].status, "unobservable" if not observed["observable"]
                   else {True: "agrees", False: "disagrees", None: "no_claim"}[observed["agrees"]])
            outcomes[key[0]][key[1:]] += 1
            if observed.get("agrees") is False or (checks[chosen].status == UNKNOWN and observed["observable"]):
                disagreements.append({"case_id": short(identity({"state": row["state"],
                                                                  "legal_actions": row["legal_actions"]})),
                                      "action": brief(row["legal_actions"][chosen]),
                                      "analyzer": result_dict(checks[chosen]), "observed": observed})
        case_id = identity({"state": row["state"], "legal_actions": row["legal_actions"]})
        variants = {"B_strict": {i for i, result in enumerate(checks) if is_demotable(result)},
                    "C_direct_only_diagnostic": {i for i, result in enumerate(checks)
                                                 if result.status == NO_DIRECT_EFFECT}}
        for variant, demote in variants.items():
            new_order = constrained_order(order, demote)
            stats = rerank[variant][group]
            stats["decisions"] += 1
            stats["top1_matches_player_A"] += order[0] == chosen
            stats["top1_matches_player_variant"] += new_order[0] == chosen
            stats["decisions_with_demoted_action"] += bool(demote)
            stats["player_chose_demoted_action"] += chosen in demote
            stats["top1_supported_unknown"] += top.status == UNKNOWN
            if new_order[0] != order[0]:
                stats["top1_changed"] += 1
                stats["changed_and_A_matched_player"] += order[0] == chosen
                stats["changed_and_variant_matches_player"] += new_order[0] == chosen
                rerank_examples.append({"variant": variant, "group": group, "case_id": short(case_id),
                                        "known_episode": KNOWN_EPISODES.get(case_id),
                                        "A_top1": brief(row["legal_actions"][order[0]]),
                                        "variant_top1": brief(row["legal_actions"][new_order[0]]),
                                        "variant_top1_analyzer": result_dict(checks[new_order[0]]),
                                        "player": brief(row["legal_actions"][chosen]),
                                        "player_rank_A": order.index(chosen) + 1,
                                        "analyzer_A_top1": result_dict(checks[order[0]]),
                                        "observed_after_player_action": observed})
        new_order = constrained_order(order, variants["B_strict"])
        labels = category(row, order, checks)
        if case_id in KNOWN_EPISODES:
            labels = [KNOWN_EPISODES[case_id] + "_known_episode"] + labels
        for label in labels:
            cases[label].append((case_id in KNOWN_EPISODES, hashlib.sha256(case_id.encode()).hexdigest(), {
                "case_id": short(case_id), "group": group, "known_episode": KNOWN_EPISODES.get(case_id),
                "frozen_top3": [{"action": brief(row["legal_actions"][i]),
                                 "analyzer": result_dict(checks[i])} for i in order[:3]],
                "player_action": brief(row["legal_actions"][chosen]), "player_action_rank": order.index(chosen) + 1,
                "constrained_top1": brief(row["legal_actions"][new_order[0]]),
                "could_help": helpfulness(row, order, checks),
                "observed_after_player_action": observed}))
    selected = {label: [item for *_, item in sorted(items, key=lambda x: (not x[0], x[1]))[:CASES_PER_CATEGORY]]
                for label, items in sorted(cases.items())}
    result = {
        "inputs": {"dataset_sha256": EXPECTED_DATA, "canonical_content_sha256": EXPECTED_CONTENT,
                   "frozen_checkpoint_sha256": EXPECTED_FROZEN, "catalog_sha256": EXPECTED_CATALOG,
                   "decisions": len(rows), "matches": len({row["game_id"] for row in rows}),
                   "development_test_matches": len(development),
                   "older_matches_in_frozen_training_splits": len(groups["older"] & frozen_seen),
                   "development_matches_in_frozen_training_splits": len(development & frozen_seen)},
        "verified_effects": {key: {"mechanic": value.mechanic, "value": value.value, "provenance": value.provenance}
                             for key, value in sorted(effects.items())},
        "hero_power_evidence": evidence,
        "legal_action_checks": {mechanic: [{"status": k[0], "reason": k[1], "side_effects": k[2], "count": n}
                                           for k, n in sorted(counter.items(), key=str)]
                                for mechanic, counter in sorted(status_counts.items())},
        "frozen_top1_checks": {mechanic: [{"status": k[0], "side_effects": k[1], "count": n}
                                          for k, n in sorted(counter.items(), key=str)]
                               for mechanic, counter in sorted(top1_counts.items())},
        "frozen_top1_restore_by_target_side": [
            {"target_side": k[0], "status": k[1], "reason": k[2], "count": n}
            for k, n in sorted(restore_sides.items(), key=str)],
        "visible_card_occurrences": {"text_in_pinned_catalog": catalog_gap[True],
                                     "text_not_in_pinned_catalog": catalog_gap[False],
                                     "distinct_missing_ids": len(missing_ids),
                                     "most_frequent_missing": missing_ids.most_common(12)},
        "chosen_action_outcomes": {mechanic: [{"status": k[0], "verdict": k[1], "count": n}
                                              for k, n in sorted(counter.items(), key=str)]
                                   for mechanic, counter in sorted(outcomes.items())},
        "outcome_disagreements_and_unknowns": disagreements,
        "rerank": {variant: {name: dict(sorted(counter.items())) for name, counter in by_group.items()}
                   for variant, by_group in rerank.items()},
        "rerank_changes": rerank_examples,
        "cases": selected,
        "fabled": fabled_diagnostics(rows, records, orders),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/consequence_pilot_1/results.json")
    parser.add_argument("--data-root", type=Path, default=ROOT / "data",
                        help="directory holding the git-ignored corpus and frozen checkpoint")
    args = parser.parse_args()
    configure(args.data_root)
    run(args.output)


if __name__ == "__main__":
    main()
