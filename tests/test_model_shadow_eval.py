"""MODEL-SHADOW-EVAL-1: pairing of shadow rows with the player's confirmed action, metrics and independence."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from test_real_policy_dataset import fixture  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.policy_shadow import evaluation as ev  # noqa: E402
from manamind.policy_shadow.shadow import action_sha  # noqa: E402

CATALOG = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")
MODELS = ["policy_v2", "retrained_v2", "policy_v3"]
MATCH = "a" * 64

ACTIONS = [{"type": "END_TURN", "play_position": 0},
           {"type": "HERO_POWER", "card_id": "HP", "source_card_id": "HP", "play_position": 0},
           {"type": "PLAY_CARD", "card_id": "X", "hand_index": 0, "source_card_id": "X", "play_position": 0},
           {"type": "ATTACK", "source_card_id": "M", "source_board_position": 1, "source_is_hero": False,
            "target_kind": "HERO", "target_side": "OPPONENT", "play_position": 0}]


def state(turn: int = 3) -> dict:
    player = {"available_mana": 2, "max_mana": 2, "hero_health": 30, "armor": 0, "board": [], "player_class": "DEMONHUNTER",
              "hand_size": 1}
    return {"self_player": dict(player), "opponent": {**player, "player_class": "ROGUE"}, "self_hand": [], "turn_number": turn}


def make(options: int, chosen: int, rank_lists: dict[str, list[int]], *, match=MATCH, state_hash=None, actions=None,
         mana=2, klass="DEMONHUNTER", seq=None):
    """A labeled example and the shadow row that belongs to it (consistent hashes, models given as rank vectors)."""
    actions = copy.deepcopy(actions if actions is not None else ACTIONS)
    state_hash = state_hash or f"{options:064x}"
    example = {"game_id": match, "decision_id": f"{match}:{options}", "state": state(), "legal_actions": actions,
               "chosen_action_index": chosen, "provenance": {"state_hash": state_hash}}
    models = [{"name": name, "status": "OK", "checkpoint_sha256": name, "ranks": list(ranks)}
              for name, ranks in rank_lists.items()]
    row = {"event": "MODEL_SHADOW", "match_id": match, "decision_id": f"{match}:{seq or options}:{options}:{state_hash}",
           "seq": seq or options, "options_id": options, "state_hash": state_hash, "turn": 3, "self_class": klass,
           "opponent_class": "ROGUE", "mana": mana, "menu_size": len(actions), "menu_sha256": ev.menu_digest(actions),
           "actions": [{"index": i, "type": a["type"], "sha": action_sha(a)} for i, a in enumerate(actions)],
           "models": models}
    return example, row


def ranks_for(order: list[int]) -> list[int]:
    """Rank vector of a model whose preference order (best first) is ``order``."""
    ranks = [0] * len(order)
    for rank, index in enumerate(order, 1):
        ranks[index] = rank
    return ranks


def models_with(top_orders: dict[str, list[int]]) -> dict[str, list[int]]:
    return {name: ranks_for(order) for name, order in top_orders.items()}


GOOD = models_with({"policy_v2": [1, 0, 2, 3], "retrained_v2": [2, 0, 1, 3], "policy_v3": [3, 2, 1, 0]})


def labels_for(*examples, error=None, skipped=None, match=MATCH) -> dict:
    return {match: ev.MatchLabels(examples=list(examples), skipped=dict(skipped or {}), import_error=error)}


def reasons(result) -> dict:
    return {s["decision_id"].split(":")[2]: s["reason"] for s in result["skipped"]}


def test_a_decision_is_paired_only_when_match_options_state_and_menu_all_agree():
    example, row = make(1, chosen=2, rank_lists=GOOD)
    result = ev.match_decisions([row], labels_for(example), MODELS)
    assert not result["skipped"] and len(result["matched"]) == 1
    item = result["matched"][0]
    assert item["chosen"] == 2
    assert item["rank"] == {"policy_v2": 3, "retrained_v2": 1, "policy_v3": 2}
    assert item["top1"] == {"policy_v2": 1, "retrained_v2": 2, "policy_v3": 3}


def test_a_different_state_hash_is_never_paired():
    example, row = make(1, 2, GOOD)
    row["state_hash"] = "f" * 64
    result = ev.match_decisions([row], labels_for(example), MODELS)
    assert reasons(result) == {"1": "STATE_HASH_MISMATCH"} and not result["matched"]


def test_a_reordered_menu_is_refused_as_an_order_mismatch_and_a_changed_menu_as_a_mismatch():
    example, row = make(1, 2, GOOD)
    example["legal_actions"] = [ACTIONS[0], ACTIONS[2], ACTIONS[1], ACTIONS[3]]          # same actions, other order
    assert reasons(ev.match_decisions([row], labels_for(example), MODELS)) == {"1": "MENU_ORDER_MISMATCH"}
    changed = copy.deepcopy(ACTIONS)
    changed[2]["card_id"] = "Y"
    example, row = make(1, 2, GOOD)
    example["legal_actions"] = changed
    assert reasons(ev.match_decisions([row], labels_for(example), MODELS)) == {"1": "MENU_MISMATCH"}
    example, row = make(1, 2, GOOD)
    example["legal_actions"] = ACTIONS[:3]                                               # an action missing
    assert reasons(ev.match_decisions([row], labels_for(example), MODELS)) == {"1": "MENU_MISMATCH"}


def test_missing_ambiguous_or_unreadable_labels_are_skipped_with_their_own_reason_not_guessed():
    _, row = make(1, 2, GOOD)
    other, _ = make(2, 2, GOOD)
    assert reasons(ev.match_decisions([row], labels_for(other), MODELS)) == {"1": "NO_LABEL"}
    assert reasons(ev.match_decisions([row], labels_for(skipped={"1": "AMBIGUOUS_SELECTION"}), MODELS)) == {
        "1": "IMPORTER_SKIPPED:AMBIGUOUS_SELECTION"}
    assert reasons(ev.match_decisions([row], {}, MODELS)) == {"1": "NO_POWER_LOG"}
    assert reasons(ev.match_decisions([row], labels_for(error="INCOMPLETE"), MODELS)) == {"1": "IMPORT_FAILED:INCOMPLETE"}
    twin, _ = make(1, 2, GOOD)
    example, _ = make(1, 2, GOOD)
    assert reasons(ev.match_decisions([row], labels_for(example, twin), MODELS)) == {"1": "AMBIGUOUS_LABEL"}
    for bad in (-1, 4, None, True):
        example, row = make(1, 2, GOOD)
        example["chosen_action_index"] = bad
        assert reasons(ev.match_decisions([row], labels_for(example), MODELS)) == {"1": "CHOSEN_ACTION_INVALID"}
    example, row = make(1, 2, GOOD, match="b" * 64)
    example["game_id"] = MATCH
    assert reasons(ev.match_decisions([row], labels_for(example, match="b" * 64), MODELS)) == {"1": "MATCH_ID_MISMATCH"}


def test_a_re_emitted_decision_counts_once_and_conflicting_copies_are_all_skipped():
    example, row = make(1, 2, GOOD)
    again = {**copy.deepcopy(row), "seq": 7, "decision_id": f"{MATCH}:7:1:{row['state_hash']}"}   # new seq, same decision
    result = ev.match_decisions([row, again], labels_for(example), MODELS)
    assert len(result["matched"]) == 1 and len(result["collapsed_duplicates"]) == 1 and not result["skipped"]
    conflicting = copy.deepcopy(again)
    conflicting["models"][0]["ranks"] = ranks_for([3, 2, 1, 0])
    result = ev.match_decisions([row, conflicting], labels_for(example), MODELS)
    assert not result["matched"] and [s["reason"] for s in result["skipped"]] == ["CONFLICTING_DUPLICATE_SHADOW_ROWS"] * 2


def test_an_absent_or_incomplete_shadow_is_skipped_for_the_comparison():
    example, row = make(1, 2, GOOD)
    no_model = copy.deepcopy(row)
    no_model["models"] = no_model["models"][:2]
    failed = copy.deepcopy(row)
    failed["models"][2] = {"name": "policy_v3", "status": "ERROR", "reason": "INFERENCE_FAILED"}
    bad_ranks = copy.deepcopy(row)
    bad_ranks["models"][1]["ranks"] = [1, 1, 2, 3]
    short = copy.deepcopy(row)
    short["actions"] = short["actions"][:2]
    no_hash = {k: v for k, v in row.items() if k != "menu_sha256"}
    for broken, reason in ((no_model, "MODEL_MISSING:policy_v3"), (failed, "MODEL_NOT_OK:policy_v3:ERROR"),
                           (bad_ranks, "MODEL_INVALID_RANKS:retrained_v2"), (short, "SHADOW_ROW_MALFORMED"),
                           (no_hash, "SHADOW_ROW_MALFORMED")):
        result = ev.match_decisions([broken], labels_for(example), MODELS)
        assert [s["reason"] for s in result["skipped"]] == [reason] and not result["matched"]
    assert ev.match_decisions([], labels_for(example), MODELS)["labeled_without_shadow"] == [
        {"match_id": MATCH, "decision_id": f"{MATCH}:1"}]


def test_matches_a_checkpoint_trained_on_never_enter_the_independent_statistics():
    old_example, old_row = make(1, 2, GOOD, match="c" * 64)
    new_example, new_row = make(2, 2, GOOD)
    labels = {**labels_for(old_example, match="c" * 64), **labels_for(new_example)}
    training = {"policy_v2": {"c" * 64}, "policy_v3": {"d" * 64}}
    report = ev.evaluate([old_row, new_row], labels, MODELS, training_games=training)
    assert report["coverage"]["matched"] == 1 and report["coverage"]["skip_reasons"] == {"TRAINING_OVERLAP": 1}
    assert report["metrics"]["all"]["decisions"] == 1
    assert report["independence"]["training_overlap_matches"] == {"c" * 8: ["policy_v2"]}
    assert [d["decision_id"] for d in report["matched_decisions"]] == [new_row["decision_id"]]
    only_old = ev.evaluate([old_row], {**labels_for(old_example, match="c" * 64)}, MODELS, training_games=training)
    assert only_old["metrics"]["all"]["decisions"] == 0 and only_old["coverage"]["matched"] == 0


def test_rank_metrics_and_the_chance_baseline_are_exact():
    metrics = ev.rank_metrics([1, 2, 4], [4, 4, 4])
    assert metrics["top1_hits"] == 1 and metrics["top3_hits"] == 2 and metrics["top3_decisions"] == 3
    assert metrics["mrr"] == round((1 + 1 / 2 + 1 / 4) / 3, 4) and metrics["mean_rank"] == round(7 / 3, 3)
    assert metrics["chance"]["top1"] == 0.25 and metrics["chance"]["top3"] == 0.75
    assert metrics["chance"]["mrr"] == round((1 + 1 / 2 + 1 / 3 + 1 / 4) / 4, 4)


def test_top3_counts_only_menus_of_three_or_more_while_top1_and_mrr_keep_every_decision():
    metrics = ev.rank_metrics([1, 2, 5, 1], [1, 2, 6, 3])        # menus of 1 and 2 are trivially inside any Top-3
    assert metrics["decisions"] == 4 and metrics["top1_hits"] == 2
    assert metrics["mrr"] == round((1 + 1 / 2 + 1 / 5 + 1) / 4, 4)
    assert metrics["top3_decisions"] == 2 and metrics["top3_hits"] == 1 and metrics["top3"] == 0.5
    assert metrics["chance"]["top3"] == round((3 / 6 + 3 / 3) / 2, 4) and metrics["chance"]["top1"] == round((1 + 1 / 2 + 1 / 6 + 1 / 3) / 4, 4)
    only_small = ev.rank_metrics([1, 1], [1, 2])
    assert only_small["top3_decisions"] == 0 and only_small["top3"] is None and only_small["chance"]["top3"] is None


def test_the_report_separates_matches_menus_and_models_and_is_json_serialisable():
    import json
    pairs = [make(1, 0, GOOD), make(2, 2, GOOD, state_hash="1" * 64),
             make(3, 0, models_with({"policy_v2": [0], "retrained_v2": [0], "policy_v3": [0]}), actions=ACTIONS[:1])]
    report = ev.evaluate([row for _, row in pairs], labels_for(*(e for e, _ in pairs)), MODELS)
    assert report["coverage"]["matched"] == 3
    assert report["metrics"]["all"]["decisions"] == 3 and report["metrics"]["nontrivial_menu_2plus"]["decisions"] == 2
    assert report["metrics"]["all"]["models"]["retrained_v2"]["top1_hits"] == 2
    assert list(report["per_match"]) == [MATCH[:8]]
    hero_power = report["categories"]["hero_power"]["overall"]
    assert hero_power["available"] == 2 and hero_power["player_used"] == 0
    assert hero_power["models"]["retrained_v2"]["top1_hero_power"] == 0
    assert report["categories"]["end_turn"]["player_ended_turn"] == 1
    json.dumps(report, allow_nan=False)
    assert "MODEL-SHADOW-EVAL-1" in ev.render(report)


def test_a_small_sample_is_never_called_an_established_difference_and_the_bootstrap_is_seeded():
    items = [make(i, 0, models_with({"policy_v2": [3, 2, 1, 0], "retrained_v2": [0, 1, 2, 3], "policy_v3": [0, 2, 1, 3]}),
                  state_hash=f"{i:064x}") for i in range(1, 7)]
    matched = ev.match_decisions([r for _, r in items], labels_for(*(e for e, _ in items)), MODELS)["matched"]
    first = ev.paired_comparison(matched, "retrained_v2", "policy_v2")
    assert first == ev.paired_comparison(matched, "retrained_v2", "policy_v2")
    assert first["top1"]["only_retrained_v2"] == 6 and first["top1"]["only_policy_v2"] == 0
    assert first["top1"]["exact_sign_test_p"] == round(2 * 0.5 ** 6, 4) and first["verdict"] != "ESTABLISHED"
    tie = ev.paired_comparison(matched, "retrained_v2", "policy_v3")
    assert tie["top1"]["both"] == 6 and tie["verdict"] == "INCONCLUSIVE"


def test_the_real_importer_output_pairs_with_its_own_menu_and_reports_its_skips():
    examples, summary = extract_match(fixture(45).lines, CATALOG)
    example = examples[0]
    size = len(example["legal_actions"])
    row = {"event": "MODEL_SHADOW", "match_id": example["game_id"], "decision_id": f"{example['decision_id']}:x",
           "options_id": example["decision_id"].rsplit(":", 1)[1], "state_hash": example["provenance"]["state_hash"],
           "menu_size": size, "menu_sha256": ev.menu_digest(example["legal_actions"]), "turn": 1, "mana": 1,
           "self_class": "PRIEST", "opponent_class": "ROGUE",
           "actions": [{"index": i, "type": a["type"], "sha": action_sha(a)} for i, a in enumerate(example["legal_actions"])],
           "models": [{"name": n, "status": "OK", "checkpoint_sha256": n, "ranks": list(range(1, size + 1))} for n in MODELS]}
    labels = {example["game_id"]: ev.MatchLabels.from_import(examples, summary)}
    result = ev.match_decisions([row], labels, MODELS)
    assert len(result["matched"]) == 1 and result["matched"][0]["chosen"] == example["chosen_action_index"]
    superseded, summary = extract_match(fixture(45, supersede=True).lines, CATALOG)
    assert not superseded and summary["skip_reasons"]
    skipped = ev.MatchLabels.from_import(superseded, summary)
    assert set(skipped.skipped.values()) == set(summary["skip_reasons"])


def test_results_of_a_model_other_than_the_checkpoint_the_split_was_read_from_are_not_independent():
    example, row = make(1, 2, GOOD)
    same = {name: name for name in MODELS}                      # make() journals the model name as its digest
    assert ev.match_decisions([row], labels_for(example), MODELS, checkpoints=same)["matched"]
    swapped = {**same, "policy_v3": "f" * 64}                   # the split belongs to another file than the one that ran
    result = ev.match_decisions([row], labels_for(example), MODELS, checkpoints=swapped)
    assert not result["matched"] and [s["reason"] for s in result["skipped"]] == ["CHECKPOINT_MISMATCH"]
    # a journal that mixes versions poisons the whole match, also its rows that carry the expected digest
    other, later = make(2, 2, GOOD, state_hash="2" * 64)
    later["models"][1]["checkpoint_sha256"] = "newer"
    result = ev.match_decisions([row, later], labels_for(example, other), MODELS, checkpoints=same)
    assert not result["matched"] and [s["reason"] for s in result["skipped"]] == ["CHECKPOINT_MISMATCH"] * 2
    report = ev.evaluate([row, later], labels_for(example, other), MODELS, checkpoints=same)
    assert report["metrics"]["all"]["decisions"] == 0
    assert report["independence"]["checkpoint_identity_verified"] is False
    assert report["independence"]["checkpoint_mismatch_matches"] == [MATCH[:8]]
    assert report["independence"]["checkpoint_identity"]["retrained_v2"]["journal_sha256"] == ["newer", "retrained_v2"]
    unchecked = ev.evaluate([row], labels_for(example), MODELS)
    assert unchecked["independence"]["checkpoint_identity_verified"] is False and unchecked["coverage"]["matched"] == 1


def test_decisions_without_a_shadow_row_get_a_reason_only_from_journal_events_of_that_very_decision():
    shown, row = make(1, 2, GOOD)
    unavailable, _ = make(2, 2, GOOD, state_hash="2" * 64)
    discarded, _ = make(3, 2, GOOD, state_hash="3" * 64)
    silent, _ = make(4, 2, GOOD, state_hash="4" * 64)
    events = [{"event": "RECOMMENDATION", "match_id": MATCH, "decision_id": f"{MATCH}:1:1:{'1' * 64}"},
              {"event": "UNAVAILABLE", "match_id": MATCH, "decision_id": f"{MATCH}:2:2:{'2' * 64}", "reason": "AMBIGUOUS_SELECTION"},
              {"event": "UNAVAILABLE", "match_id": MATCH, "decision_id": f"{MATCH}:3:2:{'2' * 64}", "reason": "AMBIGUOUS_SELECTION"},
              {"event": "DISCARDED", "match_id": MATCH, "decision_id": f"{MATCH}:4:3:{'3' * 64}", "reason": "DECISION_CHANGED_DURING_INFERENCE"},
              {"event": "UNAVAILABLE", "match_id": "z" * 64, "decision_id": f"{'z' * 64}:1:4:x", "reason": "OTHER_MATCH"}]
    result = ev.match_decisions([row], labels_for(shown, unavailable, discarded, silent), MODELS)
    explained = ev.explain_unshadowed(result["labeled_without_shadow"], events)
    assert explained["decisions"] == 3
    assert explained["by_decision"] == {"DISCARDED:DECISION_CHANGED_DURING_INFERENCE": 1,
                                        "NO_JOURNAL_EVENT_FOR_DECISION": 1, "UNAVAILABLE:AMBIGUOUS_SELECTION": 1}
    assert explained["journal_events_behind_these_decisions"]["UNAVAILABLE:AMBIGUOUS_SELECTION"] == 2     # 2 events, 1 decision
    assert ev.explain_unshadowed(result["labeled_without_shadow"], None)["status"] == "EVENTS_NOT_PROVIDED"
