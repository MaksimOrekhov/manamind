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

from manamind.live.desktop import DesktopApi, inline_app, window_geometry
from manamind.live.localization import CardNames
from manamind.live.presentation import OverlayFeed, PresentationEvent
from manamind.live.recommendation import RankedAction, Recommendation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import webview

    feed = OverlayFeed(CardNames.load(ROOT / "data/localization/card_names_253932.json"))
    api = DesktopApi(feed, args.output.parent / "smoke_preferences.json")
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
            state = {"self_hand": [{"card_id": "CS2_029"}], "self_player": {"hand_size": 1, "board": [], "locations": []},
                     "opponent": {"board": [], "locations": []}}
            snap = SimpleNamespace(game_key="smoke", seq=1, decision={"options_id": 1}, state_hash="smoke",
                                   status="READY", active_player="SELF", state=state)
            ranked = Recommendation(("smoke", 1, 1, "smoke"), 1, 1, (RankedAction(0, 1.0, {
                "type": "PLAY_CARD", "card_id": "CS2_029", "hand_index": 0, "target_kind": "HERO",
                "target_side": "OPPONENT", "play_position": 0}),), 1.0)
            feed.publish(PresentationEvent("recommendation", snapshot=snap, recommendation=ranked))
            time.sleep(.4)
            text = window.evaluate_js("document.querySelector('main').innerText")
            result["ru_source_target"] = "Огненный шар" in text and "ГЕРОЙ ПРОТИВНИКА" in text
            window.evaluate_js("document.querySelector('.language').click()")
            time.sleep(.3)
            result["en_switch"] = "Fireball" in window.evaluate_js("document.querySelector('.item__source').innerText")
            api.set_preferences({"language": "en", "opacity": .65, "collapsed": True})
            result["collapsed_height"] = window.height
            result["native_opacity"] = float(window.native.Opacity)
            result["native_topmost"] = bool(window.native.TopMost)
            result["native_border_style"] = str(window.native.FormBorderStyle)
            api.set_preferences({"collapsed": False})
            result["restored_height"] = window.height
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
    print(json.dumps(result))
    if result.get("failure_class") or not result.get("ru_source_target"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
