"""Measure a self-play policy against a fixed legal-action baseline."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from manamind.cards.catalog import CardCatalog
from manamind.cards.vocabulary import CardVocabulary
from manamind.encoding.state_encoder import StateEncoder
from manamind.integrations.rosettastone.policy import (
    POLICY_STATE_FEATURE_NAMES,
    PolicyNetwork,
    encode_action_card_ids,
    encode_hand_card_ids,
    encode_legal_actions,
    encode_policy_state,
    load_policy_weights,
)
from manamind.integrations.rosettastone.rollout import choose_baseline_action
from manamind.integrations.rosettastone.rosettastone import SimulatorSession
from train_selfplay import _device, _load_decks


@dataclass(frozen=True, slots=True)
class MatchResult:
    seed: int
    deck_pair: str
    policy_seat: int
    deck_order: str
    result: str
    policy_result: str
    actions: int


def _load_policy(
    path: Path, device: torch.device
) -> tuple[PolicyNetwork, CardCatalog, CardVocabulary]:
    payload = torch.load(path, map_location=device, weights_only=True)
    if payload.get("schema_version") not in (1, 2):
        raise ValueError("Unsupported self-play policy checkpoint schema")
    old_state_names = payload.get("state_feature_names", [])
    if not isinstance(old_state_names, list) or any(
        name not in POLICY_STATE_FEATURE_NAMES for name in old_state_names
    ):
        raise ValueError("Checkpoint state features do not match this version")
    if "card_catalog" in payload and "card_vocabulary" in payload:
        catalog = CardCatalog.from_dict(payload["card_catalog"])
        vocabulary = CardVocabulary.from_dict(payload["card_vocabulary"])
    else:
        project_root = Path(__file__).resolve().parent
        catalog_path = project_root / "data" / "cards" / "standard_current_enUS.json"
        if not catalog_path.is_file():
            catalog_path = project_root / "data" / "samples" / "sample_cards.json"
        catalog = CardCatalog.from_json(catalog_path)
        vocabulary = CardVocabulary(catalog)
    policy = PolicyNetwork(
        state_feature_count=len(POLICY_STATE_FEATURE_NAMES),
        card_count=vocabulary.card_count,
    ).to(device)
    load_policy_weights(policy, payload)
    policy.eval()
    return policy, catalog, vocabulary


def _play_match(
    policy: PolicyNetwork,
    opponent_policy: PolicyNetwork | None,
    encoder: StateEncoder,
    device: torch.device,
    decks: tuple[list[str], list[str], str, str, str, str],
    *,
    seed: int,
    policy_seat: int,
    swap_decks: bool,
    deck_pair: str,
    max_actions: int,
) -> MatchResult:
    deck1, deck2, class1, class2, game_format, _pair_name = decks
    if swap_decks:
        deck1, deck2 = deck2, deck1
        class1, class2 = class2, class1
    session = SimulatorSession(
        deck1,
        deck2,
        player1_class=class1,
        player2_class=class2,
        format=game_format,
        shuffle=True,
        random_start=True,
        random_seed=seed,
    )

    with torch.inference_mode():
        for action_index in range(max_actions):
            if session.is_complete:
                break
            state = session.observation("ACTIVE")
            actor_seat = 1 if session.observation("PLAYER1").active_player == "SELF" else 2
            actions = session.legal_actions()
            if not actions:
                raise RuntimeError(f"Evaluation game seed {seed} has no supported legal actions")

            acting_policy = policy if actor_seat == policy_seat else opponent_policy
            if acting_policy is not None:
                state_features = torch.as_tensor(
                    encode_policy_state(state, encoder), dtype=torch.float32, device=device
                )
                action_features = torch.as_tensor(
                    encode_legal_actions(actions), dtype=torch.float32, device=device
                )
                hand_ids = torch.as_tensor(
                    encode_hand_card_ids(state, encoder), dtype=torch.long, device=device
                )
                action_ids = torch.as_tensor(
                    encode_action_card_ids(actions, encoder), dtype=torch.long, device=device
                )
                selected = int(torch.argmax(acting_policy(
                    state_features, action_features, hand_ids, action_ids
                )).item())
                action = actions[selected]
            else:
                action = choose_baseline_action(state, actions)
            session.apply_action(action)
        else:
            if not session.is_complete:
                raise RuntimeError(f"Evaluation game seed {seed} exceeded {max_actions} actions")

    result = session.result
    if result not in {"PLAYER1_WIN", "PLAYER2_WIN", "DRAW"}:
        raise RuntimeError(f"Evaluation game returned unsupported result: {result!r}")
    if result == "DRAW":
        policy_result = "DRAW"
    elif (result == "PLAYER1_WIN") == (policy_seat == 1):
        policy_result = "WIN"
    else:
        policy_result = "LOSS"
    return MatchResult(
        seed, deck_pair, policy_seat, "swapped" if swap_decks else "original",
        result, policy_result, action_index + 1,
    )


def _play_baseline_control(
    decks: tuple[list[str], list[str], str, str, str, str],
    *,
    seed: int,
    swap_decks: bool,
    deck_pair: str,
    max_actions: int,
) -> MatchResult:
    """Run the fixed baseline against itself to expose seat/deck bias."""
    deck1, deck2, class1, class2, game_format, _pair_name = decks
    if swap_decks:
        deck1, deck2 = deck2, deck1
        class1, class2 = class2, class1
    session = SimulatorSession(
        deck1,
        deck2,
        player1_class=class1,
        player2_class=class2,
        format=game_format,
        shuffle=True,
        random_start=True,
        random_seed=seed,
    )
    for action_index in range(max_actions):
        if session.is_complete:
            break
        state = session.observation("ACTIVE")
        actions = session.legal_actions()
        if not actions:
            raise RuntimeError(f"Baseline control seed {seed} has no supported legal actions")
        session.apply_action(choose_baseline_action(state, actions))
    else:
        if not session.is_complete:
            raise RuntimeError(f"Baseline control seed {seed} exceeded {max_actions} actions")

    result = session.result
    if result not in {"PLAYER1_WIN", "PLAYER2_WIN", "DRAW"}:
        raise RuntimeError(f"Baseline control returned unsupported result: {result!r}")
    return MatchResult(
        seed, deck_pair, 0, "swapped" if swap_decks else "original",
        result, result, action_index + 1,
    )


def _wilson_interval(wins: int, decisive: int, z: float = 1.96) -> tuple[float, float] | None:
    if decisive == 0:
        return None
    rate = wins / decisive
    denominator = 1.0 + z * z / decisive
    center = (rate + z * z / (2.0 * decisive)) / denominator
    margin = z * math.sqrt(rate * (1.0 - rate) / decisive + z * z / (4.0 * decisive * decisive)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def summarize(results: list[MatchResult]) -> dict[str, Any]:
    counts = Counter(result.policy_result for result in results)
    wins, losses, draws = counts["WIN"], counts["LOSS"], counts["DRAW"]
    decisive = wins + losses
    interval = _wilson_interval(wins, decisive)
    return {
        "games": len(results),
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "decisive_win_rate": wins / decisive if decisive else None,
        "score_rate_with_half_draws": (wins + 0.5 * draws) / len(results) if results else None,
        "decisive_win_rate_wilson_95": list(interval) if interval else None,
        "by_policy_seat": {
            str(seat): dict(Counter(item.policy_result for item in results if item.policy_seat == seat))
            for seat in (1, 2)
        },
        "by_deck_order": {
            order: dict(Counter(item.policy_result for item in results if item.deck_order == order))
            for order in ("original", "swapped")
        },
        "by_deck_pair": {
            deck_pair: dict(Counter(item.policy_result for item in results if item.deck_pair == deck_pair))
            for deck_pair in sorted({item.deck_pair for item in results})
        },
        "mean_actions": float(np.mean([item.actions for item in results])) if results else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a policy against the fixed heuristic baseline.")
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/policy_selfplay_v1.pt"))
    parser.add_argument(
        "--opponent-checkpoint", type=Path,
        help="Optional second policy checkpoint for head-to-head comparison; otherwise use the heuristic baseline",
    )
    parser.add_argument("--decks", type=Path, default=Path("data/samples/rosettastone_test_decks.json"))
    parser.add_argument(
        "--pairs", type=int, default=10,
        help="Seed count; runs both policy seats and both deck orders per seed",
    )
    parser.add_argument("--seed", type=int, default=10_001, help="Use a seed range separate from training")
    parser.add_argument("--max-actions", type=int, default=2000)
    parser.add_argument("--report", type=Path, help="Optional new JSON report path; existing files are not overwritten")
    args = parser.parse_args()
    if args.pairs < 1 or args.max_actions < 1:
        parser.error("--pairs and --max-actions must be positive")
    if not args.checkpoint.is_file():
        parser.error(f"Policy checkpoint not found: {args.checkpoint}; run train_selfplay.py first")
    if args.report and args.report.exists():
        parser.error(f"Report already exists; choose a new path: {args.report}")

    device = _device()
    policy, catalog, vocabulary = _load_policy(args.checkpoint, device)
    opponent_loaded = _load_policy(args.opponent_checkpoint, device) if args.opponent_checkpoint else None
    if opponent_loaded and opponent_loaded[2].to_dict() != vocabulary.to_dict():
        parser.error("Policy checkpoints use different card vocabularies and cannot be compared")
    opponent_policy = opponent_loaded[0] if opponent_loaded else None
    encoder = StateEncoder(catalog, vocabulary)
    deck_pairs = _load_decks(args.decks)

    results: list[MatchResult] = []
    baseline_controls: list[MatchResult] = []
    for decks in deck_pairs:
        pair_label = decks[5]
        for pair_index in range(args.pairs):
            seed = args.seed + pair_index
            for swap_decks in (False, True):
                for policy_seat in (1, 2):
                    result = _play_match(
                        policy,
                        opponent_policy,
                        encoder,
                        device,
                        decks,
                        seed=seed,
                        policy_seat=policy_seat,
                        swap_decks=swap_decks,
                        deck_pair=pair_label,
                        max_actions=args.max_actions,
                    )
                    results.append(result)
                    print(
                        f"{pair_label} | seed {seed} | decks {'swapped' if swap_decks else 'original'} | "
                        f"policy seat {policy_seat} | {result.policy_result} "
                        f"({result.result}) | {result.actions} actions"
                    )
                control = _play_baseline_control(
                    decks, seed=seed, swap_decks=swap_decks, deck_pair=pair_label,
                    max_actions=args.max_actions
                )
                baseline_controls.append(control)
                print(
                    f"{pair_label} | seed {seed} | decks {control.deck_order} | baseline vs baseline | "
                    f"{control.result} | {control.actions} actions"
                )

    report = {
        "checkpoint": str(args.checkpoint),
        "deck_config": str(args.decks),
        "opponent": (
            str(args.opponent_checkpoint)
            if args.opponent_checkpoint else "fixed cheapest-minion/first-attack baseline"
        ),
        "evaluation_policy": "greedy argmax",
        "seed_start": args.seed,
        "paired_seeds": args.pairs,
        "deck_pairs": len(deck_pairs),
        "games_per_deck_pair": args.pairs * 4,
        "summary": summarize(results),
        "matches": [asdict(item) for item in results],
        "baseline_control": {
            "opponent": "same fixed heuristic baseline on both seats",
            "games": len(baseline_controls),
            "results": dict(Counter(item.result for item in baseline_controls)),
            "matches": [asdict(item) for item in baseline_controls],
        },
        "limitations": [
            "The selected Mother Drake list has focused card and combo coverage, but not exhaustive edge-case coverage.",
            "The current Standard ban list and complete card-effect pool are not yet audited.",
            "This weak fixed opponent and small sample do not establish ranked-play strength.",
        ],
    }
    print("SUMMARY " + json.dumps(report["summary"], ensure_ascii=False))
    print("BASELINE_CONTROL " + json.dumps(report["baseline_control"]["results"], ensure_ascii=False))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(f"Report saved to {args.report}")


if __name__ == "__main__":
    main()
