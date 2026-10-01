from scripts.build_standard_registry import (
    dynamic_pool_hypotheses,
    evidence_freshness,
    reachable_closure,
)


def test_keyword_only_batch_is_counted_as_generated_and_stays_unverified():
    import json
    from pathlib import Path

    registry = json.loads(Path("data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))
    for card_id in ("CORE_GIL_558", "CORE_ULD_723", "EDR_486", "END_031", "RLK_067"):
        row = registry["cards"][card_id]
        assert row["implementation"]["generated_owner"] == "keyword_only"
        assert row["implementation"]["registration_status"] == "GENERATED_KEYWORD_ONLY"
        assert row["rules_verification"]["status"] == "IMPLEMENTED_UNVERIFIED"
        assert row["training_eligibility"]["status"] == "BLOCKED"


def test_damage_battlecry_batch_is_counted_as_generated_and_stays_unverified():
    import json
    from pathlib import Path

    registry = json.loads(Path("data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))
    for card_id in ("CORE_UNG_084", "CORE_OG_149", "CORE_CS2_024", "CORE_CS2_094", "CORE_EX1_129",
                    "CORE_TSC_076", "CORE_GVG_061", "CORE_BOT_222", "CORE_BOT_451", "CORE_RLK_062",
                    "CORE_LOOT_368"):
        row = registry["cards"][card_id]
        assert row["implementation"]["generated_owner"] == "effect_composition"
        assert row["implementation"]["registration_status"] == "GENERATED_EFFECT_COMPOSITION"
        assert row["rules_verification"]["status"] == "IMPLEMENTED_UNVERIFIED"
        assert row["training_eligibility"]["status"] == "BLOCKED"


def test_voltaic_burst_declares_its_metadata_only_rush_token_dependency():
    import json
    from pathlib import Path

    registry = json.loads(Path("data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))
    row = registry["cards"]["CORE_BOT_451"]
    assert row["implementation"]["generated_owner"] == "effect_composition"
    assert row["rules_verification"]["status"] == "IMPLEMENTED_UNVERIFIED"
    assert row["dependency_closure"]["known_source_candidate_ids"] == ["BOT_102t"]
    assert row["training_eligibility"]["status"] == "BLOCKED"


def test_nerubian_swarmguard_self_summon_is_scoped_and_still_blocked_for_dk_setup():
    import json
    from pathlib import Path

    registry = json.loads(Path("data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))
    row = registry["cards"]["CORE_RLK_062"]
    assert row["implementation"]["generated_owner"] == "effect_composition"
    assert row["rules_verification"]["status"] == "IMPLEMENTED_UNVERIFIED"
    assert row["bridge_action_support"]["status"] == "NOT_AUDITED"
    assert row["training_eligibility"]["status"] == "BLOCKED"


def test_voidlord_deathrattle_tracks_its_registered_voidwalker_dependency():
    import json
    from pathlib import Path

    registry = json.loads(Path("data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))
    row = registry["cards"]["CORE_LOOT_368"]
    assert row["implementation"]["generated_owner"] == "effect_composition"
    assert row["dependency_closure"]["known_source_candidate_ids"] == ["CS2_065"]
    assert row["rules_verification"]["status"] == "IMPLEMENTED_UNVERIFIED"
    assert row["training_eligibility"]["status"] == "BLOCKED"


def test_derived_core_alias_batch_keeps_provenance_and_training_blockers():
    import json
    from pathlib import Path

    manifest = json.loads(Path("integrations/rosettastone/card_rules/core_aliases.generated.json").read_text(encoding="utf-8"))
    aliases = {row["card_id"]: row for row in manifest["cards"]}
    registry = json.loads(Path("data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))
    for card_id, base_id in (("CORE_BT_292", "BT_292"), ("CORE_EX1_189", "EX1_189"), ("CORE_UNG_809", "UNG_809")):
        alias = aliases[card_id]
        assert alias["base_card_id"] == base_id
        assert alias["copy_of_dbf_id"] is None
        assert alias["match_basis"] == "DERIVED_CORE_ID_AND_EXACT_RULES_TEXT"
        row = registry["cards"][card_id]
        assert row["implementation"]["generated_owner"] == "core_alias"
        assert row["rules_verification"]["status"] == "IMPLEMENTED_UNVERIFIED"
        assert row["training_eligibility"]["status"] == "BLOCKED"


def test_cycle_with_unverified_exit_remains_in_reachable_closure():
    adjacency = {"root": ["a"], "a": ["b"], "b": ["a", "unsupported_exit"]}
    assert reachable_closure(adjacency, "root") == {"a", "b", "unsupported_exit"}


def test_pool_rule_change_invalidates_evidence_even_when_membership_is_unchanged():
    evidence = {
        "rules_fingerprint": "rules-1",
        "pool_membership_sha256": "same-membership",
        "pool_predicate_version": "predicate-1",
        "capability_fingerprint": "cap-1",
        "engine_build_fingerprint": "build-1",
        "scenario_fingerprint": "scenario-1",
    }
    current = {**evidence, "pool_predicate_version": "predicate-2"}
    assert current["pool_membership_sha256"] == evidence["pool_membership_sha256"]
    assert evidence_freshness(evidence, current) == "STALE"


def test_evidence_without_complete_execution_identity_is_not_current():
    assert evidence_freshness({"rules_fingerprint": "rules-1"}, {"rules_fingerprint": "rules-1"}) == "STALE_OR_INCOMPLETE"


def test_random_board_target_is_not_classified_as_a_card_pool():
    assert dynamic_pool_hypotheses("Deal 2 damage to a random enemy minion.") == []
    assert dynamic_pool_hypotheses("Give a random friendly minion +2 Attack.") == []


def test_discover_and_random_card_outcomes_remain_pool_candidates():
    assert dynamic_pool_hypotheses("Discover a Beast.") == ["discover"]
    assert dynamic_pool_hypotheses("Add a random Mage spell to your hand.") == ["random_card_or_pool"]
    assert dynamic_pool_hypotheses("Summon a random minion from your opponent's deck.") == ["random_card_or_pool", "generated_card"]
    assert dynamic_pool_hypotheses("Get a random\nDragon that costs 3 or less.") == ["random_card_or_pool"]
    assert dynamic_pool_hypotheses("Fill your hand with random Dragons.") == ["random_card_or_pool"]


def test_state_and_history_dependent_card_outcomes_remain_pool_candidates():
    assert dynamic_pool_hypotheses("Copy a card in your opponent's deck and add it to your hand.") == ["generated_card"]
    assert dynamic_pool_hypotheses("Copy a card in your opponent\ufffds deck.") == ["generated_card"]
    assert dynamic_pool_hypotheses("Summon every minion killed by this weapon.") == ["generated_card"]
    assert dynamic_pool_hypotheses("Resurrect minions that died this game.") == ["generated_card"]
    assert dynamic_pool_hypotheses("Draw a minion. Summon an 8/8 copy of it.") == ["generated_card"]


def test_fixed_named_token_summon_is_not_a_dynamic_pool():
    assert dynamic_pool_hypotheses("Summon two 1/1 Cannoneers.") == []
    assert dynamic_pool_hypotheses("Choose One: Summon two Dormant Dreadseeds; or deal damage to all minions.") == []


def test_metadata_only_minions_are_generated_but_not_rules_verified_or_training_eligible():
    import json
    from pathlib import Path

    registry = json.loads(Path("data/cards/standard_registry_20261001_enUS.json").read_text(encoding="utf-8"))
    for card_id in ("Core_CS2_200", "TIME_053", "TLC_248"):
        row = registry["cards"][card_id]
        assert row["implementation"]["generated_owner"] == "metadata_only"
        assert row["implementation"]["registration_status"] == "GENERATED_METADATA_ONLY"
        assert row["rules_verification"]["status"] == "METADATA_ONLY_CANDIDATE"
        assert row["dependency_closure"]["known_source_candidate_ids"] == []
        assert row["training_eligibility"]["status"] == "BLOCKED"
