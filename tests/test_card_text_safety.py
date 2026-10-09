import json
from pathlib import Path

from manamind.research.card_text_features import CardTextAdapter, normalize_rules_text


ROOT = Path(__file__).parents[1]
CATALOG_PATH = ROOT / "data/cards/standard_current_enUS.json"


def test_control_cards_keep_formatting_numbers_and_only_use_rules_text():
    adapter = CardTextAdapter(CATALOG_PATH)

    mother = adapter.text_status["BE_036"]
    assert mother["text_usable"] and mother["text_present"]
    assert "[x]" not in mother["normalized_text"]
    assert "format_bold_start Battlecry: format_bold_end" in mother["normalized_text"]
    assert "a card in your hand by (5)" in mother["normalized_text"]
    assert "mother has arrived" not in mother["normalized_text"]

    missing = adapter.status_for("TLC_248")
    assert missing == {"text_present": False, "text_usable": False,
                       "text_mask": 0, "normalization_warnings": ["TEXT_MISSING"]}
    assert adapter.features("TLC_248")[1] is False

    for card_id in ("CATA_131", "FIR_911"):
        status = adapter.text_status[card_id]
        assert status["text_present"] and not status["text_usable"]
        assert "UNRESOLVED_PLACEHOLDER" in status["normalization_warnings"]
        assert "UNRESOLVED_VARIANT_SEPARATOR" in status["normalization_warnings"]
        vector, usable = adapter.features(card_id)
        assert not usable and not vector.any()
    # Its second variant is preserved only as an ambiguous diagnostic string,
    # never selected from collectionText or exposed as vector features.
    assert "Ready!" in adapter.text_status["CATA_131"]["normalized_text"]

    uppercase_close = adapter.text_status["EDR_493"]
    assert uppercase_close["text_usable"]
    assert "format_italic_start" in uppercase_close["normalized_text"]
    assert "format_italic_end" in uppercase_close["normalized_text"]
    assert "original stats and Cost." in uppercase_close["normalized_text"]

    nested = adapter.text_status["CAP_005"]
    assert nested["text_usable"]
    assert nested["normalized_text"].count("format_bold_start") == 4
    assert nested["normalized_text"].count("format_bold_end") == 4
    assert "Stealth" in nested["normalized_text"] and "reduce the Cost" in nested["normalized_text"]

    legendary = adapter.text_status["CATA_308"]["normalized_text"]
    numeric_forms = [term for term in adapter.terms if term in {"$4", "#4", "(1)", "4"}]
    assert "$4" in legendary and "(1)" in legendary
    assert "$4" in numeric_forms and "(1)" in numeric_forms


def test_control_card_duplicates_and_keyword_format_are_not_mechanics_inference():
    adapter = CardTextAdapter(CATALOG_PATH)
    same = [adapter.text_status[card_id]["normalized_text"]
            for card_id in ("CATA_558", "CORE_NEW1_023", "EDR_598")]
    assert same[0] == same[1] == same[2]
    assert "format_bold_start Elusive format_bold_end" == same[0]
    # Bold formatting is preserved as text structure and does not populate mechanics.
    for card_id in ("CATA_558", "CORE_NEW1_023", "EDR_598"):
        record = adapter.record(card_id)
        assert "ELUSIVE" in record["mechanics"]

    all_enemy = adapter.text_status["CATA_898"]["normalized_text"]
    assert "All enemy minions" in all_enemy and "format_bold_start Taunt format_bold_end" in all_enemy
    assert "nobody does" not in all_enemy  # flavor text is not read
    discover = adapter.text_status["CORE_GIL_836"]["normalized_text"]
    assert "format_bold_start Discover format_bold_end" in discover
    assert "format_bold_start Battlecry format_bold_end" in discover
    assert "shaman" not in discover
    assert adapter.text_status["CATA_558"]["normalized_text"] == adapter.text_status["CORE_NEW1_023"]["normalized_text"]

    no_mechanics = normalize_rules_text("<b>Taunt</b>")
    assert no_mechanics["text_usable"]  # Formatting is a neutral boundary, not a mechanic inference.


def test_conservative_normalizer_masks_unknown_syntax_without_rewriting_values():
    safe = normalize_rules_text("[x]<b>Deal</b> $4 damage\n and heal #4; cost (1), 1, +2/+2")
    assert safe["text_usable"]
    assert "format_bold_start Deal format_bold_end" in safe["normalized_text"]
    assert "$4" in safe["normalized_text"] and "#4" in safe["normalized_text"]
    assert "(1)" in safe["normalized_text"] and "+2/+2" in safe["normalized_text"]

    ambiguous = normalize_rules_text("Draw {0} card. <i>Ready!</i>@Next variant")
    assert ambiguous["text_present"] and not ambiguous["text_usable"]
    assert "UNRESOLVED_PLACEHOLDER" in ambiguous["normalization_warnings"]
    assert "UNRESOLVED_VARIANT_SEPARATOR" in ambiguous["normalization_warnings"]
    assert "{0}" in ambiguous["normalized_text"] and "@" in ambiguous["normalized_text"]

    unknown_markup = normalize_rules_text("Deal <u>extra</u> damage")
    assert not unknown_markup["text_usable"]
    assert "UNSUPPORTED_MARKUP" in unknown_markup["normalization_warnings"]


def test_adapter_schema_v2_masks_missing_unknown_and_ambiguous_text(tmp_path):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"format": "STANDARD", "cards": [
        {"id": "SAFE", "text": "Deal $4 damage.", "flavor": "heal #4", "collectionText": "draw 1"},
        {"id": "AMBIG", "text": "Draw {0} cards @stage2"},
        {"id": "EMPTY", "text": None},
    ]}), encoding="utf-8")
    adapter = CardTextAdapter(catalog)
    path = adapter.cache(tmp_path / "cache")
    cache = json.loads(path.read_text(encoding="utf-8"))
    assert cache["schema_version"] == 2
    assert "text_usable" in cache["cards"]["SAFE"]
    assert cache["cards"]["SAFE"]["text_usable"]
    assert not cache["cards"]["AMBIG"]["text_usable"]
    assert cache["cards"]["AMBIG"]["features"] == []
    assert adapter.status_for("UNKNOWN") == {"text_present": False, "text_usable": False,
        "text_mask": 0, "normalization_warnings": ["UNKNOWN_CARD_ID", "TEXT_MISSING"]}
