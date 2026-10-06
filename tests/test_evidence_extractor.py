"""Evidence extractor: attribution, SubSpell, support filtering, legality, hidden information."""

from __future__ import annotations

import json

from evidence_fixtures import EvLog, blk, flat, full, hide, meta, play_game, show, subspell, tag

from manamind.cards.catalog import CardCatalog
from manamind.evidence.extract import extract_game
from manamind.evidence.schema import validate_observation
from manamind.evidence.support import ScopeResolver, SupportInventory

CANARIES = ("CANARY_OVERRIDE", "CANARY_SHOW_THEN_HIDE", "CANARY_SECRET", "CANARY_DECK")


def run(log: EvLog, *, supported=(), include_secondary=False, control_counts=None, max_control=3):
    inventory = SupportInventory("test", "0" * 64, "DECLARATION_PROXY", {c: "SUPPORTED" for c in supported})
    result = extract_game(
        log.build_lines(), source_kind="COLLECTED_SLICE", inventory=inventory, scope=ScopeResolver(),
        catalog=CardCatalog(), catalog_sha256="0" * 64, include_secondary=include_secondary,
        control_counts=control_counts if control_counts is not None else {}, max_control_samples=max_control,
    )
    for observation in result.observations:
        validate_observation(observation)
    return result


def obs_for(result, card_id, role=None):
    found = [o for o in result.observations if o["subject"]["card_id"] == card_id
             and (role is None or o["subject"]["role"] == role)]
    assert found, f"no observation for {card_id}: {[o['subject'] for o in result.observations]}"
    return found[0]


def facts(observation, kind):
    return [f for f in observation["facts"] if f["kind"] == kind]


def attributed(fact):
    return fact["attribution"].get("attributed_to", {}).get("card_id")


# -- SubSpell ------------------------------------------------------------------------------------

def test_creation_inside_subspell_is_extracted():
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, subspell(
        full(70, "TEST_TOKEN", CARDTYPE="MINION", ZONE="PLAY", CONTROLLER=1, CREATOR=6))))
    result = run(play_game(body, entity=6))
    assert result.summary["walker_stats"]["subspell_packets"] >= 1
    created = facts(obs_for(result, "TEST_SPELL"), "ENTITY_CREATED")
    assert [f["data"]["entity"]["card_id"] for f in created] == ["TEST_TOKEN"]
    assert created[0]["attribution"]["basis"] == "CREATOR_TAG" and attributed(created[0]) == "TEST_SPELL"


# -- units, foreign triggers, watchers --------------------------------------------------------

def _foreign_trigger_play():
    body = flat(
        tag(6, "ZONE", "PLAY"),
        blk("POWER", 6, flat(meta("DAMAGE", 3, 50), tag(50, "DAMAGE", 3), tag(50, "LAST_AFFECTED_BY", 6))),
        blk("TRIGGER", 41, flat(
            full(70, "TEST_ENCH", CARDTYPE="ENCHANTMENT", ZONE="PLAY", CREATOR=41, ATTACHED=50),
            tag(50, "ATK", 3))),
        blk("TRIGGER", 41, []),
    )
    return play_game(body, entity=6, target=50, targets=[(50, "PLAY", 1, "TEST_ENEMY", 2, None)])


def test_foreign_nested_trigger_is_nested_only_and_empty_watcher_is_counted():
    result = run(_foreign_trigger_play())
    spell = obs_for(result, "TEST_SPELL", "PLAYED_CARD")
    damage = facts(spell, "DAMAGE_PACKET")[0]
    assert damage["attribution"]["basis"] == "LAST_AFFECTED_BY_SAME_UNIT" and attributed(damage) == "TEST_SPELL"
    assert damage["data"]["amount"] == 3 and damage["data"]["damage_tag_after"] == 3
    foreign = [f for f in spell["facts"] if f["unit_id"] == "u2" and f["kind"] in ("ENCHANTMENT_ATTACHED", "STAT_DELTA")]
    assert foreign and all(f["attribution"]["basis"] == "NESTED_ONLY" for f in foreign)
    assert all(attributed(f) == "TEST_FRIEND" for f in foreign)
    assert spell["window"]["empty_watcher_trigger_count"] == 1
    assert spell["attribution_summary"]["own_effect_facts"] == 1
    assert spell["attribution_summary"]["nested_only_facts"] == 2
    kinds = {c["kind"] for c in spell["confounders"]}
    assert "FOREIGN_UNIT_WITH_EFFECTS_IN_WINDOW" in kinds
    # the foreign unit is its own subject; the spell's damage is nested-only from its point of view
    friend = obs_for(result, "TEST_FRIEND")
    assert friend["subject"]["role"] == "TRIGGER_SOURCE"
    assert {f["attribution"]["basis"] for f in facts(friend, "DAMAGE_PACKET")} == {"NESTED_ONLY"}


def test_creator_tag_beats_block_owner_in_both_directions():
    body = flat(
        tag(6, "ZONE", "PLAY"),
        # created inside the spell's own unit, but the game says the minion made it
        blk("POWER", 6, full(70, "TEST_E1", CARDTYPE="ENCHANTMENT", ZONE="PLAY", CREATOR=41, ATTACHED=50)),
        # created inside the minion's trigger, but the game says the spell made it
        blk("TRIGGER", 41, full(71, "TEST_E2", CARDTYPE="ENCHANTMENT", ZONE="PLAY", CREATOR=6, ATTACHED=50)),
    )
    spell = obs_for(run(play_game(body, entity=6)), "TEST_SPELL", "PLAYED_CARD")
    by_card = {f["data"]["enchantment"]["card_id"]: f for f in facts(spell, "ENCHANTMENT_ATTACHED")}
    assert by_card["TEST_E1"]["attribution"]["basis"] == "NESTED_ONLY" and attributed(by_card["TEST_E1"]) == "TEST_FRIEND"
    assert by_card["TEST_E2"]["attribution"]["basis"] == "CREATOR_TAG" and attributed(by_card["TEST_E2"]) == "TEST_SPELL"


def test_enchantment_chain_resolves_to_the_original_creator():
    body = flat(
        tag(6, "ZONE", "PLAY"),
        blk("POWER", 6, flat(
            full(70, "TEST_E1", CARDTYPE="ENCHANTMENT", ZONE="PLAY", CREATOR=6, ATTACHED=41),
            full(71, "TEST_E2", CARDTYPE="ENCHANTMENT", ZONE="PLAY", CREATOR=70, ATTACHED=41))),
    )
    spell = obs_for(run(play_game(body, entity=6)), "TEST_SPELL", "PLAYED_CARD")
    chained = [f for f in facts(spell, "ENCHANTMENT_ATTACHED") if f["data"]["enchantment"]["card_id"] == "TEST_E2"][0]
    assert chained["attribution"]["basis"] == "CREATOR_TAG" and attributed(chained) == "TEST_SPELL"
    assert chained["attribution"]["via_creator_chain"] == [70, 6]


def test_last_affected_by_is_used_only_when_set_in_the_same_unit():
    stale_before = tag(50, "LAST_AFFECTED_BY", 41)  # sticky value from an earlier effect, outside every unit
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(meta("DAMAGE", 2, 50), tag(50, "DAMAGE", 2))))
    spell = obs_for(run(play_game(body, entity=6, before=stale_before)), "TEST_SPELL", "PLAYED_CARD")
    damage = facts(spell, "DAMAGE_PACKET")[0]
    assert damage["attribution"]["basis"] == "UNIT_OWNER" and attributed(damage) == "TEST_SPELL"
    stale = [c for c in spell["confounders"] if c["kind"] == "STALE_LAST_AFFECTED_BY"]
    assert stale and stale[0]["entity"]["card_id"] == "TEST_FRIEND" and "DAMAGE_AMOUNT" in stale[0]["affects_claim_kinds"]


def test_foreign_enchantment_rewriting_an_effect_is_a_confounder():
    before = full(70, "TEST_REWRITE_E", CARDTYPE="ENCHANTMENT", ZONE="PLAY", CONTROLLER=1, CREATOR=41, ATTACHED=4)
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(
        meta("DAMAGE", 8, 5), tag(5, "DAMAGE", 8), tag(5, "LAST_AFFECTED_BY", 6),
        blk("TRIGGER", 70, tag(70, "ZONE", "GRAVEYARD")))))
    spell = obs_for(run(play_game(body, entity=6, before=before)), "TEST_SPELL", "PLAYED_CARD")
    active = [c for c in spell["confounders"] if c["kind"] == "FOREIGN_ENCHANTMENT_ACTIVE"]
    assert active and "DAMAGE_AMOUNT" in active[0]["affects_claim_kinds"] and "HEAL_AMOUNT" in active[0]["affects_claim_kinds"]
    assert spell["attribution_summary"]["ambiguous"] is True
    assert "DAMAGE_AMOUNT" in spell["attribution_summary"]["confounded_claim_kinds"]
    # the packet is still recorded as a fact; it is simply not clean
    assert facts(spell, "DAMAGE_PACKET")[0]["data"]["amount"] == 8


def test_unattributed_root_packets_make_an_observation_ambiguous():
    body = flat(tag(6, "ZONE", "PLAY"), meta("DAMAGE", 2, 50), tag(50, "DAMAGE", 2))  # directly in the root unit
    spell = obs_for(run(play_game(body, entity=6)), "TEST_SPELL", "PLAYED_CARD")
    assert facts(spell, "DAMAGE_PACKET")[0]["attribution"]["basis"] == "UNATTRIBUTED"
    summary = spell["attribution_summary"]
    assert summary["tier"] == "NO_ATTRIBUTED_EFFECTS" and summary["ambiguous"] is True
    assert summary["unattributed_effect_facts"] == 1 and summary["own_effect_facts"] == 0


def test_noop_unit_still_yields_an_observation_without_a_negative_claim():
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, []))
    spell = obs_for(run(play_game(body, entity=6)), "TEST_SPELL", "PLAYED_CARD")
    assert spell["attribution_summary"]["own_effect_facts"] == 0
    assert spell["attribution_summary"]["tier"] == "NO_ATTRIBUTED_EFFECTS"
    assert spell["inferences"] == [] and not any(f["kind"] in ("DAMAGE_PACKET", "ENTITY_CREATED") for f in spell["facts"])
    assert "ABSENCE_OF_AN_EFFECT_IS_NOT_A_NEGATIVE_RULE" in spell["evidence_limits"]
    assert "NO_VISIBLE_EFFECT" not in json.dumps(spell)  # no negative claim is ever emitted by the extractor


def test_random_outcomes_are_single_draws_never_a_pool():
    outcomes = {}
    for seed, token in ((1, "TEST_TOKEN_A"), (2, "TEST_TOKEN_B")):
        body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, full(
            70, token, CARDTYPE="MINION", ZONE="PLAY", CONTROLLER=1, CREATOR=6)))
        spell = obs_for(run(play_game(body, entity=6, seed=seed)), "TEST_SPELL", "PLAYED_CARD")
        outcomes[token] = spell
        created = facts(spell, "ENTITY_CREATED")[0]
        assert created["attribution"]["basis"] == "CREATOR_TAG" and created["data"]["entity"]["card_id"] == token
    for spell in outcomes.values():
        text = json.dumps(spell)
        assert "pool" not in text and "probab" not in text and "candidates" not in text
        assert "OBSERVED_OUTCOMES_ARE_SINGLE_DRAWS_NOT_POOLS" in spell["evidence_limits"]
        assert "TEST_TOKEN_A" not in text or "TEST_TOKEN_B" not in text  # no cross-game outcome set


# -- inferences are never facts ------------------------------------------------------------------

def test_inferences_reference_facts_and_are_never_facts():
    before = full(60, "TEST_VICTIM", CARDTYPE="MINION", ZONE="PLAY", CONTROLLER=2, HEALTH=2, DAMAGE=0)
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(
        meta("DAMAGE", 3, 60), tag(60, "DAMAGE", 3), tag(60, "LAST_AFFECTED_BY", 6)), ),
        blk("DEATHS", 1, tag(60, "ZONE", "GRAVEYARD")))
    spell = obs_for(run(play_game(body, entity=6, before=before)), "TEST_SPELL", "PLAYED_CARD")
    kinds = {i["kind"] for i in spell["inferences"]}
    assert "DEATH_BY_DAMAGE" in kinds
    fact_ids = {f["fact_id"] for f in spell["facts"]}
    for inference in spell["inferences"]:
        assert inference["inputs"] and set(inference["inputs"]) <= fact_ids
        assert inference["kind"] not in {f["kind"] for f in spell["facts"]}
    assert all("inputs" not in f for f in spell["facts"])


# -- support filtering ------------------------------------------------------------------------

def test_supported_cards_are_capped_control_samples_and_unsupported_are_novel():
    counts: dict[str, int] = {}
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(meta("DAMAGE", 1, 50), tag(50, "DAMAGE", 1))))
    first = run(play_game(body, entity=6), supported={"TEST_SPELL"}, control_counts=counts, max_control=1)
    sample = obs_for(first, "TEST_SPELL")
    assert sample["subject"]["role"] == "CONTROL_SAMPLE" and sample["triage"] == "CONTROL_UNCOMPARED"
    assert sample["support_detection"]["subject_support_state"] == "SUPPORTED"
    second = run(play_game(body, entity=6, seed=9), supported={"TEST_SPELL"}, control_counts=counts, max_control=1)
    assert not [o for o in second.observations if o["subject"]["card_id"] == "TEST_SPELL"]

    body_minion = flat(tag(7, "ZONE", "PLAY"), blk("POWER", 7, flat(meta("DAMAGE", 1, 50), tag(50, "DAMAGE", 1))))
    novel = obs_for(run(play_game(body_minion, entity=7), supported={"TEST_SPELL"}), "TEST_MINION")
    assert novel["triage"] == "NOVEL_OBSERVATION" and novel["subject"]["role"] == "PLAYED_CARD"
    assert novel["support_detection"]["basis"] == "DECLARATION_PROXY"
    assert novel["support_detection"]["subject_support_state"] == "UNSUPPORTED_NO_DECLARATION"


# -- server legality evidence ----------------------------------------------------------------

def test_server_options_become_target_legality_facts():
    targets = [(50, "PLAY", 1, "TEST_ENEMY", 2, None), (41, "PLAY", 1, "TEST_FRIEND", 1, "REQ_ENEMY_TARGET"),
               (4, "PLAY", 0, "HERO_01", 1, "REQ_MINION_TARGET")]
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(meta("DAMAGE", 1, 50), tag(50, "DAMAGE", 1))))
    spell = obs_for(run(play_game(body, entity=6, target=50, targets=targets)), "TEST_SPELL", "PLAYED_CARD")
    legality = facts(spell, "TARGET_LEGALITY")
    rows = {f["data"]["target"]["card_id"]: (f["data"]["accepted"], f["data"]["server_error_code"]) for f in legality}
    assert rows == {"TEST_ENEMY": (True, None), "TEST_FRIEND": (False, "REQ_ENEMY_TARGET"),
                    "HERO_01": (False, "REQ_MINION_TARGET")}
    assert all(f["visibility"] == "SELF_PRIVATE" and f["data"]["option_card"]["card_id"] == "TEST_SPELL" for f in legality)
    assert all(f["data"]["option_accepted"] for f in legality)


def test_opponent_plays_have_no_legality_evidence_and_reveal_their_identity():
    log = EvLog().create().start_turn(1, 2)
    log.power(blk("PLAY", 20, flat(
        show(20, "TEST_OPP_SPELL", CARDTYPE="SPELL", ZONE="HAND", CONTROLLER=2), tag(20, "ZONE", "PLAY"),
        blk("POWER", 20, flat(meta("DAMAGE", 2, 41), tag(41, "DAMAGE", 2), tag(41, "LAST_AFFECTED_BY", 20))))))
    log.start_turn(2, 1).hand_option(6)  # the server's validation of SELF's options identifies SELF
    log.complete()
    opp = obs_for(run(log), "TEST_OPP_SPELL", "PLAYED_CARD")
    assert opp["subject"]["side"] == "OPPONENT" and not facts(opp, "TARGET_LEGALITY")
    assert facts(opp, "DAMAGE_PACKET")[0]["attribution"]["basis"] == "LAST_AFFECTED_BY_SAME_UNIT"


# -- hidden information ---------------------------------------------------------------------

def test_hidden_identities_never_reach_the_output():
    before = flat(
        show(22, "CANARY_SECRET", CARDTYPE="SPELL", ZONE="SECRET", CONTROLLER=2),
        show(30, "CANARY_DECK", ZONE="DECK", CONTROLLER=2),
    )
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(
        meta("DAMAGE", 1, 50), tag(50, "DAMAGE", 1), tag(50, "LAST_AFFECTED_BY", 6),
        meta("OVERRIDE_HISTORY", 0, 1),
        show(20, "CANARY_OVERRIDE", ZONE="HAND", CONTROLLER=2),
        show(21, "CANARY_SHOW_THEN_HIDE", ZONE="HAND", CONTROLLER=2),
        hide(21, "HAND", "CANARY_SHOW_THEN_HIDE", 2, 2),
        blk("TRIGGER", 22, tag(50, "ATK", 9)),  # a hidden secret's trigger: not an extractable subject
    )))
    result = run(play_game(body, entity=6, before=before))
    assert not any(name in json.dumps(result.observations) for name in CANARIES)
    spell = obs_for(result, "TEST_SPELL", "PLAYED_CARD")
    reveals = facts(spell, "ENTITY_REVEALED")
    assert reveals and all(f["visibility"] == "OFFLINE_ONLY_HIDDEN" and f["data"]["entity"]["card_id"] is None
                           for f in reveals)
    assert spell["privacy"]["contains_offline_only_hidden"] is True and spell["privacy"]["model_input_allowed"] is False
    assert result.summary["counters"]["subjects_skipped_hidden_identity"] >= 1
    assert not any("CANARY" in line for o in result.observations for line in o["public_states"]["public_delta"])


# -- SELF detection -----------------------------------------------------------------------------

def test_self_is_resolved_for_both_player_orders():
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(meta("DAMAGE", 1, 50), tag(50, "DAMAGE", 1))))
    for self_pid in (1, 2):
        result = run(play_game(body, entity=6, self_pid=self_pid))
        spell = obs_for(result, "TEST_SPELL", "PLAYED_CARD")
        assert result.summary["status"] == "PROCESSED" and spell["subject"]["side"] == "SELF"
        assert facts(spell, "TARGET_LEGALITY")


def test_self_resolves_when_the_opponent_acts_first():
    log = EvLog(self_pid=2).create().start_turn(1, 1)
    log.power(blk("PLAY", 20, flat(show(20, "TEST_OPP_SPELL", CARDTYPE="SPELL", ZONE="HAND", CONTROLLER=1),
                                    tag(20, "ZONE", "PLAY"))))
    log.start_turn(2, 2).hand_option(6)
    log.power(blk("PLAY", 6, tag(6, "ZONE", "PLAY"))).complete()
    # entity 20 belongs to player 2 in the layout; the point here is only the options-after-play ordering
    result = run(log)
    assert result.summary["status"] == "PROCESSED"
    assert obs_for(result, "TEST_SPELL")["subject"]["side"] == "SELF"


def test_self_disagreement_or_missing_cross_check_skips_the_game():
    disagree = EvLog().create().start_turn(1, 1)
    disagree.options([(20, "HAND", 1, "TEST_X", None, [])])  # the server validated an entity of player 2
    disagree.power(blk("PLAY", 6, tag(6, "ZONE", "PLAY"))).complete()
    assert run(disagree).summary["reason"] == "SELF_DISAGREE"

    no_options = EvLog().create().start_turn(1, 1)
    no_options.power(blk("PLAY", 6, tag(6, "ZONE", "PLAY"))).complete()
    result = run(no_options)
    assert result.summary["reason"] == "SELF_UNVERIFIED" and result.observations == []


# -- provenance, unknown ids, modes ---------------------------------------------------------

def test_unknown_ids_build_and_mode_are_recorded():
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(
        meta("DAMAGE", 1, 50), tag(50, "DAMAGE", 1), tag(50, "4297", 1))), blk("TRIGGER", 41, tag(50, "ATK", 5), keyword=4297))
    spell = obs_for(run(play_game(body, entity=6)), "TEST_SPELL", "PLAYED_CARD")
    provenance = spell["provenance"]
    assert "4297" in provenance["unknown_tag_ids_in_window"]
    assert provenance["client_build"] == 253216 and provenance["game_type"] == "GT_RANKED"
    assert provenance["rules_scope"] == "STANDARD_PRIMARY" and provenance["source"] == "POWER_LOG"
    assert any(u["trigger_keyword"] == 4297 for u in spell["window"]["units"])  # numeric keywords stay numbers


def test_non_primary_modes_are_skipped_or_tagged_secondary():
    body = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(meta("DAMAGE", 1, 50), tag(50, "DAMAGE", 1))))
    wild = play_game(body, entity=6, game_type="GT_VS_AI", format_type="FT_WILD")
    skipped = run(wild)
    assert skipped.summary["reason"] == "UNSUPPORTED_MODE" and skipped.observations == []
    secondary = obs_for(run(wild, include_secondary=True), "TEST_SPELL", "PLAYED_CARD")
    assert secondary["provenance"]["rules_scope"] == "OTHER_MODE_SECONDARY"
    assert "MODE_OR_BUILD_OUTSIDE_SCOPE" in {c["kind"] for c in secondary["confounders"]}


def test_incomplete_games_are_skipped():
    log = EvLog().create().start_turn(1, 1).hand_option(6)
    log.power(blk("PLAY", 6, tag(6, "ZONE", "PLAY")))
    assert run(log).summary["reason"] == "INCOMPLETE"


def test_derived_inferences_for_battlecry_blocks_and_stat_changes():
    body = flat(tag(7, "ZONE", "PLAY"), blk("POWER", 7, flat(
        full(70, "TEST_E", CARDTYPE="ENCHANTMENT", ZONE="PLAY", CREATOR=7, ATTACHED=41),
        tag(41, "ATK", 4), tag(41, "HEALTH", 6))), blk("TRIGGER", 41, tag(41, "ATK", 5)))
    minion = obs_for(run(play_game(body, entity=7)), "TEST_MINION", "PLAYED_CARD")
    kinds = [i["kind"] for i in minion["inferences"]]
    assert "BATTLECRY_FROM_OWN_POWER_BLOCK" in kinds and "STAT_CHANGE_EXPLAINED_BY_ENCHANTMENT" in kinds
    battlecry = [i for i in minion["inferences"] if i["kind"] == "BATTLECRY_FROM_OWN_POWER_BLOCK"][0]
    assert battlecry["status"] == "ASSUMPTION_DEPENDENT" and battlecry["assumptions"]
