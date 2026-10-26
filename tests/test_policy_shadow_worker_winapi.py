"""Windows API boundary tests for the optional Policy Shadow worker."""
from __future__ import annotations

import ctypes
import json
import sys
import threading
from ctypes import wintypes
from types import SimpleNamespace

import pytest

from manamind.policy_shadow import worker as worker_module
from manamind.policy_shadow.journal import ModelShadowJournal
from manamind.policy_shadow.shadow import ShadowStats


class FakeFunction:
    def __init__(self, result):
        self.result = result
        self.argtypes = None
        self.restype = None
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def fake_winapi(monkeypatch, *, priority_result=True):
    handle = 0x12345678ABCDEF01 if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x12345678
    get_current_thread = FakeFunction(handle)
    set_thread_priority = FakeFunction(priority_result)
    kernel = SimpleNamespace(GetCurrentThread=get_current_thread, SetThreadPriority=set_thread_priority)
    calls = []

    def load_library(name, *, use_last_error):
        calls.append((name, use_last_error))
        return kernel

    monkeypatch.setattr(worker_module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(worker_module.ctypes, "WinDLL", load_library, raising=False)
    return handle, get_current_thread, set_thread_priority, calls


def test_winapi_signatures_handle_and_below_normal_priority_are_explicit(monkeypatch):
    handle, get_current_thread, set_thread_priority, calls = fake_winapi(monkeypatch)

    assert worker_module._lower_thread_priority() is True

    assert calls == [("kernel32", True)]
    assert get_current_thread.argtypes == []
    assert get_current_thread.restype is wintypes.HANDLE
    assert set_thread_priority.argtypes == [wintypes.HANDLE, ctypes.c_int]
    assert set_thread_priority.restype is wintypes.BOOL
    assert set_thread_priority.calls == [(handle, worker_module.THREAD_PRIORITY_BELOW_NORMAL)]
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert handle > 0xFFFFFFFF


def test_winapi_refusal_and_exception_are_best_effort(monkeypatch):
    _, _, set_thread_priority, _ = fake_winapi(monkeypatch, priority_result=False)
    assert worker_module._lower_thread_priority() is False
    assert len(set_thread_priority.calls) == 1

    _, _, set_thread_priority, _ = fake_winapi(monkeypatch, priority_result=OSError("denied"))
    assert worker_module._lower_thread_priority() is False
    assert len(set_thread_priority.calls) == 1


def test_non_windows_platform_does_not_load_or_call_windows_api(monkeypatch):
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("Windows API must not load on this platform")

    monkeypatch.setattr(worker_module, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(worker_module.ctypes, "WinDLL", forbidden, raising=False)

    assert worker_module._lower_thread_priority() is False
    assert called is False


def test_worker_keeps_processing_when_windows_refuses_priority(tmp_path, monkeypatch):
    fake_winapi(monkeypatch, priority_result=False)

    class Shadow:
        stats = ShadowStats()

        def score(self, snapshot, _recommendation, cancelled=lambda: None):
            return {"schema": "manamind.model_shadow/1", "models": [], "for": snapshot.state_hash}

    shadow = Shadow()
    journal = ModelShadowJournal(tmp_path / "model_shadow.jsonl")
    worker = worker_module.ModelShadowWorker(shadow, journal, threaded=True)
    snapshot = SimpleNamespace(game_key="match", seq=1, decision={"options_id": 1}, state_hash="after-priority-denial")
    worker.submit(snapshot, None)
    assert worker.flush(timeout=5)
    worker.close()

    assert shadow.stats.recorded == 1
    rows = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1 and rows[0]["event"] == "MODEL_SHADOW"


@pytest.mark.skipif(sys.platform != "win32", reason="requires the real Windows kernel32 API")
def test_real_windows_api_lowers_priority_on_a_disposable_thread():
    results = []
    thread = threading.Thread(target=lambda: results.append(worker_module._lower_thread_priority()))
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert results == [True]
