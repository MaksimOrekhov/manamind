"""PREPARE-ROOTS-1: a Prepare card lists two roots for one hand entity; map them to PLAY_CARD / PREPARE_CARD.

Synthetic logs only. The role of a root is accepted only where the options message itself decides it (affordability
of the normal play, or which root needs a target), never from the order of the roots, and every other pattern stays
refused. The feature is experimental and off by default.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from live_fixtures import CANARIES, LiveLog, desc  # noqa: E402
from test_live_recommendation import ready, recommender  # noqa: E402,F401  (fixture)
from test_policy_v2 import model, scene  # noqa: E402
from test_real_policy_dataset import CATALOG  # noqa: E402
from test_policy_v3 import model as model_v3  # noqa: E402

from manamind.domain.policy_action import ACTION_FIELDS, ACTION_TYPES, PREPARE_ACTION_TYPES  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.integrations.powerlog.policy_actions import map_actions  # noqa: E402
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.live.recommendation import RecommendationUnavailable  # noqa: E402
from manamind.models.policy import ACTION_FEATURE_NAMES, encode_legal_actions  # noqa: E402
from manamind.models.policy_inputs import encode_policy_inputs  # noqa: E402
from manamind.models.policy_v2 import ACTION_V2_FEATURE_NAMES, encode_policy_v2  # noqa: E402
from manamind.training.real_policy import validate_example  # noqa: E402

HAND = desc(6, "HAND", 1, "CS2_029", 1)
TARGET = desc(50, "PLAY", 1, "CS2_168", 2)


def prepare_log(roots, *, mana=3, cost=5, deck_action_cost=1, send=1, target=0, block="DECK_ACTION",
                tradeable=False, prepare=True, seed=1):
    """SELF hand card 6 with two roots. ``roots`` is [(error, lists_a_target), ...] in listed order (option 1, 2)."""
    log = LiveLog(seed=seed).create_game().mulligan()
    tags = ["CARDTYPE value=SPELL", f"COST value={cost}"]
    if prepare:
        tags += ["PREPARE value=1", f"DECK_ACTION_COST value={deck_action_cost}"]
    if tradeable:
        tags.append("TRADEABLE value=1")
    log.batch([f"TAG_CHANGE Entity=6 tag={tag}" for tag in tags]).finish_list()
    log.begin_turn(1, mana=mana)
    log.options_id += 1
    log.raw("GameState", "DebugPrintOptions", f"id={log.options_id}")
    log.raw("GameState", "DebugPrintOptions", "option 0 type=END_TURN mainEntity= error=INVALID errorParam=")
    for number, (error, has_target) in enumerate(roots, 1):
        log.raw("GameState", "DebugPrintOptions",
                f"option {number} type=POWER mainEntity={HAND} error={error} errorParam=")
        if has_target:
            log.raw("GameState", "DebugPrintOptions", f"target 0 entity={TARGET} error=NONE errorParam=")
    log.raw("GameState", "SendOption",
            f"selectedOption={send} selectedSubOption=-1 selectedTarget={target} selectedPosition=0")
    log.p(f"BLOCK_START BlockType={block} Entity={HAND} EffectCardId= EffectIndex=0 Target=0 SubOption=-1")
    log.p("BLOCK_END")
    log.p("TAG_CHANGE Entity=2 tag=PLAYSTATE value=WON")
    log.p("TAG_CHANGE Entity=3 tag=PLAYSTATE value=LOST")
    return log.complete()


def label(log, **kwargs):
    rows, summary = extract_match(log.lines, CATALOG, **kwargs)
    return rows, summary


def types(row):
    return [a["type"] for a in row["legal_actions"]]


def chosen(row):
    return row["legal_actions"][row["chosen_action_index"]]


# -- off by default: the version 1 behaviour is unchanged -------------------------------------------------------------

def test_default_keeps_refusing_a_prepare_card_as_ambiguous():
    rows, summary = label(prepare_log([("NONE", False), ("REQ_ENOUGH_MANA", False)]))
    assert rows == [] and summary["skip_reasons"] == {"AMBIGUOUS_SELECTION": 1}


# -- affordability decides the role ----------------------------------------------------------------------------------

def test_only_the_cheap_root_is_legal_it_is_prepare_whatever_the_listed_order():
    for roots, send in (([("NONE", False), ("REQ_ENOUGH_MANA", False)], 1),
                        ([("REQ_ENOUGH_MANA", False), ("NONE", False)], 2)):
        rows, summary = label(prepare_log(roots, send=send), prepare_actions=True)
        assert summary["decisions_labeled"] == 1, summary
        row = rows[0]
        assert row["action_schema_version"] == 2
        assert sorted(types(row)) == ["END_TURN", "PREPARE_CARD"]       # the unaffordable play is not a legal action
        action = chosen(row)
        assert action["type"] == "PREPARE_CARD" and action["card_id"] == "CS2_029" and action["hand_index"] == 0
        assert action["card_cost"] == 5 and action["play_position"] == 0 and "target_kind" not in action


def test_a_target_less_spell_with_no_target_to_play_is_prepare():
    rows, _ = label(prepare_log([("REQ_TARGET_TO_PLAY", False), ("NONE", False)], mana=9, send=2),
                    prepare_actions=True)
    assert sorted(types(rows[0])) == ["END_TURN", "PREPARE_CARD"] and chosen(rows[0])["type"] == "PREPARE_CARD"


def test_two_unaffordable_roots_add_no_action_and_no_ambiguity():
    log = prepare_log([("REQ_ENOUGH_MANA", False), ("REQ_ENOUGH_MANA", False)], mana=0, send=0)
    rows, summary = label(log, prepare_actions=True)
    assert summary["decisions_labeled"] == 1 and types(rows[0]) == ["END_TURN"]
    assert rows[0]["action_schema_version"] == 1                       # no Prepare action: an ordinary version 1 menu


# -- both roots legal: the target requirement decides -----------------------------------------------------------------

@pytest.mark.parametrize("roots,play_option,prepare_option", [
    ([("NONE", True), ("NONE", False)], 1, 2),
    ([("NONE", False), ("NONE", True)], 2, 1),      # the same cards listed the other way round
])
def test_targeted_root_is_the_normal_play_and_the_other_is_prepare(roots, play_option, prepare_option):
    expected_menu = ["END_TURN", "PLAY_CARD", "PREPARE_CARD"]
    for send, target, kind in ((play_option, 50, "PLAY_CARD"), (prepare_option, 0, "PREPARE_CARD")):
        block = "PLAY" if kind == "PLAY_CARD" else "DECK_ACTION"
        rows, summary = label(prepare_log(roots, mana=9, send=send, target=target, block=block), prepare_actions=True)
        assert summary["decisions_labeled"] == 1, summary
        assert sorted(types(rows[0])) == expected_menu                      # the complete menu, one card, two actions
        action = chosen(rows[0])
        assert action["type"] == kind and action["hand_index"] == 0
        assert (action.get("target_card_id") == "CS2_168") == (kind == "PLAY_CARD")


def test_menu_hashes_are_distinct_and_free_of_handles():
    rows, _ = label(prepare_log([("NONE", True), ("NONE", False)], mana=9, send=1, target=50, block="PLAY"),
                    prepare_actions=True)
    actions = rows[0]["legal_actions"]
    assert len({json.dumps(a, sort_keys=True) for a in actions}) == len(actions)
    for action in actions:
        assert set(action) <= ACTION_FIELDS and action["type"] in PREPARE_ACTION_TYPES
        assert not [key for key in action if "entity" in key or "option" in key or "handle" in key]
    text = json.dumps(rows[0])
    assert not any(canary in text for canary in CANARIES)


# -- everything not decided by the message stays refused ----------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    dict(roots=[("NONE", False), ("NONE", False)], mana=9),                       # two legal minion-like roots: order only
    dict(roots=[("NONE", True), ("NONE", True)], mana=9),                          # both need a target
    dict(roots=[("NONE", False), ("REQ_ENOUGH_MANA", False)], mana=9),             # arithmetic contradicts the error
    dict(roots=[("NONE", False), ("REQ_ENOUGH_MANA", False)], mana=0, deck_action_cost=2),   # cheap root unaffordable
    dict(roots=[("NONE", False), ("REQ_YOUR_TURN", False)]),                       # an error we have no evidence for
    dict(roots=[("NONE", True), ("REQ_ENOUGH_MANA", False)]),                      # legal root lists a target
])
def test_unproven_patterns_are_refused(kwargs):
    roots = kwargs.pop("roots")
    rows, summary = label(prepare_log(roots, **kwargs), prepare_actions=True)
    assert rows == [] and summary["skip_reasons"] == {"AMBIGUOUS_SELECTION": 1}


def test_tradeable_card_and_single_root_prepare_card_are_not_guessed():
    rows, summary = label(prepare_log([("NONE", False), ("REQ_ENOUGH_MANA", False)], tradeable=True),
                          prepare_actions=True)
    assert rows == [] and summary["skip_reasons"] == {"UNSUPPORTED_DECISION_KIND": 1}
    rows, summary = label(prepare_log([("NONE", False)]), prepare_actions=True)
    assert rows == [] and summary["skip_reasons"] == {"UNSUPPORTED_DECISION_KIND": 1}


def test_a_card_without_prepare_keeps_its_duplicate_roots_ambiguous_even_with_the_flag():
    log = prepare_log([("NONE", False), ("REQ_ENOUGH_MANA", False)], prepare=False)
    rows, summary = label(log, prepare_actions=True)
    assert rows == [] and summary["skip_reasons"] == {"AMBIGUOUS_SELECTION": 1}


# -- the label is verified by what the game did next -------------------------------------------------------------------

def test_a_label_the_following_block_contradicts_is_dropped():
    # chosen root classified as PREPARE, but the game played the card normally: not a trustworthy label
    log = prepare_log([("NONE", False), ("REQ_ENOUGH_MANA", False)], send=1, block="PLAY")
    rows, summary = label(log, prepare_actions=True)
    assert rows == [] and summary["skip_reasons"] == {"UNSUPPORTED_DECISION_KIND": 1}


# -- dataset contract ----------------------------------------------------------------------------------------------------

def test_prepare_rows_are_a_different_action_schema_that_the_v1_training_loader_refuses():
    rows, _ = label(prepare_log([("NONE", False), ("REQ_ENOUGH_MANA", False)]), prepare_actions=True)
    row = rows[0]
    assert "PREPARE_CARD" not in ACTION_TYPES and row["action_schema_version"] == 2
    with pytest.raises(ValueError):
        validate_example(row)
    v1 = copy.deepcopy(row)
    v1["action_schema_version"] = 1
    with pytest.raises(ValueError):
        validate_example(v1)                       # nor can the action type be smuggled into a version 1 row


def test_other_rows_are_identical_with_and_without_the_flag():
    log = LiveLog(seed=5).create_game().mulligan().self_decision(1)
    log.send_option(1)
    log.p("TAG_CHANGE Entity=2 tag=PLAYSTATE value=WON")
    log.p("TAG_CHANGE Entity=3 tag=PLAYSTATE value=LOST")
    log.complete()
    assert label(log) == label(log, prepare_actions=True)


# -- models ------------------------------------------------------------------------------------------------------------

def _scene_with_prepare():
    state, _ = scene()
    card = state.self_hand[0]
    play = {"type": "PLAY_CARD", "card_id": card.card_id, "source_card_id": card.card_id, "source_kind": "MINION",
            "card_type": "MINION", "hand_index": 0, "card_cost": 5, "play_position": 2}
    prepare = {**play, "type": "PREPARE_CARD", "play_position": 0}
    return state, [{"type": "END_TURN", "play_position": 0}, play, prepare]


def test_features_use_the_existing_prepare_column_and_link_the_same_hand_token():
    state, actions = _scene_with_prepare()
    rows = encode_legal_actions(actions)
    prepare_column = ACTION_FEATURE_NAMES.index("prepare_card")
    assert rows[:, prepare_column].tolist() == [0.0, 0.0, 1.0] and rows[2, ACTION_FEATURE_NAMES.index("play_card")] == 0
    inputs = encode_policy_v2(state, actions, StateEncoder(CATALOG))
    links, ids = inputs[5], inputs[4]
    assert links[1, 0] == links[2, 0] >= 0 and torch.equal(ids[1], ids[2])    # same hand token, same card identity
    assert links[2, 2] == -1 and links[2, 3] == -1                                # a Prepare never has an insertion slot
    features = inputs[3]
    differing = (features[1] != features[2]).nonzero().flatten().tolist()
    names = {ACTION_V2_FEATURE_NAMES[i] for i in differing}
    assert names == {"play_card", "prepare_card", "play_position", "has_left_neighbor", "has_right_neighbor"}


def test_prepare_with_a_board_slot_is_rejected_by_the_encoder():
    state, actions = _scene_with_prepare()
    actions[2]["play_position"] = 1
    with pytest.raises(ValueError):
        encode_policy_v2(state, actions, StateEncoder(CATALOG))


def test_v1_v2_and_v3_score_a_menu_with_prepare_without_touching_their_weights():
    encoder = StateEncoder(CATALOG)
    state, actions = _scene_with_prepare()
    from manamind.models.policy import PolicyNetwork
    from manamind.models.policy_inputs import representation_of
    for policy in (PolicyNetwork(card_count=encoder.vocabulary.card_count).eval(), model(encoder), model_v3(encoder)):
        before = {key: value.clone() for key, value in policy.state_dict().items()}
        with torch.inference_mode():
            logits = policy(*encode_policy_inputs(state, actions, encoder, representation=representation_of(policy)))
        assert logits.shape == (3,) and torch.isfinite(logits).all()
        assert all(torch.equal(before[key], value) for key, value in policy.state_dict().items())


# -- LIVE recommendation ----------------------------------------------------------------------------------------------

def live_scene(roots, **kwargs):
    log = prepare_log(roots, **kwargs)
    cut = next(i for i, line in enumerate(log.lines) if "SendOption" in line)
    live = LiveLog(seed=1)
    live.lines = log.lines[:cut]
    return ready(live)


def test_live_menu_is_complete_and_names_the_right_action_type(recommender):  # noqa: F811
    scorer, path = recommender
    session, snapshot = live_scene([("NONE", True), ("NONE", False)], mana=9)
    with pytest.raises(RecommendationUnavailable, match="AMBIGUOUS_SELECTION"):
        scorer.score(snapshot, session)                                    # default: unchanged "no recommendation"

    from manamind.live.recommendation import PolicyRecommender
    experimental = PolicyRecommender(path, prepare_actions=True)
    experimental.require_catalog(session.catalog)
    result = experimental.score(snapshot, session)
    assert result.menu_size == 3
    assert sorted(item.action["type"] for item in result.menu) == ["END_TURN", "PLAY_CARD", "PREPARE_CARD"]
    assert len({json.dumps(item.action, sort_keys=True) for item in result.menu}) == 3
    assert all(set(item.action) <= ACTION_FIELDS for item in result.menu)


def test_live_refuses_what_the_mapper_cannot_decide(recommender):  # noqa: F811
    _, path = recommender
    from manamind.live.recommendation import PolicyRecommender
    experimental = PolicyRecommender(path, prepare_actions=True)
    session, snapshot = live_scene([("NONE", False), ("NONE", False)], mana=9)
    experimental.require_catalog(session.catalog)
    with pytest.raises(RecommendationUnavailable, match="AMBIGUOUS_SELECTION"):
        experimental.score(snapshot, session)


def test_instruction_and_panel_text_name_prepare():
    from manamind.live.instructions import instruction
    from manamind.live.localization import CardNames
    from manamind.live.panel import describe_action
    action = {"type": "PREPARE_CARD", "card_id": "CS2_029", "source_card_id": "CS2_029", "hand_index": 0,
              "play_position": 0}
    assert "Prepare" in describe_action(action, {"CS2_029": "Fireball"})
    view = instruction(action, None, CardNames({}), "ru")
    assert view["verb"] != "ДЕЙСТВИЕ" and "Prepare" in view["verb"]


def test_map_actions_flag_is_keyword_only_and_off_by_default():
    import inspect
    parameter = inspect.signature(map_actions).parameters["prepare_actions"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is False
