"""Live session: settle gate, trust states, SELF resolution, modes, privacy boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hslog import LogParser

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from live_fixtures import (  # noqa: E402
    CANARIES,
    CANARY_OPP_HAND,
    LiveLog,
)
from power_log_fixtures import SECRET_NAME  # noqa: E402

import collect_power_logs as cpl  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.exporter import CompatibleEntityTreeExporter  # noqa: E402
from manamind.integrations.powerlog.lines import inspect_segment  # noqa: E402
from manamind.live.reducer import GameReducer  # noqa: E402
from manamind.live.session import LiveSession  # noqa: E402
from manamind.live.snapshot import Snapshot  # noqa: E402
from manamind.live.trust import LiveStatus, ModePolicy, Reason, StatusEvent  # noqa: E402

CATALOG = CardCatalog.from_json(ROOT / "data" / "cards" / "standard_current_enUS.json")


def make(policy: ModePolicy | None = None, **kwargs) -> LiveSession:
    return LiveSession(CATALOG, policy, **kwargs)


def drive(session: LiveSession, lines: list[str], now: int = 1000) -> list:
    """Feed one batch, then let the message-idle window pass."""
    events = session.feed(lines, now)
    events += session.tick(now + 150)
    return events


def snapshots(events) -> list[Snapshot]:
    return [event for event in events if isinstance(event, Snapshot)]


def statuses(events) -> list[tuple[str, str | None]]:
    return [(e.status.value, e.reason) for e in events if isinstance(e, StatusEvent)]


def decision_log(**kwargs) -> LiveLog:
    return LiveLog(**kwargs).create_game().mulligan().self_decision(1)


# -- cadence and the settle gate -------------------------------------------------


def test_one_snapshot_per_settled_self_options_message():
    session = make()
    log = decision_log()
    events = drive(session, log.lines)
    assert len(snapshots(events)) == 1
    snap = snapshots(events)[0]
    assert snap.status == "READY" and snap.decision["options_id"] == 1
    assert session.status is LiveStatus.READY

    # The player acts, the next options message is a second decision.
    log.lines.clear()
    log.send_option(1)
    log.batch(["TAG_CHANGE Entity=2 tag=RESOURCES_USED value=1"]).finish_list()
    log.options()
    events = drive(session, log.lines, now=3000)
    assert [s.decision["options_id"] for s in snapshots(events)] == [2]
    assert [s.seq for s in snapshots(events)] == [2]


def test_no_snapshot_during_opponent_turn():
    session = make()
    log = LiveLog().create_game().mulligan().begin_turn(1, self_turn=False)
    log.options(legal=False)  # every option has an error: nothing to decide
    events = drive(session, log.lines)
    assert snapshots(events) == []
    assert session.status is LiveStatus.SYNCING


def test_superseded_options_message_is_dropped():
    session = make()
    log = decision_log()
    log.send_option(1)  # the player already acted: the message is stale
    log.batch(["TAG_CHANGE Entity=2 tag=RESOURCES_USED value=1"])
    events = drive(session, log.lines)
    assert snapshots(events) == []


def test_unsettled_message_waits_for_the_ui_then_emits_once():
    session = make()
    log = LiveLog().create_game().mulligan()
    log.batch([
        "TAG_CHANGE Entity=GameEntity tag=TURN value=1",
        "TAG_CHANGE Entity=2 tag=CURRENT_PLAYER value=1",
        "TAG_CHANGE Entity=3 tag=CURRENT_PLAYER value=0",
    ])  # task list queued, never finished yet
    log.options()
    events = drive(session, log.lines)
    assert snapshots(events) == []  # the screen has not caught up
    events = session.feed([f"D 20:59:00.0000000 PowerProcessor.EndCurrentTaskList() - m_currentTaskList={log.q}"], 2000)
    events += session.tick(2200)
    assert len(snapshots(events)) == 1
    assert snapshots(session.tick(9000)) == []  # once per options id


def test_settle_timeout_makes_the_game_untrusted_then_resyncs():
    session = make()
    log = LiveLog().create_game().mulligan()
    log.batch(["TAG_CHANGE Entity=GameEntity tag=TURN value=1",
               "TAG_CHANGE Entity=2 tag=CURRENT_PLAYER value=1",
               "TAG_CHANGE Entity=3 tag=CURRENT_PLAYER value=0"])
    log.options()
    events = drive(session, log.lines, now=1000)
    assert snapshots(events) == []
    events = session.tick(1000 + 15_000)
    assert (LiveStatus.UNTRUSTED.value, Reason.SETTLE_TIMEOUT) in statuses(events)
    assert snapshots(events) == []
    # The automatic rebuild leaves the game in SYNCING; the stale message is never offered.
    assert session.status is LiveStatus.SYNCING
    assert snapshots(session.tick(40_000)) == []


def test_unfinished_game_start_is_not_an_event():
    session = make()
    assert drive(session, ["D 20:00:01.0000000 GameState.DebugPrintPower() - CREATE_GAME"]) == []
    assert session.status is LiveStatus.WAITING_FOR_GAME


# -- SELF identification ---------------------------------------------------------


def test_self_rules_agree_and_snapshot_is_from_self_perspective():
    snap = snapshots(drive(make(), decision_log().lines))[0]
    assert snap.active_player == "SELF"
    assert [card["card_id"] for card in snap.state["self_hand"]] == ["CS2_029", "CS2_023", "CS2_024"]
    assert snap.state["self_player"]["hand_size"] == 3
    assert snap.state["opponent"]["hand_size"] == 3


def test_self_rules_disagree_is_untrusted():
    log = LiveLog().create_game()
    # The client sent a mulligan choice that belongs to player 2, but player 1 shows its hand.
    log.raw("GameState", "SendChoices", "id=1 ChoiceType=MULLIGAN")
    log.raw("GameState", "SendChoices", "  m_chosenEntities[0]=[entityName=X id=20 zone=HAND zonePos=1 cardId= player=2]")
    log.self_decision(1)
    session = make()
    events = drive(session, log.lines)
    assert snapshots(events) == []
    assert (session.status, session.reason) == (LiveStatus.UNTRUSTED, Reason.SELF_AMBIGUOUS)


def test_self_unknown_without_any_evidence_is_untrusted():
    log = LiveLog().create_game()
    for entity_id in (6, 7, 8):  # empty SELF hand: nothing identifies the local side
        log.p(f"TAG_CHANGE Entity={entity_id} tag=ZONE value=GRAVEYARD")
    log.begin_turn(1)
    log.raw("GameState", "DebugPrintOptions", "id=1")
    log.raw("GameState", "DebugPrintOptions", "option 0 type=END_TURN mainEntity= error=NONE errorParam=")
    session = make()
    events = drive(session, log.lines)
    assert snapshots(events) == []
    assert (session.status, session.reason) == (LiveStatus.UNTRUSTED, Reason.SELF_AMBIGUOUS)


def test_self_is_remembered_when_the_hand_later_empties():
    session = make()
    log = decision_log()
    assert len(snapshots(drive(session, log.lines))) == 1
    log.lines.clear()
    log.send_option(1)
    log.batch([f"TAG_CHANGE Entity={e} tag=ZONE value=GRAVEYARD" for e in (6, 7, 8)]).finish_list()
    log.options()
    assert len(snapshots(drive(session, log.lines, now=3000))) == 1
    assert session.status is LiveStatus.READY


# -- trust state machine -------------------------------------------------------------


def test_status_transitions_and_no_decision_outside_ready():
    session = make()
    seen: list[LiveStatus] = []
    log = decision_log()
    for event in drive(session, log.lines):
        if isinstance(event, StatusEvent):
            seen.append(event.status)
        if isinstance(event, Snapshot):
            assert session.status is LiveStatus.READY and event.status == "READY"
    assert seen == [LiveStatus.SYNCING, LiveStatus.READY]

    events = drive(session, [log.complete().lines[-1]], now=5000)
    assert statuses(events) == [("GAME_OVER", None)]
    assert snapshots(events) == []  # no decision after the game ended

    # A new game restarts the cycle: SYNCING then READY.
    fresh = decision_log(seed=2)
    events = drive(session, fresh.lines, now=8000)
    assert [s for s, _ in statuses(events)] == ["SYNCING", "READY"]

    # tail driven states
    assert statuses(session.disconnected(Reason.NO_LOGS_ROOT)) == [("DISCONNECTED", Reason.NO_LOGS_ROOT)]
    assert statuses(session.connected()) == [("WAITING_FOR_GAME", None)]
    assert statuses(session.file_discontinuity(True)) == [("UNTRUSTED", Reason.FILE_DISCONTINUITY)]


def test_reconnect_create_game_with_turn_is_syncing_until_the_next_decision():
    session = make()
    log = LiveLog(turn_in_header=3).create_game().mulligan().self_decision(3)
    events = session.feed(log.lines[:30], 1000)
    assert (LiveStatus.SYNCING.value, Reason.RECONNECT) in statuses(events)
    events = drive(session, log.lines[30:])
    assert [s for s, _ in statuses(events)] == ["READY"]
    assert len(snapshots(events)) == 1


def test_game_reset_returns_to_syncing_and_next_decision_is_ready_again():
    session = make()
    log = decision_log()
    drive(session, log.lines)
    log.lines.clear()
    log.batch([
        "BLOCK_START BlockType=GAME_RESET Entity=GameEntity EffectCardId= EffectIndex=0 Target=0 SubOption=-1",
        "BLOCK_END",
    ]).finish_list()
    events = drive(session, log.lines, now=3000)
    assert (LiveStatus.SYNCING.value, Reason.GAME_RESET) in statuses(events)
    log.lines.clear()
    log.options()
    events = drive(session, log.lines, now=4000)
    assert session.status is LiveStatus.READY and len(snapshots(events)) == 1


def test_unknown_entity_and_parse_errors_are_untrusted_with_stable_reasons():
    log = decision_log()
    # Insert a change for an entity that was never created, before the options message.
    index = max(i for i, line in enumerate(log.lines) if "DebugPrintOptions() - id=" in line)
    broken = log.lines[:index] + [
        "D 20:30:00.0000000 GameState.DebugPrintPower() - TAG_CHANGE Entity=999 tag=ZONE value=HAND"
    ] + log.lines[index:]
    session = make()
    events = drive(session, broken)
    assert snapshots(events) == []
    assert (session.status, session.reason) == (LiveStatus.UNTRUSTED, Reason.ENTITY_UNKNOWN)

    malformed = decision_log().lines[:]
    malformed.insert(40, "D 20:30:00.0000000 GameState.DebugPrintPower() - BLOCK_START BlockType=NOT_A_BLOCK_TYPE")
    session = make()
    drive(session, malformed)
    assert (session.status, session.reason) == (LiveStatus.UNTRUSTED, Reason.PARSE_ERROR)


def test_unknown_game_tag_name_is_counted_and_ignored():
    log = decision_log()
    log.lines.insert(60, "D 20:30:00.0000000 GameState.DebugPrintPower() - TAG_CHANGE Entity=41 tag=BRAND_NEW_TAG value=1")
    session = make()
    events = drive(session, log.lines)
    assert len(snapshots(events)) == 1
    assert session.game.reducer.skipped_unknown_tags == 1


def test_spectator_markers_are_refused():
    session = make()
    lines = ["D 20:00:00.0000000 ================== Start Spectator Game ==================".replace(
        "================== Start Spectator Game ==================", "================== Start Spectator Game")]
    session.feed(lines, 1)
    events = drive(session, decision_log().lines, now=1000)
    assert snapshots(events) == []
    assert (session.status, session.reason) == (LiveStatus.WAITING_FOR_GAME, Reason.SPECTATOR)


# -- modes -----------------------------------------------------------------------------


@pytest.mark.parametrize("game_type,format_type", [("GT_VS_AI", "FT_WILD"), ("GT_RANKED", "FT_WILD"), ("GT_CASUAL", "FT_STANDARD")])
def test_other_modes_are_rejected_by_default(game_type, format_type):
    session = make()
    events = drive(session, decision_log(game_type=game_type, format_type=format_type).lines)
    assert snapshots(events) == []
    assert (session.status, session.reason) == (LiveStatus.WAITING_FOR_GAME, Reason.UNSUPPORTED_MODE)
    assert session.game.lines == session.game.lines[:1]  # nothing from the game is kept


def test_solo_ai_only_with_the_explicit_developer_option():
    lines = decision_log(game_type="GT_VS_AI", format_type="FT_WILD").lines
    assert snapshots(drive(make(), lines)) == []
    allowed = make(ModePolicy(frozenset({"GT_VS_AI"})))
    assert len(snapshots(drive(allowed, lines))) == 1
    with pytest.raises(ValueError):
        ModePolicy(frozenset({"GT_CASUAL"}))


def test_missing_or_conflicting_mode_is_ambiguous():
    session = make()
    events = drive(session, decision_log(game_type=None).lines)
    assert snapshots(events) == []
    assert session.game.mode_state != "OK"

    conflicting = decision_log().lines[:]
    index = next(i for i, line in enumerate(conflicting) if "FormatType=" in line)
    conflicting.insert(index + 1, conflicting[index].replace("FT_STANDARD", "FT_WILD"))
    session = make()
    assert snapshots(drive(session, conflicting)) == []
    assert (session.status, session.reason) == (LiveStatus.WAITING_FOR_GAME, Reason.MODE_AMBIGUOUS)


# -- hidden information and privacy -------------------------------------------------


def _all_text(events) -> str:
    return "\n".join(
        e.to_json() if isinstance(e, Snapshot) else json.dumps(e.to_dict()) for e in events
    )


def test_opponent_hidden_identities_never_leave_the_bridge():
    log = LiveLog(canaries=True).create_game().mulligan().begin_turn(1)
    log.canary_reveals()          # OVERRIDE_HISTORY reveal and SHOW_ENTITY followed by HIDE_ENTITY
    log.opponent_hand_identity()  # an identity in the opponent hand that the importer would expose
    log.options()
    events = drive(make(), log.lines)
    assert len(snapshots(events)) == 1
    text = _all_text(events)
    for canary in CANARIES:
        assert canary not in text
    state = snapshots(events)[0].state
    assert state["opponent_known_cards"] == []
    assert state["opponent"]["secret_count"] == 1  # count only
    assert state["opponent"]["hand_size"] == 3 and state["opponent"]["deck_size"] == 4


def test_canaries_are_real_the_offline_policy_would_expose_them():
    """Guard against a vacuous privacy test: the raw log does carry the opponent identity."""
    log = LiveLog(canaries=True).create_game().mulligan().begin_turn(1)
    log.opponent_hand_identity()
    log.options()
    session = make(parity_view=True)  # importer exposure rules
    events = drive(session, log.lines)
    assert CANARY_OPP_HAND in _all_text(events)


def test_no_entity_ids_inside_the_game_state():
    snap = snapshots(drive(make(), decision_log().lines))[0]
    state_text = json.dumps(snap.state)
    for key in ('"handle"', '"entity_id"', '"id"'):
        assert key not in state_text
    # handles exist only in the decision side channel
    assert any("handle" in json.dumps(action) for action in snap.decision["legal"])


def test_decision_exposes_only_server_validated_actions_with_visible_ids():
    snap = snapshots(drive(make(), decision_log().lines))[0]
    kinds = [a["kind"] for a in snap.decision["legal"]]
    assert kinds == ["END_TURN", "PLAY_CARD", "ATTACK"]  # option 2 has an error: excluded
    play = snap.decision["legal"][1]
    assert play["source"] == {"handle": 6, "card_id": "CS2_029"}
    assert play["targets"] == [{"handle": 50, "card_id": "CS2_168"}]  # public minion


def test_player_names_never_appear_in_output_or_errors():
    log = LiveLog(canaries=True).create_game().mulligan()
    log.lines.insert(40, f"D 20:30:00.0000000 GameState.DebugPrintPower() - TAG_CHANGE Entity={SECRET_NAME} tag=ZONE value=HAND")
    log.begin_turn(1).options()
    session = make()
    events = drive(session, log.lines)
    text = _all_text(events) + repr(events) + (session.reason or "")
    assert SECRET_NAME not in text and "Opponent#0001" not in text
    assert session.reason is not None  # the malformed input failed closed

    clean = _all_text(drive(make(), decision_log().lines))
    assert SECRET_NAME not in clean and "SecretPlayer" not in clean and "Opponent#" not in clean


def test_snapshot_schema_and_state_hash():
    snap = snapshots(drive(make(session_name="Hearthstone_2026_01_01_00_00_00"), decision_log().lines))[0]
    payload = json.loads(snap.to_json())
    assert payload["schema"] == "manamind.live.snapshot/1"
    assert {"seq", "status", "game_key", "game_type", "format", "client_build", "turn",
            "active_player", "state", "decision", "state_hash"} <= set(payload)
    assert payload["session"] == "Hearthstone_2026_01_01_00_00_00"
    import hashlib

    canonical = json.dumps(payload["state"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert payload["state_hash"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    again = snapshots(drive(make(), decision_log().lines))[0]
    assert again.state_hash == snap.state_hash  # deterministic


# -- parity with the collector and the importer ----------------------------------------


def test_game_key_equals_the_collectors_start_key():
    log = decision_log()
    snap = snapshots(drive(make(), log.lines))[0]
    assert snap.game_key == inspect_segment(log.lines).start_key
    assert snap.game_key == cpl.inspect_segment(log.lines).start_key


def test_weapon_durability_matches_the_corrected_importer():
    from import_power_log import _card_features

    log = LiveLog(weapon=True).create_game().mulligan().self_decision(1)
    snap = snapshots(drive(make(), log.lines))[0]
    live_weapon = snap.state["self_player"]["weapon"]
    assert live_weapon["current_durability"] == 1  # HEALTH 4 - DAMAGE 3

    parser = LogParser()
    for line in log.lines:
        parser.read_line(line)
    game = CompatibleEntityTreeExporter(parser.games[0]).export().game
    weapon = next(e for e in game.entities if getattr(e, "card_id", None) == "CS2_080")
    assert _card_features(weapon, CATALOG).current_durability == live_weapon["current_durability"]


def test_live_state_matches_the_importer_state_under_the_importer_policy():
    from import_power_log import _to_visible_state
    from dataclasses import asdict

    log = decision_log()
    session = make(parity_view=True)
    snap = snapshots(drive(session, log.lines))[0]
    parser = LogParser()
    for line in log.lines:
        parser.read_line(line)
    game = CompatibleEntityTreeExporter(parser.games[0]).export().game
    expected = asdict(_to_visible_state(game, 1, CATALOG))
    assert snap.state == json.loads(json.dumps(expected))


# -- incremental == one-shot -------------------------------------------------------------


def _table(game):
    return {e.id: (getattr(e, "card_id", None), dict(e.tags)) for e in game.entities}


def test_incremental_reduction_equals_one_shot_parse():
    log = LiveLog(canaries=True, weapon=True).create_game().mulligan().begin_turn(1)
    log.canary_reveals()
    log.options()
    log.send_option(1)
    log.batch(["BLOCK_START BlockType=PLAY Entity=" + "[entityName=X id=6 zone=HAND zonePos=1 cardId=CS2_029 player=1]"
               + " EffectCardId= EffectIndex=0 Target=0 SubOption=-1",
               "    TAG_CHANGE Entity=2 tag=RESOURCES_USED value=1", "BLOCK_END"]).finish_list()
    log.options()
    log.complete()

    reducer = GameReducer()
    for line in log.lines:
        reducer.read_line(line)
        if "DebugPrintOptions() - id=" in line:
            reducer.commit()  # commit at arbitrary points, as the live loop does
    reducer.commit()

    parser = LogParser()
    for line in log.lines:
        parser.read_line(line)
    one_shot = CompatibleEntityTreeExporter(parser.games[0]).export().game
    assert _table(reducer.game) == _table(one_shot)


def test_batch_boundaries_do_not_change_the_snapshots():
    log = decision_log()
    whole = [s.state_hash for s in snapshots(drive(make(), log.lines))]
    pieces = make()
    events = []
    for chunk_start in range(0, len(log.lines), 7):
        events += pieces.feed(log.lines[chunk_start:chunk_start + 7], 1000 + chunk_start)
    events += pieces.tick(5000)
    assert [s.state_hash for s in snapshots(events)] == whole


def test_live_parsing_never_touches_the_card_database_or_the_network(monkeypatch):
    """python-hearthstone downloads its card XML on a TRANSFORMED_FROM_CARD reveal; we must not."""
    import hearthstone.cardxml as cardxml

    def forbidden(*args, **kwargs):
        raise AssertionError("card database access during live parsing")

    monkeypatch.setattr(cardxml, "_load", forbidden)
    log = LiveLog().create_game().mulligan().begin_turn(1)
    log.batch([
        "SHOW_ENTITY - Updating Entity=20 CardID=CS2_168",
        "    tag=ZONE value=HAND",
        "    tag=TRANSFORMED_FROM_CARD value=1234",
        "CHANGE_ENTITY - Updating Entity=20 CardID=CS2_231",
        "    tag=TRANSFORMED_FROM_CARD value=1234",
    ]).finish_list()
    log.options()
    events = drive(make(), log.lines)
    assert len(snapshots(events)) == 1
