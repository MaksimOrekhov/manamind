"""POLICY-GAME-RESET-RECOVERY-1: a GAME_RESET (Rewind) no longer rejects a match; stale states are still refused."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from live_fixtures import SELF_HAND, LiveLog, desc  # noqa: E402
from test_hero_state_extraction import HERO_POWER_ID  # noqa: E402
from test_live_recommendation import CATALOG  # noqa: E402

from manamind.integrations.powerlog.game_reset import STALE_REASON  # noqa: E402
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.training.real_policy import validate_example  # noqa: E402

# Every entity the fixture puts in a zone the visible state is built from, with its creation tags.
ENTITIES = {
    4: ("HERO_01", {"CARDTYPE": "HERO", "ZONE": "PLAY", "CONTROLLER": 1, "HEALTH": 30}),
    5: ("HERO_02", {"CARDTYPE": "HERO", "ZONE": "PLAY", "CONTROLLER": 2, "HEALTH": 30}),
    **{i: (card, {"ZONE": "HAND", "CONTROLLER": 1, "ZONE_POSITION": i - 5, "CARDTYPE": "MINION"})
       for i, card in SELF_HAND.items()},
    **{i: ("", {"ZONE": "DECK", "CONTROLLER": 1}) for i in (10, 11, 12)},
    **{i: ("", {"ZONE": "HAND", "CONTROLLER": 2, "ZONE_POSITION": i - 19}) for i in (20, 21, 22)},
    **{i: ("", {"ZONE": "DECK", "CONTROLLER": 2}) for i in (30, 31, 32)},
    40: ("HERO_POWER_X", {"CARDTYPE": "HERO_POWER", "ZONE": "PLAY", "CONTROLLER": 1, "EXHAUSTED": 0}),
    41: ("CS2_231", {"CARDTYPE": "MINION", "ZONE": "PLAY", "CONTROLLER": 1, "ZONE_POSITION": 1, "ATK": 2, "HEALTH": 3}),
    50: ("CS2_168", {"CARDTYPE": "MINION", "ZONE": "PLAY", "CONTROLLER": 2, "ZONE_POSITION": 1, "ATK": 1, "HEALTH": 2}),
}


def reset_block(*, omit: tuple[int, ...] = (), override: dict[int, dict] | None = None) -> list[str]:
    lines = ["BLOCK_START BlockType=GAME_RESET Entity=GameEntity EffectCardId= EffectIndex=0 Target=0 SubOption=-1",
             "    RESET_GAME"]
    for entity_id, (card, tags) in ENTITIES.items():
        if entity_id in omit:
            continue
        lines.append(f"    FULL_ENTITY - Updating {desc(entity_id, tags['ZONE'], tags.get('ZONE_POSITION', 0), card, tags['CONTROLLER'])} CardID={card}")
        for name, value in {**tags, **(override or {}).get(entity_id, {}), "ENTITY_ID": entity_id}.items():
            lines.append(f"        tag={name} value={value}")
    lines.append("BLOCK_END")
    return lines


def game(reset: list[str] | None, *, decision_after: bool = True) -> list[str]:
    log = LiveLog().create_game().mulligan()
    log.begin_turn(1)
    log.raw("GameState", "DebugPrintOptions", "id=1")
    log.options_id = 1                                               # the next fixture options packet is id=2
    log.raw("GameState", "DebugPrintOptions", "option 0 type=END_TURN mainEntity= error=INVALID errorParam=")
    log.raw("GameState", "DebugPrintOptions",
            f"option 1 type=POWER mainEntity={desc(40, 'PLAY', 0, HERO_POWER_ID, 1)} error=NONE errorParam=")
    log.raw("GameState", "SendOption", "selectedOption=1 selectedSubOption=-1 selectedTarget=0 selectedPosition=0")
    log.p(f"BLOCK_START BlockType=PLAY Entity={desc(40, 'PLAY', 0, HERO_POWER_ID, 1)} "
          "EffectCardId= EffectIndex=0 Target=0 SubOption=-1")
    log.p("BLOCK_END")
    if reset is not None:
        log.batch(reset)
        log.finish_list()
    if decision_after:
        log.self_decision(3)
        log.send_option(0)                                           # END_TURN
    log.p("TAG_CHANGE Entity=2 tag=PLAYSTATE value=WON")
    log.p("TAG_CHANGE Entity=3 tag=PLAYSTATE value=LOST")
    log.complete()
    return log.lines


def test_a_match_with_a_reset_is_no_longer_rejected_and_counts_it():
    rows, summary = extract_match(game(reset_block(), decision_after=False), CATALOG)
    assert len(rows) == 1 and summary["final_result"] == 1.0 and summary["skip_reasons"] == {}


def test_a_decision_after_a_full_reset_is_kept_and_reads_the_reset_values():
    rows, summary = extract_match(game(reset_block(override={50: {"ATK": 5}})), CATALOG)
    assert STALE_REASON not in summary["skip_reasons"]
    assert [row["decision_id"].rsplit(":", 1)[1] for row in rows] == ["1", "2"]
    after = rows[1]
    assert after["state"]["opponent"]["board"][0]["current_attack"] == 5          # the rewound value, not the old 1
    assert after["final_result"] == 1.0 and rows[0]["game_id"] == after["game_id"]
    for row in rows:
        validate_example(row)


def test_an_entity_the_reset_did_not_resend_makes_the_following_decision_untrusted():
    rows, summary = extract_match(game(reset_block(omit=(50,))), CATALOG)
    assert [row["decision_id"].rsplit(":", 1)[1] for row in rows] == ["1"]      # before the reset: unchanged
    assert summary["skip_reasons"] == {STALE_REASON: 1}
    assert summary["skipped_decisions"][0]["decision_id"].endswith(":2")


def test_a_hidden_opponent_card_not_resent_also_blocks():
    _, summary = extract_match(game(reset_block(omit=(21,))), CATALOG)            # opponent hand: hand_size depends on it
    assert summary["skip_reasons"] == {STALE_REASON: 1}


def test_without_a_reset_nothing_changes():
    rows, summary = extract_match(game(None), CATALOG)
    assert len(rows) == 2 and summary["skip_reasons"] == {}


def test_recovered_and_skipped_rows_pass_the_strict_dataset_audit(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    from import_policy_power_log import save_match
    from manamind.training.real_policy import SKIP_REASONS, audit_dataset

    assert STALE_REASON in SKIP_REASONS
    rows, summary = extract_match(game(reset_block(omit=(50,))), CATALOG)
    save_match(rows, summary, tmp_path / "policy")
    audit = audit_dataset(tmp_path / "policy", CATALOG)
    assert audit["privacy_checks"] == "PASS"
