"""Convert a player-visible GameState into arrays for a value network."""

from dataclasses import dataclass

import numpy as np

from manamind.cards.catalog import CardCatalog
from manamind.cards.vocabulary import CardVocabulary
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.encoding.entity_encoder import EncodedZone, EntityEncoder, _normalise

PLAYER_NUMERIC_FEATURE_NAMES = (
    "hero_health",
    "armor",
    "hero_attack",
    "max_mana",
    "available_mana",
    "overloaded_mana",
    "pending_overload",
    "deck_size",
    "hand_size",
    "fatigue",
    "hero_power_ready",
)

GLOBAL_FEATURE_NAMES = (
    "turn_number",
    "self_turn",
    "opponent_turn",
    *(f"self_{name}" for name in PLAYER_NUMERIC_FEATURE_NAMES),
    "self_known_hand_size",
    *(f"opponent_{name}" for name in PLAYER_NUMERIC_FEATURE_NAMES),
    "opponent_known_cards_count",
)
STATE_ENCODING_SCHEMA_VERSION = 4


@dataclass(frozen=True, slots=True)
class EncodedGameState:
    """Tensor-ready arrays with all sides oriented as SELF and OPPONENT."""

    global_features: np.ndarray
    self_class_id: int
    opponent_class_id: int
    self_hand: EncodedZone
    self_board: EncodedZone
    opponent_board: EncodedZone
    opponent_known_cards: EncodedZone
    self_weapon: EncodedZone
    opponent_weapon: EncodedZone
    self_hero_power: EncodedZone
    opponent_hero_power: EncodedZone


def _encode_player_features(player: PlayerObservation) -> list[float]:
    values = (
        player.hero_health,
        player.armor,
        player.hero_attack,
        player.max_mana,
        player.available_mana,
        player.overloaded_mana,
        player.pending_overload,
        player.deck_size,
        player.hand_size,
        player.fatigue,
        0 if player.hero_power_ready is None else (1 if player.hero_power_ready else -1),
    )
    return [_normalise(value) for value in values]


class StateEncoder:
    """Encode only information available to the perspective player."""

    def __init__(
        self,
        catalog: CardCatalog,
        vocabulary: CardVocabulary | None = None,
    ) -> None:
        self.catalog = catalog
        self.vocabulary = vocabulary or CardVocabulary(catalog)
        self.entity_encoder = EntityEncoder(catalog, self.vocabulary)

    @property
    def global_feature_names(self) -> tuple[str, ...]:
        return GLOBAL_FEATURE_NAMES

    def encode(self, state: GameState) -> EncodedGameState:
        global_values = [
            _normalise(state.turn_number),
            float(state.active_player == "SELF"),
            float(state.active_player == "OPPONENT"),
            *_encode_player_features(state.self_player),
            _normalise(state.self_hand_known_count),
            *_encode_player_features(state.opponent),
            _normalise(len(state.opponent_known_cards)),
        ]

        return EncodedGameState(
            global_features=np.asarray(global_values, dtype=np.float32),
            self_class_id=self.vocabulary.player_class(state.self_player.player_class),
            opponent_class_id=self.vocabulary.player_class(state.opponent.player_class),
            self_hand=self.entity_encoder.encode_zone(state.self_hand, ordered=True),
            self_board=self.entity_encoder.encode_board(state.self_player.board),
            opponent_board=self.entity_encoder.encode_board(state.opponent.board),
            opponent_known_cards=self.entity_encoder.encode_zone(state.opponent_known_cards),
            self_weapon=self.entity_encoder.encode_optional_card(state.self_player.weapon),
            opponent_weapon=self.entity_encoder.encode_optional_card(state.opponent.weapon),
            self_hero_power=self.entity_encoder.encode_optional_card(state.self_player.hero_power),
            opponent_hero_power=self.entity_encoder.encode_optional_card(state.opponent.hero_power),
        )
