"""Opt-in Windows host smoke: opens its own overlay briefly, then closes it.

No Hearthstone access or input automation. Not part of headless pytest/CI.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_REQUIRED_CHECKS = (
    "app_mounted", "ru_source_target", "warning_ru", "en_switch", "warning_en",
    "collapsed_height_ok", "native_opacity_ok", "native_topmost", "native_borderless",
    "restored_height_ok", "feedback_button_visible", "feedback_saved_once",
    "feedback_resets_on_new_decision", "game_over_clears_advice", "no_http_server",
)


from manamind.live.desktop import DesktopApi, inline_app, window_geometry
from manamind.live.localization import CardNames
from manamind.live.presentation import OverlayFeed, PresentationEvent
from manamind.live.recommendation import RankedAction, Recommendation


def smoke_passed(result: dict) -> bool:
    return not result.get("failure_class") and all(result.get(name) is True for name in _REQUIRED_CHECKS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import webview

    feed = OverlayFeed(CardNames.load(ROOT / "data/localization/card_names_253932.json",
                                       ROOT / "data/cards/standard_current_enUS.json"))
    feedback_calls = []
    api = DesktopApi(feed, args.output.parent / "smoke_preferences.json",
                     flag_current=lambda: feedback_calls.append(True) is None)
    api.set_preferences({"language": "ru", "collapsed": False, "opacity": .92})
    window = webview.create_window("ManaMind host smoke", html=inline_app(ROOT / "apps/overlay-ui/dist"),
                                   js_api=api, on_top=True, frameless=True, easy_drag=False,
                                   min_size=(340, 56), **window_geometry(api._settings, webview.screens))
    api._window = window
    window.events.shown += api._apply
    window.events.moved += api._moved
    window.events.resized += api._resized
    stop = threading.Event()
    result = {}

    def heartbeat():
        while not stop.wait(.2):
            feed.heartbeat()

    def check():
        pulse = threading.Thread(target=heartbeat)
        pulse.start()
        try:
            window.events.loaded.wait(15)
            # The Vue module needs a DOM and the pywebviewready bridge.
            time.sleep(.8)
            result["app_mounted"] = bool(window.evaluate_js("document.querySelector('header')"))
            state = {"self_hand": [{"card_id": "JAIL_913"}],
                     "self_player": {"hand_size": 1, "board": [], "locations": []},
                     "opponent": {"board": [{"card": {"card_id": "TIME_005t6"}, "board_position": 1,
                                              "current_attack": 6, "current_health": 6, "max_health": 6,
                                              "divine_shield": False, "lifesteal": False}], "locations": []}}
            snap = SimpleNamespace(game_key="smoke", seq=1, decision={"options_id": 1}, state_hash="smoke",
                                   status="READY", active_player="SELF", state=state)
            ranked = Recommendation(("smoke", 1, 1, "smoke"), 1, 2, (RankedAction(0, 1.0, {
                "type": "PLAY_CARD", "card_id": "JAIL_913", "source_card_id": "JAIL_913",
                "source_kind": "SPELL", "hand_index": 0, "target_kind": "MINION",
                "target_side": "OPPONENT", "target_card_id": "TIME_005t6", "target_board_position": 1,
                "target_attack": 6, "target_health": 6, "play_position": 0}),
                RankedAction(1, 0.0, {"type": "END_TURN", "play_position": 0})), 1.0)
            feed.publish(PresentationEvent("recommendation", snapshot=snap, recommendation=ranked))
            time.sleep(.4)
            text = window.evaluate_js("document.querySelector('main').innerText")
            result["ru_source_target"] = "Задержи их!" in text and "СУЩЕСТВО ПРОТИВНИКА" in text
            ru_warning = window.evaluate_js("document.querySelector('.item__risk-warning')?.innerText || ''")
            result["warning_ru"] = "Внимание" in ru_warning and "Похищение жизни" in ru_warning
            window.evaluate_js("document.querySelector('.language').click()")
            time.sleep(.3)
            en_text = window.evaluate_js("document.querySelector('.item__source').innerText")
            result["en_switch"] = "Hold Them Off!" in en_text
            en_warning = window.evaluate_js("document.querySelector('.item__risk-warning')?.innerText || ''")
            result["warning_en"] = "Warning" in en_warning and "Lifesteal" in en_warning
            api.set_preferences({"language": "en", "opacity": .65, "collapsed": True})
            result["collapsed_height"] = int(window.height)
            result["collapsed_height_ok"] = result["collapsed_height"] == 56
            result["native_opacity"] = float(window.native.Opacity)
            result["native_opacity_ok"] = abs(result["native_opacity"] - .65) <= .02
            result["native_topmost"] = bool(window.native.TopMost)
            result["native_border_style"] = str(window.native.FormBorderStyle)
            result["native_borderless"] = "none" in result["native_border_style"].lower()
            api.set_preferences({"collapsed": False})
            time.sleep(.2)
            result["restored_height"] = int(window.height)
            result["restored_height_ok"] = result["restored_height"] > 56
            flag = window.evaluate_js("document.querySelector('.feedback-flag')")
            result["feedback_button_visible"] = bool(flag)
            window.evaluate_js("document.querySelector('.feedback-flag').click()")
            time.sleep(.3)
            flagged_text = window.evaluate_js("document.querySelector('.feedback-flag').innerText")
            result["feedback_saved_once"] = (
                ("Отмечено" in flagged_text or "Saved for review" in flagged_text)
                and window.evaluate_js("document.querySelector('.feedback-flag').disabled")
                and len(feedback_calls) == 1
            )
            feed.publish(PresentationEvent("recommendation", snapshot=snap, recommendation=ranked))
            time.sleep(.3)
            result["feedback_resets_on_new_decision"] = not window.evaluate_js(
                "document.querySelector('.feedback-flag').disabled")
            feed.publish(PresentationEvent("status", status="GAME_OVER"))
            time.sleep(.4)
            result["game_over_clears_advice"] = window.evaluate_js("document.querySelectorAll('.item').length") == 0
            result["no_http_server"] = window._server is None
        except Exception as error:
            result["failure_class"] = type(error).__name__
        finally:
            stop.set()
            pulse.join()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            window.destroy()

    webview.start(func=check, gui="edgechromium", debug=False, http_server=False)
    failed = [name for name in _REQUIRED_CHECKS if result.get(name) is not True]
    result["failed_checks"] = failed
    print(json.dumps(result))
    if not smoke_passed(result):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
