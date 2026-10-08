from __future__ import annotations

import pytest

from manamind.integrations.manaengine import ManaEngineSession, UnsupportedSimulationError
from manamind.integrations.rosettastone.policy import encode_legal_actions


def _native_dark_gift_manifests(native):
    from pathlib import Path

    from manamind.integrations.manaengine.pool_manifest import load_dark_gift_option_manifest

    root = Path(__file__).resolve().parents[3]
    doc = load_dark_gift_option_manifest(
        root / "experiments/manaengine/data/pools/dark_gift_launch_review_20261004_v1.json",
        root / "experiments/manaengine/data/dark_gift_option_metadata.json",
    )
    return [doc.to_native(native)]


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
    assert STATE_ENCODING_SCHEMA_VERSION == 16
    assert encoded.global_features[encoder.global_feature_names.index("self_previous_minion_type_elemental")] > 0


def test_choose_one_mode_and_target_continuation_adapter_policy_clone() -> None:
    deck = ["CORE_AT_037"] * 30
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    play = next(action for action in session.legal_actions() if action.get("card_id") == "CORE_AT_037")
    session.apply_action(play)
    modes = session.legal_actions()
    assert [action["choose_one"] for action in modes] == [1, 2]
    assert all(action["source_card_id"] == "CORE_AT_037" for action in modes)
    features = encode_legal_actions(modes)
    assert features.shape[0] == 2
    assert [int(row[26]) for row in features] == [1, 0]
    assert [int(row[27]) for row in features] == [0, 1]

    clone = session.clone()
    damage_mode = next(action for action in modes if action["choose_one"] == 1)
    session.apply_action(damage_mode)
    targets = session.legal_actions()
    enemy_hero = next(action for action in targets if action["target_is_hero"] and not action["target_is_self"])
    assert enemy_hero["choose_one"] == 1
    assert encode_legal_actions(targets).shape[0] == len(targets)
    clone_summon = next(action for action in clone.legal_actions() if action["choose_one"] == 2)
    clone.apply_action(clone_summon)
    clone_state = clone.observation()
    assert sum(minion.card.card_id == "AT_037t" for minion in clone_state.self_player.board) == 2
    assert session.observation().self_player.board == ()
    result = session.apply_action(enemy_hero)
    assert result.opponent.hero_health == 28
    assert result.self_player.board == ()
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())

    conditional = ManaEngineSession(["EDR_570"] * 30, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    ominous = next(action for action in conditional.legal_actions() if action.get("card_id") == "EDR_570")
    conditional.apply_action(ominous)
    assert [action["choose_one"] for action in conditional.legal_actions()] == [1]
    assert encode_legal_actions(conditional.legal_actions()).shape[0] == 1


def test_deadly_poison_requires_current_friendly_weapon_in_adapter() -> None:
    deck = ["CORE_CS2_074"] * 30
    session = ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    actions = session.legal_actions()
    assert all(action.get("card_id") != "CORE_CS2_074" for action in actions)
    assert encode_legal_actions(actions).shape[0] == len(actions)


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
    native = _load_native()
    native.CardCatalog(list(definitions.values()), [], "", "", _native_dark_gift_manifests(native))

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


def test_vulcanos_colossal_and_plume_declarations_reach_native_catalog() -> None:
    from pathlib import Path
    from manamind.integrations.manaengine.engine import _definition_rows, _load_native

    definitions = {row.card_id: row for row in _definition_rows()}
    root = definitions["CATA_488"]
    left = definitions["CATA_488t"]
    right = definitions["CATA_488t2"]
    assert root.support_state == "SUPPORTED" and root.rules_contract_reviewed
    assert root.ability == "END_TURN_OTHER_MINIONS_DAMAGE" and root.damage == 3
    assert root.colossal_appendages == ["CATA_488t", "CATA_488t2"]
    assert (root.cost, root.attack, root.health, root.race) == (7, 4, 8, "ELEMENTAL")
    for plume in (left, right):
        assert plume.support_state == "SUPPORTED" and plume.rules_contract_reviewed
        assert (plume.attack, plume.health, plume.race) == (1, 5, "ELEMENTAL")
        assert plume.takes_damage_pool_id == "fire_spell_standard_253932_inferred_v1"
        assert plume.takes_damage_cost_delta == -3

    # The pinned inferred manifest is supplied explicitly for simulation, with training still blocked by evidence debt.
    native = _load_native()
    from manamind.integrations.manaengine.pool_manifest import load_pool_manifest
    root = Path(__file__).resolve().parents[3]
    manifest = load_pool_manifest(root / "experiments/manaengine/data/pools/fire_spell_standard_253932_inferred_v1.json",
                                  expected_profile_id="standard_full_20261001_v1", expected_as_of_date="2026-10-01",
                                  metadata_snapshot_path=root / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json",
                                  standard_roots_path=root / "data/cards/standard_roots_20261001_enUS.json",
                                  expected_metadata_snapshot_id="data/cards/source_snapshots/cards_collectible_20261001_enUS.json")
    native.CardCatalog(list(definitions.values()), [manifest.to_native(native)], manifest.metadata_snapshot_id,
                       manifest.metadata_snapshot_sha256, _native_dark_gift_manifests(native))


def test_plume_inferred_fire_runtime_records_debt_only_when_sampled() -> None:
    from manamind.integrations.manaengine.engine import ManaEngineSession

    filler = "CORE_EX1_145"
    sampled = False
    for seed in range(32):
        session = ManaEngineSession(["CATA_488", *([filler] * 29)], [filler] * 30,
                                    player1_class="MAGE", player2_class="MAGE", shuffle=False,
                                    random_seed=seed)
        assert session.evidence_constraints == ()
        for _ in range(18):
            actions = session.legal_actions()
            root = next((action for action in actions if action.get("card_id") == "CATA_488"), None)
            if root is not None:
                session.apply_action(root)
                break
            session.apply_action(next(action for action in actions if action["type"] == "END_TURN"))
        else:
            pytest.fail("Vulcanos did not become playable during the turn progression")
        try:
            session.apply_action(next(action for action in session.legal_actions() if action["type"] == "END_TURN"))
        except UnsupportedSimulationError:
            # Unsupported Fire outcomes still carry inferred-membership debt after sampling.
            pass
        if session.evidence_constraints:
            assert session.evidence_constraints == ("FIRE_POOL_MEMBERSHIP_INFERRED",)
            sampled = True
            break
    assert sampled, "Vulcanos Plume should sample the admitted inferred pool on its first damage trigger"


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
    hero_power.ability = "TARGET_DAMAGE"  # pre-gate Fireblast encoding; a supported Hero Power must carry its effect
    hero_power.damage = 1
    hero_power.support_state = "SUPPORTED"
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
    from manamind.integrations.manaengine.engine import _export_state, _load_definitions, _load_native

    native = _load_native()
    rows, card_metadata = _load_definitions()
    native.CardCatalog(rows, [], "", "", _native_dark_gift_manifests(native))
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
    state = _export_state(raw, card_metadata=card_metadata)
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


def test_solo_shatter_observation_constructs_game_state_without_dangling_partner() -> None:
    from copy import deepcopy

    from manamind.integrations.manaengine.engine import _export_state

    raw = {
        "turn_number": 3,
        "active_player": "SELF",
        "self_player": {"hero_health": 30, "hand_size": 1},
        "opponent": {"hero_health": 30},
        "self_hand": [{
            "card_id": "CATA_489t",
            "card_type": "SPELL",
            "shatter_fragment": "SOLO",
            "shatter_original_card_id": "CATA_489",
            "shatter_partner_hand_position": -1,
        }],
    }
    state = _export_state(deepcopy(raw))
    fragment = state.self_hand[0]
    assert fragment.shatter_fragment == "SOLO"
    assert fragment.shatter_original_card_id == "CATA_489"
    assert fragment.shatter_partner_hand_position is None

    dangling = deepcopy(raw)
    dangling["self_hand"][0]["shatter_fragment"] = "LEFT"
    with pytest.raises(ValueError, match="Linked Shatter fragments require a valid partner"):
        _export_state(dangling)

def test_finite_pool_manifests_are_strict_and_native_compatible(tmp_path) -> None:
    import json
    from pathlib import Path

    from manamind.integrations.manaengine.engine import _load_native
    from manamind.integrations.manaengine.pool_manifest import load_pool_manifest

    root = Path(__file__).resolve().parents[3]
    snapshot = root / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
    pool_dir = root / "experiments/manaengine/data/pools"
    manifests = sorted(path for path in pool_dir.glob("*.json") if path.name.startswith(("fire_spell_", "whelp_")))
    assert len(manifests) == 5
    native = _load_native()
    expected_counts = {"fire_spell_standard_20261001_candidate_v1.json": 33,
                       "fire_spell_standard_253932_inferred_v1.json": 33,
                       "whelp_one_cost_spell_standard_20261001_raw_candidate_v1.json": 77,
                       "whelp_one_cost_spell_standard_20261001_nonquest_anyclass_candidate_v1.json": 65,
                       "whelp_one_cost_spell_standard_20261001_class_candidate_v1.json": 63}
    for path in manifests:
        document = load_pool_manifest(path, expected_profile_id="standard_full_20261001_v1",
                                     expected_as_of_date="2026-10-01", metadata_snapshot_path=snapshot,
                                     standard_roots_path=root / "data/cards/standard_roots_20261001_enUS.json",
                                     expected_metadata_snapshot_id="data/cards/source_snapshots/cards_collectible_20261001_enUS.json")
        assert document.count == expected_counts[path.name]
        expected_status = "REVIEWED_INFERRED" if path.name == "fire_spell_standard_253932_inferred_v1.json" else "CANDIDATE"
        assert document.membership_status == expected_status
        assert document.dependency_status == "OPEN"
        assert not document.training_eligible
        native_manifest = document.to_native(native)
        native.CardCatalog([], [native_manifest], document.metadata_snapshot_id,
                           document.metadata_snapshot_sha256)

    inferred_path = pool_dir / "fire_spell_standard_253932_inferred_v1.json"
    inferred_raw = json.loads(inferred_path.read_text(encoding="utf-8"))
    assert inferred_raw["pool_id"] == "fire_spell_standard_253932_inferred_v1"
    assert inferred_raw["as_of_date"] == "2026-10-01"
    assert inferred_raw["metadata_snapshot"]["id"].endswith("20261001_enUS.json")
    assert inferred_raw["membership_status"] == "REVIEWED_INFERRED"
    assert inferred_raw["dependency_status"] == "OPEN" and inferred_raw["training_eligible"] is False
    assert inferred_raw["card_ids"] == sorted(set(inferred_raw["card_ids"])) and len(inferred_raw["card_ids"]) == 33
    candidate_raw = json.loads((pool_dir / "fire_spell_standard_20261001_candidate_v1.json").read_text(encoding="utf-8"))
    assert candidate_raw["membership_status"] == "CANDIDATE"
    assert candidate_raw["card_ids"] == inferred_raw["card_ids"]
    assert candidate_raw["predicate"] == inferred_raw["predicate"]
    assert candidate_raw["metadata_snapshot"] == inferred_raw["metadata_snapshot"]
    assert candidate_raw["sorted_membership_sha256"] == inferred_raw["sorted_membership_sha256"] == "480f5971bdf90a339f08142a9f2e47c7650be1ddd6973241960885b20b3e0e87"
    expected_inferred = json.loads(json.dumps(candidate_raw))
    expected_inferred["pool_id"] = "fire_spell_standard_253932_inferred_v1"
    expected_inferred["membership_status"] = "REVIEWED_INFERRED"
    expected_inferred["exclusions"][-1]["rationale"] = (
        "Exhaustive runtime membership remains unresolved. Project policy admits this exact 33-card build-253932 candidate for simulation only; this inference is not rules verification and carries FIRE_POOL_MEMBERSHIP_INFERRED evidence debt whenever sampled."
    )
    expected_inferred["exclusions"][-1]["evidence_ref"] = "reports/manaengine_fire_pool_20261005/FIRE_POOL_RUNTIME_MEMBERSHIP_AUDIT.md"
    from manamind.integrations.manaengine.pool_manifest import _predicate_fingerprint
    expected_inferred["predicate_rules_fingerprint"] = _predicate_fingerprint(expected_inferred)
    assert inferred_raw == expected_inferred

    reviewed_with_debt = json.loads(json.dumps(inferred_raw))
    reviewed_with_debt["membership_status"] = "MEMBERSHIP_REVIEWED"
    malformed = tmp_path / "reviewed_with_unresolved_exclusion.json"
    malformed.write_text(json.dumps(reviewed_with_debt), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot contain unresolved"):
        load_pool_manifest(malformed, expected_profile_id="standard_full_20261001_v1", expected_as_of_date="2026-10-01",
                           metadata_snapshot_path=snapshot, standard_roots_path=root / "data/cards/standard_roots_20261001_enUS.json",
                           expected_metadata_snapshot_id="data/cards/source_snapshots/cards_collectible_20261001_enUS.json")

    wrong_build = json.loads(json.dumps(inferred_raw))
    wrong_build["as_of_date"] = "2026-10-06"
    malformed.write_text(json.dumps(wrong_build), encoding="utf-8")
    with pytest.raises(ValueError, match="identity mismatch"):
        load_pool_manifest(malformed, expected_profile_id="standard_full_20261001_v1", expected_as_of_date="2026-10-01",
                           metadata_snapshot_path=snapshot, standard_roots_path=root / "data/cards/standard_roots_20261001_enUS.json",
                           expected_metadata_snapshot_id="data/cards/source_snapshots/cards_collectible_20261001_enUS.json")

    raw = json.loads(manifests[0].read_text(encoding="utf-8"))
    raw["card_ids"].reverse()
    malformed = tmp_path / "unsorted.json"
    malformed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="sorted and unique"):
        load_pool_manifest(malformed, expected_profile_id="standard_full_20261001_v1",
                           expected_as_of_date="2026-10-01", metadata_snapshot_path=snapshot,
                                     standard_roots_path=root / "data/cards/standard_roots_20261001_enUS.json",
                                     expected_metadata_snapshot_id="data/cards/source_snapshots/cards_collectible_20261001_enUS.json")

    raw = json.loads(manifests[0].read_text(encoding="utf-8"))
    raw["training_eligible"] = True
    malformed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="training eligibility"):
        load_pool_manifest(malformed, expected_profile_id="standard_full_20261001_v1",
                           expected_as_of_date="2026-10-01", metadata_snapshot_path=snapshot,
                                     standard_roots_path=root / "data/cards/standard_roots_20261001_enUS.json",
                                     expected_metadata_snapshot_id="data/cards/source_snapshots/cards_collectible_20261001_enUS.json")

    roots = json.loads((root / "data/cards/standard_roots_20261001_enUS.json").read_text(encoding="utf-8"))
    roots["roots"] = []
    roots["root_count"] = 0
    roots["root_membership_sha256"] = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    bad_roots = tmp_path / "empty_roots.json"
    bad_roots.write_text(json.dumps(roots), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the pinned Standard roots"):
        load_pool_manifest(manifests[0], expected_profile_id="standard_full_20261001_v1",
                           expected_as_of_date="2026-10-01", metadata_snapshot_path=snapshot,
                           standard_roots_path=bad_roots,
                           expected_metadata_snapshot_id="data/cards/source_snapshots/cards_collectible_20261001_enUS.json")


def test_dark_gift_option_manifest_keeps_unresolved_admission_and_hashes(tmp_path) -> None:
    import json
    from pathlib import Path

    from manamind.integrations.manaengine.engine import _load_native
    from manamind.integrations.manaengine.pool_manifest import load_dark_gift_option_manifest

    root = Path(__file__).resolve().parents[3]
    manifest_path = root / "experiments/manaengine/data/pools/dark_gift_launch_review_20261004_v1.json"
    metadata_path = root / "experiments/manaengine/data/dark_gift_option_metadata.json"
    doc = load_dark_gift_option_manifest(manifest_path, metadata_path)
    assert len(doc.candidate_option_ids) == 12
    assert len(doc.launch_reviewed_option_ids) == 10
    native = _load_native()
    from manamind.integrations.manaengine.engine import _definition_rows

    catalog = native.CardCatalog(_definition_rows(), [], "", "", [doc.to_native(native)])
    assert catalog is not None

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["runtime_membership_status"] = "MEMBERSHIP_REVIEWED"
    malformed = tmp_path / "promoted.json"
    malformed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="uncertainty/training status"):
        load_dark_gift_option_manifest(malformed, metadata_path)

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["launch_reviewed_option_ids"].pop()
    malformed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="set sizes"):
        load_dark_gift_option_manifest(malformed, metadata_path)


def test_dark_gift_observation_is_public_only_and_policy_uses_stable_columns() -> None:
    from manamind.cards import CardCatalog
    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding.entity_encoder import NUMERIC_FEATURES, STATE_FLAG_NAMES, _normalise
    from manamind.encoding.state_encoder import StateEncoder
    from manamind.integrations.rosettastone.policy import ACTION_FEATURE_NAMES, encode_legal_actions
    from manamind.domain.dark_gift import DARK_GIFT_OPTION_IDS, DARK_GIFT_POLICY_INDEX

    state = game_state_from_dict({
        "turn_number": 4,
        "active_player": "SELF",
        "self_hand": [{"card_id": "FIR_900", "card_type": "MINION", "dark_gifts": ["EDR_100t", "EDR_100t3"]}],
        "self_player": {"hero_health": 30, "hand_size": 1, "board": [{
            "card_id": "EDR_100t", "card_type": "MINION", "attack": 2, "health": 2,
            "current_attack": 5, "current_health": 4, "max_health": 4, "charge": True,
            "dark_gifts": ["EDR_100t2"],
        }]},
        "opponent": {"hero_health": 30, "hand_size": 4},
        "pending_choice_owner": "SELF",
        "pending_choice_options": [{"card_id": "EDR_100t4", "card_type": "MINION", "dark_gifts": ["EDR_100t6"]}],
    })
    assert state.self_player.board[0].charge is True
    assert state.self_hand[0].dark_gifts == ("EDR_100t", "EDR_100t3")
    assert state.opponent_known_cards == ()
    encoded = StateEncoder(CardCatalog([])).encode(state)
    assert "dark_gift_EDR_100t2" in NUMERIC_FEATURES
    gift_column = NUMERIC_FEATURES.index("dark_gift_EDR_100t2")
    assert encoded.self_board.numeric_present[0, gift_column] == 1
    assert encoded.self_board.numeric[0, gift_column] == _normalise(1)
    assert encoded.self_board.state_flags[0, STATE_FLAG_NAMES.index("charge")] == 1

    actions = [{"type": "PLAY_CARD", "card_dark_gifts": [gift]} for gift in DARK_GIFT_OPTION_IDS]
    rows = encode_legal_actions(actions)
    for index, gift in enumerate(DARK_GIFT_OPTION_IDS):
        assert rows[index, ACTION_FEATURE_NAMES.index(f"play_dark_gift_{DARK_GIFT_POLICY_INDEX[gift]}")] == 1
    rosetta_choice = encode_legal_actions([{"type": "CHOOSE_CARD", "dark_gift_id": 8}])
    manaengine_choice = encode_legal_actions([{"type": "CHOOSE_CARD", "choice_dark_gift": "EDR_100t9"}])
    assert (rosetta_choice == manaengine_choice).all()
    assert len({tuple(row) for row in rows}) == len(DARK_GIFT_OPTION_IDS)
    with pytest.raises(ValueError, match="Unreviewed Dark Gift identity"):
        encode_legal_actions([{"type": "PLAY_CARD", "card_dark_gifts": ["UNKNOWN_GIFT"]}])


def test_rosettastone_singular_gift_observation_normalizes_to_canonical_domain_shape() -> None:
    from dataclasses import asdict

    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding.entity_encoder import NUMERIC_FEATURES
    from manamind.encoding.state_encoder import StateEncoder
    from manamind.cards import CardCatalog

    def observed(card):
        return game_state_from_dict({
            "turn_number": 1, "active_player": "SELF",
            "self_player": {"hero_health": 30, "hand_size": 1},
            "opponent": {"hero_health": 30}, "self_hand": [card],
        })

    rosetta = observed({"card_id": "EX1_116", "dark_gift_id": 8})
    manaengine = observed({"card_id": "EX1_116", "dark_gifts": ["EDR_100t9"]})
    assert rosetta.self_hand[0].dark_gifts == manaengine.self_hand[0].dark_gifts == ("EDR_100t9",)
    assert game_state_from_dict(asdict(rosetta)) == rosetta
    encoder = StateEncoder(CardCatalog([]))
    left = encoder.encode(rosetta).self_hand
    right = encoder.encode(manaengine).self_hand
    index = NUMERIC_FEATURES.index("dark_gift_EDR_100t9")
    assert left.numeric[0, index] == right.numeric[0, index] > 0
    assert (left.numeric == right.numeric).all()
    assert (left.numeric_present == right.numeric_present).all()


def test_dark_gift_evidence_debt_is_session_scoped_cloned_serialized_and_admission_blocking() -> None:
    from dataclasses import asdict, replace

    from manamind.cards import CardCatalog
    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding import StateEncoder
    from manamind.integrations.manaengine.engine import require_canonical_training_admission

    filler = "CORE_EX1_145"
    session = ManaEngineSession(["FIR_900", *([filler] * 29)], [filler] * 30,
                                player1_class="MAGE", player2_class="MAGE", shuffle=False)
    clean_branch = session.clone()
    state = session.observation()
    for _ in range(14):
        actions = session.legal_actions()
        offer = next((action for action in actions if action.get("card_id") == "FIR_900"), None)
        if offer is not None:
            state = session.apply_action(offer)
            break
        state = session.apply_action(next(action for action in actions if action["type"] == "END_TURN"))
    else:
        pytest.fail("FIR_900 did not become playable during the bounded fixture progression")

    expected = tuple(sorted(("DARK_GIFT_RUNTIME_MEMBERSHIP_UNRESOLVED", "DARK_GIFT_SAMPLER_UNVERIFIED")))
    assert session.is_valid and not session.training_eligible
    assert session.evidence_constraints == expected
    assert state.evidence_constraints == expected
    assert clean_branch.evidence_constraints == ()
    assert session.clone().evidence_constraints == expected
    assert game_state_from_dict(asdict(state)).evidence_constraints == expected

    with pytest.raises(UnsupportedSimulationError, match="DARK_GIFT_"):
        session.require_training_admission()
    require_canonical_training_admission((), global_gate_blocked=False)
    with pytest.raises(UnsupportedSimulationError, match="DARK_GIFT_SAMPLER_UNVERIFIED"):
        require_canonical_training_admission(expected, global_gate_blocked=False)

    encoder = StateEncoder(CardCatalog.from_json("data/cards/standard_current_enUS.json"))
    without_debt = replace(state, evidence_constraints=())
    assert (encoder.encode(state).global_features == encoder.encode(without_debt).global_features).all()
    invalid = asdict(state)
    invalid["evidence_constraints"] = ["UNRECOGNIZED_CONSTRAINT"]
    with pytest.raises(ValueError, match="Unknown evidence constraints"):
        game_state_from_dict(invalid)


@pytest.mark.parametrize("multi_death", [False, True])
def test_intrinsic_reborn_adapter_identity_visibility_clone_and_debt(multi_death: bool) -> None:
    from dataclasses import asdict, replace

    from manamind.cards import CardCatalog
    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding import StateEncoder
    from manamind.encoding.entity_encoder import STATE_FLAG_NAMES
    from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION
    from manamind.integrations.manaengine.engine import require_canonical_training_admission

    filler = "CORE_EX1_145"
    count = 2 if multi_death else 1
    opponent_damage = "CORE_CS2_032" if multi_death else "CORE_DS1_185"
    session = ManaEngineSession([*(["CORE_ULD_723"] * count), *([filler] * (30 - count))],
                                [opponent_damage, *([filler] * 29)],
                                player1_class="MAGE", player2_class="MAGE", shuffle=False)
    clean_branch = session.clone()
    original_ids = []
    for _ in range(20):
        actions = session.legal_actions()
        root = next((a for a in actions if a.get("card_id") == "CORE_ULD_723"), None)
        if root is not None:
            state = session.apply_action(root)
            original_ids.append(session._native.observation("PLAYER1")["self_player"]["board"][-1]["entity_id"])
            continue
        damage = next((a for a in actions if a.get("card_id") == opponent_damage
                       and (multi_death or a.get("target_entity_id") in original_ids)), None)
        if damage is not None and len(original_ids) == count:
            before = session.observation("PLAYER1")
            assert all(m.reborn is True for m in before.self_player.board)
            before_encoder = StateEncoder(CardCatalog.from_json("data/cards/standard_current_enUS.json"))
            assert (before_encoder.encode(before).self_board.state_flags[:count, STATE_FLAG_NAMES.index("reborn")] == 1).all()
            assert all(m.reborn is True for m in session.observation("PLAYER2").opponent.board)
            pre_damage_clone = session.clone()
            session.apply_action(damage)
            pre_damage_clone.apply_action(damage)
            state = session.observation("PLAYER1")
            assert pre_damage_clone.observation("PLAYER1") == state
            break
        session.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
    else:
        pytest.fail("bounded Reborn fixture did not reach the damage action")

    assert session.is_valid and len(state.self_player.board) == count
    assert all(m.current_health == 1 and m.reborn is False and m.can_attack is False
               for m in state.self_player.board)
    assert all(m["entity_id"] not in original_ids
               for m in session._native.observation("PLAYER1")["self_player"]["board"])
    expected = ("REBORN_MULTI_DEATH_SLOT_UNVERIFIED",) if multi_death else ()
    assert state.evidence_constraints == session.evidence_constraints == expected
    assert clean_branch.evidence_constraints == ()
    assert session.clone().evidence_constraints == expected
    assert game_state_from_dict(asdict(state)) == state
    assert STATE_ENCODING_SCHEMA_VERSION == 16
    encoder = StateEncoder(CardCatalog.from_json("data/cards/standard_current_enUS.json"))
    encoded = encoder.encode(state)
    assert (encoded.self_board.state_flags[:, STATE_FLAG_NAMES.index("reborn")] == 0).all()
    assert (encoded.global_features == encoder.encode(replace(state, evidence_constraints=())).global_features).all()
    if multi_death:
        with pytest.raises(UnsupportedSimulationError, match="REBORN_MULTI_DEATH_SLOT_UNVERIFIED"):
            require_canonical_training_admission(expected, global_gate_blocked=False)
    else:
        require_canonical_training_admission(expected, global_gate_blocked=False)
    invalid = asdict(state)
    invalid["evidence_constraints"] = ["REBORN_UNKNOWN_CONSTRAINT"]
    with pytest.raises(ValueError, match="Unknown evidence constraints"):
        game_state_from_dict(invalid)
    # Existing action schema remains sufficient; no ID-specific policy feature.
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())


def test_intrinsic_reborn_metadata_does_not_enable_granted_dark_gift_reborn() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows

    definitions = {d.card_id: d for d in _definition_rows()}
    assert definitions["CORE_ULD_723"].reborn is True
    # The option's REBORN tag describes a grant, not an intrinsic minion.
    option = definitions["EDR_100t9"]
    assert option.card_type == "SPELL" and option.reborn is False
    assert option.support_state == "UNSUPPORTED" and "REBORN" in option.dark_gift_keywords
    assert all(d.card_type == "MINION" and d.health > 0 for d in definitions.values() if d.reborn)


def test_damage_group_vulcanos_barrier_poison_and_quiescent_clone() -> None:
    deck = ["CATA_488", *(["CORE_EX1_145"] * 29)]
    opponent = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(deck, opponent, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    session.set_diagnostic_trace(True)
    for _ in range(24):
        actions = session.legal_actions()
        root = next((a for a in actions if a.get("card_id") == "CATA_488"), None)
        if root is not None:
            session.apply_action(root)
            break
        session.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
    else:
        pytest.fail("Vulcanos did not reach the bounded play action")
    state = session.observation("PLAYER1")
    assert [m.current_health for m in state.self_player.board] == [5, 8, 5]
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())
    clone = session.clone()
    end = next(a for a in session.legal_actions() if a["type"] == "END_TURN")
    for branch in (session, clone):
        # The inferred Fire manifest is loaded. This fixed seed selects an
        # unsupported outcome, which must poison both branches without reroll.
        with pytest.raises(UnsupportedSimulationError, match="selected generated outcome is unsupported: TLC_222"):
            branch.apply_action(end)
        assert not branch.is_valid
        trace = list(branch.diagnostic_trace)
        barrier = next(i for i, row in enumerate(trace) if "GROUP_MUTATIONS_COMPLETE" in row)
        reaction = next(i for i, row in enumerate(trace) if "DAMAGE_REACTION" in row)
        packets = [row for row in trace[:barrier] if row.startswith("DAMAGE source=")]
        assert len(packets) == 2 and all("amount=3" in row for row in packets)
        assert barrier < reaction
        for access in (branch.legal_actions, branch.observation, branch.clone):
            with pytest.raises(UnsupportedSimulationError):
                access()
        # A poisoned session is never a terminal episode, a pending-choice state or a training sample.
        for name in ("result", "is_complete", "needs_choice", "choice_options"):
            with pytest.raises(UnsupportedSimulationError):
                getattr(branch, name)
        assert branch.unsupported_outcome and branch.diagnostic_trace
        with pytest.raises(UnsupportedSimulationError):
            branch.apply_action(end)
    assert session.diagnostic_trace == clone.diagnostic_trace
    # Failed state is available only as diagnostic trace, never a policy observation.


def test_damage_group_minion_area_trace_and_policy_schema() -> None:
    from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION

    deck = ["CATA_582", *(["CORE_EX1_145"] * 29)]
    opponent = ["CORE_EX1_145"] * 30
    session = ManaEngineSession(deck, opponent, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    session.set_diagnostic_trace(True)
    for _ in range(6):
        actions = session.legal_actions()
        root = next((a for a in actions if a.get("card_id") == "CATA_582"), None)
        if root is not None:
            session.apply_action(root)
            break
        session.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
    else:
        pytest.fail("Searing Winds did not reach the bounded action")
    assert session.is_valid and STATE_ENCODING_SCHEMA_VERSION == 16
    assert any("GROUP_MUTATIONS_COMPLETE" in row for row in session.diagnostic_trace)
    state = session.observation("PLAYER1")
    assert state.self_player.hero_attack == 3
    assert encode_legal_actions(session.legal_actions()).shape[0] == len(session.legal_actions())


def test_mortal_queued_eot_source_constraint_is_registered_and_blocks_admission() -> None:
    from manamind.domain.game_state import EVIDENCE_CONSTRAINT_IDS
    from manamind.integrations.manaengine.engine import require_canonical_training_admission

    constraint = "MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED"
    assert constraint in EVIDENCE_CONSTRAINT_IDS
    # Evidence debt blocks canonical admission independently of the global gate.
    with pytest.raises(UnsupportedSimulationError, match=constraint):
        require_canonical_training_admission((constraint,), global_gate_blocked=False)


def test_inferred_fire_pool_evidence_is_registered_and_blocks_canonical_admission() -> None:
    from manamind.domain.game_state import EVIDENCE_CONSTRAINT_IDS
    from manamind.integrations.manaengine.engine import require_canonical_training_admission

    constraint = "FIRE_POOL_MEMBERSHIP_INFERRED"
    assert constraint in EVIDENCE_CONSTRAINT_IDS
    with pytest.raises(UnsupportedSimulationError, match=constraint):
        require_canonical_training_admission((constraint,), global_gate_blocked=False)


def test_poisoned_session_accessors_are_adapter_errors_not_native_state() -> None:
    deck = ["CATA_488", *(["CORE_EX1_145"] * 29)]
    session = ManaEngineSession(deck, ["CORE_EX1_145"] * 30, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    for _ in range(24):
        actions = session.legal_actions()
        root = next((a for a in actions if a.get("card_id") == "CATA_488"), None)
        if root is not None:
            session.apply_action(root)
            break
        session.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
    else:
        pytest.fail("Vulcanos did not reach the bounded play action")
    # Healthy session: accessors work and report in-progress state.
    assert session.result is None and not session.is_complete and not session.needs_choice
    assert session.choice_options == ()
    with pytest.raises(UnsupportedSimulationError, match="selected generated outcome is unsupported: TLC_222"):
        session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    assert not session.is_valid and session.unsupported_outcome
    for name in ("result", "is_complete", "needs_choice", "choice_options"):
        with pytest.raises(UnsupportedSimulationError):
            getattr(session, name)


def test_post_mutation_standard_exception_is_normalized_at_adapter_boundary() -> None:
    from manamind.integrations.manaengine.engine import (
        _definition_rows,
        _load_native,
    )

    native = _load_native()
    definitions = _definition_rows()
    secret = next(d for d in definitions if d.card_id == "CORE_LOOT_101")
    # Synthetic malformed runtime text passes declarative catalog validation and fails
    # with std::invalid_argument only after an opponent minion has entered play.
    secret.ability = "NONE"
    secret.support_state = "VERIFIED_VANILLA"
    secret.rules_contract_reviewed = True
    secret.required_mechanics = []
    secret.cost = 1
    secret.secret = True
    secret.secret_trigger = "OPPONENT_PLAYS_MINION"
    secret.secret_effect = "INVALID_TEST_EFFECT"
    manifest = _native_dark_gift_manifests(native)[0]

    filler_definition = next(
        d for d in definitions
        if d.card_type == "MINION" and d.support_state == "VERIFIED_VANILLA"
        and d.cost <= 2 and d.attack > 0 and d.health > 0
    )
    filler_definition.race = ""
    filler_definition.minion_types = []
    filler = filler_definition.card_id
    catalog = native.CardCatalog(definitions, [], "", "", [manifest])
    secret_deck = ["CORE_LOOT_101", *([filler] * 29)]
    opponent_deck = [filler] * 30
    session = ManaEngineSession(
        secret_deck, opponent_deck, player1_class="MAGE", player2_class="MAGE", shuffle=False
    )
    session._unsupported_exception = native.UnsupportedSimulationError
    session._native = native.GameSession(
        secret_deck, opponent_deck, catalog, 31, False, "MAGE", "MAGE"
    )

    # Invalid user input is checked before execution and leaves the session usable.
    with pytest.raises(ValueError):
        session.apply_action({"type": "ATTACK", "attacker_entity_id": 99999, "target_entity_id": 2})
    assert session.is_valid
    assert session.observation() and session.legal_actions()

    secret_action = next(a for a in session.legal_actions() if a.get("card_id") == "CORE_LOOT_101")
    session.apply_action(secret_action)
    for _ in range(8):
        action = next(
            (a for a in session.legal_actions() if a.get("card_id") == filler), None
        )
        if action is not None:
            with pytest.raises(UnsupportedSimulationError, match="unknown Secret effect"):
                session.apply_action(action)
            break
        session.apply_action(next(a for a in session.legal_actions() if a["type"] == "END_TURN"))
    else:
        pytest.fail("synthetic minion did not become playable")

    assert not session.is_valid
    assert "action failed after mutation" in (session.unsupported_outcome or "")
    assert "unknown Secret effect" in (session.unsupported_outcome or "")
    for access in (
        session.observation,
        session.legal_actions,
        session.clone,
        lambda: session.result,
    ):
        with pytest.raises(UnsupportedSimulationError):
            access()


# ---- Phase 4I.1: Arcane Barrage (TIME_855) bounded targeting contract -------------------------------------
BARRAGE_CONSTRAINT = "ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED"


def _advance_to_barrage(session: ManaEngineSession, minion: str = "TIME_006t1", limit: int = 16):
    """Player 1 passes until Arcane Barrage is castable; player 2 plays its cheap minion whenever it can."""
    for _ in range(limit):
        actions = session.legal_actions()
        if session.observation("PLAYER1").active_player == "SELF":
            if any(a["type"] == "PLAY_CARD" and a.get("card_id") == "TIME_855" for a in actions):
                return actions
        else:
            play = next((a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == minion), None)
            if play is not None:
                session.apply_action(play)
                continue
        session.apply_action(next(a for a in actions if a["type"] == "END_TURN"))
    pytest.fail("Arcane Barrage did not become castable during the bounded fixture progression")


def test_every_native_evidence_constraint_is_a_registered_domain_id() -> None:
    from manamind.domain.game_state import EVIDENCE_CONSTRAINT_IDS
    from manamind.integrations.manaengine.engine import _load_native

    native = _load_native()
    # One parity check for every mapping: adding a native constraint without registering its canonical ID fails here.
    assert set(native.EvidenceConstraint.__members__) == set(EVIDENCE_CONSTRAINT_IDS)
    assert BARRAGE_CONSTRAINT in EVIDENCE_CONSTRAINT_IDS


def test_time_855_declaration_round_trips_to_typed_native_steps_and_promotes_nothing_else() -> None:
    import json
    from pathlib import Path

    from manamind.integrations.manaengine.engine import _definition_rows, _load_native

    native = _load_native()
    rows = {d.card_id: d for d in _definition_rows()}
    barrage = rows["TIME_855"]
    assert (barrage.support_state, barrage.ability, barrage.rules_contract_reviewed) == (
        "SUPPORTED", "EFFECT_COMPOSITION", True)
    primary, extras = barrage.effects
    assert (primary.kind, primary.target, primary.amount) == (
        native.EffectKind.DAMAGE, native.TargetSelector.EXPLICIT_ENEMY_CHARACTER, 3)
    assert (primary.random_count, primary.exclude_previous_target, primary.evidence_constraint) == (0, False, None)
    assert (extras.kind, extras.target, extras.amount) == (
        native.EffectKind.DAMAGE, native.TargetSelector.RANDOM_DISTINCT_ENEMY_CHARACTERS, 2)
    assert extras.random_count == 2 and extras.exclude_previous_target is True
    assert extras.evidence_constraint == native.EvidenceConstraint.ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED

    root = Path(__file__).resolve().parents[3]
    declarations = json.loads((root / "experiments/manaengine/data/card_abilities.json").read_text(encoding="utf-8"))["cards"]
    # Nothing in the declaration was dropped by the Python -> native conversion.
    assert declarations["TIME_855"]["effects"][1] == {
        "kind": "DAMAGE", "target": "RANDOM_DISTINCT_ENEMY_CHARACTERS", "amount": 2, "random_count": 2,
        "exclude_previous_target": True, "evidence_constraint": BARRAGE_CONSTRAINT}
    # Only TIME_855 uses the new fields; the other real random-distinct consumers stay unpromoted, and the
    # synthetic genericity controls exist only in native tests.
    users = sorted(
        card_id for card_id, d in rows.items()
        if any(e.random_count or e.exclude_previous_target or e.evidence_constraint is not None for e in d.effects))
    assert users == ["TIME_855"]
    for card_id in ("FIR_909", "TIME_441", "CATA_498", "CORE_CATA_007", "TIME_611"):
        assert card_id not in declarations
        assert card_id not in rows or rows[card_id].support_state == "UNSUPPORTED"
    assert not [card_id for card_id in declarations if card_id.startswith("TEST_")]


def test_random_distinct_parser_is_strict_and_native_catalog_validation_fails_closed() -> None:
    from manamind.integrations.manaengine.engine import _load_native, _parse_effect_steps

    native = _load_native()
    base = {"kind": "DAMAGE", "target": "RANDOM_DISTINCT_ENEMY_MINIONS", "amount": 1, "random_count": 3}
    (step,) = _parse_effect_steps(native, "CONTROL", [base])
    assert step.target == native.TargetSelector.RANDOM_DISTINCT_ENEMY_MINIONS and step.random_count == 3
    for malformed, message in (
        ({**base, "random_count": True}, "random_count must be an integer"),
        ({**base, "random_count": 2.0}, "random_count must be an integer"),
        ({**base, "random_count": "2"}, "random_count must be an integer"),
        ({**base, "exclude_previous_target": 1}, "exclude_previous_target must be a boolean"),
        ({**base, "exclude_previous_target": "true"}, "exclude_previous_target must be a boolean"),
        ({**base, "evidence_constraint": "NOT_A_CONSTRAINT"}, "unknown evidence_constraint"),
        ({**base, "evidence_constraint": BARRAGE_CONSTRAINT.lower()}, "unknown evidence_constraint"),
        ({**base, "evidence_constraint": None}, "unknown evidence_constraint"),
        ({**base, "random_distinct_count": 3}, "only supported optional fields"),
    ):
        with pytest.raises(ValueError, match=message):
            _parse_effect_steps(native, "CONTROL", [malformed])
    with pytest.raises(ValueError, match="effects must be a list"):
        _parse_effect_steps(native, "CONTROL", base)

    def spell(effects: list[dict]):
        definition = native.CardDefinition()
        definition.card_id, definition.card_type, definition.ability = "CONTROL", "SPELL", "EFFECT_COMPOSITION"
        definition.support_state, definition.rules_contract_reviewed = "SUPPORTED", True
        definition.effects = _parse_effect_steps(native, "CONTROL", effects)
        return definition

    explicit = {"kind": "DAMAGE", "target": "EXPLICIT_ENEMY_CHARACTER", "amount": 3}
    native.CardCatalog([spell([base])])
    native.CardCatalog([spell([explicit, {**base, "target": "RANDOM_DISTINCT_ENEMY_CHARACTERS", "random_count": 2,
                                          "exclude_previous_target": True, "evidence_constraint": BARRAGE_CONSTRAINT}])])
    for effects in (
        [{**base, "random_count": 0}],
        [{**base, "random_count": 4}],
        [{**explicit, "random_count": 2}],
        [{**explicit, "exclude_previous_target": True}],
        [{**explicit, "evidence_constraint": BARRAGE_CONSTRAINT}],
        [{**base, "exclude_previous_target": True}],
        [{**base, "evidence_constraint": "DARK_GIFT_SAMPLER_UNVERIFIED"}],
        [{**base, "kind": "DRAW"}],
    ):
        with pytest.raises(ValueError):
            native.CardCatalog([spell(effects)])


def test_native_engine_sources_have_no_card_id_branch_for_random_distinct_targeting() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sources = [*root.glob("src/*.cpp"), *root.glob("include/**/*.hpp")]
    assert sources
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for card_id in ("TIME_855", "FIR_909", "TIME_441", "CATA_498", "CORE_CATA_007", "TIME_611"):
            assert card_id not in text, f"{path.name} must not branch on {card_id}"


def test_arcane_barrage_adapter_session_exports_constraint_and_blocks_admission() -> None:
    from dataclasses import asdict, replace

    from manamind.cards import CardCatalog
    from manamind.domain.serialization import game_state_from_dict
    from manamind.encoding import StateEncoder
    from manamind.encoding.state_encoder import STATE_ENCODING_SCHEMA_VERSION
    from manamind.integrations.manaengine.engine import require_canonical_training_admission
    from manamind.integrations.rosettastone.policy import (
        ACTION_FEATURE_NAMES,
        POLICY_ACTION_SCHEMA_VERSION,
        POLICY_STATE_FEATURE_NAMES,
    )

    session = ManaEngineSession(["TIME_855", *(["CORE_EX1_145"] * 29)], ["TIME_006t1"] * 30,
                                player1_class="MAGE", player2_class="MAGE", shuffle=False)
    clean_branch = session.clone()
    actions = _advance_to_barrage(session)
    assert session.evidence_constraints == () and session.is_valid

    # Barrage is a generic targeted PlayCard: the hero plus every enemy minion, nothing on the caster's side.
    casts = [a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == "TIME_855"]
    enemy_board = [m["entity_id"] for m in session._native.observation("PLAYER1")["opponent"]["board"]]
    assert len(enemy_board) >= 2
    assert len(casts) == 1 + len(enemy_board)
    assert {a["target_entity_id"] for a in casts if not a["target_is_hero"]} == set(enemy_board)
    assert sum(1 for a in casts if a["target_is_hero"]) == 1 and not any(a["target_is_self"] for a in casts)
    assert encode_legal_actions(actions).shape[0] == len(actions)
    # ML-1B added a generic placement feature in policy schema 4. A new evidence
    # ID still does not add a card-specific feature or change the state schema.
    assert POLICY_ACTION_SCHEMA_VERSION == 4 and STATE_ENCODING_SCHEMA_VERSION == 16
    assert not [n for n in (*ACTION_FEATURE_NAMES, *POLICY_STATE_FEATURE_NAMES)
                if "TIME_855" in n or "BARRAGE" in n.upper()]

    session.set_diagnostic_trace(True)
    cast = next(a for a in casts if not a["target_is_hero"])  # a minion primary puts the hero in the extras pool
    state = session.apply_action(cast)
    selection = [row for row in session.diagnostic_trace if row.startswith("RANDOM_DISTINCT_SELECTION")]
    assert len(selection) == 1 and f"candidates={len(enemy_board)}" in selection[0] and "requested=2" in selection[0]

    expected = (BARRAGE_CONSTRAINT,)
    assert session.is_valid and not session.training_eligible
    assert session.evidence_constraints == expected and state.evidence_constraints == expected
    assert clean_branch.evidence_constraints == () and session.clone().evidence_constraints == expected
    assert game_state_from_dict(asdict(state)).evidence_constraints == expected
    assert session.observation("PLAYER1").evidence_constraints == expected

    # The evidence debt blocks canonical admission on its own, independent of the global gate.
    with pytest.raises(UnsupportedSimulationError, match=BARRAGE_CONSTRAINT):
        session.require_training_admission()
    with pytest.raises(UnsupportedSimulationError, match=BARRAGE_CONSTRAINT):
        require_canonical_training_admission(session.evidence_constraints, global_gate_blocked=False)

    # It is session-level debt, never a player-visible feature.
    encoder = StateEncoder(CardCatalog.from_json("data/cards/standard_current_enUS.json"))
    assert (encoder.encode(state).global_features
            == encoder.encode(replace(state, evidence_constraints=())).global_features).all()


def test_arcane_barrage_unsupported_outcome_is_normalized_and_adds_no_debt_before_the_extras() -> None:
    from manamind.integrations.manaengine.engine import _definition_rows, _load_native

    native = _load_native()
    definitions = _definition_rows()
    victim = next(d for d in definitions if d.card_id == "TIME_006t1")
    # A vanilla minion that reacts to damage with a generation pool that was never loaded: the primary's reaction fails.
    # `_definition_rows()` rows are caller-owned, so this synthetic edit cannot reach any other caller or session.
    victim.takes_damage_pool_id = "UNLOADED_POOL_FOR_ADAPTER_TEST"
    victim.takes_damage_cost_delta = -3
    catalog = native.CardCatalog(definitions, [], "", "", _native_dark_gift_manifests(native))
    first_deck, second_deck = ["TIME_855", *(["CORE_EX1_145"] * 29)], ["TIME_006t1"] * 30
    session = ManaEngineSession(first_deck, second_deck, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    session._unsupported_exception = native.UnsupportedSimulationError
    session._native = native.GameSession(first_deck, second_deck, catalog, 31, False, "MAGE", "MAGE")

    actions = _advance_to_barrage(session)
    cast = next(a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == "TIME_855" and not a["target_is_hero"])
    with pytest.raises(UnsupportedSimulationError, match="pool identity is not loaded"):
        session.apply_action(cast)
    # The primary's reaction failed before the extras instruction, so no targeting debt exists; the branch is invalid.
    assert not session.is_valid and "pool identity is not loaded" in (session.unsupported_outcome or "")
    assert session.evidence_constraints == ()
    for access in (session.observation, session.legal_actions, session.clone):
        with pytest.raises(UnsupportedSimulationError):
            access()
    for name in ("result", "is_complete", "needs_choice", "choice_options"):
        with pytest.raises(UnsupportedSimulationError):
            getattr(session, name)


# ---- _definition_rows ownership and runtime-catalog cache isolation ---------------------------------------
# Contract under test: `_definition_rows()` returns fresh, caller-owned mutable rows on every call; the only process-wide
# cache is `_NATIVE_CATALOG_CACHE` (resolved catalog path -> built native catalog + that catalog's own metadata).
def _row_fingerprint(rows):
    """Everything a caller can observe or edit on a native CardDefinition row, as plain comparable data."""
    return [
        (d.card_id, d.card_type, d.card_class, d.race, d.spell_school, d.ability, d.support_state,
         d.rules_contract_reviewed, d.collectible, d.cost, d.attack, d.health, d.durability, d.damage,
         d.rush, d.taunt, d.lifesteal, d.battlecry, d.reborn, d.secret, d.takes_damage_pool_id,
         d.takes_damage_cost_delta, tuple(d.required_mechanics), tuple(d.minion_types),
         tuple(d.colossal_appendages),
         tuple((e.kind, e.target, e.amount, e.lifesteal, e.random_count, e.exclude_previous_target,
                e.evidence_constraint, e.summon_card) for e in d.effects))
        for d in rows
    ]


@pytest.fixture
def isolated_runtime_catalogs(monkeypatch):
    """A private runtime-catalog cache so the order in which tests create sessions can never matter."""
    from manamind.integrations.manaengine import engine as adapter

    cache: dict = {}
    monkeypatch.setattr(adapter, "_NATIVE_CATALOG_CACHE", cache)
    return cache


def _catalog_copy(tmp_path, name: str, *, murmy_race: str | None = None):
    """A distinct catalog file; optionally changes the race of CORE_ULD_723 (Murmy) so metadata leaks are observable."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    raw = json.loads((root / "data/cards/standard_current_enUS.json").read_text(encoding="utf-8-sig"))
    if murmy_race is not None:
        for row in raw["cards"]:
            if row.get("id") == "CORE_ULD_723":
                row["race"] = murmy_race
    path = tmp_path / name
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _murmy_session(catalog_path=None) -> ManaEngineSession:
    deck = ["CORE_ULD_723", *(["CORE_EX1_145"] * 29)]
    return ManaEngineSession(deck, deck, player1_class="MAGE", player2_class="MAGE", shuffle=False,
                             catalog_path=catalog_path)


def test_definition_rows_default_path_is_stable_and_caller_owned() -> None:
    from manamind.integrations.manaengine import engine as adapter

    first, first_metadata = adapter._load_definitions()
    second, second_metadata = adapter._load_definitions()
    assert len(first) > 1000 and _row_fingerprint(first) == _row_fingerprint(second)
    assert dict(first_metadata) == dict(second_metadata) and len(first_metadata) > 1000
    assert _row_fingerprint(adapter._definition_rows()) == _row_fingerprint(first)
    # Fresh objects on every call; the metadata mapping handed to sessions is read-only.
    assert not any(a is b for a, b in zip(first, second))
    with pytest.raises(TypeError):
        first_metadata["CORE_ULD_723"] = None  # type: ignore[index]


def test_mutating_returned_definition_rows_never_reaches_other_callers() -> None:
    from manamind.integrations.manaengine import engine as adapter

    native = adapter._load_native()
    baseline = _row_fingerprint(adapter._definition_rows())
    rows = adapter._definition_rows()
    barrage = next(d for d in rows if d.card_id == "TIME_855")
    minion = next(d for d in rows if d.card_id == "TIME_006t1")
    barrage.support_state = "UNSUPPORTED"
    barrage.ability = "NONE"
    steps = barrage.effects  # the property returns copies; a nested edit only counts once it is assigned back
    steps[1].random_count = 1
    steps[1].target = native.TargetSelector.ENEMY_MINIONS
    barrage.effects = steps[:1]
    minion.takes_damage_pool_id = "LEAK_PROBE"
    minion.required_mechanics = ["LEAK_PROBE"]
    rows.append(native.CardDefinition())
    rows.reverse()
    assert _row_fingerprint(rows) != baseline  # the edits really happened to the rows we hold

    for later in (adapter._definition_rows(), adapter._load_definitions()[0]):
        assert _row_fingerprint(later) == baseline
        later_barrage = next(d for d in later if d.card_id == "TIME_855")
        assert (later_barrage.support_state, later_barrage.ability, len(later_barrage.effects)) == (
            "SUPPORTED", "EFFECT_COMPOSITION", 2)
        assert later_barrage.effects[1].random_count == 2
        assert next(d for d in later if d.card_id == "TIME_006t1").takes_damage_pool_id == ""


def test_distinct_catalog_paths_keep_separate_rows_metadata_and_runtime_catalogs(
        tmp_path, isolated_runtime_catalogs) -> None:
    from manamind.integrations.manaengine import engine as adapter

    same = _catalog_copy(tmp_path, "catalog_same.json")
    alternate = _catalog_copy(tmp_path, "catalog_alternate.json", murmy_race="DEMON")
    same_rows, same_metadata = adapter._load_definitions(same)
    alt_rows, alt_metadata = adapter._load_definitions(alternate)
    changed = [a[0] for a, b in zip(_row_fingerprint(same_rows), _row_fingerprint(alt_rows)) if a != b]
    assert changed == ["CORE_ULD_723"]
    assert (same_metadata["CORE_ULD_723"].race, alt_metadata["CORE_ULD_723"].race) == ("MURLOC", "DEMON")

    # Interleaved creation, observation only afterwards: a last-loaded global would make the earlier sessions see DEMON.
    on_same, on_alternate, on_default = _murmy_session(same), _murmy_session(alternate), _murmy_session()
    assert len(isolated_runtime_catalogs) == 3
    assert on_same.observation().self_hand[0].race == "MURLOC"
    assert on_alternate.observation().self_hand[0].race == "DEMON"
    assert on_default.observation().self_hand[0].race == "MURLOC"
    assert on_alternate.clone().observation().self_hand[0].race == "DEMON"
    assert on_same.clone().observation().self_hand[0].race == "MURLOC"
    # And again after a cache hit for each path.
    assert _murmy_session(alternate).observation().self_hand[0].race == "DEMON"
    assert _murmy_session(same).observation().self_hand[0].race == "MURLOC"
    assert len(isolated_runtime_catalogs) == 3


def test_ordinary_sessions_share_one_native_catalog_per_path(monkeypatch, tmp_path, isolated_runtime_catalogs) -> None:
    from manamind.integrations.manaengine import engine as adapter

    builds: list = []
    real = adapter._load_definitions

    def counting(path=None):
        builds.append(path)
        return real(path)

    monkeypatch.setattr(adapter, "_load_definitions", counting)
    sessions = [_murmy_session() for _ in range(3)]
    assert len(builds) == 1 and len(isolated_runtime_catalogs) == 1  # one build, two cache hits
    # Shared catalog, independent games.
    sessions[0].apply_action(next(a for a in sessions[0].legal_actions() if a["type"] == "END_TURN"))
    assert sessions[0].observation("PLAYER1").turn_number != sessions[1].observation("PLAYER1").turn_number
    assert sessions[1].observation("PLAYER1") == sessions[2].observation("PLAYER1")
    # A different path is built exactly once more, however many sessions use it.
    other = _catalog_copy(tmp_path, "catalog_other.json")
    _murmy_session(other)
    _murmy_session(other)
    assert len(builds) == 2 and len(isolated_runtime_catalogs) == 2


def test_export_state_enrichment_uses_only_explicit_catalog_metadata() -> None:
    import copy

    from manamind.integrations.manaengine import engine as adapter

    raw = {
        "turn_number": 4,
        "active_player": "SELF",
        "self_player": {"hero_health": 30, "secret_count": 1, "spell_damage": 0, "known_secrets": ["CORE_EX1_287"]},
        "opponent": {"hero_health": 30, "secret_count": 0, "spell_damage": 0, "known_secrets": []},
    }
    _rows, metadata = adapter._load_definitions()
    expected = metadata["CORE_EX1_287"].mechanics
    assert expected  # Counterspell carries catalog mechanics worth enriching with
    assert adapter._export_state(copy.deepcopy(raw), card_metadata=metadata).self_player.known_secrets[0].mechanics == expected
    # With no metadata passed there is no hidden fallback to some previously loaded catalog.
    assert adapter._export_state(copy.deepcopy(raw)).self_player.known_secrets[0].mechanics == ()


def _barrage_scenario():
    """Fixed-seed ordinary session through an Arcane Barrage cast; returns everything observable about the outcome."""
    from dataclasses import asdict

    session = ManaEngineSession(["TIME_855", *(["CORE_EX1_145"] * 29)], ["TIME_006t1"] * 30,
                                player1_class="MAGE", player2_class="MAGE", shuffle=False, random_seed=7)
    actions = _advance_to_barrage(session)
    session.set_diagnostic_trace(True)
    cast = next(a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == "TIME_855" and not a["target_is_hero"])
    state = session.apply_action(cast)
    return asdict(state), tuple(session.diagnostic_trace), session.evidence_constraints, session.is_valid


def _synthetic_catalog_without_barrage():
    """Test-only synthetic mutation: private rows in which Arcane Barrage is declared unsupported."""
    from manamind.integrations.manaengine import engine as adapter

    native = adapter._load_native()
    rows = adapter._definition_rows()
    barrage = next(d for d in rows if d.card_id == "TIME_855")
    barrage.support_state, barrage.ability, barrage.effects = "UNSUPPORTED", "NONE", []
    catalog = native.CardCatalog(rows, [], "", "", _native_dark_gift_manifests(native))
    game = native.GameSession(["TIME_855", *(["CORE_EX1_145"] * 29)], ["TIME_006t1"] * 30, catalog, 7, False, "MAGE", "MAGE")
    # The mutation is effective in that private catalog: an unsupported card in the opening hand is refused.
    with pytest.raises(native.UnsupportedSimulationError):
        game.legal_actions()


def test_synthetic_mutation_and_ordinary_sessions_are_order_independent(isolated_runtime_catalogs) -> None:
    # Order X: synthetic mutation first, then the first ordinary session builds the runtime catalog.
    _synthetic_catalog_without_barrage()
    ordinary_after_synthetic = _barrage_scenario()
    isolated_runtime_catalogs.clear()
    # Order Y: the ordinary session builds and caches first, the synthetic mutation happens afterwards, and a further
    # ordinary session (a cache hit) must still be unaffected.
    ordinary_first = _barrage_scenario()
    _synthetic_catalog_without_barrage()
    ordinary_after_cache_hit = _barrage_scenario()
    assert ordinary_after_synthetic == ordinary_first == ordinary_after_cache_hit
    assert ordinary_first[2] == ("ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED",) and ordinary_first[3]
