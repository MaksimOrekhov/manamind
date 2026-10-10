from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.research.algorithmic_advisor import advise

KNOWN = {"OWN", "ENEMY", "TAUNT"}


def _minion(card_id, attack, health, position, *, can_attack=False, taunt=False, poisonous=False):
    card = CardFeatures(card_id=card_id, card_type="MINION", attack=attack, health=health)
    return BoardEntity(card, attack, health, health, position, can_attack=can_attack,
                       taunt=taunt, poisonous=poisonous)


def _state(own, enemy, *, enemy_health=30, armor=0, opponent_secrets=0, hand=(), mana=0):
    return GameState(3, "SELF", PlayerObservation(30, available_mana=mana, hand_size=len(hand), board=tuple(own)),
                     PlayerObservation(enemy_health, armor=armor, secret_count=opponent_secrets,
                                       board=tuple(enemy)), self_hand=tuple(hand))


def _face(source, attack, health):
    return {"type": "ATTACK", "source_board_position": source, "source_attack": attack,
            "source_health": health, "target_kind": "HERO", "target_side": "OPPONENT"}


def _minion_attack(source, attack, health, target, target_attack, target_health, *, taunt=False):
    return {"type": "ATTACK", "source_board_position": source, "source_attack": attack,
            "source_health": health, "target_kind": "MINION", "target_side": "OPPONENT",
            "target_board_position": target, "target_attack": target_attack,
            "target_health": target_health, "target_taunt": taunt}


def test_arithmetic_lethal_counts_opponent_armor():
    state = _state([_minion("OWN", 3, 2, 1, can_attack=True)], [], enemy_health=2, armor=1)
    actions = [_face(1, 3, 2), {"type": "END_TURN"}]
    advice = advise(state, actions, known_card_ids=KNOWN)
    # Independent expected result: 2 Health + 1 Armor equals exactly 3 damage.
    assert advice.status == "RECOMMEND"
    assert advice.rule_type == "ATTACK_ONLY_LETHAL"
    assert advice.action == actions[0]


def test_taunt_menu_never_claims_all_face_lethal():
    own = [_minion("OWN", 3, 3, 1, can_attack=True)]
    enemy = [_minion("TAUNT", 1, 2, 1, taunt=True)]
    state = _state(own, enemy, enemy_health=2)
    action = _minion_attack(1, 3, 3, 1, 1, 2, taunt=True)
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids=KNOWN)
    assert advice.rule_type != "ATTACK_ONLY_LETHAL"


def test_hidden_opponent_secret_prevents_proven_lethal_claim():
    state = _state([_minion("OWN", 3, 2, 1, can_attack=True)], [], enemy_health=2,
                   opponent_secrets=1)
    advice = advise(state, [_face(1, 3, 2), {"type": "END_TURN"}], known_card_ids=KNOWN)
    assert advice.rule_type != "ATTACK_ONLY_LETHAL"


def test_favorable_trade_uses_current_combat_arithmetic():
    state = _state([_minion("OWN", 3, 3, 1, can_attack=True)],
                   [_minion("ENEMY", 2, 3, 1)])
    action = _minion_attack(1, 3, 3, 1, 2, 3)
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids=KNOWN)
    # Independent expected result: target reaches 0 Health; source retains 1.
    assert advice.status == "RECOMMEND"
    assert advice.rule_type == "ARITHMETIC_FAVORABLE_TRADE"
    assert advice.action == action
    assert advice.applicability == "PARTIAL"


def test_attack_that_loses_source_without_killing_target_is_warning_only():
    state = _state([_minion("OWN", 2, 1, 1, can_attack=True)],
                   [_minion("ENEMY", 2, 3, 1)])
    action = _minion_attack(1, 2, 1, 1, 2, 3)
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids=KNOWN)
    # Independent expected result: source dies; target retains 1 Health.
    assert advice.status == "ABSTAIN"
    assert advice.rule_type == "ARITHMETIC_BAD_TRADE_WARNING"
    assert advice.action is None


def test_unsupported_poisonous_combat_abstains():
    state = _state([_minion("OWN", 2, 2, 1, can_attack=True, poisonous=True)],
                   [_minion("ENEMY", 2, 4, 1)])
    action = _minion_attack(1, 2, 2, 1, 2, 4)
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids=KNOWN)
    assert advice.status == "ABSTAIN"
    assert advice.action is None


def test_simple_known_minion_play_is_only_an_approximate_partial_recommendation():
    card = CardFeatures(card_id="PLAIN_MINION", card_type="MINION", cost=3, current_cost=2,
                        attack=3, health=3)
    state = _state([], [], hand=[card], mana=2)
    action = {"type": "PLAY_CARD", "card_type": "MINION", "card_id": "PLAIN_MINION",
              "card_cost": 2, "card_attack": 3, "card_health": 3, "hand_index": 0,
              "play_position": 1}
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids={"PLAIN_MINION"},
                    metadata={"PLAIN_MINION": card})
    assert advice.status == "RECOMMEND"
    assert advice.rule_type == "SIMPLE_MINION_PLAY_ESTIMATE"
    assert advice.applicability == "APPROXIMATE_PARTIAL"
    assert advice.action == action
    assert any("не калибрована" in limit for limit in advice.limitations)


def test_unknown_card_metadata_does_not_get_a_minion_play_estimate():
    card = CardFeatures(card_id="UNLISTED_MINION", card_type="MINION", cost=3, attack=3, health=3)
    state = _state([], [], hand=[card], mana=3)
    action = {"type": "PLAY_CARD", "card_type": "MINION", "card_id": "UNLISTED_MINION",
              "card_cost": 3, "card_attack": 3, "card_health": 3, "hand_index": 0,
              "play_position": 1}
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids=set(), metadata={})
    assert advice.status == "ABSTAIN"
    assert advice.action is None


def test_spell_effect_is_not_inferred_from_card_metadata_or_id():
    spell = CardFeatures(card_id="KNOWN_SPELL", card_type="SPELL", cost=1, current_cost=1)
    state = _state([], [], hand=[spell], mana=1)
    action = {"type": "PLAY_CARD", "card_type": "SPELL", "card_id": "KNOWN_SPELL",
              "card_cost": 1, "hand_index": 0, "play_position": 0}
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids={"KNOWN_SPELL"},
                    metadata={"KNOWN_SPELL": spell})
    assert advice.status == "ABSTAIN"
    assert advice.action is None
