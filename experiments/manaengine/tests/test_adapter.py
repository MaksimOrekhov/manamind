from __future__ import annotations

import pytest

from manamind.integrations.manaengine import ManaEngineSession, UnsupportedSimulationError
from manamind.integrations.rosettastone.policy import encode_legal_actions


def test_bookkeeper_phase_model_runes_history_adapter_and_policy() -> None:
    from manamind.cards import CardCatalog
    from manamind.encoding import StateEncoder
    from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION

    deck = ["CORE_DRG_107", "CORE_DRG_107", "TLC_226", *(["CORE_EX1_145"] * 27)]
    opponent = ["CORE_LOOT_101", *(["CORE_EX1_145"] * 29)]
    session = ManaEngineSession(deck, opponent, player1_class="MAGE", player2_class="MAGE", shuffle=False)

    def play(card_id: str):
        return session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == card_id))

    def end():
        return session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))

    initial = session.observation()
    assert initial.self_player.previous_turn_minion_types_played == ()
    state = play("CORE_DRG_107")
    assert state.self_player.current_turn_minion_types_played == ("BEAST", "ELEMENTAL")
    end()
    state = end()
    assert state.self_player.previous_turn_minion_types_played == ("BEAST", "ELEMENTAL")
    play("CORE_DRG_107")
    end()
    play("GAME_005")
    play("CORE_LOOT_101")
    state = end()
    assert state.opponent.known_secrets == () and state.opponent.secret_count == 1
    action = next(a for a in session.legal_actions() if a.get("card_id") == "TLC_226")
    original_id = session._native.observation("PLAYER1")["self_hand"][action["hand_index"]]["entity_id"]
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())
    clone = session.clone()
    before = clone.observation()
    state = session.apply_action(action)
    copies = [m for m in state.self_player.board if m.card.card_id == "TLC_226"]
    assert len(copies) == 1
    native_copies = [m for m in session._native.observation("PLAYER1")["self_player"]["board"] if m["card_id"] == "TLC_226"]
    assert native_copies[0]["entity_id"] != original_id
    assert (copies[0].current_attack, copies[0].current_health, copies[0].can_attack) == (2, 2, False)
    assert state.opponent.secret_count == 0
    assert clone.observation() == before and clone.apply_action(action) == state
    assert state.self_player.current_turn_minion_types_played == ("ELEMENTAL",)
    assert not session.training_eligible
    encoder = StateEncoder(CardCatalog.from_json("data/cards/standard_current_enUS.json"))
    encoded = encoder.encode(state)
    assert STATE_ENCODING_SCHEMA_VERSION == 15
    assert encoded.global_features[encoder.global_feature_names.index("self_previous_minion_type_elemental")] > 0


def test_overheat_school_discard_declaration_reaches_adapter() -> None:
    deck = ["FIR_906", "JAIL_805", *(["CORE_EX1_145"] * 28)]
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)

    def end_turn():
        return session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))

    for _ in range(4):
        end_turn()

    before = session.observation()
    assert {card.card_id for card in before.self_hand} >= {"FIR_906", "JAIL_805"}
    action = next(action for action in session.legal_actions() if action.get("card_id") == "FIR_906")
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())
    after = session.apply_action(action)
    assert "FIR_906" not in {card.card_id for card in after.self_hand}
    assert "JAIL_805" not in {card.card_id for card in after.self_hand}
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())


def test_overload_state_reaches_adapter_and_turn_refill() -> None:
    deck = ["CORE_BOT_451", "CORE_EX1_238", *(["CORE_EX1_145"] * 28)]
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    burst = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_BOT_451")
    state = session.apply_action(burst)
    assert state.self_player.pending_overload == 1 and state.self_player.overloaded_mana == 0
    assert len(state.self_player.board) == 2
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())

    def end_turn():
        return session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))

    end_turn()
    state = end_turn()
    assert state.self_player.pending_overload == 0
    assert state.self_player.overloaded_mana == 1
    assert state.self_player.available_mana == state.self_player.max_mana - 1


def test_minion_history_public_unknown_empty_and_strict_types() -> None:
    from dataclasses import replace

    from manamind.cards import CardCatalog
    from manamind.domain import game_state_from_dict
    from manamind.encoding import StateEncoder

    state = game_state_from_dict({"turn_number": 1, "active_player": "SELF", "self_player": {"hero_health": 30}, "opponent": {"hero_health": 30}})
    assert state.self_player.previous_turn_minion_types_played is None
    encoder = StateEncoder(CardCatalog.from_json("data/cards/standard_current_enUS.json"))
    empty = replace(state, self_player=replace(state.self_player, previous_turn_minion_types_played=()))
    mask = encoder.global_feature_names.index("self_has_previous_minion_type_history")
    assert encoder.encode(state).global_features[mask] == 0
    assert encoder.encode(empty).global_features[mask] > 0
    typed = replace(state.self_player, previous_turn_minion_types_played=("ELEMENTAL", "BEAST", "ELEMENTAL"))
    assert typed.previous_turn_minion_types_played == ("BEAST", "ELEMENTAL")
    with pytest.raises(ValueError, match="minion type history"):
        replace(state.self_player, previous_turn_minion_types_played=("PRIVATE_CARD_ID",))


def test_sleet_dynamic_damage_boundary_real_actions_and_clone() -> None:
    deck = ["END_022", "CATA_485", *(["CORE_EX1_145"] * 28)]
    opponent = ["END_022", *(["CORE_EX1_145"] * 29)]
    session = ManaEngineSession(deck, opponent, player1_class="MAGE", player2_class="MAGE", shuffle=False, random_seed=87)
    session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "END_022"))
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "END_022"))
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    actions = session.legal_actions()
    sleet = next(a for a in actions if a.get("card_id") == "CATA_485" and a.get("target_card_id") == "END_022" and a.get("target_is_self"))
    assert sleet["card_spell_damage"] == 0  # Persistent instance bonus, separate from the board aura.
    assert encode_legal_actions(actions).shape[0] == len(actions)
    clone = session.clone()
    before = session.observation()
    result = session.apply_action(sleet)
    assert clone.observation() == before
    assert clone.apply_action(sleet) == result
    assert result.self_player.board[0].current_health == 1
    assert result.self_player.spell_damage == 2
    assert result.opponent.board == ()  # Its 1/3 Seer takes 3, rather than the old cast snapshot's 1.
    assert not session.training_eligible


def test_safe_existing_primitive_harvest_declarations_reach_adapter_and_policy() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows, _load_native

    definitions = {row.card_id: row for row in _definition_rows()}
    expected = {
        "CORE_DS1_185": ("TARGET_DAMAGE", 2),
        "CORE_CS1_130": ("EFFECT_COMPOSITION", 3),
        "CORE_CS2_032": ("EFFECT_COMPOSITION", 5),
        "CORE_BAR_801": ("EFFECT_COMPOSITION", 1),
    }
    for card_id, (ability, amount) in expected.items():
        assert definitions[card_id].support_state == "SUPPORTED"
        assert definitions[card_id].rules_contract_reviewed is True
        assert definitions[card_id].ability == ability
        assert (definitions[card_id].damage if card_id == "CORE_DS1_185" else definitions[card_id].effects[0].amount) == amount

    token = definitions["BAR_035t"]
    assert token.support_state == "VERIFIED_VANILLA"
    assert (token.card_type, token.attack, token.health, token.race, token.rush) == ("MINION", 1, 1, "BEAST", True)
    assert token.required_mechanics == ["RUSH"]
    _load_native().CardCatalog(list(definitions.values()))

    filler = "CORE_EX1_145"
    deck = ["CORE_BAR_801", *([filler] * 29)]
    opponent = [filler] * 30
    session = ManaEngineSession(deck, opponent, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    actions = session.legal_actions()
    assert encode_legal_actions(actions).shape[0] == len(actions)
    wound_prey = next(action for action in actions if action.get("card_id") == "CORE_BAR_801" and action.get("target_is_hero") and not action.get("target_is_self"))
    state = session.apply_action(wound_prey)
    assert state.opponent.hero_health == 29
    assert len(state.self_player.board) == 1
    hyena = state.self_player.board[0]
    assert (hyena.card.card_id, hyena.current_attack, hyena.current_health, hyena.can_attack) == ("BAR_035t", 1, 1, True)
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())


def test_effect_target_boundaries_declarations_and_adapter() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows

    definitions = {row.card_id: row for row in _definition_rows()}
    searing = definitions["CATA_582"]
    assert [step.target.name for step in searing.effects] == ["ALL_MINIONS", "SELF"]
    spirit_bomb = definitions["CORE_BOT_222"]
    assert [step.target.name for step in spirit_bomb.effects] == ["EXPLICIT_MINION", "SELF_HERO"]
    execute = definitions["CORE_CS2_108"]
    growth = definitions["EDR_531"]
    assert execute.effects[0].kind.name == "DESTROY_MINION"
    assert execute.effects[0].target.name == "EXPLICIT_DAMAGED_ENEMY_MINION"
    assert growth.effects[0].target.name == "EXPLICIT_FRIENDLY_MINION"
    assert definitions["CORE_AT_055"].effects[0].kind.name == "HEAL"
    assert definitions["CATA_302"].effects[0].kind.name == "HEAL_MINION_TO_FULL"
    trap = definitions["CORE_EX1_610"]
    assert trap.support_state == "SUPPORTED" and trap.secret_trigger == "FRIENDLY_HERO_ATTACKED"
    assert trap.secret_effect == "ENEMY_AREA_DAMAGE" and trap.damage == 2
    coil, slam, breath = (definitions[key] for key in ("CORE_EX1_302", "CORE_EX1_391", "CATA_303"))
    assert coil.damage_outcome_condition.name == "MORTALLY_WOUNDED"
    assert coil.damage_outcome_followup.name == "DRAW_SELF" and coil.damage_outcome_amount == 0
    assert slam.damage_outcome_condition.name == "SURVIVES"
    assert slam.damage_outcome_followup.name == "DRAW_SELF"
    assert breath.damage_outcome_condition.name == "MORTALLY_WOUNDED"
    assert breath.damage_outcome_followup.name == "HEAL_ENEMY_HERO" and breath.damage_outcome_amount == 5
    conflagrate = definitions["FIR_954"]
    assert conflagrate.damage_outcome_condition.name == "ALWAYS"
    assert conflagrate.damage_outcome_followup.name == "DRAW_TARGET_OWNER"

    deck = ["CATA_582", *("CORE_EX1_145" for _ in range(29))]
    session = ManaEngineSession(deck, ["CORE_EX1_145"] * 30, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    before = session.observation()
    state = session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "CATA_582"))
    assert state.self_player.hero_attack == before.self_player.hero_attack + 3
    assert state.self_player.hero_health == before.self_player.hero_health
    assert state.opponent.hero_health == before.opponent.hero_health


def test_spellweaver_dynamic_cost_policy_and_exact_fixed_dependency() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows
    from manamind.integrations.rosettastone.policy import ACTION_FEATURE_NAMES

    definitions = {row.card_id: row for row in _definition_rows()}
    token = definitions["CATA_452t"]
    assert token.support_state == "VERIFIED_VANILLA"
    assert (token.card_type, token.race, token.attack, token.health) == ("MINION", "DRAGON", 6, 6)
    assert not token.collectible and token.required_mechanics == []
    deck = ["CATA_452", "CORE_CS2_029", *(["CORE_EX1_145"] * 28)]
    opponent = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(deck, opponent, player1_class="MAGE", player2_class="MAGE", shuffle=False, random_seed=93)
    assert session.observation().self_hand[0].current_cost == 10
    for _ in range(14):  # Own turn eight: enough mana to deal six, then spend the remaining four.
        session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    clone = session.clone()
    fire = next(a for a in session.legal_actions() if a.get("card_id") == "CORE_CS2_029" and a.get("target_is_hero") and not a.get("target_is_self"))
    state = session.apply_action(fire)
    held = next(card for card in state.self_hand if card.card_id == "CATA_452")
    assert held.cost == 10 and held.current_cost == 4
    assert clone.observation().self_hand[0].current_cost == 10
    summon = next(a for a in session.legal_actions() if a.get("card_id") == "CATA_452")
    assert summon["card_cost"] == 4 and "target_entity_id" not in summon
    comparison = dict(summon, card_cost=10)
    encoded = encode_legal_actions([summon, comparison])
    cost_column = ACTION_FEATURE_NAMES.index("card_cost")
    assert encoded[0, cost_column] < encoded[1, cost_column]
    result = session.apply_action(summon)
    dragon = result.self_player.board[0]
    assert (dragon.card.card_id, dragon.card.card_type, dragon.card.race) == ("CATA_452t", "MINION", "DRAGON")
    assert (dragon.current_attack, dragon.current_health, dragon.can_attack) == (6, 6, False)
    assert result.self_player.available_mana == 0
    assert not session.training_eligible


def test_spellweaver_zero_cost_and_global_turn_reset_in_adapter() -> None:
    deck = ["CATA_452", "CORE_CS2_029", "CORE_CS2_029", *(["CORE_EX1_145"] * 27)]
    session = ManaEngineSession(deck, ["CORE_EX1_145"] * 30, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    for _ in range(6):
        session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    for _ in range(2):
        session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "CORE_EX1_145"))
        session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "CORE_CS2_029" and a.get("target_is_hero") and not a.get("target_is_self")))
    zero = next(a for a in session.legal_actions() if a.get("card_id") == "CATA_452")
    assert zero["card_cost"] == 0
    clone = session.clone()
    session.apply_action(zero)
    assert session.observation().self_player.board[0].card.card_id == "CATA_452t"
    clone.apply_action(next(a for a in clone.legal_actions() if a["type"] == "END_TURN"))
    assert next(card for card in clone.observation("PLAYER1").self_hand if card.card_id == "CATA_452").current_cost == 10


def test_unsupported_hero_power_session_and_training_fail_closed() -> None:
    deck = ["CORE_EX1_145"] * 30
    with pytest.raises(UnsupportedSimulationError, match="hero powers"):
        ManaEngineSession(deck, deck, player1_class="SHAMAN", player2_class="MAGE")
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE")
    assert not session.training_eligible
    with pytest.raises(UnsupportedSimulationError, match="backend-specific"):
        session.require_training_admission()


def test_catalog_mechanic_and_token_identity_guard() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows, _rules_coverage

    definitions = {row.card_id: row for row in _definition_rows()}
    assert definitions["CORE_CS2_033"].support_state == "UNSUPPORTED"
    assert definitions["CORE_SW_072"].support_state == "UNSUPPORTED"  # Tradeable is absent.
    assert definitions["CS2_tk1"].support_state == "VERIFIED_VANILLA"
    assert "EX1_100t" not in definitions and "TEST_HELD_TRACKER" not in definitions
    assert "CORE_SW_108t" not in definitions
    assert not _rules_coverage({"text": "Freeze anything damaged by this minion.", "mechanics": ["FREEZE"]}, {"ability": "NONE"})
    assert _rules_coverage({"text": "<b>Taunt</b>", "mechanics": ["TAUNT"]}, {"ability": "NONE"})
    assert not _rules_coverage({"text": "Unknown new behavior"}, {"ability": "TARGET_DAMAGE", "reviewed_rules_text": "Deal $6 damage."})


def test_public_transition_state_roundtrip_encoding_and_privacy() -> None:
    from dataclasses import asdict
    from manamind.cards import CardCatalog
    from manamind.domain.card import CardFeatures
    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding import StateEncoder

    deck = ["JAIL_327", "CORE_GIL_836", "CORE_EX1_145", "CORE_EX1_145", *(["CORE_EX1_145"] * 26)]
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "CORE_EX1_145"))
    state = session.observation()
    assert state.self_player.spells_cast_this_turn == 1 and state.self_player.spell_discount == 2
    catalog = CardCatalog([CardFeatures(card_id=card) for card in deck])
    encoder = StateEncoder(catalog)
    assert game_state_from_dict(asdict(state)) == state
    for _ in range(4):
        session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "CORE_EX1_145"))
    session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "JAIL_327"))
    state = session.observation()
    assert state.self_player.active_effects[0].effect_turns_remaining == 3
    assert encoder.encode(state).self_active_effects.card_ids.shape == (1,)
    session.apply_action(next(a for a in session.legal_actions() if a.get("card_id") == "CORE_GIL_836"))
    state = session.observation()
    assert state.pending_choice_owner == "SELF" and len(state.pending_choice_options) == 3
    assert encoder.encode(state).pending_choice_options.card_ids.shape == (3,)
    other = session.observation("PLAYER2")
    assert other.pending_choice_owner == "OPPONENT" and other.pending_choice_options == ()
    assert other.self_hand != state.self_hand
    assert game_state_from_dict(asdict(state)) == state
    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(v) for v in value.values()))
        if isinstance(value, (tuple, list)):
            return set().union(*(keys(v) for v in value))
        return set()
    assert not keys(asdict(state)) & {"entity_id", "activation_sequence", "rng", "deck", "trace", "diagnostic_trace"}


def test_exports_existing_game_state_and_policy_compatible_card_actions() -> None:
    deck = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=17,
    )

    state = session.observation()
    assert state.active_player == "SELF"
    assert len(state.self_hand) == 4
    assert state.opponent.hand_size == 5
    assert state.self_player.hero_power is not None
    assert state.self_player.hero_power.card_id == "HERO_08bp"
    assert state.self_player.hero_power_ready is True
    assert state.opponent_known_cards == ()
    assert not hasattr(state.self_player.board[0], "entity_id") if state.self_player.board else True

    actions = session.legal_actions()
    plays = [action for action in actions if action["type"] == "PLAY_CARD"]
    assert not any(action["type"] == "HERO_POWER" for action in actions)
    assert plays
    assert all(action["card_id"] == "CORE_EX1_145" for action in plays)
    assert all(action["field_position"] == -1 for action in plays)
    encoded = encode_legal_actions(actions)
    assert encoded.shape[0] == len(actions)

    clone = session.clone()
    assert clone.observation() == state
    result_state = session.apply_action(plays[0])
    assert result_state.self_player.available_mana == 1
    assert len(result_state.self_hand) == 3
    assert clone.observation() == state


def test_optional_diagnostic_trace_is_off_by_default_and_clone_local() -> None:
    deck = ["CORE_DRG_107"] * 30
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    assert session.diagnostic_trace == ()
    session.set_diagnostic_trace(True)
    branch = session.clone()
    session.apply_action(next(row for row in session.legal_actions() if row["type"] == "END_TURN"))
    assert session.diagnostic_trace and session.diagnostic_trace[0].startswith("ACTION ")
    assert branch.diagnostic_trace == ()
    session.set_diagnostic_trace(False)
    assert session.diagnostic_trace == ()


def test_held_spell_progress_is_per_card_instance_and_clone_safe() -> None:
    deck = [
        "JAIL_801", "JAIL_801", "CORE_EX1_129",
        "JAIL_801", "CORE_EX1_129", "JAIL_801",
        *(["JAIL_801"] * 24),
    ]
    session = ManaEngineSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=41,
    )

    for _ in range(2):
        end_turn = next(action for action in session.legal_actions() if action["type"] == "END_TURN")
        session.apply_action(end_turn)
    first_fan = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_EX1_129")
    progressed = session.apply_action(first_fan)
    tracker_costs = sorted(
        card.held_spell_progress for card in progressed.self_hand if card.card_id == "JAIL_801"
    )
    assert tracker_costs == [0, 1, 1, 1]

    branch = session.clone()
    assert sorted(
        card.held_spell_progress for card in branch.observation().self_hand if card.card_id == "JAIL_801"
    ) == tracker_costs

    for _ in range(2):
        end_turn = next(action for action in session.legal_actions() if action["type"] == "END_TURN")
        session.apply_action(end_turn)
    second_fan = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_EX1_129")
    after_branch = session.apply_action(second_fan)
    assert sorted(
        card.held_spell_progress for card in after_branch.self_hand if card.card_id == "JAIL_801"
    ) == [0, 1, 1, 2, 2, 2]
    assert sorted(
        card.held_spell_progress for card in branch.observation().self_hand if card.card_id == "JAIL_801"
    ) == tracker_costs
    for _ in range(2):
        session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    assert any(
        action.get("card_id") == "JAIL_801" and action.get("card_cost") == 3
        for action in session.legal_actions()
    )


def test_profile_held_threshold_transform_exports_minion_actions_and_clones() -> None:
    deck = [
        "JAIL_801", "CORE_EX1_145", "CORE_EX1_145", "CORE_EX1_145",
        *(["CORE_EX1_145"] * 26),
    ]
    opponent_deck = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(
        deck,
        opponent_deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=53,
    )

    for _ in range(2):
        action = next(action for action in session.legal_actions() if action["card_id"] == "CORE_EX1_145")
        session.apply_action(action)
    assert session.observation().self_hand[0].card_id == "JAIL_801"
    branch = session.clone()

    third_spell = next(action for action in session.legal_actions() if action["card_id"] == "CORE_EX1_145")
    state = session.apply_action(third_spell)
    transformed = state.self_hand[0]
    assert transformed.card_id == "JAIL_801t"
    assert transformed.card_type == "MINION"
    assert transformed.attack == transformed.health == 3
    assert branch.observation().self_hand[0].card_id == "JAIL_801"

    for _ in range(6):
        end_turn = next(action for action in session.legal_actions() if action["type"] == "END_TURN")
        session.apply_action(end_turn)
    battlecry = next(
        action for action in session.legal_actions()
        if action["card_id"] == "JAIL_801t" and action.get("target_entity_id") == 2
    )
    assert battlecry["card_type"] == "MINION"
    final_state = session.apply_action(battlecry)
    assert final_state.opponent.hero_health == 26


def test_blazing_invocation_uses_complete_pinned_pool_and_choice_continuation() -> None:
    deck = ["CORE_GIL_836"] * 30
    session = ManaEngineSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=0,
    )
    root = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_GIL_836")
    session.apply_action(root)
    assert session.needs_choice
    options = [action for action in session.legal_actions() if action["type"] == "CHOOSE_CARD"]
    assert len(options) == 3
    assert len({action["choice_card_id"] for action in options}) == 3
    assert all(action["choice_card_type"] == "MINION" for action in options)
    assert encode_legal_actions(options).shape[0] == 3
    repeated = ManaEngineSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=0,
    )
    repeated_root = next(action for action in repeated.legal_actions() if action.get("card_id") == "CORE_GIL_836")
    repeated.apply_action(repeated_root)
    repeated_ids = [action["choice_card_id"] for action in repeated.legal_actions()]
    assert [action["choice_card_id"] for action in options] == repeated_ids
    unsupported_branch = session.clone()
    unsupported_choice = unsupported_branch.legal_actions()[0]
    try:
        unsupported_branch.apply_action(unsupported_choice)
    except UnsupportedSimulationError:
        pass
    else:
        raise AssertionError("selecting an unsupported full-pool outcome must invalidate the branch")
    assert not unsupported_branch.is_valid

    # Find a reproducible draw containing the already supported neutral Viper.
    selected_session = None
    viper_option = None
    for seed in range(512):
        candidate = ManaEngineSession(
            deck,
            deck,
            player1_class="MAGE",
            player2_class="MAGE",
            shuffle=False,
            random_seed=seed,
        )
        candidate_root = next(action for action in candidate.legal_actions() if action.get("card_id") == "CORE_GIL_836")
        candidate.apply_action(candidate_root)
        choice_actions = candidate.legal_actions()
        option = next((action for action in choice_actions if action["choice_card_id"] == "CATA_458"), None)
        if option is not None:
            selected_session, viper_option = candidate, option
            break
    assert selected_session is not None and viper_option is not None
    branch = selected_session.clone()
    branch_options = branch.legal_actions()
    assert [row["choice_card_id"] for row in branch_options] == [row["choice_card_id"] for row in selected_session.legal_actions()]
    result = selected_session.apply_action(viper_option)
    viper = next(card for card in result.self_hand if card.card_id == "CATA_458")
    assert viper.current_cost == 3
    assert any(action["type"] == "END_TURN" for action in selected_session.legal_actions())


def test_arcane_flow_shatter_survives_native_adapter_and_exports_semantic_links() -> None:
    from manamind.cards import CardCatalog
    from manamind.domain.card import CardFeatures
    from manamind.encoding import StateEncoder

    deck = ["CORE_EX1_145"] * 3 + ["CATA_489"] + ["CORE_EX1_145"] * 26
    session = ManaEngineSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=47,
    )
    state = session.observation("PLAYER1")
    assert state.self_hand[0].card_id == "CATA_489t"
    assert state.self_hand[-1].card_id == "CATA_489t2"
    assert state.self_hand[0].shatter_fragment == "LEFT"
    assert state.self_hand[0].shatter_partner_hand_position == len(state.self_hand) - 1
    assert state.self_hand[-1].shatter_partner_hand_position == 0
    assert not hasattr(state.self_hand[0], "entity_id")

    catalog = CardCatalog([CardFeatures(card_id="CATA_489", cost=4, card_type="SPELL", card_class="MAGE")])
    encoded = StateEncoder(catalog).encode(state).self_hand
    root_id = StateEncoder(catalog).vocabulary.card_id("CATA_489")
    assert encoded.card_ids[0] == root_id and encoded.card_ids[-1] == root_id
    assert encoded.hand_semantic_features[0, 0] == 1
    assert encoded.hand_semantic_features[-1, 1] == 1

    for _ in range(6):
        session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    left_action = next(action for action in session.legal_actions()
                       if action["type"] == "PLAY_CARD" and action["card_id"] == "CATA_489t")
    assert left_action["shatter_fragment"] == "LEFT"
    assert left_action["shatter_original_card_id"] == "CATA_489"
    current_hand = session.observation().self_hand
    right_position = next(i for i, card in enumerate(current_hand) if card.card_id == "CATA_489t2")
    assert left_action["shatter_partner_hand_position"] == right_position


def test_prepare_card_round_trips_as_its_own_action_kind() -> None:
    from manamind.integrations.manaengine.engine import _load_native
    from manamind.integrations.rosettastone.policy import ACTION_FEATURE_NAMES

    native = _load_native()
    filler = native.CardDefinition()
    filler.card_id = "TEST_PREPARE_FILLER"
    filler.card_type = "MINION"
    filler.support_state = "VERIFIED_VANILLA"
    hero_power = native.CardDefinition()
    hero_power.card_id = "HERO_08bp"
    hero_power.card_type = "HERO_POWER"
    hero_power.card_class = "MAGE"
    hero_power.cost = 2
    hero_power.support_state = "VERIFIED_VANILLA"
    prepared = native.CardDefinition()
    prepared.card_id = "TEST_PREPARE_SPELL"
    prepared.card_type = "SPELL"
    prepared.cost = 5
    prepared.damage = 3
    prepared.ability = "TARGET_DAMAGE"
    prepared.support_state = "SUPPORTED"
    prepared.prepare = True
    for definition in (filler, hero_power, prepared):
        definition.rules_contract_reviewed = True
    catalog = native.CardCatalog([filler, hero_power, prepared])
    deck = ["TEST_PREPARE_SPELL", *(["TEST_PREPARE_FILLER"] * 29)]
    session = native.GameSession(deck, deck, catalog, 13, False, "MAGE", "MAGE")
    session.apply_action({"type": "END_TURN"})
    actions = session.legal_actions()
    prepare = next(action for action in actions if action["type"] == "PREPARE_CARD")
    assert prepare["card_id"] == "TEST_PREPARE_SPELL"
    assert prepare["card_cost"] == 5
    assert prepare["hand_index"] == 0
    action_features = encode_legal_actions([prepare])
    assert action_features[0, ACTION_FEATURE_NAMES.index("prepare_card")] == 1.0
    clone = session.clone()
    after = session.apply_action(prepare)
    assert after["self_player"]["available_mana"] == 0
    assert after["self_hand"][0]["current_cost"] == 3
    assert after["self_hand"][0]["prepare_locked"] is True
    assert clone.observation("ACTIVE")["self_hand"][0]["current_cost"] == 5
    assert clone.observation("ACTIVE")["self_hand"][0]["prepare_locked"] is False
    from manamind.cards import CardCatalog
    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding import StateEncoder
    adapted = game_state_from_dict(after)
    encoded = StateEncoder(CardCatalog([])).encode(adapted).self_hand
    assert encoded.hand_semantic_features[0, 4:].tolist() == [1.0, 1.0]
    remaining = session.legal_actions()
    assert not any(action["type"] in {"PLAY_CARD", "PREPARE_CARD"} and action.get("hand_index") == 0 for action in remaining)


def test_secret_catalog_and_perspective_safe_state_encoding() -> None:
    from manamind.cards import CardCatalog
    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding import StateEncoder
    from manamind.encoding.state_encoder import GLOBAL_FEATURE_NAMES
    from manamind.integrations.manaengine.engine import _definition_rows, _export_state, _load_native

    native = _load_native()
    rows = _definition_rows()
    native.CardCatalog(rows)
    by_id = {row.card_id: row for row in rows}
    mage_secrets = {
        card_id for card_id, row in by_id.items()
        if row.secret and row.collectible and row.card_class == "MAGE"
    }
    assert mage_secrets == {
        "CORE_BAR_812", "CORE_EX1_287", "CORE_EX1_289",
        "CORE_LOOT_101", "END_024", "JAIL_315",
    }
    assert by_id["JAIL_321"].ability == "CAST_RANDOM_SECRETS"
    assert by_id["JAIL_321"].random_cast_count == 2
    assert by_id["JAIL_321"].prepare is True

    raw = {
        "turn_number": 4,
        "active_player": "SELF",
        "self_player": {"hero_health": 30, "secret_count": 1, "spell_damage": 2, "known_secrets": ["CORE_EX1_287"]},
        "opponent": {"hero_health": 30, "secret_count": 1, "spell_damage": 0, "known_secrets": []},
    }
    state = _export_state(raw)
    assert state.self_player.known_secrets[0].card_id == "CORE_EX1_287"
    assert state.self_player.spell_damage == 2
    assert state.opponent.secret_count == 1
    assert state.opponent.known_secrets == ()

    catalog = CardCatalog([state.self_player.known_secrets[0]])
    encoded = StateEncoder(catalog).encode(state)
    secret_id = encoded.self_known_secrets.card_ids[0]
    assert secret_id == StateEncoder(catalog).vocabulary.card_id("CORE_EX1_287")
    assert encoded.global_features[GLOBAL_FEATURE_NAMES.index("opponent_secret_count")] > 0

    raw["opponent"]["known_secrets"] = ["CORE_EX1_287"]
    with pytest.raises(ValueError, match="Secret identities must remain hidden"):
        game_state_from_dict(raw)


def test_manaengine_exports_current_spell_damage() -> None:
    deck = ["CORE_EX1_012", *("CORE_EX1_145" for _ in range(29))]
    session = ManaEngineSession(
        deck,
        deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=61,
    )
    for _ in range(2):
        end_turn = next(action for action in session.legal_actions() if action["type"] == "END_TURN")
        session.apply_action(end_turn)
    bloodmage = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_EX1_012")
    state = session.apply_action(bloodmage)
    assert state.self_player.spell_damage == 1
    assert state.opponent.spell_damage == 0


def test_archmage_kalec_marks_spell_instances_in_hand_and_exports_action_value() -> None:
    deck = ["CATA_458", "CORE_CS2_029", *(["CORE_CS2_024"] * 28)]
    opponent_deck = ["CORE_DRG_107"] * 30
    session = ManaEngineSession(
        deck,
        opponent_deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=63,
    )
    for _ in range(12):
        state = session.observation()
        if any(action.get("card_id") == "CATA_458" for action in session.legal_actions()):
            break
        session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    kalec = next(action for action in session.legal_actions() if action.get("card_id") == "CATA_458")
    state = session.apply_action(kalec)
    fireball = next(card for card in state.self_hand if card.card_id == "CORE_CS2_029")
    assert fireball.current_spell_damage == 1
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    spell_action = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_CS2_029")
    assert spell_action["card_spell_damage"] == 1
    encoded_actions = encode_legal_actions([spell_action, {**spell_action, "card_spell_damage": 0}])
    assert (encoded_actions[0] != encoded_actions[1]).any()
    assert state.opponent.hand_size >= 1
    assert state.opponent_known_cards == ()


def test_living_flame_draws_a_fire_spell_from_its_deck() -> None:
    deck = ["FIR_929", "CORE_SW_108", "CORE_CS2_029", "CORE_CS2_024", *("CORE_CS2_029" for _ in range(26))]
    opponent_deck = ["CORE_DRG_107"] * 30
    session = ManaEngineSession(
        deck,
        opponent_deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=73,
    )
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    violet = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_DRG_107")
    session.apply_action(violet)
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    living_flame = next(action for action in session.legal_actions() if action.get("card_id") == "FIR_929")
    session.apply_action(living_flame)
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    before_attack = session.observation("PLAYER1")
    fire_cards_before = sum(card.card_id in {"CORE_SW_108", "CORE_CS2_029"} for card in before_attack.self_hand)
    attack = next(action for action in session.legal_actions() if action["type"] == "ATTACK" and action.get("target_card_id") == "FIR_929")
    session.apply_action(attack)
    observed = session.observation("PLAYER1")
    fire_cards_after = sum(card.card_id in {"CORE_SW_108", "CORE_CS2_029"} for card in observed.self_hand)
    assert fire_cards_after == fire_cards_before + 1


def test_raincaller_attack_gain_crosses_adapter_boundary() -> None:
    deck = ["CATA_487", "CORE_SW_108", "CORE_CS2_029", *(["CORE_CS2_029"] * 27)]
    opponent_deck = ["CORE_DRG_107"] * 30
    session = ManaEngineSession(
        deck,
        opponent_deck,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
        random_seed=79,
    )
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    coin = next(action for action in session.legal_actions() if action.get("card_id") == "GAME_005")
    session.apply_action(coin)
    violet = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_DRG_107")
    session.apply_action(violet)
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    raincaller = next(action for action in session.legal_actions() if action.get("card_id") == "CATA_487")
    state = session.apply_action(raincaller)
    assert state.self_player.board[0].current_attack == 1
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
    target = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_SW_108" and action.get("target_card_id") == "CORE_DRG_107")
    state = session.apply_action(target)
    assert state.self_player.board[0].current_attack == 3
    attack = next(action for action in session.legal_actions() if action["type"] == "ATTACK" and action.get("source_card_id") == "CATA_487")
    assert attack["source_attack"] == 3
def test_mirror_dimension_conditional_fixed_summon_adapter() -> None:
    deck = ["TIME_006", "CATA_452t", *("CORE_EX1_145" for _ in range(28))]
    opponent = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(
        deck,
        opponent,
        player1_class="MAGE",
        player2_class="MAGE",
        shuffle=False,
    )
    action = next(a for a in session.legal_actions() if a.get("card_id") == "TIME_006")
    state = session.apply_action(action)
    assert [entity.card.card_id for entity in state.self_player.board].count("TIME_006t1") == 2
