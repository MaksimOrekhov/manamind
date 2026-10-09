import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import audit_model_first_3a_text_safety as safety  # noqa: E402


def test_catalog_inventory_counts_mask_and_control_cards():
    report = safety.audit(ROOT / "data/cards/standard_current_enUS.json")
    assert report["text_coverage"]["catalog_cards"] == 1185
    assert report["text_coverage"]["text_present"] == 1182
    assert report["text_coverage"]["missing_text"] == 3
    assert report["text_coverage"]["text_usable_full_features"] < 1182
    assert report["text_coverage"]["warning_or_missing_mask"] == (
        1185 - report["text_coverage"]["text_usable_full_features"])
    exact = {tuple(group["ids"]) for group in report["exact_text_duplicates_different_ids"]}
    assert ("CATA_558", "CORE_NEW1_023", "EDR_598") in exact


def test_existing_split_overlap_and_real_state_coverage_are_read_only(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    cards = [
        {"id": "TRAIN", "type": "MINION", "cost": 3, "attack": 3, "health": 3,
         "cardClass": "NEUTRAL", "mechanics": [], "text": "Battlecry: Deal 4 damage to all enemy minions."},
        {"id": "TWIN", "type": "MINION", "cost": 3, "attack": 3, "health": 3,
         "cardClass": "NEUTRAL", "mechanics": [], "text": "Battlecry: Deal 4 damage to all enemy minions."},
        {"id": "NEAR", "type": "MINION", "cost": 3, "attack": 3, "health": 3,
         "cardClass": "NEUTRAL", "mechanics": [],
         "text": "Battlecry: Deal 5 damage to all enemy minions."},
        {"id": "MISSING", "type": "MINION", "cost": 2, "attack": 2, "health": 2, "text": None},
    ]
    catalog_path.write_text(json.dumps({"format": "STANDARD", "profile_id": "test", "cards": cards}), encoding="utf-8")
    rows = [
        {"game_id": "train-game", "state": {"self_hand": [{"card_id": "TRAIN", "cost": 3,
                                                               "attack": 3, "health": 3}] }},
        {"game_id": "test-game", "state": {"self_player": {"board": [
            {"card": {"card_id": "TWIN", "cost": 3, "attack": 3, "health": 3},
             "current_attack": 4, "current_health": 3},
            {"card": {"card_id": "NEAR", "cost": 3, "attack": 3, "health": 3},
             "current_attack": 3, "current_health": 4},
            {"card": {"card_id": "MISSING", "cost": 2, "attack": 2, "health": 2},
             "current_attack": 2, "current_health": 2},
            {"card": {"card_id": "UNKNOWN_TOKEN"}, "current_attack": 1, "current_health": 1},
        ]}}},
    ]
    monkeypatch.setattr(safety, "_load_rows", lambda _path: rows)
    manifest = tmp_path / "split.json"
    manifest.write_text(json.dumps({"split": {"game_ids": {"train": ["train-game"],
                                                                "validation": ["val-game"],
                                                                "test": ["test-game"]}}}), encoding="utf-8")
    report = safety.audit(catalog_path, dataset=tmp_path / "existing", split_manifest=manifest,
                          near_threshold=0.4)
    overlap = report["split_overlap"]
    assert overlap["split_created"] is False
    assert { (pair["train_id"], pair["test_id"]) for pair in overlap["functional_twins_between_train_and_test"] } == {("TRAIN", "TWIN")}
    assert { (pair["train_id"], pair["test_id"]) for pair in overlap["number_masked_template_overlaps_between_train_and_test"] } == {("TRAIN", "NEAR")}
    assert overlap["near_pair_count_at_threshold"] >= 1
    assert any(pair["train_id"] == "TRAIN" and pair["test_id"] == "NEAR"
               for pair in overlap["near_text_template_overlaps_between_train_and_test"])
    coverage = report["real_state_coverage"]
    assert coverage["known_catalog"]["text_missing_ids"] == 1
    assert coverage["unknown_to_catalog"]["distinct_ids"] == 1
    assert coverage["unknown_to_catalog"]["instance_value_records"] == 1
    assert coverage["known_unknown_coverage_differs"]
