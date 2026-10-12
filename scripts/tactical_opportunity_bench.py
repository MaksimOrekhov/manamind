"""Read-only tactical opportunity diagnostics on permitted real train/validation matches.

This tool ranks existing legal actions with frozen Policy checkpoints and separately
counts conservative arithmetic/Outcome facts. It never learns, writes checkpoints, or
uses match result/action choice as a tactical label.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import torch

from manamind.domain.serialization import game_state_from_dict
from manamind.models.policy_inputs import representation_of
from manamind.outcome import forecast_action
from manamind.outcome.model import Status
from manamind.outcome.texts import TextSource
from manamind.training.combat_reality import extract_attack
from manamind.training.policy_checkpoint import load_policy_checkpoint
from manamind.training.real_policy import encode_example, validate_example


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data/processed_policy_real/real_policy_retrain_1"
DEFAULT_V1 = ROOT / "data/processed_policy_ml1c/baseline_seed42_v1/policy.pt"
DEFAULT_V2 = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
CARD_TEXTS = (ROOT / "data/cards/standard_current_enUS.json",
              ROOT / "data/cards/hearthstonejson_latest_enUS.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def permitted_rows(data_root: Path) -> tuple[list[dict], dict[str, set[str]]]:
    """Read only filenames named by train/validation lists; never open test files."""
    manifest = json.loads((data_root / "retrain_manifest.json").read_text(encoding="utf-8"))
    allowed = {part: set(manifest["split"]["game_ids"][part]) for part in ("train", "validation")}
    if allowed["train"] & allowed["validation"]:
        raise ValueError("train/validation game overlap")
    game_part = {game: part for part, games in allowed.items() for game in games}
    paths = sorted(path for path in data_root.glob("*.jsonl") if path.stem in game_part)
    rows, seen = [], set()
    seen_games = set()
    for path in paths:
        file_games = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            validate_example(row)
            if row["game_id"] not in game_part or row["decision_id"] in seen:
                raise ValueError("unexpected or duplicate permitted row")
            seen.add(row["decision_id"])
            file_games.add(row["game_id"])
            rows.append(row)
        if len(file_games) != 1 or path.stem not in file_games or seen_games & file_games:
            raise ValueError("match file identity mismatch")
        seen_games |= file_games
    if seen_games != set(game_part):
        raise ValueError("permitted train/validation file set is incomplete")
    return rows, allowed


def source_key(action: dict) -> tuple:
    if action.get("source_is_hero"):
        return ("HERO",)
    return (action.get("source_kind"), action.get("source_board_position"), action.get("source_card_id"))


def attack_faces(row: dict) -> list[tuple[int, dict]]:
    return [(i, a) for i, a in enumerate(row["legal_actions"])
            if a.get("type") == "ATTACK" and a.get("target_kind") == "HERO"
            and a.get("target_side") == "OPPONENT" and (a.get("source_attack") or 0) > 0]


def row_opportunities(row: dict, texts: TextSource) -> dict:
    state = row["state"]
    opp = state["opponent"]
    hp, armor = opp.get("hero_health"), opp.get("armor")
    faces = attack_faces(row)
    actors = {source_key(action): action for _, action in faces}
    damage = sum(max(0, int(action["source_attack"])) for action in actors.values())
    arithmetic_lethal = (type(hp) is int and type(armor) is int and hp > 0 and armor >= 0
                         and damage >= hp + armor)
    shield_blocks_known = opp.get("hero_divine_shield") is True
    face_forecasts = []
    game_state = game_state_from_dict(state)
    for index, action in faces:
        forecast = forecast_action(game_state, action, texts)
        target_events = [event for event in forecast.events if event.subject and event.subject.side == "OPPONENT"
                         and event.subject.zone == "HERO" and event.kind == "DAMAGE"]
        exact_hit = (forecast.status == Status.EXACT and len(target_events) == 1
                     and type(target_events[0].amount) is int and target_events[0].amount > 0)
        attacker_damaged = any(event.kind == "DAMAGE" and event.subject and event.subject.side == "SELF"
                               and event.subject.zone in {"BOARD", "HERO"} for event in forecast.events)
        face_forecasts.append((index, forecast, exact_hit, not attacker_damaged))
    potential = bool(faces and arithmetic_lethal and not shield_blocks_known)
    confirmed_single_attack_lethal = any(
        exact and type(hp) is int and type(armor) is int and armor >= 0
        and event_damage(forecast, "OPPONENT") >= hp + armor
        for _, forecast, exact, _ in face_forecasts)
    # A multi-action sum is only an upper bound across the original menu. We do not
    # claim that subsequent attacks remain legal after the first action.
    return {"faces": faces, "damage": damage, "potential_lethal": potential,
            "arithmetic_lethal": arithmetic_lethal,
            "hero_shield_unknown": opp.get("hero_divine_shield") is None,
            "confirmed_single_attack_lethal": confirmed_single_attack_lethal,
            "face_forecasts": face_forecasts, "hero_hp": hp, "hero_armor": armor}


def rank_row(policy, encoder, row: dict) -> tuple[list[int], int]:
    device = next(policy.parameters()).device
    with torch.no_grad():
        logits = policy(*encode_example(row, encoder, device,
                                        representation=representation_of(policy)))
    order = torch.argsort(logits, descending=True, stable=True).tolist()
    return order, order.index(row["chosen_action_index"]) + 1


def evaluate(rows: list[dict], models: dict, texts: TextSource, allowed: dict[str, set[str]]) -> dict:
    report = {}
    for partition in ("train", "validation"):
        subset = [r for r in rows if r["game_id"] in allowed[partition]]
        games = {r["game_id"] for r in subset}
        metric = {name: {"top1": 0, "top3": 0, "imitation_top1": 0, "imitation_top3": 0}
                  for name in models}
        opportunities = Counter(
            potential_lethal_states=0,
            potential_lethal_multi_actor=0,
            potential_lethal_single_actor=0,
            potential_lethal_shield_unknown=0,
            confirmed_single_attack_lethal_states=0,
            legal_positive_face_attack_states=0,
            exact_face_hit_no_return_states=0,
            face_candidate_with_uncertainty_states=0,
        )
        mechanic = Counter()
        mismatch = Counter()
        uncertainty = Counter()
        trade_rank = {name: Counter() for name in models}
        per_game = defaultdict(Counter)
        for row in subset:
            opp = row_opportunities(row, texts)
            face_indices = [index for index, _ in opp["faces"]]
            potential = opp["potential_lethal"]
            if potential:
                opportunities["potential_lethal_states"] += 1
                opportunities["potential_lethal_shield_unknown"] += opp["hero_shield_unknown"]
                opportunities["potential_lethal_multi_actor"] += len({source_key(a) for _, a in opp["faces"]}) > 1
                opportunities["potential_lethal_single_actor"] += len({source_key(a) for _, a in opp["faces"]}) == 1
                per_game[row["game_id"]]["potential_lethal_states"] += 1
            opportunities["confirmed_single_attack_lethal_states"] += opp["confirmed_single_attack_lethal"]
            if opp["faces"]:
                opportunities["legal_positive_face_attack_states"] += 1
                exact_no_return = any(exact and no_return for _, _, exact, no_return in opp["face_forecasts"])
                uncertain = any(forecast.status != Status.EXACT for _, forecast, _, _ in opp["face_forecasts"])
                opportunities["exact_face_hit_no_return_states"] += exact_no_return
                opportunities["face_candidate_with_uncertainty_states"] += uncertain
                for _, forecast, _, _ in opp["face_forecasts"]:
                    if forecast.status != Status.EXACT:
                        for unknown in forecast.unknowns:
                            uncertainty[unknown.tag or unknown.kind.value] += 1
            # Coarse can_attack is intentionally compared with the server's legal menu.
            for minion in row["state"]["self_player"]["board"]:
                if not minion.get("can_attack"):
                    continue
                key = ("MINION", minion["board_position"], minion["card"]["card_id"])
                has_attack = any(a.get("type") == "ATTACK" and not a.get("source_is_hero")
                                 and source_key(a) == key for a in row["legal_actions"])
                if not has_attack:
                    mismatch["can_attack_without_legal_attack_entities"] += 1
                    mismatch["such_entities_dormant"] += bool(minion.get("dormant"))
                    mismatch["such_entities_frozen"] += bool(minion.get("frozen"))
                    mismatch["such_entities_zero_attack"] += (minion.get("current_attack") or 0) <= 0
                    mismatch["such_entities_opponent_has_taunt"] += any(m.get("taunt") for m in opp_minions(row))
                    mismatch["such_entities_all_enemy_minions_stealth"] += (bool(opp_minions(row))
                                                                               and all(m.get("stealth") for m in opp_minions(row)))
            # Existing NCA extractor is used unchanged for local minion combat facts.
            losing_trade_pairs = []
            for index, action in enumerate(row["legal_actions"]):
                if action.get("type") != "ATTACK" or action.get("source_kind") != "MINION" or action.get("target_kind") != "MINION":
                    continue
                attack = extract_attack(row, action, texts)
                props = attack["properties"]
                if (props.get("source_body_dies", {}).get("value") is True
                        and props.get("target_body_dies", {}).get("value") is False
                        and props.get("source_body_dies", {}).get("knownness") == "VERIFIED_LOCAL"
                        and props.get("target_body_dies", {}).get("knownness") == "VERIFIED_LOCAL"):
                    mechanic["verified_source_dies_target_survives_actions"] += 1
                    mechanic["verified_source_dies_target_survives_states"] += 1
                    per_game[row["game_id"]]["verified_losing_trade_states"] += 1
                    # Search a same-source alternative that locally kills its target and survives.
                    safe_kill = []
                    for other_i, other in enumerate(row["legal_actions"]):
                        if other.get("type") != "ATTACK" or source_key(other) != source_key(action) or other.get("target_kind") != "MINION":
                            continue
                        other_fact = extract_attack(row, other, texts)
                        p = other_fact["properties"]
                        if (p.get("source_body_dies", {}).get("value") is False
                                and p.get("target_body_dies", {}).get("value") is True
                                and p.get("source_body_dies", {}).get("knownness") == "VERIFIED_LOCAL"
                                and p.get("target_body_dies", {}).get("knownness") == "VERIFIED_LOCAL"):
                            safe_kill.append(other_i)
                    if safe_kill:
                        mechanic["narrow_local_alternatives_exist"] += 1
                        losing_trade_pairs.append((index, safe_kill))
            for name, (policy, encoder) in models.items():
                order, behavior_rank = rank_row(policy, encoder, row)
                metric[name]["imitation_top1"] += behavior_rank == 1
                metric[name]["imitation_top3"] += behavior_rank <= 3
                if potential and face_indices:
                    metric[name]["top1"] += order[0] in face_indices
                    metric[name]["top3"] += bool(set(order[:3]) & set(face_indices))
                positions = {action_index: rank for rank, action_index in enumerate(order, 1)}
                for losing_index, safe_indices in losing_trade_pairs:
                    trade_rank[name]["comparisons"] += 1
                    trade_rank[name]["policy_ranks_losing_trade_above_local_alternative"] += any(
                        positions[safe_index] < positions[losing_index] for safe_index in safe_indices)
        decisions = len(subset)
        model_result = {}
        potential_count = opportunities["potential_lethal_states"]
        for name in models:
            model_result[name] = {key: round(value / decisions, 6) for key, value in metric[name].items()}
            model_result[name]["potential_lethal_top1_recall"] = (
                round(metric[name]["top1"] / potential_count, 6) if potential_count else None)
            model_result[name]["potential_lethal_top3_recall"] = (
                round(metric[name]["top3"] / potential_count, 6) if potential_count else None)
            model_result[name]["decisions"] = decisions
        report[partition] = {
            "decisions": decisions, "matches": len(games),
            "opportunities": dict(opportunities), "mechanical_trade_facts": dict(mechanic),
            "coarse_can_attack_menu_mismatch": dict(mismatch),
            "face_forecast_unknown_tags_action_counts": dict(uncertainty),
            "policy_rank_on_narrow_trade_comparisons": {
                name: dict(counts) for name, counts in trade_rank.items()},
            "policy_metrics_fraction_of_decisions": model_result,
            "matches_with_potential_lethal": sum(c["potential_lethal_states"] > 0 for c in per_game.values()),
            "matches_with_verified_losing_trade": sum(c["verified_losing_trade_states"] > 0 for c in per_game.values()),
            "max_potential_lethal_states_in_one_match": max((c["potential_lethal_states"] for c in per_game.values()), default=0),
            "max_verified_losing_trade_states_in_one_match": max((c["verified_losing_trade_states"] for c in per_game.values()), default=0),
        }
    return report


def opp_minions(row: dict) -> list[dict]:
    return row["state"]["opponent"]["board"]


def event_damage(forecast, side: str) -> int:
    return sum(event.amount for event in forecast.events
               if event.kind == "DAMAGE" and event.subject and event.subject.side == side
               and event.subject.zone == "HERO" and type(event.amount) is int)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--v1-checkpoint", type=Path, default=DEFAULT_V1)
    parser.add_argument("--v2-checkpoint", type=Path, default=DEFAULT_V2)
    parser.add_argument("--output", type=Path, help="Optional aggregate JSON output; contains no game identifiers")
    args = parser.parse_args()
    rows, allowed = permitted_rows(args.data_root)
    manifest = json.loads((args.data_root / "retrain_manifest.json").read_text(encoding="utf-8"))
    texts = TextSource.from_files(*CARD_TEXTS)
    models = {}
    for name, path in (("v1_reference", args.v1_checkpoint), ("v2_live", args.v2_checkpoint)):
        policy, encoder, _ = load_policy_checkpoint(path)
        models[name] = (policy, encoder)
    output = {
        "schema": "manamind.tactical_opportunity_bench/1",
        "inputs": {
            "dataset": "real_policy_retrain_1 train+validation only",
            "train_matches": len(allowed["train"]), "validation_matches": len(allowed["validation"]),
            "decisions": len(rows),
            "split_sha256": manifest["split_sha256"],
            "dataset_sha256": manifest["split"]["dataset_sha256"],
            "v1_checkpoint_sha256": sha256(args.v1_checkpoint),
            "v2_checkpoint_sha256": sha256(args.v2_checkpoint),
            "card_text_files": {p.name: sha256(p) for p in CARD_TEXTS},
            "note": "Top-1/Top-3 imitation metrics use chosen actions as behavior reference only; tactical counts are separate and not strategy labels.",
        },
        "results": evaluate(rows, models, texts, allowed),
    }
    serialized = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(serialized.encode("utf-8"))
    print(serialized, end="")


if __name__ == "__main__":
    main()
