"""Create a small learnable toy dataset for the end-to-end ML pipeline."""

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity
from manamind.domain.game_state import GameState, PlayerObservation


@dataclass(frozen=True, slots=True)
class LabeledState:
    state: GameState
    target: float
    game_id: str = ""
    sample_id: str = ""
    perspective: str = "SELF"
    source: str = "synthetic"


def create_synthetic_catalog(base_catalog: CardCatalog) -> CardCatalog:
    """Extend a real/sample catalog with simple synthetic minion templates."""
    cards = list(base_catalog)
    classes = (
        "NEUTRAL", "MAGE", "WARRIOR", "DRUID", "HUNTER", "PALADIN", "ROGUE",
        "PRIEST", "WARLOCK", "SHAMAN", "DEMONHUNTER", "DEATHKNIGHT",
    )
    mechanics = ((), ("TAUNT",), ("RUSH",), ("DIVINE_SHIELD",), ("LIFESTEAL",))
    for index in range(20):
        cost = index % 8 + 1
        attack = (index * 3) % 9 + 1
        health = (index * 5) % 10 + 1
        cards.append(
            CardFeatures(
                card_id=f"SYN_MINION_{index:02d}",
                cost=cost,
                attack=attack,
                health=health,
                card_type="MINION",
                card_class=classes[index % len(classes)],
                mechanics=mechanics[index % len(mechanics)],
            )
        )
    return CardCatalog(cards)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _side_strength(player: PlayerObservation, known_hand_size: int) -> float:
    board_attack = sum(entity.current_attack for entity in player.board)
    board_health = sum(entity.current_health for entity in player.board)
    return (
        0.055 * player.hero_health
        + 0.025 * player.armor
        + 0.055 * player.available_mana
        + 0.12 * board_attack
        + 0.055 * board_health
        + 0.16 * known_hand_size
        + 0.025 * player.deck_size
        - 0.06 * player.fatigue
    )


def _create_board(rng: random.Random, card_pool: tuple[CardFeatures, ...]) -> tuple[BoardEntity, ...]:
    board_size = rng.randint(0, 7)
    entities: list[BoardEntity] = []
    for position in range(board_size):
        card = rng.choice(card_pool)
        current_attack = max(0, (card.attack or 0) + rng.randint(-1, 3))
        max_health = max(1, (card.health or 1) + rng.randint(-1, 3))
        current_health = rng.randint(1, max_health)
        entities.append(
            BoardEntity(
                card=card,
                current_attack=current_attack,
                current_health=current_health,
                max_health=max_health,
                board_position=position,
                taunt="TAUNT" in card.mechanics,
                divine_shield="DIVINE_SHIELD" in card.mechanics,
                rush="RUSH" in card.mechanics,
                lifesteal="LIFESTEAL" in card.mechanics,
                can_attack=rng.random() < 0.55,
            )
        )
    return tuple(entities)


def generate_synthetic_dataset(
    size: int,
    card_catalog: CardCatalog,
    seed: int = 42,
) -> list[LabeledState]:
    """Generate visible positions with outcomes sampled from a simple heuristic.

    The labels are intentionally synthetic: they validate the training pipeline,
    not real Hearthstone strategy.
    """
    if size < 1:
        raise ValueError("Dataset size must be at least 1")

    rng = random.Random(seed)
    card_pool = tuple(card for card in card_catalog if card.card_id.startswith("SYN_MINION_"))
    if not card_pool:
        raise ValueError("Use create_synthetic_catalog() before generating examples")

    classes = ("MAGE", "WARRIOR", "DRUID", "HUNTER", "PALADIN", "ROGUE", "PRIEST", "WARLOCK", "SHAMAN", "DEMONHUNTER", "DEATHKNIGHT")
    examples: list[LabeledState] = []

    for index in range(size):
        turn_number = rng.randint(1, 15)
        self_hand = tuple(rng.choice(card_pool) for _ in range(rng.randint(0, 10)))
        opponent_hand_size = rng.randint(0, 10)

        self_player = PlayerObservation(
            hero_health=rng.randint(1, 30),
            armor=rng.randint(0, 12),
            hero_attack=rng.randint(0, 5),
            max_mana=min(turn_number, 10),
            available_mana=rng.randint(0, min(turn_number, 10)),
            overloaded_mana=rng.randint(0, 2),
            pending_overload=rng.randint(0, 2),
            deck_size=rng.randint(0, 30),
            hand_size=len(self_hand),
            fatigue=rng.randint(0, 4),
            player_class=rng.choice(classes),
            board=_create_board(rng, card_pool),
        )
        opponent = PlayerObservation(
            hero_health=rng.randint(1, 30),
            armor=rng.randint(0, 12),
            hero_attack=rng.randint(0, 5),
            max_mana=min(turn_number, 10),
            available_mana=rng.randint(0, min(turn_number, 10)),
            overloaded_mana=rng.randint(0, 2),
            pending_overload=rng.randint(0, 2),
            deck_size=rng.randint(0, 30),
            hand_size=opponent_hand_size,
            fatigue=rng.randint(0, 4),
            player_class=rng.choice(classes),
            board=_create_board(rng, card_pool),
        )
        state = GameState(
            turn_number=turn_number,
            active_player=rng.choice(("SELF", "OPPONENT")),
            self_player=self_player,
            opponent=opponent,
            self_hand=self_hand,
            self_hand_known_count=len(self_hand),
        )

        advantage = _side_strength(self_player, len(self_hand)) - _side_strength(
            opponent, opponent_hand_size
        )
        active_turn_bonus = 0.4 if state.active_player == "SELF" else -0.4
        win_chance = _sigmoid(advantage + active_turn_bonus - 1.2)
        target = float(rng.random() < win_chance)
        examples.append(LabeledState(
            state=state,
            target=target,
            game_id=f"synthetic-{seed}-{index // 5:06d}",
            sample_id=f"synthetic-{seed}-{index:08d}",
        ))

    return examples


def save_synthetic_dataset(path: str | Path, examples: list[LabeledState]) -> None:
    """Save examples as JSON Lines for inspection and future reuse."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for example in examples:
            row = {
                "schema_version": 1,
                "game_id": example.game_id,
                "sample_id": example.sample_id,
                "perspective": example.perspective,
                "source": example.source,
                "state": asdict(example.state),
                "target": example.target,
            }
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_labeled_dataset(path: str | Path) -> list[LabeledState]:
    """Load validated JSONL examples while retaining match and sample metadata."""
    from manamind.domain import game_state_from_dict

    examples: list[LabeledState] = []
    with Path(path).open("r", encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("schema_version") != 1:
                    raise ValueError("unsupported or missing schema_version")
                target = float(row["target"])
                if not 0.0 <= target <= 1.0:
                    raise ValueError("target must be between 0 and 1")
                state = game_state_from_dict(row["state"])
                game_id = str(row["game_id"])
                sample_id = str(row["sample_id"])
                examples.append(LabeledState(
                    state=state, target=target, game_id=game_id, sample_id=sample_id,
                    perspective=str(row.get("perspective", "SELF")),
                    source=str(row.get("source", "unknown")),
                ))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid dataset row at {path}:{line_number}: {error}") from error
    if not examples:
        raise ValueError(f"Dataset is empty: {path}")
    return examples
