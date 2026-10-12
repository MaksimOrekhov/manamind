"""Optional Windows Vue/WebView2 host. One process, no recommendation HTTP server."""
from __future__ import annotations

import json
import re
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from .localization import CardNames
from .presentation import OverlayFeed, PresentationEvent


def inline_app(dist: Path) -> str:
    """Inline the trusted Vite bundle so pywebview never starts its file server."""
    html = (dist / "index.html").read_text(encoding="utf-8")

    def asset(name: str) -> str:
        path = (dist / name.removeprefix("./")).resolve()
        if not path.is_relative_to(dist.resolve()):
            raise ValueError("Invalid overlay asset")
        return path.read_text(encoding="utf-8")

    html = re.sub(r'<script type="module"[^>]*src="([^"]+)"[^>]*></script>',
                  lambda m: '<script type="module">' + asset(m[1]).replace("</script", "<\\/script") + "</script>", html)
    html = re.sub(r'<link rel="stylesheet"[^>]*href="([^"]+)"[^>]*>',
                  lambda m: "<style>" + asset(m[1]) + "</style>", html)
    if 'src="' in html or 'href="' in html:
        raise ValueError("Overlay must be self-contained")
    return html


def preferences(payload: dict) -> dict:
    opacity = payload.get("opacity", 0.92)
    if type(opacity) not in (int, float) or not 0.55 <= opacity <= 1:
        opacity = 0.92
    result = {"language": "en" if payload.get("language") == "en" else "ru",
              "opacity": opacity, "collapsed": payload.get("collapsed") is True}
    for key in ("x", "y", "width", "height"):
        value = payload.get(key)
        if type(value) is int and -20000 <= value <= 20000:
            result[key] = value
    result["width"] = max(340, min(700, result.get("width", 420)))
    result["height"] = max(400, min(1000, result.get("height", 640)))
    return result


def window_geometry(settings: dict, screens) -> dict:
    """Restore in logical pixels; recover onto a monitor after a resolution change."""
    width, height = settings["width"], settings["height"]
    x, y = settings.get("x", 40), settings.get("y", 120)
    screen = next((s for s in screens if s.x <= x < s.x + s.width and s.y <= y < s.y + s.height), screens[0])
    width, height = min(width, screen.width), min(height, screen.height)
    return {"x": max(screen.x, min(x, screen.x + screen.width - width)),
            "y": max(screen.y, min(y, screen.y + screen.height - height)), "width": width,
            "height": 56 if settings["collapsed"] else height}


class DesktopApi:
    """Only local presentation settings and the current-decision flag are exposed to the UI."""
    def __init__(self, feed: OverlayFeed, settings_path: Path,
                 flag_current: Callable[[], bool] | None = None) -> None:
        self._feed, self._path = feed, settings_path
        self._flag_current = flag_current
        self._window = None
        self._lock = threading.RLock()
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        self._settings = preferences(payload if isinstance(payload, dict) else {})

    def get_frame(self) -> dict:
        with self._lock:
            return {**self._feed.read(), "preferences": dict(self._settings)}

    def set_preferences(self, payload: dict) -> dict:
        with self._lock:
            # JS can change presentation only, never paths, logs, policy or actions.
            changes = {k: v for k, v in payload.items() if k in {"language", "opacity", "collapsed"}}
            self._settings = preferences({**self._settings, **changes})
            self._save()
            result = dict(self._settings)
        # WinForms resize events run on another thread; never Invoke while holding the lock.
        self._apply()
        return result

    def flag_suspicious(self, payload: dict) -> dict:
        """Reject stale UI frames before asking the runtime to revalidate the live decision."""
        if not isinstance(payload, dict) or type(payload.get("revision")) is not int:
            return {"status": "STALE"}
        frame = self._feed.read()
        if (payload.get("session") != frame["session"] or payload["revision"] != frame["revision"]
                or frame["status"] != "READY"):
            return {"status": "STALE"}
        if self._flag_current is None:
            return {"status": "UNAVAILABLE"}
        return {"status": "SAVED" if self._flag_current() else "STALE"}

    def close(self) -> None:
        self._feed.publish(PresentationEvent("status", status="DISCONNECTED", reason="APP_STOP"))
        if self._window is not None:
            self._window.destroy()

    def _apply(self) -> None:
        if self._window is None or self._window.native is None:
            return
        from System import Action
        with self._lock:
            settings = dict(self._settings)
        opacity = float(settings["opacity"])
        self._window.native.Invoke(Action(lambda: setattr(self._window.native, "Opacity", opacity)))
        self._window.resize(settings["width"], 56 if settings["collapsed"] else settings["height"])

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._settings, indent=2) + "\n", encoding="utf-8")

    def _moved(self, x, y) -> None:
        with self._lock:
            self._settings.update(x=round(x), y=round(y))
            self._save()

    def _resized(self, width, height) -> None:
        with self._lock:
            if not self._settings["collapsed"]:
                self._settings.update(width=round(width), height=round(height))
                self._save()


def launch_desktop(runtime, root: Path, cards_path: Path, poll_ms: int = 50) -> None:
    if sys.platform != "win32":
        raise RuntimeError("The desktop overlay requires Windows / WebView2")
    import webview

    if runtime.recommender is not None:
        from manamind.models.policy_inputs import representation_of
        if representation_of(runtime.recommender.policy) != 2:
            raise ValueError("The Vue overlay requires Policy v2; use console/Tkinter for older checkpoints")

    html = inline_app(root / "apps/overlay-ui/dist")
    names = CardNames.load(root / "data/localization/card_names_253932.json", cards_path)
    feed = OverlayFeed(names, policy_available=runtime.recommender is not None)
    api = DesktopApi(feed, runtime.collector.raw_output.parent / "overlay_preferences.json",
                     flag_current=runtime.flag_active_recommendation)
    # The settings file contains window coordinates/language only; no game data.
    window = webview.create_window("ManaMind · Policy v2", html=html, js_api=api, on_top=True,
                                   frameless=True, easy_drag=False, min_size=(340, 56),
                                   background_color="#12161f", **window_geometry(api._settings, webview.screens))
    if window is None:
        raise RuntimeError("Overlay window unavailable")
    api._window = window
    stopped = threading.Event()
    window.events.closed += stopped.set
    window.events.shown += api._apply
    window.events.moved += api._moved
    window.events.resized += api._resized
    runtime.on_event = feed.publish
    feed.publish(PresentationEvent("status", status=runtime.live.session.status.value))
    if runtime.recommender is None:
        feed.publish(PresentationEvent("unavailable", reason="CHECKPOINT_UNAVAILABLE"))

    def run() -> None:
        while not stopped.is_set():
            feed.heartbeat()
            runtime.step()
            feed.heartbeat()
            stopped.wait(poll_ms / 1000)

    worker = threading.Thread(target=run, name="manamind-live")
    # Launch only when WebView2 initialized, so failed host startup starts no poller.
    try:
        webview.start(func=worker.start, gui="edgechromium", debug=False, http_server=False)
    finally:
        stopped.set()
        if worker.ident is not None:
            worker.join()  # Finish any active collector write before the caller's runtime.finish().
        runtime.on_event = None
