from __future__ import annotations

import argparse
import gc
import json
import math
import platform
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from compare_reference import _make_deck
from manamind.integrations.manaengine import ManaEngineSession
from manamind.integrations.rosettastone.rosettastone import SimulatorSession

ROOT = Path(__file__).resolve().parents[3]
SEED = 7


def _memory_working_set() -> int:
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    psapi = ctypes.WinDLL("Psapi.dll", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = kernel32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.WorkingSetSize)


def _measure(fn: Callable[[], Any], count: int) -> dict[str, float]:
    samples: list[float] = []
    for _ in range(count):
        start = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "iterations": count,
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[p95_index],
    }


def _session(backend: str, deck: list[str]) -> Any:
    classes = {"player1_class": "MAGE", "player2_class": "MAGE", "shuffle": False, "random_seed": SEED}
    if backend == "RosettaStone":
        return SimulatorSession(deck, deck, **classes, random_start=False)
    return ManaEngineSession(deck, deck, **classes)


def _play_end_turns_to_terminal(backend: str, deck: list[str]) -> tuple[int, str | None]:
    session = _session(backend, deck)
    transitions = 0
    while not session.is_complete:
        action = next(row for row in session.legal_actions() if row["type"] == "END_TURN")
        session.apply_action(action)
        transitions += 1
        if transitions > 200:
            raise RuntimeError("pass-only game did not reach terminal state within 200 turn transitions")
    return transitions, session.result


def _bench_backend(name: str, deck: list[str], iterations: int) -> dict[str, Any]:
    warm = _session(name, deck)
    warm.legal_actions()
    creation = _measure(lambda: _session(name, deck), iterations)

    session = _session(name, deck)
    legal = _measure(session.legal_actions, iterations * 10)

    turn_sessions = [_session(name, deck) for _ in range(iterations)]
    end_turns = [next(row for row in s.legal_actions() if row["type"] == "END_TURN") for s in turn_sessions]
    apply_samples = []
    for current, action in zip(turn_sessions, end_turns, strict=True):
        start = time.perf_counter_ns()
        current.apply_action(action)
        apply_samples.append((time.perf_counter_ns() - start) / 1_000_000)
    ordered_apply = sorted(apply_samples)
    apply = {
        "iterations": len(ordered_apply),
        "median_ms": statistics.median(ordered_apply),
        "p95_ms": ordered_apply[min(len(ordered_apply) - 1, math.ceil(0.95 * len(ordered_apply)) - 1)],
    }

    clone: dict[str, float] | None = None
    if name == "ManaEngine":
        clone = _measure(session.clone, iterations * 20)

    games = []
    for _ in range(max(3, min(10, iterations))):
        started = time.perf_counter()
        transitions, result = _play_end_turns_to_terminal(name, deck)
        elapsed = time.perf_counter() - started
        games.append({"seconds": elapsed, "transitions": transitions, "result": result})

    game_seconds = sum(row["seconds"] for row in games)
    transition_count = sum(row["transitions"] for row in games)
    game_count = len(games)

    before = _memory_working_set()
    held = [_session(name, deck) for _ in range(max(10, iterations))]
    after = _memory_working_set()
    estimated_bytes_per_session = max(0, (after - before) // len(held))
    del held
    gc.collect()

    return {
        "session_creation": creation,
        "legal_actions": legal,
        "apply_action_end_turn": apply,
        "clone": clone,
        "working_set_delta_bytes_per_session_estimate": estimated_bytes_per_session,
        "pass_only_complete_games": {
            "iterations": game_count,
            "games_per_second": game_count / game_seconds,
            "transitions_per_second": transition_count / game_seconds,
            "mean_transitions_per_game": transition_count / game_count,
            "results": [row["result"] for row in games],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.iterations < 3:
        parser.error("--iterations must be at least 3")
    deck = _make_deck()
    results = {
        "scenario": "30-card validated Mage fixture; seeded, no shuffle; pass-only matches reach fatigue terminal",
        "seed": SEED,
        "iterations": args.iterations,
        "build_type": "Release (CMake Ninja)",
        "cpu": platform.processor() or platform.machine(),
        "os": platform.platform(),
        "backends": {
            "RosettaStone": _bench_backend("RosettaStone", deck, args.iterations),
            "ManaEngine": _bench_backend("ManaEngine", deck, args.iterations),
        },
    }
    payload = json.dumps(results, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
