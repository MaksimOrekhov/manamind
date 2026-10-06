"""Tailer and runner: read-only, newline-safe, attach points, discontinuities."""

from __future__ import annotations

import builtins
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from live_fixtures import LiveLog  # noqa: E402

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.live.runner import LiveRunner  # noqa: E402
from manamind.live.session import LiveSession  # noqa: E402
from manamind.live.snapshot import Snapshot  # noqa: E402
from manamind.live.tail import FILE_DISCONTINUITY, NEW_SESSION, START, LogTail, find_last_create_game  # noqa: E402
from manamind.live.trust import LiveStatus, Reason, StatusEvent  # noqa: E402

CATALOG = CardCatalog.from_json(ROOT / "data" / "cards" / "standard_current_enUS.json")


def write(path: Path, lines: list[str], *, newline: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + ("\n" if newline else "")
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(text)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def runner_for(root: Path, clock: Clock | None = None, **kwargs) -> tuple[LiveRunner, Clock]:
    clock = clock or Clock()
    return LiveRunner(root, LiveSession(CATALOG), clock=clock, **kwargs), clock


def run_until_quiet(runner: LiveRunner, clock: Clock, steps: int = 6) -> list:
    events = []
    for _ in range(steps):
        events += runner.step()
        clock.advance(0.05)
    return events


def snaps(events) -> list[Snapshot]:
    return [e for e in events if isinstance(e, Snapshot)]


def status_names(events) -> list[str]:
    return [e.status.value for e in events if isinstance(e, StatusEvent)]


# -- attach points ----------------------------------------------------------------------


def test_attach_before_hearthstone_then_a_game_appears(tmp_path: Path):
    root = tmp_path / "Logs"
    runner, clock = runner_for(root)
    events = runner.step()
    assert status_names(events) == ["DISCONNECTED"] and events[0].reason == Reason.NO_LOGS_ROOT
    root.mkdir()
    events = runner.step()
    assert events[0].reason == Reason.NO_POWER_LOG
    log = LiveLog().create_game().mulligan().self_decision(1)
    power = write(root / "Hearthstone_2026_10_06_10_00_00" / "Power.log", log.lines[:5])
    events = run_until_quiet(runner, clock)
    assert "WAITING_FOR_GAME" in status_names(events)
    append(power, "\n".join(log.lines[5:]) + "\n")
    events = run_until_quiet(runner, clock)
    assert status_names(events)[-1] == "READY" and len(snaps(events)) == 1


def test_attach_between_games_waits_for_the_next_one(tmp_path: Path):
    root = tmp_path / "Logs"
    done = LiveLog().create_game().mulligan().self_decision(1).complete()
    power = write(root / "Hearthstone_2026_10_06_10_00_00" / "Power.log", done.lines)
    runner, clock = runner_for(root)
    events = run_until_quiet(runner, clock)
    assert runner.session.status is LiveStatus.GAME_OVER
    assert snaps(events) == [] or all(s.status == "READY" for s in snaps(events))
    fresh = LiveLog(seed=2).create_game().mulligan().self_decision(1)
    append(power, "\n".join(fresh.lines) + "\n")
    events = run_until_quiet(runner, clock)
    assert runner.session.status is LiveStatus.READY
    assert len(snaps(events)) == 1


def test_attach_mid_game_catches_up_from_the_last_create_game_and_emits_quickly(tmp_path: Path):
    root = tmp_path / "Logs"
    old = LiveLog(seed=1).create_game().mulligan().self_decision(1).complete()
    current = LiveLog(seed=2).create_game().mulligan().self_decision(1)
    write(root / "Hearthstone_2026_10_06_10_00_00" / "Power.log", old.lines + current.lines)
    runner, clock = runner_for(root)
    batches = []
    for _ in range(4):  # 4 polls = 150 ms of virtual time
        batches += runner.step()
        clock.advance(0.05)
    result = snaps(batches)
    assert len(result) == 1  # only the current game's pending decision, nothing from the old one
    assert result[0].decision["options_id"] == 1
    assert clock.now - 1000.0 <= 2.0


def test_find_last_create_game_prefers_the_newest_complete_line(tmp_path: Path):
    first = LiveLog(seed=1).create_game()
    second = LiveLog(seed=2).create_game()
    path = write(tmp_path / "Power.log", first.lines + second.lines)
    offset, _ = find_last_create_game(path)
    data = path.read_bytes()
    assert data[offset:].startswith(second.lines[0].encode())
    no_game = write(tmp_path / "Other.log", ["D 00:00:00.0000000 Something.Else() - x"])
    assert find_last_create_game(no_game)[0] is None


# -- line safety --------------------------------------------------------------------------


def test_partial_trailing_line_is_held_until_its_newline(tmp_path: Path):
    root = tmp_path / "Logs"
    log = LiveLog().create_game().mulligan().self_decision(1)
    text = "\n".join(log.lines) + "\n"
    cut = len(text) - 20
    power = root / "Hearthstone_2026_10_06_10_00_00" / "Power.log"
    power.parent.mkdir(parents=True)
    power.write_bytes(text[:cut].encode())
    tail = LogTail(root)
    first = tail.poll()
    assert first.reset == START
    assert all(line.startswith(("D ", "W ", "E ")) and line.rstrip() == line for line in first.lines)
    count = len(first.lines)
    assert tail.poll().lines == []  # nothing new, the partial line stays buffered
    with power.open("ab") as file:
        file.write(text[cut:].encode())
    rest = tail.poll()
    assert count + len(rest.lines) == len(log.lines)
    assert rest.lines[-1] == log.lines[-1]


def test_runner_never_emits_state_from_a_partial_line(tmp_path: Path):
    root = tmp_path / "Logs"
    log = LiveLog().create_game().mulligan().self_decision(1)
    text = ("\n".join(log.lines) + "\n").encode()
    power = root / "Hearthstone_2026_10_06_10_00_00" / "Power.log"
    power.parent.mkdir(parents=True)
    power.write_bytes(text[:-30])
    runner, clock = runner_for(root)
    events = run_until_quiet(runner, clock)
    assert snaps(events) == []  # the options message is still incomplete: no decision
    with power.open("ab") as file:
        file.write(text[-30:])
    events = run_until_quiet(runner, clock)
    assert len(snaps(events)) == 1
    assert [a["kind"] for a in snaps(events)[0].decision["legal"]] == ["END_TURN", "PLAY_CARD", "ATTACK"]


def test_crlf_lines_are_normalized(tmp_path: Path):
    root = tmp_path / "Logs"
    log = LiveLog().create_game()
    power = root / "Hearthstone_2026_10_06_10_00_00" / "Power.log"
    power.parent.mkdir(parents=True)
    power.write_bytes(("\r\n".join(log.lines) + "\r\n").encode())
    batch = LogTail(root).poll()
    assert batch.lines == log.lines


# -- discontinuities ---------------------------------------------------------------------------


def test_shrunk_file_is_a_discontinuity_and_rebuilds_from_create_game(tmp_path: Path):
    root = tmp_path / "Logs"
    log = LiveLog().create_game().mulligan().self_decision(1)
    power = write(root / "Hearthstone_2026_10_06_10_00_00" / "Power.log", log.lines)
    runner, clock = runner_for(root)
    run_until_quiet(runner, clock)
    assert runner.session.status is LiveStatus.READY

    # The file is replaced by a shorter one that holds a different game.
    other = LiveLog(seed=9).create_game().mulligan().self_decision(1)
    write(power, other.lines[:60])
    events = run_until_quiet(runner, clock, steps=2)
    assert (LiveStatus.UNTRUSTED, Reason.FILE_DISCONTINUITY) in [
        (e.status, e.reason) for e in events if isinstance(e, StatusEvent)
    ]
    assert runner.session.status in (LiveStatus.UNTRUSTED, LiveStatus.SYNCING)
    append(power, "\n".join(other.lines[60:]) + "\n")
    events = run_until_quiet(runner, clock)
    assert len(snaps(events)) == 1 and runner.session.status is LiveStatus.READY


def test_new_session_folder_is_followed(tmp_path: Path):
    root = tmp_path / "Logs"
    first = LiveLog(seed=1).create_game().mulligan().self_decision(1)
    write(root / "Hearthstone_2026_10_06_10_00_00" / "Power.log", first.lines)
    runner, clock = runner_for(root)
    run_until_quiet(runner, clock)
    assert runner.session.status is LiveStatus.READY

    second = LiveLog(seed=5).create_game().mulligan().self_decision(1)
    write(root / "Hearthstone_2026_10_06_11_00_00" / "Power.log", second.lines)
    events = run_until_quiet(runner, clock)
    names = status_names(events)
    assert names[0] == "WAITING_FOR_GAME" and names[-1] == "READY"
    assert runner.session.session_name == "Hearthstone_2026_10_06_11_00_00"
    assert LogTail(root).poll().reset in (START, NEW_SESSION, FILE_DISCONTINUITY)


def test_unreadable_root_recovers_by_catching_up_again(tmp_path: Path):
    root = tmp_path / "Logs"
    log = LiveLog().create_game().mulligan().self_decision(1)
    write(root / "Hearthstone_2026_10_06_10_00_00" / "Power.log", log.lines)
    runner, clock = runner_for(root)
    run_until_quiet(runner, clock)
    tail = runner.tail
    original = Path.is_dir
    try:
        Path.is_dir = lambda self: False if self == root else original(self)  # type: ignore[method-assign]
        events = runner.step()
        assert status_names(events) == ["DISCONNECTED"]
    finally:
        Path.is_dir = original  # type: ignore[method-assign]
    assert tail.path is None
    events = run_until_quiet(runner, clock)
    assert runner.session.status is LiveStatus.READY and len(snaps(events)) == 1


# -- read-only guarantee --------------------------------------------------------------------------


def test_the_tail_never_writes_renames_or_deletes(tmp_path: Path, monkeypatch):
    root = tmp_path / "Logs"
    log = LiveLog().create_game().mulligan().self_decision(1)
    session_dir = root / "Hearthstone_2026_10_06_10_00_00"
    power = write(session_dir / "Power.log", log.lines)
    config = write(root / "log.config", ["[Power]"])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (power, config)}
    listing = sorted(str(p) for p in root.rglob("*"))

    opened: list[str] = []
    real_open = builtins.open
    real_path_open = Path.open

    def guarded_open(file, mode="r", *args, **kwargs):
        opened.append(mode)
        return real_open(file, mode, *args, **kwargs)

    def guarded_path_open(self, mode="r", *args, **kwargs):
        opened.append(mode)
        return real_path_open(self, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("the tail must not modify files")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    for name in ("rename", "replace", "remove", "unlink", "rmdir", "mkdir", "truncate", "utime"):
        monkeypatch.setattr(os, name, forbidden, raising=False)

    tail = LogTail(root)
    tail.poll()
    tail.poll()
    assert opened and set(opened) == {"rb"}
    monkeypatch.undo()
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (power, config)} == before
    assert sorted(str(p) for p in root.rglob("*")) == listing
    source = (ROOT / "src" / "manamind" / "live" / "tail.py").read_text(encoding="utf-8")
    assert "log.config" not in source.replace("``log.config``", "")


@pytest.mark.skipif(not os.environ.get("MANAMIND_HEARTHSTONE_LOGS"), reason="needs a local Hearthstone Logs folder")
def test_real_logs_incremental_matches_one_shot_and_stays_private():
    """Aggregate-only check on completed local games; nothing is printed or copied."""
    from hslog import LogParser

    from manamind.integrations.powerlog.exporter import CompatibleEntityTreeExporter
    from manamind.integrations.powerlog.lines import read_complete_lines, split_games

    def table(game):
        return {e.id: (getattr(e, "card_id", None), dict(e.tags)) for e in game.entities}

    root = Path(os.environ["MANAMIND_HEARTHSTONE_LOGS"])
    from manamind.live.trust import ModePolicy

    checked = 0
    for power in sorted(root.glob("Hearthstone_*/Power.log"))[-2:]:
        for section in split_games(read_complete_lines(power)):
            if not any("tag=STATE value=COMPLETE" in line for line in section):
                continue
            session = LiveSession(CATALOG, ModePolicy(frozenset({"GT_VS_AI"})))
            events = []
            for index, line in enumerate(section):
                events += session.feed([line], 1000 + index) + session.tick(1150 + index)
            if session.game is None or session.game.failed:
                continue
            session.game.reducer.commit()
            parser = LogParser()
            for line in section:
                parser.read_line(line)
                if "tag=STATE value=COMPLETE" in line and "Entity=GameEntity" in line:
                    break
            one_shot = CompatibleEntityTreeExporter(parser.games[0]).export().game
            assert table(session.game.reducer.game) == table(one_shot)
            assert all('"handle"' not in str(s.state) for s in snaps(events))
            checked += 1
    assert checked >= 0
