from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.research.algorithmic_advisor import advise


def _minion(card_id, attack, health, position, *, can_attack=False, mechanics=(), taunt=False,
            poisonous=False):
    card = CardFeatures(card_id=card_id, card_type="MINION", attack=attack, health=health,
                        mechanics=tuple(mechanics))
    return BoardEntity(card, attack, health, health, position, can_attack=can_attack,
                       taunt=taunt, poisonous=poisonous)


def _state(own=(), enemy=(), *, enemy_health=30, armor=0, opponent_secrets=0, hand=(), mana=0):
    return GameState(3, "SELF", PlayerObservation(30, available_mana=mana, hand_size=len(hand), board=tuple(own)),
                     PlayerObservation(enemy_health, armor=armor, secret_count=opponent_secrets, hero_divine_shield=False,
                                       board=tuple(enemy)), self_hand=tuple(hand))


def _face(source, attack, health):
    return {"type": "ATTACK", "source_kind": "MINION", "source_board_position": source,
            "source_attack": attack, "source_health": health,
            "target_kind": "HERO", "target_side": "OPPONENT"}


def _minion_attack(source, attack, health, target, target_attack, target_health, *, taunt=False):
    return {"type": "ATTACK", "source_kind": "MINION", "source_board_position": source,
            "source_attack": attack, "source_health": health,
            "target_kind": "MINION", "target_side": "OPPONENT",
            "target_board_position": target, "target_attack": target_attack,
            "target_health": target_health, "target_taunt": taunt}


def test_attack_only_lethal_survives_other_unassessed_menu_actions():
    state = _state([_minion("OWN", 3, 2, 1, can_attack=True)], [], enemy_health=2, armor=1)
    attack = _face(1, 3, 2)
    actions = [attack, {"type": "PLAY_CARD", "card_type": "SPELL"},
               {"type": "HERO_POWER"}, {"type": "END_TURN"}]
    advice = advise(state, actions, known_card_ids={"OWN"},
                    metadata={"OWN": state.self_player.board[0].card})
    # Independent arithmetic: 2 Health + 1 Armor is exactly 3 attack damage.
    assert advice.status == "RECOMMEND"
    assert advice.rule_type == "ATTACK_ONLY_LETHAL"
    assert advice.action == attack
    assert advice.unassessed_alternatives


def test_taunt_blocks_face_attack_but_direct_damage_fact_remains_scoped():
    own = [_minion("OWN", 3, 3, 1, can_attack=True)]
    enemy = [_minion("TAUNT", 1, 2, 1, taunt=True)]
    state = _state(own, enemy, enemy_health=2)
    action = _minion_attack(1, 3, 3, 1, 1, 2, taunt=True)
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids={"OWN", "TAUNT"},
                    metadata={entity.card.card_id: entity.card for entity in (*own, *enemy)})
    assert advice.action is None
    assert advice.facts[0]["type"] == "DIRECT_ATTACK_ARITHMETIC"
    assert advice.analysis_status == "PARTIAL"


def test_secret_and_unknown_hero_shield_prevent_proven_lethal():
    minion = _minion("OWN", 3, 2, 1, can_attack=True)
    state = _state([minion], [], enemy_health=2, opponent_secrets=1)
    advice = advise(state, [_face(1, 3, 2), {"type": "END_TURN"}], known_card_ids={"OWN"},
                    metadata={"OWN": minion.card})
    assert advice.action is None
    assert any(item["type"] == "ORDINARY_FACE_ATTACK_DAMAGE_POTENTIAL" for item in advice.facts)
    assert "OPPONENT_SECRET_REACTION_UNRESOLVED" in advice.blockers


def test_visible_face_damage_is_reported_even_when_not_lethal():
    minion = _minion("OWN", 9, 2, 1, can_attack=True)
    state = _state([minion], [], enemy_health=30)
    advice = advise(state, [_face(1, 9, 2), {"type": "END_TURN"}], known_card_ids={"OWN"},
                    metadata={"OWN": minion.card})
    fact = next(item for item in advice.facts if item["type"] == "ORDINARY_FACE_ATTACK_DAMAGE_POTENTIAL")
    assert fact["damage_if_all_visible_ordinary_attacks_resolve_unmodified"] == 9
    assert advice.status == "ABSTAIN"


def test_visible_hero_attack_contributes_to_potential_damage_not_proven_win():
    state = _state(enemy_health=5)
    hero_attack = {"type": "ATTACK", "source_kind": "HERO", "source_is_hero": True,
                   "source_board_position": -1, "source_attack": 2, "source_health": 30,
                   "target_kind": "HERO", "target_side": "OPPONENT"}
    advice = advise(state, [hero_attack, {"type": "END_TURN"}], known_card_ids=set(), metadata={})
    fact = next(item for item in advice.facts if item["type"] == "ORDINARY_FACE_ATTACK_DAMAGE_POTENTIAL")
    assert fact["damage_if_all_visible_ordinary_attacks_resolve_unmodified"] == 2
    assert advice.action is None


def test_unknown_or_combat_mechanics_do_not_claim_full_attack_resolution():
    attacker = _minion("OWN", 3, 3, 1, can_attack=True, mechanics=("NEW_TRIGGER",))
    enemy = _minion("ENEMY", 2, 3, 1)
    state = _state([attacker], [enemy])
    action = _minion_attack(1, 3, 3, 1, 2, 3)
    advice = advise(state, [action, {"type": "END_TURN"}, {"type": "HERO_POWER"}],
                    known_card_ids={"OWN", "ENEMY"},
                    metadata={"OWN": attacker.card, "ENEMY": enemy.card})
    fact = next(item for item in advice.facts if item["type"] == "DIRECT_ATTACK_ARITHMETIC")
    assert fact["target_reaches_zero_from_direct_damage"]
    assert fact["resolution"] == "FULL_RESOLUTION_UNRESOLVED"
    assert "UNKNOWN_MECHANIC_NEW_TRIGGER" in fact["resolution_blockers"]
    assert advice.action is None


def test_known_noncombat_mechanic_allows_only_direct_arithmetic():
    attacker = _minion("OWN", 3, 3, 1, can_attack=True, mechanics=("BATTLECRY",))
    enemy = _minion("ENEMY", 2, 3, 1)
    state = _state([attacker], [enemy])
    action = _minion_attack(1, 3, 3, 1, 2, 3)
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids={"OWN", "ENEMY"},
                    metadata={"OWN": attacker.card, "ENEMY": enemy.card})
    fact = next(item for item in advice.facts if item["type"] == "DIRECT_ATTACK_ARITHMETIC")
    assert fact["resolution"] == "DIRECT_DAMAGE_ONLY"
    assert advice.action is None


def test_unknown_metadata_blocks_full_resolution_but_keeps_arithmetic_fact():
    attacker = _minion("UNKNOWN", 3, 3, 1, can_attack=True)
    state = _state([attacker], [_minion("ENEMY", 2, 3, 1)])
    action = _minion_attack(1, 3, 3, 1, 2, 3)
    advice = advise(state, [action], known_card_ids=set(), metadata={})
    fact = next(item for item in advice.facts if item["type"] == "DIRECT_ATTACK_ARITHMETIC")
    assert fact["resolution"] == "FULL_RESOLUTION_UNRESOLVED"
    assert "CARD_METADATA_MISSING" in fact["resolution_blockers"]


def test_minion_estimates_distinguish_copies_and_all_legal_positions():
    card = CardFeatures(card_id="PLAIN", card_type="MINION", cost=3, attack=3, health=3)
    hand = (card, card)
    state = _state(hand=hand, mana=3)
    actions = [
        {"type": "PLAY_CARD", "card_type": "MINION", "card_id": "PLAIN", "card_cost": 3,
         "hand_index": hand_index, "play_position": position}
        for hand_index in (0, 1) for position in (1,)
    ] + [{"type": "END_TURN"}]
    advice = advise(state, actions, known_card_ids={"PLAIN"}, metadata={"PLAIN": card})
    assert advice.action is None
    assert len(advice.estimates) == 2
    assert {item["hand_index"] for item in advice.estimates} == {0, 1}
    assert len({item["candidate_id"] for item in advice.estimates}) == 2
    assert advice.analysis_status == "PARTIAL"


def test_play_position_bounds_follow_shared_board_insertion_contract():
    card = CardFeatures(card_id="PLAIN", card_type="MINION", cost=1, attack=1, health=1)
    own = [_minion("O1", 1, 1, 1), _minion("O2", 1, 1, 2)]
    state = _state(own, hand=(card,), mana=1)
    actions = [
        {"type": "PLAY_CARD", "card_type": "MINION", "card_id": "PLAIN", "card_cost": 1,
         "hand_index": 0, "play_position": position}
        for position in (1, 2, 3, 4)
    ]
    advice = advise(state, actions, known_card_ids={"PLAIN"}, metadata={"PLAIN": card})
    assert [item["play_position"] for item in advice.estimates] == [1, 2, 3]
    assert dict(advice.candidate_exclusions)["MENU_STRUCTURE_INVALID_PLAY_POSITION"] == 1


def test_full_board_and_missing_card_metadata_are_excluded():
    card = CardFeatures(card_id="UNKNOWN", card_type="MINION", cost=1, attack=1, health=1)
    board = [_minion(f"O{position}", 1, 1, position) for position in range(1, 8)]
    state = _state(board, hand=(card,), mana=1)
    action = {"type": "PLAY_CARD", "card_type": "MINION", "card_id": "UNKNOWN", "card_cost": 1,
              "hand_index": 0, "play_position": 1}
    advice = advise(state, [action], known_card_ids=set(), metadata={})
    assert advice.estimates == ()
    assert dict(advice.candidate_exclusions)["NO_OPEN_SHARED_BOARD_SLOT"] == 1


def test_spell_effect_is_not_inferred_from_card_metadata_or_id():
    spell = CardFeatures(card_id="KNOWN_SPELL", card_type="SPELL", cost=1)
    state = _state(hand=(spell,), mana=1)
    action = {"type": "PLAY_CARD", "card_type": "SPELL", "card_id": "KNOWN_SPELL",
              "card_cost": 1, "hand_index": 0, "play_position": 0}
    advice = advise(state, [action, {"type": "END_TURN"}], known_card_ids={"KNOWN_SPELL"},
                    metadata={"KNOWN_SPELL": spell})
    assert advice.status == "ABSTAIN"
    assert advice.estimates == ()
    assert "PLAY_CARD non-minion effects" in advice.unassessed_alternatives
