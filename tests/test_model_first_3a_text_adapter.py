import json

import numpy as np

from manamind.research.card_text_features import CardTextAdapter


def test_text_adapter_uses_rules_not_flavor_and_keeps_instance_values_separate(tmp_path):
    catalog = tmp_path / "cards.json"
    catalog.write_text(json.dumps({"format": "STANDARD", "cards": [
        {"id": "RULE", "type": "MINION", "cost": 2, "attack": 3, "health": 4,
         "mechanics": ["TAUNT"], "text": "<b>Taunt</b>", "flavor": "dragon-moon-secret"},
        {"id": "EMPTY", "type": "MINION", "flavor": "flavor-only-word"},
    ]}), encoding="utf-8")
    adapter = CardTextAdapter(catalog)
    record = adapter.record("RULE", current_instance={"current_attack": 8})
    vector, present = adapter.features("RULE")
    assert present and np.linalg.norm(vector) > 0
    assert "dragon" not in adapter.terms and "moon" not in adapter.terms
    assert record["base"] == {"cost": 2, "attack": 3, "health": 4}
    assert record["current_instance"] == {"current_attack": 8}
    assert record["mechanics"] == ["TAUNT"] and record["rules_text_present"]
    missing, missing_present = adapter.features("EMPTY")
    assert not missing_present and not missing.any()
    assert not adapter.features("UNKNOWN")[1]
    cache_path = adapter.cache(tmp_path / "cache")
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache["catalog_sha256"] == adapter.catalog_sha256
    assert cache["config_sha256"] == adapter.config_sha256


def test_cache_key_tracks_catalog_content(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text('{"format":"STANDARD","cards":[{"id":"A","text":"draw a card"}]}', encoding="utf-8")
    first = CardTextAdapter(path).cache_key()
    path.write_text('{"format":"STANDARD","cards":[{"id":"A","text":"deal damage"}]}', encoding="utf-8")
    second = CardTextAdapter(path).cache_key()
    assert first != second
