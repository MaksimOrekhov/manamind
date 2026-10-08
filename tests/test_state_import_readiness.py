"""ENGINE-STATE-IMPORT-0 diagnostics: synthetic, sanitized positions with independent expectations."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import state_import_readiness as cli  # noqa: E402
from manamind.domain.game_state import PlayerObservation  # noqa: E402
from manamind.integrations.manaengine.state_import_capability import DEPENDENCY_FILES, CapabilityIndex  # noqa: E402
from manamind.integrations.manaengine.state_import_corpus import (  # noqa: E402
    CorpusPosition, aggregate, analyze_corpus, read_live_positions, read_policy_positions, read_value_positions, select_sample,
)
from manamind.integrations.manaengine.state_import_readiness import (  # noqa: E402
    BLOCKER_SPECS, FIELD_PROVENANCE, NATIVE_STATE_CONTRACT, REVIEWED_MECHANIC_IDENTITIES, analyze_position, canonical_dumps,
)

CAP = CapabilityIndex()
UNSUPPORTED_ID = "ZZZ_UNDECLARED_MINION"  # present in no catalog: stands for a card the engine cannot execute


def supported_id(card_type: str) -> str:
    for card_id in CAP.declared_card_ids:
        capability = CAP.card(card_id)
        if capability.supported and capability.card_type == card_type:
            return card_id
    raise AssertionError(f"no supported {card_type} declaration")


SUPPORTED_MINION, SUPPORTED_SPELL = supported_id("MINION"), supported_id("SPELL")


def card(card_id=SUPPORTED_MINION, card_type="MINION", **extra):
    return {"card_id": card_id, "card_type": card_type, "cost": 2, "attack": 2, "health": 3, "mechanics": [], **extra}


def minion(card_id=SUPPORTED_MINION, position=1, attack=2, health=3, **flags):
    return {"card": card(card_id, attack=2, health=3), "current_attack": attack, "current_health": health, "max_health": health,
            "board_position": position, "cant_be_targeted_by_spells": False, "cant_be_targeted_by_hero_powers": False, **flags}


def player(**over):
    base = {
        "hero_health": 30, "hero_max_health": 30, "armor": 0, "hero_attack": 0, "max_mana": 5, "available_mana": 5, "overloaded_mana": 0, "pending_overload": 0,
        "deck_size": 0, "hand_size": 0, "fatigue": 0, "secret_count": 0, "spell_damage": 0, "known_secrets": [],
        "hero_power_ready": True, "hero_frozen": False, "hero_freeze_turns_remaining": 0, "hero_divine_shield": False,
        "player_class": "PRIEST", "weapon": None,
        "hero_power": {"card_id": "HERO_09bp", "card_type": "HERO_POWER", "current_cost": 2},
        "board": [], "locations": [], "spells_cast_this_turn": 0, "spell_discount": 0, "demon_discount": 0, "active_effects": [],
        "current_turn_minion_types_played": [], "previous_turn_minion_types_played": [], "healing_bonus": 0,
    }
    base.update(over)
    return base


def state(self_over=None, opp_over=None, **over):
    base = {"turn_number": 5, "active_player": "SELF", "self_player": player(**(self_over or {})),
            "opponent": player(player_class="MAGE", hero_power={"card_id": "HERO_08bp", "card_type": "HERO_POWER", "current_cost": 2},
                               **(opp_over or {})),
            "self_hand": [], "self_hand_known_count": 0, "opponent_known_cards": [], "evidence_constraints": []}
    base.update(over)
    return base


def codes(diagnostic):
    return {blocker.code for blocker in diagnostic.blockers}


def analyze(st, **kwargs):
    # Synthetic fixtures are fully populated; the real-extractor default profile is exercised in its own tests.
    kwargs.setdefault("source_profile", "FULLY_POPULATED")
    return analyze_position(st, CAP, **kwargs)


# -- required position cases -----------------------------------------------------------------------------------------------


def test_valid_ordinary_state_is_still_not_importable():
    diagnostic = analyze(state(self_over={"board": [minion()], "hand_size": 1}, self_hand=[card(SUPPORTED_SPELL, "SPELL")]))
    result = diagnostic.to_dict()
    assert diagnostic.structurally_valid
    # Fully populated and fully supported: nothing visible is missing (the hero maximum Health is observed).
    assert codes(diagnostic) == set()
    assert result["hero_power"]["SELF"]["status"] == "PROVEN_SUPPORTED_BASE"
    assert result["faithful_native_import_possible_today"] is False
    assert result["axes"]["native_hydration"] == "BLOCKED_NO_FROM_STATE_CONSTRUCTOR"
    assert result["axes"]["canonical_training"] == "BLOCKED_GLOBAL_GATE"
    assert result["axes"]["source_completeness"] == "COMPLETE_VISIBLE_FIELDS"
    assert result["known"]["hero_max_health"] == {"SELF": "KNOWN_SUPPORTED_NATIVE", "OPPONENT": "KNOWN_SUPPORTED_NATIVE"}
    assert result["axes"]["native_capability"] == "NO_KNOWN_GAP"


def test_real_extractor_profiles_do_not_pretend_defaults_are_knowledge():
    live = analyze_position(state(), CAP)  # default LIVE_SANITIZED profile
    assert "PLAYER_EFFECTS_NOT_EXTRACTED" in codes(live) and "SECRET_COUNT_NOT_EXTRACTED" not in codes(live)
    parity = analyze_position(state(), CAP, source_profile="OFFLINE_PARITY")
    assert {"PLAYER_EFFECTS_NOT_EXTRACTED", "SECRET_COUNT_NOT_EXTRACTED"} <= codes(parity)
    assert "PLAYER_EFFECTS_NOT_EXTRACTED" not in codes(analyze(state()))


def test_missing_hero_power_id_is_unknown_and_never_taken_from_the_class():
    for hero_power in (None, {"card_id": "UNKNOWN_CARD"}):
        diagnostic = analyze(state(self_over={"hero_power": hero_power, "player_class": "MAGE"}))
        assert "HERO_POWER_ID_UNKNOWN" in codes(diagnostic)
        assert diagnostic.to_dict()["hero_power"]["SELF"] == {"identity_observed": False, "status": "MISSING", "class_is_not_evidence": True}
        assert BLOCKER_SPECS["HERO_POWER_ID_UNKNOWN"].category.value == "UNKNOWN"


def test_identity_not_class_decides_hero_power_support():
    mage_with_priest_power = state(self_over={"player_class": "MAGE", "hero_power": {"card_id": "HERO_09bp", "current_cost": 2}})
    assert analyze(mage_with_priest_power).to_dict()["hero_power"]["SELF"]["status"] == "PROVEN_SUPPORTED_BASE"
    replaced = state(self_over={"hero_power": {"card_id": "HERO_09dbp", "current_cost": 2}})  # supported class, unreviewed power
    diagnostic = analyze(replaced)
    assert "HERO_POWER_IDENTITY_UNREVIEWED" in codes(diagnostic)
    assert diagnostic.to_dict()["hero_power"]["SELF"]["status"] == "UNREVIEWED_IDENTITY"
    assert "RULE_UNRESOLVED" in diagnostic.categories()
    assert not CAP.card("HERO_09dbp").supported  # a suffixed variant is never aliased to the reviewed HERO_09bp
    assert analyze(replaced).to_dict()["axes"]["rules_evidence"] == "UNRESOLVED"


def test_imbued_priest_is_an_unsupported_mechanic():
    assert "EDR_449p" in REVIEWED_MECHANIC_IDENTITIES
    diagnostic = analyze(state(self_over={"hero_power": {"card_id": "EDR_449p", "current_cost": 2}}))
    rows = [b for b in diagnostic.blockers if b.code == "HERO_POWER_IMBUE"]
    assert rows and rows[0].spec.category.value == "UNSUPPORTED_MECHANIC" and rows[0].spec.resolution == "ENGINE_PRIMITIVE"
    assert diagnostic.to_dict()["hero_power"]["SELF"]["status"] == "IMBUE_UNSUPPORTED"
    assert "HERO_POWER_IDENTITY_UNREVIEWED" not in codes(diagnostic)


def test_modified_hero_power_cost_is_not_represented_natively():
    assert "HERO_POWER_COST_MODIFIED" in codes(analyze(state(self_over={"hero_power": {"card_id": "HERO_09bp", "current_cost": 1}})))
    assert "HERO_POWER_COST_UNKNOWN" in codes(analyze(state(self_over={"hero_power": {"card_id": "HERO_09bp"}})))
    assert "HERO_POWER_READINESS_UNKNOWN" in codes(analyze(state(self_over={"hero_power_ready": None})))
    # Readiness only matters for the seat whose turn it is.
    assert "HERO_POWER_READINESS_UNKNOWN" not in codes(analyze(state(opp_over={"hero_power_ready": None})))


def test_unsupported_card_in_self_hand_blocks_enumeration_and_all_blockers_are_listed():
    action = {"type": "END_TURN"}
    diagnostic = analyze(state(self_over={"hand_size": 2}, self_hand=[card(UNSUPPORTED_ID), card(SUPPORTED_SPELL, "SPELL")]), action=action)
    hand = [b for b in diagnostic.blockers if b.code.startswith("UNSUPPORTED_CARD")]
    assert [b.code for b in hand] == ["UNSUPPORTED_CARD_NOT_IN_CATALOG"]  # no metadata anywhere: the reason is the missing catalog entry
    supported_card = analyze(state(self_over={"hand_size": 1}, self_hand=[card(SUPPORTED_SPELL, "SPELL")]))
    assert not any(b.code.startswith("UNSUPPORTED_CARD") for b in supported_card.blockers)
    # Several blockers at once: nothing stops at the first one.
    many = analyze(state(self_over={"hand_size": 3, "hero_power": None, "deck_size": 4}, self_hand=[card(UNSUPPORTED_ID)] * 3, opp_over={"hand_size": 2}))
    assert {"HERO_POWER_ID_UNKNOWN", "OPPONENT_HAND_IDENTITIES_UNKNOWN", "SELF_DECK_COMPOSITION_UNKNOWN"} <= codes(many)
    assert any(code.startswith("UNSUPPORTED_CARD") for code in codes(many))


def test_declared_unsupported_and_undeclared_reasons_are_distinct():
    unsupported_declared = next(card_id for card_id in CAP.declared_card_ids if CAP.card(card_id).reason == "DECLARED_UNSUPPORTED")
    undeclared = next(card_id for card_id in ("CATA_301", "TLC_817") if CAP.card(card_id).reason == "UNDECLARED")
    diagnostic = analyze(state(self_over={"hand_size": 2}, self_hand=[card(unsupported_declared, "SPELL"), card(undeclared, "SPELL")]))
    reasons = {b.card_id: b.detail for b in diagnostic.blockers if b.code == "UNSUPPORTED_CARD_SELF_HAND"}
    assert reasons == {unsupported_declared: "DECLARED_UNSUPPORTED", undeclared: "UNDECLARED"}


def test_unsupported_self_hand_when_opponent_is_active_bites_at_turn_rotation():
    st = state(self_over={"hand_size": 1}, self_hand=[card("CATA_301", "LOCATION")], active_player="OPPONENT")
    blocker = next(b for b in analyze(st).blockers if b.code == "UNSUPPORTED_CARD_SELF_HAND")
    assert blocker.effective_applicability == ("TURN_ROTATION",)


def test_unknown_opponent_hand_identities_are_hidden_not_zero():
    hidden = analyze(state(opp_over={"hand_size": 5}, opponent_known_cards=[card(SUPPORTED_SPELL, "SPELL")]))
    row = next(b for b in hidden.blockers if b.code == "OPPONENT_HAND_IDENTITIES_UNKNOWN")
    assert row.detail == "hidden=4" and row.spec.nature == "INHERENTLY_HIDDEN"
    assert hidden.to_dict()["axes"]["hidden_information"] == "GAPS_PRESENT"
    assert "OPPONENT_HAND_IDENTITIES_UNKNOWN" not in codes(analyze(state(opp_over={"hand_size": 1}, opponent_known_cards=[card(SUPPORTED_SPELL, "SPELL")])))
    assert "SELF_HAND_IDENTITIES_UNKNOWN" in codes(analyze(state(self_over={"hand_size": 3}, self_hand=[card(SUPPORTED_SPELL, "SPELL")])))


def test_healing_bonus_known_zero_and_positive_versus_unknown():
    assert "HEALING_BONUS_UNKNOWN" in codes(analyze(state(self_over={"healing_bonus": None})))
    assert "HEALING_BONUS_UNKNOWN" not in codes(analyze(state(self_over={"healing_bonus": 0})))
    assert "HEALING_BONUS_UNKNOWN" not in codes(analyze(state(self_over={"healing_bonus": 2})))
    legacy = copy.deepcopy(state())
    del legacy["self_player"]["healing_bonus"]
    assert "HEALING_BONUS_UNKNOWN" in codes(analyze(legacy))  # absent key in an old snapshot stays unknown


def test_unknown_deck_composition_and_order():
    present = analyze(state(self_over={"deck_size": 12}, opp_over={"deck_size": 9}))
    assert {"SELF_DECK_COMPOSITION_UNKNOWN", "SELF_DECK_ORDER_UNKNOWN", "OPPONENT_DECK_COMPOSITION_UNKNOWN", "OPPONENT_DECK_ORDER_UNKNOWN"} <= codes(present)
    assert BLOCKER_SPECS["SELF_DECK_ORDER_UNKNOWN"].nature == "INHERENTLY_HIDDEN"
    assert BLOCKER_SPECS["SELF_DECK_COMPOSITION_UNKNOWN"].nature == "OBSERVABLE"  # a decklist would be an import input
    empty = analyze(state())
    assert not any("DECK" in code for code in codes(empty))


def test_hero_with_forty_health_exceeds_the_native_fixed_maximum():
    forty = analyze(state(self_over={"hero_health": 40, "hero_max_health": 40}))
    assert {"HERO_HEALTH_EXCEEDS_NATIVE_MAX", "HERO_MAX_HEALTH_UNSUPPORTED_NATIVE"} <= codes(forty)
    assert "HERO_MAX_HEALTH_UNKNOWN" not in codes(forty)
    thirty = analyze(state(self_over={"hero_health": 30}))
    assert not {"HERO_HEALTH_EXCEEDS_NATIVE_MAX", "HERO_MAX_HEALTH_UNKNOWN", "HERO_MAX_HEALTH_UNSUPPORTED_NATIVE"} & codes(thirty)


def test_hero_max_health_has_four_separate_outcomes():
    def seat_codes(**over):
        return {b.code for b in analyze(state(self_over=over)).blockers if b.seat == "SELF"}
    unknown = analyze(state(self_over={"hero_max_health": None}))
    assert "HERO_MAX_HEALTH_UNKNOWN" in codes(unknown) and unknown.to_dict()["known"]["hero_max_health"]["SELF"] == "UNKNOWN"
    historical = state()
    del historical["self_player"]["hero_max_health"]
    assert "HERO_MAX_HEALTH_UNKNOWN" in codes(analyze(historical))  # a historical state: absent is not 30
    # Known and valid, damaged or not: no hero-health blocker at all.
    for health, maximum in ((20, 30), (30, 30), (1, 30)):
        assert not {c for c in seat_codes(hero_health=health, hero_max_health=maximum) if c.startswith(("HERO_MAX", "HERO_HEALTH", "INTEGRITY"))}
    # Known but not the native fixed 30: unsupported by the engine, even when the hero is damaged below 30.
    damaged_forty = analyze(state(self_over={"hero_health": 25, "hero_max_health": 40}))
    assert damaged_forty.to_dict()["known"]["hero_max_health"]["SELF"] == "KNOWN_UNSUPPORTED_NATIVE"
    assert "HERO_MAX_HEALTH_UNSUPPORTED_NATIVE" in codes(damaged_forty) and "HERO_HEALTH_EXCEEDS_NATIVE_MAX" not in codes(damaged_forty)
    spec = BLOCKER_SPECS["HERO_MAX_HEALTH_UNSUPPORTED_NATIVE"]
    assert (spec.category.value, spec.axis, spec.resolution) == ("UNSUPPORTED_MECHANIC", "NATIVE", "ENGINE_PRIMITIVE")
    assert BLOCKER_SPECS["HERO_MAX_HEALTH_UNKNOWN"].category.value == "UNKNOWN"
    # Inconsistent: current above maximum, or a maximum that is not a positive integer.
    for over in ({"hero_health": 31, "hero_max_health": 30}, {"hero_max_health": 0}, {"hero_max_health": -4}, {"hero_max_health": True},
                 {"hero_max_health": "30"}, {"hero_max_health": 30.0}):
        diagnostic = analyze(state(self_over=over))
        assert "INTEGRITY_ENTITY_RANGE" in codes(diagnostic), over
        assert "INCONSISTENT" in diagnostic.categories() and not diagnostic.structurally_valid
        assert "HERO_MAX_HEALTH_UNSUPPORTED_NATIVE" not in codes(diagnostic)  # an invalid value is not reported as a valid one
    assert "HERO_MAX_HEALTH_NOT_REPRESENTED" not in BLOCKER_SPECS  # the unconditional blocker is gone


def test_hero_freeze_blocker_distinguishes_unknown_unfrozen_and_frozen_without_duration():
    def freeze(**over):
        return [b for b in analyze(state(self_over=over)).blockers if b.code == "HERO_FREEZE_UNKNOWN" and b.seat == "SELF"]
    assert freeze(hero_frozen=None, hero_freeze_turns_remaining=None)[0].detail == "frozen state unknown"
    assert freeze(hero_frozen=None, hero_freeze_turns_remaining=1)[0].detail == "frozen state unknown"
    assert freeze(hero_frozen=True, hero_freeze_turns_remaining=None)[0].detail == "frozen, duration unknown"
    assert not freeze(hero_frozen=True, hero_freeze_turns_remaining=1)
    # An explicitly unfrozen hero has no duration left to know.
    assert not freeze(hero_frozen=False, hero_freeze_turns_remaining=None)


def test_location_on_board_is_not_represented_natively():
    location = {"card": card("CATA_301", "LOCATION"), "current_health": 3, "max_health": 3, "board_position": 2, "on_cooldown": False}
    diagnostic = analyze(state(self_over={"board": [minion(position=1)], "locations": [location]}), action={"type": "ACTIVATE_LOCATION", "source_board_position": 2})
    row = next(b for b in diagnostic.blockers if b.code == "LOCATION_NOT_REPRESENTED_NATIVE")
    assert row.spec.category.value == "NOT_REPRESENTED" and row.spec.axis == "NATIVE"
    assert {"LOCATION_ACTIVATION_STATE_UNKNOWN", "UNSUPPORTED_CARD_LOCATION"} <= codes(diagnostic)
    activating = [b for b, effect in zip(diagnostic.blockers, diagnostic.chosen_effects) if b.code == "LOCATION_ACTIVATION_STATE_UNKNOWN"]
    assert activating and diagnostic.chosen_effects[diagnostic.blockers.index(activating[0])] == "BLOCKS"


def test_modified_minion_state_and_native_missing_keywords():
    modified = analyze(state(self_over={"board": [minion(attack=5, health=3)]}))
    assert "MINION_MODIFIER_PROVENANCE_NOT_REPRESENTED" in codes(modified)
    assert "MINION_MODIFIER_PROVENANCE_NOT_REPRESENTED" not in codes(analyze(state(self_over={"board": [minion()]})))
    keywords = analyze(state(opp_over={"board": [minion(position=1, windfury=True, poisonous=True)]}))
    assert next(b for b in keywords.blockers if b.code == "MINION_KEYWORD_NOT_NATIVE").detail == "windfury,poisonous"
    targeting = analyze(state(self_over={"board": [minion(cant_be_targeted_by_spells=True)]}))
    assert "MINION_TARGETING_RESTRICTION_NOT_NATIVE" in codes(targeting)
    unobserved = minion()
    unobserved["cant_be_targeted_by_spells"] = None
    assert "MINION_TARGETING_FLAGS_UNOBSERVED" in codes(analyze(state(self_over={"board": [unobserved]})))
    power = minion()
    power["card"]["mechanics"] = ["SPELLPOWER"]
    assert "SPELL_DAMAGE_UNOBSERVED" in codes(analyze(state(self_over={"board": [power]})))


def test_invalid_owner_board_and_order_information_is_inconsistent_and_never_raises():
    cases = {
        "duplicate slot": state(self_over={"board": [minion(position=1), minion(position=1)]}),
        "gap": state(self_over={"board": [minion(position=1), minion(position=3)]}),
        "unordered list": state(self_over={"board": [minion(position=2), minion(position=1)]}),
        "slot out of range": state(self_over={"board": [minion(position=9)]}),
        "dead minion on board": state(self_over={"board": [minion(health=0)]}),
        "max below current": state(self_over={"board": [{**minion(), "max_health": 1}]}),
        "invalid active player": state(active_player="NOBODY"),
        "eight entities": state(self_over={"board": [minion(position=index) for index in range(1, 9)]}),
        "missing field": {key: value for key, value in state().items() if key != "opponent"},
        "evidence debt in real state": state(evidence_constraints=["FIRE_POOL_MEMBERSHIP_INFERRED"]),
        "opponent secret identity": state(opp_over={"secret_count": 1, "known_secrets": [{"card_id": "X"}]}),
    }
    for name, st in cases.items():
        diagnostic = analyze(st)
        assert "INCONSISTENT" in diagnostic.categories(), name
        assert diagnostic.to_dict()["axes"]["source_completeness"] == "INCONSISTENT", name
    assert analyze(cases["duplicate slot"]).structurally_valid
    assert not analyze(cases["eight entities"]).structurally_valid


def test_shared_board_slots_with_a_location_are_valid_when_contiguous():
    location = {"card": card("CATA_301", "LOCATION"), "current_health": 3, "max_health": 3, "board_position": 2}
    diagnostic = analyze(state(self_over={"board": [minion(position=1), minion(position=3)], "locations": [location]}))
    assert "INTEGRITY_BOARD_ORDER" not in codes(diagnostic)


def test_live_trust_metadata_is_checked_without_inferring_anything():
    st = state()
    ok = {"status": "READY", "game_type": "GT_RANKED", "format": "FT_STANDARD", "phase": "SELF_DECISION", "opponent_identity_policy": "none"}
    assert "INTEGRITY_TRUST" not in codes(analyze(st, snapshot=ok))
    assert "INTEGRITY_TRUST" in codes(analyze(st, snapshot={**ok, "status": "SYNCING"}))
    assert "INTEGRITY_TRUST" in codes(analyze(st, snapshot={**ok, "format": "FT_WILD"}))
    exposed = state(opp_over={"hand_size": 1}, opponent_known_cards=[card(SUPPORTED_SPELL, "SPELL")])
    assert "INTEGRITY_OPPONENT_IDENTITY_EXPOSED" in codes(analyze(exposed, snapshot=ok))
    assert "INTEGRITY_OPPONENT_IDENTITY_EXPOSED" not in codes(analyze(exposed))


def test_pending_choice_and_player_effects_need_an_import_contract():
    st = state(pending_choice_owner="SELF", pending_choice_options=[card(SUPPORTED_SPELL, "SPELL")])
    st["self_player"]["active_effects"] = [{"card_id": "SOME_EFFECT"}]
    assert {"PENDING_CHOICE_CONTINUATION_NOT_REPRESENTED", "ACTIVE_EFFECT_NOT_REPRESENTED"} <= codes(analyze(st))


# -- next-action relevance ---------------------------------------------------------------------------------------------------


def test_blocker_must_involve_the_next_action_to_block_it():
    st = state(self_over={"board": [minion(position=1), minion("ZZZ_OTHER", position=2)]}, opp_over={"board": [minion(position=1)]})
    attack_first = analyze(st, action={"type": "ATTACK", "source_is_hero": False, "source_board_position": 1, "target_side": "OPPONENT",
                                       "target_board_position": 1, "target_is_hero": False})
    by_entity = {tuple(b.entity): effect for b, effect in zip(attack_first.blockers, attack_first.chosen_effects) if b.code == "UNSUPPORTED_CARD_NOT_IN_CATALOG"}
    # The unsupported minion at slot 2 is not part of the attack, but its passive behavior is unknown: undetermined, not cleared.
    assert by_entity == {("BOARD", "SELF", 2): "UNDETERMINED"}
    modified = analyze(state(self_over={"board": [minion(position=1, attack=9)]}), action={"type": "HERO_POWER"})
    effect = next(e for b, e in zip(modified.blockers, modified.chosen_effects) if b.code == "MINION_MODIFIER_PROVENANCE_NOT_REPRESENTED")
    assert effect == "NOT_INVOLVED"
    end_turn = analyze(state(self_over={"board": [minion(position=1, attack=9)]}), action={"type": "END_TURN"})
    effect = next(e for b, e in zip(end_turn.blockers, end_turn.chosen_effects) if b.code == "MINION_MODIFIER_PROVENANCE_NOT_REPRESENTED")
    assert effect == "BLOCKS"  # temporary buffs can expire at turn rotation
    assert analyze(state()).chosen_action is None and set(analyze(state()).chosen_effects) <= {"NOT_ASSESSED"}


def test_deck_and_healing_blockers_depend_on_the_action_effect():
    st = state(self_over={"deck_size": 5, "healing_bonus": None, "hand_size": 1}, self_hand=[card(SUPPORTED_SPELL, "SPELL")])
    end = analyze(st, action={"type": "END_TURN"})
    effects = dict(zip((b.code for b in end.blockers), end.chosen_effects))
    assert effects["SELF_DECK_ORDER_UNKNOWN"] == "BLOCKS" and effects["HEALING_BONUS_UNKNOWN"] == "UNDETERMINED"
    play = analyze(st, action={"type": "PLAY_CARD", "hand_index": 0, "card_id": SUPPORTED_SPELL})
    effects = dict(zip((b.code for b in play.blockers), play.chosen_effects))
    assert effects["SELF_DECK_ORDER_UNKNOWN"] in ("BLOCKS", "NOT_INVOLVED")
    assert CAP.has_effect(SUPPORTED_SPELL, "DRAW") == (effects["SELF_DECK_ORDER_UNKNOWN"] == "BLOCKS")


# -- capability, determinism, privacy, aggregation ------------------------------------------------------------------------


def test_capability_comes_from_declarations_not_a_second_list():
    summary = CAP.summary()
    assert summary["declarations"] == len(CAP.declared_card_ids)
    assert set(summary["effectively_supported_hero_powers"]) == set(CAP.supported_hero_power_ids)
    assert {"HERO_01bp", "HERO_05bp", "HERO_08bp", "HERO_09bp"} <= CAP.supported_hero_power_ids
    assert not CAP.card("HERO_09dbp").supported and not CAP.has_metadata("HERO_09dbp")
    engine_source = (ROOT / "src/manamind/integrations/manaengine/engine.py").read_text(encoding="utf-8")
    engine_files = re.findall(r'_ROOT / "(experiments/manaengine/data/[a-z0-9_]+\.json)"', engine_source)
    assert set(DEPENDENCY_FILES) | {"experiments/manaengine/data/card_abilities.json"} == set(engine_files)


def test_native_contract_matches_the_header_text():
    header = (ROOT / "experiments/manaengine/include/manaengine/engine.hpp").read_text(encoding="utf-8")
    for name in (*NATIVE_STATE_CONTRACT["player_fields"], *NATIVE_STATE_CONTRACT["minion_keywords"]):
        assert re.search(rf"\b{name}\b", header), name
    for gap in ("windfury", "poisonous", "dormant", "location", "imbue"):
        assert not re.search(rf"\b{gap}\b", header, re.IGNORECASE), gap
    assert "hero_power_id" in header and "hero_max_health" in header


def test_field_provenance_covers_every_player_observation_field():
    fields = set(PlayerObservation.__dataclass_fields__)
    assert fields - set(FIELD_PROVENANCE) == set()
    assert set(FIELD_PROVENANCE) - fields == set()


def test_identical_input_gives_byte_identical_output():
    st = state(self_over={"board": [minion(attack=7)], "deck_size": 3, "hand_size": 1}, self_hand=[card(UNSUPPORTED_ID)],
               opp_over={"hand_size": 4})
    first = canonical_dumps(analyze(st, action={"type": "END_TURN"}).to_dict())
    assert first == canonical_dumps(analyze(copy.deepcopy(st), action={"type": "END_TURN"}).to_dict())
    assert "NO_FROM_STATE_CONSTRUCTOR" in first


def test_analysis_never_mutates_or_completes_the_input():
    st = state(self_over={"healing_bonus": None, "hero_power": None})
    before = canonical_dumps(st)
    analyze(st)
    assert canonical_dumps(st) == before
    assert st["self_player"]["healing_bonus"] is None and st["self_player"]["hero_power"] is None


def test_historical_snapshot_without_new_fields_stays_readable():
    legacy = json.loads((ROOT / "data/samples/example_state.json").read_text(encoding="utf-8"))
    diagnostic = analyze(legacy)
    assert diagnostic.structurally_valid
    assert {"HERO_POWER_ID_UNKNOWN", "HEALING_BONUS_UNKNOWN", "TURN_COUNTERS_UNKNOWN"} <= codes(diagnostic)
    assert "INCONSISTENT" not in diagnostic.categories()
    assert not any(b.card_id == "UNKNOWN_CARD" for b in diagnostic.blockers)  # an unknown identity is not misread as a card ID
    stripped = {key: value for key, value in legacy["self_player"].items() if key != "armor"}
    assert "SOURCE_FIELD_ABSENT" in codes(analyze({**legacy, "self_player": stripped}))  # absent is unknown, not zero


def test_game_state_objects_are_accepted_too():
    from manamind.domain.serialization import game_state_from_dict
    domain_state = game_state_from_dict(state(self_over={"hand_size": 1}, self_hand=[card(SUPPORTED_SPELL, "SPELL")]))
    assert analyze(domain_state).structurally_valid


def test_live_snapshot_from_the_existing_session_is_analyzable():
    pytest.importorskip("hslog")
    sys.path.insert(0, str(ROOT / "tests"))
    from live_fixtures import LiveLog
    from manamind.cards.catalog import CardCatalog
    from manamind.live.session import LiveSession
    from manamind.live.snapshot import Snapshot
    session = LiveSession(CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json"))
    log = LiveLog().create_game().mulligan().self_decision(1)
    events = session.feed(log.lines, 1000) + session.tick(1150)
    snapshots = [event for event in events if isinstance(event, Snapshot)]
    assert snapshots
    envelope = snapshots[0].to_dict()
    diagnostic = analyze(envelope["state"], snapshot=envelope)
    assert diagnostic.structurally_valid and "INCONSISTENT" not in diagnostic.categories()
    assert "OPPONENT_HAND_IDENTITIES_UNKNOWN" in codes(diagnostic)


def position(game, number, st, action=None):
    return CorpusPosition(game, f"{game}:{number}", "POLICY_DECISION", number, st, action,
                          {"status": "READY", "game_type": "GT_RANKED", "format": "FT_STANDARD", "phase": "SELF_DECISION", "opponent_identity_policy": "none"})


def test_aggregation_counts_distinct_positions_with_overlapping_blockers():
    positions = [
        position("g1", 0, state(self_over={"hero_power": None}), {"type": "END_TURN"}),
        position("g1", 1, state(self_over={"hero_power": {"card_id": "EDR_449p", "current_cost": 2}, "healing_bonus": None}), {"type": "END_TURN"}),
        position("g2", 0, state(self_over={"hero_power": {"card_id": "EDR_449p", "current_cost": 2}}, opp_over={"hand_size": 2}), {"type": "HERO_POWER"}),
    ]
    metrics = aggregate(analyze_corpus(positions, CAP))
    assert (metrics["unique_games"], metrics["decision_positions"]) == (2, 3)
    ranking = {row["code"]: row for row in metrics["ranking"]}
    assert ranking["HERO_POWER_ID_UNKNOWN"]["distinct_positions"] == 1
    assert ranking["HERO_POWER_IMBUE"]["distinct_positions"] == 2 and ranking["HERO_POWER_IMBUE"]["distinct_games"] == 2
    assert ranking["HEALING_BONUS_UNKNOWN"]["distinct_positions"] == 1
    # Several blockers per position: the percentages overlap and must exceed 100% when summed.
    assert sum(entry["percent_positions"] for entry in metrics["categories"].values()) > 100
    assert metrics["hero_power"]["not_proven_supported_either_seat"]["positions"] == 3
    assert metrics["ready_for_import_design"]["native_hydration_possible_today"]["positions"] == 0
    cumulative = metrics["cumulative_resolution_effect"]
    assert [step["positions_with_no_remaining_non_hidden_blocker"] for step in cumulative] == sorted(step["positions_with_no_remaining_non_hidden_blocker"] for step in cumulative)
    sole = ranking["HERO_POWER_ID_UNKNOWN"]["positions_where_it_is_the_only_non_hidden_blocker"]
    assert sole <= ranking["HERO_POWER_ID_UNKNOWN"]["distinct_positions"]


def test_sample_is_deterministic_spread_over_games_and_independent_of_input_order():
    positions = []
    for game in range(8):
        for turn in range(1, 13):
            st = state(self_over={"board": [minion(position=index + 1) for index in range(turn % 5)]}, turn_number=turn)
            positions.append(position(f"game{game}", turn, st, {"type": "END_TURN" if turn % 2 else "HERO_POWER"}))
    first = select_sample(positions, 20, 7, per_game_cap=3)
    assert [p.position_id for p in first] == [p.position_id for p in select_sample(list(reversed(positions)), 20, 7, per_game_cap=3)]
    assert len(first) == 20 and len({p.game_id for p in first}) == 8
    assert max(sum(1 for p in first if p.game_id == game) for game in {p.game_id for p in first}) <= 3
    assert [p.position_id for p in first] != [p.position_id for p in select_sample(positions, 20, 8, per_game_cap=3)]
    assert select_sample([], 5, 1) == []


# -- corpus readers, CLI and report privacy ------------------------------------------------------------------------------


def write_policy_corpus(directory: Path):
    directory.mkdir(parents=True)
    hidden = "CANARY_OPPONENT_REVEALED_ID"
    for game in ("SENTINEL_GAME_ONE", "SENTINEL_GAME_TWO"):
        rows = []
        for number in range(4):
            st = state(self_over={"hand_size": 1, "board": [minion(position=1)]}, self_hand=[card(UNSUPPORTED_ID)], turn_number=number + 1,
                       opp_over={"hand_size": 1}, opponent_known_cards=[card(hidden)])
            action = {"type": "ATTACK", "source_board_position": 1, "target_side": "OPPONENT", "target_is_hero": True,
                      "attacker_entity_id": 987654, "player_name": "SENTINEL_PLAYER#1234"}
            rows.append({"schema_version": 1, "game_id": game, "decision_id": f"{game}:{number}", "state": st, "legal_actions": [{"type": "END_TURN"}, action],
                         "chosen_action_index": 1, "final_result": 1.0, "source": "power_log_ranked_standard", "provenance": {"state_hash": "f" * 64}})
        (directory / f"{game}.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        (directory / f"{game}.audit.json").write_text("{}", encoding="utf-8")
    return hidden


def test_cli_reports_are_deterministic_and_free_of_private_identifiers(tmp_path, capsys):
    hidden = write_policy_corpus(tmp_path / "policy")
    outputs = []
    for name in ("a", "b"):
        assert cli.main(["--policy-dir", str(tmp_path / "policy"), "--sample-size", "5", "--report-dir", str(tmp_path / name),
                         "--output-dir", str(tmp_path / f"local_{name}")]) == 0
        outputs.append({file: (tmp_path / name / file).read_bytes() for file in ("coverage.json", "blockers.json")})
    assert outputs[0] == outputs[1]
    text = "".join(blob.decode("utf-8") for blob in outputs[0].values())
    for forbidden in ("SENTINEL_GAME", "SENTINEL_PLAYER", hidden, "987654", "attacker_entity_id", "decision_id", "game_id"):
        assert forbidden not in text, forbidden
    assert not re.search(r"[0-9a-f]{32,}", text.replace(CAP.fingerprint, ""))  # only the repository-input fingerprint is a long hash
    assert "INTEGRITY_OPPONENT_IDENTITY_EXPOSED" in text  # the exposed revealed card is flagged, never echoed
    coverage = json.loads(outputs[0]["coverage.json"])
    assert coverage["data_availability"]["POLICY_DECISION"]["distinct_games"] == 2
    assert coverage["full_corpora"]["POLICY_DECISION"]["ready_for_import_design"]["native_hydration_possible_today"]["positions"] == 0
    local = (tmp_path / "local_a" / "sample_positions.jsonl").read_text(encoding="utf-8")
    assert "NO_FROM_STATE_CONSTRUCTOR" in local


def test_cli_refuses_to_overwrite_and_missing_directories_are_reported(tmp_path):
    write_policy_corpus(tmp_path / "policy")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["--policy-dir", str(tmp_path / "policy"), "--report-dir", str(tmp_path / "out")])
    assert (tmp_path / "out" / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert cli.main(["--policy-dir", str(tmp_path / "nowhere")]) == 0  # availability is reported, not invented


def test_readers_skip_unreadable_records_and_keep_sources_apart(tmp_path):
    write_policy_corpus(tmp_path / "policy")
    (tmp_path / "policy" / "broken.jsonl").write_text("{not json}\n[]\n", encoding="utf-8")
    positions, info = read_policy_positions(tmp_path / "policy")
    assert len(positions) == 8 and info["unreadable_records"] == 2
    live = tmp_path / "live" / "session" / "game"
    live.mkdir(parents=True)
    (live / "snapshots.jsonl").write_text(json.dumps({"game_key": "k", "seq": 1, "status": "SYNCING", "phase": "SELF_DECISION", "state": state()}) + "\n", encoding="utf-8")
    (live / "meta.json").write_text(json.dumps({"opponent_identity_policy": "none"}), encoding="utf-8")
    live_positions, _ = read_live_positions(tmp_path / "live")
    assert codes(analyze(live_positions[0].state, snapshot=live_positions[0].envelope)) >= {"INTEGRITY_TRUST"}
    (tmp_path / "value").mkdir()
    (tmp_path / "value" / "m.jsonl").write_text(json.dumps({"game_id": "v", "sample_id": "v-0", "state": state(self_over={"hand_size": 1}, self_hand=[card(SUPPORTED_SPELL, "SPELL")])}) + "\n", encoding="utf-8")
    value_positions, _ = read_value_positions(tmp_path / "value")
    value_codes = codes(analyze(value_positions[0].state, source_profile=value_positions[0].source_profile))
    assert {"SELF_HAND_ORDER_UNPROVEN", "SECRET_COUNT_NOT_EXTRACTED"} <= value_codes  # a stored 0 is a default there, not knowledge
    assert not {"SELF_HAND_ORDER_UNPROVEN", "SECRET_COUNT_NOT_EXTRACTED"} & codes(analyze(value_positions[0].state))
    with pytest.raises(ValueError):
        analyze(value_positions[0].state, source_profile="UNKNOWN_PROFILE")
