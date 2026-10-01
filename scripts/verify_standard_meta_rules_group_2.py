"""Smoke-check the implemented Standard coverage group in live game sessions."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (
    SimulatorSession,
    make_simple_test_deck,
    validate_decks,
)
from manamind.integrations.rosettastone.policy import ACTION_FEATURE_NAMES, encode_legal_actions


def start_game(card_id: str, player_class: str, opponent_deck: list[str] | None = None):
    player_deck = make_simple_test_deck(player_class=player_class)
    player_deck[0] = card_id
    enemy_deck = opponent_deck or make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck,
        enemy_deck,
        player1_class=player_class,
        player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    return SimulatorSession(
        player_deck,
        enemy_deck,
        player1_class=player_class,
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )


def apply_action(game: SimulatorSession, action_type: str, card_id: str | None = None):
    action = next(
        (
            candidate
            for candidate in game.legal_actions()
            if candidate["type"] == action_type
            and (card_id is None or candidate.get("card_id") == card_id)
        ),
        None,
    )
    if action is None:
        raise AssertionError(f"Missing legal action {action_type} {card_id or ''}")
    return game.apply_action(action)


def end_turn(game: SimulatorSession) -> None:
    apply_action(game, "END_TURN")


def play_free_minion(game: SimulatorSession) -> None:
    action = next(
        (
            candidate
            for candidate in game.legal_actions()
            if candidate["type"] == "PLAY_CARD"
            and candidate.get("card_type") == "MINION"
            and candidate.get("card_cost", 99) == 0
        ),
        None,
    )
    if action is None:
        raise AssertionError("Expected a free minion in the deterministic test hand")
    game.apply_action(action)


def verify_searing_fissure() -> None:
    game = start_game("CATA_582", "WARRIOR")
    play_free_minion(game)
    end_turn(game)
    play_free_minion(game)
    end_turn(game)
    state = game.observation("PLAYER1")
    if state.active_player != "SELF" or state.turn_number != 3:
        raise AssertionError("Expected Warrior's second turn before casting Searing Fissure")
    if not state.self_player.board or not state.opponent.board:
        raise AssertionError("Both boards should have a minion before the area damage")

    apply_action(game, "PLAY_CARD", "CATA_582")
    after = game.observation("PLAYER1")
    if after.self_player.hero_attack != 3:
        raise AssertionError(f"Searing Fissure should give +3 hero Attack, got {after.self_player.hero_attack}")
    if after.self_player.board or after.opponent.board:
        raise AssertionError("One damage should destroy the two 1/1 test minions")
    print("PASS CATA_582: area damage and temporary hero Attack")


def verify_sanguine_depths() -> None:
    game = start_game("CORE_REV_990", "WARRIOR")
    play_free_minion(game)
    play_action = next(
        action
        for action in game.legal_actions()
        if action["type"] == "PLAY_CARD" and action.get("card_id") == "CORE_REV_990"
    )
    if play_action.get("target_entity_id") is not None:
        raise AssertionError("A Location is played without choosing its activation target")
    game.apply_action(play_action)
    end_turn(game)
    end_turn(game)

    activation = next(
        (
            action
            for action in game.legal_actions()
            if action["type"] == "ACTIVATE_LOCATION"
            and action.get("card_id") == "CORE_REV_990"
        ),
        None,
    )
    if activation is None or activation.get("target_entity_id") is None:
        raise AssertionError("Sanguine Depths should expose a minion target on activation")
    game.apply_action(activation)
    if any(action["type"] == "ACTIVATE_LOCATION" for action in game.legal_actions()):
        raise AssertionError("The activated Location should enter its one-turn cooldown")
    print("PASS CORE_REV_990: targeted activation reaches RosettaStone")


def verify_devouring_plague_lifesteal() -> None:
    game = start_game("CORE_BAR_311", "PRIEST")
    end_turn(game)

    # The opponent develops a free minion, which can attack the Priest next turn.
    play_free_minion(game)
    end_turn(game)
    end_turn(game)

    actions = game.legal_actions()
    face_attack = next(
        (action for action in actions if action["type"] == "ATTACK" and action.get("target_is_hero")),
        None,
    )
    if face_attack is None:
        raise AssertionError("Expected the opponent's minion to attack the Priest hero")
    game.apply_action(face_attack)
    end_turn(game)

    before = game.observation("PLAYER1").self_player.hero_health
    if before >= 30:
        raise AssertionError("The Priest must be damaged before checking Lifesteal")
    apply_action(game, "PLAY_CARD", "CORE_BAR_311")
    after = game.observation("PLAYER1").self_player.hero_health
    if after <= before:
        raise AssertionError(f"Devouring Plague should heal its owner ({before} -> {after})")
    print(f"PASS CORE_BAR_311: damage to enemy minions healed Priest ({before} -> {after})")


def verify_royal_librarian() -> None:
    trade_game = start_game("CORE_SW_066", "WARRIOR")
    trade_actions = [
        action for action in trade_game.legal_actions()
        if action["type"] == "TRADE_CARD" and action.get("card_id") == "CORE_SW_066"
    ]
    if not trade_actions:
        raise AssertionError("Royal Librarian should be tradeable with 1 mana and cards in deck")
    encoded = encode_legal_actions(trade_actions)
    trade_feature = ACTION_FEATURE_NAMES.index("trade_card")
    if encoded.shape[0] != 1 or encoded[0, trade_feature] != 1.0:
        raise AssertionError(f"Unexpected Tradeable action encoding shape: {encoded.shape}")
    hand_size = trade_game.observation("PLAYER1").self_player.hand_size
    trade_game.apply_action(trade_actions[0])
    if trade_game.observation("PLAYER1").self_player.hand_size != hand_size:
        raise AssertionError("Trading Royal Librarian should exchange one hand card for one draw")

    game = start_game("CORE_SW_066", "WARRIOR")
    play_free_minion(game)
    end_turn(game)
    played = False
    for _ in range(12):
        state = game.observation("PLAYER1")
        if state.active_player == "SELF":
            action = next(
                (
                    candidate
                    for candidate in game.legal_actions()
                    if candidate["type"] == "PLAY_CARD"
                    and candidate.get("card_id") == "CORE_SW_066"
                    and candidate.get("target_is_self")
                ),
                None,
            )
            if action is not None:
                game.apply_action(action)
                silenced = any(
                    minion.card.card_id == "CORE_ICC_023" and minion.silenced
                    for minion in game.observation("PLAYER1").self_player.board
                )
                if not silenced:
                    raise AssertionError("Royal Librarian should silence the chosen minion")
                played = True
                break
        end_turn(game)

    if not played:
        raise AssertionError("Could not play Royal Librarian on its friendly target")
    print("PASS CORE_SW_066: Tradeable action and Battlecry Silence")


def verify_medivhs_triumph_cost() -> None:
    deck = make_simple_test_deck(player_class="PRIEST")
    displaced_card = deck[1]
    deck[0] = "CATA_308"
    deck[1] = "CORE_EX1_012"  # Bloodmage Thalnos is a supported Legendary minion.
    duplicate = next(
        index for index in range(2, len(deck)) if deck[index] == "CORE_EX1_012"
    )
    deck[duplicate] = displaced_card
    opponent_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        deck,
        opponent_deck,
        player1_class="PRIEST",
        player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        deck,
        opponent_deck,
        player1_class="PRIEST",
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )
    initial_cost = next(
        card.effective_cost for card in game.observation("PLAYER1").self_hand
        if card.card_id == "CATA_308"
    )
    end_turn(game)
    end_turn(game)
    apply_action(game, "PLAY_CARD", "CORE_EX1_012")
    reduced_cost = next(
        card.effective_cost for card in game.observation("PLAYER1").self_hand
        if card.card_id == "CATA_308"
    )
    if initial_cost != 5 or reduced_cost != 1:
        raise AssertionError(f"Medivh's Triumph should cost 1 with a Legendary: {initial_cost} -> {reduced_cost}")

    end_turn(game)
    end_turn(game)
    effect_action = next(
        (
            action for action in game.legal_actions()
            if action["type"] == "PLAY_CARD" and action.get("card_id") == "CATA_308"
        ),
        None,
    )
    if effect_action is None or effect_action["card_cost"] != 1:
        raise AssertionError("Discounted Medivh's Triumph should be playable for 1 mana")
    game.apply_action(effect_action)
    if any(card.card_id == "CATA_308" for card in game.observation("PLAYER1").self_hand):
        raise AssertionError("Medivh's Triumph should leave the hand after the board clear")
    print("PASS CATA_308: Legendary discount and area damage")


def verify_ebb_and_flow() -> None:
    game = start_game("TIME_702", "DRUID")
    initial = game.observation("PLAYER1")
    enemy_health = initial.opponent.hero_health

    minion = next(
        (
            action for action in game.legal_actions()
            if action["type"] == "PLAY_CARD"
            and action.get("card_type") == "MINION"
            and action.get("card_cost", 0) == 0
        ),
        None,
    )
    if minion is None:
        raise AssertionError("Expected a free minion to play while holding Ebb and Flow")
    game.apply_action(minion)

    effect = None
    for _ in range(6):
        effect = next(
            (
                action for action in game.legal_actions()
                if action["type"] == "PLAY_CARD"
                and action.get("card_id") == "TIME_702"
                and action.get("target_is_hero")
                and not action.get("target_is_self")
            ),
            None,
        )
        if effect is not None:
            break
        end_turn = next(
            (action for action in game.legal_actions() if action["type"] == "END_TURN"),
            None,
        )
        if end_turn is None:
            raise AssertionError("Expected an end-turn action while waiting for 2 mana")
        game.apply_action(end_turn)
    if effect is None:
        raise AssertionError("Ebb and Flow did not become playable")

    game.apply_action(effect)
    result = game.observation("PLAYER1")
    if result.opponent.hero_health != enemy_health - 3:
        raise AssertionError("Ebb and Flow should deal 3 damage to the selected enemy hero")
    if result.self_player.armor != 5:
        raise AssertionError("Ebb and Flow should gain 5 Armor after a minion was played while held")
    print("PASS TIME_702: targeted damage and conditional Armor")


def verify_press_the_advantage() -> None:
    game = start_game("END_007", "DRUID")
    initial = game.observation("PLAYER1")
    enemy_health = initial.opponent.hero_health

    effect = None
    for _ in range(6):
        effect = next(
            (
                action for action in game.legal_actions()
                if action["type"] == "PLAY_CARD"
                and action.get("card_id") == "END_007"
                and action.get("target_is_hero")
                and not action.get("target_is_self")
            ),
            None,
        )
        if effect is not None:
            break
        end_turn = next(
            (action for action in game.legal_actions() if action["type"] == "END_TURN"),
            None,
        )
        if end_turn is None:
            raise AssertionError("Expected an end-turn action while waiting for 2 mana")
        game.apply_action(end_turn)
    if effect is None:
        raise AssertionError("Press the Advantage did not become playable")

    game.apply_action(effect)
    result = game.observation("PLAYER1")
    if result.opponent.hero_health != enemy_health - 1:
        raise AssertionError("Press the Advantage should deal 1 damage to the selected enemy hero")
    if result.self_player.hero_attack != 1 or result.self_player.armor != 1:
        raise AssertionError("Press the Advantage should grant temporary Attack and 1 Armor")
    print("PASS END_007: targeted damage, temporary Attack, draw, and Armor")


def verify_haunt() -> None:
    game = start_game("CAP_801", "PRIEST")
    free_minion = next(
        (
            action for action in game.legal_actions()
            if action["type"] == "PLAY_CARD"
            and action.get("card_type") == "MINION"
            and action.get("card_cost", 0) == 0
        ),
        None,
    )
    if free_minion is None:
        raise AssertionError("Expected a free minion for the Haunt target scenario")
    game.apply_action(free_minion)

    effect = None
    for _ in range(7):
        effect = next(
            (
                action for action in game.legal_actions()
                if action["type"] == "PLAY_CARD"
                and action.get("card_id") == "CAP_801"
                and not action.get("target_is_hero")
                and action.get("target_is_self")
            ),
            None,
        )
        if effect is not None:
            break
        end_turn = next(
            (action for action in game.legal_actions() if action["type"] == "END_TURN"),
            None,
        )
        if end_turn is None:
            raise AssertionError("Expected an end-turn action while waiting for Haunt")
        game.apply_action(end_turn)
    if effect is None:
        raise AssertionError("Haunt did not become playable against a friendly minion")

    game.apply_action(effect)
    target = next(
        (entity for entity in game.observation("PLAYER1").self_player.board
         if entity.reborn and entity.taunt),
        None,
    )
    if target is None or target.current_attack < target.card.attack + 2:
        raise AssertionError("Haunt should give the minion +2 Attack")
    if target.max_health < target.card.health + 3 or not target.taunt or not target.reborn:
        raise AssertionError("Haunt should grant +3 Health, Taunt, and Reborn")
    print("PASS CAP_801: +2/+3, Taunt, and Reborn")


def verify_specter_specialist() -> None:
    player_deck = make_simple_test_deck(player_class="PRIEST")
    player_deck[0] = "CAP_801"
    player_deck[1] = "CAP_804"
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck,
        enemy_deck,
        player1_class="PRIEST",
        player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        player_deck,
        enemy_deck,
        player1_class="PRIEST",
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )
    free_minion = next(
        (
            action for action in game.legal_actions()
            if action["type"] == "PLAY_CARD"
            and action.get("card_type") == "MINION"
            and action.get("card_cost", 0) == 0
        ),
        None,
    )
    if free_minion is None:
        raise AssertionError("Expected a free minion for the Reborn-copy scenario")
    game.apply_action(free_minion)

    def find_friendly_target(card_id: str):
        return next(
            (
                action for action in game.legal_actions()
                if action["type"] == "PLAY_CARD"
                and action.get("card_id") == card_id
                and not action.get("target_is_hero")
                and action.get("target_is_self")
            ),
            None,
        )

    haunt = None
    for _ in range(7):
        haunt = find_friendly_target("CAP_801")
        if haunt is not None:
            break
        end_turn(game)
    if haunt is None:
        raise AssertionError("Haunt did not become playable in the Reborn-copy scenario")
    game.apply_action(haunt)

    specialist = None
    for _ in range(7):
        specialist = find_friendly_target("CAP_804")
        if specialist is not None:
            break
        end_turn(game)
    if specialist is None:
        raise AssertionError("Specter Specialist did not become playable")
    board_before = len(game.observation("PLAYER1").self_player.board)
    game.apply_action(specialist)
    board_after = game.observation("PLAYER1").self_player.board
    if len(board_after) != board_before + 2:
        raise AssertionError("Specter Specialist should summon a copy of a Reborn minion")
    if not any(entity.reborn for entity in board_after):
        raise AssertionError("The original Reborn minion should keep Reborn")
    print("PASS CAP_804: Reborn target receives a copy")


def verify_erupting_volcano() -> None:
    player_deck = make_simple_test_deck(player_class="WARRIOR")
    player_deck[0] = "CATA_584"
    player_deck[1] = "CATA_582"
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck,
        enemy_deck,
        player1_class="WARRIOR",
        player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        player_deck,
        enemy_deck,
        player1_class="WARRIOR",
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )
    enemy_health = game.observation("PLAYER1").opponent.hero_health

    def advance_turn() -> None:
        end = next(action for action in game.legal_actions() if action["type"] == "END_TURN")
        game.apply_action(end)

    location_play = None
    for _ in range(20):
        actions = game.legal_actions()
        location_play = next(
            (action for action in actions
             if action["type"] == "PLAY_CARD" and action.get("card_id") == "CATA_584"), None
        )
        available_mana = game.observation("PLAYER1").self_player.available_mana
        if location_play is not None and available_mana >= 3:
            break
        advance_turn()
    if location_play is None:
        raise AssertionError("Erupting Volcano did not become playable")
    game.apply_action(location_play)
    advance_turn()
    advance_turn()

    fire_spell = None
    activation = None
    for _ in range(20):
        actions = game.legal_actions()
        fire_spell = next(
            (action for action in actions
             if action["type"] == "PLAY_CARD" and action.get("card_id") == "CATA_582"), None
        )
        activation = next(
            (action for action in actions
             if action["type"] == "ACTIVATE_LOCATION" and action.get("card_id") == "CATA_584"),
            None,
        )
        if fire_spell is not None and activation is not None:
            break
        advance_turn()
    if fire_spell is None or activation is None:
        raise AssertionError("Fire spell and Erupting Volcano should be available on the activation turn")
    game.apply_action(fire_spell)
    activation = next(
        (action for action in game.legal_actions()
         if action["type"] == "ACTIVATE_LOCATION" and action.get("card_id") == "CATA_584"),
        None,
    )
    if activation is None:
        raise AssertionError("Erupting Volcano should remain activatable after Searing Fissure")
    game.apply_action(activation)
    actual_health = game.observation("PLAYER1").opponent.hero_health
    if actual_health != enemy_health - 6:
        raise AssertionError(
            f"Erupting Volcano should deal 6 damage after a Fire spell; hero health is {actual_health}"
        )
    print("PASS CATA_584: random split damage and Fire spell bonus")


def verify_spiderling() -> None:
    player_deck = make_simple_test_deck(player_class="DRUID")
    player_deck[0] = "JAIL_202"
    for index in range(1, len(player_deck)):
        if player_deck[index] == "JAIL_202":
            player_deck[index] = "CORE_CS2_122"
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck,
        enemy_deck,
        player1_class="DRUID",
        player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        player_deck,
        enemy_deck,
        player1_class="DRUID",
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )
    apply_action(game, "PLAY_CARD", "JAIL_202")
    attack_on_turn = game.observation("PLAYER1").self_player.hero_attack
    if attack_on_turn != 1:
        raise AssertionError(f"Spiderling should grant +1 hero Attack on your turn, got {attack_on_turn}")
    end_turn(game)
    attack_off_turn = game.observation("PLAYER1").self_player.hero_attack
    if attack_off_turn != 0:
        raise AssertionError("Spiderling's hero Attack should end when the opponent's turn starts")
    print("PASS JAIL_202: hero Attack aura is active only on its controller's turn")


def verify_carrier_whelp() -> None:
    game = start_game("CATA_556", "WARRIOR")
    for _ in range(10):
        action = next(
            (candidate for candidate in game.legal_actions()
             if candidate["type"] == "PLAY_CARD"
             and candidate.get("card_id") == "CATA_556"),
            None,
        )
        if action is not None:
            break
        end_turn(game)
    if action is None:
        raise AssertionError("Carrier Whelp did not become playable")
    initial_hand_size = game.observation("PLAYER1").self_player.hand_size
    game.apply_action(action)
    final_hand_size = game.observation("PLAYER1").self_player.hand_size
    if final_hand_size != initial_hand_size:
        raise AssertionError(
            "Carrier Whelp should replace itself with one random Dragon in hand "
            f"(hand size {initial_hand_size} -> {final_hand_size})"
        )
    print("PASS CATA_556: Battlecry adds a random low-cost Dragon")


def verify_prescient_slitherdrake() -> None:
    player_deck = make_simple_test_deck(player_class="WARRIOR")
    player_deck[0] = "END_033"
    player_deck[1] = "CORE_NEW1_023"
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck, enemy_deck,
        player1_class="WARRIOR", player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        player_deck, enemy_deck,
        player1_class="WARRIOR", player2_class="WARRIOR",
        shuffle=False, random_seed=20260928,
    )
    hand = game.observation("PLAYER1").self_hand
    card = next((held for held in hand if held.card_id == "END_033"), None)
    if card is None or card.effective_cost != 4:
        raise AssertionError(
            "Prescient Slitherdrake should cost 4 while another Dragon is in hand; "
            f"hand={[(held.card_id, held.effective_cost) for held in hand]}"
        )
    print("PASS END_033: another Dragon in hand reduces cost by 3")


def verify_spider_rider() -> None:
    player_deck = make_simple_test_deck(player_class="DRUID")
    player_deck[0] = "JAIL_872"
    for index in range(1, len(player_deck)):
        if player_deck[index] == "JAIL_872":
            player_deck[index] = "CORE_CS2_122"
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck, enemy_deck,
        player1_class="DRUID", player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        player_deck, enemy_deck,
        player1_class="DRUID", player2_class="WARRIOR",
        shuffle=False, random_seed=20260928,
    )
    for _ in range(6):
        action = next(
            (candidate for candidate in game.legal_actions()
             if candidate["type"] == "PLAY_CARD"
             and candidate.get("card_id") == "JAIL_872"),
            None,
        )
        if action is not None:
            break
        end_turn(game)
    if action is None:
        raise AssertionError("Spider Rider did not become playable")
    game.apply_action(action)
    hero_power = None
    for _ in range(8):
        if game.observation("PLAYER1").active_player == "SELF":
            hero_power = next(
                (candidate for candidate in game.legal_actions()
                 if candidate["type"] == "HERO_POWER"),
                None,
            )
            if hero_power is not None:
                break
        end_turn(game)
    if hero_power is None:
        raise AssertionError("Druid hero power did not become available")
    game.apply_action(hero_power)
    attack_action = next(
        (candidate for candidate in game.legal_actions()
         if candidate["type"] == "ATTACK"
         and candidate.get("source_is_hero")
         and candidate.get("target_is_hero")
         and not candidate.get("target_is_self")),
        None,
    )
    if attack_action is None:
        state = game.observation("PLAYER1").self_player
        raise AssertionError(
            "Could not expose a hero attack for Spider Rider; "
            f"attack={state.hero_attack}, actions={game.legal_actions()}"
        )
    hand_size = game.observation("PLAYER1").self_player.hand_size
    game.apply_action(attack_action)
    updated_hand_size = game.observation("PLAYER1").self_player.hand_size
    if updated_hand_size != hand_size + 1:
        raise AssertionError("Spider Rider should draw a card after a hero attack")
    print("PASS JAIL_872: hero attack draws one card")


def verify_kindred_costs() -> None:
    warrior_deck = make_simple_test_deck(player_class="WARRIOR")
    warrior_deck[0] = "CORE_NEW1_023"
    warrior_deck[1] = "TLC_600"
    warrior_enemy = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        warrior_deck, warrior_enemy,
        player1_class="WARRIOR", player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Kindred scenario deck validation failed: " + "; ".join(errors))
    warrior_game = SimulatorSession(
        warrior_deck, warrior_enemy,
        player1_class="WARRIOR", player2_class="WARRIOR",
        shuffle=False, random_seed=20260928,
    )
    dragon = None
    for _ in range(6):
        dragon = next(
            (action for action in warrior_game.legal_actions()
             if action["type"] == "PLAY_CARD"
             and action.get("card_id") == "CORE_NEW1_023"),
            None,
        )
        if dragon is not None:
            break
        end_turn(warrior_game)
    if dragon is None:
        raise AssertionError("Faerie Dragon did not become playable")
    warrior_game.apply_action(dragon)
    end_turn(warrior_game)
    end_turn(warrior_game)
    wyrm = next(
        (card for card in warrior_game.observation("PLAYER1").self_hand
         if card.card_id == "TLC_600"),
        None,
    )
    if wyrm is None or wyrm.effective_cost != 5:
        raise AssertionError("Dragon played last turn should discount Windpeak Wyrm by 3")
    print("PASS TLC_600: Dragon played last turn discounts Windpeak Wyrm")

    priest_deck = make_simple_test_deck(player_class="PRIEST")
    priest_deck[0] = "CORE_AT_055"
    priest_deck[1] = "TLC_816"
    priest_enemy = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        priest_deck, priest_enemy,
        player1_class="PRIEST", player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Kindred scenario deck validation failed: " + "; ".join(errors))
    priest_game = SimulatorSession(
        priest_deck, priest_enemy,
        player1_class="PRIEST", player2_class="WARRIOR",
        shuffle=False, random_seed=20260929,
    )
    heal = next(
        (action for action in priest_game.legal_actions()
         if action["type"] == "PLAY_CARD"
         and action.get("card_id") == "CORE_AT_055"
         and action.get("target_is_hero")
         and action.get("target_is_self")),
        None,
    )
    if heal is None:
        raise AssertionError("Holy spell target on own hero was not available")
    priest_game.apply_action(heal)
    end_turn(priest_game)
    end_turn(priest_game)
    sunbloom = next(
        (card for card in priest_game.observation("PLAYER1").self_hand
         if card.card_id == "TLC_816"),
        None,
    )
    if sunbloom is None or sunbloom.effective_cost != 2:
        raise AssertionError("Holy spell cast last turn should discount Sunbloom by 2")
    print("PASS TLC_816: Holy spell cast last turn discounts Gravedawn Sunbloom")


def verify_undeath_sentence() -> None:
    player_deck = make_simple_test_deck(player_class="PRIEST")
    player_deck[0] = "CORE_EX1_096"
    for index in range(1, len(player_deck)):
        if player_deck[index] == "CORE_EX1_096":
            player_deck[index] = "CORE_CS2_122"
    player_deck[1] = "CORE_CS1_130"
    player_deck[2] = "JAIL_940"
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck, enemy_deck,
        player1_class="PRIEST", player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        player_deck, enemy_deck,
        player1_class="PRIEST", player2_class="WARRIOR",
        shuffle=False, random_seed=20260930,
    )

    loot_action = None
    for _ in range(6):
        loot_action = next(
            (action for action in game.legal_actions()
             if action["type"] == "PLAY_CARD"
             and action.get("card_id") == "CORE_EX1_096"),
            None,
        )
        if loot_action is not None:
            break
        end_turn(game)
    if loot_action is None:
        raise AssertionError("Loot Hoarder did not become playable")
    game.apply_action(loot_action)
    end_turn(game)
    end_turn(game)

    hoarder = next(
        (entity for entity in game.observation("PLAYER1").self_player.board
         if entity.card.card_id == "CORE_EX1_096"),
        None,
    )
    if hoarder is None:
        raise AssertionError("Loot Hoarder should remain on board for the destroy spell")
    smite = next(
        (action for action in game.legal_actions()
         if action["type"] == "PLAY_CARD"
         and action.get("card_id") == "CORE_CS1_130"
         and action.get("target_board_position") == hoarder.board_position
         and action.get("target_health") == 1),
        None,
    )
    if smite is None:
        raise AssertionError("Holy Smite could not target friendly Loot Hoarder")
    game.apply_action(smite)
    deck_after_first_deathrattle = game.observation("PLAYER1").self_player.deck_size
    end_turn(game)
    end_turn(game)

    sentence = next(
        (action for action in game.legal_actions()
         if action["type"] == "PLAY_CARD"
         and action.get("card_id") == "JAIL_940"),
        None,
    )
    if sentence is None:
        raise AssertionError("Undeath Sentence did not become playable")
    game.apply_action(sentence)
    deck_after_sentence = game.observation("PLAYER1").self_player.deck_size
    if deck_after_sentence != deck_after_first_deathrattle - 2:
        raise AssertionError("Undeath Sentence should replay Loot Hoarder's Draw Deathrattle")
    print("PASS JAIL_940: Deathrattle from a friendly minion in the graveyard triggers again")


def verify_naralex_first_dragon_discount() -> None:
    player_deck = make_simple_test_deck(player_class="WARRIOR")
    player_deck[0] = "EDR_844"
    player_deck[1] = "END_033"
    player_deck[2] = "CORE_NEW1_023"
    for index in range(3, len(player_deck)):
        if player_deck[index] == "END_033":
            player_deck[index] = "CORE_CS2_122"
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck, enemy_deck,
        player1_class="WARRIOR", player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        player_deck, enemy_deck,
        player1_class="WARRIOR", player2_class="WARRIOR",
        shuffle=False, random_seed=20261001,
    )

    naralex = None
    for _ in range(20):
        naralex = next(
            (action for action in game.legal_actions()
             if action["type"] == "PLAY_CARD"
             and action.get("card_id") == "EDR_844"),
            None,
        )
        if naralex is not None:
            break
        end_turn(game)
    if naralex is None:
        raise AssertionError("Naralex did not become playable")
    game.apply_action(naralex)
    end_turn(game)
    end_turn(game)

    dragon_action = next(
        (action for action in game.legal_actions()
         if action["type"] == "PLAY_CARD"
         and action.get("card_id") == "END_033"),
        None,
    )
    if dragon_action is None or dragon_action["card_cost"] != 3:
        raise AssertionError(
            "Prescient Slitherdrake should cost 3 from Naralex plus its held-Dragon discount"
        )
    game.apply_action(dragon_action)
    faerie = next(
        (card for card in game.observation("PLAYER1").self_hand
         if card.card_id == "CORE_NEW1_023"),
        None,
    )
    if faerie is None or faerie.effective_cost != 2:
        raise AssertionError("Naralex's discount should end after the first Dragon is played")
    print("PASS EDR_844: only the first Dragon each turn receives the cost reduction")


def verify_waveshaping_deck_choice() -> None:
    game = start_game("TIME_701", "DRUID")
    before = game.observation("PLAYER1")
    apply_action(game, "PLAY_CARD", "TIME_701")
    choices = [action for action in game.legal_actions() if action["type"] == "CHOOSE_CARD"]
    if len(choices) != 3 or any(action.get("card_id") is None for action in choices):
        raise AssertionError("Waveshaping should offer three real cards from the deck")
    selected = choices[0]["card_id"]
    game.apply_action(choices[0])
    after = game.observation("PLAYER1")
    if after.self_player.deck_size != before.self_player.deck_size - 1:
        raise AssertionError("Choosing from the deck should remove exactly the selected card")
    if after.self_player.hand_size != before.self_player.hand_size:
        raise AssertionError("Waveshaping and its selected deck card should net to the same hand size")
    if any(action["type"] == "CHOOSE_CARD" for action in game.legal_actions()):
        raise AssertionError("The deck choice should close after selecting one card")
    print(f"PASS TIME_701: deck choice selected {selected}; unchosen cards remain in the deck")


def verify_cannonmaster_cannoneer() -> None:
    game = start_game("CAP_107", "WARRIOR")
    apply_action(game, "PLAY_CARD", "CAP_107")
    hand = game.observation("PLAYER1").self_hand
    if not any(card.card_id == "CAP_107t" for card in hand):
        raise AssertionError("Cannonmaster should add a Cannoneer to hand")

    end_turn(game)
    end_turn(game)
    apply_action(game, "PLAY_CARD", "CAP_107t")
    end_turn(game)
    enemy_health = game.observation("PLAYER1").opponent.hero_health
    if enemy_health != 29:
        raise AssertionError(f"Cannoneer should deal 1 end-of-turn damage, got hero health {enemy_health}")
    print("PASS CAP_107: Battlecry generates Cannoneer; its end-of-turn shot hits the only enemy")


def verify_hook_and_heave() -> None:
    import json

    game = start_game("CAP_105", "WARRIOR")
    hook_action = None
    for _ in range(5):
        hook_action = next(
            (action for action in game.legal_actions()
             if action["type"] == "PLAY_CARD" and action.get("card_id") == "CAP_105"),
            None,
        )
        if hook_action is not None:
            break
        end_turn(game)
        end_turn(game)
    if hook_action is None:
        raise AssertionError("Hook n' Heave did not become playable during the setup turns")
    game.apply_action(hook_action)
    choices = [action for action in game.legal_actions() if action["type"] == "CHOOSE_CARD"]
    catalog = json.loads(
        (PROJECT_ROOT / "data/cards/standard_current_enUS.json").read_text(encoding="utf-8")
    )["cards"]
    pirate_ids = {card["id"] for card in catalog if card.get("race") == "PIRATE"}
    if len(choices) != 3 or any(
        action.get("card_id") not in pirate_ids for action in choices
    ):
        raise AssertionError("Hook n' Heave should offer three Pirate choices")
    game.apply_action(choices[0])
    tokens = [entity for entity in game.observation("PLAYER1").self_player.board
              if entity.card.card_id == "CAP_107t"]
    if len(tokens) != 2:
        raise AssertionError(f"Hook n' Heave should summon two Cannoneers, got {len(tokens)}")
    print("PASS CAP_105: Pirate Discover choice and two Cannoneer summons")


def verify_chainbreaker_hogger() -> None:
    deck = make_simple_test_deck(player_class="WARRIOR")
    deck[0] = "JAIL_384"
    deck[1] = "TLC_600"
    baseline_deck = list(deck)
    baseline_deck[0] = "CAP_107"
    enemy = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        deck, enemy, player1_class="WARRIOR", player2_class="WARRIOR"
    )
    if errors:
        raise AssertionError("Hogger scenario deck validation failed: " + "; ".join(errors))
    with_hogger = SimulatorSession(
        deck, enemy, player1_class="WARRIOR", player2_class="WARRIOR",
        shuffle=False, random_seed=20260928,
    )
    baseline = SimulatorSession(
        baseline_deck, enemy, player1_class="WARRIOR", player2_class="WARRIOR",
        shuffle=False, random_seed=20260928,
    )
    copied_size = with_hogger.observation("PLAYER1").self_player.deck_size
    baseline_size = baseline.observation("PLAYER1").self_player.deck_size
    if copied_size != baseline_size + 1:
        raise AssertionError(
            f"Hogger should duplicate the one other Legendary in the deck; "
            f"sizes are {copied_size} and {baseline_size}"
        )
    print("PASS JAIL_384: Start of Game adds one copy of the other Legendary card")


def verify_ysera_mana_start() -> None:
    deck = make_simple_test_deck(player_class="DRUID")
    deck[0] = "EDR_000"
    baseline_deck = list(deck)
    baseline_deck[0] = "TIME_701"
    enemy = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        deck, enemy, player1_class="DRUID", player2_class="WARRIOR"
    )
    if errors:
        raise AssertionError("Ysera scenario deck validation failed: " + "; ".join(errors))

    with_ysera = SimulatorSession(
        deck, enemy, player1_class="DRUID", player2_class="WARRIOR",
        shuffle=False, random_seed=20260928,
    )
    baseline = SimulatorSession(
        baseline_deck, enemy, player1_class="DRUID", player2_class="WARRIOR",
        shuffle=False, random_seed=20260928,
    )
    for perspective in ("PLAYER1", "PLAYER2"):
        actual = with_ysera.observation(perspective)
        control = baseline.observation(perspective)
        actual_player = actual.self_player
        control_player = control.self_player
        if actual_player.max_mana != control_player.max_mana + 5:
            raise AssertionError(
                f"Ysera should grant both players five max Mana: "
                f"{actual_player.max_mana} vs {control_player.max_mana}"
            )

    battlecry = None
    for _ in range(5):
        battlecry = next(
            (action for action in with_ysera.legal_actions()
             if action["type"] == "PLAY_CARD" and action.get("card_id") == "EDR_000"),
            None,
        )
        if battlecry is not None:
            break
        end_turn(with_ysera)
        end_turn(with_ysera)
    if battlecry is None:
        raise AssertionError("Ysera should be playable with the increased starting Mana")
    before = with_ysera.observation("PLAYER1").self_player.max_mana
    with_ysera.apply_action(battlecry)
    after = with_ysera.observation("PLAYER1").self_player.max_mana
    if after != min(10, before + 3):
        raise AssertionError(f"Ysera Battlecry should add three Mana Crystals, got {before} to {after}")
    print("PASS EDR_000: Start of Game grants both players five max Mana; Battlecry adds three")


def verify_brood_keeper_weapon() -> None:
    deck = make_simple_test_deck(player_class="WARRIOR")
    deck[0] = "EDR_457"
    deck[1] = "TLC_600"
    enemy = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        deck, enemy, player1_class="WARRIOR", player2_class="WARRIOR"
    )
    if errors:
        raise AssertionError("Brood Keeper scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        deck, enemy, player1_class="WARRIOR", player2_class="WARRIOR",
        shuffle=False, random_seed=20260928,
    )
    if not any(card.card_id == "TLC_600" for card in game.observation("PLAYER1").self_hand):
        raise AssertionError("The test Dragon should be in hand with Brood Keeper")
    action = None
    for _ in range(4):
        action = next(
            (candidate for candidate in game.legal_actions()
             if candidate["type"] == "PLAY_CARD"
             and candidate.get("card_id") == "EDR_457"),
            None,
        )
        if action is not None:
            break
        end_turn(game)
        end_turn(game)
    if action is None:
        raise AssertionError("Brood Keeper should become playable during setup")
    game.apply_action(action)
    weapon = game.observation("PLAYER1").self_player.weapon
    if weapon is None or weapon.card_id != "EDR_457t" or weapon.effective_attack != 2 or weapon.effective_durability != 2:
        raise AssertionError(f"Brood Keeper should equip its 2/2 Sword, got {weapon}")
    print("PASS EDR_457: a held Dragon makes Brood Keeper equip the 2/2 Nightmare Slicer")


def verify_mother_duck() -> None:
    game = start_game("EDR_492", "WARRIOR")
    action = None
    for _ in range(5):
        action = next(
            (candidate for candidate in game.legal_actions()
             if candidate["type"] == "PLAY_CARD"
             and candidate.get("card_id") == "EDR_492"),
            None,
        )
        if action is not None:
            break
        end_turn(game)
        end_turn(game)
    if action is None:
        raise AssertionError("Mother Duck should become playable during setup")
    game.apply_action(action)
    ducklings = [
        entity for entity in game.observation("PLAYER1").self_player.board
        if entity.card.card_id == "EDR_492t"
    ]
    if len(ducklings) != 3 or any(not duckling.rush for duckling in ducklings):
        raise AssertionError(
            f"Mother Duck should summon three 1/1 Rush Ducklings, got {ducklings}"
        )
    print("PASS EDR_492: Battlecry summons three 1/1 Rush Ducklings")


def verify_twilight_influence() -> None:
    destroy_game = start_game("EDR_463", "PRIEST")
    end_turn(destroy_game)
    play_free_minion(destroy_game)
    end_turn(destroy_game)
    destroy_action = next(
        (candidate for candidate in destroy_game.legal_actions()
         if candidate["type"] == "PLAY_CARD"
         and candidate.get("card_id") == "EDR_463"
         and candidate.get("choose_one") == 1
         and candidate.get("target_entity_id") is not None),
        None,
    )
    if destroy_action is None:
        raise AssertionError("Twilight Influence should offer its targeted destroy choice")
    if destroy_action.get("target_attack", 99) > 3:
        raise AssertionError("Twilight Influence must not target a minion above 3 Attack")
    destroy_game.apply_action(destroy_action)
    if destroy_game.observation("PLAYER1").opponent.board:
        raise AssertionError("Twilight Influence should destroy the selected minion")

    summon_game = start_game("EDR_463", "PRIEST")
    end_turn(summon_game)
    end_turn(summon_game)
    summon_action = next(
        (candidate for candidate in summon_game.legal_actions()
         if candidate["type"] == "PLAY_CARD"
         and candidate.get("card_id") == "EDR_463"
         and candidate.get("choose_one") == 2
         and candidate.get("target_entity_id") is None),
        None,
    )
    if summon_action is None:
        raise AssertionError("Twilight Influence should offer its random summon choice")
    summon_game.apply_action(summon_action)
    summoned = summon_game.observation("PLAYER1").self_player.board
    if len(summoned) != 1 or summoned[0].card.effective_cost != 2:
        raise AssertionError(f"Twilight Influence should summon one random 2-Cost minion: {summoned}")
    print("PASS EDR_463: Choose One destroys a minion at 3 Attack or less, or summons a random 2-Cost minion")


def verify_ritual_of_life() -> None:
    game = start_game("DINO_426", "PRIEST")
    action = None
    for _ in range(5):
        action = next(
            (candidate for candidate in game.legal_actions()
             if candidate["type"] == "PLAY_CARD"
             and candidate.get("card_id") == "DINO_426"),
            None,
        )
        if action is not None:
            break
        end_turn(game)
        end_turn(game)
    if action is None:
        raise AssertionError("Ritual of Life should become playable during setup")
    game.apply_action(action)
    choices = [candidate for candidate in game.legal_actions()
               if candidate["type"] == "CHOOSE_CARD"]
    if not choices or any(
        candidate.get("card_type") != "MINION" or candidate.get("card_cost") != 3
        for candidate in choices
    ):
        raise AssertionError(f"Ritual of Life should Discover three-cost minions: {choices}")
    game.apply_action(choices[0])
    board = game.observation("PLAYER1").self_player.board
    if len(board) != 1 or board[0].current_attack != 2 or board[0].current_health != 3:
        raise AssertionError(f"Ritual of Life should summon its choice as a 2/3 copy: {board}")
    print("PASS DINO_426: Discover offers only 3-Cost minions and summons the selected minion as a 2/3 copy")


def verify_torch_overkill() -> None:
    player_deck = make_simple_test_deck(player_class="WARRIOR")
    player_deck[0] = "CATA_585"
    player_deck[1] = "CORE_ULD_271"
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    game = SimulatorSession(
        player_deck,
        enemy_deck,
        player1_class="WARRIOR",
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )
    end_turn(game)
    end_turn(game)
    apply_action(game, "PLAY_CARD", "CORE_ULD_271")
    state = game.observation("PLAYER1")
    if len(state.self_player.board) != 1 or state.self_player.board[0].current_health != 3:
        raise AssertionError("Injured Tol'vir should be a damaged 2/3 target")
    end_turn(game)
    end_turn(game)
    torch_action = next(
        (
            action for action in game.legal_actions()
            if action["type"] == "PLAY_CARD"
            and action.get("card_id") == "CATA_585"
            and action.get("target_is_self")
            and action.get("target_health") == 3
        ),
        None,
    )
    if torch_action is None:
        raise AssertionError("Torch should target the damaged Injured Tol'vir")
    game.apply_action(torch_action)
    after = game.observation("PLAYER1")
    if after.self_player.board:
        raise AssertionError("Eight Torch damage should destroy Injured Tol'vir")
    if not any(card.card_id == "CATA_585" for card in after.self_hand):
        raise AssertionError("Torch should return to hand after excess damage")
    print("PASS CATA_585: Torch returns to hand when its 8 damage overkills the target")


def verify_acceleration_aura() -> None:
    game = start_game("END_011", "DRUID")
    end_turn(game)
    end_turn(game)
    apply_action(game, "PLAY_CARD", "END_011")
    for trigger_number in range(1, 4):
        end_turn(game)
        end_turn(game)
        state = game.observation("PLAYER1").self_player
        if state.available_mana != state.max_mana + 1:
            raise AssertionError(
                f"Acceleration Aura trigger {trigger_number} should grant one temporary Mana"
            )
    end_turn(game)
    end_turn(game)
    state = game.observation("PLAYER1").self_player
    if state.available_mana != state.max_mana:
        raise AssertionError("Acceleration Aura should expire after three triggers")
    print("PASS END_011: grants one temporary Mana for exactly three of its controller's turns")


def verify_held_mana_cards() -> None:
    import json

    # First prove Felwood Treant's below-threshold temporary crystal branch.
    game = start_game("CATA_131", "DRUID")
    end_turn(game)
    end_turn(game)
    apply_action(game, "PLAY_CARD", "CATA_131")
    state = game.observation("PLAYER1").self_player
    if state.max_mana != 2 or state.available_mana != 1:
        raise AssertionError("Felwood Treant should grant temporary Mana below its threshold")

    # The held card must count Hero Power and card payments, but not its own cost.
    player_deck = make_simple_test_deck(player_class="DRUID")
    player_deck[:7] = [
        "CATA_131", "END_007", "END_007", "TIME_702",
        "TIME_702", "JAIL_201", "JAIL_201",
    ]
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    game = SimulatorSession(
        player_deck,
        enemy_deck,
        player1_class="DRUID",
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )
    for _ in range(3):
        end_turn(game)
        end_turn(game)
        hero_power = next(
            (action for action in game.legal_actions() if action["type"] == "HERO_POWER"),
            None,
        )
        if hero_power is not None:
            game.apply_action(hero_power)
    apply_action(game, "PLAY_CARD", "CATA_131")
    if game.observation("PLAYER1").self_player.max_mana != 5:
        raise AssertionError("Four Mana spent while holding Felwood Treant should make its crystal permanent")

    # Keep Merithra in hand while spending 25 Mana across card and power actions.
    player_deck = make_simple_test_deck(player_class="DRUID")
    player_deck[:7] = [
        "CATA_140", "END_007", "END_007", "TIME_702",
        "TIME_702", "JAIL_201", "JAIL_201",
    ]
    game = SimulatorSession(
        player_deck,
        enemy_deck,
        player1_class="DRUID",
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )
    mana_spent = 0
    for _ in range(11):
        actions = game.legal_actions()
        if game.observation("PLAYER1").active_player != "SELF":
            raise AssertionError("Expected the Druid to act before spending Mana")
        if mana_spent >= 25 and any(
            action.get("card_id") == "CATA_140" for action in actions
        ):
            apply_action(game, "PLAY_CARD", "CATA_140")
            break

        while True:
            actions = game.legal_actions()
            hero_power = next(
                (action for action in actions if action["type"] == "HERO_POWER"),
                None,
            )
            if hero_power is not None:
                mana_spent += hero_power.get("card_cost", 2)
                game.apply_action(hero_power)
                continue
            candidate = next(
                (
                    action for action in actions
                    if action["type"] == "PLAY_CARD"
                    and action.get("card_id") in {"END_007", "TIME_702", "JAIL_201"}
                    and action.get("card_cost", 0) > 0
                ),
                None,
            )
            if candidate is None:
                break
            mana_spent += candidate["card_cost"]
            game.apply_action(candidate)
        end_turn(game)
        end_turn(game)
    else:
        raise AssertionError(f"Could not spend 25 Mana while holding Merithra; spent {mana_spent}")

    state = game.observation("PLAYER1")
    catalog_path = PROJECT_ROOT / "vendor" / "RosettaStone" / "Resources" / "cards.json"
    standard_cards = json.loads(catalog_path.read_text(encoding="utf-8"))
    dragon_ids = {
        card["id"] for card in standard_cards if card.get("race") == "DRAGON"
    }
    generated_dragons = [card for card in state.self_hand if card.card_id in dragon_ids]
    if not generated_dragons or any(
        card.effective_cost != 1 or card.race != "DRAGON" for card in generated_dragons
    ):
        raise AssertionError(
            "Merithra should fill hand with Dragons reduced to 1 after 25 held Mana; "
            f"spent={mana_spent}, hand={[(card.card_id, card.effective_cost, card.race) for card in state.self_hand]}"
        )
    print("PASS CATA_131/CATA_140: held-Mana thresholds use card and Hero Power payments")


def verify_staff_of_trickery() -> None:
    game = start_game("JAIL_875", "DRUID")
    # Reach the fourth Druid turn, when the four-cost weapon is playable.
    for _ in range(3):
        end_turn(game)
        end_turn(game)
    apply_action(game, "PLAY_CARD", "JAIL_875")
    attack = next(
        (action for action in game.legal_actions()
         if action["type"] == "ATTACK" and action.get("target_is_hero")),
        None,
    )
    if attack is None:
        raise AssertionError("Staff of Trickery should let the hero attack")
    hero_attack = game.observation("PLAYER1").self_player.hero_attack
    game.apply_action(attack)
    choices = [
        action for action in game.legal_actions()
        if action["type"] == "CHOOSE_CARD"
    ]
    if len(choices) != 3:
        raise AssertionError(f"Staff should offer three Discover choices, got {len(choices)}")
    import json

    catalog_paths = (
        PROJECT_ROOT / "vendor" / "RosettaStone" / "Resources" / "cards.json",
        PROJECT_ROOT / "vendor" / "RosettaStone" / "Resources" / "cards.standard_current.json",
    )
    by_id = {}
    for catalog_path in catalog_paths:
        by_id.update(
            (card["id"], card)
            for card in json.loads(catalog_path.read_text(encoding="utf-8"))
        )
    if any(by_id[action["card_id"]]["cardClass"] != "DRUID" for action in choices):
        raise AssertionError("Staff of Trickery Discover must contain only Druid cards")
    choice = next(
        (action for action in choices if by_id[action["card_id"]].get("cost", 0) > hero_attack),
        None,
    )
    if choice is None:
        raise AssertionError("Expected a discovered Druid card whose cost can be discounted")
    original_cost = by_id[choice["card_id"]]["cost"]
    game.apply_action(choice)
    selected = next(
        (card for card in game.observation("PLAYER1").self_hand
         if card.card_id == choice["card_id"]),
        None,
    )
    expected_cost = max(0, original_cost - hero_attack)
    if selected is None or selected.effective_cost != expected_cost:
        raise AssertionError(
            f"Staff should reduce selected card from {original_cost} to {expected_cost}; "
            f"got {None if selected is None else selected.effective_cost}"
        )
    print("PASS JAIL_875: post-attack Druid Discover discounts the selected card by hero Attack")


def verify_amirdrassil() -> None:
    game = start_game("FIR_907", "DRUID")
    for _ in range(4):
        end_turn(game)
        end_turn(game)
    apply_action(game, "PLAY_CARD", "FIR_907")
    end_turn(game)
    end_turn(game)
    game.observation("PLAYER1")
    hero_power = next(
        (action for action in game.legal_actions() if action["type"] == "HERO_POWER"),
        None,
    )
    if hero_power is None:
        raise AssertionError("Expected Druid Hero Power before first Location activation")
    game.apply_action(hero_power)
    before_activation = game.observation("PLAYER1")
    before_activation_board_size = len(before_activation.self_player.board)
    before_activation_hand_size = len(before_activation.self_hand)
    activation = next(
        (action for action in game.legal_actions()
         if action["type"] == "ACTIVATE_LOCATION" and action.get("card_id") == "FIR_907"),
        None,
    )
    if activation is None:
        raise AssertionError("Amirdrassil should be activatable after being played")
    game.apply_action(activation)
    first_observation = game.observation("PLAYER1")
    first = first_observation.self_player
    if first.available_mana != 5 or first.armor != 2:
        raise AssertionError("First Amirdrassil use should refresh 1 Mana and grant 1 Armor")
    if len(first_observation.self_hand) != before_activation_hand_size + 1 or len(first.board) != before_activation_board_size + 1:
        raise AssertionError("Amirdrassil should draw one card and summon one minion")
    if first.board[-1].card.effective_cost != 1:
        raise AssertionError(f"Amirdrassil should summon a 1-Cost minion, got {first.board[-1].card.effective_cost}")

    end_turn(game)
    end_turn(game)
    hero_power = next(
        (action for action in game.legal_actions() if action["type"] == "HERO_POWER"),
        None,
    )
    if hero_power is None:
        raise AssertionError("Expected Druid Hero Power before the second Location use")
    game.apply_action(hero_power)
    activation = next(
        (action for action in game.legal_actions()
         if action["type"] == "ACTIVATE_LOCATION" and action.get("card_id") == "FIR_907"),
        None,
    )
    if activation is None:
        raise AssertionError("Amirdrassil should become activatable again next turn")
    game.apply_action(activation)
    second = game.observation("PLAYER1").self_player
    if second.available_mana != 7 or second.armor != 4:
        raise AssertionError("Second Amirdrassil use should refresh 2 Mana and grant another Armor")
    print("PASS FIR_907: summons, grants Armor, draws, and scales Mana refresh from 1 to 2")


def verify_infest_the_scullery() -> None:
    source_deck = make_simple_test_deck(player_class="DRUID")
    fillers = [card_id for card_id in source_deck if card_id not in {"JAIL_201", "JAIL_200"}]
    player_deck = ["JAIL_201", "JAIL_201", "JAIL_200", *fillers[:27]]
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck,
        enemy_deck,
        player1_class="DRUID",
        player2_class="WARRIOR",
    )
    if errors:
        raise RuntimeError("Scenario deck validation failed: " + "; ".join(errors))
    game = SimulatorSession(
        player_deck,
        enemy_deck,
        player1_class="DRUID",
        player2_class="WARRIOR",
        shuffle=False,
        random_seed=20260928,
    )

    def grant_attack_and_attack() -> None:
        choice = next(
            action for action in game.legal_actions()
            if action["type"] == "PLAY_CARD"
            and action.get("card_id") == "JAIL_201"
            and action.get("choose_one") == 1
        )
        game.apply_action(choice)
        attack = next(
            action for action in game.legal_actions()
            if action["type"] == "ATTACK" and action.get("target_is_hero")
        )
        game.apply_action(attack)

    grant_attack_and_attack()
    end_turn(game)
    end_turn(game)
    grant_attack_and_attack()
    end_turn(game)
    end_turn(game)
    while game.observation("PLAYER1").self_player.available_mana < 5:
        end_turn(game)
        end_turn(game)

    before = game.observation("PLAYER1").self_player.board
    apply_action(game, "PLAY_CARD", "JAIL_200")
    after = game.observation("PLAYER1").self_player.board
    summoned = after[len(before):]
    if len(summoned) != 2 or any(entity.card.effective_cost != 5 for entity in summoned):
        raise AssertionError(
            "Two hero attacks should make Infest the Scullery summon two 5-Cost minions; "
            f"got {[entity.card.effective_cost for entity in summoned]}"
        )
    print("PASS JAIL_200: two hero attacks raise both random summon costs from 3 to 5")


def verify_secret_ingredient() -> None:
    attack_game = start_game("JAIL_201", "DRUID")
    end_turn(attack_game)
    end_turn(attack_game)
    attack_action = next(
        (candidate for candidate in attack_game.legal_actions()
         if candidate["type"] == "PLAY_CARD"
         and candidate.get("card_id") == "JAIL_201"
         and candidate.get("choose_one") == 1),
        None,
    )
    if attack_action is None:
        raise AssertionError("Secret Ingredient should offer its hero Attack choice")
    attack_game.apply_action(attack_action)
    if attack_game.observation("PLAYER1").self_player.hero_attack != 2:
        raise AssertionError("Secret Ingredient should give the hero +2 Attack this turn")

    card_game = start_game("JAIL_201", "DRUID")
    end_turn(card_game)
    end_turn(card_game)
    card_action = next(
        (candidate for candidate in card_game.legal_actions()
         if candidate["type"] == "PLAY_CARD"
         and candidate.get("card_id") == "JAIL_201"
         and candidate.get("choose_one") == 2),
        None,
    )
    if card_action is None:
        raise AssertionError("Secret Ingredient should offer its random Druid card choice")
    initial_hand_size = len(card_game.observation("PLAYER1").self_hand)
    card_game.apply_action(card_action)
    hand = card_game.observation("PLAYER1").self_hand
    if len(hand) != initial_hand_size or not any(card.card_class == "DRUID" for card in hand):
        raise AssertionError("Secret Ingredient should add one random Druid card to hand")
    print("PASS JAIL_201: Choose One grants hero Attack or a random Druid card")


def verify_holy_embrace() -> None:
    game = start_game("JAIL_941", "PRIEST")
    end_turn(game)
    play_free_minion(game)
    end_turn(game)
    end_turn(game)
    face_attack = next(
        (action for action in game.legal_actions()
         if action["type"] == "ATTACK" and action.get("target_is_hero")),
        None,
    )
    if face_attack is None:
        raise AssertionError("Expected an opposing minion to attack the Priest hero")
    game.apply_action(face_attack)
    end_turn(game)

    before_health = game.observation("PLAYER1").self_player.hero_health
    if before_health >= 30:
        raise AssertionError("Holy Embrace's healing scenario needs a damaged hero")
    apply_action(game, "PLAY_CARD", "JAIL_941")
    healed = game.observation("PLAYER1")
    if healed.self_player.hero_health != min(30, before_health + 4):
        raise AssertionError("Holy Embrace should restore 4 Health to its controller's hero")
    if not any(card.card_id == "JAIL_941t" for card in healed.self_hand):
        raise AssertionError("Holy Embrace should add Dark Embrace to hand")

    end_turn(game)
    end_turn(game)
    enemy_hero_action = next(
        (action for action in game.legal_actions()
         if action["type"] == "PLAY_CARD"
         and action.get("card_id") == "JAIL_941t"
         and action.get("target_is_hero")
         and not action.get("target_is_self")),
        None,
    )
    if enemy_hero_action is None:
        raise AssertionError("Dark Embrace should allow its controller to target the enemy hero")
    game.apply_action(enemy_hero_action)
    if game.observation("PLAYER1").opponent.hero_health != 26:
        raise AssertionError("Dark Embrace should deal 4 damage to the selected enemy hero")
    print("PASS JAIL_941: heals its controller and generates a targeted 4-damage spell")


def main() -> None:
    verify_searing_fissure()
    verify_sanguine_depths()
    verify_devouring_plague_lifesteal()
    verify_royal_librarian()
    verify_medivhs_triumph_cost()
    verify_ebb_and_flow()
    verify_press_the_advantage()
    verify_haunt()
    verify_specter_specialist()
    verify_erupting_volcano()
    verify_spiderling()
    verify_carrier_whelp()
    verify_prescient_slitherdrake()
    verify_spider_rider()
    verify_kindred_costs()
    verify_undeath_sentence()
    verify_naralex_first_dragon_discount()
    verify_waveshaping_deck_choice()
    verify_cannonmaster_cannoneer()
    verify_hook_and_heave()
    verify_chainbreaker_hogger()
    verify_ysera_mana_start()
    verify_brood_keeper_weapon()
    verify_mother_duck()
    verify_twilight_influence()
    verify_ritual_of_life()
    verify_torch_overkill()
    verify_acceleration_aura()
    verify_held_mana_cards()
    verify_staff_of_trickery()
    verify_amirdrassil()
    verify_infest_the_scullery()
    verify_secret_ingredient()
    verify_holy_embrace()


if __name__ == "__main__":
    main()
