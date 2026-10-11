"""The rules-text grammar: reviewed templates only, everything else opaque, no card-ID branching."""

from __future__ import annotations

import json
import re
from pathlib import Path

from manamind.outcome.grammar import board_profile, normalise, parse_text, trigger_events
from manamind.outcome.texts import TextSource

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "cards" / "standard_current_enUS.json"


def kinds(text: str) -> list[str]:
    return [clause.kind for clause in parse_text(text).clauses]


def test_sentences_follow_periods_and_keyword_lines_not_layout_wrapping():
    assert normalise("<b>Prepare</b>\nGive a minion +5/+5 and <b>Lifesteal</b>.") == [
        "Prepare", "Give a minion +5/+5 and Lifesteal"]
    assert normalise("[x]Deal $5 damage\nto a minion. If it dies,\nrestore #5 Health to\nthe enemy hero.") == [
        "Deal $5 damage to a minion", "If it dies, restore #5 Health to the enemy hero"]
    assert normalise("[x]<b>Prepare</b>, <b>Taunt</b>\n<b>Deathrattle:</b> Restore #6 Health\nto your hero.") == [
        "Prepare, Taunt", "Deathrattle: Restore #6 Health to your hero"]


def test_reviewed_templates_parse_with_their_numbers():
    heal = parse_text("Restore #5 Health.").clauses[0]
    assert (heal.kind, heal.amount, heal.selector.mode, heal.selector.kinds) == ("HEAL", 5, "CHOSEN", "CHARACTER")
    buff = parse_text("Give a minion +5/+5 and <b>Lifesteal</b>.").clauses[0]
    assert (buff.kind, buff.attack, buff.health, buff.keywords) == ("BUFF", 5, 5, ("lifesteal",))
    several = parse_text("Give a minion +2/+2, <b>Reborn</b>, and <b>Taunt</b>.").clauses[0]
    assert several.keywords == ("reborn", "taunt")
    purge = parse_text("Destroy all minions with 5 or more Attack.").clauses[0]
    assert (purge.kind, purge.attack_filter, purge.selector.mode) == ("DESTROY", ("GE", 5), "ALL")
    assert parse_text("Gain 5 Armor.").clauses[0].amount == 5


def test_extra_words_make_a_sentence_opaque_instead_of_being_ignored():
    assert kinds("Deal $3 damage to a minion and your hero.") == ["OPAQUE"]
    assert kinds("Deal $3 damage to a random enemy.") == ["OPAQUE"]
    assert parse_text("Deal $3 damage to a random enemy.").clauses[0].category == "RANDOM_OUTCOME"
    assert kinds("Give a minion +1/+1 until end of turn.") == ["OPAQUE"]
    assert parse_text("Rewind").clauses[0].category == "KEYWORD_UNDEFINED"


def test_combo_and_outcast_are_play_time_effects_not_inert_triggers():
    assert kinds("Combo: Deal 2 damage.") == ["OPAQUE"]
    assert parse_text("Outcast: Draw a card.").trigger_sentences == ()


def test_trigger_paragraph_swallows_its_continuation_sentences():
    parsed = parse_text("Deathrattle: Restore #6 Health to your hero. Summon a random 6-Cost minion.")
    assert parsed.clauses == () and len(parsed.trigger_sentences) == 2
    after_keyword = parse_text("Deathrattle: Draw a card.\nTaunt")
    assert [c.kind for c in after_keyword.clauses] == ["KEYWORDS"]


def test_board_profile_separates_play_time_text_triggers_and_statics():
    triggers, statics = board_profile("<b>Taunt</b>\n<b>Battlecry:</b> Draw a card.\nAt the end of your turn, "
                                      "gain +1 Attack.\nHas +6 Attack while damaged.")
    assert triggers == ("At the end of your turn, gain +1 Attack",)
    assert statics == ("Has +6 Attack while damaged",)


def test_trigger_condition_classes():
    assert trigger_events("At the end of your turn, give +1") == {"TURN_END"}
    assert trigger_events("After you cast a spell, deal 1 damage") == {"SPELL_CAST"}
    assert trigger_events("Deathrattle: Draw a card") == {"DEATH_SELF"}
    assert "DAMAGE" in trigger_events("Whenever this minion takes damage, gain +2")
    assert trigger_events("Whenever a minion gains Attack, deal 1") >= {"BUFF"}
    assert trigger_events("Whenever you spend your last Mana Crystal, draw") == {"MANA_SPENT"}
    assert trigger_events("Whenever the moon is full, howl") == {"ANY"}          # unreadable: assume anything


def test_every_pinned_catalog_text_parses_without_error():
    assert len(TextSource.from_files(CATALOG)) > 1000
    selected = {"DAMAGE", "HEAL", "BUFF", "GRANT", "DESTROY", "DESTROY_HIGHEST"}
    for record in json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]:
        text = record.get("text") or ""
        board_profile(text)
        for clause in parse_text(text).clauses:
            assert clause.selector is not None or clause.kind not in selected


def test_no_card_id_is_hard_coded_in_the_forecaster_sources():
    card_id = re.compile(r"""["'](?:[A-Z]{2,6}_)?[A-Z]{0,4}\d{2,4}[a-z]?[A-Za-z0-9_]*["']|["'][A-Z]{2,6}_\d{2,}\w*["']""")
    for name in ("forecast", "world", "grammar", "compare", "texts", "model", "verify"):
        source = (ROOT / "src" / "manamind" / "outcome" / f"{name}.py").read_text(encoding="utf-8")
        assert not card_id.findall(source), (name, card_id.findall(source))


def test_battlecry_continuation_is_not_a_static_rule_but_a_later_description_is():
    battlecry = "[x]<b>Battlecry:</b> Give a\nfriendly minion <b>Reborn</b>.\nIf it already has <b>Reborn</b>,\nsummon a copy of it."
    assert board_profile(battlecry) == ((), ())
    assert board_profile("Battlecry: Draw a card. Your other minions have +1 Attack.") == (
        (), ("Your other minions have +1 Attack",))
