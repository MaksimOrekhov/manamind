"""CARD-METADATA-2: the full read-only metadata layer, its comparison and coverage logic, and its isolation."""

import gzip
import hashlib
import json
import re
import socket
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from manamind.card_metadata import (
    AmbiguousCardId, CardMetadata, SnapshotError, SnapshotInfo, SnapshotIntegrityError, Status, plain_text,
    quality_flags, read_manifest, strip_text_artifacts,
)
from manamind.card_metadata.compare import classify_text_change, compare_snapshots
from manamind.card_metadata.coverage import TextStatus, entities, missing_fields, status_counts, text_status
from manamind.card_metadata.snapshot import DEFAULT_ROOT, MANIFEST_NAME
from manamind.card_metadata.text_features import families, special_cases

ROOT = Path(__file__).resolve().parents[1]
CURRENT, PREVIOUS = "hsjson_255130_enUS", "hsjson_253216_enUS"


def info(**overrides):
    base = dict(snapshot_id="t", build=1, patch=None, locale="enUS", file="t.json.gz", raw_sha256="0" * 64, raw_bytes=0,
                record_count=0, source_url="", retrieved_at_utc="", equivalent_builds=(), role="current", notes="")
    return SnapshotInfo(**{**base, **overrides})


def store(records, snapshot_id="t"):
    return CardMetadata(info(snapshot_id=snapshot_id, record_count=len(records)), records)


@pytest.fixture(scope="module")
def new():
    return CardMetadata.load()


@pytest.fixture(scope="module")
def old():
    return CardMetadata.load(PREVIOUS)


# ---------------------------------------------------------------- pinned snapshots, offline
def test_pinned_snapshots_load_without_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    current, previous = CardMetadata.load(), CardMetadata.load(PREVIOUS)
    assert current.snapshot_id == CURRENT and len(current) == 36390 and not current.ambiguous_ids()
    assert previous.snapshot_id == PREVIOUS and len(previous) == 36022 and not previous.ambiguous_ids()


def test_manifest_pins_exactly_one_current_snapshot_and_real_files():
    infos = read_manifest()
    assert [i.snapshot_id for i in infos if i.role == "current"] == [CURRENT]
    for item in infos:
        raw = gzip.decompress((DEFAULT_ROOT / item.file).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == item.raw_sha256 and len(raw) == item.raw_bytes
        assert item.source_url.startswith("https://api.hearthstonejson.com/v1/%d/" % item.build)
    assert (ROOT / "data/card_metadata" / MANIFEST_NAME).exists()


def test_corrupted_snapshot_is_rejected(tmp_path):
    payload = json.dumps([{"id": "A"}]).encode()
    (tmp_path / "s.json.gz").write_bytes(gzip.compress(payload))
    entry = {"snapshot_id": "s", "build": 1, "locale": "enUS", "file": "s.json.gz", "raw_sha256": "f" * 64,
             "raw_bytes": len(payload), "record_count": 1, "source_url": "u", "retrieved_at_utc": "t", "role": "current"}
    (tmp_path / MANIFEST_NAME).write_text(json.dumps({"schema_version": 1, "snapshots": [entry]}), encoding="utf-8")
    with pytest.raises(SnapshotIntegrityError):
        CardMetadata.load(root=tmp_path)
    entry["raw_sha256"] = hashlib.sha256(payload).hexdigest()
    (tmp_path / MANIFEST_NAME).write_text(json.dumps({"schema_version": 1, "snapshots": [entry]}), encoding="utf-8")
    assert "A" in CardMetadata.load(root=tmp_path)
    with pytest.raises(SnapshotError):
        CardMetadata.load("unknown", root=tmp_path)


def test_manifest_needs_exactly_one_current(tmp_path):
    entry = {"snapshot_id": "s", "build": 1, "locale": "enUS", "file": "s", "raw_sha256": "0" * 64, "raw_bytes": 0,
             "record_count": 0, "source_url": "u", "retrieved_at_utc": "t", "role": "previous"}
    (tmp_path / MANIFEST_NAME).write_text(json.dumps({"schema_version": 1, "snapshots": [entry]}), encoding="utf-8")
    with pytest.raises(SnapshotError):
        CardMetadata.load(root=tmp_path)


# ---------------------------------------------------------------- stable resolution of known IDs
def test_known_ids_resolve_with_stable_fields(new, old):
    coin = new.describe("GAME_005")
    assert coin.card_type == "SPELL" and coin.cost == 0 and coin.collectible is False and coin.dbf_id is not None
    assert old.describe("GAME_005").dbf_id == coin.dbf_id
    for card_id in ("CORE_EX1_559", "BE_036"):
        assert new.describe(card_id).collectible is True and new.describe(card_id).name


def test_tokens_and_non_collectible_cards_resolve_and_are_marked_tokens(new, old):
    token = new.describe("BE_009t1")
    assert token is not None and token.collectible is False and token.is_token and token.card_type in {"MINION", "SPELL", "WEAPON"}
    assert "BE_009t1" not in old and old.lookup("BE_009t1").status is Status.MISSING
    power = next(r for r in new.records() if r.get("type") == "HERO_POWER")
    assert new.describe(power["id"]).is_token is False and new.describe(power["id"]).card_type == "HERO_POWER"


def test_every_old_collectible_record_is_identical_in_the_previous_snapshot(old):
    """Provenance of the model-side catalog source: it is the collectible subset of build 253216, byte for byte."""
    collectible = json.loads((ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json").read_text(encoding="utf-8"))
    assert len(collectible) == 8170
    assert all(dict(old.get(card["id"])) == card for card in collectible)
    assert {r["id"] for r in old.records() if r.get("collectible")} == {card["id"] for card in collectible}


def test_missing_ids_and_descriptions(new):
    found = new.lookup("NOT_A_CARD_123")
    assert found.status is Status.MISSING and found.record is None
    assert new.get("NOT_A_CARD_123") is None and new.describe("NOT_A_CARD_123") is None and "NOT_A_CARD_123" not in new
    assert not new.ids_for_dbf_id(-1)


def test_records_are_read_only(new):
    record = new.get("GAME_005")
    with pytest.raises(TypeError):
        record["cost"] = 99


# ---------------------------------------------------------------- duplicates and ambiguity
def test_duplicate_ids_are_ambiguous_and_never_picked_silently():
    meta = store([{"id": "X", "dbfId": 1, "name": "one"}, {"id": "X", "dbfId": 2, "name": "two"}, {"id": "Y", "dbfId": 2}])
    assert meta.ambiguous_ids() == {"X"} and "X" in meta
    found = meta.lookup("X")
    assert found.status is Status.AMBIGUOUS and found.record is None and len(found.candidates) == 2
    with pytest.raises(AmbiguousCardId):
        meta.get("X")
    with pytest.raises(AmbiguousCardId):
        meta.describe("X")
    assert meta.lookup("Y").status is Status.FOUND
    assert sorted(meta.ids_for_dbf_id(2)) == ["X", "Y"]


def test_record_without_id_is_refused():
    with pytest.raises(SnapshotError):
        store([{"name": "no id"}])


# ---------------------------------------------------------------- incomplete and suspicious data
def test_quality_flags_report_each_problem_separately_and_never_repair():
    minion = {"id": "M", "type": "MINION", "name": "m", "cardClass": "MAGE", "cost": 1, "attack": 1, "health": 1, "text": "Hi"}
    assert quality_flags(minion) == ()
    assert quality_flags({**minion, "cost": None}) == ("MISSING_COST",)
    assert "MISSING_STATS" in quality_flags({"id": "M", "type": "MINION", "name": "m", "cardClass": "MAGE", "cost": 1})
    assert "MISSING_CLASS" in quality_flags({k: v for k, v in minion.items() if k != "cardClass"})
    assert quality_flags({"id": "Z"}) == ("MISSING_TYPE", "MISSING_NAME")
    empty = {**minion, "text": "", "mechanics": ["BATTLECRY"]}
    assert set(quality_flags(empty)) == {"EMPTY_TEXT", "EMPTY_TEXT_WITH_EFFECT_TAG"}
    assert quality_flags({**minion, "text": "", "mechanics": ["TAUNT"]}) == ("EMPTY_TEXT",)
    assert "PLACEHOLDER_TEXT" in quality_flags({**minion, "text": "Flavor to be revealed"})
    assert "TEMPLATE_VALUE_IN_TEXT" in quality_flags({**minion, "text": "Summon a {0}/{1}"})
    assert "MULTI_STATE_TEXT" in quality_flags({**minion, "text": "a ({0} left)@(Ready)"})
    assert missing_fields({**minion, "cost": None}) == ("MISSING_COST",) and missing_fields(None) == ()


def test_text_artifacts_are_removed_only_where_they_are_artifacts():
    assert strip_text_artifacts("<b>Battlecry:</b>& Deal 3.") == "<b>Battlecry:</b> Deal 3."
    assert strip_text_artifacts("After you cast a spell,&\ndraw") == "After you cast a spell,\ndraw"
    assert strip_text_artifacts("Fire & Ice") == "Fire & Ice"
    assert strip_text_artifacts("Attack \\& Armor") == "Attack \\& Armor"
    tagged = "Summon a 3/3.~GAMEPLAY ASPROXY CATA 528"
    assert strip_text_artifacts(tagged) == "Summon a 3/3."
    assert plain_text("[x]<b>Taunt</b>\n$5 damage,&\nand #3") == "Taunt 5 damage, and 3"
    assert "LAYOUT_MARKER_IN_TEXT" in quality_flags({"id": "A", "type": "SPELL", "name": "a", "cardClass": "MAGE", "cost": 1, "text": "x,& y"})
    assert "DEBUG_MARKER_IN_TEXT" in quality_flags({"id": "A", "type": "SPELL", "name": "a", "cardClass": "MAGE", "cost": 1, "text": tagged})


def test_the_new_snapshot_text_artifacts_are_exactly_the_documented_ones(new):
    layout = {r["id"] for r in new.records() if "LAYOUT_MARKER_IN_TEXT" in quality_flags(r)}
    debug = {r["id"] for r in new.records() if "DEBUG_MARKER_IN_TEXT" in quality_flags(r)}
    assert len(debug) == 10 and len(layout) >= 320
    assert not any("&" in strip_text_artifacts(new.get(i)["text"]).replace(" & ", "").replace("\\&", "")
                   for i in layout | debug)


# ---------------------------------------------------------------- comparison
def test_text_change_classification():
    assert classify_text_change("a", "a") == "identical"
    assert classify_text_change("<b>Battlecry:</b> Draw", "<b>Battlecry:</b>& Draw") == "text_artifact_only"
    assert classify_text_change("Draw a\ncard", "Draw a card") == "markup_or_whitespace_only"
    assert classify_text_change("Deal $3 damage", "Deal $4 damage") == "numbers_only"
    assert classify_text_change("Deal 3 damage", "Draw 3 cards") == "wording"
    assert classify_text_change("", "Taunt") == "text_added_or_removed"


def make(card_id, **fields):
    return {"id": card_id, "dbfId": zlib.crc32(card_id.encode()), "name": card_id, "type": "MINION", "cardClass": "NEUTRAL",
            "cost": 1, "attack": 1, "health": 1, "set": "CORE", "collectible": True, "text": "", **fields}


def test_compare_separates_scope_new_cards_and_changes():
    old_records = [
        make("KEEP"), make("TOKEN_OLD", collectible=False), make("GONE", collectible=False),
        make("MARKER", text="<b>Taunt</b> Draw"), make("NUM", text="Deal $2"), make("BALANCE", cost=3),
        make("ART", artist="a"), make("BE_OLD", set="BE"), make("BG_X", set="BATTLEGROUNDS", collectible=False, cost=2),
    ]
    new_records = [
        make("KEEP"), make("TOKEN_OLD", collectible=False), make("MARKER", text="<b>Taunt</b>& Draw"),
        make("NUM", text="Deal $3"), make("BALANCE", cost=4), make("ART", artist="b"), make("BE_OLD", set="BE", health=9),
        make("BG_X", set="BATTLEGROUNDS", collectible=False, cost=3),
        make("BE_NEW", set="BE"), make("BE_NEW_T", set="BE", collectible=False), make("NEW_BG", set="BATTLEGROUNDS", collectible=False),
        make("NEW_EN", type="ENCHANTMENT", collectible=False),
    ]
    result = compare_snapshots(store(old_records, "old"), store(new_records, "new"), {"KEEP", "MARKER", "NUM", "BALANCE", "ART", "BE_OLD"})
    assert result["ids"] == {"old_full": 9, "new_full": 12, "common": 8, "added": 4, "removed": 1,
                             "ambiguous_old": 0, "ambiguous_new": 0}
    assert result["scope_effect"]["old_noncollectible_ids_still_present"] == 2
    assert result["scope_effect"]["of_which_new_in_new_build"] == 4
    added = result["added"]
    assert added["expansion_set_ids"] == 2 and added["expansion_set_collectible"] == 1 and added["enchantments"] == 1
    assert added["playable_standard_like"] == 2 and added["in_other_game_modes"] == 1
    assert result["removed"]["ids"] == ["GONE"]
    groups = result["changed"]["cause_groups"]
    assert groups == {"expansion_set_record": 1, "text_artifact_only": 1, "gameplay_field_change_collectible_other_sets": 2,
                      "gameplay_field_change_noncollectible": 1, "non_gameplay_metadata_only": 1}
    changed = {c["id"] for c in result["changed"]["collectible_substantive_changes"]}
    assert changed == {"NUM", "BALANCE", "BE_OLD"}
    assert result["changed"]["identity_changes"]["dbf_id_changed"] == 0


def test_comparison_script_reproduces_the_committed_report(tmp_path):
    out = tmp_path / "compare.json"
    subprocess.run([sys.executable, "-I", "reports/card_metadata_2/compare_snapshots.py", "--output", str(out)],
                   check=True, capture_output=True, cwd=ROOT)
    committed = ROOT / "reports/card_metadata_2/compare_snapshots.json"
    assert out.read_bytes() == committed.read_bytes()
    refuse = subprocess.run([sys.executable, "-I", "reports/card_metadata_2/compare_snapshots.py", "--output", str(out)],
                            capture_output=True, cwd=ROOT)
    assert refuse.returncode != 0


def test_committed_comparison_pins_the_headline_numbers():
    report = json.loads((ROOT / "reports/card_metadata_2/compare_snapshots.json").read_text(encoding="utf-8"))
    assert report["ids"]["added"] == 369 and report["ids"]["removed"] == 1
    assert report["new_set_totals"]["new_collectible"] == 135 and report["new_set_totals"]["new_full"] == 300
    assert report["old_collectible_file"]["records_identical_to_old_snapshot"] is True
    assert report["changed"]["identity_changes"]["dbf_id_changed"] == 0


# ---------------------------------------------------------------- coverage logic
class _Parsed:
    def __init__(self, triggers=(), kinds=()):
        self.trigger_sentences = tuple(triggers)
        self.clauses = tuple(type("C", (), {"kind": k}) for k in kinds)


def fake_parse(text):
    if "Whenever" in text:
        return _Parsed(triggers=[text])
    if "weird" in text:
        return _Parsed(kinds=["OPAQUE"])
    return _Parsed(kinds=["DAMAGE"])


def test_text_status_levels_are_distinct():
    base = {"id": "A", "type": "MINION", "name": "a", "cardClass": "MAGE", "cost": 1, "attack": 1, "health": 1}
    assert text_status(None, fake_parse) is TextStatus.MISSING_ID
    assert text_status({**base, "text": ""}, fake_parse) is TextStatus.EMPTY_TEXT_VANILLA
    assert text_status({**base, "text": "", "mechanics": ["DEATHRATTLE"]}, fake_parse) is TextStatus.EMPTY_TEXT_WITH_EFFECT_TAG
    assert text_status({**base, "text": "Deal 1"}, fake_parse) is TextStatus.TEXT_PARSED
    assert text_status({**base, "text": "Whenever x"}, fake_parse) is TextStatus.TEXT_UNPARSED_TRIGGER
    assert text_status({**base, "text": "weird thing"}, fake_parse) is TextStatus.TEXT_UNPARSED_OPAQUE
    no_class = {k: v for k, v in base.items() if k != "cardClass"}
    assert text_status({**no_class, "text": "Deal 1"}, fake_parse) is TextStatus.TEXT_PARSED     # completeness is separate
    assert missing_fields(no_class) == ("MISSING_CLASS",)


def test_status_counts_weight_by_appearance_and_report_levels_separately():
    base = {"type": "MINION", "name": "a", "cardClass": "MAGE", "cost": 1, "attack": 1, "health": 1}
    cards = {"P": {**base, "id": "P", "text": "Deal 1"}, "T": {**base, "id": "T", "text": "Whenever x"},
             "N": {k: v for k, v in {**base, "id": "N", "text": "Deal 2"}.items() if k != "cardClass"}}
    result = status_counts({"P": 5, "T": 3, "N": 1, "GONE": 1}, cards.get, fake_parse, engine_ids={"P"})
    assert result["appearances"] == 10 and result["unique_ids"] == 4
    assert result["status_appearances"] == {"MISSING_ID": 1, "TEXT_PARSED": 6, "TEXT_UNPARSED_TRIGGER": 3}
    assert result["level_appearances"] == {"resolved": 9, "complete": 8, "text_meaningful": 9, "parse_complete": 6, "engine_declared": 5}
    assert result["incomplete_field_appearances"] == {"MISSING_CLASS": 1}


def test_entities_read_nested_board_cards_and_flat_zones():
    state = {
        "self_player": {"board": [{"card": {"card_id": "S1"}}], "locations": [], "weapon": {"card_id": "W1"}, "hero_power": {"card_id": "H1"}},
        "opponent": {"board": [{"card": {"card_id": "O1"}}, {"card": {}}], "locations": [{"card": {"card_id": "L1"}}]},
        "self_hand": [{"card_id": "C1"}], "opponent_known_cards": ["R1"],
    }
    assert sorted(entities(state)) == sorted([
        ("self_board", "S1"), ("self_weapon", "W1"), ("self_hero_power", "H1"), ("opp_board", "O1"),
        ("opp_location", "L1"), ("hand", "C1"), ("opp_revealed", "R1")])


def test_text_features_screen_what_the_text_cannot_say():
    spell = {"id": "S", "type": "SPELL", "mechanics": ["DISCOVER"], "text": "<b>Discover</b> a random spell. Whenever you draw, gain {0}."}
    assert {"pool_not_in_text", "runtime_value_in_text", "stateful_keyword"} <= special_cases(spell)
    assert {"tag:DISCOVER", "type:SPELL", "verb:discover", "verb:random", "verb:trigger_sentence"} <= families(spell)
    assert special_cases({"id": "V", "type": "MINION", "text": "Deal 3 damage."}) == frozenset()


# ---------------------------------------------------------------- compatibility and isolation
PINNED_SHA256 = {
    "data/cards/standard_current_enUS.json": "c767c303baad170e52ee5f901ba00e8b0880eb4f0e3aa47d9fdea4fcf0bdcb34",
    "data/cards/source_snapshots/cards_collectible_20261001_enUS.json": "d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930",
    "data/cards/standard_roots_20261001_enUS.json": "1820a2f3b78539929e267a7da68e3a91d2275528ba969ed2540d778735198915",
    "data/cards/standard_scope_20261001.json": "adc6ae328d5d5db9edc911fb307af4d571492144aab0e11061f480167cfc32cb",
    "data/cards/standard_sets.json": "fd454733401f01c0bd3502491ad91aed503793e0df85468a8156167d72ff3ac5",
    "configs/standard_profile.json": "5e1280193459698d7df7f864bfa561977b93df982508e024976bf84cc4437f57",
}


@pytest.mark.parametrize("relative", sorted(PINNED_SHA256))
def test_model_side_artifacts_are_unchanged(relative):
    digest = hashlib.sha256((ROOT / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert digest == PINNED_SHA256[relative], f"{relative} changed; CARD-METADATA-2 must not touch model-side artifacts"


def test_standard_profile_does_not_reference_the_new_layer():
    profile = (ROOT / "configs/standard_profile.json").read_text(encoding="utf-8")
    assert "card_metadata" not in profile and "255130" not in profile


def test_nothing_outside_the_layer_imports_it():
    pattern = re.compile(r"\b(?:from|import)\s+manamind\.card_metadata\b|\bfrom\s+manamind\s+import\s+card_metadata\b")
    offenders = [str(path.relative_to(ROOT)) for path in (ROOT / "src").rglob("*.py")
                 if "card_metadata" not in path.parts and pattern.search(path.read_text(encoding="utf-8"))]
    assert offenders == []


def test_catalog_and_vocabulary_never_read_the_snapshot_directory():
    for name in ("catalog.py", "vocabulary.py"):
        source = (ROOT / "src/manamind/cards" / name).read_text(encoding="utf-8")
        assert "card_metadata" not in source


def test_loading_the_layer_does_not_change_the_model_catalog():
    from manamind.cards.catalog import CardCatalog

    before = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json").to_dict()
    CardMetadata.load()
    assert CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json").to_dict() == before


def test_a_card_in_the_full_snapshot_is_not_automatically_standard_legal(new):
    catalog_ids = {c["id"] for c in json.loads((ROOT / "data/cards/standard_current_enUS.json").read_text(encoding="utf-8"))["cards"]}
    be_new = [r["id"] for r in new.records() if r.get("set") == "BE" and r.get("collectible")]
    assert len(be_new) == 135 and len(set(be_new) - catalog_ids) > 100        # present in metadata, absent from the Standard profile


# ---------------------------------------------------------------- fetch tool
def test_fetch_tool_helpers_are_deterministic_and_validate_input(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import fetch_card_metadata_snapshot as fetch
    finally:
        sys.path.pop(0)
    raw = json.dumps([{"id": "A"}, {"id": "B"}]).encode()
    assert fetch.deterministic_gzip(raw) == fetch.deterministic_gzip(raw)
    assert gzip.decompress(fetch.deterministic_gzip(raw)) == raw
    assert len(fetch.validate(raw)) == 2
    for bad in (b"{}", b"[]", json.dumps([{"name": "x"}]).encode(), json.dumps([1]).encode()):
        with pytest.raises(SystemExit):
            fetch.validate(bad)
    fetch.atomic_write_bytes(tmp_path / "x.bin", b"data")
    assert (tmp_path / "x.bin").read_bytes() == b"data" and [p.name for p in tmp_path.iterdir()] == ["x.bin"]
