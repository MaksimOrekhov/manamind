"""Recorder, deterministic replay, and the command-line tools."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from live_fixtures import CANARIES, LiveLog  # noqa: E402
from power_log_fixtures import SECRET_NAME  # noqa: E402

import live_replay  # noqa: E402
import live_state  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.live.recorder import Recorder  # noqa: E402
from manamind.live.replay import replay_game, verify_replay  # noqa: E402
from manamind.live.runner import LiveRunner  # noqa: E402
from manamind.live.session import LiveSession  # noqa: E402
from manamind.live.snapshot import Snapshot  # noqa: E402

CARDS = ROOT / "data" / "cards" / "standard_current_enUS.json"
CATALOG = CardCatalog.from_json(CARDS)
SESSION = "Hearthstone_2026_10_06_10_00_00"
REAL_SLEEP = time.sleep  # live_state.time is the time module; keep the original


class Clock:
    def __init__(self) -> None:
        self.now = 500.0

    def __call__(self) -> float:
        return self.now


def play_two_decisions(tmp_path: Path, *, chunk: int = 11) -> tuple[Path, Path, list[Snapshot]]:
    """Grow a log in small pieces so the recorded trace has real batch boundaries."""
    root = tmp_path / "Logs"
    power = root / SESSION / "Power.log"
    power.parent.mkdir(parents=True)
    power.write_text("", encoding="utf-8")
    log = LiveLog(canaries=True).create_game().mulligan().begin_turn(1)
    log.canary_reveals()
    log.options()
    log.send_option(1)
    log.batch(["TAG_CHANGE Entity=2 tag=RESOURCES_USED value=1"]).finish_list()
    log.options()
    log.send_option(0)
    log.batch(["TAG_CHANGE Entity=GameEntity tag=TURN value=2"]).finish_list()

    recorder = Recorder(tmp_path / "rec", catalog_path=CARDS)
    clock = Clock()
    runner = LiveRunner(root, LiveSession(CATALOG), recorder, clock=clock)
    found: list[Snapshot] = []
    for start in range(0, len(log.lines), chunk):
        with power.open("a", encoding="utf-8", newline="\n") as file:
            file.write("\n".join(log.lines[start:start + chunk]) + "\n")
        for _ in range(4):
            found += [e for e in runner.step() if isinstance(e, Snapshot)]
            clock.now += 0.05
    for _ in range(6):
        found += [e for e in runner.step() if isinstance(e, Snapshot)]
        clock.now += 0.05
    return root, tmp_path / "rec", found


def game_dir(rec: Path) -> Path:
    dirs = [d for d in (rec / SESSION).iterdir() if d.is_dir()]
    assert len(dirs) == 1
    return dirs[0]


def test_recording_layout_and_privacy(tmp_path: Path):
    _, rec, found = play_two_decisions(tmp_path)
    assert len(found) == 2
    directory = game_dir(rec)
    assert len(directory.name) == 16 and directory.name == found[0].game_key[:16]
    assert {p.name for p in directory.iterdir()} >= {
        "slice.log", "tail_trace.jsonl", "snapshots.jsonl", "meta.json"
    }
    # the raw slice is private and may hold names; everything else must not
    assert SECRET_NAME in (directory / "slice.log").read_text(encoding="utf-8")
    for name in ("tail_trace.jsonl", "snapshots.jsonl", "meta.json", "status.jsonl"):
        text = (directory / name).read_text(encoding="utf-8")
        assert SECRET_NAME not in text and "Opponent#" not in text
        assert not any(canary in text for canary in CANARIES)
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    assert meta["opponent_identity_policy"] == "none" and meta["hslog"] and meta["catalog_sha256"]
    rows = [json.loads(r) for r in (directory / "tail_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sum(r["n"] for r in rows) == len((directory / "slice.log").read_text(encoding="utf-8").splitlines())
    assert all({"t", "n"} <= set(r) for r in rows)


def test_replay_reproduces_the_state_hash_sequence(tmp_path: Path):
    _, rec, found = play_two_decisions(tmp_path)
    directory = game_dir(rec)
    identical, recorded, replayed = verify_replay(directory, CATALOG)
    assert identical and recorded == replayed == [s.state_hash for s in found]
    live_rows = [{**s.to_dict(), "session": None} for s in found]
    assert [s.to_dict() for s in replay_game(directory, CATALOG)] == live_rows  # all fields, not only the hash


def test_replay_is_independent_of_how_the_log_was_chunked(tmp_path: Path):
    for chunk, name in ((3, "a"), (40, "b")):
        _, rec, found = play_two_decisions(tmp_path / name, chunk=chunk)
        identical, recorded, _ = verify_replay(game_dir(rec), CATALOG)
        # Large batches can contain an options message and the action that answers it, which
        # supersedes the message; whatever was emitted live must be reproduced exactly.
        assert identical and len(recorded) == len(found)


def test_replay_detects_a_changed_sequence(tmp_path: Path):
    _, rec, _ = play_two_decisions(tmp_path)
    directory = game_dir(rec)
    snapshots = directory / "snapshots.jsonl"
    rows = snapshots.read_text(encoding="utf-8").splitlines()
    snapshots.write_text("\n".join(rows[:1]) + "\n", encoding="utf-8")
    identical, _, _ = verify_replay(directory, CATALOG)
    assert not identical


# -- command line ------------------------------------------------------------------------------


def run_state_cli(monkeypatch, tmp_path: Path, argv: list[str], capsys, root: Path) -> tuple[int, str, str]:
    calls = {"n": 0}

    def sleep(seconds):
        calls["n"] += 1
        REAL_SLEEP(0.02)
        if calls["n"] > 12:
            raise KeyboardInterrupt

    monkeypatch.setattr(live_state.time, "sleep", sleep)
    code = live_state.main(["--logs-root", str(root), "--poll-ms", "10", "--cards", str(CARDS), *argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def make_log_root(tmp_path: Path, **kwargs) -> Path:
    root = tmp_path / "Logs"
    log = LiveLog(canaries=True, **kwargs).create_game().mulligan().begin_turn(1)
    log.canary_reveals()
    log.options()
    power = root / SESSION / "Power.log"
    power.parent.mkdir(parents=True)
    power.write_text("\n".join(log.lines) + "\n", encoding="utf-8", newline="\n")
    return root


def test_cli_json_prints_sanitized_snapshots_only(monkeypatch, tmp_path: Path, capsys):
    root = make_log_root(tmp_path)
    code, out, err = run_state_cli(monkeypatch, tmp_path, ["--json"], capsys, root)
    assert code == 0 and err == ""
    rows = [json.loads(line) for line in out.splitlines()]
    snapshots = [r for r in rows if r["schema"] == "manamind.live.snapshot/1"]
    assert len(snapshots) == 1 and snapshots[0]["status"] == "READY"
    assert any(r["schema"] == "manamind.live.status/1" for r in rows)
    assert SECRET_NAME not in out and "Opponent#" not in out
    assert not any(canary in out for canary in CANARIES)


def test_cli_human_output_and_default_mode_gate(monkeypatch, tmp_path: Path, capsys):
    root = make_log_root(tmp_path)
    code, out, _ = run_state_cli(monkeypatch, tmp_path, [], capsys, root)
    assert code == 0 and "[#1]" in out and "legal:" in out and "status: READY" in out
    assert SECRET_NAME not in out

    solo = make_log_root(tmp_path / "solo", game_type="GT_VS_AI", format_type="FT_WILD")
    _, out, _ = run_state_cli(monkeypatch, tmp_path, ["--json"], capsys, solo)
    assert "manamind.live.snapshot/1" not in out and "UNSUPPORTED_MODE" in out
    _, out, _ = run_state_cli(monkeypatch, tmp_path, ["--json", "--allow-mode", "GT_VS_AI"], capsys, solo)
    assert "manamind.live.snapshot/1" in out


def test_cli_rejects_unknown_developer_modes_and_missing_root(capsys):
    with pytest.raises(SystemExit):
        live_state.main(["--logs-root", "x", "--allow-mode", "GT_RANKED"])
    with pytest.raises(SystemExit):
        live_state.main([])
    capsys.readouterr()


def test_cli_logs_root_from_environment(monkeypatch, tmp_path: Path, capsys):
    root = make_log_root(tmp_path)
    monkeypatch.setenv("MANAMIND_HEARTHSTONE_LOGS", str(root))
    monkeypatch.setattr(live_state.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt))
    assert live_state.main(["--json", "--cards", str(CARDS)]) == 0
    capsys.readouterr()


def test_cli_errors_print_only_the_exception_class(monkeypatch, tmp_path: Path, capsys):
    root = make_log_root(tmp_path)

    def broken(self):
        raise RuntimeError(SECRET_NAME)

    monkeypatch.setattr(LiveRunner, "step", broken)
    code = live_state.main(["--logs-root", str(root), "--cards", str(CARDS)])
    out = capsys.readouterr()
    assert code == 1 and "RuntimeError" in out.err
    assert SECRET_NAME not in out.out + out.err


def test_cli_record_then_replay_tool(monkeypatch, tmp_path: Path, capsys):
    root = make_log_root(tmp_path)
    rec = tmp_path / "rec"
    code, _, _ = run_state_cli(monkeypatch, tmp_path, ["--json", "--record", str(rec)], capsys, root)
    assert code == 0
    directory = game_dir(rec)
    assert live_replay.main([str(directory), "--cards", str(CARDS)]) == 0
    assert "IDENTICAL" in capsys.readouterr().out
    assert live_replay.main([str(tmp_path / "missing"), "--cards", str(CARDS)]) == 2
    assert "FileNotFoundError" in capsys.readouterr().err
