"""Player instructions, privacy and fail-closed LIVE presentation lifecycle."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from manamind.live.desktop import DesktopApi, inline_app, preferences, window_geometry
from manamind.live.instructions import board_slots, instruction
from manamind.live.localization import CardNames
from manamind.live.panel import describe_action
from manamind.live.presentation import OverlayFeed, PresentationEvent
from manamind.live.recommendation import RankedAction, Recommendation
from manamind.live.trust import LiveStatus, StatusEvent

ROOT = Path(__file__).parents[1]
NAMES = CardNames({"A": {"ruRU": "Копия", "enUS": "Copy"}, "L": {"ruRU": "Локация"}})


def state():
    return {"self_hand": [{"card_id": "A"}] * 4, "self_player": {"hand_size": 4, "board": [
        {"card": {"card_id": "A"}, "board_position": 1, "current_attack": 4, "current_health": 5},
        {"card": {"card_id": "A"}, "board_position": 3, "current_attack": 3, "current_health": 2}],
        "locations": [{"card": {"card_id": "L"}, "board_position": 2, "current_health": 2}]},
        "opponent": {"board": [{"card": {"card_id": "A"}, "board_position": 1,
                               "current_attack": 5, "current_health": 5}], "locations": []}}


def action(**fields):
    return {"type": "ATTACK", "source_kind": "MINION", "source_card_id": "A",
            "source_board_position": 3, "source_attack": 99, "source_health": 99,
            "target_kind": "MINION", "target_card_id": "A", "target_side": "OPPONENT",
            "target_board_position": 1, "target_attack": 5, "target_health": 5,
            "play_position": 0, **fields}


def recommendation():
    snap = SimpleNamespace(game_key="private_game_key", seq=4, decision={"options_id": 8},
                           state_hash="hash", status="READY", active_player="SELF", state=state())
    result = Recommendation((snap.game_key, 4, 8, "hash"), 3, 40,
                            (RankedAction(17, 7.5, action(player_name="PRIVATE_NAME")),
                             RankedAction(5, -8.0, {"type": "END_TURN", "play_position": 0})), 2.0)
    return snap, result


def test_official_names_fallbacks_and_tokens():
    names = CardNames.load(ROOT / "data/localization/card_names_253932.json")
    assert names.get("CS2_029") == "Огненный шар"
    assert names.get("CS2_029", "en") == "Fireball"
    assert names.get("HERO_01bp") != "HERO_01bp"  # hero power
    assert names.get("CS2_101t") != "CS2_101t"  # token
    assert CardNames({"A": {"enUS": "Copy"}}).get("A") == "Copy"
    assert names.get("NEW_PATCH_UNKNOWN") == "NEW_PATCH_UNKNOWN"


def test_same_cards_distinguished_by_current_stats_side_and_shared_slots():
    view = instruction(action(), state(), NAMES)
    assert "ТВОЁ СУЩЕСТВО" in view["source"] and "3/2" in view["source"] and "3-е слева" in view["source"]
    assert "СУЩЕСТВО ПРОТИВНИКА" in view["target"] and "5/5" in view["target"] and "1-е слева" in view["target"]
    assert "99" not in view["source"] and not view["warning"]
    assert [s["board_position"] for s in board_slots(state(), "SELF")] == [1, 2, 3]


def test_targeted_play_has_hand_coordinate_target_and_placement():
    play = action(type="PLAY_CARD", source_card_id="A", hand_index=3, card_type="MINION", play_position=3)
    view = instruction(play, state(), NAMES)
    assert "4-я карта слева" in view["source"]
    assert "ПРОТИВНИКА" in view["target"]
    assert "Между 2-й и 3-й" in view["placement"]
    assert "цель:" in describe_action(play, {"A": "Копия"})


@pytest.mark.parametrize(("position", "expected"), [(1, "Слева"), (4, "Справа")])
def test_edge_placements(position, expected):
    view = instruction(action(type="PLAY_CARD", hand_index=0, play_position=position), state(), NAMES)
    assert expected in view["placement"]


def test_hero_attack_power_and_location_target():
    hero = instruction(action(source_is_hero=True, source_kind="HERO", source_attack=3, source_health=12,
                              target_kind="HERO"), state(), NAMES)
    assert hero["source"] == "ТВОЙ ГЕРОЙ · 3/12" and "ГЕРОЙ ПРОТИВНИКА" in hero["target"]
    assert "0/" not in hero["target"]
    power = instruction(action(type="HERO_POWER", source_kind="HERO_POWER", target_side="SELF",
                               target_board_position=3), state(), NAMES)
    assert "СИЛА ГЕРОЯ" in power["source"] and "ТВОЁ СУЩЕСТВО" in power["target"]
    location = instruction(action(type="ACTIVATE_LOCATION", source_kind="LOCATION", source_card_id="L",
                                  source_board_position=2, target_kind="LOCATION", target_card_id="L",
                                  target_side="SELF", target_board_position=2), state(), NAMES)
    assert "ТВОЯ ЛОКАЦИЯ" in location["target"] and "2 прочности" in location["source"]


def test_unknown_inconsistent_coordinates_never_invent_left_position():
    broken = state()
    broken["self_player"]["locations"][0]["board_position"] = 3
    view = instruction(action(), broken, NAMES)
    assert "3-е слева" not in view["source"] and view["warning"]
    broken["self_player"]["hand_size"] = 5
    view = instruction(action(type="PLAY_CARD", hand_index=3, play_position=2), broken, NAMES)
    assert "4-я карта слева" not in view["source"] and "не подтвержден" in view["placement"]


def test_dto_exact_top_order_logit_no_names_hidden_state_or_handles():
    snap, result = recommendation()
    snap.state["opponent_known_cards"] = [{"card_id": "HIDDEN_CARD"}]
    snap.state["player_name"] = "PRIVATE_NAME"
    feed = OverlayFeed(NAMES)
    feed.publish(PresentationEvent("recommendation", snapshot=snap, recommendation=result))
    frame = feed.read()
    assert frame["status"] == "READY"
    assert [r["rank"] for r in frame["recommendations"]] == [1, 2]
    assert [r["logit"] for r in frame["recommendations"]] == [7.5, -8.0]
    serialized = json.dumps(frame)
    assert all(secret not in serialized for secret in ["HIDDEN_CARD", "PRIVATE_NAME", "private_game_key", "options_id", "state_hash"])
    assert frame["recommendations"][0]["action"] == {k: v for k, v in result.ranked[0].action.items() if k != "player_name"}
    feed.publish(PresentationEvent("unavailable", reason="PRIVATE_NAME"))
    assert feed.read()["reason"] == "UNAVAILABLE"


@pytest.mark.parametrize("status", ["SYNCING", "UNTRUSTED", "GAME_OVER", "DISCONNECTED", "UNAVAILABLE"])
def test_status_change_immediately_clears_advice_and_reload_has_no_history(status):
    snap, result = recommendation()
    feed = OverlayFeed(NAMES)
    feed.publish(PresentationEvent("recommendation", snapshot=snap, recommendation=result))
    feed.publish(PresentationEvent("status", status=status, reason="RECONNECT"))
    assert feed.read()["recommendations"] == [] and feed.read()["generated_at"] is None
    assert feed.read()["status"] == status


def test_mismatched_snapshot_and_worker_timeout_cannot_restore_stale_advice():
    now = [0.0]
    feed = OverlayFeed(NAMES, clock=lambda: now[0])
    snap, result = recommendation()
    feed.publish(PresentationEvent("recommendation", snapshot=snap, recommendation=replace(result, identity=("old", 4, 8, "hash"))))
    assert feed.read()["status"] == "UNAVAILABLE"
    feed.publish(PresentationEvent("recommendation", snapshot=snap, recommendation=result))
    now[0] = 3
    assert feed.read()["recommendations"] == []
    feed.heartbeat()
    assert feed.read()["recommendations"] == []  # requires a fresh structured recommendation


def test_preferences_only_control_presentation_and_recover_offscreen(tmp_path):
    api = DesktopApi(OverlayFeed(NAMES), tmp_path / "prefs.json")
    value = api.set_preferences({"language": "en", "opacity": .6, "checkpoint": "PRIVATE", "x": 123})
    assert value["language"] == "en" and value["opacity"] == .6 and "checkpoint" not in value and "x" not in value
    assert preferences({"opacity": float("nan")})["opacity"] == .92
    geometry = window_geometry(preferences({"x": 9999, "y": -9999}),
                               [SimpleNamespace(x=0, y=0, width=1280, height=720)])
    assert 0 <= geometry["x"] <= 860 and 0 <= geometry["y"] <= 80


def test_bundle_inlined_without_a_server_and_no_path_escape(tmp_path):
    (tmp_path / "bundle.js").write_text("console.log('local')")
    (tmp_path / "index.html").write_text('<script type="module" src="./bundle.js"></script>')
    assert inline_app(tmp_path) == '<script type="module">console.log(\'local\')</script>'
    (tmp_path / "index.html").write_text('<script type="module" src="../private.js"></script>')
    with pytest.raises(ValueError):
        inline_app(tmp_path)


def test_structured_runtime_status_and_missing_checkpoint_clear_feed(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_manamind import UnifiedRuntime
    session = SimpleNamespace(status=LiveStatus.READY, current_snapshot=None, reason=None)
    live = SimpleNamespace(session=session)
    feed = OverlayFeed(NAMES)
    runtime = UnifiedRuntime(live, object(), None, emit=lambda _: None, on_event=feed.publish)
    runtime._events([StatusEvent(LiveStatus.READY, None)])
    assert feed.read()["reason"] == "CHECKPOINT_UNAVAILABLE"
    session.status = LiveStatus.GAME_OVER
    runtime._events([StatusEvent(LiveStatus.GAME_OVER, None)])
    runtime._invalidate("GAME_OVER")
    assert feed.read()["status"] == "GAME_OVER"


def test_missing_policy_remains_visible_through_log_disconnect_and_sync():
    feed = OverlayFeed(NAMES, policy_available=False)
    for status in ("DISCONNECTED", "SYNCING", "UNAVAILABLE"):
        feed.publish(PresentationEvent("status", status=status))
        assert feed.read()["policy_available"] is False
        assert not feed.read()["recommendations"]
