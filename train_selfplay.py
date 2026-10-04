"""Train a small action policy from terminal outcomes in RosettaStone self-play."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.distributions import Categorical

from manamind.cards.catalog import CardCatalog
from manamind.encoding.state_encoder import StateEncoder
from manamind.integrations.rosettastone.policy import (
    ACTION_FEATURE_NAMES,
    POLICY_ACTION_SCHEMA_VERSION,
    POLICY_STATE_FEATURE_NAMES,
    PolicyNetwork,
    encode_action_card_ids,
    encode_hand_card_ids,
    encode_legal_actions,
    encode_policy_state,
    load_policy_weights,
)
from manamind.integrations.rosettastone.rosettastone import (
    SimulatorSession,
    validate_deck,
    validate_decks,
)


@dataclass(slots=True)
class Decision:
    state_features: np.ndarray
    action_features: np.ndarray
    hand_card_ids: np.ndarray
    action_card_ids: np.ndarray
    selected_action: int
    actor_player: int
    reward: float


def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


DeckPair = tuple[list[str], list[str], str, str, str, str]


def _load_decks(path: Path) -> list[DeckPair]:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    game_format = config.get("format", "STANDARD")
    if "decks" in config:
        deck_specs = config["decks"]
        if not isinstance(deck_specs, list) or len(deck_specs) < 2:
            raise ValueError("A deck pool must contain at least two deck entries")
        normalized: list[tuple[str, list[str], str]] = []
        for index, spec in enumerate(deck_specs):
            name = str(spec.get("name", f"deck-{index + 1}"))
            player_class = str(spec["player_class"])
            cards = list(spec["cards"])
            errors = validate_deck(cards, player_class=player_class, format=game_format)
            if errors:
                raise ValueError(
                    f"Deck validation failed for {name}:\n" + "\n".join(errors)
                )
            normalized.append((name, cards, player_class))
        return [
            (cards1, cards2, class1, class2, game_format, f"{name1} vs {name2}")
            for index, (name1, cards1, class1) in enumerate(normalized)
            for name2, cards2, class2 in normalized[index + 1:]
        ]

    player1_class = config.get("player1_class", "WARLOCK")
    player2_class = config.get("player2_class", "PALADIN")
    deck1 = list(config["player1_deck"])
    deck2 = list(config["player2_deck"])
    errors = validate_decks(
        deck1, deck2,
        player1_class=player1_class,
        player2_class=player2_class,
        format=game_format,
    )
    if errors:
        raise ValueError("Deck validation failed:\n" + "\n".join(errors))
    return [(deck1, deck2, player1_class, player2_class, game_format,
             f"{player1_class} vs {player2_class}")]


def _play_game(
    policy: PolicyNetwork,
    encoder: StateEncoder,
    device: torch.device,
    decks: DeckPair,
    *,
    seed: int,
    max_actions: int,
) -> tuple[list[Decision], str, int]:
    deck1, deck2, class1, class2, game_format, _pair_name = decks
    # Alternate which deck occupies each engine seat so deck quality is not
    # permanently confounded with PLAYER1/PLAYER2.
    if seed % 2:
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
    decisions: list[Decision] = []

    policy.eval()
    with torch.inference_mode():
        for action_index in range(max_actions):
            if session.is_complete:
                break
            state = session.observation("ACTIVE")
            actor_player = (
                1 if session.observation("PLAYER1").active_player == "SELF" else 2
            )
            actions = session.legal_actions()
            if not actions:
                raise RuntimeError(
                    f"Game seed {seed} stopped at action {action_index}: "
                    "no supported legal action is available"
                )

            encoded_state = encode_policy_state(state, encoder)
            action_features = encode_legal_actions(actions)
            hand_card_ids = encode_hand_card_ids(state, encoder)
            action_card_ids = encode_action_card_ids(actions, encoder)
            state_tensor = torch.as_tensor(encoded_state, dtype=torch.float32, device=device)
            action_tensor = torch.as_tensor(action_features, dtype=torch.float32, device=device)
            hand_tensor = torch.as_tensor(hand_card_ids, dtype=torch.long, device=device)
            action_card_tensor = torch.as_tensor(action_card_ids, dtype=torch.long, device=device)
            distribution = Categorical(logits=policy(
                state_tensor, action_tensor, hand_tensor, action_card_tensor
            ))
            selected_index = int(distribution.sample().item())

            decisions.append(Decision(
                state_features=encoded_state,
                action_features=action_features,
                hand_card_ids=hand_card_ids,
                action_card_ids=action_card_ids,
                selected_action=selected_index,
                actor_player=actor_player,
                reward=0.0,
            ))
            session.apply_action(actions[selected_index])
        else:
            if not session.is_complete:
                raise RuntimeError(
                    f"Game seed {seed} did not finish within {max_actions} actions"
                )

    result = session.result
    if result not in {"PLAYER1_WIN", "PLAYER2_WIN", "DRAW"}:
        raise RuntimeError(f"Game seed {seed} returned unsupported result: {result!r}")

    player1_reward = 0.0 if result == "DRAW" else float(result == "PLAYER1_WIN") * 2.0 - 1.0
    for decision in decisions:
        decision.reward = player1_reward if decision.actor_player == 1 else -player1_reward
    return decisions, result, action_index + 1


def _train_batch(
    policy: PolicyNetwork,
    optimizer: torch.optim.Optimizer,
    decisions: list[Decision],
    device: torch.device,
    entropy_weight: float,
) -> tuple[float, float]:
    if not decisions:
        raise ValueError("No self-play decisions were collected")

    rewards = torch.tensor([decision.reward for decision in decisions], dtype=torch.float32)
    baseline = rewards.mean()
    advantages = (rewards - baseline).to(device)
    if float(advantages.abs().max()) == 0.0:
        return 0.0, 0.0

    policy.train()
    log_probabilities: list[torch.Tensor] = []
    entropies: list[torch.Tensor] = []
    for decision in decisions:
        state = torch.as_tensor(decision.state_features, dtype=torch.float32, device=device)
        actions = torch.as_tensor(decision.action_features, dtype=torch.float32, device=device)
        hand_ids = torch.as_tensor(decision.hand_card_ids, dtype=torch.long, device=device)
        action_ids = torch.as_tensor(decision.action_card_ids, dtype=torch.long, device=device)
        distribution = Categorical(logits=policy(state, actions, hand_ids, action_ids))
        log_probabilities.append(distribution.log_prob(torch.tensor(decision.selected_action, device=device)))
        entropies.append(distribution.entropy())

    log_probs = torch.stack(log_probabilities)
    entropy = torch.stack(entropies)
    loss = -(log_probs * advantages).mean() - entropy_weight * entropy.mean()
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    torch.nn.utils.clip_grad_norm_(policy.parameters(), max_norm=1.0)
    optimizer.step()
    return float(loss.detach().cpu()), float(entropy.mean().detach().cpu())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a legal-action policy by playing RosettaStone matches against itself."
    )
    parser.add_argument("--decks", type=Path, default=Path("data/samples/rosettastone_test_decks.json"))
    parser.add_argument("--games-per-cycle", type=int, default=8)
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--max-actions", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--entropy-weight", type=float, default=0.01)
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/policy_selfplay_v1.pt"))
    parser.add_argument("--resume", action="store_true", help="Continue from the selected policy checkpoint")
    args = parser.parse_args()

    if args.games_per_cycle < 2 or args.cycles < 1 or args.max_actions < 1:
        parser.error("Use at least 2 games per cycle, 1 cycle, and a positive action limit")

    checkpoint = args.checkpoint
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if checkpoint.exists() and not args.resume:
        parser.error(f"Checkpoint already exists; use --resume or choose a new path: {checkpoint}")

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = _device()
    project_root = Path(__file__).resolve().parent
    catalog_path = project_root / "data" / "cards" / "standard_current_enUS.json"
    if not catalog_path.is_file():
        catalog_path = project_root / "data" / "samples" / "sample_cards.json"
    encoder = StateEncoder(CardCatalog.from_json(catalog_path))
    policy = PolicyNetwork(
        state_feature_count=len(POLICY_STATE_FEATURE_NAMES),
        card_count=encoder.vocabulary.card_count,
    ).to(device)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=args.learning_rate)
    next_seed = args.seed
    starting_cycle = 0
    if args.resume:
        payload = torch.load(checkpoint, map_location=device, weights_only=True)
        if payload.get("schema_version") not in (1, 2):
            raise ValueError("Unsupported self-play policy checkpoint schema")
        old_state_names = payload.get("state_feature_names", [])
        if any(name not in POLICY_STATE_FEATURE_NAMES for name in old_state_names):
            raise ValueError("Checkpoint state-feature schema does not match this code")
        migrated = load_policy_weights(policy, payload)
        if "optimizer_state_dict" in payload and not migrated:
            optimizer.load_state_dict(payload["optimizer_state_dict"])
        elif migrated:
            print("Migrated legacy policy weights; starting a fresh optimizer state.")
        next_seed = int(payload.get("next_seed", args.seed))
        starting_cycle = int(payload.get("cycle", 0))
        if "torch_rng_state" in payload:
            torch.set_rng_state(payload["torch_rng_state"].cpu())
        if torch.cuda.is_available() and payload.get("cuda_rng_state_all"):
            torch.cuda.set_rng_state_all(
                [state.cpu() for state in payload["cuda_rng_state_all"]]
            )

    deck_pairs = _load_decks(args.decks)
    results = {"PLAYER1_WIN": 0, "PLAYER2_WIN": 0, "DRAW": 0}
    games_played = starting_cycle * args.games_per_cycle
    for cycle_offset in range(args.cycles):
        cycle = starting_cycle + cycle_offset
        cycle_decisions: list[Decision] = []
        for _ in range(args.games_per_cycle):
            decks = deck_pairs[games_played % len(deck_pairs)]
            decisions, result, action_count = _play_game(
                policy,
                encoder,
                device,
                decks,
                seed=next_seed,
                max_actions=args.max_actions,
            )
            next_seed += 1
            games_played += 1
            results[result] += 1
            cycle_decisions.extend(decisions)
            print(
                f"cycle {cycle + 1} | {decks[5]} | seed {next_seed - 1} | "
                f"{result} | {action_count} actions"
            )

        loss, entropy = _train_batch(
            policy,
            optimizer,
            cycle_decisions,
            device,
            args.entropy_weight,
        )
        policy.eval()
        torch.save({
            "schema_version": 2,
            "policy_action_schema_version": POLICY_ACTION_SCHEMA_VERSION,
            "policy_state_dict": policy.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "state_feature_names": list(POLICY_STATE_FEATURE_NAMES),
            "action_feature_names": list(ACTION_FEATURE_NAMES),
            "action_feature_count": len(ACTION_FEATURE_NAMES),
            "card_catalog_path": str(catalog_path),
            "card_catalog": encoder.catalog.to_dict(),
            "card_vocabulary": encoder.vocabulary.to_dict(),
            "cycle": cycle + 1,
            "next_seed": next_seed,
            "torch_rng_state": torch.get_rng_state(),
            "cuda_rng_state_all": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
        }, checkpoint)
        print(
            f"cycle {cycle + 1} update | policy loss {loss:.4f} | "
            f"entropy {entropy:.3f} | checkpoint {checkpoint}"
        )

    total = sum(results.values())
    print(f"Finished {total} games: {results}")
    print(f"Saved self-play policy to {checkpoint}")


if __name__ == "__main__":
    main()
